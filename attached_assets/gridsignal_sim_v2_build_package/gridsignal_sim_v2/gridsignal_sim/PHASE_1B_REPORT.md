# Phase 1b — Continuous Loading Layer: Implementation Report

## Summary

Phase 1b adds the **continuous loading layer** (`core/loading.py`) that replaces
the ad-hoc advance()-based setpoint tracking for canonical SYNCHRONISED units.  
The loading layer solves four correctness problems from the pre-Phase-2 path:
- Setpoints were applied incrementally via `advance()` with no fleet-level coordination.
- `ramp_capability_mw` was capped by an ad-hoc installed-MW guard in the frontend (now removed).
- No sub-MSL surplus signal existed to expose floor-rounding gaps to the frontend.
- `balance_residual_mw` was silently absorbing dispatch errors rather than exposing them.

---

## Acceptance Criteria — Result

| ID | Criterion | Result |
|----|-----------|--------|
| P1b-1 | `compute_loading_setpoints()` is pure and order-independent (TC-77) | **PASS** — 4 subtests |
| P1b-2 | `apply_loading()` terminates on any fleet size including sub-MSL case (TC-78) | **PASS** — 2 subtests |
| P1b-3 | `ramp_capability()` clamps correctly: headroom dominates at 90% output, ramp dominates near zero (TC-79) | **PASS** — 3 subtests |
| P1b-4 | STARTING unit contributes zero ramp credit before timer expires, full credit at expiry (TC-80) | **PASS** — 4 subtests |
| P1b-5 | `ramp_capability_mw` present in `TickResult` and WS broadcast dict | **PASS** — `test_new_fields_present_in_ws_dict` |
| P1b-6 | `sub_msl_surplus_mw` present in `TickResult` | **PASS** |
| P1b-7 | `balance_residual_mw` removed from `TickResult` and wire dict (Branch B) | **PASS** — `test_D4_*` and `test_new_fields_present_in_ws_dict` |
| P1b-8 | Backward compat: RAMPING/AT_TARGET units still use `advance()`, not the loading layer | **PASS** — B1a regression passes |

Total Phase 1b tests: **24** (TC-77 × 4, TC-78 × 2, TC-79 × 3, TC-80 × 6, TC-81 × 9)

---

## Implementation Decisions

### Allocated Set A = `SYNCHRONISED` state only
The loading layer filter in `simulation_core.py` uses `t.state == TurbineState.SYNCHRONISED`,
**not** `t.is_synchronised` (which would include RAMPING/AT_TARGET).  RAMPING and AT_TARGET
are pre-Phase-2 aliases that continue to use `advance()` for their ramp mechanism.  This
preserves backward compatibility with all existing scenarios and tests.

**Why this matters:** Using `t.is_synchronised` in the filter caused B1a to fail — the turbine
delivered exactly its setpoint in one tick because both the loading layer AND `advance()` applied,
doubling the ramp step.  Allocated set A = SYNCHRONISED only is the correct invariant.

### `LEAD_WINDOW_S = 45.0` (chosen)
The 45-second lead window for `ramp_capability()` is a design constant (`core/loading.py`),
not measured from any specific fleet.  Future calibration against turbine OEM data should
update this constant and bump the associated test expectations.

### `ramp_capability()` includes STARTING units
A STARTING unit whose `time_to_online_s < LEAD_WINDOW_S` contributes
`r_asset_mw_per_s × (LEAD_WINDOW_S − time_to_online_s)` to the ramp credit.
A unit that won't come online within the window contributes zero.
Hot-standby units are excluded.

### D4 inline assertion (Branch B)
The Branch B pre-work asserts:
```python
assert (
    abs((turbine_output + bess_output + p_renewable) - (p_total + grid_exchange + frequency_forcing + model_error + sub_msl_surplus))
    < 1e-3
), "D4: power balance identity violated"
```
This fires in the middle of `evaluate_tick()`, not as a test.  It will catch any future
changes that break the channel decomposition immediately at runtime (not just in CI).

---

## Spec Contradictions Found

### Contradiction 1: `ramp_capability()` window vs dispatch lead time
The spec (`§7.3`) defines a 45-second lead window as the "example" value.  The dispatch
arbitrator uses a runtime `dt_lead_seconds` computed per tick.  The two values are
independent — `ramp_capability()` uses the fixed constant while the dispatch uses the
computed lead time.  They may diverge if run duration or Kube signal changes the effective
lead.  **The spec does not address this potential mismatch.**

Resolution chosen: `LEAD_WINDOW_S = 45.0` is the constant used in the frontend tile
(spec `§9.2 turbine ramp credit tile`) and `ramp_capability_mw` in `TickResult`.  The
dispatch arbitrator's own ramp accounting continues to use its runtime `dt_lead_seconds`.

### Contradiction 2: sub-MSL surplus semantics
`sub_msl_surplus_mw` is documented as a gap that occurs when `P_allocated < Σmsl_i`.  But
in practice `apply_loading()` enforces the MSL floor (turbines are set to at least `msl_mw`),
so the surplus is the difference between floor-enforced output and the demanded fleet setpoint.
The spec does not explicitly call this field out as a frontend signal — it was added to surface
the gap to the telemetry dashboard (Phase TBD).

---

## Out-of-Scope Temptations Rejected

1. **Migrating `dispatch.py` `stage_for_predicted_step()` to use `UnitAvailability`** for the
   full dispatch loop (not just ramp credit).  The staging call (`turbine.stage_target()`) must
   remain on `TurbineModule` since it mutates turbine state.  Only the *credit formula* was
   extracted as `turbine_ramp_credit_mw()`.

2. **Implementing exponential backoff in the Kube oscillation path** — `test_power_cap_toggle_count_within_300s`
   is an intentionally-red test documenting the known §6.2 oscillation issue.  Fixing it is
   a separate task; Phase 1b does not touch the Kube agent.

3. **Removing the legacy `stage_target()` / `advance()` path** for RAMPING/AT_TARGET.  These
   must coexist until all scenarios are migrated to emit SYNCHRONISED-state turbines.  Forced
   migration would break all existing test scenarios in a single step.

4. **Adding a `P_allocated` vs `P_total` discrepancy alert** in the frontend.  The
   `sub_msl_surplus_mw` field is now available in `TickResult`, but the frontend tile to
   visualise it is deferred to Phase UI-5.

---

## Files Changed

| File | Change |
|------|--------|
| `core/loading.py` | **New** — `compute_loading_setpoints()`, `apply_loading()`, `ramp_capability()`, `LEAD_WINDOW_S` |
| `core/simulation_core.py` | Loading layer call (SYNCHRONISED only), D4 inline assert, `ramp_capability_mw` stamp, `balance_residual_mw` removed |
| `core/models.py` | `TickResult`: `balance_residual_mw` removed; `sub_msl_surplus_mw` and `ramp_capability_mw` added |
| `runtime/run_manager.py` | Wire dict updated: removed `balance_residual_mw`, added `sub_msl_surplus_mw` and `ramp_capability_mw` |
| `frontend/src/types.ts` | Same field changes |
| `frontend/src/subsystem/panels/turbineFleet.ts` | Phase 0.5 cap deleted; reads `tick.ramp_capability_mw` |
| `tests/test_13_2_balance_decomp.py` | `TestD4SumIdentity` rewritten for Branch B (no `balance_residual_mw`) |
| `tests/test_forecast_path.py` | B1a corroboration and key-presence list updated |
| `tests/test_p1b_p2.py` | **New** — TC-77 through TC-81 (24 tests) |
