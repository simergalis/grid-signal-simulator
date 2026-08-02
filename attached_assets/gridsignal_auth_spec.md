# GridSignal Auth System — Current State Specification

> **Purpose:** Complete specification of the existing single-tenant authentication database, logic, and UI so a multi-tenant design can be built from it.

---

## 1. Overview

GridSignal uses **email-based one-time-password (OTP) sign-in** as its primary authentication mechanism. A password is optional — accounts start passwordless and users may add one at any time. There is no self-registration; all accounts are created by an administrator.

Sessions are carried as a signed **JWT in an httpOnly cookie** (`gs_session`). The cookie is issued on successful OTP verification or password sign-in and expires after 24 hours.

---

## 2. Database

### 2.1 Engine

| Environment | Driver | Backend |
|---|---|---|
| Production (Replit deploy) | `asyncpg` | Replit managed PostgreSQL (Neon) — persists across redeploys |
| Development / local | `aiosqlite` | SQLite file at `gridsignal_sim/../gridsignal.db` |

Resolution order: `DATABASE_URL` env var (set automatically by Replit) → `GRIDSIGNAL_DB` env var → default SQLite path.

`DATABASE_URL` arrives as a libpq URL (`postgresql://...`). The code converts it to `postgresql+asyncpg://` and strips `sslmode=disable` before passing to SQLAlchemy.

### 2.2 Schema: `auth_user`

```sql
CREATE TABLE auth_user (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,   -- SERIAL in PostgreSQL
    email         TEXT     NOT NULL UNIQUE,
    phone         TEXT     NOT NULL DEFAULT '',         -- stored as-entered; not used for auth
    display_name  TEXT     NOT NULL,
    role          TEXT     NOT NULL DEFAULT 'operator',
    password_hash TEXT     NOT NULL DEFAULT '',         -- bcrypt $2b$... or empty string
    is_active     BOOLEAN  NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_auth_user_role
        CHECK (role IN ('viewer', 'operator', 'approver', 'admin'))
);
```

**Notes:**
- `email` is case-folded to lowercase on every write and lookup.
- `phone` is stored for display only; it is not verified and not used in any auth check.
- `password_hash` is an empty string (`""`) when no password has been set. All auth code checks `bool(password_hash)` to distinguish "no password" from "password set".
- No `created_at` / `updated_at` timestamps exist on this table.
- No foreign keys. `auth_user` is entirely self-contained.

### 2.3 Startup migration guard (SQLite only)

At app startup, `create_auth_tables()` runs:

1. **PostgreSQL path:** calls `metadata.create_all(checkfirst=True)` directly — no migration guard needed.
2. **SQLite path:** reads `sqlite_master` to check if `'admin'` appears in the stored `CREATE TABLE` SQL. If the table exists but `'admin'` is absent from the CHECK constraint (legacy schema), the table is dropped and recreated before `create_all`. This guard is safe because the old constraint predates any real data.

### 2.4 Initial admin seeding

On every cold start, after table creation:

```
if INITIAL_ADMIN_EMAIL is set AND auth_user is empty:
    INSERT admin account (email=INITIAL_ADMIN_EMAIL, display_name=INITIAL_ADMIN_NAME, role=admin, password_hash='')
```

This covers first deploy to a fresh PostgreSQL database. The seeded account signs in via OTP immediately; there is no standing password.

---

## 3. Roles

Four roles are defined. The app enforces them at the API level; the database only stores the string.

| Role | Description |
|---|---|
| `viewer` | Read-only access to simulation output |
| `operator` | Can start/stop runs, adjust parameters |
| `approver` | Can approve AI-generated parameter proposals |
| `admin` | Full access including user management |

Role is assignable at account creation and changeable at any time via `PATCH /api/admin/users/{id}`. An `admin` may not be demoted by themselves (not enforced server-side in current code — design note for multi-tenant).

---

## 4. Authentication Flow

### 4.1 OTP sign-in (primary path)

```
Step 1 — Request code
  POST /api/auth/request-code  { email }
  ↓
  Rate-limit: 60s cooldown between code requests per email address.
  Generates a 6-digit code via SystemRandom.
  Stores in in-memory dict:
    _otp_store[email] = { code, expires_at (10 min), attempts: 0, last_sent }
  If email exists and is_active: sends code via SendGrid (send_otp_email).
  Returns 200 { ok: true, email_sent: bool } — always 200 even for unknown emails
  (avoids account enumeration).

Step 2 — Verify code
  POST /api/auth/login  { email, code }
  ↓
  Look up _otp_store[email].
  Increment attempts counter (max 5 — lockout after 5 wrong guesses).
  Compare code strings (exact match, no timing-safe compare needed — 6-digit space).
  On match: pop entry (single-use), look up user in DB, issue JWT cookie.
  On failure: generic "Invalid or expired code." regardless of reason.
  Returns 200 { ok: true, display_name, role }
```

**OTP store:** purely in-memory (`dict`). Codes are lost on server restart. TTL = 10 minutes. Max attempts = 5. Resend cooldown = 60 seconds.

### 4.2 Session cookie

```
Name:       gs_session
httpOnly:   true
samesite:   lax
max_age:    86400 (24 hours)
path:       /
secure:     NOT currently set (no explicit secure=True in set_cookie call)
```

The cookie carries a JWT with:
```json
{ "sub": "<user_id>", "email": "<email>", "exp": "<unix_timestamp>" }
```

JWT is signed HS256 using `JWT_SECRET` env var, falling back to `SESSION_SECRET`. The app raises `RuntimeError` at import time if neither is set.

### 4.3 Session validation (`get_current_user` dependency)

On every authenticated route:
1. Read `gs_session` cookie.
2. Decode and verify JWT signature + expiry.
3. Load `AuthUser` by `payload["sub"]` (integer user ID).
4. Reject if user not found or `is_active == False`.

There is no server-side session store — validity is determined entirely by the JWT. A deactivated user remains valid until their 24-hour JWT expires.

### 4.4 Logout

```
POST /api/auth/logout
```
Clears the `gs_session` cookie client-side by calling `response.delete_cookie`. No server-side token revocation.

---

## 5. Password Management

### 5.1 Hashing

bcrypt via the `bcrypt` library directly (not passlib — passlib 4.x removed `__about__` which broke the bcrypt backend). Cost factor: default `gensalt()` (~12 rounds).

```python
hash_password(plain: str) -> str          # returns $2b$... string
verify_password(plain: str, hashed: str) -> bool
```

### 5.2 First-time password set

Accounts start with `password_hash = ""`. The `GET /api/auth/password-status` endpoint returns `{ has_password: bool }`. When `has_password = false`, the change-password form omits the "current password" field and the backend skips current-password verification.

### 5.3 User change-password

```
POST /api/auth/change-password  { current_password: str|null, new_password: str }
Requires: active session cookie.
Rules:
  - new_password must be ≥ 8 characters.
  - If password_hash is non-empty: current_password must verify.
  - If password_hash is empty: current_password is ignored (first-time set).
```

### 5.4 Admin password reset

```
PATCH /api/admin/users/{id}  { password: str }
Requires: admin session or X-Admin-Key header.
Rules:
  - password must be ≥ 8 characters (enforced client-side only — design gap).
  - Sets new bcrypt hash unconditionally (no current-password required).
```

---

## 6. Admin API

All admin routes are under `/api/admin/`. Access requires **either**:
- `X-Admin-Key` header matching `ADMIN_SECRET` env var (API/curl callers), **or**
- A valid session cookie where the authenticated user has `role = "admin"`.

If `ADMIN_SECRET` is not set, the header path is disabled; session-based admin access still works.

### 6.1 Endpoints

| Method | Path | Action |
|---|---|---|
| `POST` | `/api/admin/users` | Create account; sends welcome email |
| `GET` | `/api/admin/users` | List all users (all roles, active + inactive) |
| `PATCH` | `/api/admin/users/{id}` | Update `is_active`, `role`, and/or `password` |
| `DELETE` | `/api/admin/users/{id}` | Permanently delete account (no soft-delete) |
| `GET` | `/api/admin/bootstrap` | Break-glass: create recovery admin when all admins locked out |
| `GET` | `/api/admin/email-check` | Diagnostic: verify SendGrid configuration |

### 6.2 Create user (`POST /api/admin/users`)

Request:
```json
{ "email": "...", "display_name": "...", "role": "operator", "phone": "" }
```

- `phone` is optional and not used for auth.
- `password_hash` is always `""` on creation.
- Sends a welcome email via SendGrid (non-fatal if delivery fails).
- Returns `409 Conflict` if email already exists.

### 6.3 Bootstrap / break-glass (`GET /api/admin/bootstrap`)

- Requires `X-Admin-Key` header only (no session fallback — this endpoint exists precisely because there are no valid sessions).
- If at least one active admin exists: returns `{ status: "ok", admin_exists: true }`.
- If no active admin exists:
  - Creates or reactivates a well-known recovery account (`recovery@gridsignal.io`).
  - Injects a 6-digit OTP into the live auth store (10-minute TTL).
  - Returns the email and one-time code in the response body.
  - Caller posts `{ email, code }` to `/api/auth/login` to get a session cookie.

---

## 7. Email Service

All emails sent via **SendGrid** (`sendgrid` Python library).

| Config | Source |
|---|---|
| `SENDGRID_API_KEY` | Replit Secret |
| `SENDGRID_FROM_EMAIL` | Replit Secret — must be a verified SendGrid sender identity |

**Email types:**
- `send_otp_email(to, display_name, code)` — sign-in code, HTML + plain-text
- `send_welcome_email(to, display_name)` — sent on account creation
- `send_password_reset_email(to, display_name, temp_password)` — sent on admin password reset

All send functions:
- Return `bool` (True = SendGrid 2xx, False = any failure).
- Log the full SendGrid response body on non-2xx (so unverified-sender 403s appear in logs).
- Are non-fatal — caller continues on failure.

`/api/admin/email-check` returns:
```json
{
  "ok": bool,
  "api_key_set": bool,
  "from_email": "...",
  "is_default": bool,          // true if still using noreply@gridsignal.app
  "sendgrid_pkg": bool,
  "issues": ["..."]
}
```

---

## 8. Auth Route Summary

```
POST /api/auth/request-code    — send OTP; returns {ok, email_sent}
POST /api/auth/login           — verify OTP; sets gs_session cookie
POST /api/auth/logout          — clear cookie
GET  /api/auth/me              — current user profile {user_id, email, display_name, role}
GET  /api/auth/password-status — {has_password: bool} for current user
POST /api/auth/change-password — update own password
```

All `/api/auth/*` routes bypass the middleware auth check (they are public or self-authenticating).

---

## 9. Frontend Components

### 9.1 `LoginPage.tsx`

Two-step form:

**Step 1 — Email entry:**
- Input: email address
- Submits `POST /api/auth/request-code`
- On `resp.ok`: advances to step 2; sets `emailWarning = (body.email_sent === false)`

**Step 2 — Code entry:**
- If `emailWarning`: shows amber ⚠ banner ("Email delivery may not be configured")
- Otherwise: shows "A 6-digit code was sent to [email]"
- 6-digit numeric input, auto-cleans non-digits
- "Resend code" button with 60s countdown
- "← Change email" returns to step 1
- Submits `POST /api/auth/login`
- On success: calls `onAuthenticated(display_name, role)`
- `adminMode` prop: if set, rejects non-admin role and redirects

### 9.2 `AdminPage.tsx`

Full user management table (admin-only):
- Lists all users: name, email, role (inline `<select>`), status toggle (ACTIVE/INACTIVE button)
- **Add account** modal: email, display name, role select → `POST /api/admin/users`
- **Reset password** modal: new + confirm fields → `PATCH /api/admin/users/{id}` with `{ password }`
- **Delete** with confirm step → `DELETE /api/admin/users/{id}`
- Role change: `PATCH /api/admin/users/{id}` with `{ role }` on `<select>` change
- Status toggle: `PATCH /api/admin/users/{id}` with `{ is_active: !current }`

### 9.3 `ChangePasswordModal.tsx`

In-session password management:
- Calls `GET /api/auth/password-status` on mount to determine if account has a password
- No current-password field when `has_password = false` (first-time set)
- Current-password field shown when `has_password = true`
- New password + confirm → `POST /api/auth/change-password`
- Minimum 8 characters enforced client-side and server-side

---

## 10. Security Notes (current gaps for multi-tenant design to address)

| Gap | Detail |
|---|---|
| OTP in memory | Codes lost on restart; no persistence or Redis backing |
| No `secure` flag on cookie | `set_cookie(secure=True)` not set — cookie sent over HTTP in dev |
| Deactivated users stay logged in | JWT has no revocation; 24h window after deactivation |
| No rate limiting on `/login` | Beyond the 5-attempt OTP lockout, no IP or global rate limiting |
| No CSRF protection | `samesite=lax` provides partial protection; no token |
| Phone not verified | Stored as a string, never validated |
| Single global admin key | `ADMIN_SECRET` grants full admin across all data |
| No audit log | Account creation/deletion/role changes are not recorded |
| Password min-length only | No complexity, breach-check, or history enforcement |

---

## 11. Environment Variables / Secrets

| Name | Required | Purpose |
|---|---|---|
| `SESSION_SECRET` | Yes | JWT signing key (fallback when `JWT_SECRET` absent) |
| `JWT_SECRET` | No | JWT signing key (takes precedence over `SESSION_SECRET`) |
| `ADMIN_SECRET` | Recommended | Enables X-Admin-Key header path and bootstrap endpoint |
| `DATABASE_URL` | Auto-injected by Replit | asyncpg PostgreSQL connection string |
| `GRIDSIGNAL_DB` | Dev only | Override SQLite path |
| `SENDGRID_API_KEY` | For email | SendGrid API key |
| `SENDGRID_FROM_EMAIL` | For email | Verified sender address |
| `INITIAL_ADMIN_EMAIL` | For first deploy | Seeds admin account when DB is empty |
| `INITIAL_ADMIN_NAME` | For first deploy | Display name for seeded admin |

---

## 12. Key Design Decisions to Carry Forward

1. **No self-registration.** All accounts are admin-provisioned. This must be preserved in multi-tenant (with per-tenant admin creating per-tenant users).
2. **OTP is always available.** Even users with passwords can always sign in via OTP. Password is supplemental, never the only path.
3. **Email is the unique identifier.** Across the entire system today. In multi-tenant, uniqueness scope becomes (tenant_id, email).
4. **Roles are flat strings.** No hierarchical RBAC. Multi-tenant needs a second axis: tenant scope vs. platform scope.
5. **Admin key is a global bypass.** In multi-tenant, platform-admin and tenant-admin must be separate principals.
6. **Bootstrap endpoint is break-glass.** Multi-tenant needs the same concept at both platform and tenant levels.
