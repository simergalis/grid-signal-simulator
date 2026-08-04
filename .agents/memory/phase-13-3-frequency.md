---
name: phase-13-3-frequency
description: Phase 13.3 swing equation, governor droop, and BESS lag — what was implemented, key traps, and design decisions.
---

## What was built
Phase 13.3 adds governor droop to the islanded simulation and tightens the
swing equation to use `frequency_forcing_mw` ONLY (not +asset_delivery_error).

### Files changed
- `core/simulation_core.py` — droop pre-correction block (before step 4), updated arbitrator call, updated decomposition block, updated swing equation, updated TickResult gt_setpoint_mw, zero-droop guard
- `core/models.py` — BessConfig.bess_response_tau_s added (default 0.05 s); gt_setpoint_mw and asset_delivery_error_mw docstrings updated
- `core/asset_modules.py` — BessModule._prev_output_mw field; first-order lag in cover_shortfall(); import math needed
- `frontend/src/types.ts` — frequency_hz added to TickPayload; comments updated
- `tests/test_13_3_frequency.py` — new file, I1–I5 (8 tests)
- `tests/test_forecast_path.py` — B1a assertion flipped (delivery fault must NOT move frequency); B5 redesigned (solar surplus, not GPU+depleted BESS)

## Key design decisions

### Swing equation: frequency_forcing_mw only
`df/dt = frequency_forcing_mw / (2H × S_base) × f₀`
`asset_delivery_error_mw` is DIAGNOSTIC ONLY — it does not participate in the
swing equation under Phase 13.3. "Model error must not move frequency."

### Governor droop formula
`_droop_correction = −Δf / (droop × f₀) × S_base`
Active: islanded AND |Δf| > 0.02 Hz (deadband) AND droop > 0.
Guard: `droop = 0.0` is explicitly excluded to avoid ZeroDivisionError.

### Droop pre-correction position
`_islanded` and `_s_base_mw` are computed BEFORE `turbine.advance()` (before step 4).
`_p_dispatch_droop_mw` feeds into: `arbitrator.tick()`, `_p_commanded_mw` formula, `_asset_delivery_error_mw` formula, and `gt_setpoint_mw` in TickResult.

### B1a assertion direction flip (Phase 13.3)
Old B1a asserted `frequency_hz != 50 Hz` (delivery fault moves frequency).
New B1a asserts `frequency_hz == 50 Hz` (delivery fault does NOT move frequency —
Phase 13.3 principle). The `frequency_forcing_mw == 0` assertion was also added.

### B5 redesign trap (solar surplus, not GPU+depleted BESS)
The depleted-BESS + slow GPU scenario does NOT produce frequency_forcing > 0 on the
first tick: GPU power is evaluated at PRE-advance ramp_progress=0 (~2.5% TDP =
0.0026 MW), the turbine ramp step of 0.02 MW already covers it, fleet_shortfall=0,
bess_setpoint=0 → frequency_forcing=0. Use solar override for clean forcing tests.

### I3 droop restoring force test — correct scenario
I3 requires a POSITIVE LOAD for droop to create a restoring force (negative
frequency_forcing). With no load and frequency elevated: frequency_forcing = 0 (no
forcing at all). Correct approach: use _make_state(island_mode=ISLANDED) + GPU job,
manually set ramp_progress["job-1"] = 1.0 for full TDP, set _frequency_hz = 52.0,
run one tick → frequency_forcing < 0 → frequency_hz < 52.0.

### BESS lag clamp prevents re-fire artifacts
cover_shortfall: `discharge_mw = max(0, min(lag_output, discharge_target))`.
When target=0 this ALWAYS gives 0 regardless of prev_output, so "taper → stay zero"
behavior is preserved.

### Pre-existing failures not caused by Phase 13.3
- test_item4: 3-tuple unpack of 4-tuple arb.tick() return (Phase 11.3 regression)
- test_d10: BESS re-fires after taper (BESS anchor reserve logic, pre-dates 13.3)
- test_f5: dt_lead_next_s = 115 vs 40 (GPU ramp_seconds discrepancy, pre-dates 13.3)
- test_step8/16/solar_routes HTTP tests: async server state-leak failures on full run;
  each individual test passes when isolated.

## BESS tau reference
- bess_response_tau_s default: 0.05 s (grid-forming inverter, 50 ms)
- gridsignal_logger.py uses 0.3 s (slow droop / legacy UPS class)
- At dt=0.1s, tau=0.05s: alpha ≈ 0.865 (fast convergence per tick)
- At dt=5.0s, tau=0.05s: alpha ≈ 1.0 (instant — no visible lag at 5-second ticks)
