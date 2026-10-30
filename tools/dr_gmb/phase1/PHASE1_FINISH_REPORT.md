# DR-GMB Phase 1 finish

## Scope and ruling

This close-out updates only the D9 tests in the simulator package. No simulator
code, scenario JSON, dispatch behavior, reserve-floor release behavior, or
workflow was changed. The D9 assertions follow DR-2026-10-27-GRID-MODE-BESS D1
and Lloyd's 2026-10-29 F-GMB-2 ruling: without an import cap, grid import
carries positive residual and the BESS remains idle; with a cap, the BESS
covers only residual demand above that cap, subject to rating and SoC floor.

The previous `test_d9_demo_20mw_produces_nonzero_bess_output` expectation was
obsolete under D1. Its fixture passed at pre-D1 commit `7828736`; the fixture
itself remains unchanged. The existing assertion that any BESS output must be
positive was replaced with uncapped-grid assertions, and a capped companion
case was added.

## SJ-1 per-tick check

The amended V4 criterion was checked over all SJ-1 ticks: **0 non-excluded
deviations**, **24 rating-limited ticks excluded**, and largest deviation
`0 MW`. The 0.074 MWh below-cap discharge is gone while the above-cap
1.238 MWh role is retained; unserved energy remains no worse than 0.252 MWh.

## V5 description-only scenario edits

Commit `39508cd` changed descriptions only in these four scenarios. The
canonical physical hash (all scenario fields except `name` and `description`)
is unchanged in every case:

| Scenario file | File SHA-256 before | File SHA-256 after | Physical hash before and after |
|---|---|---|---|
| `config/scenarios/demo-10-tenant-overload-120pct.json` | `30a4311e884d5f083e05198131957f12fa8e872d30285fbcd5d0e7a7d4128401` | `ab4f537073fddeac0beb086a54b6c1da8d7cad2d45894af83da222cf60491638` | `6f8bfd93b9daae8bcf92c769f72c02d1ef74e7e23ed645322f2695e752e6931b` |
| `config/scenarios/demo-fc-bess-grid-peak.json` | `8693357a9d578d6dae744b20d5c54a616ba65ebd1116e30250cb45c0b592be52` | `85a03c8124b125b55c86ea7313733c2717e82c7b5b84b9d93d1776868bbdff19` | `71a6853c17b13e1d6aa9232225da1c01ed8cf7e9117571502545f5e930e6b7c7` |
| `config/scenarios/demo-grid-fc-bess-shaped-load.json` | `f17c6e6b1afd23489d9803cbf7df15028a752bcb8d2ff5cd2fd7f7a104df4b5e` | `e842742695b81036b75fa306eca0b5707bd4fa5956b0029104c4b1baa162f4b9` | `9d6f9545d49f31255d73a1eb849e424c6adbc9c54705413bfb513e367b81932d` |
| `config/scenarios/demo-rolling-planning-peaks.json` | `8e46703ec10cad06f905ae470e11dc73c4d2714da21baa28e562adeebf4e08a0` | `8a1f33fe2a3a7780f6c7fb095e5038ddd5805136f0250f784a60de9c8cdcedb9` | `736eb87b77e24fd825580cd000ac704a0580f2e71a78006fe641c4d17ee8b36c` |

## D9 focused tests

The two D9 tests passed after the final test wording was in place:

```text
..                                                                       [100%]
2 passed in 3.03s
```

The uncapped test computes pre-BESS residual from each tick's demand,
turbine/fuel-cell/diesel output, and renewable output. It asserts that a
positive residual occurs, BESS output stays at zero, and grid import equals
that residual within `1e-6 MW`.

The capped companion uses a `10 MW` import cap, marked
`PROPOSED_HERE`: it is below the approximately `14.43 MW` residual peak, and
the approximately `4.43 MW` peak excess fits the `5 MW` BESS rating. It checks
each tick from measured outputs. No tick was rating- or floor-limited; the
largest deviation from the expected above-cap BESS output was `0 MW`.

| Sim time (s) | Pre-BESS residual (MW) | Grid import (MW) | BESS output (MW) | Expected BESS (MW) |
|---:|---:|---:|---:|---:|
| 5 | -4.782418750 | 0.000000000 | 0.000000000 | 0.000000000 |
| 10 | -4.574487500 | 0.000000000 | 0.000000000 | 0.000000000 |
| 15 | -4.366556250 | 0.000000000 | 0.000000000 | 0.000000000 |
| 20 | -4.158625000 | 0.000000000 | 0.000000000 | 0.000000000 |
| 25 | -3.692859000 | 0.000000000 | 0.000000000 | 0.000000000 |
| 30 | -2.195754000 | 0.000000000 | 0.000000000 | 0.000000000 |
| 35 | -0.698649000 | 0.000000000 | 0.000000000 | 0.000000000 |
| 40 | 0.798456000 | 0.798456000 | 0.000000000 | 0.000000000 |
| 45 | 2.295561000 | 2.295561000 | 0.000000000 | 0.000000000 |
| 50 | 3.792666000 | 3.792666000 | 0.000000000 | 0.000000000 |
| 55 | 5.289771000 | 5.289771000 | 0.000000000 | 0.000000000 |
| 60 | 6.786876000 | 6.786876000 | 0.000000000 | 0.000000000 |
| 65 | 8.283981000 | 8.283981000 | 0.000000000 | 0.000000000 |
| 70 | 9.781086000 | 9.781086000 | 0.000000000 | 0.000000000 |
| 75 | 11.278191000 | 10.000000000 | 1.278191000 | 1.278191000 |
| 80 | 12.775296000 | 10.000000000 | 2.775296000 | 2.775296000 |
| 85 | 14.000704167 | 10.000000000 | 4.000704167 | 4.000704167 |
| 90 | 14.139325000 | 10.000000000 | 4.139325000 | 4.139325000 |
| 95 | 14.277945833 | 10.000000000 | 4.277945833 | 4.277945833 |
| 100 | 14.434964359 | 10.000000000 | 4.434964359 | 4.434964359 |

Rate-limited ticks: `0`. Floor-limited ticks: `0`. Largest non-excluded
absolute deviation: `0 MW`.

## V6 full suite

Both runs used the full package test suite with `PYTHONHASHSEED=1`:

```text
PYTHONHASHSEED=1 python -m pytest -q --tb=no --junitxml=/tmp/dr_gmb_phase1_full_suite_run1.xml
15 failed, 2291 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 985.67s (0:16:25)

PYTHONHASHSEED=1 python -m pytest -q --tb=no --junitxml=/tmp/dr_gmb_phase1_full_suite_run2.xml
15 failed, 2291 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 967.02s (0:16:07)
```

Each run's 15 failed IDs exactly match the `PYTHONHASHSEED=1` reference list in
`tools/dr_isl/isl30/FULL_SUITE_2.txt`; neither run added or removed a failing
ID. The two runs have identical pass/fail/skip/xfail outcomes. Relative to the
reference's 2278 passes, each current run has 13 additional passing cases.
The only source difference between the two runs was the comment/docstring
clarification of the proposed capped-test rationale; assertions and behavior
were unchanged.

The unchanged failing IDs in both runs are:

1. `tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation`
2. `tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config`
3. `tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar`
4. `tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment`
5. `tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve`
6. `tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names`
7. `tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel`
8. `tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited`
9. `tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context`
10. `tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants`
11. `tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude`
12. `tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait`
13. `tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes`
14. `tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load`
15. `tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip`

## V7 commits

1. `c1cf8816e3415d6dceb7cb26278df79f51bfbe46` — D9 test update in
   `tests/test_formulas.py`.
2. `fad51ed5f5be23675cb37270866d9f832a87cbda` — force-add the previously
   ignored `tests/test_dr_gmb_grid_mode_bess.py` (TC-GMB-01 through TC-GMB-03).
3. This report-only commit records the Phase 1 close-out.
