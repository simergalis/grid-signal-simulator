---
name: Parameter Reference System
description: Architecture and decisions for gridsignal_parameters.json, ParameterModal, regression test, and INV-2 compliance.
---

## What was built

1. **gridsignal_parameters.json** — authoritative source, copied to:
   - `gridsignal_sim/gridsignal_parameters.json` (for Python tests)
   - `frontend/src/parameters.json` (TypeScript import by ParameterModal)

2. **`tests/test_worked_example.py`** — 24 regression tests from `worked_example` fixture in JSON. Tests pure arithmetic; no simulation engine needed. All pass.

3. **`core/models.py` SiteConfig** — Added `band_pct_calibrated`, `band_mult_uncalibrated`, `band_mult_unmapped_hw` fields + `reserve_band_upper(is_unmapped_hw)` method.

4. **`core/dispatch.py`** — INV-2 compliance: in `stage_for_predicted_step`, the power check now uses `peak_shortfall_mw × (1 + band_upper)` vs `fleet_power_ceiling`. `band_upper = 0.0` when `band_pct_calibrated = 0` (SiteConfig default) → backward-compatible.

5. **`api/schemas.py` ScenarioSpec** — New optional fields: `dt_thermal_seconds`, `plant_dt_thermal_seconds`, `alpha_max`, `plant_alpha_max`, `tau_seconds`, `plant_tau_seconds`, `anchor_reserve_pct`, `band_pct_calibrated`, `band_mult_uncalibrated`, `band_mult_unmapped_hw`.

6. **`runtime/scenario_factory.py`** — Wires new fields into SiteConfig (with plant-over-engine priority). `anchor_reserve_pct` converts to `p_anchor_reserve_mw = rated_mw × pct / 100` for grid-forming BESS.

7. **`frontend/src/components/ParameterModal.tsx`** — Modal generated from JSON. Split params show PLANT ──🔗── ENGINE columns with link toggle. Provenance dots (green/blue/orange/gray). Locked table at bottom.

8. **`frontend/src/components/ScenarioBuilder.tsx`** — Added `physicsParams` state (default from JSON), "≡ Parameters" button opening ParameterModal, and merges physicsParams into spec on save.

## Key decisions (PROPOSED_HERE → decided here)

- `band_pct_calibrated = 4%`: calibrated × 2.0 = 8% uncalibrated = worked-example fixture value. Makes fixture a live regression.
- `band_mult_uncalibrated = 2.0×`: minimum meaningful widening, per §17.3.
- `band_mult_unmapped_hw = 1.5×`: independent multiplier, conservative anti-fatigue.
- `anchor_reserve_pct = 8%`: placeholder per JSON PROPOSED_HERE; pending commissioning (OI-1).

## Backward compatibility

- `SiteConfig.band_pct_calibrated = 0.0` (default) → band_upper = 0.0 → reserve check identical to pre-existing code.
- `ScenarioSpec.band_pct_calibrated = 0.0` (default) → factory passes 0.0 to SiteConfig → compat.
- All 417 pre-existing tests still pass. 24 new tests added.

## JSON field structure (actual)

- `adjustable[].id` = PARAM-01…PARAM-15
- `adjustable[].ui.group` = timing / thermal / storage / confidence (NOT top-level `group`)
- `adjustable[].split` = true → plant/engine split
- `adjustable[].note` = rationale text
- `locked[].key` (not `.id`), `.value`, `.unit`, `.reason`, `.ui.group`

## TRAP: Don't use `group` directly — it's in `ui.group`

ParameterModal uses `p.ui?.group` for grouping, not `p.group`.

## TRAP: server to restart

Always restart `artifacts/gridsignal: web` (FastAPI/Python, port 22126) after Python changes. NOT `artifacts/api-server` (Node.js).
