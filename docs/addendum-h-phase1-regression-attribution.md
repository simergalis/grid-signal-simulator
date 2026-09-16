# Addendum H Phase 1 — Regression Attribution

Date: 2026-09-16

## Conclusion

The complete matched comparison does **not establish a Phase 1 regression**. The raw outcome diff contains one apparent NEW failure, `tests/test_gpu_load_profile.py::test_gpu_load_profile`, but it is nondeterministic and unrelated to the Phase 1 diff: the same node passed three isolated serial runs at both commits. No Phase 1 source change touches the GPU profile path.

Phase 2 remains deferred.

## Commit boundary

- **Pre-change:** `e874c455b9c7d5b31c72fbac5594ef970e559f4d` (`e874c455`, `Update scenario route path parameter`)
- **Current:** `8b2b9198804af3bb048c675bbf9d3cc28bb87e80` (`8b2b919`, `Implement new simulation core modules and API schema extensions`)

The pre-change commit was identified as the direct parent of the current commit. `git show --stat 8b2b919` showed the current commit introducing the Addendum H fuel-model files and changes, including the new `tests/test_addendum_h_phase1.py`; `git diff e874c45 8b2b919` contains the Phase 1 fuel parameters, accounting, telemetry, API, frontend types, and tests. No earlier commit message explicitly named Addendum H, so the file-level diff was used to confirm the boundary.

## Test execution method

Both commits were checked out into detached temporary worktrees outside the main project tree:

- `/tmp/gridsignal-h-pre`
- `/tmp/gridsignal-h-current`

The worktrees used the same Python executable, pytest flags, `PYTHONHASHSEED=0`, and per-file execution method. The main workspace was not checked out or modified. Pre-existing ignored source/test files required by this repository were overlaid identically into both temporary worktrees; the Phase 1 test file was present only at the current commit.

The 154 pre-change and 155 current test-file batches were executed. The current `test_gpu_load_profile.py` file batch exceeded the first per-batch limit and was split to its single node; the single-test batch completed and produced the recorded failure. No collected test was left unrun, and there were no collection errors in either full matrix.

The full raw lists are in:

- `addendum-h-phase1-pre-change-outcomes.jsonl`
- `addendum-h-phase1-current-outcomes.jsonl`

## Totals

| Outcome | Pre-change | Current |
|---|---:|---:|
| Collected | 2033 | 2043 |
| Passed | 1937 | 1946 |
| Failed | 71 | 72 |
| Errored | 0 | 0 |
| Skipped | 3 | 3 |
| XFailed | 22 | 22 |
| XPassed | 0 | 0 |

## Outcome diff

- **NEW failures in the raw full-matrix comparison:** 1
- **FIXED:** 0
- **PRE-EXISTING failures:** 71
- **Tests present only at pre-change:** 0
- **Tests present only at current:** 10

### Tests present only at current

These are the ten Addendum H Phase 1 tests. All passed:

- `tests/test_addendum_h_phase1.py::test_aeroderivative_defaults_have_explicit_provenance`
- `tests/test_addendum_h_phase1.py::test_constant_load_accounts_for_load_no_load_headroom_and_low_load_time`
- `tests/test_addendum_h_phase1.py::test_factory_applies_aeroderivative_fuel_defaults_without_scenario_edit`
- `tests/test_addendum_h_phase1.py::test_frame_without_fuel_parameters_is_not_modelled`
- `tests/test_addendum_h_phase1.py::test_fuel_fields_are_present_in_the_wire_payload`
- `tests/test_addendum_h_phase1.py::test_hot_standby_fuel_is_separate_from_synchronized_fuel`
- `tests/test_addendum_h_phase1.py::test_part_load_heat_rate_is_linearly_interpolated`
- `tests/test_addendum_h_phase1.py::test_schema_accepts_optional_fuel_parameters_and_provenance`
- `tests/test_addendum_h_phase1.py::test_start_fuel_uses_the_selected_thermal_tier`
- `tests/test_addendum_h_phase1.py::test_startup_interval_does_not_receive_a_full_synchronized_fuel_credit`

### NEW failure in the raw matrix

#### `tests/test_gpu_load_profile.py::test_gpu_load_profile`

- **Failure:** `tests/test_gpu_load_profile.py:169`, called from `tests/test_gpu_load_profile.py:275`
- **Message:** `[FAIL-A] phase-2 sim_t=720.0s: gpu_load_fraction=1.0 expected 0.5`
- **Likely cause:** nondeterministic black-box run/timing behavior, not Addendum H. The test polls a live run and asserts the profile at the phase boundary. It passed three isolated serial runs at both commits. The Phase 1 diff adds turbine fuel configuration/accounting and metadata; it does not alter the GPU profile setup at `runtime/scenario_factory.py:1182-1185` or the GPU tick path. The only Phase 1 factory additions are turbine-fuel wiring and telemetry at approximately `runtime/scenario_factory.py:820-900` and `1943-1961`.

A preliminary concurrent matrix also produced an apparent `tests/test_auth.py::test_login_set_cookie_no_secure_flag_by_default` NEW failure due an SQLite commit/lock path. That result was not used in the final raw comparison: the test passed in isolated serial runs at both commits. It was a worktree-concurrency artifact, not a Phase 1 failure.

## Earlier suspected failures

### Legacy 900-second cold-start expectation

`tests/test_cold_start_override.py::TestTC251DefaultPreserved::test_default_cold_start_is_900_seconds_when_not_overridden` failed at both commits with the same assertion that the default cold start should be 900 seconds. It is therefore PRE-EXISTING, not introduced by Phase 1.

The related override test passed at both commits, further separating the failure from Phase 1 fuel accounting.

### Hot-standby-only scenario construction/behavior

These failed at both commits and are PRE-EXISTING:

- `tests/test_operator_unit_commands.py::test_tc_203_5c2_start_hot_standby_returns_bad_state_code`
- `tests/test_operator_unit_commands.py::test_tc_203_5c3_trip_hot_standby_releases_and_queues_sync`
- `tests/test_scenario_fc100_islanded_v2.py::test_fc100_reference_is_registered_and_exercises_all_hot_standby_ramp`

Their identical pre/current outcomes rule out Phase 1 as the cause. Phase 1 only records hot-standby fuel when an optional fuel model is present; it does not change hot-standby dispatch, operator commands, or scenario construction.

## Three root-level audit tests

The separate root-level audit invocation was run from the package parent without adding the simulator package directory to `PYTHONPATH`, matching the previously observed environment issue. The following three files failed identically at both commits during collection:

- `audit_tests/test_step1b_findings.py` — `ModuleNotFoundError: No module named 'core'`
- `audit_tests/test_step2_findings.py` — `ModuleNotFoundError: No module named 'core'`
- `audit_tests/test_step3_findings.py` — `ModuleNotFoundError: No module named 'core'`

This is an import-path/setup failure, separate from the package-scoped full matrix. Running the package-scoped `tests/test_source_audit.py` independently produced 25 passed at both commits.

## Final attribution

- Raw comparison: one apparent NEW failure, GPU profile test.
- Reproduction: GPU test passed repeatedly at both commits when run serially.
- Phase 1 source diff: no GPU profile implementation changes.
- Conclusion: **no Phase 1-attributable regression was found.** Do not start Phase 2 based on this report; Phase 2 remains gated on explicit confirmation.
