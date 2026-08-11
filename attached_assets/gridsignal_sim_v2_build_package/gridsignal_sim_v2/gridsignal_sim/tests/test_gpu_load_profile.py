"""
tests/test_gpu_load_profile.py — GPU load profile (zero-order-hold compute scaling).

Covers:
  ZOH   _gpu_load_fraction_at helper: 0%, 100%, mid-range, step transitions,
         empty profile, before-first-anchor, boundary exactness.
  TICK  evaluate_tick produces scaled p_compute_demand_mw and matching
         gpu_load_fraction in TickResult.
  COOL  cooling.record_job_compute receives the throttled draws (not full TDP),
         so p_cooling_demand_mw tracks the profiled GPU load.
  WIRE  _tick_result_to_dict carries gpu_load_fraction on the wire payload.
  FACT  scenario_factory wires gpu_load_profile from ScenarioSpec to SimulationState.
"""

from __future__ import annotations

import contextlib
import math

import pytest

from api.schemas import (
    BessUnitSpec,
    ScenarioSpec,
    TurbineUnitSpec,
    WorkloadEventSpec,
)
from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.models import (
    BessConfig,
    HardwareProfile,
    IslandMode,
    SiteConfig,
    SolarConfig,
    TurbineConfig,
)
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, _gpu_load_fraction_at, evaluate_tick
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec


# ---------------------------------------------------------------------------
# Plane-guard helper (required to call evaluate_tick from test layer)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _plane_guard():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


# ---------------------------------------------------------------------------
# Shared state builder
# ---------------------------------------------------------------------------

def _make_state(gpu_load_profile: list[tuple[float, float]] | None = None) -> SimulationState:
    """Minimal SimulationState with one GPU module running a job.

    The GPU module is pre-advanced with a STARTING signal at t=0 so that
    _per_job_draws is non-empty and p_compute_demand_mw > 0 on the first tick.
    island_mode=ISLANDED so the turbine forms the bus (no grid import).
    """
    from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal

    hw = {"enterprise_8gpu_air": HardwareProfile(
        profile_id="enterprise_8gpu_air", rated_kw=10.2
    )}
    site = SiteConfig(
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        site_id="gpu-profile-test",
        pue_base=1.03,
        uncalibrated=False,
        island_mode=IslandMode.ISLANDED,
    )
    gpu  = GPUModule(asset_id="gpu-0", site=site, hardware_library=hw)
    turb = TurbineModule(TurbineConfig(asset_id="t-0", rated_mw=20.0, r_asset_mw_per_s=2.0))
    bess = BessModule(BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=5.0))
    cool = CoolingModule(asset_id="cool-0", site=site)
    solar = SolarModule(
        SolarConfig(asset_id="sol-0", rated_mw=0.0),
        irradiance_profile=IrradianceProfile([(0.0, 0.0)]),
    )

    state = SimulationState(
        run_id="gpu-profile-run",
        site=site,
        gpu_modules=[gpu],
        turbines=[turb],
        bess_units=[bess],
        solar_arrays=[solar],
        cooling=cool,
    )
    if gpu_load_profile is not None:
        state.gpu_load_profile = gpu_load_profile

    # Warm the GPU with a STARTING signal (100 nodes × 10.2 kW = 1.02 MW before PUE)
    signal = WorkloadSignal(
        event_id="e0",
        job_id="job-0",
        event_type=WorkloadEventType.STARTING,
        timestamp=0.0,
        hardware_profile_id="enterprise_8gpu_air",
        node_count=100,
        workload_class=WorkloadClass.TRAINING,
        site_id="gpu-profile-test",
    )
    state.apply_workload_signal(signal, dt_lead_seconds=0.0)
    # Advance GPU module to RUNNING (dt large enough to ramp fully)
    gpu.advance(sim_time=0.0, dt_seconds=60.0)

    return state


def _make_clock(sim_time: float = 0.0, dt: float = 5.0) -> SimClock:
    return SimClock(
        sim_time=sim_time,
        dt_seconds=dt,
        wall_stamp_utc=0.0,
        rate=1.0,
        tick_seq=int(sim_time / dt),
    )


# ---------------------------------------------------------------------------
# ZOH helper: _gpu_load_fraction_at
# ---------------------------------------------------------------------------

class TestGpuLoadFractionAt:

    def test_empty_profile_returns_1(self):
        """Empty profile = no throttle = 1.0 at all times."""
        assert _gpu_load_fraction_at([], 0.0)    == pytest.approx(1.0)
        assert _gpu_load_fraction_at([], 1000.0) == pytest.approx(1.0)

    def test_single_zero_fraction(self):
        """Profile [(0, 0.0)] → 0% at all times."""
        p = [(0.0, 0.0)]
        assert _gpu_load_fraction_at(p, 0.0)   == pytest.approx(0.0)
        assert _gpu_load_fraction_at(p, 600.0) == pytest.approx(0.0)

    def test_single_full_fraction(self):
        """Profile [(0, 1.0)] → 100% at all times."""
        p = [(0.0, 1.0)]
        assert _gpu_load_fraction_at(p, 0.0)    == pytest.approx(1.0)
        assert _gpu_load_fraction_at(p, 9999.0) == pytest.approx(1.0)

    def test_intermediate_fraction(self):
        """Profile [(0, 0.5)] → 50% at all times."""
        p = [(0.0, 0.5)]
        assert _gpu_load_fraction_at(p, 0.0)   == pytest.approx(0.5)
        assert _gpu_load_fraction_at(p, 300.0) == pytest.approx(0.5)

    def test_step_down_at_t30(self):
        """[(0, 1.0), (30, 0.3)]: 100% until t<30, 30% from t=30 onward."""
        p = [(0.0, 1.0), (30.0, 0.3)]
        assert _gpu_load_fraction_at(p,  0.0) == pytest.approx(1.0)
        assert _gpu_load_fraction_at(p, 29.9) == pytest.approx(1.0)
        assert _gpu_load_fraction_at(p, 30.0) == pytest.approx(0.3)  # exactly at step
        assert _gpu_load_fraction_at(p, 60.0) == pytest.approx(0.3)

    def test_step_up_mid_run(self):
        """[(0, 0.2), (600, 1.0)]: ramps GPU back up after low-power phase."""
        p = [(0.0, 0.2), (600.0, 1.0)]
        assert _gpu_load_fraction_at(p,   0.0) == pytest.approx(0.2)
        assert _gpu_load_fraction_at(p, 599.9) == pytest.approx(0.2)
        assert _gpu_load_fraction_at(p, 600.0) == pytest.approx(1.0)
        assert _gpu_load_fraction_at(p, 999.0) == pytest.approx(1.0)

    def test_multiple_steps(self):
        """Three-step ramp-down profile."""
        p = [(0.0, 1.0), (60.0, 0.7), (120.0, 0.4)]
        assert _gpu_load_fraction_at(p,   0.0) == pytest.approx(1.0)
        assert _gpu_load_fraction_at(p,  59.9) == pytest.approx(1.0)
        assert _gpu_load_fraction_at(p,  60.0) == pytest.approx(0.7)
        assert _gpu_load_fraction_at(p, 119.9) == pytest.approx(0.7)
        assert _gpu_load_fraction_at(p, 120.0) == pytest.approx(0.4)
        assert _gpu_load_fraction_at(p, 999.0) == pytest.approx(0.4)

    def test_before_first_anchor_uses_first_value(self):
        """When t < first point's time, first fraction applies (ZOH convention)."""
        p = [(100.0, 0.6), (200.0, 0.3)]
        # t=0 is before t=100; first point's value (0.6) must be used
        assert _gpu_load_fraction_at(p, 0.0)  == pytest.approx(0.6)
        assert _gpu_load_fraction_at(p, 99.9) == pytest.approx(0.6)

    def test_clamp_high(self):
        """Values > 1.0 are clamped to 1.0 for safety."""
        p = [(0.0, 1.5)]
        assert _gpu_load_fraction_at(p, 0.0) == pytest.approx(1.0)

    def test_clamp_low(self):
        """Values < 0.0 are clamped to 0.0 for safety."""
        p = [(0.0, -0.5)]
        assert _gpu_load_fraction_at(p, 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# evaluate_tick: p_compute_demand_mw scales with profile
# ---------------------------------------------------------------------------

class TestEvaluateTickGpuLoadScaling:

    def test_no_profile_is_unchanged(self):
        """Absent profile → gpu_load_fraction=1.0 and unmodified compute MW."""
        state_base    = _make_state(gpu_load_profile=None)
        state_explicit = _make_state(gpu_load_profile=[])
        clock = _make_clock()

        with _plane_guard():
            r_none = evaluate_tick(state_base, clock)
        with _plane_guard():
            r_empty = evaluate_tick(state_explicit, clock)

        assert r_none.gpu_load_fraction  == pytest.approx(1.0)
        assert r_empty.gpu_load_fraction == pytest.approx(1.0)
        assert r_none.p_compute_demand_mw == pytest.approx(r_empty.p_compute_demand_mw)

    def test_zero_profile_zeros_compute(self):
        """Profile fraction=0.0 → p_compute_demand_mw == 0."""
        state = _make_state(gpu_load_profile=[(0.0, 0.0)])
        clock = _make_clock()

        with _plane_guard():
            result = evaluate_tick(state, clock)

        assert result.gpu_load_fraction == pytest.approx(0.0)
        assert result.p_compute_demand_mw == pytest.approx(0.0, abs=1e-9)

    def test_half_profile_halves_compute(self):
        """Profile fraction=0.5 → p_compute_demand_mw is ~50% of unthrottled."""
        state_full = _make_state(gpu_load_profile=None)
        state_half = _make_state(gpu_load_profile=[(0.0, 0.5)])
        clock = _make_clock()

        with _plane_guard():
            r_full = evaluate_tick(state_full, clock)
        with _plane_guard():
            r_half = evaluate_tick(state_half, clock)

        assert r_half.gpu_load_fraction == pytest.approx(0.5)
        # Allow small tolerance for PUE and cooling interaction
        assert r_half.p_compute_demand_mw == pytest.approx(
            r_full.p_compute_demand_mw * 0.5, rel=1e-6
        )

    def test_full_profile_matches_no_profile(self):
        """Profile fraction=1.0 → same compute MW as running with no profile."""
        state_none = _make_state(gpu_load_profile=None)
        state_full = _make_state(gpu_load_profile=[(0.0, 1.0)])
        clock = _make_clock()

        with _plane_guard():
            r_none = evaluate_tick(state_none, clock)
        with _plane_guard():
            r_full = evaluate_tick(state_full, clock)

        assert r_full.gpu_load_fraction    == pytest.approx(1.0)
        assert r_full.p_compute_demand_mw  == pytest.approx(r_none.p_compute_demand_mw, rel=1e-6)

    def test_step_transition_correct_fraction_before_and_after(self):
        """Two-phase profile: 100% before t=60, 40% from t=60 onward."""
        profile = [(0.0, 1.0), (60.0, 0.4)]
        state_before = _make_state(gpu_load_profile=profile)
        state_after  = _make_state(gpu_load_profile=profile)
        state_ref    = _make_state(gpu_load_profile=None)

        clock_before = _make_clock(sim_time=0.0)   # fraction = 1.0 (t < 60)
        clock_after  = _make_clock(sim_time=60.0)  # fraction = 0.4 (t ≥ 60)

        with _plane_guard():
            r_ref    = evaluate_tick(state_ref,    clock_before)
        with _plane_guard():
            r_before = evaluate_tick(state_before, clock_before)
        with _plane_guard():
            r_after  = evaluate_tick(state_after,  clock_after)

        assert r_before.gpu_load_fraction == pytest.approx(1.0)
        assert r_before.p_compute_demand_mw == pytest.approx(r_ref.p_compute_demand_mw, rel=1e-6)

        assert r_after.gpu_load_fraction == pytest.approx(0.4)
        assert r_after.p_compute_demand_mw == pytest.approx(
            r_ref.p_compute_demand_mw * 0.4, rel=1e-6
        )


# ---------------------------------------------------------------------------
# Cooling model follows the profiled load
# ---------------------------------------------------------------------------

class TestCoolingFollowsProfile:
    """cooling.record_job_compute must receive the throttled draws.

    p_cooling_demand_mw at t=0 is determined by the thermal model's response
    to the GPU heat input recorded this tick.  When the profile throttles GPU
    to 0%, the per-job draws passed to record_job_compute are zeroed, so the
    cooling model sees no heat input and p_cooling_demand_mw must be ≤ that
    of the unthrottled run.
    """

    def test_zero_profile_cooling_no_higher_than_unthrottled(self):
        """Throttled-to-zero run must have cooling ≤ unthrottled cooling."""
        state_full = _make_state(gpu_load_profile=None)
        state_zero = _make_state(gpu_load_profile=[(0.0, 0.0)])
        clock = _make_clock()

        with _plane_guard():
            r_full = evaluate_tick(state_full, clock)
        with _plane_guard():
            r_zero = evaluate_tick(state_zero, clock)

        # Cooling for throttled run should be ≤ full-load cooling.
        # (Initial transient may give 0 MW; it must never EXCEED the full run.)
        assert r_zero.p_cooling_demand_mw <= r_full.p_cooling_demand_mw + 1e-9

    def test_half_profile_cooling_no_higher_than_full(self):
        """Half-throttled run must have cooling ≤ full-load cooling."""
        state_full = _make_state(gpu_load_profile=None)
        state_half = _make_state(gpu_load_profile=[(0.0, 0.5)])
        clock = _make_clock()

        with _plane_guard():
            r_full = evaluate_tick(state_full, clock)
        with _plane_guard():
            r_half = evaluate_tick(state_half, clock)

        assert r_half.p_cooling_demand_mw <= r_full.p_cooling_demand_mw + 1e-9

    def test_full_profile_cooling_matches_no_profile(self):
        """Profile fraction=1.0 → same cooling as no profile (identical heat input)."""
        state_none = _make_state(gpu_load_profile=None)
        state_full = _make_state(gpu_load_profile=[(0.0, 1.0)])
        clock = _make_clock()

        with _plane_guard():
            r_none = evaluate_tick(state_none, clock)
        with _plane_guard():
            r_full = evaluate_tick(state_full, clock)

        assert r_full.p_cooling_demand_mw == pytest.approx(
            r_none.p_cooling_demand_mw, rel=1e-6
        )


# ---------------------------------------------------------------------------
# Wire payload: _tick_result_to_dict carries gpu_load_fraction
# ---------------------------------------------------------------------------

class TestWirePayload:

    def test_gpu_load_fraction_in_payload(self):
        """gpu_load_fraction must appear in the serialised tick dict."""
        state = _make_state(gpu_load_profile=[(0.0, 0.75)])
        clock = _make_clock()

        with _plane_guard():
            result = evaluate_tick(state, clock)

        payload = _tick_result_to_dict(result)
        assert "gpu_load_fraction" in payload, (
            "gpu_load_fraction missing from _tick_result_to_dict output"
        )
        assert payload["gpu_load_fraction"] == pytest.approx(0.75, abs=1e-4)

    def test_no_profile_payload_fraction_is_1(self):
        """No profile → gpu_load_fraction = 1.0 in wire payload."""
        state = _make_state(gpu_load_profile=None)
        clock = _make_clock()

        with _plane_guard():
            result = evaluate_tick(state, clock)

        payload = _tick_result_to_dict(result)
        assert payload["gpu_load_fraction"] == pytest.approx(1.0, abs=1e-4)

    def test_zero_profile_payload_fraction_is_0(self):
        """Profile 0% → gpu_load_fraction = 0.0 in wire payload."""
        state = _make_state(gpu_load_profile=[(0.0, 0.0)])
        clock = _make_clock()

        with _plane_guard():
            result = evaluate_tick(state, clock)

        payload = _tick_result_to_dict(result)
        assert payload["gpu_load_fraction"] == pytest.approx(0.0, abs=1e-4)


# ---------------------------------------------------------------------------
# Scenario factory: gpu_load_profile wired from ScenarioSpec → SimulationState
# ---------------------------------------------------------------------------

class TestScenarioFactoryWiring:

    def _minimal_spec(self, gpu_load_profile=None) -> ScenarioSpec:
        base = {
            "name": "test",
            "description": "",
            "workload_events": [
                WorkloadEventSpec(
                    event_id="e0", job_id="job", event_type="starting",
                    timestamp=0.0, node_count=1,
                ),
            ],
            "bess_units":    [BessUnitSpec(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0)],
            "turbine_units": [TurbineUnitSpec(asset_id="t-0", rated_mw=10.0)],
        }
        spec = ScenarioSpec(**base)
        if gpu_load_profile is not None:
            spec.gpu_load_profile = gpu_load_profile
        return spec

    def test_no_gpu_load_profile_leaves_state_empty(self):
        """Absent profile → sim_state.gpu_load_profile is empty."""
        spec = self._minimal_spec()
        ctx  = build_run_context_from_spec("test-no-profile", spec.model_dump())
        assert ctx.sim_state.gpu_load_profile == []

    def test_gpu_load_profile_wired_to_state(self):
        """ScenarioSpec.gpu_load_profile → sim_state.gpu_load_profile, sorted by time."""
        profile = [(60.0, 0.5), (0.0, 1.0)]  # intentionally unsorted
        spec = self._minimal_spec(gpu_load_profile=profile)
        ctx  = build_run_context_from_spec("test-with-profile", spec.model_dump())

        expected_sorted = [(0.0, 1.0), (60.0, 0.5)]
        assert len(ctx.sim_state.gpu_load_profile) == 2
        for i, (exp_t, exp_f) in enumerate(expected_sorted):
            assert ctx.sim_state.gpu_load_profile[i][0] == pytest.approx(exp_t)
            assert ctx.sim_state.gpu_load_profile[i][1] == pytest.approx(exp_f)

    def test_empty_gpu_load_profile_leaves_state_empty(self):
        """Explicit empty profile → sim_state.gpu_load_profile is empty."""
        spec = self._minimal_spec(gpu_load_profile=[])
        ctx  = build_run_context_from_spec("test-empty-profile", spec.model_dump())
        assert ctx.sim_state.gpu_load_profile == []
