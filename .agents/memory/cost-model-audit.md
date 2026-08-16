---
name: cost-model-audit
description: GS-DIAG-COST-001 findings, fixes applied, and open items.
---

# Cost Model Audit — DIAG-COST-001

## Fixes applied (all in this pass)

**DIAG-1 (defect fixed):**
- `ScenarioSpec.grid_import_price_per_mwh: Optional[float] = None` added to `api/schemas.py`.
  Default is `None` (not $55 — that was a copy-paste from SyntheticPriceCurve and is wrong).
- Same field added to `RunContext` and `CompletedRun` in `runtime/run_manager.py`.
- `scenario_factory.py` writes `spec_data.get("grid_import_price_per_mwh")` onto ctx.
- `compute_run_cost_from_completed()` merges with `is not None` (never `or`) so $0.0 is honoured.

**DIAG-2 (defect fixed):**
- `ScenarioSpec.bess_charge_price_override_per_mwh: Optional[float] = None` added.
- When `None`, BESS charge price derives from effective grid import price (Path A billing price).
- When set, it takes precedence (sites with contracted off-peak charging tariff).
- Same `is not None` pattern throughout — no `or`-based fallback.

**Why `is not None` not `or`:** `or` silently shadows a legitimate `$0.0` override
(fully self-generated site). Every cost float override in this codebase must use `is not None`.

**DIAG-3 (doc fix):** turbine $/kWh is a scenario output, not a fixed assumption.
At defaults ($45k/MW·yr capital, $55/MWh variable):
- 10% duty → ~$0.106/kWh, 15% → ~$0.089/kWh, 50% → ~$0.065/kWh.
Old "$0.005–$0.010/kWh" range omitted the variable component and used wrong duty cycle.

**DIAG-4 Option A (doc + scope tag):** $120/MWh is a wholesale/direct-access fallback,
NOT a C&I all-in utility tariff. Tagged `WHOLESALE_SPOT_FALLBACK` in comments and
`core/cost_model.py` module docstring. Option B (dual named tariff defaults from PG&E
B-20 / SDG&E AL-TOU sheets) is deferred — see open item below.

**DIAG-5 (doc fix):** Solar PV and fuel cell $0 variable cost scope exclusion is now
explicitly documented in `core/cost_model.py` and `_COST_CFG_DEFAULTS`.

**DIAG-6 → PROC-1:** SyntheticPriceCurve tail events deferred. Any implementation
must preserve AT-7 determinism invariant via seeded RNG.

## Key architectural facts

- **Path A** (billing): `_COST_CFG_DEFAULTS["grid_import_price_per_mwh"] = $120` in
  `runtime/run_manager.py`. Used by the §21.2 cost engine for run accounting.
- **Path B** (market signal): `SyntheticPriceCurve.BASE_MARKET_PRICE_PER_MWH = $55` in
  `core/procurement.py`. Advisory only — its `evaluate_tick()` return value is discarded
  at `run_manager.py:2192`. Never reaches billing. These are different concepts.
- **Path B advisory confirmed clean:** `procurement_layer.evaluate_tick()` return value is
  discarded in `_drive()` — no ReservationProposal estimated_cost ever leaks into billing.

## Open items

- **DIAG-4 Option B**: source real PG&E B-20 and SDG&E AL-TOU energy-charge line items
  before adding C&I tariff named defaults. Do not invent the $220 figure without citation.
- **PROC-1**: SyntheticPriceCurve tail events (negative-price troughs, scarcity spikes).
  Deferred. Must use seeded deterministic generator (AT-7 invariant).
- **Test gap**: no end-to-end test that verifies `ScenarioSpec.grid_import_price_per_mwh`
  override actually produces the correct cost in the run result API response.
