# D6g step 1 — IMPL-ISL-29 active-job forecast power

## Change

- Implementation commit: `80f00d0` — `IMPL-ISL-29: preserve active job power in forecast cache`.
- `P/runtime/turbine_commitment.py:282–301` factors event-index refresh into `_ensure_forecast_event_index`; `_job_state_at` uses that shared helper at `:317–320`.
- `_announced_start_times` accepts an optional callback at `:402–417`. The forecast caller passes its real `power_for_event` at `:531–535`, so current active-job state uses the same power values as forecast profile samples. The comment cites DR D6d/D6e and IMPL-ISL-29.
- The future-burst refusal caller at `:708–711` has no event-power callback. It initializes/uses the sorted event index but does not advance or seed the shared job-state cache. This preserves announced-start detection without storing zero-MW active jobs.
- `_background_samples` was not changed. The 360-second start horizon was not changed.

## Tests and verification

TC-ISL IDs 74–79 are newly used; no collisions were found in `P/tests/`.

| ID | Test | Coverage |
|---|---|---|
| TC-ISL-74 | `test_tc_isl_74_active_announced_job_uses_callback_in_current_and_profile` | Active announced job contributes callback MW at the current point and profile samples. |
| TC-ISL-75 | `test_tc_isl_75_starting_and_scale_records_count_one_job_once` | Overlapping STARTING/SCALE records update one job entry rather than summing. |
| TC-ISL-76 | `test_tc_isl_76_job_end_removes_power_from_later_profile_samples` | JOB_END removes load from later forecast points. |
| TC-ISL-77 | `test_tc_isl_77_measured_history_residual_is_unchanged_and_counted_once` | Historical residual remains 8 MW; forecast is 14 MW (8 MW residual plus 4 MW IT and 2 MW cooling), without double counting. |
| TC-ISL-78 | `test_tc_isl_78_baseline_mode_does_not_build_or_consume_forecast` | Conventional mode does not invoke the callback or build forecast state. |
| TC-ISL-79 | `test_tc_isl_79_announced_scan_without_callback_does_not_seed_zero_state` | No-callback path indexes announcements without advancing or poisoning the job-state cache. |

Final focused command set: the new test file; `test_addendum_h_phase2a_commitment.py`, `test_fuel_cell_turbine_commitment.py`, and `test_addendum_h_phase2b_stage2.py`; study-harness tests TC-ISL-67, 68, 71, 72, and 73; MCP tests TC-ISL-65, 66, and 70. Result: **55 passed, 0 failed, 2 warnings, 29.06 seconds**. One warning is the existing Starlette/httpx deprecation; the other is the existing BESS C-rate warning in TC-ISL-131.

The first focused attempt exposed a no-callback event-index regression in TC-ISL-133: the refusal reason changed because the mocked forecast had not initialized the sorted event list. Factoring index initialization separately from power-state advancement fixed it; TC-ISL-133 passes in the final run.

There is no file matching `tests/test_turbine_commitment*.py` under `P/tests/`; the three commitment-related files listed above were run instead. No full suite or standalone counterfactual scenario runs were requested or performed. The test selection includes the existing TC-ISL-115 headless smoke test.

## Scope and repository state

The only implementation file changed is `P/runtime/turbine_commitment.py`; the new test file is `P/tests/test_d6e_forecast_active_job_power.py`. This report and the new test file are committed with the tests commit. An unrelated pre-existing modification to `artifacts/mockup-sandbox/src/.generated/mockup-components.ts` was left untouched and excluded from both commits.

## Step 2 — seed-42 study-pair counterfactuals

Each pair was run once through `StudyRunExecutor.run_pair`. All four conventional/baseline arms match their pre-fix references exactly across physical hash, unserved energy, peak unserved power, starts, turbine fuel, and invalid-frequency tick count. Counterfactual JSON files contain the full values and source references.

| Scenario | Arm | Physical hash before → after | Unserved MWh before → after | Peak unserved MW before → after | Starts before → after | Fuel MMBtu before → after | Invalid-frequency ticks before → after | compare_runs before → after |
|---|---|---|---:|---:|---:|---:|---:|---|
| S10 (`S10_COUNTERFACTUAL.json`) | Baseline | `22a109ae31e928518db467fbe3ff90675604ce2e38c0f6ed5551c21aa10d9a3f` → same | 5.535769413 → 5.535769413 | 16.8004944 → 16.8004944 | 37 → 37 | 7785.288838529 → 7785.288838529 | 519 → 519 | FAIL (8/10; unserved and peak conditions) → FAIL (9/10; peak condition) |
| S10 (`S10_COUNTERFACTUAL.json`) | Informed | `31500784c695aec403662bb71ccccb0dff6e74d1cb5440197b43251330d380b0` → `7e63ec904f1a3624dad21207f0fffb95a2c834d056ac43446152399de6a5d63b` | 13.94040689 → 4.399430718 | 31.8004944 → 31.8004944 | 47 → 42 | 7428.01542868 → 7471.889208508 | 628 → 226 | FAIL (8/10; unserved and peak conditions) → FAIL (9/10; peak condition) |
| Base demo (`BASE_COUNTERFACTUAL.json`) | Baseline | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` → same | 0.351692658 → 0.351692658 | 22.309362466 → 22.309362466 | 2 → 2 | 714.363019086 → 714.363019086 | 53 → 53 | PASS (10/10) → PASS (10/10) |
| Base demo (`BASE_COUNTERFACTUAL.json`) | Informed | `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754` → `a5cb3e37d8f8c0c2bd58ede455182a25c7c0fdef62e7e9de6479c389522af049` | 0.020719074 → 0.020722990 | 7.523250570 → 7.524660522 | 2 → 2 | 665.398247704 → 665.395402401 | 0 → 0 | PASS (10/10) → PASS (10/10) |
| H1-24h (`H1_COUNTERFACTUAL.json`) | Baseline | `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` → same | 0.894372986 → 0.894372986 | 35.021533247 → 35.021533247 | 12 → 12 | 6039.74023024 → 6039.74023024 | 811 → 811 | PASS (10/10) → PASS (10/10) |
| H1-24h (`H1_COUNTERFACTUAL.json`) | Informed | `437d480102d11676df747a5ddc742cd29c9785956c1255098dc8d00d9f18a264` → `902465184c53186fafc4607de77eb1f60c2fe094c53021c16988979f54ca4474` | 0.124133405 → 0.138684661 | 20.746308977 → 20.746308977 | 12 → 12 | 5848.898717938 → 5836.177208739 | 76 → 76 | PASS (10/10) → PASS (10/10) |
| H2-24h (`H2_COUNTERFACTUAL.json`) | Baseline | `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` → same | 5.011418076 → 5.011418076 | 44.86838787 → 44.86838787 | 11 → 11 | 5330.503098761 → 5330.503098761 | 549 → 549 | PASS (10/10) → PASS (10/10) |
| H2-24h (`H2_COUNTERFACTUAL.json`) | Informed | `17954e9420ad8d0c9493a690c03cd670ae0a5f57df60f801b7c292aeea3a9fba` → same | 0.859772492 → 0.859772492 | 42.36838787 → 42.36838787 | 14 → 14 | 5327.34949305 → 5327.34949305 | 412 → 412 | PASS (10/10) → PASS (10/10) |

Evidence commits: S10 `ba2d361`, base demo `5b14d09`, H1 `ee3350e`, H2 `e8b2cef`. H2 baseline gate passed exactly; compare_runs passed all 10 conditions before and after.
