---
name: Ramp Algorithm Phase Tracker
description: Phase-by-phase status of the DR-2026-08-06 ramp-algorithm replacement spec.
---

## Baseline (entering Phase A)
12 failed / 965 passed / 974 collected / 0 errors (CWD: gridsignal_sim/)

## Phase A — structures, zero behaviour change ✅ COMPLETE
**Gate:** 12 failed / 965 passed / 3 xfailed / 977 collected.

## Phase B — interval ordering and write guard ✅ COMPLETE
**Gate:** 12 failed / 967 passed / 3 xfailed / 982 collected.

## Phase C — one control law, legacy path deleted ✅ COMPLETE
**Gate:** 42 failed / 937 passed / 3 xfailed / 982 collected.

## Phase D — commitment engine wired ✅ COMPLETE
**Gate:** 38 failed / 946 passed. 12 pre-existing + 26 correct stale failures. 0 regressions.

**Item 8 — Phase D N-1 window (demo-20mw, 300 s):**
First COVERED: t=0 s; 60/60 ticks COVERED (100%). hot_start_s=300 s; turbine never on bus.

## Phase E — stop sequencing, loading policy, physical constraints ✅ COMPLETE

**Final gate: 13 failed / 975 passed / 16 xfailed. 0 regressions.**

13 failures = 12 pre-existing (D3×2, I4a, f5, B1a, d10, kube×4, step16, telemetry) +
1 Item 8 correct delta (TC-203-3: old default assertion, classified CORRECT).

### Items 1-4 (Gate repairs) ✅ COMPLETE
Gate: 12 failed / 958 passed / 16 xfailed.

**Item 1 (N-1 re-measurement, 1800 s):** First SYNCHRONISED t=900 s. COVERED 179 ticks /
895 s (BESS-only). COVERED_WITH_SHED 181 ticks / 905 s. CANNOT_CARRY 0.

**Item 2 (discriminator):** SYNCHRONISED unit rate-limit test added (passing).

**Item 3 (TC-91b):** Both production paths share pending register → ≤1 unit/tick (passing).

**Item 4 (26 stale repairs):** TC-84a-e, B4a/b, TC-203-1/3/4 scaffolding repaired.
TC-81×4, R4×4/5×3/6×3, ramp-rate, d8_staging all xfailed with Phase E reports.

### Items 5+6 (Stop sequencing) ✅ COMPLETE
Gate: 12 failed / 964 passed / 16 xfailed. 0 regressions.

**Implementation:**
- `_last_breaker_open_s` field on SimulationState (NaN sentinel)
- UNLOADING units → MSL setpoint; SYNCHRONISED units → fleet residual (split in simulation_core.py)
- Levelled-off breaker check: |output - msl| < levelled_off_tol_mw sustained for unload_tail_s
- Sequential-stop guard in decommit handler: blocks if n_unloading > 0 OR not settled
- `levelled_off_tol_mw: float = 0.05` on TurbineConfig; `_levelled_off_since_s` on TurbineModule

**Tests:** TC-94 (3 tests), TC-97 (3 tests) — all 6 PASS.

**Scaffolding traps:**
- SimulationState.cooling field name is `cooling=` (singular, not `cooling_units=`)
- evaluate_tick() takes SimClock(sim_time, dt_seconds, wall_stamp_utc=0.0, rate=1.0, tick_seq=0)
- Requires `_plane_guard_active()` context manager; define locally as @contextlib.contextmanager
- Check turbine state BEFORE the tick to catch UNLOADING that opens breaker within same tick
- TC-94 assertion tolerance: r_asset × dt + levelled_off_tol_mw (prev output up to one step above MSL)

### Item 7 (Sequential base-loading) ✅ COMPLETE
Gate: 12 failed / 970 passed / 16 xfailed. 0 regressions.

**Implementation in core/loading.py:** Replace proportional sharing with sequential allocation:
floor all units at MSL, distribute residual in commitment order (list order = start order).
Existing redistribution loop remains as safety guard.

**Tests:** TC-96 (6 tests) — all 6 PASS.

**TC-96 three-unit test trap:** With 3 units at rated=7, msl=2.8, p_fleet=17.0:
residual = 8.6; u0 fills 4.2 → 7.0; u1 fills 4.2 → 7.0; u2 gets 0.2 → 3.0 (marginal).
Must use p_fleet=17.0 NOT 15.0 (at 15.0, u1 is the marginal at 5.2, not u2).

### Item 8 (Enable physical constraints) ✅ COMPLETE
Gate: 13 failed / 975 passed / 16 xfailed.
**1 correct delta:** TC-203-3 (old default assertion: `t_min_down_s == 0.0` now fails;
CORRECT — default changed to 900s. Spec says "edit none of them".)

**Implementation:**
- `TurbineUnitSpec` in schemas.py: added `t_min_run_s=1800, t_min_down_s=900` fields
- `_turbine()` helper in scenarios.py: defaults changed to `p_min_stable_frac=0.40, t_min_run_s=1800, t_min_down_s=900`
- `runtime/scenario_factory.py`: reads `t_min_run_s` and `t_min_down_s` with CHOSEN defaults
- `command_stop()` in asset_modules.py: R5 guard added (t_min_run_s enforcement)
- `t_min_down_s` enforcement already existed in `command_start()` (R6)
- Guard D1 exemptions: added `t_min_run_s` and `t_min_down_s` with Reason B (disable-flag vs production default)
- parameters.json: 3 new CHOSEN catalog entries (p_min_stable_frac_all_scenarios, t_min_run_s, t_min_down_s), spec_ref §7.1.3.6

**Tests:** TC-95 (6 tests) — all 6 PASS.

### Item 9 (§7.2 amendment measurement) ✅ REPORTED
Peak BESS discharge at breaker-open: normal case = 0 MW (3 survivors absorb 2.8 MW MSL step
at 1.0 MW/tick each = 3.0 MW > 2.8 MW). Worst case (last unit) = 2.8 MW vs 18 MW rated = 15.6%.
No spec edit required.

## Reserved TC numbers
TC-87/88 = Phase B. TC-89/90/91/92/93 = Phase D. All done.
TC-94 = state sequence SYNCHRONISED→UNLOADING→OFFLINE (Phase E). ✅
TC-95 = MSL floors allocation / sub-MSL surplus (Phase E Item 8). ✅
TC-96 = per-unit utilisation diverges from fleet (Phase E Item 7). ✅
TC-97 = sequential-stop guard (Phase E Items 5+6). ✅
