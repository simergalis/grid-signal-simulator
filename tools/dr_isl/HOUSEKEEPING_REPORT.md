# DR-ISL housekeeping — IMPL-ISL-18 and remaining test-file tracking

Date: 2026-10-22.
Starting HEAD: `3c4abab7175736cf119a359eea5a743db9e7ab36`.
Package root P:
`attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

## Acceptance recorded

Lloyd approved acceptance of IMPL-ISL-17, the observation-only P4b
successful-start event logging, as validated:
```text
Design:         94c108a
Implementation: 146b89f
Validation:     1dc45ea
Follow-up:      3c4abab
```
This records the user's 2026-10-22 decision. It does not rewrite the
historical V1 16-failure result or its original zero-added-failures verdict.
The housekeeping suite below is a separate new measurement after fixing
the diagnosed test readiness race.

## Boundaries

- No production application, runtime, schema, scenario JSON, dispatch,
  physics, frequency, protection, BESS or diesel changes.
- No publish, deploy, push, workflow restart or Phase 4 work.
- K1 changes one existing test and one standard-library import in that file.
- K2 adds exactly six existing ignored test files without changing bytes.
- Evidence is bounded summaries, logs, JUnit and incremental failing IDs
  under `/tmp/DR-ISL-housekeeping/`; per-file resource limit is
  200,000,000 bytes. No simulation tick export was requested or generated
  by the housekeeping verification runner.

## K1 — IMPL-ISL-18

Commit:
`0e46dd2753270d560bd9f65558dbb6609e08264f`
```text
IMPL-ISL-18: test_step16 waits for first telemetry ingestion (test-only)
```
Only changed file:
`P/tests/test_step16_wiring.py`.
Changed locations: import at line 35; readiness wait at lines 195–210.
The existing test starts at line 187; its original assertions now follow
the polling loop, lines 212–225.

### Change

The test polls the existing GET endpoint until the active run has at least
one switch record. It uses `monotonic()` and a **10.0-second test-only
deadline**, marked `PROPOSED_HERE` with its finite-budget rationale at
line 198. It has no fixed sleep. A non-200 response exits polling so the
existing status assertion still fails normally.

The timeout message includes the run ID, budget, response status,
`last_updated_s`, and the returned switch list:
```text
Run <run_id>: no network telemetry ingested within 10s; last response status=200, last_updated_s=5.0, switches=[]
```
The `<run_id>` above is the variable part, not a fabricated fixed run ID;
the literal negative-case log is retained in
`/tmp/DR-ISL-housekeeping/held-through-timeout.log`.

The comment cites DR IMPL-ISL-18 and the diagnosed source locations:
`runtime/run_manager.py:2190–2193,2310–2314,3236,3252`;
`api/routes/advisory.py:442–445`.

AST comparison against `3c4abab`:
```text
Original assertion ASTs unchanged: 6
```
The comparison includes every original `ast.Assert` subtree and its
message, ignoring only source line/column locations. No assertion was
deleted, weakened or substituted.

### Focused verification, real package

| Check | Literal result |
|---|---|
| Isolation 1 | `1 passed, 1 warning in 10.88s` |
| Isolation 2 | `1 passed, 1 warning in 1.53s` |
| Isolation 3 | `1 passed, 1 warning in 1.57s` |
| Entire `tests/test_step16_wiring.py` | `17 passed, 1 warning in 4.61s` |
| Initially occupied advisory executor, released after first empty read | `1 passed, 1 warning in 1.34s` |
| Executor held through the deadline: deliberate negative check | `1 failed, 1 warning in 11.55s`, expected exit 1 and the clear 10-second timeout message |

The occupied-executor verification submits one Event-wait blocker to
each of the existing executor's four workers. A read-only thread-profile
observer releases them upon observing the first empty telemetry-store
read. That is event-driven, not a fixed sleep. The original immediate
assertion would fail on that empty response; the new test continues until
actual ingestion. All blockers are released/joined in `finally`.

Literal successful controlled observations:
```json
{
  "mode": "release-after-empty",
  "workers": 4,
  "observations": [
    {"store_records": 0, "drive_lines": [3236]},
    {"store_records": 2, "drive_lines": [3236]}
  ],
  "pytest_exit": 0
}
```
The second stack location is the next advisory await after the first
ingestion, not evidence that the two records existed before ingestion.

Keeping all workers occupied indefinitely cannot produce telemetry.
The separate held-through-timeout check intentionally verifies that the
test fails clearly instead of hanging or passing without records:
```text
mode=held-through-timeout
workers=4
observed reads=4692
first: store_records=0, drive_lines=[3236]
last:  store_records=0, drive_lines=[3236]
pytest_exit=1 (expected)
```
This deliberate negative probe is not a regression-suite failure.

Evidence:
`/tmp/DR-ISL-housekeeping/focused_results.json`,
`isolation-{1,2,3}.{log,xml}`, `whole-file.{log,xml}`,
`release-after-empty.{log,xml,json}`, and
`held-through-timeout.{log,xml,json}`.

## K2 — IMPL-ISL-16: track six unchanged test files

Commit:
`9f71dba88cfdcb2d62d84e5c6ef59bb6aa7ff656`
```text
DR-ISL IMPL-ISL-16: track remaining test files under ignored attached_assets/ (no content change)
```
Every row was untracked before, was force-added individually with
`git add -f`, and passed `git ls-files --error-unmatch` afterwards.
The six files contribute 1,319 source lines to the commit, but their tests
were already collected from the real package before tracking.

| File under P | Bytes | Added line range | SHA-256 before = SHA-256 after |
|---|---:|---|---|
|tests/test_addendum_g2_fuel_physics.py|17200|1–463|`a82600bda84d5e8ea44b4bc739354d800e2b1fb0ec209de8359b51edbcf754c2`|
|tests/test_addendum_g_stage3_option_c.py|15429|1–412|`b583941bb6b8a7c3a62e8480500d0c9ede9ac2f58fbc804a2b0beec681af17e5`|
|tests/test_fuel_cell_apparent_rating.py|2081|1–58|`8d4046e1712c50a361ccb80b260e5dfd5f9e3abe4ef2f2fe8f636640e86d75bc`|
|tests/test_infrastructure_admission.py|6691|1–198|`594dae2e6e5a22ae639b8d72ff4d3da6ccfcaecc8d9edca8cfbce61c21874f5d`|
|tests/test_kube_scheduler_phase_a.py|3918|1–127|`5056fd2994dcfe9fdc3d43f07ec78c2637eb1aef4e87ba597cc8d832a244eb47`|
|tests/test_kubernetes_scheduler_demo_scenario.py|2367|1–61|`e65f658a0df5eac223c17183603a8301ef408efdc999dbe95a397e899a650737`|

### What imports or runs them

All six are executed by normal pytest `tests/test_*.py` collection.
The retained V1 native JUnit already contains, respectively,
**26, 16, 3, 7, 4 and 1 cases** for these six modules (57 total).

There is also a tracked test-to-test import:
`P/tests/test_dr_isl_phase2b.py:7` imports
`_factory_tick` from `tests.test_addendum_g_stage3_option_c`.
No other direct tracked Python importer of these six modules was found.

Relevant production imports in the six files:

- G2 fuel physics: `api.schemas`, `core.fuel_cell_module`,
  `runtime.advisory_gate`, `runtime.fuel_cell_readiness`.
- Stage 3 Option C: `api.schemas`, `core.models`, `core.fuel_cell_module`,
  `core.simulation_core`, `runtime.run_manager`, `runtime.scenario_factory`.
- Apparent rating: `core.fuel_cell_module`, `runtime.fuel_cell_readiness`.
- Infrastructure admission: `core.infrastructure_admission`,
  `core.ray_models`, `core.slurm_scheduler` (lines 5–16).
- Kube phase A: `core.kube_scheduler` (line 5).
- Scheduler demo: `api.routes.scenarios`, `core.kube_scheduler`,
  `runtime.scenario_factory` (lines 7–9).

SHA evidence:
`/tmp/DR-ISL-housekeeping/K2_before.json` and `K2_after.json`.

### Other untracked project files imported or loaded — REPORT ONLY

None of the following was added or modified:

| File under P | Bytes at census | Tracked consumer / execution path |
|---|---:|---|
|tests/test_task_630_100mw_fuel_cell_scenario.py|6305|Loaded by full pytest collection; retained V1 native JUnit contains its three scenario tests.|
|knowledge/behind-the-meter-market-context.md|2255|`api/routes/ai.py:821,842–848` reads every `knowledge/*.md` document into the cached Gridley corpus.|
|knowledge/gridsignal-operator-benefits.md|3155|Same tracked knowledge-directory loader at `api/routes/ai.py:842–848`; `tests/test_gridley.py:265` also asserts the corresponding source ID.|
|mcp_server/__init__.py|64|Package initializer implicitly loaded by tracked `api/app.py:101`, `from mcp_server.server import ...`.|
|gridsignal.db|122880|Conditional runtime data: SQLite fallback path at `api/db.py:52–56` when database environment configuration does not select another location/backend; not asserted to be the selected DB in every test.|

An additional untracked CLI entry is
`P/mcp_server/__main__.py` (247 bytes): it is executable through
`python -m mcp_server`. No tracked launcher invoking that module entry
was found; it is reported separately rather than claimed to be a direct
tracked-code import. It was not added.

Audit method: resolve tracked Python AST imports and literal project
filename references, then check dynamic loaders, pytest discovery and
the package initializer. The pre-add first-party inventory contained
59 untracked files, including the six added tests. It excluded installed
vendor dependencies, generated interpreter caches and build/cache
directories (`.pythonlibs`, `node_modules`, `__pycache__`, `.pytest_cache`,
`dist`, `.vite`). This is not a claim to prove every possible future
runtime-computed file path.

The remaining untracked `frontend/src/subsystem/panels/agents.ts` has no
tracked importer found by the targeted frontend search. It was not added.
Other untracked reports and smoke artifacts were not misclassified as
inputs: for example `scripts/run_phase2a_smoke.py:673,740` writes its
`smoke_results.json` and `smoke_summary.txt`; the S9 test's similarly named
CSV is an output at `/tmp/S9_catalogued_invariants.csv`
(`tests/test_s9_islanded_ramp.py:462`), not a read of the untracked
`reports/S9_catalogued_invariants.csv`.

Inventory/reference evidence:
`/tmp/DR-ISL-housekeeping/K2_untracked_inventory.json`,
`K2_untracked_references.json`.
No `.gitignore` edit and no force-add beyond the six authorized files.

## K3 — complete real-package regression suite

**COMPLETE — housekeeping acceptance PASS; the suite retains the 15 known
pre-existing failures.** No added failure was observed.

Literal final output:
```text
15 failed, 2171 passed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed in 696.54s (0:11:36)
HOUSEKEEPING_PYTEST_EXIT= 1
```
The exit is nonzero because the 15 expected pre-existing failures remain;
this is not represented as an entirely green suite.

| Set comparison against `tools/dr_isl/PHASE_3_FAILING_TESTS.txt` | Count |
|---|---:|
| Added | 0 |
| Removed | 0 |
| Remaining | 15 |

Added IDs: `[]`. Removed IDs: `[]`.
The sorted remaining IDs are saved in
`tools/dr_isl/HOUSEKEEPING_FAILING_TESTS.txt`.
The original IMPL-ISL-17 validation's 16-ID list is unchanged. Relative to
that historical list, this suite removes only the telemetry readiness test.

Native JUnit:
```text
tests=2215 failures=15 errors=0 skipped=26
time=696.475
timestamp=2026-10-22T15:32:36.310019+00:00
hostname=repl
```
Incremental JUnit:
```text
tests=2212 failures=15 errors=0 skipped=26
```
Native counts include the three passing subtests; JUnit skipped includes
the 23 expected failures as well as the three ordinary skips.

The updated target test passed in the complete suite:
```text
classname=tests.test_step16_wiring
name=test_network_telemetry_returns_required_fields_for_active_run
time=0.191
failure=False
error=False
```
All six K2 source-file hashes were rechecked after the full suite and still
equal their before/after hashes in the table above.

Invocation uses the real P directory, not a scratch checkout:
```text
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=1729
pytest -q -p no:cacheprovider --junitxml=/tmp/DR-ISL-housekeeping/suite_native.xml
```
The retained Phase 3 observer
`/tmp/DR-ISL-phase3/finish/dr_isl_incremental.py` is loaded in memory with
only its evidence output directory changed. It writes valid incremental
JUnit and a sorted failing-node list as tests finish.

Evidence paths:
```text
/tmp/DR-ISL-housekeeping/suite_incremental.xml
/tmp/DR-ISL-housekeeping/suite_native.xml
/tmp/DR-ISL-housekeeping/suite_failing_tests.txt
/tmp/replit-background-tasks/8be7906b-f62a-4095-88be-2b3f1bba12c0.log
```

## K4 — commits and stop boundary

Implementation commits:
```text
0e46dd2753270d560bd9f65558dbb6609e08264f  IMPL-ISL-18: test_step16 waits for first telemetry ingestion (test-only)
9f71dba88cfdcb2d62d84e5c6ef59bb6aa7ff656  DR-ISL IMPL-ISL-16: track remaining test files under ignored attached_assets/ (no content change)
```
A separate report-only commit includes this report and
`tools/dr_isl/HOUSEKEEPING_FAILING_TESTS.txt`.
Its hash and final git status are reported at delivery, avoiding a
self-referential commit hash in this file.

The only changed package paths relative to the starting commit are the
seven authorized test files. Production source and scenario trees remain
unchanged. The six newly tracked test files have identical working-tree
and commit-blob SHA-256 values.

**STOP — housekeeping complete. Do not start Phase 4.**
