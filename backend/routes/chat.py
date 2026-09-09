"""
Routes du chatbot — POST /api/v1/chat
                   GET  /api/v1/edt/classes
"""
import json
import os
import re
import unicodedata
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse

from backend.models.schemas import (
    ChatRequest, 
    ChatResponse, 
    ClassesResponse, 
    ClassInfo, 
    ClassChangeRequestCreate,
    FeedbackRequest,
    RevisionPlanCreate,
)
from backend.services.auth_service import get_current_user
from backend.services import db_service
from backend.services.router_service import route_question_api, get_available_classes, _is_edt_question, _is_campus_info_question
from backend.services.chatbot_service import detect_user_state
from backend.services.cache_service import get_semantic_cache, set_semantic_cache
from backend.services.groq_service import summarize_title, _is_global_engineering_tracks_question
from backend.services.logging_service import logger
from backend.services.limiter_service import limiter

router = APIRouter(prefix="/api/v1", tags=["Chat"])


def _resolve_user_from_token(current_user: dict) -> dict:
    user_db = db_service.find_user_by_email(current_user["email"])
    if not user_db:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user_db


def get_preferred_language(request: Request, user_db: dict) -> str:
    lang = user_db.get("language")
    if not lang:
        accept_lang = request.headers.get("accept-language", "")
        if "ar" in accept_lang.lower():
            lang = "ar"
        elif "en" in accept_lang.lower():
            lang = "en"
        else:
            lang = "fr"
    return lang


def _is_basic_conversation_question(question: str) -> bool:
    normalized = unicodedata.normalize("NFD", question or "")
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    words_text = re.sub(r"[^a-zA-Z0-9]+", " ", normalized.lower()).strip()
    tokens = set(words_text.split())

    greeting_tokens = {"bonjour", "salut", "salam", "hello", "hi", "hey", "bonsoir"}
    if 0 < len(tokens) <= 3 and tokens & greeting_tokens:
        return True

    identity_markers = [
        "qui es tu",
        "tu es qui",
        "who are you",
        "what are you",
        "que peux tu faire",
        "c est quoi ton role",
        "quel est ton role",
    ]
    return any(marker in words_text for marker in identity_markers)


@router.post("/chat/stream", summary="Streamer une question au chatbot (SSE)")
@limiter.limit("10/minute")
def chat_stream(request: Request, body: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Version streaming (Server-Sent Events) pour le chatbot.
    """
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La question est vide.")

    user_db = _resolve_user_from_token(current_user)
    if body.conversation_id and not db_service.conversation_belongs_to_user(body.conversation_id, user_db["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à cette conversation.",
        )

    language = get_preferred_language(request, user_db)
    is_edt_question = _is_edt_question(question)
    is_campus_info_question = _is_campus_info_question(question)
    is_basic_question = _is_basic_conversation_question(question)
    bypass_semantic_cache = is_basic_question or is_edt_question or is_campus_info_question or _is_global_engineering_tracks_question(question)
    
    # Check semantic cache
    semantic_cache_key = f"{language}:{question}"
    cached_answer, cached_source = (None, None) if bypass_semantic_cache else get_semantic_cache(semantic_cache_key)

    class_label = None
    if current_user.get("role") == "admin":
        class_label = body.class_label
        if not class_label and user_db:
            class_label = user_db.get("class_label")
    else:
        if user_db:
            class_label = user_db.get("class_label")

    # History
    history = []
    if body.conversation_id:
        msgs = db_service.get_messages(body.conversation_id, limit=5)
        history = [{"role": m["role"], "content": m["content"]} for m in msgs]

    user_state = detect_user_state(question, history=history, language=language)

    from backend.services.router_service import route_question_api_stream

    # Capture metadata locally for the generator closure
    final_tt = None
    rag_conf = None
    rag_score = None

    def stream_generator():
        nonlocal final_tt, rag_conf, rag_score
        full_answer = ""
        source_file = None

        if cached_answer and not history:
            # If we have a semantic cache hit and no history (simple Q&A), use it
            source_file = cached_source
            if source_file:
                yield f"data: __metadata__:{json.dumps({'source_files': source_file})}\n\n"
            
            # Stream the cached answer in small chunks to simulate natural flow
            words = cached_answer.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i+3]) + (" " if i+3 < len(words) else "")
                full_answer += chunk
                yield f"data: {chunk}\n\n"
        else:
            # On passe par le router stream
            for chunk in route_question_api_stream(question, class_label, history=history, language=language, user_state=user_state):
                if chunk:
                    if chunk.startswith("__metadata__:"):
                        try:
                            meta = json.loads(chunk.replace("__metadata__:", ""))
                            if "source_files" in meta: source_file = meta.get("source_files")
                            if "timetable" in meta: final_tt = meta.get("timetable")
                            if "rag_confidence" in meta: rag_conf = meta.get("rag_confidence")
                            if "rag_score" in meta:      rag_score = meta.get("rag_score")
                            yield f"data: {chunk}\n\n"
                        except Exception as exc:
                            logger.debug(f"Invalid stream metadata chunk ignored: {exc}")
                        continue
                    full_answer += chunk
                    yield f"data: {chunk}\n\n"

            # Cache the new answer if it was a fresh generation and not an error
            if not bypass_semantic_cache and not cached_answer and full_answer and not full_answer.startswith("❌") and not history:
                set_semantic_cache(semantic_cache_key, full_answer, source_file)

        # Sauvegarde en base après la fin du stream
        try:
            user_id = user_db["id"]
            conv_id = body.conversation_id
            if not conv_id:
                # Generate AI-summarized title for new conversations
                if os.getenv("ENABLE_TITLE_LLM", "false").lower() != "true":
                    title = (question[:40] + "...") if len(question) > 40 else question
                elif is_basic_question or is_campus_info_question or is_edt_question:
                    title = (question[:40] + "...") if len(question) > 40 else question
                else:
                    title = summarize_title(question, language)
                conv_id = db_service.create_conversation(user_id, title)

            if conv_id:
                db_service.add_message(conv_id, "user", question[:1000] + ("..." if len(question) > 1000 else ""))
                # Store detected metadata (including timetable) in the DB
                msg_metadata = {}
                if source_file: msg_metadata["source_files"] = source_file
                if final_tt:    msg_metadata["timetable"] = final_tt
                if rag_conf:    msg_metadata["rag_confidence"] = rag_conf
                if rag_score:   msg_metadata["rag_score"] = rag_score
                
                db_service.add_message(conv_id, "assistant", full_answer, source_file=source_file, metadata=msg_metadata)
                db_service.log_audit_action("chat_request", user_id, details=f"Question length: {len(question)}")
            else:
                logger.error("Unable to persist streamed chat: conversation creation failed.")
        except Exception as e:
            # Never break SSE stream on persistence failure.
            logger.error(f"Stream persistence error: {e}")
        
        # Signal de fin pour le client
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.post("/chat", response_model=ChatResponse, summary="Envoyer une question au chatbot")
@limiter.limit("10/minute")
def chat(request: Request, body: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Envoie une question au moteur RAG + EDT.
    """
    logger.info(f"[CHAT] Starting handler")
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La question est vide.")

    logger.info(f"[CHAT] Question: {question[:50]}")
    user_db = _resolve_user_from_token(current_user)
    logger.info(f"[CHAT] Resolved user")
    if body.conversation_id and not db_service.conversation_belongs_to_user(body.conversation_id, user_db["id"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé à cette conversation.",
        )

    logger.info(f"[CHAT] Getting language...")
    language = get_preferred_language(request, user_db)
    logger.info(f"[CHAT] Language: {language}")
    logger.info(f"[CHAT] Checking question types...")
    is_edt_question = _is_edt_question(question)
    logger.info(f"[CHAT] EDT check done: {is_edt_question}")
    is_campus_info_question = _is_campus_info_question(question)
    logger.info(f"[CHAT] Campus check done: {is_campus_info_question}")
    is_basic_question = _is_basic_conversation_question(question)
    logger.info(f"[CHAT] Basic check done: {is_basic_question}")
    bypass_semantic_cache = is_basic_question or is_edt_question or is_campus_info_question or _is_global_engineering_tracks_question(question)
    logger.info(f"[CHAT] Bypass cache: {bypass_semantic_cache}")
    
    # Check semantic cache
    logger.info(f"[CHAT] Getting semantic cache...")
    semantic_cache_key = f"{language}:{question}"
    cached_answer, cached_source = (None, None) if bypass_semantic_cache else get_semantic_cache(semantic_cache_key)
    logger.info(f"[CHAT] Cache check done")

    class_label = None
    user_db = _resolve_user_from_token(current_user)
    if user_db.get("role") == "admin":
        class_label = body.class_label
        if not class_label and user_db:
            class_label = user_db.get("class_label")
    else:
        if user_db:
            class_label = user_db.get("class_label")

    # History
    logger.info(f"[CHAT] Getting history...")
    history = []
    if body.conversation_id:
        msgs = db_service.get_messages(body.conversation_id, limit=5)
        history = [{"role": m["role"], "content": m["content"]} for m in msgs]
    logger.info(f"[CHAT] History retrieved: {len(history)} messages")

    logger.info(f"[CHAT] Detecting user state...")
    from backend.services.chatbot_service import detect_user_state_details
    user_state_details = detect_user_state_details(question, history=history, language=language)
    user_state = user_state_details.get("label")
    user_sentiment = user_state
    user_sentiment_confidence = user_state_details.get("confidence")
    logger.info(f"[CHAT] User state detected: {user_state} (conf: {user_sentiment_confidence})")

    if cached_answer and not history:
        logger.info(f"[CHAT] Using cached answer")
        result = {
            "answer": cached_answer,
            "source_file": cached_source,
            "class_label": class_label,
            "requires_class_selection": False
        }
    else:
        logger.info(f"[CHAT] Calling route_question_api...")
        result = route_question_api(question, class_label=class_label, history=history, language=language, user_state=user_state)
        logger.info(f"[CHAT] route_question_api returned: {str(result)[:100]}")
        # Cache if new
        if not bypass_semantic_cache and not cached_answer and result.get("answer") and not result["answer"].startswith("❌") and not history:
            set_semantic_cache(semantic_cache_key, result["answer"], result.get("source_file"))

    # Gérer la conversation en base
    conv_id = body.conversation_id
    user_id = user_db["id"]

    try:
        if not conv_id:
            logger.info("[CHAT] Creating conversation - generating title")
            # Avoid calling Groq to summarize title for FAQ/campus or EDT questions
            if os.getenv("ENABLE_TITLE_LLM", "false").lower() != "true":
                title = (question[:40] + "...") if len(question) > 40 else question
                logger.info("[CHAT] Using fast title (title LLM disabled)")
            elif is_basic_question or is_campus_info_question or is_edt_question:
                title = (question[:40] + "...") if len(question) > 40 else question
                logger.info("[CHAT] Using fast title (no Groq) for basic/campus/EDT question")
            else:
                title = summarize_title(question, language)
                logger.info("[CHAT] Title generated")
            conv_id = db_service.create_conversation(user_id, title)
        if conv_id:
            db_service.add_message(conv_id, "user", question[:1000] + ("..." if len(question) > 1000 else ""))
            # Store metadata
            msg_metadata = {}
            if result.get("source_file"): msg_metadata["source_files"] = result["source_file"]
            if result.get("timetable"):   msg_metadata["timetable"] = result["timetable"]
            if result.get("rag_confidence"): msg_metadata["rag_confidence"] = result["rag_confidence"]
            if result.get("rag_score"):      msg_metadata["rag_score"] = result["rag_score"]
            
            db_service.add_message(conv_id, "assistant", result["answer"], source_file=result.get("source_file"), metadata=msg_metadata)
            db_service.log_audit_action("chat_request", user_id, details=f"Question length: {len(question)}")
    except Exception as e:
        logger.error(f"Chat persistence error: {e}")

    if not result.get("requires_class_selection") and result.get("class_label") and result["class_label"] != class_label:
        try:
            available = get_available_classes()
            canonical_label = available.get(result["class_label"], {}).get("canonical_label", result["class_label"])
        except Exception:
            canonical_label = result["class_label"]
        db_service.update_user_class(user_id, canonical_label)

    return ChatResponse(
        answer=result["answer"],
        conversation_id=conv_id,
        class_label=result.get("class_label"),
        requires_class_selection=result.get("requires_class_selection", False),
        available_classes=result.get("available_classes", []),
        source_file=result.get("source_file"),
        timetable=result.get("timetable"),
        rag_confidence=result.get("rag_confidence"),
        rag_score=result.get("rag_score"),
        sentiment=user_sentiment,
        sentiment_confidence=user_sentiment_confidence,
    )


@router.post("/chat/feedback/{message_id}", summary="Donner un feedback sur une réponse")
def update_feedback(
    message_id: int,
    body: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """Met à jour le feedback (-1, 0, 1) d'un message."""
    user_db = _resolve_user_from_token(current_user)
    if not db_service.message_belongs_to_user(message_id, user_db["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    db_service.update_message_feedback(message_id, body.feedback)
    return {"success": True}


@router.post("/class-change-requests", summary="Demander un changement de filière")
def create_class_change_request(
    body: ClassChangeRequestCreate,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un administrateur n'a pas besoin de demande de changement de filière.",
        )

    user_db = _resolve_user_from_token(current_user)
    req = db_service.create_class_change_request(
        user_id=user_db["id"],
        requested_class_label=body.requested_class_label,
        reason=body.reason,
    )
    if not req:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Demande invalide. Vérifie la filière demandée.",
        )

    if req.get("status") == "pending_existing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Une demande de changement est déjà en attente.",
        )

    return {"success": True, "request": req}


@router.get("/class-change-requests/me", summary="Mes demandes de changement de filière")
def get_my_class_change_requests(current_user: dict = Depends(get_current_user)):
    user_db = _resolve_user_from_token(current_user)
    rows = db_service.get_class_change_requests(user_id=user_db["id"])
    return {"requests": rows}


@router.get("/edt/classes", response_model=ClassesResponse, summary="Liste des classes disponibles")
def list_classes():
    """Retourne toutes les classes ayant un emploi du temps actif publié."""
    available = get_available_classes()
    return ClassesResponse(
        classes=[
            ClassInfo(label=label, has_calendrier=False)
            for label, info in available.items()
        ]
    )


@router.get("/revision-plans", summary="Lister mes plannings de revision")
def list_my_revision_plans(current_user: dict = Depends(get_current_user)):
    user_db = _resolve_user_from_token(current_user)
    return {"plans": db_service.list_revision_plans(user_db["id"])}


@router.post("/revision-plans", summary="Sauvegarder un planning de revision")
def create_my_revision_plan(
    body: RevisionPlanCreate,
    current_user: dict = Depends(get_current_user),
):
    user_db = _resolve_user_from_token(current_user)
    plan = db_service.create_revision_plan(
        user_id=user_db["id"],
        title=body.title,
        modules=[module.model_dump() for module in body.modules],
        availability=[slot.model_dump() for slot in body.availability],
        sessions=[session.model_dump() for session in body.sessions],
    )
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de sauvegarder ce planning.",
        )
    return {"success": True, "plan": plan}


@router.delete("/revision-plans/{plan_id}", summary="Supprimer un planning de revision")
def delete_my_revision_plan(plan_id: int, current_user: dict = Depends(get_current_user)):
    user_db = _resolve_user_from_token(current_user)
    deleted = db_service.delete_revision_plan(plan_id, user_db["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Planning introuvable.")
    return {"success": True}


@router.get("/conversations", summary="Historique des conversations")
def get_conversations(current_user: dict = Depends(get_current_user)):
    """Retourne la liste des conversations de l'utilisateur connecté."""
    user_db = _resolve_user_from_token(current_user)
    convs = db_service.get_conversations(user_db["id"])
    return {"conversations": convs}


@router.get("/conversations/{conv_id}/messages", summary="Messages d'une conversation")
def get_messages(conv_id: int, current_user: dict = Depends(get_current_user)):
    """Retourne les messages d'une conversation (appartenant à l'utilisateur)."""
    user_db = _resolve_user_from_token(current_user)
    convs = db_service.get_conversations(user_db["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    messages = db_service.get_messages(conv_id)
    return {"messages": messages}


@router.delete("/conversations/{conv_id}", summary="Supprimer une conversation")
def delete_conversation(conv_id: int, current_user: dict = Depends(get_current_user)):
    """Supprime une conversation et ses messages."""
    user_db = _resolve_user_from_token(current_user)
    convs = db_service.get_conversations(user_db["id"])
    if not any(c["id"] == conv_id for c in convs):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    db_service.delete_conversation(conv_id)
    db_service.log_audit_action("conversation_deleted", user_db["id"], details=f"Conversation ID: {conv_id}")
    return {"success": True}

@router.delete("/conversations", summary="Supprimer toutes les conversations")
def delete_all_conversations(current_user: dict = Depends(get_current_user)):
    """Supprime toutes les conversations de l'utilisateur connecté (Droit à l'effacement)."""
    user_db = _resolve_user_from_token(current_user)
    db_service.delete_all_conversations(user_db["id"])
    db_service.log_audit_action("all_history_deleted", user_db["id"])
    return {"success": True}

@router.post("/chat/contest/{message_id}", summary="Contester une réponse")
def contest_message(message_id: int, current_user: dict = Depends(get_current_user)):
    """Procédure de contestation (Oversight humain)."""
    user_db = _resolve_user_from_token(current_user)
    if not db_service.message_belongs_to_user(message_id, user_db["id"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    
    db_service.log_audit_action("user_contestation", user_db["id"], details=f"Interaction ID/Message ID: {message_id}")
    return {"success": True}
