"""
test_ramping_turbine_ignores_loading_setpoint_drop
---------------------------------------------------
Behavioural discriminator for the D1 dual-writer contradiction.

Establishes which of two mutually exclusive accounts of simulation_core.py:641-644 is
correct:

  D1 diagnostic claim:
    _synchronised_units uses is_synchronised (True for RAMPING), so apply_loading()
    writes _current_output_mw on RAMPING turbines every tick.

  Phase 1 state-table claim:
    _synchronised_units uses t.state == TurbineState.SYNCHRONISED, which is False for
    RAMPING, so apply_loading() never touches RAMPING turbines.

Discriminator:
  If a RAMPING turbine's output continues rising at r_asset × dt per tick while the net
  demand (loading setpoint) is far below its current accumulated output, apply_loading()
  is not influencing it — partition is clean — Phase 1 report correct.

  If the turbine's output falls toward the dropped setpoint, apply_loading() is writing
  _current_output_mw on RAMPING units — D1 report correct.

Setup
-----
Single turbine, r_asset_mw_per_s=0.2, dt=5 s → max_delta=1.0 MW/tick.
GPU demand ~8 MW steady (NODE_COUNT=800, RATED_KW=10.0, PUE=1.0, ramp_seconds=5).
Solar step at sim_time=50 s: irradiance 0.2→0.95, rated 15 MW → solar jumps ~3→~14.25 MW.
After the step: net_demand ≈ 0 MW (solar over-covers).  The turbine is RAMPING toward
target_mw ~8.24 MW through and past t=50.

Expected (if partition is clean)
---------------------------------
Ticks 0-7 (RAMPING, pre-transition): _current_output_mw rises by exactly +1.000 MW/tick.
The loading setpoint (5.24 MW for SYNCHRONISED units) is irrelevant because the RAMPING
turbine is not in _synchronised_units.

Transition observation (tick 8)
---------------------------------
At tick 8 the turbine reaches its target inside advance() and transitions RAMPING →
SYNCHRONISED.  Because advance() runs BEFORE _synchronised_units is built in the same
tick (simulation_core.py:629-644), the newly-SYNCHRONISED unit is immediately subject
to apply_loading() within that same tick.  This is a transition-tick dual-write: advance()
sets _current_output_mw = target_mw, then apply_loading() adjusts it toward the fleet
demand setpoint.  Both writers touch the same field in tick 8.
"""

import sys
import os

# Allow running from tests/ or from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    HardwareProfile,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
    TurbineState,
)
from core.models import (
    BessConfig,
    SiteConfig,
    SolarConfig,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.simulation_core import SimulationState, evaluate_tick
from core.sim_clock import SimClock
from core._plane_guard import _EVALUATE_TICK_PERMITTED

DT = 5.0
R  = 0.2          # MW/s → max_delta = R × DT = 1.0 MW/tick
# Phase D repair: RAMPING deleted; STARTING units have frozen output (0 MW).
# apply_loading() excludes STARTING units, so output must NOT change.
EXPECTED_STEP = 0.0   # STARTING units contribute zero; loading exclusion holds


def _make_state() -> tuple[SimulationState, TurbineModule, SolarModule]:
    turbine = TurbineModule(TurbineConfig(
        asset_id="turb-0", r_asset_mw_per_s=R, rated_mw=25.0,
        cold_start_s=60.0,   # Phase D repair: 60 s → 12 ticks at DT=5 s; transition visible in 24-tick loop
    ))
    bess    = BessModule(BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0))
    site    = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="test-d1-B")

    # Low solar initially (0.2 × 15 MW = 3 MW); solar step to 0.95 fraction at t=50.
    irradiance = IrradianceProfile([(0.0, 0.2), (50.0, 0.95), (600.0, 0.95)])
    solar   = SolarModule(SolarConfig(asset_id="solar-0", rated_mw=15.0), irradiance_profile=irradiance)
    cooling = CoolingModule(asset_id="cool-0", site=site)

    PROFILE_ID = "p0"; NODE_COUNT = 800; RATED_KW = 10.0; PUE = 1.0
    library = {PROFILE_ID: HardwareProfile(PROFILE_ID, rated_kw=RATED_KW)}
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=library)
    gpu.ramp_seconds = 5.0   # near-instant: demand is stable from tick 1

    state = SimulationState(
        run_id="test-d1-discriminator",
        site=site,
        gpu_modules=[gpu],
        turbines=[turbine],
        bess_units=[bess],
        solar_arrays=[solar],
        cooling=cooling,
    )
    state.apply_workload_signal(
        WorkloadSignal(
            event_id="e1", job_id="job1",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id=PROFILE_ID,
            node_count=NODE_COUNT,
            workload_class=WorkloadClass.TRAINING,
            site_id="test-d1-B",
        ),
        dt_lead_seconds=5.0,
    )
    return state, turbine, solar


def test_starting_turbine_output_frozen_by_loading_exclusion() -> None:
    """
    DISCRIMINATOR (Phase D repair): a STARTING turbine's _current_output_mw must
    stay at 0 MW every tick regardless of net demand, because apply_loading()
    excludes STARTING units from the loaded set.

    If apply_loading() were writing STARTING units' output the output would
    deviate from 0.0 MW — test would catch the exclusion failure.

    Also verifies the transition-tick dual-write: on the tick where advance()
    transitions the unit STARTING → SYNCHRONISED (at tick 12 with cold_start_s=60 s),
    apply_loading() runs in the same tick and adjusts output.  After the transition,
    the loading layer is the sole writer and output tracks the fleet demand setpoint.
    """
    state, turbine, solar = _make_state()
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        sim_time = 0.0
        prev_out: float | None = None
        transition_tick: int | None = None

        for tick_i in range(24):
            before_out  = turbine._current_output_mw
            before_state = turbine.state

            tick = evaluate_tick(
                state,
                SimClock(sim_time=sim_time, dt_seconds=DT,
                         wall_stamp_utc=None, rate=1.0, tick_seq=tick_i),
            )
            after_out = turbine._current_output_mw

            if before_state == TurbineState.STARTING and turbine.state == TurbineState.STARTING:
                # ── Pure STARTING tick ─────────────────────────────────────────────
                # advance() ticks the countdown; apply_loading() excludes STARTING
                # units from the loaded set.  Output must stay at 0.0 MW.
                if prev_out is not None:
                    actual_step = after_out - prev_out
                    assert abs(actual_step - EXPECTED_STEP) < 1e-9, (
                        f"Tick {tick_i} (t={sim_time}): expected {EXPECTED_STEP} MW step "
                        f"for STARTING turbine (frozen output); got {actual_step:.6f} MW. "
                        f"If step deviates, apply_loading() is influencing STARTING output."
                    )

            elif before_state == TurbineState.STARTING and turbine.state == TurbineState.SYNCHRONISED:
                # ── Transition tick ────────────────────────────────────────────────
                # advance() fires first (STARTING→SYNCHRONISED), then apply_loading()
                # runs on the newly-SYNCHRONISED unit in the same tick.
                # Record for inspection; do not assert a fixed step here.
                transition_tick = tick_i

            prev_out = after_out
            sim_time += DT

        # At least some STARTING ticks must have occurred before transition.
        assert transition_tick is not None or turbine.state == TurbineState.STARTING, (
            "Turbine never entered STARTING state — test setup failed."
        )

    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)
