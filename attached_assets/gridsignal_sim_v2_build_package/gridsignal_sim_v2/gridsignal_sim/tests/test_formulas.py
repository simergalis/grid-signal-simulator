"""
Whitebox tests for the deterministic core -- Design Spec Section 12,
"direct extension of the functional spec's own plan (source spec
Section 16, Addendum A)". No asyncio here: this is the pure-Python
layer, tested independently of the run-management/concurrency layer.
"""

import math

from core.asset_modules import BessModule, CoolingModule, GPUModule, IrradianceProfile, SolarModule, TurbineModule
from core.dispatch import CheckpointClassifier, CheckpointState, DispatchArbitrator
from core.models import BessConfig, HardwareProfile, SiteConfig, SolarConfig, TurbineConfig, WorkloadEventType, WorkloadSignal, WorkloadClass


def test_tc01_instantaneous_compute_term_single_profile():
    """Source spec TC-01: 10 nodes, enterprise_8gpu_air (10.2 kW), PUE_base=1.03
    -> P_compute ~= 0.1051 MW, within +/-0.1%.

    Step 3 Item 2 (Δt_lead ramp) re-anchor: draw starts near zero at STARTING
    (container init phase) and reaches full TDP after the ramp completes.
    The TC-01 target value is unchanged; evaluation is re-anchored at ramp
    completion rather than at tick 0, which was only correct when advance()
    was a no-op.  The pre-ramp assertion is new (verifies the ramp actually
    starts low) and does not weaken the original assertion.
    """
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

    # NEW: verify ramp starts low (§6.1 container-init phase, PROTO-1 shape).
    # This assertion was not present before Item 2 because advance() was a no-op
    # and output_mw() immediately returned full TDP.
    assert gpu.output_mw() < expected * 0.5, (
        f"draw must start below 50 % of full TDP at STARTING; "
        f"got {gpu.output_mw():.4f} MW vs full TDP {expected:.4f} MW"
    )

    # Advance past ramp completion (default ramp_seconds=45 s; advance 50 s).
    # RE-ANCHOR: the original assertion evaluated immediately after apply_signal.
    # After Item 2, output_mw() is partial until advance() has run for >= ramp_seconds.
    # The expected value is identical; only the evaluation point moves.
    t = 0.0
    while t < gpu.ramp_seconds + 5.0:
        gpu.advance(t, 5.0)
        t += 5.0

    assert math.isclose(gpu.output_mw(), expected, rel_tol=1e-3), (
        f"P_compute after ramp completion: expected {expected:.6f} MW, "
        f"got {gpu.output_mw():.6f} MW"
    )


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

    # 1. BESS must fire at some point during the first 20 ticks (0–95 s).
    #    Step 3 Item 2 re-anchor: with the Δt_lead ramp, compute starts near 0
    #    and solar covers the load for the first few ticks, so BESS does NOT
    #    fire at tick 1.  It fires once the ramp drives P_compute above P_solar
    #    and the turbine can't yet cover the gap — typically around tick 3–4
    #    (t≈15–20 s).  The assertion is unchanged (any > 0 in [:20]); only the
    #    explanatory comment is updated.
    assert any(b > 0.0 for b in bess_outputs[:20]), (
        "BESS must discharge during ramp (within ticks 0-19 / t=0-95 s).\n"
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


# ---------------------------------------------------------------------------
# Step 3 Item 1 — per-job draw attribution for checkpoint classifier
# ---------------------------------------------------------------------------

def test_step3_item1_per_job_draw_detects_small_job_checkpoint():
    """Step 3 Item 1: checkpoint dip on a small job must be visible to the
    classifier.  The old code passed the site-wide p_compute_mw sum; a 20%
    dip in a 1 MW job is a ~1.5% dip in a 50 MW site and never crosses §6.2's
    15% threshold.

    Setup
    -----
    One GPU module carrying two training jobs:
      - large:  100 nodes × enterprise_8gpu_air → 1.0506 MW
      - small:   10 nodes × enterprise_8gpu_air → 0.1051 MW
    Site total: 1.1557 MW

    After scaling the small job from 10 → 1 node:
      - small draw drops to 0.0105 MW  (–90 % of per-job median) → IN_VALLEY
      - site total drops to 1.0612 MW  (– 8.2% of site median)    → NORMAL

    The test runs the classifier directly (no full evaluate_tick loop needed)
    so it is fast and does not depend on runtime/ plumbing.
    """
    PROFILE_ID = "enterprise_8gpu_air"
    RATED_KW = 10.2
    PUE = 1.03

    large_draw = 100 * RATED_KW * PUE / 1000.0   # 1.0506 MW
    small_draw = 10  * RATED_KW * PUE / 1000.0   # 0.1051 MW
    small_draw_dip = 1 * RATED_KW * PUE / 1000.0 # 0.0105 MW  (scale 10→1 node)

    site_total_before = large_draw + small_draw     # 1.1557 MW
    site_total_after  = large_draw + small_draw_dip # 1.0612 MW

    DT = 5.0
    BASELINE_TICKS = 12   # 60 s — enough for a stable trailing median

    # ------------------------------------------------------------------ #
    # Path A: per-job attribution (new code) — dip MUST be detected       #
    # ------------------------------------------------------------------ #
    clf_per_job = CheckpointClassifier()
    t = 0.0
    for _ in range(BASELINE_TICKS):
        clf_per_job.record_and_classify("large", t, large_draw)
        clf_per_job.record_and_classify("small", t, small_draw)
        t += DT

    # First dip tick — small job scaled down to 1 node
    clf_per_job.record_and_classify("large", t, large_draw)
    state_small_after = clf_per_job.record_and_classify("small", t, small_draw_dip)

    assert state_small_after == CheckpointState.IN_VALLEY, (
        f"Per-job attribution must detect a 90% draw dip on the small job "
        f"(small_draw={small_draw:.4f} MW → {small_draw_dip:.4f} MW).\n"
        f"  median ≈ {small_draw:.4f} MW, threshold = {small_draw * 0.85:.4f} MW, "
        f"  got state={state_small_after!r}"
    )

    # ------------------------------------------------------------------ #
    # Path B: site-wide aggregate (old code) — dip must NOT be detected   #
    # ------------------------------------------------------------------ #
    # Use the same job id ("small") so the median builds from the same
    # baseline draw — here we pretend the classifier only sees the total.
    clf_aggregate = CheckpointClassifier()
    t = 0.0
    for _ in range(BASELINE_TICKS):
        clf_aggregate.record_and_classify("small", t, site_total_before)
        t += DT

    state_agg_after = clf_aggregate.record_and_classify("small", t, site_total_after)

    assert state_agg_after == CheckpointState.NORMAL, (
        f"Site-wide aggregate draw must NOT detect the small-job dip "
        f"(site total drops only {(1 - site_total_after/site_total_before)*100:.1f}% "
        f"< 15% threshold).\n"
        f"  Expected NORMAL, got {state_agg_after!r}"
    )

    # ------------------------------------------------------------------ #
    # Sanity: per_job_compute_mw() accessor returns the right values       #
    # ------------------------------------------------------------------ #
    site = SiteConfig(site_id="site-item1", pue_base=PUE)
    library = {PROFILE_ID: HardwareProfile(PROFILE_ID, rated_kw=RATED_KW)}
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=library)

    from core.models import WorkloadClass
    for job_id, n in [("large", 100), ("small", 10)]:
        gpu.apply_signal(WorkloadSignal(
            event_id=f"e-{job_id}", job_id=job_id,
            event_type=WorkloadEventType.STARTING, timestamp=0.0,
            hardware_profile_id=PROFILE_ID, node_count=n,
            workload_class=WorkloadClass.TRAINING, site_id="site-item1",
        ))

    # Step 3 Item 2 re-anchor: per_job_compute_mw() now returns the RAMPED draw,
    # which is near-zero immediately after apply_signal(STARTING).  Advance past
    # ramp completion (default 45 s; advance 50 s) before checking the values.
    # The expected values are unchanged; only the evaluation point moves.
    t_sanity = 0.0
    while t_sanity < gpu.ramp_seconds + 5.0:
        gpu.advance(t_sanity, 5.0)
        t_sanity += 5.0

    assert abs(gpu.per_job_compute_mw("large") - large_draw) < 1e-9, (
        f"per_job_compute_mw('large') after ramp: expected {large_draw:.6f}, "
        f"got {gpu.per_job_compute_mw('large'):.6f}"
    )
    assert abs(gpu.per_job_compute_mw("small") - small_draw) < 1e-9, (
        f"per_job_compute_mw('small') after ramp: expected {small_draw:.6f}, "
        f"got {gpu.per_job_compute_mw('small'):.6f}"
    )
    # Sum of per-job draws must equal module output_mw() (also after ramp)
    assert abs(
        gpu.per_job_compute_mw("large") + gpu.per_job_compute_mw("small")
        - gpu.output_mw()
    ) < 1e-9, "sum of per_job_compute_mw() values must equal output_mw()"


# ---------------------------------------------------------------------------
# Step 3 Item 3 — per-job cooling superposition
# ---------------------------------------------------------------------------

def test_item3_concurrent_job_cooling_no_dip_and_smooth_rise():
    """Step 3 Item 3 (a): second concurrent job's cooling rises smoothly.

    Pre-fix behaviour: with a single aggregate alpha already at alpha_max,
    job B's lagged compute arrives as a +2.000 MW step in one tick — the
    aliasing §8 warns against.  Post-fix: job B has its own envelope with
    onset_t=400, so α_B(490) = 0 and the rise is first-order at tau.

    (a) job A's cooling must not dip when job B starts.
    (b) max single-tick delta must be below the first-order bound at tau.
    (c) steady-state identity: Σ α_k × P_k = α_max × P_compute.
    """
    site = SiteConfig(site_id="s1", pue_base=1.03, alpha_max=0.20,
                      tau_seconds=20.0, dt_thermal_seconds=90.0)
    cooling = CoolingModule(asset_id="c1", site=site)

    t = 0.0
    while t < 400.0:
        cooling.record_compute_sample(t, 5.0)
        cooling.advance(t, 5.0)
        t += 5.0
    settled_a = cooling.output_mw()
    assert settled_a > 0.9, f"job A should settle near 1.0 MW; got {settled_a:.3f} MW"

    trace: list[float] = []
    deltas: list[float] = []
    prev = settled_a
    while t < 800.0:
        cooling.record_compute_sample(t, 15.0)   # job B adds 10 MW
        cooling.advance(t, 5.0)
        trace.append(cooling.output_mw())
        deltas.append(cooling.output_mw() - prev)
        prev = cooling.output_mw()
        t += 5.0

    # (a) job A's cooling must not dip when job B starts
    assert min(trace) >= settled_a * 0.95, (
        f"P_cooling dipped to {min(trace):.3f} MW from settled {settled_a:.3f} MW — "
        "job A's cooling must not fall because job B started (naive t0 reset symptom)"
    )
    # (b) max single-tick rise must be below the first-order bound at tau
    step_mw = site.alpha_max * 10.0
    first_order_max = step_mw * (1 - math.exp(-5.0 / site.tau_seconds))
    assert max(deltas) < first_order_max * 2.0, (
        f"P_cooling jumped {max(deltas):.3f} MW in one tick; "
        f"first-order bound at tau={site.tau_seconds}s: ~{first_order_max:.3f} MW. "
        "The second step-load must not alias as an instantaneous step."
    )
    # (c) steady-state §12 identity
    assert math.isclose(trace[-1], site.alpha_max * 15.0, rel_tol=1e-3), (
        f"settled at {trace[-1]:.3f} MW, expected {site.alpha_max * 15.0:.3f} MW"
    )


def test_item3_job_end_cooling_persists_over_thermal_lag():
    """Step 3 Item 3 (b): ending a job must not collapse P_cooling immediately.

    Pre-fix failure mode: deleting the envelope on JOB_END drops P_cooling to
    zero in one tick — a discontinuous step in the opposite direction from the
    second-step aliasing bug.

    Post-fix: envelope.end_t is set but load_mw is preserved.  _lagged_mw
    returns load_mw for target_time ≤ end_t, so P_cooling stays elevated for
    ~dt_thermal seconds and decays only when the lagged-compute cursor crosses
    end_t.

    Assert: for all ticks within dt_thermal − 2·DT seconds of job end,
    P_cooling remains ≥ 90 % of the settled value.
    """
    site = SiteConfig(site_id="s1", pue_base=1.03, alpha_max=0.20,
                      tau_seconds=20.0, dt_thermal_seconds=90.0)
    cooling = CoolingModule(asset_id="c1", site=site)
    DT = 5.0

    # Settle job A at 5 MW
    t = 0.0
    while t < 400.0:
        cooling.record_compute_sample(t, 5.0)
        cooling.advance(t, DT)
        t += DT
    settled = cooling.output_mw()
    assert settled > 0.9, f"job A should settle near 1.0 MW; got {settled:.3f} MW"

    # End job A: compute drops to 0
    t_end = t   # 400.0
    post_end: list[float] = []
    while t < t_end + site.dt_thermal_seconds + DT:
        cooling.record_compute_sample(t, 0.0)
        cooling.advance(t, DT)
        post_end.append(cooling.output_mw())
        t += DT

    # P_cooling must stay elevated for dt_thermal − 2 ticks (grace for boundaries)
    grace_ticks = 2
    sustained = post_end[: int(site.dt_thermal_seconds / DT) - grace_ticks]
    assert sustained, "sustained window is empty — check dt_thermal / DT ratio"
    assert all(v > settled * 0.9 for v in sustained), (
        f"P_cooling collapsed before dt_thermal={site.dt_thermal_seconds}s elapsed. "
        f"Min in sustained window: {min(sustained):.3f} MW "
        f"(threshold {settled * 0.9:.3f} MW). "
        "The heat is still in the room — retention must hold for ~dt_thermal."
    )


def test_item3_cursor_pruning_does_not_corrupt_lagged_lookup():
    """P1: deque popleft() must not silently shift the cursor to the wrong sample.

    THE TRAP: if _cursor_abs is a plain deque index and popleft() is called,
    the index points at the NEXT element rather than the intended one — wrong
    cooling values, no error raised.  The fix uses an absolute counter
    (_cursor_abs) plus a pruned-count (_pruned_count); cursor_rel =
    _cursor_abs - _pruned_count remains valid after every popleft().

    Procedure: register a job, run 500 s (retention_buf = 190 s, so several
    rounds of pruning occur).  Compare _lagged_mw() cursor result against a
    brute-force min(history, …) scan of the retained deque.  Also verify
    pruning actually happened (otherwise the cursor path was never exercised).
    """
    site = SiteConfig(site_id="s1", pue_base=1.03, alpha_max=0.20,
                      tau_seconds=20.0, dt_thermal_seconds=90.0)
    cooling = CoolingModule(asset_id="c1", site=site)
    DT = 5.0
    JOB = "job-cursor-test"
    cooling.register_job_start(JOB, onset_t=0.0)

    t = 0.0
    while t < 500.0:
        # Linearly increasing load — every sample has a unique value so a
        # corrupted cursor produces a detectably wrong result.
        mw = 1.0 + t / 100.0
        cooling.record_job_compute(t, {JOB: mw})
        t += DT

    env = cooling._envelopes[JOB]

    # Pruning must have occurred
    assert env._pruned_count > 0, (
        f"No samples were pruned (_pruned_count={env._pruned_count}). "
        "Increase run duration or check retention_buf calculation."
    )

    # Advance cursor to the current lag_time by calling _lagged_mw once
    lag_time = (t - DT) - site.dt_thermal_seconds
    cursor_result = cooling._lagged_mw(env, lag_time)

    # Brute-force nearest-sample on the retained deque
    brute = min(env.history, key=lambda s: abs(s[0] - lag_time))[1]

    assert math.isclose(cursor_result, brute, rel_tol=1e-9), (
        f"Cursor gave {cursor_result:.6f} MW; brute-force gave {brute:.6f} MW. "
        f"(_cursor_abs={env._cursor_abs}, _pruned_count={env._pruned_count}, "
        f"cursor_rel={env._cursor_abs - env._pruned_count}, "
        f"deque len={len(env.history)}) — pruning has corrupted the cursor."
    )
