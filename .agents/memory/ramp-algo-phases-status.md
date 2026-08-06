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

## Phase C — one control law, legacy path deleted ⬜ PENDING

Delete RAMPING branch, stage_target(), _target_mw. Add UNLOADING state, command_stop().
Rename is_synchronised → is_on_bus + contributes_to_reserve (individual reclassification).
Persisted-state migration with schema version bump.
Fix test_tc_p0_1/2/3/5 HERE (fixtures use breaker_closed, state set changing).
D-05 payload rename lives here.
Expect large delta; report every newly failing test, classify correct-or-incorrect.

## Phase D — commitment ⬜ PENDING

Wire evaluate_commitment() into simulation_core.py, replace headroom block entirely.
Reserve floor: Σ rated_SYNC ≥ P_dispatch + max(rated_SYNC).
Sequential starts: PendingStartRegister + inter_start_settle_s + command_start() only.
Remove cold-start bypass. hot_start_s 60 → 300 (D-08, same commit as UI §U-5).
TC-89, TC-90, TC-91 must all PASS in Phase D gate.
Add TC-92, TC-93.

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
TC-92, TC-93 = Phase D (TBD).
TC-94 … TC-97 = Phase E (TBD).
