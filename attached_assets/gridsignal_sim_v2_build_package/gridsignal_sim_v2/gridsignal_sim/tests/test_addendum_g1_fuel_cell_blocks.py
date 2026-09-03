import pytest
from pydantic import ValidationError

from api.schemas import FuelCellUnitSpec
from core.fuel_cell_module import (
    BlockFuelCellArray,
    BlockFuelCellConfig,
    FuelCellConfig,
    FuelCellModule,
    FuelCellState,
)


def test_unit_schema_derives_capacity_and_rejects_independent_rating():
    unit = FuelCellUnitSpec(asset_id="fc-a", block_rated_mw=2.5, block_count=4)
    assert unit.rated_mw == 10.0
    with pytest.raises(ValidationError):
        FuelCellUnitSpec(
            asset_id="fc-a", block_rated_mw=2.5, block_count=4, rated_mw=10.0
        )


def test_unit_schema_rejects_impossible_initial_block_total():
    with pytest.raises(ValidationError):
        FuelCellUnitSpec(
            asset_id="fc-a", block_rated_mw=1, block_count=2,
            initial_running_blocks=1, initial_hot_standby_blocks=2,
        )


def test_cold_and_warming_blocks_are_not_available_until_ready():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=1,
        cold_start_s=2, warm_start_s=1, hot_start_s=0.5,
    ))
    array.set_load_following_target_mw(2)
    array.advance(0, 1)
    assert array.state == FuelCellState.WARMING
    assert array.available_mw == 0
    array.advance(1, 2)
    assert array.state == FuelCellState.HOT_STANDBY
    assert array.available_mw == 0
    array.advance(3, 1)
    assert array.available_mw == 2


def test_readiness_summary_does_not_manufacture_fast_credit_at_zero_lead():
    """Hot standby is not event reserve until its actual start+dwell fits."""
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=1,
        initial_hot_standby_blocks=1, hot_start_s=0.5, readiness_dwell_s=0.5,
    ))

    summary = array.readiness_summary(fast_window_s=0.0)

    assert summary["available_now_mw"] == 0.0
    assert summary["available_fast_mw"] == 0.0


def test_readiness_summary_counts_running_headroom_not_running_nameplate():
    """Only MW above measured RUNNING output is immediately reserve credit."""
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=2,
        initial_running_blocks=1, initial_hot_standby_blocks=1,
        min_stable_frac=0.25, hot_start_s=0.5, readiness_dwell_s=0.5,
    ))

    summary = array.readiness_summary(fast_window_s=1.0)

    # The running block produces 0.5 MW, leaving 1.5 MW upward headroom;
    # the separate hot block adds 2 MW only after its 1 s readiness time fits.
    assert array.output_mw() == pytest.approx(0.5)
    assert summary["available_now_mw"] == pytest.approx(1.5)
    assert summary["available_fast_mw"] == pytest.approx(3.5)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("discrete_blocks", 4.0), ("modulating", 3.0), ("hybrid", 3.0)],
)
def test_dispatch_modes_have_expected_block_output(mode, expected):
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=2,
        initial_running_blocks=2, dispatch_mechanism=mode,
    ))
    array.set_load_following_target_mw(3)
    array.advance(0, 1)
    assert array.output_mw() == expected


def test_blocks_follow_distinct_cold_warm_and_hot_start_paths():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=1,
        initial_running_blocks=1, cold_start_s=9, warm_start_s=4,
        hot_start_s=1, controlled_cooling_s=2,
    ))

    # A running hot block cools only to retained warm readiness.
    assert array.command_stop(0)
    assert array.state == FuelCellState.CONTROLLED_COOLING
    assert array.blocks[0].timer_s == 2
    array.advance(0, 2)
    assert array.blocks[0].state == FuelCellState.COLD
    assert array.blocks[0].thermal_readiness == "warm"

    # Its subsequent start is the real warm-start path, not a cold start.
    assert array.command_start(2)
    assert array.blocks[0].timer_s == 4
    array.advance(2, 4)
    assert array.blocks[0].state == FuelCellState.HOT_STANDBY
    assert array.command_run(6)
    assert array.blocks[0].dwell_s == 1

    # A genuinely cold block still takes the independent cold-start path.
    cold = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-b", block_rated_mw=2, block_count=1,
        cold_start_s=9, warm_start_s=4, hot_start_s=1,
    ))
    assert cold.command_start(0)
    assert cold.blocks[0].timer_s == 9


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("discrete_blocks", 2.0),
        ("modulating", 2.0),
        ("hybrid", 1.0),
    ],
)
def test_low_dispatch_commands_obey_explicit_physical_floors(mode, expected):
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=2,
        initial_running_blocks=2, dispatch_mechanism=mode,
    ))
    array.set_load_following_target_mw(0.5)
    array.advance(0, 1)

    # The requested 0.5 MW is below every applicable stable/quantized floor;
    # actual output is the documented physical floor, never an implicit 0.5.
    assert array.commanded_output_mw == 0.5
    assert array.output_mw() == expected
    assert array.minimum_dispatchable_output_mw == (
        1.0 if mode == "hybrid" else 2.0
    )


def test_legacy_module_api_remains_scalar():
    module = FuelCellModule(FuelCellConfig(asset_id="legacy", rated_mw=4))
    assert module.command_start(0)
    module.advance(0, module.config.cold_start_s)
    assert module.command_run(1)
    assert module.output_mw() >= module.min_stable_mw