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
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional

from runtime.solar_sim import generate_solar_forecast, _solar_fraction_at

router = APIRouter()

# Simulation duration used for the weather-preview call.
#
# Must be long enough that Mistral's natural sample spacing (typically every
# 60–120 s for a ~10-minute window) stays within the _parse_forecast filter
# cutoff of sim_duration_s × 1.05.  With 60 s the cutoff is only 63 s, so any
# sample beyond that was silently dropped, leaving an empty list that triggered
# the physics fallback even when Mistral returned valid data.
# 600 s gives a 630 s cutoff, comfortably covering Mistral's typical output.
# Only weather metadata (weather, conditions, source) is used from the result;
# the irradiance samples themselves are discarded by get_solar_preview().
_PREVIEW_DURATION_S = 600.0

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
async def get_solar_preview(
    request: Request,
    utc_now: Optional[str] = Query(
        None,
        description=(
            "Override the current UTC instant (ISO-8601, e.g. '2026-06-21T10:00:00'). "
            "Intended for testing only; omit in production to use server wall-clock time."
        ),
    ),
) -> JSONResponse:
    """Return the current Mistral solar forecast label for the active site location.

    Uses the location stored at app.state.site_location (set by PUT /api/location;
    defaults to San Diego, CA).  Calls generate_solar_forecast() with a minimal
    duration (60 s) so the Mistral prompt receives the correct local time for
    the selected site.  Only the weather metadata is returned; samples are discarded.

    Falls back silently to a physics estimate when MISTRAL_API_KEY is absent
    or the API call fails.

    Extended fields (Task-75):
      sun_elevation_deg  — sun elevation angle in degrees; negative = below horizon.
      expected_fraction  — physics-model output fraction at current time [0, 1].
      p_renewable_mw     — expected_fraction × plant_rated_ac_mw (MW).
      lat                — site latitude degrees North.
      utc_offset_h       — DST-aware UTC offset used for the computation.
      plant_rated_ac_mw  — AC rated capacity of the PV plant in MW.

    Query parameters:
      utc_now  (optional) — override wall-clock time for testing; ISO-8601 string.
    """
    from site_config import get_site_location_or_default as _gslod, utc_offset_for_dt as _utc_off
    loc = getattr(request.app.state, "site_location", None) or _gslod()

    if utc_now is not None:
        try:
            _parsed = datetime.datetime.fromisoformat(utc_now.replace("Z", "+00:00"))
            if _parsed.tzinfo is not None:
                # Convert timezone-aware value to UTC, then drop tzinfo.
                _utc_now = _parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            else:
                # Already a naive UTC string (most common test form).
                _utc_now = _parsed
        except ValueError:
            return JSONResponse(
                {"error": f"utc_now must be ISO-8601 (e.g. '2026-06-21T10:00:00'); got {utc_now!r}"},
                status_code=422,
            )
    else:
        _utc_now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    # Derive the DST-aware UTC offset for the *override* instant (not wall-clock now),
    # so that a June utc_now correctly resolves CEST (+2) rather than CET (+1).
    _utc_now_aware = _utc_now.replace(tzinfo=datetime.timezone.utc)
    live_offset = _utc_off(loc.tz_name, _utc_now_aware)

    local_dt   = _utc_now + datetime.timedelta(hours=live_offset)
    local_time = local_dt.strftime("%H:%M")

    forecast = generate_solar_forecast(
        sim_duration_s=_PREVIEW_DURATION_S,
        utc_now=_utc_now,
        site=loc,           # preferred: longitude-based true solar time
    )

    # Use longitude-based true solar time (NOAA EoT) for both physics outputs.
    sun_elev      = _sun_elevation_deg(
        _utc_now, loc.latitude_deg, live_offset, longitude_deg=loc.longitude_deg
    )
    expected_frac = _solar_fraction_at(
        _utc_now, lat_deg=loc.latitude_deg, longitude_deg=loc.longitude_deg
    )

    # Plant rated MW from the live SolarSim if available, else canonical default.
    solar_sim = getattr(request.app.state, "solar_sim", None)
    plant_rated_mw = solar_sim.cfg.plant_rated_ac_mw if solar_sim is not None else 4.99

    return JSONResponse({
        "weather":           forecast.weather,
        "conditions":        forecast.conditions,
        "source":            forecast.source,
        "local_time":        local_time,
        "site_name":         loc.site_name,
        "sun_elevation_deg": round(sun_elev, 1),
        "expected_fraction": round(expected_frac, 4),
        "p_renewable_mw":    round(expected_frac * plant_rated_mw, 4),
        "lat":               loc.latitude_deg,
        "utc_offset_h":      live_offset,
        "plant_rated_ac_mw": round(plant_rated_mw, 3),
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

    Extended fields (Task-75):
      site.sun_elevation_deg — sun elevation angle in degrees; negative = below horizon.
      site.lat               — site latitude in degrees North.
      site.utc_offset_h      — DST-aware UTC offset used for the computation.
    """
    from api.routes.location import current_utc_offset_h as _live_offset
    from site_config import get_site_location_or_default as _gslod
    snap = _get_sim(request).snapshot()

    loc = getattr(request.app.state, "site_location", None) or _gslod()
    utc_now    = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    live_off   = _live_offset(loc)
    sun_elev   = _sun_elevation_deg(utc_now, loc.latitude_deg, live_off)

    snap["site"]["sun_elevation_deg"] = round(sun_elev, 1)
    snap["site"]["lat"]               = loc.latitude_deg
    snap["site"]["utc_offset_h"]      = live_off

    return JSONResponse(snap)


@router.get("/api/solar/config", tags=["solar"])
async def solar_config(request: Request) -> JSONResponse:
    """Site constants only — subset of /api/solar/state['site'].

    Includes Task-75 sun elevation fields so /config is always a superset of
    the site keys the frontend reads from /api/solar/state.
    """
    from api.routes.location import current_utc_offset_h as _live_offset
    from site_config import get_site_location_or_default as _gslod
    site = _get_sim(request).snapshot()["site"]
    loc = getattr(request.app.state, "site_location", None) or _gslod()
    utc_now  = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    live_off = _live_offset(loc)
    sun_elev = _sun_elevation_deg(utc_now, loc.latitude_deg, live_off)
    site["sun_elevation_deg"] = round(sun_elev, 1)
    site["lat"]               = loc.latitude_deg
    site["utc_offset_h"]      = live_off
    return JSONResponse(site)


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

def _sun_elevation_deg(
    utc_dt: datetime.datetime,
    lat_deg: float,
    utc_offset_h: float,
    *,
    longitude_deg: Optional[float] = None,
) -> float:
    """Return sun elevation angle in degrees (negative when below horizon).

    When longitude_deg is provided the NOAA equation of time is applied for
    true solar time (same model as _solar_fraction_at).  Falls back to the
    legacy UTC-offset approximation when longitude_deg is None.
    """
    day_of_year = utc_dt.timetuple().tm_yday
    utc_h = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    if longitude_deg is not None:
        B = math.radians(360.0 / 365.0 * (day_of_year - 81))
        eot_min = 9.87 * math.sin(2.0 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
        solar_h = (utc_h + longitude_deg / 15.0 + eot_min / 60.0) % 24.0
    else:
        solar_h = (utc_h + utc_offset_h) % 24.0
    hour_angle_rad = math.radians((solar_h - 12.0) * 15.0)
    decl_rad = math.radians(
        23.45 * math.sin(math.radians(360.0 / 365.0 * (day_of_year - 81)))
    )
    lat_rad = math.radians(lat_deg)
    sin_elev = (
        math.sin(lat_rad) * math.sin(decl_rad)
        + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_angle_rad)
    )
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))
