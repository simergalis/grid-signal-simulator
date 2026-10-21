# DR-2026-10-20-ISLAND-COLLAPSE — resumed Phase 2c

Status: STOPPED at 2c.6: added TC156 failure. Phase 2c is NOT finished; no Phase 3.
Base: 869d55bbdfa1ce16e6e1514ade9a6ca4ca3a0442.
Implementation commit: NONE. Application changes remain uncommitted for review.
Package prefix P: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/.
Scratch prefix T: /tmp/DR-ISL-phase2c/.
The report-only commit hash is delivered in chat after committing this report and the H identity map.

## Preserved STOP report
tools/dr_isl/PHASE_2C_STOP1_REPORT.md is the byte-for-byte rename of the earlier report, performed before source edits.
SHA-256: 749bbb2e625d33254607898357fe410e3caa67cfecfd86f9987a2f85f6a5583c.

## 2c.1 — D8
P/study_harness/executor.py _expanded_spec now validates ONLY the base demo through ScenarioSpec.model_validate_json -> model_dump(mode='json'), then applies the study fuel overlay, duration and parameter overrides. The H branch is unchanged.
The same resulting spec is passed to the existing probe and both arms. Each arm records canonicalisation plus the post-validation fuel/mode/workload/demand/duration/parameter overrides actually applied. No runtime/core schema validation implementation was duplicated.
Controlled old/new base-demo identity digests (engine/harness base commit held fixed, seed=42, 5.0 s):
```json
{
  "before_raw_loader": {
    "baseline": "4e0a6ae5c8d6947e884a58ab34a6911900e13dbceb3b4085b61e9927b8ef6fc1",
    "informed": "2015c4f950ab5bfc32af9d57bf2f0458000d941dd0aff65add2221d8d5bebc4f"
  },
  "after_canonical_D9c": {
    "baseline": "d7171c8d9ce5d539c50a2900a17089589502caed54f440183fc2e28a7898f76e",
    "informed": "9fb49f03b2ebea82182f507cd60cfa6046ae3673a2d0a026dfe671c8ef67e767"
  }
}
```
These deliberately reset the base-demo cache; they do not claim the new source commit has the same production identity as the controlled comparison.

## 2c.2 — D9b
P/runtime/build_warnings.py reads the EXISTING arbitrator soc_floor_mwh. It never sets/caps/rejects it. The diesel contribution is computed for attribution only, using the existing MARGIN_MULTIPLIER and diesel_worst_case_sync_s; dispatch and its single floor formula are untouched.
Structured warnings carry code, BESS id, actual floor/usable MWh, winning term, configured diesel units and start/residual/offset timings, plus the configured fleet synchronization horizon.
P/runtime/scenario_factory.py creates the warnings once per build; P/runtime/run_manager.py RunContext.metadata stores them without changing positional constructor arguments; P/api/routes/runs.py and P/api/schemas.py return build_warnings in StartRunResponse; P/study_harness/executor.py copies them into each study run record.
The RunControlBar has only an inline error channel (frontend/src/components/RunControlBar.tsx:531–535); its start response consumers at :187 and :258 did not have a run/build-warning display. ScenarioManagerPage.tsx:157–167 displays UPLOAD c_rate/initial_spinning warnings, not build results. No new frontend warning channel or frontend edit was added.
Literal post-change builds (including all three untouched over-capacity scenarios):
```json
[
  {
    "scenario": "scenario-h1-k8s-ray-24h",
    "diesel_count": 0,
    "floors_mwh": [
      0.0
    ],
    "warnings": [],
    "identities": {
      "baseline": "d8813756114b33e2c48fd267531795f433112640bf096adf83e54c7108a443e4",
      "informed": "5e27d7b9b734299b6ef613c88667826fea5218cd402a5910d22bee052cd9f8db"
    }
  },
  {
    "scenario": "scenario-h1-k8s-ray-7d",
    "diesel_count": 0,
    "floors_mwh": [
      0.0
    ],
    "warnings": [],
    "identities": {
      "baseline": "23f4fa5911aff98c77e37d42529bb5782219295f5511be9d2fe26d4b07ced635",
      "informed": "60cae3fd33c450ae93bf86ce46d7b5bf9d0d3d5091a4cfa05d840dd2ae7965c3"
    }
  },
  {
    "scenario": "scenario-h2-slurm-24h",
    "diesel_count": 0,
    "floors_mwh": [
      0.0
    ],
    "warnings": [],
    "identities": {
      "baseline": "ab014bb4e9ff8a7eb76bafbeab08aa471b70267a934cdff34b770ad26700347f",
      "informed": "c0404784a7673fb23558955a0c705da3bb1c26cc9ff6c1329fddcf4bf69376d6"
    }
  },
  {
    "scenario": "scenario-h2-slurm-7d",
    "diesel_count": 0,
    "floors_mwh": [
      0.0
    ],
    "warnings": [],
    "identities": {
      "baseline": "b75e36ed492921092abe61c66a6ddc9f5134cf70a8e5374e4fccf102b0f787e9",
      "informed": "61243ba4995c41e8be9a84aedbe1a0de7008055797701bb8371e8070a9cddf61"
    }
  },
  {
    "scenario": "scenario-uneven-multisched-01",
    "diesel_count": 1,
    "floors_mwh": [
      1.4583333333333333
    ],
    "warnings": [],
    "identities": {
      "baseline": "d7171c8d9ce5d539c50a2900a17089589502caed54f440183fc2e28a7898f76e",
      "informed": "9fb49f03b2ebea82182f507cd60cfa6046ae3673a2d0a026dfe671c8ef67e767"
    },
    "app_floor_mwh": 1.4583333333333333,
    "app_warnings": []
  },
  {
    "scenario": "scenario-fc100-islanded-v2",
    "diesel_count": 1,
    "floors_mwh": [
      152.5
    ],
    "warnings": [
      {
        "code": "bess_reserve_floor_above_usable",
        "bess_id": "bess-fc100",
        "floor_mwh": 152.5,
        "usable_mwh": 40.0,
        "winning_term": "diesel_floor",
        "diesel_units": [
          {
            "asset_id": "diesel-000",
            "delta_t_start_s": 3600.0,
            "residual_ramp_s": 60.0,
            "start_offset_s": 0.0
          }
        ],
        "diesel_worst_case_sync_s": 3660.0
      }
    ]
  },
  {
    "scenario": "scenario-fc100-islanded-zero-hot-v2",
    "diesel_count": 1,
    "floors_mwh": [
      152.5
    ],
    "warnings": [
      {
        "code": "bess_reserve_floor_above_usable",
        "bess_id": "bess-fc100",
        "floor_mwh": 152.5,
        "usable_mwh": 40.0,
        "winning_term": "diesel_floor",
        "diesel_units": [
          {
            "asset_id": "diesel-000",
            "delta_t_start_s": 3600.0,
            "residual_ramp_s": 60.0,
            "start_offset_s": 0.0
          }
        ],
        "diesel_worst_case_sync_s": 3660.0
      }
    ]
  },
  {
    "scenario": "islanded-fc-bess-diesel-slurm-gpu-peaks",
    "diesel_count": 1,
    "floors_mwh": [
      152.5
    ],
    "warnings": [
      {
        "code": "bess_reserve_floor_above_usable",
        "bess_id": "bess-fc100",
        "floor_mwh": 152.5,
        "usable_mwh": 40.0,
        "winning_term": "diesel_floor",
        "diesel_units": [
          {
            "asset_id": "diesel-000",
            "delta_t_start_s": 3600.0,
            "residual_ramp_s": 60.0,
            "start_offset_s": 0.0
          }
        ],
        "diesel_worst_case_sync_s": 3660.0
      }
    ]
  }
]
```
The third configuration is an inline catalogue seed, not a config/scenarios JSON file (P/api/routes/scenarios.py:1481–1486). The scratch snapshot selector initially raised FileNotFoundError for a guessed JSON filename, then was corrected to read build_seeded_store().list_all(); no application build failed and no seed code was changed.

## 2c.3 — D9c
Only P/config/scenarios/scenario-uneven-multisched-01.json was edited: description line 3 and delta_t_start_s line 191. Timing is 10.0 s; residual_ramp_s remains 60.0 s and all other fields remain unchanged.
Approved source/assumption: NFPA 110 Type 10; Cummins 'FAQ NFPA 110 Time to Readiness'; PROPOSED_HERE as explicitly authorized, not a newly calibrated machine measurement.
Resolved app/study BESS floor = 1.4583333333333333 MWh; build_warnings=[]. The three fc100 / islanded-fc-bess-diesel configurations remain 152.5 MWh floor, 40.0 MWh usable and each emits one warning (full terms above).

## 2c.4 — tests
TC collision search found no prior TC-ISL-17/18; IDs used: TC-ISL-17 and parametrised TC-ISL-18.
New tests cover exact canonical spec + recorded override equality, one materialised diesel, above-capacity versus below-capacity warnings, once-at-build logging, unchanged actual reserve/dispatch after diagnostic evaluation, and StartRunResponse warning serialization.
Only existing test changed: test_tc157_base_demo_loader_only_adds_study_fuel_overlay, whose raw-load expected dictionary is superseded by D8; the test cites D8 and DR-2026-09-24 Phase 1.2. No other existing test was edited.
Literal targeted output:
```text
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.1.1, pluggy-1.6.0 -- /home/runner/workspace/.pythonlibs/bin/python
rootdir: /home/runner/workspace/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim
configfile: pyproject.toml
plugins: asyncio-1.4.0, anyio-4.14.2
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items

tests/test_dr_isl_phase2c.py::test_tc_isl_17_base_demo_uses_canonical_spec_then_recorded_overrides PASSED [ 20%]
tests/test_dr_isl_phase2c.py::test_tc_isl_18_floor_warning_is_diagnostic_only[3600.0-1] PASSED [ 40%]
tests/test_dr_isl_phase2c.py::test_tc_isl_18_floor_warning_is_diagnostic_only[10.0-0] PASSED [ 60%]
tests/test_addendum_h_phase2b_stage1.py::test_tc157_base_demo_loader_only_adds_study_fuel_overlay PASSED [ 80%]
tests/test_addendum_h_phase2b_stage1.py::test_tc159_base_demo_baseline_run_reconciles_full_day PASSED [100%]

============================== 5 passed in 17.91s ==============================
```

## 2c.5 — H conditional reset gate
Fresh 24-hour H runs were executed before and after, both arms, reuse_cache=False. Existing configured RNG seeds are retained; H identity seed metadata=None follows the repository H executor tests (tests/test_study_harness.py:349). Fabric, Python/NumPy and wall clock are pinned identically (1729 / 1792454400.0). No independent date-labelled certification manifest was substituted for this literal repository-path comparison.
All four expanded H specs differ ONLY at diesel_power_block.delta_t_start_s (3600.0 -> 10.0); all eight before/after builds have zero diesel units. H1/H2 seven-day scenarios were built only, NEVER simulated.
The eight identity mappings are persisted in tools/dr_isl/H_IDENTITY_MAP_D9c.md; commit inputs were held fixed to isolate the D9c reset. Actual future source commit changes also enter identities.
Every metric dictionary and every compact tick row was compared, not merely the hashes. Non-identity run metadata also matched, excluding the newly added empty build-warning field. Literal gate results:
```json
[
  {
    "scenario": "scenario-h1-k8s-ray-24h",
    "mode": "baseline",
    "old_identity": "cb5defdcfb3367e3b2f8d0c126ef21af201b62d4d261893f9ecfce6e8d19925a",
    "new_identity": "d8813756114b33e2c48fd267531795f433112640bf096adf83e54c7108a443e4",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "metrics_compared": 27,
    "metric_differences": [],
    "compact_rows_compared": 17280,
    "compact_row_differences": 0,
    "before_compact_hash": {
      "sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755",
      "tick_count": 17280
    },
    "after_compact_hash": {
      "sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755",
      "tick_count": 17280
    },
    "run_metadata_equal_except_identity_and_added_build_warning_field": true
  },
  {
    "scenario": "scenario-h1-k8s-ray-24h",
    "mode": "informed",
    "old_identity": "bda7cab1d84991324c1b2175a4e2e85026896df37ff060b2a0b9ca7377001a57",
    "new_identity": "5e27d7b9b734299b6ef613c88667826fea5218cd402a5910d22bee052cd9f8db",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "metrics_compared": 27,
    "metric_differences": [],
    "compact_rows_compared": 17280,
    "compact_row_differences": 0,
    "before_compact_hash": {
      "sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2",
      "tick_count": 17280
    },
    "after_compact_hash": {
      "sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2",
      "tick_count": 17280
    },
    "run_metadata_equal_except_identity_and_added_build_warning_field": true
  },
  {
    "scenario": "scenario-h1-k8s-ray-7d",
    "mode": "baseline",
    "old_identity": "439e7044d457faf04e4eb4d3792495d071022311280d6f8ec596554db055fac6",
    "new_identity": "23f4fa5911aff98c77e37d42529bb5782219295f5511be9d2fe26d4b07ced635",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "simulation": "NOT RUN: build-only as instructed"
  },
  {
    "scenario": "scenario-h1-k8s-ray-7d",
    "mode": "informed",
    "old_identity": "2b91e1bd173971ffd139cade2fb83c25adb0d3b125b52ede1f1de5dc261e64dd",
    "new_identity": "60cae3fd33c450ae93bf86ce46d7b5bf9d0d3d5091a4cfa05d840dd2ae7965c3",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "simulation": "NOT RUN: build-only as instructed"
  },
  {
    "scenario": "scenario-h2-slurm-24h",
    "mode": "baseline",
    "old_identity": "52a83f88c8b1b1ca7bcfa890e0da3185930f2e8c1bcbbf06a4e30fa006c2893c",
    "new_identity": "ab014bb4e9ff8a7eb76bafbeab08aa471b70267a934cdff34b770ad26700347f",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "metrics_compared": 27,
    "metric_differences": [],
    "compact_rows_compared": 17280,
    "compact_row_differences": 0,
    "before_compact_hash": {
      "sha256": "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66",
      "tick_count": 17280
    },
    "after_compact_hash": {
      "sha256": "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66",
      "tick_count": 17280
    },
    "run_metadata_equal_except_identity_and_added_build_warning_field": true
  },
  {
    "scenario": "scenario-h2-slurm-24h",
    "mode": "informed",
    "old_identity": "760ebcf2e2f7d4aeb175aeb5dd470f1ea150b61888e7e287059fae3b04a30685",
    "new_identity": "c0404784a7673fb23558955a0c705da3bb1c26cc9ff6c1329fddcf4bf69376d6",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "metrics_compared": 27,
    "metric_differences": [],
    "compact_rows_compared": 17280,
    "compact_row_differences": 0,
    "before_compact_hash": {
      "sha256": "6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711",
      "tick_count": 17280
    },
    "after_compact_hash": {
      "sha256": "6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711",
      "tick_count": 17280
    },
    "run_metadata_equal_except_identity_and_added_build_warning_field": true
  },
  {
    "scenario": "scenario-h2-slurm-7d",
    "mode": "baseline",
    "old_identity": "d2686e54b265d9c82a12a980c44db3144c2bee185648c6ae23f118df88d3d1d7",
    "new_identity": "b75e36ed492921092abe61c66a6ddc9f5134cf70a8e5374e4fccf102b0f787e9",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "simulation": "NOT RUN: build-only as instructed"
  },
  {
    "scenario": "scenario-h2-slurm-7d",
    "mode": "informed",
    "old_identity": "1e8ed14c287fe22b803a59ea584148924ef25e8d25a766a0ab4ec628b6042c86",
    "new_identity": "61243ba4995c41e8be9a84aedbe1a0de7008055797701bb8371e8070a9cddf61",
    "diesel_counts": [
      0,
      0
    ],
    "expanded_spec_diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "simulation": "NOT RUN: build-only as instructed"
  }
]
```
H2 conventional retains the PRE-EXISTING typed StartFuelReconciliationError: reported=124.000000000, measured=124.000000000, recorded_events=6, measured_events=11, hot_standby_release_charged=True. Both records remain status=FAIL; no event list/guard was repaired. Diagnostic accounting used the existing allow_guard_failure path. Other three H arm records are PASS before and after.

### Base-demo A/B: fresh seed 42, no parameter overrides, twice per arm
All reported metric dictionaries and compact streams match their repeated run. GT fuel below is GT-only; diesel gallons are separately reported and are NOT included in turbine_fuel_mmbtu.
| Metric | 2026-09-29 baseline/informed (given reference) | New baseline | New informed |
|---|---|---|---|
| Dispatch curtailment MWh | 4.795 / 0.370 | 13.657247027 | 10.361665378 |
| GT fuel MMBtu | 757.524 / 670.028 | 757.523545804 | 670.027967582 |
| Unserved MWh | 1.552 / 0.036 | 0.414708048 | 0.027148128 |
| Peak unserved MW | 36.886 / 7.523 | 27.5 | 7.52325057 |
D8 now materialises the configured diesel. Its actual new output is 0–20 MW and 10.0 MWh per arm. It consumes 115.63888888918185 gal per arm (first-tick remaining minus final remaining; no first-tick diesel burn). The historical raw-loader study had zero diesel units/output. Demand compute trace remains a1483fdf5ef04fc06dcf549c3d9d5dd52ba66fc8b8cef7380bad4cee750d03df. These are deliberately different modeled supply inputs from the historical raw study, not dispatch/cost/frequency edits.
Archived raw-study tick streams survive. Comparing them to the new compact streams confirms compute/cooling/total demand equality at every tick. The extra curtailment plus extra served load accounts for the new 10 MWh diesel contribution (floating-point residuals shown literally):
```json
[
  {
    "mode": "baseline",
    "archive_record": ".study-mcp-data/cache/records/2371244b01b6bb564b5b3a3c434899374d89bfdc7afe79479fa5f8ed0fe8e7ea.json",
    "identical_compute_cooling_and_total_demand_every_tick": true,
    "old_curtailment_mwh": 4.794772638888889,
    "new_curtailment_mwh": 13.65724611111111,
    "extra_curtailment_mwh": 8.86247347222222,
    "old_unserved_mwh": 1.5522348611111112,
    "new_unserved_mwh": 0.41470833333333335,
    "extra_served_mwh": 1.1375265277777777,
    "extra_curtailment_plus_extra_served_mwh": 9.999999999999998
  },
  {
    "mode": "informed",
    "archive_record": ".study-mcp-data/cache/records/8b6a71123e6c7ea24452f96e63da5bade985a26e05a6b013f4cd03f0feec9097.json",
    "identical_compute_cooling_and_total_demand_every_tick": true,
    "old_curtailment_mwh": 0.3700526388888889,
    "new_curtailment_mwh": 10.361665277777778,
    "extra_curtailment_mwh": 9.991612638888888,
    "old_unserved_mwh": 0.035535555555555556,
    "new_unserved_mwh": 0.027148194444444444,
    "extra_served_mwh": 0.008387361111111113,
    "extra_curtailment_plus_extra_served_mwh": 9.999999999999998
  }
]
```
Full requested metrics, components, curtailment fuel attribution/exposure, starts, BESS start/end, reserve refusals, forecast misses, balance failure counts and provenance:
```json
[
  {
    "mode": "baseline",
    "repetitions": 2,
    "metrics_identical": true,
    "compact_hash_both": {
      "sha256": "f33a5c8078523942782952fc9ac89f216e0f1c825a85aafd71aa892a90c6fd38",
      "tick_count": 1440
    },
    "initial_bess_soc": 0.95,
    "first_tick_bess_soc": 0.9503857481294763,
    "final_tick_bess_soc": 0.9999999985053148,
    "diesel_output_range_mw": [
      0.0,
      20.0
    ],
    "diesel_energy_mwh": 10.0,
    "diesel_initial_first_tick_fuel_gal": 11040.0,
    "diesel_final_fuel_gal": 10924.361111110818,
    "diesel_fuel_used_gal": 115.63888888918154,
    "physical_balance_failures": 0,
    "measured_start_event_count": 2,
    "build_warnings": [],
    "study_input_provenance": {
      "canonicalised": true,
      "post_validation_overrides": [
        {
          "field": "turbine_units",
          "operation": "apply_study_fuel_model"
        },
        {
          "field": "turbine_commitment_mode",
          "value": "baseline"
        },
        {
          "operation": "baseline_demand_replay",
          "tick_count": 1440
        },
        {
          "event_count": 237,
          "operation": "baseline_workload_replay",
          "removed_fields": [
            "kube_clusters",
            "slurm_config"
          ]
        }
      ],
      "source": "config/scenarios/scenario-uneven-multisched-01.json",
      "validation": "ScenarioSpec.model_validate_json -> model_dump(mode=json)"
    },
    "metrics": {
      "bess_soc_final": 0.999999999,
      "bess_soc_max": 0.999999999,
      "bess_soc_min": 0.70762325,
      "commitment": {
        "distinct_event_count": 8,
        "log_complete": true,
        "omitted_record_count": 0,
        "reserve_floor_distinct_event_count": 0,
        "reserve_floor_log_complete": true,
        "reserve_floor_omitted_record_count": 0,
        "reserve_floor_refusal_count": 0,
        "reserve_floor_suppressed_repeat_count": 0,
        "reserve_floor_visible_distinct_event_count": 0,
        "same_unit_restart_within_min_down_window_count": 0,
        "suppressed_repeat_count": 0,
        "visible_distinct_event_count": 8
      },
      "compute_trace_count": 1440,
      "compute_trace_sha256": "a1483fdf5ef04fc06dcf549c3d9d5dd52ba66fc8b8cef7380bad4cee750d03df",
      "constraints_valid": true,
      "daily_breakdown": [
        {
          "bess_soc_end": 0.999999999,
          "curtailed_mwh": 13.657247027,
          "day": 1,
          "fuel_by_component_mmbtu": {
            "hot_standby_fuel_mmbtu": 0.039236111,
            "load_fuel_mmbtu": 732.917643026,
            "no_load_fuel_mmbtu": 8.566666667,
            "start_fuel_mmbtu": 16.0
          },
          "fuel_mmbtu": 757.523545804,
          "kind": "weekday",
          "unserved_mwh": 0.414708048
        }
      ],
      "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
        "gt-hot-01": 29.230315323,
        "gt-hot-02": 23.474442334,
        "gt-spin-01": 43.37128373,
        "gt-spin-02": 41.683279435
      },
      "dispatch_curtailment_attributable_fuel_mmbtu": 137.759320822,
      "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
        "hot_standby_fuel_mmbtu": 0.0,
        "load_fuel_mmbtu": 326.374694106,
        "no_load_fuel_mmbtu": 3.563333333,
        "start_fuel_mmbtu": 0.0
      },
      "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
        "gt-hot-01": 65.716888202,
        "gt-hot-02": 49.576458333,
        "gt-spin-01": 109.711268337,
        "gt-spin-02": 104.933412567
      },
      "dispatch_curtailment_interval_exposure_fuel_mmbtu": 329.938027439,
      "dispatch_curtailment_mwh": 13.657247027,
      "energy_balance": {
        "closure_status": true,
        "max_abs_physical_ledger_defect_mw": 0.0,
        "served_demand_mwh": 64.114647341,
        "unserved_demand_mwh": 0.414708048
      },
      "forecast": {
        "miss_count": 0,
        "miss_peak_mw": 0.0
      },
      "fuel_by_component_mmbtu": {
        "hot_standby_fuel_mmbtu": 0.039236111,
        "load_fuel_mmbtu": 732.917643026,
        "no_load_fuel_mmbtu": 8.566666667,
        "start_fuel_mmbtu": 16.0
      },
      "fuel_reconciled": true,
      "hard_violations": [],
      "interval_seconds": 5.0,
      "peak_unserved_mw": 27.5,
      "served_mwh": 64.114647341,
      "start_fuel_reconciliation": {
        "measured_event_count": 2,
        "measured_start_fuel_mmbtu": 16.0,
        "passed": true,
        "recorded_event_count": 2,
        "release_charged": true,
        "tier_sum_mmbtu": null
      },
      "tick_count": 1440,
      "turbine_fuel_mmbtu": 757.523545804,
      "unserved_intervals": [
        {
          "end_sim_time_s": 465.0,
          "peak_unserved_mw": 22.30936246553462,
          "start_sim_time_s": 325.0
        },
        {
          "end_sim_time_s": 1860.0,
          "peak_unserved_mw": 27.5,
          "start_sim_time_s": 1850.0
        }
      ],
      "unserved_mwh": 0.414708048
    }
  },
  {
    "mode": "informed",
    "repetitions": 2,
    "metrics_identical": true,
    "compact_hash_both": {
      "sha256": "02f6edeb0cf502b6a719974990eed1d54d8c6862ea581f4213fc84fed6c47283",
      "tick_count": 1440
    },
    "initial_bess_soc": 0.95,
    "first_tick_bess_soc": 0.9503857481294763,
    "final_tick_bess_soc": 0.9507210908516522,
    "diesel_output_range_mw": [
      0.0,
      20.0
    ],
    "diesel_energy_mwh": 10.0,
    "diesel_initial_first_tick_fuel_gal": 11040.0,
    "diesel_final_fuel_gal": 10924.361111110818,
    "diesel_fuel_used_gal": 115.63888888918154,
    "physical_balance_failures": 0,
    "measured_start_event_count": 2,
    "build_warnings": [],
    "study_input_provenance": {
      "canonicalised": true,
      "post_validation_overrides": [
        {
          "field": "turbine_units",
          "operation": "apply_study_fuel_model"
        },
        {
          "field": "turbine_commitment_mode",
          "value": "informed"
        },
        {
          "operation": "baseline_demand_replay",
          "tick_count": 1440
        },
        {
          "event_count": 237,
          "operation": "baseline_workload_replay",
          "removed_fields": [
            "kube_clusters",
            "slurm_config"
          ]
        }
      ],
      "source": "config/scenarios/scenario-uneven-multisched-01.json",
      "validation": "ScenarioSpec.model_validate_json -> model_dump(mode=json)"
    },
    "metrics": {
      "bess_soc_final": 0.950721091,
      "bess_soc_max": 0.954116222,
      "bess_soc_min": 0.805512891,
      "commitment": {
        "distinct_event_count": 11,
        "log_complete": true,
        "omitted_record_count": 0,
        "reserve_floor_distinct_event_count": 1377,
        "reserve_floor_log_complete": true,
        "reserve_floor_omitted_record_count": 0,
        "reserve_floor_refusal_count": 1377,
        "reserve_floor_suppressed_repeat_count": 0,
        "reserve_floor_visible_distinct_event_count": 1377,
        "same_unit_restart_within_min_down_window_count": 0,
        "suppressed_repeat_count": 1374,
        "visible_distinct_event_count": 11
      },
      "compute_trace_count": 1440,
      "compute_trace_sha256": "a1483fdf5ef04fc06dcf549c3d9d5dd52ba66fc8b8cef7380bad4cee750d03df",
      "constraints_valid": true,
      "daily_breakdown": [
        {
          "bess_soc_end": 0.950721091,
          "curtailed_mwh": 10.361665378,
          "day": 1,
          "fuel_by_component_mmbtu": {
            "hot_standby_fuel_mmbtu": 0.000347222,
            "load_fuel_mmbtu": 647.184287026,
            "no_load_fuel_mmbtu": 6.843333333,
            "start_fuel_mmbtu": 16.0
          },
          "fuel_mmbtu": 670.027967582,
          "kind": "weekday",
          "unserved_mwh": 0.027148128
        }
      ],
      "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
        "gt-hot-01": 23.788387843,
        "gt-hot-02": 19.467154433,
        "gt-spin-01": 28.820942507,
        "gt-spin-02": 27.774953651
      },
      "dispatch_curtailment_attributable_fuel_mmbtu": 99.851438434,
      "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
        "hot_standby_fuel_mmbtu": 0.0,
        "load_fuel_mmbtu": 271.70085307,
        "no_load_fuel_mmbtu": 2.46,
        "start_fuel_mmbtu": 0.0
      },
      "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
        "gt-hot-01": 65.963309428,
        "gt-hot-02": 48.961839923,
        "gt-spin-01": 81.302955229,
        "gt-spin-02": 77.93274849
      },
      "dispatch_curtailment_interval_exposure_fuel_mmbtu": 274.16085307,
      "dispatch_curtailment_mwh": 10.361665378,
      "energy_balance": {
        "closure_status": true,
        "max_abs_physical_ledger_defect_mw": 0.0,
        "served_demand_mwh": 64.50220726,
        "unserved_demand_mwh": 0.027148128
      },
      "forecast": {
        "miss_count": 4,
        "miss_peak_mw": 3.208264895
      },
      "fuel_by_component_mmbtu": {
        "hot_standby_fuel_mmbtu": 0.000347222,
        "load_fuel_mmbtu": 647.184287026,
        "no_load_fuel_mmbtu": 6.843333333,
        "start_fuel_mmbtu": 16.0
      },
      "fuel_reconciled": true,
      "hard_violations": [],
      "interval_seconds": 5.0,
      "peak_unserved_mw": 7.52325057,
      "served_mwh": 64.50220726,
      "start_fuel_reconciliation": {
        "measured_event_count": 2,
        "measured_start_fuel_mmbtu": 16.0,
        "passed": true,
        "recorded_event_count": 2,
        "release_charged": true,
        "tier_sum_mmbtu": null
      },
      "tick_count": 1440,
      "turbine_fuel_mmbtu": 670.027967582,
      "unserved_intervals": [
        {
          "end_sim_time_s": 345.0,
          "peak_unserved_mw": 7.5232505700275,
          "start_sim_time_s": 335.0
        },
        {
          "end_sim_time_s": 1855.0,
          "peak_unserved_mw": 4.628919357798523,
          "start_sim_time_s": 1850.0
        }
      ],
      "unserved_mwh": 0.027148128
    }
  }
]
```
compare_metrics/compare_runs acceptance verdict and EVERY condition (identical in both repetitions):
```json
{
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
  "conditions": {
    "baseline_energy_balance": true,
    "baseline_fuel_reconciled": true,
    "baseline_valid": true,
    "build_parity": true,
    "identical_compute_trace": true,
    "informed_energy_balance": true,
    "informed_fuel_reconciled": true,
    "informed_peak_unserved_no_worse": true,
    "informed_unserved_energy_no_worse": true,
    "informed_valid": true
  },
  "informed_vs_baseline": {
    "baseline_peak_unserved_mw": 27.5,
    "baseline_unserved_mwh": 0.414708048,
    "informed_peak_unserved_mw": 7.52325057,
    "informed_unserved_mwh": 0.027148128
  },
  "verdict": "PASS"
}
```
### App path comparison
Unchanged tools/dr_isl/baseline_runner.py via ScenarioSpec + RunManager, instant playback, in-memory sink; one run for the requested comparison. Energies use sum(MW * 5 / 3600) over every tick:
```json
{
  "ticks": 1440,
  "dispatch_curtailment_mwh": 13.6572470270914,
  "unserved_mwh": 0.4147080477143562,
  "physical_hash": "4a3232ee26b604f48b9e48346680993b12bd04c338134a6be0ae6520a94268f4"
}
```
### Six regression scenarios vs Phase 2b
Unchanged persisted runner, two repetitions each. All twelve physical hashes match the Phase 2b POST-fix reference hashes; all balance-failure counts are zero. No physical delta to explain. Full literal hashes and counts:
```json
[
  {
    "scenario_id": "S10_mit_supercloud_2021-08-11",
    "repetition": 1,
    "physical_sha256": "51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52",
    "tick_count": 17280,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "S10_mit_supercloud_2021-08-11",
    "repetition": 2,
    "physical_sha256": "51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52",
    "tick_count": 17280,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "demo-islanded-ramp",
    "repetition": 1,
    "physical_sha256": "fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a",
    "tick_count": 2160,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "demo-islanded-ramp",
    "repetition": 2,
    "physical_sha256": "fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a",
    "tick_count": 2160,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-100mw-fuel-cell-bess-diesel",
    "repetition": 1,
    "physical_sha256": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
    "tick_count": 252,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-100mw-fuel-cell-bess-diesel",
    "repetition": 2,
    "physical_sha256": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
    "tick_count": 252,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-equinix-sj-1",
    "repetition": 1,
    "physical_sha256": "328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84",
    "tick_count": 720,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": false,
    "verification_modes": [
      "grid_tied_provisional"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-equinix-sj-1",
    "repetition": 2,
    "physical_sha256": "328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84",
    "tick_count": 720,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": false,
    "verification_modes": [
      "grid_tied_provisional"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-hybrid-ai-100mw-addendum-i",
    "repetition": 1,
    "physical_sha256": "4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518",
    "tick_count": 120,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-hybrid-ai-100mw-addendum-i",
    "repetition": 2,
    "physical_sha256": "4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518",
    "tick_count": 120,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-turbine-01",
    "repetition": 1,
    "physical_sha256": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a",
    "tick_count": 720,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a",
    "identical_to_phase2b": true
  },
  {
    "scenario_id": "scenario-turbine-01",
    "repetition": 2,
    "physical_sha256": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a",
    "tick_count": 720,
    "failing_tick_count": 0,
    "failing_ticks": [],
    "spec_island_mode": true,
    "verification_modes": [
      "islanded_verified"
    ],
    "tolerances_mw": [
      1.9913e-14
    ],
    "hash_exclusions": [
      "advisory_telemetry",
      "fabric_modal",
      "insufficient_reserve_proposal_id",
      "wall_stamp_utc"
    ],
    "phase2b_reference": "006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a",
    "identical_to_phase2b": true
  }
]
```

## 2c.6 — full suite, REAL package
The first full-suite execution reached 100% but the scratch session-finish collector raised AssertionError while parsing the prior report, before saving counts/failure IDs. That capture is NOT used as a passing check and complete counts/IDs cannot be claimed. T/full-suite-capture-error.log preserves it. Only the scratch collector was corrected (pre-parse a contiguous 15-node summary and persist live results); application/test code stayed unchanged, and the full suite was executed again.
Command: PYTHONDONTWRITEBYTECODE=1 python /tmp/DR-ISL-phase2c/suite_capture.py; pytest tests -q --tb=short -p no:cacheprovider --basetemp=/tmp/DR-ISL-phase2c/pytest-temp.
Reference failing set is read from the literal Phase 2b real-suite summary in tools/dr_isl/PHASE_2B_REPORT.md, not from missing /tmp history.
The repeated suite was STOPPED on observing an added TC156 failure. No final full-suite pass/fail totals or removed-node claims are made. Counts below are PARTIAL report-event counts (including subtests), not complete suite counts.
Added node: tests/test_addendum_h_phase2b_stage1.py::test_tc156_phase1_h_expansions_match_prechange_hashes.
P/tests/test_addendum_h_phase2b_stage1.py:457–477 still requires frozen expanded-spec hashes; line 477 fails. This test/hash fixture was NOT updated. The approved D9c timing change is the only expanded-spec delta, as independently demonstrated by the H gate. Under the explicit any-added-failure STOP rule, no test or production correction was attempted.
Literal added assertion:
```text
tests/test_addendum_h_phase2b_stage1.py:477: in test_tc156_phase1_h_expansions_match_prechange_hashes
    assert hashlib.sha256(canonical).hexdigest() == expected_hash
E   AssertionError: assert '327835d3b130...38f4e1ba0b050' == 'f2465233ab67...f38a5ffe9681a'
E     
E     - f2465233ab677c0c9305b139fcc6ccd8b675aeea4df6ccdf46ff38a5ffe9681a
E     + 327835d3b1305e731c4397a19a772a877458ec4954b3406474f38f4e1ba0b050
```
Observed failure-set comparison:
```text

```
```json
{
  "counts": {
    "passed": 1925,
    "skipped": 3,
    "failed": 15,
    "xfailed": 18
  },
  "failed_nodeids": [
    "tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation",
    "tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config",
    "tests/test_addendum_h_phase2b_stage1.py::test_tc156_phase1_h_expansions_match_prechange_hashes",
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
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load"
  ],
  "status": "STOPPED at added TC156 failure; partial suite only",
  "complete": false,
  "reference_15": [
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
  "added": [
    "tests/test_addendum_h_phase2b_stage1.py::test_tc156_phase1_h_expansions_match_prechange_hashes"
  ],
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
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load"
  ],
  "removed": [],
  "reference_not_yet_observed": [
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ]
}
```
The one reference node not yet observed is NOT a removed failure: it had not completed when the suite was stopped.

## 2c.7 — implementation and integrity
Implementation commit: NONE. Requested implementation commit deferred because the suite gate failed. The nine source/test/scenario files remain staged but uncommitted. The report, identity map and STOP1 preservation are documentation-only outputs.
No frozen H legacy asset, no H expansion code edits, no other scenario JSON edits, no dispatch/cost/commitment/reserve-floor formula/frequency/protection changes. No publish/deploy/push.
The managed GridSignal web workflow was restarted once. Uvicorn completed startup and GET / returned 200; appPreview rendered the existing sign-in screen. The unauthenticated browser's 401 is the sign-in boundary, not a UI behavior test. No authentication flow was changed.
Changed files and new-side hunk line ranges:
```json
{
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/runs.py": [
    "687\u2013690"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py": [
    "2893"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json": [
    "3",
    "191"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py": [
    "1\u201343"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py": [
    "1275"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py": [
    "1946\u20131948",
    "1952"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py": [
    "13",
    "269\u2013273",
    "277\u2013285",
    "290\u2013295",
    "376\u2013385"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py": [
    "495\u2013497",
    "504"
  ],
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py": [
    "1\u201372"
  ]
}
```
Full implementation diff (literal file paths and hunk line ranges):
```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/runs.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/runs.py
index 4470b05..0cee4cd 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/runs.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/runs.py
@@ -684,7 +684,10 @@ async def start_run(
         )
 
     await manager.start_run(ctx)
-    return StartRunResponse(run_id=run_id, soc_floor_pct=_soc_floor, soc_ceil_pct=_soc_ceil)
+    return StartRunResponse(
+        run_id=run_id, soc_floor_pct=_soc_floor, soc_ceil_pct=_soc_ceil,
+        build_warnings=ctx.metadata.get("build_warnings", []),
+    )
 
 
 @router.get(
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py
index 79e9fb8..94f7ca5 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py
@@ -2890,6 +2890,7 @@ class StartRunRequest(BaseModel):
 
 class StartRunResponse(BaseModel):
     run_id: str
+    build_warnings: list[dict[str, Any]] = Field(default_factory=list)  # DR D9b
     soc_floor_pct: float = 10.0   # operator-set BESS lower display bound
     soc_ceil_pct: float  = 95.0   # operator-set BESS upper display bound
 
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
index 3158199..b8b4f48 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json
@@ -1,6 +1,6 @@
 {
   "name": "01 Turbine Scenario with Kubernetes Slurm Ray",
-  "description": "Two-hour Kubernetes, Slurm, and Ray demonstration with 45 MW and 90 MW bursts starting at t=30 s and t=310 s, followed by bursts at t=920 s, t=1850 s, and t=2700 s. Burst durations are 240 s, 300 s, and 600 s for the final three bursts, so workloads do not overlap. Two gas turbines are spinning at 35% minimum stable load from t=0; two more start from hot standby at Burst-02 and the grid-forming BESS bridges their startup gap. GE assumptions: 300-second hot start, 360-second warm start, 600-second cold start, and 30 MW/min ramp.",
+  "description": "Two-hour Kubernetes, Slurm, and Ray demonstration with 45 MW and 90 MW bursts starting at t=30 s and t=310 s, followed by bursts at t=920 s, t=1850 s, and t=2700 s. Burst durations are 240 s, 300 s, and 600 s for the final three bursts, so workloads do not overlap. Two gas turbines are spinning at 35% minimum stable load from t=0; two more start from hot standby at Burst-02 and the grid-forming BESS bridges their startup gap. GE assumptions: 300-second hot start, 360-second warm start, 600-second cold start, and 30 MW/min ramp. Diesel delta_t_start_s revised 3600 → 10 s on 2026-10-21 (DR-2026-10-20-ISLAND-COLLAPSE D9c; NFPA 110 Type 10; PROPOSED_HERE).",
 
   "hardware_profile_id": "enterprise_8gpu_air",
   "dt_lead_seconds": 45.0,
@@ -188,7 +188,7 @@
     "p_start": 1.0,
     "target_reliability": 1.0,
     "f_block": 1.0,
-    "delta_t_start_s": 3600.0,
+    "delta_t_start_s": 10.0,
     "residual_ramp_s": 60.0,
     "start_stagger_interval_s": 1.0,
     "authority_tier": "advisory_only"
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
new file mode 100644
index 0000000..bb24105
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
@@ -0,0 +1,43 @@
+"""Build-time diagnostics only; never change reserve floors or dispatch."""
+import logging
+
+from core.dispatch import MARGIN_MULTIPLIER
+
+_log = logging.getLogger("gridsignal.scenario_factory")
+
+
+def reserve_capacity_warnings(state) -> list[dict]:
+    """DR D9b: flag the arbitrator's actual floor, without capping/rejecting it."""
+    arbitrator = state.arbitrator
+    timings = [
+        {
+            "asset_id": unit.config.asset_id,
+            "delta_t_start_s": unit.config.delta_t_start_s,
+            "residual_ramp_s": unit.config.residual_ramp_s,
+            "start_offset_s": unit.config.start_offset_s,
+        }
+        for unit in state.diesel_units
+    ]
+    warnings = []
+    for bess in state.bess_units:
+        floor = arbitrator.soc_floor_mwh(bess)
+        if floor <= bess.config.usable_mwh:
+            continue
+        # Diagnostic attribution of the existing diesel term, not a second floor.
+        diesel_term = (
+            MARGIN_MULTIPLIER * bess.config.rated_mw
+            * arbitrator.diesel_worst_case_sync_s() / 3600.0
+        )
+        warning = {
+            # PROPOSED_HERE: stable diagnostic code for API/study consumers.
+            "code": "bess_reserve_floor_above_usable",
+            "bess_id": bess.config.asset_id,
+            "floor_mwh": floor,
+            "usable_mwh": bess.config.usable_mwh,
+            "winning_term": "diesel_floor" if diesel_term >= floor else "depth_reserve",
+            "diesel_units": timings,
+            "diesel_worst_case_sync_s": arbitrator.diesel_worst_case_sync_s(),
+        }
+        warnings.append(warning)
+        _log.warning("DR D9b build warning: %s", warning)
+    return warnings
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
index ad80ba0..6eec6e0 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
@@ -1272,6 +1272,7 @@ class RunContext:
     dt_lead_seconds: float
     end_sim_time: float                    # scenario duration, e.g. 4h = 14400s
     playback_speed: float = 1.0            # 1.0 = real-time-equivalent, up to "max"
+    metadata: dict[str, Any] = field(default_factory=dict, kw_only=True)  # DR D9b; preserve positional callers.
     sink: TimeseriesSink = field(default_factory=InMemoryTimeseriesSink)
     sim_time: float = 0.0
     _next_event_idx: int = 0
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
index 53e3fa3..226dcfd 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
@@ -1943,9 +1943,13 @@ def build_run_context_from_spec(
     if _turbine_commitment_controller is not None:
         sim_state._commitment_mode = _commitment_mode
         sim_state._commitment_transition_sink = _turbine_commitment_controller
+    # DR-2026-10-20-ISLAND-COLLAPSE D9b: warn once at build, never alter the floor.
+    from runtime.build_warnings import reserve_capacity_warnings
+    _build_warnings = reserve_capacity_warnings(sim_state)
     return RunContext(
         run_id=run_id,
         sim_state=sim_state,
+        metadata={"build_warnings": _build_warnings},
         events=events,
         dt_lead_seconds=float(spec_data.get("dt_lead_seconds", 30.0)),
         end_sim_time=float(spec_data.get("end_sim_time", 300.0)),
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py
index 9edcb34..5029a1f 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py
@@ -10,6 +10,7 @@ import subprocess
 from pathlib import Path
 from typing import Any, Iterable, Mapping
 
+from api.schemas import ScenarioSpec
 from runtime.phase2b_reference import (
     apply_study_fuel_model,
     expand_phase2b_reference_spec,
@@ -265,15 +266,33 @@ class StudyRunExecutor:
                 / "scenarios"
                 / f"{BASE_DEMO_SCENARIO_ID}.json"
             )
-            on_disk_spec = json.loads(base_path.read_text())
-            spec = copy.deepcopy(on_disk_spec)
+            # DR D8 supersedes DR-2026-09-24-BASE-STUDY Phase 1.2 raw loading.
+            # H references deliberately retain their separate expansion above.
+            spec = ScenarioSpec.model_validate_json(
+                base_path.read_bytes()
+            ).model_dump(mode="json")
             spec["turbine_units"] = apply_study_fuel_model(
                 spec.get("turbine_units", [])
             )
+            # PROPOSED_HERE: provenance labels describe overrides, not control parameters.
+            spec["study_input_provenance"] = {
+                "canonicalised": True,
+                "validation": "ScenarioSpec.model_validate_json -> model_dump(mode=json)",
+                "source": f"config/scenarios/{BASE_DEMO_SCENARIO_ID}.json",
+                "post_validation_overrides": [
+                    {"field": "turbine_units", "operation": "apply_study_fuel_model"},
+                ],
+            }
         if duration_seconds is not None:
             spec["end_sim_time"] = float(duration_seconds)
         if parameter_overrides:
             _deep_merge(spec, parameter_overrides)
+        if study_class == STUDY_CLASS_BASE_DEMO:
+            overrides = spec["study_input_provenance"]["post_validation_overrides"]
+            if duration_seconds is not None:
+                overrides.append({"field": "end_sim_time", "value": float(duration_seconds)})
+            if parameter_overrides:
+                overrides.append({"operation": "parameter_overrides", "value": copy.deepcopy(parameter_overrides)})
         return spec
 
     def _probe(
@@ -354,6 +373,16 @@ class StudyRunExecutor:
                 ):
                     progress_callback(len(tick_rows) * self.tick_seconds)
             raw_metadata = _controller_metadata(ctx)
+            raw_metadata["build_warnings"] = ctx.metadata.get("build_warnings", [])
+            if "study_input_provenance" in spec:
+                provenance = copy.deepcopy(spec["study_input_provenance"])
+                provenance["post_validation_overrides"].extend([
+                    {"field": "turbine_commitment_mode", "value": mode},
+                    {"operation": "baseline_demand_replay", "tick_count": len(demand_replay)},
+                    {"operation": "baseline_workload_replay", "event_count": len(replay_events),
+                     "removed_fields": ["kube_clusters", "slurm_config"]},
+                ])
+                raw_metadata["study_input_provenance"] = provenance
             raw_metadata.update(
                 {
                     "run_id": f"{scenario_id}-{mode}-{identity.digest[:16]}",
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py
index a595f65..e4d09c5 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py
@@ -492,13 +492,16 @@ def test_tc157_base_demo_loader_only_adds_study_fuel_overlay(
 
     base_path = SCENARIOS / f"{BASE_DEMO_SCENARIO_ID}.json"
     on_disk = json.loads(base_path.read_text())
-    expected = copy.deepcopy(on_disk)
+    # D8 supersedes DR-2026-09-24-BASE-STUDY Phase 1.2 raw loading.
+    from api.schemas import ScenarioSpec
+    expected = ScenarioSpec.model_validate_json(base_path.read_bytes()).model_dump(mode="json")
     # PROPOSED_HERE: Assert the harness-only overlay already used by Phase 2b.
     for turbine in expected.get("turbine_units", []):
         turbine["gt_mode"] = "aero"
 
     executor = StudyRunExecutor(output_dir=tmp_path / "base-loader")
     loaded = executor._expanded_spec(BASE_DEMO_SCENARIO_ID, None, None)
+    assert loaded.pop("study_input_provenance")["canonicalised"] is True
     assert loaded == expected
     assert executor._study_class_for_scenario(BASE_DEMO_SCENARIO_ID) == (
         STUDY_CLASS_BASE_DEMO
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py
new file mode 100644
index 0000000..b84a58d
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py
@@ -0,0 +1,72 @@
+"""TC-ISL-17/18: D8 canonical input and D9b diagnostic-only warning."""
+import copy
+import json
+from pathlib import Path
+
+import pytest
+
+from api.schemas import ScenarioSpec, StartRunResponse
+from runtime.build_warnings import reserve_capacity_warnings
+from runtime.phase2b_reference import apply_study_fuel_model
+from runtime.scenario_factory import build_run_context_from_spec
+from study_harness.executor import BASE_DEMO_SCENARIO_ID, StudyRunExecutor
+
+# PROPOSED_HERE: locate the catalogue fixture rather than duplicate scenario inputs.
+SOURCE = Path(__file__).resolve().parents[1] / "config/scenarios" / (
+    BASE_DEMO_SCENARIO_ID + ".json"
+)
+
+
+def test_tc_isl_17_base_demo_uses_canonical_spec_then_recorded_overrides(tmp_path):
+    expected = ScenarioSpec.model_validate_json(SOURCE.read_bytes()).model_dump(mode="json")
+    expected["turbine_units"] = apply_study_fuel_model(expected["turbine_units"])
+    executor = StudyRunExecutor(output_dir=tmp_path)
+    actual = executor._expanded_spec(BASE_DEMO_SCENARIO_ID, None, None)
+    provenance = actual.pop("study_input_provenance")
+    assert actual == expected
+    assert len(actual["diesel_units"]) == 1
+    assert provenance["canonicalised"] is True
+    assert provenance["post_validation_overrides"] == [
+        {"field": "turbine_units", "operation": "apply_study_fuel_model"}
+    ]
+    overridden = executor._expanded_spec(
+        BASE_DEMO_SCENARIO_ID, {"turbine_forecast_lead_seconds": 90.0}, 120.0
+    )
+    assert overridden["end_sim_time"] == 120.0
+    assert overridden["turbine_forecast_lead_seconds"] == 90.0
+    assert overridden["study_input_provenance"]["post_validation_overrides"][1:] == [
+        {"field": "end_sim_time", "value": 120.0},
+        {"operation": "parameter_overrides",
+         "value": {"turbine_forecast_lead_seconds": 90.0}},
+    ]
+
+
+@pytest.mark.parametrize("start_s,expected_count", [(3600.0, 1), (10.0, 0)])
+def test_tc_isl_18_floor_warning_is_diagnostic_only(start_s, expected_count, caplog):
+    # D9b fixture explicitly covers the legacy over-capacity floor and D9c timing.
+    raw = json.loads(SOURCE.read_bytes())
+    raw["diesel_power_block"]["delta_t_start_s"] = start_s
+    spec = ScenarioSpec.model_validate_json(json.dumps(raw)).model_dump(mode="json")
+    ctx = build_run_context_from_spec("tc-isl-18", spec)
+    bess = ctx.sim_state.bess_units[0]
+    arbitrator = ctx.sim_state.arbitrator
+    expected_floor = 2.5 * 30.0 * (start_s + 60.0) / 3600.0
+    assert arbitrator.soc_floor_mwh(bess) == pytest.approx(expected_floor)
+    warnings = ctx.metadata["build_warnings"]
+    assert len(warnings) == expected_count
+    assert sum("DR D9b build warning:" in r.message for r in caplog.records) == expected_count
+    if warnings:
+        warning = warnings[0]
+        assert warning["bess_id"] == bess.config.asset_id
+        assert warning["floor_mwh"] == pytest.approx(76.25)
+        assert warning["usable_mwh"] == 60.0
+        assert warning["winning_term"] == "diesel_floor"
+        assert warning["diesel_units"][0]["delta_t_start_s"] == start_s
+        assert warning["diesel_units"][0]["residual_ramp_s"] == 60.0
+    before = (bess.soc_mwh, arbitrator.soc_floor_mwh(bess),
+              copy.deepcopy(arbitrator).tick(20.0, 5.0))
+    assert reserve_capacity_warnings(ctx.sim_state) == warnings
+    after = (bess.soc_mwh, arbitrator.soc_floor_mwh(bess),
+             copy.deepcopy(arbitrator).tick(20.0, 5.0))
+    assert after == before
+    assert StartRunResponse(run_id=ctx.run_id, build_warnings=warnings).build_warnings == warnings
```

Report outputs: T/PHASE_2C_REPORT.md; tools/dr_isl/PHASE_2C_REPORT.md; tools/dr_isl/H_IDENTITY_MAP_D9c.md. Previous STOP report preserved as above. Raw JSON metrics/records/compact streams and suite logs are in T only. The report/map/STOP rename are committed in a separate report-only commit.
STOP — PHASE 2c BLOCKED AT 2c.6. TC156 was left unchanged. Do not start Phase 3.
