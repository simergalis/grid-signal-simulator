"""
Whitebox tests for the deterministic core -- Design Spec Section 12,
"direct extension of the functional spec's own plan (source spec
Section 16, Addendum A)". No asyncio here: this is the pure-Python
layer, tested independently of the run-management/concurrency layer.
"""

import contextlib
import math

import pytest

from core.asset_modules import BessModule, CoolingModule, GPUModule, IrradianceProfile, SolarModule, TurbineModule
from core.dispatch import CheckpointClassifier, CheckpointState, DispatchArbitrator
from core.models import BessConfig, HardwareProfile, SiteConfig, SolarConfig, TurbineConfig, WorkloadEventType, WorkloadSignal, WorkloadClass
from core.sim_clock import SimClock


@contextlib.contextmanager
def _plane_guard_active():
    """Set the Step-4 ContextVar sentinel for tests that call evaluate_tick()
    directly (without going through RunContext.step()).  Mirrors the set/reset
    logic in RunContext.step() — see tests/test_plane_separation.py."""
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _make_clock(
    sim_time: float,
    dt_seconds: float,
    tick_seq: int = 0,
    rate: float = 1.0,
) -> SimClock:
    """Convenience factory for tests that call evaluate_tick() directly.
    wall_stamp_utc=None signals absent wall clock — arithmetic on None is a
    TypeError, not a silent 1970 result.  Mirrors the SimClock constructed by
    RunContext.step() in runtime/run_manager.py, minus the real-time wall stamp."""
    return SimClock(
        sim_time=sim_time,
        dt_seconds=dt_seconds,
        wall_stamp_utc=None,
        rate=rate,
        tick_seq=tick_seq,
    )


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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1", pue_base=1.03)
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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1", dt_thermal_seconds=90.0)
    cooling = CoolingModule(asset_id="cool-0", site=site)
    cooling.record_compute_sample(0.0, 5.0)
    cooling.record_compute_sample(60.0, 5.0)
    cooling.advance(60.0, 5.0)
    assert cooling.output_mw() == 0.0


def test_tc03_cooling_converges_to_alpha_max_at_steady_state():
    """Source spec TC-03: held constant >= dt_thermal + 5*tau -> P_cooling
    converges to alpha_max * P_compute within 2% of asymptote."""
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1", dt_thermal_seconds=90.0, tau_seconds=20.0, alpha_max=0.20)
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
    arbitrator = DispatchArbitrator(turbines=[turbine], bess_units=[], site=SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-tc10"))

    alert, _credit, _shortfall = arbitrator.stage_for_predicted_step(delta_p_mw=20.0, dt_lead_seconds=30.0, sim_time=0.0)

    assert alert is not None
    assert math.isclose(alert.gap_duration_s, 70.0, abs_tol=1e-6)
    assert math.isclose(alert.shortfall_mw, 14.0, abs_tol=1e-6)


def test_tc11_sufficient_reserve_no_false_alert():
    """Source spec TC-11: 5 MW job, dt_lead=60s, r_asset=0.2 MW/s
    -> required ramp 25s < 60s lead -> no alert."""
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=25.0))
    arbitrator = DispatchArbitrator(turbines=[turbine], bess_units=[], site=SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-tc11"))

    alert, _credit, _shortfall = arbitrator.stage_for_predicted_step(delta_p_mw=5.0, dt_lead_seconds=60.0, sim_time=0.0)

    assert alert is None


@pytest.mark.xfail(
    reason=(
        "Phase E Item 4 report — stage_target() and advance() deleted in Phase C. "
        "Old: stage_target(6.0) set _target_mw; advance(dt=30) drove RAMPING output. "
        "New: STARTING units advance via command_start/begin_interval; SYNCHRONISED "
        "units track setpoints via apply_loading().  Rate-limited descent is tested "
        "by test_synchronised_unit_rate_limits_setpoint_drop (Phase E Item 2). "
        "Why: Phase C collapsed RAMPING/AT_TARGET into SYNCHRONISED."
    ),
    strict=True,
)
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

    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="site-onboard", pue_base=1.03, uncalibrated=False)
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
    with _plane_guard_active():
        for i in range(3):
            state.apply_workload_signal(_signal(f"job-{i}", UNMAPPED_A, t), dt_lead_seconds=30.0)
            tick = evaluate_tick(state, _make_clock(t, DT, tick_seq=i))
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
    with _plane_guard_active():
        tick_b = evaluate_tick(state, _make_clock(t, DT))

    assert tick_b.unrecognised_profile_alerts == frozenset({UNMAPPED_B}), (
        f"Fourth job with a new unmapped profile_id {UNMAPPED_B!r} must produce "
        f"exactly one alert; got {tick_b.unrecognised_profile_alerts!r}"
    )


# ---------------------------------------------------------------------------
# D8 — staging sizes against P_dispatch_required, not P_total
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    reason=(
        "Phase E Item 4 report — test body reads turbine._target_mw as an assertion "
        "proxy; _target_mw deleted in Phase C.  "
        "Old: stage_for_predicted_step() stored dispatch delta in _target_mw. "
        "New: staging delta flows through the commitment engine's pending_start register "
        "and commitment engine's dispatch delta; no _target_mw field on TurbineModule. "
        "Why: Phase C removed _target_mw when it replaced the RAMPING state machine. "
        "The underlying property (solar offset reduces dispatch delta) still holds — "
        "it is exercised by TC-91b via the real evaluate_tick() path."
    ),
    strict=True,
)
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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="site-d8", pue_base=PUE)

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
    from core.models import IslandMode
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="site-demo20", pue_base=PUE,
                      island_mode=IslandMode.GRID_TIE)   # demo-20mw is grid-connected (SDG&E)

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
    with _plane_guard_active():
        for i in range(20):   # 100 simulated seconds — plenty of time to see BESS fire
            tick = evaluate_tick(state, _make_clock(t, DT, tick_seq=i))
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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="site-d10", pue_base=PUE)

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

    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=library)
    # Pin ramp_seconds=45 s so this test keeps documenting the "fire then taper"
    # arc at the original ramp duration.  The production default was raised to
    # 120 s (slower, more realistic); at 120 s a 25 MW turbine pre-staged to
    # the full draw always stays ahead of the slow load curve and BESS never
    # fires — that's correct new behaviour, but tested separately.
    gpu.ramp_seconds = 45.0

    state = SimulationState(
        run_id="run-d10",
        site=site,
        gpu_modules=[gpu],
        turbines=[turbine],
        bess_units=[bess],
        solar_arrays=[solar],
        cooling=cooling,
    )

    # Solar has not advanced yet at t=0, so staging delta equals the full
    # compute draw (19.957 MW).  Turbine stages to 19.957 MW (fits within
    # rated 25 MW).  Ramp time = 45 s (pinned above); run is 300 s.
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
    with _plane_guard_active():
        for i in range(60):   # 300 simulated seconds
            tick = evaluate_tick(state, _make_clock(t, DT, tick_seq=i))
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
    # 3. Once tapered, BESS must not re-fire (stays at zero to run end).
    assert all(b == 0.0 for b in bess_outputs[taper_tick:]), (
        "BESS must stay at zero after taper; re-fire detected.\n"
        f"  bess_outputs = {bess_outputs}"
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

    arbitrator = DispatchArbitrator(turbines=[turbine], bess_units=[bess],
                                    site=SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-d11"))
    alert, _credit, _shortfall = arbitrator.stage_for_predicted_step(
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
    from core.models import IslandMode
    _mode = IslandMode.ISLANDED
    assert bess.max_sustainable_seconds(14.0, _mode) == 0.0, (
        "max_sustainable_seconds(14.0) must return 0.0 because 14 MW > rated 5 MW; "
        f"got {bess.max_sustainable_seconds(14.0, _mode)}"
    )
    # Energy-limited path still works: at or below rated power, energy governs.
    expected_s = (10.0 / 4.0) * 3600.0   # 4 MW ≤ 5 MW rated → 9000 s
    assert bess.max_sustainable_seconds(4.0, _mode) == expected_s, (
        f"max_sustainable_seconds(4.0) should be {expected_s} s (energy-limited); "
        f"got {bess.max_sustainable_seconds(4.0, _mode)}"
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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="site-item1", pue_base=PUE)
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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1", pue_base=1.03, alpha_max=0.20,
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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1", pue_base=1.03, alpha_max=0.20,
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
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1", pue_base=1.03, alpha_max=0.20,
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


# ---------------------------------------------------------------------------
# Step 3 Item 4 — BESS fleet split, anchor constraint, reserve aggregation
# ---------------------------------------------------------------------------

def test_item4_fleet_covers_shortfall_above_single_unit_rating():
    """Step 3 Item 4 (a): a shortfall that exceeds any single unit's rating
    but is within the combined fleet capacity must NOT fire an alert.

    Pre-fix behaviour (equal-share min()): each unit gets peak/n.  With two
    units rated 5 MW each and peak=8 MW, each gets 4 MW, max_sustainable_s(4)
    is finite, min > gap_s → passes.  But with two units rated 3 MW and 7 MW,
    each gets 4 MW: unit-A (rated 3) → 4 > 3 → 0.0, min=0 → FALSE ALERT.

    Post-fix (proportional split + sum): unit-A gets 8×3/10=2.4 MW < 3 MW,
    unit-B gets 8×7/10=5.6 MW < 7 MW; both return finite seconds; sum > gap_s.
    """
    from core.dispatch import DispatchArbitrator
    from core.models import BessConfig, IslandMode, SiteConfig, TurbineConfig

    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1")
    # Two heterogeneous units: 3 MW and 7 MW, fleet total = 10 MW.
    # Peak shortfall = 8 MW > 3 MW (single unit), < 10 MW (fleet).
    bess_a = BessModule(BessConfig(asset_id="bess-a", rated_mw=3.0, usable_mwh=4.0))
    bess_b = BessModule(BessConfig(asset_id="bess-b", rated_mw=7.0, usable_mwh=4.0))
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=20.0))
    arb = DispatchArbitrator([turbine], [bess_a, bess_b], site)

    # peak_shortfall = 8 MW, dt_lead=30s → already_ramped=6 MW → peak=2 MW
    # Use delta_p_mw large enough that peak_shortfall_mw > single unit rating.
    # r_asset=0.2, dt_lead=30 → already_ramped=6; delta_p=14 → peak=8 MW.
    alert, _credit, _shortfall = arb.stage_for_predicted_step(
        delta_p_mw=14.0, dt_lead_seconds=30.0, sim_time=0.0
    )
    assert alert is None, (
        f"Fleet (3+7=10 MW) should cover an 8 MW shortfall without alert; "
        f"got {alert}. Equal-share division allocates 4 MW to the 3 MW unit "
        "(D11 → 0.0), making min()=0 < gap_s. Proportional split is required."
    )


def test_item4_small_unit_capped_to_ceiling_under_equal_share():
    """Step 3 Item 4 (b): equal-share caps the small unit at its power ceiling.

    Fixture (both grid_forming=False → anchor_deduction=0 → ceiling = rated_mw):
      Unit A: rated_mw=2.0, usable_mwh=10.0 → bridging_available_mw = 2.0 MW
      Unit B: rated_mw=6.0, usable_mwh=10.0 → bridging_available_mw = 6.0 MW

    Power ceilings differ ([2.0, 6.0] MW).  Fleet shortfall = 4 MW.

    _capped_equal_share_allocations trace:
      Round 1: equal share = 4/2 = 2.0 MW each.
               A: share (2.0) ≥ headroom (2.0) → capped at 2.0 MW.  Capping bound.
               B: share (2.0) < headroom (6.0) → allocated 2.0 MW.
               remaining = 4 - (2.0 + 2.0) = 0 → done.
      Result: A=2.0 MW (100% ceiling, fully utilised), B=2.0 MW (33% of ceiling).

    Both allocations are equal in MW but for different reasons — A hit its ceiling,
    B absorbed only the equal share because the residual demand was zero.  The result
    is NOT a coincidence of equal ceilings; A's ceiling of 2.0 MW is half of B's 6.0 MW.

    Pre-D14 proportional-by-ceiling gave A=4×(2/8)=1 MW (50% utilisation), B=3 MW.
    Equal-share drives the small unit to 100% of its ceiling first.

    Endurance consequence (see _capped_equal_share_allocations docstring):
    A is driven harder than under proportional, which shortens its endurance.
    D13's min() will therefore be set by A in any scenario where A's SoC/MW
    ratio is lower than B's — which is the correct physical outcome.

    tick() must deliver these allocations via cover_shortfall; confirmed by
    checking each unit's output_mw() after one tick.
    """
    from core.dispatch import DispatchArbitrator
    from core.models import BessConfig, IslandMode, SiteConfig, TurbineConfig

    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s1")
    bess_a = BessModule(BessConfig(asset_id="ba", rated_mw=2.0, usable_mwh=10.0))
    bess_b = BessModule(BessConfig(asset_id="bb", rated_mw=6.0, usable_mwh=10.0))
    # Turbine produces 0 MW so fleet shortfall = p_dispatch_required.
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.0, rated_mw=0.0))
    arb = DispatchArbitrator([turbine], [bess_a, bess_b], site)

    turbine_mw, bess_mw, _, _ = arb.tick(p_dispatch_required_mw=4.0, dt_seconds=5.0)
    # D14 equal-share-then-cap: A(ceiling=2) → 2 MW (full), B → 2 MW.
    assert math.isclose(bess_a.output_mw(), 2.0, abs_tol=1e-9), (
        f"unit-A (rated 2 MW) should be fully utilised at 2.0 MW (D14); "
        f"got {bess_a.output_mw():.4f} MW.  Pre-D14 proportional gave 1.0 MW (50%)."
    )
    assert math.isclose(bess_b.output_mw(), 2.0, abs_tol=1e-9), (
        f"unit-B (rated 6 MW) should get the remaining 2.0 MW; got {bess_b.output_mw():.4f} MW."
    )
    assert math.isclose(bess_mw, 4.0, abs_tol=1e-9), (
        f"fleet BESS output should equal shortfall 4.0 MW; got {bess_mw:.4f} MW."
    )


def test_item4_anchor_unit_contributes_less_bridging_than_grid_following():
    """Step 3 Item 4 (c): identical units — one grid-forming anchor, one grid-following.

    Post-fix: anchor.bridging_available_mw < grid_following.bridging_available_mw
    by exactly p_anchor_reserve_mw.  The reserve check sees fewer MW from the
    anchor, so the fleet check may fire when the anchor deficit is large enough.
    """
    from core.models import BessConfig, IslandMode

    # Two identical units, 8 MW rated, 1 MW anchor reserve (default).
    grid_following = BessModule(BessConfig(
        asset_id="gf", rated_mw=8.0, usable_mwh=4.0,
        grid_forming=False,  # grid-following: full 8 MW available
    ))
    anchor = BessModule(BessConfig(
        asset_id="anc", rated_mw=8.0, usable_mwh=4.0,
        grid_forming=True,   # anchor: 8 - 1 = 7 MW available
    ))

    mode = IslandMode.ISLANDED
    gf_bridge = grid_following.bridging_available_mw(mode)
    anc_bridge = anchor.bridging_available_mw(mode)

    assert gf_bridge > anc_bridge, (
        f"grid-following bridging ({gf_bridge} MW) must exceed anchor bridging "
        f"({anc_bridge} MW); both units are identical except for grid_forming."
    )
    expected_deduction = anchor.config.p_anchor_reserve_mw
    assert math.isclose(gf_bridge - anc_bridge, expected_deduction, abs_tol=1e-9), (
        f"deduction should be exactly p_anchor_reserve_mw={expected_deduction} MW; "
        f"got {gf_bridge - anc_bridge:.4f} MW."
    )

    # In GRID_TIE mode, even grid_forming=True units have no deduction.
    assert math.isclose(
        anchor.bridging_available_mw(IslandMode.GRID_TIE),
        anchor.config.rated_mw,
        abs_tol=1e-9,
    ), "anchor unit in GRID_TIE mode must have zero anchor deduction"

    # max_sustainable_seconds respects the anchor ceiling.
    assert anchor.max_sustainable_seconds(7.5, mode) == 0.0, (
        "anchor (bridging=7 MW) must return 0.0 for discharge_mw=7.5 > 7.0"
    )
    assert anchor.max_sustainable_seconds(6.0, mode) > 0, (
        "anchor (bridging=7 MW) should return positive duration for 6 MW request"
    )


def test_item4_demo_scenarios_alert_behavior():
    """Step 3 Item 4 (d): anchor reserve does not break demo-20mw (no alert)
    and demo-alert still fires.

    Uses the same sizing as example_usage.py: demo-20mw has bess_rated_mw=18
    (P5 resize: was 15, giving only 30 mW / 0.2% margin after 1 MW anchor
    deduction; 18 MW gives bridging=17 MW → 21.7% margin over ~13.97 MW
    shortfall), bess_usable_mwh=8, bess_grid_forming=True; demo-alert has
    rated=5, mwh=2.5, grid_forming=True.  Both are islanded anchors with
    p_anchor_reserve=1 MW.
    """
    from runtime.scenario_factory import build_run_context

    ctx_ok = build_run_context(
        "item4-20mw", job_id="job-big", node_count=1900,
        turbine_rated_mw=25.0, bess_rated_mw=18.0,
        bess_usable_mwh=8.0, bess_grid_forming=True,
        end_sim_time=300.0,
    )
    ctx_alert = build_run_context(
        "item4-alert", job_id="job-alert", node_count=1900,
        turbine_rated_mw=25.0, bess_usable_mwh=2.5,
        bess_grid_forming=True,
        end_sim_time=300.0,
    )

    import asyncio
    from runtime.run_manager import RunManager, WebSocketHub

    async def _run():
        hub = WebSocketHub()
        mgr = RunManager(hub)
        await asyncio.gather(
            mgr.start_run(ctx_ok),
            mgr.start_run(ctx_alert),
        )
        await asyncio.gather(
            mgr._tasks[ctx_ok.run_id],
            mgr._tasks[ctx_alert.run_id],
        )

    asyncio.run(_run())

    alerts_20mw = any(r.insufficient_reserve_alert for r in ctx_ok.sink.rows)
    alerts_alert = any(r.insufficient_reserve_alert for r in ctx_alert.sink.rows)

    assert not alerts_20mw, (
        f"demo-20mw (18 MW BESS, anchor, bridging=17 MW) must not alert; "
        f"peak shortfall ≈ 13.97 MW < 17 MW → reserve check passes (21.7% margin). "
        f"If alerting, anchor reserve deduction is over-applied."
    )
    assert alerts_alert, (
        f"demo-alert (5 MW BESS, anchor, bridging=4 MW) must alert; "
        f"peak shortfall ≈ 13.97 MW > 4 MW → reserve check fails. "
        f"If not alerting, anchor reserve deduction is not being applied."
    )


def test_d14_capped_allocation_sum_invariant():
    """D14: _capped_equal_share_allocations must satisfy sum == min(demand, sum(ceilings)).

    No allocation may exceed its unit's ceiling.  Two sub-cases:
      (a) demand < fleet capacity → sum(allocs) == demand, small unit fully used.
      (b) demand > fleet capacity → sum(allocs) == sum(ceilings), all units capped.

    User D14 example: 5 MW + 20 MW fleet, shortfall = 12 MW.
      Pre-D14 proportional-by-ceiling: [2.4, 9.6] — small unit at 48%.
      D14 equal-share-then-cap:         [5.0, 7.0] — small unit fully used.
    """
    from core.dispatch import DispatchArbitrator
    from core.models import BessConfig, SiteConfig, TurbineConfig

    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-d14")
    bess_a = BessModule(BessConfig(asset_id="a-d14", rated_mw=5.0,  usable_mwh=10.0))
    bess_b = BessModule(BessConfig(asset_id="b-d14", rated_mw=20.0, usable_mwh=10.0))
    turbine = TurbineModule(TurbineConfig(asset_id="t-d14", r_asset_mw_per_s=0.0, rated_mw=0.0))
    arb = DispatchArbitrator([turbine], [bess_a, bess_b], site)
    ceilings = [5.0, 20.0]

    # (a) demand 12 MW < fleet ceiling 25 MW: full demand must be met.
    allocs = arb._capped_equal_share_allocations(12.0, ceilings)
    assert all(a <= c + 1e-9 for a, c in zip(allocs, ceilings)), (
        f"no allocation may exceed its ceiling; got {allocs} vs ceilings {ceilings}"
    )
    assert math.isclose(sum(allocs), 12.0, abs_tol=1e-9), (
        f"sum(allocs)={sum(allocs):.6f} must equal demand 12.0"
    )
    assert math.isclose(allocs[0], 5.0, abs_tol=1e-9), (
        f"small unit (5 MW ceiling) must be fully used; got {allocs[0]:.4f}. "
        "Pre-D14 proportional gave 2.4 MW (48%)."
    )
    assert math.isclose(allocs[1], 7.0, abs_tol=1e-9), (
        f"large unit gets remainder 7 MW; got {allocs[1]:.4f}."
    )

    # (b) demand 30 MW > fleet ceiling 25 MW: every unit capped, remainder unmet.
    allocs_over = arb._capped_equal_share_allocations(30.0, ceilings)
    assert all(a <= c + 1e-9 for a, c in zip(allocs_over, ceilings)), (
        "over-demand: no allocation may exceed ceiling"
    )
    assert math.isclose(sum(allocs_over), sum(ceilings), abs_tol=1e-9), (
        f"power-limited: sum(allocs)={sum(allocs_over):.4f} must equal "
        f"fleet ceiling {sum(ceilings):.4f}"
    )

    # (c) homogeneous fleet: equal split, both well below ceiling.
    bess_c = BessModule(BessConfig(asset_id="c-d14", rated_mw=5.0, usable_mwh=10.0))
    bess_d = BessModule(BessConfig(asset_id="d-d14", rated_mw=5.0, usable_mwh=10.0))
    arb2 = DispatchArbitrator([turbine], [bess_c, bess_d], site)
    allocs_hom = arb2._capped_equal_share_allocations(6.0, [5.0, 5.0])
    assert math.isclose(sum(allocs_hom), 6.0, abs_tol=1e-9)
    assert all(a <= 5.0 + 1e-9 for a in allocs_hom)
    # Equal split of 6 MW: each gets 3 MW (both below ceiling of 5 MW).
    assert math.isclose(allocs_hom[0], 3.0, abs_tol=1e-9), (
        f"homogeneous fleet equal-split: each should get 3.0 MW; got {allocs_hom[0]:.4f}"
    )


def test_d13_min_not_sum_fleet_endurance():
    """D13 — reserve aggregation must use min(), not sum(), over per-unit durations.

    Counter-example from the defect report:
      Unit A: 10 MW rated, 1 MWh usable  → max_sustainable_seconds(10 MW) = 360 s
      Unit B: 10 MW rated, 10 MWh usable → max_sustainable_seconds(10 MW) = 3600 s
      Fleet peak shortfall: 20 MW  (proportional: 10 MW each, equal weights)
      gap_s = 400 s  (constructed via r_asset=0.05 MW/s, dt_lead=0 s)

    At t=360 s unit A is empty.  The fleet drops to 10 MW and there is a
    10 MW hole for the remaining 40 s of the gap.  The alert must fire.

    sum = 360 + 3600 = 3960 s ≥ 400 s → no alert (WRONG — B's surplus masks A)
    min = 360 s < 400 s → alert fires (CORRECT)

    This test asserts the alert fires AND explicitly shows that sum() would not
    have fired, so any regression that reintroduces sum is immediately visible.
    """
    from core.dispatch import DispatchArbitrator
    from core.models import BessConfig, IslandMode, SiteConfig, TurbineConfig

    # Construct gap_s = 400 s:
    #   required_ramp_s = delta_p_mw / r_asset = 20 / 0.05 = 400 s
    #   gap_s = required_ramp_s - dt_lead_seconds = 400 - 0 = 400 s
    turbine = TurbineModule(TurbineConfig(
        asset_id="t-d13", r_asset_mw_per_s=0.05, rated_mw=100.0,
    ))
    # Unit A: runs out of energy at 10 MW after 360 s (1 MWh / 10 MW × 3600)
    bess_a = BessModule(BessConfig(asset_id="a-d13", rated_mw=10.0, usable_mwh=1.0))
    # Unit B: plenty of energy — 3600 s at 10 MW — but cannot compensate for A's gap
    bess_b = BessModule(BessConfig(asset_id="b-d13", rated_mw=10.0, usable_mwh=10.0))

    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-d13-test")
    arb = DispatchArbitrator([turbine], [bess_a, bess_b], site)

    # delta_p_mw=20, dt_lead=0 → gap_s=400, already_ramped=0, peak_shortfall=20 MW
    # proportional: both get 10 MW (equal rated_mw → equal bridging weights)
    alert, _credit, _shortfall = arb.stage_for_predicted_step(
        delta_p_mw=20.0, dt_lead_seconds=0.0, sim_time=0.0,
    )

    assert alert is not None, (
        "D13: InsufficientReserveAlert must fire — unit A exhausts at 360 s < gap_s=400 s. "
        "sum() = 3960 s would have masked the alert; min() = 360 s correctly fires it."
    )

    # Explicitly verify sum() would have given the wrong answer.
    island_mode = IslandMode.ISLANDED
    alloc_each = 10.0  # proportional share for each equal-rated unit
    dur_a = bess_a.max_sustainable_seconds(alloc_each, island_mode)
    dur_b = bess_b.max_sustainable_seconds(alloc_each, island_mode)
    assert math.isclose(dur_a, 360.0, rel_tol=1e-9), (
        f"Unit A should sustain 360 s at 10 MW; got {dur_a:.1f} s"
    )
    assert dur_a + dur_b > 400.0, (
        f"Regression guard: sum={dur_a + dur_b:.0f} s > 400 s (sum path would miss the alert)"
    )
    assert min(dur_a, dur_b) < 400.0, (
        f"Regression guard: min={min(dur_a, dur_b):.0f} s < 400 s (min path fires correctly)"
    )


# ---------------------------------------------------------------------------
# Turbine ramp credit / peak shortfall — values returned by stage_for_predicted_step
# ---------------------------------------------------------------------------

def test_stage_ramp_credit_nonzero_with_residual_shortfall():
    """Gap path (gap_s > 0): already_ramped_mw is positive and peak_shortfall is
    strictly less than delta_p_mw when dt_lead > 0.

    Setup: r_asset=0.2 MW/s, dt_lead=30 s, delta_p=20 MW.
      already_ramped = 0.2 × 30 = 6.0 MW (capped to delta_p=20 → 6.0)
      peak_shortfall = 20 - 6.0 = 14.0 MW
    """
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=25.0))
    arb = DispatchArbitrator(turbines=[turbine], bess_units=[], site=SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-credit"))

    alert, credit_mw, shortfall_mw = arb.stage_for_predicted_step(
        delta_p_mw=20.0, dt_lead_seconds=30.0, sim_time=0.0
    )
    assert math.isclose(credit_mw, 6.0, abs_tol=1e-9), (
        f"Turbine ramp credit must be r_asset × dt_lead = 6.0 MW; got {credit_mw}"
    )
    assert math.isclose(shortfall_mw, 14.0, abs_tol=1e-9), (
        f"Peak shortfall must be delta_p - credit = 14.0 MW; got {shortfall_mw}"
    )
    # Consistency: credit + shortfall = delta_p
    assert math.isclose(credit_mw + shortfall_mw, 20.0, abs_tol=1e-9)


def test_stage_ramp_credit_full_coverage_zero_shortfall():
    """Gap-free path (gap_s <= 0): turbine ramp covers the full step; peak_shortfall must be 0.

    Setup: r_asset=0.2 MW/s, dt_lead=60 s, delta_p=5 MW.
      required_ramp_s = 5 / 0.2 = 25 s < dt_lead=60 s → gap_s ≤ 0
      credit = min(0.2 × 60, 5.0) = min(12.0, 5.0) = 5.0 MW (capped)
      peak_shortfall = max(0, 5 - 5) = 0.0 MW
    """
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=0.2, rated_mw=25.0))
    arb = DispatchArbitrator(turbines=[turbine], bess_units=[], site=SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-zero-sf"))

    alert, credit_mw, shortfall_mw = arb.stage_for_predicted_step(
        delta_p_mw=5.0, dt_lead_seconds=60.0, sim_time=0.0
    )
    assert alert is None, "No alert expected when lead time is sufficient"
    assert math.isclose(credit_mw, 5.0, abs_tol=1e-9), (
        f"Credit must be capped to delta_p=5.0 MW (not raw 12.0); got {credit_mw}"
    )
    assert shortfall_mw == 0.0, (
        f"Peak shortfall must be 0.0 when ramp credit covers the full step; got {shortfall_mw}"
    )


def test_stage_ramp_credit_excludes_hot_standby():
    """Hot-standby turbines must not contribute to ramp credit (D15 fix).

    Setup: two turbines — one active (r_asset=0.2 MW/s), one hot-standby (r_asset=0.3 MW/s).
    Only the active turbine's ramp rate must appear in the credit.

    dt_lead=30 s, delta_p=20 MW.
      credit from active only = 0.2 × 30 = 6.0 MW
      credit if standby included = (0.2 + 0.3) × 30 = 15.0 MW (wrong)
    """
    active  = TurbineModule(TurbineConfig(
        asset_id="t-active", r_asset_mw_per_s=0.2, rated_mw=25.0, hot_standby=False
    ))
    standby = TurbineModule(TurbineConfig(
        asset_id="t-standby", r_asset_mw_per_s=0.3, rated_mw=25.0, hot_standby=True
    ))
    arb = DispatchArbitrator(turbines=[active, standby], bess_units=[], site=SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-standby-excl"))

    alert, credit_mw, shortfall_mw = arb.stage_for_predicted_step(
        delta_p_mw=20.0, dt_lead_seconds=30.0, sim_time=0.0
    )
    assert math.isclose(credit_mw, 6.0, abs_tol=1e-9), (
        f"Standby turbine must not contribute to credit; expected 6.0 MW (active only), "
        f"got {credit_mw:.3f} MW. If standby included, would be 15.0 MW."
    )
    assert math.isclose(shortfall_mw, 14.0, abs_tol=1e-9), (
        f"peak_shortfall must be delta_p - active_credit = 14.0; got {shortfall_mw}"
    )


def test_stage_ramp_credit_capped_to_delta_p():
    """Credit must never exceed delta_p_mw even when r_asset × dt_lead > delta_p.

    Setup: r_asset=2.0 MW/s, dt_lead=100 s → raw credit = 200 MW > delta_p=10 MW.
    Credit must be capped to 10.0 MW; shortfall = 0.0.
    """
    turbine = TurbineModule(TurbineConfig(asset_id="t0", r_asset_mw_per_s=2.0, rated_mw=50.0))
    arb = DispatchArbitrator(turbines=[turbine], bess_units=[], site=SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="s-cap"))

    alert, credit_mw, shortfall_mw = arb.stage_for_predicted_step(
        delta_p_mw=10.0, dt_lead_seconds=100.0, sim_time=0.0
    )
    assert alert is None
    assert math.isclose(credit_mw, 10.0, abs_tol=1e-9), (
        f"Credit must be capped to delta_p=10.0 MW; got {credit_mw}"
    )
    assert shortfall_mw == 0.0, (
        f"Shortfall must be 0.0 when credit covers the step; got {shortfall_mw}"
    )
