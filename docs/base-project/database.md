> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Database — Schema & ORM

## Engine

| Environment | Database | Driver |
|-------------|----------|--------|
| Production (Docker) | PostgreSQL 15 | `pg8000` via SQLAlchemy |
| Local development | PostgreSQL 15 (Docker) | `pg8000` |
| Test / Legacy | SQLite | built-in |

The `DATABASE_URL` environment variable controls which is used.
SQLite compatibility is maintained automatically (`check_same_thread=False`, `PRAGMA foreign_keys=ON`).

---

## Migrations

Managed by **Alembic 1.14.1**.

- Config: `backend/alembic.ini`
- Migration scripts: `backend/alembic/versions/`
- Current head revision: `20260419_0003`

### Running Migrations
```bash
# Apply all pending migrations
cd backend && alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"
```

The `init_db()` function checks the Alembic version at startup and applies missing migrations automatically when the database already exists with Alembic metadata.

---

## Schema — Tables

### `users`
Core user accounts table.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | Auto-increment |
| `email` | String(255) | Unique, indexed, lowercase |
| `password` | String(255) | bcrypt hash (prefix `bcrypt$`) |
| `role` | String(50) | `student` or `admin` |
| `class_label` | String(120) | Nullable, assigned filière |
| `language` | String(5) | Default `fr` — `fr`, `en`, `ar` |
| `failed_login_attempts` | Integer | Default 0, reset on success |
| `locked_until` | DateTime | Nullable, lockout expiry |
| `created_at` | DateTime | UTC |

Relationships: one-to-many with `conversations` (cascade delete), `class_change_requests` (cascade delete).

---

### `conversations`
Chat session containers.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | Integer FK → `users.id` | Cascade delete |
| `title` | String(255) | AI-generated from first question |
| `created_at` | DateTime | UTC |
| `updated_at` | DateTime | Auto-updated |

Relationships: belongs to `User`, has many `messages` (cascade delete).

---

### `messages`
Individual Q&A turns within a conversation.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `conversation_id` | Integer FK → `conversations.id` | Cascade delete |
| `role` | String(50) | `user` or `assistant` |
| `content` | Text | Truncated to 1000 chars (+ `...`) before storage |
| `source_file` | String(255) | Nullable, FAQ file origin |
| `feedback` | Integer | `-1`, `0`, or `1` (thumb down/neutral/up) |
| `metadata_json` | Text | JSON string: `source_files`, `timetable`, `rag_confidence`, `rag_score` |
| `created_at` | DateTime | UTC |

---

### `audit_logs`
Tracks all security-critical actions for GDPR accountability.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `action` | String(100) | e.g. `user_login`, `data_export_requested`, `chat_request` |
| `user_id` | Integer FK → `users.id` | Nullable (cascade delete) |
| `timestamp` | DateTime | UTC |
| `details` | Text | Nullable, extra context |

Logged actions:
- `user_login`
- `user_registration`
- `chat_request`
- `data_export_requested`
- `conversation_deleted`
- `all_history_deleted`
- `user_contestation`

---

### `qa_review`
Admin-managed queue for flagging FAQ gaps.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `question_hash` | String(64) | SHA-256 hash, unique index |
| `question` | Text | Original question text |
| `status` | String(50) | `pending` or `treated` |
| `note` | Text | Admin review note |
| `updated_at` | DateTime | Auto-updated |

---

### `class_change_requests`
Student filière change workflow.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | Integer FK → `users.id` | Cascade delete |
| `current_class_label` | String(120) | At request time |
| `requested_class_label` | String(120) | Target class |
| `reason` | Text | Student's explanation |
| `status` | String(50) | `pending`, `approved`, `rejected` |
| `review_note` | Text | Admin decision note |
| `reviewed_by` | Integer FK → `users.id` | Admin who decided |
| `created_at` / `updated_at` | DateTime | UTC |

---

### `timetables`
Timetable headers (one per class/semester).

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `class_label` | String(120) | e.g. `G2ER`, `IACS S4`, indexed |
| `academic_year` | String(50) | e.g. `2025-2026` |
| `semester` | String(10) | e.g. `S4` |
| `is_active` | Boolean | Default `True` |
| `created_at` / `updated_at` | DateTime | UTC |

Relationship: has many `timetable_slots` (cascade delete).

---

### `timetable_slots`
Individual course time blocks.

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `timetable_id` | Integer FK → `timetables.id` | Cascade delete |
| `day_of_week` | Integer | 0=Monday … 6=Sunday |
| `start_time` | String(10) | e.g. `08:30` |
| `end_time` | String(10) | e.g. `10:20` |
| `subject` | String(255) | Course name |
| `professor` | String(255) | Nullable |
| `room` | String(100) | Nullable |
| `type` | String(50) | `Cours`, `TD`, `TP` |

---

### `alembic_version`
Alembic migration tracking table — single row with current revision hash.

---

## Password Hashing

Three hash formats are supported for backward compatibility:

| Format | Detection | Algorithm |
|--------|-----------|-----------|
| Modern | `stored.startswith("bcrypt$")` | bcrypt (cost=12) + prefix |
| Legacy bcrypt | `stored.startswith("$2a$")` etc. | bcrypt direct |
| Legacy SHA-256 | anything else | SHA-256 with random salt (32-byte hex) |

New passwords always use `bcrypt` with cost factor 12, prefixed with `bcrypt$`.  
Legacy passwords are upgraded on next successful login (`password_needs_rehash()`).

---

## Key Database Functions

### Initialization
- `init_db()` — Creates schema, runs Alembic migrations if needed
- `seed_admin()` — Upserts the admin account from `ADMIN_PASSWORD` env var

### User Operations
- `create_user(email, password, class_label, language)` → dict or None
- `find_user_by_email(email)` → dict or None
- `get_user_by_id(id)` → dict or None
- `verify_user(email, password)` → user dict, locked dict, or None
- `update_user_class(user_id, class_label)`
- `update_user_language(user_id, language)`
- `delete_user(user_id)` — deletes user and all associated data (cascade)
- `get_user_activity_graph(user_id)` → list of `{day, count}` for chart

### Conversation & Message Operations
- `create_conversation(user_id, title)` → conv_id
- `get_conversations(user_id)` → list of dicts
- `add_message(conv_id, role, content, source_file, metadata)`
- `get_messages(conv_id, limit=None)` → list of dicts
- `delete_conversation(conv_id)`
- `delete_all_conversations(user_id)`
- `conversation_belongs_to_user(conv_id, user_id)` → bool
- `message_belongs_to_user(msg_id, user_id)` → bool
- `update_message_feedback(msg_id, feedback_value)`
- `cleanup_old_conversations(days=180)` → deleted count

### Admin / Stats
- `get_all_users()` → list
- `get_users_activity(email_query)` → list with per-user message counts
- `get_total_conversations()` / `get_total_messages()` → int
- `get_top_questions(limit)` → most-asked questions by frequency
- `get_weak_questions_grouped(limit)` → questions with negative feedback
- `get_feedback_stats()` → `{"positive": N, "negative": N}`
- `get_all_qa_pairs()` → flat list of all Q&A for audit
- `log_audit_action(action, user_id, details)`

### Timetable Operations
- `save_timetable(class_label, academic_year, semester, slots)` → id
- `get_active_timetable(class_label)` → dict with slots list
- `get_timetable_by_id(id, active_only)` → dict
- `list_active_timetables()` → list
- `delete_timetable(id)` → bool

### Class Change Requests
- `create_class_change_request(user_id, requested_class_label, reason)`
- `get_class_change_requests(user_id, status)` → list
- `decide_class_change_request(request_id, admin_id, decision, note)`

---

## Docker Volume

PostgreSQL data is persisted in a named Docker volume:
```yaml
volumes:
  postgres_data:/var/lib/postgresql/data
```

Connection string in Docker: `postgresql://ensa_user:ensa_pass@postgres:5432/ensa_db`
