---
name: Ramp Algorithm Phase Tracker
description: Phase-by-phase status of the DR-2026-08-06 ramp-algorithm replacement spec.
---

## Baseline (entering Phase A)
12 failed / 965 passed / 974 collected / 0 errors (CWD: gridsignal_sim/)

## Phase A — structures, zero behaviour change ✅ COMPLETE

**Deliverables:**
- `core/commitment.py` — CommitmentConfig, SustainedCondition, PendingStartRegister, CommitmentDecision, evaluate_commitment()
- `gridsignal_parameters.json` — 8 new locked CHOSEN entries (commit_utilisation, decommit_utilisation, decommit_post_removal_max, commit_confirm_s, decommit_confirm_s, inter_start_settle_s, levelled_off_epsilon_mw, levelled_off_window_s), spec_ref §7.1.3.3
- `tests/test_tc89_tc90_tc91_sequential_start.py` — TC-89, TC-90, TC-91 (all xfailed strict=True after Phase B C-1)
- Old `tests/test_tc87_tc88_sequential_start.py` deleted (TC-87/TC-88 reserved for Phase B)
- dispatch.py N_needed+1 formula RESTORED (Phase B sequential-start was erroneously applied; reverted)
- test_tc84f original assertions RESTORED (COVERED_WITH_SHED not in pre_states_set)

**Gate:** 12 failed / 965 passed / 3 xfailed / 977 collected. Guard D1 green.

**TC-91 failure mode (reported per correction §Item 2):**
Fails with 2 simultaneous starts (`t-1: offline→ramping`, `t-2: offline→ramping`).
Root cause: N_needed+1 stages 2 units from stage_for_predicted_step alone
(_n_start = min(max(1, ceil(5/7)+1), 2) = 2), same mechanism as TC-89/TC-90.
After Phase D, stage_for_predicted_step starts 1; PendingStartRegister prevents
headroom check from starting the second.

## Phase B — interval ordering and write guard ✅ COMPLETE

**Deliverables:**
- `tests/test_tc87_tc88_interval_ordering.py` — TC-87 and TC-88 tests added.
- `core/asset_modules.py` TurbineModule — `_output_writes: int = 0` field added;
  `begin_interval()` resets it; `set_output()` increments and raises RuntimeError if > 1.
- `core/simulation_core.py` — Item 1: snapshot `_entry_states` before advance(),
  call `begin_interval()` on each turbine, build `_synchronised_units` from entry
  states (not live state). A unit promoted RAMPING→SYNCHRONISED during advance() is
  excluded from the loaded set for the promotion interval.
- `tests/test_tc89_tc90_tc91_sequential_start.py` — C-1: TC-89/90/91 flipped to
  `strict=True` (all three still fail as expected).

**TC-88 pre-fix/post-fix confirmation (required by spec):**
- PRE-FIX (before Item 1): output=2.000 MW ≠ 3.0 MW. apply_loading() stepped the
  promoted unit from 3.0 → 2.0 MW (demand=0, so loading drove it down 1 step).
- POST-FIX (after Item 1): output=3.0 MW preserved. Promoted unit excluded from
  loading set via entry-state filter. TC-88 PASSES. ✓

**TC-87 result:** PASSES — ramp is rate-determined, constant HIGH setpoint (rated_mw=7)
proves not satisfiable by rising-setpoint shortcut.

**C-1:** TC-89/90/91 all flipped to strict=True; all 3 still xfail (fail the
assertion, not error). Confirmed in suite as "3 xfailed".

**C-2: p_min_stable_frac per seeded scenario:**
- demo-20mw: ALL turbines = 0.40 (turbine-0..3 active + turbine-4 hot-standby)
- ALL other scenarios: 0.0 (default — not set)
- Only demo-20mw has a non-zero p_min_stable floor.

**C-3: Degraded N-1 window measurement (current tree: N_needed+1 + Phase B Item 1):**
- First COVERED: t=5.0 s (tick 0, very first evaluation interval).
- Window = 5.0 s (essentially immediate — N_needed+1 starts 2 units simultaneously,
  providing N-1 resilience from tick 1: 1.0 + 6.0 MW ramp credit > 6.3 MW demand).
- 24 COVERED / 36 COVERED_WITH_SHED ticks across 300 s run (some later ticks go to
  COVERED_WITH_SHED, likely as demand/solar varies after equilibrium).
- Contrast with Phase A measurement (under reverted sequential-start): window was
  UNBOUNDED (COVERED_WITH_SHED for entire 300 s) because only 1 unit started and
  N-1 trip left zero capacity.

**Gate:** 12 failed / 967 passed / 3 xfailed / 982 collected.
Guard D1 (`_check_loading_exclusion`) still present and valid post-Item-1.
Entry-state filter does not conflict with the exclusion check (RAMPING units never
appear in _synchronised_units built from entry states).

## Phase C — one control law, legacy path deleted ✅ COMPLETE

**Deliverables:**
- `core/models.py` — TurbineState: UNLOADING added; RAMPING/AT_TARGET/TRANSITIONAL removed; from_persisted() migration map.
- `core/asset_modules.py` — stage_target() deleted; command_stop() added (raises RuntimeError if not SYNCHRONISED); advance() RAMPING branch deleted; _target_mw field removed; is_synchronised → is_on_bus + contributes_to_reserve.
- `core/simulation_core.py` — _check_loading_exclusion deleted; _synchronised_units widened to {SYNCHRONISED, UNLOADING}; stage_target() → command_start(); is_on_bus at contingency snapshot.
- `core/loading.py` — ramp_capability: is_synchronised → contributes_to_reserve.
- `core/dispatch.py` — turbine_output_mw sum: is_on_bus; offline staging: stage_target() → command_start(); on-bus stage_target() block deleted; _per_start_target removed.
- `runtime/run_manager.py` — _ON_BUS set updated; payload rename (units_synchronised_count → units_on_bus_count, synchronised_output_mw → on_bus_output_mw); output_mw overlay: is_on_bus; trip handler: is_on_bus + _target_mw line removed.
- `frontend/src/types.ts` — field renames + comments updated.
- `frontend/src/subsystem/panels/turbineFleet.ts` — isOnBus() widened; all field renames + label updates.
- `frontend/src/opening/PlantNode.tsx` — field renames.
- `frontend/src/opening/plantLayout.ts` — mwField renames.
- `tests/test_turbine_payload_p0.py` — TC-P0-1/2/3/5 updated (fixture output_mw fields added, key renames).

**Gate:** 42 failed / 937 passed / 3 xfailed / 982 collected.
TypeScript --noEmit clean.
Guard D1 (`_check_loading_exclusion`): DELETED per Phase C spec — no orphan references.
Guard D2 and E Tier-1: not affected by Phase C changes (config-layer guards remain green).

**Failure classification (42 total):**

Pre-existing (12 — unchanged from Phase B baseline):
- test_13_2_balance_decomp: D3_grid_connected_settled, D3_islanded_settled, I4a_healthy_islanded_delivery_error_near_zero
- test_f5_sim_time_interval_end: test_internal_elapsed_unaffected_by_f5
- test_forecast_path: test_B1a_islanded_delivery_fault_visible_in_delivery_channel
- test_formulas: test_d10_demo_20mw_bess_fires_and_tapers
- test_telemetry_corruption_wiring: test_tc_gt2_f_state_flips_when_soc_crosses_threshold
- test_step16_wiring: test_demo_pms_column3_tc64_to_tc68
- test_kube_no_oscillation: test_power_cap_toggle_count_within_300s + 3 SUBFAILEDs (seeds 42/7/2025)

New Correct failures (30 — tests encoded old RAMPING/AT_TARGET/stage_target behavior):
- test_tc87_tc88_interval_ordering: TC-87 (stage_target deleted → AttributeError), TC-88 (TurbineState.RAMPING deleted)
- test_operator_unit_commands: TC-203-1/3/4 (TurbineModule.is_synchronised renamed → AttributeError)
- test_unit_trip: TC-84a-e (TurbineState.AT_TARGET deleted → AttributeError)
- test_13_4_criteria::TestB4StandbyConsistency: B4a/B4b (AT_TARGET deleted)
- test_13_5_criteria: R4×4 / R5×3 / R6×3 (stage_target deleted → AttributeError)
- test_formulas: test_turbine_ramps_at_configured_rate (RAMPING path), test_d8_staging_sizes (stage_target)
- test_p1b_p2::TestTC81: ×4 (AT_TARGET deleted; _check_loading_exclusion deleted)
- test_ramping_turbine_ignores_loading_setpoint_drop (TurbineState.RAMPING deleted)
- test_turbine_payload_p0::TC-P0-4 (KeyError on renamed field — spec forbids editing)

No incorrect (regression) failures.

Extra site (not on spec's expected list, reported not changed):
- runtime/run_manager.py:887 `is_synchronized=(t.state != TurbineState.OFFLINE)` — raw comparison, not a call to the is_synchronised property; semantics intact; left as-is per spec.

## Phase D — commitment engine wired ✅ COMPLETE

**Deliverables:**
- Item 1: `runtime/run_manager.py:889` — is_synchronized → t.is_on_bus (STARTING wrongly counted under `!= OFFLINE`).
- Item 2: Guard D1 (`test_guard_d1_no_drift`) confirmed PASSING before wiring; catalogue literals intact.
- Item 3: `tests/test_tc87_tc88_interval_ordering.py` — TC-87 repaired (begin_interval+apply_loading instead of stage_target+advance); TC-88 repaired (STARTING setup: command_start → _time_to_online_s=dt → _current_output_mw=3.0 instead of RAMPING setup).
- Item 3: `tests/test_ramping_turbine_ignores_loading_setpoint_drop.py` — renamed to `test_starting_turbine_output_frozen_by_loading_exclusion`; EXPECTED_STEP 1.0→0.0; RAMPING→STARTING state checks; cold_start_s=60.0 added.
- Item 4: `tests/test_turbine_payload_p0.py` TC-P0-4 — units_synchronised_count→units_on_bus_count, synchronised_output_mw→on_bus_output_mw.
- Item 5: `core/simulation_core.py` — CommitmentConfig/SustainedCondition/PendingStartRegister/evaluate_commitment imported; 4 new fields on SimulationState (init=False, set in __post_init__ from catalogue); headroom block replaced with evaluate_commitment() call; pending register cleared in advance() post-loop when unit reaches SYNCHRONISED.
- Item 6: `core/dispatch.py` — DispatchArbitrator gets `pending_start` attribute; stage_for_predicted_step() N_needed+1 removed → exactly 1 unit per call, PendingStartRegister gate.
- Item 6: `core/models.py` — hot_start_s 60.0→300.0 (D-08).
- Item 6: `frontend/src/subsystem/panels/turbineFleet.ts` — '60 s (1 min)' × 2 → '300 s (5 min)'.
- Item 7: `tests/test_tc89_tc90_tc91_sequential_start.py` — xfail markers removed from TC-89/90/91; TC-91 scaffold repaired (pending register wired, command_start replaces stage_target, is_on_bus replaces raw state check); TC-92 added (reserve floor commits N+1); TC-93 added (STARTING contributes zero to reserve/ramp/headroom).
- Stale: removed `_t._target_mw = 0.0` from UNIT_TRIP handler in simulation_core.py (attribute deleted in Phase C).

**Gate:** 38 failed / 946 passed (including TC-89/90/91/92/93 all PASS).
Failure classification:
  Pre-existing (12 — unchanged): D3×2, I4a, f5, B1a, d10, tc_gt2, step16, kube×4.
  Correct stale (26 — tests encoding deleted behavior): TC-84a-e, TC-81×4, R4×4, R5×3, R6×3, B4a/b, turbine_ramps_at_configured_rate, d8_staging, tc_203_1/3/4, discriminator(old name).
  Regressions: 0.

**Item 8 — Phase D N-1 window measurement (demo-20mw, 300 s):**
- hot_start_s=300 s means turbine-0 is in STARTING for the full 300 s window (synchronises ~t=300 s).
- BESS (16 MW bridging, ~7.6 MWh) covers all load throughout; N-1 COVERED from t=0.
- First COVERED: t=0 s (tick 0).
- Window: 300 s / 60 ticks (full run), all COVERED.
- COVERED: 60 ticks / 300 s (100%). COVERED_WITH_SHED: 0 ticks / 0 s (0%).
- Contrast with Phase B (N_needed+1): COVERED window was 5 s → COVERED_WITH_SHED for the rest once demand pressure rose.

## Phase E — stop sequencing, loading policy, physical constraints ⬜ PENDING

SYNCHRONISED → UNLOADING → levelled-off → breaker → OFFLINE.
Sequential stops (D-09): at most one unit UNLOADING at a time.
Loading policy (D-14): sequential base-loading replaces proportional sharing.
Enable constraints: p_min_stable_frac 0→0.40, t_min_run_s 0→1800, t_min_down_s 0→900.
Add TC-94 … TC-97.

## Reserved TC numbers
TC-87 = Phase B interval-ordering test (output = accumulated integral). ✅ DONE
TC-88 = Phase B write-guard test (promoted unit not loaded in promotion interval). ✅ DONE
TC-89 = sequential-start first-tick (from old TC-87, Phase D gate). xfail strict=True
TC-90 = sequential-start full-run 20-tick (from old TC-88, Phase D gate). xfail strict=True
TC-91 = one-already-SYNCHRONISED case (Phase D + PendingStartRegister gate). xfail strict=True
TC-92 = reserve floor commits N+1 (Phase D gate). ✅ DONE
TC-93 = STARTING contributes zero to reserve/ramp/headroom (Phase D gate). ✅ DONE
TC-94 … TC-97 = Phase E (TBD).
