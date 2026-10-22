import pytest
from pydantic import ValidationError

from api.schemas import FuelCellElectricalGroupSpec, FuelCellUnitSpec, ScenarioSpec
from core.fuel_cell_module import BlockFuelCellArray, BlockFuelCellConfig, BlockFuelCellFleet
from core.models import (
    ConfidenceBand,
    TickResult,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.sim_clock import SimClock
from core.simulation_core import evaluate_tick
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec


_FORBIDDEN = (
    "fault_current", "short_circuit", "transformer_impedance", "percent_z", "x_r",
)


def _keys_deep(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _keys_deep(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys_deep(child)


def _running_array(**overrides):
    asset_id = overrides.pop("asset_id", "fc-stage3")
    config = BlockFuelCellConfig(
        asset_id=asset_id,
        block_rated_mw=1.0,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        **overrides,
    )
    return BlockFuelCellArray(config)


def _factory_tick(
    *,
    grid_forming: bool,
    min_stable_frac: float = .1,
    with_grid_forming_bess: bool = False,
    ieee_1547_category: int = 3,
    initial_running_blocks: int = 1,
):
    spec = {
        "name": "stage3-integration",
        "frequency_nominal_hz": 60.0,
        "power_factor": .85,
        "island_mode": True,
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": True,
        "fuel_cell_units": [{
            "asset_id": "fc-former",
            "block_rated_mw": 1.0,
            "block_count": 1,
            "initial_running_blocks": initial_running_blocks,
            "initial_hot_standby_blocks": 0,
            "min_stable_frac": min_stable_frac,
            "grid_forming": grid_forming,
            "ieee_1547_category": ieee_1547_category,
        }],
        "bess_units": ([{
            "asset_id": "bess-former",
            "rated_mw": 1.0,
            "usable_mwh": 1.0,
            "initial_soc_fraction": 1.0,
            "p_anchor_reserve_mw": 0.0,
            "grid_forming": True,
        }] if with_grid_forming_bess else []),
    }
    state = build_run_context_from_spec("stage3-integration", spec).sim_state
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        return evaluate_tick(
            state,
            SimClock(
                sim_time=0.0,
                dt_seconds=.01,
                wall_stamp_utc=0.0,
                rate=1.0,
                tick_seq=1,
            ),
        )
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def test_stage3_schema_defaults_and_normative_provenance():
    unit = FuelCellUnitSpec(asset_id="fc", block_rated_mw=1, block_count=1)
    assert unit.grid_forming is False
    assert unit.power_factor == 1.0
    assert unit.ieee_1547_category == 3
    assert unit.provenance["grid_forming"] == "site_specific"
    assert unit.provenance["power_factor"] == "site_specific"
    assert unit.provenance["reactive_capability_mvar"] == "proposed"
    assert unit.provenance["ieee_1547_category"] == "site_specific"
    with pytest.raises(ValidationError):
        FuelCellUnitSpec(asset_id="bad", block_rated_mw=1, block_count=1, power_factor=0)


def test_stage3_reactive_output_and_apparent_power_preserve_pf_one():
    array = _running_array(power_factor=.8)
    # With the default fixed 1 MVA inverter, PF .8 derates the block's real
    # ceiling to .8 MW. A newly running hybrid block begins at half that
    # effective ceiling: .4 MW + .3 Mvar = .5 MVA.
    assert array.output_mw() == pytest.approx(.4)
    assert array.reactive_output_mvar == pytest.approx(.3)
    assert array.apparent_power_mva == pytest.approx(.5)
    assert _running_array().reactive_output_mvar == 0.0
    capped = _running_array(power_factor=.8, reactive_capability_mvar=.1)
    assert capped.reactive_output_mvar == pytest.approx(.1)
    assert capped.apparent_power_mva == pytest.approx((.4 ** 2 + .1 ** 2) ** .5)


def test_stage3_fleet_apparent_power_uses_aggregate_achieved_p_and_q():
    first = _running_array(asset_id="fc-pf", power_factor=.8)
    second = _running_array(
        asset_id="fc-capped", power_factor=.6, reactive_capability_mvar=.2,
    )
    fleet = BlockFuelCellFleet([first, second])
    # Fixed 1 MVA hardware derates the newly-running stable floors to .4 MW
    # and .3 MW respectively; achieved Q remains vector-aggregated.
    assert fleet.output_mw() == pytest.approx(.7)
    assert fleet.reactive_output_mvar == pytest.approx(.5)
    assert fleet.apparent_power_mva == pytest.approx((.7 ** 2 + .5 ** 2) ** .5)
    assert fleet.apparent_power_capacity_mva == pytest.approx(2.0)
    full = _running_array(asset_id="fc-full", power_factor=.8)
    full.blocks[0].output_mw = 1.0
    full_fleet = BlockFuelCellFleet([full])
    assert (
        full_fleet.apparent_power_mva
        / full_fleet.apparent_power_capacity_mva
    ) == pytest.approx(1.0)
    assert fleet.apparent_power_mva != pytest.approx(
        first.apparent_power_mva + second.apparent_power_mva
    )


def test_stage3_short_delay_and_rocof_trip_running_block_persistently():
    array = _running_array(ieee_1547_category=1)
    for _ in range(15):
        assert not array.evaluate_ride_through(62.1, 0.0, .01)
    records = array.evaluate_ride_through(62.1, 0.0, .01)
    assert records[0]["reason"] == "over_62"
    assert array.output_mw() == 0.0
    assert array.blocks[0].tripped is True

    rocof = _running_array(ieee_1547_category=1)
    records = rocof.evaluate_ride_through(60.0, .51, .01)
    assert records[0]["reason"] == "rocof"


def test_stage3_independent_timers_and_no_banking():
    # The fast and 300 s thresholds are simultaneously active above 62 Hz.
    array = _running_array()
    for _ in range(15):
        array.evaluate_ride_through(62.1, 0.0, .01)
    assert array.blocks[0].ride_through_timer_s == {
        "over_62": pytest.approx(.15), "over_61_2": pytest.approx(.15),
        "under_56_5": 0.0, "under_58_5": 0.0,
    }
    assert array.evaluate_ride_through(62.1, 0.0, .01)[0]["reason"] == "over_62"

    long = _running_array()
    for _ in range(10):
        long.evaluate_ride_through(61.5, 0.0, 10.0)
    assert long.blocks[0].ride_through_timer_s["over_61_2"] == 100.0
    long.evaluate_ride_through(60.0, 0.0, .01)
    assert long.blocks[0].ride_through_timer_s["over_61_2"] == 0.0
    for _ in range(30):
        long.evaluate_ride_through(61.5, 0.0, 10.0)
    assert long.blocks[0].tripped is True

    restarted = _running_array()
    for _ in range(29):
        restarted.evaluate_ride_through(61.5, 0.0, 10.0)
    assert restarted.blocks[0].ride_through_timer_s["over_61_2"] == 290.0
    restarted.blocks[0].output_mw = 0.0
    restarted.evaluate_ride_through(61.5, 0.0, 5.0)
    assert restarted.blocks[0].ride_through_timer_s == {}
    restarted.blocks[0].output_mw = .5
    assert not restarted.evaluate_ride_through(61.5, 0.0, 10.0)


@pytest.mark.parametrize("category,limit", [(1, .5), (2, 2.0), (3, 3.0)])
def test_stage3_category_rocof_limits(category, limit):
    array = _running_array(ieee_1547_category=category)
    assert not array.evaluate_ride_through(60.0, limit, .01)
    assert array.evaluate_ride_through(60.0, limit + .01, .01)[0]["reason"] == "rocof"


def test_stage3_multiple_bess_grid_formers_are_valid_and_groups_stay_minimal():
    scenario = ScenarioSpec(
        name="multiple formers",
        bess_units=[
            {"asset_id": "b1", "rated_mw": 1, "usable_mwh": 1, "grid_forming": True},
            {"asset_id": "b2", "rated_mw": 1, "usable_mwh": 1, "grid_forming": True},
        ],
    )
    assert len(scenario.bess_units) == 2
    assert set(FuelCellElectricalGroupSpec.model_fields) == {
        "electrical_group_id", "block_count"
    }
    payload = FuelCellUnitSpec(
        asset_id="fc", block_rated_mw=1, block_count=1
    ).model_dump()
    assert not set(_keys_deep(payload)).intersection(_FORBIDDEN)


def test_stage3_island_viability_uses_live_bess_or_fuel_cell_former():
    declared_but_dead_former = _factory_tick(
        grid_forming=True,
        initial_running_blocks=0,
    )
    assert declared_but_dead_former.island_collapsed is True
    assert declared_but_dead_former.collapse_reason == "island_collapse_no_grid_forming_source"

    fuel_cell_former = _factory_tick(grid_forming=True)
    assert fuel_cell_former.island_collapsed is False
    assert fuel_cell_former.fuel_cell_output_mw > 0.0

    bess_former = _factory_tick(
        grid_forming=False,
        with_grid_forming_bess=True,
    )
    assert bess_former.island_collapsed is False


def test_stage3_legacy_island_without_declared_former_does_not_collapse():
    spec = {
        "name": "stage3-legacy-no-former",
        "frequency_nominal_hz": 60.0,
        "power_factor": .85,
        "island_mode": True,
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "bess_units": [],
    }
    state = build_run_context_from_spec("stage3-legacy-no-former", spec).sim_state
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        result = evaluate_tick(
            state,
            SimClock(0.0, .01, 0.0, 1.0, 1),
        )
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)
    assert result.island_collapsed is False
    assert result.collapse_reason is None


def test_stage3_exhausted_grid_forming_bess_does_not_keep_island_alive():
    spec = {
        "name": "stage3-exhausted-bess",
        "frequency_nominal_hz": 60.0,
        "power_factor": .85,
        "island_mode": True,
        "fuel_cell_enabled": False,
        "bess_units": [{
            "asset_id": "empty-former",
            "rated_mw": 1.0,
            "usable_mwh": 1.0,
            "initial_soc_fraction": 0.0,
            "p_anchor_reserve_mw": 0.0,
            "grid_forming": True,
        }],
    }
    state = build_run_context_from_spec("stage3-exhausted-bess", spec).sim_state
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        result = evaluate_tick(
            state,
            SimClock(0.0, .01, 0.0, 1.0, 1),
        )
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)
    assert result.island_collapsed is True
    assert result.collapse_reason == "island_collapse_no_grid_forming_source"


def test_stage3_bess_trip_hands_island_to_fc_then_last_former_trip_collapses():
    spec = {
        "name": "stage3-former-handoff",
        "frequency_nominal_hz": 60.0,
        "power_factor": .85,
        "island_mode": True,
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": True,
        "fuel_cell_units": [{
            "asset_id": "fc-former",
            "block_rated_mw": 1.0,
            "block_count": 1,
            "initial_running_blocks": 1,
            "initial_hot_standby_blocks": 0,
            "min_stable_frac": .4,
            "grid_forming": True,
        }],
        "bess_units": [{
            "asset_id": "bess-former",
            "rated_mw": 1.0,
            "usable_mwh": 1.0,
            "initial_soc_fraction": 1.0,
            "p_anchor_reserve_mw": 0.0,
            "grid_forming": True,
        }],
    }
    state = build_run_context_from_spec("stage3-former-handoff", spec).sim_state

    def trip(asset_id, timestamp):
        state.apply_workload_signal(WorkloadSignal(
            event_id=f"trip-{asset_id}",
            job_id=asset_id,
            event_type=WorkloadEventType.UNIT_TRIP,
            timestamp=timestamp,
            hardware_profile_id="",
            node_count=0,
            workload_class=WorkloadClass.OTHER,
            site_id=state.site.site_id,
        ), dt_lead_seconds=0.0)

    def tick(sim_time, seq):
        token = _EVALUATE_TICK_PERMITTED.set(True)
        try:
            return evaluate_tick(
                state,
                SimClock(sim_time, .01, 0.0, 1.0, seq),
            )
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)

    trip("bess-former", 0.0)
    assert state.bess_units[0].tripped is True
    assert state.bess_units[0].soc_mwh > 0.0
    on_fc = tick(0.0, 1)
    assert on_fc.island_collapsed is False
    assert on_fc.fuel_cell_output_mw > 0.0
    assert on_fc.contingency_coverage.bess_bridging_available_mw == 0.0
    assert on_fc.contingency_coverage.bess_usable_energy_mwh == 0.0

    trip("fc-former", .01)
    no_former = tick(.01, 2)
    assert no_former.island_collapsed is True
    assert no_former.collapse_reason == "island_collapse_no_grid_forming_source"


def test_stage3_last_former_ride_through_trip_causes_distinct_collapse():
    # At the normal 0.5 per-block stable floor this deliberately creates
    # 3.1875 Hz/s ROCOF, just above Category III's 3.0 Hz/s capability.
    result = _factory_tick(grid_forming=True, min_stable_frac=.5)
    assert result.island_collapsed is True
    assert result.collapse_reason == "island_collapse_no_grid_forming_source"
    assert result.fuel_cell_ride_through_trips[0]["reason"] == "rocof"
    assert result.fuel_cell_output_mw == 0.0
    assert result.fuel_cell_achieved_output_mw == 0.0
    assert result.p_generation_mw == 0.0
    assert result.fuel_cell_reactive_output_mvar == 0.0
    assert result.fuel_cell_apparent_power_mva == 0.0
    assert result.fuel_cell_apparent_loading_fraction == 0.0
    assert result.p_unserved_mw == pytest.approx(result.p_demand_mw)
    assert result.physical_balance.passed is True


def test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess():
    result = _factory_tick(
        grid_forming=False,
        min_stable_frac=.5,
        ieee_1547_category=1,
        with_grid_forming_bess=True,
    )
    assert result.island_collapsed is False
    assert result.fuel_cell_ride_through_trips[0]["reason"] == "rocof"
    assert result.fuel_cell_output_mw == 0.0
    assert result.fuel_cell_achieved_output_mw == 0.0
    assert result.fuel_cell_reactive_output_mvar == 0.0
    assert result.fuel_cell_apparent_power_mva == 0.0
    assert result.p_generation_mw == pytest.approx(result.bess_output_mw)
    assert result.frequency_forcing_mw == pytest.approx(
        result.p_generation_mw - result.p_demand_mw
    )
    assert result.physical_balance.passed is True


def test_stage3_schema_and_tick_payload_have_fields_without_prohibited_keys():
    schema = FuelCellUnitSpec.model_json_schema()
    assert not set(_keys_deep(schema)).intersection(_FORBIDDEN)
    payload = _tick_result_to_dict(TickResult(
        run_id="stage3", tick_index=1, sim_time_seconds=0.0,
        p_compute_demand_mw=0.0, p_cooling_demand_mw=0.0, p_demand_mw=0.0,
        net_demand_mw=0.0, turbine_output_mw=0.0, bess_output_mw=0.0,
        bess_soc_fraction=1.0, confidence=ConfidenceBand(0.0, 0.0),
    ))
    for key in (
        "fuel_cell_reactive_output_mvar", "fuel_cell_apparent_power_mva",
        "fuel_cell_apparent_loading_fraction", "island_reactive_balance_mvar",
        "fuel_cell_ride_through_trips", "fuel_cell_ride_through_status",
    ):
        assert key in payload
    assert not set(_keys_deep(payload)).intersection(_FORBIDDEN)