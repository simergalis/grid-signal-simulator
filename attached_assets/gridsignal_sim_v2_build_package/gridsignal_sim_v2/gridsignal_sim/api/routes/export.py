"""
api/routes/export.py — Telemetry-log export endpoint.

POST /api/export/telemetry-log
    Runs gridsignal_logger.py in fast test mode (30 rows, 50 ms interval)
    and returns the resulting CSV file as a download.

The script is run in a subprocess so it is isolated from the event loop
and cannot block the WS tick stream.  asyncio.create_subprocess_exec is
used so the FastAPI event loop is not blocked while waiting for it.

Auth: covered by the global cookie middleware in api/app.py.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

router = APIRouter()

# gridsignal_logger.py lives at the workspace root, two levels above the
# frontend/dist directory (which is two above this file).
#   api/routes/export.py → api/ → gridsignal_sim/ → gridsignal_sim_v2/ → (workspace root)
_LOGGER_SCRIPT = Path(__file__).resolve().parents[6] / "gridsignal_logger.py"

# 600 rows × 0.1 s = 60 s of logging at 10 Hz.
_TEST_ROWS     = 600
_TEST_INTERVAL = 0.1


@router.post("/api/export/telemetry-log", include_in_schema=True)
async def export_telemetry_log() -> FileResponse:
    """Run the telemetry logger in fast test mode and return the CSV download."""

    if not _LOGGER_SCRIPT.exists():
        return JSONResponse(
            status_code=500,
            content={"detail": f"Logger script not found at {_LOGGER_SCRIPT}"},
        )

    # Write to a temp file so concurrent requests don't clobber each other.
    with tempfile.NamedTemporaryFile(
        suffix=".csv", prefix="gridsignal_log_", delete=False
    ) as tmp:
        out_path = tmp.name

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(_LOGGER_SCRIPT),
            "--rows",     str(_TEST_ROWS),
            "--interval", str(_TEST_INTERVAL),
            "--fast",                          # generate all rows without sleeping
            "--out",      out_path,
            # Discard stdout (progress lines) — pipe buffering would stall the
            # subprocess once the OS pipe buffer fills up.  We only need the
            # CSV file that the script writes directly to disk.
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        # --fast skips inter-tick sleep, so the script finishes in < 5 s.
        _timeout = 30
        try:
            _unused, _stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return JSONResponse(
                status_code=500,
                content={"detail": f"Logger script timed out after {_timeout:.0f} s"},
            )

        if proc.returncode != 0:
            err = _stderr.decode(errors="replace").strip()
            return JSONResponse(
                status_code=500,
                content={"detail": f"Logger script exited {proc.returncode}: {err}"},
            )

        if not Path(out_path).exists() or Path(out_path).stat().st_size == 0:
            return JSONResponse(
                status_code=500,
                content={"detail": "Logger script produced an empty file"},
            )

        def _delete_tmp() -> None:
            try:
                os.unlink(out_path)
            except OSError:
                pass

        return FileResponse(
            path=out_path,
            media_type="text/csv",
            filename="system_stats.csv",
            background=BackgroundTask(_delete_tmp),
        )

    except Exception as exc:
        # Clean up the temp file on any unexpected error.
        try:
            os.unlink(out_path)
        except OSError:
            pass
        return JSONResponse(status_code=500, content={"detail": str(exc)})
