---
name: SendGrid auth system
description: JWT cookie auth + admin panel; OTP email login replaced password auth
---

## Auth model
- Roles: viewer / operator / approver / admin
- Session: httpOnly JWT cookie (`gs_session`), 24h TTL
- Login: **email + 6-digit OTP code** (SendGrid) — no password stored or required
- Admin API: `X-Admin-Key` header (value = ADMIN_SECRET env var) OR session cookie with role=admin

## OTP flow
- `POST /api/auth/request-code` — generates code, stores in `_otp_store` (in-memory, 10 min TTL), emails via SendGrid
- `POST /api/auth/login` — verifies code, single-use (cleared on match), sets cookie
- Codes: 6-digit numeric, 5 max attempts before invalidation, 60s resend cooldown
- `SENDGRID_FROM_EMAIL` env var must be a **verified SendGrid sender** — defaults to `noreply@gridsignal.app` which is NOT verified; 403 from SendGrid means sender unverified

## Key files
- `api/routes/auth_routes.py` — OTP store + request-code + login + me endpoints
- `api/routes/admin_routes.py` — user CRUD; `CreateUserRequest` no longer needs phone or password
- `api/email_service.py` — `send_otp_email()` + `send_welcome_email()`
- `api/app.py` — middleware pass-through: all `/api/auth/` paths are unprotected

## Middleware pass-through rule
All `/api/auth/*` and `/api/admin/*` paths bypass the session-check middleware.
Auth routes handle their own auth; admin routes check X-Admin-Key OR admin session cookie.

## Known quirks
- bcrypt 4.x / passlib incompatibility — use `import bcrypt as _bcrypt` directly in `api/auth_utils.py`, never `passlib.context.CryptContext`
- `ck_auth_user_role` CHECK constraint must include `'admin'` — migration guard in `api/db.py` drops+recreates table if `'admin'` missing
- `password_hash` column still exists in AuthUser but is set to `""` for OTP-only accounts
- OTP store is in-memory: codes lost on server restart (acceptable for 10-min TTL)

**Why:** Replaced password+phone login with OTP to simplify operator onboarding — no password distribution needed, users just need their email.
