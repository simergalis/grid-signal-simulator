---
name: Droop runaway and OFFLINE setpoint gate
description: Diagnosis of unbounded droop correction at large Δf; the OFFLINE-gate fix for delivery error and gt_setpoint_mw; B5b secondary regression; d10 hot_start regression.
---

## Droop correction is unbounded (Item 1 — diagnosed, not yet implemented)

Expression in `core/simulation_core.py` (Phase 13.3 governor droop block):
```
_droop_correction_mw = −Δf / (governor_droop × f_nominal) × _s_base_mw
```
- `governor_droop = 0.04` (4% droop), `f_nominal = 50 Hz`, `_s_base_mw = Σ rated_MW / pf`
- At 4% droop, 1% frequency deviation (0.5 Hz) → correction = 25% of S_base. At 33% deviation → correction = 8× S_base.
- There is NO ceiling on `_droop_correction_mw` or `_p_dispatch_droop_mw`. The `max(0, ...)` floor prevents negative setpoints only.

**Runaway scenario:** Islanded island, turbines starting from 0 MW, demand ≈ 35.5 MW. Frequency collapses → Δf grows → correction grows. At tick 1: Δf = −16.84 Hz → correction = +445.9 MW against a 45 MW fleet.

**Downstream effects of runaway:**
- `reserve_floor_mw` shows four-digit MW on fleet modal
- `_fleet_utilisation_cs` >> 1.0 → commitment engine stages every tick
- `gt_setpoint_mw` (after gate) = thousands of MW in TickResult (before gate was applied)
- `bess_setpoint_mw` = thousands of MW (BESS output capped at rated, so actual output is correct)

**Does unboundedness explain I3 sign inversions?** NO. I3 is the MSL-floor issue: at f=52 Hz, droop correction = −S_base → setpoint = 0. MSL floor keeps turbine at MSL output (4 MW). The two issues are separable.

**Proposed bound (not yet implemented):**
```python
_p_dispatch_droop_mw = max(0.0, min(
    p_dispatch_required_mw + _droop_correction_mw,
    _s_base_mw * state.site.power_factor,   # = Σ rated_MW (total fleet)
))
```
No new catalogue constant — `_s_base_mw × pf = Σ rated_MW` is already computed.

---

## Droop clamp implemented

`_sync_ceiling_mw = _s_base_mw * state.site.power_factor` (= Σ rated_MW, already computed).
```python
_p_dispatch_droop_mw = max(0.0, min(p_dispatch_required_mw + _droop_correction_mw, _sync_ceiling_mw))
```
No new catalogue constant. Suite unchanged (no test exercises the extreme runaway regime).

---

## OFFLINE setpoint gate (Item 2 — implemented)

**Problem:** `_p_dispatch_droop_mw` (full fleet demand) was attributed as the turbine setpoint even when all turbines are OFFLINE. This produced spurious `asset_delivery_error_mw = −demand` when BESS correctly covers load.

**Fix:** Gate on `_committed_rated_mw_cs > 0` (at least one SYNCHRONISED turbine):
```python
_turb_setpoint_for_error_mw = (
    _p_dispatch_droop_mw if _committed_rated_mw_cs > 0.0 else 0.0
)
```
Apply to BOTH:
1. `_asset_delivery_error_mw` formula (uses `_turb_setpoint_for_error_mw`)
2. `gt_setpoint_mw` in TickResult (also uses `_turb_setpoint_for_error_mw`)

**Critical: BOTH fields must use the same gated variable.** D5 tests (`TestD5ModelErrorNotResidual`) check the formula `tick.asset_delivery_error_mw == (turb_out - tick.gt_setpoint_mw) + (bess_out - bess_setpoint)`. If only the delivery error formula is gated but `gt_setpoint_mw` remains ungated, D5 breaks (inconsistency). Apply the gate to both simultaneously.

**B5b secondary regression:** `test_B5b_gt_setpoint_mw_equals_dispatch_required` asserts `gt_setpoint_mw == p_dispatch_required` with OFFLINE turbine. After gate, `gt_setpoint_mw = 0`. B5b goes red. This is correct behavior (B5b tested wrong behavior). Fixing requires a test edit.

**Suite result:** 15 failed → 13 failed (D3g + D3i + I4a green, B5b red).

---

## TC-GT2-F warmup depth (Item 3)

`test_telemetry_corruption_wiring.py` uses `_N_WARMUP_TICKS=5` (25 s). With `hot_start_s=300 s`, turbines stay OFFLINE. Contingency evaluator hits early-exit path (`online=[]` → `ContingencyCoverage(energy_test_passes=True)`). TC-GT2-F asserts `energy_test_passes=False` after SoC corruption — impossible since `e_required = 0.5 × deficit × 0 = 0`, which is always ≤ stale SoC.

TC-GT2-A through TC-GT2-E pass correctly — they test corruption injection/clamping logic, not contingency physics.

**Proposed fix (not applied):** Increase `_N_WARMUP_TICKS` to ≥ 70 (= hot_start_s/dt + margin) or pre-force turbines to `TurbineState.SYNCHRONISED` in the fixture.

---

## d10 hot_start_s regression (Item 4)

`test_d10_demo_20mw_bess_fires_and_tapers` (in `test_formulas.py`): the §7.2 "fire then taper" arc assumed the turbine synchronises and ramps within the 60-tick (300 s) window. Catalogue migration raised `hot_start_s` to 300 s; turbine stays in STARTING state throughout — `turb_out = 0`, taper condition never met.

The sub_msl_surplus_mw hypothesis was refuted: `sub_msl_surplus = 0` throughout (turbine never SYNCHRONISED at MSL).

**Why:** Catalogue start-time increase was for realism (a gas turbine takes 5 min to synchronise). The §7.2 measurement window did not grow to match.

**Secondary:** Droop runaway (Item 1) drives `bess_setpoint_mw` to thousands of MW in d10, but BESS output is correctly capped at rated 5 MW. The two issues are independently caused.
