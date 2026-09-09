> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Chatbot Engine

## Architecture

The chatbot logic is distributed across three services:

| Service | File | Role |
|---------|------|------|
| `router_service` | `router_service.py` | Question routing (EDT vs FAQ) |
| `chatbot_service` | `chatbot_service.py` | Emotion detection, timetable Q&A, response shaping |
| `groq_service` | `groq_service.py` | LLM integration, PII masking, translation, prompt safety |

---

## Question Routing

`router_service.route_question_api()` and `route_question_api_stream()` are the main dispatchers.

### Decision Logic

1. **`_is_edt_question(question)`** — keyword-based heuristic check
   - Keywords: days of week, `emploi du temps`, `cours`, `edt`, `schedule`, etc.
   - Returns `True` if the question is about timetables

2. **EDT path:** deterministic DB query → LLM reformulation
3. **FAQ path:** Qdrant semantic search → LLM generation

### Available Classes Cache
`get_available_classes(force_refresh=False)` loads the list of active timetable classes from the DB. Cached in-memory and refreshed when:
- Called with `force_refresh=True`
- A timetable is published or deleted by an admin

### Class Label Resolution
`resolve_class_label(class_label, available)` performs fuzzy matching:
- Exact match
- Prefix / contains matching
- Returns `(resolved, candidates)` tuple

---

## Emotion Detection

**File:** `chatbot_service.detect_user_state()`

### Detected States

| State | Description |
|-------|-------------|
| `urgent` | Time pressure, imminent deadline |
| `stressed` | General stress signals |
| `anxious` | Worry, uncertainty |
| `frustrated` | Repeated failures, anger tone |
| `sad` | Discouragement, distress |
| `neutral` | Default — no emotional signal |

### Detection Method — Hybrid Approach

**Step 1: Rule-based marker matching**
- Multilingual keyword lists per emotion (FR, EN, AR)
- Example markers for `stressed`:
  - FR: `stressé`, `panique`, `j'arrive pas`, `tout se passe mal`
  - EN: `stressed`, `panic`, `overwhelmed`
  - AR: `متوتر`, `ضائق`
- **Negation detection:** Handles `"je ne suis pas stressé"` correctly by checking for negation words within a 3-word window before the marker

**Step 2: LLM refinement (optional)**
- If no clear marker is found and an LLM call is cheap, the Groq LLM confirms or refines the detected state

**Output:**
```python
{
    "emotion": "stressed",
    "confidence": 0.85,
    "language": "fr"
}
```

---

## Timetable Q&A Mode

Activated when `_is_edt_question()` returns True.

### Process
1. Resolve the user's `class_label` (from profile or context)
2. If class unknown → prompt user to select from available classes
3. Query `get_active_timetable(class_label)` from DB
4. Parse natural language query to extract:
   - Day reference (today, tomorrow, Monday, etc.) via `dateparser`
   - Time slot filter (morning, afternoon)
   - Subject or professor filter
5. Filter timetable slots accordingly
6. Pass structured data to Groq for natural language reformulation

### Date/Time Resolution
- Uses `dateparser` with `APP_TIMEZONE` setting (default: `Africa/Casablanca`)
- Handles: today, tomorrow, day names, "cette semaine", "prochain lundi", etc.
- Timezone-aware datetime comparisons

### Track Code Inference
The service can infer the engineering track from partial class labels:
- `G2ER` — Génie Électrique et Énergies Renouvelables
- `IAA` — Ingénierie Agroalimentaire
- `IACS` — Ingénierie Appliquée et Conception de Systèmes
- `TDI` — Transformation Digitale et Innovation
- `2AP` — 2ème Année Préparatoire

---

## FAQ Mode (RAG)

When the question is not about timetables, the RAG pipeline is used.

See `docs/rag.md` for the full RAG documentation.

**Summary:**
1. Check semantic cache in Redis
2. If cache miss → Qdrant vector search
3. Build context from top-K chunks
4. Generate answer with Groq LLM
5. Cache result

---

## Response Tone Adaptation

Based on the detected emotion, the system prompt sent to Groq is modified:

| Emotion | Prompt Modification |
|---------|-------------------|
| `urgent` | Add urgency acknowledgment, prioritize key info upfront |
| `stressed` / `anxious` | Reassuring tone, structured step-by-step response |
| `frustrated` | Apologetic opening, direct actionable answer |
| `sad` | Empathetic tone, motivational closing |
| `neutral` | Standard informative response |

---

## Conversation History

The last 5 messages of a conversation are passed to the LLM for context:
```python
history = [{"role": m["role"], "content": m["content"]} for m in msgs]
```

History is NOT used when serving from the semantic cache (simple single-turn Q&A).

---

## SSE Streaming

The `/api/v1/chat/stream` endpoint uses `StreamingResponse` with `media_type="text/event-stream"`.

**Stream format:**
```
data: Hello, the exam\n\n
data:  schedule for\n\n
data:  your class is...\n\n
data: __metadata__:{"source_files": "faq_usms.pdf", "rag_confidence": "high"}\n\n
data: [DONE]\n\n
```

**Metadata chunks** (prefixed `__metadata__:`) carry:
- `source_files` — FAQ file origin
- `timetable` — structured timetable data
- `rag_confidence` — `high`, `medium`, `low`
- `rag_score` — float similarity score

**End signal:** `data: [DONE]`

After the stream closes, the full assembled answer + metadata is persisted to the database.

---

## Conversation Title Generation

New conversations automatically get an AI-generated title via `groq_service.summarize_title(question, language)`.
- Short prompt asking Groq for a ≤8-word summary of the question
- Falls back to the first 50 characters of the question on failure

---

## Human Oversight / Contestation

Users can contest any AI response via:
```
POST /api/v1/chat/contest/{message_id}
```

This logs a `user_contestation` audit event with the message ID, enabling admin review.
