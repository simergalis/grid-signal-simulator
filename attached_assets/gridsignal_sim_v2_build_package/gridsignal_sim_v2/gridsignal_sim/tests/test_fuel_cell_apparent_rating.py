import math

from core.fuel_cell_module import (
    BlockFuelCellArray,
    BlockFuelCellConfig,
    BlockFuelCellFleet,
)
from runtime.fuel_cell_readiness import BlockFuelCellReadinessController


def test_fixed_inverter_mva_derates_real_block_capacity_and_commitment() -> None:
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc",
        block_rated_mw=.325,
        apparent_power_rating_mva_per_block=.325,
        power_factor=.9,
        block_count=200,
        initial_running_blocks=200,
        initial_hot_standby_blocks=0,
    ))

    assert math.isclose(array.config.effective_block_rated_mw, .2925)
    assert math.isclose(array.config.rated_mw, 58.5)
    assert math.isclose(array.available_mw, 58.5)
    assert array._requested_running_blocks(50.0) == 171
    assert array.config.apparent_power_capacity_mva == 65.0
    assert math.isclose(array.config.effective_block_rated_mw * 170, 49.725)


def test_default_mva_equality_is_explicitly_assumed_and_fixed_mva_bounds_q() -> None:
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc",
        block_rated_mw=.325,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        power_factor=.9,
        reactive_capability_mvar=10.0,
    ))
    fleet = BlockFuelCellFleet([array])

    assert array.config.apparent_power_rating_is_assumed
    assert array.config.provenance["apparent_power_rating_mva_per_block"] == "site_specific"
    assert math.isclose(fleet.apparent_power_capacity_mva, .325)
    assert math.hypot(array.output_mw(), array.reactive_output_mvar) <= .325 + 1e-12


def test_readiness_uses_pf_limited_effective_real_rating() -> None:
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc",
        block_rated_mw=.325,
        apparent_power_rating_mva_per_block=.325,
        power_factor=.9,
        block_count=200,
    ))
    controller = BlockFuelCellReadinessController.__new__(BlockFuelCellReadinessController)

    assert controller.derive_target(array, [50.0]).target_hot_blocks == 171