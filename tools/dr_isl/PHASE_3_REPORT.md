# DR-2026-10-20-ISLAND-COLLAPSE — PHASE 3 STOP REPORT

STATUS: STOPPED; Phase 3 is NOT finished or validated.

Base = 134538067d4eb4c2ce14232e483e9a91fd31276b; Git subject = Published your App. git diff --stat 5e55706..1345380 is empty. This is a Git finding, not a new production-deployment check.

HEAD at report = 134538067d4eb4c2ce14232e483e9a91fd31276b. No deliberate Phase 3 commit was made.

P = attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim; T = /tmp/DR-ISL-phase3/.

No publish, deployment, push or Phase 4. No source repair was made after the candidate probe failed. The working tree contains a known-crashing, UNVALIDATED candidate; do not treat it as production-ready.

## STOP conditions and scope of the remaining evidence

B5 is triggered: the base H2 informed arm rejects six starts while an eligible alternate exists. Lloyd's decision on certified records is required before an implementation commit. The requested candidate quantification then failed during the probe, before an actual H2 arm result existed. No before/after metric deltas can therefore be reported. No full suite was started.

## 3.0 Design and 3.1 unvalidated implementation

The before-edit design is tools/dr_isl/PHASE_3_DESIGN.md; it includes the runtime caller found by the base trace.

One TurbineModule.start_eligibility preserves hot_standby, state and minimum-down conditions/order. command_start delegates its safety check; unit_availability carries a verdict; core commitment, pre-staging and forecast candidate selection consume it. Explicit operator targets are not retargeted. A raw offline roster remains separate from start selection so reserve labels are not erased by the hot-standby guard. The newly introduced blocked-episode logger is defective for an existing nullable blocked_by value.

Current source locations and changed line ranges (literal diff hunk headers):

```text
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1056,0 +1057,12 @@ class TurbineModule(AssetModule):
@@ -1069 +1081,3 @@ class TurbineModule(AssetModule):
@@ -1071,11 +1084,0 @@ class TurbineModule(AssetModule):
@@ -1117 +1120,3 @@ class TurbineModule(AssetModule):
@@ -1134,0 +1140 @@ class TurbineModule(AssetModule):
@@ -1144,0 +1151,2 @@ class TurbineModule(AssetModule):
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
@@ -328,0 +329,13 @@ def evaluate_commitment(
@@ -331 +344 @@ def evaluate_commitment(
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
@@ -593 +593,2 @@ class DispatchArbitrator:
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
@@ -747,0 +748,5 @@ class UnitAvailability:
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -293,0 +294 @@ class SimulationState:
@@ -601 +602 @@ _STANDBY_THERMAL_PRIORITY = {
@@ -619,0 +621,43 @@ def _offline_turbines_by_thermal_priority(
@@ -630 +674 @@ def _promote_reserve_standby_labels(
@@ -717,5 +761 @@ def _release_hot_standby_for_contingency(
@@ -2181 +2221 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
@@ -2184,3 +2224,4 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
@@ -2242,5 +2283 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
@@ -2318,0 +2356 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
@@ -2538 +2576 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
@@ -1522 +1522,3 @@ class RunContext:
@@ -1524 +1526 @@ class RunContext:
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
@@ -622,14 +622,19 @@ class ForecastDrivenTurbineController:
@@ -831 +836 @@ class ForecastDrivenTurbineController:
@@ -1199 +1204 @@ class ForecastDrivenTurbineController:
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
@@ -0,0 +1,117 @@
```

## 3.2 TC-ISL-06

TC-ISL-06 collision search before creation returned no matches. New node IDs:

```text
tests/test_dr_isl_start_eligibility.py::test_tc_isl_06a_single_guard_call_graph
tests/test_dr_isl_start_eligibility.py::test_tc_isl_06b_skip_min_down_start_alternate
tests/test_dr_isl_start_eligibility.py::test_tc_isl_06c_no_eligible_one_log_per_episode
tests/test_dr_isl_start_eligibility.py::test_tc_isl_06_guard_boundaries_unchanged
```

```text
....                                                                     [100%]
4 passed in 6.87s
```

The four tests pass, but do not cover nullable CommitmentDecision.blocked_by. No existing test was edited. The later integration/probe failure is not relabelled a test pass.

## 3.3 B1–B4: completed BASE captures only; candidate comparisons NOT VERIFIED

For app cases the canonical physical hash is the streaming sink hash, after RunManager enrichment. The command observer also hashes RunContext.step output before that enrichment; its hashes/prefixes are labelled INTERNAL, not substituted for Phase 2d sink references. This boundary difference is an instrumentation detail, not a physical divergence.

| Base scenario/arm | Ticks | Rejected command attempts | Canonical physical SHA-256 |

|---|---|---|---|

| S10_mit_supercloud_2021-08-11 / app | 17280 | 1154 | 51dfe89b51138d85930b01684c95c58d60d7dcd1ed0c36801657c9d41840ef52 |

| demo-islanded-ramp / app | 2160 | 0 | fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a |

| scenario-100mw-fuel-cell-bess-diesel / app | 252 | 0 | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b |

| scenario-equinix-sj-1 / app | 720 | 0 | 328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84 |

| scenario-fc100-islanded-v2 / app | 264 | 0 | d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3 |

| scenario-fc100-islanded-zero-hot-v2 / app | 264 | 0 | d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2 |

| scenario-hybrid-ai-100mw-addendum-i / app | 120 | 0 | 9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a |

| scenario-turbine-01 / app | 720 | 0 | 006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a |

| scenario-uneven-multisched-01 / baseline | 1440 | 0 | 90f4b8a55acceb521f972d9596c5137f104dbc34e158ac3bc58cadf73e5164f1 |

| scenario-uneven-multisched-01 / informed | 1440 | 0 | ea12dabd9944d98aad3f8fc966122f2432e33fb7bd150c8dc313ca9a88dd27a6 |

B1 first BASE rejection: S10 pre-staging tick 1059, command sim_time=5288 s; first core commitment rejection tick 1070, sim_time=5345 s. H2 informed first rejection tick 10071, sim_time=50350 s. Completed other base cases in the table have no rejected command. No HEAD prefix/whole-run comparison passed: no corresponding completed HEAD runs exist.

### B2 S10_mit_supercloud_2021-08-11, BASE ONLY

ticks=17280; min BESS SoC=0.0; frequency min/max=[-737.1409980342337, 998.9330534505464]; unserved MWh=12.5194325350618; observed island_collapsed=True events=None (None means none observed; full requested horizon completed).

Rejected attempts=1154; core=1132; pre-staging=22.

Phase D comparison window 5345–10050 s: 234 core rejections, 50 with an eligible alternate. The 234/50 figures are reproduced for that window; the full 24h totals are larger.

```json
[
  {
    "tick": 1,
    "sim_time": 0.0,
    "unit": "turbine-1",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 107,
    "sim_time": 527.0,
    "unit": "turbine-2",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 226,
    "sim_time": 1125.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 420,
    "sim_time": 2092.0,
    "unit": "turbine-4",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 1216,
    "sim_time": 6075.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 1375,
    "sim_time": 6867.0,
    "unit": "turbine-4",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 2012,
    "sim_time": 10055.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 2072,
    "sim_time": 10355.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 2906,
    "sim_time": 14525.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 3549,
    "sim_time": 17740.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 3609,
    "sim_time": 18040.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 5271,
    "sim_time": 26347.0,
    "unit": "turbine-3",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 6667,
    "sim_time": 33330.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 6832,
    "sim_time": 34155.0,
    "unit": "turbine-1",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 6892,
    "sim_time": 34455.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 6964,
    "sim_time": 34815.0,
    "unit": "turbine-2",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 7479,
    "sim_time": 37390.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 8150,
    "sim_time": 40745.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 8639,
    "sim_time": 43186.0,
    "unit": "turbine-3",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 10491,
    "sim_time": 52449.0,
    "unit": "turbine-2",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 10550,
    "sim_time": 52745.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 10622,
    "sim_time": 53105.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 11514,
    "sim_time": 57565.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 11574,
    "sim_time": 57865.0,
    "unit": "turbine-4",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 14726,
    "sim_time": 73623.0,
    "unit": "turbine-2",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 14789,
    "sim_time": 73940.0,
    "unit": "turbine-3",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 14859,
    "sim_time": 74290.0,
    "unit": "turbine-4",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 15530,
    "sim_time": 77642.0,
    "unit": "turbine-2",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 15621,
    "sim_time": 78099.0,
    "unit": "turbine-3",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 15810,
    "sim_time": 79044.0,
    "unit": "turbine-4",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 16562,
    "sim_time": 82804.0,
    "unit": "turbine-3",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 16720,
    "sim_time": 83593.0,
    "unit": "turbine-4",
    "caller": "dispatch.py:617"
  }
]
```

Candidate rejection counts, start times and outcome deltas: NOT AVAILABLE; not run after STOP.

### B3 demo-islanded-ramp, BASE ONLY

ticks=2160; min BESS SoC=0.0; frequency min/max=[-127.48961154607643, 60.0]; unserved MWh=0.7984763561509628; observed island_collapsed=True events=None (None means none observed; full requested horizon completed).

Rejected attempts=0; core=0; pre-staging=0.

```json
[
  {
    "tick": 1,
    "sim_time": 0.0,
    "unit": "turbine-1",
    "caller": "dispatch.py:617"
  },
  {
    "tick": 72,
    "sim_time": 355.0,
    "unit": "turbine-2",
    "caller": "simulation_core.py:2350"
  },
  {
    "tick": 192,
    "sim_time": 955.0,
    "unit": "turbine-3",
    "caller": "simulation_core.py:2350"
  }
]
```

Candidate rejection counts, start times and outcome deltas: NOT AVAILABLE; not run after STOP.

## B5 H2 — literal baseline rejection evidence

BASE repetition 2: ticks=17280, rejected starts=6.

BASE repetition 1: ticks=17280, rejected starts=6.

| Tick | Command time s | Unit | Stop time s | Elapsed / minimum s | Eligible alternate |

|---|---|---|---|---|---|

| 10071 | 50350.0 | gt-hot-01 | 49480.0 | 870.0 / 900.0 | gt-hot-02 |

| 10072 | 50355.0 | gt-hot-01 | 49480.0 | 875.0 / 900.0 | gt-hot-02 |

| 10073 | 50360.0 | gt-hot-01 | 49480.0 | 880.0 / 900.0 | gt-hot-02 |

| 10074 | 50365.0 | gt-hot-01 | 49480.0 | 885.0 / 900.0 | gt-hot-02 |

| 10075 | 50370.0 | gt-hot-01 | 49480.0 | 890.0 / 900.0 | gt-hot-02 |

| 10076 | 50375.0 | gt-hot-01 | 49480.0 | 895.0 / 900.0 | gt-hot-02 |

Base command application: P/runtime/run_manager.py:1523. Base candidate selection: P/runtime/turbine_commitment.py:622–635, call :831. This is forecast START selection; the earlier progress message's 'preload' wording was imprecise. Explicit operator command application is not itself retargeted.

Completed H2 baseline controls (both repetitions):

- informed scenario-h2-slurm-24h-informed-base-2: ticks=17280, compact_sha256=6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711, native status=PASS.

- informed scenario-h2-slurm-24h-informed-base-1: ticks=17280, compact_sha256=6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711, native status=PASS.

- baseline scenario-h2-slurm-24h-baseline-base-2: ticks=17280, compact_sha256=8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66, native status=FAIL.

```json
[
  {
    "type": "StartFuelReconciliationError",
    "message": "start fuel does not reconcile with recorded start events: reported=124.000000000, measured=124.000000000, recorded_events=6, measured_events=11, hot_standby_release_charged=True"
  }
]
```

- baseline scenario-h2-slurm-24h-baseline-base-1: ticks=17280, compact_sha256=8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66, native status=FAIL.

```json
[
  {
    "type": "StartFuelReconciliationError",
    "message": "start fuel does not reconcile with recorded start events: reported=124.000000000, measured=124.000000000, recorded_events=6, measured_events=11, hot_standby_release_charged=True"
  }
]
```

The base H2 baseline's 6 recorded versus 11 measured starts, 124.000000000 reported/measured MMBtu FAIL is reproduced twice. Whether the candidate changes it is NOT MEASURED; the candidate probe aborted before an arm/control completed.

### Candidate probe — new implementation defect, not a stale test

```text
Traceback (most recent call last):
  File "/tmp/DR-ISL-phase3/observe.py", line 112, in <module>
    adapter.run(package, a.scenario, a.arm, label)
    ~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/tmp/DR-ISL-phase3/harness.py", line 79, in run
    events, demand = executor._probe(spec, run_id=f"{sid}-study-s1-probe")
                     ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/workspace/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py", line 311, in _probe
    tick = ctx.step()
  File "/tmp/DR-ISL-phase3/observe.py", line 92, in step
    tick = original_step(context)
  File "/home/runner/workspace/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py", line 1843, in step
    result = evaluate_tick(self.sim_state, clock)
  File "/home/runner/workspace/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py", line 2356, in evaluate_tick
    _log_start_ineligibility_episode(state, _commit_decision, sim_time)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/workspace/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py", line 658, in _log_start_ineligibility_episode
    blocked = decision.blocked_by.startswith("no eligible turbine:")
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'startswith'
```

P/core/simulation_core.py:658 calls decision.blocked_by.startswith(...). P/core/commitment.py:359 initializes decommit_blocked_by=None and :431 returns it on an ordinary hold. That existing nullable value exposes the new logger's invalid assumption. This is a CANDIDATE BUG. It was not fixed after the stop condition.

Every candidate H2 metric/delta, compact hash and native guard verdict is UNAVAILABLE. The batch exited 1 on its first candidate probe; later head repetitions/controls did not execute. The unrelated H base batch was stopped once the rejection condition was known; no completed H1 record is claimed.

Full BASE H2 metrics (all keys, not just selected numbers):

### BASE H2 baseline

```json
{
  "tick_count": 17280,
  "interval_seconds": 5.0,
  "fuel_by_component_mmbtu": {
    "load_fuel_mmbtu": 5136.719001539,
    "no_load_fuel_mmbtu": 65.231666667,
    "hot_standby_fuel_mmbtu": 4.552430556,
    "start_fuel_mmbtu": 124.0
  },
  "turbine_fuel_mmbtu": 5330.503098761,
  "fuel_reconciled": true,
  "start_fuel_reconciliation": {
    "release_charged": true,
    "recorded_event_count": 6,
    "measured_event_count": 11,
    "measured_start_fuel_mmbtu": 124.0,
    "tier_sum_mmbtu": 124.0,
    "passed": false
  },
  "dispatch_curtailment_mwh": 349.917690813,
  "dispatch_curtailment_interval_exposure_fuel_mmbtu": 4838.569627585,
  "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
    "load_fuel_mmbtu": 4712.832474807,
    "no_load_fuel_mmbtu": 61.375,
    "hot_standby_fuel_mmbtu": 4.362152778,
    "start_fuel_mmbtu": 60.0
  },
  "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
    "gt-spin-01": 2130.396041667,
    "gt-spin-02": 2130.396041667,
    "gt-hot-01": 345.279002588,
    "gt-hot-02": 232.498541667
  },
  "dispatch_curtailment_attributable_fuel_mmbtu": 3680.617469434,
  "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
    "gt-spin-01": 1639.723878254,
    "gt-spin-02": 1639.723878254,
    "gt-hot-01": 221.207657519,
    "gt-hot-02": 179.962055406
  },
  "unserved_mwh": 5.011418076,
  "peak_unserved_mw": 44.86838787,
  "served_mwh": 138.948956374,
  "unserved_intervals": [
    {
      "start_sim_time_s": 29125.0,
      "end_sim_time_s": 29410.0,
      "peak_unserved_mw": 38.098732218014646
    },
    {
      "start_sim_time_s": 29450.0,
      "end_sim_time_s": 29460.0,
      "peak_unserved_mw": 4.37595409165764
    },
    {
      "start_sim_time_s": 36310.0,
      "end_sim_time_s": 36415.0,
      "peak_unserved_mw": 40.894865912415625
    },
    {
      "start_sim_time_s": 43510.0,
      "end_sim_time_s": 43620.0,
      "peak_unserved_mw": 41.9036584956214
    },
    {
      "start_sim_time_s": 50710.0,
      "end_sim_time_s": 50815.0,
      "peak_unserved_mw": 40.390845418775996
    },
    {
      "start_sim_time_s": 57910.0,
      "end_sim_time_s": 58025.0,
      "peak_unserved_mw": 44.86838786968556
    },
    {
      "start_sim_time_s": 65110.0,
      "end_sim_time_s": 65215.0,
      "peak_unserved_mw": 40.390845418775996
    }
  ],
  "energy_balance": {
    "closure_status": true,
    "max_abs_physical_ledger_defect_mw": 0.0,
    "served_demand_mwh": 138.948956374,
    "unserved_demand_mwh": 5.011418076
  },
  "bess_soc_min": 0.950386947,
  "bess_soc_max": 0.999999999,
  "bess_soc_final": 0.999999998,
  "commitment": {
    "distinct_event_count": 39,
    "visible_distinct_event_count": 39,
    "suppressed_repeat_count": 0,
    "log_complete": true,
    "omitted_record_count": 0,
    "reserve_floor_refusal_count": 0,
    "reserve_floor_distinct_event_count": 0,
    "reserve_floor_visible_distinct_event_count": 0,
    "reserve_floor_suppressed_repeat_count": 0,
    "reserve_floor_log_complete": true,
    "reserve_floor_omitted_record_count": 0,
    "same_unit_restart_within_min_down_window_count": 0
  },
  "forecast": {
    "miss_count": 0,
    "miss_peak_mw": 0.0
  },
  "compute_trace_sha256": "ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b",
  "compute_trace_count": 17280,
  "daily_breakdown": [
    {
      "day": 1,
      "kind": "weekday",
      "fuel_by_component_mmbtu": {
        "load_fuel_mmbtu": 5136.719001539,
        "no_load_fuel_mmbtu": 65.231666667,
        "hot_standby_fuel_mmbtu": 4.552430556,
        "start_fuel_mmbtu": 124.0
      },
      "fuel_mmbtu": 5330.503098761,
      "unserved_mwh": 5.011418076,
      "curtailed_mwh": 349.917690813,
      "bess_soc_end": 0.999999998
    }
  ],
  "constraints_valid": false,
  "hard_violations": [
    "start_count_reconciliation:gt-hot-01:asset=2:log=1:untracked_path=production_command_or_cascade",
    "start_count_reconciliation:gt-hot-01:asset=3:log=1:untracked_path=production_command_or_cascade",
    "start_count_reconciliation:gt-hot-01:asset=4:log=1:untracked_path=production_command_or_cascade",
    "start_count_reconciliation:gt-hot-01:asset=5:log=1:untracked_path=production_command_or_cascade",
    "start_count_reconciliation:gt-hot-01:asset=6:log=1:untracked_path=production_command_or_cascade"
  ]
}
```

### BASE H2 informed

```json
{
  "tick_count": 17280,
  "interval_seconds": 5.0,
  "fuel_by_component_mmbtu": {
    "load_fuel_mmbtu": 5107.722017303,
    "no_load_fuel_mmbtu": 64.866666667,
    "hot_standby_fuel_mmbtu": 3.761458333,
    "start_fuel_mmbtu": 152.0
  },
  "turbine_fuel_mmbtu": 5328.350142303,
  "fuel_reconciled": true,
  "start_fuel_reconciliation": {
    "release_charged": true,
    "recorded_event_count": 14,
    "measured_event_count": 14,
    "measured_start_fuel_mmbtu": 152.0,
    "tier_sum_mmbtu": null,
    "passed": true
  },
  "dispatch_curtailment_mwh": 343.106291593,
  "dispatch_curtailment_interval_exposure_fuel_mmbtu": 4894.248370795,
  "dispatch_curtailment_interval_exposure_fuel_by_component_mmbtu": {
    "load_fuel_mmbtu": 4677.688023572,
    "no_load_fuel_mmbtu": 60.918333333,
    "hot_standby_fuel_mmbtu": 3.642013889,
    "start_fuel_mmbtu": 152.0
  },
  "dispatch_curtailment_interval_exposure_fuel_by_unit_mmbtu": {
    "gt-spin-01": 2152.666217898,
    "gt-spin-02": 1708.675833457,
    "gt-hot-01": 738.419791667,
    "gt-hot-02": 294.486527778
  },
  "dispatch_curtailment_attributable_fuel_mmbtu": 3608.878484911,
  "dispatch_curtailment_attributable_fuel_by_unit_mmbtu": {
    "gt-spin-01": 1645.626267003,
    "gt-spin-02": 1260.837847434,
    "gt-hot-01": 537.463176576,
    "gt-hot-02": 164.951193898
  },
  "unserved_mwh": 0.893328423,
  "peak_unserved_mw": 42.36838787,
  "served_mwh": 143.067046027,
  "unserved_intervals": [
    {
      "start_sim_time_s": 29130.0,
      "end_sim_time_s": 29165.0,
      "peak_unserved_mw": 19.287968405751712
    },
    {
      "start_sim_time_s": 29215.0,
      "end_sim_time_s": 29235.0,
      "peak_unserved_mw": 1.8802011558611156
    },
    {
      "start_sim_time_s": 36310.0,
      "end_sim_time_s": 36350.0,
      "peak_unserved_mw": 38.394865912415625
    },
    {
      "start_sim_time_s": 43510.0,
      "end_sim_time_s": 43555.0,
      "peak_unserved_mw": 39.4036584956214
    },
    {
      "start_sim_time_s": 50710.0,
      "end_sim_time_s": 50730.0,
      "peak_unserved_mw": 29.140845418775996
    },
    {
      "start_sim_time_s": 50750.0,
      "end_sim_time_s": 50760.0,
      "peak_unserved_mw": 1.25
    },
    {
      "start_sim_time_s": 57910.0,
      "end_sim_time_s": 57940.0,
      "peak_unserved_mw": 42.36838786968556
    },
    {
      "start_sim_time_s": 65110.0,
      "end_sim_time_s": 65140.0,
      "peak_unserved_mw": 37.890845418775996
    }
  ],
  "energy_balance": {
    "closure_status": true,
    "max_abs_physical_ledger_defect_mw": 0.0,
    "served_demand_mwh": 143.067046027,
    "unserved_demand_mwh": 0.893328423
  },
  "bess_soc_min": 0.950386947,
  "bess_soc_max": 0.999999998,
  "bess_soc_final": 0.999999987,
  "commitment": {
    "distinct_event_count": 67,
    "visible_distinct_event_count": 67,
    "suppressed_repeat_count": 11205,
    "log_complete": true,
    "omitted_record_count": 0,
    "reserve_floor_refusal_count": 14890,
    "reserve_floor_distinct_event_count": 14890,
    "reserve_floor_visible_distinct_event_count": 14890,
    "reserve_floor_suppressed_repeat_count": 0,
    "reserve_floor_log_complete": true,
    "reserve_floor_omitted_record_count": 0,
    "same_unit_restart_within_min_down_window_count": 0
  },
  "forecast": {
    "miss_count": 39,
    "miss_peak_mw": 13.130749227
  },
  "compute_trace_sha256": "ea1916a426e67dde51a9a926dc4b64b0c2eb2470ee2e0076fe7f17b8d55f420b",
  "compute_trace_count": 17280,
  "daily_breakdown": [
    {
      "day": 1,
      "kind": "weekday",
      "fuel_by_component_mmbtu": {
        "load_fuel_mmbtu": 5107.722017303,
        "no_load_fuel_mmbtu": 64.866666667,
        "hot_standby_fuel_mmbtu": 3.761458333,
        "start_fuel_mmbtu": 152.0
      },
      "fuel_mmbtu": 5328.350142303,
      "unserved_mwh": 0.893328423,
      "curtailed_mwh": 343.106291593,
      "bess_soc_end": 0.999999987
    }
  ],
  "constraints_valid": true,
  "hard_violations": []
}
```

### B6 base demo

Both BASE arms completed with zero rejected commands; full base metrics are in PHASE_3_EVIDENCE.json. No candidate arm completed/was validated after the STOP. No identical result or reissued compare_runs verdict is claimed.

## 3.4 Full suite

NOT RUN. Pass/fail counts and added/removed/remaining comparison are NOT MEASURED. No PHASE_3_FAILING_TESTS.txt is created, rather than presenting an empty list as a passing suite. The Phase 2d 15-failure baseline remains tools/dr_isl/PHASE_2D_FAILING_TESTS.txt.

## 3.5 Commit and tracking status

No Phase 3 implementation, test-update or report commit: B5 requires STOP before committing. Any subsequent automatic checkpoint remains UNVALIDATED until the gates and Lloyd's record decision. The new P test is explicitly force-added/tracked; no scenario JSON was changed.

```text
 M .agents/memory/MEMORY.md
 M .agents/memory/s1-study-harness.md
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
A  attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
?? tools/dr_isl/PHASE_3_DESIGN.md
?? tools/dr_isl/PHASE_3_EVIDENCE.json
?? tools/dr_isl/PHASE_3_REPORT.md
?? tools/dr_isl/PHASE_3_TC06.xml
```

Scenario diff:

```text
(empty)
```

Phase 3 commits since base:

```text
(none)
```

Baseline runner content diff:

```text
(empty)
```

Scratch storage: streaming hashes/metrics and command-event evidence only, no scenario-run full tick exports. Files are capped by RLIMIT_FSIZE=200000000. The pre-existing core diagnostic has a hardcoded /tmp/cmt001_diag.log path; it is not a new Phase 3 source edit. Output-only adapters suppress normal study tick artifacts.

```json
[
  [
    21083303,
    "base/docs/addendum-h-phase2b-results/scenario-h1-k8s-ray-7d-baseline_ticks.jsonl.gz"
  ],
  [
    20527305,
    "base/docs/addendum-h-phase2b-results/scenario-h1-k8s-ray-7d-informed_ticks.jsonl.gz"
  ],
  [
    19864183,
    "base/tools/invariants/recordings/run-37d6809c8917.jsonl"
  ],
  [
    18833087,
    "base/docs/addendum-h-phase2b-results/scenario-h2-slurm-7d-informed_ticks.jsonl.gz"
  ],
  [
    16201652,
    "base/docs/addendum-h-phase2b-results/scenario-h2-slurm-7d-baseline_ticks.jsonl.gz"
  ],
  [
    5405213,
    "base/reports/NAR-001_residuals.jsonl"
  ],
  [
    2117665,
    "base/docs/addendum-h-phase2b-results/scenario-h1-k8s-ray-24h-baseline_ticks.jsonl.gz"
  ],
  [
    2063195,
    "base/docs/addendum-h-phase2b-results/scenario-h1-k8s-ray-24h-informed_ticks.jsonl.gz"
  ]
]
```

## Full literal candidate diff (uncommitted, UNVALIDATED)

```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
index 1b2b974..11ec12b 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1054,6 +1054,18 @@ class TurbineModule(AssetModule):
         self._last_setpoint_mw = float(new_output_mw)   # store before rate-clip
         self._current_output_mw = max(0.0, min(new_output_mw, self.config.rated_mw))
 
+    def start_eligibility(self, sim_time: float) -> tuple[bool, str]:
+        """DR D2 / IMPL-ISL-5: the single, unchanged turbine start interlock."""
+        if self.config.hot_standby:
+            return False, "hot_standby"
+        if self.state != TurbineState.OFFLINE:
+            return False, "state"
+        if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
+            elapsed = sim_time - self._stop_time_s
+            if elapsed < self.config.t_min_down_s:
+                return False, "min_down"
+        return True, "eligible"
+
     def command_start(self, sim_time: float) -> None:
         """Transition OFFLINE → STARTING.  Phase 2 commitment-logic entry point.
 
@@ -1066,19 +1078,10 @@ class TurbineModule(AssetModule):
 
         No output is produced while STARTING (_current_output_mw stays 0.0).
         """
-        if self.config.hot_standby:
+        # DR D2 / IMPL-ISL-5: retain the safety check, using the same predicate
+        # as selection and the availability boundary (no second guard copy).
+        if not self.start_eligibility(sim_time)[0]:
             return
-        if self.state != TurbineState.OFFLINE:
-            return
-
-        # R6: enforce minimum down-time when the constraint is enabled.
-        # Phase E closeout Item 1 / D-03: gated on min_down_enabled so tests
-        # that create TurbineConfig() directly (min_down_enabled=False default)
-        # are unaffected.
-        if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
-            elapsed = sim_time - self._stop_time_s
-            if elapsed < self.config.t_min_down_s:
-                return  # cooling window not yet satisfied
 
         # Determine thermal state from time offline since last synchronisation.
         # First start (never stopped): use config.initial_thermal_state so the
@@ -1114,7 +1117,9 @@ class TurbineModule(AssetModule):
                 ThermalState.COLD: self.config.fuel.start_fuel_mmbtu_cold,
             }[self._thermal_state]
 
-    def unit_availability(self) -> "UnitAvailability":
+    # PROPOSED_HERE: epoch default preserves existing no-argument boundary
+    # callers; runtime selection always passes the actual simulation time.
+    def unit_availability(self, sim_time: float = 0.0) -> "UnitAvailability":
         """Build a UnitAvailability boundary object from current state.
 
         Called by simulation_core.py each tick to build the availability list
@@ -1132,6 +1137,7 @@ class TurbineModule(AssetModule):
         else:
             time_to_online = None
 
+        eligible, reason = self.start_eligibility(sim_time)
         return UnitAvailability(
             unit_id=self.config.asset_id,
             state=self.state,
@@ -1142,6 +1148,8 @@ class TurbineModule(AssetModule):
             time_to_online_s=time_to_online,
             out_of_service_reason=self._out_of_service_reason,
             hot_standby=self.config.hot_standby,
+            start_eligible=eligible,
+            start_ineligibility_reason=None if eligible else reason,
         )
 
     def command_stop(self, sim_time: float) -> Optional[str]:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
index c6b6401..85c7a7c 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/commitment.py
@@ -326,9 +326,22 @@ def evaluate_commitment(
                 ),
                 floor_mw=floor_mw, floor_violated=floor_violated,
             )
+        # DR D2 / IMPL-ISL-5: consume the one asset predicate's snapshot,
+        # preserving caller priority, rather than retrying offline[0].
+        eligible = next((unit for unit in offline if unit.start_eligible), None)
+        if eligible is None:
+            return CommitmentDecision(
+                action="hold",
+                target_unit_id=None,
+                reason=f"commit condition met (U={utilisation:.3f}, floor_violated={floor_violated})",
+                blocked_by="no eligible turbine: " + "; ".join(
+                    f"{unit.unit_id}={unit.start_ineligibility_reason}" for unit in offline
+                ),
+                floor_mw=floor_mw, floor_violated=floor_violated,
+            )
         return CommitmentDecision(
             action="commit",
-            target_unit_id=offline[0].unit_id,
+            target_unit_id=eligible.unit_id,
             reason=(
                 f"floor_violated={floor_violated}, U={utilisation:.3f}"
                 f" ≥ {cfg.commit_utilisation}" if not floor_violated else
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
index 4bd7cac..9507e45 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
@@ -590,7 +590,8 @@ class DispatchArbitrator:
         if not _active_turbines and not _active_fuel_cells:
             required_ramp_s = float("inf")
         else:
-            _offline = [t for t in _active_turbines if t.state == TurbineState.OFFLINE]
+            # DR D2 / IMPL-ISL-5: staging shares command_start's interlock.
+            _offline = [t for t in _active_turbines if t.start_eligibility(sim_time)[0]]
             _on_bus  = [t for t in _active_turbines if t.state != TurbineState.OFFLINE]
 
             # ── Stage offline turbines: N_needed + 1 N-1 spare ──────────────────
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
index cf0140b..3044d09 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/models.py
@@ -745,6 +745,11 @@ class UnitAvailability:
     time_to_online_s: Optional[float]    # 0.0 = SYNCHRONISED; None = OUT_OF_SERVICE
     out_of_service_reason: Optional[str] # None unless OUT_OF_SERVICE
     hot_standby: bool = False            # True → excluded from ramp credit and dispatch
+    # DR D2 / IMPL-ISL-5: verdict evaluated by TurbineModule.start_eligibility.
+    # PROPOSED_HERE: True preserves explicitly supplied PMS/test snapshots;
+    # live turbine snapshots always supply their time-resolved verdict.
+    start_eligible: bool = True
+    start_ineligibility_reason: Optional[str] = None
 
     @property
     def is_starting(self) -> bool:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index 60596e0..94d3a3a 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -291,6 +291,7 @@ class SimulationState:
     _commit_cfg:    CommitmentConfig    = field(init=False)
     _pending_start: PendingStartRegister = field(init=False)
     _commit_cond:   SustainedCondition  = field(init=False)
+    _start_ineligible_episode_logged: bool = field(default=False, init=False)
     _decommit_cond: SustainedCondition  = field(init=False)
     # Contingency-triggered standby release is deliberately separate from
     # evaluate_commitment().  The condition is armed again only after one
@@ -598,7 +599,7 @@ _STANDBY_THERMAL_PRIORITY = {
 }
 
 
-def _offline_turbines_by_thermal_priority(
+def _offline_turbine_roster(
     turbines: list[TurbineModule],
 ) -> list[TurbineModule]:
     """Return offline turbines in hot → warm → cold, then roster order."""
@@ -617,6 +618,49 @@ def _offline_turbines_by_thermal_priority(
     )
 
 
+def _offline_turbines_by_thermal_priority(
+    turbines: list[TurbineModule], sim_time: float, *, include_blocked: bool = False,
+) -> list[TurbineModule]:
+    """DR D2 / IMPL-ISL-5: one start predicate, unchanged thermal/roster order.
+
+    The commitment boundary includes blocked non-reserved units so it can
+    report why an episode has no candidate. Reserve labels use the raw roster.
+    """
+    candidates = []
+    for turbine in _offline_turbine_roster(turbines):
+        eligible, reason = turbine.start_eligibility(sim_time)
+        if eligible or (include_blocked and reason != "hot_standby"):
+            candidates.append(turbine)
+    return candidates
+
+
+def _releasable_hot_standby_turbines(
+    turbines: list[TurbineModule], sim_time: float,
+) -> list[TurbineModule]:
+    """Evaluate unchanged interlocks under the existing explicit release authority."""
+    candidates = []
+    for turbine in _offline_turbine_roster(turbines):
+        if turbine.config.hot_standby:
+            turbine.config.hot_standby = False
+            try:
+                eligible, _ = turbine.start_eligibility(sim_time)
+            finally:
+                turbine.config.hot_standby = True
+            if eligible:
+                candidates.append(turbine)
+    return candidates
+
+
+def _log_start_ineligibility_episode(
+    state: SimulationState, decision: CommitmentDecision, sim_time: float,
+) -> None:
+    """DR D2: one commitment-log reason per contiguous blocked episode."""
+    blocked = decision.blocked_by.startswith("no eligible turbine:")
+    if blocked and not state._start_ineligible_episode_logged:
+        _log.info("Commitment engine: %s at sim_time=%.1f", decision.blocked_by, sim_time)
+    state._start_ineligible_episode_logged = blocked
+
+
 def _promote_reserve_standby_labels(
     turbines: list[TurbineModule],
 ) -> tuple[str, ...]:
@@ -627,7 +671,7 @@ def _promote_reserve_standby_labels(
     """
     remaining = [
         turbine
-        for turbine in _offline_turbines_by_thermal_priority(turbines)
+        for turbine in _offline_turbine_roster(turbines)
         if turbine.config.hot_standby
     ]
     desired = [ThermalState.HOT, ThermalState.WARM]
@@ -714,11 +758,7 @@ def _release_hot_standby_for_contingency(
     ):
         return None
 
-    hot_standby_units = [
-        turbine
-        for turbine in _offline_turbines_by_thermal_priority(state.turbines)
-        if turbine.config.hot_standby
-    ]
+    hot_standby_units = _releasable_hot_standby_turbines(state.turbines, sim_time)
     if not hot_standby_units:
         return None
 
@@ -2178,12 +2218,13 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # reserve; using them here would make the commitment decision disagree with
     # the operator-facing reserve summary during the controlled rundown.
     _avail_on_bus = [
-        t.unit_availability() for t in state.turbines if t.contributes_to_reserve
+        t.unit_availability(sim_time) for t in state.turbines if t.contributes_to_reserve
     ]
     _avail_offline = [
-        t.unit_availability()
-        for t in _offline_turbines_by_thermal_priority(state.turbines)
-        if not t.config.hot_standby
+        t.unit_availability(sim_time)
+        for t in _offline_turbines_by_thermal_priority(
+            state.turbines, sim_time, include_blocked=True,
+        )
     ]
 
     # ── Cascade commit trigger (site.cascade_commit_fraction) ─────────────
@@ -2239,11 +2280,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
                 # command_start().  Fix: clear the flag, THEN call command_start()
                 # (the guard is gone so it transitions OFFLINE → STARTING normally,
                 # using initial_thermal_state="hot" → hot_start_s duration).
-                _hs_units = [
-                    t
-                    for t in _offline_turbines_by_thermal_priority(state.turbines)
-                    if t.config.hot_standby
-                ]
+                _hs_units = _releasable_hot_standby_turbines(state.turbines, sim_time)
                 if _hs_units and state._pending_start.is_empty:
                     _next_hs = _hs_units[0]
                     _before_state = _next_hs.state
@@ -2316,6 +2353,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         decommit_enabled     = _bess_rundown_enabled and not _generation_baseload_active,
         decommit_reason_context = _bess_rundown_reason,
     )
+    _log_start_ineligibility_episode(state, _commit_decision, sim_time)
     if (
         _commit_decision.action == "commit"
         and _commit_decision.target_unit_id is not None
@@ -2535,7 +2573,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # UNLOADING units are pinned at MSL with no upward headroom — counting their
     # nameplate overstates reserve precisely when the fleet is shrinking.
     # Distinct from on_bus_output_mw which INCLUDES UNLOADING (they do produce).
-    _avail_reserve        = [t.unit_availability() for t in state.turbines if t.contributes_to_reserve]
+    _avail_reserve        = [t.unit_availability(sim_time) for t in state.turbines if t.contributes_to_reserve]
     _committed_rated_mw_cs = sum(u.rated_mw for u in _avail_reserve)
     _fleet_utilisation_cs = (
         _commitment_demand_mw / _committed_rated_mw_cs
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
index 6eec6e0..4f3fadb 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/run_manager.py
@@ -1519,9 +1519,11 @@ class RunContext:
                         unit_id, self.sim_time, self.run_id,
                     )
                 elif action == "start":
-                    was_offline = turbine.state == _TurbineState.OFFLINE
+                    # DR D2 / IMPL-ISL-5: explicit operator commands retain
+                    # their target; eligibility is not independently reimplemented.
+                    eligible, _ = turbine.start_eligibility(self.sim_time)
                     turbine.command_start(self.sim_time)
-                    accepted = was_offline and turbine.state == _TurbineState.STARTING
+                    accepted = eligible and turbine.state == _TurbineState.STARTING
                     if not accepted:
                         refusal_reason = (
                             "start refused: unit is not offline or minimum down time "
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
index ca8445f..19e8ba6 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/turbine_commitment.py
@@ -619,20 +619,25 @@ class ForecastDrivenTurbineController:
         )
         return allowance, soc
 
-    def _candidate_start(self, turbines: list[Any]) -> Optional[Any]:
-        standby = [
-            turbine for turbine in turbines
-            if turbine.state == TurbineState.OFFLINE
-            and getattr(turbine.config, "hot_standby", False)
-        ]
-        if standby:
-            return standby[0]
-        offline = [
-            turbine for turbine in turbines
-            if turbine.state == TurbineState.OFFLINE
-            and not getattr(turbine.config, "hot_standby", False)
-        ]
-        return offline[0] if offline else None
+    def _candidate_start(self, turbines: list[Any], sim_time_s: float) -> Optional[Any]:
+        # DR D2 / IMPL-ISL-5: preserve standby-first/roster priority, but use
+        # the same interlock as the core and command path. A reserved candidate
+        # is evaluated under this controller's existing explicit release authority.
+        ordered = (
+            [t for t in turbines if getattr(t.config, "hot_standby", False)]
+            + [t for t in turbines if not getattr(t.config, "hot_standby", False)]
+        )
+        for turbine in ordered:
+            reserved = bool(turbine.config.hot_standby)
+            if reserved:
+                turbine.config.hot_standby = False
+            try:
+                eligible, _ = turbine.start_eligibility(sim_time_s)
+            finally:
+                turbine.config.hot_standby = reserved
+            if eligible:
+                return turbine
+        return None
 
     def _candidate_stop(self, turbines: list[Any]) -> Optional[Any]:
         synchronized = [
@@ -828,7 +833,7 @@ class ForecastDrivenTurbineController:
         start_horizon = self.hot_start_lookahead_seconds + self.ramp_to_load_seconds
         start_peak = forecast.peak_over(start_horizon)
         if start_peak > synchronized_capacity + bess_allowance:
-            candidate = self._candidate_start(turbines)
+            candidate = self._candidate_start(turbines, float(ctx.sim_time))
             if candidate is not None:
                 self._queue(
                     ctx,
@@ -1196,7 +1201,7 @@ class ForecastDrivenTurbineController:
         accepted = True
         refusal_reason: Optional[str] = None
         if decision.action == "commit":
-            if turbine.state != TurbineState.OFFLINE:
+            if not turbine.start_eligibility(sim_time_s)[0]:
                 accepted = False
                 refusal_reason = (
                     "forecast controller veto: unit is not offline and cannot start"
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
new file mode 100644
index 0000000..61d5f82
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_start_eligibility.py
@@ -0,0 +1,117 @@
+"""DR D2 / IMPL-ISL-5, TC-ISL-06: one unchanged turbine start interlock."""
+import ast
+from dataclasses import replace
+import inspect
+import logging
+import textwrap
+from types import SimpleNamespace
+
+from core.asset_modules import TurbineModule
+from core.commitment import (
+    CommitmentConfig, PendingStartRegister, SustainedCondition, evaluate_commitment,
+)
+from core.dispatch import DispatchArbitrator
+from core.models import TurbineConfig, TurbineState
+from core.simulation_core import (
+    _log_start_ineligibility_episode, _offline_turbines_by_thermal_priority,
+    _releasable_hot_standby_turbines,
+)
+from runtime.run_manager import RunContext
+from runtime.turbine_commitment import ForecastDrivenTurbineController
+
+
+def _calls(fn):
+    return {
+        node.func.attr for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(fn))))
+        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
+    }
+
+
+def _unit(name, stopped=False):
+    # PROPOSED_HERE: synthetic fixture timestamps straddle the existing 900 s
+    # minimum-down interlock; these are not new operational settings.
+    unit = TurbineModule(TurbineConfig(
+        asset_id=name, min_down_enabled=True, t_min_down_s=900.0,
+    ))
+    if stopped:
+        unit._stop_time_s = 0.0
+    return unit
+
+
+def _decision(units, time):
+    roster = _offline_turbines_by_thermal_priority(units, time, include_blocked=True)
+    return evaluate_commitment(
+        on_bus=[], offline=[u.unit_availability(time) for u in roster],
+        p_demand_mw=20.0, pending=PendingStartRegister(),
+        commit_cond=SustainedCondition(), decommit_cond=SustainedCondition(),
+        cfg=replace(CommitmentConfig.from_catalogue(), inter_start_settle_s=0.0),
+        dt_s=5.0, sim_time=time,
+    )
+
+
+def test_tc_isl_06a_single_guard_call_graph():
+    for fn in (TurbineModule.command_start, TurbineModule.unit_availability,
+               _offline_turbines_by_thermal_priority, _releasable_hot_standby_turbines):
+        assert "start_eligibility" in _calls(fn)
+    # Inspect the entire arbitrator: staging must call the same predicate.
+    assert "start_eligibility" in _calls(DispatchArbitrator)
+    assert "start_eligibility" in _calls(ForecastDrivenTurbineController._candidate_start)
+    assert "start_eligibility" in _calls(ForecastDrivenTurbineController.adjudicate_core_proposal)
+    assert "start_eligibility" in _calls(RunContext.drain_operator_commands)
+    source = inspect.getsource(TurbineModule.command_start)
+    assert "self.config.hot_standby" not in source
+    assert "elapsed < self.config.t_min_down_s" not in source
+    assert "self.state != TurbineState.OFFLINE" not in source
+    assert "unit.start_eligible" in inspect.getsource(evaluate_commitment)
+    assert "target_unit_id=offline[0]" not in inspect.getsource(evaluate_commitment)
+
+
+def test_tc_isl_06b_skip_min_down_start_alternate():
+    cooling, alternate = _unit("cooling", True), _unit("alternate")
+    assert cooling.start_eligibility(100.0) == (False, "min_down")
+    assert alternate.start_eligibility(100.0) == (True, "eligible")
+    decision = _decision([cooling, alternate], 100.0)
+    assert decision.action == "commit"
+    assert decision.target_unit_id == "alternate"
+    alternate.command_start(100.0)
+    assert alternate.state == TurbineState.STARTING
+    assert cooling.state == TurbineState.OFFLINE
+    # The certified study's forecast selector must skip the same interlock.
+    alternate.state = TurbineState.OFFLINE
+    assert ForecastDrivenTurbineController._candidate_start(
+        None, [cooling, alternate], 100.0,
+    ) is alternate
+
+
+def test_tc_isl_06c_no_eligible_one_log_per_episode(caplog):
+    units = [_unit("one", True), _unit("two", True)]
+    state = SimpleNamespace(_start_ineligible_episode_logged=False)
+    with caplog.at_level(logging.INFO, logger="core.simulation_core"):
+        for time in (100.0, 105.0, 110.0):
+            decision = _decision(units, time)
+            assert decision.action == "hold"
+            assert decision.target_unit_id is None
+            assert "one=min_down" in decision.blocked_by
+            assert "two=min_down" in decision.blocked_by
+            _log_start_ineligibility_episode(state, decision, time)
+        logs = [r for r in caplog.records if "no eligible turbine:" in r.message]
+        assert len(logs) == 1
+        assert all(u.state == TurbineState.OFFLINE and u._start_count == 0 for u in units)
+        # Clearing the blocked condition rearms the logger, not the guard.
+        _log_start_ineligibility_episode(state, _decision(units, 900.0), 900.0)
+        _log_start_ineligibility_episode(state, _decision(units, 100.0), 100.0)
+        assert sum("no eligible turbine:" in r.message for r in caplog.records) == 2
+        assert not any("silently dropped" in r.message for r in caplog.records)
+
+
+def test_tc_isl_06_guard_boundaries_unchanged():
+    unit = _unit("boundary", True)
+    assert unit.start_eligibility(899.0) == (False, "min_down")
+    assert unit.start_eligibility(900.0) == (True, "eligible")
+    unit.config.min_down_enabled = False
+    assert unit.start_eligibility(0.0) == (True, "eligible")
+    unit.config.hot_standby = True
+    unit.state = TurbineState.STARTING
+    assert unit.start_eligibility(0.0) == (False, "hot_standby")
+    unit.config.hot_standby = False
+    assert unit.start_eligibility(0.0) == (False, "state")
```

## Persisted deliverables

- tools/dr_isl/PHASE_3_DESIGN.md
- tools/dr_isl/PHASE_3_REPORT.md
- tools/dr_isl/PHASE_3_EVIDENCE.json
- tools/dr_isl/PHASE_3_TC06.xml

STOP. No Phase 4.
