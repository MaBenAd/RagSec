"""
Auth Service - JWT (JSON Web Tokens) + OAuth2.
Gestion des tokens d'acces signes pour l'API FastAPI.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from backend.services.logging_service import logger


def _is_weak_secret(secret: str) -> bool:
    lowered = (secret or "").strip().lower()
    return (
        len(lowered) < 32
        or "change_me" in lowered
        or "changeme" in lowered
        or lowered in {"default", "secret", "password"}
    )


def _load_secret_key() -> str:
    configured = (os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET") or "").strip()
    if configured and not _is_weak_secret(configured):
        return configured

    ephemeral = secrets.token_urlsafe(48)
    logger.warning(
        "JWT secret missing or weak. Using an ephemeral in-memory key; "
        "set JWT_SECRET_KEY (>=32 random chars) for stable and secure sessions."
    )
    return ephemeral


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
    or str(int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "0") or "0") * 60)
    or "15"
)
if ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
    ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def create_access_token(user_id: int, email: str, role: str, session_version: int = 1) -> str:
    """Genere un JWT d'acces court."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "session_version": session_version,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Genere un JWT de rafraichissement long."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "email", "role", "exp"]},
    )


def decode_refresh_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp"]},
    )


def get_current_user(request: Request, token: str | None = Depends(oauth2_scheme)) -> dict:
    """Valide le JWT Bearer ou le cookie de session."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expire.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    cookie_auth = False
    if not token:
        token = request.cookies.get("access_token")
        cookie_auth = bool(token)
    if not token:
        raise credentials_exc

    if cookie_auth and request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Jeton CSRF manquant ou invalide.",
            )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        if payload.get("type") != "access" or not user_id or not email:
            raise credentials_exc
        return {"id": int(user_id), "email": email, "role": role,
                "session_version": payload.get("session_version")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Votre session a expire. Veuillez vous reconnecter.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exc


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Verifie que l'utilisateur courant est admin (RBAC)."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux administrateurs.",
        )
    return current_user
