> Historical Chatbot-USMS documentation, retained for provenance and baseline reference. Claims, metrics, links and deployment instructions below are inherited and are not RagSec guarantees. See [RagSec README](../../README.md).

# Authentication & Authorization

## Overview

Authentication is JWT-based with refresh tokens stored in HttpOnly cookies. Authorization uses Role-Based Access Control (RBAC) with two roles: `student` and `admin`.

---

## JWT Configuration

| Parameter | Default | Env Variable |
|-----------|---------|--------------|
| Algorithm | HS256 | — |
| Access token lifetime | 15 minutes | `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Refresh token lifetime | 7 days | `REFRESH_TOKEN_EXPIRE_DAYS` |
| Secret key | (required ≥32 chars) | `JWT_SECRET_KEY` |

### Weak Secret Detection
At startup, the service checks if the configured secret is weak. Conditions that trigger a fallback to an **ephemeral in-memory key**:
- Key length < 32 characters
- Contains `change_me`, `changeme`, `default`, `secret`, or `password`
- An ephemeral key is generated with `secrets.token_urlsafe(48)` — sessions won't survive restarts

---

## Access Token

**Type:** Short-lived Bearer token (15 min default)

**Payload claims:**
```json
{
  "sub": "42",
  "email": "student@usms.ac.ma",
  "role": "student",
  "type": "access",
  "iat": 1714500000,
  "nbf": 1714500000,
  "exp": 1714500900
}
```

**Usage:** Sent as `Authorization: Bearer <token>` header on every authenticated request.

---

## Refresh Token

**Type:** Long-lived JWT (7 days)

**Payload claims:**
```json
{
  "sub": "42",
  "type": "refresh",
  "iat": 1714500000,
  "exp": 1715104800
}
```

**Storage:** HttpOnly cookie named `refresh_token`
- `samesite=strict`
- `secure=True` only when `ENV=production`
- `max-age=604800` (7 days in seconds)

**Rotation:** Every call to `POST /api/v1/auth/refresh` issues a new refresh token cookie.

---

## Auth Endpoints

### `POST /api/v1/auth/login`
Authenticates a user.

**Validations:**
1. Email must match `@usms.ac.ma` or `@usms.ma`
2. Password checked with bcrypt
3. Account lockout checked before password verification
4. On success: creates access token + refresh cookie + audit log entry

**Lockout Response (HTTP 403):**
```json
{
  "detail": "Compte verrouillé temporairement. Réessayez après HH:MM."
}
```

**Response on success:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 42,
    "email": "student@usms.ac.ma",
    "role": "student",
    "class_label": "IACS S4",
    "language": "fr"
  }
}
```

---

### `POST /api/v1/auth/register`
Creates a new student account.

**Validations:**
1. Email domain: `@usms.ac.ma` or `@usms.ma`
2. Password: ≥8 characters, ≥1 digit, ≥1 special character
3. `accepted_privacy: true` required (GDPR consent gate)
4. Email uniqueness enforced (returns HTTP 409 on duplicate)

---

### `POST /api/v1/auth/refresh`
Issues a new access token using the refresh token cookie.

- Reads `refresh_token` cookie
- Validates JWT type is `"refresh"`
- Loads user from DB to get current role
- Returns new access token + rotated refresh cookie

---

### `POST /api/v1/auth/logout`
Deletes the `refresh_token` cookie (sets `max-age=0`).

---

## Brute-Force Protection

Implemented in `db_service.verify_user()`:

| Event | Action |
|-------|--------|
| Failed login | Increment `failed_login_attempts` |
| 5th failure | Set `locked_until = now + 30 minutes` |
| Successful login | Reset `failed_login_attempts = 0`, clear `locked_until` |
| Login attempt while locked | Return `{"locked": True, "until": datetime}` |

The lockout duration is 30 minutes from the 5th failure. The route converts this to HTTP 403 with a human-readable time.

---

## FastAPI Dependencies

### `get_current_user`
Validates the Bearer token and returns the JWT payload as a dict:
```python
{"id": 42, "email": "student@usms.ac.ma", "role": "student"}
```

Used as `Depends(get_current_user)` on all protected endpoints.

Raises:
- HTTP 401 `"Votre session a expiré"` on expired token
- HTTP 401 `"Token invalide ou expiré"` on invalid token

### `require_admin`
Extends `get_current_user` — additionally asserts `role == "admin"`.

Raises:
- HTTP 403 `"Accès réservé aux administrateurs"` if not admin

---

## RBAC — Role-Based Access Control

| Role | Capabilities |
|------|-------------|
| `student` | Chat, view own conversations, update profile, export/delete own data, request class change |
| `admin` | All student capabilities + user management, FAQ upload, timetable publish, stats, audit, class change decisions |

Admin email: `admin@usms.ac.ma` (seeded from `ADMIN_PASSWORD` env var).

---

## Email Domain Validation

Both login and register enforce the regex:
```python
r"^[^@]+@(usms\.ac\.ma|usms\.ma)$"
```

Applied case-insensitively. Emails are stored lowercase.

---

## Frontend Token Handling

The frontend (`lib/api.ts`) uses an Axios interceptor:
1. Reads the token from `localStorage`
2. Attaches `Authorization: Bearer <token>` to every request
3. On HTTP 401 response: attempts `POST /api/v1/auth/refresh`
4. If refresh succeeds: retries original request
5. If refresh fails: clears localStorage + cookie → redirects to `/login`

Token + user object also stored as cookies (`token`, `role`) for Next.js middleware route guards.

---

## GDPR-Related Auth Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/me/export` | GET | Export all personal data as JSON (portability) |
| `/api/v1/auth/me` | DELETE | Delete account and all associated data |
| `/api/v1/auth/me/activity` | GET | Activity graph data for profile dashboard |
| `/api/v1/auth/me/timetable` | GET | User's current timetable |
| `/api/v1/auth/me/language` | POST | Update preferred language |
