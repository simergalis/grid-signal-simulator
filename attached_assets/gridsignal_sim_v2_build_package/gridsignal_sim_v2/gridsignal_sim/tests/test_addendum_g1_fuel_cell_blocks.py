import pytest
from pydantic import ValidationError

from api.schemas import FuelCellUnitSpec
from core.contingency import FuelCellSnapshot, PlantState, evaluate_contingency
from core.fuel_cell_module import (
    BlockFuelCellArray,
    BlockFuelCellConfig,
    FuelCellConfig,
    FuelCellModule,
    FuelCellState,
)
from core.models import IslandMode


def test_unit_schema_derives_capacity_and_rejects_independent_rating():
    unit = FuelCellUnitSpec(asset_id="fc-a", block_rated_mw=2.5, block_count=4)
    assert unit.rated_mw == 10.0
    assert unit.initial_hot_standby_blocks == 4
    assert unit.provenance["intrinsic_output_ramp_rate_mw_per_s"] == "proposed"
    with pytest.raises(ValidationError):
        FuelCellUnitSpec(
            asset_id="fc-a", block_rated_mw=2.5, block_count=4, rated_mw=10.0
        )


def test_runtime_defaults_every_non_running_block_to_hot_standby():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=.325, block_count=4,
        initial_running_blocks=1,
    ))
    assert sum(
        block.state == FuelCellState.HOT_STANDBY for block in array.blocks
    ) == 3
    assert not any(
        block.state in {FuelCellState.COLD, FuelCellState.WARMING}
        for block in array.blocks
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
        initial_hot_standby_blocks=0,
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


def test_settled_baseline_does_not_bank_commit_credit_for_a_later_peak():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=2,
        initial_running_blocks=1, initial_hot_standby_blocks=1,
        commit_rate_blocks_per_s=1, hot_start_s=1,
    ))
    array.set_load_following_target_mw(2)
    array.advance(0, 30)

    assert array._commit_credit == 0
    array.set_load_following_target_mw(4)
    array.advance(30, .5)
    assert sum(block.dwell_s > 0 for block in array.blocks) == 0
    assert sum(block.state == FuelCellState.RUNNING for block in array.blocks) == 1

    # The new request earns only this interval's 0.5 block of rate credit.
    array.advance(30.5, .5)
    assert sum(block.dwell_s > 0 for block in array.blocks) == 1
    assert sum(block.state == FuelCellState.RUNNING for block in array.blocks) == 1
    array.advance(31, .5)
    assert sum(block.state == FuelCellState.RUNNING for block in array.blocks) == 2


def test_hot_standby_commit_rate_produces_exactly_thirty_blocks_in_thirty_seconds():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=.325, block_count=246,
        initial_running_blocks=62, initial_hot_standby_blocks=92,
        commit_rate_blocks_per_s=1, hot_start_s=5,
        dispatch_mechanism="hybrid", min_stable_frac=0,
    ))
    array.set_load_following_target_mw(80)
    for sim_time in (0, 5, 10, 15, 20, 25):
        array.advance(sim_time, 5)

    assert sum(block.state == FuelCellState.RUNNING for block in array.blocks) == 92


def test_hot_start_dwell_is_committed_but_not_running_or_contingency_capacity():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=3,
        initial_hot_standby_blocks=2, commit_rate_blocks_per_s=10,
        hot_start_s=10,
    ))
    array.set_load_following_target_mw(4)
    array.advance(0, 1)

    assert sum(block.dwell_s > 0 for block in array.blocks) == 2
    assert sum(block.state == FuelCellState.RUNNING for block in array.blocks) == 0
    assert array.available_mw == 0
    assert array.readiness_summary(fast_window_s=0)["available_now_mw"] == 0
    # The two dwell transitions already meet the commitment and must not start
    # the otherwise-cold third block on the next tick.
    array.advance(1, 1)
    assert array.blocks[2].state == FuelCellState.COLD


def test_dwell_completion_allocates_output_in_the_same_interval_end_snapshot():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=2,
        initial_hot_standby_blocks=2, commit_rate_blocks_per_s=2,
        hot_start_s=4, dispatch_mechanism="hybrid", min_stable_frac=0,
        intrinsic_output_ramp_rate_mw_per_s=2,
    ))
    array.set_load_following_target_mw(4)
    array.advance(0, 5)

    running = [block for block in array.blocks if block.state == FuelCellState.RUNNING]
    assert len(running) == 2
    assert all(block.output_mw == pytest.approx(2) for block in running)
    assert array.output_mw() == pytest.approx(
        len(running) * array.config.block_rated_mw
    )


def test_hybrid_running_block_count_can_exceed_modulated_output_in_block_units():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=2,
        initial_running_blocks=2, dispatch_mechanism="hybrid",
        min_stable_frac=0, decommit_rate_blocks_per_s=.0001,
    ))
    array.set_load_following_target_mw(.5)
    array.advance(0, 1)

    running = sum(block.state == FuelCellState.RUNNING for block in array.blocks)
    assert running == 2
    assert running > array.output_mw() / array.config.block_rated_mw


def test_readiness_summary_does_not_manufacture_fast_credit_at_zero_lead():
    """Hot standby is not event reserve until its actual start+dwell fits."""
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=1,
        initial_hot_standby_blocks=1, hot_start_s=0.5, readiness_dwell_s=0.5,
    ))

    summary = array.readiness_summary(fast_window_s=0.0)

    assert summary["available_now_mw"] == 0.0
    assert summary["available_fast_mw"] == 0.0
    # This separate eventual quantity is for dispatch-deficit attribution only;
    # it must not change the authoritative zero-lead contingency credit above.
    assert summary["eventual_hot_closure_mw"] == 2.0


def test_eventual_hot_closure_includes_blocks_already_in_hot_start_dwell():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=2,
        initial_hot_standby_blocks=2, commit_rate_blocks_per_s=2,
        hot_start_s=10,
    ))
    array.set_load_following_target_mw(4)
    array.advance(0, 1)

    summary = array.readiness_summary(fast_window_s=0.0)

    assert all(block.dwell_s > 0.0 for block in array.blocks)
    assert summary["available_now_mw"] == 0.0
    assert summary["available_fast_mw"] == 0.0
    assert summary["eventual_hot_closure_mw"] == 4.0


def test_hot_start_dwell_has_no_fast_or_eligible_contingency_reserve():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-a", block_rated_mw=2, block_count=1,
        initial_hot_standby_blocks=1, hot_start_s=10,
    ))
    assert array.command_run(0)

    # The positive window is intentionally longer than hot_start_s.  A block
    # already synchronising is still in transition and cannot be admitted as
    # fast/contingency reserve, even though it remains eventual closure.
    summary = array.readiness_summary(fast_window_s=60)
    coverage = evaluate_contingency(PlantState(
        turbine_snapshots=(),
        bess_snapshots=(),
        fuel_cell_snapshots=(FuelCellSnapshot(
            rated_mw=array.config.rated_mw,
            eligible_reserve_mw=float(summary["available_fast_mw"]),
        ),),
        island_mode=IslandMode.ISLANDED,
        curtailable_capacity_mw=0.0,
        renewable_mw=0.0,
    ))

    assert array.blocks[0].dwell_s == 10
    assert summary["available_fast_mw"] == 0.0
    assert summary["eventual_hot_closure_mw"] == 2.0
    assert coverage.fuel_cell_available_mw == 0.0


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
        intrinsic_output_ramp_rate_mw_per_s=2,
    ))
    array.set_load_following_target_mw(3)
    array.advance(0, 1)
    assert array.output_mw() == expected


def test_intrinsic_output_ramp_applies_without_a_fuel_system():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-small",
        block_rated_mw=2,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        intrinsic_output_ramp_rate_mw_per_s=0.1,
    ))
    array.set_load_following_target_mw(2)

    array.advance(0, 5)

    assert array.minimum_dispatchable_output_mw == pytest.approx(1.0)
    assert array.output_mw() == pytest.approx(1.5)


def test_default_intrinsic_output_ramp_uses_three_time_constant_settling_point():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-default-ramp",
        block_rated_mw=2,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
    ))

    assert array.config.intrinsic_output_ramp_rate_mw_per_s == pytest.approx(2 / 9)


def test_intrinsic_output_ramp_limits_upward_and_downward_changes():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-symmetric-ramp",
        block_rated_mw=2,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        intrinsic_output_ramp_rate_mw_per_s=0.2,
    ))
    array.set_load_following_target_mw(2)
    array.advance(0, 1)
    assert array.output_mw() == pytest.approx(1.2)

    array.set_load_following_target_mw(1)
    array.advance(1, 1)
    assert array.output_mw() == pytest.approx(1.0)


def test_dwell_completion_does_not_receive_unearned_interval_ramp_credit():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-dwell-ramp",
        block_rated_mw=2,
        block_count=1,
        initial_running_blocks=0,
        initial_hot_standby_blocks=1,
        hot_start_s=5,
        intrinsic_output_ramp_rate_mw_per_s=0.1,
    ))
    array.set_load_following_target_mw(2)

    array.advance(0, 5)
    assert array.output_mw() == pytest.approx(1.0)

    array.advance(5, 1)
    assert array.output_mw() == pytest.approx(1.1)


def test_multi_block_target_redistribution_is_ramp_limited_per_block():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-redistribution",
        block_rated_mw=2,
        block_count=2,
        initial_running_blocks=2,
        initial_hot_standby_blocks=0,
        intrinsic_output_ramp_rate_mw_per_s=0.1,
    ))
    array.set_load_following_target_mw(4)

    array.advance(0, 1)

    assert [block.output_mw for block in array.blocks] == pytest.approx([1.1, 1.1])


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
        initial_hot_standby_blocks=0,
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