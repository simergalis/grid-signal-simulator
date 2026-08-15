"""test_log_and_trace_export.py — End-to-end tests for Log and Trace CSV export.

Task #445: Confirm Log and Trace downloads a complete CSV with all power and
scheduler variables after a real run.

TC-LT-1  Full-run CSV contains the correct row count and all required columns.
TC-LT-2  Export returns 'error' status (not a crash) when run_id has no rows.
TC-LT-3  tick_json is valid JSON on every persisted row with ≥ 80 keys.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from core.models import ConfidenceBand, DataQualityTag, TickResult
from runtime.persistence import RunTimeseries, SqlitePersistedTimeseriesSink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Columns that every exported CSV must contain
# ---------------------------------------------------------------------------

# Stored directly as typed columns in run_timeseries
_DB_REQUIRED: set[str] = {
    "run_id",
    "tick_index",
    "sim_time_seconds",
    "p_demand_mw",
    "turbine_output_mw",
    "bess_output_mw",
    "bess_soc_fraction",
}

# Sourced from tick_json expansion; cover all simulator subsystems
_JSON_REQUIRED: set[str] = {
    # Power supply
    "p_renewable_mw",
    "frequency_hz",
    "p_generation_mw",
    "gt_setpoint_mw",
    "bess_setpoint_mw",
    # Scheduler / PMS
    "forecast_mw",
    "pms_fast_shed_active",
    "edl_dispatch_cost_usd",
    # GPU / Colo
    "gpu_load_fraction",
    "step_phase",
    # Internal physics
    "d4_balance_defect_mw",
    "bess_soc_corrupted_fraction",
    "protection_provisional",
    "island_collapsed",
}

REQUIRED_COLUMNS: set[str] = _DB_REQUIRED | _JSON_REQUIRED

N_TICKS = 10   # ticks written per test run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rich_tick(run_id: str, tick_index: int) -> TickResult:
    """Build a TickResult with non-zero values in every subsystem column so
    spot-check assertions can confirm data actually flows through."""
    return TickResult(
        run_id=run_id,
        tick_index=tick_index,
        sim_time_seconds=float(tick_index * 5),
        p_compute_demand_mw=18.0,
        p_cooling_demand_mw=3.0,
        p_demand_mw=21.0,
        net_demand_mw=21.0,
        turbine_output_mw=12.0,
        bess_output_mw=4.0,
        bess_soc_fraction=0.72,
        confidence=ConfidenceBand(
            point_estimate_mw=21.0,
            plus_minus_fraction=0.08,
            tags=frozenset({DataQualityTag.WORKLOAD_SIGNAL_ABSENT}),
        ),
        # Power subsystem
        p_renewable_mw=6.5,
        frequency_hz=59.97,
        p_generation_mw=22.5,
        gt_setpoint_mw=12.0,
        bess_setpoint_mw=4.0,
        # Scheduler / PMS
        forecast_mw=22.1,
        pms_fast_shed_active=False,
        edl_dispatch_cost_usd=0.034,
        # GPU / Colo
        gpu_load_fraction=0.85,
        step_phase=0.42,
        # Internal physics
        d4_balance_defect_mw=0.12,
        bess_soc_corrupted_fraction=0.0,
        protection_provisional=False,
        island_collapsed=False,
        # Misc required fields
        insufficient_reserve_alert=False,
        checkpoint_states={},
    )


async def _write_run(
    sink: SqlitePersistedTimeseriesSink,
    run_id: str,
    n: int = N_TICKS,
) -> None:
    """Write n rich ticks for run_id and finalize the run."""
    for i in range(n):
        await sink.append(_make_rich_tick(run_id, i))
    await sink.finalize(run_id, "pass")


# ---------------------------------------------------------------------------
# TC-LT-1: Full-run CSV has the correct row count and all required columns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_lt_1_csv_has_required_columns(tmp_path: Path) -> None:
    """_build_csv must produce a well-formed CSV with one row per tick and
    every power, scheduler, and GPU-colo column present.

    The test patches api.db._engine so that _build_csv queries the temporary
    SQLite database instead of the production store, then verifies:

    1. Job status transitions to 'done'.
    2. Row count matches the number of ticks written.
    3. All REQUIRED_COLUMNS are present in the header.
    4. spot-check columns are non-empty for every row.
    """
    from api.routes.export import _build_csv, _jobs
    import api.db as _api_db

    run_id = "tc-lt-1"
    sink = SqlitePersistedTimeseriesSink(tmp_path / "lt1.db")
    await sink.start()
    await _write_run(sink, run_id)

    original_engine = _api_db._engine
    _api_db._engine = sink._engine
    try:
        out_path = str(tmp_path / "out_lt1.csv")
        job_id = "lt1-job"
        _jobs[job_id] = {
            "status":   "running",
            "out_path": out_path,
            "detail":   "",
            "run_id":   run_id,
        }

        await _build_csv(job_id, out_path, run_id)

        assert _jobs[job_id]["status"] == "done", (
            f"Expected status=done, got {_jobs[job_id]['status']!r}: "
            f"{_jobs[job_id].get('detail')}"
        )
        assert _jobs[job_id]["row_count"] == N_TICKS, (
            f"Expected {N_TICKS} rows in job registry, "
            f"got {_jobs[job_id]['row_count']}"
        )

        with open(out_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            col_set = set(reader.fieldnames or [])

        assert len(rows) == N_TICKS, (
            f"Expected {N_TICKS} data rows in CSV, got {len(rows)}"
        )

        missing = REQUIRED_COLUMNS - col_set
        assert not missing, (
            f"Missing required columns in CSV header: {sorted(missing)}"
        )

        # Spot-check that key columns carry actual data (not empty strings)
        spot = {
            "run_id", "tick_index", "sim_time_seconds",
            "p_renewable_mw", "frequency_hz", "forecast_mw", "gpu_load_fraction",
        }
        for row in rows:
            for col in spot:
                assert row[col] != "", (
                    f"Column {col!r} is empty in CSV row tick_index={row['tick_index']}"
                )

    finally:
        _api_db._engine = original_engine
        await sink.stop()


# ---------------------------------------------------------------------------
# TC-LT-2: Export returns 'error' for a non-existent run_id (no crash)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_lt_2_missing_run_id_gives_error_not_crash(tmp_path: Path) -> None:
    """_build_csv must update job status to 'error' with a descriptive message
    when the requested run_id has no rows — it must not raise an exception."""
    from api.routes.export import _build_csv, _jobs
    import api.db as _api_db

    sink = SqlitePersistedTimeseriesSink(tmp_path / "lt2.db")
    await sink.start()

    original_engine = _api_db._engine
    _api_db._engine = sink._engine
    try:
        out_path = str(tmp_path / "out_lt2.csv")
        job_id = "lt2-job"
        _jobs[job_id] = {
            "status":   "running",
            "out_path": out_path,
            "detail":   "",
            "run_id":   "no-such-run",
        }

        await _build_csv(job_id, out_path, "no-such-run")

        assert _jobs[job_id]["status"] == "error", (
            f"Expected status=error for non-existent run_id, "
            f"got {_jobs[job_id]['status']!r}"
        )
        assert _jobs[job_id]["detail"], (
            "Error status must carry a non-empty detail message"
        )

    finally:
        _api_db._engine = original_engine
        await sink.stop()


# ---------------------------------------------------------------------------
# TC-LT-3: tick_json is valid JSON on every row with ≥ 80 keys
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tc_lt_3_tick_json_has_full_field_coverage(tmp_path: Path) -> None:
    """Every persisted row's tick_json must deserialise without error and
    contain at least 80 keys, confirming that all simulator subsystems
    (dashboard, GPU-colo, scheduler, power-supply, internal physics) are
    captured in the Log-and-Trace store."""
    run_id = "tc-lt-3"
    sink = SqlitePersistedTimeseriesSink(tmp_path / "lt3.db")
    await sink.start()
    await _write_run(sink, run_id)

    assert sink._engine is not None
    async with AsyncSession(sink._engine) as session:
        result = await session.execute(
            select(RunTimeseries)
            .where(RunTimeseries.run_id == run_id)
            .order_by(RunTimeseries.tick_index)
        )
        rows = result.scalars().all()

    assert len(rows) == N_TICKS, f"Expected {N_TICKS} rows, got {len(rows)}"

    for row in rows:
        try:
            d = json.loads(row.tick_json)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"tick_json on row tick_index={row.tick_index} is not valid JSON: {exc}"
            )

        key_count = len(d)
        assert key_count >= 80, (
            f"row tick_index={row.tick_index}: tick_json has only {key_count} keys "
            f"(expected ≥ 80); missing subsystem coverage"
        )

        # Spot-check a cross-subsystem sample for presence and non-null values
        spot = {
            "run_id",           # identity
            "frequency_hz",     # power-supply physics
            "p_renewable_mw",   # renewable subsystem
            "gpu_load_fraction",# GPU / Colo
            "forecast_mw",      # scheduler
            "edl_dispatch_cost_usd",  # EDL
        }
        for key in spot:
            assert key in d, (
                f"Key {key!r} missing from tick_json on row tick_index={row.tick_index}"
            )
            assert d[key] is not None, (
                f"Key {key!r} is null in tick_json on row tick_index={row.tick_index}"
            )

    await sink.stop()
