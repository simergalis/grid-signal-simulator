"""
api/routes/location.py — Data-centre location management.

Operators can change the data-centre location so the Mistral solar/weather
agent generates insolation and ambient-temperature data that matches the real
site.  The location is stored in both app.state.site_location and the
site_config module singleton (via set_site_location).

Geocoding
---------
PUT /api/location accepts a free-text address and resolves it to coordinates
via Mistral (mistral-small-latest).  A small built-in table handles common
cities when MISTRAL_API_KEY is absent or the call fails.

Persistence (schema_version 1)
-------------------------------
gridsignal_site.json stores the current location across server restarts.
Legacy records (no schema_version field, old name/lat/lon/utc_offset_h keys)
are migrated to schema_version 1 on restore.  Records whose tz_name cannot be
derived are quarantined rather than silently falling back to San Diego.

Auth note
---------
/api/location is intentionally open so the solar console (which has no login
session) can still read the current location.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
import os
import pathlib
import urllib.error
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# SiteLocation lives in site_config — the only module permitted to contain
# geographic literals.  Re-export it here so existing importers of
# `from api.routes.location import SiteLocation` continue to work.
from site_config import (
    SiteLocation,
    SiteLocationNotConfigured,
    set_site_location,
    utc_offset_for_dt,
)

_log = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

_SITE_JSON_PATH = pathlib.Path("gridsignal_site.json")
_SCHEMA_VERSION = 1


def _old_to_new(saved: dict) -> dict | None:
    """Convert a schema_version 0 (old) record to schema_version 1.

    Old keys: name, lat, lon, utc_offset_h, climate_hint, ambient_temp_base_c, tz_name
    New keys: site_name, latitude_deg, longitude_deg, tz_name, ...

    Returns None if the record cannot be safely migrated (e.g. tz_name absent
    and timezonefinder is unavailable).
    """
    migrated: dict = {}

    # Required fields
    try:
        migrated["site_name"]        = str(saved["name"])
        migrated["latitude_deg"]     = float(saved["lat"])
        migrated["longitude_deg"]    = float(saved["lon"])
    except KeyError as exc:
        _log.warning("location: legacy record missing required key %s — quarantining", exc)
        return None

    # tz_name: already present in most records (added in a prior deploy)
    tz = saved.get("tz_name", "")
    if not tz:
        # Try timezonefinder; if unavailable, quarantine
        try:
            import timezonefinder as _tzf
            tf = _tzf.TimezoneFinder()
            tz = tf.timezone_at(
                lat=migrated["latitude_deg"],
                lng=migrated["longitude_deg"],
            ) or ""
        except Exception:
            _log.warning(
                "location: legacy record has no tz_name and timezonefinder is unavailable "
                "— quarantining record for %r",
                migrated.get("site_name"),
            )
            return None
    migrated["tz_name"] = tz

    # Optional fields
    migrated["climate_hint"]        = str(saved.get("climate_hint", ""))
    migrated["ambient_temp_base_c"] = float(saved.get("ambient_temp_base_c", 14.0))
    migrated["source"]              = "configured"
    migrated["schema_version"]      = _SCHEMA_VERSION
    return migrated


def load_site_location() -> SiteLocation | None:
    """Restore the site location from gridsignal_site.json.

    Handles both legacy (schema_version absent) and current (schema_version 1) formats.
    Returns None on any error or if the file does not exist.
    """
    if not _SITE_JSON_PATH.exists():
        return None
    try:
        saved = json.loads(_SITE_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("location: could not read %s: %s", _SITE_JSON_PATH, exc)
        return None

    if saved.get("schema_version") == _SCHEMA_VERSION:
        # Current format
        fields = {f.name for f in dataclasses.fields(SiteLocation)}
        try:
            return SiteLocation(**{k: v for k, v in saved.items() if k in fields})
        except Exception as exc:
            _log.warning("location: could not construct SiteLocation from %s: %s", saved, exc)
            return None
    else:
        # Legacy format — attempt migration
        migrated = _old_to_new(saved)
        if migrated is None:
            # Quarantine
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            qpath = _SITE_JSON_PATH.with_suffix(f".quarantine.{ts}.json")
            try:
                qpath.write_text(json.dumps(saved))
                _log.warning(
                    "location: quarantined unmigrateable legacy record → %s", qpath
                )
            except Exception:
                pass
            _SITE_JSON_PATH.unlink(missing_ok=True)
            return None
        # Save migrated format back to disk
        try:
            _SITE_JSON_PATH.write_text(json.dumps(migrated, indent=2))
        except Exception as exc:
            _log.warning("location: could not save migrated site file: %s", exc)
        fields = {f.name for f in dataclasses.fields(SiteLocation)}
        try:
            return SiteLocation(**{k: v for k, v in migrated.items() if k in fields})
        except Exception as exc:
            _log.warning("location: could not construct SiteLocation from migrated %s: %s", migrated, exc)
            return None


def save_site_location(loc: SiteLocation) -> None:
    """Persist the site location to gridsignal_site.json (schema_version 1)."""
    try:
        data = dataclasses.asdict(loc)
        data["schema_version"] = _SCHEMA_VERSION
        _SITE_JSON_PATH.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        _log.warning("location: could not persist to %s: %s", _SITE_JSON_PATH, exc)


# ---------------------------------------------------------------------------
# DST-aware UTC offset helper (re-exported for external consumers)
# ---------------------------------------------------------------------------

def current_utc_offset_h(loc: SiteLocation) -> float:
    """Return the live DST-aware UTC offset for *loc* using its tz_name."""
    return utc_offset_for_dt(loc.tz_name, datetime.datetime.now(datetime.timezone.utc))


# ---------------------------------------------------------------------------
# Built-in fallback table
# ---------------------------------------------------------------------------

_KNOWN_LOCATIONS: dict[str, SiteLocation] = {
    "san diego":   SiteLocation(
        site_name="San Diego, CA",
        latitude_deg=32.72, longitude_deg=-117.16,
        tz_name="America/Los_Angeles",
        climate_hint="Marine layer ('June Gloom') common before 10:00; clear afternoons; coastal moderate humidity.",
        ambient_temp_base_c=14.0,
    ),
    "london":      SiteLocation(
        site_name="London, UK",
        latitude_deg=51.51, longitude_deg=-0.13,
        tz_name="Europe/London",
        climate_hint="Frequent overcast and light rain; occasional sunny spells; low insolation in winter.",
        ambient_temp_base_c=8.0,
    ),
    "new york":    SiteLocation(
        site_name="New York, NY",
        latitude_deg=40.71, longitude_deg=-74.01,
        tz_name="America/New_York",
        climate_hint="Four distinct seasons; hot humid summers; cold winters; mixed cloud cover year-round.",
        ambient_temp_base_c=10.0,
    ),
    "dubai":       SiteLocation(
        site_name="Dubai, UAE",
        latitude_deg=25.20, longitude_deg=55.27,
        tz_name="Asia/Dubai",
        climate_hint="Desert climate; extremely high insolation; minimal cloud cover; very hot summers.",
        ambient_temp_base_c=25.0,
    ),
    "sydney":      SiteLocation(
        site_name="Sydney, Australia",
        latitude_deg=-33.87, longitude_deg=151.21,
        tz_name="Australia/Sydney",
        climate_hint="Temperate maritime; mostly sunny; occasional storms; mild winters.",
        ambient_temp_base_c=15.0,
    ),
    "tokyo":       SiteLocation(
        site_name="Tokyo, Japan",
        latitude_deg=35.68, longitude_deg=139.69,
        tz_name="Asia/Tokyo",
        climate_hint="Four seasons; rainy season June–July reduces output; sunny dry winters; hot humid summers.",
        ambient_temp_base_c=12.0,
    ),
    "berlin":      SiteLocation(
        site_name="Berlin, Germany",
        latitude_deg=52.52, longitude_deg=13.40,
        tz_name="Europe/Berlin",
        climate_hint="Continental; overcast winters; moderate summers with reasonable insolation; spring/summer peaks.",
        ambient_temp_base_c=7.0,
    ),
    "singapore":   SiteLocation(
        site_name="Singapore",
        latitude_deg=1.35, longitude_deg=103.82,
        tz_name="Asia/Singapore",
        climate_hint="Equatorial; consistent insolation year-round; frequent afternoon convective showers; high humidity.",
        ambient_temp_base_c=26.0,
    ),
    "los angeles": SiteLocation(
        site_name="Los Angeles, CA",
        latitude_deg=34.05, longitude_deg=-118.24,
        tz_name="America/Los_Angeles",
        climate_hint="Mediterranean; abundant sunshine; coastal morning stratus clears by midday; low annual rainfall.",
        ambient_temp_base_c=16.0,
    ),
    "chicago":     SiteLocation(
        site_name="Chicago, IL",
        latitude_deg=41.88, longitude_deg=-87.63,
        tz_name="America/Chicago",
        climate_hint="Continental; cold cloudy winters; warm sunny summers; highly variable spring/autumn.",
        ambient_temp_base_c=9.0,
    ),
    "phoenix":     SiteLocation(
        site_name="Phoenix, AZ",
        latitude_deg=33.45, longitude_deg=-112.07,
        tz_name="America/Phoenix",
        climate_hint="Hot desert; highest insolation in the US; near-cloudless 300+ days/year; extreme summer heat.",
        ambient_temp_base_c=20.0,
    ),
    "mumbai":      SiteLocation(
        site_name="Mumbai, India",
        latitude_deg=19.08, longitude_deg=72.88,
        tz_name="Asia/Kolkata",
        climate_hint="Tropical; monsoon Jun–Sep severely reduces insolation; dry sunny winters; high humidity.",
        ambient_temp_base_c=22.0,
    ),
    "toronto":     SiteLocation(
        site_name="Toronto, Canada",
        latitude_deg=43.65, longitude_deg=-79.38,
        tz_name="America/Toronto",
        climate_hint="Humid continental; snowy winters with low insolation; warm sunny summers.",
        ambient_temp_base_c=7.0,
    ),
    "cape town":   SiteLocation(
        site_name="Cape Town, South Africa",
        latitude_deg=-33.93, longitude_deg=18.42,
        tz_name="Africa/Johannesburg",
        climate_hint="Mediterranean; excellent summer insolation (Dec–Feb); wet cloudy winters.",
        ambient_temp_base_c=14.0,
    ),
    "seattle":     SiteLocation(
        site_name="Seattle, WA",
        latitude_deg=47.61, longitude_deg=-122.33,
        tz_name="America/Los_Angeles",
        climate_hint="Maritime; overcast and drizzly Oct–May; surprisingly sunny dry summers.",
        ambient_temp_base_c=9.0,
    ),
    "denver":      SiteLocation(
        site_name="Denver, CO",
        latitude_deg=39.74, longitude_deg=-104.98,
        tz_name="America/Denver",
        climate_hint="Semi-arid; high altitude boosts insolation; 300 sunny days/year; dramatic afternoon thunderstorms in summer.",
        ambient_temp_base_c=8.0,
    ),
    "honolulu":    SiteLocation(
        site_name="Honolulu, HI",
        latitude_deg=21.31, longitude_deg=-157.86,
        tz_name="Pacific/Honolulu",
        climate_hint="Tropical maritime; near-constant trade winds; abundant sunshine year-round; brief afternoon showers possible; no DST.",
        ambient_temp_base_c=23.0,
    ),
    "hawaii":      SiteLocation(
        site_name="Honolulu, HI",
        latitude_deg=21.31, longitude_deg=-157.86,
        tz_name="Pacific/Honolulu",
        climate_hint="Tropical maritime; near-constant trade winds; abundant sunshine year-round; brief afternoon showers possible; no DST.",
        ambient_temp_base_c=23.0,
    ),
    "miami":       SiteLocation(
        site_name="Miami, FL",
        latitude_deg=25.77, longitude_deg=-80.19,
        tz_name="America/New_York",
        climate_hint="Tropical; abundant sunshine; brief afternoon thunderstorms Jun–Sep; high humidity; minimal seasonal variation.",
        ambient_temp_base_c=22.0,
    ),
    "dallas":      SiteLocation(
        site_name="Dallas, TX",
        latitude_deg=32.78, longitude_deg=-96.80,
        tz_name="America/Chicago",
        climate_hint="Subtropical; hot sunny summers; mild winters; occasional severe spring storms; high annual insolation.",
        ambient_temp_base_c=16.0,
    ),
    "austin":      SiteLocation(
        site_name="Austin, TX",
        latitude_deg=30.27, longitude_deg=-97.74,
        tz_name="America/Chicago",
        climate_hint="Subtropical; very high insolation; hot summers; mild winters; occasional severe spring storms.",
        ambient_temp_base_c=17.0,
    ),
    "san antonio": SiteLocation(
        site_name="San Antonio, TX",
        latitude_deg=29.4241, longitude_deg=-98.4936,
        tz_name="America/Chicago",
        climate_hint="Hot summers with frequent clear skies; mild winters with moderate cloud cover.",
        ambient_temp_base_c=10.0,
    ),
    "portland":    SiteLocation(
        site_name="Portland, OR",
        latitude_deg=45.52, longitude_deg=-122.68,
        tz_name="America/Los_Angeles",
        climate_hint="Maritime; overcast and rainy Oct–May; dry sunny summers; lower insolation than most US cities.",
        ambient_temp_base_c=9.0,
    ),
    "auckland":    SiteLocation(
        site_name="Auckland, New Zealand",
        latitude_deg=-36.85, longitude_deg=174.76,
        tz_name="Pacific/Auckland",
        climate_hint="Temperate maritime; mild seasons; moderate cloud cover; Southern Hemisphere seasons inverted vs North America.",
        ambient_temp_base_c=13.0,
    ),
    "frankfurt":   SiteLocation(
        site_name="Frankfurt, Germany",
        latitude_deg=50.11, longitude_deg=8.68,
        tz_name="Europe/Berlin",
        climate_hint="Continental; overcast winters; moderate summers with reasonable insolation.",
        ambient_temp_base_c=7.0,
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

# Use Region/City as the example placeholder — avoids real IANA strings in this file
_GEO_SYSTEM = """\
You are a geocoding assistant. Given a location description, return ONLY
valid JSON (no markdown fences, no explanation) in this exact shape:
{
  "name":                "<City, Country or City, State>",
  "lat":                 <latitude float, degrees North>,
  "lon":                 <longitude float, degrees East>,
  "tz_name":             "<IANA timezone name, e.g. Region/City>",
  "climate_hint":        "<one sentence describing solar/cloud behaviour for a PV simulator>",
  "ambient_temp_base_c": <typical night-time dry-bulb temperature in Celsius, float>
}
Be precise with coordinates.
For tz_name use the canonical IANA/Olson name (e.g. Europe/London, Asia/Tokyo).
Do NOT include a utc_offset_h field; the server computes live DST-aware offsets.
"""


def _geocode_via_mistral(address: str, api_key: str) -> SiteLocation:
    payload = json.dumps({
        "model":       _MISTRAL_MODEL,
        "messages":    [
            {"role": "system", "content": _GEO_SYSTEM},
            {"role": "user",   "content": f"Location: {address}"},
        ],
        "max_tokens":  350,
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
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()
    data = json.loads(text)
    return SiteLocation(
        site_name=str(data["name"]),
        latitude_deg=float(data["lat"]),
        longitude_deg=float(data["lon"]),
        tz_name=str(data.get("tz_name", "")),
        climate_hint=str(data.get("climate_hint", "")),
        ambient_temp_base_c=float(data.get("ambient_temp_base_c", 14.0)),
        source="mistral",
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
            _log.info(
                "location: geocoded %r → %s (%.4f, %.4f) via Mistral",
                address, loc.site_name, loc.latitude_deg, loc.longitude_deg,
            )
            return loc, "mistral"
        except Exception as exc:
            _log.warning("location: Mistral geocode failed (%s) — trying built-in table", exc)

    loc = _fuzzy_lookup(address)
    if loc:
        _log.info("location: resolved %r → %s from built-in table", address, loc.site_name)
        return loc, "builtin"

    raise ValueError(
        f"Could not resolve '{address}'. "
        "Try a major city name (e.g. 'London', 'Tokyo', 'Phoenix') or set MISTRAL_API_KEY."
    )


def _loc_to_response(loc: SiteLocation, *, source: str = "") -> dict:
    """Serialise a SiteLocation with both new and legacy field names for the API."""
    data = dataclasses.asdict(loc)
    # Backward-compat aliases (old frontend consumers read these keys)
    data["name"]               = loc.site_name
    data["lat"]                = loc.latitude_deg
    data["lon"]                = loc.longitude_deg
    data["utc_offset_h"]       = utc_offset_for_dt(loc.tz_name, datetime.datetime.now(datetime.timezone.utc))
    data["current_utc_offset_h"] = data["utc_offset_h"]
    if source:
        data["source"] = source
    return data


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/location", tags=["location"])
async def get_location(request: Request) -> JSONResponse:
    """Return the current data-centre location used by the solar simulator."""
    loc: SiteLocation | None = getattr(request.app.state, "site_location", None)
    if loc is None:
        from site_config import get_site_location_or_default
        loc = get_site_location_or_default()
    return JSONResponse(_loc_to_response(loc))


@router.put("/api/location", tags=["location"])
async def set_location(request: Request) -> JSONResponse:
    """Geocode a free-text address and store it as the active data-centre location.

    Request body: { "address": "Tokyo, Japan" }
    """
    body = await request.json()
    address = str(body.get("address", "")).strip()
    if not address:
        return JSONResponse({"error": "address is required"}, status_code=422)

    try:
        loc, source = resolve_location(address)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)

    # Update both app.state and the process-level singleton
    request.app.state.site_location = loc
    set_site_location(loc)
    save_site_location(loc)

    # Keep SolarSim site_id label in sync
    import re as _re
    _solar_sim = getattr(request.app.state, "solar_sim", None)
    if _solar_sim is not None:
        _slug = _re.sub(r"[^a-z0-9]+", "-", loc.site_name.lower()).strip("-") or "datacenter-01"
        _solar_sim.cfg.site_id = _slug

    return JSONResponse(_loc_to_response(loc, source=source))


# ---------------------------------------------------------------------------
# Site settings — name editable by operators
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass


@_dataclass
class SiteSettings:
    """Operator-editable site display settings."""
    site_name: str = "SV1 - Silicon Valley, California"


def _get_settings(request: Request) -> SiteSettings:
    return getattr(request.app.state, "site_settings", SiteSettings())


@router.get("/api/site/settings", tags=["site"])
async def get_site_settings(request: Request) -> JSONResponse:
    """Return current operator-editable site settings."""
    s = _get_settings(request)
    return JSONResponse({"site_name": s.site_name})


@router.patch("/api/site/settings", tags=["site"])
async def patch_site_settings(request: Request) -> JSONResponse:
    """Update operator-editable site settings."""
    body = await request.json()
    s = _get_settings(request)

    if "site_name" in body:
        name = str(body["site_name"]).strip()
        if not name:
            return JSONResponse({"error": "site_name cannot be empty"}, status_code=422)
        if len(name) > 80:
            return JSONResponse({"error": "site_name must be 80 characters or fewer"}, status_code=422)
        s.site_name = name

    request.app.state.site_settings = s
    return JSONResponse({"site_name": s.site_name})
