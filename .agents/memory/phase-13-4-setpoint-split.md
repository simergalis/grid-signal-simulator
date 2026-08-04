---
name: phase-13-4-setpoint-split
description: Phase 13.4 setpoint/actual split — model_error_mw, binding_constraint, BESS lag tests, standby label fix.
---

## What was built

### New TickResult fields
- `model_error_mw: float = 0.0` — load-model bias observable (B1). Injected via `SiteConfig.load_model_bias_mw`; does NOT flow into dispatch or frequency_forcing.
- `binding_constraint: Optional[str] = None` — "bess_power_saturated" when `bess_setpoint_mw > Σ rated_mw` (B3).

### New SiteConfig field
- `load_model_bias_mw: float = 0.0` — test-only injection hook; represents PUE miscalibration / load-accounting drift.

### Serialization
- Both fields added to `run_manager.py` Phase 13.4 block.
- Both added to `frontend/src/types.ts` TickPayload.

### PlantNode.tsx fix (B4)
- Standby label now gates on `bess_setpoint_mw > 0.1` (the dispatch command), not `bess_output_mw`.
- Prevents "BESS standby" label while battery was moving 18.92 MW in previous incarnation.

## Key design decisions

### model_error_mw does not affect dispatch or frequency
The bias is read as `_model_error_mw = state.site.load_model_bias_mw` and placed ONLY in TickResult. `p_dispatch_required_mw`, `_p_dispatch_droop_mw`, and `_frequency_forcing_mw` are all computed from actual `p_total` — the bias never enters those paths. B1c and B1d tests enforce this directly.

### binding_constraint placement
Computed immediately after `state.arbitrator.tick()` returns `_bess_setpoint_mw`, using `sum(b.config.rated_mw for b in state.bess_units)` inline. This avoids reusing the `_k_bess_rated` variable that is only defined inside the kube_agent block.

### cover_shortfall signature: `power_ceiling_mw` not `ceiling_mw`
The parameter is named `power_ceiling_mw` (not `ceiling_mw`). Tests must use this exact name.

### TurbineModule internals for testing
- Field is `_current_output_mw` (not `_output_mw`).
- `advance()` only runs when `state == TurbineState.RAMPING`.
- To lock a turbine at a fixed output: set `_current_output_mw`, `_target_mw`, and `state = TurbineState.AT_TARGET`.
- Setting `_output_mw` (wrong name) silently creates a new attribute — turbine ignores it.

### _make_state turbine does NOT start pre-ramped
- Turbine starts at 0 MW (TurbineState.OFFLINE or RAMPING from 0).
- For tests needing turbine to cover load: either lock via AT_TARGET + _current_output_mw, or add a large job (for B3) with turbine cold.
- The `_transition_gap_mw` and `pre_staging_engine` are None in _make_state so they don't inflate p_dispatch_required.

### B4b regression scenario
- Seed `bess._prev_output_mw = 5.0` to simulate prior dispatch lag state.
- Lock turbine at AT_TARGET = 20 MW so fleet_shortfall = 0.
- Verify `bess_setpoint_mw = 0` immediately (early return in cover_shortfall when allocated_mw=0).
- Note: bess_output is also 0 (not lagged) because the early return fires before the lag formula.

## Pre-existing failures not caused by Phase 13.4
- test_f5: dt_lead_next_s = 115 vs 40 (GPU ramp_seconds discrepancy) — pre-dates Phase 13.
- test_d10, test_item4: BESS re-fire and 3-tuple unpack — pre-dates Phase 13.
