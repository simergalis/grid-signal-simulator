# DR-2026-10-20-ISLAND-COLLAPSE — Phase 4 reserve STOP report

Date: 2026-10-22.
**STOP at 4.5. Phase 4 is not validated or implemented on the main branch.**

Base application commit: `ae49aaab89564ccf2ef42d505e021641484d0d3a`.
Pre-implementation/report-only HEAD: `17db503763fd1b500502c7bcd6f68b9832b83a26`.
Candidate stash: `85595a8189a7adc9745b5fd326196f6325b0e275` (`stash@{0}` at capture).
P = `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

## Evidence retention limitation

The background full-suite wrapper exited with code **2**. Its persisted failing-ID list contains **16** IDs: **1 added, 0 removed, 15 remaining** relative to `tools/dr_isl/HOUSEKEEPING_FAILING_TESTS.txt`.
After that exit, `/tmp/DR-ISL-phase4-reserve/` and the background-shell log paths no longer existed. All three configured workflows were reported not started. The cause of that disappearance is not established by retained evidence. I failed to persist the full temporary results before this loss.
Final pytest pass/skip/xfail counts and the final XML cannot be verified from retained files. The last printed incremental XML observation was **2,223 test cases, 16 failures, 0 errors, 26 skipped entries**. This is an observation, not a certified final pytest summary; 26 includes entries that pytest may classify as xfail.
R1–R4 values below are reconstructed from tool output already printed during this session. Missing H hashes, complete 27-metric payloads, requested-window files, and raw run artifacts have **not** been recreated or presented as retained evidence. No simulations or tests were rerun after the STOP.

## 4.0 — Design and approved preflight decisions

Design: `tools/dr_isl/PHASE_4_RESERVE_DESIGN.md` (base-source line references are explicitly labelled there). This is D2-r/D1-b, not the separate IMPL-ISL-17 start-event work.
- Track the existing `P/mcp_server/__main__.py`, not a new `main.py`: approved; tracking not reached.
- STARTING turbines use their remaining startup countdown: approved and used in the candidate.
- D9b winning-term attribution may identify D2-r: approved; warning trigger/code and no-cap/no-reject policy unchanged.

## 4.1–4.2 — Candidate changes (now stashed)

Line references in this section refer to the **candidate in the stash**, not the restored main-tree source. Full literal diff is in the appendix and `tools/dr_isl/PHASE_4_CANDIDATE_EVIDENCE.patch`.

| Candidate file | Added/changed lines | Purpose |
|---|---|---|
| `P/core/asset_modules.py` | 1069–1088, 1106–1108 | Pure shared thermal/start-duration query; command_start uses the same timing. |
| `P/core/dispatch.py` | 383–388, 538–611 | Extend the one existing floor to max(depth, diesel, D2-r); eligibility/countdown basis and metadata history. |
| `P/core/simulation_core.py` | 354, 390–398, 998, 2036–2054, 2128 | Live GF block-FC callback, clock, and one conditional release-floor vector used upstream/downstream. |
| `P/runtime/build_warnings.py` | 37–41 | Attribution only, from the single floor result. |
| `P/runtime/scenario_factory.py` | 1952–1958 | Live basis/history references in RunContext metadata. |
| `P/tests/test_dr_isl_phase4_reserve.py` | 1–208 | Eleven cases for TC-ISL-01–03. |

The AST comparison of `start_eligibility` against base printed **True** (identical). There were no scenario/API/commitment/diesel/advisory/frequency/protection edits. The thermal timing body was factored, not retuned. See the full diff for scope, rather than treating changed physics trajectories as unchanged outputs.

## 4.3 — Focused tests

- TC-ISL-01–03 collision scan: only the new reserve test file matched those IDs.
- New tests: **11 passed in 0.92 s**.
- Existing reserve reconciliation, grid-forming viability, Phase 2c, and Addendum G Stage 3 focused files: **33 passed, 1 warning in 7.00 s**.
- Existing shared start-eligibility/hot-standby-veto files: **6 passed in 1.65 s**.
- Total final focused cases: **50 passed**. No existing tests were changed.

Printed values from the new tests:
```text
no-diesel bridge: floor=4.166666666666667 MWh; unit=gt-reserve; wait=0; start=600 s; cold
diesel winning floor: 10.0 MWh
no restartable unit: 0 MWh; basis="no restartable synchronous unit"
STARTING remaining 120 s: floor=0.8333333333333334 MWh
grid-tied / nonforming BESS / live GF block FC: D2-r term=0
sole-GF release fixture: stored=4.166666666666667 MWh; BESS output=0; unserved=10 MW; balance=True
on-bus GT or diesel fixture: stored=4.153613215609007 MWh; BESS output=9 MW; unserved=0; balance=True
```

Test-authoring transparency: the initial new-test draft had 8 pass/3 fail, and the next had 9 pass/2 fail because synthetic diesel/FC fixtures were incomplete for the canonical schema/delivering-state requirements. Only those new fixtures were completed; production policy was not adjusted to satisfy them.

## 4.4 R1 — Template and S10

“First floor” below means first stored-energy observation at/below the current normal floor. A floor can jump upward; this is not necessarily an energy-depletion/equality crossing. Frequency windows begin at each version’s own first-floor time and therefore are not fixed-time windows shared between versions.

| Scenario/version | Ticks | Collapse | Min SoC | Normal floor min/max MWh | First floor tick / seconds | Min Hz next 120 s | Run min/max Hz | Unserved MWh |
|---|---:|---|---:|---|---|---:|---|---:|
| demo-islanded-ramp / base | 2160 | no | 0 | 0 / 0 | 771 / 3855 | 56.30124604916138 | -127.48961154607643 / 60 | 0.7984763561509628 |
| demo-islanded-ramp / candidate | 2160 | no | 0.45166506501035325 | 0.0625 / 7.5 | 312 / 1560 | 59.98901877366516 | -127.48961154607643 / 60 | 0.785895723386723 |
| S10_mit_supercloud_2021-08-11 / base | 17280 | no | 0 | 0 / 0 | 2372 / 11860 | 54.48350997809083 | -729.1075118080669 / 998.9330534505464 | 10.600341682490331 |
| S10_mit_supercloud_2021-08-11 / candidate | 17280 | no | 0 | 0 / 14.9375 | 1012 / 5060 | 79.88266332350686 | -729.1075118080669 / 998.9330534505464 | 8.4639919161834 |

The S10 base 120-second-window value observed here was **54.48350997809083 Hz**, not the **55.68 Hz** quoted in the request. This discrepancy was not tuned away or investigated with more runs.
S10’s maximum normal floor **14.9375 MWh** exceeds its **14 MWh** usable capacity. No floor was capped or rejected. D9b remains the existing **build-time** warning; the clarification authorized attribution only, not a new runtime warning lifecycle.
Run completion is **not** frequency-safety validation: the unprotected whole-run ranges remain nonphysical. No frequency/protection correction was attempted.

Candidate below-normal-target observations: template **1849**, of which **1845** were not discharging; S10 **2713**, of which **2022** were not discharging. Positive below-floor discharge outside D1-b permission: **0** in both.
Template first-floor basis: turbine-4, eligibility wait **0 s**, cold startup **600 s**, D2-r **7.5 MWh**. At tick 312 the physical release floor was **0**, with a synchronous source on bus.
S10 first-floor basis: turbine-4, min-down wait **895 s**, current hot startup **300 s**, D2-r **14.9375 MWh**. At tick 1012 BESS output was **−18 MW** (charging), with physical floor **14.9375 MWh**.

TC-ISL-04 intended completion/load-coverage outcome: observed. Template candidate did not deplete (minimum SoC **0.45166506501035325**), so literal post-depletion recovery is **not exercised**. The after-floor diagnostic reached nominal-band/load coverage at tick **315**, **1575 s**, **15 s** after first normal-floor onset; frequency **59.991642290429624 Hz**, GT **43.969697761438795 MW**, BESS **0 MW**, unserved **0**. Diagnostic band: PROPOSED_HERE **±0.1 Hz**, test-only, not a protection change.
TC-ISL-05 completion: **PASS**, **17280 ticks / 86400 s**, no collapse. No frequency-safety pass is implied.

Observer correction transparency: initial scratch STOP_R1 outputs incorrectly treated below-target holdings as new discharges. The observer was corrected to test positive discharge, and synthetic holding / forbidden-discharge / permitted-release cases passed. The template physical hash was unchanged by that observer correction; simulator policy/parameters were not changed in response. Raw erroneous and corrected scratch outputs were among the lost temporary files.

R1 physical SHA-256 values:
```text
demo-islanded-ramp base fe798e4292b478ef3f6e25d67e4e22123867f51e49b991ac13981ecaa8114b2a
demo-islanded-ramp candidate f49f71f1573f1f9a22fff6d560eb5a25a380e4088ecccbe12cf6a560964f822a
S10_mit_supercloud_2021-08-11 base 4370c9ebfbfc90d2812cad93285c9749645974502508e8188c3567eb3e60d34d
S10_mit_supercloud_2021-08-11 candidate 8ba0dec0459ca09b9df4ea6fa17bd72fa16038220f425b0a8dd499bfa87557ab
```

## R2 — Advisory timing

| Scenario | First advisory tick / s / reason | First normal-floor onset tick / s | First positive retained physical guard while at/below target tick / s |
|---|---|---|---|
| template | 6 / 30 / turbine_catchup | 312 / 1560 | 315 / 1575 |
| S10 | 118 / 590 / turbine_catchup | 1012 / 5060 | 1012 / 5060 |

The catch-up advisory preceded both observations. Normal-floor onset and the actual downstream guard are distinguished: D1-b can temporarily set the latter to zero. A positive guard while charging does not prove that a positive discharge command was blocked on that tick. No bridging-floor-specific first alert was recorded by the observer. Advisory code was unchanged.

## R3 — Six regression scenarios

All six base-reference checks and paired candidate checks passed; physical hashes were identical, with observed maximum D2-r term **0.0 MWh** in each.

| Scenario | Base = candidate physical SHA-256 |
|---|---|
| scenario-equinix-sj-1 | `328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84` |
| scenario-turbine-01 | `006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a` |
| scenario-hybrid-ai-100mw-addendum-i | `9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a` |
| scenario-100mw-fuel-cell-bess-diesel | `565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b` |
| scenario-fc100-islanded-v2 | `d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3` |
| scenario-fc100-islanded-zero-hot-v2 | `d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2` |

## R4 — Protected records

Observed ordered gate results: base demo both arms passed the exact paired physical/compact/27-key metric comparisons and the nine-decimal production checks. H1-24h and H2-24h, both arms, **two repetitions per arm**, passed physical/compact/27-key metric identity and repeatability. Base and candidate compare_runs were **PASS** for base demo, H1 and H2.
H2 reconciliation is included in the unchanged metric projection; the accepted ae49aaa reference is **11/11**. The exact per-run reconciliation payload, individual H hashes and all metric objects were lost, so this report does not substitute an invented metric-by-metric dump for them.
Base-demo D2-r maximum observed term was **24.895833333333332 MWh**, without a protected physical/metric change.

| Arm | Curtailment MWh | Turbine fuel MMBtu | Unserved MWh | Peak unserved MW |
|---|---:|---:|---:|---:|
| baseline | 8.136511735 | 714.363019086 | 0.351692658 | 22.309362466 |
| informed | 5.278943188 | 665.398247704 | 0.020719074 | 7.52325057 |

These are the production-reference values at the tested nine-decimal precision, not claimed full-precision recovered outputs. No protected-record change was observed before the scratch loss.

## 4.5 — Full-suite STOP

Final persisted failing IDs: `tools/dr_isl/PHASE_4_FAILING_TESTS.txt`.
Comparison: **16 failed IDs; 1 added; 0 removed; 15 remaining**.
Added node:
```text
tests/test_gpu_load_profile.py::test_gpu_load_profile
```
Literal captured failure:
```text
assert abs(frac - expected_frac) < TOLERANCE
AssertionError: [FAIL-A] phase-2 sim_t=720.0s: gpu_load_fraction=1.0 expected 0.5
assert 0.5 < 1e-06
 + where 0.5 = abs((1.0 - 0.5))
tests/test_gpu_load_profile.py:169: AssertionError
called from tests/test_gpu_load_profile.py:284
```
The captured test uses HTTP POST /runs and GET latest-tick. No base/candidate isolation rerun was performed after the added-failure gate. Its causal classification is **unresolved**, not proven to be a D2-r regression, stale test, or race.

The suite was launched without intentional cancellation; its wrapper exited 2 after writing the failing-ID list. Final pytest counts/XML are unavailable after scratch loss. Last observed incremental XML: 2223 cases / 16 failures / 0 errors / 26 skipped entries. A final passed count is deliberately **not asserted**.

Remaining pre-existing IDs:
```text
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

## 4.6 — Tracking

**Not performed**, because 4.5 stopped the phase. No tracking commit and no no-content-change claim was made for the five files. The approved target remains existing `mcp_server/__main__.py`; no `main.py` was created. `gridsignal.db` was not added.

## 4.7 — Restoration, commits, scope

- Candidate retained in stash `85595a8189a7adc9745b5fd326196f6325b0e275`.
- `git diff ae49aaab89564ccf2ef42d505e021641484d0d3a -- P/core P/runtime P/api P/tests` returned empty after the stash.
- No Phase 4 implementation or test/tracking commit was made. Only a report/evidence/memory-documentation commit follows this report; its hash must be obtained from git / the final response to avoid embedding its own hash.
- No automatic implementation checkpoint occurred during this candidate: pre-stash HEAD remained report-only 17db503.
- The stopped GridSignal web workflow was restarted **after restoring base source**. Startup completed and GET / returned **200**. Preview showed the operator sign-in page; unauthenticated 401 was logged. No sign-in or new simulation was performed for that check.
- No publish, deployment, push, Phase 5, scenario JSON edit, or application fix for the GPU failure.

Durable evidence: `PHASE_4_RESERVE_EVIDENCE.json`, `PHASE_4_CANDIDATE_EVIDENCE.patch`, `PHASE_4_FAILING_TESTS.txt` in `tools/dr_isl/`. The JSON includes candidate file hashes, exact hunk ranges, the identical-predicate AST result, and explicit missing-evidence fields.
Documentation also retains approved countdown semantics and the two validation lessons (dynamic-floor holdings are not new discharge; bounded results must be flushed durably before continuing).

## Appendix — Literal candidate diff against application base

This is evidence of the **unvalidated, stashed** candidate, not main-tree application changes.

```diff
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
index 11ec12b..c463817 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/asset_modules.py
@@ -1066,6 +1066,26 @@ class TurbineModule(AssetModule):
                 return False, "min_down"
         return True, "eligible"
 
+    def start_timing_at(self, sim_time: float) -> tuple[ThermalState, float]:
+        """DR D2-r: preview the existing start timing, without starting a unit."""
+        if math.isnan(self._last_sync_stop_s):
+            thermal = self.config.initial_thermal_state
+        else:
+            elapsed_offline = sim_time - self._last_sync_stop_s
+            if elapsed_offline < self.config.hot_threshold_s:
+                thermal = ThermalState.HOT
+            elif elapsed_offline < self.config.warm_threshold_s:
+                thermal = ThermalState.WARM
+            else:
+                thermal = ThermalState.COLD
+        if thermal == ThermalState.HOT:
+            duration = self.config.hot_start_s
+        elif thermal == ThermalState.WARM:
+            duration = self.config.warm_start_s
+        else:
+            duration = self.config.cold_start_s
+        return thermal, duration
+
     def command_start(self, sim_time: float) -> None:
         """Transition OFFLINE → STARTING.  Phase 2 commitment-logic entry point.
 
@@ -1083,29 +1103,9 @@ class TurbineModule(AssetModule):
         if not self.start_eligibility(sim_time)[0]:
             return
 
-        # Determine thermal state from time offline since last synchronisation.
-        # First start (never stopped): use config.initial_thermal_state so the
-        # scenario-specified tier (hot/warm/cold) is honoured rather than always
-        # defaulting to the conservative cold path.  Subsequent restarts continue
-        # to use the elapsed-time classifier (time since last sync stop).
-        if math.isnan(self._last_sync_stop_s):
-            self._thermal_state = self.config.initial_thermal_state
-        else:
-            elapsed_offline = sim_time - self._last_sync_stop_s
-            if elapsed_offline < self.config.hot_threshold_s:
-                self._thermal_state = ThermalState.HOT
-            elif elapsed_offline < self.config.warm_threshold_s:
-                self._thermal_state = ThermalState.WARM
-            else:
-                self._thermal_state = ThermalState.COLD
-
-        # Start duration from config — no literals in state machine
-        if self._thermal_state == ThermalState.HOT:
-            self._time_to_online_s = self.config.hot_start_s
-        elif self._thermal_state == ThermalState.WARM:
-            self._time_to_online_s = self.config.warm_start_s
-        else:
-            self._time_to_online_s = self.config.cold_start_s
+        # DR D2-r: share exactly the existing thermal timing with the reserve
+        # query; neither start eligibility nor start physics is changed.
+        self._thermal_state, self._time_to_online_s = self.start_timing_at(sim_time)
 
         self._start_phase = "purge"
         self.state = TurbineState.STARTING
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
index 83b7d3e..5392cc9 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/dispatch.py
@@ -380,6 +380,12 @@ class DispatchArbitrator:
         self.successful_start_observer: Optional[
             Callable[[TurbineModule, float, TurbineState, float, float], None]
         ] = None
+        # DR D2-r: build epoch is zero; evaluate_tick supplies the live clock.
+        # PROPOSED_HERE: metadata names only, not new physical calibration.
+        self.reserve_sim_time_s = 0.0
+        self.live_grid_forming_fc: Optional[Callable[[], bool]] = None
+        self.reserve_floor_basis: dict[str, dict] = {}
+        self.reserve_floor_history: list[dict] = []
 
     # ------------------------------------------------------------------
     # Fleet allocation helper (Step 3 Item 4)
@@ -529,7 +535,80 @@ class DispatchArbitrator:
             if normal_depth_fraction > 0.0
             else 0.0
         )
-        return max(depth_reserve_mwh, diesel_floor_mwh)
+        # DR-2026-10-20-ISLAND-COLLAPSE D2-r / IMPL-ISL-2. This is the
+        # single floor formula for normal dispatch, physical guard and D9b.
+        applicable = (
+            self.site.island_mode == IslandMode.ISLANDED
+            and bess.config.grid_forming
+            and not (self.live_grid_forming_fc and self.live_grid_forming_fc())
+        )
+        bridge = []
+        if applicable:
+            for unit in self.turbines:
+                if unit.is_on_bus:
+                    continue
+                eligible, reason = unit.start_eligibility(self.reserve_sim_time_s)
+                if unit.state == TurbineState.STARTING:
+                    # Approved clarification: bridge the remaining countdown;
+                    # do not add another full start to an in-progress start.
+                    wait, duration = 0.0, unit.unit_availability(
+                        self.reserve_sim_time_s
+                    ).time_to_online_s
+                    if reason == "hot_standby":
+                        continue
+                    thermal = unit.thermal_state
+                elif eligible or reason == "min_down":
+                    # The predicate owns every guard. The returned min_down
+                    # reason authorizes reading its deadline, not rechecking it.
+                    wait = (
+                        max(0.0, unit._stop_time_s + unit.config.t_min_down_s
+                            - self.reserve_sim_time_s)
+                        if reason == "min_down" else 0.0
+                    )
+                    thermal, duration = unit.start_timing_at(self.reserve_sim_time_s)
+                else:
+                    continue
+                bridge.append((wait + duration, unit.config.asset_id,
+                               wait, duration, thermal.value, reason))
+        chosen = min(bridge) if bridge else None
+        bridge_s = chosen[0] if chosen is not None else 0.0
+        d2r_term_mwh = (
+            MARGIN_MULTIPLIER * bess.config.rated_mw * bridge_s / 3600.0
+        )
+        floor_mwh = max(depth_reserve_mwh, diesel_floor_mwh, d2r_term_mwh)
+        # Preserve diesel tie precedence in the existing warning attribution.
+        winning_term = max(
+            (("diesel_floor", diesel_floor_mwh),
+             ("depth_reserve", depth_reserve_mwh),
+             ("d2r", d2r_term_mwh)),
+            key=lambda term: term[1],
+        )[0]
+        basis = {
+            "bess_id": bess.config.asset_id,
+            "floor_mwh": floor_mwh,
+            "depth_reserve_mwh": depth_reserve_mwh,
+            "diesel_floor_mwh": diesel_floor_mwh,
+            "d2r_term_mwh": d2r_term_mwh,
+            "winning_term": winning_term,
+            "basis": (
+                "restartable synchronous unit" if chosen is not None
+                else "no restartable synchronous unit" if applicable
+                else "D2-r not applicable"
+            ),
+            "unit_id": chosen[1] if chosen is not None else None,
+            "eligibility_wait_s": chosen[2] if chosen is not None else None,
+            "start_duration_s": chosen[3] if chosen is not None else None,
+            "thermal_state": chosen[4] if chosen is not None else None,
+            "eligibility_reason": chosen[5] if chosen is not None else None,
+        }
+        previous = self.reserve_floor_basis.get(bess.config.asset_id)
+        self.reserve_floor_basis[bess.config.asset_id] = basis
+        if winning_term == "d2r" and basis != previous:
+            # Retain changes in a winning basis, not duplicate calls/tick data.
+            self.reserve_floor_history.append(
+                dict(basis, sim_time_s=self.reserve_sim_time_s)
+            )
+        return floor_mwh
 
     def stage_for_predicted_step(
         self, delta_p_mw: float, dt_lead_seconds: float, sim_time: float
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
index a7649e0..caf5216 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/core/simulation_core.py
@@ -351,6 +351,7 @@ class SimulationState:
         self.arbitrator.pending_start = self._pending_start
         # DR-2026-10-22-ISL-P4: the adapter resolves the audit sink at event time.
         self.arbitrator.successful_start_observer = self._observe_predicted_step_start
+        self.arbitrator.live_grid_forming_fc = self._reserve_has_live_gf_fc
         # Step 10: curtailment ladder and pre-staging engine.
         self.curtailment_ladder = CurtailmentLadder()
         if self.site.pre_staging_config is not None:
@@ -386,6 +387,15 @@ class SimulationState:
             self._job_owner_index[signal.job_id] = len(self._job_owner_index) % len(self.gpu_modules)
         return self.gpu_modules[self._job_owner_index[signal.job_id]]
 
+    def _reserve_has_live_gf_fc(self) -> bool:
+        """D2-r: same delivering block-FC definition as the viability check."""
+        # PROPOSED_HERE: reuse the existing viability delivery epsilon (1e-9
+        # MW), rather than introduce a different definition of a live former.
+        return isinstance(self.fuel_cell_module, BlockFuelCellFleet) and any(
+            array.config.grid_forming and array.output_mw() > 1e-9
+            for array in self.fuel_cell_module.arrays
+        )
+
     def _observe_predicted_step_start(
         self,
         turbine: TurbineModule,
@@ -985,6 +995,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # TickResult so the persistence layer can record both clocks per tick.
     sim_time = clock.sim_time
     dt_seconds = clock.dt_seconds
+    state.arbitrator.reserve_sim_time_s = sim_time
 
     # 0. Kubernetes demand agent — must run BEFORE gpu.advance() so demand
     #    changes driven by the scheduler take effect in the current tick's power
@@ -2022,9 +2033,25 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     _post_loading_turbine_output_mw = sum(
         t.output_mw() for t in state.turbines if t.is_on_bus
     )
+    # DR D1-b: only the new D2-r term is hard while no synchronous machine
+    # is on bus. Preserve legacy release where D2-r is not applicable.
+    _reserve_sync_on_bus = any(t.is_on_bus for t in state.turbines) or any(
+        unit.is_on_bus for unit in state.diesel_units
+    )
+    _bess_release_floors_mwh = [
+        0.0 if _reserve_sync_on_bus else
+        state.arbitrator.reserve_floor_basis[b.config.asset_id]["d2r_term_mwh"]
+        for b in state.bess_units
+    ]
     _reserve_bess_ceilings_mw = [
-        max(0.0, physical - normal)
-        for physical, normal in zip(
+        max(0.0, min(
+            physical,
+            b.deliverable_energy_mwh(hard_floor) / (dt_seconds / 3600.0)
+            if dt_seconds > 0.0 else physical,
+        ) - normal)
+        for b, hard_floor, physical, normal in zip(
+            state.bess_units,
+            _bess_release_floors_mwh,
             _bess_physical_ceilings_mw,
             _bess_normal_dispatch_ceilings_mw,
         )
@@ -2098,7 +2125,7 @@ def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
     # authorizes that retained energy for this tick only; no other contingency
     # state is introduced here.
     _bess_soc_floors_mwh = (
-        [0.0] * len(_bess_reconciled_reserve_mwh)
+        _bess_release_floors_mwh
         if _emergency_release_authorized
         else _bess_reconciled_reserve_mwh
     )
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
index bb24105..21988c1 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/build_warnings.py
@@ -34,7 +34,11 @@ def reserve_capacity_warnings(state) -> list[dict]:
             "bess_id": bess.config.asset_id,
             "floor_mwh": floor,
             "usable_mwh": bess.config.usable_mwh,
-            "winning_term": "diesel_floor" if diesel_term >= floor else "depth_reserve",
+            # Approved Phase 4 clarification: attribution only; D9b's trigger,
+            # warning code and no-cap/no-reject behavior remain unchanged.
+            "winning_term": arbitrator.reserve_floor_basis[
+                bess.config.asset_id
+            ]["winning_term"],
             "diesel_units": timings,
             "diesel_worst_case_sync_s": arbitrator.diesel_worst_case_sync_s(),
         }
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
index 226dcfd..73d675f 100644
--- a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/scenario_factory.py
@@ -1949,7 +1949,13 @@ def build_run_context_from_spec(
     return RunContext(
         run_id=run_id,
         sim_state=sim_state,
-        metadata={"build_warnings": _build_warnings},
+        # DR D2-r: live dictionaries/lists preserve the winning reserve basis
+        # in run metadata, including build-time no-restartable-unit evidence.
+        metadata={
+            "build_warnings": _build_warnings,
+            "bess_reserve_floor_basis": sim_state.arbitrator.reserve_floor_basis,
+            "bess_reserve_floor_history": sim_state.arbitrator.reserve_floor_history,
+        },
         events=events,
         dt_lead_seconds=float(spec_data.get("dt_lead_seconds", 30.0)),
         end_sim_time=float(spec_data.get("end_sim_time", 300.0)),
diff --git a/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase4_reserve.py b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase4_reserve.py
new file mode 100644
index 0000000..6672c66
--- /dev/null
+++ b/attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/tests/test_dr_isl_phase4_reserve.py
@@ -0,0 +1,208 @@
+"""TC-ISL-01–03: DR D2-r/D1-b; fixtures are not scenario calibrations."""
+import copy
+import json
+
+import pytest
+
+from api.schemas import ScenarioSpec
+from core._plane_guard import _EVALUATE_TICK_PERMITTED
+from core.dispatch import MARGIN_MULTIPLIER
+from core.models import DieselState, TurbineState
+from core.sim_clock import SimClock
+from runtime.build_warnings import reserve_capacity_warnings
+from runtime.scenario_factory import build_run_context_from_spec
+
+
+def _context(**overrides):
+    # PROPOSED_HERE: synthetic 10 MW / 20 MWh BESS and 600 s restart make
+    # reserve arithmetic visible; all timing stays in explicit fixture config.
+    spec = {
+        "name": "tc-isl-reserve", "frequency_nominal_hz": 60.0,
+        "power_factor": .85, "pue_base": 1.0, "island_mode": True,
+        "initial_spinning_count": 0, "bess_normal_dispatch_depth_fraction": 0.0,
+        "solar_rated_mw": 0.0,
+        "turbine_units": [
+            {"asset_id": "gt-reserve", "rated_mw": 1.0,
+             "hot_standby": False, "min_down_enabled": False,
+             "initial_thermal_state": "cold", "cold_start_s": 600.0},
+        ],
+        "bess_units": [
+            {"asset_id": "bess-reserve", "rated_mw": 10.0,
+             "usable_mwh": 20.0, "initial_soc_fraction": 1.0,
+             "grid_forming": True, "p_anchor_reserve_mw": 0.0},
+        ],
+    }
+    spec.update(overrides)
+    if spec.get("diesel_units"):
+        diesel = spec["diesel_units"][0]
+        # ScenarioSpec materializes diesel_units from the enabled power block;
+        # a declared list alone is intentionally not an enabled fleet.
+        spec["diesel_power_block"] = {
+            "enabled": True, "target_capacity_mw": diesel["rated_mw"],
+            "unit_rating_mw": diesel["rated_mw"],
+            "delta_t_start_s": diesel["delta_t_start_s"],
+            "residual_ramp_s": diesel["residual_ramp_s"],
+        }
+    for diesel in spec.get("diesel_units", []):
+        # PROPOSED_HERE: complete the explicit materialized test fleet schema;
+        # zero guards isolate reserve behavior, not operational diesel timing.
+        defaults = {
+            "start_offset_s": 0.0, "f_block": .6,
+            "min_stable_load_mw": .3 * diesel["rated_mw"],
+            "min_run_s": 0.0, "min_down_s": 0.0, "cooldown_s": 60.0,
+        }
+        for key, value in defaults.items():
+            diesel.setdefault(key, value)
+    canonical = ScenarioSpec.model_validate_json(json.dumps(spec)).model_dump(mode="json")
+    return build_run_context_from_spec("tc-isl-reserve", canonical)
+
+
+def _tick(state):
+    token = _EVALUATE_TICK_PERMITTED.set(True)
+    try:
+        from core.simulation_core import evaluate_tick
+        # PROPOSED_HERE: one normal simulator interval, not a timing override.
+        return evaluate_tick(state, SimClock(0.0, 5.0, None, 1.0, 1))
+    finally:
+        _EVALUATE_TICK_PERMITTED.reset(token)
+
+
+def test_tc_isl_01_no_diesel_positive_floor_and_recorded_basis():
+    ctx = _context()
+    arb = ctx.sim_state.arbitrator
+    bess = ctx.sim_state.bess_units[0]
+    expected = MARGIN_MULTIPLIER * 10.0 * 600.0 / 3600.0
+    assert arb.soc_floor_mwh(bess) == pytest.approx(expected)
+    basis = ctx.metadata["bess_reserve_floor_basis"]["bess-reserve"]
+    assert basis["winning_term"] == "d2r"
+    assert basis["unit_id"] == "gt-reserve"
+    assert basis["eligibility_wait_s"] == 0.0
+    assert basis["start_duration_s"] == 600.0
+    assert ctx.metadata["bess_reserve_floor_history"]
+    print({"TC-ISL-01": basis})
+
+
+def test_tc_isl_01_diesel_wins_unchanged():
+    ctx = _context(diesel_units=[{
+        "asset_id": "diesel-reserve", "rated_mw": 1.0, "role": "primary",
+        "delta_t_start_s": 1000.0, "residual_ramp_s": 440.0,
+    }])
+    arb = ctx.sim_state.arbitrator
+    expected = MARGIN_MULTIPLIER * 10.0 * 1440.0 / 3600.0
+    assert arb.soc_floor_mwh(ctx.sim_state.bess_units[0]) == pytest.approx(expected)
+    assert arb.reserve_floor_basis["bess-reserve"]["winning_term"] == "diesel_floor"
+    print({"TC-ISL-01 diesel floor": expected})
+
+
+def test_tc_isl_01_no_restartable_unit_records_zero():
+    ctx = _context(turbine_units=[])
+    arb = ctx.sim_state.arbitrator
+    assert arb.soc_floor_mwh(ctx.sim_state.bess_units[0]) == 0.0
+    assert arb.reserve_floor_basis["bess-reserve"]["basis"] == (
+        "no restartable synchronous unit"
+    )
+    print({"TC-ISL-01 no restartable": arb.reserve_floor_basis})
+
+
+def test_tc_isl_01_min_down_and_inflight_countdown():
+    ctx = _context()
+    state = ctx.sim_state
+    unit = state.turbines[0]
+    unit.config.min_down_enabled = True
+    # PROPOSED_HERE: exactly 90 seconds still unavailable in this test only.
+    unit.config.t_min_down_s = 90.0
+    unit._stop_time_s = 0.0
+    assert unit.start_eligibility(0.0) == (False, "min_down")
+    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == pytest.approx(
+        MARGIN_MULTIPLIER * 10.0 * 690.0 / 3600.0
+    )
+    unit.command_start(90.0)
+    state.arbitrator.reserve_sim_time_s = 90.0
+    unit._time_to_online_s = 120.0  # PROPOSED_HERE: observable remaining countdown.
+    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == pytest.approx(
+        MARGIN_MULTIPLIER * 10.0 * 120.0 / 3600.0
+    )
+    basis = state.arbitrator.reserve_floor_basis["bess-reserve"]
+    assert basis["start_duration_s"] == 120.0
+    assert basis["eligibility_wait_s"] == 0.0
+    print({"TC-ISL-01 STARTING": basis})
+
+
+def test_tc_isl_01_above_capacity_warning_attribution_only():
+    ctx = _context()
+    state = ctx.sim_state
+    state.bess_units[0].config.usable_mwh = 1.0  # PROPOSED_HERE: over-floor fixture.
+    floor = state.arbitrator.soc_floor_mwh(state.bess_units[0])
+    warnings = reserve_capacity_warnings(state)
+    assert floor > 1.0
+    assert warnings[0]["winning_term"] == "d2r"
+    assert warnings[0]["floor_mwh"] == floor
+    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == floor
+    print({"TC-ISL-01 warning": warnings})
+
+
+@pytest.mark.parametrize("overrides", [
+    {"island_mode": False},
+    {"bess_units": [{
+        "asset_id": "bess-reserve", "rated_mw": 10.0, "usable_mwh": 20.0,
+        "initial_soc_fraction": 1.0, "grid_forming": False,
+    }]},
+])
+def test_tc_isl_02_grid_tied_or_nonforming_not_applied(overrides):
+    ctx = _context(**overrides)
+    assert ctx.sim_state.arbitrator.soc_floor_mwh(ctx.sim_state.bess_units[0]) == 0.0
+    print({"TC-ISL-02 inapplicable": overrides})
+
+
+def test_tc_isl_02_live_grid_forming_block_fc_not_applied():
+    ctx = _context(fuel_cell_enabled=True, fuel_cell_units=[{
+        "asset_id": "fc-reserve", "block_rated_mw": 1.0, "block_count": 1,
+        "initial_running_blocks": 1, "initial_hot_standby_blocks": 0,
+        "min_stable_frac": .1, "grid_forming": True,
+    }])
+    state = ctx.sim_state
+    # PROPOSED_HERE: explicit 0.5 MW delivered FC fixture, independent of a
+    # site's demand policy (which is not what this reserve-scope test checks).
+    for array in state.fuel_cell_module.arrays:
+        array.set_load_following_target_mw(.5)
+        array.advance(0.0, 5.0)
+    assert any(array.output_mw() > 0.0 for array in state.fuel_cell_module.arrays)
+    assert state.arbitrator.soc_floor_mwh(state.bess_units[0]) == 0.0
+    print({"TC-ISL-02 live FC": state.arbitrator.reserve_floor_basis})
+
+
+@pytest.mark.parametrize("on_bus", [None, "turbine", "diesel"])
+def test_tc_isl_03_conditional_release_and_unserved(on_bus):
+    extra = {}
+    if on_bus == "diesel":
+        extra["diesel_units"] = [{
+            "asset_id": "diesel-live", "rated_mw": 1.0, "role": "primary",
+            "delta_t_start_s": 1.0, "residual_ramp_s": 0.0,
+        }]
+    ctx = _context(**extra)
+    state = ctx.sim_state
+    if on_bus == "turbine":
+        # Keep the original OFFLINE candidate while another GT forms the grid.
+        live = copy.deepcopy(state.turbines[0])
+        live.config.asset_id = "gt-live"
+        live.state = TurbineState.SYNCHRONISED
+        state.turbines.append(live)
+    elif on_bus == "diesel":
+        state.diesel_units[0].state = DieselState.SYNCHRONISED
+    bess = state.bess_units[0]
+    floor = state.arbitrator.soc_floor_mwh(bess)
+    bess.soc_mwh = floor
+    state.compute_floor_mw = 10.0  # PROPOSED_HERE: explicit gap exceeding the 1 MW source.
+    result = _tick(state)
+    if on_bus is None:
+        assert bess.soc_mwh == pytest.approx(floor)
+        assert result.bess_output_mw == 0.0
+        assert result.p_unserved_mw > 0.0
+    else:
+        assert bess.soc_mwh < floor
+        assert result.bess_output_mw > 0.0
+    assert result.physical_balance.passed
+    print({"TC-ISL-03": on_bus, "floor_mwh": floor,
+           "end_soc_mwh": bess.soc_mwh, "bess_mw": result.bess_output_mw,
+           "unserved_mw": result.p_unserved_mw,
+           "balance_passed": result.physical_balance.passed})
```
