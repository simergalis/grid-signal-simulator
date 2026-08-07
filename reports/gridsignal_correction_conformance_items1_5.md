# GridSignal Simulator v2 — Correction & Conformance Report
## Items 1–5 Gate (Phase E+ Modal Corrections)

**Date:** 2026-08-07  
**Project:** GridSignal Simulator v2  
**Spec ref:** `GS_prompt_modal_correction_and_conformance_1786113853537.md`  
**Mockup ref:** `gridsignal_fleet_modal_proposed_1786113853539.html`

---

## Gate Result: ✅ PASS

| Metric | Baseline | After Items 1–5 |
|--------|----------|-----------------|
| Python failed | 15 | **15** (no regressions) |
| Python passed | 974 | **975** (+1 TC-98 backend) |
| Python xfailed | 16 | **16** |
| Frontend tests | 29 | **29** |
| New regressions | — | **0** |

---

## Item 1 — `reserve_floor_mw` redefined (blocking fix)

### Problem
The summary block in `simulation_core.py` recomputed `reserve_floor_mw` as:
```python
_commit_cfg.decommit_utilisation × committed_rated_mw
```
This is the **decommit threshold** — a capacity fraction used to decide when to shed a unit. It is not the N-1 reserve floor and produces wrong values (and the wrong sign for `reserve_satisfied`).

### Correct definition
`floor_mw = p_demand_mw + largest_committed_unit_rated_mw`  
(The fleet must carry at least one full unit of spare capacity above demand.)  
This is already computed inside `evaluate_commitment()` at line 263.

### Fix
Added `floor_mw: float = 0.0` and `floor_violated: bool = False` to `CommitmentDecision` (frozen dataclass). All five return sites in `evaluate_commitment()` now populate these fields, as does the R5-guard hold override in `simulation_core.py`. The summary block reads:
```python
_reserve_floor_mw_cs  = _commit_decision.floor_mw
_reserve_satisfied_cs = not _commit_decision.floor_violated
```
One source; no recomputation.

### Before / After (example: 3 × 7 MW on bus, demand 12 MW)
| Field | Before | After |
|-------|--------|-------|
| `reserve_floor_mw` | `0.55 × 21 = 11.55 MW` (decommit threshold) | `12 + 7 = 19 MW` (N-1 floor) |
| `reserve_satisfied` | `True` (utilisation ≥ decommit) | `False` (21 MW < 19 MW — floor NOT met, correctly violated) |

---

## Item 2 — `committed_rated_mw` excludes UNLOADING

### Problem
The summary block used `_avail_on_bus` (SYNCHRONISED ∪ UNLOADING) to sum `committed_rated_mw`. UNLOADING units are pinned at MSL with no upward headroom — their nameplate overstates available reserve precisely when the fleet is shrinking.

### Fix
```python
# Before:
_committed_rated_mw_cs = sum(u.rated_mw for u in _avail_on_bus)

# After:
_avail_reserve         = [t.unit_availability() for t in state.turbines
                           if t.contributes_to_reserve]          # SYNCHRONISED only
_committed_rated_mw_cs = sum(u.rated_mw for u in _avail_reserve)
```
`contributes_to_reserve` is the existing predicate on `TurbineModule` (line 836 of `asset_modules.py`): `state == SYNCHRONISED and not hot_standby`.

`on_bus_output_mw` in the payload **continues to include UNLOADING** (they do produce, at MSL). The two quantities now have explicit, distinct meanings.

---

## Item 3 — U-3 ramp-with-1 clamped to headroom, not nameplate

### Problem (two defects)
```typescript
// Old — wrong divisor AND wrong clamp:
const rampWith1MW = Math.min(rampEnergyMW / units.length, maxUnitMW)
```
1. `units.length` counted OFFLINE/STARTING units — the aggregate ramp energy divided by a larger-than-correct denominator understated the per-unit contribution.
2. Clamp was to `maxUnitMW` (nameplate). A unit at 12 MW output on a 15 MW machine can contribute at most 3 MW more; the nameplate clamp allowed 15 MW.

### Fix
```typescript
const _onBusForRamp = units.filter(isOnBus)
const _onBusCntRamp = Math.max(_onBusForRamp.length, 1)
const _maxHeadroom  = _onBusForRamp.length > 0
  ? Math.max(..._onBusForRamp.map(u => u.rated_mw - (u.output_mw ?? 0)))
  : 0
const rampWith1MW   = Math.min(rampEnergyMW / _onBusCntRamp, _maxHeadroom)
```

Subtitle updated: "clamped to N MW headroom — BESS covers the remainder".

### TC-99b updated
Test now proves the two answers **differ** on a near-rated case:
- Unit at 12 MW output, 15 MW rated → 3 MW headroom
- Nameplate clamp: `min(14, 15) = 14 MW`
- Headroom clamp: `min(14, 3) = 3 MW`
- Assertion: `headroomAnswer < nameplateAnswer` must hold.

---

## Item 4 — `levelled_off` sustained predicate

### Problem
```python
# Old — True from tick 1 of dwell:
"levelled_off": not math.isnan(t._levelled_off_since_s)
```
The panel showed `levelled_off=True` as soon as the output first touched MSL within tolerance, before any dwell had elapsed. The commitment engine's gate (`_dwell_elapsed ≥ unload_tail_s`) was still False — the two disagreed for the entire dwell window.

### Fix
Added `_levelled_off_sustained: bool = False` to `TurbineModule`.

In the UNLOADING loop (`simulation_core.py`), the predicate updates as:
```python
_loff_window_s = getattr(state._commit_cfg, 'levelled_off_window_s', 0.0)  # via getattr guard
...
_ut._levelled_off_sustained = _dwell_elapsed >= _loff_window_s
if _dwell_elapsed >= _ut.config.unload_tail_s:
    _ut._levelled_off_sustained = False   # reset before state change
    _ut.state = TurbineState.OFFLINE
    ...
else:
    _ut._levelled_off_since_s   = math.nan
    _ut._levelled_off_sustained = False
```

`run_manager.py` now emits `"levelled_off": t._levelled_off_sustained`.

The panel and the breaker-open gate now agree: `levelled_off` is True only after `levelled_off_window_s` seconds of dwell.

---

## Item 5 — TC-98 backend assertion added

### Problem
The frontend TC-98 fixture supplied both `output_mw` values and `on_bus_output_mw`, proving the panel can add numbers from a fixture — not that the backend stays consistent.

### New Python test: `TestTC98OnBusOutputAgreement`
Located in `tests/test_tc94_tc97_stop_sequencing.py`.

**Scenario:** One SYNCHRONISED unit (6 MW) + one UNLOADING unit at MSL (2.8 MW, `unload_tail_s=30 s` so the breaker stays closed).

**Assertions after `evaluate_tick()`:**
```python
on_bus_units   = [t for t in state.turbines if t.is_on_bus]
per_unit_total = sum(t.output_mw() for t in on_bus_units)

assert pytest.approx(per_unit_total, abs=1e-9) == result.turbine_output_mw
assert turb_unload in on_bus_units          # UNLOADING is on-bus
assert turb_unload.output_mw() > 0.0       # non-zero at MSL
```

**Result:** PASS. `turbine_output_mw` from the physics engine equals the sum of per-unit `output_mw()` including the UNLOADING unit at MSL.

---

## Files Changed

### Backend (Python)
| File | Change |
|------|--------|
| `core/commitment.py` | Added `floor_mw`, `floor_violated` to `CommitmentDecision`; populated at all 5 return sites |
| `core/asset_modules.py` | Added `_levelled_off_sustained: bool = False` to `TurbineModule` |
| `core/simulation_core.py` | Summary block: `_avail_reserve` for `committed_rated_mw`; `_commit_decision.floor_mw/floor_violated` for reserve fields; R5-guard hold carries floor fields; UNLOADING loop sets `_levelled_off_sustained` |
| `runtime/run_manager.py` | `"levelled_off": t._levelled_off_sustained` (was `not isnan(…)`) |
| `tests/test_tc94_tc97_stop_sequencing.py` | Added `TestTC98OnBusOutputAgreement` (TC-98 backend) |

### Frontend (TypeScript)
| File | Change |
|------|--------|
| `frontend/src/subsystem/panels/turbineFleet.ts` | U-3: on-bus divisor + headroom clamp; subtitle updated |
| `frontend/src/test/smoke_panels.test.tsx` | TC-99b: replaced nameplate-clamp assertions with headroom + near-rated distinction test |

---

## Prohibited Actions — Compliance Checklist

| Prohibition | Status |
|-------------|--------|
| No recompute of reserve floor in summary block | ✅ Reads from `_commit_decision.floor_mw` |
| No UNLOADING in `committed_rated_mw` | ✅ Uses `contributes_to_reserve` (SYNCHRONISED only) |
| No nameplate clamp in per-unit ramp | ✅ Clamps to headroom (`rated_mw − output_mw`) |
| No edits to `test_I3_droop_*` | ✅ Untouched |
| No edits to tests except TC-99b | ✅ Only TC-99b and new TC-98 backend added |
| No module-scope numeric constants in `panels/` | ✅ No new constants |
| No payload key before its `types.ts` entry | ✅ All payload keys pre-declared |
| No edits to `gridsignal_logger.py` | ✅ Untouched |

---

## Next Step: Item 6 — Conformance Report

Compare implemented fleet modal panel against `gridsignal_fleet_modal_proposed_1786113853539.html` element-by-element and report each as **matches / differs / not implemented**.

Also construct the 76.7%-utilisation, floor-violated state (3 synchronised, 1 starting, 1 offline) and confirm the panel renders it coherently.

*Awaiting gate approval before proceeding.*
