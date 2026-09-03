"""
api/routes/export.py — Telemetry-log export endpoint.

POST /api/export/telemetry-log[?run_id=<id>]
    Kicks off a background CSV build from run_timeseries.  Returns a job_id
    immediately (no blocking wait).  If run_id is omitted the most-recently
    written run is used.

GET  /api/export/telemetry-log/{job_id}/status
    Returns {"status": "running"|"done"|"error", "detail": "...", "run_id": ...}.

GET  /api/export/telemetry-log/{job_id}/file
    Returns the CSV download once status == "done".

Columns in the CSV
------------------
Every column stored in run_timeseries is included verbatim.  Additionally,
the tick_json column is expanded: each key in the JSON dict that is not
already a named DB column is appended as its own CSV column.  This means
ALL ~80 TickResult fields are present in the output:

  Dashboard:     p_generation_mw, frequency_hz, forecast_mw, protection_provisional,
                 contingency_coverage, island_collapsed, p_served_mw, p_imbalance_mw …
  GPU Colo:      gpu_load_fraction, step_phase, step_kind, kube_metrics …
  Scheduler:     pms_fast_shed_active, pms_shortfall_log, curtailment_proposal_tiers …
  Power supply:  p_renewable_mw, fuel_cell_output_mw, bess_setpoint_mw, gt_setpoint_mw,
                 bess_rated_mw, bess_usable_mwh, bess_soc_corrupted_fraction,
                 grid_exchange_mw …
  Internal:      turbine_ramp_credit_mw, peak_shortfall_mw, bess_bridging_seconds,
                 ramp_capability_mw, sub_msl_surplus_mw, edl_dispatch_cost_usd,
                 compute_inlet_temp_c, d4_balance_defect_mw, asset_delivery_error_mw …

Auth: covered by the global cookie middleware in api/app.py.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

# In-memory job registry: job_id → {"status", "out_path", "detail", "run_id"}
_jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Background CSV-build task
# ---------------------------------------------------------------------------

async def _build_csv(job_id: str, out_path: str, run_id: Optional[str]) -> None:
    """Query run_timeseries and write a fully-expanded CSV to out_path."""
    try:
        # Import here to avoid circular-import at module load.
        from api.db import _engine  # noqa: PLC0415
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(_engine) as session:
            # Resolve run_id — use the most-recent run if caller didn't supply one.
            if not run_id:
                result = await session.execute(
                    text(
                        "SELECT run_id FROM run_timeseries "
                        "ORDER BY id DESC LIMIT 1"
                    )
                )
                row = result.fetchone()
                if row is None:
                    _jobs[job_id].update(
                        {"status": "error", "detail": "No run data in database yet"}
                    )
                    return
                run_id = row[0]

            # Fetch all ticks for this run, ordered by tick_index.
            result = await session.execute(
                text(
                    "SELECT * FROM run_timeseries "
                    "WHERE run_id = :rid ORDER BY tick_index"
                ),
                {"rid": run_id},
            )
            rows = result.mappings().all()

        if not rows:
            _jobs[job_id].update(
                {"status": "error",
                 "detail": f"No ticks found for run {run_id}"}
            )
            return

        # ── Build column list ────────────────────────────────────────────────
        # Start with the DB column names (minus tick_json — we'll expand it).
        db_cols: list[str] = [k for k in rows[0].keys() if k != "tick_json"]

        # Parse tick_json for every row and collect the full key union.
        json_key_order: list[str] = []
        json_key_set:   set[str]  = set()
        parsed_jsons: list[dict]  = []
        for row in rows:
            raw = row.get("tick_json") or "{}"
            try:
                d = json.loads(raw)
            except Exception:
                d = {}
            parsed_jsons.append(d)
            for k in d:
                if k not in json_key_set and k not in set(db_cols):
                    json_key_order.append(k)
                    json_key_set.add(k)

        output_cols = db_cols + json_key_order

        # ── Write CSV ────────────────────────────────────────────────────────
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=output_cols,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row, tj in zip(rows, parsed_jsons):
                flat: dict = {}
                # DB columns first.
                for col in db_cols:
                    flat[col] = row.get(col, "")
                # tick_json expansions.
                for k in json_key_order:
                    v = tj.get(k, "")
                    # Serialise nested structures so every cell is a scalar.
                    if isinstance(v, (list, dict)):
                        v = json.dumps(v)
                    flat[k] = v
                writer.writerow(flat)

        _jobs[job_id].update(
            {"status": "done", "run_id": run_id, "row_count": len(rows)}
        )

    except Exception as exc:
        _jobs[job_id].update({"status": "error", "detail": str(exc)})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/api/export/telemetry-log", include_in_schema=True)
async def start_telemetry_log(
    run_id: Optional[str] = Query(default=None, description="Run ID to export; omit for most-recent run"),
) -> JSONResponse:
    """Kick off a CSV export for the given run (or the most-recent run)."""
    # Block export when provisional frequency-protection parameters were used.
    from runtime.run_manager import is_export_blocked as _is_export_blocked  # noqa: PLC0415
    if _is_export_blocked():
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "Export blocked: run used PROVISIONAL-UNMEASURED frequency-protection "
                    "parameters (protection_provisional=True). Calibrated site measurements "
                    "for d_motor, fixed_speed_cooling_fraction, valve_actuation_tc_s, "
                    "fuel_to_power_tc_s, max_instantaneous_load_step_mw, "
                    "vsm_inertia_constant_s, ufls_stages, relay_81u_threshold_hz, and "
                    "relay_81u_delay_s are required before export is permitted. "
                    "See gridsignal_parameters.json for PROVISIONAL-UNMEASURED entries."
                ),
                "blocked_by": "protection_provisional",
            },
        )

    with tempfile.NamedTemporaryFile(
        suffix=".csv", prefix="gridsignal_export_", delete=False
    ) as tmp:
        out_path = tmp.name

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status":   "running",
        "out_path": out_path,
        "detail":   "",
        "run_id":   run_id,
    }
    asyncio.create_task(_build_csv(job_id, out_path, run_id))

    # eta_s: upper bound for the frontend polling timeout.
    # Set to 3600 s (60 min) to accommodate large runs without the browser
    # giving up early.  Typical DB-query builds complete in < 10 s regardless.
    return JSONResponse({"job_id": job_id, "eta_s": 3600, "run_id": run_id})


@router.get("/api/export/telemetry-log/{job_id}/status")
async def poll_telemetry_log(job_id: str) -> JSONResponse:
    """Return current job status."""
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "Unknown job"})
    return JSONResponse({
        "status":    job["status"],
        "detail":    job.get("detail", ""),
        "run_id":    job.get("run_id"),
        "row_count": job.get("row_count"),
    })


@router.get("/api/export/telemetry-log/{job_id}/file", response_model=None)
async def download_telemetry_log(job_id: str) -> FileResponse | JSONResponse:
    """Stream the completed CSV; 409 if not done yet."""
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "Unknown job"})
    if job["status"] != "done":
        return JSONResponse(
            status_code=409,
            content={"detail": f"Job not done: {job['status']}"},
        )

    out_path = job["out_path"]
    resolved_run = job.get("run_id", "run")

    def _cleanup() -> None:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        _jobs.pop(job_id, None)

    from starlette.background import BackgroundTask  # noqa: PLC0415
    filename = f"gridsignal_{str(resolved_run)[:12]}.csv"
    return FileResponse(
        path=out_path,
        media_type="text/csv",
        filename=filename,
        background=BackgroundTask(_cleanup),
    )
