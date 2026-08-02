---
name: SQLite to PostgreSQL migration for auth_user
description: Why auth users were wiped on publish and how the fix works; traps with asyncpg URL format.
---

# SQLite → PostgreSQL for auth_user persistence

## The bug
`api/db.py` always wrote to `gridsignal.db` inside the app directory.
That file is part of the container image snapshot and is **replaced on every Replit publish**, erasing all operator accounts.

## The fix
`api/db.py` now checks `DATABASE_URL` first:
- **Set (production)** → `postgresql+asyncpg://` → Replit's managed Neon PostgreSQL — survives redeploys
- **Absent (local dev)** → `sqlite+aiosqlite:///gridsignal.db` — unchanged for local dev

**Why:**
Replit injects `DATABASE_URL` as a libpq-style URL (`postgresql://...`) into both dev and prod containers automatically. The dev DB exists immediately; the production Neon DB is created on first Publish.

## asyncpg URL conversion trap
Replit's `DATABASE_URL` comes in as `postgresql://...?sslmode=disable`.
asyncpg needs two changes:
1. Replace `postgresql://` → `postgresql+asyncpg://`
2. Strip `?sslmode=disable` — asyncpg uses different SSL params; the internal Replit DB doesn't need TLS

The regex `re.sub(r"[?&]sslmode=[^&]*", "", url).rstrip("?&")` handles it.

## SQLite migration guard
`create_auth_tables()` has a guard that reads `sqlite_master` to detect the pre-'admin' schema and drop/recreate.
This must be **skipped on PostgreSQL** (no `sqlite_master` table). Guarded by `if not _using_postgres:`.

## connect_args
`{"check_same_thread": False}` is SQLite-only. Must be `{}` for PostgreSQL or asyncpg raises an error.

## asyncpg installation
Added to `scripts/start_prod.sh` alongside websockets:
```bash
python3 -c "import asyncpg" 2>/dev/null || \
  pip3 install --target="$PYTHONLIBS_SITE" asyncpg --quiet 2>&1 | tail -1 || true
```

## Fresh deploy seeding
`INITIAL_ADMIN_EMAIL` + `INITIAL_ADMIN_NAME` secrets → `create_auth_tables()` seeds a default admin when the DB is empty.
This covers first publish to a fresh Neon DB. Set both secrets before publishing.

## One-time password loss
After first publish with the new code, production Neon starts empty. INITIAL_ADMIN_EMAIL seeds Lloyd with `password_hash=""`.
If Lloyd had a password set on the old SQLite DB, he'll need to set a new one via the change-password flow after publishing.
He can still sign in via OTP — passwordless flow is always available.
