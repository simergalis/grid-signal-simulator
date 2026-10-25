# S10 licence-note removal

**Status: PASS.** Only the requested S10 description sentence and its generator source were changed. The S10 scenario remains parseable and discoverable. Both pinned physical references are unchanged.

## Changes

The one-off UTF-8 text replacement found exactly one occurrence in each target file, removed the sentence and its adjacent separator space, and did not reserialize JSON or alter line endings.

| File | Location | SHA-256 before | SHA-256 after |
|---|---:|---|---|
| `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/S10_mit_supercloud_2021-08-11.json` | description, line 3 | `5577d437249e48f7b139fa8c7ded820dcc81e5f7ac062e524045dad6f2a187ea` | `8bf3a8fd3d59469fe762838907b4bf907a6279c4e78474402665f6824571b288` |
| `tools/supercloud/make_scenario.py` | description generator, line 485 | `84dec5309188b11449a8b6a84bd99fd28666c8d10c1da77a9aa73c6b5a245a4f` | `c652edccf75d79214ac6d2f01768276d5f20d8677ed2eb0538f21bbc32949e41` |

The exact sentence count was `1` in each file before replacement. Context:

- Scenario JSON before: `...V100 power physics are not modelled. Source data CC BY-NC-ND 4.0 — internal use. Initial BESS SoC fraction...`
- Scenario JSON after: `...V100 power physics are not modelled. Initial BESS SoC fraction...`
- Generator before: `...physics are not modelled. Source data CC BY-NC-ND 4.0 — internal use.`
- Generator after: `...physics are not modelled.`

`git diff --stat` for the two requested files: 2 files changed, 2 insertions(+), 2 deletions(-). Word-diff excerpt:

```diff
-Source data CC BY-NC-ND 4.0 — internal use.
```

The generator line changed from:

```python
f"physics are not modelled. Source data CC BY-NC-ND 4.0 — internal use."
```

to:

```python
f"physics are not modelled."
```

No test asserted the removed description text, so no test fixture or assertion was changed. `python -m json.tool` accepted the edited scenario.

## Acceptance

- `ScenarioSpec.model_validate_json(...)`: passed; scenario ID/name remains `S10_mit_supercloud_2021-08-11`; its description no longer contains the removed sentence.
- UI scenario catalogue: `build_seeded_store()` returned S10 with the updated description.
- In-process MCP: `list_scenarios` includes S10 and `get_scenario` returns the updated description.
- Pinned runner, seed 1729 and wall clock 1792454400.0: 17,280 ticks; physical SHA-256 remains `ad91ced6445f21aa4a9a9b4ccb2fb4dd5114d42f2eae3ab5e0be5769fceaf508`; non-fuel SHA-256 remains `e0ccf0e15265d70738e53c74d273e8ab223d9b30b4439797b8188cb76be7aaba`.
- `ctx.step` S10 hash remains `f230ae8f141183e1e6bcdb8dda0eb8f4920bf5674167bba972e4a72f37c64353` for 17,280 ticks.
- Identity comparison: only `description` changed in the S10 normalized identity payload. With the same engine/harness commit strings (`4d1d182d978bf0c0234f34fc1e9e55642b0c219e-dirty`) and seed, the S10 digest changed from `278f5d714c1ea6ef6800238b6e257860bfcddef08cd62f8398959ad510357777` to `8f634edd230cec258a0d0a339a4e2a3d79503d36434d4db5542d8d0d13c33fa0`. Base-demo, H1 and H2 identities were unaffected; the focused identity test passed.
- Generator tests: **21 passed**.
- Focused MCP/study-harness tests, including TC-ISL-65, -66, -67, -69 and -73: **5 passed** (one Starlette deprecation warning).

### Full-suite runs

Both runs used the real package and wrote incremental JUnit XML under `/tmp`.

| `PYTHONHASHSEED` | Passed | Failed | Skipped | Xfailed | Subtests passed | Warnings | Duration |
|---:|---:|---:|---:|---:|---:|---:|---:|
| `1` | 2,255 | 15 | 3 | 23 | 3 | 54 | 1,044.65 s |
| `987654321` | 2,255 | 15 | 3 | 23 | 3 | 54 | 1,027.79 s |

Failure-set comparison against `tools/dr_isl/PHASE_6C_FAILING_TESTS.txt`: **0 added** in either run; both runs had the same 15 failing IDs. The only baseline failure absent in both was the existing waived `tests/test_gpu_load_profile.py::test_gpu_load_profile`.

The 15 failures in both runs were:

```text
tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation
tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config
tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar
tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names
tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel
tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context
tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants
tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude
tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes
tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip
```

## Other notes left unchanged

These repository notes were not removed, as requested:

- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py:1435` — S10 comment says the source data is CC BY-NC-ND 4.0 and “internal use”.
- `tools/supercloud/make_scenario.py:21` — general source-data licence/developer note.
- `tools/supercloud/.gitignore:1` — comment about the data licence and not committing raw rows.
- `tools/supercloud/profile_slurm_log.py:18` — dataset licence note.
- `tools/supercloud/convert_to_kube_trace.py:38` — licence note for row-level output.
- `tools/supercloud/run_replay.py:8` — aggregate-only licence note.
- Four D6 candidate/reproduction JSON files under `tools/dr_isl/d6/` still contain the old sentence in their line-3 descriptions: `S10_2021-08-11_cpu_candidate.json`, `S10_2021-08-11_cpu_candidate_a_plus_c.json`, `S10_2021-08-11_cpu_soc_fuel_candidate.json`, and `S10_D6A_PROVENANCE_REPRO.json`.

No other S10/SuperCloud licence or internal-use note was found in app UI strings or MCP descriptions. These remaining notes are listed for Lloyd's separate decision.

## Commits

- `f4d99c0` — `Remove S10 licence note from scenario and generator` (scenario JSON, generator, and the required internal project-memory update).
- The report-only commit hash is included in the completion summary.

No publish, deploy, push, or workflow restart was performed.

## Remaining S10 catalogue comment removal

Lloyd's 2026-10-25 ruling authorized removal of the remaining S10-specific licence wording in the catalogue comment. An exact-string replacement found one occurrence of `; source data CC BY-NC-ND 4.0, internal use.` and replaced it with a period. The descriptive portion of the comment remains.

- File: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/scenarios.py:1435`
- Before: `# S10 — one real day (2021-08-11 UTC) of MIT SuperCloud GPU jobs at true start/end times, scaled to 50 MW H100-equivalent; source data CC BY-NC-ND 4.0, internal use.`
- After: `# S10 — one real day (2021-08-11 UTC) of MIT SuperCloud GPU jobs at true start/end times, scaled to 50 MW H100-equivalent.`
- `python -m py_compile api/routes/scenarios.py`: passed.
- `build_seeded_store()` returned `S10_mit_supercloud_2021-08-11`; its description and scenario data were unchanged.
- Focused tests: 6 passed (`test_tc_isl_65_s10_list_and_get_scenario_use_tracked_source`, `test_tc160_list_scenarios_marks_all_six_study_scenarios`, and study-harness TC-ISL-67, -69, -72, -73).
- Full suite (`PYTHONHASHSEED=1`): 2,255 passed, 15 failed, 3 skipped, 23 xfailed, 3 subtests passed, 54 warnings. Compared with `tools/dr_isl/PHASE_6C_FAILING_TESTS.txt`, there were 0 added failures; the only baseline ID absent was the waived `tests/test_gpu_load_profile.py::test_gpu_load_profile`.
- The 15 failures matched the other Phase 6c baseline IDs: `test_I4_delivery_fault_causes_frequency_deviation`, `test_R4_fields_present_on_turbine_config`, `test_tc173_executor_run_validates_from_truncated_record_and_sidecar`, `test_live_diesel_is_less_aggressive_than_disabled_before_curtailment`, `test_hybrid_covered_demand_does_not_release_bess_reserve`, `test_fabric_scenario_names`, `test_B1a_islanded_delivery_fault_visible_in_delivery_channel`, `test_fixed_target_survives_a_step_load_and_output_remains_rate_limited`, the three `tests/test_gridley.py` failures, `test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait`, `test_api_gate_clean_api_passes`, `test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load`, and `test_tc84f_demo_20mw_contingency_state_changes_after_trip`.
- This comment-only edit does not change the seeded S10 record or simulation behavior.
- Descriptive source commit: `d63a50e` (`Remove remaining S10 catalogue licence wording`); it contains only the catalogue comment and the related project-memory update.
