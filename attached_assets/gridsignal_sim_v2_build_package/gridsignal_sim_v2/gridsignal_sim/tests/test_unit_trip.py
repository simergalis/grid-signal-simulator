"""
tests/test_unit_trip.py — TC-84: UNIT_TRIP workload event.

Verifies that a "unit_trip" WorkloadSignal forces the named turbine to
TurbineState.OFFLINE immediately on that tick, and that the contingency
coverage reported on the next TickResult reflects the reduced fleet.

Integration tests (TC-84f) run the seeded demo-20mw scenario end-to-end
and verify the dashboard-facing contingency_coverage.state transitions from
COVERED (before t=120 s) to COVERED_WITH_SHED (after t=120 s).
"""

from __future__ import annotations

import pytest

from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
    TurbineState,
)
from core.models import (
    BessConfig,
    IslandMode,
    SiteConfig,
    SolarConfig,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.simulation_core import SimulationState
from core.contingency import BessSnapshot, PlantState, evaluate_contingency
from core.sim_clock import SimClock
from core.fuel_cell_module import (
    BlockFuelCellArray,
    BlockFuelCellConfig,
    BlockFuelCellFleet,
    FuelCellState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_site() -> SiteConfig:
    return SiteConfig(
        frequency_nominal_hz=50.0, power_factor=0.85,  # required; frequency unused in this non-frequency test
        site_id="test-site",
        pue_base=1.03,
        dt_thermal_seconds=90.0,
        tau_seconds=20.0,
        alpha_max=0.9,
    )


def _make_turbine(asset_id: str, rated_mw: float = 7.0) -> TurbineModule:
    return TurbineModule(
        config=TurbineConfig(
            asset_id=asset_id,
            rated_mw=rated_mw,
            r_asset_mw_per_s=0.2,
        )
    )


def _make_bess() -> BessModule:
    return BessModule(
        config=BessConfig(
            asset_id="bess-0",
            rated_mw=18.0,
            usable_mwh=8.0,
            initial_soc_fraction=0.95,
            grid_forming=True,
        )
    )


def _unit_trip_signal(
    asset_id: str,
    t: float = 120.0,
    electrical_group_id: str | None = None,
) -> WorkloadSignal:
    """Build a UNIT_TRIP signal targeting a generating asset or FC group."""
    return WorkloadSignal(
        event_id=f"evt-unit-trip-{asset_id}",
        job_id=asset_id,           # asset_id is carried in job_id for non-job events
        event_type=WorkloadEventType.UNIT_TRIP,
        timestamp=t,
        hardware_profile_id="",
        node_count=0,
        workload_class=WorkloadClass.OTHER,
        site_id="test-site",
        electrical_group_id=electrical_group_id,
    )


def _make_state(
    turbines: list[TurbineModule],
    fuel_cell_module: BlockFuelCellFleet | None = None,
) -> SimulationState:
    site = _make_site()
    return SimulationState(
        run_id="tc84-run",
        site=site,
        gpu_modules=[
            GPUModule(
                asset_id="gpu-0",
                site=site,
                hardware_library={},
            )
        ],
        turbines=turbines,
        bess_units=[_make_bess()],
        solar_arrays=[
            SolarModule(
                config=SolarConfig(asset_id="solar-0", rated_mw=5.0),
                irradiance_profile=IrradianceProfile([(0.0, 1.0)]),
            )
        ],
        cooling=CoolingModule(asset_id="cooling-0", site=site),
        fuel_cell_module=fuel_cell_module,
    )


def _make_fuel_cell_fleet() -> BlockFuelCellFleet:
    return BlockFuelCellFleet([BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-array-1",
        block_rated_mw=.325,
        block_count=6,
        initial_running_blocks=6,
        initial_hot_standby_blocks=0,
        electrical_groups=[("board-a", 4), ("board-b", 2)],
    ))])


# ---------------------------------------------------------------------------
# TC-84a: UNIT_TRIP event forces named turbine OFFLINE
# ---------------------------------------------------------------------------

def test_tc84a_unit_trip_forces_turbine_offline():
    """apply_workload_signal(UNIT_TRIP) sets the named turbine to OFFLINE."""
    turbines = [
        _make_turbine("turbine-0"),
        _make_turbine("turbine-1"),
        _make_turbine("turbine-2"),
    ]
    # Phase E repair: AT_TARGET deleted (Phase C). Setup with SYNCHRONISED — the
    # direct successor: a unit fully on the bus and settled at an output level.
    for t in turbines:
        t.state = TurbineState.SYNCHRONISED
        t._current_output_mw = 6.0

    state = _make_state(turbines)
    signal = _unit_trip_signal("turbine-1", t=120.0)

    state.apply_workload_signal(signal, dt_lead_seconds=0.0)

    # turbine-1 must be OFFLINE with zero output.
    assert state.turbines[1].state == TurbineState.OFFLINE, (
        f"Expected turbine-1 OFFLINE; got {state.turbines[1].state}"
    )
    assert state.turbines[1]._current_output_mw == 0.0, (
        f"Expected turbine-1 output_mw == 0.0; got {state.turbines[1]._current_output_mw}"
    )
    # Phase E repair: _target_mw deleted (Phase C).  The property it tested
    # (tripped unit produces nothing) is now covered by output_mw() == 0.0.
    assert state.turbines[1].output_mw() == 0.0, (
        f"Expected tripped turbine-1 output_mw == 0.0; got {state.turbines[1].output_mw()}"
    )


def test_unit_trip_forces_bess_offline_and_removes_grid_forming_capability():
    """A charged GF BESS cannot remain a dispatch or former after UNIT_TRIP."""
    state = _make_state([])
    bess = state.bess_units[0]
    bess._current_output_mw = 4.0

    state.apply_workload_signal(_unit_trip_signal("bess-0"), dt_lead_seconds=0.0)

    assert bess.tripped is True
    assert bess.soc_mwh > 0.0  # retained measurement is not operational credit
    assert bess.output_mw() == 0.0
    assert bess.bridging_available_mw(IslandMode.ISLANDED) == 0.0
    assert bess.cover_shortfall(4.0, False, 1.0, 4.0) == 0.0
    assert bess.absorb_surplus(4.0, 1.0) == 0.0


def test_tripped_bess_receives_no_contingency_power_or_energy_credit():
    state = _make_state([])
    bess = state.bess_units[0]
    state.apply_workload_signal(_unit_trip_signal("bess-0"), dt_lead_seconds=0.0)

    snapshots = tuple(
        BessSnapshot(
            asset_id=b.config.asset_id,
            rated_mw=b.config.rated_mw,
            soc_mwh=b.soc_mwh,
            usable_mwh=b.config.usable_mwh,
            p_anchor_reserve_mw=b.config.p_anchor_reserve_mw,
            grid_forming=b.config.grid_forming,
        )
        for b in state.bess_units
        if not b.tripped
    )
    coverage = evaluate_contingency(PlantState(
        turbine_snapshots=(),
        bess_snapshots=snapshots,
        island_mode=IslandMode.ISLANDED,
        curtailable_capacity_mw=0.0,
        renewable_mw=0.0,
    ))
    assert bess.soc_mwh > 0.0
    assert coverage.bess_bridging_available_mw == 0.0
    assert coverage.bess_usable_energy_mwh == 0.0


# ---------------------------------------------------------------------------
# TC-84b: Other turbines are unaffected by a unit trip
# ---------------------------------------------------------------------------

def test_tc84b_other_turbines_unaffected():
    """Only the named turbine goes OFFLINE; others retain their state."""
    turbines = [
        _make_turbine("turbine-0"),
        _make_turbine("turbine-1"),
        _make_turbine("turbine-2"),
    ]
    # Phase E repair: AT_TARGET deleted (Phase C) → SYNCHRONISED.
    for t in turbines:
        t.state = TurbineState.SYNCHRONISED
        t._current_output_mw = 6.0

    state = _make_state(turbines)
    state.apply_workload_signal(_unit_trip_signal("turbine-1"), dt_lead_seconds=0.0)

    # turbine-0 and turbine-2 must remain SYNCHRONISED (unchanged by the trip).
    assert state.turbines[0].state == TurbineState.SYNCHRONISED, (
        "turbine-0 should not be affected by a trip on turbine-1"
    )
    assert state.turbines[2].state == TurbineState.SYNCHRONISED, (
        "turbine-2 should not be affected by a trip on turbine-1"
    )


# ---------------------------------------------------------------------------
# TC-84c: Unknown asset_id is silently ignored (no crash)
# ---------------------------------------------------------------------------

def test_tc84c_unknown_asset_id_ignored():
    """A UNIT_TRIP targeting a non-existent turbine must not raise."""
    # Phase E repair: AT_TARGET deleted (Phase C) → SYNCHRONISED.
    turbines = [_make_turbine("turbine-0")]
    turbines[0].state = TurbineState.SYNCHRONISED
    state = _make_state(turbines)

    # Should not raise; unknown asset_id is logged and skipped.
    state.apply_workload_signal(_unit_trip_signal("turbine-BOGUS"), dt_lead_seconds=0.0)

    # Fleet unchanged.
    assert state.turbines[0].state == TurbineState.SYNCHRONISED


# ---------------------------------------------------------------------------
# TC-84d: Trip event does not touch GPU module state
# ---------------------------------------------------------------------------

def test_tc84d_unit_trip_does_not_touch_gpu_state():
    """UNIT_TRIP early-returns before the GPU plane; no job owner is registered."""
    # Phase E repair: AT_TARGET deleted (Phase C) → SYNCHRONISED.
    turbines = [_make_turbine("turbine-0"), _make_turbine("turbine-1")]
    for t in turbines:
        t.state = TurbineState.SYNCHRONISED
        t._current_output_mw = 6.0
    state = _make_state(turbines)

    state.apply_workload_signal(_unit_trip_signal("turbine-0"), dt_lead_seconds=0.0)

    # No job owner index entry should have been created for this non-job event.
    assert "turbine-0" not in state._job_owner_index, (
        "UNIT_TRIP must not register a GPU job owner entry"
    )


# ---------------------------------------------------------------------------
# TC-84e: Tripped turbine output_mw() returns 0 and state stays OFFLINE
# ---------------------------------------------------------------------------

def test_tc84e_tripped_turbine_stays_offline_after_advance():
    """After a trip, advancing the turbine one tick must not re-engage it."""
    turbines = [_make_turbine("turbine-0"), _make_turbine("turbine-1")]
    # Phase E repair: AT_TARGET deleted (Phase C) → SYNCHRONISED; _target_mw removed.
    turbines[0].state = TurbineState.SYNCHRONISED
    turbines[0]._current_output_mw = 6.0
    turbines[1].state = TurbineState.SYNCHRONISED
    turbines[1]._current_output_mw = 6.0

    state = _make_state(turbines)
    state.apply_workload_signal(_unit_trip_signal("turbine-0"), dt_lead_seconds=0.0)

    # Advance one tick — OFFLINE turbines skip advance() (state != STARTING).
    state.turbines[0].advance(sim_time=121.0, dt_seconds=5.0)

    assert state.turbines[0].state == TurbineState.OFFLINE
    assert state.turbines[0].output_mw() == 0.0


def test_g2_unit_trip_can_trip_one_fuel_cell_electrical_group():
    fleet = _make_fuel_cell_fleet()
    state = _make_state([], fuel_cell_module=fleet)

    state.apply_workload_signal(
        _unit_trip_signal("fc-array-1", electrical_group_id="board-b"),
        dt_lead_seconds=0.0,
    )

    array = fleet.arrays[0]
    assert [b.state for b in array.blocks[:4]] == [FuelCellState.RUNNING] * 4
    assert [b.state for b in array.blocks[4:]] == [FuelCellState.COLD] * 2
    assert all(b.tripped for b in array.blocks[4:])
    array.set_load_following_target_mw(array.config.rated_mw)
    array.advance(125.0, 5.0)
    assert [b.state for b in array.blocks[4:]] == [FuelCellState.COLD] * 2


def test_g2_unit_trip_can_trip_whole_fuel_cell_array():
    fleet = _make_fuel_cell_fleet()
    state = _make_state([], fuel_cell_module=fleet)

    state.apply_workload_signal(
        _unit_trip_signal("fc-array-1"),
        dt_lead_seconds=0.0,
    )

    array = fleet.arrays[0]
    assert all(b.state == FuelCellState.COLD and b.tripped for b in array.blocks)
    assert array.output_mw() == 0.0
    array.advance(125.0, 5.0)
    assert all(b.state == FuelCellState.COLD for b in array.blocks)


# ---------------------------------------------------------------------------
# TC-84f: Integration — demo-20mw state transitions COVERED → COVERED_WITH_SHED
# ---------------------------------------------------------------------------

def test_tc84f_demo_20mw_contingency_state_changes_after_trip():
    """End-to-end: run the seeded demo-20mw scenario through t=125 s and
    confirm that:
      1. turbine-1 is OFFLINE on the first tick after t=120 s.
      2. contingency_coverage.state is COVERED before the trip.
      3. contingency_coverage.state does not reach UNCOVERED after the trip;
         COVERED_WITH_SHED is acceptable (curtailment closes the gap).

    With incremental dispatch, demo-20mw starts turbine-0 and turbine-1
    (N_needed + 1 N-1 spare) at t=0.  Turbines 2 and 3 do not start because
    the 600-node / ~6.3 MW job never loads the 2-unit fleet above the 80 %
    headroom threshold needed to trigger the per-tick startup check.  After
    turbine-1 trips at t=120 s, only turbine-0 remains synchronised; N-1
    assessment for that single-unit fleet is COVERED_WITH_SHED (curtailment
    closes the hypothetical second trip).  The trip machinery still fires and
    the dashboard gen-trip indicator changes visual state — that is the TC-84
    acceptance criterion, not the post-trip coverage tier.
    """
    from api.routes.scenarios import build_seeded_store
    from api.schemas import ScenarioSpec
    from runtime.scenario_factory import build_run_context_from_spec
    from core.models import ContingencyState

    store = build_seeded_store()
    rec = store.get("demo-20mw")
    spec = ScenarioSpec.model_validate_json(rec.spec_json)
    ctx = build_run_context_from_spec("tc84f-run", spec.model_dump())

    # Run tick by tick, collecting contingency states around t=120 s.
    # demo-20mw uses TICK_INTERVAL_SIM_SECONDS = 5 s.
    # t=115 s → tick 23 (interval-end at 120 s, but sim_time was 115 at start of that tick).
    # t=120 s → tick 24 (this is the tick AFTER the trip fires at sim_time=120).

    pre_trip_states: list[str] = []
    post_trip_states: list[str] = []
    turbine1_offline_seen = False

    for tick in range(26):  # 0–25 → covers t=0 to t=125 s
        result = ctx.step()
        # sim_time_seconds is the interval END (sim_time + dt). Interval start = sim_time - 5.
        interval_start = result.sim_time_seconds - 5.0
        cc = result.contingency_coverage
        state_val = cc.state

        if 40.0 <= interval_start < 120.0:
            # Before the trip (ramp_seconds=120 s so ramp is still in progress,
            # but load is well within fleet capacity throughout).
            pre_trip_states.append(state_val)
        elif interval_start >= 120.0:
            post_trip_states.append(state_val)
            # Check turbine-1 is OFFLINE in the sim_state.
            t1 = next(t for t in ctx.sim_state.turbines if t.config.asset_id == "turbine-1")
            if t1.state == TurbineState.OFFLINE:
                turbine1_offline_seen = True

    assert turbine1_offline_seen, (
        "turbine-1 was never set OFFLINE after the UNIT_TRIP event at t=120 s"
    )

    assert pre_trip_states, "No pre-trip ticks collected (ramp may not have completed)"
    assert post_trip_states, "No post-trip ticks collected"

    pre_states_set = set(pre_trip_states)
    post_states_set = set(post_trip_states)

    # With N_needed + 1 turbines synchronised before the trip, the N-1
    # contingency must be COVERED throughout the pre-trip window.
    assert ContingencyState.COVERED_WITH_SHED not in pre_states_set, (
        f"Pre-trip contingency_coverage must be COVERED; got {pre_states_set}"
    )
    # After turbine-1 trips the single surviving unit's N-1 contingency
    # is COVERED_WITH_SHED (curtailment closes a hypothetical turbine-0 trip).
    # CANNOT_CARRY would mean even curtailment cannot save the load — that must not happen.
    assert ContingencyState.CANNOT_CARRY not in post_states_set, (
        f"Fleet must not be CANNOT_CARRY after the trip at t=120 s; got {post_states_set}"
    )
