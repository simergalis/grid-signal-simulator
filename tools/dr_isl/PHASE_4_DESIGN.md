# DR-2026-10-22-ISL-P4 — turbine start-event reconciliation

## Gate and authority

Phase 4a diagnostic/design only, 2026-10-22. **COMPLETE; awaiting approval.**
Phase 4b implementation and Phase 4c evidence have NOT started.
Entry HEAD: `4e2f9b01dd8830572f3aab784588c6db51244b1a`.
No application, scenario, configuration, test or parameter changes; no new
simulation or test runs. This document is the only repository write.
The findings below combine current source inspection with retained Phase 3
execution evidence, not a newly instrumented H2 run.

`P` = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim`.
Source line references are against entry HEAD.

Approved scope from the user:
> make every turbine start reached through the untracked
> "production_command_or_cascade" path (the gt-hot-01 starts in H2) appear
> in the start event log, so recorded and measured start counts reconcile
> and the H2 baseline becomes valid. Fix the accounting only.
> Do not change which units start, when they start, or the start physics.

No changes to frequency/protection, BESS dispatch, diesel, scenario JSON,
guard durations or start-eligibility conditions. Leave S10 untouched.
No publish, deploy or push. Each phase requires separate approval.

## 4a.1 — actual missing path

**Confirmed event-logging omission in `DispatchArbitrator.stage_for_predicted_step`.**
Not a demonstrated turbine start-counter defect.

At `P/core/dispatch.py:593–594`, pre-staging selects offline units through
the Phase 3 `start_eligibility(sim_time)` predicate. At `:614–618` it applies
the existing shared pending-start gate and calls `_ht.command_start(sim_time)`.
At `:623–624` it records the pending start when the unit is STARTING.
There is NO transition-event emission in this successful-start block.
`PendingStartRegister.record_start` is sequencing bookkeeping, not an
append to the controller's start-event log.

The asset applies its existing eligibility safety check at
`P/core/asset_modules.py:1081–1083`.
A successful command sets STARTING and increments `_start_count` at
`:1111–1112`, then charges its configured thermal-tier start fuel at
`:1114–1118`. The authoritative counter and fuel are already updated.
Source search of `P/core` and `P/runtime` found the turbine STARTING
assignment and turbine `_start_count += 1` at this one asset boundary.
The diesel's similarly named command is a different class and is not in scope.

### Exact source call chains for the unlogged production entrypoints

Study arm entry:
`P/study_harness/executor.py:340–344` installs the replay events and removes
live Slurm/Kubernetes inputs; `:356–361` builds the context; `:367` calls
`RunContext.step()`. This is not a live Slurm scheduler during the arm.

Common runtime prefix:
`P/runtime/run_manager.py:1824–1825` ->
`_apply_due_events()` at `:1574–1581` ->
`SimulationState.apply_workload_signal(signal, dt_lead_seconds)` at
`P/core/simulation_core.py:387`.

Two source entry branches reach the same missing event hook:

1. STARTING workload:
   `P/core/simulation_core.py:498–542` computes the job's staging delta and
   calls `arbitrator.stage_for_predicted_step(..., sim_time=signal.timestamp)`
   at `:538–542`.
2. SOLAR_STEP:
   `P/core/simulation_core.py:403–413` calls the same method at `:408–412`,
   with renewable shortfall and zero lead time.

Both continue:
`P/core/dispatch.py:593–618` -> `TurbineModule.command_start` ->
`P/core/asset_modules.py:1081–1118` ->
`P/core/dispatch.py:623–624` pending bookkeeping -> return WITHOUT a start event.

Retained H2 command observations explicitly identify
`source="stage_for_predicted_step"` for each missing start. They do not retain
the originating WorkloadSignal/event_id with the command. The branch inventory
above is the exact source routing; this report does not invent an originating
event_id or claim a SOLAR_STEP occurred in H2.

## 4a.2 — why gt-hot-01 is measured 2–6 versus log=1

Retained evidence:
`/tmp/DR-ISL-phase3/finish/scenario-h2-slurm-24h-baseline-1.json`.
Candidate command attempts start at line 1323; candidate hard violations at
2298; candidate start-fuel reconciliation at 2327; measured events at 2442.
JSON paths: `summaries.candidate.trace.attempts`,
`summaries.candidate.record.starts`, `...record.measured_start_events`,
`...record.hard_violations`, `...record.start_fuel_reconciliation`.
These are the validated Phase 3 D2-a results.

| asset start ordinal | command tick | command sim_time_s | measured interval-end sim_time_s | source | recorded? | charged tier fuel MMBtu |
|---|---:|---:|---:|---|---|---:|
|gt-hot-01 #1|5830|29145.0|29150.0|_release_hot_standby_for_contingency|yes, automatic_contingency release|8.0|
|gt-hot-01 #2|7207|36030.0|36035.0|stage_for_predicted_step|NO|12.0|
|gt-hot-01 #3|8647|43230.0|43235.0|stage_for_predicted_step|NO|12.0|
|gt-hot-01 #4|10087|50430.0|50435.0|stage_for_predicted_step|NO|12.0|
|gt-hot-01 #5|11527|57630.0|57635.0|stage_for_predicted_step|NO|12.0|
|gt-hot-01 #6|12967|64830.0|64835.0|stage_for_predicted_step|NO|12.0|

The first release clears the reserved-hot-standby flag before the existing
command and logs that physical transition:
`P/core/simulation_core.py:768–790`. Subsequent starts are ordinary eligible
restarts of that same asset, despite its name containing "hot".

Other H2 baseline starts are already logged:
gt-hot-02 at 36400.0 s (automatic_contingency release), and at
43585.0, 50785.0, 57985.0, 65185.0 s (core_commitment starts).
Thus gt-hot-01 has measured=6/logged=1 and gt-hot-02 measured=5/logged=5;
the total is measured=11/logged=6. Five missing warm starts carry 60.0 MMBtu;
total measured start fuel is 124.0 MMBtu. This is already charged fuel,
not fuel to charge again.

Controller reconciliation at `P/runtime/turbine_commitment.py:1495–1518`
compares each asset `_start_count` with accepted, changed-state start/release
records. It produces:
```text
start_count_reconciliation:gt-hot-01:asset=2:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=3:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=4:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=5:log=1:untracked_path=production_command_or_cascade
start_count_reconciliation:gt-hot-01:asset=6:log=1:untracked_path=production_command_or_cascade
```
That suffix is a generic diagnostic label, not identification of a separate
cascade defect. The observed missing caller here is pre-staging.
Distinct mismatch strings persist in the violation list (`:1517–1518`).

The observer runs after physics:
`P/runtime/run_manager.py:1855–1856` calls controller `record_tick`.
Metrics separately detect actual counter/fuel increments at
`P/study_harness/metrics.py:235–254`, using interval-end timestamps.
The 5 s timestamp difference in the table is therefore not a duplicate start.
The collector counts recorded events at `:135–140` and rejects mismatched
counts at `:429–460`.

The saved `tier_sum_mmbtu=124.0` does not prove the six logged events cover
all fuel: diagnostic guard-failure handling replaces only the temporary
collector input with measured events, then preserves the original failed
reconciliation. See `P/study_harness/executor.py:402–442`.
It explicitly does NOT repair the original event list or convert it into PASS.

Classification: missing authoritative events; derived log-based start counts
are consequently low. The measured asset counter is consistent with the 11
observed successful commands. No counter-increment or start-physics fix is proposed.

## 4a.3 — complete production caller inventory

Search of current `P/core` and `P/runtime` turbine `.command_start(...)`
call sites found these six calls. All successful paths except pre-staging
already emit through an existing runtime event receiver.

| caller | command line | existing event route |
|---|---|---|
|operator/controller release|runtime/run_manager.py:1501|:1556–1572 -> controller.record_command_result -> command_result|
|operator/controller start|runtime/run_manager.py:1522–1526|same :1556–1572 route|
|contingency hot release|core/simulation_core.py:770|:779–790 -> _record_turbine_transition|
|baseload/automatic hot cascade|core/simulation_core.py:2290|:2293–2316 -> _record_turbine_transition|
|core commitment start|core/simulation_core.py:2390|:2398–2418 -> _record_turbine_transition|
|predicted-step pre-staging|core/dispatch.py:618|pending only at :623–624; NO transition event|

`P/core/simulation_core.py:692–727` is the existing core-to-runtime
`_record_turbine_transition` adapter. It reads the state's optional
`_commitment_transition_sink` and calls `record_transition`.
The factory installs the controller as that sink at
`P/runtime/scenario_factory.py:1941–1945`.
`P/runtime/turbine_commitment.py:1132–1178` appends the authoritative event:
accepted=True, changed_state=True, exact from/to states, source and time.
Runtime command-result logging is at `:1406–1420` and `:1289–1389`.
There is no need to add another event journal or to modify these logged paths.

When turbine commitment is disabled, the controller/sink is absent by design:
`P/runtime/scenario_factory.py:1924–1945`.
The schema default is disabled (`P/api/schemas.py:1689–1694`).
Absence of a controller log in that mode is not itself failed reconciliation.

## 4a.4 — scope beyond H2, using retained evidence only

Read-only comparison of retained `finish/<scenario>-<arm>-<rep>.json`
matched successful command observations against accepted changed-state
start/release records by unit id and command simulation time.

| retained case | observed successful commands | pre-staging commands | unmatched logged starts |
|---|---:|---:|---|
|H1-24h baseline, repetitions 1/2|12 each|0|0|
|H1-24h informed, repetitions 1/2|12 each|0|0|
|H2-24h baseline|11|5|5, table above|
|H2-24h informed, repetitions 1/2|14 each|0|0|
|base demo baseline|2|0|0|
|base demo informed|2|0|0|
|demo-islanded-ramp app path|3|1|no controller record in retained app summary|
|S10 app path|38|21|no controller record in retained app summary|
|SJ-1, turbine-01, hybrid, fc-bess-diesel, fc100-v2, fc100-zero-hot-v2 app paths|0 each|0|no successful starts in retained commands|

The template and S10 JSON omit turbine_commitment_mode; their seeder-path
schema default is disabled, not baseline. Their retained calls demonstrate
the shared pre-staging path, not another proven invalid study baseline.
S10 was not run or edited for this diagnosis.

Among retained enabled study arms examined, only H2-24h baseline has this gap.
This is NOT a claim that every catalogue scenario or H2-7d is free of it:
no new catalogue-wide runs, H2-7d run, or controller-log reconstruction for
disabled-mode app runs was performed.
The source defect can affect any enabled-controller scenario that successfully
starts through pre-staging; its predicates are not H2-specific.

## Proposed design — APPROVAL REQUIRED before Phase 4b

### Minimal shared-event hook, not new start logic

1. Add an optional, observation-only successful-start transition callback to
   `DispatchArbitrator`, alongside its existing optional pending-start wiring
   (`P/core/dispatch.py:373–378`).
2. Wire it from `SimulationState.__post_init__`, where the shared pending
   register is currently assigned (`P/core/simulation_core.py:341–351`).
   The adapter invokes existing `_record_turbine_transition(state, turbine, ...)`.
   Resolve the state's sink at event time, not construction time: the factory
   attaches the controller later at `P/runtime/scenario_factory.py:1941–1945`.
   Do not import runtime classes into core.
3. At the existing successful command boundary in pre-staging
   (`P/core/dispatch.py:617–624`), capture before state/counter, keep the
   command and pending-register operations in their existing order, then emit
   exactly one event if the command actually caused OFFLINE -> STARTING and
   incremented the asset start counter. This is observation of success, not a
   new eligibility test. Preserve the existing sole call to the shared
   `start_eligibility` predicate; do not reproduce any guard conditions.
4. Route through `_record_turbine_transition` -> controller.record_transition,
   action=`start`, original staging command time, actual asset/thermal tier,
   accepted=True, changed_state=True, from=offline, to=starting.
   PROPOSED_HERE metadata source label: `predicted_step_staging`, to distinguish
   actual pre-staging from core_commitment/cascade. Rationale: forensic source
   identification, no operational constant or behavior.
   Include the observed staging delta/lead in the reason; do not alter them.
   Use controller_approved=None for this existing automatic path: do not
   invent a controller approval or introduce a veto.
5. Emit independently of whether a standalone arbitrator test supplied a
   PendingStartRegister. No sink/callback means a no-op, as in the existing
   core transition adapter. Do not add a fallback engine or synthetic tick-end
   event backfill.

This covers both STARTING and SOLAR_STEP entrypoints through one callback.
The already-logged five caller paths remain unchanged, preventing double counts.
The callback writes only the existing controller event log; it must not issue
commands, clear hot-standby flags, change pending state or mutate turbine fuel.

### Why not reconstruct missing starts at record_tick/finalization?

That would obscure the command-time source, substitute interval-end timestamps,
and risk logging already-recorded starts a second time. It would also create
a second logging implementation instead of fixing the successful start boundary.
Do not change `_start_count`, fuel totals, metric tolerances or the diagnostic
guard; do not clear existing violations to obtain a pass.
The five hard violations should never be created in a fresh corrected run,
because each real event is logged before that tick's `record_tick` reconciliation.

### Proposed Phase 4b tests, continuing the TC-ISL sequence

Source search found no existing TC-ISL-07/08/09; TC-ISL-10 onward has prior uses.
Reserve TC-ISL-07a–g for this fix, subject to a collision recheck on implementation:

- 07a: accepted pre-staging start emits one authoritative event with exact
  unit/time/source/tier/from/to, matching one counter increment.
- 07b: min-down/ineligible and pending-start-blocked cases emit none; guards
  and sequencing outcomes are unchanged.
- 07c: repeated staging calls during the same start do not duplicate events.
- 07d: workload STARTING and SOLAR_STEP both use this one hook.
- 07e: already-logged operator, core and cascade starts are not duplicated.
- 07f: multiple starts of the same formerly released hot-standby asset reconcile
  per tick, including restart ordinals 2–6; no synthetic violation cleanup.
- 07g: absent sink/disabled controller and standalone arbitrator behavior remain
  unchanged; adding/removing the observer does not change physical state,
  counters or fuel. Any synthetic constants must be PROPOSED_HERE.

These are designs only; no tests have been added or run at this gate.

### Proposed Phase 4c evidence and accounting-only acceptance

Use Phase 3 pinning, both H2 arms, unchanged scenarios and arm configurations.
Expected H2 baseline recorded=measured=11 (gt-hot-01 6/6, gt-hot-02 5/5),
measured start fuel still 124.0 MMBtu, zero start-count hard violations,
constraints_valid=True and comparison baseline_valid=True.
The existing other nine H2 comparison conditions are True in the saved Phase 3
report (`tools/dr_isl/PHASE_3_REPORT.md:185–190`); verify, do not assume, the
complete comparison passes after the event-only correction.
H2 informed must retain 14/14 starts and its Phase 3 physical metrics.

Compare every H2 physical tick field, start target and time, asset start/fuel
counters, and physical metrics with Phase 3, not merely the aggregate fuel.
Existing physical hashes:
baseline `f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1`;
informed `b7383d283f09d625f531ecc216b447b868792f50069bbc662b1636d2b988bbfb`.
Only accounting metadata may change: starts/log/source, event counts,
reconciliation/hard violations, validity and the resulting comparison verdict.
Reported start fuel must not change; the missing five events describe already
charged 60.0 MMBtu, not additional consumption.

Do not reissue or alter certified H1 records. Check that existing H1 and base-demo
logged paths do not duplicate events. Leave S10 scenarios, inputs and behavior
untouched; no S10 execution is part of this diagnostic gate.
Run the real-package full suite only in approved Phase 4c, with failing-ID
comparison against `tools/dr_isl/PHASE_3_FAILING_TESTS.txt` (15 known failures).
Require zero added failures. Save the final approved evidence in
`tools/dr_isl/PHASE_4_REPORT.md` and `tools/dr_isl/PHASE_4_FAILING_TESTS.txt`.
Stream hashes/metrics; do not export full long-run ticks or exceed 200 MB/file.

## GATE — STOP

This is a proposed accounting-only design, not an implementation approval.
Only `tools/dr_isl/PHASE_4_DESIGN.md` was created.
No new simulations/tests, application edits, local commits, publish, deploy
or push were performed in Phase 4a.
Await approval before Phase 4b. Phase 4c requires its own later approval.
