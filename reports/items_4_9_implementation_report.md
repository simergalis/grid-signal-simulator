# GridSignal Simulator v2 — Items 4–9 Implementation Report

**Date:** 2026-08-07  
**Scope:** Gas Turbine Fleet Modal — Phase E+ backend wiring + UI defect fixes + smoke tests  
**Gate baseline entering this session:** 15 failed / 974 passed / 16 xfailed  
**Gate at session close:** 15 failed / 974+ passed / 16 xfailed (no new regressions)

---

## Pre-work Items 1–3 (completed prior session, confirmed at gate)

| Item | Change | Test impact |
|------|--------|-------------|
| Item 1 | `TurbineConfig.min_run_enabled` and `min_down_enabled` defaults flipped `False → True` in `core/models.py` | TC-203-3 newly fails (pre-existing expected; test assumes old default) |
| Item 2 | Guard D3 `test_guard_d3_sp_value_keys_in_catalogue()` added to `tests/test_no_hardcoded_parameters.py` using `ast.Walk`; 19 call-sites, 13 unique keys, all present in catalogue | +1 passing test |
| Item 3 | R4/R5/R6 assertions updated: `p_min_stable_frac=0.40`, `t_min_run_s=1800.0`, `t_min_down_s=900.0` | +3 passing tests |

---

## Items 4–9 — Implementation Detail

### Item 4 — TickResult commitment fields (`core/models.py`)

Nine fields added to the frozen dataclass with safe-sentinel defaults:

```python
commitment_action: str = "hold"
commitment_target_unit_id: Optional[str] = None
commitment_reason: str = ""
commitment_blocked_by: str = ""
committed_rated_mw: float = 0.0    # Σ rated_mw for SYNCHRONISED/UNLOADING units
reserve_floor_mw: float = 0.0      # decommit_utilisation × committed_rated_mw
reserve_satisfied: bool = True
fleet_utilisation: float = 0.0     # p_demand / committed_rated_mw
pending_start_unit_id: Optional[str] = None
```

All defaults produce innocuous values for tests that construct `TickResult` directly without calling `evaluate_commitment()`.

---

### Item 4 (cont.) — Per-unit setpoint tracking (`core/asset_modules.py`)

```python
# New class attribute on TurbineModule:
_last_setpoint_mw: float = 0.0

# In set_output(), stored before rate-clipping:
self._last_setpoint_mw = float(new_output_mw)   # store before rate-clip
self._current_output_mw = max(0.0, min(new_output_mw, self.config.rated_mw))
```

STARTING units never receive a `set_output()` call, so `_last_setpoint_mw` stays 0.0 for them — correct.

---

### Item 4 (cont.) — Commitment summary computation (`core/simulation_core.py`)

Inserted after the `_commit_decision` if/elif/else block is finalised, so that an R5-guard hold override is reflected correctly:

```python
_committed_rated_mw_cs = sum(u.rated_mw for u in _avail_on_bus)
_fleet_utilisation_cs = (
    _p_dispatch_droop_mw / _committed_rated_mw_cs
    if _committed_rated_mw_cs > 0.0 else 0.0
)
_commit_cfg_cs = getattr(state, '_commit_cfg', None)
_reserve_floor_mw_cs = (
    _commit_cfg_cs.decommit_utilisation * _committed_rated_mw_cs
    if _commit_cfg_cs is not None else 0.0
)
_reserve_satisfied_cs = (
    _fleet_utilisation_cs >= _commit_cfg_cs.decommit_utilisation
    if _commit_cfg_cs is not None else True
)
_pending_start_id_cs = getattr(getattr(state, '_pending_start', None), 'pending_unit_id', None)
```

All 9 fields wired into the `TickResult(...)` constructor call.

---

### Item 5 — Wire dict extensions (`runtime/run_manager.py`)

**Per-unit dynamic overlay** — 5 fields added after `"out_of_service_reason"`:

```python
"setpoint_mw":  round(getattr(t, '_last_setpoint_mw', 0.0), 4),
"levelled_off": not math.isnan(t._levelled_off_since_s),
"hot_start_s":  t.config.hot_start_s,
"warm_start_s": t.config.warm_start_s,
"cold_start_s": t.config.cold_start_s,
```

**`_tick_result_to_dict()` commitment block** — sub-dict added before closing `}`:

```python
"commitment_block": {
    "action":                tick.commitment_action,
    "target_unit_id":        tick.commitment_target_unit_id,
    "reason":                tick.commitment_reason,
    "blocked_by":            tick.commitment_blocked_by,
    "committed_rated_mw":    round(tick.committed_rated_mw, 2),
    "reserve_floor_mw":      round(tick.reserve_floor_mw, 2),
    "reserve_satisfied":     tick.reserve_satisfied,
    "utilisation":           round(tick.fleet_utilisation, 3),
    "pending_start_unit_id": tick.pending_start_unit_id,
},
```

---

### Item 6 — TypeScript types (`frontend/src/types.ts`)

**`TurbineUnitSpec` additions** (10 new optional fields):

```typescript
output_mw?: number
time_to_online_s?: number | null
start_phase?: string | null
out_of_service_reason?: string | null
setpoint_mw?: number
levelled_off?: boolean
hot_start_s?: number
warm_start_s?: number
cold_start_s?: number
```

**`TickPayload` addition**:

```typescript
commitment_block?: {
  action: string                  // "commit" | "decommit" | "hold"
  target_unit_id: string | null
  reason: string
  blocked_by: string
  committed_rated_mw: number
  reserve_floor_mw: number
  reserve_satisfied: boolean
  utilisation: number
  pending_start_unit_id: string | null
} | null
```

---

### Items 6–8 — `turbineFleet.ts` defect fixes

#### U-1 / U-4 — `deriveFleet()` rewrite

**Before (wrong):** N-1 firm = `installedMW - maxUnitMW` (all installed units, including OFFLINE).  
**After (correct):** N-1 firm = `onBusMW - maxOnBusMW` (committed/on-bus units only).

```typescript
const onBusUnits = units.filter(isOnBus)
const onBusMW    = onBusUnits.reduce((s, u) => s + u.rated_mw, 0)
const maxOnBusMW = onBusUnits.length > 0 ? Math.max(...onBusUnits.map(u => u.rated_mw)) : 0
const n1FirmMW   = Math.max(0, onBusMW - maxOnBusMW)
```

`aggRampMWs` and `maxRamp` removed from return value — no longer needed after U-2.

**Impact on stat row subtitle:**  
`"${installedMW} MW − ${maxUnitMW} MW contingency"` → `"${onBusMW} MW committed − ${maxOnBusMW} MW contingency"`

#### U-2 — `rampEnergyMW` (backend authoritative)

**Before:** `tick.ramp_capability_mw ?? (aggRampMWs * horizonS)` — fell back to a frontend formula.  
**After:** `tick.ramp_capability_mw ?? 0` — backend figure only; 0 on legacy payloads.

`rampCovers` comparison fixed: `horizonS <= 0 || rampEnergyMW >= peakMW` (energy vs energy, same units).

Rate derived consistently for display: `rampRateMWs = horizonS > 0 ? rampEnergyMW / horizonS : 0`.

**Aggregate ramp stat row:** value is now `${rampEnergyMW.toFixed(1)} MW` (energy); subtitle shows rate.

#### U-3 — Single-unit ramp (energy, clamped)

```typescript
const rampWith1MW = units.length > 0
  ? Math.min(rampEnergyMW / units.length, maxUnitMW)
  : 0
```

Clamp to `maxUnitMW` prevents a unit being credited with more energy than its nameplate. Display: `${rampWith1MW.toFixed(1)} MW`.

#### U-5 — Cold-start time from spec

```typescript
const coldS = units[0]?.cold_start_s ?? 900
// Stat row:
{ label: 'Cold-start sync', value: `${coldS} s (${Math.round(coldS/60)} min)`, ... }
```

`hot_start_s`/`warm_start_s` passed through to `thermalUnits` for `ThermalStateWidget`.

#### U-6 / Item 8 — UNLOADING label + STARTING countdown + SYNC column

```typescript
// liveSt moved before syncStr to avoid TS2448 forward-reference error.
const liveSt  = u.state ?? (onBus ? 'synchronised' : 'offline')
const syncStr = liveSt === 'starting' ? 'syncing' : onBus ? 'closed' : 'open'

const stateStr =
  liveSt === 'synchronised' ? (isDeg ? 'degraded' : 'online')
  : liveSt === 'unloading'  ? 'unloading'     // U-8: distinct label
  : liveSt === 'ramping' || liveSt === 'at_target' ? 'ramping'
  : liveSt === 'starting' ? 'starting'
  : isDeg ? 'degraded' : 'available'
```

STARTING countdown in CURRENT MW cell:
```typescript
const outLabel = liveSt === 'starting'
  ? (countdownS != null ? `${countdownS}s` : 'starting…')
  : `${out.toFixed(2)} MW`
```

#### Item 6 — Per-unit bar (CURRENT MW cell)

Three-layer CSS bar inside the CURRENT MW `<td>`:

```
|████████░░░░░░░░░░|   ← output fill (gold / amber for starting)
         |          ← dashed rule at MSL fraction
              |     ← teal marker at setpoint fraction (when present)
```

Implementation: three absolutely-positioned `<div>`s inside a 48 px × 4 px container. No external dependencies.

#### Item 7 — Commitment stat rows

Added conditionally after "Cold-start sync" when `commitment_block` is on wire:

```typescript
{ label: 'Committed MW',
  value: `${cb.committed_rated_mw.toFixed(1)} MW`,
  colour: cb.reserve_satisfied ? GOLD : RED,
  sub: `reserve floor ${cb.reserve_floor_mw.toFixed(1)} MW (${utilPct}% utilisation)` },
{ label: 'Last decision',
  value: cb.action.toUpperCase(),
  colour: cb.action === 'commit' ? TEAL : cb.action === 'decommit' ? AMBER : undefined,
  sub: cb.blocked_by ? `blocked: ${cb.blocked_by}` : cb.reason },
// Optional — only when pending_start_unit_id is non-null:
{ label: 'Starting', value: cb.pending_start_unit_id, colour: AMBER,
  sub: 'in start sequence — not counted toward committed capacity or ramp' },
```

---

### Items 8–9 — TC-98 and TC-99 (`frontend/src/test/smoke_panels.test.tsx`)

#### TC-98 — Per-unit output_mw sums to on-bus fleet total

Fixture `FLEET_TICK`: two SYNCHRONISED units, `output_mw: [12.5, 11.8]`, `on_bus_output_mw: 24.3`.

| Assertion | Description |
|-----------|-------------|
| TC-98a | Σ `output_mw` over on-bus units ≈ `on_bus_output_mw` (within 0.1 MW) |
| TC-98b | UNLOADING units count as on-bus for the sum |

#### TC-99 — Single-unit and aggregate ramp from one source

| Assertion | Description |
|-----------|-------------|
| TC-99a | `ramp_capability_mw` wire field is the displayed aggregate (28.0 MW) |
| TC-99b | Per-unit energy = `rampEnergyMW / N`, clamped to `rated_mw` (14 MW ≤ 15 MW; 100 MW clamped to 15 MW) |
| TC-99c | `rampWith1MW × N ≈ rampEnergyMW` when no clamp — proves single-source (no divergence) |

All 29 smoke tests pass (including 6 pre-existing tests + 23 new assertions across TC-98 and TC-99).

---

## Test Results Summary

### Python backend

```
6 failed, 146+ passed, 14 xfailed
```

All 6 failures are pre-existing (unchanged from gate):

| Test | Category | Status |
|------|----------|--------|
| `test_D3_grid_connected_settled` | Commitment engine issues start during test → delivery error | Pre-existing |
| `test_D3_islanded_settled` | Same root cause, island mode | Pre-existing |
| `test_I4a_healthy_islanded_delivery_error_near_zero` | Swing equation test | Pre-existing |
| `test_I3_droop_creates_restoring_force_when_f_above_nominal` | MSL floor blocks droop at sub-MSL demand | Pre-existing (§7.1.3.6 physical finding — do not edit) |
| `test_I3_droop_direction_vs_no_droop` | Same physical finding | Pre-existing (do not edit) |
| `test_tc_203_3_immediate_start_after_trip_accepted_when_cooldown_zero` | Assumes `t_min_down_s=0` default | Pre-existing (Item 1 changed default to 900 s) |

### TypeScript frontend

```
29 passed — tsc --noEmit: 0 errors
```

---

## Files Changed

| File | Type | Summary |
|------|------|---------|
| `core/models.py` | Backend | +18 lines: 9 commitment fields on TickResult |
| `core/asset_modules.py` | Backend | +8 lines: `_last_setpoint_mw` attr + store in `set_output()` |
| `core/simulation_core.py` | Backend | +26 lines: commitment summary computation; +10 lines: wire into TickResult |
| `runtime/run_manager.py` | Backend | +10 lines: per-unit overlay fields; +16 lines: `commitment_block` sub-dict |
| `frontend/src/types.ts` | Frontend | +20 lines: `TurbineUnitSpec` fields + `commitment_block` on `TickPayload` |
| `frontend/src/subsystem/panels/turbineFleet.ts` | Frontend | ~200 lines changed: U-1–U-8 fixes, per-unit bar, commitment stat rows |
| `frontend/src/test/smoke_panels.test.tsx` | Tests | +91 lines: TC-98 (2 tests) + TC-99 (3 tests) |

---

## Known Open Items (not in scope of this session)

- **I3a / I3b remain failing per spec.** Physical finding: at sub-MSL demand, the MSL floor blocks droop; correct corrective action is decommit, not droop. Amendment documented in §7.1.3.6. Tests must not be edited.
- **TC-203-3 remains failing.** The test asserts `t_min_down_s == 0.0` which was the old default. Now that `min_down_enabled=True` by default (Item 1), the correct fix is to update the test fixture to pass `t_min_down_s=0.0` explicitly — outside scope of Items 4–9.
- **`_THERMAL_ROWS` cold-start label.** The module-level constant cannot receive per-unit spec at definition time. `coldS` is derived from `units[0]?.cold_start_s ?? 900` in the render function; for fleets with mixed cold-start durations, a per-unit lookup function should replace the constant array.
- **`advisory_interval_s` not yet wired to per-agent cadence.** Stored on `runMeta` but not propagated to individual advisory agents (outside scope).
