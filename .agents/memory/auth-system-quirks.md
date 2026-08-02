---
name: Auth system quirks
description: Non-obvious bugs and fixes in the GridSignal JWT/bcrypt/SQLite auth stack
---

## bcrypt 4.x / passlib incompatibility

**Rule:** Do NOT use `passlib.context.CryptContext` with bcrypt 4.x. The library removed `__about__` and changed its internal API; passlib's bcrypt backend throws `AttributeError` and `ValueError: password cannot be longer than 72 bytes` even for short passwords.

**Fix applied:** `api/auth_utils.py` uses `import bcrypt as _bcrypt` directly:
- `hash_password`: `_bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")`
- `verify_password`: `_bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))` wrapped in try/except

**Why:** The bcrypt 4.x hash format (`$2b$...`) is identical; existing stored hashes still verify correctly.

---

## Auth middleware must not block /api/admin/*

**Rule:** The `_auth_middleware` in `api/app.py` checks for a session cookie on all `/api/*` paths. Admin routes use their own `X-Admin-Key` header auth (`_require_admin` dependency). If `/api/admin` is not in the pass-through set, curl with `X-Admin-Key` gets 401 before the route handler runs.

**Fix applied:** Middleware condition includes `or path.startswith("/api/admin")`.

---

## ck_auth_user_role CHECK constraint must include 'admin'

**Rule:** `AuthUser.__table_args__` in `runtime/persistence.py` has `ck_auth_user_role`. It must list all four roles: `'viewer', 'operator', 'approver', 'admin'`. Missing 'admin' causes `IntegrityError` on insert.

**Migration guard:** `create_auth_tables()` in `api/db.py` reads `sqlite_master` to check if `'admin'` appears in the stored `CREATE TABLE` SQL. If not, it drops the (empty) table before `create_all` so the correct schema is created. This is safe only while the table is empty — do not rely on this guard after real users exist.
