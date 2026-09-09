> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# RAG System — Retrieval-Augmented Generation

## Overview

The RAG system enables the chatbot to answer general university questions by searching a curated knowledge base and generating grounded answers with a large language model.

**File:** `backend/services/rag_service.py` (~1100 lines)

---

## Components

| Component | Technology | Details |
|-----------|-----------|---------|
| Vector store | Qdrant 1.17.1 | Local file storage or remote server |
| Embedding model | BAAI/bge-small-en-v1.5 | 384-dim, CPU-optimized via FastEmbed |
| LLM | GroqCloud LLaMA-3.3-70B | Answer generation |
| FAQ sources | PDFs, JSON, TXT | `backend/data/faq/` |

---

## Qdrant Collections

| Collection | Purpose |
|-----------|---------|
| `faq_campus` | Main FAQ knowledge base (embedded FAQ chunks) |
| `semantic_cache` | Cache of recently generated answers |

**Storage:** `backend/data/vectorstore_qdrant/` (local), or remote via `QDRANT_URL`.

Not committed to git — rebuilt from FAQ files at startup or on demand.

---

## FAQ Sources

Located in `backend/data/faq/`.

The directory contains FAQ sources in different formats (PDF, JSON, TXT, MD). Filenames may change over time; prefer the JSON exports for programmatic pipelines and use the admin UI or `backend/data/faq/` listing to discover current files.

Supported upload formats: `.pdf`, `.txt`, `.md`, `.json`

---

## Embedding Model

- **Model:** `BAAI/bge-small-en-v1.5`
- **Provider:** FastEmbed 0.8.0 (runs locally, CPU-only)
- **Dimensions:** 384
- **Language:** Multilingual support (optimized for English/French)

---

## Retrieval Pipeline

### 1. Query Preprocessing
- Strip whitespace and normalize input
- Detect language (FR/EN/AR)
- If EN or AR → translate to FR for retrieval (FAQ is primarily French)

### 2. Query Augmentation
The query is expanded with reformulations to improve recall:
- Synonym expansion
- Intent-specific rewrites (e.g., "who is the director" → "nom directeur ENSA")

### 3. Intent-Based Scoring
Query intent is classified into categories that influence result re-ranking:

| Intent | Examples |
|--------|---------|
| `contact` | email, phone, "comment contacter" |
| `who` | "qui est", "quel professeur" |
| `where` | "où", "quel bâtiment", "salle" |
| `list` | "quelles sont les", "liste des" |
| `definition` | "qu'est-ce que", "c'est quoi" |

Results matching the detected intent are boosted in ranking.

### 4. Vector Search
- Qdrant `search()` with cosine similarity
- Top-K retrieval (K configurable, default 5)
- Score threshold filtering

### 5. De-noising
Chunks penalized if they contain:
- Garbled characters (OCR artifacts)
- Excessive punctuation patterns
- Very short content (< 50 characters)

### 6. Fallback
If Qdrant is unavailable → lexical keyword search over FAQ text files.

---

## Answer Generation

After retrieval, the top chunks are passed as context to the Groq LLM:

```
System: Tu es l'assistant virtuel d'ENSA Béni Mellal. Réponds uniquement en [language].
        Base ta réponse sur le contexte fourni. Si l'information n'est pas dans le contexte,
        dis-le clairement.

Context:
[chunk 1]
[chunk 2]
...

User: [question]
```

### Confidence Scoring
The RAG service assigns a confidence level based on:
- Top-1 similarity score

| Score Range | Confidence Level |
|------------|----------------|
| ≥ 0.80 | `high` |
| ≥ 0.55 | `medium` |
| < 0.55 | `low` |

Confidence level and raw score are returned in the API response and stored in message metadata.

---

## Semantic Cache (Qdrant Collection)

**Purpose:** Avoid redundant LLM calls for semantically similar questions.

### Write path
After generating a new answer:
1. Embed the question
2. Store in the `semantic_cache` Qdrant collection with `{answer, source}` payload
3. TTL managed via Redis (see `cache_service.set_semantic_cache()`)

### Read path
Before calling the LLM:
1. Check Redis key for the question hash (fast exact match)
2. If miss → check `semantic_cache` Qdrant collection for similar vectors (semantic match)
3. If similarity ≥ threshold → return cached answer

### Hit Tracking
Cache hit counts tracked for analytics (`get_most_asked_questions()`).

---

## Vectorstore Management

### Rebuild
```bash
python backend/scripts/rebuild_faq_index.py
```
Or via admin endpoint: `POST /api/v1/admin/faq/rebuild`

Process:
1. Load all files from `backend/data/faq/`
2. Parse PDF pages via `pdfplumber`, JSON Q&A pairs, or plain text
3. Chunk text with overlap
4. Embed all chunks with FastEmbed
5. (Re)create `faq_campus` collection in Qdrant
6. Upsert all vectors
7. Invalidate Redis cache prefix `rag`

### Admin FAQ Upload
Admins can upload new FAQ documents via `POST /api/v1/admin/upload/faq`.
- Validates file extension (`.pdf`, `.txt`, `.md`, `.json`)
- Saves to `backend/data/faq/`
- Optionally triggers automatic vectorstore rebuild (`rebuild=true` query param)

### Admin FAQ File Management
- `GET /api/v1/admin/faq/files` — list files with size and timestamp
- `GET /api/v1/admin/faq/files/{filename}/preview` — preview text content (max 8000 chars)
- `GET /api/v1/admin/faq/files/{filename}/download` — download original file
- `DELETE /api/v1/admin/faq/files/{filename}` — remove file

---

## Multilingual Retrieval

The FAQ knowledge base is primarily in French. For non-French queries:

1. Detect query language (FR/EN/AR)
2. Translate the query to French before embedding
3. Retrieve French chunks
4. Generate answer in the user's language (Groq prompt specifies target language)

Translation is done via Groq with a lightweight translation prompt to avoid external translation API costs.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant server URL |
| `VECTORSTORE_PATH` | `backend/data/vectorstore_qdrant` | Local Qdrant storage path |
| `ENABLE_RAG_FALLBACK` | `false` | Enable lexical fallback if Qdrant fails |
| `CHAT_TIMEOUT_SECONDS` | `90` | LLM call timeout |
