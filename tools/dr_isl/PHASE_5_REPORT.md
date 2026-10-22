# DR-2026-10-20-ISLAND-COLLAPSE — Phase 5 / D3 (IMPL-ISL-3)

Base: fd87fc75b995f19556f598cdc5b0f443a4edce75.
Evidence directory: tools/dr_isl/phase5/. No scenario JSON or physical control changes.

## STOP — Phase 5 is not finished
5.7 failed its zero-added-failure gate. No implementation/UI/test commits were made.
The GPU failure is pre-existing sampling sensitivity, but Phase 5 provided no waiver.
The already-failing API-static test also reports a new candidate-only core import; it is not fixed here.
Main application code is restored to fd87fc7; all 15 candidate files are verified in the stash.
```json
{
  "state": "STOPPED",
  "gate": "5.7 added failure",
  "reason": "GPU profile added failure reproduced at base in preceding order (IMPL-SSH-07); no Phase 5 waiver. Existing API-static failing node also gains a new api/schemas.py core-import violation.",
  "stash": "3b856fd30d37320f6d1f48ac04c342261068ced6",
  "stash_ref": "stash@{0}",
  "head_before_report": "fd87fc75b995f19556f598cdc5b0f443a4edce75",
  "application_tracked_diff_vs_base_empty": true,
  "candidate_file_count": 15,
  "candidate_stash_hashes_all_verified": true,
  "ui_restoration": "Existing ignored frontend files restored by reversing only D3 edits; pre-edit byte hashes were not captured. See UI_PATCH_REVERSAL.diff and UI_RESTORATION_NOTE.json.",
  "implementation_commits": [],
  "ui_commits": [],
  "test_commits": [],
  "phase6_started": false
}
```

## 5.1–5.4 Candidate implementation (not active; stashed after the STOP)
- core/frequency_reporting.py contains the reporting band and one resolved-protection predicate.
- TickResult flags are stamped together at final evaluate_tick construction. No frequency assignment/clamp was added.
- runtime/run_manager.py carries both flags in the existing serializer used by WebSocket/REST.
- runtime/persistence.py::_tick_to_json uses dataclasses.asdict: both flags persist in complete tick_json; no table migration.
- ScenarioSpec logs a non-rejecting warning. Factory-resolved SiteConfig produces the same structured build warning in metadata and the existing run-start response.
- protection_configured means ANY specified UF/OF/UFLS/81U threshold, including advisory thresholds; it does not claim complete trip coverage. Delays alone do not enable it.
- Frontend Forecast Quality greys invalid current-frequency readings and shows the exact requested explanation. Opening/inner layouts show the unprotected-island notice.
- New payload flags are optional in TypeScript only for legacy saved payloads; every newly produced tick includes both.
- MetricsCollector adds three metrics. Identity-only frequency_reporting_metrics_version=1 resets old caches. compare_runs conditions are not edited.

## 5.5 Focused tests
TC-ISL-07a–g already names staging-event tests. TC-ISL-08a–d is used here.
TC-ISL-18 initially counted ALL build warnings: failures 2 vs 1 and 1 vs 0 after the additive D3 warning.
Its warning list now selects the D9b reserve-warning code only; every existing floor/dispatch assertion is retained. TC-ISL-08d independently asserts D3.
Initial output: phase5/FOCUSED_ATTEMPT1.txt/XML. Final output: phase5/FOCUSED.txt/XML.

```text
................................................                         [100%]
48 passed in 348.08s (0:05:48)
```
Frontend focused output: phase5/UI_TESTS.txt; build/type-check output: phase5/UI_BUILD.txt.

## 5.6 V1/V2: raw physical fields, hashes and validity
Pinned seeder-path app runs / native study probe and arm configuration reuse tools/dr_isl/baseline_runner.py unchanged.
Pinning and output-only hooks are inherited from phase4/stream_worker.py. No full per-tick disk exports.
Hash contract: compact sorted-key JSON + LF per raw tick; the four established nonphysical exclusions are retained; ONLY the two new reporting flags are additionally excluded.
Established nonphysical exclusions: advisory_telemetry, fabric_modal, wall_stamp_utc, insufficient_reserve_proposal_id.
Compact study rows are also compared with only those two new keys removed. Every old study metric is compared recursively.

| Scenario / arm | ticks | protection configured | invalid ticks / fraction | first invalid: tick; time; Hz | min / max Hz | physical hash |
|---|---:|---|---|---|---|---|
| scenario-uneven-multisched-01 / baseline | 1440 | False | 700 / 0.4861111111111111 | {"tick": 67, "sim_time_seconds": 335.0, "frequency_hz": 40.909530078118486} | -5.000866893367675 / 176.430848113831 | 90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1 |
| scenario-uneven-multisched-01 / informed | 1440 | False | 614 / 0.4263888888888889 | {"tick": 123, "sim_time_seconds": 615.0, "frequency_hz": 66.19487030675623} | 59.534837314959205 / 169.8277840657461 | ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6 |
| scenario-h1-k8s-ray-24h / baseline | 17280 | False | 13598 / 0.7869212962962963 | {"tick": 213, "sim_time_seconds": 1065.0, "frequency_hz": 70.13551986008387} | 17.23372983198947 / 224.93353102420852 | 57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b |
| scenario-h1-k8s-ray-24h / informed | 17280 | False | 13712 / 0.7935185185185185 | {"tick": 213, "sim_time_seconds": 1065.0, "frequency_hz": 70.13551986008387} | 48.666827290428756 / 224.93353102420852 | 60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9 |
| scenario-h2-slurm-24h / baseline | 17280 | False | 16802 / 0.9723379629629629 | {"tick": 174, "sim_time_seconds": 870.0, "frequency_hz": 70.407865020299} | -225.278937529193 / 245.96773016794788 | f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1 |
| scenario-h2-slurm-24h / informed | 17280 | False | 16955 / 0.9811921296296297 | {"tick": 174, "sim_time_seconds": 870.0, "frequency_hz": 70.407865020299} | 60.0 / 250.44034654726377 | b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb |
| S10_mit_supercloud_2021-08-11 / app | 17280 | False | 7264 / 0.4203703703703704 | {"tick": 1, "sim_time_seconds": 5.0, "frequency_hz": 71.14198664583199} | -729.1075118080669 / 998.9330534505464 | 8ba0dec0459ca09b9df4ea6fa17bd72fa16038220f425b0a8dd499bfa87557ab |
| demo-islanded-ramp / app | 2160 | False | 103 / 0.047685185185185185 | {"tick": 136, "sim_time_seconds": 680.0, "frequency_hz": 53.373055059038585} | -127.48961154607643 / 60.0 | f49f71f1573f1f9a22fff6d560eb5a25a380e4088ecccbe12cf6a560964f822a |
| scenario-equinix-sj-1 / app | 720 | True | 0 / 0.0 | null | 60.0 / 60.0 | 328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84 |
| scenario-turbine-01 / app | 720 | False | 443 / 0.6152777777777778 | {"tick": 278, "sim_time_seconds": 1390.0, "frequency_hz": 73.5537530660913} | 60.0 / 305.12517226604007 | 006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a |
| scenario-hybrid-ai-100mw-addendum-i / app | 120 | False | 78 / 0.65 | {"tick": 1, "sim_time_seconds": 5.0, "frequency_hz": -20.29765039999966} | -218.79606450000827 / 285.92631259085584 | 9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a |
| scenario-100mw-fuel-cell-bess-diesel / app | 252 | False | 0 / 0.0 | null | 60.0 / 60.0 | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b |
| scenario-fc100-islanded-v2 / app | 264 | False | 0 / 0.0 | null | 60.0 / 60.0 | d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3 |
| scenario-fc100-islanded-zero-hot-v2 / app | 264 | False | 214 / 0.8106060606060606 | {"tick": 46, "sim_time_seconds": 230.0, "frequency_hz": 39.39674952027191} | -82.80435199997717 / 60.0 | d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2 |

### scenario-uneven-multisched-01 / baseline: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 27,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": true,
  "added_metrics": {
    "invalid_frequency_tick_count": 700,
    "protection_configured": false,
    "invalid_frequency_fraction": 0.4861111111111111
  }
}
```
Evidence: tools/dr_isl/phase5/scenario-uneven-multisched-01_baseline.json (both complete 27-metric tables and run records).

### scenario-uneven-multisched-01 / informed: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 27,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": true,
  "added_metrics": {
    "invalid_frequency_tick_count": 614,
    "protection_configured": false,
    "invalid_frequency_fraction": 0.4263888888888889
  }
}
```
Evidence: tools/dr_isl/phase5/scenario-uneven-multisched-01_informed.json (both complete 27-metric tables and run records).

### scenario-h1-k8s-ray-24h / baseline: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 27,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": true,
  "added_metrics": {
    "invalid_frequency_tick_count": 13598,
    "protection_configured": false,
    "invalid_frequency_fraction": 0.7869212962962963
  }
}
```
Evidence: tools/dr_isl/phase5/scenario-h1-k8s-ray-24h_baseline.json (both complete 27-metric tables and run records).

### scenario-h1-k8s-ray-24h / informed: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 27,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": true,
  "added_metrics": {
    "invalid_frequency_tick_count": 13712,
    "protection_configured": false,
    "invalid_frequency_fraction": 0.7935185185185185
  }
}
```
Evidence: tools/dr_isl/phase5/scenario-h1-k8s-ray-24h_informed.json (both complete 27-metric tables and run records).

### scenario-h2-slurm-24h / baseline: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 27,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": true,
  "added_metrics": {
    "invalid_frequency_tick_count": 16802,
    "protection_configured": false,
    "invalid_frequency_fraction": 0.9723379629629629
  }
}
```
Evidence: tools/dr_isl/phase5/scenario-h2-slurm-24h_baseline.json (both complete 27-metric tables and run records).

### scenario-h2-slurm-24h / informed: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 27,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": true,
  "added_metrics": {
    "invalid_frequency_tick_count": 16955,
    "protection_configured": false,
    "invalid_frequency_fraction": 0.9811921296296297
  }
}
```
Evidence: tools/dr_isl/phase5/scenario-h2-slurm-24h_informed.json (both complete 27-metric tables and run records).

### S10_mit_supercloud_2021-08-11 / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/S10_mit_supercloud_2021-08-11_app.json (both complete 27-metric tables and run records).

### demo-islanded-ramp / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/demo-islanded-ramp_app.json (both complete 27-metric tables and run records).

### scenario-equinix-sj-1 / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/scenario-equinix-sj-1_app.json (both complete 27-metric tables and run records).

### scenario-turbine-01 / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/scenario-turbine-01_app.json (both complete 27-metric tables and run records).

### scenario-hybrid-ai-100mw-addendum-i / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/scenario-hybrid-ai-100mw-addendum-i_app.json (both complete 27-metric tables and run records).

### scenario-100mw-fuel-cell-bess-diesel / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/scenario-100mw-fuel-cell-bess-diesel_app.json (both complete 27-metric tables and run records).

### scenario-fc100-islanded-v2 / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/scenario-fc100-islanded-v2_app.json (both complete 27-metric tables and run records).

### scenario-fc100-islanded-zero-hot-v2 / app: comparison
```json
{
  "passed": true,
  "first_difference": null,
  "physical_identical": true,
  "existing_metrics_count": 0,
  "existing_metric_differences": {},
  "compact_identical_excluding_new_flags": null,
  "added_metrics": null
}
```
Evidence: tools/dr_isl/phase5/scenario-fc100-islanded-zero-hot-v2_app.json (both complete 27-metric tables and run records).

### Published/certified records explicitly flagged
The base-demo published record and H1/H2 reference records contain invalid-frequency ticks wherever their table count is nonzero.
These are pre-existing trajectories, not newly altered frequency. A compare_runs PASS is NOT a frequency-validity certificate.
OPEN-ISL-3 remains deferred: no acceptance/trip rule was added.

### Metric identity cache reset (provenance fixed for the version-only comparison)
```json
[
  {
    "scenario": "scenario-uneven-multisched-01",
    "arm": "baseline",
    "old": "9c0da2958408fbbb9355a60b29d123903954a1859114832b894d6fc87140bef1",
    "new": "130ab8c5b564cfddc9d3efc9c22359f0fad10a42a068f2edac876a315dd0c6fa",
    "reporting_version": 1,
    "fixed_engine_commit": "fd87fc7",
    "fixed_harness_commit": "ae49aaa"
  },
  {
    "scenario": "scenario-uneven-multisched-01",
    "arm": "informed",
    "old": "3f8e22a01c22915399621bd5d3ddd50121c52ffe2e1f0e30c6582641731be9f5",
    "new": "a04be24dcdf14ffc7a9f22e08a3a8b8abe905bf955906f6727273f9dff0dfe4a",
    "reporting_version": 1,
    "fixed_engine_commit": "fd87fc7",
    "fixed_harness_commit": "ae49aaa"
  },
  {
    "scenario": "scenario-h1-k8s-ray-24h",
    "arm": "baseline",
    "old": "4387d793abc1698f1eeb40141652502eacf9298a3b40bc09e2eb59fa626d6d1a",
    "new": "82140afc1a2f3a2f8b0729ee694c073890b6f2f1a5f4ad6e29de70d3c45c2e45",
    "reporting_version": 1,
    "fixed_engine_commit": "fd87fc7",
    "fixed_harness_commit": "ae49aaa"
  },
  {
    "scenario": "scenario-h1-k8s-ray-24h",
    "arm": "informed",
    "old": "0afa6d3b4e104f7477be5011ea30d8359d7f02e076b64bf13c8276f8f28b5b3a",
    "new": "58f1102a6822295259eaff2ff776f1c88b7d3e2b195a42c39fb8058194944782",
    "reporting_version": 1,
    "fixed_engine_commit": "fd87fc7",
    "fixed_harness_commit": "ae49aaa"
  },
  {
    "scenario": "scenario-h2-slurm-24h",
    "arm": "baseline",
    "old": "aecf35061701cdc73f67be7c0065e639fefcce00ed60e7bb681aae18f6158f64",
    "new": "f25e4ee56e2cd731a3051b9fe3af09e0d4040d04b91c3992bc3aac1d8a8a25ab",
    "reporting_version": 1,
    "fixed_engine_commit": "fd87fc7",
    "fixed_harness_commit": "ae49aaa"
  },
  {
    "scenario": "scenario-h2-slurm-24h",
    "arm": "informed",
    "old": "08393d79ee19e310ef512b9ad5e7b48fa926661cc69107000a48797aa230c538",
    "new": "6940aaeb2b99f222b753f5f4e01da00ce491c686674b1947573e5f2737149bff",
    "reporting_version": 1,
    "fixed_engine_commit": "fd87fc7",
    "fixed_harness_commit": "ae49aaa"
  }
]
```

### V3: compare_runs unchanged
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

## 5.7 Full suite
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
  "passed_gate": false,
  "pytest_summary": "16 failed, 2196 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 775.38s (0:12:55)",
  "pytest_counts": {
    "passed": 2196,
    "failed": 16,
    "skipped": 3,
    "xfailed": 23
  },
  "gpu_load_profile": {
    "outcome": "failed",
    "stage": "call",
    "duration": 12.684717221999563,
    "failure": "tests/test_gpu_load_profile.py:284: in test_gpu_load_profile\n    _run_test()\ntests/test_gpu_load_profile.py:169: in _run_test\n    assert abs(frac - expected_frac) < TOLERANCE, (\nE   AssertionError: [FAIL-A] phase-3 sim_t=2400.0s: gpu_load_fraction=0.5 expected 0.1\nE   assert 0.4 < 1e-06\nE    +  where 0.4 = abs((0.5 - 0.1))"
  }
}
```
Native pytest summary (JUnit includes passing subtests and groups xfails with skipped):
```text
WARNING  gridsignal.scenario_factory:build_warnings.py:15 DR D3 build warning: {'code': 'islanded_frequency_protection_unconfigured', 'message': 'islanded run without frequency protection configured'}
WARNING  core.simulation_core:simulation_core.py:2266 Commitment engine: clearing stale pending-start register for 'turbine-1' at sim_time=120.0 — unit is OFFLINE, start did not take
=========================== short test summary info ============================
FAILED tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation
FAILED tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config
FAILED tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar
FAILED tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
FAILED tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
FAILED tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names - Asser...
FAILED tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel
FAILED tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
FAILED tests/test_gpu_load_profile.py::test_gpu_load_profile - AssertionError...
FAILED tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants
FAILED tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude
FAILED tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context
FAILED tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
FAILED tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes
FAILED tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
FAILED tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip
16 failed, 2196 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 775.38s (0:12:55)
```
Failing IDs: tools/dr_isl/PHASE_5_FAILING_TESTS.txt.
Incremental JUnit: tools/dr_isl/phase5/P5_FULL_SUITE.incremental.xml.
Final JUnit: tools/dr_isl/phase5/P5_FULL_SUITE_FINAL.xml.

### Dev serving check
```json
{
  "workflow": "artifacts/gridsignal: web",
  "app_source_base": "fd87fc75b995f19556f598cdc5b0f443a4edce75",
  "candidate_running": false,
  "restarted_after_base_restoration": true,
  "get_root_status": 200,
  "preview": "RESTORED_PREVIEW.jpg: signed-out base app; expected unauthenticated API 401",
  "build": "RESTORED_BASE_BUILD.txt: success; pre-existing bundle-size warning"
}
```

### GPU classification using the Phase 4 P2 protocol
IMPL-SSH-07: pre-existing interval-boundary / asynchronous latest-snapshot sampling sensitivity, not a D3 workload-physics regression
Profile is evaluated at interval start; tick timestamp denotes interval end. The test computes expected_fraction from the end timestamp. Latest-snapshot HTTP polling can skip or hit the exact transition tick. fd87fc7 prefix reproduces phase-2 720s mismatch; candidate file and full suite reproduce phase-3 2400s mismatch. Both versions pass all three isolation attempts.
WebSocketHub._latest_ticks, runtime/run_manager.py:186,231-237,263; /runs/{id}/latest reads this snapshot at api/routes/runs.py:907-939
In a separately approved test fix, align expectations with the tick interval convention and use deterministic ingestion/step completion rather than relying on latest-snapshot polling.
| version | context | outcome |
|---|---|---|
| base | isolation1 | passed |
| base | isolation2 | passed |
| base | isolation3 | passed |
| base | file | passed |
| base | prefix | failed |
| candidate | isolation1 | passed |
| candidate | isolation2 | passed |
| candidate | isolation3 | passed |
| candidate | file | failed |
| candidate | prefix | passed |
Source snippets and every literal assertion: phase5/P2_CLASSIFICATION.json.
Both prefix runs use the same common preceding order; candidate adds only its 14 new cases.

### Additional violation inside the known API-static failure
```json
{
  "nodeid": "tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes",
  "base": {
    "outcome": "failed",
    "stage": "call",
    "duration": 0.11964453800010233,
    "failure": "tests/test_plane_separation.py:496: in test_api_gate_clean_api_passes\n    assert not all_violations, (\nE   AssertionError: api/ core-import violations found \u2014 build fails:\nE       api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\nE       api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\nE   assert not [\"api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden l...ngest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\"]"
  },
  "candidate": {
    "outcome": "failed",
    "stage": "call",
    "duration": 0.09649366800022108,
    "failure": "tests/test_plane_separation.py:496: in test_api_gate_clean_api_passes\n    assert not all_violations, (\nE   AssertionError: api/ core-import violations found \u2014 build fails:\nE       api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\nE       api/routes/ingest.py:18: from core.slurm_scheduler import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\nE       api/schemas.py:2430: from core.frequency_reporting import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\nE   assert not [\"api/routes/ingest.py:17: from core.models import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden l...py:2430: from core.frequency_reporting import ... \u2014 forbidden in api/ (top-level package 'core' is in forbidden list)\"]"
  },
  "new_violation": "api/schemas.py:2430: from core.frequency_reporting import ...",
  "fix_direction": "Route ScenarioSpec validation through an allowed runtime/shared interface to the same pure predicate; do not duplicate protection logic.",
  "fixed": false
}
```

### Restoration limitation: previously ignored frontend source
{
  "reason": "These three existing UI files were already ignored/untracked before D3; fd87fc7 has no Git copy. Preserve candidate bytes and reverse only the Phase 5 edits for base restoration. Do not claim a pre-edit byte hash was captured.",
  "files": {
    "App.tsx": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx",
    "forecastQuality.ts": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts",
    "forecast_quality_panel.test.tsx": "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/test/forecast_quality_panel.test.tsx"
  }
}
The three files were restored by reversing only D3 edits, not by claiming a nonexistent fd87fc7 Git copy.
Candidate and restored copies, plus the exact reversal, are preserved in phase5/UI_*.
The restored frontend builds successfully. The screenshot is the signed-out base app, not a verification of candidate UI.

### Candidate paths and line counts (refer to the stash, NOT active source)
```json
{
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py": {
    "sha256": "739953ec6398cfb95c5bedb833fe5b0394b6d44fcdaa6cebff019f6f7d362d2f",
    "lines": 3051
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py": {
    "sha256": "b142a3e98142308f74f824f51e3a862be920b8c6e71daefd4db12f550f405d44",
    "lines": 1943
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py": {
    "sha256": "f3e867309cd1e6aa97ca9ded2b28572763283341a6ac844d0f222d03a135ff47",
    "lines": 4174
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/frequency_reporting.py": {
    "sha256": "4500e888585f6ce105973ad1d8b0535d972774be30ca0c2422ae1405e1573945",
    "lines": 36
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py": {
    "sha256": "2d045b6937abed6fae8d7ec503ac56f4d68e19544ae44687723b9357e268699a",
    "lines": 57
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py": {
    "sha256": "310aa42250e9e545c605834ca497bd4a27624256527673f4091e46d8fc2e1c5e",
    "lines": 3766
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py": {
    "sha256": "1bd2e9a12a64c465ed8679f496f1960e83c4eec2e3d45bcfa036047c75678592",
    "lines": 2180
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py": {
    "sha256": "cb74935312a483f4736217fa3ca4e21891206d7197211046a61dca0b073b1d90",
    "lines": 606
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/metrics.py": {
    "sha256": "741cce7c72f88ec9d5e42d104b8fad33e193cc7cbc31c6a2af3d02f139f4868f",
    "lines": 687
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_frequency_reporting.py": {
    "sha256": "406d3560966f35a10fdb6feb496855e3c8255b2cf4dd9272497d8e1e5d166faa",
    "lines": 92
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase2c.py": {
    "sha256": "6348b069311e372315c42a2f3ff7bf7705172767cd0ccdc33f1ed392e1252d13",
    "lines": 78
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts": {
    "sha256": "e351d7b40dd3d1e1dc89d6c01d5effa3fbcaa347a63d6232d06a32b0621a2469",
    "lines": 1319
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx": {
    "sha256": "edd7208ef805991c323987617921eeb28bda0aa215f5b704ff55c11b94fa2344",
    "lines": 471
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts": {
    "sha256": "15ae7a3f57b723f085e082b79069ca61d65ed8510c420490d5a4f5c4aae5d0da",
    "lines": 178
  },
  "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/test/forecast_quality_panel.test.tsx": {
    "sha256": "2d649db19e5b85f016b86c85e1617155d6b4976f450a0eda6f7af31a81c2208a",
    "lines": 302
  }
}
```

### Literal stashed candidate diff and line ranges
```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx
new file mode 100644
index 0000000..298f369
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/App.tsx
@@ -0,0 +1,471 @@
+/**
+ * App.tsx — Root routing and run lifecycle (Step 8 / UI-Hierarchy V-2).
+ *
+ * Two distinct layouts:
+ *
+ * OPENING LAYOUT  (currentPage === 'readiness' and no resultsRunId)
+ *   GridSignalHeader  — brand bar, STANDBY/LIVE badge, UTC clock, "How it works"
+ *   OpeningScreen     — three-band SCADA mimic (V-2)
+ *   DemoBar           — demo controls (scenario + speed + START)
+ *   TopologyExplainer — modal, opened by GridSignalHeader "How it works"
+ *
+ * INNER PAGE LAYOUT  (all other pages / results screen)
+ *   RunControlBar  — scenario picker + speed + start/stop + view results
+ *   SimClockHeader — sim clock, decimation badge, DQ legend
+ *   Tab navigation — Readiness | Overview | Proposals | … | Scenario Planner
+ *   Page content
+ *
+ * Render loop: 4 Hz setInterval (250 ms) drains pending WS ticks.
+ */
+
+import { useCallback, useEffect, useRef, useState } from 'react'
+import { LoginPage }               from './components/LoginPage'
+import { GridSignalHeader }        from './opening/GridSignalHeader'
+import { DemoBar }                 from './opening/DemoBar'
+import { TopologyExplainer }       from './opening/TopologyExplainer'
+import { OpeningScreen }           from './opening/OpeningScreen'
+import { SimClockHeader }          from './components/SimClockHeader'
+import { HeroPanel }               from './components/HeroPanel'
+import { ForecastChart }           from './components/ForecastChart'
+import { AssetReservePanel }       from './components/AssetReservePanel'
+import { RunControlBar }           from './components/RunControlBar'
+import { ScenarioBuilder }         from './components/ScenarioBuilder'
+import { ResultsScreen }           from './components/ResultsScreen'
+import { ProposalsPage }           from './components/ProposalsPage'
+import { NetworkTelemetryPage }    from './components/NetworkTelemetryPage'
+import { SchedulerTelemetryPage }  from './components/SchedulerTelemetryPage'
+import { ProcurementPage }         from './components/ProcurementPage'
+import { ThermalCoolingPage }      from './components/ThermalCoolingPage'
+import { ScenarioPlannerPage }     from './components/ScenarioPlannerPage'
+import { ScenarioManagerPage }     from './components/ScenarioManagerPage'
+import { CapacityOutlookPage }     from './components/CapacityOutlookPage'
+import { ScenarioModal }           from './components/ScenarioModal'
+import { AdminPage }               from './components/AdminPage'
+import { ChangePasswordModal }     from './components/ChangePasswordModal'
+import { AskGridley }              from './components/AskGridley'
+import { useTickStore }            from './store/tickStore'
+import { useScenarioStore }        from './store/scenarioStore'
+import { useTickStream }           from './ws/useTickStream'
+
+type PageView = 'readiness' | 'overview' | 'proposals' | 'procurement' | 'capacity-outlook' | 'network' | 'slurm' | 'thermal' | 'scenarios' | 'scenario-manager' | 'admin'
+
+const FRAME_INTERVAL_MS = 250   // 4 Hz render loop
+
+export default function App() {
+  // ── Auth state ─────────────────────────────────────────────────────────────
+  // null = not yet checked, false = unauthenticated, string = display name
+  const [authUser,      setAuthUser]      = useState<string | false | null>(null)
+  const [userRole,      setUserRole]      = useState<string>('operator')
+
+  // Check session on mount by calling /api/auth/me
+  useEffect(() => {
+    fetch('/api/auth/me', { credentials: 'include' })
+      .then(r => r.ok ? r.json() : null)
+      .then((data: { display_name: string; role: string } | null) => {
+        if (data) {
+          setAuthUser(data.display_name)
+          setUserRole(data.role)
+        } else {
+          setAuthUser(false)
+        }
+      })
+      .catch(() => setAuthUser(false))
+  }, [])
+
+  const handleAuthenticated = useCallback((displayName: string, role: string) => {
+    setAuthUser(displayName)
+    setUserRole(role)
+  }, [])
+
+  const handleLogout = useCallback(async () => {
+    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
+    setAuthUser(false)
+  }, [])
+
+  // ── Auth gate ──────────────────────────────────────────────────────────────
+  if (authUser === null) {
+    // Still checking session — show minimal loading state
+    return (
+      <div className="min-h-screen flex items-center justify-center" style={{ background: '#0b1017' }}>
+        <span className="font-sans" style={{ color: '#4b5764', fontSize: 13 }}>Loading…</span>
+      </div>
+    )
+  }
+  if (authUser === false) {
+    const isAdminPath = window.location.pathname === '/admin'
+    return <LoginPage onAuthenticated={handleAuthenticated} adminMode={isAdminPath} />
+  }
+
+  // ── Authenticated — render the main interface ──────────────────────────────
+  return <AuthenticatedApp displayName={authUser} role={userRole} onLogout={handleLogout} />
+}
+
+interface AuthAppProps {
+  displayName: string
+  role: string
+  onLogout: () => void
+}
+
+function AuthenticatedApp({ displayName, role, onLogout }: AuthAppProps) {
+  const [runId,         setRunId]         = useState<string | null>(null)
+  const [lastRunId,     setLastRunId]     = useState<string | null>(null)
+  const [resultsRunId,  setResultsRunId]  = useState<string | null>(null)
+  const [isPaused,      setIsPaused]      = useState(false)
+  const [drawerOpen,    setDrawerOpen]    = useState(false)
+  const [editId,        setEditId]        = useState<string | null>(null)
+  const [currentPage,   setCurrentPage]   = useState<PageView>(() =>
+    role === 'admin' && window.location.pathname === '/admin' ? 'admin' : 'readiness'
+  )
+  const [agentsEnabled,       setAgentsEnabled]       = useState(true)
+  const [topoOpen,            setTopoOpen]            = useState(false)
+  const [scenariosOpen,       setScenariosOpen]       = useState(false)
+  const [changePasswordOpen,  setChangePasswordOpen]  = useState(false)
+
+  const drainFrame     = useTickStore(s => s.drainFrame)
+  const unprotectedIslandRun = useTickStore(s =>
+    s.latestTick?.protection_provisional === true && s.latestTick.protection_configured === false)
+  const setRunMeta     = useTickStore(s => s.setRunMeta)
+  const reset          = useTickStore(s => s.reset)
+  const setRunPaused   = useTickStore(s => s.setRunPaused)
+  const selectScenario = useScenarioStore(s => s.selectScenario)
+
+  // 4 Hz render loop — drains pending WS ticks into display state.
+  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
+  useEffect(() => {
+    intervalRef.current = setInterval(drainFrame, FRAME_INTERVAL_MS)
+    return () => {
+      if (intervalRef.current) clearInterval(intervalRef.current)
+    }
+  }, [drainFrame])
+
+  // Run lifecycle callbacks
+  const handleRunStarted = useCallback((id: string, speed: number, socFloor?: number, socCeil?: number) => {
+    reset()
+    setIsPaused(false)
+    setRunPaused(false)
+    setRunId(id)
+    setLastRunId(id)
+    setResultsRunId(null)
+    setRunMeta({ run_id: id, playback_speed: speed, soc_floor_pct: socFloor, soc_ceil_pct: socCeil })
+    // Stay on opening screen — flow lines thicken as the turbine ramps.
+    // User navigates to Overview via the tab strip or a modal link.
+  }, [reset, setRunMeta, setRunPaused])
+
+  // Auto-detect a run started externally (e.g. via curl / another client).
+  // Polls GET /runs every 2 s when idle; stops once a run is tracked.
+  useEffect(() => {
+    if (runId !== null) return
+    const poll = async () => {
+      try {
+        const resp = await fetch('/runs')
+        if (!resp.ok) return
+        const data = await resp.json() as { run_ids: string[] }
+        if (data.run_ids.length > 0) {
+          const id = data.run_ids[0]
+          reset()
+          setRunId(id)
+          setLastRunId(id)
+          setRunMeta({ run_id: id, playback_speed: 10 })
+        }
+      } catch { /* ignore */ }
+    }
+    poll()
+    const timer = setInterval(poll, 2000)
+    return () => clearInterval(timer)
+  }, [runId, reset, setRunMeta])
+
+  const handleRunStopped = useCallback(() => {
+    setRunId(null)
+    setIsPaused(false)
+    setRunPaused(false)
+    reset()
+  }, [reset, setRunPaused])
+
+  const handleRunPaused = useCallback(() => {
+    setIsPaused(true)
+    setRunPaused(true)
+  }, [setRunPaused])
+
+  const handleRunResumed = useCallback(() => {
+    setIsPaused(false)
+    setRunPaused(false)
+  }, [setRunPaused])
+
+  // WS tick stream — must be called after handleRunStopped so the run_complete
+  // sentinel from the server transitions the UI to the completed state instead
+  // of spinning in a reconnect loop.
+  useTickStream(runId, handleRunStopped)
+
+  const handleViewResults = useCallback((id: string) => {
+    setResultsRunId(id)
+  }, [])
+
+  const handleRerun = useCallback((scenarioId: string) => {
+    setResultsRunId(null)
+    selectScenario(scenarioId)
+    // Ensure the RunControlBar is visible (inner page layout).
+    setCurrentPage(prev => prev === 'readiness' ? 'overview' : prev)
+  }, [selectScenario])
+
+  const handleNewScenario = useCallback(() => {
+    setEditId(null)
+    setDrawerOpen(true)
+  }, [])
+
+  const handleEditScenario = useCallback((id: string) => {
+    setEditId(id)
+    setDrawerOpen(true)
+  }, [])
+
+  const handleDrawerSaved = useCallback((scenarioId: string) => {
+    selectScenario(scenarioId)
+    setDrawerOpen(false)
+  }, [selectScenario])
+
+  const handleToggleAgents = useCallback(() => {
+    const next = !agentsEnabled
+    setAgentsEnabled(next)
+    fetch('/api/agents/toggle', {
+      method: 'POST',
+      headers: { 'Content-Type': 'application/json' },
+      body: JSON.stringify({ enabled: next }),
+    }).catch(() => {})
+  }, [agentsEnabled])
+
+  // DR D3: keep the run notice visible in the opening and inner-page layouts.
+  const frequencyNotice = unprotectedIslandRun ? (
+      <div role="status" className="border-b border-border px-4 py-2 text-sm text-amber-400">
+        islanded run without frequency protection configured
+      </div>
+    ) : null
+
+  // ── Results screen (any page) ──────────────────────────────────────────────
+  if (resultsRunId !== null) {
+    return (
+      <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
+        <ResultsScreen
+          runId={resultsRunId}
+          onClose={() => setResultsRunId(null)}
+          onRerun={handleRerun}
+        />
+      </div>
+    )
+  }
+
+  // ── Opening layout — no tab nav, brand header, demo bar ───────────────────
+  if (currentPage === 'readiness') {
+    return (
+      <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
+        {frequencyNotice}
+        <GridSignalHeader
+          runId={runId}
+          onHowItWorks={() => setTopoOpen(true)}
+          displayName={displayName}
+          role={role}
+          onLogout={onLogout}
+          onAdmin={role === 'admin' ? () => setCurrentPage('admin') : undefined}
+          onChangePassword={() => setChangePasswordOpen(true)}
+        />
+
+        <main className="flex-1 overflow-hidden">
+          <OpeningScreen
+            onNavigate={(tabId) => setCurrentPage(tabId as PageView)}
+            onEditScenario={handleEditScenario}
+          />
+        </main>
+
+        <DemoBar
+          runId={runId}
+          lastRunId={lastRunId}
+          isPaused={isPaused}
+          onRunStarted={handleRunStarted}
+          onRunStopped={handleRunStopped}
+          onRunPaused={handleRunPaused}
+          onRunResumed={handleRunResumed}
+          onViewResults={handleViewResults}
+          onManageScenarios={() => setScenariosOpen(true)}
+        />
+
+        {topoOpen && (
+          <TopologyExplainer onClose={() => setTopoOpen(false)} />
+        )}
+
+        {changePasswordOpen && (
+          <ChangePasswordModal onClose={() => setChangePasswordOpen(false)} />
+        )}
+
+        {scenariosOpen && (
+          <ScenarioModal
+            onClose={() => setScenariosOpen(false)}
+            onNew={() => { setScenariosOpen(false); handleNewScenario() }}
+            onEdit={id => { setScenariosOpen(false); handleEditScenario(id) }}
+            onExecute={(runId, speed, socFloor, socCeil) => {
+              setScenariosOpen(false)
+              handleRunStarted(runId, speed, socFloor, socCeil)
+            }}
+          />
+        )}
+
+        {drawerOpen && (
+          <ScenarioBuilder
+            editId={editId}
+            onClose={() => setDrawerOpen(false)}
+            onSaved={handleDrawerSaved}
+          />
+        )}
+        <AskGridley />
+      </div>
+    )
+  }
+
+  // ── Inner page layout — RunControlBar + SimClockHeader + tabs ─────────────
+  return (
+    <div className="flex h-screen flex-col bg-canvas text-text overflow-hidden">
+
+      <RunControlBar
+        runId={runId}
+        lastRunId={lastRunId}
+        isPaused={isPaused}
+        onRunStarted={handleRunStarted}
+        onRunStopped={handleRunStopped}
+        onRunPaused={handleRunPaused}
+        onRunResumed={handleRunResumed}
+        onNewScenario={handleNewScenario}
+        onViewResults={handleViewResults}
+      />
+
+      <SimClockHeader onChangePassword={() => setChangePasswordOpen(true)} isPaused={isPaused} />
+
+      {frequencyNotice}
+
+      {/* Page navigation tabs */}
+      <div className="flex gap-px border-b border-border bg-border flex-shrink-0 overflow-x-auto">
+        {([
+          ['readiness',   'Readiness'],
+          ['overview',    'Overview'],
+          ['slurm',       'Workload Telemetry'],
+          ['proposals',   'Proposals & Learning'],
+          ['procurement', 'Grid & Procurement'],
+          ['capacity-outlook', 'Capacity Outlook'],
+          ['network',     'Network Telemetry'],
+          ['thermal',     'Thermal & Cooling'],
+          ['scenarios',         'Scenario Planner'],
+          ['scenario-manager',  'Scenarios'],
+        ] as const).map(([page, label]) => (
+          <button
+            key={page}
+            onClick={() => setCurrentPage(page)}
+            className={`flex-shrink-0 whitespace-nowrap px-4 py-2 text-xs font-medium transition-colors ${
+              currentPage === page
+                ? 'bg-surface text-text border-b-2 border-accent -mb-px'
+                : 'bg-canvas text-text-muted hover:text-text hover:bg-surface/50'
+            }`}
+          >
+            {label}
+            {page === 'proposals' && agentsEnabled && (
+              <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-green-400 align-middle" />
+            )}
+          </button>
+        ))}
+        {/* Renewable Console — external link to /solar-console */}
+        <a
+          href="/solar-console"
+          target="_blank"
+          rel="noopener noreferrer"
+          className="px-4 py-2 text-xs font-medium transition-colors text-text-muted hover:text-text hover:bg-surface/50"
+          style={{ textDecoration: 'none' }}
+        >
+          ☀ Renewable Console ↗
+        </a>
+
+        {/* Admin tab — only visible to admin-role users */}
+        {role === 'admin' && (
+          <button
+            onClick={() => setCurrentPage('admin')}
+            className={`px-4 py-2 text-xs font-medium transition-colors ml-auto ${
+              currentPage === 'admin'
+                ? 'bg-surface text-text border-b-2 border-accent -mb-px'
+                : 'bg-canvas text-text-muted hover:text-text hover:bg-surface/50'
+            }`}
+          >
+            ⚙ Admin
+          </button>
+        )}
+      </div>
+
+      {/* Page content */}
+      {currentPage === 'overview' ? (
+        <main className="flex-1 grid grid-cols-2 grid-rows-[auto_1fr] gap-px bg-border overflow-hidden">
+          <div className="col-span-2 bg-surface overflow-auto">
+            <HeroPanel />
+          </div>
+          <div className="bg-surface overflow-hidden">
+            <ForecastChart />
+          </div>
+          <div className="bg-surface overflow-auto">
+            <AssetReservePanel />
+          </div>
+        </main>
+      ) : currentPage === 'proposals' ? (
+        <main className="flex-1 overflow-hidden">
+          <ProposalsPage
+            runId={runId ?? lastRunId}
+            agentsEnabled={agentsEnabled}
+            onToggleAgents={handleToggleAgents}
+          />
+        </main>
+      ) : currentPage === 'procurement' ? (
+        <main className="flex-1 overflow-hidden">
+          <ProcurementPage runId={runId ?? lastRunId} />
+        </main>
+      ) : currentPage === 'capacity-outlook' ? (
+        <main className="flex-1 overflow-hidden">
+          <CapacityOutlookPage runId={runId ?? lastRunId} />
+        </main>
+      ) : currentPage === 'network' ? (
+        <main className="flex-1 overflow-hidden">
+          <NetworkTelemetryPage runId={runId ?? lastRunId} />
+        </main>
+      ) : currentPage === 'slurm' ? (
+        <main className="flex-1 overflow-hidden">
+          <SchedulerTelemetryPage />
+        </main>
+      ) : currentPage === 'thermal' ? (
+        <main className="flex-1 overflow-hidden">
+          <ThermalCoolingPage runId={runId ?? lastRunId} />
+        </main>
+      ) : currentPage === 'scenario-manager' ? (
+        <main className="flex-1 overflow-hidden">
+          <ScenarioManagerPage
+            onNewScenario={handleNewScenario}
+            onEditScenario={handleEditScenario}
+            onExecute={(runId, speed, socFloor, socCeil) =>
+              handleRunStarted(runId, speed, socFloor, socCeil)
+            }
+          />
+        </main>
+      ) : currentPage === 'admin' && role === 'admin' ? (
+        <main className="flex-1 overflow-hidden">
+          <AdminPage />
+        </main>
+      ) : (
+        <main className="flex-1 overflow-hidden">
+          <ScenarioPlannerPage runId={runId ?? lastRunId} />
+        </main>
+      )}
+
+      {drawerOpen && (
+        <ScenarioBuilder
+          editId={editId}
+          onClose={() => setDrawerOpen(false)}
+          onSaved={handleDrawerSaved}
+        />
+      )}
+
+      {changePasswordOpen && (
+        <ChangePasswordModal onClose={() => setChangePasswordOpen(false)} />
+      )}
+      <AskGridley />
+    </div>
+  )
+}
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts
new file mode 100644
index 0000000..a203459
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/subsystem/panels/forecastQuality.ts
@@ -0,0 +1,178 @@
+/**
+ * forecastQuality.ts — Forecast Quality subsystem panel config.
+ *
+ * Accent: Teal #3fb6a8.
+ * Shows DQ tags, confidence band, calibration state.
+ * Copy matches gridsignal-13-forecast-quality context.
+ *
+ * This is the tile an engineer will linger on — it shows how much to trust
+ * the numbers on every other panel.
+ *
+ * Phase 11.5 additions:
+ *   • Chart centre changed from p_total_mw → forecast_mw (F4 criterion).
+ *   • Second "actual" trace (p_total_mw) added so the prediction gap is visible.
+ *   • BESS setpoint vs measured gap shown in stat rows.
+ *   • Frequency deviation indicator shown in islanded mode (protection_provisional).
+ */
+
+import React from 'react'
+import type { PanelConfig, PanelData } from './index'
+import type { TickPayload, HistoryPoint } from '../../types'
+import { TimeSeries } from '../../charts/TimeSeries'
+
+const TEAL    = '#3fb6a8'
+const AMBER   = '#f0883e'
+const GREY    = '#30363d'
+// Dimmed teal for the confidence band fill
+const BAND_BG = '#1a2e2d'
+
+// The wording is presentation-only.  Widening percentages are appended from
+// ConfidenceEngine metadata on the tick; they must not be duplicated here.
+const DQ_EXPLANATIONS: Record<string, string> = {
+  unmapped_hardware:       'Unmapped hardware — the equipment profile is not recognised',
+  uncalibrated_site:       'Uncalibrated site — site measurements have not been calibrated',
+  invalid_payload:         'Invalid payload — the workload data did not pass validation',
+  stale_profile:           'Stale profile — the equipment profile may be out of date',
+  workload_signal_stale:   'Workload signal stale — queue information is older than expected',
+  workload_signal_absent:  'Workload signal absent — no workload signal has arrived',
+}
+
+export const forecastQualityPanel: PanelConfig = {
+  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
+    if (!tick) {
+      return {
+        stateLabel:  '—',
+        stateColour: '#30363d',
+        verdict:     'No active run. Start a scenario to see forecast quality.',
+        heroValue:   '—',
+        heroLabel:   'confidence band MW',
+        chartTitle:  'CONFIDENCE BAND — FORECAST VS ACTUAL',
+        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
+        statRows: [],
+        why: [
+          'The confidence band is the only live indicator of how much to trust every other number on screen.',
+          'Each data-quality flag widens the band independently and additively — they are chosen values, not derived.',
+          'A calibrated site with known hardware and clean payloads has a 5% base widening and nothing more.',
+        ],
+      }
+    }
+
+    const dqTags  = tick.data_quality_tags
+    const bandMW  = tick.confidence_upper_mw - tick.confidence_lower_mw
+    const hasFlags = dqTags.length > 0
+    const widening = tick.confidence_widening
+
+    const formatWidening = (fraction: number | undefined) =>
+      fraction == null ? null : `+${(fraction * 100).toFixed(0)}% CI widening`
+
+    const tagExplanation = (tag: string) => {
+      const explanation = DQ_EXPLANATIONS[tag] ?? tag
+      const wideningText = formatWidening(widening?.per_tag[tag])
+      return wideningText ? `${explanation} — ${wideningText}` : explanation
+    }
+
+    // Phase 11.5: two-trace chart.
+    // Series order matters for z-ordering: confidence band fill first, then
+    // the two signal lines on top so they are always visible.
+    const chart = React.createElement(TimeSeries, {
+      series: [
+        // Confidence band — upper bound filled; lower bound filled with a dark
+        // colour to "mask out" the region below the band, producing a shaded
+        // corridor between the two bounds around the forecast line.
+        { label: 'upper bound', colour: GREY, points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_upper_mw })), filled: true },
+        { label: 'lower bound', colour: BAND_BG, points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_lower_mw })), filled: true },
+        // Predicted — forecast_mw is the centre of the confidence band (F4
+        // criterion: agrees with the PREDICTED PEAK header figure bit-for-bit).
+        { label: 'predicted',   colour: TEAL,      points: history.map(h => ({ x: h.sim_time_seconds, y: h.forecast_mw })) },
+        // Actual — p_total_mw is the real measured site demand this tick.
+        // The gap between predicted and actual is the prediction error.
+        { label: 'actual',      colour: '#e6edf3', points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })) },
+      ],
+      xLabel:  'seconds from run start',
+      height:  200,
+    })
+
+    const tagRows = dqTags.map(tag => ({
+      label: tag,
+      value: 'ACTIVE',
+      colour: AMBER,
+      sub: tagExplanation(tag),
+    }))
+
+    const clearTags = Object.keys(DQ_EXPLANATIONS).filter(t => !dqTags.includes(t)).map(tag => ({
+      label: tag,
+      value: 'clear',
+      sub:   tagExplanation(tag),
+    }))
+
+    // Phase 11.5: BESS setpoint vs measured gap.
+    const bessDelta = tick.bess_setpoint_mw - tick.bess_output_mw
+    const bessGapStr = `${bessDelta >= 0 ? '+' : ''}${bessDelta.toFixed(3)} MW`
+    const bessGapColour = Math.abs(bessDelta) > 0.5 ? AMBER : undefined
+
+    // Phase 11.5: frequency deviation indicator — only meaningful in islanded
+    // mode.  protection_provisional is true on every islanded tick (§2A spec).
+    // frequency_nominal_hz is stamped from SiteConfig per-run.  It is required
+    // on the live TickPayload; absent historical payloads render as uninstrumented.
+    const isIslanded  = tick.protection_provisional
+    const nominalHz   = tick.frequency_nominal_hz
+    const freqDevHz   = nominalHz == null ? null : tick.frequency_hz - nominalHz
+    const freqStr     = freqDevHz == null
+      ? `${tick.frequency_hz.toFixed(3)} Hz (nominal not instrumented)`
+      : `${tick.frequency_hz.toFixed(3)} Hz (${freqDevHz >= 0 ? '+' : ''}${freqDevHz.toFixed(3)})`
+    // Colour: amber when deviation > 0.5 Hz, red when > 1.5 Hz (UFLS proximity).
+    const invalidFrequency = tick.frequency_valid === false
+    // PROPOSED_HERE: muted grey identifies a reporting-invalid reading, not a new alarm/trip.
+    const freqColour = invalidFrequency ? '#87939b' : freqDevHz == null ? undefined :
+      Math.abs(freqDevHz) > 1.5 ? '#d9534f' :
+      Math.abs(freqDevHz) > 0.5 ? AMBER : undefined
+
+    return {
+      stateLabel:  hasFlags ? 'ATTENTION' : 'READY',
+      stateColour: hasFlags ? AMBER : TEAL,
+      verdict:     hasFlags
+        ? `${dqTags.length} data-quality flag${dqTags.length > 1 ? 's' : ''} active — confidence band widened.`
+        : 'All calibration checks clear. Confidence band nominal.',
+      heroValue:  `±${(bandMW / 2).toFixed(2)}`,
+      heroLabel:  'MW confidence band',
+      chartTitle: 'CONFIDENCE BAND — FORECAST VS ACTUAL',
+      chart,
+      statRows: [
+        { label: 'DQ flags active',      value: dqTags.length.toString(),                colour: hasFlags ? AMBER : undefined },
+        { label: 'Band width',           value: `${bandMW.toFixed(2)} MW` },
+        { label: 'Upper bound',          value: `${tick.confidence_upper_mw.toFixed(2)} MW` },
+        { label: 'Lower bound',          value: `${tick.confidence_lower_mw.toFixed(2)} MW` },
+        // Phase 11.5: BESS dispatch tracking.
+        { label: 'BESS setpoint',        value: `${tick.bess_setpoint_mw.toFixed(3)} MW`,  sub: 'dispatch command (pre-clip)' },
+        { label: 'BESS measured',        value: `${tick.bess_output_mw.toFixed(3)} MW`,    sub: 'actual output this tick' },
+        { label: 'BESS setpoint gap',    value: bessGapStr,                               colour: bessGapColour, sub: 'setpoint − measured' },
+        // Phase 11.5: frequency deviation (islanded mode only).
+        ...(isIslanded || invalidFrequency ? [
+          { label: 'Frequency', value: freqStr, colour: freqColour,
+            sub: invalidFrequency
+              ? 'frequency outside validity band — not physical operation'
+              : 'islanded — swing-equation driven' },
+        ] : [
+           { label: 'Frequency',          value: 'grid-tied',
+             sub: nominalHz == null ? 'nominal not instrumented' : `locked to ${nominalHz} Hz reference` },
+        ]),
+        {
+          label: 'Base widening',
+          value: formatWidening(widening?.base_fraction)?.replace(' CI widening', '') ?? '—',
+          sub: 'always applied — sourced from ConfidenceEngine',
+        },
+        ...tagRows,
+        ...clearTags.slice(0, Math.max(0, 4 - tagRows.length)),
+      ],
+      secondary: undefined,
+      why: [
+        'The confidence band is the only live indicator of how much to trust every other number on screen.',
+        'The "predicted" trace is forecast_mw — the queue-derived point estimate used to size the confidence band. It agrees exactly with the PREDICTED PEAK header figure (F4).',
+        'The "actual" trace is p_total_mw — real measured site demand. The gap between the two traces is live prediction error.',
+        'BESS setpoint gap = dispatch command minus measured output. A large gap indicates clipping at rated power or an SoC limit.',
+        'Each data-quality flag widens the band independently and additively — they are chosen values, not derived from measurements.',
+        'A calibrated site with known hardware and clean payloads has a 5% base widening. Flags add 5–15% each.',
+      ],
+    }
+  },
+}
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/test/forecast_quality_panel.test.tsx b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/test/forecast_quality_panel.test.tsx
new file mode 100644
index 0000000..1481a24
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/test/forecast_quality_panel.test.tsx
@@ -0,0 +1,302 @@
+/**
+ * forecast_quality_panel.test.tsx — Phase 11.5 Forecast Quality panel tests.
+ *
+ * Covers:
+ *   FQ-1  Predicted trace uses forecast_mw, actual trace uses p_total_mw.
+ *         The two series must differ when forecast ≠ actual.
+ *   FQ-2  BESS setpoint gap shows amber colouring when |setpoint − measured| > 0.5 MW.
+ *   FQ-3  BESS setpoint gap shows no amber colouring for a small gap.
+ *   FQ-4  Frequency deviation row shown in islanded mode (protection_provisional=true).
+ *   FQ-5  Frequency deviation uses frequency_nominal_hz — correctly shows 0 Hz
+ *         deviation for a 50 Hz grid-connected site (tick.frequency_hz = 50.0).
+ *   FQ-6  Frequency row shows "grid-tied" when not islanded.
+ */
+
+import { describe, it, expect } from 'vitest'
+import { forecastQualityPanel } from '../subsystem/panels/forecastQuality'
+import type { TickPayload, HistoryPoint } from '../types'
+
+// ---------------------------------------------------------------------------
+// Fixtures
+// ---------------------------------------------------------------------------
+
+/** Base tick with no special conditions. */
+function makeTick(overrides: Partial<TickPayload> = {}): TickPayload {
+  const base: Partial<TickPayload> = {
+    run_id:                     'fq-test',
+    tick_index:                 1,
+    sim_time_seconds:           5.0,
+    p_compute_mw:               10.0,
+    p_cooling_mw:               2.0,
+    p_total_mw:                 12.0,
+    net_demand_mw:              7.0,
+    turbine_output_mw:          9.0,
+    bess_output_mw:             0.0,
+    bess_soc_fraction:          0.95,
+    confidence_lower_mw:        10.0,
+    confidence_upper_mw:        14.0,
+    forecast_mw:                13.5,   // intentionally ≠ p_total_mw (12.0) for FQ-1
+    bess_setpoint_mw:           0.1,    // small gap (0.1 MW) → no amber
+    frequency_hz:               60.0,
+    frequency_nominal_hz:       60.0,
+    protection_provisional:     false,  // grid-connected
+    data_quality_tags:          [],
+    p_renewable_mw:             5.0,
+    bess_bridging_seconds:      3600,
+    bridging_basis:             'predicted_peak',
+    dt_lead_next_s:             0.0,
+    insufficient_reserve_alert: false,
+    checkpoint_states:          {},
+    rated_cooling_mw:           4.59,
+    absorbable_mw:              4.59,
+    time_to_limit_s:            86400,
+    approach_rate_mw_s:         0.0,
+    turbine_units:              [],
+  }
+  return { ...base, ...overrides } as unknown as TickPayload
+}
+
+/** Two history points with distinct forecast_mw and p_total_mw values. */
+function makeHistory(n = 2): HistoryPoint[] {
+  return Array.from({ length: n }, (_, i) => ({
+    sim_time_seconds:    i * 5.0,
+    p_compute_mw:        10.0,
+    p_cooling_mw:        2.0,
+    p_total_mw:          12.0 + i * 0.1,   // actual varies slightly
+    p_renewable_mw:      5.0,
+    confidence_lower_mw: 10.0,
+    confidence_upper_mw: 14.0,
+    forecast_mw:         13.5 + i * 0.2,   // predicted diverges from actual
+    bess_setpoint_mw:    0.1,
+  }))
+}
+
+// ---------------------------------------------------------------------------
+// FQ-1 — Predicted trace uses forecast_mw; actual trace uses p_total_mw
+// ---------------------------------------------------------------------------
+
+describe('FQ-1 — chart series: predicted=forecast_mw, actual=p_total_mw', () => {
+  it('deriveData returns a chart element (non-null) when history is present', () => {
+    const tick    = makeTick()
+    const history = makeHistory(3)
+    const data    = forecastQualityPanel.deriveData(tick, null, history)
+    expect(data.chart).not.toBeNull()
+  })
+
+  it('predicted series y-values come from forecast_mw, not p_total_mw', () => {
+    const history = makeHistory(3)
+    // If both fields were the same we could not tell them apart — so keep them different.
+    // forecast_mw is 13.5, 13.7, 13.9 in the fixture.
+    // p_total_mw  is 12.0, 12.1, 12.2.
+    const data = forecastQualityPanel.deriveData(makeTick(), null, history)
+    // The chart prop is a React element.  We can't render it cheaply in a unit test,
+    // but we CAN verify that the deriveData function survives the call and the chartTitle
+    // reflects the new dual-trace intent.
+    expect(data.chartTitle).toMatch(/forecast vs actual/i)
+  })
+
+  it('heroValue encodes half the confidence band width (±)', () => {
+    const tick = makeTick()
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    // confidence band width = 14 − 10 = 4 MW → hero = ±2.00
+    expect(data.heroValue).toBe('±2.00')
+    expect(data.heroLabel).toMatch(/MW confidence band/i)
+  })
+})
+
+// ---------------------------------------------------------------------------
+// FQ-2 — BESS setpoint gap > 0.5 MW → amber colouring
+// ---------------------------------------------------------------------------
+
+describe('FQ-2 — BESS setpoint gap amber when |setpoint − measured| > 0.5 MW', () => {
+  it('saturation case: setpoint=5.0, measured=0.0 → gap row coloured amber', () => {
+    const tick = makeTick({ bess_setpoint_mw: 5.0, bess_output_mw: 0.0 })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const gapRow = data.statRows?.find(r => r.label === 'BESS setpoint gap')
+    expect(gapRow).toBeDefined()
+    expect(gapRow!.colour).toBe('#f0883e')    // AMBER
+    expect(gapRow!.value).toMatch(/\+5\.000 MW/)
+  })
+
+  it('gap row sub-label says "setpoint − measured"', () => {
+    const tick = makeTick({ bess_setpoint_mw: 5.0, bess_output_mw: 0.0 })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const gapRow = data.statRows?.find(r => r.label === 'BESS setpoint gap')
+    expect(gapRow!.sub).toMatch(/setpoint.*measured/i)
+  })
+})
+
+// ---------------------------------------------------------------------------
+// FQ-3 — BESS setpoint gap ≤ 0.5 MW → no amber colouring
+// ---------------------------------------------------------------------------
+
+describe('FQ-3 — BESS setpoint gap ≤ 0.5 MW → no amber colouring', () => {
+  it('small gap (0.1 MW) → gap row colour is undefined (nominal)', () => {
+    const tick = makeTick({ bess_setpoint_mw: 0.1, bess_output_mw: 0.0 })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const gapRow = data.statRows?.find(r => r.label === 'BESS setpoint gap')
+    expect(gapRow).toBeDefined()
+    expect(gapRow!.colour).toBeUndefined()
+  })
+
+  it('zero gap → gap value starts with +0.000', () => {
+    const tick = makeTick({ bess_setpoint_mw: 0.0, bess_output_mw: 0.0 })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const gapRow = data.statRows?.find(r => r.label === 'BESS setpoint gap')
+    expect(gapRow!.value).toMatch(/\+0\.000 MW/)
+  })
+})
+
+// ---------------------------------------------------------------------------
+// FQ-4 — Frequency deviation shown when islanded (protection_provisional=true)
+// ---------------------------------------------------------------------------
+
+describe('D3 — invalid frequency reporting', () => {
+  it('keeps achieved Hz and marks invalid operation grey with the reporting label', () => {
+    const tick = makeTick({
+      protection_provisional: true,
+      frequency_hz: 90,
+      frequency_valid: false,
+      protection_configured: false,
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const row = data.statRows?.find(r => r.label === 'Frequency')
+    expect(row?.value).toContain('90.000 Hz')
+    expect(row?.colour).toBe('#87939b')
+    expect(row?.sub).toBe('frequency outside validity band — not physical operation')
+  })
+})
+
+describe('FQ-4 — frequency row shows deviation in islanded mode', () => {
+  it('islanded tick: frequency row value includes Hz figure', () => {
+    const tick = makeTick({
+      protection_provisional: true,
+      frequency_hz:           59.5,
+      frequency_nominal_hz:   60.0,
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const freqRow = data.statRows?.find(r => r.label === 'Frequency')
+    expect(freqRow).toBeDefined()
+    expect(freqRow!.value).toMatch(/59\.500 Hz/)
+    expect(freqRow!.value).toMatch(/-0\.500/)
+  })
+
+  it('islanded tick: 0.6 Hz deviation → amber colour', () => {
+    const tick = makeTick({
+      protection_provisional: true,
+      frequency_hz:           59.4,
+      frequency_nominal_hz:   60.0,
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const freqRow = data.statRows?.find(r => r.label === 'Frequency')
+    expect(freqRow!.colour).toBe('#f0883e')   // AMBER
+  })
+
+  it('islanded tick: 1.6 Hz deviation → red colour', () => {
+    const tick = makeTick({
+      protection_provisional: true,
+      frequency_hz:           58.4,
+      frequency_nominal_hz:   60.0,
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const freqRow = data.statRows?.find(r => r.label === 'Frequency')
+    expect(freqRow!.colour).toBe('#d9534f')   // RED
+  })
+})
+
+// ---------------------------------------------------------------------------
+// FQ-5 — 50 Hz site: deviation correctly shows 0 when grid-connected
+// ---------------------------------------------------------------------------
+
+describe('FQ-5 — 50 Hz site shows zero deviation when frequency_hz = nominal', () => {
+  it('50 Hz grid-connected: frequency row shows "grid-tied", not a deviation', () => {
+    // Grid-connected: protection_provisional=false, frequency_hz=50, nominal=50
+    const tick = makeTick({
+      protection_provisional: false,
+      frequency_hz:           50.0,
+      frequency_nominal_hz:   50.0,
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const freqRow = data.statRows?.find(r => r.label === 'Frequency')
+    expect(freqRow).toBeDefined()
+    expect(freqRow!.value).toBe('grid-tied')
+  })
+
+  it('50 Hz islanded at nominal: deviation shows 0.000', () => {
+    const tick = makeTick({
+      protection_provisional: true,
+      frequency_hz:           50.0,
+      frequency_nominal_hz:   50.0,
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const freqRow = data.statRows?.find(r => r.label === 'Frequency')
+    expect(freqRow!.value).toMatch(/50\.000 Hz/)
+    expect(freqRow!.value).toMatch(/\+0\.000/)
+    // At exactly nominal there is no deviation, so no colour warning
+    expect(freqRow!.colour).toBeUndefined()
+  })
+})
+
+// ---------------------------------------------------------------------------
+// FQ-7 — widening metadata and workload-signal explanations
+// ---------------------------------------------------------------------------
+
+describe('FQ-7 — widening percentages come from the tick metadata', () => {
+  it('uses the authoritative stale-profile and workload-signal percentages', () => {
+    const tick = makeTick({
+      data_quality_tags: ['stale_profile', 'workload_signal_stale'],
+      confidence_widening: {
+        base_fraction: 0.05,
+        per_tag: {
+          stale_profile: 0.12,
+          workload_signal_stale: 0.20,
+        },
+        known_tags: ['stale_profile', 'workload_signal_stale'],
+      },
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const staleRow = data.statRows?.find(r => r.label === 'stale_profile')
+    const signalRow = data.statRows?.find(r => r.label === 'workload_signal_stale')
+    const baseRow = data.statRows?.find(r => r.label === 'Base widening')
+
+    expect(staleRow?.sub).toMatch(/\+12% CI widening/)
+    expect(signalRow?.sub).toMatch(/queue information is older than expected/i)
+    expect(signalRow?.sub).toMatch(/\+20% CI widening/)
+    expect(baseRow?.value).toBe('+5%')
+  })
+
+  it('has a static explanation for an absent workload signal', () => {
+    const tick = makeTick({
+      data_quality_tags: ['workload_signal_absent'],
+      confidence_widening: {
+        base_fraction: 0.05,
+        per_tag: { workload_signal_absent: 0.50 },
+        known_tags: ['workload_signal_absent'],
+      },
+    })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const absentRow = data.statRows?.find(r => r.label === 'workload_signal_absent')
+
+    expect(absentRow?.sub).toMatch(/no workload signal has arrived/i)
+    expect(absentRow?.sub).toMatch(/\+50% CI widening/)
+  })
+})
+
+// ---------------------------------------------------------------------------
+// FQ-6 — Grid-connected mode shows "grid-tied" frequency row
+// ---------------------------------------------------------------------------
+
+describe('FQ-6 — grid-connected: frequency row is informational, not an indicator', () => {
+  it('60 Hz grid-connected: row value is "grid-tied"', () => {
+    const tick = makeTick({ protection_provisional: false, frequency_hz: 60.0, frequency_nominal_hz: 60.0 })
+    const data = forecastQualityPanel.deriveData(tick, null, makeHistory())
+    const freqRow = data.statRows?.find(r => r.label === 'Frequency')
+    expect(freqRow!.value).toBe('grid-tied')
+  })
+
+  it('no-tick path: returns a chart with "No data" placeholder', () => {
+    const data = forecastQualityPanel.deriveData(null, null, [])
+    expect(data.stateLabel).toBe('—')
+    expect(data.heroValue).toBe('—')
+  })
+})
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
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py
index 94f7ca5..740d146 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/schemas.py
@@ -2423,6 +2423,16 @@ class ScenarioSpec(BaseModel):
         ),
     )
 
+    @model_validator(mode="after")
+    def _warn_unprotected_island(self) -> "ScenarioSpec":
+        """DR D3: validation warning, never reject or mutate the specification."""
+        import logging
+        from core.frequency_reporting import unprotected_island_warning
+        warning = unprotected_island_warning(self)
+        if warning is not None:
+            logging.getLogger(__name__).warning("ScenarioSpec validation warning: %s", warning)
+        return self
+
     @model_validator(mode="after")
     def _validate_kube_clusters(self) -> "ScenarioSpec":
         """Keep legacy and multi-cluster scheduler configuration unambiguous."""
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
index fc007ea..d9b854b 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
@@ -1,4 +1,4 @@
-"""Build-time diagnostics only; never change reserve floors or dispatch."""
+"""Build-time diagnostics only; never change reserve, dispatch or protection."""
 import logging
 
 from core.dispatch import MARGIN_MULTIPLIER
@@ -6,6 +6,16 @@ from core.dispatch import MARGIN_MULTIPLIER
 _log = logging.getLogger("gridsignal.scenario_factory")
 
 
+def frequency_configuration_warnings(state) -> list[dict]:
+    """DR D3: same warning as ScenarioSpec, using factory-resolved site values."""
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
index 0000000..589924c
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_frequency_reporting.py
@@ -0,0 +1,92 @@
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
+    assert "ScenarioSpec validation warning" in caplog.text
+    warning = next(w for w in ctx.metadata["build_warnings"]
+                   if w["code"] == "islanded_frequency_protection_unconfigured")
+    assert warning["message"] == "islanded run without frequency protection configured"
+    assert ctx.sim_state.site.uf_warning_hz is None
+    assert ctx.sim_state.site.of_trip_hz is None
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

STOP — end of Phase 5. No Phase 6, publish, deploy or push.
