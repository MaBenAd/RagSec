"""
Chatbot USMS — Backend FastAPI
Point d'entrée principal de l'API REST.

Lancer :
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

Documentation Swagger auto-générée :
    http://localhost:8000/docs
"""
import os
import sys
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()  # charge .env au démarrage

from backend.services.env_service import validate_env
if os.getenv("ENV", "dev").strip().lower() == "production" and not validate_env():
    sys.exit(1)
else:
    validate_env()  # Warn if missing env vars

# Initialize Logging
from backend.services.logging_service import logger

# Initialize Limiter
from backend.services.limiter_service import limiter

from backend.services import db_service
from backend.routes import auth, chat, admin


def _get_cors_origins() -> list[str]:
    """Build a clean CORS origin list from env with safe local defaults."""
    default_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    raw = os.getenv("CORS_ORIGINS", "")
    env_origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]

    clean: list[str] = []
    for origin in default_origins + env_origins:
        if origin == "*":
            continue
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        clean.append(origin)

    return list(dict.fromkeys(clean))


def _get_trusted_hosts() -> list[str]:
    raw = os.getenv("TRUSTED_HOSTS", "")
    defaults = ["localhost", "127.0.0.1", "testserver"]
    configured = [host.strip() for host in raw.split(",") if host.strip()]
    hosts = defaults + configured if configured else defaults
    return list(dict.fromkeys(hosts))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation au démarrage : DB + seed admin."""
    db_service.init_db()
    db_service.seed_admin()
    try:
        from backend.services.rag_service import warm_faq_cache

        cache_status = warm_faq_cache()
        logger.info(f"FAQ cache warmed: {cache_status}")
    except Exception as exc:
        logger.warning(f"FAQ cache warmup skipped: {exc}")
    yield


app = FastAPI(
    title="Chatbot USMS — API",
    description=(
        "API REST du chatbot intelligent ENSAM Béni Mellal.\n\n"
        "Fonctionnalités : FAQ dynamique, emplois du temps, calendrier des examens, "
        "dashboard administrateur.\n\n"
        "**LLM** : GroqCloud LLaMA-3.3-70B | **Vecteurs** : Qdrant local | "
        "**Auth** : JWT"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ── Rate Limiting ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Host header hardening ──
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_get_trusted_hosts())

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept-Language", "X-CSRF-Token"],
)

# ── Enregistrement des routes ──
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(admin.router)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path not in {"/docs", "/redoc", "/openapi.json"}:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.get("/", tags=["Health"], summary="Health check")
def health():
    """Vérifie que l'API est opérationnelle ainsi que ses dépendances."""
    status = {"status": "ok", "version": "2.0.0", "docs": "/docs"}
    
    # Check database
    try:
        with db_service.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["database"] = "connected"
    except Exception as exc:
        status["database"] = f"unavailable: {exc}"
        status["status"] = "partial_error"

    # Check Qdrant
    try:
        from backend.services.rag_service import get_collection
        get_collection()
        status["qdrant"] = "connected"
    except Exception as exc:
        status["qdrant"] = f"unavailable: {exc}"
        status["status"] = "partial_error"

    # Check Redis cache. It is optional: the app falls back gracefully when Redis is unavailable.
    try:
        from backend.services.cache_service import get_redis
        redis_client = get_redis()
        if redis_client is None:
            raise RuntimeError("Unable to reach Redis")
        redis_client.ping()
        status["redis"] = "connected"
    except Exception as exc:
        status["redis"] = f"unavailable: {exc}"

    # Check Groq
    try:
        from backend.services.groq_service import get_client
        get_client()
        status["groq"] = "connected"
    except Exception as exc:
        status["groq"] = f"unavailable: {exc}"
        status["status"] = "partial_error"
        
    return status


@app.get("/healthz", tags=["Health"], summary="Lightweight health check")
def healthz():
    """Probe legere pour les scripts de dev et les checks de disponibilite."""
    return {"status": "ok"}
