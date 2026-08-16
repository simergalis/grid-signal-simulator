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

## GS-DIAG-COST-002 — Sweep results + regressions

**Sweep outcome**: No new instances of the `or`-based Optional[float] bug class in
cost-bearing code paths. Full hit table (all files in runtime/, core/, api/):

| Location | Field | Verdict |
|---|---|---|
| run_manager.py:2181 | collapse_frequency_hz | Log-format guard only; not cost-bearing. Safe. |
| run_manager.py:2467 | edl_dispatch_cost_usd | Defensive sum guard; EDL active path only; None≡missing key, not zero-cost tick. Safe. |
| scenario_factory.py:921 | design_peak_load_mw (outer or) | 0.0 not a valid domain value (zero peak load is nonsensical). Correct by intent. |
| scenario_factory.py:938 | design_peak_load_mw | Same — 0.0 means "not provided". Intentional. |
| scenario_factory.py:1087 | edl_calendar_month | Month 0 doesn't exist; 0 not a valid domain value. Safe. |
| solar_sim.py:116-117 | lat, lon | Display-only Mistral prompt. 0.0 IS valid (equator/prime meridian). Fixed for consistency. |
| solar_sim.py:633 | _utc_offset | Display-only Mistral prompt. 0.0 IS valid (UTC+0). Fixed for consistency. |
| api/routes/runs.py:961 | scenario_name | String or-fallback. Not numeric. Not applicable. |
| advisory_router.py:92-93 | MISTRAL_API_KEY | Env-var string guard. Not numeric. Not applicable. |

**Consistency fixes applied** (solar_sim.py only, not cost-bearing):
- `(lat or 0) >= 0` → `lat is None or lat >= 0.0`
- `(lon or 0) >= 0` → `lon is None or lon >= 0.0`
- `(_utc_offset or 0.0)` → `_utc_offset if _utc_offset is not None else 0.0`

**Regression tests added** (`tests/test_cost_model_override_regression.py`, 9 tests, all pass):
- `TestZeroGridImportPriceOverride` — $0.0 override honoured; None falls back to $120; nonzero override applied.
- `TestBessChargeCostTracksImportPrice` — BESS charge price derives from import price; explicit BESS override wins; $0 BESS override honoured.
- `TestProcurementPathBIsolation` — Path B market signal (SyntheticPriceCurve) has zero effect on billing; `evaluate_tick()` result confirmed advisory-only via direct call.
- All 9 tests verified to FAIL against pre-fix `or`-based merge logic.

**evaluate_tick() return dict shape**: flat dict with keys
`import_mw, new_served_load_mw, reserve_gap_mw_unchanged, proposal_requires_confirmation, spot_price_per_mwh`.
NOT a nested `proposal` object — the proposal lives in AdvisoryGate.
