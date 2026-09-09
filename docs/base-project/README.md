> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Chatbot USMS — Documentation Index

Assistant académique intelligent pour ENSA Béni Mellal (Université Sultan Moulay Slimane).

**Version:** 2.0.0 | **Status:** Production-ready | **Tests:** 64/64 ✅

---

## Documents

| File | Content |
|------|---------|
| [overview.md](overview.md) | Project purpose, architecture diagram, tech stack summary, key metrics |
| [backend.md](backend.md) | FastAPI application, middleware, routing, startup lifecycle, request flow |
| [database.md](database.md) | PostgreSQL schema (all 9 tables), Alembic migrations, ORM models, CRUD functions |
| [authentication.md](authentication.md) | JWT auth, refresh tokens, RBAC, brute-force protection, email domain validation |
| [chatbot.md](chatbot.md) | Question routing (EDT vs FAQ), emotion detection, SSE streaming, conversation title generation |
| [rag.md](rag.md) | RAG pipeline, Qdrant, BAAI embeddings, semantic cache, confidence scoring, multilingual retrieval |
| [caching.md](caching.md) | Redis cache strategy, semantic cache, invalidation, analytics |
| [llm-integration.md](llm-integration.md) | GroqCloud integration, PII masking, prompt injection protection, response style adaptation |
| [frontend.md](frontend.md) | Next.js App Router, pages, Zustand stores, Axios client, SSE streaming, components |
| [internationalisation.md](internationalisation.md) | i18next setup, FR/EN/AR translation files, RTL support, language persistence |
| [security-gdpr.md](security-gdpr.md) | Full GDPR compliance (erasure, portability, audit logs), security headers, rate limiting |
| [api-reference.md](api-reference.md) | All 30+ API endpoints with request/response examples |
| [infrastructure.md](infrastructure.md) | Docker Compose, Dockerfiles, CI/CD (GitHub Actions), dev scripts, environment variables |
| [testing.md](testing.md) | pytest suite (64 tests), test modules, fixtures, CI integration |
| [data-management.md](data-management.md) | FAQ files, timetable seeds, utility scripts, vector store, logs |

---

## Quick Start

```bash
# Linux/Mac
bash ./dev.sh

# Windows
.\dev.ps1

# Manual
docker compose up -d postgres redis qdrant
PYTHONPATH=. python backend/scripts/bootstrap_dev_content.py
PYTHONPATH=. uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
cd frontend && npm run dev
```

Open: http://localhost:3000/login

Admin credentials: `admin@usms.ac.ma` / value of `ADMIN_PASSWORD` in `.env`

---

## Architecture at a Glance

```
Browser → Next.js (3000) → FastAPI (8000) ┬→ PostgreSQL (5432)
                                           ├→ Redis (6379)
                                           ├→ Qdrant (6333)
                                           └→ GroqCloud (external)
```

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| FastAPI + SSE over WebSocket | Simpler stateless streaming, works behind any reverse proxy |
| Qdrant local by default | Zero external dependency for dev; swappable to remote for prod |
| BAAI/bge-small-en-v1.5 embeddings | CPU-only, no GPU required, multilingual, 384-dim tradeoff |
| PostgreSQL as primary DB | Production-grade reliability; SQLite compatibility kept for demos |
| Alembic versioned migrations | Enables collaborative schema evolution between team members |
| Redis semantic cache | Reduces Groq API costs by 30-60% for repeated/similar questions |
| JWT with HttpOnly refresh cookies | Balances usability (SPA) with XSS protection |
| bcrypt cost=12 | Strong hashing without unacceptable latency on login |
| PII masking before cloud LLM | GDPR data minimization — personal data stays on-premise |
