"""
Whitebox tests for the deterministic core -- Design Spec Section 12,
"direct extension of the functional spec's own plan (source spec
Section 16, Addendum A)". No asyncio here: this is the pure-Python
layer, tested independently of the run-management/concurrency layer.
"""

import math

from core.asset_modules import BessModule, CoolingModule, GPUModule, IrradianceProfile, SolarModule, TurbineModule
from core.dispatch import DispatchArbitrator
from core.models import BessConfig, HardwareProfile, SiteConfig, SolarConfig, TurbineConfig, WorkloadEventType, WorkloadSignal, WorkloadClass


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


# ---------------------------------------------------------------------------
# D8 — staging sizes against P_dispatch_required, not P_total
# ---------------------------------------------------------------------------

def test_d8_staging_sizes_against_dispatch_required_not_p_total():
    """D8: stage_for_predicted_step() must receive the increment this job
    adds to P_dispatch_required, net of renewable output at staging time.

    A job starting while a solar array is already producing must cause a
    strictly smaller turbine staged-target than the same job in a scenario
    with no renewable output.  If the staging path still uses total site
    compute (old bug) or omits the renewable offset, the two targets are
    equal and this assertion fails.
    """
    from core.simulation_core import SimulationState, evaluate_tick

    PROFILE_ID = "enterprise_8gpu_air"
    NODE_COUNT = 10
    RATED_KW = 10.2
    PUE = 1.03
    SOLAR_MW = 0.060  # 60 kW — covers more than half the job's compute draw

    library = {PROFILE_ID: HardwareProfile(PROFILE_ID, rated_kw=RATED_KW)}
    site = SiteConfig(site_id="site-d8", pue_base=PUE)

    def _make_state(with_solar: bool) -> tuple:
        turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=10.0))
        cooling = CoolingModule(asset_id="cool-0", site=site)
        bess = BessModule(BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0))
        if with_solar:
            solar = SolarModule(
                SolarConfig(asset_id="solar-0", rated_mw=SOLAR_MW),
                irradiance_profile=IrradianceProfile([(0.0, 1.0), (600.0, 1.0)]),
            )
            # Pre-advance so output_mw() returns SOLAR_MW at the moment the
            # staging signal arrives (simulates solar already running when a
            # new job starts mid-run).
            solar.advance(0.0, 5.0)
            solar_arrays = [solar]
        else:
            solar_arrays = []
        state = SimulationState(
            run_id=f"run-d8-{'solar' if with_solar else 'nosolar'}",
            site=site,
            gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=library)],
            turbines=[turbine],
            bess_units=[bess],
            solar_arrays=solar_arrays,
            cooling=cooling,
        )
        return state, turbine

    signal = WorkloadSignal(
        event_id="e1",
        job_id="job-1",
        event_type=WorkloadEventType.STARTING,
        timestamp=0.0,
        hardware_profile_id=PROFILE_ID,
        node_count=NODE_COUNT,
        workload_class=WorkloadClass.TRAINING,
        site_id="site-d8",
    )

    # Scenario A: no renewables — staged target equals full job compute draw
    state_no_solar, turbine_no_solar = _make_state(False)
    state_no_solar.apply_workload_signal(signal, dt_lead_seconds=30.0)
    target_no_solar = turbine_no_solar._target_mw

    # Scenario B: solar pre-advanced to SOLAR_MW — staged target must be smaller
    state_with_solar, turbine_with_solar = _make_state(True)
    state_with_solar.apply_workload_signal(signal, dt_lead_seconds=30.0)
    target_with_solar = turbine_with_solar._target_mw

    assert target_with_solar < target_no_solar, (
        f"Staging with {SOLAR_MW} MW solar (target={target_with_solar:.5f} MW) must be "
        f"strictly less than without solar (target={target_no_solar:.5f} MW). "
        f"The staging path is not offsetting by renewable output."
    )


# ---------------------------------------------------------------------------
# D9 — demo-20mw with PROTO-7 solar sizing produces non-zero BESS output
# ---------------------------------------------------------------------------

def test_d9_demo_20mw_produces_nonzero_bess_output():
    """D9: after correcting the demo-20mw node count to 1900 (≈ 19.96 MW) and
    sizing solar at 25% of peak compute (PROTO-7 ≈ 4.99 MW), the dispatch
    arbitrator must call on the BESS at some tick.

    This confirms that the PROTO-7 solar fraction is not so large it clamps
    P_dispatch_required to zero (the old degenerate scenario with 16 MW solar
    against a 2.5 MW load), and that the single default turbine cannot ramp
    fast enough within dt_lead=30 s to cover a ≈ 15 MW requirement alone.
    """
    from core.simulation_core import SimulationState, evaluate_tick

    NODE_COUNT = 1900          # corrected to produce ≈ 19.96 MW (was 200 → ~2.1 MW)
    PROFILE_ID = "enterprise_8gpu_air"
    RATED_KW = 10.2
    PUE = 1.03

    library = {PROFILE_ID: HardwareProfile(PROFILE_ID, rated_kw=RATED_KW)}
    site = SiteConfig(site_id="site-demo20", pue_base=PUE)

    peak_compute_mw = NODE_COUNT * RATED_KW * PUE / 1000.0          # ≈ 19.957 MW
    solar_rated_mw = 0.25 * peak_compute_mw                          # PROTO-7 ≈ 4.989 MW

    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=10.0))
    bess = BessModule(BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0))
    solar = SolarModule(
        SolarConfig(asset_id="solar-0", rated_mw=solar_rated_mw),
        irradiance_profile=IrradianceProfile([(0.0, 1.0), (600.0, 1.0)]),
    )
    cooling = CoolingModule(asset_id="cool-0", site=site)

    state = SimulationState(
        run_id="run-d9-demo20",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=library)],
        turbines=[turbine],
        bess_units=[bess],
        solar_arrays=[solar],
        cooling=cooling,
    )

    # Apply the starting signal.  Solar has not advanced yet (t=0 pre-tick),
    # so the staging delta equals the full job compute draw — the turbine is
    # staged to its rated_mw cap (10 MW), well below the ≈ 15 MW dispatch req.
    state.apply_workload_signal(
        WorkloadSignal(
            event_id="e1",
            job_id="job-big",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id=PROFILE_ID,
            node_count=NODE_COUNT,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-demo20",
        ),
        dt_lead_seconds=30.0,
    )

    bess_outputs: list[float] = []
    t = 0.0
    DT = 5.0
    for _ in range(20):   # 100 simulated seconds — plenty of time to see BESS fire
        tick = evaluate_tick(state, t, DT)
        bess_outputs.append(tick.bess_output_mw)
        t += DT

    assert any(b > 0.0 for b in bess_outputs), (
        f"demo-20mw with PROTO-7 solar sizing must produce non-zero BESS output "
        f"at some tick within the first 100 s; all values were zero.\n"
        f"  solar_rated_mw={solar_rated_mw:.3f}, peak_compute_mw={peak_compute_mw:.3f}\n"
        f"  bess_outputs (first 10 ticks): {bess_outputs[:10]}"
    )


# ---------------------------------------------------------------------------
# D10 — demo-20mw must demonstrate the full §7.2 arc: fire then taper
# ---------------------------------------------------------------------------

def test_d10_demo_20mw_bess_fires_and_tapers():
    """D10 / PROTO-8: with turbine_rated_mw=25 MW the turbine can reach
    steady-state P_dispatch_required (~19 MW at full cooling), so the §7.2
    arc completes:

        1. BESS bridges the gap while turbine ramps (bess_output > 0)
        2. Turbine catches up and sustains coverage for 10 s
        3. BESS tapers to zero and stays there to run end
        4. Turbine carries the full load at the final tick

    The old fleet (turbine_rated_mw=10 MW, pinned below the ~19 MW
    steady-state load) made the taper unreachable — turbine was always
    short, BESS ran at rated power for the entire run.
    """
    from core.simulation_core import SimulationState, evaluate_tick

    NODE_COUNT = 1900
    PROFILE_ID = "enterprise_8gpu_air"
    RATED_KW = 10.2
    PUE = 1.03
    TURBINE_RATED_MW = 25.0   # PROTO-8 — CHOSEN, no measured basis

    library = {PROFILE_ID: HardwareProfile(PROFILE_ID, rated_kw=RATED_KW)}
    site = SiteConfig(site_id="site-d10", pue_base=PUE)

    peak_compute_mw = NODE_COUNT * RATED_KW * PUE / 1000.0     # ~19.957 MW
    solar_rated_mw = 0.25 * peak_compute_mw                     # PROTO-7 ~4.989 MW

    turbine = TurbineModule(TurbineConfig(
        asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=TURBINE_RATED_MW
    ))
    bess = BessModule(BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0))
    solar = SolarModule(
        SolarConfig(asset_id="solar-0", rated_mw=solar_rated_mw),
        irradiance_profile=IrradianceProfile([(0.0, 1.0), (600.0, 1.0)]),
    )
    cooling = CoolingModule(asset_id="cool-0", site=site)

    state = SimulationState(
        run_id="run-d10",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=library)],
        turbines=[turbine],
        bess_units=[bess],
        solar_arrays=[solar],
        cooling=cooling,
    )

    # Solar has not advanced yet at t=0, so staging delta equals the full
    # compute draw (19.957 MW).  Turbine stages to 19.957 MW (fits within
    # rated 25 MW).  Ramp time = 99.8 s; run is 300 s.
    state.apply_workload_signal(
        WorkloadSignal(
            event_id="e1",
            job_id="job-big",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id=PROFILE_ID,
            node_count=NODE_COUNT,
            workload_class=WorkloadClass.TRAINING,
            site_id="site-d10",
        ),
        dt_lead_seconds=30.0,
    )

    bess_outputs: list[float] = []
    turbine_outputs: list[float] = []
    t = 0.0
    DT = 5.0
    for _ in range(60):   # 300 simulated seconds
        tick = evaluate_tick(state, t, DT)
        bess_outputs.append(tick.bess_output_mw)
        turbine_outputs.append(tick.turbine_output_mw)
        t += DT

    # 1. BESS must fire during the ramp (ticks 1-20, t=0-95 s).
    #    At tick 1: turbine output = 1.0 MW, P_dispatch ~14.97 MW,
    #    shortfall ~13.97 MW > BESS rated 5 MW → BESS discharges at 5 MW.
    assert any(b > 0.0 for b in bess_outputs[:20]), (
        "BESS must discharge during ramp (ticks 1-20 / t=0-95 s).\n"
        f"  bess_outputs[:20] = {bess_outputs[:20]}"
    )

    # 2. BESS must taper to zero before run end.
    #    Turbine reaches AT_TARGET (~19.957 MW) near t=100 s, which exceeds
    #    P_dispatch_required (~16-19 MW depending on cooling phase).
    #    After 10 s sustained coverage the taper fires.
    #    Allow until tick 30 (t=145 s) for the taper, then assert silence.
    taper_tick = next(
        (i for i, b in enumerate(bess_outputs) if b == 0.0 and i >= 20),
        None,
    )
    assert taper_tick is not None and taper_tick < 30, (
        f"BESS must taper to zero by tick 30 (t=145 s); taper not observed.\n"
        f"  bess_outputs = {bess_outputs}"
    )
    assert all(b == 0.0 for b in bess_outputs[taper_tick:]), (
        f"Once BESS tapers it must stay at zero; re-fired after tick {taper_tick}.\n"
        f"  bess_outputs[{taper_tick}:] = {bess_outputs[taper_tick:]}"
    )

    # 3. Turbine must carry the load at the final tick.
    assert turbine_outputs[-1] > 0.0, (
        f"Turbine must be running at end of run; "
        f"final output = {turbine_outputs[-1]:.3f} MW"
    )


# ---------------------------------------------------------------------------
# D11 — reserve check must be power-limited, not just energy-limited
# ---------------------------------------------------------------------------

def test_d11_reserve_alert_fires_when_bess_power_insufficient():
    """D11: max_sustainable_seconds must return 0 when discharge_mw > rated_mw.

    The pre-D11 code computed energy / discharge_mw regardless of the unit's
    power rating, producing a finite (but physically impossible) sustainable
    duration and a false-negative reserve check.

    §7.2 step 4: "max sustainable discharge duration AT THE REQUIRED POWER LEVEL."
    Above rating that duration is zero — the unit cannot produce the power at all.

    This test exercises the case TC-10 does NOT cover: a power-limited BESS
    (ample stored energy, insufficient rated output) must fire the alert.
    """
    # Construct the scenario directly via DispatchArbitrator so we exercise
    # the reserve-check arithmetic without running a full tick loop.
    #
    # Fleet: 1 turbine at 0.2 MW/s, rated 100 MW (large — not the constraint).
    #        1 BESS rated 5.0 MW, 10.0 MWh (ample energy — not the constraint).
    # Job:   delta_p_mw = 20 MW, dt_lead = 30 s.
    #   required_ramp_s  = 20 / 0.2          = 100 s
    #   gap_s            = 100 - 30          =  70 s
    #   already_ramped   = 0.2 × 30          =   6 MW
    #   peak_shortfall   = 20 - 6            =  14 MW
    #   peak_shortfall / 1 BESS              =  14 MW  > rated 5 MW
    #   → max_sustainable_seconds(14) must return 0 → 0 < 70 → alert fires.
    #
    # Without D11: sustainable_s = (10.0 / 14) × 3600 = 2571 s >> 70 s → NO alert (bug).
    turbine = TurbineModule(TurbineConfig(
        asset_id="t-d11", r_asset_mw_per_s=0.2, rated_mw=100.0
    ))
    bess = BessModule(BessConfig(
        asset_id="bess-d11",
        rated_mw=5.0,
        usable_mwh=10.0,   # ample energy — the constraint is power, not energy
    ))

    arbitrator = DispatchArbitrator(turbines=[turbine], bess_units=[bess])
    alert = arbitrator.stage_for_predicted_step(
        delta_p_mw=20.0,
        dt_lead_seconds=30.0,
        sim_time=0.0,
    )

    assert alert is not None, (
        "InsufficientReserveAlert must fire when peak shortfall (14 MW) exceeds "
        "BESS rated power (5 MW), even though 10 MWh of stored energy would "
        "notionally last 2571 s at that rate.  max_sustainable_seconds must "
        "return 0 when discharge_mw > rated_mw (D11 power-ceiling fix)."
    )

    # Also directly verify the power-ceiling behaviour on the BESS instance.
    assert bess.max_sustainable_seconds(14.0) == 0.0, (
        "max_sustainable_seconds(14.0) must return 0.0 because 14 MW > rated 5 MW; "
        f"got {bess.max_sustainable_seconds(14.0)}"
    )
    # Energy-limited path still works: at or below rated power, energy governs.
    expected_s = (10.0 / 4.0) * 3600.0   # 4 MW ≤ 5 MW rated → 9000 s
    assert bess.max_sustainable_seconds(4.0) == expected_s, (
        f"max_sustainable_seconds(4.0) should be {expected_s} s (energy-limited); "
        f"got {bess.max_sustainable_seconds(4.0)}"
    )
