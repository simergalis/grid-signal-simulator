# DR-2026-10-20-ISLAND-COLLAPSE — resumed Phase 2c

Status: FINISHED Phase 2c, including 2c.6 completion and 2c.8 READ-ONLY diagnosis. No Phase 3.
Base: 869d55bbdfa1ce16e6e1514ade9a6ca4ca3a0442.
Implementation checkpoint: 52568e322aad56ee4c42800cc0a8c64b3fd17bf5 (automatic checkpoint, different commit message).
Package prefix P: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/.
Scratch prefix T: /tmp/DR-ISL-phase2c/.
Previous STOP report/map commit: fc61092120e7c49055699426a99d59469d9c6756. New TC156-only commit: ed7da7011b6b9f3348e035d8fa1e2afa9b6f8daa. The final report-only commit hash is delivered in chat after this file is committed.

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
D8 now materialises the configured diesel. Its actual new output is 0–20 MW and 10.0 MWh per arm. It consumes 115.63888888918154 gal per arm (first-tick remaining minus final remaining; no first-tick diesel burn). The historical raw-loader study had zero diesel units/output. Demand compute trace remains a1483fdf5ef04fc06dcf549c3d9d5dd52ba66fc8b8cef7380bad4cee750d03df. These are deliberately different modeled supply inputs from the historical raw study, not dispatch/cost/frequency edits.
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

## 2c.6 — FINISHED after the explicitly approved TC156 update
The earlier STOP was at tests/test_addendum_h_phase2b_stage1.py:477, a frozen expanded-input hash. The original suite capture also failed in its scratch collector; neither partial/capture-error run is used as the final suite result.
Before editing, finish_gate.py loaded each saved pre-D9c expansion and a fresh current _expanded_spec (build-only, no H simulations). Old hashes matched all four frozen TC156 values. The ONLY diff for every H input is diesel_power_block.delta_t_start_s 3600.0 -> 10.0.
```json
[
  {
    "scenario": "scenario-h1-k8s-ray-24h",
    "diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "old_expansion_sha256": "f2465233ab677c0c9305b139fcc6ccd8b675aeea4df6ccdf46ff38a5ffe9681a",
    "new_expansion_sha256": "327835d3b1305e731c4397a19a772a877458ec4954b3406474f38f4e1ba0b050"
  },
  {
    "scenario": "scenario-h1-k8s-ray-7d",
    "diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "old_expansion_sha256": "a552b3916c7e8637265918e8624c6dee82483e91213066d917c59797562d56db",
    "new_expansion_sha256": "d8472fe04f6d2fe7be231e103b76bc70bb6798feabdc8ca7d3846200dc074c2a"
  },
  {
    "scenario": "scenario-h2-slurm-24h",
    "diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "old_expansion_sha256": "fc26c77f0ac3ea2f6fd6c519874ced0418792e73dcf22d3d9e7dd81e32a786ca",
    "new_expansion_sha256": "b20b073ccb60e1167601175ac3da8a25615398f1847fadeadc59b269d2a55bcb"
  },
  {
    "scenario": "scenario-h2-slurm-7d",
    "diff": [
      {
        "path": "$.diesel_power_block.delta_t_start_s",
        "before": 3600.0,
        "after": 10.0
      }
    ],
    "old_expansion_sha256": "a2a2c1d565e77129e615c008f1c30e382f1975d44224983454f51668fd2e3187",
    "new_expansion_sha256": "46100ac7301ee7f375c5e4b510ce76242a306a09d69f4a81802f31a9982088bb"
  }
]
```
TC156 edit: ONLY four frozen hash strings plus the requested D9c / tools/dr_isl/H_IDENTITY_MAP_D9c.md comment. The test body and all other file contents are unchanged relative to 52568e3. The new comment shifts the unchanged assertion from line 477 to 478.
Complete real-package suite command:
```sh
PYTHONDONTWRITEBYTECODE=1 python -m pytest tests -q --tb=short -p no:cacheprovider --basetemp=/tmp/DR-ISL-phase2c/pytest-finish --junitxml=/tmp/DR-ISL-phase2c/full-suite-finish.xml
```
Literal terminal summary, JUnit counts and failure-set comparison against Phase 2b's 15 pre-existing nodes:
```json
{
  "terminal_summary": "15 failed, 2142 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 883.17s (0:14:43)",
  "junit_testsuites": [
    {
      "name": "pytest",
      "errors": "0",
      "failures": "15",
      "skipped": "26",
      "tests": "2186",
      "time": "883.136",
      "timestamp": "2026-10-21T15:57:43.215079+00:00",
      "hostname": "repl"
    }
  ],
  "failed_count": 15,
  "added": [],
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
  ]
}
```
JUnit XML: T/full-suite-finish.xml. Full stdout: T/full-suite-finish.log. Failing IDs: T/full-suite-finish.failing_tests.txt and tools/dr_isl/PHASE_2C_FAILING_TESTS.txt. The terminal summary is authoritative for pytest passed/xfail/subtest counts; JUnit records xfails as skipped.
Complete remaining failing node IDs:
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
## 2c.7 — implementation and integrity
D8/D9b/D9c implementation was committed by automatic checkpoint 52568e322aad56ee4c42800cc0a8c64b3fd17bf5, message 'Implement runtime build warnings and add new simulation test suite', rather than the requested implementation message. Its nine application/test/scenario files are shown below; the checkpoint also contains .agents/agent_assets_metadata.toml. TC156-only commit: ed7da7011b6b9f3348e035d8fa1e2afa9b6f8daa, exact requested message 'D9c: refresh frozen H expansion hashes (delta_t_start_s only)'.
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

Report outputs: T/PHASE_2C_REPORT.md; tools/dr_isl/PHASE_2C_REPORT.md; tools/dr_isl/H_IDENTITY_MAP_D9c.md. Previous STOP report preserved as above. Raw JSON metrics/records/compact streams and suite logs are in T only. The prior report/map/STOP preservation was committed in fc61092120e7c49055699426a99d59469d9c6756. This completion report and durable failing-ID list are committed separately from the TC156-only change.

### TC156-only literal diff
```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py
index e4d09c5..a27c166 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_addendum_h_phase2b_stage1.py
@@ -440,0 +441 @@ def test_tc151_attributable_curtailment_fuel_stays_within_curve_range() -> None:
+# DR-2026-10-20-ISLAND-COLLAPSE D9c: timing-only refresh; tools/dr_isl/H_IDENTITY_MAP_D9c.md.
@@ -443 +444 @@ H_EXPANSION_SHA256_BASELINE = {
-        "f2465233ab677c0c9305b139fcc6ccd8b675aeea4df6ccdf46ff38a5ffe9681a"
+        "327835d3b1305e731c4397a19a772a877458ec4954b3406474f38f4e1ba0b050"
@@ -446 +447 @@ H_EXPANSION_SHA256_BASELINE = {
-        "a552b3916c7e8637265918e8624c6dee82483e91213066d917c59797562d56db"
+        "d8472fe04f6d2fe7be231e103b76bc70bb6798feabdc8ca7d3846200dc074c2a"
@@ -449 +450 @@ H_EXPANSION_SHA256_BASELINE = {
-        "fc26c77f0ac3ea2f6fd6c519874ced0418792e73dcf22d3d9e7dd81e32a786ca"
+        "b20b073ccb60e1167601175ac3da8a25615398f1847fadeadc59b269d2a55bcb"
@@ -452 +453 @@ H_EXPANSION_SHA256_BASELINE = {
-        "a2a2c1d565e77129e615c008f1c30e382f1975d44224983454f51668fd2e3187"
+        "46100ac7301ee7f375c5e4b510ce76242a306a09d69f4a81802f31a9982088bb"
```

## 2c.8 — READ-ONLY diesel diagnosis (no fix)
Fresh actual StudyRunExecutor._probe + _run_mode, seed=42, reuse_cache=False, no parameter overrides. Fabric/Python/NumPy pin 1729 and wall clock 1792454400.0 match the earlier Phase 2c study checks. Observers wrap and delegate existing methods in memory; no application code/config/parameter was edited. Per-arm ALL 27 metric fields, and diesel output/BESS SoC at every one of 1440 ticks, exactly match the saved Phase 2c runs.
Evidence: T/diesel-diagnosis/{baseline,informed}.trace.json, .events.json, .record.json, .all-ticks.csv and .operation-ticks.csv; T/diesel-diagnosis/summary.json; observer source T/diesel_diagnosis.py.
Time convention: tables use TickResult tick-index and interval-END sim_time; the unit/coordinator decision occurs at the interval start, five seconds earlier (P/runtime/run_manager.py:1841–1844). Both clocks are printed; do not shift one silently.

### Start/stop trigger and controller scope
P/core/simulation_core.py:1941–1970 arbitrates GT+BESS BEFORE diesel, then computes gap=max(0, p_dispatch_required_mw - turbine_output_mw - bess_output_mw - fuel_cell_output_mw). Diesel receives this gap, not SoC, frequency, a forecast, authority_tier or a demand-step threshold.
P/core/diesel_fleet.py:203–214 accumulates positive-gap duration; a new episode starts when gap>0, positive_gap_s>=debounce_s, and no fleet cooldown. In these starts the previous accumulator is 0, dt=5 s, debounce=1 s, cooldown=NaN, primary offset=0, can_start=True, p_start=1.0.
P/core/diesel_fleet.py:255–272 chooses unattempted primary units whose offset is due and calls command_start. P/core/asset_modules.py:1421–1445 accepts OFFLINE units and sets STARTING with ten seconds countdown; :1453–1466 synchronises when the countdown reaches zero.
Restoration: P/core/diesel_fleet.py:229–240 / :328–335 attempts command_stop at gap=0. P/core/asset_modules.py:1517–1531 refuses until sim_time-run_start_s>=min_run_s; then enters UNLOADING. Configured min_run_s=900.0, restore_hold_s=300.0, cooldown_s=300.0.
This is not a direct low-SoC or under-frequency start trigger. Frequency may affect upstream turbine/BESS decisions, but it is not an input to DieselFleetCoordinator.step.
P/runtime/turbine_commitment.py:181,809,912,989–1006,1089–1094 controls/enqueues TURBINE targets and commands. Literal search for 'diesel' in that controller returns zero matches. It has no diesel-specific forecast target/start/stop command; it can INDIRECTLY change diesel starts by changing the GT output in the residual gap. The shared context contains diesel objects, but this controller does not read them explicitly.
P/api/schemas.py:696–701,728–732,754–756 says authority_tier=advisory_only is metadata, not the EDL execution tier. P/core/diesel_fleet.py:180–245 has no authority-tier gate; it physically simulates automatic backup. Diesel is not an EDL/merit-order source, per :696–701. This distinction is deliberate, not evidence of a forbidden GridSignal real-world diesel command.

### Every accepted start/stop and state transition
| Arm | Tick | Tick-end s | Decision s | Method / transition | Gap MW | Run elapsed s | Restore timer before step s |
|---|---:|---:|---:|---|---:|---:|---:|
| baseline | 66 | 330.0 | 325.0 | command_start: offline → starting | 9.301943799295508 | 'not running' | 0.0 |
| baseline | 68 | 340.0 | 335.0 | advance: starting → synchronised | 35.31675134370708 | 'not running' | 0.0 |
| baseline | 248 | 1240.0 | 1235.0 | command_stop: synchronised → unloading | 0.0 | 900.0 | 480.0 |
| baseline | 248 | 1240.0 | 1235.0 | complete_unloading: unloading → offline | 0.0 | 900.0 | 480.0 |
| baseline | 371 | 1855.0 | 1850.0 | command_start: offline → starting | 27.5 | 'not running' | 0.0 |
| baseline | 373 | 1865.0 | 1860.0 | advance: starting → synchronised | 17.5 | 'not running' | 0.0 |
| baseline | 553 | 2765.0 | 2760.0 | command_stop: synchronised → unloading | 0.0 | 900.0 | 50.0 |
| baseline | 602 | 3010.0 | 3005.0 | complete_unloading: unloading → offline | 0.0 | 1145.0 | 295.0 |
| informed | 68 | 340.0 | 335.0 | command_start: offline → starting | 7.394482447512267 | 'not running' | 0.0 |
| informed | 70 | 350.0 | 345.0 | advance: starting → synchronised | 4.190655292965744 | 'not running' | 0.0 |
| informed | 250 | 1250.0 | 1245.0 | command_stop: synchronised → unloading | 0.0 | 900.0 | 815.0 |
| informed | 250 | 1250.0 | 1245.0 | complete_unloading: unloading → offline | 0.0 | 900.0 | 815.0 |
| informed | 371 | 1855.0 | 1850.0 | command_start: offline → starting | 4.628919357798523 | 'not running' | 0.0 |
| informed | 373 | 1865.0 | 1860.0 | advance: starting → synchronised | 0.0 | 'not running' | 0.0 |
| informed | 553 | 2765.0 | 2760.0 | command_stop: synchronised → unloading | 0.0 | 900.0 | 900.0 |
| informed | 553 | 2765.0 | 2760.0 | complete_unloading: unloading → offline | 0.0 | 900.0 | 900.0 |
Deciding methods/callers: command_start at P/core/diesel_fleet.py:269; advance at :199 and P/core/asset_modules.py:1453–1466; command_stop at P/core/diesel_fleet.py:331 and P/core/asset_modules.py:1522–1530; complete_unloading at P/core/diesel_fleet.py:335 and P/core/asset_modules.py:1542–1552.
These rows include same-tick SYNCHRONISED→UNLOADING→OFFLINE transitions; they are not collapsed into one row.

### Minimum-run refusals and every operating tick
Both configurations: one 20 MW unit, f_block=1.0, residual ramp=60.0 s, nominal minimum stable load=6.0 MW. P/core/asset_modules.py:1464–1466 starts at rated*f_block=20 MW; :1487–1498 ramps the remainder (zero here) to rated, not to residual demand. The 6 MW field is not used in these output equations.
Yes: minimum run time forces output even after the primary-source residual is zero. Conventional has 296 stop refusals / 296 positive-output zero-gap ticks; informed has 355 / 355. Full refusal return strings and triggering snapshots are in the events JSON; first/last are printed below.
```json
{
  "baseline": {
    "stop_refusal_count": 296,
    "first_stop_refusal": {
      "method": "command_stop",
      "unit": "diesel-000",
      "args": [
        610.0
      ],
      "before": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 335.0,
        "time_to_online_s": 0.0,
        "min_run_s": 900.0,
        "can_start": false
      },
      "after": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 335.0,
        "time_to_online_s": 0.0
      },
      "return_value": "diesel_min_run_not_elapsed:625.000s",
      "caller": "core/diesel_fleet.py:331",
      "tick": 123,
      "sim_time": 615.0,
      "coordinator": {
        "gap_mw": 0.0,
        "decision_sim_time": 610.0,
        "dt": 5.0,
        "positive_gap_s": 285.0,
        "restore_elapsed_s": 0.0,
        "debounce_s": 1.0,
        "restore_hold_s": 300.0,
        "episode": "diesel-episode-1",
        "fleet_state": "sustaining",
        "units": [
          {
            "id": "diesel-000",
            "state": "synchronised",
            "output_mw": 20.0,
            "is_on_bus": true,
            "run_start_s": 335.0,
            "time_to_online_s": 0.0,
            "min_run_s": 900.0,
            "start_attempted": true
          }
        ],
        "core_inputs": {
          "p_dispatch_required_mw": 22.23390814333261,
          "turbine_output_mw": 67.5,
          "bess_output_mw": -30.0,
          "fuel_cell_output_mw": 0.0,
          "_bess_soc_floors_mwh": [
            1.4583333333333333
          ],
          "_emergency_release_authorized": false
        }
      }
    },
    "last_stop_refusal": {
      "method": "command_stop",
      "unit": "diesel-000",
      "args": [
        2755.0
      ],
      "before": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 1860.0,
        "time_to_online_s": 0.0,
        "min_run_s": 900.0,
        "can_start": false
      },
      "after": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 1860.0,
        "time_to_online_s": 0.0
      },
      "return_value": "diesel_min_run_not_elapsed:5.000s",
      "caller": "core/diesel_fleet.py:331",
      "tick": 552,
      "sim_time": 2760.0,
      "coordinator": {
        "gap_mw": 0.0,
        "decision_sim_time": 2755.0,
        "dt": 5.0,
        "positive_gap_s": 0.0,
        "restore_elapsed_s": 45.0,
        "debounce_s": 1.0,
        "restore_hold_s": 300.0,
        "episode": "diesel-episode-2",
        "fleet_state": "sustaining",
        "units": [
          {
            "id": "diesel-000",
            "state": "synchronised",
            "output_mw": 20.0,
            "is_on_bus": true,
            "run_start_s": 1860.0,
            "time_to_online_s": 0.0,
            "min_run_s": 900.0,
            "start_attempted": true
          }
        ],
        "core_inputs": {
          "p_dispatch_required_mw": 70.46518687838166,
          "turbine_output_mw": 41.46518687838166,
          "bess_output_mw": 29.0,
          "fuel_cell_output_mw": 0.0,
          "_bess_soc_floors_mwh": [
            1.4583333333333333
          ],
          "_emergency_release_authorized": false
        }
      }
    }
  },
  "informed": {
    "stop_refusal_count": 355,
    "first_stop_refusal": {
      "method": "command_stop",
      "unit": "diesel-000",
      "args": [
        355.0
      ],
      "before": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 345.0,
        "time_to_online_s": 0.0,
        "min_run_s": 900.0,
        "can_start": false
      },
      "after": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 345.0,
        "time_to_online_s": 0.0
      },
      "return_value": "diesel_min_run_not_elapsed:890.000s",
      "caller": "core/diesel_fleet.py:331",
      "tick": 72,
      "sim_time": 360.0,
      "coordinator": {
        "gap_mw": 0.0,
        "decision_sim_time": 355.0,
        "dt": 5.0,
        "positive_gap_s": 20.0,
        "restore_elapsed_s": 0.0,
        "debounce_s": 1.0,
        "restore_hold_s": 300.0,
        "episode": "diesel-episode-1",
        "fleet_state": "sustaining",
        "units": [
          {
            "id": "diesel-000",
            "state": "synchronised",
            "output_mw": 20.0,
            "is_on_bus": true,
            "run_start_s": 345.0,
            "time_to_online_s": 0.0,
            "min_run_s": 900.0,
            "start_attempted": true
          }
        ],
        "core_inputs": {
          "p_dispatch_required_mw": 104.2209909582013,
          "turbine_output_mw": 75.2209909582013,
          "bess_output_mw": 29.0,
          "fuel_cell_output_mw": 0.0,
          "_bess_soc_floors_mwh": [
            1.4583333333333333
          ],
          "_emergency_release_authorized": false
        }
      }
    },
    "last_stop_refusal": {
      "method": "command_stop",
      "unit": "diesel-000",
      "args": [
        2755.0
      ],
      "before": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 1860.0,
        "time_to_online_s": 0.0,
        "min_run_s": 900.0,
        "can_start": false
      },
      "after": {
        "state": "synchronised",
        "output_mw": 20.0,
        "run_start_s": 1860.0,
        "time_to_online_s": 0.0
      },
      "return_value": "diesel_min_run_not_elapsed:5.000s",
      "caller": "core/diesel_fleet.py:331",
      "tick": 552,
      "sim_time": 2760.0,
      "coordinator": {
        "gap_mw": 0.0,
        "decision_sim_time": 2755.0,
        "dt": 5.0,
        "positive_gap_s": 0.0,
        "restore_elapsed_s": 895.0,
        "debounce_s": 1.0,
        "restore_hold_s": 300.0,
        "episode": "diesel-episode-2",
        "fleet_state": "sustaining",
        "units": [
          {
            "id": "diesel-000",
            "state": "synchronised",
            "output_mw": 20.0,
            "is_on_bus": true,
            "run_start_s": 1860.0,
            "time_to_online_s": 0.0,
            "min_run_s": 900.0,
            "start_attempted": true
          }
        ],
        "core_inputs": {
          "p_dispatch_required_mw": 70.46518687838166,
          "turbine_output_mw": 61.25,
          "bess_output_mw": 9.215186878381658,
          "fuel_cell_output_mw": 0.0,
          "_bess_soc_floors_mwh": [
            1.4583333333333333
          ],
          "_emergency_release_authorized": false
        }
      }
    }
  }
}
```
CSV sign convention: BESS positive=discharge, negative=charge. demand=compute+cooling (base-demo other load is zero); floor is the resolved floor and applied_floor is the per-tick floor supplied to arbitration. Both are 1.4583333333333333 MWh in these operating rows.
All 1440 rows per arm are saved to .all-ticks.csv. The complete operation table below includes STARTING/SYNCHRONISED/UNLOADING rows and the transition-to-OFFLINE rows, not only positive fleet output.

#### baseline: 415 operating/transition rows
| tick | sim_time | decision_sim_time | demand_mw | turbine_mw | bess_mw | diesel_mw | curtailment_mw | unserved_mw | soc | floor_mwh | applied_floor_mwh | unit_state | unit_output_mw | gap_before_diesel_mw |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 66 | 330.0 | 325.0 | 58.30194379929551 | 20.0 | 29.0 | 0.0 | 0.0 | 9.301943799295508 | 0.921313970842702 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 9.301943799295508 |
| 67 | 335.0 | 330.0 | 76.30936246553462 | 25.0 | 29.0 | 0.0 | 0.0 | 22.30936246553462 | 0.9206129521747906 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 22.30936246553462 |
| 68 | 340.0 | 335.0 | 94.31675134370708 | 30.0 | 29.0 | 20.0 | 0.0 | 15.316751343707082 | 0.9199119335068792 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 35.31675134370708 |
| 69 | 345.0 | 340.0 | 100.88615700068769 | 35.0 | 29.0 | 20.0 | 0.0 | 16.88615700068769 | 0.9192109148389677 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 36.88615700068769 |
| 70 | 350.0 | 345.0 | 102.55356172362593 | 40.0 | 29.0 | 20.0 | 0.0 | 13.553561723625933 | 0.9185098961710563 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 33.55356172362593 |
| 71 | 355.0 | 350.0 | 104.22095237567783 | 45.0 | 29.0 | 20.0 | 0.0 | 10.220952375677825 | 0.9178088775031449 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 30.220952375677825 |
| 72 | 360.0 | 355.0 | 104.2209909582013 | 48.75 | 29.0 | 20.0 | 0.0 | 6.470990958201298 | 0.9171078588352335 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 26.4709909582013 |
| 73 | 365.0 | 360.0 | 104.22102100630079 | 50.0 | 29.0 | 20.0 | 0.0 | 5.221021006300788 | 0.9164068401673221 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.221021006300788 |
| 74 | 370.0 | 365.0 | 104.22104440778422 | 50.0 | 29.0 | 20.0 | 0.0 | 5.22104440778422 | 0.9157058214994106 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.22104440778422 |
| 75 | 375.0 | 370.0 | 104.22450750100259 | 50.0 | 29.0 | 20.0 | 0.0 | 5.224507501002591 | 0.9150048028314992 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.22450750100259 |
| 76 | 380.0 | 375.0 | 104.24082174764156 | 50.0 | 29.0 | 20.0 | 0.0 | 5.2408217476415615 | 0.9143037841635878 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.24082174764156 |
| 77 | 385.0 | 380.0 | 104.26582570961276 | 50.0 | 29.0 | 20.0 | 0.0 | 5.265825709612756 | 0.9136027654956764 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.265825709612756 |
| 78 | 390.0 | 385.0 | 104.29657016723249 | 50.0 | 29.0 | 20.0 | 0.0 | 5.296570167232488 | 0.912901746827765 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.29657016723249 |
| 79 | 395.0 | 390.0 | 104.3309854510916 | 50.0 | 29.0 | 20.0 | 0.0 | 5.330985451091607 | 0.9122007281598535 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.330985451091607 |
| 80 | 400.0 | 395.0 | 104.35055910041487 | 50.0 | 29.0 | 20.0 | 0.0 | 5.35055910041487 | 0.9114997094919421 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.35055910041487 |
| 81 | 405.0 | 400.0 | 104.36143504370831 | 50.0 | 29.0 | 20.0 | 0.0 | 5.361435043708312 | 0.9107986908240308 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.361435043708312 |
| 82 | 410.0 | 405.0 | 104.72922497279784 | 50.0 | 29.0 | 20.0 | 0.0 | 5.729224972797837 | 0.9100976721561194 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 25.729224972797837 |
| 83 | 415.0 | 410.0 | 106.43066093930186 | 50.0 | 29.0 | 20.0 | 0.0 | 7.430660939301859 | 0.909396653488208 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 27.43066093930186 |
| 84 | 420.0 | 415.0 | 109.03556626169207 | 50.0 | 29.0 | 20.0 | 0.0 | 10.035566261692068 | 0.9086956348202965 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 30.03556626169207 |
| 85 | 425.0 | 420.0 | 112.23721380903318 | 50.0 | 29.0 | 20.0 | 0.0 | 13.237213809033179 | 0.9079946161523851 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 33.23721380903318 |
| 86 | 430.0 | 425.0 | 115.32868714840941 | 52.5 | 29.0 | 20.0 | 0.0 | 13.828687148409415 | 0.9072935974844737 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 33.828687148409415 |
| 87 | 435.0 | 430.0 | 117.36696777185412 | 55.0 | 29.0 | 20.0 | 0.0 | 13.36696777185412 | 0.9065925788165623 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 33.36696777185412 |
| 88 | 440.0 | 435.0 | 118.49982638236047 | 57.5 | 29.0 | 20.0 | 0.0 | 11.999826382360467 | 0.9058915601486509 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 31.999826382360467 |
| 89 | 445.0 | 440.0 | 119.46867853664423 | 60.0 | 29.0 | 20.0 | 0.0 | 10.468678536644234 | 0.9051905414807394 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 30.468678536644234 |
| 90 | 450.0 | 445.0 | 120.00864605678962 | 62.5 | 29.0 | 20.0 | 0.0 | 8.508646056789615 | 0.904489522812828 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 28.508646056789615 |
| 91 | 455.0 | 450.0 | 120.42917318431195 | 65.0 | 29.0 | 20.0 | 0.0 | 6.429173184311949 | 0.9037885041449166 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 26.42917318431195 |
| 92 | 460.0 | 455.0 | 120.75668004052912 | 67.5 | 29.0 | 20.0 | 0.0 | 4.256680040529119 | 0.9030874854770052 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 24.25668004052912 |
| 93 | 465.0 | 460.0 | 120.72597944909326 | 70.0 | 29.0 | 20.0 | 0.0 | 1.7259794490932592 | 0.9023864668090938 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 21.72597944909326 |
| 94 | 470.0 | 465.0 | 111.92098068618853 | 72.5 | 29.0 | 20.0 | 9.579019313811472 | 0.0 | 0.9016854481411823 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 10.420980686188528 |
| 95 | 475.0 | 470.0 | 112.07568390449592 | 75.0 | 29.0 | 20.0 | 11.924316095504082 | 0.0 | 0.900984429473271 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.075683904495918 |
| 96 | 480.0 | 475.0 | 112.19616689205739 | 75.0 | 29.0 | 20.0 | 11.803833107942609 | 0.0 | 0.9002834108053596 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.196166892057391 |
| 97 | 485.0 | 480.0 | 112.11349833810593 | 75.0 | 29.0 | 20.0 | 11.886501661894073 | 0.0 | 0.8995823921374482 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.113498338105927 |
| 98 | 490.0 | 485.0 | 112.186574963817 | 75.0 | 29.0 | 20.0 | 11.813425036183006 | 0.0 | 0.8988813734695368 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.186574963816994 |
| 99 | 495.0 | 490.0 | 112.24348709714499 | 75.0 | 29.0 | 20.0 | 11.756512902855007 | 0.0 | 0.8981803548016253 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.243487097144993 |
| 100 | 500.0 | 495.0 | 112.2878103111471 | 75.0 | 29.0 | 20.0 | 11.712189688852902 | 0.0 | 0.8974793361337139 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.287810311147098 |
| 101 | 505.0 | 500.0 | 112.32232926492017 | 75.0 | 29.0 | 20.0 | 11.677670735079829 | 0.0 | 0.8967783174658025 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.322329264920171 |
| 102 | 510.0 | 505.0 | 112.34921265314945 | 75.0 | 29.0 | 20.0 | 11.65078734685055 | 0.0 | 0.8960772987978911 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.34921265314945 |
| 103 | 515.0 | 510.0 | 112.37014945695402 | 75.0 | 29.0 | 20.0 | 11.629850543045976 | 0.0 | 0.8953762801299797 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.370149456954024 |
| 104 | 520.0 | 515.0 | 112.21351076187145 | 75.0 | 29.0 | 20.0 | 11.786489238128553 | 0.0 | 0.8946752614620682 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.213510761871447 |
| 105 | 525.0 | 520.0 | 112.22618840526512 | 75.0 | 29.0 | 20.0 | 11.77381159473488 | 0.0 | 0.8939742427941568 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.22618840526512 |
| 106 | 530.0 | 525.0 | 112.23606176386762 | 75.0 | 29.0 | 20.0 | 11.763938236132375 | 0.0 | 0.8932732241262454 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.236061763867625 |
| 107 | 535.0 | 530.0 | 112.24375114327879 | 75.0 | 29.0 | 20.0 | 11.756248856721214 | 0.0 | 0.892572205458334 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.243751143278786 |
| 108 | 540.0 | 535.0 | 112.24973963798553 | 75.0 | 29.0 | 20.0 | 11.750260362014473 | 0.0 | 0.8918711867904227 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.249739637985527 |
| 109 | 545.0 | 540.0 | 112.25440348235257 | 75.0 | 29.0 | 20.0 | 11.745596517647428 | 0.0 | 0.8911701681225112 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.254403482352572 |
| 110 | 550.0 | 545.0 | 112.25803568799775 | 75.0 | 29.0 | 20.0 | 11.741964312002253 | 0.0 | 0.8904691494545998 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.258035687997747 |
| 111 | 555.0 | 550.0 | 112.26086445259848 | 75.0 | 29.0 | 20.0 | 11.739135547401517 | 0.0 | 0.8897681307866884 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.260864452598483 |
| 112 | 560.0 | 555.0 | 112.26306749668466 | 75.0 | 29.0 | 20.0 | 11.736932503315344 | 0.0 | 0.889067112118777 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.263067496684656 |
| 113 | 565.0 | 560.0 | 112.26478322914411 | 75.0 | 29.0 | 20.0 | 11.735216770855885 | 0.0 | 0.8883660934508656 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.264783229144115 |
| 114 | 570.0 | 565.0 | 112.26611944292708 | 75.0 | 29.0 | 20.0 | 11.733880557072922 | 0.0 | 0.8876650747829541 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.266119442927078 |
| 115 | 575.0 | 570.0 | 112.2671600872676 | 75.0 | 29.0 | 20.0 | 11.732839912732402 | 0.0 | 0.8869640561150427 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.267160087267598 |
| 116 | 580.0 | 575.0 | 112.2679705418949 | 75.0 | 29.0 | 20.0 | 11.732029458105103 | 0.0 | 0.8862630374471313 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.267970541894897 |
| 117 | 585.0 | 580.0 | 112.26860172459328 | 75.0 | 29.0 | 20.0 | 11.731398275406718 | 0.0 | 0.8855620187792199 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.268601724593282 |
| 118 | 590.0 | 585.0 | 112.26909329017305 | 75.0 | 29.0 | 20.0 | 11.730906709826954 | 0.0 | 0.8848610001113085 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.269093290173046 |
| 119 | 595.0 | 590.0 | 112.2694761218315 | 75.0 | 29.0 | 20.0 | 11.730523878168498 | 0.0 | 0.884159981443397 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.269476121831502 |
| 120 | 600.0 | 595.0 | 112.26977427142688 | 75.0 | 29.0 | 20.0 | 11.730225728573117 | 0.0 | 0.8834589627754856 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.269774271426883 |
| 121 | 605.0 | 600.0 | 112.27000647056525 | 75.0 | 29.0 | 20.0 | 11.72999352943475 | 0.0 | 0.8827579441075742 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.27000647056525 |
| 122 | 610.0 | 605.0 | 112.27018730743602 | 75.0 | 29.0 | 20.0 | 11.729812692563982 | 0.0 | 0.8820569254396629 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 8.270187307436018 |
| 123 | 615.0 | 610.0 | 22.23390814333261 | 67.5 | -30.0 | 20.0 | 35.26609185666739 | 0.0 | 0.8827219262518781 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 124 | 620.0 | 615.0 | 22.23401782643914 | 60.0 | -30.0 | 20.0 | 27.76598217356086 | 0.0 | 0.8833869270640932 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 125 | 625.0 | 620.0 | 22.234103247728402 | 52.5 | -30.0 | 20.0 | 20.265896752271598 | 0.0 | 0.8840519278763084 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 126 | 630.0 | 625.0 | 22.23416977389537 | 45.0 | -22.76583022610463 | 20.0 | 20.000000000000004 | 0.0 | 0.8845565710626787 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 127 | 635.0 | 630.0 | 22.2342215845263 | 37.5 | -15.2657784154737 | 20.0 | 19.999999999999996 | 0.0 | 0.884894962897525 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 128 | 640.0 | 635.0 | 22.234261934686238 | 30.0 | -7.765738065313762 | 20.0 | 20.0 | 0.0 | 0.8850671036348879 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 129 | 645.0 | 640.0 | 22.23429335942239 | 26.25 | -4.0157066405776085 | 20.0 | 20.000000000000004 | 0.0 | 0.8851561185741413 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 130 | 650.0 | 645.0 | 22.234317833031522 | 26.25 | -4.015682166968478 | 20.0 | 20.000000000000004 | 0.0 | 0.8852451329708958 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 131 | 655.0 | 650.0 | 22.234336893097474 | 26.25 | -4.015663106902526 | 20.0 | 20.000000000000004 | 0.0 | 0.8853341469451516 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 132 | 660.0 | 655.0 | 22.234351737091764 | 26.25 | -4.015648262908236 | 20.0 | 20.0 | 0.0 | 0.8854231605903651 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 133 | 665.0 | 660.0 | 22.23436329760614 | 26.25 | -4.015636702393859 | 20.0 | 19.999999999999996 | 0.0 | 0.8855121739793201 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 134 | 670.0 | 665.0 | 22.23437230094379 | 26.25 | -4.0156276990562105 | 20.0 | 20.0 | 0.0 | 0.8856011871687011 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 135 | 675.0 | 670.0 | 22.2343793127502 | 26.25 | -4.0156206872498 | 20.0 | 20.0 | 0.0 | 0.8856902002026533 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 136 | 680.0 | 675.0 | 22.234384773550527 | 26.25 | -4.015615226449473 | 20.0 | 20.000000000000004 | 0.0 | 0.8857792131155579 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 137 | 685.0 | 680.0 | 22.234389026426093 | 26.25 | -4.0156109735739065 | 20.0 | 20.0 | 0.0 | 0.8858682259341901 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 138 | 690.0 | 685.0 | 22.234392338568917 | 26.25 | -4.015607661431083 | 20.0 | 20.0 | 0.0 | 0.885957238679403 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 139 | 695.0 | 690.0 | 22.234394918068343 | 26.25 | -4.015605081931657 | 20.0 | 20.000000000000004 | 0.0 | 0.8860462513674371 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 140 | 700.0 | 695.0 | 22.234396926984513 | 26.25 | -4.0156030730154875 | 20.0 | 20.000000000000004 | 0.0 | 0.8861352640109401 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 141 | 705.0 | 700.0 | 22.23439849153 | 26.25 | -4.015601508469999 | 20.0 | 20.0 | 0.0 | 0.8862242766197622 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 142 | 710.0 | 705.0 | 22.305607043332586 | 26.25 | -3.9443929566674143 | 20.0 | 20.0 | 0.0 | 0.8863117107704249 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 143 | 715.0 | 710.0 | 22.706750418944058 | 26.25 | -3.5432495810559423 | 20.0 | 19.999999999999996 | 0.0 | 0.8863902528987343 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 144 | 720.0 | 715.0 | 23.760713077983013 | 26.25 | -2.489286922016987 | 20.0 | 20.0 | 0.0 | 0.886445432159567 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 145 | 725.0 | 720.0 | 26.01320005354713 | 26.25 | -0.2367999464528694 | 20.0 | 20.0 | 0.0 | 0.8864506812314576 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 146 | 730.0 | 725.0 | 28.35148590179692 | 26.25 | 2.10148590179692 | 20.0 | 20.0 | 0.0 | 0.8863998818918883 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 147 | 735.0 | 730.0 | 30.796162410894212 | 26.25 | 4.546162410894212 | 20.0 | 20.0 | 0.0 | 0.8862899872464609 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 148 | 740.0 | 735.0 | 33.34074701166033 | 26.25 | 7.0907470116603335 | 20.0 | 20.0 | 0.0 | 0.8861185822111295 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 149 | 745.0 | 740.0 | 34.6406740589541 | 28.75 | 0.0 | 20.0 | 14.109325941045903 | 0.0 | 0.8861185822111295 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 5.890674058954097 |
| 150 | 750.0 | 745.0 | 35.46699057941153 | 31.25 | 0.46699057941152944 | 20.0 | 16.25 | 0.0 | 0.8861072936209948 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 3.75 |
| 151 | 755.0 | 750.0 | 36.24583550783724 | 33.75 | 1.245835507837242 | 20.0 | 18.75 | 0.0 | 0.8860771779676107 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 1.25 |
| 152 | 760.0 | 755.0 | 36.47120098118863 | 35.0 | 1.4712009811886304 | 20.0 | 20.0 | 0.0 | 0.8860416145416774 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 153 | 765.0 | 760.0 | 36.528400392416096 | 35.0 | 1.5284003924160956 | 20.0 | 20.0 | 0.0 | 0.8860046684310868 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 154 | 770.0 | 765.0 | 36.58559978641344 | 35.0 | 1.5855997864134395 | 20.0 | 20.0 | 0.0 | 0.8859663396362554 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 155 | 775.0 | 770.0 | 36.58559983365862 | 35.0 | 1.5855998336586197 | 20.0 | 20.0 | 0.0 | 0.8859280108402818 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 156 | 780.0 | 775.0 | 36.585599870453194 | 35.0 | 1.5855998704531942 | 20.0 | 20.0 | 0.0 | 0.885889682043419 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 157 | 785.0 | 780.0 | 36.58559989910885 | 35.0 | 1.5855998991088498 | 20.0 | 20.0 | 0.0 | 0.8858513532458633 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 158 | 790.0 | 785.0 | 36.585599921425896 | 35.0 | 1.5855999214258958 | 20.0 | 20.0 | 0.0 | 0.8858130244477682 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 159 | 795.0 | 790.0 | 36.585599938806425 | 35.0 | 1.5855999388064248 | 20.0 | 20.0 | 0.0 | 0.8857746956492529 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 160 | 800.0 | 795.0 | 36.58559995234239 | 35.0 | 1.5855999523423918 | 20.0 | 20.0 | 0.0 | 0.8857363668504105 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 161 | 805.0 | 800.0 | 36.59580661501386 | 35.0 | 1.5958066150138634 | 20.0 | 20.0 | 0.0 | 0.8856977913253241 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 162 | 810.0 | 805.0 | 18.671453068732326 | 35.0 | -16.328546931267674 | 20.0 | 20.0 | 0.0 | 0.886059741224377 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 163 | 815.0 | 810.0 | 18.909388873638115 | 35.0 | -16.090611126361885 | 20.0 | 20.0 | 0.0 | 0.8864164168733127 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 164 | 820.0 | 815.0 | 19.25174063927462 | 35.0 | -15.748259360725381 | 20.0 | 19.999999999999996 | 0.0 | 0.8867655037155079 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 165 | 825.0 | 820.0 | 19.675013527654492 | 35.0 | -15.324986472345508 | 20.0 | 20.0 | 0.0 | 0.8871052079972178 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 166 | 830.0 | 825.0 | 20.137136859027983 | 35.0 | -14.862863140972017 | 20.0 | 20.0 | 0.0 | 0.8874346685325708 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 167 | 835.0 | 830.0 | 20.455319921361365 | 35.0 | -14.544680078638635 | 20.0 | 20.0 | 0.0 | 0.8877570760014277 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 168 | 840.0 | 835.0 | 20.70190752761264 | 35.0 | -14.29809247238736 | 20.0 | 20.0 | 0.0 | 0.8880740174383366 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 169 | 845.0 | 840.0 | 20.933589173790608 | 35.0 | -14.066410826209392 | 20.0 | 20.0 | 0.0 | 0.8883858232591493 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 170 | 850.0 | 845.0 | 21.067484059913166 | 35.0 | -13.932515940086834 | 20.0 | 20.000000000000004 | 0.0 | 0.888694661073028 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 171 | 855.0 | 850.0 | 21.156167634521047 | 35.0 | -13.843832365478953 | 20.0 | 20.0 | 0.0 | 0.8890015330652684 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 172 | 860.0 | 855.0 | 21.22820469456736 | 35.0 | -13.77179530543264 | 20.0 | 20.0 | 0.0 | 0.8893068082340608 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 173 | 865.0 | 860.0 | 21.27694605381888 | 35.0 | -13.723053946181121 | 20.0 | 19.999999999999996 | 0.0 | 0.8896110029680704 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 174 | 870.0 | 865.0 | 21.314905862571926 | 35.0 | -13.685094137428074 | 20.0 | 20.0 | 0.0 | 0.8899143562586248 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 175 | 875.0 | 870.0 | 21.34446899135404 | 35.0 | -13.655531008645958 | 20.0 | 20.0 | 0.0 | 0.8902170542323574 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 176 | 880.0 | 875.0 | 21.367492779199594 | 35.0 | -13.632507220800406 | 20.0 | 20.0 | 0.0 | 0.8905192418448362 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 177 | 885.0 | 880.0 | 19.69395772320298 | 35.0 | -15.306042276797019 | 20.0 | 20.000000000000004 | 0.0 | 0.8908585261963652 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 178 | 890.0 | 885.0 | 19.70792235643403 | 35.0 | -15.292077643565971 | 20.0 | 19.999999999999996 | 0.0 | 0.8911975009981462 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 179 | 895.0 | 890.0 | 19.718798023729672 | 35.0 | -15.281201976270328 | 20.0 | 20.000000000000004 | 0.0 | 0.8915362347223411 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 180 | 900.0 | 895.0 | 19.727268001935943 | 35.0 | -15.272731998064057 | 20.0 | 19.999999999999996 | 0.0 | 0.8918747806951229 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 181 | 905.0 | 900.0 | 19.733864427595584 | 35.0 | -15.266135572404416 | 20.0 | 20.0 | 0.0 | 0.8922131804469575 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 182 | 910.0 | 905.0 | 19.77110339573145 | 35.0 | -15.228896604268549 | 20.0 | 20.0 | 0.0 | 0.8925507547339903 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 183 | 915.0 | 910.0 | 19.847012063471873 | 35.0 | -15.152987936528127 | 20.0 | 20.0 | 0.0 | 0.8928866463768329 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 184 | 920.0 | 915.0 | 20.081259994321133 | 35.0 | -14.918740005678867 | 20.0 | 19.999999999999996 | 0.0 | 0.893217345517533 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 185 | 925.0 | 920.0 | 21.315223350373195 | 35.0 | -13.684776649626805 | 20.0 | 20.0 | 0.0 | 0.8935206917704325 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 186 | 930.0 | 925.0 | 23.789151711300146 | 35.0 | -11.210848288699854 | 20.0 | 20.000000000000004 | 0.0 | 0.8937691992110195 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 187 | 935.0 | 930.0 | 31.22466917281399 | 35.0 | -3.7753308271860107 | 20.0 | 20.0 | 0.0 | 0.8938528858132349 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 188 | 940.0 | 935.0 | 38.51304943749132 | 35.0 | 3.5130494374913184 | 20.0 | 20.0 | 0.0 | 0.8937679646671322 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 189 | 945.0 | 940.0 | 45.738256877737435 | 35.0 | 10.738256877737435 | 20.0 | 19.999999999999993 | 0.0 | 0.8935083881660245 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 190 | 950.0 | 945.0 | 52.96326684699795 | 35.0 | 17.963266846997954 | 20.0 | 20.0 | 0.0 | 0.8930741610833893 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 191 | 955.0 | 950.0 | 55.59153790570026 | 35.0 | 20.591537905700257 | 20.0 | 19.999999999999993 | 0.0 | 0.8925764006532894 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 192 | 960.0 | 955.0 | 56.25889604552873 | 35.0 | 21.25889604552873 | 20.0 | 20.0 | 0.0 | 0.8920625081364927 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 193 | 965.0 | 960.0 | 56.92616090666847 | 35.0 | 21.92616090666847 | 20.0 | 20.0 | 0.0 | 0.8915324857878306 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 194 | 970.0 | 965.0 | 56.92641667784794 | 35.0 | 21.92641667784794 | 20.0 | 20.0 | 0.0 | 0.8910024572563969 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 195 | 975.0 | 970.0 | 56.58846838991523 | 35.0 | 21.588468389915228 | 20.0 | 19.999999999999993 | 0.0 | 0.8904805979683644 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 196 | 980.0 | 975.0 | 53.4998272904309 | 35.0 | 18.4998272904309 | 20.0 | 20.0 | 0.0 | 0.8900334005792703 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 197 | 985.0 | 980.0 | 53.49992300544874 | 35.0 | 18.499923005448743 | 20.0 | 20.000000000000007 | 0.0 | 0.8895862008764516 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 198 | 990.0 | 985.0 | 53.49999754837959 | 35.0 | 18.49999754837959 | 20.0 | 19.999999999999993 | 0.0 | 0.8891389993717024 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 199 | 995.0 | 990.0 | 53.50005560247251 | 35.0 | 18.500055602472507 | 20.0 | 20.000000000000007 | 0.0 | 0.8886917964636082 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 200 | 1000.0 | 995.0 | 53.50010081504553 | 35.0 | 18.500100815045528 | 20.0 | 20.0 | 0.0 | 0.8882445924625879 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 201 | 1005.0 | 1000.0 | 53.504737386199444 | 35.0 | 18.504737386199444 | 20.0 | 20.000000000000007 | 0.0 | 0.8877972763814664 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 202 | 1010.0 | 1005.0 | 53.526537022556745 | 35.0 | 18.526537022556745 | 20.0 | 19.999999999999993 | 0.0 | 0.8873494333364815 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 203 | 1015.0 | 1010.0 | 52.404281763578425 | 35.0 | 17.404281763578425 | 20.0 | 20.0 | 0.0 | 0.8869287186324174 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 204 | 1020.0 | 1015.0 | 52.58874780485328 | 35.0 | 17.588747804853277 | 20.0 | 20.000000000000007 | 0.0 | 0.8865035448201282 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 205 | 1025.0 | 1020.0 | 53.31322213505521 | 35.0 | 18.313222135055213 | 20.0 | 20.0 | 0.0 | 0.8860608582481875 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 206 | 1030.0 | 1025.0 | 54.37971769496312 | 35.0 | 19.37971769496312 | 20.0 | 20.0 | 0.0 | 0.8855923912177385 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 207 | 1035.0 | 1030.0 | 55.673648928895126 | 35.0 | 20.673648928895126 | 20.0 | 19.999999999999993 | 0.0 | 0.8850926459131523 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 208 | 1040.0 | 1035.0 | 57.118357570959205 | 35.0 | 22.118357570959205 | 20.0 | 20.0 | 0.0 | 0.8845579775834701 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 209 | 1045.0 | 1040.0 | 57.93983129983981 | 35.0 | 22.93983129983981 | 20.0 | 20.0 | 0.0 | 0.8840034517220935 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 210 | 1050.0 | 1045.0 | 58.41528330910395 | 35.0 | 23.41528330910395 | 20.0 | 20.000000000000007 | 0.0 | 0.8834374327319516 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 211 | 1055.0 | 1050.0 | 58.84578369704505 | 35.0 | 23.84578369704505 | 20.0 | 20.0 | 0.0 | 0.8828610072311721 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 212 | 1060.0 | 1055.0 | 59.19075318193568 | 35.0 | 24.190753181935683 | 20.0 | 20.000000000000007 | 0.0 | 0.8822762427631937 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 213 | 1065.0 | 1060.0 | 59.48730271458086 | 35.0 | 24.487302714580863 | 20.0 | 20.0 | 0.0 | 0.8816843097863069 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 214 | 1070.0 | 1065.0 | 59.63898173914184 | 35.0 | 24.63898173914184 | 20.0 | 20.0 | 0.0 | 0.8810887102636357 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 215 | 1075.0 | 1070.0 | 59.868453547756104 | 35.0 | 24.868453547756104 | 20.0 | 20.0 | 0.0 | 0.8804875637057369 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 216 | 1080.0 | 1075.0 | 59.99497433300767 | 35.0 | 24.99497433300767 | 20.0 | 19.999999999999993 | 0.0 | 0.8798833587536196 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 217 | 1085.0 | 1080.0 | 60.06936282047397 | 35.0 | 25.06936282047397 | 20.0 | 20.0 | 0.0 | 0.8792773556043162 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 218 | 1090.0 | 1085.0 | 60.1298787649565 | 35.0 | 25.1298787649565 | 20.0 | 20.0 | 0.0 | 0.8786698895996065 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 219 | 1095.0 | 1090.0 | 60.16791742876675 | 35.0 | 25.16791742876675 | 20.0 | 19.999999999999993 | 0.0 | 0.8780615040840886 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 220 | 1100.0 | 1095.0 | 60.19754196992916 | 35.0 | 25.197541969929162 | 20.0 | 20.0 | 0.0 | 0.8774524024528334 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 221 | 1105.0 | 1100.0 | 59.989481656488394 | 35.0 | 24.989481656488394 | 20.0 | 20.0 | 0.0 | 0.8768483302755015 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 222 | 1110.0 | 1105.0 | 60.00744983334369 | 35.0 | 25.007449833343692 | 20.0 | 19.999999999999993 | 0.0 | 0.876243823752397 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 223 | 1115.0 | 1110.0 | 57.69961746354896 | 35.0 | 22.69961746354896 | 20.0 | 20.0 | 0.0 | 0.8756951045939005 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 224 | 1120.0 | 1115.0 | 57.71051571371083 | 35.0 | 22.710515713710834 | 20.0 | 20.0 | 0.0 | 0.8751461219913762 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 225 | 1125.0 | 1120.0 | 57.71900327947101 | 35.0 | 22.71900327947101 | 20.0 | 20.0 | 0.0 | 0.8745969342184365 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 226 | 1130.0 | 1125.0 | 57.725613402331405 | 35.0 | 22.725613402331405 | 20.0 | 20.0 | 0.0 | 0.8740475866586169 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 227 | 1135.0 | 1130.0 | 57.73076137119128 | 35.0 | 22.730761371191278 | 20.0 | 20.0 | 0.0 | 0.8734981146566498 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 228 | 1140.0 | 1135.0 | 57.73477061337058 | 35.0 | 22.73477061337058 | 20.0 | 20.000000000000007 | 0.0 | 0.872948545739041 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 229 | 1145.0 | 1140.0 | 57.740402846810234 | 35.0 | 22.740402846810234 | 20.0 | 20.000000000000007 | 0.0 | 0.8723988406731293 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 230 | 1150.0 | 1145.0 | 57.75471032795722 | 35.0 | 22.75471032795722 | 20.0 | 19.999999999999993 | 0.0 | 0.8718487897516529 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 231 | 1155.0 | 1150.0 | 57.77481327847242 | 35.0 | 22.774813278472422 | 20.0 | 20.0 | 0.0 | 0.8712982528803975 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 232 | 1160.0 | 1155.0 | 57.79868145743699 | 35.0 | 22.79868145743699 | 20.0 | 20.000000000000007 | 0.0 | 0.8707471390422794 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 233 | 1165.0 | 1160.0 | 57.845499232271926 | 35.0 | 22.845499232271926 | 20.0 | 19.999999999999993 | 0.0 | 0.8701948934753975 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 234 | 1170.0 | 1165.0 | 57.906794812479646 | 35.0 | 22.906794812479646 | 20.0 | 20.0 | 0.0 | 0.8696411662069298 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 235 | 1175.0 | 1170.0 | 57.55317748400848 | 35.0 | 22.55317748400848 | 20.0 | 19.999999999999993 | 0.0 | 0.8690959869504812 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 236 | 1180.0 | 1175.0 | 57.70880697440119 | 35.0 | 22.708806974401192 | 20.0 | 20.000000000000007 | 0.0 | 0.8685470456534105 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 237 | 1185.0 | 1180.0 | 57.86131733378928 | 35.0 | 22.86131733378928 | 20.0 | 20.000000000000007 | 0.0 | 0.8679944177146506 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 238 | 1190.0 | 1185.0 | 58.01290078896208 | 35.0 | 23.012900788962078 | 20.0 | 19.999999999999993 | 0.0 | 0.8674381255403107 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 239 | 1195.0 | 1190.0 | 58.0695517037395 | 35.0 | 23.0695517037395 | 20.0 | 20.000000000000007 | 0.0 | 0.8668804639401498 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 240 | 1200.0 | 1195.0 | 58.08526442269173 | 35.0 | 23.08526442269173 | 20.0 | 19.999999999999993 | 0.0 | 0.8663224225155299 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 241 | 1205.0 | 1200.0 | 58.10053930309506 | 35.0 | 23.10053930309506 | 20.0 | 20.0 | 0.0 | 0.8657640118503475 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 242 | 1210.0 | 1205.0 | 58.10173986116031 | 35.0 | 23.10173986116031 | 20.0 | 20.0 | 0.0 | 0.865205572164006 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 243 | 1215.0 | 1210.0 | 57.34624285672165 | 35.0 | 22.346242856721652 | 20.0 | 20.000000000000007 | 0.0 | 0.8646653951502045 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 244 | 1220.0 | 1215.0 | 56.685093031997 | 35.0 | 21.685093031997 | 20.0 | 20.0 | 0.0 | 0.8641412001491415 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 245 | 1225.0 | 1220.0 | 56.79159563547165 | 35.0 | 21.79159563547165 | 20.0 | 20.0 | 0.0 | 0.8636144306545195 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 246 | 1230.0 | 1225.0 | 56.47251481610179 | 35.0 | 21.472514816101793 | 20.0 | 20.0 | 0.0 | 0.8630953743188956 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 247 | 1235.0 | 1230.0 | 57.235594381746395 | 35.0 | 22.235594381746395 | 20.0 | 20.0 | 0.0 | 0.8625578720170436 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 248 | 1240.0 | 1235.0 | 57.46279186245976 | 35.0 | 22.46279186245976 | 0.0 | 0.0 | 0.0 | 0.8620148776574231 | 1.4583333333333333 | 1.4583333333333333 | offline | 0.0 | 0.0 |
| 371 | 1855.0 | 1850.0 | 98.62891935779852 | 42.12891935779852 | 29.0 | 0.0 | 0.0 | 27.5 | 0.8462315090313531 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 27.5 |
| 372 | 1860.0 | 1855.0 | 98.62893020589509 | 47.12893020589509 | 29.0 | 0.0 | 0.0 | 22.5 | 0.8455304903634417 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 22.5 |
| 373 | 1865.0 | 1860.0 | 98.33477065440118 | 51.83477065440118 | 29.0 | 20.0 | 2.5 | 0.0 | 0.8448294716955302 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 17.5 |
| 374 | 1870.0 | 1865.0 | 98.33477723410435 | 56.83477723410435 | 29.0 | 20.0 | 7.5 | 0.0 | 0.8441284530276189 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 12.5 |
| 375 | 1875.0 | 1870.0 | 98.33478235838233 | 61.83478235838233 | 29.0 | 20.0 | 12.5 | 0.0 | 0.8434274343597075 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 7.5 |
| 376 | 1880.0 | 1875.0 | 98.33478634917402 | 66.83478634917402 | 29.0 | 20.0 | 17.5 | 0.0 | 0.8427264156917961 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 2.5 |
| 377 | 1885.0 | 1880.0 | 98.33478945720573 | 69.33478945720573 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8420253970238847 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 378 | 1890.0 | 1885.0 | 98.33479187774326 | 69.33479187774326 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8413243783559732 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 379 | 1895.0 | 1890.0 | 98.33479376285977 | 69.33479376285977 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8406233596880618 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 380 | 1900.0 | 1895.0 | 98.33479523099 | 69.33479523099 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8399223410201504 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 381 | 1905.0 | 1900.0 | 98.33479637437097 | 69.33479637437097 | 29.0 | 20.0 | 20.0 | 0.0 | 0.839221322352239 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 382 | 1910.0 | 1905.0 | 98.18647726483695 | 69.18647726483695 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8385203036843276 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 383 | 1915.0 | 1910.0 | 97.69269595833255 | 68.69269595833255 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8378192850164161 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 384 | 1920.0 | 1915.0 | 97.69269649842748 | 68.69269649842748 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8371182663485047 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 385 | 1925.0 | 1920.0 | 97.68219091905382 | 68.68219091905382 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8364172476805933 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 386 | 1930.0 | 1925.0 | 97.68219124663796 | 68.68219124663796 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8357162290126819 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 387 | 1935.0 | 1930.0 | 97.68219150176074 | 68.68219150176074 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8350152103447706 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 388 | 1940.0 | 1935.0 | 97.68219170045056 | 68.68219170045056 | 29.0 | 20.0 | 20.0 | 0.0 | 0.834314191676859 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 389 | 1945.0 | 1940.0 | 96.90474785519035 | 67.90474785519035 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8336131730089477 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 390 | 1950.0 | 1945.0 | 96.87322997570182 | 67.87322997570182 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8329121543410363 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 391 | 1955.0 | 1950.0 | 95.90037446955624 | 66.90037446955624 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8322111356731249 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 392 | 1960.0 | 1955.0 | 95.90037454265014 | 66.90037454265014 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8315101170052135 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 393 | 1965.0 | 1960.0 | 95.90037459957573 | 66.90037459957573 | 29.0 | 20.0 | 20.0 | 0.0 | 0.830809098337302 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 394 | 1970.0 | 1965.0 | 95.90037464390942 | 66.90037464390942 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8301080796693906 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 395 | 1975.0 | 1970.0 | 95.9202193451032 | 66.9202193451032 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8294070610014792 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 396 | 1980.0 | 1975.0 | 95.96467142532627 | 66.96467142532627 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8287060423335678 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 397 | 1985.0 | 1980.0 | 96.10755304626802 | 67.10755304626802 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8280050236656564 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 398 | 1990.0 | 1985.0 | 96.25043466257749 | 67.25043466257749 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8273040049977449 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 399 | 1995.0 | 1990.0 | 93.1267907552793 | 64.75043466257749 | 28.376356092701812 | 20.0 | 20.0 | 0.0 | 0.8266180617098731 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 400 | 2000.0 | 1995.0 | 93.12679076517148 | 64.12679076517148 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8259170430419617 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 401 | 2005.0 | 2000.0 | 93.02803437287552 | 64.02803437287552 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8252160243740503 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 402 | 2010.0 | 2005.0 | 93.02803437887543 | 64.02803437887543 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8245150057061389 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 403 | 2015.0 | 2010.0 | 93.02803438354817 | 64.02803438354817 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8238139870382274 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 404 | 2020.0 | 2015.0 | 93.0280343871873 | 64.0280343871873 | 29.0 | 20.0 | 20.0 | 0.0 | 0.823112968370316 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 405 | 2025.0 | 2020.0 | 93.02803439002146 | 64.02803439002146 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8224119497024046 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 406 | 2030.0 | 2025.0 | 92.7779915922287 | 63.7779915922287 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8217109310344932 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 407 | 2035.0 | 2030.0 | 92.6225027939477 | 63.6225027939477 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8210099123665818 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 408 | 2040.0 | 2035.0 | 92.61619919528647 | 63.61619919528647 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8203088936986703 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 409 | 2045.0 | 2040.0 | 92.61619919632909 | 63.61619919632909 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8196078750307589 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 410 | 2050.0 | 2045.0 | 91.4185151971411 | 62.418515197141105 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8189068563628475 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 411 | 2055.0 | 2050.0 | 91.41851519777349 | 62.41851519777349 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8182058376949362 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 412 | 2060.0 | 2055.0 | 91.418515198266 | 62.41851519826599 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8175048190270248 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 413 | 2065.0 | 2060.0 | 91.41851519864954 | 62.418515198649544 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8168038003591133 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 414 | 2070.0 | 2065.0 | 91.42135967577128 | 62.421359675771285 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8161027816912019 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 415 | 2075.0 | 2070.0 | 91.43481886255935 | 62.434818862559354 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8154017630232905 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 416 | 2080.0 | 2075.0 | 91.45545586382946 | 62.45545586382946 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8147007443553791 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 417 | 2085.0 | 2080.0 | 91.14759121395522 | 62.147591213955224 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8139997256874677 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 418 | 2090.0 | 2085.0 | 91.15328841436036 | 62.15328841436036 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8132987070195562 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 419 | 2095.0 | 2090.0 | 91.1577253984972 | 62.157725398497206 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8125976883516448 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 420 | 2100.0 | 2095.0 | 91.16118092521745 | 62.16118092521745 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8118966696837334 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 421 | 2105.0 | 2100.0 | 91.1638720921331 | 62.163872092133104 | 29.0 | 20.0 | 20.0 | 0.0 | 0.811195651015822 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 422 | 2110.0 | 2105.0 | 91.16596797503439 | 62.16596797503439 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8104946323479106 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 423 | 2115.0 | 2110.0 | 91.16760025027914 | 62.167600250279136 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8097936136799991 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 424 | 2120.0 | 2115.0 | 91.16887146751793 | 62.16887146751793 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8090925950120877 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 425 | 2125.0 | 2120.0 | 91.16986149249895 | 62.16986149249895 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8083915763441764 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 426 | 2130.0 | 2125.0 | 91.17063252472944 | 62.17063252472944 | 29.0 | 20.0 | 20.0 | 0.0 | 0.807690557676265 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 427 | 2135.0 | 2130.0 | 91.20771217190098 | 62.20771217190098 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8069895390083536 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 428 | 2140.0 | 2135.0 | 91.27728595992173 | 62.27728595992173 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8062885203404421 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 429 | 2145.0 | 2140.0 | 91.5403001697585 | 62.540300169758495 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8055875016725307 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 430 | 2150.0 | 2145.0 | 91.62042941666456 | 62.620429416664564 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8048864830046193 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 431 | 2155.0 | 2150.0 | 91.88330032109714 | 62.88330032109714 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8041854643367079 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 432 | 2160.0 | 2155.0 | 92.14612236164221 | 63.14612236164221 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8034844456687965 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 433 | 2165.0 | 2160.0 | 92.24207495806453 | 63.242074958064535 | 29.0 | 20.0 | 20.0 | 0.0 | 0.802783427000885 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 434 | 2170.0 | 2165.0 | 92.26649875037428 | 63.26649875037428 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8020824083329736 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 435 | 2175.0 | 2170.0 | 92.29089946101793 | 63.29089946101793 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8013813896650622 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 436 | 2180.0 | 2175.0 | 92.29096275119751 | 63.29096275119751 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8006803709971508 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 437 | 2185.0 | 2180.0 | 92.29101204163892 | 63.29101204163892 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7999793523292394 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 438 | 2190.0 | 2185.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7992783336613279 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 439 | 2195.0 | 2190.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7985773149934166 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 440 | 2200.0 | 2195.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7978762963255052 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 441 | 2205.0 | 2200.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7971752776575938 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 442 | 2210.0 | 2205.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7964742589896824 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 443 | 2215.0 | 2210.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7957732403217709 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 444 | 2220.0 | 2215.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7950722216538595 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 445 | 2225.0 | 2220.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7943712029859481 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 446 | 2230.0 | 2225.0 | 91.98686561768936 | 62.98686561768936 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7936701843180367 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 447 | 2235.0 | 2230.0 | 92.01160676944568 | 63.01160676944568 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7929691656501253 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 448 | 2240.0 | 2235.0 | 92.04954243321205 | 63.04954243321205 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7922681469822138 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 449 | 2245.0 | 2240.0 | 91.86926546069566 | 62.86926546069566 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7915671283143024 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 450 | 2250.0 | 2245.0 | 91.94209276844316 | 62.94209276844316 | 29.0 | 20.0 | 20.0 | 0.0 | 0.790866109646391 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 451 | 2255.0 | 2250.0 | 92.01793884627267 | 63.01793884627267 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7901650909784796 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 452 | 2260.0 | 2255.0 | 92.18276080201657 | 63.182760802016574 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7894640723105683 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 453 | 2265.0 | 2260.0 | 92.3451953878579 | 63.3451953878579 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7887630536426568 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 454 | 2270.0 | 2265.0 | 92.50137809366883 | 63.50137809366883 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7880620349747454 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 455 | 2275.0 | 2270.0 | 92.65582157511143 | 63.65582157511143 | 29.0 | 20.0 | 20.0 | 0.0 | 0.787361016306834 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 456 | 2280.0 | 2275.0 | 92.71469988058739 | 63.71469988058739 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7866599976389226 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 457 | 2285.0 | 2280.0 | 92.73214729315984 | 63.73214729315984 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7859589789710112 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 458 | 2290.0 | 2285.0 | 92.748773154313 | 63.748773154313 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7852579603030997 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 459 | 2295.0 | 2290.0 | 92.75102585724413 | 63.75102585724413 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7845569416351883 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 460 | 2300.0 | 2295.0 | 92.75278026405093 | 63.75278026405093 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7838559229672769 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 461 | 2305.0 | 2300.0 | 92.75414659744588 | 63.75414659744588 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7831549042993655 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 462 | 2310.0 | 2305.0 | 92.75521069896381 | 63.75521069896381 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7824538856314541 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 463 | 2315.0 | 2310.0 | 92.75603942205923 | 63.75603942205923 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7817528669635426 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 464 | 2320.0 | 2315.0 | 92.7566848322549 | 63.756684832254905 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7810518482956312 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 465 | 2325.0 | 2320.0 | 92.75718747822069 | 63.757187478220686 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7803508296277198 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 466 | 2330.0 | 2325.0 | 92.75757893929246 | 63.75757893929246 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7796498109598085 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 467 | 2335.0 | 2330.0 | 92.75788380948168 | 63.75788380948168 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7789487922918971 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 468 | 2340.0 | 2335.0 | 92.7581212426238 | 63.7581212426238 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7782477736239856 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 469 | 2345.0 | 2340.0 | 92.76125889984773 | 63.76125889984773 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7775467549560742 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 470 | 2350.0 | 2345.0 | 91.46212438426103 | 62.46212438426103 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7768457362881628 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 471 | 2355.0 | 2350.0 | 91.48365903221573 | 62.483659032215726 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7761447176202514 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 472 | 2360.0 | 2355.0 | 91.51009139215456 | 62.510091392154564 | 29.0 | 20.0 | 20.0 | 0.0 | 0.77544369895234 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 473 | 2365.0 | 2360.0 | 91.53965248579318 | 62.539652485793184 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7747426802844285 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 474 | 2370.0 | 2365.0 | 91.57486390235664 | 62.57486390235664 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7740416616165171 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 475 | 2375.0 | 2370.0 | 91.62540743352896 | 62.62540743352896 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7733406429486057 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 476 | 2380.0 | 2375.0 | 91.76578575626205 | 62.76578575626205 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7726396242806943 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 477 | 2385.0 | 2380.0 | 91.90262649775376 | 62.90262649775376 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7719386056127829 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 478 | 2390.0 | 2385.0 | 92.03847955344402 | 63.03847955344402 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7712375869448714 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 479 | 2395.0 | 2390.0 | 92.1735633986587 | 63.1735633986587 | 29.0 | 20.0 | 20.0 | 0.0 | 0.77053656827696 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 480 | 2400.0 | 2395.0 | 92.22396516215264 | 63.22396516215264 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7698355496090487 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 481 | 2405.0 | 2400.0 | 92.27580312924269 | 63.27580312924269 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7691345309411373 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 482 | 2410.0 | 2405.0 | 92.3743212803654 | 63.37432128036539 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7684335122732259 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 483 | 2415.0 | 2410.0 | 92.64847358810152 | 63.648473588101524 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7677324936053144 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 484 | 2420.0 | 2415.0 | 92.92240551334659 | 63.92240551334659 | 29.0 | 20.0 | 20.0 | 0.0 | 0.767031474937403 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 485 | 2425.0 | 2420.0 | 93.19616580453507 | 64.19616580453507 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7663304562694916 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 486 | 2430.0 | 2425.0 | 93.46979242698585 | 64.46979242698585 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7656294376015802 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 487 | 2435.0 | 2430.0 | 93.5698103036746 | 64.5698103036746 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7649284189336688 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 488 | 2440.0 | 2435.0 | 93.59538797284237 | 64.59538797284237 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7642274002657573 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 489 | 2445.0 | 2440.0 | 93.62090250136932 | 64.62090250136932 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7635263815978459 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 490 | 2450.0 | 2445.0 | 93.62107563369351 | 64.62107563369351 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7628253629299345 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 491 | 2455.0 | 2450.0 | 9.625740469283178 | 59.62107563369351 | -30.0 | 20.0 | 39.99533516441033 | 0.0 | 0.7634903637421497 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 492 | 2460.0 | 2455.0 | 9.62584547934599 | 54.62107563369351 | -30.0 | 20.0 | 34.99523015434752 | 0.0 | 0.7641553645543648 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 493 | 2465.0 | 2460.0 | 9.628562585380582 | 49.62107563369351 | -30.0 | 20.0 | 29.992513048312926 | 0.0 | 0.76482036536658 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 494 | 2470.0 | 2465.0 | 9.641095817688438 | 44.62107563369351 | -30.0 | 20.0 | 24.97997981600507 | 0.0 | 0.7654853661787953 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 495 | 2475.0 | 2470.0 | 9.660264995468067 | 39.62107563369351 | -29.96081063822544 | 20.0 | 20.0 | 0.0 | 0.7661494982924301 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 496 | 2480.0 | 2475.0 | 9.683816550763026 | 36.25 | -26.566183449236974 | 20.0 | 20.0 | 0.0 | 0.7667383827448034 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 497 | 2485.0 | 2480.0 | 9.71016919975448 | 35.0 | -25.289830800245518 | 20.0 | 20.0 | 0.0 | 0.7672989746789017 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 498 | 2490.0 | 2485.0 | 9.725162477892692 | 35.0 | -25.27483752210731 | 20.0 | 20.0 | 0.0 | 0.7678592342615953 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 499 | 2495.0 | 2490.0 | 9.733497711600334 | 35.0 | -25.266502288399664 | 20.0 | 20.0 | 0.0 | 0.7684193090797161 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 500 | 2500.0 | 2495.0 | 9.746063644827895 | 35.0 | -25.253936355172105 | 20.0 | 20.0 | 0.0 | 0.7689791053526435 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 501 | 2505.0 | 2500.0 | 9.775768314362358 | 35.0 | -25.22423168563764 | 20.0 | 20.0 | 0.0 | 0.7695382431712585 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 502 | 2510.0 | 2505.0 | 9.81831625907733 | 35.0 | -25.181683740922672 | 20.0 | 20.0 | 0.0 | 0.770096437842614 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 503 | 2515.0 | 2510.0 | 9.869245266688878 | 35.0 | -25.13075473331112 | 20.0 | 20.0 | 0.0 | 0.7706535035862551 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 504 | 2520.0 | 2515.0 | 9.925438790825968 | 35.0 | -25.074561209174032 | 20.0 | 20.0 | 0.0 | 0.7712093237052565 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 505 | 2525.0 | 2520.0 | 9.957790857471862 | 35.0 | -25.042209142528137 | 20.0 | 20.0 | 0.0 | 0.7717644266859047 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 506 | 2530.0 | 2525.0 | 9.976091424751935 | 35.0 | -25.023908575248065 | 20.0 | 20.0 | 0.0 | 0.7723191240034827 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 507 | 2535.0 | 2530.0 | 9.991657284657505 | 35.0 | -25.008342715342494 | 20.0 | 20.0 | 0.0 | 0.7728734762774113 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 508 | 2540.0 | 2535.0 | 10.000525054058311 | 35.0 | -24.99947494594169 | 20.0 | 20.0 | 0.0 | 0.7734276319822115 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 509 | 2545.0 | 2540.0 | 9.74478130936912 | 35.0 | -25.25521869063088 | 20.0 | 20.0 | 0.0 | 0.7739874566802762 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 510 | 2550.0 | 2545.0 | 9.750159876855905 | 35.0 | -25.249840123144097 | 20.0 | 20.0 | 0.0 | 0.7745471621532828 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 511 | 2555.0 | 2550.0 | 9.754348709426417 | 35.0 | -25.245651290573583 | 20.0 | 20.0 | 0.0 | 0.7751067747737206 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 512 | 2560.0 | 2555.0 | 9.811891975512484 | 35.0 | -25.188108024487516 | 20.0 | 20.0 | 0.0 | 0.7756651118502023 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 513 | 2565.0 | 2560.0 | 9.936022070894902 | 35.0 | -25.0639779291051 | 20.0 | 20.0 | 0.0 | 0.7762206973728756 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 514 | 2570.0 | 2565.0 | 10.328823935296244 | 35.0 | -24.671176064703758 | 20.0 | 20.0 | 0.0 | 0.77676757577692 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 515 | 2575.0 | 2570.0 | 10.721188120681443 | 35.0 | -24.278811879318557 | 20.0 | 20.0 | 0.0 | 0.7773057567642322 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 516 | 2580.0 | 2575.0 | 11.11321144130614 | 35.0 | -23.88678855869386 | 20.0 | 20.0 | 0.0 | 0.7778352478906571 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 517 | 2585.0 | 2580.0 | 11.504969296188433 | 35.0 | -23.495030703811565 | 20.0 | 20.0 | 0.0 | 0.7783560550406923 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 518 | 2590.0 | 2585.0 | 11.648275299475998 | 35.0 | -23.351724700524002 | 20.0 | 20.0 | 0.0 | 0.7788736855704415 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 519 | 2595.0 | 2590.0 | 9.483438862985025 | 35.0 | -25.516561137014975 | 20.0 | 20.0 | 0.0 | 0.7794393033664766 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 520 | 2600.0 | 2595.0 | 7.739884362689776 | 35.0 | -27.260115637310225 | 20.0 | 20.0 | 0.0 | 0.7800435700011396 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 521 | 2605.0 | 2600.0 | 7.740228203005562 | 35.0 | -27.25977179699444 | 20.0 | 20.0 | 0.0 | 0.7806478290139997 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 522 | 2610.0 | 2605.0 | 7.740495986112748 | 35.0 | -27.259504013887252 | 20.0 | 20.0 | 0.0 | 0.7812520820909937 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 523 | 2615.0 | 2610.0 | 7.740704535806318 | 35.0 | -27.259295464193684 | 20.0 | 20.0 | 0.0 | 0.7818563305451305 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 524 | 2620.0 | 2615.0 | 7.740866954470978 | 35.0 | -27.259133045529023 | 20.0 | 20.0 | 0.0 | 0.7824605753989825 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 525 | 2625.0 | 2620.0 | 7.740993446254202 | 35.0 | -27.2590065537458 | 20.0 | 20.0 | 0.0 | 0.7830648174489299 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 526 | 2630.0 | 2625.0 | 7.741091958154029 | 35.0 | -27.25890804184597 | 20.0 | 20.0 | 0.0 | 0.7836690573151941 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 527 | 2635.0 | 2630.0 | 7.741168679298756 | 35.0 | -27.258831320701244 | 20.0 | 20.0 | 0.0 | 0.7842732954808043 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 528 | 2640.0 | 2635.0 | 7.741228429786347 | 35.0 | -27.258771570213653 | 20.0 | 20.0 | 0.0 | 0.7848775323219436 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 529 | 2645.0 | 2640.0 | 7.755008296846206 | 35.0 | -27.244991703153794 | 20.0 | 20.0 | 0.0 | 0.7854814637089901 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 530 | 2650.0 | 2645.0 | 7.78580720401553 | 35.0 | -27.21419279598447 | 20.0 | 20.0 | 0.0 | 0.7860847123860938 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 531 | 2655.0 | 2650.0 | 7.892495908869154 | 35.0 | -27.107504091130846 | 20.0 | 20.0 | 0.0 | 0.7866855961273514 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 532 | 2660.0 | 2655.0 | 8.028212723658532 | 35.0 | -26.971787276341466 | 20.0 | 20.0 | 0.0 | 0.7872834714755401 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 533 | 2665.0 | 2660.0 | 8.254473610144219 | 35.0 | -26.745526389855783 | 20.0 | 20.0 | 0.0 | 0.7878763313679528 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 534 | 2670.0 | 2665.0 | 8.581636771975681 | 35.0 | -26.41836322802432 | 20.0 | 20.0 | 0.0 | 0.7884619391347539 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 535 | 2675.0 | 2670.0 | 9.206025877870696 | 35.0 | -25.793974122129306 | 20.0 | 20.0 | 0.0 | 0.7890337062594698 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 536 | 2680.0 | 2675.0 | 9.769977811585745 | 35.0 | -25.230022188414253 | 20.0 | 20.0 | 0.0 | 0.7895929724343865 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 537 | 2685.0 | 2680.0 | 10.251578237923823 | 35.0 | -24.748421762076177 | 20.0 | 20.0 | 0.0 | 0.7901415631201475 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 538 | 2690.0 | 2685.0 | 10.776640126359208 | 35.0 | -24.223359873640792 | 20.0 | 20.0 | 0.0 | 0.7906785149198325 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 539 | 2695.0 | 2690.0 | 10.974180978323954 | 35.0 | -24.025819021676046 | 20.0 | 20.0 | 0.0 | 0.7912110878919508 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 540 | 2700.0 | 2695.0 | 11.030234651914899 | 35.0 | -23.9697653480851 | 20.0 | 20.0 | 0.0 | 0.7917424183394537 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 541 | 2705.0 | 2700.0 | 71.08411293218028 | 37.5 | 29.0 | 20.0 | 15.415887067819725 | 0.0 | 0.7910413996715423 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 4.584112932180275 |
| 542 | 2710.0 | 2705.0 | 71.08943625380347 | 40.0 | 29.0 | 20.0 | 17.91056374619653 | 0.0 | 0.7903403810036309 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 2.08943625380347 |
| 543 | 2715.0 | 2710.0 | 71.09358206085216 | 42.09358206085216 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7896393623357195 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 544 | 2720.0 | 2715.0 | 70.38240281862815 | 41.38240281862815 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7889383436678081 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 545 | 2725.0 | 2720.0 | 70.38491737771244 | 41.38491737771244 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7882373249998966 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 546 | 2730.0 | 2725.0 | 70.38687571829635 | 41.38687571829635 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7875363063319852 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 547 | 2735.0 | 2730.0 | 70.38840087547663 | 41.388400875476634 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7868352876640738 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 548 | 2740.0 | 2735.0 | 70.39155716515423 | 41.391557165154225 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7861342689961625 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 549 | 2745.0 | 2740.0 | 70.40179653570026 | 41.40179653570026 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7854332503282511 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 550 | 2750.0 | 2745.0 | 70.41679863059312 | 41.41679863059312 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7847322316603396 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 551 | 2755.0 | 2750.0 | 70.43492304667578 | 41.43492304667578 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7840312129924282 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 552 | 2760.0 | 2755.0 | 70.46518687838166 | 41.46518687838166 | 29.0 | 20.0 | 20.0 | 0.0 | 0.7833301943245168 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 553 | 2765.0 | 2760.0 | 70.52480594467411 | 41.524805944674114 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7826291756566054 | 1.4583333333333333 | 1.4583333333333333 | unloading | 20.0 | 0.0 |
| 554 | 2770.0 | 2765.0 | 70.60503040859949 | 41.60503040859949 | 29.0 | 0.0 | 0.0 | 0.0 | 0.781928156988694 | 1.4583333333333333 | 1.4583333333333333 | unloading | 19.666666666666664 | 0.0 |
| 555 | 2775.0 | 2770.0 | 70.70124325044097 | 41.70124325044097 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7812271383207825 | 1.4583333333333333 | 1.4583333333333333 | unloading | 19.333333333333332 | 0.0 |
| 556 | 2780.0 | 2775.0 | 68.095345964568 | 39.20124325044097 | 28.89410271412703 | 0.0 | 0.0 | 0.0 | 0.7805286795140531 | 1.4583333333333333 | 1.4583333333333333 | unloading | 19.0 | 0.0 |
| 557 | 2785.0 | 2780.0 | 68.15551730705438 | 39.15551730705438 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7798276608461417 | 1.4583333333333333 | 1.4583333333333333 | unloading | 18.666666666666668 | 0.0 |
| 558 | 2790.0 | 2785.0 | 67.85125157200201 | 38.85125157200201 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7791266421782304 | 1.4583333333333333 | 1.4583333333333333 | unloading | 18.333333333333332 | 0.0 |
| 559 | 2795.0 | 2790.0 | 67.615886795856 | 38.615886795856 | 29.0 | 0.0 | 0.0 | 0.0 | 0.778425623510319 | 1.4583333333333333 | 1.4583333333333333 | unloading | 18.0 | 0.0 |
| 560 | 2800.0 | 2795.0 | 67.90418084760657 | 38.90418084760657 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7777246048424076 | 1.4583333333333333 | 1.4583333333333333 | unloading | 17.666666666666664 | 0.0 |
| 561 | 2805.0 | 2800.0 | 68.18885297193196 | 39.188852971931965 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7770235861744961 | 1.4583333333333333 | 1.4583333333333333 | unloading | 17.333333333333336 | 0.0 |
| 562 | 2810.0 | 2805.0 | 68.3369568514362 | 39.3369568514362 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7763225675065847 | 1.4583333333333333 | 1.4583333333333333 | unloading | 17.0 | 0.0 |
| 563 | 2815.0 | 2810.0 | 68.17457494670994 | 39.17457494670994 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7756215488386733 | 1.4583333333333333 | 1.4583333333333333 | unloading | 16.666666666666668 | 0.0 |
| 564 | 2820.0 | 2815.0 | 68.24215264413922 | 39.242152644139225 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7749205301707619 | 1.4583333333333333 | 1.4583333333333333 | unloading | 16.333333333333332 | 0.0 |
| 565 | 2825.0 | 2820.0 | 68.26164064033749 | 39.26164064033749 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7742195115028505 | 1.4583333333333333 | 1.4583333333333333 | unloading | 16.0 | 0.0 |
| 566 | 2830.0 | 2825.0 | 68.2803620100462 | 39.280362010046204 | 29.0 | 0.0 | 0.0 | 0.0 | 0.773518492834939 | 1.4583333333333333 | 1.4583333333333333 | unloading | 15.666666666666666 | 0.0 |
| 567 | 2835.0 | 2830.0 | 68.28589744155563 | 39.28589744155563 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7728174741670276 | 1.4583333333333333 | 1.4583333333333333 | unloading | 15.333333333333332 | 0.0 |
| 568 | 2840.0 | 2835.0 | 68.29522522392794 | 39.29522522392794 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7721164554991162 | 1.4583333333333333 | 1.4583333333333333 | unloading | 15.0 | 0.0 |
| 569 | 2845.0 | 2840.0 | 68.32122021092148 | 39.32122021092148 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7714154368312048 | 1.4583333333333333 | 1.4583333333333333 | unloading | 14.666666666666668 | 0.0 |
| 570 | 2850.0 | 2845.0 | 68.34693317179045 | 39.346933171790454 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7707144181632934 | 1.4583333333333333 | 1.4583333333333333 | unloading | 14.333333333333334 | 0.0 |
| 571 | 2855.0 | 2850.0 | 68.37242649049276 | 39.37242649049276 | 29.0 | 0.0 | 0.0 | 0.0 | 0.770013399495382 | 1.4583333333333333 | 1.4583333333333333 | unloading | 14.0 | 0.0 |
| 572 | 2860.0 | 2855.0 | 68.39774875170369 | 39.39774875170369 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7693123808274706 | 1.4583333333333333 | 1.4583333333333333 | unloading | 13.666666666666668 | 0.0 |
| 573 | 2865.0 | 2860.0 | 68.40723601542858 | 39.40723601542858 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7686113621595592 | 1.4583333333333333 | 1.4583333333333333 | unloading | 13.333333333333336 | 0.0 |
| 574 | 2870.0 | 2865.0 | 68.23549059420706 | 39.235490594207064 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7679103434916478 | 1.4583333333333333 | 1.4583333333333333 | unloading | 13.0 | 0.0 |
| 575 | 2875.0 | 2870.0 | 68.238063971148 | 39.238063971147994 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7672093248237364 | 1.4583333333333333 | 1.4583333333333333 | unloading | 12.666666666666666 | 0.0 |
| 576 | 2880.0 | 2875.0 | 68.28556253066571 | 39.285562530665715 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7665083061558249 | 1.4583333333333333 | 1.4583333333333333 | unloading | 12.333333333333334 | 0.0 |
| 577 | 2885.0 | 2880.0 | 68.39704892558765 | 39.397048925587654 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7658072874879135 | 1.4583333333333333 | 1.4583333333333333 | unloading | 12.0 | 0.0 |
| 578 | 2890.0 | 2885.0 | 68.76319207710523 | 39.76319207710523 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7651062688200021 | 1.4583333333333333 | 1.4583333333333333 | unloading | 11.666666666666664 | 0.0 |
| 579 | 2895.0 | 2890.0 | 69.1429657039572 | 40.1429657039572 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7644052501520907 | 1.4583333333333333 | 1.4583333333333333 | unloading | 11.333333333333332 | 0.0 |
| 580 | 2900.0 | 2895.0 | 69.53174080195532 | 40.53174080195532 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7637042314841793 | 1.4583333333333333 | 1.4583333333333333 | unloading | 11.0 | 0.0 |
| 581 | 2905.0 | 2900.0 | 69.86347944325051 | 40.86347944325051 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7630032128162678 | 1.4583333333333333 | 1.4583333333333333 | unloading | 10.666666666666666 | 0.0 |
| 582 | 2910.0 | 2905.0 | 70.00727822760769 | 41.007278227607685 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7623021941483564 | 1.4583333333333333 | 1.4583333333333333 | unloading | 10.333333333333332 | 0.0 |
| 583 | 2915.0 | 2910.0 | 70.04970660560419 | 41.049706605604186 | 29.0 | 0.0 | 0.0 | 0.0 | 0.761601175480445 | 1.4583333333333333 | 1.4583333333333333 | unloading | 10.0 | 0.0 |
| 584 | 2920.0 | 2915.0 | 70.09055361168443 | 41.09055361168443 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7609001568125336 | 1.4583333333333333 | 1.4583333333333333 | unloading | 9.666666666666666 | 0.0 |
| 585 | 2925.0 | 2920.0 | 70.09575709947887 | 41.095757099478874 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7601991381446223 | 1.4583333333333333 | 1.4583333333333333 | unloading | 9.333333333333334 | 0.0 |
| 586 | 2930.0 | 2925.0 | 70.1003017038657 | 41.100301703865696 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7594981194767108 | 1.4583333333333333 | 1.4583333333333333 | unloading | 9.0 | 0.0 |
| 587 | 2935.0 | 2930.0 | 69.98218635773931 | 40.98218635773931 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7587971008087994 | 1.4583333333333333 | 1.4583333333333333 | unloading | 8.666666666666668 | 0.0 |
| 588 | 2940.0 | 2935.0 | 69.9882147267443 | 40.9882147267443 | 29.0 | 0.0 | 0.0 | 0.0 | 0.758096082140888 | 1.4583333333333333 | 1.4583333333333333 | unloading | 8.333333333333332 | 0.0 |
| 589 | 2945.0 | 2940.0 | 69.99451981845412 | 40.99451981845412 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7573950634729766 | 1.4583333333333333 | 1.4583333333333333 | unloading | 8.0 | 0.0 |
| 590 | 2950.0 | 2945.0 | 70.00092615398505 | 41.00092615398505 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7566940448050652 | 1.4583333333333333 | 1.4583333333333333 | unloading | 7.666666666666666 | 0.0 |
| 591 | 2955.0 | 2950.0 | 70.00488269872803 | 41.004882698728025 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7559930261371537 | 1.4583333333333333 | 1.4583333333333333 | unloading | 7.333333333333334 | 0.0 |
| 592 | 2960.0 | 2955.0 | 69.69169655456825 | 40.69169655456825 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7552920074692423 | 1.4583333333333333 | 1.4583333333333333 | unloading | 7.0 | 0.0 |
| 593 | 2965.0 | 2960.0 | 69.81727976167133 | 40.81727976167133 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7545909888013309 | 1.4583333333333333 | 1.4583333333333333 | unloading | 6.666666666666668 | 0.0 |
| 594 | 2970.0 | 2965.0 | 69.22689502462032 | 40.22689502462032 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7538899701334195 | 1.4583333333333333 | 1.4583333333333333 | unloading | 6.333333333333333 | 0.0 |
| 595 | 2975.0 | 2970.0 | 69.26409796968176 | 40.26409796968176 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7531889514655081 | 1.4583333333333333 | 1.4583333333333333 | unloading | 6.000000000000001 | 0.0 |
| 596 | 2980.0 | 2975.0 | 69.69406943617143 | 40.69406943617143 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7524879327975966 | 1.4583333333333333 | 1.4583333333333333 | unloading | 5.666666666666666 | 0.0 |
| 597 | 2985.0 | 2980.0 | 70.14096842523752 | 41.14096842523752 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7517869141296852 | 1.4583333333333333 | 1.4583333333333333 | unloading | 5.333333333333334 | 0.0 |
| 598 | 2990.0 | 2985.0 | 70.34678114553282 | 41.346781145532816 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7510858954617738 | 1.4583333333333333 | 1.4583333333333333 | unloading | 5.0 | 0.0 |
| 599 | 2995.0 | 2990.0 | 70.50822291216039 | 41.50822291216039 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7503848767938625 | 1.4583333333333333 | 1.4583333333333333 | unloading | 4.666666666666666 | 0.0 |
| 600 | 3000.0 | 2995.0 | 70.71059389355213 | 41.71059389355213 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7496838581259511 | 1.4583333333333333 | 1.4583333333333333 | unloading | 4.333333333333334 | 0.0 |
| 601 | 3005.0 | 3000.0 | 71.13983674027598 | 42.13983674027598 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7489828394580396 | 1.4583333333333333 | 1.4583333333333333 | unloading | 3.999999999999999 | 0.0 |
| 602 | 3010.0 | 3005.0 | 71.56593611490909 | 42.56593611490909 | 29.0 | 0.0 | 0.0 | 0.0 | 0.7482818207901282 | 1.4583333333333333 | 1.4583333333333333 | offline | 0.0 | 0.0 |

#### informed: 366 operating/transition rows
| tick | sim_time | decision_sim_time | demand_mw | turbine_mw | bess_mw | diesel_mw | curtailment_mw | unserved_mw | soc | floor_mwh | applied_floor_mwh | unit_state | unit_output_mw | gap_before_diesel_mw |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 68 | 340.0 | 335.0 | 94.31675134370708 | 57.922268896194815 | 29.0 | 0.0 | 0.0 | 7.39448244751226 | 0.9309237908664557 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 7.394482447512267 |
| 69 | 345.0 | 340.0 | 100.88615700068769 | 64.36290643066019 | 29.0 | 0.0 | 0.0 | 7.5232505700275 | 0.9302227721985443 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 7.5232505700275 |
| 70 | 350.0 | 345.0 | 102.55356172362593 | 69.36290643066019 | 29.0 | 20.0 | 15.809344707034256 | 0.0 | 0.9295217535306329 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 4.190655292965744 |
| 71 | 355.0 | 350.0 | 104.22095237567783 | 74.36290643066019 | 29.0 | 20.0 | 19.141954054982364 | 0.0 | 0.9288207348627215 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.8580459450176363 |
| 72 | 360.0 | 355.0 | 104.2209909582013 | 75.2209909582013 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9281197161948102 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 73 | 365.0 | 360.0 | 104.22102100630079 | 75.22102100630079 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9274186975268986 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 74 | 370.0 | 365.0 | 104.22104440778422 | 75.22104440778422 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9267176788589873 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 75 | 375.0 | 370.0 | 104.22450750100259 | 75.22450750100259 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9260166601910759 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 76 | 380.0 | 375.0 | 104.24082174764156 | 75.24082174764156 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9253156415231645 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 77 | 385.0 | 380.0 | 104.26582570961276 | 75.26582570961276 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9246146228552531 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 78 | 390.0 | 385.0 | 104.29657016723249 | 75.29657016723249 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9239136041873416 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 79 | 395.0 | 390.0 | 104.3309854510916 | 75.3309854510916 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9232125855194302 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 80 | 400.0 | 395.0 | 104.35055910041487 | 75.35055910041487 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9225115668515188 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 81 | 405.0 | 400.0 | 104.36143504370831 | 75.36143504370831 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9218105481836074 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 82 | 410.0 | 405.0 | 104.72922497279784 | 75.72922497279784 | 29.0 | 20.0 | 20.0 | 0.0 | 0.921109529515696 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 83 | 415.0 | 410.0 | 106.43066093930186 | 77.43066093930186 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9204085108477845 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 84 | 420.0 | 415.0 | 109.03556626169207 | 79.93066093930186 | 29.0 | 20.0 | 19.895094677609777 | 0.0 | 0.9197074921798731 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.10490532239020922 |
| 85 | 425.0 | 420.0 | 112.23721380903318 | 82.43066093930186 | 29.0 | 20.0 | 19.193447130268666 | 0.0 | 0.9190064735119617 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.8065528697313198 |
| 86 | 430.0 | 425.0 | 115.32868714840941 | 86.25 | 29.0 | 20.0 | 19.921312851590585 | 0.0 | 0.9183054548440504 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.07868714840941493 |
| 87 | 435.0 | 430.0 | 117.36696777185412 | 88.36696777185412 | 29.0 | 20.0 | 20.0 | 0.0 | 0.917604436176139 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 88 | 440.0 | 435.0 | 118.49982638236047 | 89.49982638236047 | 29.0 | 20.0 | 20.000000000000014 | 0.0 | 0.9169034175082275 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 89 | 445.0 | 440.0 | 119.46867853664423 | 90.46867853664423 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9162023988403161 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 90 | 450.0 | 445.0 | 120.00864605678962 | 91.00864605678962 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9155013801724047 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 91 | 455.0 | 450.0 | 120.42917318431195 | 91.42917318431195 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.9148003615044933 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 92 | 460.0 | 455.0 | 120.75668004052912 | 91.75668004052912 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9140993428365819 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 93 | 465.0 | 460.0 | 120.72597944909326 | 91.72597944909326 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.9133983241686704 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 94 | 470.0 | 465.0 | 111.92098068618853 | 88.39696013528179 | 23.52402055090674 | 20.0 | 20.0 | 0.0 | 0.9128296766669285 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 95 | 475.0 | 470.0 | 112.07568390449592 | 86.05166335358918 | 26.02402055090674 | 20.0 | 20.0 | 0.0 | 0.9122005965214011 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 96 | 480.0 | 475.0 | 112.19616689205739 | 83.67214634115065 | 28.52402055090674 | 20.0 | 20.0 | 0.0 | 0.9115110837320882 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 97 | 485.0 | 480.0 | 112.11349833810593 | 83.11349833810593 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9108100650641767 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 98 | 490.0 | 485.0 | 112.186574963817 | 83.186574963817 | 29.0 | 20.0 | 20.000000000000014 | 0.0 | 0.9101090463962653 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 99 | 495.0 | 490.0 | 112.24348709714499 | 83.24348709714499 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9094080277283539 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 100 | 500.0 | 495.0 | 112.2878103111471 | 83.2878103111471 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9087070090604425 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 101 | 505.0 | 500.0 | 112.32232926492017 | 83.32232926492017 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9080059903925312 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 102 | 510.0 | 505.0 | 112.34921265314945 | 83.34921265314945 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.9073049717246197 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 103 | 515.0 | 510.0 | 112.37014945695402 | 83.37014945695402 | 29.0 | 20.0 | 20.000000000000014 | 0.0 | 0.9066039530567083 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 104 | 520.0 | 515.0 | 112.21351076187145 | 83.21351076187145 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9059029343887969 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 105 | 525.0 | 520.0 | 112.22618840526512 | 83.22618840526512 | 29.0 | 20.0 | 20.000000000000014 | 0.0 | 0.9052019157208855 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 106 | 530.0 | 525.0 | 112.23606176386762 | 83.23606176386762 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.9045008970529741 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 107 | 535.0 | 530.0 | 112.24375114327879 | 83.24375114327879 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9037998783850626 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 108 | 540.0 | 535.0 | 112.24973963798553 | 83.24973963798553 | 29.0 | 20.0 | 20.0 | 0.0 | 0.9030988597171512 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 109 | 545.0 | 540.0 | 112.25440348235257 | 83.25440348235257 | 29.0 | 20.0 | 20.000000000000014 | 0.0 | 0.9023978410492398 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 110 | 550.0 | 545.0 | 112.25803568799775 | 83.25803568799775 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.9016968223813284 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 111 | 555.0 | 550.0 | 112.26086445259848 | 83.26086445259848 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.900995803713417 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 112 | 560.0 | 555.0 | 112.26306749668466 | 83.26306749668466 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.9002947850455055 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 113 | 565.0 | 560.0 | 112.26478322914411 | 83.26478322914411 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8995937663775941 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 114 | 570.0 | 565.0 | 112.26611944292708 | 83.26611944292708 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8988927477096827 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 115 | 575.0 | 570.0 | 112.2671600872676 | 83.2671600872676 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8981917290417714 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 116 | 580.0 | 575.0 | 112.2679705418949 | 83.2679705418949 | 29.0 | 20.0 | 20.0 | 0.0 | 0.89749071037386 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 117 | 585.0 | 580.0 | 112.26860172459328 | 83.26860172459328 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8967896917059485 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 118 | 590.0 | 585.0 | 112.26909329017305 | 83.26909329017305 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.8960886730380371 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 119 | 595.0 | 590.0 | 112.2694761218315 | 83.2694761218315 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8953876543701257 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 120 | 600.0 | 595.0 | 112.26977427142688 | 83.26977427142688 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8946866357022143 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 121 | 605.0 | 600.0 | 112.27000647056525 | 83.27000647056525 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8939856170343029 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 122 | 610.0 | 605.0 | 112.27018730743602 | 83.27018730743602 | 29.0 | 20.0 | 19.999999999999986 | 0.0 | 0.8932845983663914 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 123 | 615.0 | 610.0 | 22.23390814333261 | 75.77018730743602 | -30.0 | 20.0 | 43.536279164103405 | 0.0 | 0.8939495991786066 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 124 | 620.0 | 615.0 | 22.23401782643914 | 68.27018730743602 | -30.0 | 20.0 | 36.036169480996875 | 0.0 | 0.8946145999908218 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 125 | 625.0 | 620.0 | 22.234103247728402 | 60.77018730743602 | -30.0 | 20.0 | 28.536084059707616 | 0.0 | 0.8952796008030369 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 126 | 630.0 | 625.0 | 22.23416977389537 | 53.27018730743602 | -30.0 | 20.0 | 21.036017533540647 | 0.0 | 0.8959446016152521 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 127 | 635.0 | 630.0 | 22.2342215845263 | 45.77018730743602 | -23.53596572290972 | 20.0 | 19.999999999999996 | 0.0 | 0.896466316159319 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 128 | 640.0 | 635.0 | 22.234261934686238 | 38.27018730743602 | -16.03592537274978 | 20.0 | 20.0 | 0.0 | 0.8968217796059024 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 129 | 645.0 | 640.0 | 22.23429335942239 | 35.0 | -12.765706640577609 | 20.0 | 20.000000000000004 | 0.0 | 0.8971047531153853 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 130 | 650.0 | 645.0 | 22.234317833031522 | 35.0 | -12.765682166968478 | 20.0 | 20.000000000000004 | 0.0 | 0.8973877260823692 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 131 | 655.0 | 650.0 | 22.234336893097474 | 35.0 | -12.765663106902526 | 20.0 | 20.000000000000004 | 0.0 | 0.8976706986268543 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 132 | 660.0 | 655.0 | 22.234351737091764 | 35.0 | -12.765648262908236 | 20.0 | 20.0 | 0.0 | 0.8979536708422973 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 133 | 665.0 | 660.0 | 22.23436329760614 | 35.0 | -12.76563670239386 | 20.0 | 19.999999999999996 | 0.0 | 0.8982366428014819 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 134 | 670.0 | 665.0 | 22.23437230094379 | 35.0 | -12.76562769905621 | 20.0 | 20.0 | 0.0 | 0.8985196145610922 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 135 | 675.0 | 670.0 | 22.2343793127502 | 35.0 | -12.7656206872498 | 20.0 | 20.0 | 0.0 | 0.898802586165274 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 136 | 680.0 | 675.0 | 22.234384773550527 | 35.0 | -12.765615226449473 | 20.0 | 20.000000000000004 | 0.0 | 0.8990855576484079 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 137 | 685.0 | 680.0 | 22.234389026426093 | 35.0 | -12.765610973573907 | 20.0 | 20.0 | 0.0 | 0.8993685290372696 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 138 | 690.0 | 685.0 | 22.234392338568917 | 35.0 | -12.765607661431083 | 20.0 | 20.0 | 0.0 | 0.899651500352712 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 139 | 695.0 | 690.0 | 22.234394918068343 | 35.0 | -12.765605081931657 | 20.0 | 20.000000000000004 | 0.0 | 0.8999344716109755 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 140 | 700.0 | 695.0 | 22.234396926984513 | 35.0 | -12.765603073015487 | 20.0 | 20.000000000000004 | 0.0 | 0.900217442824708 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 141 | 705.0 | 700.0 | 22.23439849153 | 35.0 | -12.765601508469999 | 20.0 | 20.0 | 0.0 | 0.9005004140037596 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 142 | 710.0 | 705.0 | 22.305607043332586 | 35.0 | -12.694392956667414 | 20.0 | 20.0 | 0.0 | 0.9007818067246517 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 143 | 715.0 | 710.0 | 22.706750418944058 | 35.0 | -12.293249581055942 | 20.0 | 19.999999999999996 | 0.0 | 0.9010543074231906 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 144 | 720.0 | 715.0 | 23.760713077983013 | 35.0 | -11.239286922016987 | 20.0 | 20.0 | 0.0 | 0.9013034452542527 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 145 | 725.0 | 720.0 | 26.01320005354713 | 35.0 | -8.98679994645287 | 20.0 | 20.0 | 0.0 | 0.9015026528963728 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 146 | 730.0 | 725.0 | 28.35148590179692 | 35.0 | -6.64851409820308 | 20.0 | 20.0 | 0.0 | 0.9016500284722171 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 147 | 735.0 | 730.0 | 30.796162410894212 | 35.0 | -4.203837589105788 | 20.0 | 20.0 | 0.0 | 0.9017432136525897 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 148 | 740.0 | 735.0 | 33.34074701166033 | 35.0 | -1.6592529883396665 | 20.0 | 20.0 | 0.0 | 0.9017799938054202 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 149 | 745.0 | 740.0 | 34.6406740589541 | 35.0 | -0.35932594104590265 | 20.0 | 20.0 | 0.0 | 0.9017879588735085 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 150 | 750.0 | 745.0 | 35.46699057941153 | 35.0 | 0.46699057941152944 | 20.0 | 20.0 | 0.0 | 0.9017766702833737 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 151 | 755.0 | 750.0 | 36.24583550783724 | 35.0 | 1.245835507837242 | 20.0 | 20.0 | 0.0 | 0.9017465546299895 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 152 | 760.0 | 755.0 | 36.47120098118863 | 35.0 | 1.4712009811886304 | 20.0 | 20.0 | 0.0 | 0.9017109912040564 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 153 | 765.0 | 760.0 | 36.528400392416096 | 35.0 | 1.5284003924160956 | 20.0 | 20.0 | 0.0 | 0.9016740450934658 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 154 | 770.0 | 765.0 | 36.58559978641344 | 35.0 | 1.5855997864134395 | 20.0 | 20.0 | 0.0 | 0.9016357162986343 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 155 | 775.0 | 770.0 | 36.58559983365862 | 35.0 | 1.5855998336586197 | 20.0 | 20.0 | 0.0 | 0.9015973875026607 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 156 | 780.0 | 775.0 | 36.585599870453194 | 35.0 | 1.5855998704531942 | 20.0 | 20.0 | 0.0 | 0.9015590587057979 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 157 | 785.0 | 780.0 | 36.58559989910885 | 35.0 | 1.5855998991088498 | 20.0 | 20.0 | 0.0 | 0.9015207299082422 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 158 | 790.0 | 785.0 | 36.585599921425896 | 35.0 | 1.5855999214258958 | 20.0 | 20.0 | 0.0 | 0.9014824011101471 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 159 | 795.0 | 790.0 | 36.585599938806425 | 35.0 | 1.5855999388064248 | 20.0 | 20.0 | 0.0 | 0.9014440723116318 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 160 | 800.0 | 795.0 | 36.58559995234239 | 35.0 | 1.5855999523423918 | 20.0 | 20.0 | 0.0 | 0.9014057435127893 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 161 | 805.0 | 800.0 | 36.59580661501386 | 35.0 | 1.5958066150138634 | 20.0 | 20.0 | 0.0 | 0.901367167987703 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 162 | 810.0 | 805.0 | 18.671453068732326 | 35.0 | -16.328546931267674 | 20.0 | 20.0 | 0.0 | 0.9017291178867559 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 163 | 815.0 | 810.0 | 18.909388873638115 | 35.0 | -16.090611126361885 | 20.0 | 20.0 | 0.0 | 0.9020857935356916 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 164 | 820.0 | 815.0 | 19.25174063927462 | 35.0 | -15.748259360725381 | 20.0 | 19.999999999999996 | 0.0 | 0.9024348803778869 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 165 | 825.0 | 820.0 | 19.675013527654492 | 35.0 | -15.324986472345508 | 20.0 | 20.0 | 0.0 | 0.9027745846595967 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 166 | 830.0 | 825.0 | 20.137136859027983 | 35.0 | -14.862863140972017 | 20.0 | 20.0 | 0.0 | 0.9031040451949497 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 167 | 835.0 | 830.0 | 20.455319921361365 | 35.0 | -14.544680078638635 | 20.0 | 20.0 | 0.0 | 0.9034264526638066 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 168 | 840.0 | 835.0 | 20.70190752761264 | 35.0 | -14.29809247238736 | 20.0 | 20.0 | 0.0 | 0.9037433941007155 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 169 | 845.0 | 840.0 | 20.933589173790608 | 35.0 | -14.066410826209392 | 20.0 | 20.0 | 0.0 | 0.9040551999215282 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 170 | 850.0 | 845.0 | 21.067484059913166 | 35.0 | -13.932515940086834 | 20.0 | 20.000000000000004 | 0.0 | 0.9043640377354069 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 171 | 855.0 | 850.0 | 21.156167634521047 | 35.0 | -13.843832365478953 | 20.0 | 20.0 | 0.0 | 0.9046709097276473 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 172 | 860.0 | 855.0 | 21.22820469456736 | 35.0 | -13.77179530543264 | 20.0 | 20.0 | 0.0 | 0.9049761848964397 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 173 | 865.0 | 860.0 | 21.27694605381888 | 35.0 | -13.723053946181121 | 20.0 | 19.999999999999996 | 0.0 | 0.9052803796304493 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 174 | 870.0 | 865.0 | 21.314905862571926 | 35.0 | -13.685094137428074 | 20.0 | 20.0 | 0.0 | 0.9055837329210037 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 175 | 875.0 | 870.0 | 21.34446899135404 | 35.0 | -13.655531008645958 | 20.0 | 20.0 | 0.0 | 0.9058864308947363 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 176 | 880.0 | 875.0 | 21.367492779199594 | 35.0 | -13.632507220800406 | 20.0 | 20.0 | 0.0 | 0.9061886185072151 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 177 | 885.0 | 880.0 | 19.69395772320298 | 35.0 | -15.306042276797019 | 20.0 | 20.000000000000004 | 0.0 | 0.9065279028587442 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 178 | 890.0 | 885.0 | 19.70792235643403 | 35.0 | -15.292077643565971 | 20.0 | 19.999999999999996 | 0.0 | 0.9068668776605251 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 179 | 895.0 | 890.0 | 19.718798023729672 | 35.0 | -15.281201976270328 | 20.0 | 20.000000000000004 | 0.0 | 0.90720561138472 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 180 | 900.0 | 895.0 | 19.727268001935943 | 35.0 | -15.272731998064057 | 20.0 | 19.999999999999996 | 0.0 | 0.9075441573575019 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 181 | 905.0 | 900.0 | 19.733864427595584 | 35.0 | -15.266135572404416 | 20.0 | 20.0 | 0.0 | 0.9078825571093365 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 182 | 910.0 | 905.0 | 19.77110339573145 | 40.0 | -20.22889660426855 | 20.0 | 20.0 | 0.0 | 0.9083309648650716 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 183 | 915.0 | 910.0 | 19.847012063471873 | 45.0 | -25.152987936528127 | 20.0 | 20.0 | 0.0 | 0.9088885234453193 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 184 | 920.0 | 915.0 | 20.081259994321133 | 40.0 | -19.918740005678867 | 20.0 | 19.999999999999996 | 0.0 | 0.909330056054722 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 185 | 925.0 | 920.0 | 21.315223350373195 | 35.0 | -13.684776649626805 | 20.0 | 20.0 | 0.0 | 0.9096334023076215 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 186 | 930.0 | 925.0 | 23.789151711300146 | 35.0 | -11.210848288699854 | 20.0 | 20.000000000000004 | 0.0 | 0.9098819097482084 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 187 | 935.0 | 930.0 | 31.22466917281399 | 35.0 | -3.7753308271860107 | 20.0 | 20.0 | 0.0 | 0.9099655963504237 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 188 | 940.0 | 935.0 | 38.51304943749132 | 35.0 | 3.5130494374913184 | 20.0 | 20.0 | 0.0 | 0.909880675204321 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 189 | 945.0 | 940.0 | 45.738256877737435 | 35.0 | 10.738256877737435 | 20.0 | 19.999999999999993 | 0.0 | 0.9096210987032135 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 190 | 950.0 | 945.0 | 52.96326684699795 | 40.0 | 12.963266846997954 | 20.0 | 20.0 | 0.0 | 0.9093077369081493 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 191 | 955.0 | 950.0 | 55.59153790570026 | 35.0 | 20.591537905700257 | 20.0 | 19.999999999999993 | 0.0 | 0.9088099764780492 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 192 | 960.0 | 955.0 | 56.25889604552873 | 40.0 | 16.25889604552873 | 20.0 | 20.0 | 0.0 | 0.9084169492488235 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 193 | 965.0 | 960.0 | 56.92616090666847 | 35.0 | 21.92616090666847 | 20.0 | 20.0 | 0.0 | 0.9078869269001614 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 194 | 970.0 | 965.0 | 56.92641667784794 | 40.0 | 16.92641667784794 | 20.0 | 20.0 | 0.0 | 0.9074777636562987 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 195 | 975.0 | 970.0 | 56.58846838991523 | 35.0 | 21.588468389915228 | 20.0 | 19.999999999999993 | 0.0 | 0.9069559043682661 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 196 | 980.0 | 975.0 | 53.4998272904309 | 35.0 | 18.4998272904309 | 20.0 | 20.0 | 0.0 | 0.9065087069791721 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 197 | 985.0 | 980.0 | 53.49992300544874 | 40.0 | 13.499923005448743 | 20.0 | 20.000000000000007 | 0.0 | 0.9061823725639242 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 198 | 990.0 | 985.0 | 53.49999754837959 | 35.0 | 18.49999754837959 | 20.0 | 19.999999999999993 | 0.0 | 0.905735171059175 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 199 | 995.0 | 990.0 | 53.50005560247251 | 40.0 | 13.500055602472507 | 20.0 | 20.000000000000007 | 0.0 | 0.9054088334386516 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 200 | 1000.0 | 995.0 | 53.50010081504553 | 35.0 | 18.500100815045528 | 20.0 | 20.0 | 0.0 | 0.9049616294376314 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 201 | 1005.0 | 1000.0 | 53.504737386199444 | 40.0 | 13.504737386199444 | 20.0 | 20.000000000000007 | 0.0 | 0.9046351786440808 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 202 | 1010.0 | 1005.0 | 53.526537022556745 | 35.0 | 18.526537022556745 | 20.0 | 19.999999999999993 | 0.0 | 0.9041873355990958 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 203 | 1015.0 | 1010.0 | 52.404281763578425 | 35.0 | 17.404281763578425 | 20.0 | 20.0 | 0.0 | 0.9037666208950318 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 204 | 1020.0 | 1015.0 | 52.58874780485328 | 40.0 | 12.588747804853277 | 20.0 | 20.000000000000007 | 0.0 | 0.9034623123703135 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 205 | 1025.0 | 1020.0 | 53.31322213505521 | 35.0 | 18.313222135055213 | 20.0 | 20.0 | 0.0 | 0.9030196257983728 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 206 | 1030.0 | 1025.0 | 54.37971769496312 | 40.0 | 14.37971769496312 | 20.0 | 20.0 | 0.0 | 0.9026720240554946 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 207 | 1035.0 | 1030.0 | 55.673648928895126 | 35.0 | 20.673648928895126 | 20.0 | 19.999999999999993 | 0.0 | 0.9021722787509084 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 208 | 1040.0 | 1035.0 | 57.118357570959205 | 40.0 | 17.118357570959205 | 20.0 | 20.0 | 0.0 | 0.9017584757087973 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 209 | 1045.0 | 1040.0 | 57.93983129983981 | 35.0 | 22.93983129983981 | 20.0 | 20.0 | 0.0 | 0.9012039498474206 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 210 | 1050.0 | 1045.0 | 58.41528330910395 | 35.0 | 23.41528330910395 | 20.0 | 20.000000000000007 | 0.0 | 0.9006379308572787 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 211 | 1055.0 | 1050.0 | 58.84578369704505 | 35.0 | 23.84578369704505 | 20.0 | 20.0 | 0.0 | 0.9000615053564992 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 212 | 1060.0 | 1055.0 | 59.19075318193568 | 35.0 | 24.190753181935683 | 20.0 | 20.000000000000007 | 0.0 | 0.8994767408885208 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 213 | 1065.0 | 1060.0 | 59.48730271458086 | 35.0 | 24.487302714580863 | 20.0 | 20.0 | 0.0 | 0.8988848079116339 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 214 | 1070.0 | 1065.0 | 59.63898173914184 | 35.0 | 24.63898173914184 | 20.0 | 20.0 | 0.0 | 0.8982892083889628 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 215 | 1075.0 | 1070.0 | 59.868453547756104 | 35.0 | 24.868453547756104 | 20.0 | 20.0 | 0.0 | 0.897688061831064 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 216 | 1080.0 | 1075.0 | 59.99497433300767 | 35.0 | 24.99497433300767 | 20.0 | 19.999999999999993 | 0.0 | 0.8970838568789467 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 217 | 1085.0 | 1080.0 | 60.06936282047397 | 39.92561062413894 | 20.14375219633503 | 20.0 | 20.0 | 0.0 | 0.8965969207985531 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 218 | 1090.0 | 1085.0 | 60.1298787649565 | 35.0 | 25.1298787649565 | 20.0 | 20.0 | 0.0 | 0.8959894547938434 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 219 | 1095.0 | 1090.0 | 60.16791742876675 | 39.92561062413894 | 20.24230680462781 | 20.0 | 19.999999999999993 | 0.0 | 0.8955001363472354 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 220 | 1100.0 | 1095.0 | 60.19754196992916 | 35.0 | 25.197541969929162 | 20.0 | 20.0 | 0.0 | 0.8948910347159802 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 221 | 1105.0 | 1100.0 | 59.989481656488394 | 39.92561062413894 | 20.063871032349454 | 20.0 | 20.0 | 0.0 | 0.894406029607558 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 222 | 1110.0 | 1105.0 | 60.00744983334369 | 35.0 | 25.007449833343692 | 20.0 | 19.999999999999993 | 0.0 | 0.8938015230844536 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 223 | 1115.0 | 1110.0 | 57.69961746354896 | 35.0 | 22.69961746354896 | 20.0 | 20.0 | 0.0 | 0.8932528039259572 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 224 | 1120.0 | 1115.0 | 57.71051571371083 | 35.0 | 22.710515713710834 | 20.0 | 20.0 | 0.0 | 0.8927038213234328 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 225 | 1125.0 | 1120.0 | 57.71900327947101 | 35.0 | 22.71900327947101 | 20.0 | 20.0 | 0.0 | 0.8921546335504932 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 226 | 1130.0 | 1125.0 | 57.725613402331405 | 35.0 | 22.725613402331405 | 20.0 | 20.0 | 0.0 | 0.8916052859906735 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 227 | 1135.0 | 1130.0 | 57.73076137119128 | 40.0 | 17.730761371191278 | 20.0 | 20.0 | 0.0 | 0.8911766792762774 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 228 | 1140.0 | 1135.0 | 57.73477061337058 | 35.0 | 22.73477061337058 | 20.0 | 20.000000000000007 | 0.0 | 0.8906271103586686 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 229 | 1145.0 | 1140.0 | 57.740402846810234 | 40.0 | 17.740402846810234 | 20.0 | 20.000000000000007 | 0.0 | 0.8901982705803279 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 230 | 1150.0 | 1145.0 | 57.75471032795722 | 35.0 | 22.75471032795722 | 20.0 | 19.999999999999993 | 0.0 | 0.8896482196588515 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 231 | 1155.0 | 1150.0 | 57.77481327847242 | 40.0 | 17.774813278472422 | 20.0 | 20.0 | 0.0 | 0.8892185480751671 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 232 | 1160.0 | 1155.0 | 57.79868145743699 | 35.0 | 22.79868145743699 | 20.0 | 20.000000000000007 | 0.0 | 0.888667434237049 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 233 | 1165.0 | 1160.0 | 57.845499232271926 | 35.0 | 22.845499232271926 | 20.0 | 19.999999999999993 | 0.0 | 0.8881151886701669 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 234 | 1170.0 | 1165.0 | 57.906794812479646 | 35.0 | 22.906794812479646 | 20.0 | 20.0 | 0.0 | 0.8875614614016992 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 235 | 1175.0 | 1170.0 | 57.55317748400848 | 35.0 | 22.55317748400848 | 20.0 | 19.999999999999993 | 0.0 | 0.8870162821452506 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 236 | 1180.0 | 1175.0 | 57.70880697440119 | 35.0 | 22.708806974401192 | 20.0 | 20.000000000000007 | 0.0 | 0.8864673408481799 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 237 | 1185.0 | 1180.0 | 57.86131733378928 | 38.875374104374856 | 18.985943229414424 | 20.0 | 20.000000000000007 | 0.0 | 0.8860083925505343 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 238 | 1190.0 | 1185.0 | 58.01290078896208 | 35.0 | 23.012900788962078 | 20.0 | 19.999999999999993 | 0.0 | 0.8854521003761945 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 239 | 1195.0 | 1190.0 | 58.0695517037395 | 38.87488475073492 | 19.194666953004578 | 20.0 | 20.000000000000007 | 0.0 | 0.8849881065879738 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 240 | 1200.0 | 1195.0 | 58.08526442269173 | 35.0 | 23.08526442269173 | 20.0 | 19.999999999999993 | 0.0 | 0.8844300651633539 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 241 | 1205.0 | 1200.0 | 58.10053930309506 | 38.87488475073492 | 19.22565455236014 | 20.0 | 20.0 | 0.0 | 0.8839653223101117 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 242 | 1210.0 | 1205.0 | 58.10173986116031 | 35.0 | 23.10173986116031 | 20.0 | 20.0 | 0.0 | 0.8834068826237702 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 243 | 1215.0 | 1210.0 | 57.34624285672165 | 35.0 | 22.346242856721652 | 20.0 | 20.000000000000007 | 0.0 | 0.8828667056099687 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 244 | 1220.0 | 1215.0 | 56.685093031997 | 40.0 | 16.685093031997 | 20.0 | 20.0 | 0.0 | 0.8824633758964767 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 245 | 1225.0 | 1220.0 | 56.79159563547165 | 35.0 | 21.79159563547165 | 20.0 | 20.0 | 0.0 | 0.8819366064018547 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 246 | 1230.0 | 1225.0 | 56.47251481610179 | 40.0 | 16.472514816101793 | 20.0 | 20.0 | 0.0 | 0.8815384153538018 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 247 | 1235.0 | 1230.0 | 57.235594381746395 | 35.0 | 22.235594381746395 | 20.0 | 20.0 | 0.0 | 0.8810009130519497 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 248 | 1240.0 | 1235.0 | 57.46279186245976 | 40.0 | 17.46279186245976 | 20.0 | 20.000000000000007 | 0.0 | 0.8805787839799002 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 249 | 1245.0 | 1240.0 | 58.2257360881691 | 45.0 | 13.2257360881691 | 20.0 | 20.0 | 0.0 | 0.8802590775007736 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 250 | 1250.0 | 1245.0 | 58.9886341660349 | 40.0 | 18.9886341660349 | 0.0 | 0.0 | 0.0 | 0.8798000641549621 | 1.4583333333333333 | 1.4583333333333333 | offline | 0.0 | 0.0 |
| 371 | 1855.0 | 1850.0 | 98.62891935779852 | 65.0 | 29.0 | 0.0 | 0.0 | 4.628919357798523 | 0.8696431085990601 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 4.628919357798523 |
| 372 | 1860.0 | 1855.0 | 98.62893020589509 | 74.93199464494965 | 23.696935560945434 | 0.0 | 0.0 | 0.0 | 0.8690702812128355 | 1.4583333333333333 | 1.4583333333333333 | starting | 0.0 | 0.0 |
| 373 | 1865.0 | 1860.0 | 98.33477065440118 | 72.43199464494965 | 25.90277600945153 | 20.0 | 20.0 | 0.0 | 0.8684441319185819 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 374 | 1870.0 | 1865.0 | 98.33477723410435 | 69.33477723410435 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8677431132506706 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 375 | 1875.0 | 1870.0 | 98.33478235838233 | 69.33478235838233 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8670420945827592 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 376 | 1880.0 | 1875.0 | 98.33478634917402 | 74.33478235838233 | 24.000003990791697 | 20.0 | 20.0 | 0.0 | 0.8664619411059491 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 377 | 1885.0 | 1880.0 | 98.33478945720573 | 78.65073671467692 | 19.684052742528806 | 20.0 | 20.0 | 0.0 | 0.8659861173668916 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 378 | 1890.0 | 1885.0 | 98.33479187774326 | 81.15073671467692 | 17.184055163066333 | 20.0 | 20.0 | 0.0 | 0.8655707262131078 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 379 | 1895.0 | 1890.0 | 98.33479376285977 | 83.65073671467692 | 14.68405704818285 | 20.0 | 20.0 | 0.0 | 0.8652157676575405 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 380 | 1900.0 | 1895.0 | 98.33479523099 | 86.15073671467692 | 12.184058516313073 | 20.0 | 20.0 | 0.0 | 0.8649212417102695 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 381 | 1905.0 | 1900.0 | 98.33479637437097 | 88.0659543562946 | 10.26884201807637 | 20.0 | 20.0 | 0.0 | 0.8646730124015625 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 382 | 1910.0 | 1905.0 | 98.18647726483695 | 83.0659543562946 | 15.120522908542355 | 20.0 | 20.0 | 0.0 | 0.8643075031316497 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 383 | 1915.0 | 1910.0 | 97.69269595833255 | 87.13302155629461 | 10.559674402037942 | 20.0 | 20.0 | 0.0 | 0.8640522435149981 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 384 | 1920.0 | 1915.0 | 97.69269649842748 | 82.13302155629461 | 15.559674942132872 | 20.0 | 20.0 | 0.0 | 0.86367611859772 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 385 | 1925.0 | 1920.0 | 97.68219091905382 | 87.12862172933133 | 10.553569189722495 | 20.0 | 20.0 | 0.0 | 0.8634210065627169 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 386 | 1930.0 | 1925.0 | 97.68219124663796 | 82.12862172933133 | 15.553569517306627 | 20.0 | 20.0 | 0.0 | 0.8630450292322241 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 387 | 1935.0 | 1930.0 | 97.68219150176074 | 87.12862172933133 | 10.553569772429412 | 20.0 | 20.0 | 0.0 | 0.8627899171831354 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 388 | 1940.0 | 1935.0 | 97.68219170045056 | 82.12862172933133 | 15.55356997111923 | 20.0 | 20.0 | 0.0 | 0.8624139398416726 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 389 | 1945.0 | 1940.0 | 96.90474785519035 | 87.09080012933133 | 9.813947725859023 | 20.0 | 20.0 | 0.0 | 0.8621767067188542 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 390 | 1950.0 | 1945.0 | 96.87322997570182 | 82.09080012933133 | 14.78242984637049 | 20.0 | 20.0 | 0.0 | 0.8618193701919785 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 391 | 1955.0 | 1950.0 | 95.90037446955624 | 86.85588894296376 | 9.044485526592482 | 20.0 | 20.0 | 0.0 | 0.861600737323158 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 392 | 1960.0 | 1955.0 | 95.90037454265014 | 86.86126230418357 | 9.039112238466572 | 20.0 | 20.0 | 0.0 | 0.8613822343431404 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 393 | 1965.0 | 1960.0 | 95.90037459957573 | 81.2616369037593 | 14.638737695816431 | 20.0 | 20.0 | 0.0 | 0.8610283712948843 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 394 | 1970.0 | 1965.0 | 95.90037464390942 | 86.86126230418357 | 9.039112339725847 | 20.0 | 20.0 | 0.0 | 0.860809868312419 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 395 | 1975.0 | 1970.0 | 95.9202193451032 | 81.28148164928677 | 14.638737695816431 | 20.0 | 20.0 | 0.0 | 0.860456005264163 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 396 | 1980.0 | 1975.0 | 95.96467142532627 | 83.75 | 12.214671425326273 | 20.0 | 20.0 | 0.0 | 0.8601607393092816 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 397 | 1985.0 | 1980.0 | 96.10755304626802 | 80.85755304626802 | 15.25 | 20.0 | 20.0 | 0.0 | 0.8597921001821903 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 398 | 1990.0 | 1985.0 | 96.25043466257749 | 83.75 | 12.50043466257749 | 20.0 | 20.0 | 0.0 | 0.8594899264561395 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 399 | 1995.0 | 1990.0 | 93.1267907552793 | 78.75 | 14.376790755279302 | 20.0 | 20.0 | 0.0 | 0.8591423954663427 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 400 | 2000.0 | 1995.0 | 93.12679076517148 | 75.37679076517148 | 17.75 | 20.0 | 20.0 | 0.0 | 0.858713323695466 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 401 | 2005.0 | 2000.0 | 93.02803437287552 | 72.77803437287552 | 20.25 | 20.0 | 20.0 | 0.0 | 0.8582238192808037 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 402 | 2010.0 | 2005.0 | 93.02803437887543 | 70.27803437887543 | 22.75 | 20.0 | 20.0 | 0.0 | 0.857673882222356 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 403 | 2015.0 | 2010.0 | 93.02803438354817 | 75.27803437887543 | 17.750000004672742 | 20.0 | 20.0 | 0.0 | 0.8572448104513662 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 404 | 2020.0 | 2015.0 | 93.0280343871873 | 78.75 | 14.278034387187304 | 20.0 | 20.0 | 0.0 | 0.8568996667049352 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 405 | 2025.0 | 2020.0 | 93.02803439002146 | 81.25 | 11.77803439002146 | 20.0 | 20.0 | 0.0 | 0.8566149556022212 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 406 | 2030.0 | 2025.0 | 92.7779915922287 | 76.25 | 16.5279915922287 | 20.0 | 20.0 | 0.0 | 0.8562154235108682 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 407 | 2035.0 | 2030.0 | 92.6225027939477 | 81.25 | 11.372502793947703 | 20.0 | 20.0 | 0.0 | 0.85594051534675 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 408 | 2040.0 | 2035.0 | 92.61619919528647 | 76.25 | 16.36619919528647 | 20.0 | 20.0 | 0.0 | 0.8555448942723136 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 409 | 2045.0 | 2040.0 | 92.61619919632909 | 81.25 | 11.366199196329092 | 20.0 | 20.0 | 0.0 | 0.8552701384854231 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 410 | 2050.0 | 2045.0 | 91.4185151971411 | 76.25 | 15.168515197141105 | 20.0 | 20.0 | 0.0 | 0.8549034690951578 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 411 | 2055.0 | 2050.0 | 91.41851519777349 | 71.25 | 20.168515197773488 | 20.0 | 20.0 | 0.0 | 0.8544159344173062 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 412 | 2060.0 | 2055.0 | 91.418515198266 | 68.668515198266 | 22.75 | 20.0 | 20.0 | 0.0 | 0.8538659973588586 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 413 | 2065.0 | 2060.0 | 91.41851519864954 | 66.16851519864954 | 25.25 | 20.0 | 20.0 | 0.0 | 0.8532556276566254 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 414 | 2070.0 | 2065.0 | 91.42135967577128 | 63.671359675771285 | 27.75 | 20.0 | 20.0 | 0.0 | 0.8525848253106069 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 415 | 2075.0 | 2070.0 | 91.43481886255935 | 62.434818862559354 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8518838066426954 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 416 | 2080.0 | 2075.0 | 91.45545586382946 | 62.45545586382946 | 29.0 | 20.0 | 20.0 | 0.0 | 0.851182787974784 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 417 | 2085.0 | 2080.0 | 91.14759121395522 | 62.147591213955224 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8504817693068726 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 418 | 2090.0 | 2085.0 | 91.15328841436036 | 62.15328841436036 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8497807506389612 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 419 | 2095.0 | 2090.0 | 91.1577253984972 | 67.15328841436036 | 24.004436984136845 | 20.0 | 20.0 | 0.0 | 0.8492004900031479 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 420 | 2100.0 | 2095.0 | 91.16118092521745 | 72.15328841436036 | 19.00789251085709 | 20.0 | 20.0 | 0.0 | 0.8487410111242596 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 421 | 2105.0 | 2100.0 | 91.1638720921331 | 75.0 | 16.163872092133104 | 20.0 | 20.0 | 0.0 | 0.8483502809145246 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 422 | 2110.0 | 2105.0 | 91.16596797503439 | 77.5 | 13.665967975034391 | 20.0 | 20.0 | 0.0 | 0.848019932684677 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 423 | 2115.0 | 2110.0 | 91.16760025027914 | 80.0 | 11.167600250279136 | 20.0 | 20.0 | 0.0 | 0.8477499776415317 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 424 | 2120.0 | 2115.0 | 91.16887146751793 | 82.5 | 8.668871467517931 | 20.0 | 20.0 | 0.0 | 0.8475404245129642 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 425 | 2125.0 | 2120.0 | 91.16986149249895 | 83.75 | 7.419861492498953 | 20.0 | 20.0 | 0.0 | 0.8473610637743588 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 426 | 2130.0 | 2125.0 | 91.17063252472944 | 78.75 | 12.420632524729442 | 20.0 | 20.0 | 0.0 | 0.8470608191099759 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 427 | 2135.0 | 2130.0 | 91.20771217190098 | 73.75 | 17.45771217190098 | 20.0 | 20.0 | 0.0 | 0.8466388128295784 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 428 | 2140.0 | 2135.0 | 91.27728595992173 | 71.02728595992173 | 20.25 | 20.0 | 20.0 | 0.0 | 0.8461493084149161 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 429 | 2145.0 | 2140.0 | 91.5403001697585 | 68.7903001697585 | 22.75 | 20.0 | 20.0 | 0.0 | 0.8455993713564685 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 430 | 2150.0 | 2145.0 | 91.62042941666456 | 66.37042941666456 | 25.25 | 20.0 | 20.0 | 0.0 | 0.8449890016542353 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 431 | 2155.0 | 2150.0 | 91.88330032109714 | 64.13330032109714 | 27.75 | 20.0 | 20.0 | 0.0 | 0.8443181993082167 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 432 | 2160.0 | 2155.0 | 92.14612236164221 | 63.14612236164221 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8436171806403052 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 433 | 2165.0 | 2160.0 | 92.24207495806453 | 63.242074958064535 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8429161619723938 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 434 | 2170.0 | 2165.0 | 92.26649875037428 | 63.26649875037428 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8422151433044824 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 435 | 2175.0 | 2170.0 | 92.29089946101793 | 63.29089946101793 | 29.0 | 20.0 | 20.0 | 0.0 | 0.841514124636571 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 436 | 2180.0 | 2175.0 | 92.29096275119751 | 63.29096275119751 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8408131059686597 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 437 | 2185.0 | 2180.0 | 92.29101204163892 | 63.29101204163892 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8401120873007482 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 438 | 2190.0 | 2185.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8394110686328368 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 439 | 2195.0 | 2190.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8387100499649254 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 440 | 2200.0 | 2195.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.838009031297014 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 441 | 2205.0 | 2200.0 | 91.98163679999999 | 62.98163679999999 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8373080126291026 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 442 | 2210.0 | 2205.0 | 91.98163679999999 | 67.98163679999999 | 24.0 | 20.0 | 20.0 | 0.0 | 0.8367278592487621 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 443 | 2215.0 | 2210.0 | 91.98163679999999 | 72.5 | 19.48163679999999 | 20.0 | 20.0 | 0.0 | 0.8362569285219252 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 444 | 2220.0 | 2215.0 | 91.98163679999999 | 75.0 | 16.98163679999999 | 20.0 | 20.0 | 0.0 | 0.8358464304388739 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 445 | 2225.0 | 2220.0 | 91.98163679999999 | 77.5 | 14.48163679999999 | 20.0 | 20.0 | 0.0 | 0.8354963649996079 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 446 | 2230.0 | 2225.0 | 91.98686561768936 | 80.0 | 11.98686561768936 | 20.0 | 20.0 | 0.0 | 0.8352066058076166 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 447 | 2235.0 | 2230.0 | 92.01160676944568 | 82.5 | 9.511606769445677 | 20.0 | 20.0 | 0.0 | 0.8349766811901265 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 448 | 2240.0 | 2235.0 | 92.04954243321205 | 83.75 | 8.299542433212054 | 20.0 | 20.0 | 0.0 | 0.8347760558735471 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 449 | 2245.0 | 2240.0 | 91.86926546069566 | 78.75 | 13.119265460695658 | 20.0 | 20.0 | 0.0 | 0.8344589231150219 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 450 | 2250.0 | 2245.0 | 91.94209276844316 | 74.19209276844316 | 17.75 | 20.0 | 20.0 | 0.0 | 0.8340298513441451 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 451 | 2255.0 | 2250.0 | 92.01793884627267 | 71.76793884627267 | 20.25 | 20.0 | 20.0 | 0.0 | 0.8335403469294829 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 452 | 2260.0 | 2255.0 | 92.18276080201657 | 69.43276080201657 | 22.75 | 20.0 | 20.0 | 0.0 | 0.8329904098710351 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 453 | 2265.0 | 2260.0 | 92.3451953878579 | 67.0951953878579 | 25.25 | 20.0 | 20.0 | 0.0 | 0.832380040168802 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 454 | 2270.0 | 2265.0 | 92.50137809366883 | 64.75137809366883 | 27.75 | 20.0 | 20.0 | 0.0 | 0.8317092378227834 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 455 | 2275.0 | 2270.0 | 92.65582157511143 | 63.65582157511143 | 29.0 | 20.0 | 20.0 | 0.0 | 0.831008219154872 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 456 | 2280.0 | 2275.0 | 92.71469988058739 | 63.71469988058739 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8303072004869605 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 457 | 2285.0 | 2280.0 | 92.73214729315984 | 63.73214729315984 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8296061818190491 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 458 | 2290.0 | 2285.0 | 92.748773154313 | 63.748773154313 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8289051631511377 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 459 | 2295.0 | 2290.0 | 92.75102585724413 | 63.75102585724413 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8282041444832263 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 460 | 2300.0 | 2295.0 | 92.75278026405093 | 63.75278026405093 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8275031258153149 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 461 | 2305.0 | 2300.0 | 92.75414659744588 | 63.75414659744588 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8268021071474034 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 462 | 2310.0 | 2305.0 | 92.75521069896381 | 63.75521069896381 | 29.0 | 20.0 | 20.0 | 0.0 | 0.826101088479492 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 463 | 2315.0 | 2310.0 | 92.75603942205923 | 68.75521069896381 | 24.000828723095424 | 20.0 | 20.0 | 0.0 | 0.8255209150663806 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 464 | 2320.0 | 2315.0 | 92.7566848322549 | 72.5 | 20.256684832254905 | 20.0 | 20.0 | 0.0 | 0.8250312490588837 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 465 | 2325.0 | 2320.0 | 92.75718747822069 | 75.0 | 17.757187478220686 | 20.0 | 20.0 | 0.0 | 0.8246020035446826 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 466 | 2330.0 | 2325.0 | 92.75757893929246 | 77.5 | 15.257578939292458 | 20.0 | 20.0 | 0.0 | 0.8242331812114558 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 467 | 2335.0 | 2330.0 | 92.75788380948168 | 80.0 | 12.757883809481683 | 20.0 | 20.0 | 0.0 | 0.8239247841523699 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 468 | 2340.0 | 2335.0 | 92.7581212426238 | 82.5 | 10.258121242623801 | 20.0 | 20.0 | 0.0 | 0.8236768139975845 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 469 | 2345.0 | 2340.0 | 92.76125889984773 | 77.5 | 15.261258899847732 | 20.0 | 20.0 | 0.0 | 0.8233079027084595 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 470 | 2350.0 | 2345.0 | 91.46212438426103 | 82.5 | 8.962124384261031 | 20.0 | 20.0 | 0.0 | 0.8230912607602696 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 471 | 2355.0 | 2350.0 | 91.48365903221573 | 83.75 | 7.733659032215726 | 20.0 | 20.0 | 0.0 | 0.8229043145756888 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 472 | 2360.0 | 2355.0 | 91.51009139215456 | 78.75 | 12.760091392154564 | 20.0 | 20.0 | 0.0 | 0.82259586415258 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 473 | 2365.0 | 2360.0 | 91.53965248579318 | 83.75 | 7.789652485793184 | 20.0 | 20.0 | 0.0 | 0.8224075644350254 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 474 | 2370.0 | 2365.0 | 91.57486390235664 | 78.75 | 12.82486390235664 | 20.0 | 20.0 | 0.0 | 0.8220975482623022 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 475 | 2375.0 | 2370.0 | 91.62540743352896 | 84.53825597072336 | 7.087151462805608 | 20.0 | 20.0 | 0.0 | 0.82192623014238 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 476 | 2380.0 | 2375.0 | 91.76578575626205 | 78.75 | 13.015785756262048 | 20.0 | 20.0 | 0.0 | 0.8216115988047016 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 477 | 2385.0 | 2380.0 | 91.90262649775376 | 84.53825597072336 | 7.3643705270304025 | 20.0 | 20.0 | 0.0 | 0.8214335794523959 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 478 | 2390.0 | 2385.0 | 92.03847955344402 | 78.75 | 13.28847955344402 | 20.0 | 20.0 | 0.0 | 0.8211123562718744 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 479 | 2395.0 | 2390.0 | 92.1735633986587 | 84.53825597072336 | 7.635307427935345 | 20.0 | 20.0 | 0.0 | 0.8209277875462805 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 480 | 2400.0 | 2395.0 | 92.22396516215264 | 78.75 | 13.473965162152638 | 20.0 | 20.0 | 0.0 | 0.8206020806114717 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 481 | 2405.0 | 2400.0 | 92.27580312924269 | 74.52580312924269 | 17.75 | 20.0 | 20.0 | 0.0 | 0.8201730088405949 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 482 | 2410.0 | 2405.0 | 92.3743212803654 | 72.1243212803654 | 20.25 | 20.0 | 20.0 | 0.0 | 0.8196835044259326 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 483 | 2415.0 | 2410.0 | 92.64847358810152 | 69.89847358810152 | 22.75 | 20.0 | 20.0 | 0.0 | 0.8191335673674849 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 484 | 2420.0 | 2415.0 | 92.92240551334659 | 67.67240551334659 | 25.25 | 20.0 | 20.0 | 0.0 | 0.8185231976652517 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 485 | 2425.0 | 2420.0 | 93.19616580453507 | 65.44616580453507 | 27.75 | 20.0 | 20.0 | 0.0 | 0.8178523953192331 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 486 | 2430.0 | 2425.0 | 93.46979242698585 | 64.46979242698585 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8171513766513218 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 487 | 2435.0 | 2430.0 | 93.5698103036746 | 64.5698103036746 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8164503579834103 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 488 | 2440.0 | 2435.0 | 93.59538797284237 | 64.59538797284237 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8157493393154989 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 489 | 2445.0 | 2440.0 | 93.62090250136932 | 64.62090250136932 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8150483206475875 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 490 | 2450.0 | 2445.0 | 93.62107563369351 | 64.62107563369351 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8143473019796761 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 491 | 2455.0 | 2450.0 | 9.625740469283178 | 59.62107563369351 | -30.0 | 20.0 | 39.99533516441033 | 0.0 | 0.8150123027918912 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 492 | 2460.0 | 2455.0 | 9.62584547934599 | 54.62107563369351 | -30.0 | 20.0 | 34.99523015434752 | 0.0 | 0.8156773036041064 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 493 | 2465.0 | 2460.0 | 9.628562585380582 | 49.62107563369351 | -30.0 | 20.0 | 29.992513048312926 | 0.0 | 0.8163423044163216 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 494 | 2470.0 | 2465.0 | 9.641095817688438 | 44.62107563369351 | -30.0 | 20.0 | 24.97997981600507 | 0.0 | 0.8170073052285367 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 495 | 2475.0 | 2470.0 | 9.660264995468067 | 39.62107563369351 | -29.96081063822544 | 20.0 | 20.0 | 0.0 | 0.8176714373421716 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 496 | 2480.0 | 2475.0 | 9.683816550763026 | 36.25 | -26.566183449236974 | 20.0 | 20.0 | 0.0 | 0.818260321794545 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 497 | 2485.0 | 2480.0 | 9.71016919975448 | 35.0 | -25.289830800245518 | 20.0 | 20.0 | 0.0 | 0.8188209137286433 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 498 | 2490.0 | 2485.0 | 9.725162477892692 | 35.0 | -25.27483752210731 | 20.0 | 20.0 | 0.0 | 0.8193811733113369 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 499 | 2495.0 | 2490.0 | 9.733497711600334 | 35.0 | -25.266502288399664 | 20.0 | 20.0 | 0.0 | 0.8199412481294577 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 500 | 2500.0 | 2495.0 | 9.746063644827895 | 35.0 | -25.253936355172105 | 20.0 | 20.0 | 0.0 | 0.8205010444023849 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 501 | 2505.0 | 2500.0 | 9.775768314362358 | 35.0 | -25.22423168563764 | 20.0 | 20.0 | 0.0 | 0.8210601822210001 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 502 | 2510.0 | 2505.0 | 9.81831625907733 | 35.0 | -25.181683740922672 | 20.0 | 20.0 | 0.0 | 0.8216183768923554 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 503 | 2515.0 | 2510.0 | 9.869245266688878 | 35.0 | -25.13075473331112 | 20.0 | 20.0 | 0.0 | 0.8221754426359966 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 504 | 2520.0 | 2515.0 | 9.925438790825968 | 35.0 | -25.074561209174032 | 20.0 | 20.0 | 0.0 | 0.822731262754998 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 505 | 2525.0 | 2520.0 | 9.957790857471862 | 35.0 | -25.042209142528137 | 20.0 | 20.0 | 0.0 | 0.8232863657356462 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 506 | 2530.0 | 2525.0 | 9.976091424751935 | 35.0 | -25.023908575248065 | 20.0 | 20.0 | 0.0 | 0.8238410630532242 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 507 | 2535.0 | 2530.0 | 9.991657284657505 | 35.0 | -25.008342715342494 | 20.0 | 20.0 | 0.0 | 0.8243954153271529 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 508 | 2540.0 | 2535.0 | 10.000525054058311 | 35.0 | -24.99947494594169 | 20.0 | 20.0 | 0.0 | 0.824949571031953 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 509 | 2545.0 | 2540.0 | 9.74478130936912 | 35.0 | -25.25521869063088 | 20.0 | 20.0 | 0.0 | 0.8255093957300178 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 510 | 2550.0 | 2545.0 | 9.750159876855905 | 35.0 | -25.249840123144097 | 20.0 | 20.0 | 0.0 | 0.8260691012030243 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 511 | 2555.0 | 2550.0 | 9.754348709426417 | 35.0 | -25.245651290573583 | 20.0 | 20.0 | 0.0 | 0.8266287138234621 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 512 | 2560.0 | 2555.0 | 9.811891975512484 | 35.0 | -25.188108024487516 | 20.0 | 20.0 | 0.0 | 0.8271870508999438 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 513 | 2565.0 | 2560.0 | 9.936022070894902 | 35.0 | -25.0639779291051 | 20.0 | 20.0 | 0.0 | 0.827742636422617 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 514 | 2570.0 | 2565.0 | 10.328823935296244 | 35.0 | -24.671176064703758 | 20.0 | 20.0 | 0.0 | 0.8282895148266615 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 515 | 2575.0 | 2570.0 | 10.721188120681443 | 35.0 | -24.278811879318557 | 20.0 | 20.0 | 0.0 | 0.8288276958139738 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 516 | 2580.0 | 2575.0 | 11.11321144130614 | 35.0 | -23.88678855869386 | 20.0 | 20.0 | 0.0 | 0.8293571869403986 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 517 | 2585.0 | 2580.0 | 11.504969296188433 | 35.0 | -23.495030703811565 | 20.0 | 20.0 | 0.0 | 0.8298779940904338 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 518 | 2590.0 | 2585.0 | 11.648275299475998 | 35.0 | -23.351724700524002 | 20.0 | 20.0 | 0.0 | 0.8303956246201829 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 519 | 2595.0 | 2590.0 | 9.483438862985025 | 35.0 | -25.516561137014975 | 20.0 | 20.0 | 0.0 | 0.8309612424162182 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 520 | 2600.0 | 2595.0 | 7.739884362689776 | 35.0 | -27.260115637310225 | 20.0 | 20.0 | 0.0 | 0.8315655090508811 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 521 | 2605.0 | 2600.0 | 7.740228203005562 | 35.0 | -27.25977179699444 | 20.0 | 20.0 | 0.0 | 0.8321697680637412 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 522 | 2610.0 | 2605.0 | 7.740495986112748 | 35.0 | -27.259504013887252 | 20.0 | 20.0 | 0.0 | 0.8327740211407353 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 523 | 2615.0 | 2610.0 | 7.740704535806318 | 35.0 | -27.259295464193684 | 20.0 | 20.0 | 0.0 | 0.833378269594872 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 524 | 2620.0 | 2615.0 | 7.740866954470978 | 35.0 | -27.259133045529023 | 20.0 | 20.0 | 0.0 | 0.8339825144487241 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 525 | 2625.0 | 2620.0 | 7.740993446254202 | 35.0 | -27.2590065537458 | 20.0 | 20.0 | 0.0 | 0.8345867564986714 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 526 | 2630.0 | 2625.0 | 7.741091958154029 | 35.0 | -27.25890804184597 | 20.0 | 20.0 | 0.0 | 0.8351909963649357 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 527 | 2635.0 | 2630.0 | 7.741168679298756 | 35.0 | -27.258831320701244 | 20.0 | 20.0 | 0.0 | 0.8357952345305457 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 528 | 2640.0 | 2635.0 | 7.741228429786347 | 35.0 | -27.258771570213653 | 20.0 | 20.0 | 0.0 | 0.8363994713716851 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 529 | 2645.0 | 2640.0 | 7.755008296846206 | 35.0 | -27.244991703153794 | 20.0 | 20.0 | 0.0 | 0.8370034027587316 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 530 | 2650.0 | 2645.0 | 7.78580720401553 | 35.0 | -27.21419279598447 | 20.0 | 20.0 | 0.0 | 0.8376066514358353 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 531 | 2655.0 | 2650.0 | 7.892495908869154 | 35.0 | -27.107504091130846 | 20.0 | 20.0 | 0.0 | 0.8382075351770929 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 532 | 2660.0 | 2655.0 | 8.028212723658532 | 35.0 | -26.971787276341466 | 20.0 | 20.0 | 0.0 | 0.8388054105252817 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 533 | 2665.0 | 2660.0 | 8.254473610144219 | 40.0 | -30.0 | 20.0 | 21.745526389855783 | 0.0 | 0.8394704113374968 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 534 | 2670.0 | 2665.0 | 8.581636771975681 | 45.0 | -30.0 | 20.0 | 26.41836322802432 | 0.0 | 0.840135412149712 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 535 | 2675.0 | 2670.0 | 9.206025877870696 | 50.0 | -30.0 | 20.0 | 30.793974122129306 | 0.0 | 0.8408004129619272 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 536 | 2680.0 | 2675.0 | 9.769977811585745 | 55.0 | -30.0 | 20.0 | 35.23002218841425 | 0.0 | 0.8414654137741423 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 537 | 2685.0 | 2680.0 | 10.251578237923823 | 60.0 | -30.0 | 20.0 | 39.74842176207618 | 0.0 | 0.8421304145863575 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 538 | 2690.0 | 2685.0 | 10.776640126359208 | 64.03156518586077 | -30.0 | 20.0 | 43.25492505950156 | 0.0 | 0.8427954153985727 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 539 | 2695.0 | 2690.0 | 10.974180978323954 | 59.03156518586077 | -30.0 | 20.0 | 38.05738420753681 | 0.0 | 0.8434604162107878 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 540 | 2700.0 | 2695.0 | 11.030234651914899 | 64.03156518586077 | -30.0 | 20.0 | 43.001330533945875 | 0.0 | 0.844125417023003 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 541 | 2705.0 | 2700.0 | 71.08411293218028 | 59.03156518586077 | 12.052547746319505 | 20.0 | 20.0 | 0.0 | 0.8438340700931388 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 542 | 2710.0 | 2705.0 | 71.08943625380347 | 65.20555997172153 | 5.883876282081943 | 20.0 | 20.0 | 0.0 | 0.8436918388133656 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 543 | 2715.0 | 2710.0 | 71.09358206085216 | 59.03156518586077 | 12.062016874991386 | 20.0 | 20.0 | 0.0 | 0.8434002629857094 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 544 | 2720.0 | 2715.0 | 70.38240281862815 | 54.03156518586077 | 16.35083763276738 | 20.0 | 20.0 | 0.0 | 0.8430050132472074 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 545 | 2725.0 | 2720.0 | 70.38491737771244 | 49.03156518586077 | 21.35335219185167 | 20.0 | 20.0 | 0.0 | 0.8424888374365531 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 546 | 2730.0 | 2725.0 | 70.38687571829635 | 45.41844090415712 | 24.96843481413923 | 20.0 | 20.0 | 0.0 | 0.8418852740257516 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 547 | 2735.0 | 2730.0 | 70.38840087547663 | 42.919966061337405 | 27.46843481413923 | 20.0 | 20.0 | 0.0 | 0.8412212779711649 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 548 | 2740.0 | 2735.0 | 70.39155716515423 | 41.391557165154225 | 29.0 | 20.0 | 20.0 | 0.0 | 0.8405202593032535 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 549 | 2745.0 | 2740.0 | 70.40179653570026 | 46.391557165154225 | 24.01023937054603 | 20.0 | 20.0 | 0.0 | 0.8399398584060198 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 550 | 2750.0 | 2745.0 | 70.41679863059312 | 51.391557165154225 | 19.025241465438896 | 20.0 | 20.0 | 0.0 | 0.8394799601498545 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 551 | 2755.0 | 2750.0 | 70.43492304667578 | 56.391557165154225 | 14.043365881521552 | 20.0 | 20.0 | 0.0 | 0.8391404890587079 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 552 | 2760.0 | 2755.0 | 70.46518687838166 | 61.25 | 9.215186878381658 | 20.0 | 20.0 | 0.0 | 0.8389177298162928 | 1.4583333333333333 | 1.4583333333333333 | synchronised | 20.0 | 0.0 |
| 553 | 2765.0 | 2760.0 | 70.52480594467411 | 56.25 | 14.274805944674114 | 0.0 | 0.0 | 0.0 | 0.8385726641111882 | 1.4583333333333333 | 1.4583333333333333 | offline | 0.0 | 0.0 |

### Diesel energy split — distinguish coincidence from attribution
No bus telemetry uniquely labels which source served which load. Thus two quantities are reported separately: (1) binary temporal coincidence with curtailment>0, exactly as requested; (2) an EXPLICIT diesel-last bookkeeping allocation, NOT a measured causal source tracing or a revised dispatch policy.
Definitions, dt=5 s: coincidence energy=sum(D*dt) on C>0 versus C<=0; diesel-last curtailment=sum(min(D,max(C,0))*dt); diesel-last served=sum(D*dt)-diesel-last curtailment. Curtailment-while-on uses D>0, not UNLOADING state with zero aggregate power. All MW seconds are divided by 3600.
```json
{
  "baseline": {
    "ticks": 1440,
    "metrics_identical_to_saved_phase2c": true,
    "diesel_and_soc_identical_every_tick": true,
    "diesel_energy_mwh": 10.0,
    "diesel_energy_on_positive_curtailment_ticks_mwh": 9.277777777777777,
    "diesel_energy_on_zero_curtailment_ticks_mwh": 0.7222222222222222,
    "diesel_last_to_surplus_mwh": 8.862473733149889,
    "diesel_last_to_served_load_mwh": 1.1375262668501112,
    "run_curtailment_mwh": 13.6572470270914,
    "curtailment_while_diesel_positive_mwh": 8.964225162268743,
    "fraction_curtailment_while_diesel_positive": 0.6563713129364012,
    "stop_refusal_count": 296,
    "positive_diesel_ticks": 360,
    "positive_diesel_zero_gap_ticks": 296,
    "bess_discharging_and_diesel_curtailment_ticks": 234,
    "on_bus_unit_output_omitted_from_aggregate_mwh": 0.8166666666666667
  },
  "informed": {
    "ticks": 1440,
    "metrics_identical_to_saved_phase2c": true,
    "diesel_and_soc_identical_every_tick": true,
    "diesel_energy_mwh": 10.0,
    "diesel_energy_on_positive_curtailment_ticks_mwh": 10.0,
    "diesel_energy_on_zero_curtailment_ticks_mwh": 0.0,
    "diesel_last_to_surplus_mwh": 9.991612713085395,
    "diesel_last_to_served_load_mwh": 0.008387286914604886,
    "run_curtailment_mwh": 10.361665377960906,
    "curtailment_while_diesel_positive_mwh": 10.29349820740888,
    "fraction_curtailment_while_diesel_positive": 0.9934212148273949,
    "stop_refusal_count": 355,
    "positive_diesel_ticks": 360,
    "positive_diesel_zero_gap_ticks": 355,
    "bess_discharging_and_diesel_curtailment_ticks": 257,
    "on_bus_unit_output_omitted_from_aggregate_mwh": 0.0
  }
}
```
Rounded interpretation: conventional diesel-last served 1.137526267 MWh, curtailed 8.862473733 MWh; informed served 0.008387287, curtailed 9.991612713. Binary overlap is 9.277777778/10 MWh conventional and 10/10 MWh informed, which is NOT the same as saying all that overlapped energy was curtailed.
Of all curtailment, 65.63713129364012% occurs while conventional diesel aggregate output is positive; 99.34212148273949% for informed. The additional 10 MWh equals the earlier measured increase in curtailment plus reduction in unserved energy (original comparator table retained above).

### Why totals agree but timelines do not
NOT identical behavior tick-by-tick: first start commands occur at tick 66 conventional versus tick 68 informed; first synchronous outputs at 68 versus 70; first accepted stops at 248 versus 250. Second starts/sync/stops coincide at 371/373/553. Exactly four ticks have different aggregate diesel outputs across arms (68,69,248,249).
Identical totals arise from the same configured 20 MW block and two successful 900-second synchronized operating intervals: 360 positive-output ticks, 10.0 MWh per arm. Turbine commitment can alter the residual gap and therefore timing, but cannot command a different diesel output. The fuel counter reports 115.63888888918154 gal per arm. Fuel burn occurs before the stop decision (P/core/diesel_fleet.py:198–200,363–380), so stop-boundary fuel is included even when the final tick snapshot is zero.

### Classification and fix directions (READ-ONLY; no fix)
1. Expected configured backup behavior / scenario-configuration issue, not a balance-ledger defect: f_block=1.0 plus min_run=900 s forces full output after deficits disappear; arbitration precedes diesel (P/core/simulation_core.py:1941–1970), and the existing surplus sink curtails the resulting achieved surplus (:2994–3037). This explains the high curtailment. Authority metadata does not disable physical backup. No replacement settings are proposed here.
2. Genuine model-accounting inconsistency: DieselModule.is_on_bus includes UNLOADING (P/core/asset_modules.py:1404–1406) and advance continues a positive unload curve (:1501–1512), but coordinator output (:114–123) AND fuel (:368–370) exclude UNLOADING. Conventional episode 2 has 49 ticks (553–601) with on-bus unit output omitted from the fleet aggregate: 0.8166666666666667 MWh; informed has zero such retained-unloading ticks because it finishes immediately. Physical_balance passes because the ledger consumes the already-filtered fleet value (P/core/simulation_core.py:1969,2999,3460), so that is not proof the unit/fleet representations agree.
Fix direction for 2: reconcile one consistent on-bus diesel output population across fleet aggregation, fuel accounting and the physical ledger throughout unloading.
3. Genuine lifecycle timing inconsistency: restore_elapsed_s increases even when command_stop returns a minimum-run refusal (P/core/diesel_fleet.py:232–234 and :328–331). When stop finally succeeds, a previously accumulated timer can immediately call complete_unloading (:236–240), bypassing the unit's configured local unload ramp (P/core/asset_modules.py:1501–1512). At first stops restore-before is 480 s conventional / 815 s informed; second stops 50 / 900 s. Both informed unloads and conventional's first finish immediately. Conventional's second completes after only 245 s of unit unloading, while cooldown_s is 300 s: the restore timer was already 55 s immediately after stop acceptance (50 s before that step plus its 5 s increment).
Fix direction for 3: define and enforce separate restoration/minimum-run/unloading completion clocks so a refused stop cannot count as time spent unloading or skip the configured unload transition.
No change to diesels, dispatch, commitment, costs, reserve floors, frequency, protection or any scenario was made in this diagnosis. The omitted-unloading MWh is NOT silently added to the certified harness metrics above. These inconsistencies need a separate reviewed fix; this phase only reports them.

## End-of-phase integrity
The only repository source edit after 52568e3 is the approved four-hash/comment refresh, committed alone as ed7da7011b6b9f3348e035d8fa1e2afa9b6f8daa. Report and failing-ID list are committed separately. All scratch scripts, JUnit XML and raw diagnosis CSV/JSON stay in T.
Documentation-only tracking notes in .agents/memory/ignored-simulator-source.md and its MEMORY.md index are updated with the automatic-checkpoint caveat: a historical uncommitted status can become checkpointed code without the scientific validation gate passing. These are not application/configuration changes.
No publish, deploy, push or Phase 3. No production source changed in this finishing phase. After the tool session disconnected, the existing artifacts/gridsignal: web development workflow was started again: Application startup complete; GET / returned 200. Literal log: /tmp/logs/artifactsgridsignal_web_20261021_161542_495_4b4c09a2.log. The separate Node API and mockup workflows were not started.
STOP — END OF PHASE 2c.
