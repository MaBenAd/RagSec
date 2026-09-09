> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# LLM Integration — GroqCloud

## Overview

The application uses **GroqCloud** as its LLM provider with the **LLaMA 3.3 70B Versatile** model. All LLM logic is centralized in `backend/services/groq_service.py` (~1400 lines).

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | (required) | GroqCloud API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Model identifier |
| `CHAT_TIMEOUT_SECONDS` | `90` | Per-call timeout |

**Client initialization:** Lazy singleton via `get_client()` with `@lru_cache`.

---

## Use Cases

The Groq client is used for 5 distinct tasks:

### 1. FAQ Answer Generation
**Function:** Called from `rag_service.py` after context retrieval

**System prompt structure:**
```
Tu es l'assistant virtuel d'ENSA Béni Mellal (Université Sultan Moulay Slimane).
Réponds uniquement en {language}.
Base ta réponse UNIQUEMENT sur le contexte fourni.
Si l'information n'est pas dans le contexte, dis-le clairement.
{style_instruction_based_on_emotion}
```

**User message:**
```
Contexte:
{retrieved_chunks}

Question: {user_question}
```

---

### 2. Timetable Answer Reformulation
**Function:** Called from `chatbot_service.py` after DB query

Converts structured timetable data (dict of slots) into natural language.

**System prompt:** Instructs the model to format a timetable response in the user's language with appropriate structure (lists, time formatting).

---

### 3. Conversation Title Generation
**Function:** `summarize_title(question, language)`

Generates a concise (≤8 words) conversation title from the first user question.

```python
prompt = f"Résume en 5-8 mots maximum, sans ponctuation finale: {question}"
```

Falls back to `question[:50]` if the LLM call fails.

---

### 4. Language Detection & Translation
**Functions:** 
- `detect_language(text)` — returns `"fr"`, `"en"`, or `"ar"`
- `translate_to_french(text)` — for EN/AR queries before FAQ retrieval
- `translate_response(text, target_lang)` — translates FR answer to EN/AR

Used to support multilingual users while keeping the FAQ retrieval in French.

---

### 5. Emotion State Refinement (optional)
**Function:** Called from `chatbot_service.detect_user_state()` as a secondary pass

Only invoked when rule-based detection is inconclusive. Confirms or overrides the rule-based emotion label with a low-cost prompt.

---

## Response Style Adaptation

`_style_instruction(user_state)` returns an extra system prompt line based on detected emotion:

| Emotion | Style Instruction |
|---------|-------------------|
| `urgent` | "L'utilisateur semble dans l'urgence. Sois direct et concis." |
| `stressed` | "L'utilisateur semble stressé. Adopte un ton rassurant et structuré." |
| `anxious` | "L'utilisateur semble anxieux. Explique clairement et rassure." |
| `frustrated` | "L'utilisateur semble frustré. Sois compréhensif et propose des solutions directement." |
| `sad` | "L'utilisateur semble découragé. Sois empathique et encourageant." |
| `neutral` | (no extra instruction) |

---

## PII Masking

Before every LLM call, personally identifiable information in the user's question is masked:

```python
_pii_mask(text) → masked_text
```

**Patterns masked:**
- Email addresses: `user@example.com` → `[EMAIL]`
- French/Moroccan phone numbers: `06 12 34 56 78`, `+212 6 12 34 56 78` → `[PHONE]`

Implementation uses compiled regex patterns for performance.

**Why:** Prevents personal data from being transmitted to the GroqCloud cloud infrastructure, maintaining GDPR data minimization compliance.

---

## Prompt Injection Protection

Before submission, queries are checked for injection attempt patterns:

```python
_INJECTION_PATTERNS = [
    r"ignore (previous|all|prior) instructions",
    r"you are now",
    r"act as if you are",
    r"disregard",
    r"forget (everything|all|your)",
    r"new persona",
    # ...
]
```

Detected injection attempts are sanitized or rejected.

---

## Cacheable Answer Filtering

`is_cacheable_faq_answer(answer)` determines if an LLM response is worth caching:

**Not cached if:**
- Answer length < 25 characters (too short / likely an error)
- Starts with `"oui."`, `"oui,"`, `"yes."`, `"yes,"` with total length < 220 chars (generic)
- Starts with `"le site"`, `"la page d'accueil"` (noisy web-scraped response)

---

## Track Information

The service maintains a `_TRACK_DETAILS` dictionary used to enrich context about engineering programs:

| Code | Full Name | Key Aliases |
|------|-----------|-------------|
| `G2ER` | Génie Électrique et Énergies Renouvelables | energies renouvelables, genie electrique |
| `IAA` | Industries Agroalimentaires | industrie agroalimentaire, agroalimentaire |
| `IACS` | Intelligence Artificielle et Cybersécurité | intelligence artificielle, cybersecurite |
| `TDI` | Transformation Digitale Industrielle | transformation digitale, industrie 4.0 |

Used when the LLM needs context about what a filière code means.

---

## Stopwords

French and English stopwords are stripped from FAQ queries before embedding to improve vector search quality:

```python
_STOPWORDS = {"a", "à", "au", "avec", "dans", "de", "des", "du", ...}
```

Applied in query preprocessing before Qdrant search.

---

## Error Handling

All Groq calls are wrapped with:
- Timeout: `CHAT_TIMEOUT_SECONDS` (default 90s)
- Exception catch: returns a graceful error message starting with `❌` on failure
- Connection check in health endpoint: `GET /` tests `get_client()`

---

## Streaming

For SSE streaming responses, the Groq client is called with `stream=True`:

```python
response = client.chat.completions.create(
    model=GROQ_MODEL,
    messages=[...],
    stream=True,
    timeout=CHAT_TIMEOUT_SECONDS,
)
for chunk in response:
    delta = chunk.choices[0].delta.content or ""
    yield delta
```

Each yielded chunk is forwarded directly to the SSE stream in `routes/chat.py`.
