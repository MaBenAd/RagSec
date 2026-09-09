> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Project Overview — Chatbot USMS

## Purpose

Chatbot USMS is an intelligent conversational assistant built for **ENSA Béni Mellal** (École Nationale des Sciences Appliquées), part of **Université Sultan Moulay Slimane (USMS)**. It gives students and administrators instant, natural-language access to:

- University FAQs (admission, courses, administration)
- Class timetables and exam schedules
- Administrative information and procedures

The chatbot runs in **French, English, and Arabic** and enforces full **GDPR / RGPD compliance**.

---

## Version & Status

| Field | Value |
|-------|-------|
| Version | 2.0.0 |
| Status | Production-ready |
| Default admin | admin@usms.ac.ma |
| Stable branch | `main` (PostgreSQL + GDPR) |
| Legacy reference | `sqlite-demo` / tag `v1-sqlite-demo` |

---

## High-Level Architecture

```
┌──────────────────────┐        ┌──────────────────────┐
│   Next.js Frontend   │◄──────►│   FastAPI Backend     │
│   (TypeScript, SSE)  │        │   (Python 3.10+)      │
└──────────────────────┘        └──────────┬───────────┘
                                           │
                  ┌────────────────────────┼─────────────────────┐
                  │                        │                     │
         ┌────────▼────────┐    ┌──────────▼────────┐  ┌────────▼────────┐
         │  PostgreSQL 15  │    │  Redis 7 (Cache)  │  │  Qdrant Vector  │
         │  (Primary DB)   │    │                   │  │  Store (RAG)    │
         └─────────────────┘    └───────────────────┘  └────────┬────────┘
                                                                │
                                                       ┌────────▼────────┐
                                                       │  GroqCloud LLM  │
                                                       │  LLaMA-3.3-70B  │
                                                       └─────────────────┘
```

### Data Flow (Chat Request)

1. User sends a message from the React frontend.
2. Frontend calls `POST /api/v1/chat/stream` with JWT Bearer token.
3. Backend detects language, emotion state, and question type (timetable vs FAQ).
4. If timetable → deterministic DB query → LLM reformulation.
5. If FAQ → Qdrant semantic search → top-K context → Groq LLM generation.
6. Response streamed back via Server-Sent Events (SSE).
7. Message and metadata persisted to PostgreSQL.

---

## Technology Stack Summary

### Backend
| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.135.1 |
| Server | Uvicorn 0.41.0 |
| ORM | SQLAlchemy 2.0.38 |
| Migrations | Alembic 1.14.1 |
| Auth | PyJWT 2.12.1, bcrypt 5.0.0 |
| LLM | GroqCloud — LLaMA-3.3-70B |
| Vector DB | Qdrant 1.17.1 |
| Embeddings | FastEmbed 0.8.0 (BAAI/bge-small-en-v1.5, 384-dim) |
| Cache | Redis 5.2.1 |
| PDF | pdfplumber 0.11.9, PyPDFium2 |
| Rate Limit | SlowAPI 0.1.9 |
| Logging | Loguru 0.7.3 |
| Validation | Pydantic 2.12.5 |

### Frontend
| Layer | Technology |
|-------|-----------|
| Framework | Next.js 15.5.15 (App Router) |
| Language | TypeScript 5.8.2 |
| Styling | Tailwind CSS 3.4.17 |
| State | Zustand 5.0.3 |
| Forms | React Hook Form 7.56.4 + Zod 3.24.2 |
| HTTP | Axios 1.15.0 + Fetch API (SSE) |
| i18n | i18next 26.0.3, react-i18next 17.0.2 |
| Markdown | react-markdown 9.1.0 |
| Notifications | Sonner 1.7.4 |

### Infrastructure
| Layer | Technology |
|-------|-----------|
| Containerization | Docker & Docker Compose |
| CI/CD | GitHub Actions |
| DB Container | postgres:15-alpine |
| Cache Container | redis:7-alpine |
| Vector DB Container | qdrant/qdrant:latest |

---

## Key Capabilities

| Feature | Details |
|---------|---------|
| Dual-mode QA | Timetable (deterministic) + FAQ (RAG/LLM) |
| Emotion detection | Adaptive empathetic tone (urgent, stressed, etc.) |
| Multilingual | FR/EN/AR — auto-detect + user preference |
| Semantic cache | Avoids redundant LLM calls for similar questions |
| SSE streaming | Real-time character-by-character response display |
| GDPR compliance | Right to erasure, portability, audit logs, PII masking |
| Role-based access | Student vs. admin (RBAC via JWT) |
| Brute-force protection | Account lockout after 5 failed attempts (30 min) |

---

## Project Metrics

| Metric | Value |
|--------|-------|
| Backend LOC | ~3,900 (core, excl. tests) |
| Frontend LOC | ~2,100 |
| Database tables | 9 |
| API endpoints | 30+ |
| Test count | 64 (all passing) |
| Supported languages | 3 (FR, EN, AR) |
| Max chat timeout | 90 seconds |
| Auto data purge | 180 days |

---

## Institution

- **Institution:** ENSA Béni Mellal — Université Sultan Moulay Slimane
- **Authorized email domains:** `@usms.ac.ma`, `@usms.ma`
- **License:** Educational use — © 2025-2026 ENSA Béni Mellal
