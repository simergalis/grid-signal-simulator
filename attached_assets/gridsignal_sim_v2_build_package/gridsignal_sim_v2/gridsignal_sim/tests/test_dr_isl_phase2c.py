"""TC-ISL-17/18: D8 canonical input and D9b diagnostic-only warning."""
import copy
import json
from pathlib import Path

import pytest

from api.schemas import ScenarioSpec, StartRunResponse
from runtime.build_warnings import reserve_capacity_warnings
from runtime.phase2b_reference import apply_study_fuel_model
from runtime.scenario_factory import build_run_context_from_spec
from study_harness.executor import BASE_DEMO_SCENARIO_ID, StudyRunExecutor

# PROPOSED_HERE: locate the catalogue fixture rather than duplicate scenario inputs.
SOURCE = Path(__file__).resolve().parents[1] / "config/scenarios" / (
    BASE_DEMO_SCENARIO_ID + ".json"
)


def test_tc_isl_17_base_demo_uses_canonical_spec_then_recorded_overrides(tmp_path):
    expected = ScenarioSpec.model_validate_json(SOURCE.read_bytes()).model_dump(mode="json")
    expected["turbine_units"] = apply_study_fuel_model(expected["turbine_units"])
    executor = StudyRunExecutor(output_dir=tmp_path)
    actual = executor._expanded_spec(BASE_DEMO_SCENARIO_ID, None, None)
    provenance = actual.pop("study_input_provenance")
    assert actual == expected
    assert len(actual["diesel_units"]) == 1
    assert provenance["canonicalised"] is True
    assert provenance["post_validation_overrides"] == [
        {"field": "turbine_units", "operation": "apply_study_fuel_model"}
    ]
    overridden = executor._expanded_spec(
        BASE_DEMO_SCENARIO_ID, {"turbine_forecast_lead_seconds": 90.0}, 120.0
    )
    assert overridden["end_sim_time"] == 120.0
    assert overridden["turbine_forecast_lead_seconds"] == 90.0
    assert overridden["study_input_provenance"]["post_validation_overrides"][1:] == [
        {"field": "end_sim_time", "value": 120.0},
        {"operation": "parameter_overrides",
         "value": {"turbine_forecast_lead_seconds": 90.0}},
    ]


@pytest.mark.parametrize("start_s,expected_count", [(3600.0, 1), (10.0, 0)])
def test_tc_isl_18_floor_warning_is_diagnostic_only(start_s, expected_count, caplog):
    # D9b fixture explicitly covers the legacy over-capacity floor and D9c timing.
    raw = json.loads(SOURCE.read_bytes())
    raw["diesel_power_block"]["delta_t_start_s"] = start_s
    spec = ScenarioSpec.model_validate_json(json.dumps(raw)).model_dump(mode="json")
    ctx = build_run_context_from_spec("tc-isl-18", spec)
    bess = ctx.sim_state.bess_units[0]
    arbitrator = ctx.sim_state.arbitrator
    expected_floor = 2.5 * 30.0 * (start_s + 60.0) / 3600.0
    # DR D2-r/C2(c), approved TC-ISL-18 update: retain all three reserve terms.
    basis = arbitrator.reserve_floor_basis[bess.config.asset_id]
    expected_floor = max(expected_floor, basis["depth_reserve_mwh"], basis["d2r_term_mwh"])
    assert arbitrator.soc_floor_mwh(bess) == pytest.approx(expected_floor)
    warnings = ctx.metadata["build_warnings"]
    assert len(warnings) == expected_count
    assert sum("DR D9b build warning:" in r.message for r in caplog.records) == expected_count
    if warnings:
        warning = warnings[0]
        assert warning["bess_id"] == bess.config.asset_id
        assert warning["floor_mwh"] == pytest.approx(76.25)
        assert warning["usable_mwh"] == 60.0
        assert warning["winning_term"] == "diesel_floor"
        assert warning["diesel_units"][0]["delta_t_start_s"] == start_s
        assert warning["diesel_units"][0]["residual_ramp_s"] == 60.0
    before = (bess.soc_mwh, arbitrator.soc_floor_mwh(bess),
              copy.deepcopy(arbitrator).tick(20.0, 5.0))
    assert reserve_capacity_warnings(ctx.sim_state) == warnings
    after = (bess.soc_mwh, arbitrator.soc_floor_mwh(bess),
             copy.deepcopy(arbitrator).tick(20.0, 5.0))
    assert after == before
    assert StartRunResponse(run_id=ctx.run_id, build_warnings=warnings).build_warnings == warnings
