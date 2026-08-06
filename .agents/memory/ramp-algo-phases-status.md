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
- `tests/test_tc89_tc90_tc91_sequential_start.py` — TC-89, TC-90, TC-91 (all xfailed, Phase D will un-xfail)
- Old `tests/test_tc87_tc88_sequential_start.py` deleted (TC-87/TC-88 reserved for Phase B)
- dispatch.py N_needed+1 formula RESTORED (Phase B sequential-start was erroneously applied; reverted)
- test_tc84f original assertions RESTORED (COVERED_WITH_SHED not in pre_states_set)

**Gate:** 12 failed / 965 passed / 3 xfailed / 977 collected. Guard D1 green.

**TC-91 failure mode (reported per correction §Item 2):**
Fails today with 2 simultaneous starts (`t-1: offline→ramping`, `t-2: offline→ramping`).
Root cause: N_needed+1 stages 2 units from stage_for_predicted_step alone
(_n_start = min(max(1, ceil(5/7)+1), 2) = 2), same mechanism as TC-89/TC-90.
After Phase D, stage_for_predicted_step starts 1; PendingStartRegister prevents
headroom check from starting the second.

**Degraded N-1 window measurement (§7.1.3.8):**
Under Phase B sequential-start, the degraded window is UNBOUNDED — turbine-1
never starts at all. demo-20mw demand (~6.3 MW equilibrium) gives fleet
utilisation 2.8/7.0 = 40%, below the 80% headroom threshold. The headroom
check never fires. Coverage stays COVERED_WITH_SHED for the entire run (>400 s).
Phase D must replace the headroom block entirely with evaluate_commitment().

## Phase B — interval ordering and write guard ⬜ PENDING

TC-87: output at interval n equals accumulated integral, independent of setpoint trajectory.
TC-88: a unit promoted during advance() is not loaded in the interval of its promotion.
Add begin_interval() + RuntimeError write guard on second set_output per interval.
Gate: TC-88 confirmed failing before ordering change, passing after.

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
TC-87 = Phase B interval-ordering test (output = accumulated integral).
TC-88 = Phase B write-guard test (promoted unit not loaded in promotion interval).
TC-89 = sequential-start first-tick (from old TC-87, Phase D gate).
TC-90 = sequential-start full-run 20-tick (from old TC-88, Phase D gate).
TC-91 = one-already-SYNCHRONISED case (Phase D + PendingStartRegister gate).
TC-92, TC-93 = Phase D (TBD).
TC-94 … TC-97 = Phase E (TBD).
