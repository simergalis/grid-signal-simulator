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

`git show --stat` reports 8 files changed, 736 insertions, and 55 deletions. This follow-up adds only this report and `tools/dr_isl/d6c/D6C_X1_TICK_DIFF.json`; it does not resolve the gate failure. D6c remains stopped for review.
