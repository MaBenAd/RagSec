> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Chatbot USMS

Intelligent academic assistant for **ENSA Béni Mellal** (École Nationale des Sciences Appliquées, Université Sultan Moulay Slimane). Provides students and staff with natural-language access to university FAQs, class timetables, and administrative information through a conversational interface.

**Version:** 2.0.0 | **Stack:** FastAPI · Next.js 15 · PostgreSQL · Redis · Qdrant · GroqCloud

---

## Features

**Conversational Q&A (RAG)**
Retrieval-Augmented Generation over official university documents (PDFs). Questions are semantically matched against a curated knowledge base and answered by LLaMA 3.3-70B via GroqCloud.

**Smart Timetables**
Natural language queries resolved against structured DB schedules — "What do I have tomorrow morning?", "Who teaches Mechanics on Wednesday?" — with date-aware parsing and class disambiguation.

**Adaptive Response Tone**
Hybrid emotion detection (rule-based + LLM) identifies stress, urgency, and frustration to adapt response tone automatically. Supports French, English, and Arabic markers.

**Multilingual Support**
Full FR / EN / AR support: auto-detection, per-user language preference, query translation for retrieval, and response generation in the user's language.

**GDPR-Compliant by Design**
Right to erasure, right to portability, PII masking before cloud processing, audit logging, automatic 180-day data purge, and privacy consent gate at registration.

**Admin Dashboard**
Usage statistics, user management, FAQ document upload, timetable publishing, class change request review, cache management, and data lifecycle controls.

---

## Architecture

```
Browser
  └── Next.js 15 (port 3000)
        └── FastAPI (port 8000)
              ├── PostgreSQL 15   — users, conversations, messages, timetables, audit logs
              ├── Redis 7         — semantic response cache (TTL 1h)
              ├── Qdrant          — FAQ vector index + semantic cache collection
              └── GroqCloud       — LLaMA-3.3-70B (external API)
```

**Request flow:** User question → JWT validation → rate limit → language detection → emotion detection → route (timetable DB query *or* Qdrant vector search) → Groq LLM generation → Server-Sent Events stream → persist to PostgreSQL.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI 0.135.1 + Uvicorn |
| ORM / Migrations | SQLAlchemy 2.0 + Alembic |
| Authentication | PyJWT 2.12.1, bcrypt (cost=12) |
| LLM | GroqCloud — LLaMA-3.3-70B |
| Vector store | Qdrant 1.17.1 (local or remote) |
| Embeddings | FastEmbed 0.8.0 — BAAI/bge-small-en-v1.5 (384-dim, CPU) |
| Cache | Redis 7 |
| Rate limiting | SlowAPI |
| Frontend | Next.js 15.5 · TypeScript 5.8 · Tailwind CSS 3.4 |
| State management | Zustand 5 |
| Forms | React Hook Form + Zod |
| i18n | i18next 26 + react-i18next |
| Infrastructure | Docker · Docker Compose · GitHub Actions |

---

## Getting Started

### Prerequisites

- Docker Engine (or Docker Desktop)
- Python 3.10+ and Node.js 18+ (local development only)
- GroqCloud API key ([console.groq.com](https://console.groq.com))

### Local Development

The provided scripts handle virtual environment setup, `.env` creation, Docker service startup, database initialization, and process launch.

**Linux / macOS:**
```bash
bash ./dev.sh
```

**Windows (PowerShell):**
```powershell
.\dev.ps1
```

After setup:
- Frontend: http://127.0.0.1:3000
- Backend API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs

Default admin: `admin@usms.ac.ma` / value of `ADMIN_PASSWORD` in `.env`

### Production (Full Docker)

```bash
# Build and start all services
docker compose up -d --build

# Initialize database, seed admin, import timetables, build FAQ index
docker compose exec backend python backend/scripts/bootstrap_dev_content.py
docker compose exec backend python backend/scripts/seed_timetables.py --replace
docker compose exec backend python backend/scripts/rebuild_faq_index.py
```

---

## Configuration

Copy `.env.example` to `.env` and fill in the required values:

```env
# Required
GROQ_API_KEY=your_groqcloud_key
JWT_SECRET_KEY=a_random_string_of_at_least_32_characters
DATABASE_URL=postgresql://ensa_user:ensa_pass@127.0.0.1:5432/ensa_db
ADMIN_PASSWORD=strong_admin_password

# Docker override (uses 'postgres' hostname)
DOCKER_DATABASE_URL=postgresql://ensa_user:ensa_pass@postgres:5432/ensa_db
POSTGRES_USER=ensa_user
POSTGRES_PASSWORD=ensa_pass
POSTGRES_DB=ensa_db
```

See [`docs/infrastructure.md`](docs/infrastructure.md) for the full environment variable reference.

---

## Testing

```bash
PYTHONPATH=. pytest backend/tests/ -v
```

64 tests across 9 modules — all passing on `main`. Covers authentication, chat, admin, RAG quality, emotion detection, timetable seeding, database operations, health checks, and utilities.

---

## Documentation

Detailed technical documentation is in the [`docs/`](docs/) directory:

| Document | Content |
|----------|---------|
| [docs/overview.md](docs/overview.md) | Architecture diagram, tech stack, key metrics |
| [docs/backend.md](docs/backend.md) | FastAPI app, middleware, request lifecycle |
| [docs/database.md](docs/database.md) | Full schema (9 tables), migrations, ORM |
| [docs/authentication.md](docs/authentication.md) | JWT, refresh tokens, RBAC, brute-force protection |
| [docs/chatbot.md](docs/chatbot.md) | Routing logic, emotion detection, SSE streaming |
| [docs/rag.md](docs/rag.md) | RAG pipeline, Qdrant, embeddings, confidence scoring |
| [docs/caching.md](docs/caching.md) | Redis strategy, semantic cache, invalidation |
| [docs/llm-integration.md](docs/llm-integration.md) | GroqCloud integration, PII masking, prompt safety |
| [docs/frontend.md](docs/frontend.md) | Next.js pages, Zustand stores, components |
| [docs/internationalisation.md](docs/internationalisation.md) | i18next, FR/EN/AR, RTL, language persistence |
| [docs/security-gdpr.md](docs/security-gdpr.md) | GDPR compliance checklist, security controls |
| [docs/api-reference.md](docs/api-reference.md) | All 30+ endpoints with request/response examples |
| [docs/infrastructure.md](docs/infrastructure.md) | Docker Compose, CI/CD, environment variables |
| [docs/testing.md](docs/testing.md) | Test suite structure, fixtures, CI integration |
| [docs/data-management.md](docs/data-management.md) | FAQ files, timetable seeds, utility scripts |

---

## Repository Structure

```
Chatbot-USMS/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── routes/                  # auth.py, chat.py, admin.py
│   ├── services/                # db, auth, chatbot, rag, groq, cache, ...
│   ├── models/schemas.py        # Pydantic request/response models
│   ├── alembic/                 # Versioned database migrations
│   ├── data/faq/                # FAQ source documents (git-versioned)
│   ├── data/seeds/              # timetables.json (git-versioned)
│   ├── scripts/                 # bootstrap, seed, export, rebuild
│   └── tests/                   # 64 pytest tests
├── frontend/
│   ├── src/app/                 # Next.js App Router pages
│   ├── src/components/          # React components
│   ├── src/store/               # Zustand state stores
│   ├── src/lib/                 # API client, i18n config
│   └── src/locales/             # fr.json, en.json, ar.json
├── docs/                        # Technical documentation
├── docker-compose.yml
├── dev.sh / dev.ps1             # Dev startup scripts
└── .env.example
```

---

## Team Workflow

- Branch from `main` for all new features
- Run `PYTHONPATH=. pytest backend/tests/` before merging
- Use `alembic revision --autogenerate` for schema changes
- Run `export_timetables_seed.py` and commit `timetables.json` after publishing new schedules
- Run `rebuild_faq_index.py` after adding FAQ documents

---

## License

Developed for educational purposes at ENSA Béni Mellal.  
© 2025-2026 Université Sultan Moulay Slimane. All rights reserved.
