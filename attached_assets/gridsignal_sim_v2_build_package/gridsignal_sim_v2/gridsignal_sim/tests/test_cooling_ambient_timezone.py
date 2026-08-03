"""
tests/test_cooling_ambient_timezone.py — CA-1 through CA-8

Audit and regression suite for task #76: confirm the cooling model and load
patterns correctly use site local time, not server UTC, when applying ambient
temperature adjustments.

Audit findings (task #76)
--------------------------
Three files were audited for unqualified wall-clock UTC usage in physics paths:

runtime/scenario_factory.py
  No datetime.now() or .hour access.  The only time-aware path is
  spec_data["ambient_steps"], which is pre-computed by solar_sim.py
  (correctly applying utc_offset_h) before build_run_context_from_spec()
  is called.  alpha_max is scaled once at run-build time from those
  pre-corrected ambient steps.  CLEAN.

core/simulation_core.py
  No datetime.now() or .hour access in any physics path.  The cooling
  envelope (CoolingPlant.advance()) uses sim_time (relative seconds from
  t=0), not wall-clock hours.  CLEAN.

runtime/run_manager.py
  datetime.now(timezone.utc) appears at line 1173 (completed_at) and
  persistence.py:768 (wall-clock metadata only).  Neither feeds physics.
  CLEAN.

core/procurement.py
  SyntheticPriceCurve.price_at() uses sim_time + seed-based phase offset.
  No wall-clock hours.  CLEAN.

core/kube_demand.py
  Uses EMA on actual compute load.  No time-of-day patterns.  CLEAN.

Pipeline that IS time-sensitive (and already correct)
------------------------------------------------------
  runs.py reads site_utc_offset_h from the spec
    → calls generate_solar_forecast(..., site_utc_offset_h=...)
      → _parse_forecast() / _physics_ambient_steps() correctly apply offset
    → injects forecast.ambient_steps into spec_data["ambient_steps"]
  build_run_context_from_spec() reads ambient_steps
    → ambient_alpha_scale(ambient_steps) → scale factor
    → site.alpha_max *= scale  (higher ambient → more cooling fraction)
    → stored as RunContext.ambient_alpha_scale

The regression tests below confirm this pipeline stays correct for a UTC+12
site.  Any future change that re-introduces a UTC-as-local bug in the ambient
steps would change ambient_alpha_scale and be caught here.

CA-1  ambient_alpha_scale() — Auckland afternoon steps give higher scale than pre-dawn
CA-2  build_run_context_from_spec() ambient_avg_c is higher for Auckland afternoon
CA-3  build_run_context_from_spec() ambient_alpha_scale is higher for Auckland afternoon
CA-4  Broken UTC offset (offset=0) gives same scale as pre-dawn — the regression scenario
CA-5  Correctly-offset afternoon run → higher site.alpha_max than broken-offset run
CA-6  Correctly-offset afternoon run → higher p_cooling_mw per tick
CA-7  No datetime.now() / .hour in scenario_factory.py physics block (source audit)
CA-8  Tick-level p_cooling_mw is higher for Auckland afternoon than broken-offset run
      (runs 60 ticks with fast thermal params; confirms the alpha_max scaling reaches
      tick output, not just the construction-time attribute)
"""

from __future__ import annotations

import datetime
import math
import os

import pytest

from runtime.scenario_factory import build_run_context_from_spec
from runtime.solar_sim import ambient_alpha_scale, _physics_ambient_steps


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Auckland, New Zealand — UTC+12
_AUCKLAND_LAT  = -36.85
_AUCKLAND_UTC  = 12.0
_BASE_TEMP     = 14.0   # default base_temp_c for NZ maritime climate

# June solstice
_JUN_SOLSTICE = datetime.date(2026, 6, 21)

def _utc(date: datetime.date, hour: int) -> datetime.datetime:
    return datetime.datetime(date.year, date.month, date.day, hour, 0, 0)

# 04:00 UTC = 16:00 Auckland local (afternoon, solar > 0, warmer ambient)
_AFTERNOON_UTC = _utc(_JUN_SOLSTICE, 4)
# 16:00 UTC = 04:00 Auckland local (pre-dawn, solar = 0, cold ambient)
_PREDAWN_UTC   = _utc(_JUN_SOLSTICE, 16)

_RUN_DURATION_S = 60.0   # 12 ticks at 5 s — short but enough for cooling signal


def _make_ambient_steps(utc_now: datetime.datetime, utc_offset_h: float) -> list:
    """Generate physics-based ambient_steps for the given site and UTC time."""
    return _physics_ambient_steps(
        _RUN_DURATION_S, utc_now,
        lat_deg=_AUCKLAND_LAT,
        utc_offset_h=utc_offset_h,
        base_temp_c=_BASE_TEMP,
    )


def _minimal_spec(ambient_steps: list, tag: str) -> dict:
    """Build a minimal spec with ambient_steps injected (no solar needed)."""
    return {
        "name": f"cooling-tz-test-{tag}",
        "end_sim_time": _RUN_DURATION_S,
        "alpha_max": 0.20,
        "island_mode": False,
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
                "job_id": "job-cooling-test",
                "node_count": 100,
                "hardware_profile_id": "enterprise_8gpu_air",
            }
        ],
        "ambient_steps": [[t, db, wb] for t, db, wb in ambient_steps],
    }


def _run_n_ticks(ctx, n: int):
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
# CA-1  ambient_alpha_scale() — afternoon steps give higher scale than pre-dawn
# ---------------------------------------------------------------------------

def test_ca1_afternoon_ambient_scale_exceeds_predawn():
    """Auckland afternoon (04:00 UTC = 16:00 local) has higher dry-bulb temperatures
    than pre-dawn (16:00 UTC = 04:00 local), which must produce a higher
    ambient_alpha_scale — meaning the cooling system is configured to work
    harder during the hotter part of the day.

    This directly tests the ambient_alpha_scale() function with UTC-offset-
    corrected input from _physics_ambient_steps().
    """
    steps_afternoon = _make_ambient_steps(_AFTERNOON_UTC, _AUCKLAND_UTC)
    steps_predawn   = _make_ambient_steps(_PREDAWN_UTC,   _AUCKLAND_UTC)

    scale_afternoon = ambient_alpha_scale(steps_afternoon)
    scale_predawn   = ambient_alpha_scale(steps_predawn)

    assert scale_afternoon > scale_predawn, (
        f"Auckland afternoon (16:00 local) ambient_alpha_scale ({scale_afternoon:.4f}) "
        f"must exceed pre-dawn (04:00 local) scale ({scale_predawn:.4f}). "
        "If equal, utc_offset_h is not reaching _physics_ambient_steps()."
    )


# ---------------------------------------------------------------------------
# CA-2  build_run_context_from_spec() ambient_avg_c higher for Auckland afternoon
# ---------------------------------------------------------------------------

def test_ca2_runcontext_ambient_avg_c_higher_for_afternoon():
    """RunContext.ambient_avg_c must be higher when ambient_steps were generated
    at Auckland afternoon (warm) than at pre-dawn (cold).

    ambient_avg_c is the per-run constant that operators see in tick payloads
    (PROTO-32-AMB) and that indicates how hot the site was during the run.
    """
    steps_afternoon = _make_ambient_steps(_AFTERNOON_UTC, _AUCKLAND_UTC)
    steps_predawn   = _make_ambient_steps(_PREDAWN_UTC,   _AUCKLAND_UTC)

    ctx_afternoon = build_run_context_from_spec(
        "ca2-afternoon", _minimal_spec(steps_afternoon, "ca2a")
    )
    ctx_predawn = build_run_context_from_spec(
        "ca2-predawn", _minimal_spec(steps_predawn, "ca2p")
    )

    assert ctx_afternoon.ambient_avg_c > ctx_predawn.ambient_avg_c, (
        f"Auckland afternoon run ambient_avg_c ({ctx_afternoon.ambient_avg_c:.2f} °C) "
        f"must exceed pre-dawn run ({ctx_predawn.ambient_avg_c:.2f} °C). "
        "ambient_steps are not propagating correctly to RunContext."
    )


# ---------------------------------------------------------------------------
# CA-3  build_run_context_from_spec() ambient_alpha_scale higher for afternoon
# ---------------------------------------------------------------------------

def test_ca3_runcontext_alpha_scale_higher_for_afternoon():
    """RunContext.ambient_alpha_scale must be higher for Auckland afternoon than
    pre-dawn, reflecting that hotter ambient → HVAC works harder → more power.

    This is the key quantity that multiplies site.alpha_max and drives
    p_cooling_mw.  If UTC offset is not applied to ambient generation, this
    scale would be the same for both times.
    """
    steps_afternoon = _make_ambient_steps(_AFTERNOON_UTC, _AUCKLAND_UTC)
    steps_predawn   = _make_ambient_steps(_PREDAWN_UTC,   _AUCKLAND_UTC)

    ctx_afternoon = build_run_context_from_spec(
        "ca3-afternoon", _minimal_spec(steps_afternoon, "ca3a")
    )
    ctx_predawn = build_run_context_from_spec(
        "ca3-predawn", _minimal_spec(steps_predawn, "ca3p")
    )

    assert ctx_afternoon.ambient_alpha_scale > ctx_predawn.ambient_alpha_scale, (
        f"Auckland afternoon ambient_alpha_scale ({ctx_afternoon.ambient_alpha_scale:.4f}) "
        f"must exceed pre-dawn ({ctx_predawn.ambient_alpha_scale:.4f}). "
        "If equal, the UTC offset is not flowing through to ambient_alpha_scale."
    )


# ---------------------------------------------------------------------------
# CA-4  Broken UTC offset gives same scale as pre-dawn (the regression)
# ---------------------------------------------------------------------------

def test_ca4_broken_offset_gives_same_scale_as_predawn():
    """With utc_offset_h=0, Auckland 04:00 UTC is misread as 04:00 local (pre-dawn).

    _physics_ambient_steps() would then produce cold ambient_steps identical to
    the actual pre-dawn run.  ambient_alpha_scale would match pre-dawn, and the
    operator would see a 'cold' cooling baseline for an afternoon run — silently
    wrong for an Auckland data centre.

    This test documents the failure mode: if it started passing with the broken
    offset, it would mean some OTHER mechanism was compensating, which should be
    investigated.
    """
    steps_afternoon_correct = _make_ambient_steps(_AFTERNOON_UTC, _AUCKLAND_UTC)
    steps_afternoon_broken  = _make_ambient_steps(_AFTERNOON_UTC, 0.0)  # broken
    steps_predawn_correct   = _make_ambient_steps(_PREDAWN_UTC,   _AUCKLAND_UTC)

    scale_correct = ambient_alpha_scale(steps_afternoon_correct)
    scale_broken  = ambient_alpha_scale(steps_afternoon_broken)
    scale_predawn = ambient_alpha_scale(steps_predawn_correct)

    # Broken offset at 04:00 UTC reads local_h=4 (pre-dawn) → same cold steps
    assert math.isclose(scale_broken, scale_predawn, abs_tol=1e-9), (
        f"Broken-offset afternoon (utc_offset=0): scale {scale_broken:.6f}. "
        f"Pre-dawn (correct offset): scale {scale_predawn:.6f}. "
        "They should be identical (both treat the time as pre-dawn local). "
        "If they differ, the broken-offset scenario is not correctly modelled."
    )

    # And the correct offset gives a strictly different (higher) scale
    assert scale_correct > scale_broken, (
        f"Correct-offset afternoon scale ({scale_correct:.4f}) must exceed "
        f"broken-offset scale ({scale_broken:.4f}) to confirm the fix matters."
    )


# ---------------------------------------------------------------------------
# CA-5  Correctly-offset run → higher effective site.alpha_max than broken-offset
# ---------------------------------------------------------------------------

def test_ca5_correct_offset_gives_higher_alpha_max():
    """When ambient_steps are generated with the correct UTC offset, site.alpha_max
    is multiplied by a higher ambient_alpha_scale than with the broken offset.

    site.alpha_max is the rated cooling fraction; a higher value means the
    CoolingPlant is sized for (and driven toward) more MW per unit of compute.
    """
    steps_correct = _make_ambient_steps(_AFTERNOON_UTC, _AUCKLAND_UTC)
    steps_broken  = _make_ambient_steps(_AFTERNOON_UTC, 0.0)

    base_spec_correct = _minimal_spec(steps_correct, "ca5c")
    base_spec_broken  = _minimal_spec(steps_broken,  "ca5b")

    # Record baseline alpha_max (before ambient scaling)
    _BASE_ALPHA = float(base_spec_correct.get("alpha_max", 0.20))

    ctx_correct = build_run_context_from_spec("ca5-correct", base_spec_correct)
    ctx_broken  = build_run_context_from_spec("ca5-broken",  base_spec_broken)

    # The effective alpha_max = base * ambient_alpha_scale; it lives on site
    # We can back it out from ambient_alpha_scale × base
    effective_alpha_correct = _BASE_ALPHA * ctx_correct.ambient_alpha_scale
    effective_alpha_broken  = _BASE_ALPHA * ctx_broken.ambient_alpha_scale

    assert effective_alpha_correct > effective_alpha_broken, (
        f"Correct-offset afternoon effective alpha_max ({effective_alpha_correct:.5f}) "
        f"must exceed broken-offset ({effective_alpha_broken:.5f}). "
        "ambient_alpha_scale is not differing between the two runs."
    )


# ---------------------------------------------------------------------------
# CA-6  Correctly-offset afternoon run → higher site.alpha_max on SimulationState
# ---------------------------------------------------------------------------

def test_ca6_correct_offset_gives_higher_site_alpha_max():
    """build_run_context_from_spec() mutates site.alpha_max in-place as:
        site.alpha_max = base_alpha_max * ambient_alpha_scale(ambient_steps)

    This is the exact value CoolingPlant.advance() reads to compute αₖ and
    therefore p_cooling_mw for every future tick once compute load is present.
    A higher site.alpha_max → more cooling MW per unit of compute.

    The correctly-offset Auckland afternoon run (warmer ambient → higher scale)
    must produce a strictly higher site.alpha_max on the SimulationState than
    the broken-offset run (cold ambient misread → lower scale).

    Testing site.alpha_max directly avoids the thermal lag
    (dt_thermal_seconds default = 90 s) that delays p_cooling_mw output,
    while still confirming the end-to-end path:
      ambient_steps → ambient_alpha_scale() → site.alpha_max on SimulationState
    """
    steps_correct = _make_ambient_steps(_AFTERNOON_UTC, _AUCKLAND_UTC)
    steps_broken  = _make_ambient_steps(_AFTERNOON_UTC, 0.0)

    ctx_correct = build_run_context_from_spec(
        "ca6-correct", _minimal_spec(steps_correct, "ca6c")
    )
    ctx_broken = build_run_context_from_spec(
        "ca6-broken", _minimal_spec(steps_broken, "ca6b")
    )

    alpha_correct = ctx_correct.sim_state.site.alpha_max
    alpha_broken  = ctx_broken.sim_state.site.alpha_max

    assert alpha_correct > alpha_broken, (
        f"Correctly-offset Auckland afternoon run site.alpha_max ({alpha_correct:.5f}) "
        f"must exceed broken-offset run ({alpha_broken:.5f}). "
        "ambient_alpha_scale from warm afternoon ambient_steps must increase "
        "site.alpha_max so CoolingPlant draws more per unit of compute. "
        "If equal, the ambient_steps → site.alpha_max multiplication is broken."
    )


# ---------------------------------------------------------------------------
# CA-7  Source audit: no datetime.now()/.hour in scenario_factory physics block
# ---------------------------------------------------------------------------

def test_ca7_scenario_factory_physics_block_has_no_wall_clock_usage():
    """Confirm that scenario_factory.py contains no datetime.now() or bare .hour
    calls in the section that builds the RunContext physics objects.

    This is a canary: if someone later adds a wall-clock lookup (e.g. to set a
    'current time of day' default for some new diurnal parameter) without
    threading the site UTC offset, this test will alert immediately.

    Method: read the source file and assert the forbidden patterns are absent
    from the non-import, non-comment lines of the physics-relevant section.
    """
    import pathlib
    factory_path = (
        pathlib.Path(__file__).parent.parent / "runtime" / "scenario_factory.py"
    )
    source = factory_path.read_text(encoding="utf-8")

    # Strip comment lines so we don't flag strings inside docstrings or comments
    code_lines = [
        ln for ln in source.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)

    # datetime.now() is forbidden in the factory entirely (metadata timestamps
    # belong in run_manager or persistence, not the factory).
    assert "datetime.now(" not in code, (
        "scenario_factory.py contains datetime.now() — this should not be present; "
        "any timestamp metadata belongs in run_manager.py or persistence.py, "
        "and physics-time lookups must use sim_time (not wall-clock UTC)."
    )

    # Bare .hour attribute access (e.g. dt.hour without UTC offset) is forbidden
    # in physics paths.  The only safe pattern is (dt.hour + utc_offset_h) % 24
    # as used in solar_sim.py.
    forbidden_hour_patterns = [".hour\n", ".hour ", ".hour)", ".hour,"]
    for pat in forbidden_hour_patterns:
        assert pat not in code, (
            f"scenario_factory.py contains {pat!r} — bare .hour access without "
            "UTC offset qualification is forbidden in physics paths. "
            "Use (dt.hour + site_utc_offset_h) % 24 as in solar_sim.py."
        )


# ---------------------------------------------------------------------------
# CA-8  Tick-level p_cooling_mw is higher for Auckland afternoon than broken run
# ---------------------------------------------------------------------------

# CA-8 uses a longer run and fast thermal params so the cooling response
# reaches tick output within the test window.
_CA8_RUN_DURATION_S = 300.0   # 60 ticks at 5 s — thermal signal settles well
_CA8_TAU_S         = 5.0      # fast exponential rise (default 20 s)
_CA8_DT_THERMAL_S  = 5.0      # short lag before envelope opens (default 90 s)


def _make_ambient_steps_ca8(utc_now: datetime.datetime, utc_offset_h: float) -> list:
    """Generate ambient steps sized for the CA-8 run window."""
    return _physics_ambient_steps(
        _CA8_RUN_DURATION_S, utc_now,
        lat_deg=_AUCKLAND_LAT,
        utc_offset_h=utc_offset_h,
        base_temp_c=_BASE_TEMP,
    )


def _ca8_spec(ambient_steps: list, tag: str) -> dict:
    """Spec with fast thermal parameters so p_cooling_mw diverges within 60 ticks."""
    return {
        "name": f"ca8-cooling-tick-tz-{tag}",
        "end_sim_time": _CA8_RUN_DURATION_S,
        "alpha_max": 0.20,
        # Fast thermal params: cooling signal visible well before tick 20
        "plant_tau_seconds":        _CA8_TAU_S,
        "plant_dt_thermal_seconds": _CA8_DT_THERMAL_S,
        "island_mode": False,
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
                "job_id": "job-ca8",
                "node_count": 100,
                "hardware_profile_id": "enterprise_8gpu_air",
            }
        ],
        "ambient_steps": [[t, db, wb] for t, db, wb in ambient_steps],
    }


def test_ca8_tick_level_cooling_mw_higher_for_correct_utc_offset():
    """Tick-level p_cooling_mw must be higher when ambient_steps are generated
    with the correct UTC+12 offset (Auckland afternoon, warm) than when the
    offset is 0 (broken: 04:00 UTC misread as 04:00 local, cold ambient).

    This test runs 60 actual simulation ticks with fast thermal parameters
    (tau=5 s, dt_thermal=5 s) so the cooling envelope opens quickly and
    p_cooling_mw values diverge within the test window.  It confirms that
    the ambient_steps → alpha_max scaling pipeline flows all the way through
    to tick output, not just to the RunContext construction-time attribute.

    The assertion checks average p_cooling_mw across ticks 20-60 (after the
    envelope has fully settled) rather than peak, making it robust to the
    ramp-up phase where both runs start from zero.
    """
    steps_correct = _make_ambient_steps_ca8(_AFTERNOON_UTC, _AUCKLAND_UTC)
    steps_broken  = _make_ambient_steps_ca8(_AFTERNOON_UTC, 0.0)

    ctx_correct = build_run_context_from_spec(
        "ca8-correct", _ca8_spec(steps_correct, "correct")
    )
    ctx_broken = build_run_context_from_spec(
        "ca8-broken", _ca8_spec(steps_broken, "broken")
    )

    # Sanity: confirm the alpha_max divergence that drives the tick-level result
    assert ctx_correct.sim_state.site.alpha_max > ctx_broken.sim_state.site.alpha_max, (
        "Precondition failed: correct-offset alpha_max must exceed broken-offset. "
        "If this fails, the ambient_steps → alpha_max path is broken upstream of ticks."
    )

    # Run 60 ticks on each context independently
    _N_TICKS = 60
    ticks_correct = _run_n_ticks(ctx_correct, _N_TICKS)
    ticks_broken  = _run_n_ticks(ctx_broken,  _N_TICKS)

    # Average p_cooling_mw from tick 20 onward (envelope fully settled by then
    # given dt_thermal=5 s and tau=5 s: ~5 × tau = 25 s ≈ 5 ticks to settle)
    settled_correct = [t.p_cooling_mw for t in ticks_correct[20:]]
    settled_broken  = [t.p_cooling_mw for t in ticks_broken[20:]]

    avg_correct = sum(settled_correct) / len(settled_correct)
    avg_broken  = sum(settled_broken)  / len(settled_broken)

    assert avg_correct > avg_broken, (
        f"Auckland afternoon tick-level avg p_cooling_mw ({avg_correct:.4f} MW) "
        f"must exceed broken-offset run ({avg_broken:.4f} MW) across ticks 20-60. "
        "The UTC+12 ambient correction must flow all the way through alpha_max to "
        "tick output.  If equal, the ambient_alpha_scale multiplication in "
        "build_run_context_from_spec() is not reaching CoolingModule.advance()."
    )
