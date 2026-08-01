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
    """Ensure the AuthUser table exists.

    Called from the app lifespan so the table is always present before any
    request arrives.  Uses create_all(checkfirst=True) so existing tables
    are never modified.
    """
    from runtime.persistence import Base
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
