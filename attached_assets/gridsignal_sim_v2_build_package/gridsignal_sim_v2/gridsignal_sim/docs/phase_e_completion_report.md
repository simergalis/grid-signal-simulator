# Phase E Completion Report — DR-2026-08-06

**Date:** 2026-08-07  
**Spec:** `GS_prompt_E_stop_sequencing_1786106100955.md`  
**Final suite:** 13 failed / 975 passed / 16 xfailed  
**Entering baseline (after Items 1–4):** 12 failed / 958 passed / 16 xfailed

---

## Items 1–4 — Gate Repairs

Repaired prior to Phase E proper. Gate after Items 1–4: **12 failed / 958 passed / 16 xfailed**.

| Item | Description | Gate delta |
|------|-------------|------------|
| 1 | N-1 re-measurement at 1800 s window | 0 Δ |
| 2 | Discriminator — SYNCHRONISED rate-limit test | 0 Δ |
| 3 | TC-91b — pending register shared across both production paths (≤ 1 unit/tick) | 0 Δ |
| 4 | 26 stale assertion repairs (TC-84a-e, B4a/b, TC-203-1/3/4, ramp-rate, etc.) | 0 Δ |

---

## Item 5 + 6 — Stop Sequencing and Sequential Stops

**Gate:** 12 failed / 964 passed / 16 xfailed — **6 new tests added, 0 regressions**

### What changed

| File | Change |
|------|--------|
| `core/models.py` | `levelled_off_tol_mw: float = 0.05` added to `TurbineConfig` |
| `core/asset_modules.py` | `_levelled_off_since_s: float = math.nan` field; reset in `command_stop()` |
| `core/simulation_core.py` | `_last_breaker_open_s` on `SimulationState`; UNLOADING branch → MSL setpoint; SYNCHRONISED branch → fleet residual; levelled-off breaker-open check; sequential-stop guard in decommit handler |
| `tests/test_tc94_tc97_stop_sequencing.py` | TC-94 (3 tests), TC-97 (3 tests) |

### Sequence

```
SYNCHRONISED  →  UNLOADING  →  [levelled-off at MSL]  →  OFFLINE
                  ↑ setpoint = MSL                         ↑ breaker open
                  ↑ fleet residual excludes this unit
```

- **Breaker open condition:** `|output − MSL| < levelled_off_tol_mw` sustained for `unload_tail_s` seconds.
- **Sequential-stop guard:** decommit handler blocks if any unit is `UNLOADING` or settling has not elapsed.

### Scaffolding traps discovered

- `SimulationState.cooling` field is `cooling=` (singular `CoolingModule`, not `cooling_units=`)
- `evaluate_tick()` takes `SimClock(sim_time, dt_seconds, wall_stamp_utc=0.0, rate=1.0, tick_seq=0)`, not raw floats
- `evaluate_tick()` requires `_plane_guard_active()` context manager — define locally as `@contextlib.contextmanager`
- TC-94 descent assertion: `prev_output` may be up to `r_asset × dt` above MSL; correct tolerance = `r_asset × dt + levelled_off_tol_mw`
- TC-97 third test: check state **before** the tick to catch UNLOADING that opens the breaker within the same `evaluate_tick()` call

---

## Item 7 — Sequential Base-Loading

**Gate:** 12 failed / 970 passed / 16 xfailed — **6 new tests added, 0 regressions**

### What changed

| File | Change |
|------|--------|
| `core/loading.py` | Replaced proportional sharing (`shares = rated_i / Σ rated`) with sequential fill: set all units to MSL, distribute residual in commitment order |
| `tests/test_tc96_sequential_base_loading.py` | TC-96 (6 tests) |

### Algorithm (sequential fill)

```
1. Floor every on-bus unit at MSL (= p_min_stable_frac × rated_mw).
2. residual = p_fleet − Σ MSL
3. For each unit in commitment order (list = start order):
       headroom = rated_mw − current_setpoint
       allocation = min(residual, headroom)
       setpoint += allocation
       residual -= allocation
       if residual ≤ 0: break
```

Per-unit utilisation now diverges from fleet utilisation — the first unit to start is filled to rated before the next unit receives load above its MSL.

### Test construction trap

Three-unit test with `rated=7, MSL=2.8, p_fleet=17.0`: residual = 8.6; u0 fills 4.2 → 7.0; u1 fills 4.2 → 7.0; u2 gets 0.2 → 3.0. Must use `p_fleet=17.0` not `15.0` (at 15.0, u1 is the marginal unit, not u2).

---

## Item 8 — Physical Constraints Enabled

**Gate:** 13 failed / 975 passed / 16 xfailed — **6 new tests added**  
**Per-scenario delta:** 1 assertion moved (classified CORRECT, not edited)

### Default changes — all 23 seeded scenarios

| Parameter | Old default | New default | Provenance | Spec ref |
|-----------|-------------|-------------|------------|----------|
| `p_min_stable_frac` | 0.0 | **0.40** | CHOSEN | §7.1.3.6 |
| `t_min_run_s` | 0.0 | **1800 s** | CHOSEN | §7.1.3.6 |
| `t_min_down_s` | 0.0 | **900 s** | CHOSEN | §7.1.3.6 |

`demo-20mw` already had `p_min_stable_frac=0.40`; all three constraints are new for the remaining 23 scenarios.

### What changed

| File | Change |
|------|--------|
| `api/schemas.py` | `TurbineUnitSpec`: replaced `p_min_stable_frac=0.0` with `p_min_stable_frac=0.40`, added `t_min_run_s=1800.0`, `t_min_down_s=900.0` |
| `api/routes/scenarios.py` | `_turbine()` helper: new signature defaults `p_min_stable_frac=0.40, t_min_run_s=1800.0, t_min_down_s=900.0`; both threaded through to `TurbineUnitSpec` |
| `runtime/scenario_factory.py` | Reads `t_min_run_s` and `t_min_down_s` from spec dict with CHOSEN defaults (1800 / 900); passes to `TurbineConfig` |
| `core/asset_modules.py` | `command_stop()`: R5 guard added — silently defer if `sim_time − _run_start_s < t_min_run_s` |
| `gridsignal_parameters.json` | 3 new `CHOSEN` catalog entries: `p_min_stable_frac_all_scenarios`, `t_min_run_s`, `t_min_down_s` (all `spec_ref §7.1.3.6`) |
| `tests/test_no_hardcoded_parameters.py` | Guard D1 exemptions: `t_min_run_s` and `t_min_down_s` with Reason B (disable-flag sentinel vs CHOSEN production default) |
| `tests/test_tc95_msl_floor_allocation.py` | TC-95 (6 tests) |

### R5 enforcement (command_stop guard)

```python
if (
    self.config.t_min_run_s > 0.0
    and not math.isnan(self._run_start_s)
    and (sim_time - self._run_start_s) < self.config.t_min_run_s
):
    return  # defer; caller retries on next decommit check
```

`t_min_down_s` / R6 enforcement already existed in `command_start()`.

### Per-scenario delta

| Test | Before | After | Classification |
|------|--------|-------|----------------|
| `TC-203-3` (`test_tc_203_3_immediate_start_after_trip_accepted_when_cooldown_zero`) | PASS | FAIL | **CORRECT** — test's precondition asserts `t_min_down_s == 0.0` (the old default). Default is now 900 s. The behavioral property (restart with `t_min_down_s=0` is immediately accepted) remains true; the scenario no longer has `t_min_down_s=0`. Not edited per spec. |

No simulation assertion failures from the constraint change itself. Sequential-base-loading MSL floor (TC-96) and UNLOADING sequence (TC-94/97) absorbed the constraint correctly.

---

## Item 9 — §7.2 Amendment Measurement

**Report only; spec not edited.**

### Setup

`demo-20mw` post–Item 8: 4 online turbines, rated 7 MW each, MSL = 2.8 MW (`p_min_stable_frac=0.40`), `r_asset = 0.2 MW/s`, `dt = 5 s`, BESS = 18 MW / 8 MWh grid-forming.

### Peak BESS discharge at breaker-open

| Scenario | MSL step (MW) | Surviving turbines | Survivor ramp capacity (MW/tick) | Net gap to BESS (MW) |
|----------|--------------|--------------------|---------------------------------|----------------------|
| Normal case (3 survivors) | 2.8 | 3 | 3 × (0.2 × 5) = **3.0** | 2.8 − 3.0 = **−0.2** (no burst) |
| Worst case (last unit alone) | 2.8 | 0 | 0 | **2.8 MW** |

### Conclusion

In the normal controlled-stop sequence, the 3 surviving turbines' combined ramp (3.0 MW/tick) exceeds the MSL step (2.8 MW) — the BESS sees zero incremental discharge at breaker-open. The degenerate case (final unit stopping with no survivors online) produces a 2.8 MW BESS discharge spike; at 18 MW rated the BESS is loaded to **15.6%** of its discharge ceiling. Well within margin; no §7.2 spec amendment required.

---

## Failure Classification — Final Gate

**13 failed / 975 passed / 16 xfailed**

| # | Test | Origin | Status |
|---|------|---------|--------|
| 1 | `test_D3_grid_connected_settled` | Pre-existing | Unchanged |
| 2 | `test_D3_islanded_settled` | Pre-existing | Unchanged |
| 3 | `test_I4a_healthy_islanded_delivery_error_near_zero` | Pre-existing | Unchanged |
| 4 | `test_internal_elapsed_unaffected_by_f5` | Pre-existing | Unchanged |
| 5 | `test_B1a_islanded_delivery_fault_visible_in_delivery_channel` | Pre-existing | Unchanged |
| 6 | `test_d10_demo_20mw_bess_fires_and_tapers` | Pre-existing | Unchanged |
| 7 | `test_oscillation_is_reproducible_across_seeds` (seed=42) | Pre-existing | Unchanged |
| 8 | `test_oscillation_is_reproducible_across_seeds` (seed=7) | Pre-existing | Unchanged |
| 9 | `test_oscillation_is_reproducible_across_seeds` (seed=2025) | Pre-existing | Unchanged |
| 10 | `test_power_cap_toggle_count_within_300s` | Pre-existing | Unchanged |
| 11 | `test_demo_pms_column3_tc64_to_tc68` | Pre-existing | Unchanged |
| 12 | `test_tc_gt2_f_state_flips_when_soc_crosses_threshold` | Pre-existing | Unchanged |
| 13 | `test_tc_203_3_immediate_start_after_trip_accepted_when_cooldown_zero` | **Item 8 delta** | CORRECT — not edited |
