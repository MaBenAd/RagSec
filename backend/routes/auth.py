"""
Routes d'authentification - POST /login, /register, session et profil.
"""
import os
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.models.schemas import (
    LanguageUpdateRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from backend.services import db_service
from backend.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_current_user,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

_EMAIL_REGEX = re.compile(r"^[^@]+@(usms\.ac\.ma|usms\.ma)$", re.IGNORECASE)


def _validate_email(email: str) -> bool:
    return bool(_EMAIL_REGEX.match(email.strip()))


def _secure_cookie() -> bool:
    return os.getenv("ENV", "dev") == "production"


def _set_refresh_cookie(response: Response, user_id: int):
    response.set_cookie(
        key="refresh_token",
        value=create_refresh_token(user_id),
        httponly=True,
        max_age=7 * 24 * 3600,
        expires=7 * 24 * 3600,
        samesite="strict",
        secure=_secure_cookie(),
    )


def _set_session_cookies(response: Response, access_token: str, user_id: int):
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=15 * 60,
        samesite="strict",
        secure=_secure_cookie(),
    )
    response.set_cookie(
        key="csrf_token",
        value=secrets.token_urlsafe(32),
        httponly=False,
        max_age=15 * 60,
        samesite="strict",
        secure=_secure_cookie(),
    )
    _set_refresh_cookie(response, user_id)


def _token_response(user: dict, response: Response) -> TokenResponse:
    token = create_access_token(user["id"], user["email"], user["role"])
    _set_session_cookies(response, token, user["id"])
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=token,
        user=UserOut(
            id=user["id"],
            email=user["email"],
            role=user["role"],
            class_label=user.get("class_label"),
            language=user.get("language", "fr"),
        ),
    )


@router.post("/login", response_model=TokenResponse, summary="Connexion etudiant/admin")
def login(body: LoginRequest, response: Response):
    if not _validate_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="L'email doit appartenir au domaine @usms.ac.ma ou @usms.ma",
        )

    user = db_service.verify_user(body.email.strip().lower(), body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
        )
    if isinstance(user, dict) and user.get("locked"):
        unlock_time = user.get("until")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Compte verrouille temporairement. Reessayez apres {unlock_time.strftime('%H:%M')}.",
        )

    db_service.log_audit_action("user_login", user["id"], details=f"User login: {user['email']}")
    return _token_response(user, response)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Inscription etudiant",
)
def register(body: RegisterRequest, response: Response):
    if not _validate_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="L'email doit appartenir au domaine @usms.ac.ma ou @usms.ma",
        )
    if len(body.password) < 8 or not any(c.isdigit() for c in body.password) or not any(not c.isalnum() for c in body.password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Le mot de passe doit contenir au moins 8 caracteres, un chiffre et un caractere special.",
        )
    if not body.accepted_privacy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous devez accepter la politique de confidentialite avant de confirmer l'inscription.",
        )

    user = db_service.create_user(
        email=body.email.strip().lower(),
        password=body.password,
        class_label=body.class_label,
        language=body.language or "fr",
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte avec cet email existe deja.",
        )

    db_service.log_audit_action("user_registration", user["id"], details=f"New User registered: {user['email']}")
    return _token_response(user, response)


@router.post("/refresh", response_model=TokenResponse, summary="Rafraichir le token d'acces")
def refresh_token(request: Request, response: Response):
    refresh_cookie = request.cookies.get("refresh_token")
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="Session expiree ou refresh token manquant")

    try:
        payload = decode_refresh_token(refresh_cookie)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token de type invalide")
        user = db_service.get_user_by_id(int(payload["sub"]))
        if not user:
            raise HTTPException(status_code=401, detail="Utilisateur non trouve")
        return _token_response(user, response)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Refresh token invalide ou expire")


@router.post("/logout", summary="Deconnexion")
def logout(response: Response):
    response.delete_cookie("access_token", samesite="strict")
    response.delete_cookie("csrf_token", samesite="strict")
    response.delete_cookie("refresh_token", samesite="strict")
    return {"success": True}


@router.get("/me", response_model=UserOut, summary="Profil utilisateur courant")
def get_me(current_user: dict = Depends(get_current_user)):
    user = db_service.find_user_by_email(current_user["email"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur non trouve")
    return UserOut(
        id=user["id"],
        email=user["email"],
        role=user["role"],
        class_label=user.get("class_label"),
        language=user.get("language", "fr"),
    )


@router.post("/me/language", summary="Mettre a jour la langue preferee")
def update_language(body: LanguageUpdateRequest, current_user: dict = Depends(get_current_user)):
    db_service.update_user_language(current_user["id"], body.language)
    return {"success": True}


@router.get("/me/activity", summary="Obtenir l'activite de l'utilisateur")
def get_user_activity(current_user: dict = Depends(get_current_user)):
    data = db_service.get_user_activity_graph(current_user["id"])
    return {"activity": data}


@router.get("/me/export", summary="Exporter mes donnees")
def export_my_data(current_user: dict = Depends(get_current_user)):
    user_db = db_service.find_user_by_email(current_user["email"])
    if not user_db:
        raise HTTPException(status_code=404, detail="Utilisateur non trouve")

    convs = db_service.get_conversations(user_db["id"])
    export_data = {
        "user_profile": {
            "email": user_db["email"],
            "role": user_db["role"],
            "class_label": user_db.get("class_label"),
            "language": user_db.get("language"),
            "created_at": user_db.get("created_at"),
        },
        "conversations": [],
    }

    for conv in convs:
        messages = db_service.get_messages(conv["id"])
        export_data["conversations"].append(
            {
                "title": conv["title"],
                "created_at": conv["created_at"],
                "messages": [
                    {
                        "role": message["role"],
                        "content": message["content"],
                        "created_at": message["created_at"],
                        "metadata": message.get("metadata"),
                    }
                    for message in messages
                ],
            }
        )

    db_service.log_audit_action("data_export_requested", user_db["id"])
    return export_data


@router.delete("/me", summary="Supprimer mon compte")
def delete_my_account(current_user: dict = Depends(get_current_user)):
    db_service.delete_user(current_user["id"])
    return {"success": True}


@router.get("/me/timetable", summary="Obtenir mon emploi du temps")
def get_my_timetable(current_user: dict = Depends(get_current_user)):
    from backend.services.router_service import get_available_classes, resolve_class_label

    user_db = db_service.find_user_by_email(current_user["email"])
    if not user_db or not user_db.get("class_label"):
        return {"timetable": None}

    class_label = user_db["class_label"]
    available = get_available_classes()
    resolved, candidates = resolve_class_label(class_label, available)
    if resolved:
        class_label = resolved
    elif candidates:
        return {"timetable": None}

    db_class_label = available.get(class_label, {}).get("canonical_label", class_label)
    return {"timetable": db_service.get_active_timetable(db_class_label)}
