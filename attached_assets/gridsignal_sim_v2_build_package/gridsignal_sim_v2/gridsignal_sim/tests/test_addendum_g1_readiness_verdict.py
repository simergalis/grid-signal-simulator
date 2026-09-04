from core.fuel_cell_module import BlockFuelCellArray, BlockFuelCellConfig
from api.schemas import ScenarioSpec
from runtime.advisory_gate import AdvisoryGate
from runtime.scenario_factory import build_run_context_from_spec
from runtime.fuel_cell_readiness import BlockFuelCellReadinessController
from runtime.verdict import EvalRow, evaluate_verdict


def test_readiness_controller_is_advisory_and_uses_full_start_horizon():
    array = BlockFuelCellArray(BlockFuelCellConfig(
        asset_id="fc", block_rated_mw=.325, block_count=246,
        initial_running_blocks=62, initial_hot_standby_blocks=92,
        cold_start_s=8 * 3600, warm_start_s=4 * 3600, hot_start_s=60,
        readiness_dwell_s=30,
    ))
    controller = BlockFuelCellReadinessController(AdvisoryGate())
    proposal = controller.evaluate(array, [20., 80.], sim_time=0, confidence=.9)
    assert proposal is not None
    assert proposal.requires_confirmation
    assert "hot=184" in proposal.reasoning
    assert "horizon=28890s" in proposal.reasoning
    assert [block.state.value for block in array.blocks].count("warming") == 0
    assert controller.evaluate(array, [80.], sim_time=15, confidence=.4) is None


def test_g1_fuel_cell_assertions_cover_telemetry_and_eligibility():
    rows = [
        EvalRow(
            i, 80., .8, False, 80., 50.05, 50.05, 154, 92, 0,
            sim_time_seconds=i * 15.0,
            fuel_cell_cold_warming_contingency_contribution_mw=0.0,
        )
        for i in range(77)
    ]
    result = evaluate_verdict([
        {"check": "persistent_fuel_cell_deficit", "expected_deficit_mw": 29.95,
         "duration_s": 19 * 60, "tick_seconds": 15},
        {"check": "peak_fuel_cell_array_output", "expected_mw": 50.05},
        {"check": "no_cold_warming_contingency_capacity", "block_rated_mw": .325},
        {"check": "fuel_cell_commanded_and_achieved_reported"},
    ], rows, dropped_ticks=0)
    assert result.overall == "PASS"


def test_deficit_duration_uses_retained_timestamps_not_caller_cadence():
    rows = [
        EvalRow(
            i, 80., .8, False, 80., 50.05,
            sim_time_seconds=i * 5.0,
        )
        for i in range(1, 5)
    ]
    result = evaluate_verdict(
        [{
            "check": "persistent_fuel_cell_deficit",
            "expected_deficit_mw": 29.95,
            "duration_s": 30,
            # Deliberately false: observed cadence is 5 s, not 15 s.
            "tick_seconds": 15,
        }],
        rows,
        dropped_ticks=0,
    )
    assert result.assertions[0].status == "FAIL"


def test_deficit_gap_cannot_be_used_to_prove_duration():
    rows = [
        EvalRow(1, 80., .8, False, 80., 50.05, sim_time_seconds=5.0),
        EvalRow(3, 80., .8, False, 80., 50.05, sim_time_seconds=15.0),
    ]
    result = evaluate_verdict(
        [{"check": "persistent_fuel_cell_deficit", "expected_deficit_mw": 29.95,
          "duration_s": 10}],
        rows,
        dropped_ticks=1,
    )
    assert result.assertions[0].status == "INCONCLUSIVE"


def test_declining_fuel_cell_reserve_alert_is_existential_and_gap_aware():
    retained_alert = EvalRow(
        1, 80., .8, False,
        fuel_cell_declining_reserve_alert={"event_fast_window_s": 30.0},
    )
    assert evaluate_verdict(
        [{"check": "declining_fuel_cell_reserve_alert_fires"}],
        [retained_alert],
        dropped_ticks=1,
    ).assertions[0].status == "PASS"

    missing_with_gap = evaluate_verdict(
        [{"check": "declining_fuel_cell_reserve_alert_fires"}],
        [EvalRow(1, 80., .8, False)],
        dropped_ticks=1,
    )
    assert missing_with_gap.assertions[0].status == "INCONCLUSIVE"

    missing_without_gap = evaluate_verdict(
        [{"check": "declining_fuel_cell_reserve_alert_fires"}],
        [EvalRow(1, 80., .8, False)],
        dropped_ticks=0,
    )
    assert missing_without_gap.assertions[0].status == "FAIL"


def test_cold_warming_assertion_requires_accounting_telemetry():
    result = evaluate_verdict(
        [{"check": "no_cold_warming_contingency_capacity"}],
        [EvalRow(1, 80., .8, False, fuel_cell_available_now_mw=0.0)],
        dropped_ticks=0,
    )
    assert result.assertions[0].status == "INCONCLUSIVE"


def test_declared_array_auto_enables_and_injects_nonzero_output_verdict_guard():
    spec_data = {
        "name": "array-source-of-truth",
        "fuel_cell_units": [{
            "asset_id": "fc-array", "block_rated_mw": 1.0, "block_count": 1,
        }],
    }
    # Legacy JSON that omits the toggle has an effective explicit enable.
    spec = ScenarioSpec.model_validate(spec_data)
    assert spec.fuel_cell_enabled is True
    context = build_run_context_from_spec(
        "fc-guard", spec.model_dump(mode="json")
    )
    assert context.assertions[-1].check == "fuel_cell_output_nonzero"

    failed = evaluate_verdict(
        context.assertions,
        [EvalRow(1, 1.0, .9, False, fuel_cell_achieved_output_mw=0.0)],
        dropped_ticks=0,
    )
    passed = evaluate_verdict(
        context.assertions,
        [EvalRow(1, 1.0, .9, False, fuel_cell_achieved_output_mw=0.1)],
        dropped_ticks=0,
    )
    assert failed.overall == "FAIL"
    assert failed.assertions[-1].status == "FAIL"
    assert passed.overall == "PASS"
    assert passed.assertions[-1].status == "PASS"