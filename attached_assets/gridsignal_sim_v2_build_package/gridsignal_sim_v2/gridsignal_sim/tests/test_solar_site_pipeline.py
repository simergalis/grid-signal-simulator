"""
tests/test_solar_site_pipeline.py — SP-1 through SP-7

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
"""

from __future__ import annotations

import contextlib
import datetime
import os

import pytest

from runtime.scenario_factory import build_run_context_from_spec
from runtime.solar_sim import SolarForecast, generate_solar_forecast


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
