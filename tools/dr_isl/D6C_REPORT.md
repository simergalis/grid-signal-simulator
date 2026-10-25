# D6c STOP diagnosis

## Status

**STOPPED at the pinned-S10 physical-hash gate.** This is a read-only diagnosis of the D6c hash change; no application code, tests, or scenarios were changed for this follow-up. D6c acceptance work did not continue beyond the requested comparison.

## D6c.X1 — direct pinned-run comparison

Ran `tools/dr_isl/d6f/run_operating_cost.py` against S10 at base `d12ed881e6c0c0f553132aa3282f3e92baf5b18b` in a temporary worktree and at current HEAD `774fae597f6fe75cf05d21c549a6c0d18c20890c`. The runner pins seed `1729` and wall clock `1792454400.0` (`tools/dr_isl/d6f/run_operating_cost.py:25–26`). Each run produced 17,280 ticks. The comparison retained the base serialized tick rows in memory and streamed the current rows against them; the compared bytes were exactly `physical_tick_json(tick)`, the bytes consumed by `PhysicalIdentityHasher` (`core/physical_identity.py:47–65, 75–76`). No per-tick export was written.

| Run | Physical SHA-256 | Non-fuel SHA-256 |
|---|---|---|
| D6b base `d12ed88` | `4e33ec591dbf46a41a8d3518f891a7b7f7b1096ad3ca7bbf2a7afc27ab3f2029` | `808873c0bd14974ae4a605c49df4a43e7ba349831689d00399c5a2063da68f9e` |
| D6c HEAD `774fae597f6fe75cf05d21c549a6c0d18c20890c` | `ad91ced6445f21aa4a9a9b4ccb2fb4dd5114d42f2eae3ab5e0be5769fceaf508` | `e0ccf0e15265d70738e53c74d273e8ab223d9b30b4439797b8188cb76be7aaba` |

There are four differing tick fields; each first differs at tick 1 (`sim_time_seconds=5.0`):

| Field | D6b value → D6c value | Differing ticks |
|---|---:|---:|
| `turbine_units[1].breaker_closed` | `true → false` | 71 |
| `turbine_units[2].breaker_closed` | `true → false` | 3,177 |
| `turbine_units[3].breaker_closed` | `true → false` | 8,110 |
| `turbine_units[4].breaker_closed` | `true → false` | 8,391 |

The union is 10,570 ticks with at least one differing field. No diesel field differs. No compared physical quantity differs: demand, served, unserved, generation, curtailment, turbine/BESS output, BESS SoC, frequency, compute/cooling/non-GPU demand, turbine starts, per-turbine state, and per-turbine output all have zero differing ticks. The physical-hash difference is caused by the four `breaker_closed` fields being included in the serialized tick identity, not by a change to those physical quantities. Full machine-readable counts are in `tools/dr_isl/d6c/D6C_X1_TICK_DIFF.json`.

## D6c.X2 — hashed object and the unchanged existing-scenario gate

The pinned cost runner hashes `sink.rows` (`tools/dr_isl/d6f/run_operating_cost.py:136–146`). Those rows are the RunManager-enriched `TickResult`: RunManager overlays `turbine_units` at `runtime/run_manager.py:3072–3098`, then hashes and appends that `tick_result` at `runtime/run_manager.py:3242–3243`. The D6c helper now takes `breaker_closed` from the physical tick value (`runtime/run_manager.py:103–115`); the core sets that value from `bool(turbine.is_on_bus)` (`core/simulation_core.py:4126`).

At base `d12ed88`, the RunManager overlay spread the static turbine spec and overlaid `state` and `output_mw`, but did not replace `breaker_closed` (`git show d12ed88:.../runtime/run_manager.py:3036–3052`). The static spec set it to `not hot_standby` (`runtime/scenario_factory.py:2178–2182`), so the normal offline/starting turbines had `true` in the pinned RunManager rows. D6c replaces this reporting value with the core tick’s `false` for off-bus units.

The unchanged existing-scenario hash gate uses a different path: it calls `ctx.step()` and hashes that result directly (`tools/dr_isl/d6f/run_existing_gates.py:63–68`), without the RunManager overlay. This explains why that gate remains unchanged while the pinned `run_operating_cost.py` hash changes.

`tools/dr_isl/d6b/D6B_3_FIRST_DIFF.json` is a one-tick comparison (`compared_ticks=1`, `comparison_index=1`) between its pinned/headless side and REST. Its pinned-side offline/starting turbine breaker values are indeed `false`, while the REST side shows `true`. That does not contradict X1: the JSON is not the 17,280-row `sink.rows` stream consumed by the D6b pinned hash runner. The direct headless path reports the core value; the pinned cost runner hashes the RunManager-enriched row.

## D6c.X3 — pre-existing commit contents

Before this diagnosis, the D6c edits were already in the generic Replit Agent commit `774fae597f6fe75cf05d21c549a6c0d18c20890c`, dated 2026-10-25 01:07:09 UTC, message `Update scenario planner and runtime logic with new diagnostic tools`. Its full file list was:

- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/frontend/src/components/ScenarioPlannerPage.tsx`
- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/api/routes/runs.py`
- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py`
- `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_operating_cost.py`
- `tools/dr_isl/d6c/C1_GRID_IMPORT_DIAGNOSIS.md`
- `tools/dr_isl/d6c/EXISTING_SCENARIO_HASHES.json`
- `tools/dr_isl/d6c/S10_PINNED_REP1.json`
- `tools/dr_isl/d6c/S10_PINNED_REP2.json`

`git show --stat` reports 8 files changed, 736 insertions, and 55 deletions. This was the state at the first D6c stop; the acceptance work below resumed after Lloyd's ruling.

## D6c resumed acceptance — 2026-10-24 ruling

### Accepted S10 pinned-run reference

Lloyd accepted the new pinned-runner reference. The old D6b pinned reference (`4e33ec59…` physical; `808873c0…` non-fuel) is superseded for the pinned runner only. The accepted reference is:

- Physical SHA-256: `ad91ced6445f21aa4a9a9b4ccb2fb4dd5114d42f2eae3ab5e0be5769fceaf508`
- Non-fuel SHA-256: `e0ccf0e15265d70738e53c74d273e8ab223d9b30b4439797b8188cb76be7aaba`
- Both pinned repetitions match this reference. `D6C_X1_TICK_DIFF.json` records that only `turbine_units[1..4].breaker_closed` differ from the prior pinned reference (10,570 union ticks); no physical quantity differs.

The separate `ctx.step()` existing-scenario gate remains unchanged versus D6b for all eight cases, including S10 `f230ae8f141183e1e6bcdb8dda0eb8f4920bf5674167bba972e4a72f37c64353`. Its hashes are in `tools/dr_isl/d6c/ACCEPTANCE_EXISTING_SCENARIO_HASHES.json`; each case has zero balance failures.

### Cost, REST reporting, and study gates

The implementation was already present in automatic commit `774fae597f6fe75cf05d21c549a6c0d18c20890c` (generic message; file list in D6c.X3 above). No application, test, or scenario edits were made during this resumed acceptance. The source locations are:

- No configured diesel fleet produces `diesel_fuel_consumed_gal=None`: `runtime/run_manager.py:90–100`. A configured but idle fleet remains numeric zero.
- REST turbine overlay now copies `breaker_closed` from the physical tick row: `runtime/run_manager.py:103–115`.
- Islanded legacy grid import returns `0.0`; grid-connected residual formula is unchanged: `api/routes/runs.py:741–752`.
- Scenario Planner shows “Operating cost (cited prices)” and collapses “Indicative estimate (placeholder rates)” by default when itemized operating cost exists: `frontend/src/components/ScenarioPlannerPage.tsx:657–723`.

The in-process REST handler run completed 17,280 ticks. S10 itemized operating cost totaled `$50,128.167952` (displayed to cents: `$50,128.17`); the diesel line has null quantity and amount. Islanded grid import is `0.0 MWh`. The legacy estimate changed from total `$45,685.3722` to `$45,021.0796`; grid-import cost changed from `$664.2925` to `$0`. The small total delta discrepancy is due to the legacy summary's four-decimal rounded components. REST breaker rows were false for all 19,749 offline/starting records; on-bus synchronized/unloading values matched the physical tick.

The base demo, H1-24h, and H2-24h seed-42 study gates match the D6-F/D6b references: all compared metrics are identical (42 metric fields per arm), `compare_runs` is PASS with all 10 conditions matching for each pair. `ACCEPTANCE_STUDY_GATES.json` preserves scalar metric values and represents any large list/dict metric values by type, count, and canonical-JSON SHA-256 rather than committing bulky event data. Physical hashes:

| Scenario | Baseline | Informed |
|---|---|---|
| Base demo | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` | `72cc28766574a78c44913d389207bc6cca268ac1bf29b15abd148c63af334754` |
| H1-24h | `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` | `437d480102d11676df747a5ddc742cd29c9785956c1255098dc8d00d9f18a264` |
| H2-24h | `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` | `17954e9420ad8d0c9493a690c03cd670ae0a5f57df60f801b7c292aeea3a9fba` |

Base-demo certified values remain unchanged: unserved energy `0.351692658 / 0.020719074 MWh`; turbine fuel `714.363019086 / 665.398247704 MMBtu`; curtailment `8.136511735 / 5.278943188 MWh`; peak unserved `22.309362466 / 7.52325057 MW`.

### Tests and full suites

Focused tests passed: 28 passed (`tests/test_operating_cost.py` and `tests/test_dr_isl_frequency_feedback.py`). The frontend production build passed (`tsc --noEmit` and Vite build); Vite emitted only its existing large-chunk advisory.

Full-suite results in the real simulator package:

| `PYTHONHASHSEED` | Passed | Failed | Skipped | Xfailed | Added vs Phase 6c | Removed |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 2,246 | 15 | 3 | 23 | 0 | `tests/test_gpu_load_profile.py::test_gpu_load_profile` |
| 987654321 | 2,246 | 15 | 3 | 23 | 0 | `tests/test_gpu_load_profile.py::test_gpu_load_profile` |

Both runs also reported 54 warnings and 3 passing subtests. The 15 failure IDs are identical between runs and are the 15 remaining baseline IDs; the waived GPU-load test passed in both runs. The JUnit XML, failure lists, and JSON summaries are saved under `tools/dr_isl/d6c/`.

### Final D6c disposition

- D6c acceptance gates pass under Lloyd's accepted S10 pinned-reference change; the direct existing-scenario hashes and protected study gates remain unchanged.
- No test fixture change was needed beyond tests already in `774fae5`; no separate test commit was made.
- No workflow was restarted. No publish, deploy, or push was performed.
- `git ls-files` returned no matches for `slurm-log.csv`, `tres-mapping.txt`, `*.channels.csv`, or `gridsignal.db`.
- Machine-readable evidence: `ACCEPTANCE_EXISTING_SCENARIO_HASHES.json`, `ACCEPTANCE_STUDY_GATES.json`, `S10_REST_ACCEPTANCE.json`, both `SUITE_SUMMARY_*.json`, both `FAILING_TESTS_*.txt`, and both `FULL_SUITE_*.xml` files in `tools/dr_isl/d6c/`.

This completes D6c only. IMPL-ISL-25 was not started.
