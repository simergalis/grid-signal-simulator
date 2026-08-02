"""
api/routes/solar.py — Solar endpoints.

GET  /solar-preview
    Returns the current Mistral weather forecast for the configured San Diego
    time without starting a run.  Uses the same fallback chain as runs.py:
    Mistral → physics → flat profile.  Intended for the opening screen.

GET  /api/solar/state
    Full PV plant snapshot: atmosphere, power, fleet, inverter blocks,
    exposure, reserve arithmetic (§7.2 step 4), and event log.
    The Renewable Supply Console polls this at 1 Hz.

GET  /api/solar/config
    Site constants only (subset of /api/solar/state).

POST /api/solar/inject/{kind}
    Stressor injection for the standalone console:
    cloud, cloud_clear, trip, poi, soil, spike, turbine, bess, reset.

GET  /solar-console
    Serves the standalone Renewable Supply Console HTML file.
    The console polls /api/solar/state and POSTs to /api/solar/inject/*;
    both paths resolve correctly from this same origin.
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from runtime.solar_sim import generate_solar_forecast

router = APIRouter()

# San Diego UTC offset (PST, simplified — no DST)
_UTC_OFFSET_H = -8.0

# Short simulation duration just to get weather metadata.
_PREVIEW_DURATION_S = 60.0

# Path to the standalone console HTML (lives next to this package).
_CONSOLE_HTML = Path(__file__).resolve().parents[2] / "renewable" / "console.html"

# Valid stressors the console may inject.
_VALID_STRESSORS = {"cloud", "cloud_clear", "trip", "poi", "soil",
                    "spike", "turbine", "bess", "reset"}


# ---------------------------------------------------------------------------
# Existing: weather preview for the opening screen
# ---------------------------------------------------------------------------

@router.get("/solar-preview", tags=["solar"])
async def get_solar_preview() -> JSONResponse:
    """Return the current Mistral solar forecast label for San Diego.

    Calls generate_solar_forecast() with a minimal duration (60 s) so the
    Mistral prompt receives the current local San Diego time.  Only the
    weather metadata is returned; the irradiance samples are discarded.

    Falls back silently to physics estimate when MISTRAL_API_KEY is absent
    or the API call fails.
    """
    utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    local_dt = utc_now + datetime.timedelta(hours=_UTC_OFFSET_H)
    local_time = local_dt.strftime("%H:%M")

    forecast = generate_solar_forecast(
        sim_duration_s=_PREVIEW_DURATION_S,
        utc_now=utc_now,
    )

    return JSONResponse({
        "weather":    forecast.weather,
        "conditions": forecast.conditions,
        "source":     forecast.source,
        "local_time": local_time,
    })


# ---------------------------------------------------------------------------
# New: Renewable Supply Console API (§7.1.1, §7.1.2, §7.2)
# ---------------------------------------------------------------------------

def _get_sim(request: Request):
    """Pull the SolarSim singleton from app.state (set in lifespan)."""
    sim = getattr(request.app.state, "solar_sim", None)
    if sim is None:
        raise HTTPException(status_code=503, detail="SolarSim not initialised")
    return sim


@router.get("/api/solar/state", tags=["solar"])
async def solar_state(request: Request) -> JSONResponse:
    """Full PV plant snapshot consumed by the Renewable Supply Console.

    Returns atmosphere, power, fleet, inverter blocks, exposure, and the
    §7.2 step 4 reserve check results for three contingency cases:
    N−1 inverter block, plant loss at POI, and compound event (plant + 6 MW).
    """
    return JSONResponse(_get_sim(request).snapshot())


@router.get("/api/solar/config", tags=["solar"])
async def solar_config(request: Request) -> JSONResponse:
    """Site constants only — subset of /api/solar/state['site']."""
    return JSONResponse(_get_sim(request).snapshot()["site"])


@router.post("/api/solar/inject/{kind}", tags=["solar"])
async def solar_inject(kind: str, request: Request) -> JSONResponse:
    """Inject a stressor into the live PV plant model.

    Valid kinds: cloud, cloud_clear, trip, poi, soil, spike, turbine, bess, reset.

    A cloud stressor auto-clears after 14 s (matching the console behaviour).
    """
    if kind not in _VALID_STRESSORS:
        raise HTTPException(
            status_code=400,
            detail="unknown stressor '%s'; valid: %s" % (kind, sorted(_VALID_STRESSORS)),
        )
    sim = _get_sim(request)
    result = sim.inject(kind)
    if kind == "cloud":
        asyncio.create_task(_clear_cloud_later(sim))
    return JSONResponse(result)


async def _clear_cloud_later(sim) -> None:
    """Auto-clear a cloud transient after 14 s (§6.3 ramp model)."""
    await asyncio.sleep(14)
    sim.inject("cloud_clear")


# ---------------------------------------------------------------------------
# New: serve the standalone console HTML
# ---------------------------------------------------------------------------

@router.get("/solar-console", tags=["solar"], include_in_schema=False)
async def solar_console() -> FileResponse:
    """Serve the Renewable Supply Console.

    The console is a self-contained HTML file that polls /api/solar/state and
    POSTs to /api/solar/inject/{kind}.  Both paths resolve correctly from the
    same origin.  The page also runs entirely in-browser if the server is
    unreachable (it carries its own physics mirror).
    """
    if not _CONSOLE_HTML.exists():
        raise HTTPException(status_code=404, detail="Console HTML not found")
    return FileResponse(str(_CONSOLE_HTML), media_type="text/html")
