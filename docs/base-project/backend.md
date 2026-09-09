> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Backend — FastAPI Application

## Entry Point

**File:** `backend/main.py`

The application is launched with:
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI auto-generated at: `http://localhost:8000/docs`

---

## Application Initialization

### Lifespan (startup)
On startup, FastAPI runs the `lifespan` async context manager:
1. `db_service.init_db()` — creates all tables (or runs Alembic migrations)
2. `db_service.seed_admin()` — creates the admin account if it doesn't exist

### Environment Loading
- `.env` loaded via `python-dotenv` at module import
- `env_service.validate_env()` warns if required variables are missing

---

## Middleware Stack

### CORS
Configured via `CORSMiddleware`. Allowed origins are built from:
- Hard-coded defaults: `http://localhost:3000`, `http://127.0.0.1:3000`
- `CORS_ORIGINS` env variable (comma-separated list)

Settings: `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`

### Security Headers
Applied as HTTP middleware on every response:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (HTTPS only) |

### Rate Limiting
Using **SlowAPI** with `get_remote_address` as the key function.
- Chat endpoints: limited to **10 requests/minute** per IP
- Exceeded requests return HTTP 429

---

## Router Registration

Three routers are registered:

| Router | Prefix | File |
|--------|--------|------|
| Auth | `/api/v1/auth` | `backend/routes/auth.py` |
| Chat | `/api/v1` | `backend/routes/chat.py` |
| Admin | `/api/v1/admin` | `backend/routes/admin.py` |

---

## Health Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Full health check — tests Qdrant and Groq connectivity |
| `/healthz` | GET | Lightweight liveness probe (always returns `{"status": "ok"}`) |

The `/` endpoint returns:
```json
{
  "status": "ok",
  "version": "2.0.0",
  "docs": "/docs",
  "qdrant": "connected",
  "groq": "connected"
}
```

If a dependency fails, `status` becomes `"partial_error"` and the failing service shows an error string.

---

## Service Architecture

All business logic lives in `backend/services/`:

| Service | File | Responsibility |
|---------|------|----------------|
| `db_service` | `db_service.py` | Database ORM, all CRUD operations |
| `auth_service` | `auth_service.py` | JWT creation/validation, OAuth2 dependency |
| `chatbot_service` | `chatbot_service.py` | Emotion detection, timetable Q&A, response shaping |
| `rag_service` | `rag_service.py` | Qdrant vector search, embeddings, semantic cache |
| `groq_service` | `groq_service.py` | LLM API calls, PII masking, multilingual translation |
| `cache_service` | `cache_service.py` | Redis read/write, semantic cache helpers |
| `router_service` | `router_service.py` | Dispatches questions to EDT or RAG path |
| `env_service` | `env_service.py` | Environment variable validation on startup |
| `logging_service` | `logging_service.py` | Loguru logger configuration |
| `limiter_service` | `limiter_service.py` | SlowAPI limiter singleton |

---

## Request Lifecycle (Chat)

```
POST /api/v1/chat/stream
        │
        ▼
  JWT validation (get_current_user)
        │
        ▼
  Rate limit check (10/min)
        │
        ▼
  Load user from DB (class_label, language)
        │
        ▼
  Detect question type (_is_edt_question)
        │
   ┌────┴────┐
   │         │
  EDT       FAQ
   │         │
   ▼         ▼
  DB query  Semantic cache check
   │         │ (miss)
   ▼         ▼
  Groq    Qdrant vector search
  reform.    │
   │         ▼
   │       Groq generation
   │
   └──────► SSE stream to client
                │
                ▼
           Persist to PostgreSQL
           (conversation + messages)
```

---

## Logging

Uses **Loguru**. Configured in `logging_service.py`.
- Log file: `backend/data/logs/app.log`
- Level: INFO in production, DEBUG in development
- Format: timestamp, level, module, message

---

## Error Handling

FastAPI's default error handling is extended with:
- `RateLimitExceeded` → HTTP 429 (SlowAPI handler)
- `HTTPException` → standard JSON `{"detail": "..."}` responses
- JWT `ExpiredSignatureError` → HTTP 401 "Session expirée"
- JWT `InvalidTokenError` → HTTP 401 "Token invalide ou expiré"
- Role check failure → HTTP 403 "Accès réservé aux administrateurs"

---

## Python Version & Dependencies

- **Python:** 3.10+
- **Key dependencies:** (from `requirements.txt` / `requirements.docker.txt`)
  - `fastapi`, `uvicorn[standard]`
  - `sqlalchemy`, `alembic`, `pg8000` (PostgreSQL driver)
  - `pyjwt`, `bcrypt`, `python-multipart`
  - `slowapi`, `loguru`, `python-dotenv`
  - `qdrant-client`, `fastembed`
  - `groq` (GroqCloud SDK)
  - `pdfplumber`, `pypdfium2`
  - `dateparser`, `redis`
  - `pydantic[email]`
