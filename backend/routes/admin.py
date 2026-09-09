"""
Routes administrateur — accès réservé au rôle admin (RBAC via JWT).

GET  /api/v1/admin/stats
GET  /api/v1/admin/conversations
POST /api/v1/admin/upload
POST /api/v1/admin/faq/rebuild
GET  /api/v1/admin/users
"""
import os
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse

from backend.models.schemas import (
    StatsResponse, 
    UploadResponse, 
    ClassChangeDecisionRequest,
    QuestionReviewRequest,
    TimetablePublishRequest,
)
from backend.services.auth_service import require_admin
from backend.services import db_service
from backend.services.rag_service import get_most_asked_questions
from backend.services.logging_service import logger

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

FAQ_DIR       = os.path.join(os.path.dirname(__file__), "..", "data", "faq")

_ALLOWED_FAQ_EXTENSIONS = {".pdf", ".txt", ".md", ".json"}


def _faq_upload_max_bytes() -> int:
    raw = (os.getenv("FAQ_UPLOAD_MAX_MB") or "10").strip()
    try:
        mb = int(raw)
    except ValueError:
        mb = 10
    mb = max(1, min(100, mb))
    return mb * 1024 * 1024


MAX_FAQ_UPLOAD_BYTES = _faq_upload_max_bytes()


def _save_upload_with_limit(file: UploadFile, dest_path: str, max_bytes: int) -> None:
    written = 0
    with open(dest_path, "wb") as handle:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Fichier trop volumineux (max {int(max_bytes / (1024 * 1024))} MB).",
                )
            handle.write(chunk)


@router.get("/stats", response_model=StatsResponse, summary="Statistiques d'utilisation")
def get_stats(admin: dict = Depends(require_admin)):
    """Retourne les métriques globales : users, conversations, messages, top questions."""
    total_users = len(db_service.get_all_users())
    total_conversations = db_service.get_total_conversations()
    total_messages = db_service.get_total_messages()

    return StatsResponse(
        total_users=total_users,
        total_conversations=total_conversations,
        total_messages=total_messages,
        top_questions=db_service.get_top_questions(limit=10),
        weak_questions=db_service.get_weak_questions_grouped(limit=20),
        feedback_stats=db_service.get_feedback_stats(),
    )


@router.get("/stats/most-asked", summary="Questions les plus posées (Semantic Cache)")
def stats_most_asked(limit: int = 10, admin: dict = Depends(require_admin)):
    """
    Retourne les questions les plus fréquentes basées sur le cache sémantique.
    """
    return {"questions": get_most_asked_questions(limit)}


@router.get("/conversations", summary="Toutes les conversations")
def get_all_conversations(admin: dict = Depends(require_admin)):
    """Retourne l'ensemble des paires Q/A pour audit."""
    pairs = db_service.get_all_qa_pairs()
    return {"qa_pairs": pairs}


@router.get("/users", summary="Liste des utilisateurs")
def get_users(query: str = "", admin: dict = Depends(require_admin)):
    """Retourne les utilisateurs avec leur activité. Filtre optionnel par email."""
    users = db_service.get_users_activity(email_query=query)
    return {"users": users}


@router.delete("/users/{user_id}", summary="Supprimer un utilisateur")
def delete_user(user_id: int, admin: dict = Depends(require_admin)):
    """Supprime un utilisateur et toutes ses données associées."""
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un administrateur ne peut pas se supprimer lui-même.",
        )

    deleted = db_service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")

    return {"success": True}


@router.get("/class-change-requests", summary="Demandes de changement de filière")
def get_class_change_requests(request_status: str = "pending", admin: dict = Depends(require_admin)):
    status_clean = (request_status or "").strip().lower()
    if status_clean not in {"pending", "approved", "rejected", "all"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Statut invalide. Utilise pending/approved/rejected/all.",
        )

    rows = db_service.get_class_change_requests(status=None if status_clean == "all" else status_clean)
    return {"requests": rows}


@router.post("/class-change-requests/{request_id}/decision", summary="Accepter ou refuser une demande")
def decide_class_change_request(
    request_id: int,
    body: ClassChangeDecisionRequest,
    admin: dict = Depends(require_admin),
):
    row = db_service.decide_class_change_request(
        request_id=request_id,
        admin_id=admin["id"],
        decision=body.decision,
        note=body.note,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demande introuvable.")
    if row.get("status") == "already_processed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette demande a déjà été traitée.",
        )
    return {"success": True, "request": row}


@router.post(
    "/upload/faq",
    response_model=UploadResponse,
    summary="Importer un document FAQ",
)
async def upload_faq(
    file: UploadFile = File(...),
    rebuild: bool = True,
    admin: dict = Depends(require_admin),
):
    """
    Upload un document dans la base de connaissance FAQ.
    Si rebuild=true, reconstruit le vectorstore Qdrant automatiquement.
    """
    safe_name = os.path.basename((file.filename or "").strip())
    if not safe_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nom de fichier invalide.",
        )

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _ALLOWED_FAQ_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Format non supporté. Attendu : {_ALLOWED_FAQ_EXTENSIONS}",
        )

    os.makedirs(FAQ_DIR, exist_ok=True)
    dest_path = os.path.join(FAQ_DIR, safe_name)
    try:
        _save_upload_with_limit(file, dest_path, MAX_FAQ_UPLOAD_BYTES)
    except HTTPException:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise
    except Exception as exc:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        logger.error(f"FAQ upload failed for '{safe_name}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible d'importer ce fichier.",
        )
    finally:
        await file.close()

    if rebuild:
        try:
            from backend.services.rag_service import rebuild_vectorstore
            rebuild_vectorstore()
            return UploadResponse(
                success=True,
                message="Document importé et vectorstore reconstruit.",
                filename=safe_name,
            )
        except Exception as exc:
            logger.error(f"FAQ rebuild failed after upload '{safe_name}': {exc}")
            return UploadResponse(
                success=True,
                message="Document importé mais reconstruction du vectorstore échouée.",
                filename=safe_name,
            )

    return UploadResponse(success=True, message="Document importé.", filename=safe_name)


@router.post("/faq/rebuild", summary="Reconstruire le vectorstore FAQ")
def rebuild_faq(admin: dict = Depends(require_admin)):
    """Force la reconstruction complète de l'index vectoriel Qdrant."""
    try:
        from backend.services.rag_service import rebuild_vectorstore
        from backend.services.cache_service import invalidate_cache
        rebuild_vectorstore()
        invalidate_cache("rag")
        return {"success": True, "message": "Vectorstore reconstruit et cache purgé."}
    except Exception as exc:
        logger.error(f"FAQ rebuild error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la reconstruction.",
        )


@router.post("/cache/flush", summary="Vider le cache Redis")
def flush_cache(admin: dict = Depends(require_admin)):
    """Vide manuellement le cache des réponses du chatbot."""
    try:
        from backend.services.cache_service import invalidate_cache
        invalidate_cache()
        return {"success": True, "message": "Cache Redis vidé avec succès."}
    except Exception as exc:
        logger.error(f"Cache flush error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la purge.",
        )


@router.post("/data/cleanup", summary="Nettoyage des vieilles données (Storage Limitation RGPD)")
def cleanup_old_data(days: int = 180, admin: dict = Depends(require_admin)):
    """
    Supprime manuellement les conversations plus vieilles que X jours.
    Ceci assure que les données ne sont pas conservées indéfiniment.
    """
    count = db_service.cleanup_old_conversations(days=days)
    return {"success": True, "deleted_count": count, "message": f"{count} conversations supprimées."}


@router.post("/faq/review", summary="Marquer une question FAQ comme traitée")
def review_faq_question(body: QuestionReviewRequest, admin: dict = Depends(require_admin)):
    """Permet à l'admin de marquer une question comme 'traitée' après ajout en base."""
    db_service.set_question_review_status(body.question, status=body.status, note=body.note)
    return {"success": True}


@router.get("/edt/published", summary="Lister les emplois du temps publiés")
def list_published_timetables(admin: dict = Depends(require_admin)):
    rows = db_service.list_active_timetables()
    return {"timetables": rows}


@router.get("/edt/published/{timetable_id}", summary="Détail d'un emploi du temps publié")
def get_published_timetable(timetable_id: int, admin: dict = Depends(require_admin)):
    timetable = db_service.get_timetable_by_id(timetable_id, active_only=True)
    if not timetable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emploi du temps introuvable.",
        )
    return {"timetable": timetable}


@router.get("/faq/files", summary="Lister les fichiers FAQ importés")
def list_faq_files(admin: dict = Depends(require_admin)):
    os.makedirs(FAQ_DIR, exist_ok=True)
    files = []
    for name in sorted(os.listdir(FAQ_DIR)):
        if name.startswith("."):
            continue
        path = os.path.join(FAQ_DIR, name)
        if not os.path.isfile(path):
            continue
        stat = os.stat(path)
        files.append(
            {
                "name": name,
                "size_kb": max(1, int(stat.st_size / 1024)),
                "updated_at": str(int(stat.st_mtime)),
            }
        )
    return {"files": files}


@router.get("/faq/files/{filename}/preview", summary="Aperçu d'un fichier FAQ")
def preview_faq_file(filename: str, admin: dict = Depends(require_admin)):
    safe_name = os.path.basename(filename)
    path = os.path.join(FAQ_DIR, safe_name)
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier FAQ introuvable.",
        )

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _ALLOWED_FAQ_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Format non supporté. Attendu : {_ALLOWED_FAQ_EXTENSIONS}",
        )

    try:
        from backend.services.rag_service import _load_pdf, _load_faq_json, _load_text

        if ext == ".pdf":
            docs = _load_pdf(path, max_pages=8, max_chars=12000)
        elif ext == ".json":
            docs = _load_faq_json(path)
        else:
            docs = _load_text(path)

        text_parts = [d.get("page_content", "") for d in docs if d.get("page_content")]
        full_text = "\n\n".join(text_parts).strip()

        if not full_text:
            full_text = "Aucun contenu textuel exploitable detecte dans ce fichier."

        max_chars = 8000
        was_truncated = len(full_text) > max_chars
        preview_text = full_text[:max_chars]
        if was_truncated:
            preview_text += "\n\n[...] Apercu tronque"

        return {
            "filename": safe_name,
            "file_type": ext.lstrip("."),
            "snippet_count": len(docs),
            "truncated": was_truncated,
            "text": preview_text,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impossible de generer l'apercu: {e}",
        )


@router.get("/faq/files/{filename}/download", summary="Telecharger un fichier FAQ")
def download_faq_file(filename: str, admin: dict = Depends(require_admin)):
    safe_name = os.path.basename(filename)
    path = os.path.join(FAQ_DIR, safe_name)
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier FAQ introuvable.",
        )

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _ALLOWED_FAQ_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Format non supporte. Attendu : {_ALLOWED_FAQ_EXTENSIONS}",
        )

    media_type, _ = mimetypes.guess_type(path)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=safe_name,
    )


@router.post("/edt/publish", summary="Publier un emploi du temps dans la base de données")
def publish_timetable(body: TimetablePublishRequest, admin: dict = Depends(require_admin)):
    """
    Reçoit les données validées par l'admin et les stocke en base.
    """
    class_label = body.class_label
    academic_year = body.academic_year
    semester = body.semester
    slots = [slot.model_dump() for slot in body.slots]

    tt_id = db_service.save_timetable(class_label, academic_year, semester, slots)
    if not tt_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la sauvegarde en base de données."
        )

    try:
        from backend.services.router_service import get_available_classes
        get_available_classes(force_refresh=True)
    except Exception as exc:
        logger.debug(f"Class cache refresh skipped after publish: {exc}")

    return {"success": True, "timetable_id": tt_id}


@router.delete("/edt/published/{timetable_id}", summary="Supprimer un emploi du temps publié")
def delete_published_timetable(timetable_id: int, admin: dict = Depends(require_admin)):
    deleted = db_service.delete_timetable(timetable_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emploi du temps introuvable.",
        )

    try:
        from backend.services.router_service import get_available_classes
        get_available_classes(force_refresh=True)
    except Exception as exc:
        logger.debug(f"Class cache refresh skipped after delete: {exc}")

    return {"success": True}


@router.delete("/faq/files/{filename}", summary="Supprimer un fichier FAQ")
def delete_faq_file(filename: str, admin: dict = Depends(require_admin)):
    safe_name = os.path.basename(filename)
    path = os.path.join(FAQ_DIR, safe_name)
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier FAQ introuvable.",
        )
    os.remove(path)
    return {"success": True}
