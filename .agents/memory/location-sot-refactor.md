---
name: Location Single-Source-of-Truth Refactor
description: Design decisions and traps from the 7-phase location refactor that eliminated p_renewable_mw=0.0 for non-US sites.
---

## Rule
`site_config.py` is the ONLY file permitted to contain geographic literals (lat/lon floats, IANA timezone strings). Every other module must import `SiteLocation` from there and must never hard-code coordinates or timezone names.

**Why:** Five separate files each had their own `_LAT_DEG = 32.72` / `_UTC_OFFSET_H = -8.0` / `tz_name = "America/Los_Angeles"` defaults. A user switching to Auckland, Tokyo, or Frankfurt got `p_renewable_mw: 0.0` because solar time was still computed for San Diego. Guard A (test_no_hardcoded_location.py) enforces this via AST scan.

**How to apply:** When any new module needs site coordinates, import from `site_config`:
```python
from site_config import get_site_location, SiteLocation, utc_offset_for_dt
```
Never add a `lat: float = 32.72` default to a function signature — Guard A will catch it.

---

## TRAP 1 — `_solar_fraction_at`: longitude vs. utc_offset_h
`_solar_fraction_at(utc_dt, lat, *, longitude_deg=None, utc_offset_h=None)` now requires at least one of the two kwargs. The **longitude_deg path** uses NOAA equation of time (true solar time, immune to DST). The **utc_offset_h path** is the legacy alias kept only for TZ regression tests that document the pre-fix broken behaviour (utc_offset_h=0.0 = wrong).

When adding a new call: always use `longitude_deg=site.longitude_deg`, never `utc_offset_h=`.

---

## TRAP 2 — `generate_solar_forecast` fallback to process-level singleton
When called without `site=` (e.g. bare test helpers), `generate_solar_forecast` falls back to `get_site_location_or_default()`. The **singleton is contaminated** by API test runs that load `gridsignal_site.json` via the lifespan → `set_site_location()`. Temperature range tests (T4) MUST pass `site=_SAN_DIEGO` explicitly to be isolation-safe.

---

## TRAP 3 — Guard A false positive: word boundary
Guard A regex must use `\b` word boundaries: `r'\b(?:lat|lon|lng|coord|offset|tz)\b'`. Without boundaries, "ESCALATION" matches "lat" (E-S-C-A-L-A-T → contains "LAT"). Also exclude `.pythonlibs/` from the scan (timezonefinder has `MAX_LAT_VAL = 90.0` etc.).

---

## TRAP 4 — TickResult + RunContext field defaults
Both `RunContext` (run_manager.py) and `TickResult` (core/models.py) had hardcoded `site_lat: float = 32.72` which Guard A flags. Changed to `field(default_factory=float)` (RunContext) and `site_lat: float = 0.0` (TickResult). The `0.0` default is fine because `abs(0.0) ≤ 1e-9` → Guard A's zero-exclusion rule skips it.

---

## TRAP 5 — Legacy JSON migration
`gridsignal_site.json` stores `schema_version: 1` records with `site_name/latitude_deg/longitude_deg/tz_name`. The previous schema used `name/lat/lon/utc_offset_h`. Migration lives in `load_site_location()` in `api/routes/location.py`. If `tz_name` is absent and `timezonefinder` is unavailable, the record is quarantined (`.quarantine.<ts>.json`) not silently zeroed.

---

## Key file list
- `site_config.py` — defines SiteLocation, `get_site_location()`, `set_site_location()`, `get_site_location_or_default()`, `utc_offset_for_dt()`, `_SAN_DIEGO_DEFAULT`, `_KNOWN_LOCATIONS` (all geographic literals live here).
- `api/routes/location.py` — imports SiteLocation from site_config; `load_site_location()` / `save_site_location()` with migration; re-exports SiteLocation for backward compat.
- `runtime/solar_sim.py` — `_solar_fraction_at(longitude_deg=)` + `generate_solar_forecast(site=)`.
- `tests/test_no_hardcoded_location.py` — Guard A/B/C + restart fidelity.
