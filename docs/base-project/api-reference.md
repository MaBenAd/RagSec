> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# API Reference

**Base URL:** `http://localhost:8000`  
**Swagger UI:** `http://localhost:8000/docs`  
**Authentication:** Bearer JWT token in `Authorization` header (except public endpoints)

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | Full health check (Qdrant, Groq) |
| GET | `/healthz` | No | Lightweight liveness probe |

### `GET /`
**Response:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "docs": "/docs",
  "qdrant": "connected",
  "groq": "connected"
}
```

---

## Auth — `/api/v1/auth`

### `POST /api/v1/auth/login`
**Body:**
```json
{
  "email": "student@usms.ac.ma",
  "password": "pass1234!"
}
```
**Response:** `TokenResponse` (access_token + user) + `refresh_token` HttpOnly cookie  
**Errors:** 400 (invalid domain), 401 (wrong credentials), 403 (locked)

---

### `POST /api/v1/auth/register`
**Body:**
```json
{
  "email": "student@usms.ac.ma",
  "password": "pass1234!",
  "class_label": "IACS S4",
  "language": "fr",
  "accepted_privacy": true
}
```
**Response:** `TokenResponse` + `refresh_token` cookie  
**Errors:** 400 (invalid domain, privacy not accepted), 409 (email exists), 422 (weak password)

---

### `POST /api/v1/auth/refresh`
Uses `refresh_token` cookie to issue a new access token.  
**Response:** `TokenResponse` + rotated `refresh_token` cookie  
**Errors:** 401 (missing or expired refresh token)

---

### `POST /api/v1/auth/logout`
Clears `refresh_token` cookie.  
**Response:** `{"success": true}`

---

### `POST /api/v1/auth/me/language`
**Body:** `{"language": "fr"}` — pattern: `^(fr|en|ar)$`  
**Response:** `{"success": true}`

---

### `GET /api/v1/auth/me/activity`
**Response:**
```json
{
  "activity": [{"day": "2026-04-28", "count": 5}, ...]
}
```

---

### `GET /api/v1/auth/me/export`
Returns all user data as JSON (GDPR portability).  
**Response:**
```json
{
  "user_profile": {"email": "...", "role": "...", "class_label": "...", "language": "...", "created_at": "..."},
  "conversations": [
    {
      "title": "...",
      "created_at": "...",
      "messages": [{"role": "user", "content": "...", "created_at": "...", "metadata": null}]
    }
  ]
}
```

---

### `DELETE /api/v1/auth/me`
Deletes the authenticated user's account and all associated data.  
**Response:** `{"success": true}`

---

### `GET /api/v1/auth/me/timetable`
**Response:** `{"timetable": <TimetableObject> | null}`

---

## Chat — `/api/v1`

### `POST /api/v1/chat/stream` ⚡ SSE
**Rate limit:** 10/minute  
**Body:**
```json
{
  "question": "Quels cours ai-je demain?",
  "class_label": null,
  "conversation_id": null
}
```
**Response:** `text/event-stream`
```
data: Voici vos cours de demain...\n\n
data: __metadata__:{"timetable": {...}, "rag_confidence": "high"}\n\n
data: [DONE]\n\n
```

---

### `POST /api/v1/chat` (Non-streaming)
**Rate limit:** 10/minute  
**Body:** Same as `/chat/stream`  
**Response:**
```json
{
  "answer": "...",
  "conversation_id": 42,
  "class_label": "IACS S4",
  "requires_class_selection": false,
  "available_classes": [],
  "source_file": "faq_usms.pdf",
  "timetable": null,
  "rag_confidence": "high",
  "rag_score": 0.87
}
```
**Special:** `requires_class_selection: true` when the user has no assigned class for EDT queries.

---

### `POST /api/v1/chat/feedback/{message_id}`
**Body:** `{"feedback": 1}` — values: `-1` (negative), `0` (neutral), `1` (positive)  
**Response:** `{"success": true}`  
**Errors:** 403 (message doesn't belong to user)

---

### `POST /api/v1/chat/contest/{message_id}`
Flags an AI response for human review.  
**Response:** `{"success": true}`

---

### `GET /api/v1/conversations`
**Response:** `{"conversations": [{"id": 1, "title": "...", "created_at": "...", "updated_at": "..."}]}`

---

### `GET /api/v1/conversations/{conv_id}/messages`
**Response:** `{"messages": [{"id": 1, "role": "user", "content": "...", "feedback": 0, "created_at": "...", "metadata": {...}}]}`

---

### `DELETE /api/v1/conversations/{conv_id}`
**Response:** `{"success": true}`  
**Errors:** 403 (not owner)

---

### `DELETE /api/v1/conversations`
Deletes all conversations of the authenticated user.  
**Response:** `{"success": true}`

---

### `GET /api/v1/edt/classes`
**Response:**
```json
{
  "classes": [
    {"label": "IACS S4", "has_calendrier": false},
    {"label": "G2ER S6", "has_calendrier": false}
  ]
}
```

---

### `POST /api/v1/class-change-requests`
**Body:**
```json
{
  "requested_class_label": "TDI S2",
  "reason": "Je me suis inscrit dans la mauvaise filière."
}
```
**Response:** `{"success": true, "request": {...}}`  
**Errors:** 400 (admin user, invalid class), 409 (pending request exists)

---

### `GET /api/v1/class-change-requests/me`
**Response:** `{"requests": [...]}`

---

## Admin — `/api/v1/admin` (role: admin)

### `GET /api/v1/admin/stats`
**Response:**
```json
{
  "total_users": 120,
  "total_conversations": 450,
  "total_messages": 2300,
  "top_questions": [{"question": "...", "count": 15}],
  "weak_questions": [{"question": "...", "negative_count": 3}],
  "feedback_stats": {"positive": 180, "negative": 12}
}
```

---

### `GET /api/v1/admin/stats/most-asked`
**Query:** `?limit=10`  
**Response:** `{"questions": [...]}`  Source: Qdrant semantic cache

---

### `GET /api/v1/admin/conversations`
Returns all Q&A pairs for audit.  
**Response:** `{"qa_pairs": [{"question": "...", "answer": "...", "email": "...", "created_at": "..."}]}`

---

### `GET /api/v1/admin/users`
**Query:** `?query=email_filter`  
**Response:** `{"users": [{"email": "...", "role": "...", "class_label": "...", "message_count": 12, ...}]}`

---

### `POST /api/v1/admin/upload/faq`
**Form-data:** `file` (PDF/TXT/MD/JSON), `?rebuild=true`  
**Response:** `{"success": true, "message": "...", "filename": "..."}`  
**Errors:** 415 (unsupported extension)

---

### `POST /api/v1/admin/faq/rebuild`
Rebuilds Qdrant vectorstore from all FAQ files.  
**Response:** `{"success": true, "message": "Vectorstore reconstruit et cache purgé."}`

---

### `POST /api/v1/admin/cache/flush`
Flushes all Redis cache entries.  
**Response:** `{"success": true, "message": "Cache Redis vidé avec succès."}`

---

### `POST /api/v1/admin/data/cleanup`
**Query:** `?days=180`  
Deletes conversations older than N days.  
**Response:** `{"success": true, "deleted_count": 42, "message": "42 conversations supprimées."}`

---

### `GET /api/v1/admin/faq/files`
**Response:** `{"files": [{"name": "faq_usms.pdf", "size_kb": 120, "updated_at": "1714500000"}]}`

---

### `GET /api/v1/admin/faq/files/{filename}/preview`
**Response:**
```json
{
  "filename": "faq_usms.pdf",
  "file_type": "pdf",
  "snippet_count": 45,
  "truncated": true,
  "text": "...(up to 8000 chars)..."
}
```

---

### `GET /api/v1/admin/faq/files/{filename}/download`
**Response:** Binary file download

---

### `DELETE /api/v1/admin/faq/files/{filename}`
**Response:** `{"success": true}`

---

### `POST /api/v1/admin/faq/review`
**Body:**
```json
{
  "question": "Quel est le numéro du secrétariat?",
  "status": "treated",
  "note": "Ajouté dans le FAQ PDF v3"
}
```
**Response:** `{"success": true}`

---

### `GET /api/v1/admin/edt/published`
**Response:** `{"timetables": [{"id": 1, "class_label": "IACS S4", "academic_year": "2025-2026", "semester": "S4", "is_active": true}]}`

---

### `GET /api/v1/admin/edt/published/{timetable_id}`
**Response:** `{"timetable": {"id": 1, "class_label": "...", "slots": [...]}}`

---

### `POST /api/v1/admin/edt/publish`
**Body:**
```json
{
  "class_label": "IACS S4",
  "academic_year": "2025-2026",
  "semester": "S4",
  "slots": [
    {
      "day_of_week": 0,
      "start_time": "08:30",
      "end_time": "10:20",
      "subject": "Mathématiques",
      "professor": "Dr. Alaoui",
      "room": "Amphi A",
      "type": "Cours"
    }
  ]
}
```
**Response:** `{"success": true, "timetable_id": 7}`

---

### `DELETE /api/v1/admin/edt/published/{timetable_id}`
**Response:** `{"success": true}`

---

### `GET /api/v1/admin/class-change-requests`
**Query:** `?request_status=pending` (pending/approved/rejected/all)  
**Response:** `{"requests": [...]}`

---

### `POST /api/v1/admin/class-change-requests/{request_id}/decision`
**Body:**
```json
{
  "decision": "approve",
  "note": "Demande validée."
}
```
**Response:** `{"success": true, "request": {...}}`  
**Errors:** 404 (not found), 409 (already processed)

---

## Error Response Format

All errors follow FastAPI's default format:
```json
{
  "detail": "Human-readable error message"
}
```

HTTP codes used:
- `400` — Bad request / validation error
- `401` — Unauthorized (missing or expired token)
- `403` — Forbidden (wrong role or account locked)
- `404` — Not found
- `409` — Conflict (duplicate email, duplicate request)
- `415` — Unsupported media type
- `422` — Unprocessable entity (Pydantic validation)
- `429` — Too many requests (rate limit)
- `500` — Internal server error
