> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Data Management

## Shared Data Sources of Truth

The project separates mutable operational data (in PostgreSQL) from versioned seed data (in git):

| Data | Location | Git-Versioned | Rebuilt? |
|------|----------|---------------|----------|
| FAQ documents | `backend/data/faq/` | Yes | No (source files) |
| Timetable seeds | `backend/data/seeds/timetables.json` | Yes | No (authoritative export) |
| Vector index | `backend/data/vectorstore_qdrant/` | No | Yes (from FAQ files) |
| User accounts | PostgreSQL | No | No |
| Conversations | PostgreSQL | No | No |

---

## FAQ Knowledge Base

**Directory:** `backend/data/faq/`

### Current Files

The `backend/data/faq/` directory contains the project's FAQ source files. Filenames and formats vary depending on how content was imported or generated (PDF, JSON, TXT, MD). Do not rely on hard-coded filenames in documentation — use the admin UI or list the directory to see the current set of source files.

If a canonical dataset is required for tests or CI, prefer the JSON export (e.g. `faq_ensa_bm_officielle_5000.json`) which is the machine-readable twin of any PDF source.

### Supported Formats
- `.pdf` — Parsed with `pdfplumber` (page-by-page text extraction)
- `.json` — Expected format: array of `{"question": "...", "answer": "..."}` objects
- `.txt` / `.md` — Plain text, chunked by paragraph

### Adding New Documents
1. Upload via admin UI: `POST /api/v1/admin/upload/faq` (triggers automatic rebuild)
2. Or manually copy to `backend/data/faq/` then rebuild the index

### Document Loading Pipeline (`rag_service.py`)

```python
_load_pdf(path)   → list of {page_content, metadata}
_load_faq_json(path) → list of Q+A pairs as documents
_load_text(path)  → chunked paragraphs
```

All loaders output a normalized list of document dicts with `page_content` and `metadata` fields.

---

## Timetable Seeds

**File:** `backend/data/seeds/timetables.json`

### Format

```json
[
  {
    "class_label": "IACS S4",
    "academic_year": "2025-2026",
    "semester": "S4",
    "slots": [
      {
        "day_of_week": 0,
        "start_time": "08:30",
        "end_time": "10:20",
        "subject": "Mathématiques Avancées",
        "professor": "Dr. Alaoui",
        "room": "Amphi A",
        "type": "Cours"
      }
    ]
  }
]
```

### Field Definitions

| Field | Type | Values |
|-------|------|--------|
| `class_label` | string | e.g., `G2ER`, `IACS S4`, `TDI S2` |
| `academic_year` | string | e.g., `2025-2026` |
| `semester` | string | e.g., `S1`–`S6` |
| `day_of_week` | integer | `0`=Monday … `6`=Sunday |
| `start_time` | string | `HH:MM` format (24-hour) |
| `end_time` | string | `HH:MM` format (24-hour) |
| `subject` | string | Course name |
| `professor` | string? | Nullable |
| `room` | string? | Nullable |
| `type` | string | `Cours`, `TD`, `TP` |

---

## Utility Scripts

### `bootstrap_dev_content.py`

**Full environment initialization script.**

```bash
PYTHONPATH=. python backend/scripts/bootstrap_dev_content.py
```

Steps:
1. Call `db_service.init_db()` — create all tables (run migrations if needed)
2. Call `db_service.seed_admin()` — create/update admin account
3. Check if `timetables` table is empty → if yes, run timetable seed import
4. Check if Qdrant `faq_campus` collection is empty → if yes, rebuild FAQ index

**When to use:** First-time setup, after fresh database, after environment reset.

---

### `seed_timetables.py`

**Imports timetables from JSON seed into the database.**

```bash
PYTHONPATH=. python backend/scripts/seed_timetables.py
PYTHONPATH=. python backend/scripts/seed_timetables.py --replace  # clears existing before import
```

- Reads `backend/data/seeds/timetables.json`
- For each timetable entry: creates a `timetable` row and all `timetable_slot` rows
- `--replace` flag: deletes all existing timetables before importing (full refresh)

**When to use:** After cloning the repo, after pulling new timetable data from a teammate.

---

### `export_timetables_seed.py`

**Exports current database timetables to the JSON seed file.**

```bash
PYTHONPATH=. python backend/scripts/export_timetables_seed.py
```

- Queries all active timetables from the database
- Serializes to `backend/data/seeds/timetables.json`
- Overwrites the existing file

**When to use:** After manually updating timetables via the admin UI, to commit the updated seed for teammates.

---

### `rebuild_faq_index.py`

**Rebuilds the Qdrant vector index from all FAQ files.**

```bash
PYTHONPATH=. python backend/scripts/rebuild_faq_index.py
```

- Loads all files from `backend/data/faq/`
- Parses and chunks content
- Embeds chunks with FastEmbed (BAAI/bge-small-en-v1.5)
- (Re)creates `faq_campus` collection in Qdrant
- Upserts all vectors

**When to use:** After adding or modifying FAQ files, after Qdrant data loss.

---

### `rag_pdf_benchmark.py`

**Benchmarks RAG retrieval quality on PDF documents.**

```bash
PYTHONPATH=. python backend/scripts/rag_pdf_benchmark.py
```

Runs a set of benchmark questions against the FAQ and measures:
- Retrieval precision
- Answer quality metrics
- Response latency

Used for tuning retrieval parameters (K, score thresholds).

---

## Logs

**File:** `backend/data/logs/app.log`

Written by Loguru. Contains:
- INFO: API requests, cache hits/misses, successful operations
- WARNING: Weak JWT secret, Redis unavailable, Qdrant unavailable
- ERROR: LLM failures, DB errors, stream persistence failures
- DEBUG: Metadata chunk parsing, class cache refresh

Not committed to git (listed in `.gitignore`).

---

## Vector Store

**Directory:** `backend/data/vectorstore_qdrant/`

Local Qdrant storage. Contains:
- `meta.json` — Qdrant storage metadata
- `collection/faq_campus/` — Main FAQ collection
- `collection/semantic_cache/` — Semantic cache collection

**Not committed to git** — reconstructed from FAQ files at startup.

In Docker: stored in the `qdrant_data` named volume (`/qdrant/storage`).

---

## Test Databases

Test runs create temporary SQLite databases in `backend/data/`:
- `*.db` files (e.g., `test_*.db`)
- `*.db-shm`, `*.db-wal` (SQLite WAL files)

These are git-ignored and safe to delete.
