# DR-2026-10-20-ISLAND-COLLAPSE — Phase 2d STOP report
**STOPPED, NOT FINISHED: scratch filesystem exhausted (ENOSPC).**
Implementation commit: NONE. Current HEAD: `bb59f6eeccf6456c0bf838d4ee6331c0fc0524dd`.
No new tests or simulations were started after the storage failure. No implementation commit, workflow restart, publish, deploy or push. Phase 3 was not started.
The previous coordinator-gap STOP report is preserved as `/tmp/DR-ISL-phase2d/PHASE_2D_STOP2_REPORT.md` and in commit bb59f6e. This report supersedes its status.
## Stop condition and cleanup
Printed filesystem values at failure:

```
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           4.0G  4.0G     0 100% /tmp
/dev/vdd        256G  2.6G  252G   2% /home/runner/workspace
```
The report-file write failed with the literal tool error `ENOSPC: no space left on device, write`.
Observed background exits: diesel checks tMmXUVGg = 120; H/no-diesel/base sequence N8QT3Ai9 = -1; full suite aYwveBkE = 120. These are incomplete verification processes, not successful scenario or suite results.
Only the following generated, incomplete export was removed to restore scratch capacity. Its size/hash were recorded BEFORE removal:

```json
{
  "path": "/tmp/DR-ISL-phase2d/before/islanded-fc-bess-diesel-slurm-gpu-peaks.1.ticks.jsonl",
  "bytes": 2173403136,
  "sha256_partial_file": "6822e5c5d6e461a68262b5a64c36ff6611e15180584c310f46ac382cf450be76",
  "complete_lines": 840,
  "status": "incomplete export, removed to restore scratch capacity; not a simulation result"
}
```
The 840 LF-terminated records in that partial export are NOT a finalized simulation tick count or a validated physical hash. No completed Slurm GPU-peaks baseline result is claimed.
After removing it, the printed /tmp values were 4.0G total, 2.0G used, 2.1G available, 50% used. Application data and the other scratch evidence were retained.
## 2d.0 design note
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1448–1547: optional controlled advance separates physical startup capability from dispatched output; dispatch bounds and target application are on DieselModule.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:777–860,1696–1885,2065–2076: diesel enters the existing merit allocator, its current delivery is credited to primary/BESS demand, and achieved dispatch is used for fuel accounting.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:114–123,180–263,375–400: the coordinator owns lifecycle decisions, on-bus rollup and the fuel curve.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:830–846: PROPOSED_HERE infinity is the diesel ranking-only fallback, not a monetary price. The generic allocator ranks BESS, turbine, FC, diesel. In the live call, existing measured FC delivery is still netted before the allocation (fuel_cell_available_mw=0.0); that existing policy was not changed. The complete source hunk is below.
The user approved two explicit exceptions: (1) the 30% bound is SYNCHRONISED-only; UNLOADING may ramp below it; (2) the coordinator may use primary feasible supply, respecting ramp/policy/AC-energy bounds, rather than a residual that includes primary MW displaced by the diesel minimum.
## 2d.1–2d.3 implementation state: working tree only, not accepted by all gates
- D10: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py:1526–1554; attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1696–1885. Synchronized minimum = 0.30 × rated; UNLOADING remains its existing physical tail. The comment identifies NFPA 110 §8.4.2/Annex A as a monthly-test-load proxy, NOT a continuous-operation requirement.
- Dispatch-aware gap: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py:1783–1802. It uses existing BESS AC ceilings and ramp/policy-bounded primary capacity; no second diesel dispatch loop.
- IMPL-ISL-14: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:114–123,384–400: on-bus UNLOADING power and fuel counted. Fuel remains proportional to delivered load fraction; no no-load term was added.
- IMPL-ISL-15: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py:230–260: a refused stop resets the hold; completion requires each unloading unit's configured cooldown/ramp duration to have elapsed.
No scenario JSON, commitment, reserve-floor formula, frequency/protection code, configured diesel timing value or authority tier was edited. Exact production/test diff follows in the appendix.
## 2d.4 tests — completed targeted evidence
Assigned IDs: TC-ISL-19,20,21,22. Case-insensitive search for those IDs outside the new test file returned no matches.
/tmp/DR-ISL-phase2d/final-new-tests.log:1–2:

```
....                                                                     [100%]
4 passed in 0.75s
```
Asserted values in attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py: minimum 6.0 MW for a 20 MW synchronized unit; UNLOADING 5.9 MW remains counted with fuel; refused-stop hold 0.0; unloading retains its 300 s ramp; final state OFFLINE/output 0.0. TC-ISL-20 additionally covers an unloading resume and policy-held GT capacity.
The broader targeted check (before the final explicit-target edge assertion was added) was 54 passed / 2 failed. The final new-test check above includes that assertion. Full literal targeted output:

```
.............F...............F..........................                 [100%]
=================================== FAILURES ===================================
_____ test_live_diesel_is_less_aggressive_than_disabled_before_curtailment _____
tests/test_diesel_phase3.py:189: in test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
    assert disabled_tiers
E   assert ()
___________ test_hybrid_covered_demand_does_not_release_bess_reserve ___________
tests/test_diesel_setpoint_gap.py:134: in test_hybrid_covered_demand_does_not_release_bess_reserve
    assert result_480.fuel_cell_output_mw + result_480.diesel_output_mw > (
E   AssertionError: assert (59.600000000000136 + 39.99227768757201) > 99.59227768757215
E    +  where 59.600000000000136 = TickResult(run_id='diesel-setpoint-gap-regression', tick_index=96, sim_time_seconds=480.0, p_compute_demand_mw=82.9935...tisfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).fuel_cell_output_mw
E    +  and   39.99227768757201 = TickResult(run_id='diesel-setpoint-gap-regression', tick_index=96, sim_time_seconds=480.0, p_compute_demand_mw=82.9935...tisfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).diesel_output_mw
E    +  and   99.59227768757215 = TickResult(run_id='diesel-setpoint-gap-regression', tick_index=96, sim_time_seconds=480.0, p_compute_demand_mw=82.9935...tisfied=False, fleet_utilisation=0.0, commit_utilisation_threshold=0.8, pending_start_unit_id=None, slurm_metrics=None).net_demand_mw
=========================== short test summary info ============================
FAILED tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
FAILED tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
2 failed, 54 passed in 2.14s
```
The two failing NODE IDs are in tools/dr_isl/PHASE_2C_FAILING_TESTS.txt. This does not assert that every failure signature is unchanged; their literal assertions are reproduced above.
Only two existing tests were edited, both in attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py: fixed-block diesel MW and additive-generation/residual assertions were replaced with D10 minimum/actual-source-accounting assertions and comments. No other existing test was edited.
## 2d.5 scenario evidence — incomplete
### Completed H checks
Sources: /tmp/DR-ISL-phase2d/H-after.log:1–6 and each named metrics/compact-hash JSON file:1. Comparisons below are read-only rechecks of retained files, not new runs.
| Scenario | Mode | Rep | Ticks | Curtailment MWh | Balance failures | Metrics equal Phase 2c | Compact equal Phase 2c |
|---|---|---:|---:|---:|---:|---|---|
| scenario-h1-k8s-ray-24h | baseline | 1 | 17280 | 187.690139189 | 0 | True | True |
| scenario-h1-k8s-ray-24h | informed | 1 | 17280 | 176.779572526 | 0 | True | True |
| scenario-h1-k8s-ray-24h | baseline | 2 | 17280 | 187.690139189 | 0 | True | True |
| scenario-h1-k8s-ray-24h | informed | 2 | 17280 | 176.779572526 | 0 | True | True |
| scenario-h2-slurm-24h | baseline | 1 | 17280 | 349.917690813 | 0 | True | True |
| scenario-h2-slurm-24h | informed | 1 | 17280 | 343.106291593 | 0 | True | True |

Full printed H rows, including physical and compact hashes:

```json
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "baseline", "repetition": 1, "status": "PASS", "curtailment": 187.690139189, "physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b", "balance_failures": 0, "compact": {"sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755", "tick_count": 17280}}
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "informed", "repetition": 1, "status": "PASS", "curtailment": 176.779572526, "physical_sha256": "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9", "balance_failures": 0, "compact": {"sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2", "tick_count": 17280}}
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "baseline", "repetition": 2, "status": "PASS", "curtailment": 187.690139189, "physical_sha256": "57a1370fd9d26d4bea4d2361f3ae2086aede264badba0c314095219d9741727b", "balance_failures": 0, "compact": {"sha256": "e0d9b888edb338c3796d64a26bd99ac6afb751b4c93bcf0e54b0a73165705755", "tick_count": 17280}}
{"scenario": "scenario-h1-k8s-ray-24h", "mode": "informed", "repetition": 2, "status": "PASS", "curtailment": 176.779572526, "physical_sha256": "60430dc7631204990acc39213cbcbeba8636b71a05d23c1a101c6c5faee71ef9", "balance_failures": 0, "compact": {"sha256": "19c2420ea61da37cb73fd2187495dad781f1e4de10766f988347894fe671c4e2", "tick_count": 17280}}
{"scenario": "scenario-h2-slurm-24h", "mode": "baseline", "repetition": 1, "status": "FAIL", "curtailment": 349.917690813, "physical_sha256": "f7c8de426e7b1b08650e0980e6ea26d38ce8bf03db2734cd21a18368f413b4a1", "balance_failures": 0, "compact": {"sha256": "8d0d3037dcaa712ccc34a5f744654af15b8654363911e63566f78467443e8b66", "tick_count": 17280}}
{"scenario": "scenario-h2-slurm-24h", "mode": "informed", "repetition": 1, "status": "PASS", "curtailment": 343.106291593, "physical_sha256": "3b40147d28ee89f1ec312b7f57f1c9f77e82c99bd7e6ee4447ff5384f951dbdf", "balance_failures": 0, "compact": {"sha256": "6ae0ce3d7a1b300cd4402fbd640abc67addb953b453075454c39bdefad8b0711", "tick_count": 17280}}
```
H1 both arms/repetitions completed and matched. H2 has only repetition 1 completed for both arms; repetition 2 was not finalized. H2 baseline status FAIL is preserved rather than relabeled PASS; the comparison to Phase 2c is exact in its completed record.
### Pre-change diesel baselines
Built from the immutable bb59f6e scratch worktree, with missing ignored source inputs copied separately (inventory: /tmp/DR-ISL-phase2d/before-ignored-source-copies.json). No tracked pre-change implementation file was overwritten. Runner file unchanged.
| Scenario | Rep | Ticks | Physical SHA-256 | Balance failures |
|---|---:|---:|---|---:|
| scenario-100mw-fuel-cell-bess-diesel | 1 | 252 | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b | 0 |
| scenario-100mw-fuel-cell-bess-diesel | 2 | 252 | 565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b | 0 |
| scenario-fc100-islanded-v2 | 1 | 264 | d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3 | 0 |
| scenario-fc100-islanded-v2 | 2 | 264 | d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3 | 0 |
| scenario-fc100-islanded-zero-hot-v2 | 1 | 264 | d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2 | 0 |
| scenario-fc100-islanded-zero-hot-v2 | 2 | 264 | d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2 | 0 |
| scenario-hybrid-ai-100mw-addendum-i | 1 | 120 | 4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518 | 0 |
| scenario-hybrid-ai-100mw-addendum-i | 2 | 120 | 4e9c1a040eeaa4952600225cef71fa7ab8088419a916184bad09ba45bc8bc518 | 0 |

### Pending / unavailable
- No-diesel after-change gate: NOT COMPLETED (the H sequence failed before it).
- Base-demo harness A/B, all requested fuel components/start timelines/SoC/refusals/forecast misses/comparison verdict: NOT RUN in this resumed verification sequence.
- Base-demo app-path comparison: NOT RUN.
- Diesel after-change metrics/hashes: NOT RUN; the large pre-change Slurm baseline did not finalize.
- Therefore no final before/after delta, app=harness verdict, or complete 2d.5 acceptance is claimed.
## 2d.6 full suite — NOT COMPLETED
Full-suite process exited 120 during scratch exhaustion. /tmp/DR-ISL-phase2d/full-suite.xml is 0 bytes. No reliable final pass/fail counts, added/removed/remaining set comparison, or final Phase 2d failing-ID list exists. Do not treat incomplete progress marks as counts.
Tail of /tmp/DR-ISL-phase2d/full-suite.log (the traceback itself was truncated by the write failure):

```

Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/pytest/__main__.py", line 9, in <module>
    raise SystemExit(_console_main())
                     ~~~~~~~~~~~~~^^
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/_pytest/config/__init__.py", line 253, in _console_main
    code = _main(prog=_get_prog_name(sys.argv))
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/_pytest/config/__init__.py", line 229, in _main
    ret: ExitCode | int = config.hook.pytest_cmdline_main(config=config)
                          ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^
  File "/home/runner/workspace/.pythonlibs/lib/python3.13/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
           ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/workspace/.pythonlibs/lib/python3.1
```
Known Phase 2c failures, for reference ONLY (not a Phase 2d result):

```
tests/test_13_3_frequency.py::TestI4DeliveryFaultMovesFrequency::test_I4_delivery_fault_causes_frequency_deviation
tests/test_13_5_criteria.py::TestR4PMinStable::test_R4_fields_present_on_turbine_config
tests/test_artifact_truncation.py::test_tc173_executor_run_validates_from_truncated_record_and_sidecar
tests/test_diesel_phase3.py::test_live_diesel_is_less_aggressive_than_disabled_before_curtailment
tests/test_diesel_setpoint_gap.py::test_hybrid_covered_demand_does_not_release_bess_reserve
tests/test_fabric_scenarios_e2e.py::test_fabric_scenario_names
tests/test_forecast_path.py::TestDispatchTruthfulness::test_B1a_islanded_delivery_fault_visible_in_delivery_channel
tests/test_fuel_cell_phase2.py::test_fixed_target_survives_a_step_load_and_output_remains_rate_limited
tests/test_gridley.py::test_gridley_logs_no_match_with_question_and_scenario_context
tests/test_gridley.py::test_gridley_retrieves_operator_knowledge_for_natural_variants
tests/test_gridley.py::test_gridley_uses_grounded_operator_benefits_fallback_without_claude
tests/test_kubernetes_scheduler_demo_scenario.py::test_catalogue_demo_constructs_phase_a_scheduler_and_has_real_queue_wait
tests/test_plane_separation.py::TestApiStaticLayer::test_api_gate_clean_api_passes
tests/test_scenario_fc100_islanded_v2.py::test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load
tests/test_unit_trip.py::test_tc84f_demo_20mw_contingency_state_changes_after_trip
```
## 2d.7 commits and changed files
No implementation or completion-report commit was made in this resumed attempt. Changes remain uncommitted; the implementation is not declared ready. Current HEAD is bb59f6eeccf6456c0bf838d4ee6331c0fc0524dd.
| File | Changed/new line ranges |
|---|---|
| .agents/memory/MEMORY.md | 71–71 |
| .agents/memory/diesel-dispatch-scope.md | 11–16 |
| .agents/memory/headless-export-storage.md | 1–10 (new) |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py | 1360–1360, 1448–1448, 1468–1468, 1475–1475, 1502–1506, 1525–1553, 1575–1577 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py | 115–115, 120–120, 187–188, 200–203, 233–233, 235–239, 241–242, 247–250, 375–383, 390–390 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py | 36–37, 69–74, 107–107, 122–122, 146–153, 158–159, 170–172, 174–174, 203–203 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py | 42–42 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py | 32–35, 786–786, 830–845, 852–852, 1696–1733, 1783–1812, 1815–1815, 1818–1818, 1820–1820, 1826–1826, 1828–1836, 1849–1849, 1883–1884, 1988–1988, 1990–1990, 2011–2011, 2051–2051, 2068–2074 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py | 138–142, 165–168, 170–173, 175–176 |
| attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py | 1–120 (new) |
| tools/dr_isl/PHASE_2D_REPORT.md | 1–882 |

## Full literal production and test diff

```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
index 59a2f49..1b2b974 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1357,6 +1357,7 @@ class DieselModule(AssetModule):
     _resuming_from_unloading: bool = False
     _resume_start_output_mw: float = 0.0
     _resume_elapsed_s: float = 0.0
+    _dispatch_ceiling_mw: Optional[float] = field(default=None, init=False)
 
     def __post_init__(self) -> None:
         if self.config.rated_mw <= 0.0:
@@ -1444,7 +1445,7 @@ class DieselModule(AssetModule):
         self._current_output_mw = 0.0
         self._resuming_from_unloading = False
 
-    def advance(self, sim_time: float, dt_seconds: float) -> None:
+    def advance(self, sim_time: float, dt_seconds: float, *, dispatch_controlled: bool = False) -> None:
         """Advance startup, synchronization output, or controlled unloading."""
         if dt_seconds < 0.0:
             raise ValueError("diesel dt_seconds must not be negative")
@@ -1464,12 +1465,14 @@ class DieselModule(AssetModule):
                     self._current_output_mw = (
                         self.config.rated_mw * self.config.f_block
                     )
+                    self._dispatch_ceiling_mw = self._current_output_mw
                 else:
                     self.state = DieselState.FAILED_START
                     self._current_output_mw = 0.0
             return
 
         if self.state == DieselState.SYNCHRONISED:
+            _delivered_before_advance = self._current_output_mw
             if self._resuming_from_unloading:
                 self._resume_elapsed_s += dt_seconds
                 duration = self.config.residual_ramp_s
@@ -1496,6 +1499,11 @@ class DieselModule(AssetModule):
                     base_mw
                     + (self.config.rated_mw - base_mw) * fraction
                 )
+            self._dispatch_ceiling_mw = self._current_output_mw
+            if dispatch_controlled:
+                # D10: advance machine capability, not delivered power.  A
+                # subsequent accepted stop must capture actual dispatched MW.
+                self._current_output_mw = _delivered_before_advance
             return
 
         if self.state == DieselState.UNLOADING:
@@ -1514,6 +1522,35 @@ class DieselModule(AssetModule):
     def output_mw(self) -> float:
         return self._current_output_mw
 
+    @property
+    def dispatch_floor_mw(self) -> float:
+        if self.state == DieselState.UNLOADING:
+            # User-approved D10 exception: preserve the tail below 30%.
+            return self.output_mw()
+        if self.state == DieselState.SYNCHRONISED:
+            # PROPOSED_HERE, D10: NFPA 110 §8.4.2 / Annex A test-load
+            # reference, used as a wet-stacking proxy for continuous load;
+            # this is a modelling minimum, not an NFPA run requirement.
+            return 0.30 * self.config.rated_mw
+        return 0.0
+
+    @property
+    def dispatch_ceiling_mw(self) -> float:
+        if self.state != DieselState.SYNCHRONISED:
+            return self.dispatch_floor_mw
+        available = (
+            self.output_mw() if self._dispatch_ceiling_mw is None
+            else self._dispatch_ceiling_mw
+        )
+        return max(self.dispatch_floor_mw, min(self.config.rated_mw, available))
+
+    def apply_dispatch_target(self, target_mw: float) -> None:
+        """D10: sole economic output application; unloading stays physical."""
+        if self.state == DieselState.SYNCHRONISED:
+            self._current_output_mw = max(
+                self.dispatch_floor_mw, min(self.dispatch_ceiling_mw, target_mw),
+            )
+
     def command_stop(self, sim_time: float) -> Optional[str]:
         """Begin controlled unloading, enforcing the diesel minimum run time."""
         self._last_known_sim_time = sim_time
@@ -1535,6 +1572,9 @@ class DieselModule(AssetModule):
         if self.state != DieselState.UNLOADING:
             return
         self.state = DieselState.SYNCHRONISED
+        # D10: resuming exposes the current tail, not a stale pre-unload
+        # capacity. advance() then raises capability on the existing ramp.
+        self._dispatch_ceiling_mw = self._current_output_mw
         self._resuming_from_unloading = True
         self._resume_start_output_mw = self._current_output_mw
         self._resume_elapsed_s = 0.0
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
index 2a63a3a..5e8e365 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
@@ -112,12 +112,12 @@ class DieselFleetCoordinator:
 
     @property
     def output_mw(self) -> float:
-        """Aggregate measured output from synchronised diesel units."""
+        """IMPL-ISL-14: aggregate every breaker-closed unit, including unloading."""
         return sum(
             (
                 unit.output_mw()
                 for unit in self.diesel_units
-                if unit.state == DieselState.SYNCHRONISED
+                if unit.is_on_bus
             ),
             0.0,
         )
@@ -184,6 +184,8 @@ class DieselFleetCoordinator:
         dt_seconds: float,
         *,
         success_overrides: Optional[Mapping[str, bool]] = None,
+        advance_units: bool = True,
+        consume_fuel: bool = True,
     ) -> DieselFleetSnapshot:
         """Advance units and coordinate one synthetic-gap fleet tick.
 
@@ -195,9 +197,10 @@ class DieselFleetCoordinator:
             raise ValueError("diesel fleet dt_seconds must not be negative")
         self._last_sim_time = sim_time
 
-        for unit in self.diesel_units:
-            unit.advance(sim_time, dt_seconds)
-        self._consume_fuel(dt_seconds)
+        if advance_units:
+            self.advance_units(sim_time, dt_seconds)
+        if consume_fuel:
+            self._consume_fuel(dt_seconds)
         self._complete_cooldown_if_ready(sim_time)
 
         if gap_mw > 0.0:
@@ -227,15 +230,24 @@ class DieselFleetCoordinator:
                     success_overrides or {},
                 )
         else:
-            if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
-                self._restore_elapsed_s += dt_seconds
-            elif any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units):
+            if any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units):
                 self._begin_unloading(sim_time)
+            # IMPL-ISL-15: a refused stop is not unloading/restoration time.
+            if (
+                any(unit.state == DieselState.UNLOADING for unit in self.diesel_units)
+                and not any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units)
+            ):
                 self._restore_elapsed_s += dt_seconds
+            else:
+                self._restore_elapsed_s = 0.0
 
             if (
                 self._restore_elapsed_s >= self.restore_hold_s
                 and any(unit.state == DieselState.UNLOADING for unit in self.diesel_units)
+                and all(
+                    unit._unload_elapsed_s >= unit.config.cooldown_s
+                    for unit in self.diesel_units if unit.state == DieselState.UNLOADING
+                )
             ):
                 self._finish_unloading(sim_time)
 
@@ -360,13 +372,22 @@ class DieselFleetCoordinator:
         self.insufficient_start_alert_fired = False
         self.insufficient_start_alerts.clear()
 
+    def advance_units(self, sim_time: float, dt_seconds: float, *, dispatch_controlled: bool = False) -> None:
+        """Advance lifecycle once; live D10 dispatch separately records delivery."""
+        for unit in self.diesel_units:
+            unit.advance(sim_time, dt_seconds, dispatch_controlled=dispatch_controlled)
+
+    def record_dispatch_fuel(self, dt_seconds: float) -> None:
+        """D10: use this interval's achieved, not pre-allocation, load fraction."""
+        self._consume_fuel(dt_seconds)
+
     def _consume_fuel(self, dt_seconds: float) -> None:
         dt_hours = dt_seconds / 3600.0
         if dt_hours <= 0.0:
             return
         consumed_gal = 0.0
         for unit in self.diesel_units:
-            if unit.state != DieselState.SYNCHRONISED:
+            if not unit.is_on_bus:  # IMPL-ISL-14: the unloading tail burns fuel.
                 continue
             if unit.config.rated_mw <= 0.0:
                 continue
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
index 587d1d5..fa69800 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
@@ -33,6 +33,8 @@ if TYPE_CHECKING:
 def compute_loading_setpoints(
     synchronised: "list[TurbineModule]",
     p_fleet: float,
+    *,
+    output_bounds: dict[str, tuple[float, float]] | None = None,
 ) -> tuple[list[float], float]:
     """Compute per-unit setpoints for units in A.  Pure — no side effects.
 
@@ -64,6 +66,12 @@ def compute_loading_setpoints(
         return [0.0] * len(synchronised), 0.0
 
     msl_i = [t.config.p_min_stable_frac * t.config.rated_mw for t in synchronised]
+    ceiling_i = [t.config.rated_mw for t in synchronised]
+    if output_bounds is not None:
+        # D10: the same sequential allocator can use this interval's physical
+        # ramp/policy envelope; no second turbine/diesel loading algorithm.
+        msl_i = [output_bounds[t.config.asset_id][0] for t in synchronised]
+        ceiling_i = [output_bounds[t.config.asset_id][1] for t in synchronised]
     sum_msl = sum(msl_i)
 
     # ── Sub-MSL: feasible band lower bound ───────────────────────────────────
@@ -96,7 +104,7 @@ def compute_loading_setpoints(
     for i, t in enumerate(synchronised):
         if _residual_s < 1e-9:
             break
-        _headroom_i   = t.config.rated_mw - msl_i[i]
+        _headroom_i   = ceiling_i[i] - msl_i[i]
         _fill_i       = min(_residual_s, _headroom_i)
         setpoints[i] += _fill_i
         _residual_s  -= _fill_i
@@ -111,7 +119,7 @@ def compute_loading_setpoints(
         unclamped: list[int] = []
         for i, t in enumerate(synchronised):
             lo = msl_i[i]
-            hi = t.config.rated_mw
+            hi = ceiling_i[i]
             if setpoints[i] < lo - 1e-9:
                 residual += lo - setpoints[i]   # positive: we under-allocated
                 setpoints[i] = lo
@@ -135,10 +143,20 @@ def compute_loading_setpoints(
 # Apply loading to SYNCHRONISED units (has side effects on output_mw)
 # ---------------------------------------------------------------------------
 
+def ramp_limited_output(turbine: "TurbineModule", target_mw: float, dt_seconds: float) -> float:
+    """Pure prediction of the existing loading step, also used to apply it."""
+    delta = target_mw - turbine.output_mw()
+    max_step = turbine.config.r_asset_mw_per_s * dt_seconds
+    step = max(-max_step, min(max_step, delta))
+    return turbine.output_mw() + step
+
+
 def apply_loading(
     synchronised: "list[TurbineModule]",
     p_fleet: float,
     dt_seconds: float,
+    *,
+    output_bounds: dict[str, tuple[float, float]] | None = None,
 ) -> float:
     """Compute setpoints and advance SYNCHRONISED unit outputs toward them.
 
@@ -149,12 +167,11 @@ def apply_loading(
     No stored state — calling twice with the same inputs is idempotent for the
     setpoint computation, though output_mw will advance twice.
     """
-    setpoints, sub_msl_surplus_mw = compute_loading_setpoints(synchronised, p_fleet)
+    setpoints, sub_msl_surplus_mw = compute_loading_setpoints(
+        synchronised, p_fleet, output_bounds=output_bounds,
+    )
     for t, sp in zip(synchronised, setpoints):
-        delta = sp - t.output_mw()
-        max_step = t.config.r_asset_mw_per_s * dt_seconds
-        step = max(-max_step, min(max_step, delta))
-        t.set_output(t.output_mw() + step)
+        t.set_output(ramp_limited_output(t, sp, dt_seconds))
     return sub_msl_surplus_mw
 
 
@@ -183,10 +200,7 @@ def apply_loading_targets(
                 float(targets_mw.get(turbine.config.asset_id, minimum)),
             ),
         )
-        delta = target - turbine.output_mw()
-        max_step = turbine.config.r_asset_mw_per_s * dt_seconds
-        step = max(-max_step, min(max_step, delta))
-        turbine.set_output(turbine.output_mw() + step)
+        turbine.set_output(ramp_limited_output(turbine, target, dt_seconds))
     return sub_msl_surplus_mw
 
 
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
index 8a7cf6c..adc2ab9 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
@@ -39,6 +39,7 @@ class PowerSourceType(str, Enum):
     BESS         = "bess"
     TURBINE      = "turbine"
     FUEL_CELL    = "fuel_cell"
+    DIESEL       = "diesel"
 
 
 class AuthorityTier(str, Enum):
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index d253eb5..9c7e8bb 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -29,7 +29,10 @@ from .asset_modules import (
     TurbineState,
 )
 from .fuel_cell_module import BlockFuelCellFleet, FuelCellModule
-from .loading import apply_loading, apply_loading_targets, ramp_capability
+from .loading import (
+    apply_loading, apply_loading_targets, compute_loading_setpoints,
+    ramp_capability, ramp_limited_output,
+)
 from .contingency import BessSnapshot, FuelCellSnapshot, PlantState, TurbineSnapshot, evaluate_contingency
 from .kube_demand import KubeDemandAgent, KubeGridState
 from .lead_time_observations import LeadTimeObservationRecorder
@@ -780,6 +783,7 @@ def _cost_ranked_dispatch_allocations(
     bess_available_mw: float,
     turbine_available_mw: float,
     fuel_cell_available_mw: float,
+    diesel_available_mw: float = 0.0,
 ) -> dict[str, float]:
     """Allocate discretionary demand using the shared marginal-cost ranking.
 
@@ -823,12 +827,29 @@ def _cost_ranked_dispatch_allocations(
             cost_basis_note="catalogue: fuel_cell_ppa_rate_mwh",
         ),
     ]
+    if diesel_available_mw > 0.0:
+        sources.append(_PowerSource(
+            source_id="diesel-fleet",
+            source_type=_PowerSourceType.DIESEL,
+            dispatchable=True,
+            counts_toward_reserve=True,
+            # PROPOSED_HERE, D10 fallback: no catalogue diesel price exists.
+            # Rank-only infinity (not a fuel price): diesel is last on rise /
+            # first on back-down because diesel fuel/MWh exceeds gas and FC.
+            # Source: approved DR-2026-10-20-ISLAND-COLLAPSE D10.
+            marginal_cost_mwh=math.inf,
+            response_latency_class=_ResponseLatencyClass.RAMP_LIMITED,
+            authority_tier=_AuthorityTier.AUTONOMOUS,
+            available_mw=diesel_available_mw,
+            cost_basis_note="D10: ranking-only last; no catalogue diesel price",
+        ))
     ranked = _PowerRanker().rank(sources).ranked_sources
     remaining_mw = max(0.0, demand_mw)
     allocations = {
         "bess-fleet": 0.0,
         "turbine-fleet": 0.0,
         "fuel-cell-fleet": 0.0,
+        "diesel-fleet": 0.0,
     }
     for source in ranked:
         if remaining_mw <= 1e-9:
@@ -1672,6 +1693,44 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         )
         for t in _truly_sync_units
     )
+    _diesel_loading_bounds = None
+    if state.diesel_units:
+        # D10: one ramp calculation/one sequential loading allocator. Preserve
+        # the existing controller/baseload policy as a physical floor, rather
+        # than allocating diesel against turbine MW already held by that policy.
+        _diesel_loading_bounds = {}
+        _policy_targets = dict(getattr(state, "_preload_targets_mw", {}) or {})
+        _explicit_policy_targets = bool(_policy_targets)
+        if not _policy_targets and _generation_baseload_active:
+            _base_setpoints, _ = compute_loading_setpoints(
+                _truly_sync_units,
+                max(0.0, _generation_baseload_target_mw - _uncontrolled_on_bus_mw - _msl_held_mw),
+            )
+            _policy_targets = {
+                t.config.asset_id: sp for t, sp in zip(_truly_sync_units, _base_setpoints)
+            }
+        for _t in _truly_sync_units:
+            _minimum = _t.config.p_min_stable_frac * _t.config.rated_mw
+            _lo = ramp_limited_output(_t, _minimum, dt_seconds)
+            _hi = ramp_limited_output(_t, _t.config.rated_mw, dt_seconds)
+            if _explicit_policy_targets or _t.config.asset_id in _policy_targets:
+                # apply_loading_targets holds omitted units at minimum too.
+                _target = max(_minimum, min(_t.config.rated_mw, _policy_targets.get(_t.config.asset_id, _minimum)))
+                _lo = ramp_limited_output(_t, _target, dt_seconds)
+                if _explicit_policy_targets or not _generation_peak_following:
+                    _hi = _lo
+            _diesel_loading_bounds[_t.config.asset_id] = (_lo, max(_lo, _hi))
+        _msl_held_mw = sum(
+            ramp_limited_output(t, t.config.p_min_stable_frac * t.config.rated_mw, dt_seconds)
+            for t in _unloading_units
+        )
+        _turbine_must_run_mw = (
+            _uncontrolled_on_bus_mw + _msl_held_mw
+            + sum(bounds[0] for bounds in _diesel_loading_bounds.values())
+        )
+        _turbine_incremental_available_mw = sum(
+            hi - lo for lo, hi in _diesel_loading_bounds.values()
+        )
     # Economic BESS availability must account for both the instantaneous power
     # ceiling and energy that can actually be delivered during this tick.  If
     # only the power ceiling is ranked, an empty/near-empty BESS reserves cheap
@@ -1721,18 +1780,60 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             min(_physical_ceiling_mw, _normal_energy_ceiling_mw)
         )
     _bess_available_mw = sum(_bess_normal_dispatch_ceilings_mw)
+    _diesel_dispatch_floor_mw = 0.0
+    _diesel_dispatch_headroom_mw = 0.0
+    if state.diesel_units:
+        # Approved D10 signal amendment: primary-only achievable shortfall,
+        # using this allocation's ramp/policy/AC-energy bounds, not the primary
+        # MW displaced by a live diesel minimum. This is a capacity diagnostic,
+        # not a second dispatch. START condition and every timer stay unchanged.
+        state.diesel_fleet_coordinator.advance_units(
+            sim_time, dt_seconds, dispatch_controlled=True,
+        )
+        _diesel_control_gap_mw = max(
+            0.0, p_dispatch_required_mw - fuel_cell_output_mw
+            - _turbine_must_run_mw - _turbine_incremental_available_mw
+            - _bess_available_mw,
+        )
+        state.diesel_fleet_coordinator.step(
+            gap_mw=_diesel_control_gap_mw, sim_time=sim_time,
+            dt_seconds=dt_seconds, advance_units=False, consume_fuel=False,
+        )
+        _diesel_dispatch_floor_mw = sum(t.dispatch_floor_mw for t in state.diesel_units)
+        _diesel_dispatch_headroom_mw = sum(
+            t.dispatch_ceiling_mw - t.dispatch_floor_mw for t in state.diesel_units
+        )
+    # D10: diesel must not be hidden behind the old primary-only dispatch
+    # intent ceiling. Keep the droop/frequency calculation unchanged; the one
+    # allocator's resource envelopes bound the full physical dispatch request.
+    _allocation_demand_mw = (
+        max(0.0, p_dispatch_required_mw + _droop_correction_mw)
+        if state.diesel_units else _p_dispatch_droop_mw
+    )
     _economic_demand_mw = max(
         0.0,
-        _p_dispatch_droop_mw
+        _allocation_demand_mw
         - fuel_cell_output_mw
         - _turbine_must_run_mw,
+        # diesel's synchronized minimum / immutable unloading tail is must-run.
     )
+    _economic_demand_mw = max(0.0, _economic_demand_mw - _diesel_dispatch_floor_mw)
     _economic_allocations = _cost_ranked_dispatch_allocations(
         _economic_demand_mw,
         bess_available_mw=_bess_available_mw,
         turbine_available_mw=_turbine_incremental_available_mw,
         fuel_cell_available_mw=0.0,
-    )
+        diesel_available_mw=_diesel_dispatch_headroom_mw,
+    )
+    _diesel_dispatch_target_mw = _diesel_dispatch_floor_mw + _economic_allocations["diesel-fleet"]
+    _diesel_extra_mw = _economic_allocations["diesel-fleet"]
+    for _diesel in state.diesel_units:
+        _extra = min(
+            _diesel_extra_mw,
+            _diesel.dispatch_ceiling_mw - _diesel.dispatch_floor_mw,
+        )
+        _diesel.apply_dispatch_target(_diesel.dispatch_floor_mw + _extra)
+        _diesel_extra_mw -= _extra
     _planned_bess_setpoint_mw = _economic_allocations["bess-fleet"]
     _thermal_dispatch_target_mw = (
         _turbine_must_run_mw + _economic_allocations["turbine-fleet"]
@@ -1745,7 +1846,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # replacing conventional turbine generation during a peak.
         _conventional_following_target_mw = max(
             0.0,
-            _p_dispatch_droop_mw - fuel_cell_output_mw,
+            _p_dispatch_droop_mw - fuel_cell_output_mw - _diesel_dispatch_target_mw,
         )
         if _generation_peak_following:
             _thermal_dispatch_target_mw = max(
@@ -1779,7 +1880,8 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         )
     else:
         _sub_msl_surplus_mw = apply_loading(
-            _truly_sync_units, _p_sync_fleet_mw, dt_seconds
+            _truly_sync_units, _p_sync_fleet_mw, dt_seconds,
+            output_bounds=_diesel_loading_bounds,
         )
 
     # Addendum H Phase 1: account for the completed interval after loading has
@@ -1883,7 +1985,9 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         p_dispatch_required_mw
         - _post_loading_turbine_output_mw
         - fuel_cell_output_mw,
+        # D10: the single plan has already credited current diesel delivery.
     )
+    _physical_bess_shortfall_mw = max(0.0, _physical_bess_shortfall_mw - _diesel_dispatch_target_mw)
     _emergency_release_authorized = False
     if _normal_bess_energy_exhausted:
         _grid_emergency_support_mw = (
@@ -1904,7 +2008,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
             # Diesel coordination runs after BESS arbitration.  Use measured
             # delivery from the preceding interval when deciding whether the
             # retained reserve must be released.
-            - state._prev_diesel_output_mw
+            - (0.0 if state.diesel_units else state._prev_diesel_output_mw)
             - _grid_emergency_support_mw,
         )
         _emergency_release_authorized = _emergency_gap_mw > 0.0
@@ -1944,7 +2048,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         # against an actual shortfall; negative values preserve its existing
         # surplus-absorption path so fixed FC overproduction charges the BESS.
         # tick() removes measured turbine output exactly once.
-        p_dispatch_required_mw - fuel_cell_output_mw,
+        p_dispatch_required_mw - fuel_cell_output_mw - _diesel_dispatch_target_mw,
         dt_seconds,
         bess_dispatch_target_mw=_effective_bess_setpoint_mw,
         bess_dispatch_ceilings_mw=_bess_dispatch_ceilings_mw,
@@ -1961,11 +2065,13 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
         - fuel_cell_output_mw,
     )
     diesel_enabled = bool(state.diesel_units)
-    _diesel_snapshot = state.diesel_fleet_coordinator.step(
-        gap_mw=_gap_before_diesel_mw if diesel_enabled else 0.0,
-        sim_time=sim_time,
-        dt_seconds=dt_seconds,
-    )
+    if diesel_enabled:
+        state.diesel_fleet_coordinator.record_dispatch_fuel(dt_seconds)
+        _diesel_snapshot = state.diesel_fleet_coordinator.snapshot()
+    else:
+        _diesel_snapshot = state.diesel_fleet_coordinator.step(
+            gap_mw=0.0, sim_time=sim_time, dt_seconds=dt_seconds,
+        )
     diesel_output_mw = float(_diesel_snapshot.output_mw)
     state._prev_diesel_output_mw = diesel_output_mw if diesel_enabled else 0.0
 
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
index 4fc360c..b40b63f 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
@@ -135,7 +135,11 @@ def test_live_diesel_output_reduces_remaining_gap_before_curtailment() -> None:
 
     expected_diesel_mw = enabled.sim_state.diesel_fleet_coordinator.output_mw
     assert disabled.sim_state.diesel_fleet_coordinator.output_mw == 0.0
-    assert expected_diesel_mw == pytest.approx(3.0)
+    # D10 supersedes the fixed-block 3 MW assertion: the live unit follows
+    # the shared allocation down to its synchronized minimum.
+    assert expected_diesel_mw == pytest.approx(
+        enabled.sim_state.diesel_units[0].dispatch_floor_mw,
+    )
     assert captured["gap_mw"] < disabled_tick.p_demand_mw
     assert captured["gap_mw"] == pytest.approx(
         max(
@@ -158,13 +162,18 @@ def test_live_diesel_output_increases_generation_and_balance_residual() -> None:
     enabled_tick = _tick(enabled.sim_state, tick_index=0)
     diesel_output_mw = enabled.sim_state.diesel_fleet_coordinator.output_mw
 
-    assert diesel_output_mw == pytest.approx(3.0)
-    assert enabled_tick.p_generation_mw - disabled_tick.p_generation_mw == pytest.approx(
-        diesel_output_mw
+    # D10: diesel is allocated with primary sources, no longer an additive
+    # fixed block that must increase generation/imbalance by exactly 3 MW.
+    assert diesel_output_mw == pytest.approx(
+        enabled.sim_state.diesel_units[0].dispatch_floor_mw,
     )
-    assert enabled_tick.p_imbalance_mw - disabled_tick.p_imbalance_mw == pytest.approx(
-        diesel_output_mw
+    assert enabled_tick.p_generation_mw == pytest.approx(
+        enabled_tick.turbine_output_mw + enabled_tick.bess_output_mw
+        + enabled_tick.fuel_cell_output_mw + enabled_tick.p_renewable_mw
+        + diesel_output_mw,
     )
+    assert enabled_tick.physical_balance.passed
+    assert disabled_tick.physical_balance.passed
 
 
 def test_live_diesel_is_less_aggressive_than_disabled_before_curtailment() -> None:
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py
new file mode 100644
index 0000000..399589c
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py
@@ -0,0 +1,120 @@
+"""TC-ISL-19..22, D10 + IMPL-ISL-14/15.
+
+PROPOSED_HERE diagnostic fixture magnitudes are synthetic, not new plant
+defaults. The runtime minimum's source/rationale is documented on the module.
+"""
+import copy
+import pytest
+
+from core.asset_modules import DieselModule
+from core.diesel_fleet import DieselFleetCoordinator
+from core.models import DieselConfig, DieselState
+from core.simulation_core import _cost_ranked_dispatch_allocations
+from runtime.scenario_factory import build_run_context_from_spec
+from tests.test_diesel_phase3 import _spec, _tick
+
+
+def _live_context():
+    spec = copy.deepcopy(_spec(diesel_enabled=True))
+    spec["diesel_units"][0].update(
+        rated_mw=20.0, f_block=1.0, min_run_s=900.0, cooldown_s=300.0,
+    )
+    spec["diesel_power_block"].update(
+        unit_rating_mw=20.0, target_capacity_mw=20.0,
+        min_run_s=900.0, cooldown_s=300.0,
+    )
+    spec["bess_units"][0].update(rated_mw=10.0, usable_mwh=20.0)
+    ctx = build_run_context_from_spec("D10-regression", spec)
+    unit = ctx.sim_state.diesel_units[0]
+    unit.state = DieselState.SYNCHRONISED
+    unit._current_output_mw = 20.0
+    unit._run_start_s = 0.0
+    ctx.sim_state.diesel_fleet_coordinator.episode_id = "D10-fixture"
+    return ctx
+
+
+def test_tc_isl_19_closing_gap_backs_diesel_down_before_curtailment():
+    ctx = _live_context()
+    ctx.sim_state.compute_floor_mw = 30.0
+    high = _tick(ctx.sim_state, 1)
+    ctx.sim_state.compute_floor_mw = 1.0
+    low = _tick(ctx.sim_state, 2)
+    assert high.diesel_output_mw > 6.0
+    assert low.diesel_output_mw == pytest.approx(6.0)
+    assert high.p_dispatch_curtailed_mw == pytest.approx(0.0)
+    assert low.p_dispatch_curtailed_mw == pytest.approx(0.0)
+    assert high.physical_balance.passed
+    assert low.physical_balance.passed
+
+
+def test_tc_isl_20_shared_merit_order_rising_and_falling():
+    for demand in (20.0, 40.0, 60.0, 80.0, 60.0, 40.0, 20.0):
+        result = _cost_ranked_dispatch_allocations(
+            demand, bess_available_mw=10.0, turbine_available_mw=20.0,
+            fuel_cell_available_mw=30.0, diesel_available_mw=40.0,
+        )
+        assert result["bess-fleet"] == min(10.0, demand)
+        assert result["turbine-fleet"] == min(20.0, max(0.0, demand - 10.0))
+        assert result["fuel-cell-fleet"] == min(30.0, max(0.0, demand - 30.0))
+        assert result["diesel-fleet"] == max(0.0, demand - 60.0)
+    # Reversing a falling-demand unload must not expose stale rated capacity.
+    unit = DieselModule(DieselConfig(asset_id="resume", rated_mw=20.0, role="primary"))
+    unit.state = DieselState.UNLOADING
+    unit._current_output_mw = 2.0
+    unit._dispatch_ceiling_mw = 20.0
+    unit.resume_from_unloading()
+    unit.apply_dispatch_target(20.0)
+    assert unit.output_mw() == 6.0
+    # Explicit targets hold omitted GTs at minimum; they are not available
+    # primary headroom for the coordinator's dispatch-aware gap.
+    ctx = _live_context()
+    ctx.sim_state.compute_floor_mw = 20.0
+    ctx.sim_state._preload_targets_mw = {"not-on-bus": 0.0}
+    constrained = _tick(ctx.sim_state, 1)
+    assert constrained.turbine_output_mw == 0.0
+    assert constrained.diesel_output_mw > 6.0
+    assert constrained.p_unserved_mw == pytest.approx(0.0)
+    assert constrained.physical_balance.passed
+
+
+def test_tc_isl_21_unloading_power_fuel_and_physical_balance():
+    ctx = _live_context()
+    state = ctx.sim_state
+    state.compute_floor_mw = 1.0
+    unit = state.diesel_units[0]
+    unit.state = DieselState.UNLOADING
+    unit._current_output_mw = 6.0
+    unit._unload_start_output_mw = 6.0
+    before = state.diesel_fleet_coordinator.fuel_remaining_gal
+    tick = _tick(state, 1)
+    assert unit.is_on_bus
+    assert tick.diesel_output_mw == pytest.approx(5.9)
+    assert state.diesel_fleet_coordinator.output_mw == pytest.approx(5.9)
+    assert before - state.diesel_fleet_coordinator.fuel_remaining_gal == pytest.approx(
+        5.9 / 20.0 * 230.0 * 5.0 / 3600.0,
+    )
+    assert tick.physical_balance.passed
+
+
+def test_tc_isl_22_refused_stop_does_not_credit_hold_or_shorten_ramp():
+    unit = DieselModule(DieselConfig(
+        asset_id="timing-fixture", rated_mw=20.0, role="primary", f_block=1.0,
+    ))
+    unit.state = DieselState.SYNCHRONISED
+    unit._current_output_mw = 20.0
+    unit._run_start_s = 0.0
+    coordinator = DieselFleetCoordinator([unit])
+    coordinator.episode_id = "timing-fixture"
+    for t in (5.0, 100.0, 895.0):
+        coordinator.step(gap_mw=0.0, sim_time=t, dt_seconds=5.0)
+        assert coordinator._restore_elapsed_s == 0.0
+        assert unit.state == DieselState.SYNCHRONISED
+    coordinator.step(gap_mw=0.0, sim_time=900.0, dt_seconds=5.0)
+    assert unit.state == DieselState.UNLOADING
+    for elapsed in range(5, 300, 5):
+        coordinator.step(gap_mw=0.0, sim_time=900.0 + elapsed, dt_seconds=5.0)
+        assert unit.state == DieselState.UNLOADING
+        assert unit.output_mw() == pytest.approx(20.0 * (1.0 - elapsed / 300.0))
+    coordinator.step(gap_mw=0.0, sim_time=1200.0, dt_seconds=5.0)
+    assert unit.state == DieselState.OFFLINE
+    assert unit.output_mw() == 0.0
```
## Git status at STOP (including ignored new test)

```
 M .agents/memory/MEMORY.md
 M .agents/memory/diesel-dispatch-scope.md
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/diesel_fleet.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/loading.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/power_source_priority.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
 M attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_diesel_phase3.py
 M tools/dr_isl/PHASE_2D_REPORT.md
?? .agents/memory/headless-export-storage.md
attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_diesel_dispatch.py
```

## Resumption requirement
A disk-backed output location needs approval: /tmp has a separate 4 GiB limit. No model/scenario/control change is proposed to address the storage failure. Remaining verification must finish before any implementation commit or Phase 3.
