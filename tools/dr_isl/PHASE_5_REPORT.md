# DR-2026-10-20-ISLAND-COLLAPSE — Phase 5 D3 / R5

State: COMPLETE — R5 gates passed.

Application baseline: fd87fc75b995f19556f598cdc5b0f443a4edce75.
Resumption HEAD: 1db4393. Original candidate stash 3b856fd is retained.
Evidence is incremental in tools/dr_isl/phase5/R5/. No physics/control/scenario JSON changes.

## R5.1 Suite waiver and current gate
```json
{
  "pytest_exit_code": 1,
  "junit_counts": {
    "tests": 2241,
    "failures": 16,
    "errors": 0,
    "skipped": 26,
    "passed": 2199
  },
  "added": [
    "tests/test_gpu_load_profile.py::test_gpu_load_profile"
  ],
  "removed": [],
  "remaining": [
    "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
    "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
    "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar",
    "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment",
    "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve",
    "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names",
    "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel",
    "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited",
    "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context",
    "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants",
    "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude",
    "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait",
    "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ],
  "passed_gate": true,
  "pytest_summary": "16 failed, 2196 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 848.20s (0:14:08)",
  "pytest_counts": {
    "passed": 2196,
    "failed": 16,
    "skipped": 3,
    "xfailed": 23
  },
  "gpu_load_profile": {
    "outcome": "failed",
    "stage": "call",
    "duration": 13.676032540000051,
    "failure": "tests/test_gpu_load_profile.py:284: in test_gpu_load_profile\n    _run_test()\ntests/test_gpu_load_profile.py:169: in _run_test\n    assert abs(frac - expected_frac) < TOLERANCE, (\nE   AssertionError: [FAIL-A] phase-3 sim_t=2400.0s: gpu_load_fraction=0.5 expected 0.1\nE   assert 0.4 < 1e-06\nE    +  where 0.4 = abs((0.5 - 0.1))"
  },
  "approved_waiver": "tests/test_gpu_load_profile.py::test_gpu_load_profile",
  "waived_added": [
    "tests/test_gpu_load_profile.py::test_gpu_load_profile"
  ],
  "unwaived_added": []
}
```
Known failure modes (not only node IDs):
```json
{
  "known_failure_reviews": [
    {
      "nodeid": "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
      "base_assertions": [
        "E   AssertionError: I4: asset_delivery_error_mw must be non-zero (fleet under-delivers); got 0.000000000",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.05253, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0x7f37c9ad6ac0>(0.0, abs=1e-06)",
        "E    +    where <function approx at 0x7f37c9ad6ac0> = pytest.approx"
      ],
      "after_assertions": [
        "E   AssertionError: I4: asset_delivery_error_mw must be non-zero (fleet under-delivers); got 0.000000000",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.05253, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0x7f5d31d4ea20>(0.0, abs=1e-06)",
        "E    +    where <function approx at 0x7f5d31d4ea20> = pytest.approx"
      ],
      "base_signature": [
        "E    +    where <function approx at 0xADDR> = pytest.approx",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0xADDR>(0.0, abs=1e-06)",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.05253, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E   AssertionError: I4: asset_delivery_error_mw must be non-zero (fleet under-delivers); got 0.000000000",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06"
      ],
      "after_signature": [
        "E    +    where <function approx at 0xADDR> = pytest.approx",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0xADDR>(0.0, abs=1e-06)",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.05253, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E   AssertionError: I4: asset_delivery_error_mw must be non-zero (fleet under-delivers); got 0.000000000",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
      "base_assertions": [
        "E   AssertionError: p_min_stable_frac default must be 0.40 (CHOSEN catalogue value).  Got 0.35",
        "E   assert 0.35 == 0.4 \u00b1 4.0e-07",
        "E     ",
        "E     comparison failed",
        "E     Obtained: 0.35",
        "E     Expected: 0.4 \u00b1 4.0e-07"
      ],
      "after_assertions": [
        "E   AssertionError: p_min_stable_frac default must be 0.40 (CHOSEN catalogue value).  Got 0.35",
        "E   assert 0.35 == 0.4 \u00b1 4.0e-07",
        "E     ",
        "E     comparison failed",
        "E     Obtained: 0.35",
        "E     Expected: 0.4 \u00b1 4.0e-07"
      ],
      "base_signature": [
        "E     ",
        "E     Expected: 0.4 \u00b1 4.0e-07",
        "E     Obtained: 0.35",
        "E     comparison failed",
        "E   AssertionError: p_min_stable_frac default must be 0.40 (CHOSEN catalogue value).  Got 0.35",
        "E   assert 0.35 == 0.4 \u00b1 4.0e-07"
      ],
      "after_signature": [
        "E     ",
        "E     Expected: 0.4 \u00b1 4.0e-07",
        "E     Obtained: 0.35",
        "E     comparison failed",
        "E   AssertionError: p_min_stable_frac default must be 0.40 (CHOSEN catalogue value).  Got 0.35",
        "E   assert 0.35 == 0.4 \u00b1 4.0e-07"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar",
      "base_assertions": [
        "E   AssertionError: assert {'load_fuel_m..._mmbtu': 16.0} == {'load_fuel_m..._mmbtu': 16.0}",
        "E     ",
        "E     Omitting 2 identical items, use -vv to show",
        "E     Differing items:",
        "E     {'hot_standby_fuel_mmbtu': 0.039236111} != {'hot_standby_fuel_mmbtu': 0.039237}",
        "E     {'load_fuel_mmbtu': 690.133782974} != {'load_fuel_mmbtu': 690.133783}",
        "E     Use -v to get more diff"
      ],
      "after_assertions": [
        "E   AssertionError: assert {'load_fuel_m..._mmbtu': 16.0} == {'load_fuel_m..._mmbtu': 16.0}",
        "E     ",
        "E     Omitting 2 identical items, use -vv to show",
        "E     Differing items:",
        "E     {'load_fuel_mmbtu': 690.133782974} != {'load_fuel_mmbtu': 690.133783}",
        "E     {'hot_standby_fuel_mmbtu': 0.039236111} != {'hot_standby_fuel_mmbtu': 0.039237}",
        "E     Use -v to get more diff"
      ],
      "base_signature": [
        "E     ",
        "E     Differing items:",
        "E     Omitting 2 identical items, use -vv to show",
        "E     Use -v to get more diff",
        "E     {'hot_standby_fuel_mmbtu': 0.039236111} != {'hot_standby_fuel_mmbtu': 0.039237}",
        "E     {'load_fuel_mmbtu': 690.133782974} != {'load_fuel_mmbtu': 690.133783}",
        "E   AssertionError: assert {'load_fuel_m..._mmbtu': 16.0} == {'load_fuel_m..._mmbtu': 16.0}"
      ],
      "after_signature": [
        "E     ",
        "E     Differing items:",
        "E     Omitting 2 identical items, use -vv to show",
        "E     Use -v to get more diff",
        "E     {'hot_standby_fuel_mmbtu': 0.039236111} != {'hot_standby_fuel_mmbtu': 0.039237}",
        "E     {'load_fuel_mmbtu': 690.133782974} != {'load_fuel_mmbtu': 690.133783}",
        "E   AssertionError: assert {'load_fuel_m..._mmbtu': 16.0} == {'load_fuel_m..._mmbtu': 16.0}"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment",
      "base_assertions": [
        "E   assert ()"
      ],
      "after_assertions": [
        "E   assert ()"
      ],
      "base_signature": [
        "E   assert ()"
      ],
      "after_signature": [
        "E   assert ()"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve",
      "base_assertions": [
        "E   assert 5.117526258383993 == 5.52 \u00b1 5.5e-06",
        "E     ",
        "E     comparison failed",
        "E     Obtained: 5.117526258383993",
        "E     Expected: 5.52 \u00b1 5.5e-06"
      ],
      "after_assertions": [
        "E   assert 5.117526258383993 == 5.52 \u00b1 5.5e-06",
        "E     ",
        "E     comparison failed",
        "E     Obtained: 5.117526258383993",
        "E     Expected: 5.52 \u00b1 5.5e-06"
      ],
      "base_signature": [
        "E     ",
        "E     Expected: 5.52 \u00b1 5.5e-06",
        "E     Obtained: 5.117526258383993",
        "E     comparison failed",
        "E   assert 5.117526258383993 == 5.52 \u00b1 5.5e-06"
      ],
      "after_signature": [
        "E     ",
        "E     Expected: 5.52 \u00b1 5.5e-06",
        "E     Obtained: 5.117526258383993",
        "E     comparison failed",
        "E   assert 5.117526258383993 == 5.52 \u00b1 5.5e-06"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names",
      "base_assertions": [
        "E   AssertionError: Expected a regression-test display name, got '02 Regression test \u2014 Healthy training baseline'",
        "E   assert False",
        "E    +  where False = <built-in method startswith of str object at 0x7f37b5c6f550>('Regression test \u2014')",
        "E    +    where <built-in method startswith of str object at 0x7f37b5c6f550> = '02 Regression test \u2014 Healthy training baseline'.startswith",
        "E    +      where '02 Regression test \u2014 Healthy training baseline' = ScenarioRecord(scenario_id='regression-test-healthy-training-baseline', name='02 Regression test \u2014 Healthy training ba...:null}', created_at=datetime.datetime(2026, 10, 22, 19, 0, 11, 692884, tzinfo=datetime.timezone.utc), last_run_id=None).name"
      ],
      "after_assertions": [
        "E   AssertionError: Expected a regression-test display name, got '02 Regression test \u2014 Healthy training baseline'",
        "E   assert False",
        "E    +  where False = <built-in method startswith of str object at 0x7f5d1dfd25b0>('Regression test \u2014')",
        "E    +    where <built-in method startswith of str object at 0x7f5d1dfd25b0> = '02 Regression test \u2014 Healthy training baseline'.startswith",
        "E    +      where '02 Regression test \u2014 Healthy training baseline' = ScenarioRecord(scenario_id='regression-test-healthy-training-baseline', name='02 Regression test \u2014 Healthy training ba...null}', created_at=datetime.datetime(2026, 10, 22, 20, 42, 16, 276763, tzinfo=datetime.timezone.utc), last_run_id=None).name"
      ],
      "base_signature": [
        "E    +      where '02 Regression test \u2014 Healthy training baseline' = ScenarioRecord(<context repr>)",
        "E    +    where <built-in method startswith of str object at 0xADDR> = '02 Regression test \u2014 Healthy training baseline'.startswith",
        "E    +  where False = <built-in method startswith of str object at 0xADDR>('Regression test \u2014')",
        "E   AssertionError: Expected a regression-test display name, got '02 Regression test \u2014 Healthy training baseline'",
        "E   assert False"
      ],
      "after_signature": [
        "E    +      where '02 Regression test \u2014 Healthy training baseline' = ScenarioRecord(<context repr>)",
        "E    +    where <built-in method startswith of str object at 0xADDR> = '02 Regression test \u2014 Healthy training baseline'.startswith",
        "E    +  where False = <built-in method startswith of str object at 0xADDR>('Regression test \u2014')",
        "E   AssertionError: Expected a regression-test display name, got '02 Regression test \u2014 Healthy training baseline'",
        "E   assert False"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel",
      "base_assertions": [
        "E   AssertionError: B1a: delivery fault must appear in asset_delivery_error_mw; got 0.000000000  (turbine_out=0.000000, gt_setpoint=0.000000)",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.10506, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0x7f37c9ad6ac0>(0.0, abs=1e-06)",
        "E    +    where <function approx at 0x7f37c9ad6ac0> = pytest.approx"
      ],
      "after_assertions": [
        "E   AssertionError: B1a: delivery fault must appear in asset_delivery_error_mw; got 0.000000000  (turbine_out=0.000000, gt_setpoint=0.000000)",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.10506, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0x7f5d31d4ea20>(0.0, abs=1e-06)",
        "E    +    where <function approx at 0x7f5d31d4ea20> = pytest.approx"
      ],
      "base_signature": [
        "E    +    where <function approx at 0xADDR> = pytest.approx",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0xADDR>(0.0, abs=1e-06)",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.10506, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E   AssertionError: B1a: delivery fault must appear in asset_delivery_error_mw; got 0.000000000  (turbine_out=0.000000, gt_setpoint=0.000000)",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06"
      ],
      "after_signature": [
        "E    +    where <function approx at 0xADDR> = pytest.approx",
        "E    +  and   0.0 \u00b1 1.0e-06 = <function approx at 0xADDR>(0.0, abs=1e-06)",
        "E    +  where 0.0 = TickResult(run_id='test', tick_index=1, sim_time_seconds=5.1, p_compute_demand_mw=0.10506, p_cooling_demand_mw=0.0, p_...sfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id='gt-1', slurm_metrics=None).asset_delivery_error_mw",
        "E   AssertionError: B1a: delivery fault must appear in asset_delivery_error_mw; got 0.000000000  (turbine_out=0.000000, gt_setpoint=0.000000)",
        "E   assert 0.0 != 0.0 \u00b1 1.0e-06"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited",
      "base_assertions": [
        "E   AttributeError: 'str' object has no attribute 'value'"
      ],
      "after_assertions": [
        "E   AttributeError: 'str' object has no attribute 'value'"
      ],
      "base_signature": [
        "E   AttributeError: 'str' object has no attribute 'value'"
      ],
      "after_signature": [
        "E   AttributeError: 'str' object has no attribute 'value'"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context",
      "base_assertions": [
        "E   AssertionError: assert '43 demo-20mw' == 'demo-20mw'",
        "E     ",
        "E     - demo-20mw",
        "E     + 43 demo-20mw",
        "E     ? +++"
      ],
      "after_assertions": [
        "E   AssertionError: assert '43 demo-20mw' == 'demo-20mw'",
        "E     ",
        "E     - demo-20mw",
        "E     + 43 demo-20mw",
        "E     ? +++"
      ],
      "base_signature": [
        "E     ",
        "E     + 43 demo-20mw",
        "E     - demo-20mw",
        "E     ? +++",
        "E   AssertionError: assert '43 demo-20mw' == 'demo-20mw'"
      ],
      "after_signature": [
        "E     ",
        "E     + 43 demo-20mw",
        "E     - demo-20mw",
        "E     ? +++",
        "E   AssertionError: assert '43 demo-20mw' == 'demo-20mw'"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants",
      "base_assertions": [
        "E   AssertionError: What does GridSignal do for someone running a GPU data center?",
        "E   assert 'behind-the-m...arket-context' == 'gridsignal-operator-benefits'",
        "E     ",
        "E     - gridsignal-operator-benefits",
        "E     + behind-the-meter-market-context"
      ],
      "after_assertions": [
        "E   AssertionError: What does GridSignal do for someone running a GPU data center?",
        "E   assert 'behind-the-m...arket-context' == 'gridsignal-operator-benefits'",
        "E     ",
        "E     - gridsignal-operator-benefits",
        "E     + behind-the-meter-market-context"
      ],
      "base_signature": [
        "E     ",
        "E     + behind-the-meter-market-context",
        "E     - gridsignal-operator-benefits",
        "E   AssertionError: What does GridSignal do for someone running a GPU data center?",
        "E   assert 'behind-the-m...arket-context' == 'gridsignal-operator-benefits'"
      ],
      "after_signature": [
        "E     ",
        "E     + behind-the-meter-market-context",
        "E     - gridsignal-operator-benefits",
        "E   AssertionError: What does GridSignal do for someone running a GPU data center?",
        "E   assert 'behind-the-m...arket-context' == 'gridsignal-operator-benefits'"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude",
      "base_assertions": [
        "E   AssertionError: assert 'does not replace or directly command' in '**Grounded GridSignal guidance**\\n\\n- The financing pressure around long-lived power assets and shorter GPU contract ...heduler queue and allocation signals to provide an earlier view of power demand while the job is still waiting to run.'"
      ],
      "after_assertions": [
        "E   AssertionError: assert 'does not replace or directly command' in '**Grounded GridSignal guidance**\\n\\n- The financing pressure around long-lived power assets and shorter GPU contract ...heduler queue and allocation signals to provide an earlier view of power demand while the job is still waiting to run.'"
      ],
      "base_signature": [
        "E   AssertionError: assert 'does not replace or directly command' in '**Grounded GridSignal guidance**\\n\\n- The financing pressure around long-lived power assets and shorter GPU contract ...heduler queue and allocation signals to provide an earlier view of power demand while the job is still waiting to run.'"
      ],
      "after_signature": [
        "E   AssertionError: assert 'does not replace or directly command' in '**Grounded GridSignal guidance**\\n\\n- The financing pressure around long-lived power assets and shorter GPU contract ...heduler queue and allocation signals to provide an earlier view of power demand while the job is still waiting to run.'"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait",
      "base_assertions": [
        "E   AssertionError: assert '24 Kubernete...ce Queue Demo' == 'Kubernetes S...ce Queue Demo'",
        "E     ",
        "E     - Kubernetes Scheduler - Resource Queue Demo",
        "E     + 24 Kubernetes Scheduler - Resource Queue Demo",
        "E     ? +++"
      ],
      "after_assertions": [
        "E   AssertionError: assert '24 Kubernete...ce Queue Demo' == 'Kubernetes S...ce Queue Demo'",
        "E     ",
        "E     - Kubernetes Scheduler - Resource Queue Demo",
        "E     + 24 Kubernetes Scheduler - Resource Queue Demo",
        "E     ? +++"
      ],
      "base_signature": [
        "E     ",
        "E     + 24 Kubernetes Scheduler - Resource Queue Demo",
        "E     - Kubernetes Scheduler - Resource Queue Demo",
        "E     ? +++",
        "E   AssertionError: assert '24 Kubernete...ce Queue Demo' == 'Kubernetes S...ce Queue Demo'"
      ],
      "after_signature": [
        "E     ",
        "E     + 24 Kubernetes Scheduler - Resource Queue Demo",
        "E     - Kubernetes Scheduler - Resource Queue Demo",
        "E     ? +++",
        "E   AssertionError: assert '24 Kubernete...ce Queue Demo' == 'Kubernetes S...ce Queue Demo'"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
      "base_assertions": [
        "E   AssertionError: api/ core-import violations found \u2014 build fails:",
        "E       api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E       api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E   assert not [\"api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden l...ngest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\"]"
      ],
      "after_assertions": [
        "E   AssertionError: api/ core-import violations found \u2014 build fails:",
        "E       api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E       api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E   assert not [\"api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden l...ngest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\"]"
      ],
      "base_signature": [
        "E       api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E       api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E   AssertionError: api/ core-import violations found \u2014 build fails:",
        "E   assert not [\"api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden l...ngest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\"]"
      ],
      "after_signature": [
        "E       api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E       api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
        "E   AssertionError: api/ core-import violations found \u2014 build fails:",
        "E   assert not [\"api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden l...ngest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\"]"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
      "base_assertions": [
        "E   assert False",
        "E    +  where False = all(<generator object test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load.<locals>.<genexpr> at 0x7f37b67c72e0>)"
      ],
      "after_assertions": [
        "E   assert False",
        "E    +  where False = all(<generator object test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load.<locals>.<genexpr> at 0x7f5d1df89d50>)"
      ],
      "base_signature": [
        "E    +  where False = all(<generator object test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load.<locals>.<genexpr> at 0xADDR>)",
        "E   assert False"
      ],
      "after_signature": [
        "E    +  where False = all(<generator object test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load.<locals>.<genexpr> at 0xADDR>)",
        "E   assert False"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    },
    {
      "nodeid": "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip",
      "base_assertions": [
        "E   AssertionError: turbine-1 was never set OFFLINE after the UNIT_TRIP event at t=120 s",
        "E   assert False"
      ],
      "after_assertions": [
        "E   AssertionError: turbine-1 was never set OFFLINE after the UNIT_TRIP event at t=120 s",
        "E   assert False"
      ],
      "base_signature": [
        "E   AssertionError: turbine-1 was never set OFFLINE after the UNIT_TRIP event at t=120 s",
        "E   assert False"
      ],
      "after_signature": [
        "E   AssertionError: turbine-1 was never set OFFLINE after the UNIT_TRIP event at t=120 s",
        "E   assert False"
      ],
      "same_failure_mode": true,
      "outcome": "failed"
    }
  ],
  "changed": [],
  "normalization": "Object addresses; ScenarioRecord context repr after the asserted name; dictionary-diff display ordering. Raw diagnostics and every asserted value are retained."
}
```

## R5.2 Layering fix
The candidate-only ScenarioSpec validator/import was removed. api/schemas.py equals the application baseline.
The sole build-warning producer remains runtime/build_warnings.py::frequency_configuration_warnings on resolved SiteConfig.
ScenarioSpec still validates. TC-ISL-08d asserts the runtime warning, unchanged null thresholds, and StartRunResponse.build_warnings.
Three literal violation lists: base, candidate before R5.2, and after R5.2:
```json
{
  "base": [
    "api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
    "api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)"
  ],
  "candidate_before_fix": [
    "api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
    "api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
    "api/schemas.py:2430: from core.frequency_reporting import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)"
  ],
  "after_fix": [
    "api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)",
    "api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)"
  ],
  "after_equals_base": true,
  "focused": "105 passed; 1 known plane-separation failure"
}
```

## Focused checks
105 passed; the one known API-static test fails with exactly the base violation list.
TC-ISL-07 is occupied by staging-start tests; frequency tests remain TC-ISL-08a–d (14 parametrized cases).
Full output and JUnit: R5/FOCUSED.txt and R5/FOCUSED.xml.

## R5.3 Frontend tracking — report only
```json
{
  "frontend_root": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend",
  "tracked_count": 3,
  "untracked_nonignored_count": 0,
  "untracked_ignored_count": 9976,
  "edited_paths": {
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx": false,
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts": false,
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts": true,
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/test/forecast_quality_panel.test.tsx": false
  },
  "counts_include_generated_and_dependency_files": true
}
```
The root counts include ignored dependency/build files. No .gitignore change and no new frontend files are tracked.
Only src/types.ts is already tracked among the edited files and can be committed separately.
App.tsx, panels/forecastQuality.ts and the panel test stay ignored/untracked in the working tree.
Their working-only changes are saved in the tracked tools/dr_isl/phase5/UI_CANDIDATE.diff.
Thus the full UI implementation is NOT recoverable from the code commits alone; apply/review that saved diff against the existing frontend.

## Requested R5 V1 subset
Base demo both arms: raw physical fields and all 27 existing study metrics match fd87fc7.
SJ-1 app path: raw physical fields/hash match; the app runner has no study metrics table.
```json
{
  "passed": true,
  "cases": [
    {
      "scenario": "scenario-uneven-multisched-01",
      "arm": "baseline",
      "ticks": 1440,
      "first_difference": null,
      "invalid_frequency_tick_count": 700,
      "first_invalid_tick": {
        "tick": 67,
        "sim_time_seconds": 335.0,
        "frequency_hz": 40.909530078118486
      },
      "frequency_min": -5.000866893367675,
      "frequency_max": 176.430848113831,
      "protection_configured": false,
      "existing_metrics_count": 27,
      "existing_metric_differences": {},
      "physical_identical": true,
      "compact_identical_excluding_new_flags": true,
      "added_metrics": {
        "protection_configured": false,
        "invalid_frequency_tick_count": 700,
        "invalid_frequency_fraction": 0.4861111111111111
      },
      "passed": true,
      "invalid_frequency_fraction": 0.4861111111111111
    },
    {
      "scenario": "scenario-uneven-multisched-01",
      "arm": "informed",
      "ticks": 1440,
      "first_difference": null,
      "invalid_frequency_tick_count": 614,
      "first_invalid_tick": {
        "tick": 123,
        "sim_time_seconds": 615.0,
        "frequency_hz": 66.19487030675623
      },
      "frequency_min": 59.534837314959205,
      "frequency_max": 169.8277840657461,
      "protection_configured": false,
      "existing_metrics_count": 27,
      "existing_metric_differences": {},
      "physical_identical": true,
      "compact_identical_excluding_new_flags": true,
      "added_metrics": {
        "protection_configured": false,
        "invalid_frequency_tick_count": 614,
        "invalid_frequency_fraction": 0.4263888888888889
      },
      "passed": true,
      "invalid_frequency_fraction": 0.4263888888888889
    },
    {
      "scenario": "scenario-equinix-sj-1",
      "arm": "app",
      "ticks": 720,
      "first_difference": null,
      "invalid_frequency_tick_count": 0,
      "first_invalid_tick": null,
      "frequency_min": 60.0,
      "frequency_max": 60.0,
      "protection_configured": true,
      "existing_metrics_count": 0,
      "existing_metric_differences": {},
      "physical_identical": true,
      "passed": true,
      "invalid_frequency_fraction": 0.0
    }
  ]
}
```

## Full invalid-frequency table (previously measured; retained, not re-run in R5)
Source: phase5/V1_V3_COMPLETE.json. The requested three-case subset above is the R5 recheck.
| scenario / arm | ticks | protection configured | invalid count | fraction | first invalid | min / max Hz |
|---|---:|---|---:|---:|---|---|
End-of-phase tracking counts:
```json
{
  "tracked_count": 3,
  "untracked_nonignored_count": 0,
  "untracked_ignored_count": 9976,
  "counts_include_dependencies_and_builds": true,
  "tracked_paths": [
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/public/scenario_spec_schema.json",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/AlertDock.tsx",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts"
  ]
}
```
| scenario-uneven-multisched-01 / baseline | 1440 | False | 700 | 0.4861111111111111 | {"tick": 67, "sim_time_seconds": 335.0, "frequency_hz": 40.909530078118486} | -5.000866893367675 / 176.430848113831 |
| scenario-uneven-multisched-01 / informed | 1440 | False | 614 | 0.4263888888888889 | {"tick": 123, "sim_time_seconds": 615.0, "frequency_hz": 66.19487030675623} | 59.534837314959205 / 169.8277840657461 |
| scenario-h1-k8s-ray-24h / baseline | 17280 | False | 13598 | 0.7869212962962963 | {"tick": 213, "sim_time_seconds": 1065.0, "frequency_hz": 70.13551986008387} | 17.23372983198947 / 224.93353102420852 |
| scenario-h1-k8s-ray-24h / informed | 17280 | False | 13712 | 0.7935185185185185 | {"tick": 213, "sim_time_seconds": 1065.0, "frequency_hz": 70.13551986008387} | 48.666827290428756 / 224.93353102420852 |
| scenario-h2-slurm-24h / baseline | 17280 | False | 16802 | 0.9723379629629629 | {"tick": 174, "sim_time_seconds": 870.0, "frequency_hz": 70.407865020299} | -225.278937529193 / 245.96773016794788 |
| scenario-h2-slurm-24h / informed | 17280 | False | 16955 | 0.9811921296296297 | {"tick": 174, "sim_time_seconds": 870.0, "frequency_hz": 70.407865020299} | 60.0 / 250.44034654726377 |
| S10_mit_supercloud_2021-08-11 / app | 17280 | False | 7264 | 0.4203703703703704 | {"tick": 1, "sim_time_seconds": 5.0, "frequency_hz": 71.14198664583199} | -729.1075118080669 / 998.9330534505464 |
| demo-islanded-ramp / app | 2160 | False | 103 | 0.047685185185185185 | {"tick": 136, "sim_time_seconds": 680.0, "frequency_hz": 53.373055059038585} | -127.48961154607643 / 60.0 |
| scenario-equinix-sj-1 / app | 720 | True | 0 | 0.0 | null | 60.0 / 60.0 |
| scenario-turbine-01 / app | 720 | False | 443 | 0.6152777777777778 | {"tick": 278, "sim_time_seconds": 1390.0, "frequency_hz": 73.5537530660913} | 60.0 / 305.12517226604007 |
| scenario-hybrid-ai-100mw-addendum-i / app | 120 | False | 78 | 0.65 | {"tick": 1, "sim_time_seconds": 5.0, "frequency_hz": -20.29765039999966} | -218.79606450000827 / 285.92631259085584 |
| scenario-100mw-fuel-cell-bess-diesel / app | 252 | False | 0 | 0.0 | null | 60.0 / 60.0 |
| scenario-fc100-islanded-v2 / app | 264 | False | 0 | 0.0 | null | 60.0 / 60.0 |
| scenario-fc100-islanded-zero-hot-v2 / app | 264 | False | 214 | 0.8106060606060606 | {"tick": 46, "sim_time_seconds": 230.0, "frequency_hz": 39.39674952027191} | -82.80435199997717 / 60.0 |

Published base demo and H1/H2 records contain the invalid ticks shown above. The trajectories were NOT changed or clamped.
The nominal ±10% reporting band is PROPOSED_HERE, not a trip or acceptance condition.
protection_configured means any resolved UF/OF/UFLS/81U threshold (including advisory thresholds), not full trip coverage.
OPEN-ISL-3 remains open; compare_runs was not edited. Previous base-demo/H1/H2 comparisons remain PASS 10/10:
```json
{
  "scenario-uneven-multisched-01/base": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 0.351692658,
      "informed_unserved_mwh": 0.020719074,
      "baseline_peak_unserved_mw": 22.309362466,
      "informed_peak_unserved_mw": 7.52325057
    }
  },
  "scenario-uneven-multisched-01/candidate": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 0.351692658,
      "informed_unserved_mwh": 0.020719074,
      "baseline_peak_unserved_mw": 22.309362466,
      "informed_peak_unserved_mw": 7.52325057
    }
  },
  "scenario-h1-k8s-ray-24h/base": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 0.894372986,
      "informed_unserved_mwh": 0.124133405,
      "baseline_peak_unserved_mw": 35.021533247,
      "informed_peak_unserved_mw": 20.746308977
    }
  },
  "scenario-h1-k8s-ray-24h/candidate": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 0.894372986,
      "informed_unserved_mwh": 0.124133405,
      "baseline_peak_unserved_mw": 35.021533247,
      "informed_peak_unserved_mw": 20.746308977
    }
  },
  "scenario-h2-slurm-24h/base": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 5.011418076,
      "informed_unserved_mwh": 0.859772492,
      "baseline_peak_unserved_mw": 44.86838787,
      "informed_peak_unserved_mw": 42.36838787
    }
  },
  "scenario-h2-slurm-24h/candidate": {
    "conditions": {
      "build_parity": true,
      "baseline_valid": true,
      "informed_valid": true,
      "baseline_energy_balance": true,
      "informed_energy_balance": true,
      "baseline_fuel_reconciled": true,
      "informed_fuel_reconciled": true,
      "identical_compute_trace": true,
      "informed_unserved_energy_no_worse": true,
      "informed_peak_unserved_no_worse": true
    },
    "condition_order": [
      "build_parity",
      "baseline_valid",
      "informed_valid",
      "baseline_energy_balance",
      "informed_energy_balance",
      "baseline_fuel_reconciled",
      "informed_fuel_reconciled",
      "identical_compute_trace",
      "informed_unserved_energy_no_worse",
      "informed_peak_unserved_no_worse"
    ],
    "verdict": "PASS",
    "informed_vs_baseline": {
      "baseline_unserved_mwh": 5.011418076,
      "informed_unserved_mwh": 0.859772492,
      "baseline_peak_unserved_mw": 44.86838787,
      "informed_peak_unserved_mw": 42.36838787
    }
  }
}
```
Metric identity reset: frequency_reporting_metrics_version=1 is identity-only; execution inputs and old metrics are unchanged.
Version-only old/new identity digests: phase5/METRIC_IDENTITY_MAP.json.

## Files, line ranges and commits
### COMMITS.json
```json
[
  {
    "kind": "implementation",
    "hash": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "message": "D3 (IMPL-ISL-3): frequency_valid and protection_configured; no clamping",
    "files": [
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/frequency_reporting.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py"
    ]
  },
  {
    "kind": "tracked UI types only",
    "hash": "21f552f62711df34da8be4d4052ee1ff3857d6f8",
    "message": "D3 UI types: frequency reporting flags; ignored display edits retained in evidence",
    "files": [
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts"
    ]
  },
  {
    "kind": "tests",
    "hash": "f730ee578a8930d5e45e5225d003d8b500bdbb62",
    "message": "D3 tests: TC-ISL-08 frequency reporting and runtime build warnings",
    "files": [
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_frequency_reporting.py",
      "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py"
    ]
  }
]
```
### SERVING.json
```json
{
  "workflow": "artifacts/gridsignal: web",
  "restarted": true,
  "backend_implementation_commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
  "code_and_tests_head": "f730ee578a8930d5e45e5225d003d8b500bdbb62",
  "get_root_status": 200,
  "frontend_build": "R5/PROD_BUILD.txt: success",
  "ui_display_source": "existing ignored working files; diff saved, not committed as source",
  "startup_complete": true,
  "startup_log": "R5/DEV_STARTUP.log",
  "screenshot": "R5/DEV_PREVIEW.jpg: signed-out page only"
}
```
### FINAL_GATE.json
```json
{
  "passed": true,
  "full_suite_set_gate": true,
  "no_new_failure_modes": true,
  "changed_modes": [],
  "waived_gpu_signature_ok": true,
  "waived_added": [
    "tests/test_gpu_load_profile.py::test_gpu_load_profile"
  ],
  "physics_subset_passed": true,
  "layering_matches_base": true,
  "native_summary": "16 failed, 2196 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 848.20s (0:14:08)"
}
```
### Changed files and literal hunk ranges
```json
[
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/frequency_reporting.py",
    "hunk": "@@ -0,0 +1,36 @@"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py",
    "hunk": "@@ -1732,0 +1733,3 @@ class TickResult:"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
    "hunk": "@@ -15,0 +16,2 @@ from __future__ import annotations"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py",
    "hunk": "@@ -4157,0 +4160,4 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py",
    "hunk": "@@ -1 +1 @@"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py",
    "hunk": "@@ -8,0 +9,14 @@ _log = logging.getLogger(\"gridsignal.scenario_factory\")"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py",
    "hunk": "@@ -797,0 +798,2 @@ def _tick_result_to_dict(tick: TickResult) -> dict:"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py",
    "hunk": "@@ -1947,2 +1947,2 @@ def build_run_context_from_spec("
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py",
    "hunk": "@@ -36 +36 @@ from .manifest import RunIdentity, RunManifestCache, make_run_identity"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py",
    "hunk": "@@ -73,0 +74,2 @@ def make_study_run_identity("
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py",
    "hunk": "@@ -156,0 +159,2 @@ def _compact_tick(tick: Any) -> dict[str, Any]:"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py",
    "hunk": "@@ -21,0 +22,4 @@ from .errors import ("
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py",
    "hunk": "@@ -177,0 +182,2 @@ class MetricsCollector:"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py",
    "hunk": "@@ -205,0 +212,3 @@ class MetricsCollector:"
  },
  {
    "commit": "67e02b1ab4dff1a261eaa5dc03bc68fbd190fe2f",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py",
    "hunk": "@@ -487,0 +497,5 @@ class MetricsCollector:"
  },
  {
    "commit": "21f552f62711df34da8be4d4052ee1ff3857d6f8",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts",
    "hunk": "@@ -238,0 +239,3 @@ export interface TickPayload {"
  },
  {
    "commit": "f730ee578a8930d5e45e5225d003d8b500bdbb62",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_frequency_reporting.py",
    "hunk": "@@ -0,0 +1,97 @@"
  },
  {
    "commit": "f730ee578a8930d5e45e5225d003d8b500bdbb62",
    "file": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py",
    "hunk": "@@ -58 +58,4 @@ def test_tc_isl_18_floor_warning_is_diagnostic_only(start_s, expected_count, cap"
  },
  {
    "commit": null,
    "status": "ignored working copy only",
    "file": "candidate-working-copy/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx",
    "hunk": "@@ -122,6 +122,8 @@"
  },
  {
    "commit": null,
    "status": "ignored working copy only",
    "file": "candidate-working-copy/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx",
    "hunk": "@@ -230,6 +232,13 @@"
  },
  {
    "commit": null,
    "status": "ignored working copy only",
    "file": "candidate-working-copy/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx",
    "hunk": "@@ -247,6 +256,7 @@"
  },
  {
    "commit": null,
    "status": "ignored working copy only",
    "file": "candidate-working-copy/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx",
    "hunk": "@@ -325,6 +335,8 @@"
  },
  {
    "commit": null,
    "status": "ignored working copy only",
    "file": "candidate-working-copy/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts",
    "hunk": "@@ -121,7 +121,9 @@"
  },
  {
    "commit": null,
    "status": "ignored working copy only",
    "file": "candidate-working-copy/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts",
    "hunk": "@@ -145,8 +147,11 @@"
  },
  {
    "commit": null,
    "status": "ignored working copy only",
    "file": "candidate-working-copy/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/test/forecast_quality_panel.test.tsx",
    "hunk": "@@ -151,6 +151,22 @@"
  }
]
```

### Literal tracked application diff vs fd87fc7
```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts
index 0f1efdf..551f464 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts
@@ -236,6 +236,9 @@ export interface TickPayload {
   // Islanded: integrated each tick via frequency_forcing_mw (governor droop provides restoring force).
   // Grid-connected: held at site frequency_nominal_hz (grid is the reference; forcing term is 0).
   frequency_hz: number
+  // DR D3: every new tick carries these; optional only for pre-D3 saved payloads.
+  frequency_valid?: boolean
+  protection_configured?: boolean
   // Phase 11.5: site nominal frequency — constant for the duration of a run.
   // 60.0 Hz = WECC/SDG&E (US West Coast); 50.0 Hz = EU/APAC/NZ.
   // Stamped by run_manager._drive() from SiteConfig.frequency_nominal_hz.
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/frequency_reporting.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/frequency_reporting.py
new file mode 100644
index 0000000..88a3f66
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/frequency_reporting.py
@@ -0,0 +1,36 @@
+"""DR D3 / IMPL-ISL-3: observation only; never change frequency or protection."""
+from core.models import IslandMode
+
+# PROPOSED_HERE: synchronous-machine overspeed trips are typically about 110%
+# of rated speed. Symmetric nominal +/-10% is a REPORTING band, not a relay.
+FREQUENCY_VALIDITY_BAND_FRACTION = 0.10
+
+
+def frequency_is_valid(frequency_hz: float, nominal_hz: float) -> bool:
+    return bool(abs(frequency_hz - nominal_hz) <= nominal_hz * FREQUENCY_VALIDITY_BAND_FRACTION)
+
+
+def protection_is_configured(site) -> bool:
+    """Inspect resolved threshold values; relay delays alone do not enable a relay."""
+    if site.island_mode not in (True, IslandMode.ISLANDED):
+        return True
+    if any(getattr(site, name, None) is not None for name in (
+        "uf_warning_hz", "ufls_stage1_hz", "island_collapse_hz",
+        "of_warning_hz", "of_trip_hz", "relay_81u_threshold_hz",
+    )):
+        return True
+    return any(
+        (stage.get("threshold_hz") if isinstance(stage, dict)
+         else getattr(stage, "threshold_hz", None)) is not None
+        for stage in (getattr(site, "ufls_stages", None) or [])
+    )
+
+
+def unprotected_island_warning(site) -> dict | None:
+    if protection_is_configured(site):
+        return None
+    return {
+        # PROPOSED_HERE: stable warning identity; no validation or trip condition.
+        "code": "islanded_frequency_protection_unconfigured",
+        "message": "islanded run without frequency protection configured",
+    }
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
index 3044d09..2481814 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
@@ -1730,6 +1730,9 @@ class TickResult:
     # D4: sum(grid_exchange_mw + frequency_forcing_mw + asset_delivery_error_mw)
     #     == (_p_gen_mw − p_total_mw) is asserted inline in evaluate_tick().
     frequency_hz:         float = 0.0   # always overwritten by evaluate_tick; 0 = sentinel
+    # DR D3: reporting only, stamped together at the final tick construction.
+    frequency_valid: bool = True
+    protection_configured: bool = False
     # Phase 11.5: site nominal frequency — constant for the duration of a run.
     # Sourced from SiteConfig.frequency_nominal_hz and stamped by run_manager._drive()
     # via dataclasses.replace() (same enrichment path as dt_thermal_seconds).
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index e117bff..08a5061 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -13,6 +13,8 @@ without any parallelism.
 
 from __future__ import annotations
 
+from core.frequency_reporting import frequency_is_valid, protection_is_configured
+
 import logging
 import math
 import dataclasses
@@ -4155,6 +4157,10 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         p_generation_mw=_p_generation_mw,
         # Phase 2A: protection_provisional — True for all islanded ticks.
         protection_provisional=_protection_provisional,
+        # DR D3 / IMPL-ISL-3: observe the final achieved frequency exactly once.
+        # No clamp, filter, threshold default or change to the swing equation.
+        frequency_valid=frequency_is_valid(state._frequency_hz, state.site.frequency_nominal_hz),
+        protection_configured=protection_is_configured(state.site),
         # Phase 6: supply/served producers.
         p_served_mw=_p_served_mw,
         p_unserved_mw=_p_unserved_mw,
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
index fc007ea..14ff070 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
@@ -1,4 +1,4 @@
-"""Build-time diagnostics only; never change reserve floors or dispatch."""
+"""Build-time diagnostics only; never change reserve, dispatch or protection."""
 import logging
 
 from core.dispatch import MARGIN_MULTIPLIER
@@ -6,6 +6,20 @@ from core.dispatch import MARGIN_MULTIPLIER
 _log = logging.getLogger("gridsignal.scenario_factory")
 
 
+def frequency_configuration_warnings(state) -> list[dict]:
+    """DR D3 / R5.2: warn here on resolved values, not in API schema validation.
+
+    ScenarioSpec remains valid and imports no new core logic. This runtime
+    warning flows through run metadata and the existing run-start response.
+    """
+    from core.frequency_reporting import unprotected_island_warning
+    warning = unprotected_island_warning(state.site)
+    if warning is None:
+        return []
+    _log.warning("DR D3 build warning: %s", warning)
+    return [warning]
+
+
 def reserve_capacity_warnings(state) -> list[dict]:
     """DR D9b: flag the arbitrator's actual floor, without capping/rejecting it."""
     arbitrator = state.arbitrator
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
index 4f3fadb..7ddf995 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
@@ -795,6 +795,8 @@ def _tick_result_to_dict(tick: TickResult) -> dict:
         "bess_setpoint_mw":      round(tick.bess_setpoint_mw, 4),
         "gt_setpoint_mw":        round(tick.gt_setpoint_mw, 4),
         "frequency_hz":          round(tick.frequency_hz, 4),
+        "frequency_valid":       tick.frequency_valid,
+        "protection_configured": tick.protection_configured,
         "frequency_nominal_hz":  round(tick.frequency_nominal_hz, 4),
         # ── Phase 13.2: Balance decomposition ────────────────────────────────
         # Three independent channels.  D4 invariant asserted in evaluate_tick().
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
index 73d675f..6cbcb08 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
@@ -1944,8 +1944,8 @@ def build_run_context_from_spec(
         sim_state._commitment_mode = _commitment_mode
         sim_state._commitment_transition_sink = _turbine_commitment_controller
     # DR-2026-10-20-ISLAND-COLLAPSE D9b: warn once at build, never alter the floor.
-    from runtime.build_warnings import reserve_capacity_warnings
-    _build_warnings = reserve_capacity_warnings(sim_state)
+    from runtime.build_warnings import reserve_capacity_warnings, frequency_configuration_warnings
+    _build_warnings = reserve_capacity_warnings(sim_state) + frequency_configuration_warnings(sim_state)
     return RunContext(
         run_id=run_id,
         sim_state=sim_state,
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py
index 5029a1f..f5db3c2 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py
@@ -33,7 +33,7 @@ from .errors import (
     error_payload,
 )
 from .manifest import RunIdentity, RunManifestCache, make_run_identity
-from .metrics import MetricsCollector, collect_metrics
+from .metrics import MetricsCollector, collect_metrics, FREQUENCY_REPORTING_METRICS_VERSION
 
 
 # PROPOSED_HERE: The base scenario ID and study-class labels are harness metadata.
@@ -71,6 +71,8 @@ def make_study_run_identity(
     # The replay trace is an execution input; its content is separately hashed.
     identity_parameters.pop("workload_events", None)
     identity_parameters["study_class"] = study_class_for_scenario(scenario_id)
+    # DR D3: invalidate old metric caches without changing the execution spec.
+    identity_parameters["frequency_reporting_metrics_version"] = FREQUENCY_REPORTING_METRICS_VERSION
     return make_run_identity(
         scenario_id=scenario_id,
         mode=mode,
@@ -154,6 +156,8 @@ def _compact_tick(tick: Any) -> dict[str, Any]:
     row = _tick_result_to_dict(tick)
     keys = (
         "tick_index",
+        "frequency_valid",
+        "protection_configured",
         "sim_time_seconds",
         "p_compute_mw",
         "p_cooling_mw",
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py
index f6828cc..c97c4c2 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py
@@ -19,6 +19,10 @@ from .errors import (
     StartFuelReconciliationError,
 )
 
+# PROPOSED_HERE: cache identity revision for three additive D3 reporting metrics;
+# not a physics, guard or acceptance-condition revision.
+FREQUENCY_REPORTING_METRICS_VERSION = 1
+
 
 FUEL_COMPONENTS = (
     "load_fuel_mmbtu",
@@ -175,6 +179,8 @@ class MetricsCollector:
 
     def __post_init__(self) -> None:
         self.tick_count = 0
+        self.invalid_frequency_tick_count = 0
+        self.protection_configured = True
         self.last_tick: Any = None
         self.last_telemetry: dict[str, dict[str, Any]] = {}
         self.previous_cumulative: dict[str, dict[str, float]] = {}
@@ -203,6 +209,9 @@ class MetricsCollector:
 
     def add(self, tick: Any) -> None:
         self.tick_count += 1
+        # DR D3: consume the engine's reporting flags; never recompute physics.
+        self.invalid_frequency_tick_count += int(_get(tick, "frequency_valid", True) is False)
+        self.protection_configured = bool(_get(tick, "protection_configured", True))
         self.last_tick = tick
         sim_time = _number(_get(tick, "sim_time_seconds"))
         compute = _number(
@@ -485,6 +494,11 @@ class MetricsCollector:
         daily_rows = _daily_rows(self.daily)
         return {
             "tick_count": self.tick_count,
+            "invalid_frequency_tick_count": self.invalid_frequency_tick_count,
+            "invalid_frequency_fraction": (
+                self.invalid_frequency_tick_count / self.tick_count if self.tick_count else 0.0
+            ),
+            "protection_configured": self.protection_configured,
             "interval_seconds": self.tick_seconds,
             "fuel_by_component_mmbtu": {
                 key: round(value, 9) for key, value in components.items()
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_frequency_reporting.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_frequency_reporting.py
new file mode 100644
index 0000000..674be55
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_frequency_reporting.py
@@ -0,0 +1,97 @@
+"""TC-ISL-08a–d: D3 observation only (07 is already staging-start logging)."""
+import copy
+import json
+from unittest.mock import patch
+
+import pytest
+
+from api.schemas import ScenarioSpec
+from core._plane_guard import _EVALUATE_TICK_PERMITTED
+from core.frequency_reporting import frequency_is_valid, protection_is_configured
+from runtime.persistence import _tick_to_json
+from runtime.run_manager import _tick_result_to_dict
+from runtime.scenario_factory import build_run_context_from_spec
+
+
+def context(**overrides):
+    # PROPOSED_HERE: small zero-load inverter-only fixture isolates reporting;
+    # these are test inputs, not defaults or changes to production scenarios.
+    raw = dict(name="tc-isl-08", island_mode=True, turbine_units=[],
+               solar_rated_mw=0.0, pue_base=1.0,
+               bess_units=[dict(asset_id="bess", rated_mw=10.0, usable_mwh=20.0,
+                                initial_soc_fraction=1.0, grid_forming=True)])
+    raw.update(overrides)
+    spec = ScenarioSpec.model_validate(raw)
+    return build_run_context_from_spec("tc-isl-08", spec.model_dump(mode="json"))
+
+
+def step(ctx):
+    token = _EVALUATE_TICK_PERMITTED.set(True)
+    try:
+        return ctx.step()
+    finally:
+        _EVALUATE_TICK_PERMITTED.reset(token)
+
+
+def test_tc_isl_08a_unprotected_island_flags_and_wire_persistence():
+    tick = step(context())
+    assert tick.protection_configured is False
+    assert tick.frequency_valid is True
+    for encoded in [_tick_result_to_dict(tick), json.loads(_tick_to_json(tick))]:
+        assert encoded["protection_configured"] is False
+        assert encoded["frequency_valid"] is True
+    print({"TC-ISL-08a": dict(protection_configured=False, frequency_valid=True)})
+
+
+@pytest.mark.parametrize("nominal,frequency,valid", [
+    (60.0, 54.0, True), (60.0, 66.0, True), (60.0, 53.9, False),
+    (60.0, 90.0, False), (50.0, 45.0, True), (50.0, 55.0, True),
+    (50.0, 55.1, False),
+])
+def test_tc_isl_08b_band_does_not_modify_frequency(nominal, frequency, valid):
+    # PROPOSED_HERE: explicit boundary/outside-band reporting samples.
+    assert frequency_is_valid(frequency, nominal) is valid
+    print({"TC-ISL-08b": [nominal, frequency, valid]})
+
+
+def test_tc_isl_08b_tick_frequency_unchanged_when_flag_changes():
+    ctx = context()
+    ctx.sim_state._frequency_hz = 90.0  # PROPOSED_HERE: invalid, unclamped test initial state.
+    other = copy.deepcopy(ctx)
+    actual = step(ctx)
+    with patch("core.simulation_core.frequency_is_valid", return_value=True):
+        reference = step(other)
+    assert actual.frequency_valid is False
+    assert reference.frequency_valid is True
+    assert actual.frequency_hz == reference.frequency_hz
+    assert actual.frequency_hz > 66.0
+    print({"TC-ISL-08b unchanged achieved Hz": actual.frequency_hz})
+
+
+# PROPOSED_HERE: synthetic protection fixtures, not production threshold defaults.
+@pytest.mark.parametrize("extra", [
+    {"island_mode": False}, {"uf_warning_hz": 59.5},
+    {"relay_81u_threshold_hz": 57.5},
+    {"ufls_stages": [{"threshold_hz": 58.0, "delay_s": 1.0, "block_fraction": .1}]},
+])
+def test_tc_isl_08c_grid_tied_or_protected(extra):
+    ctx = context(**extra)
+    assert protection_is_configured(ctx.sim_state.site)
+    assert step(ctx).protection_configured is True
+    print({"TC-ISL-08c": extra, "protection_configured": True})
+
+
+def test_tc_isl_08d_null_protection_warns_and_still_validates(caplog):
+    ctx = context()
+    # DR R5.2: validation still succeeds; runtime owns the non-rejecting warning.
+    from api.schemas import StartRunResponse
+    assert "DR D3 build warning" in caplog.text
+    warning = next(w for w in ctx.metadata["build_warnings"]
+                   if w["code"] == "islanded_frequency_protection_unconfigured")
+    assert warning["message"] == "islanded run without frequency protection configured"
+    assert ctx.sim_state.site.uf_warning_hz is None
+    assert ctx.sim_state.site.of_trip_hz is None
+    assert StartRunResponse(
+        run_id=ctx.run_id, build_warnings=ctx.metadata["build_warnings"],
+    ).build_warnings == ctx.metadata["build_warnings"]
+    print({"TC-ISL-08d": warning, "build": "succeeded"})
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py
index ed622b6..2bc41c8 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py
@@ -55,7 +55,10 @@ def test_tc_isl_18_floor_warning_is_diagnostic_only(start_s, expected_count, cap
     basis = arbitrator.reserve_floor_basis[bess.config.asset_id]
     expected_floor = max(expected_floor, basis["depth_reserve_mwh"], basis["d2r_term_mwh"])
     assert arbitrator.soc_floor_mwh(bess) == pytest.approx(expected_floor)
-    warnings = ctx.metadata["build_warnings"]
+    # DR D3 adds an independent frequency warning; TC-ISL-18 still checks
+    # exactly the D9b reserve warnings, without changing its floor/dispatch assertions.
+    warnings = [w for w in ctx.metadata["build_warnings"]
+                if w["code"] == "bess_reserve_floor_above_usable"]
     assert len(warnings) == expected_count
     assert sum("DR D9b build warning:" in r.message for r in caplog.records) == expected_count
     if warnings:

```
Persistence uses runtime/persistence.py::_tick_to_json/dataclasses.asdict; no schema migration.
The run-manager serializer carries both flags into existing REST/WebSocket payloads.
The opening and inner UI layouts show the unprotected-island notice; Forecast Quality marks invalid current readings grey without changing Hz.
The two payload fields remain optional in TypeScript only for legacy saved payloads.
No automatic checkpoint appeared during this resumption. The separate report-only commit hash is supplied in the completion response (not self-embedded).
The startup screenshot verifies the signed-out app only; its unauthenticated resource 401 is expected. Display behavior was unit-tested in the prior unchanged UI evidence (17 passed).

Historical STOP evidence is retained in phase5/STOP_RESULT.json and commit 1db4393; it is superseded by this R5 report.
STOP — end of Phase 5. No Phase 6, publish, deploy or push.
