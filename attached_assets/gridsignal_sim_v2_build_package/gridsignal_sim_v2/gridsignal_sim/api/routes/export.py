"""
api/routes/export.py — Telemetry-log export endpoint.

POST /api/export/telemetry-log
    Starts gridsignal_logger.py in a background asyncio task and returns a
    job_id immediately (no blocking wait).  The 60-second subprocess runs
    while the browser polls for completion.

GET  /api/export/telemetry-log/{job_id}/status
    Returns {"status": "running"|"done"|"error", "detail": "..."}.

GET  /api/export/telemetry-log/{job_id}/file
    Returns the CSV download once status == "done".

Auth: covered by the global cookie middleware in api/app.py.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

router = APIRouter()

# gridsignal_logger.py lives at the workspace root.
_LOGGER_SCRIPT = Path(__file__).resolve().parents[6] / "gridsignal_logger.py"

# 600 rows × 0.1 s = 60 s of logging at 10 Hz.
_TEST_ROWS     = 600
_TEST_INTERVAL = 0.1

# In-memory job registry: job_id → {"status", "out_path", "detail"}
_jobs: dict[str, dict] = {}


async def _run_logger(job_id: str, out_path: str) -> None:
    """Background task: run the logger subprocess and update _jobs when done."""
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(_LOGGER_SCRIPT),
            "--rows",     str(_TEST_ROWS),
            "--interval", str(_TEST_INTERVAL),
            "--out",      out_path,
            # Discard stdout (progress lines) to avoid pipe-buffer stall.
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        timeout = _TEST_ROWS * _TEST_INTERVAL + 30   # 90 s
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            _jobs[job_id].update({"status": "error", "detail": "Logger timed out"})
            return

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            _jobs[job_id].update({"status": "error",
                                   "detail": f"Exit {proc.returncode}: {err}"})
            return

        if not Path(out_path).exists() or Path(out_path).stat().st_size == 0:
            _jobs[job_id].update({"status": "error", "detail": "Empty output file"})
            return

        _jobs[job_id]["status"] = "done"

    except Exception as exc:
        _jobs[job_id].update({"status": "error", "detail": str(exc)})


@router.post("/api/export/telemetry-log", include_in_schema=True)
async def start_telemetry_log() -> JSONResponse:
    """Kick off the logger; return job_id and eta immediately."""
    # Phase 2A (DR-2026-08-08-FREQ): Block demo export when run used
    # PROVISIONAL-UNMEASURED protection parameters.  Any islanded tick sets
    # protection_provisional=True (D_eff uses d_motor + fixed_speed_cooling_fraction,
    # both PROVISIONAL-UNMEASURED).  The run_manager propagates this flag run-wide.
    # Callers must supply measured site data before export is permitted.
    from runtime.run_manager import is_export_blocked as _is_export_blocked
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
                    "relay_81u_delay_s are required before demo export is permitted. "
                    "See gridsignal_parameters.json for PROVISIONAL-UNMEASURED entries."
                ),
                "blocked_by": "protection_provisional",
            },
        )
    if not _LOGGER_SCRIPT.exists():
        return JSONResponse(
            status_code=500,
            content={"detail": f"Logger script not found at {_LOGGER_SCRIPT}"},
        )

    with tempfile.NamedTemporaryFile(
        suffix=".csv", prefix="gridsignal_log_", delete=False
    ) as tmp:
        out_path = tmp.name

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "out_path": out_path, "detail": ""}
    asyncio.create_task(_run_logger(job_id, out_path))

    return JSONResponse({
        "job_id": job_id,
        "eta_s":  _TEST_ROWS * _TEST_INTERVAL,
    })


@router.get("/api/export/telemetry-log/{job_id}/status")
async def poll_telemetry_log(job_id: str) -> JSONResponse:
    """Return current job status."""
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "Unknown job"})
    return JSONResponse({"status": job["status"], "detail": job.get("detail", "")})


@router.get("/api/export/telemetry-log/{job_id}/file", response_model=None)
async def download_telemetry_log(job_id: str) -> FileResponse | JSONResponse:
    """Stream the completed CSV; 409 if not done yet."""
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "Unknown job"})
    if job["status"] != "done":
        return JSONResponse(status_code=409,
                            content={"detail": f"Job not done: {job['status']}"})

    out_path = job["out_path"]

    def _cleanup() -> None:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        _jobs.pop(job_id, None)

    return FileResponse(
        path=out_path,
        media_type="text/csv",
        filename="system_stats.csv",
        background=BackgroundTask(_cleanup),
    )
