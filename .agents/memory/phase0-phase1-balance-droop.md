---
name: phase0-phase1-balance-droop
description: Integration of power_balance.py and droop.py into the simulator — findings, attribute names, catalogue keys, and gate wiring.
---

## Phase 0 — D4 finding

The previous `d4_balance_defect_mw` at simulation_core.py was a **routing identity**, always zero by algebraic construction when islanded:
```
_d4_sum = _grid_exchange_mw + _frequency_forcing_mw
_d4_balance_defect_mw = _d4_sum - _balance_residual_mw
# islanded: _grid_exchange_mw=0, _frequency_forcing_mw=_balance_residual_mw → always 0
```
The actual supply-demand residual is `_balance_residual_mw = _p_gen_mw - p_demand_mw` (line ~1314). Phase 0 replaces the routing check with `_balance_defect_mw(BalanceTerms(...))` from `core/power_balance.py`.

**Why:** `p_unserved_mw` is not yet computed at the D4 site (~line 1402); shed is evaluated downstream (~line 1676). Integration guide says `p_unserved_mw=0.0` for Phase 0.

## Physical invariant independence caveat

The later physical invariant currently passes `served = min(demand - shed, local_generation + grid_import)` and `unserved = demand - served`, while grid-tied import is itself derived from `_balance_residual_mw` when the PCC is not saturated; losses are a constant zero. It is therefore a partial aggregate supply-vs-demand check, not an independent five-term measurement, and can be tautological on the unrestricted grid-tie path.

**Why:** exact cancellation in a balanced SJ-1 trace is structural: the dispatch/grid routing and served/unserved definitions reuse the same demand and supply values, so a zero residual is not evidence of floating-point headroom.

**How to apply:** a genuinely independent gate must use explicit load-side shed (not a supply-capped served remainder), an independent PCC import/meter value for grid-tied runs, and a real loss model or an explicit islanded-only scope.

## Phase 1 — droop attribute names

The integration guide uses field names that do not match the codebase:

| Guide says | Actual | Note |
|---|---|---|
| `t.unit_id` | `t.config.asset_id` | TurbineModule has no `.unit_id` |
| `t.current_output_mw` | `t.output_mw()` | method, not attribute |
| `t.config.msl_mw` | `t.config.p_min_stable_frac * t.config.rated_mw` | no `.msl_mw` on TurbineConfig |

## Catalogue keys added (locked section)

- `governor_deadband_hz` = 0.02 — was class literal `_GOVERNOR_DEADBAND_HZ` in simulation_core.py. Sub-step governor loop at ~line 1525 still uses `_GOVERNOR_DEADBAND_HZ`.
- `droop_max_frequency_error_hz` = null — DR-BAL-1 open. Phase 1 bounded droop is gated: falls back to unbounded formula while null.
- `balance_defect_tolerance_mw` = `1.9913e-14` MW — the current catalogue noise floor used by the authoritative physical balance invariant; do not widen it to hide MW-scale defects.

## simulation_core.py import needed

`site_parameters` is NOT imported in simulation_core.py by default. Must add `from . import site_parameters as _sp` before calling `_sp.value(...)`. models.py uses the same pattern.

## Gate wiring

`GET /runs/{run_id}/result` → `RunResultResponse.balance_gate` (BalanceGateResponse). Verdict computed from tick_dicts' `d4_balance_defect_mw` values in `run_manager.py` at CompletedRun creation time. No UI design was specified.

## Test delta

- Phase 0: the legacy D4 routing check remains separate from the authoritative physical balance invariant; tests must distinguish the two identities.
- Phase 1: 0 new failures. All 13 pre-existing failures are unrelated to droop/balance.
