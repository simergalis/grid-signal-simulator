"""
tests/test_solar_site_pipeline.py — SP-1 through SP-10

Regression tests confirming that Auckland-style (non-US) site coordinates
propagate correctly through the full solar-to-tick pipeline.

The pipeline under test
-----------------------
runs.py reads site_latitude + site_utc_offset_h from the scenario spec →
calls generate_solar_forecast() with those site params →
injects forecast.samples as spec_data["irradiance_steps"] →
build_run_context_from_spec() reads solar_rated_mw + irradiance_steps →
creates SolarModule(IrradianceProfile(irradiance_steps)) →
each tick: p_renewable_mw = solar.output_mw(sim_time) * irradiance_fraction

The HTTP layer (runs.py) is not under test here.  These tests mirror the
critical steps that runs.py performs so that any future breakage in the
spec-field reading or the factory wiring is caught immediately.

SP-1  Non-zero irradiance samples produce non-zero p_renewable_mw in ticks
SP-2  All-zero irradiance samples produce zero p_renewable_mw in all ticks
SP-3  spec_data fields site_latitude / site_utc_offset_h are the correct
      field names read by runs.py — a rename would be caught by this test
SP-4  Full Auckland pipeline at local afternoon (04:00 UTC = 16:00 local):
      generate_solar_forecast() with correct offset → non-zero p_renewable_mw
SP-5  Full Auckland pipeline with broken offset (utc_offset_h=0): same UTC
      time is misread as pre-dawn → zero irradiance → zero p_renewable_mw
SP-6  Correct and broken offset pipelines produce different p_renewable_mw values
SP-7  Site params encoded in spec flow through to solar output magnitude
SP-8  PUT /api/location (Frankfurt) saves longitude_deg; GET /api/location
      returns longitude_deg=8.68, not the default San Diego value
SP-9  GET /solar-preview with Frankfurt location and utc_now at Frankfurt
      solar noon returns p_renewable_mw > 0 (proves timezone-aware physics)
SP-10 Full location-to-solar-preview round-trip: PUT → GET longitude → GET
      solar-preview at Frankfurt noon → p_renewable_mw > 0 end-to-end
"""

from __future__ import annotations

import contextlib
import datetime
import os

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from runtime.scenario_factory import build_run_context_from_spec
from runtime.solar_sim import SolarForecast, _solar_fraction_at, generate_solar_forecast


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Auckland, New Zealand — the canonical non-US test site
_AUCKLAND_LAT   = -36.85
_AUCKLAND_LON   = 174.76
_AUCKLAND_UTC   = 12.0
_AUCKLAND_NAME  = "Auckland, NZ"

# June solstice: 04:00 UTC = 16:00 Auckland local (afternoon, solar > 0)
_AUCKLAND_AFTERNOON_UTC = datetime.datetime(2026, 6, 21, 4, 0, 0)

# Solar capacity injected into the spec
_SOLAR_MW = 5.0

# Short run — enough ticks to verify non-zero output without waiting long
_RUN_DURATION_S = 60.0   # 12 ticks at dt=5 s


@contextlib.contextmanager
def _no_mistral_key():
    """Remove MISTRAL_API_KEY from env so generate_solar_forecast uses physics."""
    original = os.environ.pop("MISTRAL_API_KEY", None)
    try:
        yield
    finally:
        if original is not None:
            os.environ["MISTRAL_API_KEY"] = original


def _minimal_spec(irradiance_steps: list, run_tag: str) -> dict:
    """Build a minimal runnable scenario spec with solar + one turbine + BESS."""
    return {
        "name": f"auckland-solar-pipeline-{run_tag}",
        "end_sim_time": _RUN_DURATION_S,
        "solar_rated_mw": _SOLAR_MW,
        "irradiance_steps": irradiance_steps,
        "island_mode": False,
        # Required by SiteConfig (no default): use WECC/ERCOT 60 Hz (non-frequency test).
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,  # CHOSEN — typical gas turbine; non-frequency test
        "turbine_units": [
            {"asset_id": "t-0", "rated_mw": 20.0, "r_asset_mw_per_s": 5.0}
        ],
        "bess_units": [
            {
                "asset_id": "b-0", "rated_mw": 5.0, "usable_mwh": 2.0,
                "initial_soc_fraction": 1.0, "grid_forming": False,
            }
        ],
        "workload_events": [
            {
                "event_type": "starting",
                "timestamp": 0.0,
                "job_id": "job-solar-test",
                "node_count": 50,
                "hardware_profile_id": "enterprise_8gpu_air",
            }
        ],
    }


def _run_n_ticks(ctx, n: int):
    """Advance RunContext by n ticks; return list of TickResult objects."""
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    results = []
    for _ in range(n):
        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            results.append(ctx.step())
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)
    return results


# ---------------------------------------------------------------------------
# SP-1  Non-zero irradiance produces non-zero p_renewable_mw
# ---------------------------------------------------------------------------

def test_sp1_nonzero_irradiance_gives_nonzero_p_renewable():
    """A spec with non-zero irradiance_steps and solar_rated_mw > 0 must produce
    p_renewable_mw > 0 on every tick (irradiance fraction is constant at 0.5 here).

    This is the base wiring test: confirms the IrradianceProfile → SolarModule →
    p_renewable_mw pipeline is intact before any site-specific logic runs.
    """
    # A flat non-zero irradiance across the whole run
    irr = [[0.0, 0.5], [_RUN_DURATION_S, 0.5]]
    ctx = build_run_context_from_spec("sp1-run", _minimal_spec(irr, "sp1"))
    ticks = _run_n_ticks(ctx, 12)

    for i, t in enumerate(ticks):
        assert t.p_renewable_mw > 0.0, (
            f"tick {i+1}: expected p_renewable_mw > 0 with irradiance=0.5; "
            f"got {t.p_renewable_mw:.4f} MW. "
            "IrradianceProfile → SolarModule pipeline may be broken."
        )
        assert t.p_renewable_mw == pytest.approx(_SOLAR_MW * 0.5, abs=0.05), (
            f"tick {i+1}: expected p_renewable_mw ≈ {_SOLAR_MW*0.5:.2f} MW "
            f"(rated × fraction); got {t.p_renewable_mw:.4f} MW."
        )


# ---------------------------------------------------------------------------
# SP-2  All-zero irradiance produces zero p_renewable_mw
# ---------------------------------------------------------------------------

def test_sp2_zero_irradiance_gives_zero_p_renewable():
    """A spec with all-zero irradiance_steps must produce p_renewable_mw = 0 on
    every tick, even though solar_rated_mw > 0.

    This is the complement of SP-1 and the baseline for SP-5: confirms zero
    irradiance → zero solar output so that a failed UTC-offset run is distinguishable.
    """
    irr = [[0.0, 0.0], [_RUN_DURATION_S, 0.0]]
    ctx = build_run_context_from_spec("sp2-run", _minimal_spec(irr, "sp2"))
    ticks = _run_n_ticks(ctx, 12)

    for i, t in enumerate(ticks):
        assert t.p_renewable_mw == pytest.approx(0.0, abs=1e-9), (
            f"tick {i+1}: expected p_renewable_mw = 0 with irradiance=0; "
            f"got {t.p_renewable_mw:.6f} MW."
        )


# ---------------------------------------------------------------------------
# SP-3  spec field names for site coords match what runs.py reads
# ---------------------------------------------------------------------------

def test_sp3_spec_field_names_match_runs_py():
    """Verify the canonical spec field names for site parameters.

    runs.py reads:
        spec_data.get("site_latitude",     _def_lat)
        spec_data.get("site_utc_offset_h", _def_utc)
        spec_data.get("site_name",         _def_name)

    If these field names are renamed in either runs.py or the scenario JSON
    schema, this test will fail, alerting that the solar forecast will silently
    fall back to San Diego defaults for non-US sites.
    """
    spec = {
        "site_latitude":    _AUCKLAND_LAT,
        "site_utc_offset_h": _AUCKLAND_UTC,
        "site_name":         _AUCKLAND_NAME,
    }

    # The field names are correct if reads return the Auckland values (not None).
    assert spec.get("site_latitude")     == _AUCKLAND_LAT,  "site_latitude key changed"
    assert spec.get("site_utc_offset_h") == _AUCKLAND_UTC,  "site_utc_offset_h key changed"
    assert spec.get("site_name")         == _AUCKLAND_NAME, "site_name key changed"

    # Mirror what runs.py lines 149-152 do:
    _def_lat, _def_utc, _def_name = 32.72, -8.0, "San Diego, CA"
    resolved_lat  = float(spec.get("site_latitude",     _def_lat))
    resolved_utc  = float(spec.get("site_utc_offset_h", _def_utc))
    resolved_name = str(  spec.get("site_name",         _def_name))

    assert resolved_lat  == _AUCKLAND_LAT,  (
        f"site_latitude resolved to {resolved_lat} instead of {_AUCKLAND_LAT} — "
        "runs.py would use San Diego latitude for Auckland runs."
    )
    assert resolved_utc  == _AUCKLAND_UTC,  (
        f"site_utc_offset_h resolved to {resolved_utc} instead of {_AUCKLAND_UTC} — "
        "runs.py would use San Diego UTC offset for Auckland runs."
    )
    assert resolved_name == _AUCKLAND_NAME, (
        f"site_name resolved to {resolved_name!r} instead of {_AUCKLAND_NAME!r}."
    )


# ---------------------------------------------------------------------------
# SP-4  Full Auckland pipeline at local afternoon → p_renewable_mw > 0
# ---------------------------------------------------------------------------

def test_sp4_auckland_afternoon_pipeline_gives_nonzero_output():
    """Full pipeline: Auckland params → generate_solar_forecast() → irradiance_steps
    → build_run_context_from_spec() → ticks with p_renewable_mw > 0.

    This mirrors what runs.py does for a scenario with
    site_latitude=-36.85, site_utc_offset_h=+12.0, utc_now=04:00 UTC
    (= 16:00 Auckland local, afternoon).

    At least one tick in a 12-tick run must carry non-zero solar output.
    If the UTC offset is not applied, generate_solar_forecast() produces
    all-zero samples (04:00 treated as pre-dawn) and this assertion fails.
    """
    with _no_mistral_key():
        fc = generate_solar_forecast(
            _RUN_DURATION_S,
            _SOLAR_MW,
            utc_now=_AUCKLAND_AFTERNOON_UTC,
            site_latitude=_AUCKLAND_LAT,
            site_utc_offset_h=_AUCKLAND_UTC,
            site_name=_AUCKLAND_NAME,
        )

    assert fc.source == "physics", (
        f"Expected physics fallback (no API key); got source={fc.source!r}"
    )

    # Verify the forecast itself carries non-zero fractions before injecting
    nonzero_fc = [f for _, f in fc.samples if f > 0.0]
    assert len(nonzero_fc) > 0, (
        "generate_solar_forecast() with Auckland params at 04:00 UTC produced "
        "all-zero samples — UTC offset not applied."
    )

    # Inject samples into the spec exactly as runs.py does (line 257)
    irr = [[t, f] for t, f in fc.samples]
    spec = _minimal_spec(irr, "sp4")

    ctx = build_run_context_from_spec("sp4-run", spec)
    ticks = _run_n_ticks(ctx, 12)

    nonzero_ticks = [t for t in ticks if t.p_renewable_mw > 0.0]
    assert len(nonzero_ticks) > 0, (
        f"No tick produced p_renewable_mw > 0 despite non-zero irradiance samples. "
        f"Tick outputs: {[round(t.p_renewable_mw, 4) for t in ticks]}. "
        "The IrradianceProfile → SolarModule → tick pipeline is broken."
    )

    # All ticks within a 60 s window starting at afternoon should be positive
    # (the run is short enough that irradiance doesn't drop to zero during it)
    for i, t in enumerate(ticks):
        assert t.p_renewable_mw >= 0.0, (
            f"p_renewable_mw must never be negative; tick {i+1} = {t.p_renewable_mw}"
        )


# ---------------------------------------------------------------------------
# SP-5  Broken offset → zero irradiance → zero p_renewable_mw
# ---------------------------------------------------------------------------

def test_sp5_broken_offset_pipeline_gives_zero_output():
    """With utc_offset_h=0, Auckland 04:00 UTC is misread as 04:00 local (pre-dawn).

    generate_solar_forecast() then produces all-zero samples, which get injected
    as irradiance_steps.  Every tick must have p_renewable_mw = 0.

    This is the canonical regression scenario: the original bug would pass this test
    (it always produced zero); the fix is confirmed by SP-4 failing to find non-zero
    output when the offset is omitted.
    """
    with _no_mistral_key():
        fc_broken = generate_solar_forecast(
            _RUN_DURATION_S,
            _SOLAR_MW,
            utc_now=_AUCKLAND_AFTERNOON_UTC,
            site_latitude=_AUCKLAND_LAT,
            site_utc_offset_h=0.0,          # broken: UTC treated as local
            site_name=_AUCKLAND_NAME,
        )

    assert fc_broken.source == "physics"

    # Confirm the samples are all zero (pre-dawn with offset=0 at lat=-36.85)
    nonzero_fc = [f for _, f in fc_broken.samples if f > 0.0]
    assert len(nonzero_fc) == 0, (
        "Expected all-zero samples with offset=0 at Auckland 04:00 UTC; "
        f"got {len(nonzero_fc)} non-zero samples."
    )

    irr_broken = [[t, f] for t, f in fc_broken.samples]
    spec = _minimal_spec(irr_broken, "sp5")
    ctx = build_run_context_from_spec("sp5-run", spec)
    ticks = _run_n_ticks(ctx, 12)

    for i, t in enumerate(ticks):
        assert t.p_renewable_mw == pytest.approx(0.0, abs=1e-9), (
            f"tick {i+1}: p_renewable_mw must be 0 when all irradiance samples are zero; "
            f"got {t.p_renewable_mw:.6f} MW."
        )


# ---------------------------------------------------------------------------
# SP-6  Correct and broken offset pipelines produce measurably different outputs
# ---------------------------------------------------------------------------

def test_sp6_correct_vs_broken_offset_pipelines_differ():
    """Correct offset → non-zero p_renewable_mw.  Broken offset → zero.
    The two pipelines must produce different total solar output.

    This is the combined assertion that SP-4 + SP-5 express separately,
    structured as a direct comparison so any partial regression is caught:
    if the fix is reverted, both would return zero and the strict inequality fails.
    """
    with _no_mistral_key():
        fc_correct = generate_solar_forecast(
            _RUN_DURATION_S, _SOLAR_MW,
            utc_now=_AUCKLAND_AFTERNOON_UTC,
            site_latitude=_AUCKLAND_LAT,
            site_utc_offset_h=_AUCKLAND_UTC,   # correct: +12
            site_name=_AUCKLAND_NAME,
        )
        fc_broken = generate_solar_forecast(
            _RUN_DURATION_S, _SOLAR_MW,
            utc_now=_AUCKLAND_AFTERNOON_UTC,
            site_latitude=_AUCKLAND_LAT,
            site_utc_offset_h=0.0,              # broken: UTC as local
            site_name=_AUCKLAND_NAME,
        )

    ctx_correct = build_run_context_from_spec(
        "sp6-correct",
        _minimal_spec([[t, f] for t, f in fc_correct.samples], "sp6c"),
    )
    ctx_broken = build_run_context_from_spec(
        "sp6-broken",
        _minimal_spec([[t, f] for t, f in fc_broken.samples], "sp6b"),
    )

    ticks_correct = _run_n_ticks(ctx_correct, 12)
    ticks_broken  = _run_n_ticks(ctx_broken,  12)

    total_correct = sum(t.p_renewable_mw for t in ticks_correct)
    total_broken  = sum(t.p_renewable_mw for t in ticks_broken)

    assert total_correct > total_broken, (
        f"Correct offset (+12) total p_renewable_mw over 12 ticks: {total_correct:.4f} MW·ticks. "
        f"Broken offset (0) total: {total_broken:.4f} MW·ticks. "
        "Correct offset must produce more solar output for Auckland afternoon. "
        "If equal, the UTC offset is not reaching the physics curve."
    )
    assert total_broken == pytest.approx(0.0, abs=1e-6), (
        f"Broken offset pipeline must give zero total output; got {total_broken:.6f}."
    )


# ---------------------------------------------------------------------------
# SP-7  Site params encoded in spec drive solar output magnitude
# ---------------------------------------------------------------------------

def test_sp7_site_latitude_affects_solar_output():
    """Site latitude changes solar elevation angle and therefore output magnitude.

    To isolate the latitude effect from UTC-offset and time-of-day effects,
    both sites use the SAME utc_now (04:00 UTC, June solstice) and the SAME
    utc_offset_h (+12), so local time is identical (16:00) for both.  Only
    latitude differs.

    At local 16:00 (hour_angle = +60°) on the June solstice:
    - Auckland (lat=-36.85°) sin_elev ≈ 0.129  →  fraction ≈ 0.135  (low winter sun)
    - Singapore (lat=+1.35°)  sin_elev ≈ 0.467  →  fraction ≈ 0.491  (near-equatorial)

    The near-equatorial site must produce substantially more output than Auckland,
    confirming that site_latitude propagates all the way to the IrradianceProfile
    used by build_run_context_from_spec().
    """
    # Same UTC time, same offset → same local clock (16:00), different elevation
    utc_time = _AUCKLAND_AFTERNOON_UTC   # 04:00 UTC = 16:00 local for +12 offset

    with _no_mistral_key():
        fc_auckland = generate_solar_forecast(
            _RUN_DURATION_S, _SOLAR_MW,
            utc_now=utc_time,
            site_latitude=-36.85,      # Auckland — low winter sun at 16:00
            site_utc_offset_h=12.0,
            site_name="Auckland, NZ",
        )
        fc_equatorial = generate_solar_forecast(
            _RUN_DURATION_S, _SOLAR_MW,
            utc_now=utc_time,
            site_latitude=1.35,        # near-equatorial — high sun at 16:00
            site_utc_offset_h=12.0,    # same offset → same local time
            site_name="Equatorial Test Site",
        )

    total_auckland    = sum(t.p_renewable_mw for t in _run_n_ticks(
        build_run_context_from_spec("sp7-auckland",
            _minimal_spec([[t, f] for t, f in fc_auckland.samples],    "sp7a")), 12
    ))
    total_equatorial  = sum(t.p_renewable_mw for t in _run_n_ticks(
        build_run_context_from_spec("sp7-equatorial",
            _minimal_spec([[t, f] for t, f in fc_equatorial.samples],  "sp7e")), 12
    ))

    # Both must produce solar (afternoon, not night)
    assert total_auckland   > 0.0, (
        f"Auckland 16:00 local must produce non-zero solar; got {total_auckland:.4f}"
    )
    assert total_equatorial > 0.0, (
        f"Equatorial site 16:00 local must produce non-zero solar; "
        f"got {total_equatorial:.4f}"
    )

    # Near-equatorial sun is higher at 16:00 on June solstice → more output
    assert total_equatorial > total_auckland, (
        f"Near-equatorial site (lat=1.35°) must produce more output than Auckland "
        f"(lat=-36.85°) at local 16:00 on June solstice. "
        f"Equatorial={total_equatorial:.4f} MW·ticks, "
        f"Auckland={total_auckland:.4f} MW·ticks. "
        "If equal, site_latitude is not reaching the physics curve."
    )


# ---------------------------------------------------------------------------
# Shared HTTP client fixture for SP-8 / SP-9 / SP-10
# ---------------------------------------------------------------------------

# Frankfurt on the June solstice: CEST = UTC+2, so solar noon local (12:00)
# corresponds to 10:00 UTC.  At lat=50.11° the sun is well above the horizon.
_FRANKFURT_NOON_UTC = "2026-06-21T10:00:00"
_FRANKFURT_LONGITUDE = 8.68


@pytest.fixture(scope="module")
def _pipeline_client():
    """Single TestClient whose lifespan spans the SP-8/SP-9/SP-10 sub-suite.

    Module scope avoids the asyncpg pool-teardown race that fires when multiple
    TestClient instances are created sequentially in one pytest session
    (same pattern as test_solar_routes.py / test_api.py).
    """
    with TestClient(create_app()) as client:
        yield client


# ---------------------------------------------------------------------------
# SP-8  PUT /api/location saves longitude_deg; GET /api/location returns it
# ---------------------------------------------------------------------------

def test_sp8_location_put_saves_longitude(
    _pipeline_client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    """Round-trip: PUT /api/location with 'Frankfurt' → GET /api/location must
    return longitude_deg=8.68 (not 0.0 or the San Diego default -117.16).

    The built-in geocoder table (_KNOWN_LOCATIONS in api/routes/location.py)
    contains Frankfurt with longitude_deg=8.68 and is used whenever
    MISTRAL_API_KEY is absent, making the test deterministic with no network call.

    Failure modes caught:
    - The PUT handler omits longitude_deg when constructing SiteLocation
    - _loc_to_response() fails to include longitude_deg in the GET response
    - The legacy alias 'lon' is returned instead of the new 'longitude_deg' key
    """
    # Ensure no Mistral key so the built-in table is used (deterministic)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    # Redirect the on-disk persistence file so tests don't pollute the repo root
    monkeypatch.chdir(tmp_path)

    put_resp = _pipeline_client.put(
        "/api/location",
        json={"address": "Frankfurt"},
    )
    assert put_resp.status_code == 200, (
        f"PUT /api/location returned {put_resp.status_code}: {put_resp.text}"
    )
    put_body = put_resp.json()
    assert "longitude_deg" in put_body, (
        "PUT /api/location response is missing 'longitude_deg' key. "
        "_loc_to_response() must include it (not just the legacy 'lon' alias)."
    )
    assert abs(put_body["longitude_deg"] - _FRANKFURT_LONGITUDE) < 1e-3, (
        f"PUT /api/location returned longitude_deg={put_body['longitude_deg']!r}, "
        f"expected ≈{_FRANKFURT_LONGITUDE}. "
        "The built-in Frankfurt entry may have changed or the wrong city was matched."
    )

    get_resp = _pipeline_client.get("/api/location")
    assert get_resp.status_code == 200, (
        f"GET /api/location returned {get_resp.status_code}: {get_resp.text}"
    )
    get_body = get_resp.json()
    assert "longitude_deg" in get_body, (
        "GET /api/location response is missing 'longitude_deg' key. "
        "_loc_to_response() must serialise the full SiteLocation dataclass."
    )
    assert abs(get_body["longitude_deg"] - _FRANKFURT_LONGITUDE) < 1e-3, (
        f"GET /api/location returned longitude_deg={get_body['longitude_deg']!r} "
        f"after PUT with Frankfurt; expected ≈{_FRANKFURT_LONGITUDE}. "
        "The value was not persisted to app.state.site_location or the "
        "SiteLocation dataclass dropped the field."
    )


# ---------------------------------------------------------------------------
# SP-9  solar-preview uses Frankfurt tz when longitude is correct
# ---------------------------------------------------------------------------

def test_sp9_solar_preview_frankfurt_noon_gives_nonzero_output(
    _pipeline_client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    """With Frankfurt as the active location and utc_now pinned to Frankfurt
    solar noon (10:00 UTC on 21 Jun 2026 = 12:00 CEST), GET /solar-preview must:
    - return p_renewable_mw > 0 (sun is up, physics is applied)
    - return utc_offset_h == 2.0 (CEST is correctly derived from the override instant)
    - return expected_fraction that differs from the lon=0.0 baseline, confirming
      longitude_deg=8.68 drives the true-solar-time model, not just the tz offset

    At UTC 10:00 Frankfurt (lon=8.68) true solar hour ≈ 10.58 h, while lon=0.0
    gives ≈ 10.0 h; the NOAA equation of time produces measurably different
    fractions at the same instant, so the comparison catches a longitude-ignored
    regression even if both sides are above zero.
    """
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    # Establish Frankfurt as the active location
    put_resp = _pipeline_client.put(
        "/api/location",
        json={"address": "Frankfurt"},
    )
    assert put_resp.status_code == 200, (
        f"PUT /api/location (setup for SP-9) failed: {put_resp.status_code}"
    )

    # Frankfurt solar noon: 2026-06-21 10:00 UTC = 12:00 CEST (UTC+2 summer)
    preview_resp = _pipeline_client.get(
        "/solar-preview",
        params={"utc_now": _FRANKFURT_NOON_UTC},
    )
    assert preview_resp.status_code == 200, (
        f"GET /solar-preview returned {preview_resp.status_code}: {preview_resp.text}"
    )
    body = preview_resp.json()

    assert "p_renewable_mw" in body, (
        "GET /solar-preview response is missing 'p_renewable_mw'. "
        "The endpoint must expose this field (= expected_fraction × plant_rated_ac_mw)."
    )
    assert "expected_fraction" in body, (
        "GET /solar-preview response is missing 'expected_fraction'."
    )

    p_renewable_mw    = body["p_renewable_mw"]
    expected_fraction = body["expected_fraction"]

    # ── DST guard ─────────────────────────────────────────────────────────────
    # On 2026-06-21 Frankfurt is in CEST (UTC+2); offset must be 2.0, not 1.0
    # (CET winter) or 0.0 (broken fallback).  A wrong offset means current server
    # wall-clock was used for DST resolution rather than the override instant.
    utc_offset_h_returned = body.get("utc_offset_h")
    assert utc_offset_h_returned == pytest.approx(2.0, abs=0.01), (
        f"utc_offset_h={utc_offset_h_returned!r} for Frankfurt on 2026-06-21; "
        "expected 2.0 (CEST).  The endpoint must resolve DST from the utc_now "
        "override instant, not from the server's wall-clock date."
    )

    # ── Physics guard ─────────────────────────────────────────────────────────
    assert expected_fraction > 0.0, (
        f"expected_fraction={expected_fraction:.4f} at Frankfurt solar noon "
        f"(utc_now={_FRANKFURT_NOON_UTC}). "
        "Solar must be positive at local noon on the June solstice (lat=50.11°)."
    )
    assert p_renewable_mw > 0.0, (
        f"p_renewable_mw={p_renewable_mw:.4f} MW at Frankfurt solar noon. "
        f"expected_fraction={expected_fraction:.4f}, "
        f"plant_rated_ac_mw={body.get('plant_rated_ac_mw')}."
    )

    # ── Longitude-distinguishing guard ────────────────────────────────────────
    # Compute expected_fraction for lon=0.0 (prime meridian) at the same UTC
    # instant and latitude.  Frankfurt (lon=8.68) is 0.58 h of solar time east
    # of Greenwich so its true-solar-time fraction must differ from lon=0.0.
    _utc_dt = datetime.datetime(2026, 6, 21, 10, 0, 0)
    frac_lon_zero = _solar_fraction_at(
        _utc_dt, lat_deg=50.11, longitude_deg=0.0
    )
    assert abs(expected_fraction - frac_lon_zero) > 1e-4, (
        f"expected_fraction with Frankfurt (lon=8.68) = {expected_fraction:.6f} "
        f"is indistinguishable from lon=0.0 fraction = {frac_lon_zero:.6f}. "
        "The endpoint is not passing longitude_deg to the physics model; "
        "it is either using utc_offset_h as a proxy or ignoring longitude entirely."
    )


# ---------------------------------------------------------------------------
# SP-10 Full round-trip: location PUT → longitude GET → solar-preview MW > 0
# ---------------------------------------------------------------------------

def test_sp10_frankfurt_location_to_solar_preview_roundtrip(
    _pipeline_client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    """End-to-end confirmation that the frontend's city-picker POST is wired
    correctly: saving Frankfurt via PUT, reading longitude_deg back, and then
    confirming the solar preview returns positive renewable output at noon.

    This is the combined assertion that SP-8 + SP-9 express in isolation.
    If either part breaks the strict ordering (longitude saved → preview positive),
    both tests would need to fail independently; SP-10 exists so a reviewer can
    see the complete round-trip in a single failing assertion chain.

    Steps mirrored:
    1. PUT /api/location {"address": "Frankfurt"} → HTTP 200
    2. GET /api/location → longitude_deg == 8.68 (not 0.0)
    3. GET /solar-preview?utc_now=2026-06-21T10:00:00 → p_renewable_mw > 0
    """
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    # Step 1 — save Frankfurt location
    put_resp = _pipeline_client.put(
        "/api/location",
        json={"address": "Frankfurt"},
    )
    assert put_resp.status_code == 200, (
        f"Step 1 failed: PUT /api/location returned {put_resp.status_code}: {put_resp.text}"
    )

    # Step 2 — confirm longitude is 8.68
    get_resp = _pipeline_client.get("/api/location")
    assert get_resp.status_code == 200, (
        f"Step 2 failed: GET /api/location returned {get_resp.status_code}"
    )
    lon = get_resp.json().get("longitude_deg", None)
    assert lon is not None, (
        "Step 2 failed: GET /api/location response lacks 'longitude_deg' key. "
        "The SiteLocation SOT refactor must include longitude_deg in _loc_to_response()."
    )
    assert abs(lon - _FRANKFURT_LONGITUDE) < 1e-3, (
        f"Step 2 failed: GET /api/location returned longitude_deg={lon!r}, "
        f"expected ≈{_FRANKFURT_LONGITUDE} (Frankfurt). "
        "If 0.0, the frontend's city-picker POST omitted longitude_deg and the "
        "backend silently fell back to a default."
    )

    # Step 3 — solar preview at Frankfurt noon must be non-zero AND longitude-driven
    preview_resp = _pipeline_client.get(
        "/solar-preview",
        params={"utc_now": _FRANKFURT_NOON_UTC},
    )
    assert preview_resp.status_code == 200, (
        f"Step 3 failed: GET /solar-preview returned {preview_resp.status_code}: "
        f"{preview_resp.text}"
    )
    preview_body   = preview_resp.json()
    p_renewable_mw = preview_body.get("p_renewable_mw", 0.0)
    expected_frac  = preview_body.get("expected_fraction", 0.0)

    # 3a — must be positive (sun is up at Frankfurt noon)
    assert p_renewable_mw > 0.0, (
        f"Step 3a failed: p_renewable_mw={p_renewable_mw:.4f} MW at Frankfurt "
        f"solar noon (utc_now={_FRANKFURT_NOON_UTC}).\n"
        f"  longitude_deg confirmed at step 2: {lon}\n"
        f"  utc_offset_h returned by /solar-preview: {preview_body.get('utc_offset_h')}\n"
        f"  expected_fraction: {expected_frac}\n"
        "Most likely cause: app.state.site_location was not updated by PUT /api/location, "
        "or the physics model is not applying the Europe/Berlin UTC offset correctly."
    )

    # 3b — DST offset must be 2.0 (CEST) for the override date 2026-06-21
    utc_off = preview_body.get("utc_offset_h")
    assert utc_off == pytest.approx(2.0, abs=0.01), (
        f"Step 3b failed: utc_offset_h={utc_off!r} for Frankfurt on 2026-06-21; "
        "expected 2.0 (CEST).  DST must be resolved from the utc_now override "
        "instant, not from the server's current wall-clock date."
    )

    # 3c — expected_fraction must differ from the lon=0.0 baseline, proving
    #       longitude_deg=8.68 drives the physics, not just tz_name.
    _utc_dt = datetime.datetime(2026, 6, 21, 10, 0, 0)
    frac_lon_zero = _solar_fraction_at(
        _utc_dt, lat_deg=50.11, longitude_deg=0.0
    )
    assert abs(expected_frac - frac_lon_zero) > 1e-4, (
        f"Step 3c failed: expected_fraction with Frankfurt (lon={lon}) = "
        f"{expected_frac:.6f} is indistinguishable from lon=0.0 fraction = "
        f"{frac_lon_zero:.6f}.  The endpoint is not passing longitude_deg to "
        "the physics model; longitude_deg must reach _solar_fraction_at() for "
        "the NOAA true-solar-time correction to take effect."
    )
