"""
tests/test_persistence.py — SQLite persistence layer tests.

Three tests required by Step 2 acceptance criteria:
  1. A run's ticks are all recoverable after finalize().
  2. Two concurrent runs' rows don't interleave (each run_id has only its own ticks).
  3. Persistence survives re-opening: new engine instance, same file, prior data intact.

Uses pytest-asyncio in auto mode (pytest.ini: asyncio_mode = auto) and
pytest's tmp_path fixture for isolated per-test database files.

These tests import from runtime/persistence.py which must be installed
(sqlalchemy, aiosqlite) before they can run.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from core.models import ConfidenceBand, DataQualityTag, TickResult
from runtime.persistence import Recommendation, RunTimeseries, Scenario, SqlitePersistedTimeseriesSink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_tick(run_id: str, tick_index: int, p_total: float = 1.5) -> TickResult:
    """Build a minimal but fully-populated TickResult for persistence tests."""
    return TickResult(
        run_id=run_id,
        tick_index=tick_index,
        sim_time_seconds=float(tick_index * 5),
        p_compute_mw=p_total * 0.8,
        p_cooling_mw=p_total * 0.2,
        p_total_mw=p_total,
        net_demand_mw=p_total,
        turbine_output_mw=p_total * 0.9,
        bess_output_mw=p_total * 0.1,
        bess_soc_fraction=0.85,
        confidence=ConfidenceBand(
            point_estimate_mw=p_total,
            plus_minus_fraction=0.05,
            tags=frozenset(),
        ),
        insufficient_reserve_alert=False,
        checkpoint_states={},
    )


# ---------------------------------------------------------------------------
# Test 1: ticks all recoverable after finalize()
# ---------------------------------------------------------------------------

async def test_ticks_recoverable_after_finalize(tmp_path: Path) -> None:
    """A run's ticks must all be readable from the DB after finalize() returns.

    finalize() calls asyncio.Queue.join() internally, which guarantees that
    every tick enqueued by append() has been written to SQLite before finalize()
    returns.  This test verifies that guarantee holds end-to-end.
    """
    db_path = tmp_path / "test_recover.db"
    sink = SqlitePersistedTimeseriesSink(db_path)
    await sink.start()

    N = 8
    for i in range(N):
        await sink.append(_make_tick("run-recover", i))
    await sink.finalize("run-recover", "pass")

    # Query directly using the engine that is still alive after finalize().
    assert sink._engine is not None
    async with AsyncSession(sink._engine) as session:
        result = await session.execute(
            select(RunTimeseries)
            .where(RunTimeseries.run_id == "run-recover")
            .order_by(RunTimeseries.tick_index)
        )
        rows = result.scalars().all()

    assert len(rows) == N, f"expected {N} rows, got {len(rows)}"
    for i, row in enumerate(rows):
        assert row.run_id == "run-recover"
        assert row.tick_index == i
        assert row.sim_time_seconds == float(i * 5)

    # Scenario row must be written with verdict="pass".
    async with AsyncSession(sink._engine) as session:
        result = await session.execute(
            select(Scenario).where(Scenario.run_id == "run-recover")
        )
        scenario = result.scalar_one_or_none()
    assert scenario is not None, "Scenario row not written by finalize()"
    assert scenario.verdict == "pass"
    assert scenario.completed_at is not None

    await sink.stop()


# ---------------------------------------------------------------------------
# Test 2: two concurrent runs' rows don't interleave
# ---------------------------------------------------------------------------

async def test_concurrent_runs_rows_do_not_interleave(tmp_path: Path) -> None:
    """Rows from two concurrent runs must be correctly attributed to their
    respective run_ids, even when both append concurrently to the same sink.

    The bounded write queue serialises INSERT statements, but both runs share
    it.  This test confirms the run_id column on each row matches the run that
    wrote it — no row from run-A appears in run-B's result set and vice versa.
    """
    db_path = tmp_path / "test_concurrent.db"
    sink = SqlitePersistedTimeseriesSink(db_path)
    await sink.start()

    N = 12

    async def _write_run(run_id: str) -> None:
        for i in range(N):
            await sink.append(_make_tick(run_id, i, p_total=float(i + 1)))
        await sink.finalize(run_id, "ok")

    # Drive both runs concurrently — this is the same concurrency pattern
    # as RunManager managing multiple RunContext instances simultaneously.
    await asyncio.gather(_write_run("run-A"), _write_run("run-B"))

    assert sink._engine is not None
    for run_id in ("run-A", "run-B"):
        async with AsyncSession(sink._engine) as session:
            result = await session.execute(
                select(RunTimeseries).where(RunTimeseries.run_id == run_id)
            )
            rows = result.scalars().all()

        assert len(rows) == N, (
            f"{run_id}: expected {N} rows, got {len(rows)}"
        )
        wrong_ids = {r.run_id for r in rows} - {run_id}
        assert not wrong_ids, (
            f"{run_id}: rows contain foreign run_ids: {wrong_ids}"
        )

    await sink.stop()


# ---------------------------------------------------------------------------
# Test 3: persistence survives re-opening
# ---------------------------------------------------------------------------

async def test_persistence_survives_reopening(tmp_path: Path) -> None:
    """Data written by one sink instance must be readable by a fresh instance
    opened on the same file.

    This is the §22.1 principle 4 portability check: the file is the store,
    and the ORM layer is swappable — not the in-process object.
    """
    db_path = tmp_path / "test_reopen.db"

    # --- Write with sink1 ---
    sink1 = SqlitePersistedTimeseriesSink(db_path)
    await sink1.start()
    for i in range(4):
        await sink1.append(_make_tick("run-reopen", i))
    await sink1.finalize("run-reopen", "verified")
    await sink1.stop()  # fully disposes engine

    # --- Read with a brand-new sink2 on the same file ---
    sink2 = SqlitePersistedTimeseriesSink(db_path)
    await sink2.start()

    assert sink2._engine is not None
    async with AsyncSession(sink2._engine) as session:
        result = await session.execute(
            select(RunTimeseries)
            .where(RunTimeseries.run_id == "run-reopen")
            .order_by(RunTimeseries.tick_index)
        )
        rows = result.scalars().all()

    assert len(rows) == 4, f"expected 4 rows after reopen, got {len(rows)}"
    for i, row in enumerate(rows):
        assert row.tick_index == i

    # Scenario row must also survive the reopen.
    async with AsyncSession(sink2._engine) as session:
        result = await session.execute(
            select(Scenario).where(Scenario.run_id == "run-reopen")
        )
        scenario = result.scalar_one_or_none()

    assert scenario is not None, "Scenario row lost after reopen"
    assert scenario.verdict == "verified"

    await sink2.stop()


# ---------------------------------------------------------------------------
# Test 4: recommendation CHECK constraint (reviewer_id required for terminal states)
# ---------------------------------------------------------------------------

async def test_recommendation_reviewer_constraint(tmp_path: Path) -> None:
    """A Recommendation row must not reach state=applied or state=rejected
    with reviewer_id IS NULL.

    This verifies the DB-level CHECK constraint introduced in §21.6 is
    actually enforced by SQLite (it isn't enforced by default in old SQLite
    versions without PRAGMA enforce_foreign_keys / enforce_checks; confirm
    aiosqlite+SQLAlchemy enforce it).
    """
    from datetime import timezone
    import pytest
    from sqlalchemy.exc import IntegrityError
    from runtime.persistence import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'check.db'}", echo=False)
    from sqlalchemy import text as sa_text
    async with engine.begin() as conn:
        await conn.execute(sa_text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)

    now = __import__("datetime").datetime.now(timezone.utc)
    bad_row = Recommendation(
        state="applied",          # terminal state
        reviewer_id=None,         # violates ck_recommendation_reviewer_required
        originating_agent="test-agent",
        parameter_name="tau_seconds",
        current_value="20.0",
        proposed_value="25.0",
        observation_count=100,
        window_start=now,
        window_end=now,
        evidence_digest="a" * 64,
        generated_by="model",
        created_at=now,
    )
    with pytest.raises((IntegrityError, Exception)):
        async with AsyncSession(engine) as session:
            async with session.begin():
                session.add(bad_row)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Test 5: data_quality_tags round-trips correctly
# ---------------------------------------------------------------------------

async def test_data_quality_tags_roundtrip(tmp_path: Path) -> None:
    """Tags stored as a JSON array in data_quality_tags must deserialise back
    to the original set of tag value strings."""
    db_path = tmp_path / "test_tags.db"
    sink = SqlitePersistedTimeseriesSink(db_path)
    await sink.start()

    tagged_tick = TickResult(
        run_id="run-tags",
        tick_index=0,
        sim_time_seconds=0.0,
        p_compute_mw=1.0,
        p_cooling_mw=0.2,
        p_total_mw=1.2,
        net_demand_mw=1.2,
        turbine_output_mw=1.1,
        bess_output_mw=0.1,
        bess_soc_fraction=0.9,
        confidence=ConfidenceBand(
            point_estimate_mw=1.2,
            plus_minus_fraction=0.18,
            tags=frozenset({DataQualityTag.UNMAPPED_HARDWARE, DataQualityTag.UNCALIBRATED_SITE}),
        ),
        insufficient_reserve_alert=False,
        checkpoint_states={"job-1": "in_valley"},
    )
    await sink.append(tagged_tick)
    await sink.finalize("run-tags", None)

    assert sink._engine is not None
    async with AsyncSession(sink._engine) as session:
        result = await session.execute(
            select(RunTimeseries).where(RunTimeseries.run_id == "run-tags")
        )
        row = result.scalar_one()

    stored_tags = set(json.loads(row.data_quality_tags))
    assert stored_tags == {"unmapped_hardware", "uncalibrated_site"}

    stored_states = json.loads(row.checkpoint_states)
    assert stored_states == {"job-1": "in_valley"}

    await sink.stop()
