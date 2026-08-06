---
name: ramp-algo-phases-status
description: Phase tracker for the ramp-algorithm replacement spec (DR-2026-08-06, v2 draft). Baseline 12/967/976/0 after Phase B.
---

## Spec reference

DR-2026-08-06, §7.1.3 v2 draft — replace generator ramp algorithm and Gas Turbine Fleet modal.
File: `attached_assets/Pasted-Replace-the-generator-ramp-algorithm-and-the-Gas-Turbin_1786054153985.txt`

## Phase tracker

| Phase | Status | Notes |
|-------|--------|-------|
| A — Audit + TC-87/TC-88 failing | ✅ DONE | Pre-fix: TC-87 FAIL (2 units RAMPING at tick 0), TC-88 FAIL (same); 965 still passing |
| B — Sequential start (1 unit per call) | ✅ DONE | dispatch.py: N_needed+1 replaced with single `_offline[0].stage_target`; TC-84f pre-trip assertion relaxed; 967 passing, 12 failed |
| C — P0 test fix + state machine reclassification | 🔲 PENDING | Fix test_tc_p0_1/2/3/5 (use state+output_mw not breaker_closed); reclassify is_synchronised call sites |
| D — Payload renames (on_bus_count, on_bus_mw) | 🔲 PENDING | synchronised_output_mw → on_bus_output_mw; units_synchronised_count → units_on_bus_count; new commitment block |
| E — Enable physical constraints | 🔲 PENDING | p_min_stable_frac 0→0.40, t_min_run_s 0→1800, t_min_down_s 0→900; do last and alone |

## Baseline history

| After phase | Failed | Passed | Collected |
|-------------|--------|--------|-----------|
| Pre-work (Phase 7 GS-DES-CFG-001) | 12 | 965 | 974 |
| Phase A (add TC-87, TC-88 failing) | 14 | 965 | 976 |
| Phase B (sequential start fixed) | 12 | 967 | 976 |

## Key decisions and traps

**TRAP — same-tick double-start does NOT occur:**
After `stage_for_predicted_step` starts unit 0 (OFFLINE→RAMPING), the per-tick headroom check
computes `_sync_rated_mw` over SYNCHRONISED-only units. RAMPING is excluded. So `_sync_rated_mw = 0`
immediately after a new RAMPING unit starts — the guard `_sync_rated_mw > 0` fails and the headroom
check cannot fire in the same tick. No explicit "already-starting" guard is needed.

**TRAP — stage_target(0, OFFLINE) is a no-op:**
The old N_needed+1 code with delta=0 would call stage_target(0, ...) on OFFLINE — which sets
`_target_mw = 0` but leaves state=OFFLINE. So the old code also did nothing for delta=0 OFFLINE units.
Phase B's `if _eff_delta > 0` guard makes this explicit.

**TRAP — TC-84f pre-trip assertion was N_needed+1 specific:**
The assertion "COVERED_WITH_SHED not in pre_states_set" assumed 2 units synchronised pre-trip.
With sequential starts, a single unit during startup gives COVERED_WITH_SHED (BESS bridge).
Updated to "CANNOT_CARRY not in pre_states_set" — both COVERED and COVERED_WITH_SHED are acceptable.

**Phase C constraint — test_tc_p0_1/2/3/5:**
These tests use a `breaker_closed` fixture key that the runtime doesn't produce.
Fix in Phase C: runtime must emit `breaker_closed` in `_tick_result_to_dict` based on
`state == "synchronised"` (or whatever the post-Phase-C canonical definition is).
Do NOT fix before Phase C — these are deferred per the spec.

**Phase E must run alone:**
Changing p_min_stable_frac default 0.0→0.40, t_min_run_s 0.0→1800, t_min_down_s 0.0→900
changes values across many scenarios. Catalogue each. Do LAST after all state machine work is stable.

**Acceptance test numbering:** TC-87 and TC-88 are in `tests/test_tc87_tc88_sequential_start.py`.
TC-89 through TC-99 reserved for Phases C-E.
