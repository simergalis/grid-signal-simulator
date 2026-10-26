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
