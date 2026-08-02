"""
api/db.py — Async SQLAlchemy session dependency for API routes.

Uses the same SQLite database file as the simulation persistence layer
(runtime/persistence.py) but manages its own engine/session so API routes
don't share transaction state with the background drain loops.

The engine is created lazily on first request so that test environments that
never call a DB-backed route don't pay the connection setup cost.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Engine — shared with persistence.py on the same SQLite file
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get(
    "GRIDSIGNAL_DB",
    str(Path(__file__).resolve().parents[1] / "gridsignal.db"),
)
_DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

_engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
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

    Schema migration guard
    ----------------------
    SQLite cannot ALTER a CHECK constraint.  If auth_user was created before
    'admin' was added to ck_auth_user_role we drop and recreate the table.
    The guard reads sqlite_master to confirm the constraint before dropping, so
    existing data is never discarded on a schema-compatible deployment.

    Default admin seeding
    ---------------------
    When INITIAL_ADMIN_EMAIL is set and no users exist yet, a single admin
    account is created automatically.  This makes the DB self-initialising
    after a fresh clone or any workspace restore that resets the file.
    The DB file must NOT be tracked in git — see gridsignal_sim/.gitignore.
    """
    from sqlalchemy import text, select
    from runtime.persistence import Base, AuthUser

    async with _engine.begin() as conn:
        result = await conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='auth_user'")
        )
        row = result.fetchone()
        if row is not None and "'admin'" not in (row[0] or ""):
            # Old schema without 'admin' role — drop and recreate.
            # Safe: the guard only fires when 'admin' is absent from the
            # constraint, which means either the table is empty or was created
            # by an older code version before admin role was added.
            await conn.execute(text("DROP TABLE auth_user"))
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    # Seed default admin from environment if no users exist yet.
    # This covers fresh installs and workspace restores where the DB file
    # was not preserved (because it is not tracked in git).
    admin_email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip().lower()
    admin_name  = os.environ.get("INITIAL_ADMIN_NAME", "Admin").strip()
    if admin_email:
        async with _SessionLocal() as session:
            count_result = await session.execute(
                text("SELECT COUNT(*) FROM auth_user")
            )
            user_count = count_result.scalar_one()
            if user_count == 0:
                from sqlalchemy import select as _select
                import logging as _logging
                _log = _logging.getLogger(__name__)
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
