"""
Whitebox tests for the deterministic core -- Design Spec Section 12,
"direct extension of the functional spec's own plan (source spec
Section 16, Addendum A)". No asyncio here: this is the pure-Python
layer, tested independently of the run-management/concurrency layer.
"""

import math

from core.asset_modules import CoolingModule, GPUModule, TurbineModule
from core.dispatch import DispatchArbitrator
from core.models import HardwareProfile, SiteConfig, TurbineConfig, WorkloadEventType, WorkloadSignal, WorkloadClass


def test_tc01_instantaneous_compute_term_single_profile():
    """Source spec TC-01: 10 nodes, enterprise_8gpu_air (10.2 kW), PUE_base=1.03
    -> P_compute ~= 0.1051 MW, within +/-0.1%."""
    site = SiteConfig(site_id="s1", pue_base=1.03)
    library = {"enterprise_8gpu_air": HardwareProfile("enterprise_8gpu_air", rated_kw=10.2)}
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=library)
    gpu.apply_signal(
        WorkloadSignal(
            event_id="e1", job_id="job-1", event_type=WorkloadEventType.STARTING,
            timestamp=0.0, hardware_profile_id="enterprise_8gpu_air", node_count=10,
            workload_class=WorkloadClass.TRAINING, site_id="s1",
        )
    )
    expected = 10 * 10.2 * 1.03 / 1000.0
    assert math.isclose(gpu.output_mw(), expected, rel_tol=1e-3)


def test_tc02_cooling_zero_before_thermal_delay():
    """Source spec TC-02: evaluate at t0+60s (< default dt_thermal=90s) -> P_cooling == 0."""
    site = SiteConfig(site_id="s1", dt_thermal_seconds=90.0)
    cooling = CoolingModule(asset_id="cool-0", site=site)
    cooling.record_compute_sample(0.0, 5.0)
    cooling.record_compute_sample(60.0, 5.0)
    cooling.advance(60.0, 5.0)
    assert cooling.output_mw() == 0.0


def test_tc03_cooling_converges_to_alpha_max_at_steady_state():
    """Source spec TC-03: held constant >= dt_thermal + 5*tau -> P_cooling
    converges to alpha_max * P_compute within 2% of asymptote."""
    site = SiteConfig(site_id="s1", dt_thermal_seconds=90.0, tau_seconds=20.0, alpha_max=0.20)
    cooling = CoolingModule(asset_id="cool-0", site=site)
    p_compute = 10.0
    t = 0.0
    while t <= 90 + 5 * 20 + 5:
        cooling.record_compute_sample(t, p_compute)
        cooling.advance(t, 5.0)
        t += 5.0
    expected_asymptote = 0.20 * p_compute
    assert math.isclose(cooling.output_mw(), expected_asymptote, rel_tol=0.02)


def test_tc10_insufficient_reserve_worked_example():
    """Source spec TC-10 / Section 7.3: 20 MW job, dt_lead=30s, single
    turbine r_asset=0.2 MW/s -> alert fires, gap ~70s, peak shortfall 14 MW."""
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=25.0))
    arbitrator = DispatchArbitrator(turbines=[turbine], bess_units=[])

    alert = arbitrator.stage_for_predicted_step(delta_p_mw=20.0, dt_lead_seconds=30.0, sim_time=0.0)

    assert alert is not None
    assert math.isclose(alert.gap_duration_s, 70.0, abs_tol=1e-6)
    assert math.isclose(alert.shortfall_mw, 14.0, abs_tol=1e-6)


def test_tc11_sufficient_reserve_no_false_alert():
    """Source spec TC-11: 5 MW job, dt_lead=60s, r_asset=0.2 MW/s
    -> required ramp 25s < 60s lead -> no alert."""
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=25.0))
    arbitrator = DispatchArbitrator(turbines=[turbine], bess_units=[])

    alert = arbitrator.stage_for_predicted_step(delta_p_mw=5.0, dt_lead_seconds=60.0, sim_time=0.0)

    assert alert is None


def test_turbine_ramps_at_configured_rate():
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=25.0))
    turbine.stage_target(6.0)
    turbine.advance(sim_time=0.0, dt_seconds=30.0)
    # 0.2 MW/s * 30s = 6.0 MW -> exactly reaches target
    assert math.isclose(turbine.output_mw(), 6.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# D7: §5.1 onboarding alert deduplication
# ---------------------------------------------------------------------------

def test_d7_onboarding_alert_fires_once_per_unique_profile_id():
    """§5.1: one onboarding alert per unique unmapped hardware_profile_id per site.

    Three jobs all carrying the same unmapped profile_id must produce exactly
    one alert total.  A fourth job carrying a different unmapped profile_id must
    produce exactly one more alert — not zero, not two.

    The alert surfaces on TickResult.unrecognised_profile_alerts (a frozenset of
    profile_id strings) so it reaches operator subscribers, not only the log.
    It is non-empty on at most one tick per unique profile_id per run.
    """
    from core.simulation_core import SimulationState, evaluate_tick
    from core.asset_modules import BessModule, CoolingModule, SolarModule
    from core.models import (
        BessConfig, SolarConfig, TurbineConfig,
        WorkloadClass, WorkloadEventType, WorkloadSignal,
    )

    site = SiteConfig(site_id="site-onboard", pue_base=1.03, uncalibrated=False)
    # Empty hardware_library — every profile is unmapped.
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library={})
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=10.0))
    cooling = CoolingModule(asset_id="cool-0", site=site)

    state = SimulationState(
        run_id="run-onboard",
        site=site,
        gpu_modules=[gpu],
        turbines=[turbine],
        bess_units=[],
        solar_arrays=[],
        cooling=cooling,
    )

    def _signal(job_id: str, profile_id: str, t: float) -> WorkloadSignal:
        return WorkloadSignal(
            event_id=f"e-{job_id}",
            job_id=job_id,
            event_type=WorkloadEventType.STARTING,
            timestamp=t,
            hardware_profile_id=profile_id,
            node_count=4,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-onboard",
        )

    UNMAPPED_A = "missing-sku-a"
    UNMAPPED_B = "missing-sku-b"
    DT = 5.0

    # --- Three jobs, all UNMAPPED_A ---
    alerts_seen: list[frozenset[str]] = []
    t = 0.0
    for i in range(3):
        state.apply_workload_signal(_signal(f"job-{i}", UNMAPPED_A, t), dt_lead_seconds=30.0)
        tick = evaluate_tick(state, t, DT)
        if tick.unrecognised_profile_alerts:
            alerts_seen.append(tick.unrecognised_profile_alerts)
        t += DT

    assert len(alerts_seen) == 1, (
        f"Expected exactly 1 alert for 3 jobs on the same unmapped profile_id "
        f"({UNMAPPED_A!r}); got {len(alerts_seen)}: {alerts_seen}"
    )
    assert alerts_seen[0] == frozenset({UNMAPPED_A}), (
        f"Alert frozenset should contain only {UNMAPPED_A!r}; got {alerts_seen[0]}"
    )

    # --- Fourth job, different unmapped profile_id (UNMAPPED_B) ---
    state.apply_workload_signal(_signal("job-3", UNMAPPED_B, t), dt_lead_seconds=30.0)
    tick_b = evaluate_tick(state, t, DT)

    assert tick_b.unrecognised_profile_alerts == frozenset({UNMAPPED_B}), (
        f"Fourth job with a new unmapped profile_id {UNMAPPED_B!r} must produce "
        f"exactly one alert; got {tick_b.unrecognised_profile_alerts!r}"
    )
