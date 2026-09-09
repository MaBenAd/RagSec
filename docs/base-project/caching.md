> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Caching Strategy

## Overview

The project uses a two-layer caching strategy to reduce LLM API costs and improve response latency:

| Layer | Technology | Purpose |
|-------|-----------|---------|
| L1 — Exact cache | Redis | Fast hash-based key lookup |
| L2 — Semantic cache | Qdrant + Redis | Similarity-based lookup for paraphrased questions |

---

## Redis Cache

**File:** `backend/services/cache_service.py`

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `redis` (Docker) / `127.0.0.1` (local) | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `ENABLE_CACHE` | `true` | Feature flag to disable caching entirely |
| `CACHE_TTL` | `3600` (1 hour) | Default TTL in seconds |

### Connection

Lazy singleton pattern — Redis is connected on first use:
```python
_REDIS_CLIENT = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
_REDIS_CLIENT.ping()  # validates connection
```

If Redis is unavailable, all cache operations are silently skipped (no crash).

### Key Format

```
chatbot:{prefix}:{sha256[:16]}
```

Example:
- `chatbot:semantic:a3f9b12c45e67d89` — semantic cache for a specific question hash

Prefixes in use:
- `semantic` — RAG Q&A answers

### Core Functions

```python
get_cached_response(prefix, query) → str | None
set_cached_response(prefix, query, response, ttl)
invalidate_cache(prefix="*")           # deletes all keys matching chatbot:{prefix}:*
```

---

## Semantic Cache Layer

Combines Redis (fast lookup) with Qdrant (similarity matching).

### Write Path (after LLM generation)
```python
set_semantic_cache(question, answer, source_file)
```
Stores JSON `{"answer": "...", "source": "..."}` in Redis under the question's hash key.

### Read Path (before LLM call)
```python
cached_answer, cached_source = get_semantic_cache(question)
```
Returns `(None, None)` if no cache hit.

### When Cache is Bypassed
- Timetable / EDT questions are **always bypassed** — answers depend on the current date/time
- Questions with conversation history (multi-turn context) are **not cached** — context makes each answer unique
- Answers starting with `❌` (error responses) are **not cached**

### Cache Invalidation

Admins can flush the cache via:
```bash
POST /api/v1/admin/cache/flush
```
This calls `invalidate_cache()` which deletes all `chatbot:*:*` keys.

Automatic invalidation after FAQ vectorstore rebuild:
```python
invalidate_cache("rag")  # removes chatbot:rag:* keys
```

---

## Cache in the Request Flow

```
POST /api/v1/chat/stream
        │
        ▼
  is_edt_question?
  YES → skip cache entirely
  NO  → get_semantic_cache(question)
           │
      cache hit?
      YES → stream cached answer in 3-word chunks
            → [DONE]
      NO  → run RAG pipeline
            → set_semantic_cache(question, answer)
            → stream answer
            → [DONE]
```

---

## Docker Redis Setup

```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  restart: unless-stopped
```

No authentication configured (internal Docker network only). For production, add Redis AUTH password.

---

## Analytics — Most Asked Questions

`get_most_asked_questions(limit)` in `rag_service.py` queries the Qdrant `semantic_cache` collection to return the most frequently served cached answers, providing insight into the most common student questions.

This data is exposed at `GET /api/v1/admin/stats/most-asked`.
