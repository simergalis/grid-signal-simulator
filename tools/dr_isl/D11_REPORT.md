# DR D11 / IMPL-ISL-19 — STOP report

Status: **STOPPED at D11.5**. One added suite failure is outside the authorized
sustained-surplus test updates. No implementation or test commit was made.
The main application is restored to 5225a05 application code.
Candidate stash: `29a087dc197579b81d674856a95a65778fbab914`.

`P` = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`. Candidate line references below refer to that stash, not the
restored main application.

## D11.0 — evidence hygiene: PASS under the user's clarified boundary

- Original report-only commit: `1209c8dd0e418f978a8d001f74687f8dc7ce1a83`.
  It included eight channel CSVs.
- Amended local report-only commit:
  `c8a1e41995d0f8d39c95c97af793d0726f6170b8`.
  Eight CSVs were removed from the index; their on-disk bytes were retained.
- `.gitignore:60–61` excludes `tools/dr_isl/**/*.channels.csv`.
- The user explicitly selected: **"Keep the S10 scenario and non-CSV evidence
  tracked; exclude channel CSVs."** Existing S10 scenario and non-CSV evidence
  therefore remain tracked. No claim is made that no S10-named file is tracked.
- Literal file hashes and the S10 tracking inventory are in
  `tools/dr_isl/d11/D11_0_GATE_REPORT.md`.
- Automatic checkpoint `d47413e` contains documentation/metadata, not D11
  application code. No publish, deploy or push occurred.

## D11.1–D11.2 — candidate design and implementation

Base 5225a05 `P/core/simulation_core.py:3213–3235` advanced the dump timer by
the outer interval; `:3438–3489` integrated the pre-dump residual throughout
the substeps. The candidate preserves b74830d's same-tick rotor transient as
a finite response rather than sustained forcing.

Candidate changes, preserved in `CANDIDATE_FULL.diff` and the stash:

- `P/core/simulation_core.py:946–948`: one linear response helper shared by
  the unchanged scheduled ledger calculation and the achieved substep sink.
- `:3218–3239`: snapshot the episode timer; compute the existing ledger sink
  without advancing that timer by the outer tick.
- `:3466–3511`: advance the timer at each substep; net achieved dump response
  out of swing forcing. Zero delay responds immediately. Episode reset and
  carry semantics remain as specified.
- `:4147–4152`: islanded public `frequency_forcing_mw` reports the last
  executed substep's net MW **before damping**, including already-active
  UFLS shed and any FC output loss applied by earlier substeps. It is NOT
  necessarily the post-trip end-of-tick generation-minus-demand value.
- Grid-tied telemetry, D7, the final ledger curtailment value, dispatch,
  commitment, reserve, diesel, protection and guard conditions were not
  changed. No scenario JSON was edited and no frequency clamp was added.
- `docs/addendum-h-phase2a-change-record.md:38–66` was updated in the candidate.
- `APPLIED_AST_PARITY.json` confirms both applied function ASTs equal those
  used in the scratch acceptance runs. No acceptance run used a second
  production implementation.

No new production calibration constant was introduced. Synthetic test
inputs and the analysis-only classification tolerance are marked
PROPOSED_HERE. Existing response delay and frequency validity bounds were
not tuned.

## D11.3 — paired acceptance: PASS

Fourteen scenario/arm cases, two repetitions each, with both base and
candidate: 28 completed pairs / 56 completed runs. An unfinished serial
repetition was cancelled solely to schedule independent repetitions in
parallel; no result from it is used.

Every compared non-frequency tick is identical; every non-frequency hash
is identical; all 27 original study metrics and protection_configured are
unchanged. The two frequency-validity metrics change as reported.
Hashes exclude exactly the four established nondeterministic fields plus
frequency_hz, frequency_valid and frequency_forcing_mw; see
`D11_3_RESULTS.json`. Both repetitions agree in their hashes, metrics and
frequency statistics.

"Template" denotes demo-islanded-ramp as in the preceding diagnostic;
the catalogue maps that ID to demo-islanded-ramp.json
(`P/api/routes/scenarios.py:1364`). It is reported once, not as an invented
separate scenario.

All base-demo, H1 and H2 comparisons remain PASS, 10/10, before and after.
Their complete condition payloads and the full frequency/hash tables follow.

# D11.3 paired acceptance evidence

Two repetitions per case, each with a 5225a05 base and isolated D11 candidate. Non-frequency ticks stream through SHA-256 and pairwise comparison; no full tick exports.

|Scenario / arm|Ticks|Hz before|Hz after|Invalid fraction before → after|Non-frequency hash identical|
|---|---:|---|---|---|---|
|scenario-uneven-multisched-01 / baseline|1440|-5.000866893367675–176.430848113831|-5.000866893367675–60.04391555797632|0.4861111111111111 → 0.03680555555555556|True|
|scenario-uneven-multisched-01 / informed|1440|59.534837314959205–169.8277840657461|55.495062375543036–60.29869344972031|0.4263888888888889 → 0.0|True|
|scenario-h1-k8s-ray-24h / baseline|17280|17.23372983198947–224.93353102420852|17.09771681495931–60.271876826116234|0.7869212962962963 → 0.04693287037037037|True|
|scenario-h1-k8s-ray-24h / informed|17280|48.666827290428756–224.93353102420852|48.59156754833297–60.458333516015756|0.7935185185185185 → 0.004398148148148148|True|
|scenario-h2-slurm-24h / baseline|17280|-225.278937529193–245.96773016794788|-239.88626623828412–60.22370565114776|0.9723379629629629 → 0.03177083333333333|True|
|scenario-h2-slurm-24h / informed|17280|60.0–250.44034654726377|11.925776125116506–60.14917658611521|0.9811921296296297 → 0.023842592592592592|True|
|S10_mit_supercloud_2021-08-11 / app|17280|-729.1075118080669–998.9330534505464|-749.6905479257669–60.54595734564584|0.4203703703703704 → 0.034375|True|
|scenario-equinix-sj-1 / app|720|60.0–60.0|60.0–60.0|0.0 → 0.0|True|
|scenario-turbine-01 / app|720|60.0–305.12517226604007|60.0–60.58640692110985|0.6152777777777778 → 0.0|True|
|scenario-hybrid-ai-100mw-addendum-i / app|120|-218.79606450000827–285.92631259085584|-218.79606450000827–60.97955266880781|0.65 → 0.45|True|
|scenario-100mw-fuel-cell-bess-diesel / app|252|60.0–60.0|60.0–60.0|0.0 → 0.0|True|
|scenario-fc100-islanded-v2 / app|264|60.0–60.0|60.0–60.0|0.0 → 0.0|True|
|scenario-fc100-islanded-zero-hot-v2 / app|264|-82.80435199997717–60.0|-82.80435199997717–60.0|0.8106060606060606 → 0.8106060606060606|True|
|demo-islanded-ramp / app|2160|-127.48961154607643–60.0|-127.48961154607643–60.0|0.047685185185185185 → 0.047685185185185185|True|

## Complete non-frequency SHA-256 values

|Scenario / arm|Before = after|
|---|---|
|scenario-uneven-multisched-01 / baseline|`c72eb2a1fc1ba90c70e61cc571cbc310040346e195ffb16cbf4f20b4dc875cf5`|
|scenario-uneven-multisched-01 / informed|`766b066a7c35e1d9824ae2ceddf0391f9d7e0a164f6dea47cdb5a4e7a46af76e`|
|scenario-h1-k8s-ray-24h / baseline|`c3d6a39d63e786f5abef82b30bc045b122e675bc9fcc07ffc60a93262de0b823`|
|scenario-h1-k8s-ray-24h / informed|`958efa040f72ec67186b89a70f8ee984069fa19a961332559db36e83f3be845c`|
|scenario-h2-slurm-24h / baseline|`905a7f9d83cb2492d77bead4bd687f3959f300535f98838b33c384951cb75ca3`|
|scenario-h2-slurm-24h / informed|`49363ec20bc1634542c5b13d1e56a2fba5c035697689a362c50ab7d797f2d97c`|
|S10_mit_supercloud_2021-08-11 / app|`8a9415b84b564b706b7ee2e13035902f0dc3da941b74834de398feed7e3ddebe`|
|scenario-equinix-sj-1 / app|`65f41459bbb89a002473166453aa3792efc7460d210813e4700b7ea27734bd65`|
|scenario-turbine-01 / app|`4287d6a45c254914ffc67d5925ed9949c24a4dcd626a45f180929b7dd5afa7e4`|
|scenario-hybrid-ai-100mw-addendum-i / app|`74f55fca1651deabc7364360b1d0f52941b8564df6e6001be377bc3a3458cfc1`|
|scenario-100mw-fuel-cell-bess-diesel / app|`c6ccccd59d04a3356f651c3f963e7eb4bdfb3367af7ddf9faab63c1c7db87f65`|
|scenario-fc100-islanded-v2 / app|`c3738260c4f18bf43dd2d7284f501386d2756572e74be23beb81b704a154eccb`|
|scenario-fc100-islanded-zero-hot-v2 / app|`aefdc289bec7a9da3c99398716f8549a0eef0bfdf765bd72a1264a95fe44a507`|
|demo-islanded-ramp / app|`88b04757bff6b8a1d88fc2de6a0396f1da203c724f3021cc4f1db1bd97d16ceb`|

## Remaining invalid ticks (candidate)

Classification priority matches ISL19: positive ledger curtailment first, then negative forcing, then approximately zero forcing. The diagnostic 1e-9 MW tolerance is PROPOSED_HERE, analysis-only, never a simulation input. Positive curtailment with zero integrated forcing can represent carried frequency.

|Scenario / arm|Total invalid|Curtailment positive|Deficit forcing|Carried / zero forcing|Other|
|---|---:|---:|---:|---:|---:|
|scenario-uneven-multisched-01 / baseline|53|0|27|26|0|
|scenario-uneven-multisched-01 / informed|0|0|0|0|0|
|scenario-h1-k8s-ray-24h / baseline|811|26|52|733|0|
|scenario-h1-k8s-ray-24h / informed|76|0|4|72|0|
|scenario-h2-slurm-24h / baseline|549|54|166|329|0|
|scenario-h2-slurm-24h / informed|412|51|42|319|0|
|S10_mit_supercloud_2021-08-11 / app|594|0|476|118|0|
|scenario-equinix-sj-1 / app|0|0|0|0|0|
|scenario-turbine-01 / app|0|0|0|0|0|
|scenario-hybrid-ai-100mw-addendum-i / app|54|0|10|44|0|
|scenario-100mw-fuel-cell-bess-diesel / app|0|0|0|0|0|
|scenario-fc100-islanded-v2 / app|0|0|0|0|0|
|scenario-fc100-islanded-zero-hot-v2 / app|214|0|207|7|0|
|demo-islanded-ramp / app|103|0|90|13|0|

## compare_runs (unchanged implementation)

### scenario-uneven-multisched-01/base

```json
{
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
}
```

### scenario-uneven-multisched-01/candidate

```json
{
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
}
```

### scenario-h1-k8s-ray-24h/base

```json
{
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
}
```

### scenario-h1-k8s-ray-24h/candidate

```json
{
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
}
```

### scenario-h2-slurm-24h/base

```json
{
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
```

### scenario-h2-slurm-24h/candidate

```json
{
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
```



### Remaining invalid frequency

Remaining invalid ticks are material and were **not fixed or clamped**:
H1 baseline has 811, including 733 classified as carried/zero forcing;
H2 baseline has 549, including 329 carried; H2 informed has 412,
including 319 carried. S10 has 594, including 476 deficit-forcing and
118 carried ticks. Its minimum changes from -729.1075118080669 to
-749.6905479257669 Hz while the non-frequency hash remains identical.
The categories use ISL19's priority ordering; positive curtailment is a
coincidence class, not proof of continuing positive rotor forcing.
No IMPL-ISL-20 or Phase 6 work was started.

## D11.4 — focused tests

IDs TC-ISL-23/24/25 were free and assigned to
`P/tests/test_dr_isl_dump_response.py` (candidate only, in stash).
All three passed. TC-23 also verifies timer carry, reset and a new episode.
TC-24 checks the exact original recurrence at all 500 substeps.

```json
{
  "TC-ISL-23": {
    "substeps": 500,
    "positive_forcing_substeps": 49,
    "negative_forcing_substeps": 0,
    "zero_forcing_substeps": 451,
    "dt_sub_s": 0.01,
    "first_forcing_mw": 0.98,
    "last_forcing_mw": 0.0,
    "frequency_hz": 60.1561875,
    "frequency_valid": true,
    "ledger_curtailment_mw": 1.0,
    "physical_balance_passed": true
  },
  "TC-ISL-24": {
    "substeps": 500,
    "positive_forcing_substeps": 0,
    "negative_forcing_substeps": 500,
    "zero_forcing_substeps": 0,
    "dt_sub_s": 0.01,
    "first_forcing_mw": -10.501,
    "last_forcing_mw": -10.501,
    "frequency_hz": -274.71937500000143,
    "frequency_valid": false,
    "ledger_curtailment_mw": 0.0,
    "physical_balance_passed": true
  },
  "TC-ISL-25": {
    "substeps": 500,
    "positive_forcing_substeps": 0,
    "negative_forcing_substeps": 0,
    "zero_forcing_substeps": 500,
    "dt_sub_s": 0.01,
    "first_forcing_mw": 0.0,
    "last_forcing_mw": 0.0,
    "frequency_hz": 60.0,
    "frequency_valid": true,
    "ledger_curtailment_mw": 1.0,
    "physical_balance_passed": true
  }
}
```

Applied focused set: **114 passed, 2 failed, 2 skipped**.
The two failures already occur on the unmodified base:
I4 and B1a both report asset_delivery_error_mw = 0.0 where their assertions
expect non-zero. Logs: `FOCUSED_APPLIED.txt`, `FOCUSED_EXISTING_BASE.txt`.
An additional scratch balance/patch set had 63 passed, 2 skipped.

Only seven existing sustained-surplus assertion/formula sections were
updated in the candidate: I1, I2 single-tick, I2 explicit,
TC-SURP-4, TC-SURP-5, B1b and B5. Their inputs and original excursion
tolerances were not loosened. Full test diffs are preserved below.

## D11.5 — full real-package suite: STOP

Literal counts:
```json
{
  "passed": 2199,
  "failed": 16,
  "skipped": 3,
  "xfailed": 23,
  "xpassed": 0,
  "error": 0,
  "exitstatus": 1
}
```

Reference: `tools/dr_isl/PHASE_5_FAILING_TESTS.txt`
(16 IDs).
Added: 1; removed: 1;
remaining: 15.
GPU load-profile result: `passed`.

```json
{
  "status": "STOPPED",
  "reference_failure_count": 16,
  "added": [
    "tests/test_addendum_g_stage3_option_c.py::test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess"
  ],
  "removed": [
    "tests/test_gpu_load_profile.py::test_gpu_load_profile"
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
    "tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load",
    "tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip"
  ],
  "gpu_outcome": "passed"
}
```

Complete output is preserved as bounded JUnit/results files in this
directory, and the final failing-ID list is
`tools/dr_isl/D11_FAILING_TESTS.txt`.
In-process tests imported the candidate from the real package. The
HTTP-based GPU test used the already-running development server on port
22126, which had not been restarted onto the unvalidated candidate.
Its reported pass must not be described as a fresh candidate-server test.

### Added failure: exact assertion

```text
def test_stage3_nonforming_fc_trip_reconciles_accounting_with_live_bess():
        result = _factory_tick(
            grid_forming=False,
            min_stable_frac=.5,
            ieee_1547_category=1,
            with_grid_forming_bess=True,
        )
        assert result.island_collapsed is False
        assert result.fuel_cell_ride_through_trips[0]["reason"] == "rocof"
        assert result.fuel_cell_output_mw == 0.0
        assert result.fuel_cell_achieved_output_mw == 0.0
        assert result.fuel_cell_reactive_output_mvar == 0.0
        assert result.fuel_cell_apparent_power_mva == 0.0
        assert result.p_generation_mw == pytest.approx(result.bess_output_mw)
>       assert result.frequency_forcing_mw == pytest.approx(
            result.p_generation_mw - result.p_demand_mw
        )
E       assert 0.49 == 0.0 ± 1.0e-12
E         
E         comparison failed
E         Obtained: 0.49
E         Expected: 0.0 ± 1.0e-12

tests/test_addendum_g_stage3_option_c.py:391: AssertionError
```

The fixture uses a 0.01 s interval
(`P/tests/test_addendum_g_stage3_option_c.py:83–94`), and the test requests
one 1 MW FC block with min_stable_frac 0.5 (`:64–72`, `:377–382`).
The first/only integrated substep sees 0.5 MW minus the achieved
0.01 MW sink = **0.49 MW**. Ride-through evaluation is AFTER integration
(candidate `P/core/simulation_core.py:3500–3524`). The FC then trips;
post-trip generation minus demand is **0.0 MW**.

Earlier assertions in `:384–390` passed: no island collapse, ROCOF trip,
zero FC achieved/real/reactive/apparent output, generation equals BESS.
The failure is at `:391–393`, which equates the public forcing channel to
the post-trip residual. The physical_balance assertion at `:394` was
NOT reached; this report does not claim it passed in this test.

This is a public-telemetry timing-contract conflict with the requested
last-actually-integrated definition. The test does not assert sustained
positive surplus forcing; updating it is outside the authorized stale-test
scope. It was left unchanged. Retaining the old public value would instead
depart from D11.2, and the non-frequency-hash exception did not trigger.
**Lloyd's decision is required; no fix, test waiver or new design was applied.**

## D11.6 — safe state and local Git

Implementation commit: **none**. Test commit: **none**.
Candidate stash: `29a087dc197579b81d674856a95a65778fbab914`.
Pre-report HEAD: `d47413ed30b14adae016e42c088f4e9bf7ade63f`.
Diff against 5225a05 for the entire package: `True`.
No channel CSV is tracked: `True`.
The report-only commit containing this report is identified in the final
chat response; no application code is included in that commit.

The main application was restored after the completed suite. No further
test, H2 evidence run, IMPL-ISL-20 or Phase 6 work was started.

The 15 remaining failures have the same failing assertion (14 cases) or
the same `AttributeError: 'str' object has no attribute 'value'` at
`P/core/lead_time_observations.py:66` (one case) as the Phase 5 JUnit.
Literal before/after tracebacks are in `d11/KNOWN_FAILURE_SIGNATURES.json`.

The development workflow `artifacts/gridsignal: web` was restarted with
the restored base application; startup completed and `GET /` returned
**200**. This is a base-code service check, not a candidate evidence run.
See `d11/RESTORED_SERVICE.json`.

## Full candidate diff (NOT applied on the restored main tree)

```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 08a5061..e35b704 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -943,6 +943,11 @@ def _cost_ranked_dispatch_allocations(
     return allocations
 
 
+def _dispatch_dump_response_mw(surplus_mw: float, elapsed_s: float, delay_s: float) -> float:
+    """DR D11 / IMPL-ISL-19: one linear sink response (b74830d)."""
+    return surplus_mw * (1.0 if delay_s <= 0.0 else min(1.0, elapsed_s / delay_s))
+
+
 def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     """The fixed-order tick evaluation (Design Spec Section 5 / 10.1):
 
@@ -3199,39 +3204,35 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     )
     # Once synchronized turbines have reached their minimum stable load and the
     # BESS has accepted all energy it physically can, the remaining positive
-    # residual is an explicit dispatch-curtailment sink.  Keep generation and
-    # turbine fuel physical, but do not subtract that sink before the
-    # electromechanical response: the rotor must see the surplus on this tick.
+    # residual is an explicit dispatch-curtailment sink. Keep generation and
+    # turbine fuel physical. DR D11 / IMPL-ISL-19 preserves b74830d's rotor
+    # transient, but subtracts the achieved dump response in each substep.
     #
     # Turbine rundown is already time-based above (machine ramp rate and the
     # existing commitment/unloading policy).  The explicit dump action has its
     # own configurable response delay on SiteConfig; this ledger value is the
     # surplus scheduled for that action, not a fictional change to measured
     # generation.  Keeping it as an explicit balance term preserves a closed
-    # physical ledger while frequency_forcing_mw receives the pre-curtailment
-    # residual.
+    # physical ledger. The swing equation sees only the residual not yet
+    # absorbed by the finite dump response; the ledger value is unchanged.
     _surplus_before_dump_mw = (
         max(0.0, _p_gen_mw - p_demand_mw) if _islanded else 0.0
     )
+    # DR D11 / IMPL-ISL-19, b74830d: preserve the scheduled ledger
+    # sink, but let the rotor see the finite, substep-resolved dump transient.
+    _dump_elapsed_start_s = state._dispatch_curtailment_elapsed_s
+    _dump_delay_s = max(
+        0.0, float(getattr(state.site, "dispatch_curtailment_response_delay_s", 0.0)),
+    )
     if _surplus_before_dump_mw <= 1e-12:
         state._dispatch_curtailment_elapsed_s = 0.0
+        _dump_elapsed_start_s = 0.0
         _p_dispatch_curtailed_mw = 0.0
     else:
-        _dump_delay_s = max(
-            0.0,
-            float(getattr(state.site, "dispatch_curtailment_response_delay_s", 0.0)),
-        )
-        state._dispatch_curtailment_elapsed_s = min(
+        _p_dispatch_curtailed_mw = _dispatch_dump_response_mw(
+            _surplus_before_dump_mw,
+            min(_dump_delay_s, _dump_elapsed_start_s + max(0.0, dt_seconds)),
             _dump_delay_s,
-            state._dispatch_curtailment_elapsed_s + max(0.0, dt_seconds),
-        )
-        _dump_response_fraction = (
-            1.0
-            if _dump_delay_s <= 0.0
-            else state._dispatch_curtailment_elapsed_s / _dump_delay_s
-        )
-        _p_dispatch_curtailed_mw = (
-            _surplus_before_dump_mw * min(1.0, _dump_response_fraction)
         )
     _balance_residual_mw = _p_gen_mw - p_demand_mw
 
@@ -3367,9 +3368,10 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     _fp_collapse_frequency_hz: Optional[float] = None
     _fc_ride_through_trips: list[dict] = []
     # FC trips can change the supply imbalance during this outer tick.  Keep a
-    # mutable forcing for the sub-step integrator; the public forcing is
-    # reconciled to the post-trip balance below.
+    # mutable raw forcing for the sub-step integrator and post-trip D4 balance.
+    # D11 public telemetry reports the last executed net substep, below.
     _dynamic_frequency_forcing_mw = _frequency_forcing_mw
+    _last_integrated_frequency_forcing_mw = 0.0
     # Phase 2A: protection_provisional — True for every islanded tick.
     # D_eff uses d_motor + fixed_speed_cooling_fraction (both PROVISIONAL-UNMEASURED).
     _protection_provisional: bool = _islanded
@@ -3460,6 +3462,23 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
                 break
             _f_dev = _f - _f0
 
+            # D11: advance from the episode snapshot, not repeated additions.
+            # The last substep uses exact outer dt to preserve ledger timing.
+            _achieved_dump_mw = 0.0
+            if _surplus_before_dump_mw > 1e-12:
+                _dump_sub_elapsed_s = (
+                    dt_seconds if _k == _n_sub - 1 else (_k + 1) * _dt_sub
+                )
+                state._dispatch_curtailment_elapsed_s = min(
+                    _dump_delay_s,
+                    _dump_elapsed_start_s + max(0.0, _dump_sub_elapsed_s),
+                )
+                _achieved_dump_mw = _dispatch_dump_response_mw(
+                    _surplus_before_dump_mw,
+                    state._dispatch_curtailment_elapsed_s,
+                    _dump_delay_s,
+                )
+
             # Phase 3: Swing equation sub-step.
             # 2·H_agg/f0 · df/dt = P_net/S_base − D_eff·(f−f0)/f0
             # => df/dt = [P_net_pu·f0 − D_eff·f_dev] / (2·H_agg)
@@ -3479,9 +3498,12 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             # Within-tick shed from UFLS is added to the forcing since shed
             # reduces the effective load immediately (sub-step granularity).
             if _s_base_mva > 0.0 and _h_aggregate > 0.0:
+                _last_integrated_frequency_forcing_mw = (
+                    _dynamic_frequency_forcing_mw - _achieved_dump_mw
+                    + _shed_this_tick_mw
+                )
                 _p_net_pu = (
-                    (_dynamic_frequency_forcing_mw + _shed_this_tick_mw)
-                    / _s_base_mva
+                    _last_integrated_frequency_forcing_mw / _s_base_mva
                 )
                 _df_dt_sub = (
                     _p_net_pu * _f0 - _d_eff * _f_dev
@@ -4122,7 +4144,12 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # Phase 13.2: balance decomposition — three independent channels.
         # D4 (sum == scratch residual) is asserted inline above, not via a broadcast field.
         grid_exchange_mw=_grid_exchange_mw,
-        frequency_forcing_mw=_frequency_forcing_mw,
+        # D11: last executed substep's net MW, before motor damping.
+        # Keep the raw forcing above unchanged for the D4 identity.
+        frequency_forcing_mw=(
+            _last_integrated_frequency_forcing_mw if _islanded
+            else _frequency_forcing_mw
+        ),
         asset_delivery_error_mw=_asset_delivery_error_mw,
         # Phase 13.4: setpoint/actual split.
         model_error_mw=_model_error_mw,
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_13_3_frequency.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_13_3_frequency.py
index b60c7e0..f43fe73 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_13_3_frequency.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_13_3_frequency.py
@@ -145,7 +145,7 @@ class TestI1FrequencyDeviationVisible:
     """I1: A power surplus in islanded mode appears as a frequency_hz deviation.
 
     Mechanism: 1 MW solar override with no GPU load → _p_commanded = 1 MW,
-    p_total ≈ 0 → frequency_forcing_mw ≈ 1 MW > 0 → df/dt > 0 → frequency rises.
+    p_total ≈ 0 → positive finite forcing → df/dt > 0 → frequency rises (D11).
     Verified: frequency_hz > 50 Hz and frequency_forcing_mw is the direct cause.
     """
 
@@ -157,8 +157,10 @@ class TestI1FrequencyDeviationVisible:
         # No GPU job → p_total ≈ 0
         tick = _run_tick(state, sim_time=0.0, dt=0.1)
 
-        assert tick.frequency_forcing_mw > 0.9, (
-            f"I1: frequency_forcing_mw must be ≈ 1.0 MW with 1 MW solar surplus; "
+        # DR D11: the last substep has already absorbed 0.1 / 0.5 of the surplus.
+        expected_forcing = 1.0 * (1.0 - 0.1 / state.site.dispatch_curtailment_response_delay_s)
+        assert tick.frequency_forcing_mw == pytest.approx(expected_forcing), (
+            f"I1: frequency_forcing_mw must follow the finite dump response; "
             f"got {tick.frequency_forcing_mw:.6f} MW"
         )
         assert tick.frequency_hz > f_nom, (
@@ -178,7 +180,7 @@ class TestI1FrequencyDeviationVisible:
 
 class TestI2SwingEquationAccuracy:
     """I2: The frequency change must match
-        Δf = frequency_forcing_mw / (2·H·S_base) · f₀ · dt
+        Δf = Σ frequency_forcing_mw(k)·dt_sub / (2·H·S_base) · f₀
     within ±10%.  Verifies the formula is implemented as specified.
     """
 
@@ -202,7 +204,15 @@ class TestI2SwingEquationAccuracy:
         # §INV-INERTIA: S_base (MVA) = on-bus rated_mw / power_factor.
         # The fixture pre-forces gt-1 to SYNCHRONISED so it contributes to S_base.
         s_base_mva = S_base_rated / state.site.power_factor
-        df_predicted = ff / (2.0 * H * s_base_mva) * f0 * dt
+        # DR D11: integrate the finite response, not the final forcing over all dt.
+        n_sub = max(1, round(dt / state.site.dynamic_step_s))
+        dt_sub = dt / n_sub
+        delay = state.site.dispatch_curtailment_response_delay_s
+        forcing_integral = sum(
+            (1.0 - min(1.0, (k + 1) * dt_sub / delay)) * dt_sub
+            for k in range(n_sub)
+        )
+        df_predicted = forcing_integral / (2.0 * H * s_base_mva) * f0
         df_actual = tick.frequency_hz - f0
 
         if abs(ff) < 1e-9:
@@ -216,10 +226,10 @@ class TestI2SwingEquationAccuracy:
         )
 
     def test_I2_explicit_formula_fixture(self):
-        """I2 (explicit): 1 MW forcing → Δf = 1/(2×4×(10/0.85))×50×5 = 2.65625 Hz.
+        """I2 (D11): finite 1 MW dump transient gives Δf ≈ 0.13015625 Hz.
 
         S_base (MVA) = rated_mw / power_factor = 10 / 0.85 ≈ 11.765 MVA.
-        Δf = 1 / (2 × 4 × 11.765) × 50 × 5 ≈ 2.65625 Hz (was 3.125 Hz at pf=1).
+        Integrate the response over substeps; do not sustain 1 MW for all 5 s.
         """
         H = 4.0
         S_base_rated_mw = 10.0
@@ -233,18 +243,26 @@ class TestI2SwingEquationAccuracy:
             solar_mw=1.0,
         )
         f0 = state.site.frequency_nominal_hz  # sourced from config (= 50.0)
-        # No GPU job → p_total ≈ 0 → frequency_forcing ≈ 1 MW
+        # No GPU job: 1 MW surplus, fully absorbed after the finite D11 delay.
         tick = _run_tick(state, sim_time=0.0, dt=dt)
 
-        assert tick.frequency_forcing_mw == pytest.approx(1.0, abs=0.1), (
-            f"I2 precondition: frequency_forcing_mw should be ~1 MW; "
+        assert tick.frequency_forcing_mw == pytest.approx(0.0, abs=0.1), (
+            f"I2 precondition: final forcing should be zero after the D11 response; "
             f"got {tick.frequency_forcing_mw:.6f}"
         )
 
         # §INV-INERTIA: S_base (MVA) = on-bus rated_mw / power_factor.
         # The fixture pre-forces gt-1 to SYNCHRONISED so it contributes to S_base.
         s_base_mva = S_base_rated_mw / state.site.power_factor
-        df_predicted = 1.0 / (2.0 * H * s_base_mva) * f0 * dt
+        # DR D11: unchanged swing equation, with substep-resolved forcing.
+        n_sub = max(1, round(dt / state.site.dynamic_step_s))
+        dt_sub = dt / n_sub
+        delay = state.site.dispatch_curtailment_response_delay_s
+        forcing_integral = sum(
+            (1.0 - min(1.0, (k + 1) * dt_sub / delay)) * dt_sub
+            for k in range(n_sub)
+        )
+        df_predicted = forcing_integral / (2.0 * H * s_base_mva) * f0
         df_actual = tick.frequency_hz - f0
         assert abs(df_actual - df_predicted) < df_predicted * 0.11, (   # ±10% tolerance
             f"I2: Δf={df_actual:.4f} Hz; predicted={df_predicted:.4f} Hz; "
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_bess_surplus_absorption.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_bess_surplus_absorption.py
index 8915b86..62d1a72 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_bess_surplus_absorption.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_bess_surplus_absorption.py
@@ -254,7 +254,7 @@ class TestSurplusAbsorption:
 
     def test_TC_SURP_4_partial_absorption_when_rated_mw_limits(self):
         """TC-SURP-4: When fleet_surplus > rated_mw, BESS absorbs at most rated_mw.
-        Some surplus remains and routes to frequency_forcing_mw (islanded)."""
+        Remaining surplus drives only the finite D11 dump-response transient."""
         # fleet_surplus ≈ 10 MW (turbine), BESS rated at 3 MW.
         state = _make_state(
             turbine_output_mw=10.0,
@@ -268,14 +268,15 @@ class TestSurplusAbsorption:
         assert absorbed == pytest.approx(3.0, abs=0.05), (
             f"TC-SURP-4: absorption limited to rated_mw=3.0 MW; got {absorbed:.4f} MW"
         )
-        # Residual surplus (10 - 3 = 7 MW) routes to frequency_forcing_mw.
-        assert tick.frequency_forcing_mw > 0.0, (
-            f"TC-SURP-4: un-absorbed surplus must appear in frequency_forcing_mw; "
+        # DR D11: the dump absorbs the residual after its finite response.
+        assert tick.p_dispatch_curtailed_mw > 0.0
+        assert tick.frequency_forcing_mw == 0.0, (
+            f"TC-SURP-4: forcing must be zero after the dump response; "
             f"got {tick.frequency_forcing_mw:.4f}"
         )
 
     def test_TC_SURP_5_absorption_reduces_frequency_forcing(self):
-        """TC-SURP-5: BESS absorption shrinks frequency_forcing_mw in island mode.
+        """TC-SURP-5: BESS absorption shrinks the D11 forcing transient in island mode.
         With a BESS that can absorb and one that cannot (full), the latter must
         produce a larger frequency deviation for the same generation surplus."""
         # Two scenarios: same turbine surplus, one BESS absorbs, one cannot.
@@ -285,11 +286,12 @@ class TestSurplusAbsorption:
         tick_absorb = _run_tick(state_absorb, dt=1.0)
         tick_full   = _run_tick(state_full,   dt=1.0)
 
-        # When BESS absorbs, balance_residual is smaller → frequency_forcing is smaller.
-        assert tick_absorb.frequency_forcing_mw < tick_full.frequency_forcing_mw, (
-            f"TC-SURP-5: BESS absorption must reduce frequency_forcing_mw; "
-            f"absorb={tick_absorb.frequency_forcing_mw:.4f}, "
-            f"full={tick_full.frequency_forcing_mw:.4f}"
+        # DR D11: both final forcings are zero; the integrated transient differs.
+        assert tick_absorb.frequency_forcing_mw == tick_full.frequency_forcing_mw == 0.0
+        assert tick_absorb.frequency_hz < tick_full.frequency_hz, (
+            f"TC-SURP-5: BESS absorption must reduce the frequency excursion; "
+            f"absorb={tick_absorb.frequency_hz:.4f}, "
+            f"full={tick_full.frequency_hz:.4f}"
         )
 
     def test_TC_SURP_6_taper_reset_bess_re_engages_on_shortfall(self):
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_dump_response.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_dump_response.py
new file mode 100644
index 0000000..f367342
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_dump_response.py
@@ -0,0 +1,113 @@
+"""TC-ISL-23–25. D11 finite dump response; no control/physics fixture overrides."""
+import inspect
+import sys
+
+import core.simulation_core as core
+from tests.test_13_3_frequency import _make_islanded_solar_state
+from tests.test_forecast_path import _run_tick, _starting_signal
+
+# PROPOSED_HERE: all numeric fixture inputs below are synthetic, chosen to
+# isolate a 1 MW solar surplus or an uncovered IT demand, not plant calibration.
+
+
+def _state(delay=0.5, *, deficit=False):
+    state, _ = _make_islanded_solar_state(
+        f_nominal=60.0, solar_mw=0.0 if deficit else 1.0,
+        turbine_rated_mw=1.0 if deficit else 10.0,
+        turbine_ramp=0.001 if deficit else 5.0,
+        bess_soc=0.0 if deficit else 1.0,
+    )
+    state.site.dispatch_curtailment_response_delay_s = delay
+    if deficit:
+        state.apply_workload_signal(_starting_signal(
+            nodes=1000, site_id=state.site.site_id), dt_lead_seconds=0.0)
+    return state
+
+
+def _trace_tick(state, sim_time=0.0):
+    """Observe the real integrator; never replace its state or calculations."""
+    fn = core.evaluate_tick
+    lines, start = inspect.getsourcelines(fn)
+    marker = next(i for i, line in enumerate(lines)
+                  if "# If _s_base_mva==0 or _h_aggregate==0" in line)
+    line_number = start + next(i for i in range(marker + 1, len(lines))
+                              if lines[i].strip().startswith("if isinstance("))
+    samples = []
+
+    def trace(frame, event, arg):
+        if frame.f_code is fn.__code__ and event == "line" and frame.f_lineno == line_number:
+            v = frame.f_locals
+            samples.append({k: v[k] for k in (
+                "_k", "_f", "_f0", "_s_base_mva", "_h_aggregate",
+                "_dynamic_frequency_forcing_mw", "_shed_this_tick_mw",
+                "_last_integrated_frequency_forcing_mw", "_d_eff", "_dt_sub")})
+        return trace
+
+    previous = sys.gettrace()
+    sys.settrace(trace)
+    try:
+        tick = _run_tick(state, sim_time=sim_time, dt=5.0)
+    finally:
+        sys.settrace(previous)
+    return tick, samples
+
+
+def test_tc_isl_23_finite_surplus_response_and_unchanged_ledger():
+    state = _state()
+    tick, samples = _trace_tick(state)
+    assert len(samples) == 500
+    forces = [s["_last_integrated_frequency_forcing_mw"] for s in samples]
+    assert all(f > 0 for f in forces[:49])
+    assert all(f == 0 for f in forces[49:])
+    assert tick.frequency_forcing_mw == 0
+    assert tick.frequency_valid and 54.0 <= tick.frequency_hz <= 66.0
+    # Pre-D11 ledger: min(delay, outer_dt)/delay * 1 MW = 1 MW.
+    assert tick.p_dispatch_curtailed_mw == 1.0
+    assert tick.physical_balance.passed
+    assert state._dispatch_curtailment_elapsed_s == 0.5
+    continued, continuing_samples = _trace_tick(state, sim_time=5.0)
+    assert all(s["_last_integrated_frequency_forcing_mw"] == 0
+               for s in continuing_samples)
+    assert continued.p_dispatch_curtailed_mw == 1.0
+    state.solar_arrays[0].override_output_mw(0.0)
+    _run_tick(state, sim_time=10.0, dt=5.0)
+    assert state._dispatch_curtailment_elapsed_s == 0.0
+    state.solar_arrays[0].override_output_mw(1.0)
+    restarted, restarting_samples = _trace_tick(state, sim_time=15.0)
+    assert restarting_samples[0]["_last_integrated_frequency_forcing_mw"] > 0
+    assert restarting_samples[-1]["_last_integrated_frequency_forcing_mw"] == 0
+    assert restarted.p_dispatch_curtailed_mw == 1.0
+
+
+def test_tc_isl_24_deficit_matches_original_swing_trajectory():
+    state = _state(deficit=True)
+    tick, samples = _trace_tick(state)
+    assert len(samples) == 500
+    assert tick.frequency_forcing_mw < 0
+    expected = 60.0
+    for s in samples:
+        original_forcing = (
+            s["_dynamic_frequency_forcing_mw"] + s["_shed_this_tick_mw"])
+        assert original_forcing < 0
+        assert s["_last_integrated_frequency_forcing_mw"] == original_forcing
+        # Unchanged pre-D11 swing recurrence, using the actual inertial/damping
+        # inputs. Exact equality checks the entire 500-substep trajectory.
+        derivative = (
+            (original_forcing / s["_s_base_mva"]) * s["_f0"]
+            - s["_d_eff"] * (expected - s["_f0"])
+        ) / (2.0 * s["_h_aggregate"])
+        expected += derivative * s["_dt_sub"]
+        assert s["_f"] == expected
+    assert tick.frequency_hz == expected
+    assert tick.p_dispatch_curtailed_mw == 0
+
+
+def test_tc_isl_25_zero_delay_from_first_substep():
+    state = _state(delay=0.0)
+    tick, samples = _trace_tick(state)
+    assert len(samples) == 500
+    assert all(s["_last_integrated_frequency_forcing_mw"] == 0 for s in samples)
+    assert tick.frequency_hz == 60.0
+    assert tick.frequency_forcing_mw == 0
+    assert tick.p_dispatch_curtailed_mw == 1.0
+    assert tick.physical_balance.passed
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_forecast_path.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_forecast_path.py
index ce84f80..3a4edc1 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_forecast_path.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_forecast_path.py
@@ -687,9 +687,10 @@ class TestDispatchTruthfulness:
             f"turbine_out={tick.turbine_output_mw:.6f} gt_setpoint={tick.gt_setpoint_mw:.6f}  "
             f"bess_out={tick.bess_output_mw:.6f} bess_setpoint={tick.bess_setpoint_mw:.6f}"
         )
-        # The 1 MW surplus IS visible in the forcing channel (islanded).
-        assert tick.frequency_forcing_mw > 0.5, (
-            f"B1b: 1 MW solar surplus should appear in frequency_forcing_mw; "
+        # DR D11: surplus remains in the ledger, not sustained rotor forcing.
+        assert tick.p_dispatch_curtailed_mw == pytest.approx(1.0)
+        assert tick.frequency_forcing_mw == 0.0, (
+            f"B1b: forcing should be zero after the finite dump response; "
             f"got {tick.frequency_forcing_mw:.9f}"
         )
         # Frequency rose (positive forcing drives f above nominal).
@@ -826,9 +827,10 @@ class TestDispatchTruthfulness:
         tick = _run_tick(state, sim_time=0.0, dt=0.1)
 
         # 1 MW solar surplus → _p_commanded = 0 + 0 + 1.0 = 1.0; p_total ≈ 0
-        # frequency_forcing ≈ 1.0 MW (exact only when cooling = 0)
-        assert tick.frequency_forcing_mw > 0.9, (
-            f"B5 precondition: frequency_forcing_mw must be ≈ 1.0 MW with "
+        # DR D11: final forcing includes the response accrued over 0.1 s.
+        expected_forcing = 1.0 * (1.0 - 0.1 / _site_b5.dispatch_curtailment_response_delay_s)
+        assert tick.frequency_forcing_mw == pytest.approx(expected_forcing), (
+            f"B5 precondition: frequency_forcing_mw must follow the dump response with "
             f"1 MW solar surplus; got {tick.frequency_forcing_mw:.6f}"
         )
         # _site_b5.frequency_nominal_hz = 50.0 (EU/APAC fixture, set by intent above).
@@ -847,7 +849,15 @@ class TestDispatchTruthfulness:
         _H = 4.0
         _f0 = _site_b5.frequency_nominal_hz  # sourced from config (50.0 EU/APAC)
         _dt = 0.1
-        _df_expected = tick.frequency_forcing_mw / (2.0 * _H * _s_base_mw) * _f0 * _dt
+        # DR D11: integrate substep forcing rather than multiplying its endpoint.
+        _n_sub = max(1, round(_dt / _site_b5.dynamic_step_s))
+        _dt_sub = _dt / _n_sub
+        _delay = _site_b5.dispatch_curtailment_response_delay_s
+        _forcing_integral = sum(
+            (1.0 - min(1.0, (k + 1) * _dt_sub / _delay)) * _dt_sub
+            for k in range(_n_sub)
+        )
+        _df_expected = _forcing_integral / (2.0 * _H * _s_base_mw) * _f0
         _df_actual = tick.frequency_hz - _f0
         assert abs(_df_actual - _df_expected) / max(abs(_df_expected), 1e-9) < 0.10, (
             f"B5: frequency deviation {_df_actual:.6f} Hz should be within "
diff --git a/docs/addendum-h-phase2a-change-record.md b/docs/addendum-h-phase2a-change-record.md
index 7ae1dab..fdf9603 100644
--- a/docs/addendum-h-phase2a-change-record.md
+++ b/docs/addendum-h-phase2a-change-record.md
@@ -37,19 +37,29 @@ This work preserves the Phase 2a contract:
 The repair restores the intended ordering without changing commitment policy,
 the acceptance rule, the baseline fixture, or alert/disposition behavior:
 
-- Islanded `frequency_forcing_mw` and `p_imbalance_mw` now use measured
-  generation minus served load before the explicit dispatch-curtailment sink.
-  Positive surplus therefore reaches the swing equation on the same tick it
-  occurs.
+- The original repair used the measured pre-dump residual for islanded swing
+  forcing. **DR D11 / IMPL-ISL-19 supersedes its sustained-surplus forcing:**
+  the rotor sees surplus only until the finite dump response absorbs it.
+  `p_imbalance_mw`, D7 served/unserved accounting and the ledger sink are
+  unchanged; deficit forcing is not netted against recorded unserved load.
 - Turbine rundown remains governed by the existing physical ramp and
   commitment/unloading paths. The explicit dump sink is applied only to the
   residual after BESS absorption and turbine rundown.
 - The dump response has a configurable
   `dispatch_curtailment_response_delay_s` input, marked `PROPOSED_HERE`, and
-  ramps the explicit sink to full response over that delay. The default
-  0.5-second delay is below the unchanged 5-second smoke interval.
+  ramps to full response over that delay. D11 advances the existing episode
+  timer per frequency substep, carries it across ticks and preserves its
+  reset condition. Delay zero gives full response immediately. The unchanged
+  0.5-second default is below the unchanged 5-second smoke interval.
 - `p_dispatch_curtailed_mw` remains an explicit term in the physical balance
-  ledger, and the separate unaccounted-surplus channel remains zero.
+  ledger at its existing outer-tick scheduled value, not a substep average.
+  The separate unaccounted-surplus channel remains zero.
+- Public islanded `frequency_forcing_mw` is the net MW actually integrated in
+  the last executed substep, before motor damping: raw dynamic forcing minus
+  achieved dump response plus already-active UFLS shed. Existing FC-trip and
+  UFLS adjustments are unchanged. Grid-tied telemetry is unchanged. This
+  retains b74830d's same-tick rotor transient without integrating already
+  absorbed surplus indefinitely; it adds no frequency clamp or protection.
 
 The implementation is in `core/simulation_core.py` (balance ordering and
 response timer), with the configuration surfaced through `core/models.py`,

```
