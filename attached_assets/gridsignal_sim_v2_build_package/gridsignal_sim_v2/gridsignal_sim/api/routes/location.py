"""
api/routes/location.py — Data-centre location management.

Operators can change the data-centre location so the Mistral solar/weather
agent generates insolation and ambient-temperature data that matches the real
site.  The location is stored on app.state.site_location and consumed by:

  - GET  /solar-preview    (refreshes the opening-screen weather badge)
  - POST /runs             (seeds site_latitude / site_utc_offset_h / site_name
                            when the scenario does not override them)

Geocoding
---------
PUT /api/location accepts a free-text address and resolves it to coordinates
via Mistral (mistral-small-latest).  A small built-in table handles common
cities when MISTRAL_API_KEY is absent or the call fails.

Auth note
---------
/api/location is intentionally unauthenticated so the solar console (which
has no login session) can still read the current location.  Write access (PUT)
is protected in production by wrapping this route in the admin middleware; for
the simulator that guard is left to a future hardening step.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

_log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# DST-aware UTC offset helper
# ---------------------------------------------------------------------------

def current_utc_offset_h(loc: "SiteLocation") -> float:
    """Return the live UTC offset for *loc*, honouring DST.

    Uses Python's built-in zoneinfo module (stdlib ≥ 3.9) when loc.tz_name
    is set.  Falls back to the stored standard-time utc_offset_h when the
    timezone name is absent or zoneinfo raises (e.g. tzdata not installed).
    """
    tz_name = getattr(loc, "tz_name", "")
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            return _dt.now(ZoneInfo(tz_name)).utcoffset().total_seconds() / 3600.0
        except Exception as exc:
            _log.debug("current_utc_offset_h: zoneinfo failed for %r: %s", tz_name, exc)
    return loc.utc_offset_h


# ---------------------------------------------------------------------------
# Location model
# ---------------------------------------------------------------------------

@dataclass
class SiteLocation:
    """Operator-configured data-centre location.

    Defaults to San Diego, CA — the original hard-coded reference site.
    Every field can be changed by the operator via PUT /api/location.
    """
    name: str  = "San Diego, CA"
    lat:  float = 32.72
    lon:  float = -117.16
    utc_offset_h: float = -8.0
    # One-line climate description fed into the Mistral solar prompt.
    # Mistral writes this when geocoding; a sensible default covers the
    # physics fallback path.
    climate_hint: str = (
        "Marine layer ('June Gloom') common before 10:00; clear afternoons "
        "near solar noon; occasional cloud transients; coastal moderate humidity."
    )
    # Night-time dry-bulb base temperature for the physics ambient model.
    ambient_temp_base_c: float = 14.0
    # IANA timezone name (e.g. "America/Los_Angeles").  Used by
    # current_utc_offset_h() to apply DST at query time.  Empty string means
    # "use utc_offset_h as-is" (safe fallback for Mistral-geocoded locations
    # before the prompt was updated to return this field).
    tz_name: str = "America/Los_Angeles"


# ---------------------------------------------------------------------------
# Built-in fallback table — used when MISTRAL_API_KEY is absent or geocoding fails
# ---------------------------------------------------------------------------

_KNOWN_LOCATIONS: dict[str, SiteLocation] = {
    "san diego":   SiteLocation(),   # tz_name default = "America/Los_Angeles"
    "london":      SiteLocation(
        name="London, UK", lat=51.51, lon=-0.13, utc_offset_h=0.0,
        climate_hint="Frequent overcast and light rain; occasional sunny spells; low insolation in winter.",
        ambient_temp_base_c=8.0, tz_name="Europe/London",
    ),
    "new york":    SiteLocation(
        name="New York, NY", lat=40.71, lon=-74.01, utc_offset_h=-5.0,
        climate_hint="Four distinct seasons; hot humid summers; cold winters; mixed cloud cover year-round.",
        ambient_temp_base_c=10.0, tz_name="America/New_York",
    ),
    "dubai":       SiteLocation(
        name="Dubai, UAE", lat=25.20, lon=55.27, utc_offset_h=4.0,
        climate_hint="Desert climate; extremely high insolation; minimal cloud cover; very hot summers.",
        ambient_temp_base_c=25.0, tz_name="Asia/Dubai",
    ),
    "sydney":      SiteLocation(
        name="Sydney, Australia", lat=-33.87, lon=151.21, utc_offset_h=10.0,
        climate_hint="Temperate maritime; mostly sunny; occasional storms; mild winters.",
        ambient_temp_base_c=15.0, tz_name="Australia/Sydney",
    ),
    "tokyo":       SiteLocation(
        name="Tokyo, Japan", lat=35.68, lon=139.69, utc_offset_h=9.0,
        climate_hint="Four seasons; rainy season June–July reduces output; sunny dry winters; hot humid summers.",
        ambient_temp_base_c=12.0, tz_name="Asia/Tokyo",
    ),
    "berlin":      SiteLocation(
        name="Berlin, Germany", lat=52.52, lon=13.40, utc_offset_h=1.0,
        climate_hint="Continental; overcast winters; moderate summers with reasonable insolation; spring/summer peaks.",
        ambient_temp_base_c=7.0, tz_name="Europe/Berlin",
    ),
    "singapore":   SiteLocation(
        name="Singapore", lat=1.35, lon=103.82, utc_offset_h=8.0,
        climate_hint="Equatorial; consistent insolation year-round; frequent afternoon convective showers; high humidity.",
        ambient_temp_base_c=26.0, tz_name="Asia/Singapore",
    ),
    "los angeles": SiteLocation(
        name="Los Angeles, CA", lat=34.05, lon=-118.24, utc_offset_h=-8.0,
        climate_hint="Mediterranean; abundant sunshine; coastal morning stratus clears by midday; low annual rainfall.",
        ambient_temp_base_c=16.0, tz_name="America/Los_Angeles",
    ),
    "chicago":     SiteLocation(
        name="Chicago, IL", lat=41.88, lon=-87.63, utc_offset_h=-6.0,
        climate_hint="Continental; cold cloudy winters; warm sunny summers; highly variable spring/autumn.",
        ambient_temp_base_c=9.0, tz_name="America/Chicago",
    ),
    "phoenix":     SiteLocation(
        name="Phoenix, AZ", lat=33.45, lon=-112.07, utc_offset_h=-7.0,
        climate_hint="Hot desert; highest insolation in the US; near-cloudless 300+ days/year; extreme summer heat.",
        ambient_temp_base_c=20.0, tz_name="America/Phoenix",
    ),
    "mumbai":      SiteLocation(
        name="Mumbai, India", lat=19.08, lon=72.88, utc_offset_h=5.5,
        climate_hint="Tropical; monsoon Jun–Sep severely reduces insolation; dry sunny winters; high humidity.",
        ambient_temp_base_c=22.0, tz_name="Asia/Kolkata",
    ),
    "toronto":     SiteLocation(
        name="Toronto, Canada", lat=43.65, lon=-79.38, utc_offset_h=-5.0,
        climate_hint="Humid continental; snowy winters with low insolation; warm sunny summers.",
        ambient_temp_base_c=7.0, tz_name="America/Toronto",
    ),
    "cape town":   SiteLocation(
        name="Cape Town, South Africa", lat=-33.93, lon=18.42, utc_offset_h=2.0,
        climate_hint="Mediterranean; excellent summer insolation (Dec–Feb); wet cloudy winters.",
        ambient_temp_base_c=14.0, tz_name="Africa/Johannesburg",
    ),
    "seattle":     SiteLocation(
        name="Seattle, WA", lat=47.61, lon=-122.33, utc_offset_h=-8.0,
        climate_hint="Maritime; overcast and drizzly Oct–May; surprisingly sunny dry summers.",
        ambient_temp_base_c=9.0, tz_name="America/Los_Angeles",
    ),
    "denver":      SiteLocation(
        name="Denver, CO", lat=39.74, lon=-104.98, utc_offset_h=-7.0,
        climate_hint="Semi-arid; high altitude boosts insolation; 300 sunny days/year; dramatic afternoon thunderstorms in summer.",
        ambient_temp_base_c=8.0, tz_name="America/Denver",
    ),
}


def _fuzzy_lookup(address: str) -> SiteLocation | None:
    """Attempt a case-insensitive substring match against the built-in table."""
    lower = address.lower().strip()
    for key, loc in _KNOWN_LOCATIONS.items():
        if key in lower or lower in key:
            return loc
    return None


# ---------------------------------------------------------------------------
# Mistral geocoder
# ---------------------------------------------------------------------------

_MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL    = "mistral-small-latest"
_TIMEOUT_S        = 10.0

_GEO_SYSTEM = """\
You are a geocoding assistant. Given a location description, return ONLY
valid JSON (no markdown fences, no explanation) in this exact shape:
{
  "name":                "<City, Country or City, State>",
  "lat":                 <latitude float, degrees North>,
  "lon":                 <longitude float, degrees East>,
  "utc_offset_h":        <standard UTC offset float, e.g. -8.0 for PST>,
  "tz_name":             "<IANA timezone name, e.g. America/Los_Angeles>",
  "climate_hint":        "<one sentence describing solar/cloud behaviour for a PV simulator>",
  "ambient_temp_base_c": <typical night-time dry-bulb temperature in Celsius, float>
}
Be precise with coordinates. Use the standard (non-DST) offset for utc_offset_h.
For tz_name use the canonical IANA/Olson name (e.g. Europe/London, Asia/Tokyo).
"""


def _geocode_via_mistral(address: str, api_key: str) -> SiteLocation:
    payload = json.dumps({
        "model":       _MISTRAL_MODEL,
        "messages":    [
            {"role": "system", "content": _GEO_SYSTEM},
            {"role": "user",   "content": f"Location: {address}"},
        ],
        "max_tokens":  200,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        _MISTRAL_ENDPOINT,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        body = json.loads(resp.read())
    text = body["choices"][0]["message"]["content"].strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()
    data = json.loads(text)
    return SiteLocation(
        name=str(data["name"]),
        lat=float(data["lat"]),
        lon=float(data["lon"]),
        utc_offset_h=float(data["utc_offset_h"]),
        tz_name=str(data.get("tz_name", "")),
        climate_hint=str(data.get("climate_hint", "")),
        ambient_temp_base_c=float(data.get("ambient_temp_base_c", 14.0)),
    )


def resolve_location(address: str) -> tuple[SiteLocation, str]:
    """Geocode an address → SiteLocation.

    Returns (location, source) where source is "mistral" or "builtin".
    Raises ValueError if the address cannot be resolved by either method.
    """
    api_key = os.environ.get("MISTRAL_API_KEY")
    if api_key:
        try:
            loc = _geocode_via_mistral(address, api_key)
            _log.info("location: geocoded %r → %s (%.4f, %.4f) via Mistral",
                      address, loc.name, loc.lat, loc.lon)
            return loc, "mistral"
        except Exception as exc:
            _log.warning("location: Mistral geocode failed (%s) — trying built-in table", exc)

    loc = _fuzzy_lookup(address)
    if loc:
        _log.info("location: resolved %r → %s from built-in table", address, loc.name)
        return loc, "builtin"

    raise ValueError(
        f"Could not resolve '{address}'. "
        "Try a major city name (e.g. 'London', 'Tokyo', 'Phoenix') or set MISTRAL_API_KEY."
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/location", tags=["location"])
async def get_location(request: Request) -> JSONResponse:
    """Return the current data-centre location used by the solar simulator."""
    loc: SiteLocation = getattr(request.app.state, "site_location", SiteLocation())
    data = asdict(loc)
    data["current_utc_offset_h"] = current_utc_offset_h(loc)
    return JSONResponse(data)


@router.put("/api/location", tags=["location"])
async def set_location(request: Request) -> JSONResponse:
    """Geocode a free-text address and store it as the active data-centre location.

    Request body: { "address": "Tokyo, Japan" }

    The new location is immediately used by:
      - GET /solar-preview  (next call returns weather for the new site)
      - POST /runs          (next run uses the new lat/lon for solar generation)

    Returns the resolved location plus the geocoding source ("mistral" or "builtin").
    """
    body = await request.json()
    address = str(body.get("address", "")).strip()
    if not address:
        return JSONResponse({"error": "address is required"}, status_code=422)

    try:
        loc, source = resolve_location(address)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    request.app.state.site_location = loc
    return JSONResponse({**asdict(loc), "current_utc_offset_h": current_utc_offset_h(loc), "source": source})
