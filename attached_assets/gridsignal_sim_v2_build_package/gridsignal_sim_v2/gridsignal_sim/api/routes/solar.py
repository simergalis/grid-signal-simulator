"""
api/routes/solar.py — Solar endpoints.

GET  /solar-preview
    Returns the current Mistral weather forecast for the configured San Diego
    time without starting a run.  Uses the same fallback chain as runs.py:
    Mistral → physics → flat profile.  Intended for the opening screen.

GET  /api/solar/state
    Full PV plant snapshot: atmosphere, power, fleet, banks[], feeders[],
    exposure, reserve arithmetic (§7.2 step 4), and event log.
    Bank states: nominal | degraded | out | no_comms (four-state classifier).
    N−1 is sized on the largest feeder (~5 banks × 0.25 MW ≈ 1.07 MW at seed).
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

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional

from runtime.solar_sim import generate_solar_forecast

router = APIRouter()

# Short simulation duration just to get weather metadata.
_PREVIEW_DURATION_S = 60.0

# Path to the standalone console HTML (lives next to this package).
_CONSOLE_HTML = Path(__file__).resolve().parents[2] / "renewable" / "console.html"

# Valid stressors the console may inject.
_VALID_STRESSORS = {
    "cloud", "cloud_clear",
    "trip",  "bank_trip",   # trip / bank_trip — single-bank arc-fault (aliases)
    "poi",
    "soil",
    "spike",
    "turbine",
    "bess",
    "feeder_open",          # fdr-B breaker opens — common_cause advisory (FR-SOL-2)
    "comms_loss",           # fdr-A telemetry loss — reconciliation_divergence (FR-SOL-1)
    "bank_derate",          # single-bank inverter overtemp → degraded
    "bank_off",             # operator-commanded bank shutdown  (?target=bank-id)
    "bank_on",              # operator-commanded bank restore   (?target=bank-id)
    "feeder_off",           # operator-commanded feeder shutdown (?target=feeder-id)
    "feeder_on",            # operator-commanded feeder restore  (?target=feeder-id)
    "reset",
}


# ---------------------------------------------------------------------------
# Existing: weather preview for the opening screen
# ---------------------------------------------------------------------------

@router.get("/solar-preview", tags=["solar"])
async def get_solar_preview(request: Request) -> JSONResponse:
    """Return the current Mistral solar forecast label for the active site location.

    Uses the location stored at app.state.site_location (set by PUT /api/location;
    defaults to San Diego, CA).  Calls generate_solar_forecast() with a minimal
    duration (60 s) so the Mistral prompt receives the correct local time for
    the selected site.  Only the weather metadata is returned; samples are discarded.

    Falls back silently to a physics estimate when MISTRAL_API_KEY is absent
    or the API call fails.
    """
    from site_config import get_site_location_or_default as _gslod, utc_offset_for_dt as _uoff
    loc = getattr(request.app.state, "site_location", None) or _gslod()

    utc_now  = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    # DST-aware local time for the display badge
    _utc_off = _uoff(loc.tz_name, datetime.datetime.now(datetime.timezone.utc))
    local_dt = utc_now + datetime.timedelta(hours=_utc_off)
    local_time = local_dt.strftime("%H:%M")

    forecast = generate_solar_forecast(
        sim_duration_s=_PREVIEW_DURATION_S,
        utc_now=utc_now,
        site=loc,           # preferred: longitude-based true solar time
    )

    return JSONResponse({
        "weather":    forecast.weather,
        "conditions": forecast.conditions,
        "source":     forecast.source,
        "local_time": local_time,
        "site_name":  loc.site_name,
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

    Returns atmosphere, power, fleet, banks[], feeders[], exposure, and the
    §7.2 step 4 reserve check results for three contingency cases:
    N−1 feeder loss (~5 banks, §5), plant loss at POI, and compound event (plant + 6 MW).

    Bank states: nominal | degraded | out | no_comms.
    reserve.n1 and reserve.n1_feeder are both present and sized on the largest
    feeder (§5); reserve.n1_bank holds the largest individual bank figure.
    """
    return JSONResponse(_get_sim(request).snapshot())


@router.get("/api/solar/config", tags=["solar"])
async def solar_config(request: Request) -> JSONResponse:
    """Site constants only — subset of /api/solar/state['site']."""
    return JSONResponse(_get_sim(request).snapshot()["site"])


@router.post("/api/solar/inject/{kind}", tags=["solar"])
async def solar_inject(
    kind: str,
    request: Request,
    target: Optional[str] = Query(None, description="Bank id (bank_off/bank_on) or feeder id (feeder_off/feeder_on)"),
) -> JSONResponse:
    """Inject a stressor into the live PV plant model.

    Valid kinds: cloud, cloud_clear, trip, bank_trip, poi, soil, spike, turbine, bess,
    feeder_open, comms_loss, bank_derate, bank_off, bank_on, feeder_off, feeder_on, reset.

    bank_off / bank_on require ?target=<bank-id>  (e.g. ?target=bank-01).
    feeder_off / feeder_on require ?target=<feeder-id> (e.g. ?target=fdr-A).
    A cloud stressor auto-clears after 14 s (matching the console behaviour).
    """
    if kind not in _VALID_STRESSORS:
        raise HTTPException(
            status_code=400,
            detail="unknown stressor '%s'; valid: %s" % (kind, sorted(_VALID_STRESSORS)),
        )
    sim = _get_sim(request)
    result = sim.inject(kind, target=target)
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

    The console is a render-only HTML file that polls /api/solar/state and
    POSTs to /api/solar/inject/{kind}.  Both paths resolve correctly from the
    same origin.  All power scalars (blockOutput, bessBridging, pCooling,
    pDispatchRequired) are computed here on the server; the page only renders
    the values it receives.  A 'SERVER REQUIRED' banner is shown if the server
    is unreachable.
    """
    if not _CONSOLE_HTML.exists():
        raise HTTPException(status_code=404, detail="Console HTML not found")
    return FileResponse(str(_CONSOLE_HTML), media_type="text/html")
