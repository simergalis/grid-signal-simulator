---
name: D14 allocation design
description: Equal-share-then-cap algorithm, power-limited guard pattern, and where each must appear.
---

## Rule
`_proportional_allocations` uses equal-share-then-redistribute, not proportional-by-ceiling.
Guarantee: `sum(allocs) == min(demand, sum(ceilings))` and `allocs[i] <= ceilings[i]`.

**Why:** Proportional-by-ceiling under-uses small units (5 MW unit gets 2.4 MW of a 12 MW demand
alongside a 20 MW unit). Equal-share caps the small unit first and sends surplus to larger units.
The old code relied on D11's `max_sustainable_seconds → 0.0` guard as an implicit power-limit
detector — that is wrong because D11 is a defence-in-depth invariant, not primary logic.

## Power-limited guard — must appear in THREE places
When `peak_shortfall > sum(ceilings)`, the fleet cannot meet demand regardless of stored energy.
After D14 the capped allocation equals the ceiling, so `max_sustainable_seconds(ceiling)` returns
a *finite* positive (endurance at ceiling power) — NOT 0.0. Without the explicit guard, an
over-demand scenario silently appears sustainable.

1. **`stage_for_predicted_step`** — early-return `InsufficientReserveAlert` before endurance check.
2. **`evaluate_tick` bess_bridging_seconds block** — set `bess_bridging_seconds = 0.0` when
   `_binding_demand_mw > sum(_bbs_ceilings)`, before calling `_proportional_allocations`.
3. *(D11 guard in `max_sustainable_seconds` stays)* — defence-in-depth, but must NOT be relied on
   as the primary power-limit signal since capped allocations never exceed the ceiling.

## How to apply
Any future code path that calls `_proportional_allocations` then feeds the result into
`max_sustainable_seconds` must add a `demand > sum(ceilings)` check first.
If it is skipped, a power-limited fleet will silently report finite endurance.

## Naming
Function was renamed from `_proportional_allocations` to `_capped_equal_share_allocations`.
The old name was a lie after D14 — call sites in dispatch.py, simulation_core.py, and tests
all updated. Any future call site must also use `_capped_equal_share_allocations`.

## Tests updated by D14
- `test_item4_small_unit_capped_to_ceiling_under_equal_share` (renamed from
  `test_item4_heterogeneous_fleet_proportional_split`): [2.0,6.0] MW ceilings, demand 4 MW.
  A is capped at 2.0 (100% utilised), B gets 2.0 (33%). Equal MWs from unequal ceilings is
  correct — capping bound for A.
- `test_bess_bridging_seconds_above_power_ceiling_returns_zero`: removed stale fleet_min==0.0;
  replaced with allocs-capped assertion + power-limited pre-condition comment.
- New test: `test_d14_capped_allocation_sum_invariant` — covers demand<ceiling, demand>ceiling,
  and the D14 heterogeneous example ([5,20] fleet, demand=12 → [5,7]).
