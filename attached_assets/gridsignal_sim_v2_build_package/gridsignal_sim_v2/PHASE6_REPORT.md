# GS-DES-CFG-001 Phase 6 — Completion Report

**Date:** 2026-08-06  
**Spec:** Phase 6 — Peak load reconcile: three definitions then declare  
**Status:** ✅ COMPLETE

---

## Summary

Phase 6 reconciled three competing definitions of "peak compute load," added three constants to the locked catalogue, introduced `design_peak_load_mw` as a declared wire field, and switched the fleet modal N-1 checks to use the declared figure instead of the observed run maximum.

---

## Item 1 — `_peak_it_load_mw`: one definition, PUE-inclusive (BLOCKING)

### The defect
`scenario_factory.py:build_run_context` bound `_peak_compute_mw` twice in the same scope:
- **Line 144** (solar sizing): `node_count × rated_kw × pue_base / 1000` — PUE-**inclusive**
- **Line 183** (cooling sizing, rebind): `node_count × rated_kw / 1000` — PUE-**exclusive**

`build_load_test_context` had the same split (lines 270 vs 313). `build_run_context_from_spec` had a third definition — a round-trip at line 642: `solar_rated_mw / 0.25` which accidentally produced a PUE-inclusive figure only because solar was sized from the PUE-inclusive figure.

### Why PUE-inclusive is correct
`simulation_core.py:953` computes `p_compute_mw = Σ nodes × kW × PUE_base / 1000` (PUE-inclusive), and `simulation_core.py:1152` uses `alpha_max × p_compute_mw` for the thermal ceiling. Factory sizing must match the engine's own formula.

### Numeric deltas
| Context | Before | After |
|---|---|---|
| `build_run_context` cooling (600 nodes, 12 kW, pue=1.03, α=0.20, margin=1.15) | 1.656 MW | **1.706 MW** (+49.7 kW) |
| `build_load_test_context` cooling (1000 nodes) | 2.760 MW | **2.843 MW** (+82.8 kW) |
| `build_run_context_from_spec` cooling | no change | no change (round-trip deleted; now computed from workload_events) |

### Fix applied
- Renamed to `_peak_it_load_mw` (one name, PUE-inclusive) across all three factory functions.
- Deleted the rebind at line 183 and line 313.
- Deleted the round-trip at line 642; replaced with direct computation from `workload_events` max node count using the same formula as the factory path; falls back to 20.0 MW when no events present (kube path or idle run).

---

## Item 2 — Three constants catalogued (locked section)

| Key | Value | Unit | Provenance |
|---|---|---|---|
| `cooling_margin` | 1.15 | dimensionless | PROPOSED_HERE — v2.5 PROTO-10 |
| `solar_fraction_of_peak` | 0.25 | dimensionless | PROPOSED_HERE — v2.5 PROTO-7, CHOSEN, no measured basis |
| `bess_anchor_reserve_mw` | 1.0 | MW | CHOSEN — v2.5 §7.1.2 / PROTO-9 |

All three were previously hardcoded literals in `scenario_factory.py`. After cataloguing:
- `_COOLING_MARGIN = 1.15` and inline `1.15` at lines 316 and 645 → `_sp.value("cooling_margin")`
- `0.25` in solar sizings → `_sp.value("solar_fraction_of_peak")`
- `BessConfig.p_anchor_reserve_mw` default → `_sp.value("bess_anchor_reserve_mw")`

Import added to `scenario_factory.py`: `import core.site_parameters as _sp` (module exports bare functions — `from core.site_parameters import site_parameters as _sp` would fail).

---

## Item 3 — `design_peak_load_mw` wire field

**Definition:** declared design peak site load (MW) = `peak_it_load_mw` (IT load at full draw × PUE_base) + `rated_cooling_mw` (alpha_max × peak_it_load_mw × cooling_margin).

**Not** the observed run maximum; the factory sizing point for N-1 and reserve checks.

### Changes
| File | Change |
|---|---|
| `frontend/src/types.ts` | Added `bess_anchor_reserve_mw: number` and `design_peak_load_mw: number` to `TickPayload` (ordered first per gate requirement) |
| `core/models.py` | Added both fields to `TickResult` with catalogue defaults |
| `runtime/run_manager.py` | Added `_design_peak_load_mw: float = 0.0` to `RunContext`; emits both new fields in enrichment block; `bess_anchor_reserve_mw` sourced from grid-forming BESS unit's `p_anchor_reserve_mw`; both added to `_tick_result_to_dict` |
| `api/schemas.py` | Added optional `design_peak_load_mw` to `ScenarioSpec` with documented fallback |
| `gridsignal_parameters.json` | 3 new locked entries; total locked count: 15 → 18 |

---

## Item 4 — Fleet modal N-1 uses declared design peak

### Change
`turbineFleet.ts` main export now computes:
```typescript
const designPeakMW = (tick.design_peak_load_mw ?? 0) > 0
  ? tick.design_peak_load_mw!
  : peakMW  // observed fallback when wire value not yet broadcast
```

`designPeakMW` is passed as the primary argument to `singleUnitPanel` and `fleetPanel`.  
`peakMW` (observed run maximum) is retained as a separate display row. `peakSiteLoadMW()` not deleted.

### What switched to declared design peak
- `n1Covers` check
- `n1MarginPct` calculation
- `rampNeedMWs` calculation
- Verdict string ("declared design peak" label)
- BulletBar red-marker note
- why[] narrative lines

### What kept observed peak
- "Observed peak" stat row (new, added alongside "Design peak load" row)
- N-1 margin sub-label arithmetic display

### `storage.ts` fix (Item 2 side effect)
- Stat row "Anchor reserve": `'1.0 MW'` → `` `${tick.bess_anchor_reserve_mw.toFixed(1)} MW` ``
- why[] live-tick text: `'One megawatt is permanently withheld…'` → uses `tick.bess_anchor_reserve_mw`

---

## Guard results

| Guard | Result |
|---|---|
| D1 — no parameter drift | ✅ PASS |
| D2 — backlog reported | ✅ PASS (informational) |
| E Tier-1 — no module-scope ALL_CAPS in `panels/` | ✅ PASS |
| TypeScript `--noEmit` | ✅ clean |
| Full suite (canonical CWD: `gridsignal_sim/`) | **12 failed / 965 passed** — pre-existing baseline, zero new failures |

Pre-existing failures (never fix): `test_kube_no_oscillation` toggle, `test_demo_pms_column3_tc64_to_tc68`, `test_tc_gt2`, `test_tc_p0_1/2/3/5`.

---

## Files touched

| File | Items |
|---|---|
| `frontend/src/types.ts` | Item 3 — gate (types first) |
| `gridsignal_parameters.json` | Item 2 — 3 new locked entries |
| `core/models.py` | Item 2 — `BessConfig` default; Item 3 — 2 new `TickResult` fields |
| `runtime/scenario_factory.py` | Item 1 — one definition; Item 2 — `_sp.value()` calls; Item 3 — `_design_peak_load_mw`; import added |
| `api/schemas.py` | Item 3 — optional `design_peak_load_mw` on `ScenarioSpec` |
| `runtime/run_manager.py` | Item 3 — `RunContext` field, enrichment, `_tick_result_to_dict` |
| `frontend/src/subsystem/panels/storage.ts` | Item 2 side effect — anchor reserve from wire |
| `frontend/src/subsystem/panels/turbineFleet.ts` | Item 4 — `designPeakMW` for N-1; `observedPeakMW` for display |

---

## Known undeclared (deferred, not in scope)

The 11 undeclared items from Phase 5 remain. Storage.ts:109,117 (anchor reserve `'1.0 MW'`/`'One megawatt'`) were in that list and are now **resolved** by Item 2 side effect. Remaining 9 are unchanged.
