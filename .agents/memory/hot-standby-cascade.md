---
name: hot-standby-cascade
description: How hot-standby turbines are stored and how to cascade-commit them correctly.
---

## Rule
Hot-standby turbines (`config.hot_standby=True`) sit in **OFFLINE** state — not SYNCHRONISED.
The `hot_standby` flag suppresses `is_on_bus` and causes `command_start()` to return immediately.
They are visible in `_avail_offline` (since `t.state == TurbineState.OFFLINE`) but the
commitment engine skips them (does not select them as commit targets).

**Why:** `TurbineModule.state` defaults to `TurbineState.OFFLINE`. Nothing moves hot-standby
units to SYNCHRONISED during initialisation — they stay OFFLINE for the whole run unless
explicitly released. This is not documented; the name "hot standby" implies "warm and ready"
but the state machine treats them identically to cold-offline units.

## How to cascade-commit a hot-standby unit
1. Find it with `t.config.hot_standby and t.state == TurbineState.OFFLINE` — **never `SYNCHRONISED`**.
2. Clear the flag: `t.config.hot_standby = False` (TurbineConfig is a non-frozen `@dataclass`).
3. Call `t.command_start(sim_time)` — now accepted because the early-return guard is gone.
4. Check `t.state == TurbineState.STARTING` and call `state._pending_start.record_start(...)`.
5. Gate the whole block on `state._pending_start.is_empty` so only one unit starts at a time.

## Cascade trigger site
`core/simulation_core.py` — between `_avail_offline` construction and `evaluate_commitment()` call.
`site.cascade_commit_fraction` (Optional[float]) is threaded from `ScenarioSpec` →
`SiteConfig` via `scenario_factory.py`. None = fleet-utilisation trigger only.

## Black-box test
`tests/test_cascade_commit.py` — polls `/runs/{id}/latest-tick`, verifies each unit's
`state` field in `turbine_units` transitions out of "offline" after the lead unit's
`output_mw` crosses `cascade_commit_fraction × rated_mw`.

## What NOT to reuse from the commitment engine path
`evaluate_commitment()` + `command_start()` alone cannot start a hot-standby unit —
`command_start()` returns silently for any unit with `config.hot_standby=True`. The
cascade must clear the flag first. OFFLINE standby units (without `hot_standby`) CAN
go through the normal `force_commit_trigger` → `evaluate_commitment` path.

## Explicit release boundary
Reserved standby turbines must stay out of ordinary capacity commitment. Explicit
fuel-cell, cascade, and contingency-coverage policies may release them.

**Why:** ordinary commitment would preempt the intended BESS → fuel-cell → turbine
sequence before fuel-cell support reaches its configured commitment threshold.

**How to apply:** keep normal demand and reserve rules from consuming standby units;
make each release policy choose readiness deliberately and restore the intended reserve
tiers after it consumes one. The contingency policy re-arms only after a full COVERED
tick, so a single sustained N-1 risk episode releases at most one standby.
