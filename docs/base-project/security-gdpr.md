> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Security & GDPR Compliance

## Security Architecture

The application follows a defense-in-depth approach with security controls at every layer.

---

## Authentication Security

### JWT Hardening
- Algorithm: **HS256** (HMAC-SHA256)
- Access token: **15-minute** lifetime (short-lived, minimizes exposure)
- Refresh token: **7-day** lifetime, stored in **HttpOnly cookie** (inaccessible to JavaScript)
- Weak secret detection at startup: falls back to ephemeral key if `JWT_SECRET_KEY` is missing or trivial
- Required claims validated: `sub`, `email`, `role`, `exp`

### Refresh Token Cookie
```
Set-Cookie: refresh_token=<jwt>; HttpOnly; SameSite=Strict; Max-Age=604800; Secure (HTTPS only)
```

### Session Invalidation
- `POST /api/v1/auth/logout` → deletes `refresh_token` cookie
- Frontend clears `localStorage` token + role cookies on logout

---

## Brute-Force Protection

| Parameter | Value |
|-----------|-------|
| Max failed attempts | 5 |
| Lockout duration | 30 minutes |
| Lockout field | `users.locked_until` (datetime) |
| Counter reset | On successful login |

Implementation in `db_service.verify_user()`:
- Checks `locked_until > now` before verifying password
- Increments `failed_login_attempts` on every failure
- Sets `locked_until = now + 30 min` on the 5th failure
- Returns `{"locked": True, "until": <datetime>}` to route

---

## Password Policy

**Enforcement at registration and anywhere passwords are set:**

| Rule | Requirement |
|------|-------------|
| Minimum length | 8 characters |
| Digit | At least 1 digit (`0-9`) |
| Special character | At least 1 non-alphanumeric character |
| Hashing | bcrypt with cost factor 12 |

**Storage format:** `bcrypt$<hash>` (prevents bare bcrypt hash collisions)

**Legacy passwords** (SHA-256 with hex salt) are upgraded to bcrypt on next successful login.

---

## Email Domain Restriction

Only institutional email addresses are accepted:
```python
r"^[^@]+@(usms\.ac\.ma|usms\.ma)$"
```

Enforced on both login and registration. Prevents unauthorized external account creation.

---

## GDPR / RGPD Compliance

The project targets **"Gold Standard"** GDPR compliance with Privacy by Design.

### Article 17 — Right to Erasure (Right to be Forgotten)

**Implementation:** `DELETE /api/v1/auth/me`
- Deletes the user account
- Cascades to: all conversations, all messages, all audit logs, all class change requests
- Irreversible — no soft delete
- Available from the profile page UI

### Article 20 — Right to Data Portability

**Implementation:** `GET /api/v1/auth/me/export`
- Returns all personal data as machine-readable JSON:
  - Profile: email, role, class_label, language, created_at
  - All conversations with full message content and timestamps
- Audit log entry created on export (`data_export_requested`)
- One-click download from the profile page

### Article 5(1)(c) — Data Minimization

**PII Masking:** Emails and phone numbers are automatically masked before being sent to GroqCloud:
- Input: `Mon email est jean@gmail.com, tel: 06 12 34 56 78`
- Processed: `Mon email est [EMAIL], tel: [PHONE]`

Implemented in `groq_service.py` before every LLM call.

### Article 5(1)(e) — Storage Limitation

**Implementation:** `POST /api/v1/admin/data/cleanup?days=180`
- Auto-purges conversations older than N days (default: 180)
- Available as an admin action or schedulable
- Count of deleted conversations returned in response

### Article 5(2) — Accountability (Audit Logging)

All critical actions are logged in the `audit_logs` table:

| Action | Trigger |
|--------|---------|
| `user_login` | Successful login |
| `user_registration` | New account created |
| `chat_request` | Every chat message sent |
| `data_export_requested` | User downloads their data |
| `conversation_deleted` | Single conversation deleted |
| `all_history_deleted` | Bulk conversation deletion |
| `user_contestation` | User contests an AI response |

Each log entry records: `action`, `user_id`, `timestamp`, `details`.

### Transparency

- **RAG confidence scores** returned in API responses (`rag_confidence`, `rag_score`)
- **AI identification:** Responses clearly identify the AI role
- **Source attribution:** `source_file` field identifies the FAQ document used
- **Human contestation:** Users can flag any response for human review

### Privacy Policy

Full privacy policy accessible at `/privacy` (public page, no login required).

---

## Security Headers

Applied to every HTTP response via FastAPI middleware:

| Header | Value | Protection |
|--------|-------|-----------|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME sniffing attacks |
| `X-Frame-Options` | `DENY` | Prevents clickjacking |
| `Referrer-Policy` | `no-referrer` | Prevents URL leakage |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Denies browser feature access |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Forces HTTPS (HTTPS only) |

---

## CORS Configuration

```python
allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # + CORS_ORIGINS env var values
]
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

For production, `CORS_ORIGINS` should list only the exact frontend URL.

---

## Prompt Injection Protection

Implemented in `groq_service.py`:

**Guardrails applied before every LLM call:**
1. Input length limiting (questions truncated at 2000 chars in schema)
2. System prompt isolation (user input never injected into system role)
3. Pattern-based filtering for injection attempts (e.g., "ignore previous instructions")
4. PII masking before transmission to cloud LLM

---

## Rate Limiting

**Library:** SlowAPI 0.1.9

| Endpoint | Limit | Key |
|----------|-------|-----|
| `POST /api/v1/chat` | 10/minute | Remote IP |
| `POST /api/v1/chat/stream` | 10/minute | Remote IP |

Exceeded requests: HTTP 429 with `Retry-After` header.

---

## RBAC (Role-Based Access Control)

| Endpoint Group | Required Role |
|---------------|--------------|
| `/api/v1/auth/*` (own data) | Any authenticated user |
| `/api/v1/chat/*` | Any authenticated user |
| `/api/v1/conversations/*` | Any authenticated user (own data only) |
| `/api/v1/admin/*` | `admin` role only |

**Ownership enforcement:**
- `conversation_belongs_to_user(conv_id, user_id)` — prevents IDOR on conversations
- `message_belongs_to_user(msg_id, user_id)` — prevents IDOR on messages

---

## Input Validation

All request bodies validated by Pydantic 2 schemas with strict field constraints:

| Field | Constraint |
|-------|-----------|
| `email` | EmailStr + domain regex |
| `password` | min 8 chars + complexity rules |
| `question` | min 1, max 2000 chars |
| `language` | pattern `^(fr\|en\|ar)$` |
| `feedback` | integer, `ge=-1, le=1` |
| `decision` | pattern `^(approve\|reject)$` |
| `status` | pattern `^(pending\|treated)$` |

---

## Security Checklist

| Control | Status |
|---------|--------|
| GDPR Right to Erasure | ✅ |
| GDPR Right to Portability | ✅ |
| GDPR Data Minimization (PII masking) | ✅ |
| GDPR Storage Limitation (180-day purge) | ✅ |
| GDPR Audit Logging | ✅ |
| GDPR Transparency (confidence scores, AI labeling) | ✅ |
| JWT Bearer auth with short-lived tokens | ✅ |
| Refresh tokens in HttpOnly cookies | ✅ |
| Brute-force protection (account lockout) | ✅ |
| Password complexity policy | ✅ |
| bcrypt hashing (cost=12) | ✅ |
| Email domain restriction | ✅ |
| RBAC (student vs admin) | ✅ |
| Ownership validation (IDOR prevention) | ✅ |
| Security HTTP headers | ✅ |
| CORS configuration | ✅ |
| Rate limiting | ✅ |
| Input validation (Pydantic) | ✅ |
| PII masking before cloud LLM | ✅ |
| Prompt injection guardrails | ✅ |
| Privacy consent gate at registration | ✅ |
| Human oversight / contestation | ✅ |
| HTTPS-ready (secure cookies, HSTS) | ✅ |

### Roadmap (Planned)

| Control | Status |
|---------|--------|
| Encryption at rest (PostgreSQL column-level) | ⏳ Planned |
| Refresh token rotation (full rotation with revocation list) | ⏳ In progress |
| WCAG 2.1 accessibility audit | ⏳ Planned |
| Redis AUTH password | ⏳ Planned (production) |
