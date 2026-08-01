"""
api/routes/solar.py — Solar forecast preview endpoint.

GET /solar-preview
    Returns the current Mistral weather forecast for the configured San Diego
    time without starting a run.  Uses the same fallback chain as runs.py:
    Mistral → physics → flat profile.

    Intended for the opening screen: the Solar PV PlantNode displays the
    weather label and local time so users see why solar output may be
    constrained before they hit START.

Response shape
--------------
{
  "weather":    "marine_layer",          # short label
  "conditions": "Marine layer until ...", # one human-readable sentence
  "source":     "mistral",               # "mistral" or "physics"
  "local_time": "08:45"                  # San Diego local time (PST, UTC-8)
}
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from runtime.solar_sim import generate_solar_forecast

router = APIRouter()

# San Diego UTC offset (PST, simplified — no DST)
_UTC_OFFSET_H = -8.0

# Short simulation duration just to get weather metadata.
# We only need weather/conditions/source; samples are discarded.
_PREVIEW_DURATION_S = 60.0


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
