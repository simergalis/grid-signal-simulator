---
name: start-time-separation
description: warm_start_s was equal to hot_start_s (both 300s); raised warm_start_s to 600s to restore thermal-state distinction. Traps and downstream effects.
---

## Rule
`warm_start_s` (600 s) must remain strictly greater than `hot_start_s` (300 s) and strictly less than `cold_start_s` (900 s). The invariant `hot_start_s < warm_start_s < cold_start_s` is the physical ordering.

**Why:** D-08 fixed hot_start_s at 300 s (frame machines cannot sync in 1 min). When warm_start_s was also 300 s, the WARM thermal classification was decorative — HOT and WARM units synchronised at the same speed. The `warm_threshold_s = 14400 s` sorted units into a WARM bin but produced no different dispatch timing.

**How to apply:** Whenever adding or editing start times in `gridsignal_parameters.json`, verify the ordering. Guard E Tier-1 already enforces `unload_tail_s > levelled_off_window_s`; the ordering of start times is a candidate for Guard E Tier-2 (not yet enforced as a test).

## The 15-failure diagnosis (Group D traps)

**D3/I4a Phase D regression:** Commitment engine assigns `gt_setpoint_mw = demand` to OFFLINE turbines that have been staged but not started. Tests that use `_run_to_settlement()` with an OFFLINE turbine in the fleet will see `asset_delivery_error ≈ −demand` even in "settled" state. Fix: gate gt_setpoint_mw on turbine state == SYNCHRONISED, or pre-synchronise the turbine in the fixture.

**TC-GT2 Phase E (catalogue) regression:** `_N_WARMUP_TICKS = 5` (25 s) was calibrated against pre-catalogue start times. With hot_start_s = 300 s now from catalogue, turbines are never SYNCHRONISED after 25 s warmup. Contingency evaluator hits the `not online` early exit → `time_to_close_s = 0.0` → `e_required = 0` → stale SoC cannot flip energy_test_passes. Fix: increase `_N_WARMUP_TICKS` to cover `hot_start_s + margin` (≥ 70 ticks = 350 s).

**B1a Phase 13.3 + fixture timing:** Signal applied 0.1 s before the measured tick; `_ramp_multiplier(0.1) ≈ 0.025` gives 2.5% TDP, not 100%. Demand = 0.0026265 MW, not ~0.105 MW. Fix: apply signal before tick 0 with enough lead for full ramp.

**ramp_seconds class default:** `GPUModule.ramp_seconds = 120.0` at `asset_modules.py:95` (was 45.0). Tests using `_idle_state()` (not `_make_state()`) inherit this default. `_make_state()` overrides to 1.0, so D3/B1a tests are unaffected by this change. F5 test (`test_internal_elapsed_unaffected_by_f5`) uses `_idle_state()` → affected.

## Commit engine harness pattern
To demonstrate a commit firing:
1. SYNCHRONISED turbines must start from **0 MW output** (not rated) to keep U >> 1 throughout the 30 s confirmation window
2. At least one **OFFLINE turbine** must be in the fleet as the commit target (no OFFLINE unit → action stays 'hold' even at 30/30 s sustained)
3. With this setup: commit fires at tick 5 (sim_t=25 s) — `action='commit'`, `pending_start_unit_id='t3'`, `blocked_by=''`
