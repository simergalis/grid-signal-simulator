"""
api/db.py — Async SQLAlchemy session dependency for API routes.

When DATABASE_URL is set (Replit's managed PostgreSQL, injected at runtime),
the engine uses asyncpg so user data persists across redeploys.  In local
development where DATABASE_URL is absent, the engine falls back to the
SQLite file at GRIDSIGNAL_DB (or the default path two directories up).

The engine is created at import time and shared across all requests.
Test environments that patch DATABASE_URL or GRIDSIGNAL_DB get their own
isolated engine via the normal env-var override path.

ROOT CAUSE OF THE WIPE BUG
---------------------------
The previous implementation always wrote to gridsignal.db inside the app
directory.  That file is part of the container image snapshot and is
replaced on every Replit publish, erasing all operator accounts.

FIX
---
Production (DATABASE_URL set) → asyncpg → PostgreSQL that survives redeploys.
Development (DATABASE_URL absent) → aiosqlite → local SQLite file as before.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Resolve the database URL
# ---------------------------------------------------------------------------

_raw_db_url = os.environ.get("DATABASE_URL", "")

if _raw_db_url:
    # Replit injects DATABASE_URL as a libpq-style URL (postgresql://...).
    # 1. Swap the driver prefix to asyncpg.
    # 2. Strip sslmode=disable — asyncpg uses a different SSL knob and the
    #    internal Replit Postgres doesn't need TLS at all.
    _DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    _DATABASE_URL = re.sub(r"[?&]sslmode=[^&]*", "", _DATABASE_URL).rstrip("?&")
    _using_postgres = True
    _connect_args: dict = {}
else:
    _DB_PATH = os.environ.get(
        "GRIDSIGNAL_DB",
        str(Path(__file__).resolve().parents[1] / "gridsignal.db"),
    )
    _DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"
    _using_postgres = False
    _connect_args = {"check_same_thread": False}

_engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    # pool_pre_ping: test each connection before handing it to a request.
    # Neon (and most managed PostgreSQL) silently closes idle connections after
    # ~5 minutes.  Without this, the pool hands out a closed connection and the
    # request fails with asyncpg InterfaceError: connection is closed.
    # With it, SQLAlchemy issues a lightweight SELECT 1 first; on failure it
    # transparently reconnects, so the request never sees the error.
    pool_pre_ping=True,
    # pool_recycle: retire connections after 4 minutes regardless of use.
    # Belt-and-suspenders with pool_pre_ping — keeps the pool healthy even
    # during traffic lulls without waiting for Neon to close the connection.
    pool_recycle=240,
)

_SessionLocal = async_sessionmaker(
    bind=_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a per-request async DB session."""
    async with _SessionLocal() as session:
        yield session


async def create_auth_tables() -> None:
    """Ensure auth tables exist and seed a default admin if the DB is empty.

    Called from the app lifespan so tables are always present before any
    request arrives.

    Schema migration guard (SQLite only)
    -------------------------------------
    SQLite cannot ALTER a CHECK constraint.  If auth_user was created before
    'admin' was added to ck_auth_user_role we drop and recreate the table.
    The guard reads sqlite_master to confirm the constraint before dropping, so
    existing data is never discarded on a schema-compatible deployment.
    PostgreSQL supports ALTER TABLE … DROP CONSTRAINT / ADD CONSTRAINT and the
    schema is always correct from first deploy, so the guard is skipped there.

    Default admin seeding
    ---------------------
    When INITIAL_ADMIN_EMAIL is set and no users exist yet, a single admin
    account is created automatically.  This makes the DB self-initialising
    after a fresh clone or any workspace restore that resets the file.
    The DB file must NOT be tracked in git — see gridsignal_sim/.gitignore.
    """
    import logging as _logging
    from sqlalchemy import text
    from runtime.persistence import Base, AuthUser

    _log = _logging.getLogger(__name__)

    async with _engine.begin() as conn:
        if not _using_postgres:
            # SQLite-specific migration guard: detect tables created before
            # 'admin' was added to ck_auth_user_role and recreate them.
            result = await conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='table' AND name='auth_user'"
                )
            )
            row = result.fetchone()
            if row is not None and "'admin'" not in (row[0] or ""):
                # Old schema — safe to drop because the guard only fires when
                # the constraint lacks 'admin', which predates any real users.
                await conn.execute(text("DROP TABLE auth_user"))
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    _log.info(
        "Auth tables ready (backend=%s)",
        "postgresql" if _using_postgres else "sqlite",
    )

    # Seed default admin from environment if no users exist yet.
    # Covers fresh PostgreSQL databases (first deploy) and SQLite restores.
    admin_email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip().lower()
    admin_name  = os.environ.get("INITIAL_ADMIN_NAME", "Admin").strip()
    if not admin_email:
        return

    async with _SessionLocal() as session:
        count_result = await session.execute(text("SELECT COUNT(*) FROM auth_user"))
        user_count = count_result.scalar_one()
        if user_count == 0:
            new_admin = AuthUser(
                email=admin_email,
                phone="",
                display_name=admin_name,
                role="admin",
                password_hash="",
                is_active=True,
            )
            session.add(new_admin)
            await session.commit()
            _log.info(
                "Seeded default admin account: %s (name=%r) from INITIAL_ADMIN_EMAIL",
                admin_email, admin_name,
            )
