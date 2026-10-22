# DR-2026-10-22-ISL-P4 — Phase 4b

Status: COMPLETE. STOP at Phase 4b. Phase 4c has not started.
Entry HEAD: `94c108a` (Phase 4a design-document checkpoint).
The local implementation commit hash is reported separately in delivery.

`P` = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`.

## Changed files and final line ranges

- `P/core/dispatch.py:18`: Callable type import, no runtime import into core.
- `P/core/dispatch.py:379–382`: optional observation-only successful-start callback.
- `P/core/dispatch.py:622–623,631–641`: capture the pre-command state/count and,
  AFTER the unchanged command/pending-register operations, emit only for
  OFFLINE -> STARTING with exactly one native counter increment.
- `P/core/simulation_core.py:352–353`: wire the callback during simulation setup.
- `P/core/simulation_core.py:389–412`: adapter to existing
  `_record_turbine_transition`; it resolves the sink at event time.
  Source `predicted_step_staging` is marked PROPOSED_HERE; controller_approved=None.
- `P/tests/test_dr_isl_staging_start_events.py:1–238`: TC-ISL-07a–g.
- `tools/dr_isl/PHASE_4B_REPORT.md`: this report.

The existing pre-staging `start_eligibility` call is unchanged; no guard logic
was copied. The before/after state and counter checks observe a successful
command, not a new eligibility policy. Native start counters and fuel code
were not edited. The command remains before pending-register recording.
No callback is required on standalone arbitrators; an absent event sink is
a no-op through the existing transition adapter.

## New test coverage

Numbering search before addition found no TC-ISL-07/08/09 collisions.
The IDs used are TC-ISL-07a through TC-ISL-07g, expanded to 19 cases:

| ID | Cases | Assertions |
|---|---:|---|
|07a|2|sink replacement after setup is respected; exact event data; command -> pending -> event order; callback also works without a pending register|
|07b|4|min-down/pending/refused commands emit nothing; state-only transition without counter increment emits nothing|
|07c|1|repeated staging does not duplicate an event|
|07d|2|STARTING and SOLAR_STEP both emit through the same hook|
|07e|3|existing operator/core-commitment/contingency paths retain one event, not two|
|07f|1|initial release plus restart ordinals 2–6 reconcile before every tick observer, with zero hard violations|
|07g|6|absent sink, absent observer and standalone arbitrator preserve results and all turbine fields; positive, zero and negative steps still start the eligible unit|

Synthetic fixtures/constants are explicitly PROPOSED_HERE test inputs.

## Final focused check

Executed from P:
```text
pytest -q --tb=short \
 tests/test_dr_isl_staging_start_events.py \
 tests/test_dr_isl_start_eligibility.py \
 tests/test_dr_isl_hot_standby_veto.py \
 tests/test_addendum_h_phase2a_commitment.py::test_tc114_logs_external_start_and_refused_stop_with_reconciled_count \
 tests/test_addendum_h_phase2a_commitment.py::test_tc125_informed_core_proposal_is_logged_by_controller \
 tests/test_addendum_h_phase2a_commitment.py::test_tc132_core_start_is_vetoed_during_minimum_down_window \
 tests/test_step8_scenarios.py::TestSolarStepTriggersStaging \
 tests/test_step8_scenarios.py::TestTC33Symmetry \
 tests/test_tc89_tc90_tc91_sequential_start.py::test_tc89_first_tick_starts_at_most_one_unit \
 tests/test_tc89_tc90_tc91_sequential_start.py::test_tc91b_both_production_paths_share_pending_register \
 --junitxml=/tmp/DR-ISL-phase4b/FOCUSED.xml
36 passed, 5 warnings in 10.62s
```

19 new cases + 17 directly affected existing cases; failures=0, errors=0.
Log: `/tmp/DR-ISL-phase4b/FOCUSED.log`.
JUnit: `/tmp/DR-ISL-phase4b/FOCUSED.xml`.
Warnings: one Starlette/httpx deprecation and four existing synthetic
500 C BESS fixture warnings from the solar/symmetry tests.

Initial new-test-only run: 14 passed, 4 failed. Two fixture errors caused
the four failures: an incomplete mocked CommitmentDecision omitted floor_mw;
the standalone fixture read a nonexistent SimulationState.fuel_cell_units.
Corrected only the new test fixtures to use the actual CommitmentDecision
and existing arbitrator's fuel_cell_units. No production adjustment was made
to accommodate either error. The final run above supersedes that result.
An additional parameter case verifies a callback without a pending register.

## Startup and boundaries

The existing development workflow `artifacts/gridsignal: web` was restarted once.
Startup completed, Uvicorn listened on 0.0.0.0:22126 and GET / returned 200.
Evidence: `/tmp/logs/artifactsgridsignal_web_20261022_142543_575_3f0e8c7d.log`.
Existing scenario starting-count/base_load_mw coverage warnings remain.
No frontend edits or browser testing were performed.

`git diff --check` passed before commit. The new test under ignored
attached_assets is explicitly force-added, rather than left untracked.
No edits to asset start counters/fuel/physics, eligibility conditions,
guard durations, frequency/protection, BESS, diesel or any scenario JSON.
S10 was not edited or run. Zero/negative-step pre-staging is deliberately
unchanged, as asserted in 07g.
No H2 evidence runs, full suite, publish, deploy or push.

Design departures: NONE. Required design changes: NONE identified.
These focused results do NOT claim H2 baseline_valid=True or certify H2
physical/metric identity; those remain Phase 4c evidence gates requiring approval.
STOP — end of Phase 4b.
