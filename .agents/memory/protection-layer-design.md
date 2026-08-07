---
name: Protection Layer Design
description: IEEE 1547-2018 Cat I frequency protection thresholds implementation and S9 scenario test design decisions and traps.
---

## The rule

Five optional protection threshold fields on `SiteConfig` (all `Optional[float] = None`):
- `uf_warning_hz` (59.5 Hz), `ufls_stage1_hz` (58.5 Hz), `island_collapse_hz` (57.0 Hz)
- `of_warning_hz` (60.5 Hz), `of_trip_hz` (62.0 Hz)

`None` means disabled — runs with no spec are completely unaffected. Four collapse result fields on `TickResult`: `island_collapsed`, `collapse_reason`, `collapse_tick_index`, `collapse_frequency_hz`.

**Why:** `Optional` avoids any default value that could silently clip a 50 Hz EU/APAC test. A value of `0.0` would collapse every run on tick 1.

## S9 Scenario Test Traps

### TRAP 1 — `hot_standby=True` permanently disables `is_on_bus`
`TurbineModule.is_on_bus = state in (SYNCHRONISED, UNLOADING) and not config.hot_standby`. A hot-standby turbine NEVER registers as on-bus or `contributes_to_reserve`, even when fully SYNCHRONISED. For test assertions that count on-bus units, the 5th GT must be `hot_standby=False` starting OFFLINE (committed by the engine).

### TRAP 2 — Cooling thermal envelope adds 25–28% of compute to net demand
At 50 GPU nodes (51.5 MW compute), cooling reaches ≈14.6 MW by t≈2500 s. True net demand = compute + cooling − solar ≈ 51 MW, not the naïve ≈37 MW (compute − solar only). Failing to account for this causes UF collapse when GT capacity is sized against naïve demand only.

### TRAP 3 — BESS dispatch lag causes persistent UF drift at H=5 s
With the islanded BESS dispatch, whenever BESS must bridge a gap (GT capacity < net demand), there is a ≈1-tick lag between demand changes and BESS output adjustments. Over a 300-second new-GT startup window, this produces a ≈0.018 Hz/s UF drift that easily crosses the 57 Hz collapse threshold. Fix: size GT pre-sync capacity to cover peak demand WITHOUT BESS (no lag → no drift).

### TRAP 4 — GT ramp rate causes OF spike at demand step-down
With `r_asset_mw_per_s=0.5 MW/s`, a 31 MW compute step-down (phase-2c → phase-3) takes 3–4 ticks to absorb. The surplus during those ticks causes a +8 Hz/tick frequency spike (at H=5 s), triggering OF-2 collapse. Fix for test: set `r_asset_mw_per_s=100.0` (effectively instant dispatch) so GTs reach their new setpoint on tick 1.

### TRAP 5 — H=5 s amplifies both drift AND step-change spikes by 20×
Use `inertia_constant_s=100.0` for tests focused on protection thresholds and commitment logic (not ramp dynamics). H=100 s reduces any residual dispatch lag frequency effect to <1 Hz per tick, well within all protection bands.

### TRAP 6 — `p_min_stable_frac > 0` creates unabsorbable surplus with solar
With GTs at MSL > 0 and `bess_output ≥ 0` (BESS cannot charge in this model), the GT MSL output + solar exceeds demand → OF collapse on tick 1. For S9-class islanded tests: set `p_min_stable_frac=0.0`.

## GT commit timing for S9

4 pre-synchronised GTs (60 MW rated): N-1 fails at phase-2b start (50 nodes, net ≈51 MW; 60 < 51+15=66) → GT-05 committed at t≈2400 s. GT-05 is cold (never previously run) → cold_start_s=900 s → online at t≈3300 s (mid phase-2c). This is the A4 signal: `max(units_on_bus in phase-2c) ≥ 5`.

## How to apply

Any islanded scenario test with protection thresholds active should set `inertia_constant_s ≥ 50`, `r_asset_mw_per_s ≥ 10` (or 100 for instant), `p_min_stable_frac=0.0`, and size GT pre-sync capacity against TRUE net demand (compute + cooling − solar), not naïve demand.
