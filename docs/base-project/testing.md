> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Testing

## Overview

The project has a comprehensive backend test suite using **pytest**.

| Metric | Value |
|--------|-------|
| Total tests | 64 |
| Status (main branch) | All passing ✅ |
| Test framework | pytest |
| Test database | SQLite (in-memory / temp file) |

---

## Running Tests

```bash
# From the project root
PYTHONPATH=. pytest backend/tests/ -v

# Run a specific test module
PYTHONPATH=. pytest backend/tests/test_auth.py -v

# Run with coverage
PYTHONPATH=. pytest backend/tests/ --cov=backend --cov-report=term-missing
```

---

## Test Modules

### `test_auth.py` — Authentication
Tests for login, registration, JWT generation, token refresh, and account lockout.

Key scenarios:
- Successful login with valid credentials
- Login rejection with wrong password
- Login rejection with non-USMS email domain
- Registration with valid and invalid passwords (complexity rules)
- Registration with privacy policy not accepted
- Duplicate email registration (409 conflict)
- Account lockout after 5 failed attempts
- JWT token expiry handling
- Token refresh using refresh cookie
- Logout + cookie deletion

---

### `test_chat.py` — Chat Endpoints
Tests for question submission, conversation management, and feedback.

Key scenarios:
- Sending a question (non-streaming) and receiving an answer
- Streaming endpoint response structure
- Conversation creation on first message
- Conversation ID persistence across messages
- Message feedback update (positive / negative)
- Ownership validation (user cannot access another's conversation)
- Question deletion
- Empty question rejection

---

### `test_admin.py` — Admin Operations
Tests for statistics, user management, FAQ upload, and timetable publishing.

Key scenarios:
- Stats endpoint returns correct counts
- User listing with and without email filter
- FAQ file upload (valid and invalid extensions)
- Vectorstore rebuild trigger
- Cache flush
- Old data cleanup
- Timetable publish and delete
- Class change request decision (approve/reject)

---

### `test_rag_quality.py` — RAG System
Tests for vector search quality and fallback behavior.

Key scenarios:
- Relevant result returned for a known FAQ question
- Low-confidence fallback message returned for unknown question
- Language detection and translation
- Semantic cache hit after first query
- Qdrant collection creation and vector insertion
- Fallback to lexical search when Qdrant unavailable

---

### `test_sentiment_detection.py` — Emotion Detection
Tests for the hybrid emotion detection system.

Key scenarios:
- `stressed` detected for stress-marker phrases (FR, EN, AR)
- `urgent` detected for deadline phrases
- `frustrated` detected for anger markers
- `neutral` returned when no markers present
- Negation handling: "je ne suis pas stressé" → `neutral`
- Confidence scores within valid range [0, 1]
- Multi-language: Arabic and English markers detected correctly

---

### `test_timetable_seed.py` — Timetable Import/Export
Tests for timetable seeding and retrieval.

Key scenarios:
- Import timetable from JSON seed file
- Retrieve active timetable by class label
- Verify slot count matches seed data
- Publish timetable via admin endpoint
- Delete timetable
- Class label resolution (fuzzy matching)

---

### `test_db_improvements.py` — Database Operations
Tests for database CRUD, cascade deletes, and integrity constraints.

Key scenarios:
- User creation and retrieval
- Cascade delete: deleting user removes conversations and messages
- Password rehash migration (legacy SHA-256 → bcrypt)
- Audit log creation
- Conversation cleanup by age (180-day purge)
- `conversation_belongs_to_user` / `message_belongs_to_user` checks

---

### `test_health.py` — Health Endpoints
Tests for liveness and readiness probes.

Key scenarios:
- `GET /healthz` returns `{"status": "ok"}`
- `GET /` returns `{"status": "ok", "version": "2.0.0", "docs": "/docs"}`
- Status is `partial_error` when Qdrant unreachable

---

### `test_utils.py` — Utility Functions
Tests for helper functions.

Key scenarios:
- Timetable slot filtering by day
- Date parsing for "today", "tomorrow", day names
- Track code inference from partial class label
- PII masking (email and phone number detection)

---

## Test Configuration — `conftest.py`

Provides pytest fixtures:

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `client` | function | FastAPI `TestClient` with SQLite test DB |
| `auth_headers` | function | JWT headers for a seeded student user |
| `admin_headers` | function | JWT headers for the seeded admin user |
| `test_db` | function | Isolated SQLite session for direct DB testing |

The test database is a temporary SQLite file (or in-memory), separate from the development database. It is created fresh for each test session.

---

## CI Integration

Tests run automatically on every push and pull request via GitHub Actions:

```yaml
- name: Run backend tests
  run: |
    pip install -r requirements.txt
    PYTHONPATH=. pytest backend/tests/ -v
```

The workflow fails if any test does not pass.
