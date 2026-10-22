import pytest
from pydantic import ValidationError

from api.schemas import FuelCellUnitSpec
from core.fuel_cell_module import BlockFuelCellArray, BlockFuelCellConfig, FuelSystemConfig
from runtime.advisory_gate import AdvisoryGate
from runtime.fuel_cell_readiness import BlockFuelCellReadinessController


def _running_block(degradation_fraction: float) -> BlockFuelCellArray:
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-flow",
        block_rated_mw=.325,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        degradation_fraction=degradation_fraction,
        intrinsic_output_ramp_rate_mw_per_s=1.0,
    ))
    array.set_load_following_target_mw(.325)
    array.advance(0.0, 1.0)
    return array


@pytest.mark.parametrize(
    ("degradation_fraction", "expected_scfm"),
    [(0.0, 30.56), (0.5, 34.18), (1.0, 37.48)],
)
def test_g2_per_block_fuel_flow_sanity(
    degradation_fraction: float,
    expected_scfm: float,
):
    array = _running_block(degradation_fraction)
    assert array.total_fuel_demand_scfm == pytest.approx(expected_scfm, abs=.2)
    assert array.hot_standby_parasitic_scfm == 0.0


def test_g2_hot_standby_parasitic_flow_has_zero_output():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-standby",
        block_rated_mw=.325,
        block_count=92,
        initial_running_blocks=0,
        initial_hot_standby_blocks=92,
    ))
    array.set_load_following_target_mw(0.0)
    array.advance(0.0, 60.0)

    assert array.output_mw() == 0.0
    assert array.hot_standby_parasitic_scfm == pytest.approx(314.0, abs=1.1)
    assert array.total_fuel_demand_scfm == array.hot_standby_parasitic_scfm


def test_g2_omitted_fuel_system_retains_ideal_g1_path():
    array = _running_block(.5)
    assert array.manifold_pressure_psig is None
    assert array.pressure_derate_alert is None
    assert array.utilisation_clamp_alert is None


def test_g2_fuel_system_initial_running_flow_is_not_artificially_starved():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-manifold", block_rated_mw=.325, block_count=1,
        initial_running_blocks=1, initial_hot_standby_blocks=0,
        fuel_system=FuelSystemConfig(),
    ))
    array.set_load_following_target_mw(.325)
    array.advance(0.0, 1.0)
    # The array began at its hybrid stable floor; it is not zero-starved while
    # its commanded load moves to nameplate.
    assert array.output_mw() >= .1625
    assert array.fuel_delivered_scfm > 0
    assert array.minimum_inlet_pressure_psig is not None


def test_g2_fuel_system_can_only_constrain_intrinsic_ramped_output_further():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-layered-limit",
        block_rated_mw=2,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        intrinsic_output_ramp_rate_mw_per_s=0.1,
        fuel_system=FuelSystemConfig(manifold_volume_ft3=1e9),
    ))
    array.set_load_following_target_mw(2)

    array.advance(0.0, 1.0)

    assert array.output_mw() <= 1.1 + 1e-9
    assert array.output_mw() >= 1.0


@pytest.mark.parametrize("requested_rate", [.5, 1., 2., 4.])
def test_g2_138_block_prestaged_command_has_rate_invariant_500ft3_transient(
    requested_rate: float,
):
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-138", block_rated_mw=.325, block_count=138,
        initial_hot_standby_blocks=138, requested_commit_rate_blocks_per_s=requested_rate,
        hot_start_s=.01, fuel_system=FuelSystemConfig(manifold_volume_ft3=500),
    ))
    array.set_load_following_target_mw(44.85)
    minimum = 99.0
    for second in range(300):
        array.advance(second, 1.0)
        minimum = min(minimum, array.minimum_manifold_pressure_psig or minimum)
    assert 10.5 <= minimum <= 10.8
    assert array.minimum_inlet_pressure_psig < 12


def test_g2_default_920_does_not_derate_and_767_authored_does():
    def run(volume: float) -> BlockFuelCellArray:
        array = BlockFuelCellArray(BlockFuelCellConfig(
            asset_id=f"fc-{volume}", block_rated_mw=.325, block_count=138,
            initial_hot_standby_blocks=138, hot_start_s=.01,
            fuel_system=FuelSystemConfig(manifold_volume_ft3=volume),
        ))
        array.set_load_following_target_mw(44.85)
        for second in range(300):
            array.advance(second, 1.0)
        return array
    default = run(FuelSystemConfig().manifold_volume_ft3)
    authored = run(767)
    assert default.minimum_inlet_pressure_psig >= 12
    assert default.pressure_derate_alert is None
    assert authored.minimum_inlet_pressure_psig < 12
    assert authored.pressure_derate_alert["common_mode"] is True
    assert authored.pressure_derate_alert["affected_block_count"] == 138


def test_g2_500ft3_rate_minima_are_common_mode_and_rate_invariant():
    minima = []
    for requested_rate in (.5, 1.0, 2.0, 4.0):
        array = BlockFuelCellArray(BlockFuelCellConfig(
            asset_id=f"fc-rate-{requested_rate}",
            block_rated_mw=.325,
            block_count=138,
            initial_hot_standby_blocks=138,
            requested_commit_rate_blocks_per_s=requested_rate,
            hot_start_s=.01,
            fuel_system=FuelSystemConfig(manifold_volume_ft3=500),
        ))
        array.set_load_following_target_mw(44.85)
        minimum = 99.0
        saw_common_mode_derate = False
        for second in range(300):
            array.advance(second, 1.0)
            minimum = min(
                minimum, array.minimum_manifold_pressure_psig or minimum
            )
            if array.pressure_derate_alert:
                saw_common_mode_derate = (
                    array.pressure_derate_alert["common_mode"] is True
                    and array.pressure_derate_alert["affected_block_count"] == 138
                )
            assert array.pressure_trip_alert is None
        minima.append(minimum)
        assert saw_common_mode_derate
    assert max(minima) - min(minima) <= .3


def test_g2_pressure_trip_is_one_common_mode_event_and_removes_availability():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-trip",
        block_rated_mw=.325,
        block_count=138,
        initial_running_blocks=0,
        initial_hot_standby_blocks=138,
        requested_commit_rate_blocks_per_s=138,
        hot_start_s=.01,
        fuel_system=FuelSystemConfig(manifold_volume_ft3=350),
    ))
    array.set_load_following_target_mw(44.85)
    for second in range(20):
        array.advance(second, 1.0)
        if array.pressure_trip_alert:
            break

    assert array.pressure_trip_alert["common_mode"] is True
    assert array.pressure_trip_alert["affected_block_count"] == 138
    assert array.available_mw == 0.0
    assert array.output_mw() == 0.0
    assert all(not block.tripped for block in array.blocks)


def test_g2_utilisation_clamp_is_hard_then_recovers():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-utilisation",
        block_rated_mw=.325,
        block_count=1,
        initial_hot_standby_blocks=1,
        requested_commit_rate_blocks_per_s=10,
        hot_start_s=.01,
        fuel_system=FuelSystemConfig(manifold_volume_ft3=1e9),
    ))
    array.set_load_following_target_mw(.325)
    array.advance(0.0, .1)
    assert array.utilisation_clamp_alert is not None
    assert 0.0 < array.output_mw() < .325
    assert array.fuel_binding_constraint == "utilisation"

    for second in range(1, 30):
        array.advance(second, 1.0)
    assert array.output_mw() == pytest.approx(.325)
    assert array.utilisation_clamp_alert is None


def test_g2_supply_cap_alert_is_distinct_from_utilisation_and_pressure_records():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-supply-cap",
        block_rated_mw=.325,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        fuel_system=FuelSystemConfig(
            manifold_volume_ft3=1e9,
            maximum_supply_flow_scfm=5.0,
        ),
    ))
    array.set_load_following_target_mw(.325)
    array.advance(0.0, 1.0)

    assert array.supply_limit_alert["asset_id"] == "fc-supply-cap"
    assert array.supply_limit_alert["maximum_supply_flow_scfm"] == 5.0
    assert array.pressure_derate_alert is None
    assert array.pressure_trip_alert is None


def test_g2_finite_supply_eventually_depletes_manifold_and_limits_output():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-finite-supply",
        block_rated_mw=.325,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        fuel_system=FuelSystemConfig(maximum_supply_flow_scfm=5.0),
    ))
    array.set_load_following_target_mw(.325)
    saw_supply_limit = False
    for second in range(1200):
        array.advance(second, 1.0)
        saw_supply_limit |= array.supply_limit_alert is not None
        if array.pressure_trip_alert:
            break

    assert saw_supply_limit
    assert array.pressure_trip_alert["common_mode"] is True
    assert array.output_mw() == 0.0
    assert array.available_mw == 0.0


def test_g2_large_manifold_buffers_regulator_cap_by_spending_pressure_inventory():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-buffered-cap",
        block_rated_mw=.325,
        block_count=1,
        initial_running_blocks=1,
        initial_hot_standby_blocks=0,
        fuel_system=FuelSystemConfig(
            manifold_volume_ft3=1e9,
            maximum_supply_flow_scfm=5.0,
        ),
    ))
    array.set_load_following_target_mw(.325)
    initial_pressure = array.manifold_pressure_psig
    array.advance(0.0, 10.0)

    # The regulator obeys its cap. The cell can temporarily draw more only
    # because the explicitly modelled manifold inventory is depleted, which is
    # visible as falling pressure rather than invented supply.
    assert array._regulator_flow_scfm <= 5.0
    assert array.fuel_delivered_scfm > 5.0
    assert array.manifold_pressure_psig < initial_pressure
    assert array.supply_limit_alert is not None


def test_g2_pressure_derate_does_not_create_false_reserve_headroom():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-reserve-truth",
        block_rated_mw=.325,
        block_count=138,
        initial_hot_standby_blocks=138,
        hot_start_s=.01,
        requested_commit_rate_blocks_per_s=138,
        fuel_system=FuelSystemConfig(manifold_volume_ft3=767),
    ))
    array.set_load_following_target_mw(44.85)
    for second in range(10):
        array.advance(second, 1.0)

    assert array.pressure_derate_alert["common_mode"] is True
    summary = array.readiness_summary(fast_window_s=60.0)
    assert array.available_mw == pytest.approx(array.output_mw())
    assert summary["available_now_mw"] == pytest.approx(0.0)
    assert summary["available_fast_mw"] == pytest.approx(0.0)


def test_g2_thermal_binding_and_interval_commit_credit_do_not_bank():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-thermal",
        block_rated_mw=.325,
        block_count=2,
        initial_hot_standby_blocks=2,
        requested_commit_rate_blocks_per_s=1.0,
        hot_start_s=10.0,
        fuel_system=FuelSystemConfig(manifold_volume_ft3=1e9),
    ))
    array.set_load_following_target_mw(.325)
    array.advance(0.0, 1.0)
    assert array.achieved_commit_rate_blocks_per_s == 0.0
    assert array.fuel_binding_constraint == "thermal"

    # Synchronising capacity already covers the request; nine idle seconds
    # cannot bank starts for a later target increase.
    for second in range(1, 10):
        array.advance(second, 1.0)
    array.set_load_following_target_mw(.65)
    array.advance(10.0, 1.0)
    assert sum(block.dwell_s > 0 for block in array.blocks) <= 1


def test_g2_schema_provenance_and_legacy_commit_rate_alias():
    unit = FuelCellUnitSpec.model_validate({
        "asset_id": "fc-schema",
        "block_rated_mw": .325,
        "block_count": 1,
        "commit_rate_blocks_per_s": 2.0,
        "fuel_system": {},
    })
    assert unit.requested_commit_rate_blocks_per_s == 2.0
    assert unit.fuel_system.provenance == {
        "supply_pressure_psig": "vendor_published",
        "minimum_block_inlet_pressure_psig": "vendor_published",
        "block_trip_pressure_psig": "proposed",
        "manifold_volume_ft3": "proposed",
        "regulator_time_constant_s": "proposed",
        "regulator_droop_fraction": "proposed",
        "distribution_loss_psi": "proposed",
        "maximum_supply_flow_scfm": "site_specific",
        "delivered_to_cell_time_constant_s": "proposed",
        "max_fuel_utilisation": "proposed",
    }


def test_g2_annual_co2_sanity_at_50mw_and_92_percent_capacity_factor():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-annual",
        block_rated_mw=.25,
        block_count=200,
        initial_running_blocks=200,
        initial_hot_standby_blocks=0,
        degradation_fraction=.5,
    ))
    array.set_load_following_target_mw(50.0 * .92)
    array.advance(0.0, 365 * 24 * 60 * 60)

    assert array.output_mw() == pytest.approx(46.0)
    assert array.cumulative_co2_tonnes == pytest.approx(138_980, rel=.01)


def test_g2_group_validation_and_default_implicit_group():
    implicit = FuelCellUnitSpec(
        asset_id="fc-implicit", block_rated_mw=.325, block_count=6
    )
    assert implicit.electrical_groups == []

    with pytest.raises(ValidationError, match="sum exactly"):
        FuelCellUnitSpec(
            asset_id="fc-bad-sum",
            block_rated_mw=.325,
            block_count=6,
            electrical_groups=[
                {"electrical_group_id": "board-a", "block_count": 4},
                {"electrical_group_id": "board-b", "block_count": 1},
            ],
        )
    with pytest.raises(ValidationError, match="unique"):
        FuelCellUnitSpec(
            asset_id="fc-duplicate",
            block_rated_mw=.325,
            block_count=6,
            electrical_groups=[
                {"electrical_group_id": "board-a", "block_count": 4},
                {"electrical_group_id": "board-a", "block_count": 2},
            ],
        )
    with pytest.raises(ValidationError, match="human-meaningful"):
        FuelCellUnitSpec(
            asset_id="fc-numeric-group",
            block_rated_mw=.325,
            block_count=6,
            electrical_groups=[
                {"electrical_group_id": "123", "block_count": 6},
            ],
        )


def test_g2_fuel_configuration_provenance_defaults():
    unit = FuelCellUnitSpec(
        asset_id="fc-provenance",
        block_rated_mw=.325,
        block_count=1,
        provenance={"hot_standby_fuel_fraction": "vendor_published"},
    )
    assert unit.provenance == {
        "grid_forming": "site_specific",
        "power_factor": "site_specific",
        "intrinsic_output_ramp_rate_mw_per_s": "proposed",
        "reactive_capability_mvar": "proposed",
        "ieee_1547_category": "site_specific",
        "beginning_of_life_heat_rate_btu_per_kwh": "vendor_published",
        "end_of_life_heat_rate_btu_per_kwh": "vendor_published",
        "degradation_fraction": "site_specific",
        "part_load_heat_rate_multiplier": "proposed",
        "gas_heating_value_btu_per_scf": "site_specific",
        "hot_standby_fuel_fraction": "proposed",
        "gas_price_usd_per_mmbtu": "site_specific",
    }


def test_g2_readiness_proposal_reports_horizon_fuel_cost_and_qualification():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-readiness",
        block_rated_mw=.325,
        block_count=100,
        initial_running_blocks=0,
        initial_hot_standby_blocks=0,
    ))
    proposal = BlockFuelCellReadinessController(AdvisoryGate()).evaluate(
        array, [32.5], sim_time=0.0, confidence=1.0
    )

    assert proposal is not None
    estimate = proposal.fuel_hold_estimate
    assert estimate["target_hot_block_count"] == 100
    assert estimate["hold_duration_s"] == pytest.approx(28_805)
    assert estimate["total_standby_fuel_scf"] > 0
    assert estimate["total_standby_fuel_mmbtu"] > 0
    assert estimate["monetary_cost_usd"] == pytest.approx(
        estimate["total_standby_fuel_mmbtu"] * 5.0
    )
    assert "low-confidence" in estimate["confidence_qualification"]
    assert proposal.requires_confirmation is True


def test_g2_readiness_proposal_without_price_reports_quantity_only():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc-no-price",
        block_rated_mw=.325,
        block_count=2,
        initial_running_blocks=0,
        initial_hot_standby_blocks=0,
        gas_price_usd_per_mmbtu=None,
    ))
    proposal = BlockFuelCellReadinessController(AdvisoryGate()).evaluate(
        array, [.65], sim_time=0.0, confidence=1.0
    )

    assert proposal is not None
    assert proposal.fuel_hold_estimate["total_standby_fuel_mmbtu"] > 0
    assert proposal.fuel_hold_estimate["monetary_cost_usd"] is None
    assert "no gas price configured" in proposal.reasoning