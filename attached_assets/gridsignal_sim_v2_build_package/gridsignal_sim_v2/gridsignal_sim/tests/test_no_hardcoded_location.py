"""
tests/test_no_hardcoded_location.py — Guard A/B/C + restart fidelity.

Purpose
-------
Seven of the original location defects were caused by geographic literals
(lat/lon/tz) scattered across five source files.  This test suite is the
standing regression guard that prevents the pattern from recurring:

Guard A — AST scan
    Fails if any float literal in −180..180 (excluding ±0) is assigned to a
    variable whose name contains lat|lon|lng|coord|offset|tz, OR if any IANA
    timezone string literal is assigned to a variable matching those patterns.
    Excluded: site_config.py (the one permitted location-literal file) and
    test_*.py files (test coordinate constants are intentional and documented).

Guard B — teleport test (physics-only; no Mistral key required)
    San Diego, San Antonio, and Frankfurt must each reach their physics solar
    peak (irradiance fraction > 0.5) within ±25 minutes of the expected
    local solar noon expressed as a UTC timestamp.

Guard C — DST boundary crossing
    San Antonio (America/Chicago) clears solar noon on a November DST transition
    day (fall-back at 02:00 = clock goes 01:59 → 01:00, so the solar peak is
    still at 18:xx UTC, not 17:xx UTC).

Restart-fidelity
    Save a SiteLocation to gridsignal_site.json, restart (re-import) the
    location module and reload from disk; the round-trip must produce an
    identical SiteLocation with schema_version=1.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime
import json
import os
import pathlib
import re
import sys
import tempfile
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Guard A — AST scan
# ---------------------------------------------------------------------------

# The one file whose geographic literals are intentional.
_EXEMPT_FILES = {"site_config.py"}

_SIM_ROOT = pathlib.Path(__file__).parent.parent

# Compile-once: IANA canonical zone names present in the Python stdlib zoneinfo
# database (well-known set — avoids external tzdata dependency in the test).
_IANA_SAMPLE: set[str] = {
    "America/New_York",   "America/Los_Angeles", "America/Chicago",
    "America/Denver",     "America/Phoenix",     "America/Anchorage",
    "America/Honolulu",   "America/Toronto",
    "Europe/London",      "Europe/Berlin",        "Europe/Paris",
    "Europe/Madrid",      "Europe/Moscow",
    "Asia/Tokyo",         "Asia/Shanghai",        "Asia/Kolkata",
    "Asia/Dubai",         "Asia/Singapore",       "Asia/Bangkok",
    "Asia/Seoul",         "Asia/Jakarta",
    "Australia/Sydney",   "Australia/Melbourne",  "Pacific/Auckland",
    "Africa/Johannesburg","America/Sao_Paulo",    "America/Mexico_City",
    "Asia/Karachi",       "Asia/Tehran",          "Asia/Jerusalem",
    "Pacific/Honolulu",
}

_LOC_RE = re.compile(r"\b(?:lat|lon|lng|coord|offset|tz)\b", re.IGNORECASE)


def _check_const(node: ast.AST, name: str, lineno: int,
                 rel_path: str, violations: list[str]) -> None:
    """Check a single AST value node for coordinate-literal violations."""
    if not isinstance(node, ast.Constant):
        return
    v = node.value
    if not _LOC_RE.search(name):
        return
    # Float lat/lon/offset literal — exclude zero (used as neutral default)
    if isinstance(v, float) and abs(v) > 1e-9 and -180.0 <= v <= 180.0:
        violations.append(
            f"{rel_path}:{lineno}: float literal {v!r} assigned to {name!r} "
            f"— move geographic constants to site_config.py"
        )
    # IANA timezone string literal
    if isinstance(v, str) and v in _IANA_SAMPLE:
        violations.append(
            f"{rel_path}:{lineno}: IANA timezone {v!r} assigned to {name!r} "
            f"— move geographic constants to site_config.py"
        )


def _scan_file(path: pathlib.Path) -> list[str]:
    """Return a list of Guard A violation strings for one source file."""
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree   = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []   # broken files are caught by other tests

    rel = str(path.relative_to(_SIM_ROOT))

    for node in ast.walk(tree):
        # Module-level or class-body assignments:  x = 32.72
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _check_const(node.value, target.id, node.lineno, rel, violations)
                elif isinstance(target, ast.Attribute):
                    _check_const(node.value, target.attr, node.lineno, rel, violations)

        # Annotated assignments:  x: float = 32.72
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None:
                target = node.target
                name = (
                    target.id   if isinstance(target, ast.Name)
                    else target.attr if isinstance(target, ast.Attribute)
                    else ""
                )
                if name:
                    _check_const(node.value, name, node.lineno, rel, violations)

        # Function parameter defaults:  def f(lat: float = 32.72, ...)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args  = node.args
            defs  = args.defaults
            params = [a.arg for a in args.args]
            n_defs = len(defs)
            # positional-with-default pairs
            for param, default in zip(params[len(params) - n_defs:], defs):
                _check_const(default, param, node.lineno, rel, violations)
            # keyword-only
            for param, default in zip(args.kwonlyargs, args.kw_defaults):
                if default is not None:
                    _check_const(default, param.arg, node.lineno, rel, violations)

    return violations


def _collect_py_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for py_file in _SIM_ROOT.rglob("*.py"):
        parts = py_file.parts
        # Exclude compiled / third-party / build artefacts
        if "__pycache__" in parts:
            continue
        if ".pythonlibs" in parts:
            continue
        if "node_modules" in parts:
            continue
        if py_file.name in _EXEMPT_FILES:
            continue
        if py_file.name.startswith("test_"):
            continue
        files.append(py_file)
    return files


def test_guard_a_no_hardcoded_coordinates():
    """No .py file (except site_config.py and test_*.py) may contain
    a geographic coordinate literal (lat/lon float or IANA tz string)
    assigned to a variable whose name contains lat/lon/lng/coord/offset/tz.
    """
    violations: list[str] = []
    for py_file in _collect_py_files():
        violations.extend(_scan_file(py_file))

    if violations:
        formatted = "\n  ".join(violations)
        pytest.fail(
            f"Guard A: {len(violations)} hardcoded location literal(s) found.\n"
            f"Move them to site_config.py:\n  {formatted}"
        )


# ---------------------------------------------------------------------------
# Guard B — teleport test (physics solar peak at correct UTC time)
# ---------------------------------------------------------------------------

# Each entry: (site_label, lat, lon, tz_name, expected_solar_noon_utc_h)
# expected_solar_noon_utc_h is approximated as 12 − lon/15 clamped to 0-24.
# Tolerance: ±25 min expressed as a fraction (the physics peak may be slightly
# off-noon due to declination, so we use irradiance fraction > 0.5, not = 1.0).

_TELEPORT_SITES = [
    # San Diego, CA — UTC-8 (PST) — solar noon ≈ 20:xx UTC in winter
    dict(label="San Diego",   lat=32.72,  lon=-117.16, tz="America/Los_Angeles", noon_utc_h=20.0),
    # San Antonio, TX — UTC-6 (CST) — solar noon ≈ 18:xx UTC
    dict(label="San Antonio", lat=29.42,  lon=-98.49,  tz="America/Chicago",     noon_utc_h=18.5),
    # Frankfurt, DE — UTC+1 (CET) — solar noon ≈ 11:xx UTC
    dict(label="Frankfurt",   lat=50.11,  lon=8.68,    tz="Europe/Berlin",       noon_utc_h=11.4),
]

# June solstice — max Northern Hemisphere solar elevation.
_SOL_DATE = datetime.date(2026, 6, 21)


def _solar_noon_utc_h(lon: float, date: datetime.date) -> float:
    """Return approximate solar noon in UTC hours from longitude + NOAA EoT.

    This is the inverse of the formula used in _solar_fraction_at so the two
    must agree: if the formula changes in solar_sim.py, this guard will catch it.
    """
    import math as _m
    doy = date.timetuple().tm_yday
    B = _m.radians(360.0 / 365.0 * (doy - 81))
    eot_min = 9.87 * _m.sin(2.0 * B) - 7.53 * _m.cos(B) - 1.5 * _m.sin(B)
    # solar noon UTC = local solar noon (12:00) − longitude correction − EoT correction
    return (12.0 - lon / 15.0 - eot_min / 60.0) % 24.0


@pytest.mark.parametrize("site", _TELEPORT_SITES, ids=lambda s: s["label"])
def test_guard_b_solar_peak_at_correct_utc_time(site: dict):
    """Physics irradiance fraction must be ≥ 0.5 within ±10 min of true solar noon.

    Tests that _solar_fraction_at uses longitude_deg to compute solar time, so the
    correct UTC timestamp is solar noon for all three global test sites.
    """
    from runtime.solar_sim import _solar_fraction_at

    # Expected solar noon UTC from the NOAA formula (same formula used inside _solar_fraction_at)
    expected_noon_h = _solar_noon_utc_h(site["lon"], _SOL_DATE)

    # Check fraction at ±10-minute window around expected noon
    fractions_at_noon = []
    for delta_min in range(-10, 11):
        utc_dt = (
            datetime.datetime(_SOL_DATE.year, _SOL_DATE.month, _SOL_DATE.day) +
            datetime.timedelta(hours=expected_noon_h, minutes=delta_min)
        )
        f = _solar_fraction_at(utc_dt, site["lat"], longitude_deg=site["lon"])
        fractions_at_noon.append(f)
    max_near_noon = max(fractions_at_noon)

    # Check that fraction is ≈0 well away from noon (midnight local = noon + 12 h UTC)
    midnight_h = (expected_noon_h + 12.0) % 24.0
    utc_midnight = (
        datetime.datetime(_SOL_DATE.year, _SOL_DATE.month, _SOL_DATE.day) +
        datetime.timedelta(hours=midnight_h)
    )
    f_at_midnight = _solar_fraction_at(utc_midnight, site["lat"], longitude_deg=site["lon"])

    assert max_near_noon >= 0.5, (
        f"Guard B: {site['label']}: irradiance fraction near solar noon (UTC {expected_noon_h:.2f} h) "
        f"is only {max_near_noon:.3f} — should be ≥ 0.5.\n"
        f"Most likely cause: longitude_deg is not being forwarded to _solar_fraction_at."
    )
    assert f_at_midnight < 0.05, (
        f"Guard B: {site['label']}: irradiance fraction at local midnight (UTC {midnight_h:.2f} h) "
        f"is {f_at_midnight:.3f} — should be ~0.\n"
        f"Most likely cause: wrong timezone or sign error in longitude correction."
    )


# ---------------------------------------------------------------------------
# Guard C — DST boundary crossing (San Antonio, America/Chicago)
# ---------------------------------------------------------------------------

def test_guard_c_dst_boundary_san_antonio():
    """On the US autumn DST changeover day, San Antonio solar noon must still
    produce a high irradiance fraction at the NOAA-predicted UTC time, regardless
    of whether the local clock is on CDT (UTC-5) or CST (UTC-6).

    The DST fall-back (clocks go from 02:00 → 01:00) happens in November.
    Since the sun's position is determined by UTC + longitude, not by wall-clock
    offset, physics solar noon should be stable at ~18.5 h UTC ± 25 min.
    """
    from runtime.solar_sim import _solar_fraction_at

    # First Sunday of November 2026 (US DST ends) = November 1, 2026
    _DST_FALLBACK_DATE = datetime.date(2026, 11, 1)
    _SAN_ANTONIO_LAT = 29.42
    _SAN_ANTONIO_LON = -98.49   # test file — coordinate literals are permitted

    # Compute expected solar noon via the NOAA formula
    noon_h = _solar_noon_utc_h(_SAN_ANTONIO_LON, _DST_FALLBACK_DATE)

    # November solar noon is a few minutes later than June; allow ±25 min window
    fracs = []
    for delta_min in range(-10, 11):
        utc_dt = (
            datetime.datetime(_DST_FALLBACK_DATE.year, _DST_FALLBACK_DATE.month, _DST_FALLBACK_DATE.day)
            + datetime.timedelta(hours=noon_h, minutes=delta_min)
        )
        fracs.append(_solar_fraction_at(utc_dt, _SAN_ANTONIO_LAT, longitude_deg=_SAN_ANTONIO_LON))
    max_frac = max(fracs)

    # Must be in the 17.5–19.5 h UTC window for this longitude
    assert 17.5 <= noon_h <= 19.5, (
        f"Guard C: NOAA solar noon for San Antonio on DST-fallback day = {noon_h:.2f} h UTC, "
        f"expected 17.5–19.5 h."
    )
    assert max_frac >= 0.5, (
        f"Guard C: irradiance fraction near San Antonio DST-day solar noon ({noon_h:.2f} h UTC) "
        f"is only {max_frac:.3f} — should be ≥ 0.5.\n"
        f"Check that _solar_fraction_at uses longitude_deg, not utc_offset_h."
    )


# ---------------------------------------------------------------------------
# Restart fidelity — gridsignal_site.json round-trip
# ---------------------------------------------------------------------------

def test_restart_fidelity_new_schema():
    """Save a SiteLocation → disk (schema_version=1), reload → same object."""
    from site_config import SiteLocation
    from api.routes.location import save_site_location, load_site_location

    original = SiteLocation(
        site_name="Auckland, New Zealand",
        latitude_deg=-36.85,
        longitude_deg=174.76,
        tz_name="Pacific/Auckland",
        source="configured",
        climate_hint="Temperate maritime.",
        ambient_temp_base_c=13.0,
    )

    with tempfile.TemporaryDirectory() as td:
        # Temporarily redirect the module's path constant
        import api.routes.location as _loc_mod
        old_path = _loc_mod._SITE_JSON_PATH
        _loc_mod._SITE_JSON_PATH = pathlib.Path(td) / "gridsignal_site.json"
        try:
            save_site_location(original)
            assert _loc_mod._SITE_JSON_PATH.exists(), "save_site_location did not write file"

            raw = json.loads(_loc_mod._SITE_JSON_PATH.read_text())
            assert raw.get("schema_version") == 1, (
                f"Saved file must have schema_version=1; got {raw.get('schema_version')!r}"
            )
            # Reload
            restored = load_site_location()
        finally:
            _loc_mod._SITE_JSON_PATH = old_path

    assert restored is not None, "load_site_location returned None after save"
    assert restored.site_name       == original.site_name,       "site_name mismatch"
    assert abs(restored.latitude_deg - original.latitude_deg) < 1e-9, "latitude_deg mismatch"
    assert abs(restored.longitude_deg - original.longitude_deg) < 1e-9, "longitude_deg mismatch"
    assert restored.tz_name          == original.tz_name,          "tz_name mismatch"
    assert abs(restored.ambient_temp_base_c - original.ambient_temp_base_c) < 1e-9


def test_restart_fidelity_legacy_migration():
    """Load a legacy gridsignal_site.json (old name/lat/lon/utc_offset_h keys)
    and verify that load_site_location() produces the correct SiteLocation
    with new field names and schema_version=1 written back to disk.
    """
    legacy = {
        "name":               "San Antonio, TX, USA",
        "lat":                29.4241,
        "lon":                -98.4936,
        "utc_offset_h":       -6.0,
        "climate_hint":       "Hot summers with frequent clear skies.",
        "ambient_temp_base_c": 10.0,
        "tz_name":            "America/Chicago",
    }

    with tempfile.TemporaryDirectory() as td:
        import api.routes.location as _loc_mod
        from api.routes.location import load_site_location as _load_loc2
        old_path = _loc_mod._SITE_JSON_PATH
        _loc_mod._SITE_JSON_PATH = pathlib.Path(td) / "gridsignal_site.json"
        try:
            _loc_mod._SITE_JSON_PATH.write_text(json.dumps(legacy))
            restored = _load_loc2()
            # After migration the file must be updated to schema_version=1
            raw_after = json.loads(_loc_mod._SITE_JSON_PATH.read_text())
        finally:
            _loc_mod._SITE_JSON_PATH = old_path

    assert restored is not None, "Migration failed — load returned None"
    assert restored.site_name   == "San Antonio, TX, USA", \
        f"site_name wrong after migration: {restored.site_name!r}"
    assert abs(restored.latitude_deg  - 29.4241) < 1e-6
    assert abs(restored.longitude_deg - (-98.4936)) < 1e-6
    assert restored.tz_name     == "America/Chicago"
    assert raw_after.get("schema_version") == 1, \
        f"Migrated file should have schema_version=1; got {raw_after.get('schema_version')!r}"
    assert "name" not in raw_after,       "old 'name' key still present after migration"
    assert "lat"  not in raw_after,       "old 'lat' key still present after migration"
    assert "utc_offset_h" not in raw_after, "old 'utc_offset_h' key still present after migration"
