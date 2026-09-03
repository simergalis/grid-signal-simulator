"""
tests/test_cooling_mw_blackbox.py — TC-CL-1 through TC-CL-10

Black-box verification of the end-to-end cooling MW calculation chain:
  factory  →  RunContext._rated_cooling_mw
  CoolingModule  →  p_cooling_demand_mw on each tick

Tests cover 10 scenarios with varying compute loads to confirm:
  (a) rated_cooling_mw is always > 0 for any scenario that runs compute
  (b) rated_cooling_mw is proportional to node count (linearity)
  (c) The spec factory path without workload_events returns rated > 0
      (regression guard for the 0.0 override bug fixed in scenario_factory.py)
  (d) Thermal lag: cooling demand is zero before dt_thermal has elapsed
  (e) Cooling demand rises after dt_thermal and asymptotes to α_max × P_compute
  (f) headroom (absorbable_mw = rated − demand) is never negative

Constants from the site parameter catalogue (default SiteConfig):
  alpha_max      = 0.20
  tau_seconds    = 20.0
  dt_thermal_s   = 90.0
  pue_base       = 1.03
  cooling_margin = 1.15
  hw rated_kw    = 10.2  (enterprise_8gpu_air)
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import SiteConfig
from core.asset_modules import CoolingModule
from runtime.scenario_factory import (
    DEFAULT_HARDWARE_LIBRARY,
    build_run_context,
    build_run_context_from_spec,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Default catalogue constants — keep in sync with SiteConfig defaults.
_ALPHA_MAX    = 0.20
_TAU_S        = 20.0
_DT_THERMAL_S = 90.0
_PUE_BASE     = 1.03
_RATED_KW     = DEFAULT_HARDWARE_LIBRARY["enterprise_8gpu_air"].rated_kw   # 10.2


def _peak_it_mw(node_count: int) -> float:
    """Expected peak IT load MW for given node count using default catalogue values."""
    return node_count * _RATED_KW * _PUE_BASE / 1000.0


def _expected_rated_cooling_mw(node_count: int, cooling_margin: float = 1.15) -> float:
    """Expected rated_cooling_mw from the factory formula: α_max × IT_peak × margin."""
    return _ALPHA_MAX * _peak_it_mw(node_count) * cooling_margin


def _make_cooling_module(alpha_max: float = _ALPHA_MAX,
                          tau: float = _TAU_S,
                          dt_thermal: float = _DT_THERMAL_S) -> CoolingModule:
    """Build a CoolingModule with controlled SiteConfig parameters."""
    site = SiteConfig(
        site_id="test-site",
        frequency_nominal_hz=60.0,
        power_factor=0.85,
        alpha_max=alpha_max,
        tau_seconds=tau,
        dt_thermal_seconds=dt_thermal,
    )
    return CoolingModule(asset_id="cooling-test", site=site)


def _drive_scalar(compute_mw: float,
                  until_s: float,
                  dt_s: float = 5.0,
                  alpha_max: float = _ALPHA_MAX,
                  tau: float = _TAU_S,
                  dt_thermal: float = _DT_THERMAL_S) -> dict[float, float]:
    """
    Drive a CoolingModule with constant compute_mw from t=0 (scalar path).

    Returns a dict {sim_time: output_mw} sampled at every tick up to until_s.
    Captures times at multiples of dt_s; rounding avoids float accumulation.
    """
    cm = _make_cooling_module(alpha_max=alpha_max, tau=tau, dt_thermal=dt_thermal)
    results: dict[float, float] = {}
    t = 0.0
    while t <= until_s + 1e-9:
        cm.record_compute_sample(t, compute_mw)
        cm.advance(t, dt_s)
        results[round(t, 6)] = cm.output_mw()
        t = round(t + dt_s, 6)
    return results


def _minimal_spec_no_workload_events(
    *,
    turbine_mw: float = 10.0,
    tag: str = "default",
) -> dict:
    """Minimal spec with no workload_events — mirrors the fabric regression structure."""
    return {
        "name": f"cl-test-no-we-{tag}",
        "end_sim_time": 60.0,
        "alpha_max": _ALPHA_MAX,
        "island_mode": False,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "turbine_units": [
            {"asset_id": "t-0", "rated_mw": turbine_mw, "r_asset_mw_per_s": 5.0}
        ],
        "bess_units": [
            {
                "asset_id": "b-0", "rated_mw": 5.0, "usable_mwh": 2.0,
                "initial_soc_fraction": 1.0, "grid_forming": False,
            }
        ],
        # Deliberately no "workload_events" key — this is the path that used to
        # produce rated_cooling_mw = 0.0 before the factory fix.
    }


def _minimal_spec_with_workload_events(
    *,
    node_count: int,
    turbine_mw: float = 20.0,
    tag: str = "default",
) -> dict:
    """Minimal spec WITH workload_events so the node-count path is exercised."""
    return {
        "name": f"cl-test-we-{tag}",
        "end_sim_time": 60.0,
        "alpha_max": _ALPHA_MAX,
        "island_mode": False,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "turbine_units": [
            {"asset_id": "t-0", "rated_mw": turbine_mw, "r_asset_mw_per_s": 5.0}
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
                "job_id": "job-cl-test",
                "node_count": node_count,
                "hardware_profile_id": "enterprise_8gpu_air",
            }
        ],
    }


# ---------------------------------------------------------------------------
# TC-CL-1  Simple factory (4 nodes) → rated_cooling_mw > 0, matches formula
# ---------------------------------------------------------------------------

def test_tc_cl_1_simple_factory_4nodes_rated_positive_and_correct():
    """build_run_context(4 nodes) must produce a positive rated_cooling_mw
    that matches  alpha_max × peak_it_load_mw × cooling_margin.

    Compute load: 4 × 10.2 kW × pue_base = ~42.0 kW IT.
    Expected rated: 0.20 × 0.04202 MW × 1.15 ≈ 0.00967 MW.

    Confirms the simple-factory path populates rated correctly.
    """
    ctx = build_run_context("tc-cl-1", job_id="j1", node_count=4)
    rated = ctx._rated_cooling_mw

    assert rated > 0, (
        f"rated_cooling_mw should be positive for 4 nodes; got {rated:.6f}"
    )

    expected = _expected_rated_cooling_mw(4)
    assert abs(rated - expected) < 1e-6, (
        f"rated_cooling_mw={rated:.6f} MW, expected {expected:.6f} MW "
        f"(α_max × IT_peak × margin = 0.20 × {_peak_it_mw(4):.5f} × 1.15)"
    )


# ---------------------------------------------------------------------------
# TC-CL-2  Simple factory (10 nodes) → rated scales with node count
# ---------------------------------------------------------------------------

def test_tc_cl_2_simple_factory_10nodes_rated_proportional():
    """rated_cooling_mw must be exactly 2.5× the 4-node value (10/4 = 2.5).

    The formula is linear in node_count, so ratios must hold to floating-point
    precision.  This guards against any non-linear scaling bug in the factory.
    """
    ctx4  = build_run_context("tc-cl-2a", job_id="j1", node_count=4)
    ctx10 = build_run_context("tc-cl-2b", job_id="j1", node_count=10)

    rated4  = ctx4._rated_cooling_mw
    rated10 = ctx10._rated_cooling_mw

    assert rated10 > 0, f"10-node rated_cooling_mw should be positive; got {rated10}"
    assert rated4  > 0, f"4-node  rated_cooling_mw should be positive; got {rated4}"

    ratio = rated10 / rated4
    assert abs(ratio - 2.5) < 1e-9, (
        f"rated_cooling_mw should scale linearly with node count; "
        f"expected 10/4 = 2.5, got {ratio:.10f}"
    )


# ---------------------------------------------------------------------------
# TC-CL-3  Simple factory (20 nodes) → rated is exactly 5× the 4-node value
# ---------------------------------------------------------------------------

def test_tc_cl_3_simple_factory_20nodes_rated_proportional():
    """rated_cooling_mw must be exactly 5× the 4-node value (20/4 = 5.0).

    Verifies linearity across a wider range.  Also checks the absolute value
    matches the formula at the higher load point.
    """
    ctx4  = build_run_context("tc-cl-3a", job_id="j1", node_count=4)
    ctx20 = build_run_context("tc-cl-3b", job_id="j1", node_count=20)

    rated4  = ctx4._rated_cooling_mw
    rated20 = ctx20._rated_cooling_mw

    assert rated20 > 0, f"20-node rated_cooling_mw should be positive; got {rated20}"

    ratio = rated20 / rated4
    assert abs(ratio - 5.0) < 1e-9, (
        f"rated_cooling_mw(20 nodes) / rated_cooling_mw(4 nodes) = {ratio:.10f}, "
        f"expected 5.0 (linear scaling)"
    )

    # Also check absolute formula
    expected20 = _expected_rated_cooling_mw(20)
    assert abs(rated20 - expected20) < 1e-6, (
        f"rated_cooling_mw(20 nodes)={rated20:.6f}, expected {expected20:.6f}"
    )


# ---------------------------------------------------------------------------
# TC-CL-4  Spec factory WITH workload_events → rated from node count
# ---------------------------------------------------------------------------

def test_tc_cl_4_spec_factory_with_workload_events_40nodes():
    """build_run_context_from_spec() with workload_events (40 nodes) must produce
    a rated_cooling_mw matching alpha_max × peak_it_load(40 nodes) × margin.

    Tests the spec-factory event-driven path (not the simple factory).
    """
    spec = _minimal_spec_with_workload_events(node_count=40)
    ctx  = build_run_context_from_spec("tc-cl-4", spec)

    rated = ctx._rated_cooling_mw
    assert rated > 0, f"Spec-path rated_cooling_mw must be positive for 40 nodes; got {rated}"

    expected = _expected_rated_cooling_mw(40)
    assert abs(rated - expected) < 1e-5, (
        f"Spec-path rated_cooling_mw={rated:.6f} MW, "
        f"expected {expected:.6f} MW (40 nodes, enterprise_8gpu_air)"
    )


# ---------------------------------------------------------------------------
# TC-CL-5  Spec factory WITHOUT workload_events → rated > 0  (bug regression)
# ---------------------------------------------------------------------------

def test_tc_cl_5_spec_factory_no_workload_events_rated_nonzero():
    """build_run_context_from_spec() with NO workload_events must produce a
    positive rated_cooling_mw.

    REGRESSION GUARD: before the factory fix, the else-branch hardcoded
    _spec_rated_cooling_mw = 0.0, which propagated to ctx._rated_cooling_mw
    and broadcast 'rated = 0.00 MW' on every tick — an impossible state for a
    facility running 6+ MW of compute.

    The fix uses  alpha_max × turbine_fleet_mw × cooling_margin  as the proxy.
    For a single 10 MW turbine: 0.20 × 10.0 × 1.15 = 2.30 MW.
    """
    spec = _minimal_spec_no_workload_events(turbine_mw=10.0)
    ctx  = build_run_context_from_spec("tc-cl-5", spec)

    rated = ctx._rated_cooling_mw

    assert rated > 0.0, (
        "REGRESSION: rated_cooling_mw is 0.0 for a no-workload-events spec. "
        "The factory fix (turbine proxy formula) must produce a positive value. "
        f"Got {rated}"
    )

    # Expected: alpha_max × turbine_mw × cooling_margin = 0.20 × 10.0 × 1.15 = 2.30
    expected = _ALPHA_MAX * 10.0 * 1.15
    assert abs(rated - expected) < 1e-6, (
        f"rated_cooling_mw={rated:.6f} MW, "
        f"expected {expected:.6f} MW (α_max × 10 MW turbine × margin)"
    )


# ---------------------------------------------------------------------------
# TC-CL-6  Cooling demand is exactly zero before the thermal lag (t < 90 s)
# ---------------------------------------------------------------------------

def test_tc_cl_6_cooling_demand_zero_before_thermal_lag():
    """P_cooling(t) must be 0 for all ticks where t < dt_thermal (90 s).

    Drive 5 MW of compute from t=0; at t=85 s (the last tick before dt_thermal
    expires) the CoolingModule must still report 0.0 because the thermal lag
    has not been crossed.

    Sampled at every 5 s tick up to t=85 s.
    """
    P_COMPUTE = 5.0   # MW
    results = _drive_scalar(P_COMPUTE, until_s=_DT_THERMAL_S - 5.0)

    for t_s, p_cool in results.items():
        assert p_cool == 0.0, (
            f"p_cooling at t={t_s:.1f}s should be 0.0 (before {_DT_THERMAL_S}s thermal lag); "
            f"got {p_cool:.6f} MW"
        )


# ---------------------------------------------------------------------------
# TC-CL-7  Cooling demand rises immediately after the lag window opens (t=95 s)
# ---------------------------------------------------------------------------

def test_tc_cl_7_cooling_demand_rises_after_thermal_lag():
    """The first tick after dt_thermal has elapsed (t=95 s) must have p_cooling > 0
    and less than its steady-state ceiling α_max × P_compute.

    This confirms the exponential rise has begun but is not yet saturated.
    """
    P_COMPUTE    = 4.0          # MW
    STEADY_STATE = _ALPHA_MAX * P_COMPUTE   # 0.80 MW

    results = _drive_scalar(P_COMPUTE, until_s=200.0)

    # t=90 s is still the last tick at the lag boundary — must still be 0.
    assert results[90.0] == 0.0, (
        f"p_cooling at t=90.0s should be 0.0 (lag boundary); got {results[90.0]:.6f}"
    )

    # t=95 s is the first tick after lag expires.
    p_95 = results[95.0]
    assert 0.0 < p_95 < STEADY_STATE, (
        f"p_cooling at t=95s should be in (0, {STEADY_STATE:.4f}) MW; got {p_95:.6f} MW"
    )

    # Should be roughly 22% of steady state at t=95 s
    # (elapsed=5 s, α_k = α_max × (1−e^−5/20) ≈ 0.221 × α_max)
    pct = p_95 / STEADY_STATE * 100.0
    assert 15.0 < pct < 35.0, (
        f"p_cooling at t=95s is {pct:.1f}% of steady state, expected ~22%"
    )


# ---------------------------------------------------------------------------
# TC-CL-8  Steady-state cooling ≈ α_max × P_compute for 8 varying loads
# ---------------------------------------------------------------------------

def test_tc_cl_8_steady_state_cooling_equals_alpha_times_compute():
    """At t=300 s (> dt_thermal + 5·τ = 90+100 = 190 s), each envelope's α_k
    is within 0.1% of α_max, so total P_cooling must be within 0.1% of
    α_max × P_compute.

    Tested across 8 distinct compute loads from 0.5 MW to 12.0 MW.
    """
    loads_mw = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 12.0]

    for P_COMPUTE in loads_mw:
        results  = _drive_scalar(P_COMPUTE, until_s=350.0)
        p_steady = results[300.0]
        expected = _ALPHA_MAX * P_COMPUTE
        rel_err  = abs(p_steady - expected) / expected

        assert rel_err < 0.001, (
            f"Steady-state p_cooling ({P_COMPUTE} MW compute): "
            f"got {p_steady:.6f} MW, expected {expected:.6f} MW "
            f"(relative error {rel_err*100:.4f}% > 0.1%)"
        )


# ---------------------------------------------------------------------------
# TC-CL-9  Headroom (absorbable_mw = rated − demand) is never negative
# ---------------------------------------------------------------------------

def test_tc_cl_9_headroom_never_negative_across_varying_loads():
    """For each of 8 compute loads, absorbable_mw = rated_cooling_mw − demand
    must remain ≥ 0 at every tick from t=0 to t=350 s.

    Uses build_run_context to get the correct rated_cooling_mw per node count,
    then drives the CoolingModule to full steady state and checks the invariant.

    Node counts chosen to span a decade: 2, 4, 8, 16, 32, 64, 100, 200.
    """
    node_counts = [2, 4, 8, 16, 32, 64, 100, 200]

    for nc in node_counts:
        ctx   = build_run_context(f"tc-cl-9-nc{nc}", job_id="j1", node_count=nc)
        rated = ctx._rated_cooling_mw

        # Peak compute MW at full ramp (all nodes × rated_kw × pue_base)
        p_compute = nc * _RATED_KW * _PUE_BASE / 1000.0

        # Drive cooling module to steady state
        results = _drive_scalar(p_compute, until_s=350.0)

        violations = [
            (t_s, demand)
            for t_s, demand in results.items()
            if (rated - demand) < -1e-9
        ]

        assert not violations, (
            f"nc={nc}: headroom went negative at "
            + ", ".join(f"t={t}s (demand={d:.4f}, rated={rated:.4f})"
                        for t, d in violations[:3])
        )


# ---------------------------------------------------------------------------
# TC-CL-10  Spec factory — rated scales with turbine fleet size
# ---------------------------------------------------------------------------

def test_tc_cl_10_spec_no_workload_events_rated_scales_with_turbine_mw():
    """For the no-workload-events spec path, rated_cooling_mw must scale
    linearly with the turbine fleet size (the proxy used by the fixed factory).

    Tests 5 turbine fleet sizes: 5, 10, 15, 20, 25 MW.

    The formula is:  rated = α_max × turbine_mw × cooling_margin = 0.20 × T × 1.15
    so the ratio between any two fleet sizes must equal their MW ratio exactly.
    """
    turbine_sizes_mw = [5.0, 10.0, 15.0, 20.0, 25.0]
    cooling_margin   = 1.15

    rated_values: dict[float, float] = {}
    for t_mw in turbine_sizes_mw:
        spec = _minimal_spec_no_workload_events(turbine_mw=t_mw, tag=f"{int(t_mw)}mw")
        ctx  = build_run_context_from_spec(f"tc-cl-10-{int(t_mw)}", spec)
        rated_values[t_mw] = ctx._rated_cooling_mw

    # Every value must be positive.
    for t_mw, rated in rated_values.items():
        assert rated > 0.0, (
            f"turbine={t_mw} MW: rated_cooling_mw should be positive; got {rated}"
        )

    # Absolute correctness: rated = α_max × turbine_mw × cooling_margin.
    for t_mw, rated in rated_values.items():
        expected = _ALPHA_MAX * t_mw * cooling_margin
        assert abs(rated - expected) < 1e-9, (
            f"turbine={t_mw} MW: rated={rated:.6f}, expected {expected:.6f} "
            f"(α_max × {t_mw} × {cooling_margin})"
        )

    # Linearity: ratio between successive sizes must equal their MW ratio.
    sizes = sorted(turbine_sizes_mw)
    for i in range(1, len(sizes)):
        t_hi, t_lo  = sizes[i], sizes[i - 1]
        r_hi, r_lo  = rated_values[t_hi], rated_values[t_lo]
        expected_ratio = t_hi / t_lo
        actual_ratio   = r_hi / r_lo
        assert abs(actual_ratio - expected_ratio) < 1e-9, (
            f"rated({t_hi} MW) / rated({t_lo} MW) = {actual_ratio:.10f}, "
            f"expected {expected_ratio:.10f} (linear scaling)"
        )
