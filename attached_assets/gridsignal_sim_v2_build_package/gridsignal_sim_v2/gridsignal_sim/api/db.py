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

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from sqlalchemy import and_, or_, select
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

_pg_kwargs: dict = (
    {
        # pool_pre_ping: test each connection before handing it to a request.
        # Neon (and most managed PostgreSQL) silently closes idle connections after
        # ~5 minutes.  Without this, the pool hands out a closed connection and the
        # request fails with asyncpg InterfaceError: connection is closed.
        # With it, SQLAlchemy issues a lightweight SELECT 1 first; on failure it
        # transparently reconnects, so the request never sees the error.
        "pool_pre_ping": True,
        # pool_recycle: retire connections after 4 minutes regardless of use.
        # Belt-and-suspenders with pool_pre_ping — keeps the pool healthy even
        # during traffic lulls without waiting for Neon to close the connection.
        "pool_recycle": 240,
    }
    if _using_postgres
    else {}
    # aiosqlite does not benefit from pool_pre_ping and pool_recycle spawns a
    # background task that conflicts with pytest's event-loop teardown in tests.
)

# Under pytest, pool_recycle spawns background SQLAlchemy "heartbeat" tasks that
# call loop.create_task() during garbage collection — after the per-test event
# loop has already closed.  This raises "RuntimeError: Event loop is closed" in
# asyncpg's _cancel_current_command and marks a passing test body as FAILED.
# NullPool closes each connection immediately on release, so there is nothing
# in-flight when the loop closes.  Production (uvicorn) never sets PYTEST_CURRENT_TEST
# so the production path keeps the full connection pool.
import sys as _sys
_is_pytest = "pytest" in _sys.modules

if _is_pytest:
    from sqlalchemy.pool import NullPool as _NullPool
    _engine = create_async_engine(
        _DATABASE_URL,
        echo=False,
        poolclass=_NullPool,
    )
else:
    _engine = create_async_engine(
        _DATABASE_URL,
        echo=False,
        connect_args=_connect_args,
        **_pg_kwargs,
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


async def fetch_reference_forecast_rows(
    db: AsyncSession,
    dataset_id: str,
    start_day_of_year: int,
    start_hour_of_day: int,
    end_day_of_year: int,
    end_hour_of_day: int,
) -> list[dict[str, int]]:
    """Fetch an inclusive day/hour range from a reference forecast dataset.

    The range is ordered by the dataset's day and hour dimensions.  This is
    deliberately a raw row fetch: it performs no aggregation, interpolation,
    MW conversion, seasonal adjustment, or analogous-day matching.
    """
    start_key = (start_day_of_year, start_hour_of_day)
    end_key = (end_day_of_year, end_hour_of_day)
    if start_key > end_key:
        raise ValueError("Reference forecast range must start before it ends")

    from runtime.persistence import ReferenceForecastResolved

    result = await db.execute(
        select(ReferenceForecastResolved)
        .where(
            ReferenceForecastResolved.dataset_id == dataset_id,
            or_(
                ReferenceForecastResolved.day_of_year > start_day_of_year,
                and_(
                    ReferenceForecastResolved.day_of_year == start_day_of_year,
                    ReferenceForecastResolved.hour_of_day >= start_hour_of_day,
                ),
            ),
            or_(
                ReferenceForecastResolved.day_of_year < end_day_of_year,
                and_(
                    ReferenceForecastResolved.day_of_year == end_day_of_year,
                    ReferenceForecastResolved.hour_of_day <= end_hour_of_day,
                ),
            ),
        )
        .order_by(
            ReferenceForecastResolved.day_of_year,
            ReferenceForecastResolved.hour_of_day,
        )
    )
    return [
        {
            "day_of_year": row.day_of_year,
            "hour_of_day": row.hour_of_day,
            "kubernetes_node_count": row.kubernetes_node_count,
            "slurm_node_count": row.slurm_node_count,
            "ray_rack_count": row.ray_rack_count,
        }
        for row in result.scalars()
    ]


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
    global _trace_tables_ready
    _trace_tables_ready = True

    # ── Log-and-Trace migration: add tick_json column if absent ──────────────
    # run_timeseries rows written before this column was introduced store '{}'
    # (the column DEFAULT).  Rows written after this migration store the full
    # TickResult JSON; the export endpoint expands them into CSV columns.
    # Both PostgreSQL (≥9.6) and SQLite (≥3.37) support IF NOT EXISTS here.
    async with _engine.begin() as _m_conn:
        try:
            await _m_conn.execute(
                text(
                    "ALTER TABLE run_timeseries "
                    "ADD COLUMN IF NOT EXISTS tick_json TEXT NOT NULL DEFAULT '{}'"
                )
            )
        except Exception:  # noqa: BLE001
            # Column already exists — safe to ignore.
            pass

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


_trace_tables_ready = False


async def _ensure_trace_tables() -> None:
    """Create the trace report tables for direct route tests without lifespan.

    Production and normal TestClient requests run create_auth_tables() first.
    The small guard also keeps the route handlers usable in unit tests that
    invoke the endpoint functions directly.
    """
    global _trace_tables_ready
    if _trace_tables_ready:
        return
    from runtime.persistence import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    _trace_tables_ready = True


async def persist_trace_import_report(report: dict[str, Any]) -> None:
    from runtime.persistence import TraceImportReport

    await _ensure_trace_tables()
    window = report.get("window") or {}
    async with _SessionLocal() as session:
        async with session.begin():
            row = await session.get(TraceImportReport, report["import_id"])
            if row is None:
                row = TraceImportReport(import_id=report["import_id"])
                session.add(row)
            row.site_id = report.get("site_id", "")
            row.measurement_source = report.get("measurement_source", "")
            row.window_start = window.get("start")
            row.window_end = window.get("end")
            row.report_json = json.dumps(report, separators=(",", ":"), allow_nan=False)
            row.created_at = datetime.now(timezone.utc)


async def load_trace_import_report(import_id: str) -> dict[str, Any] | None:
    import json
    from runtime.persistence import TraceImportReport

    await _ensure_trace_tables()
    async with _SessionLocal() as session:
        row = await session.get(TraceImportReport, import_id)
    return json.loads(row.report_json) if row is not None else None


async def persist_trace_comparison_report(report: dict[str, Any]) -> None:
    from runtime.persistence import TraceComparisonReport

    await _ensure_trace_tables()
    window = report.get("window") or {}
    async with _SessionLocal() as session:
        async with session.begin():
            row = await session.get(TraceComparisonReport, report["comparison_id"])
            if row is None:
                row = TraceComparisonReport(comparison_id=report["comparison_id"])
                session.add(row)
            row.import_id = report.get("import_id", "")
            row.site_id = report.get("site_id", "")
            row.window_start = window.get("start")
            row.window_end = window.get("end")
            row.report_json = json.dumps(report, separators=(",", ":"), allow_nan=False)
            row.created_at = datetime.now(timezone.utc)


async def load_trace_comparison_report(
    comparison_id: str,
) -> dict[str, Any] | None:
    import json
    from runtime.persistence import TraceComparisonReport

    await _ensure_trace_tables()
    async with _SessionLocal() as session:
        row = await session.get(TraceComparisonReport, comparison_id)
    return json.loads(row.report_json) if row is not None else None


async def persist_capacity_outlook_report(report: dict[str, Any]) -> None:
    from runtime.persistence import CapacityOutlookReport
    await _ensure_trace_tables()
    async with _SessionLocal() as session:
        async with session.begin():
            row = await session.get(CapacityOutlookReport, report["outlook_id"])
            if row is None:
                row = CapacityOutlookReport(outlook_id=report["outlook_id"])
                session.add(row)
            row.import_id = report.get("import_id", "")
            row.site_id = report.get("site_id")
            row.report_json = json.dumps(report, separators=(",", ":"), allow_nan=False)
            row.created_at = datetime.now(timezone.utc)


async def load_capacity_outlook_report(outlook_id: str) -> dict[str, Any] | None:
    from runtime.persistence import CapacityOutlookReport
    await _ensure_trace_tables()
    async with _SessionLocal() as session:
        row = await session.get(CapacityOutlookReport, outlook_id)
    return json.loads(row.report_json) if row is not None else None


async def list_trace_import_reports() -> list[dict[str, Any]]:
    from runtime.persistence import TraceImportReport
    from sqlalchemy import select
    await _ensure_trace_tables()
    async with _SessionLocal() as session:
        result = await session.execute(select(TraceImportReport).order_by(TraceImportReport.created_at.desc()))
        return [json.loads(row.report_json) for row in result.scalars()]
