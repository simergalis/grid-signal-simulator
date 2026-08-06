"""
site_config.py — Single source of truth for data-centre location.

This is the ONLY file in the repository that may contain geographic literals
(latitude, longitude, IANA timezone strings).  All other modules must import
SiteLocation from here and must never hard-code coordinates or timezone names.

Guard A (test_no_hardcoded_location.py) enforces this at the AST level:
it scans every other .py file and fails on any float literal in the
coordinate range or IANA timezone string assigned to a matching variable.

Usage
-----
    from site_config import get_site_location, set_site_location, SiteLocationNotConfigured

    # Read (raises SiteLocationNotConfigured if not configured)
    loc = get_site_location()

    # Read with San Diego fallback (never raises)
    loc = get_site_location_or_default()

    # Write (called by PUT /api/location after geocoding)
    set_site_location(new_loc)

    # DST-aware UTC offset for a specific instant
    offset_h = utc_offset_for_dt(loc.tz_name, datetime.datetime.now(utc))
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
from typing import Optional

_log = logging.getLogger(__name__)


@dataclasses.dataclass
class SiteLocation:
    """Operator-configured data-centre location.

    All field names differ deliberately from the old `name/lat/lon/utc_offset_h`
    shape so that any code still reading old attribute names fails loudly at
    attribute-access time rather than silently returning San Diego values.

    Geographic literals below (lat/lon/tz) are permitted ONLY because this file
    is the canonical exception allowed by Guard A.
    """
    site_name:           str
    latitude_deg:        float
    longitude_deg:       float
    tz_name:             str        # IANA zone, e.g. "America/Chicago"
    source:              str   = "configured"
    climate_hint:        str   = ""
    ambient_temp_base_c: float = 14.0


class SiteLocationNotConfigured(RuntimeError):
    """Raised by get_site_location() when no location has been stored yet."""


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_stored: Optional[SiteLocation] = None

# Run-active flag — set by the run-lifecycle layer so set_site_location()
# can emit a warning when called mid-run.  Not imported from run_manager to
# avoid a circular dependency (site_config is a leaf module).
_run_active: bool = False


def notify_run_started() -> None:
    """Mark that a simulation run is now active.

    Call this at run-start (after the scenario factory has captured the
    current location) so that any subsequent set_site_location() call emits
    a warning rather than silently changing state under an active run.
    """
    global _run_active
    _run_active = True


def notify_run_ended() -> None:
    """Mark that the current simulation run has ended."""
    global _run_active
    _run_active = False


def get_site_location() -> SiteLocation:
    """Return the current site location.

    Raises SiteLocationNotConfigured if no location has been stored.
    Call set_site_location() (or restore from gridsignal_site.json via app.py)
    before the first run.
    """
    if _stored is None:
        raise SiteLocationNotConfigured(
            "No site location configured. "
            "Use PUT /api/location to set one before starting a run."
        )
    return _stored


def set_site_location(loc: SiteLocation) -> None:
    """Replace the process-level site location singleton.

    Safe to call at any time.  When called while a run is active, a WARNING is
    emitted because the change will not affect the current run (the scenario
    factory has already captured the location from the prior call).  The new
    location takes effect on the next run-start.

    GS-DES-CFG-001 §Phase-2: warn, do not raise.  Raising would break any
    UI flow that lets operators update location mid-session.
    """
    global _stored
    if _run_active:
        _log.warning(
            "set_site_location('%s') called while a run is active. "
            "The location change is stored but will not affect the current run — "
            "the scenario factory already captured the location at run-start. "
            "The new location takes effect on the next run.",
            loc.site_name,
        )
    _stored = loc


def get_site_location_or_default() -> SiteLocation:
    """Return the stored location, or San Diego if none has been stored.

    Only the opening-screen preview path uses this; the run-start path must
    call get_site_location() directly (returns 409 when not configured).
    """
    if _stored is not None:
        return _stored
    return _SAN_DIEGO_DEFAULT


def utc_offset_for_dt(tz_name: str, utc_dt: datetime.datetime) -> float:
    """Return the DST-aware UTC offset (hours) for *tz_name* at *utc_dt*.

    Uses stdlib zoneinfo (Python ≥ 3.9).  Falls back to 0.0 (UTC) when
    the timezone name is unknown or zoneinfo is unavailable, and logs a
    warning so the discrepancy is visible.
    """
    if not tz_name:
        return 0.0
    try:
        from zoneinfo import ZoneInfo
        aware = utc_dt.replace(tzinfo=datetime.timezone.utc).astimezone(ZoneInfo(tz_name))
        return aware.utcoffset().total_seconds() / 3600.0
    except Exception as exc:
        _log.warning(
            "site_config.utc_offset_for_dt: zoneinfo lookup failed for %r (%s) — using UTC",
            tz_name, exc,
        )
        return 0.0


# ---------------------------------------------------------------------------
# Built-in fallback / default — San Diego, CA
# Only geographic literals permitted in this file.
# ---------------------------------------------------------------------------

_SAN_DIEGO_DEFAULT = SiteLocation(
    site_name="San Diego, CA",
    latitude_deg=32.72,
    longitude_deg=-117.16,
    tz_name="America/Los_Angeles",
    source="default",
    climate_hint=(
        "Marine layer ('June Gloom') common before 10:00; clear afternoons "
        "near solar noon; occasional cloud transients; coastal moderate humidity."
    ),
    ambient_temp_base_c=14.0,
)
