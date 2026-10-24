# D6-F — S10 fuel model and operating-cost proposal

**Decision record:** DR-2026-10-20-ISLAND-COLLAPSE, D6-F  
**Status:** Read-only inventory and proposal; stopped for Lloyd's choice.  
**Base inspected:** `c07bc9a01275752282c7e6b1fa4ea92b071b801a` (`D6a: record completed S10 CPU and SoC candidate runs`).  
**Scope honored:** No application, test, scenario, template, or generator changes. `config/scenarios/S10_mit_supercloud_2021-08-11.json` was not changed or replaced. D6b was not started.

## Summary

- The runtime already supports optional turbine gas-fuel accounting, but the S10 turbine objects have no fuel model. In the app path, S10 therefore reports turbine fuel as **`not_modelled` / `null`**, not zero. Its five turbines are each 15 MW.
- A turbine fuel model is explicitly documented as separate from dispatch physics. The dispatch merit-order cost (`turbine_variable_per_mwh`) is a separate economic parameter; it is not calculated from the turbine heat-rate curve.
- A run cost breakdown exists, but it is a simplified grid/turbine/storage estimate. It does not calculate actual gas or diesel bills, fuel-cell/diesel/solar generation costs, start costs, or the data-center's total operating cost.
- **Recommendation for a future S10 opt-in:** Option B, a Siemens Energy SGT-400 industrial-turbine proxy at the 15 MW class, with its full-load point vendor-published and the part-load/no-load/standby/start curve explicitly marked `PROPOSED_HERE`. The simulator's existing aeroderivative curve is not a good type match for S10's frame/industrial turbine representation. This is a proposal, not evidence that S10 has SGT-400 equipment.

## F.1 — Fuel-model inventory

### F.1(a) Turbine schema and runtime behavior

`api/schemas.py:882–903` defines the optional `TurbineFuelSpec`; `runtime/scenario_factory.py:909–965` converts a raw fuel block into `TurbineFuelParameters`, and `runtime/scenario_factory.py:967–990` passes it to `TurbineConfig`. The factory's existing behavior is:

- If a fuel block is supplied, it is materialized for that turbine.
- If no block is supplied, the aeroderivative defaults are attached only when `gt_mode == "aero"`; otherwise the model is absent (`runtime/scenario_factory.py:911–917`).
- `gt_mode` itself is resolved separately on the config (`runtime/scenario_factory.py:983–989`). A future S10 fuel-only override must preserve S10's current resolved turbine mode.

The supported accounting inputs are:

| Input | Current default / unit | Source label and implementation |
|---|---:|---|
| Fuel type and units | `natural_gas`; `MMBtu` | Defaults in `core/models.py:903–904`; no S10 fuel block today. |
| Part-load heat-rate points | 25%: 11,000; 50%: 9,800; 75%: 9,000; 100%: 8,500 Btu/kWh | `core/models.py:905–910`. Each default is `Authored — PROPOSED_HERE`, not an OEM curve (`core/models.py:965–978`). |
| Synchronized no-load fuel | 1.20 MMBtu/h | `core/models.py:911`; `PROPOSED_HERE`. |
| Hot-standby fuel | 0.25 MMBtu/h | `core/models.py:912`; `PROPOSED_HERE`. |
| Start fuel by thermal state | Hot 8; warm 12; cold 20 MMBtu/start | `core/models.py:913–915`; `PROPOSED_HERE`. |
| Low-load threshold | 50% of rated output | `core/models.py:916`; `PROPOSED_HERE`; used for reporting low-load minutes, not dispatch. |
| Provenance | Per-parameter string map | Missing labels are filled with `Authored — PROPOSED_HERE` (`core/models.py:917–952`). |

The schema/runtime has no turbine gas-price field, gas contract, emissions factor, non-fuel start cost, or explicit LHV/HHV choice in this fuel model. Fuel is accounted in `core/asset_modules.py:1237–1296`: output × interpolated heat rate produces load fuel; synchronized no-load, hot-standby, and start fuel are accumulated separately. The start component is added at `core/asset_modules.py:1117–1122`. Per-unit telemetry reports `fuel_modelled`/`not_modelled` and null fuel values when there is no model (`core/asset_modules.py:1298–1329`).

### F.1(b) Fuel models across code, catalogues, and scenarios

| Resource/model | Defined values | Where it is used and provenance |
|---|---|---|
| Gas turbine, aeroderivative accounting default | The curve and ancillary values in the preceding table | `core/models.py:965–979`; expressly authored `PROPOSED_HERE`, not vendor-published. `runtime/scenario_factory.py:914–916` attaches it only to `gt_mode="aero"` when no explicit fuel block is present. |
| Gas turbine, explicit scenario fuel block | Same fields as above; supplied values override defaults and missing values inherit them | `api/schemas.py:882–903`, `runtime/scenario_factory.py:918–965`. A repository-wide scan of `config/scenarios/*.json` found **no turbine-unit `fuel` object**. Thus scenario JSONs do not currently define a separate turbine heat-rate model. |
| Fuel cells | BOL/EOL heat rate 5,811/7,127 Btu/kWh; 50% degradation fraction; part-load multiplier 1.0; gas heating value 1,030 Btu/scf; hot-standby fuel fraction 0.10; gas price default $5/MMBtu | `api/schemas.py:623–633`, provenance defaults at `api/schemas.py:671–687`: heat rates labelled vendor-published, degradation/gas values site-specific, part-load multiplier and standby fraction proposed. Runtime materialization is `runtime/scenario_factory.py:1173–1239`. These are fuel-cell parameters, not turbine assumptions. |
| Diesel | Fuel burn 230 gal/hour per unit at full load; runtime fuel consumption scales by output/rating | Fleet default `core/diesel_fleet.py:45–55`; consumption `core/diesel_fleet.py:384–405`. Scenario blocks in `scenario-100mw-fuel-cell-bess-diesel.json` and `scenario-hybrid-ai-100mw-addendum-i.json` explicitly carry 230 (`:670` and `:100`, respectively). This is a rate model, not a heat-rate curve; no diesel price, start-fuel quantity, or no-load fuel rate is present in that model. |
| Economic parameter catalogue | Turbine variable cost $55/MWh, fuel-cell PPA $65/MWh, solar PPA $28/MWh, BESS marginal dispatch cost $38/MWh | `gridsignal_parameters.json:1321–1347`, `1377–1402`; these are cost/ranking values, not fuel models. Their provenance is `PROPOSED_HERE` in the catalogue. No turbine heat-rate curve or diesel $/gal price is defined there. |

Scenario coverage:

- **S10:** `config/scenarios/S10_mit_supercloud_2021-08-11.json:1` has five 15 MW turbine units, no turbine fuel block, and no diesel block. The app factory resolves the turbine mode to the frame/default path and does not attach the aero fuel model. The app-path fuel result is therefore `not_modelled`/`null`; zero would incorrectly assert measured zero consumption.
- **Base demo and `demo-islanded-ramp`:** the scenario JSONs have no turbine fuel block. The base-demo *study harness* deliberately overlays `gt_mode="aero"` via `study_harness/executor.py:300–315` and `runtime/phase2b_reference.py:41–49`; consequently its study fuel results use the authored aeroderivative assumptions. This study-only overlay is not the raw scenario/app-path model.
- **H1/H2 reference studies:** their expansion applies the study fuel overlay (`runtime/phase2b_reference.py:41–49`, `:95–120`); the H study fuel numbers are therefore assumption-based accounting, not OEM measurements for S10.
- **Other turbine scenarios:** `scenario-turbine-01.json`, `scenario-kubernetes-scheduler-demo.json`, turbine-bearing demo/lead-time scenarios, and `S9_islanded_ramp_protection.json` have no turbine `fuel` object. S9 uses the legacy `open_cycle` label, not `aero`; no fuel model is materialized by the factory's `gt_mode == "aero"` fallback.
- **SJ-1 and hybrid:** no turbine fuel model applies; these are not the S10 turbine fleet. `scenario-hybrid-ai-100mw-addendum-i.json` carries a diesel block, whose current fuel rate is the 230 gal/hour-per-unit default above.
- **FC100 sites:** `scenario-fc100-islanded-v2.json` and `scenario-fc100-islanded-zero-hot-v2.json` declare fuel-cell arrays; the runtime fuel-cell accounting defaults apply. `scenario-100mw-fuel-cell-bess-diesel.json` also has a diesel block and fuel-cell configuration; its diesel fuel rate is 230 gal/hour per full-load unit.

### F.1(c) S10 turbine operating parameters

The S10 scenario line 1 contains five units, each rated 15 MW, with `r_asset_mw_per_s = 0.5` and `p_min_stable_frac = 0.35`. Thus each turbine's minimum stable output is **5.25 MW**. Its authored start values are:

| Unit | Initial thermal state | Start time used |
|---|---|---:|
| turbine-0 | hot | 300 s |
| turbine-1 | warm | 360 s |
| turbine-2, turbine-3, turbine-4 | cold | 600 s |

Those are the S10-resolved values; null start overrides use the factory's configured fallback (`runtime/scenario_factory.py:990–995`). These timing and ramp values describe the simulated turbine model; they do not identify an OEM.

### F.1(d) Does fuel modeling alter dispatch?

No, not by itself. The fuel-parameter class documents an accounting-only boundary (`core/models.py:893–900`), and the factory documents the same at `runtime/scenario_factory.py:909–910`. Fuel is consumed by the turbine accounting path (`core/asset_modules.py:1237–1296`). The merit-order allocator reads catalogue marginal-cost inputs, not the heat-rate curve (`core/simulation_core.py:902–934`); the dispatch cost table includes BESS, turbine and fuel-cell costs, and diesel is ranked separately at `core/simulation_core.py:935–952`. I found no dispatch/commitment/forecast read of `TurbineFuelParameters` or its heat-rate interpolation. Therefore adding an explicit turbine `fuel` accounting block while leaving `gt_mode`, dispatch costs and all operating parameters unchanged should not change S10 dispatch. Changing `gt_mode` or cost inputs is outside this proposal and must not be bundled with a fuel-only overlay.

## F.2 — Cost inventory

| Cost category | Present today? | Run/UI/MCP exposure and gap |
|---|---|---|
| Turbine gas fuel, MMBtu | **Conditional.** Per-unit MMBtu telemetry exists only when a turbine has a fuel model (`core/asset_modules.py:1233–1329`); study metrics sum it (`study_harness/metrics.py:505–519`). | REST energy summary includes fuel status, total, per-unit telemetry and provenance (`api/routes/runs.py:1210–1229`). MCP has MMBtu fuel metrics (`mcp_server/server.py:607–618`). S10 app-path total is null/not modelled. No turbine gas $ conversion exists. |
| Fuel-cell fuel, MMBtu | **Present** for fuel-cell arrays; their fuel parameters include a gas-price default (`api/schemas.py:623–630`; runtime construction `runtime/scenario_factory.py:1222–1232`). | Physical fuel quantity is available in run/tick records, but a complete per-run fuel bill is not included in the study metrics or the MCP energy response (`mcp_server/server.py:621–643`). `runtime/fuel_cell_readiness.py:108–147` can estimate standby fuel cost for a readiness proposal; that is not a completed-run total. |
| Diesel fuel, gallons | **Present as a fuel-burn quantity/rate** (`core/diesel_fleet.py:384–405`). | No diesel $/gal input or per-run diesel fuel dollar calculation is in the cost model. |
| Gas price ($/MMBtu) | **Absent for turbines.** Fuel-cell schema has a $5/MMBtu default, marked site-specific (`api/schemas.py:629`, `:671–687`). | Not a common run-level fuel tariff for all gas-fired sources. A configured site contract/price is needed before computing a defensible gas bill. |
| Diesel price ($/gal) | **Absent.** | Needs a sourced site/contract price or a conspicuously labelled proposal. |
| Start cost | **Fuel quantity partly present** for modeled turbines: hot/warm/cold start MMBtu; no monetary start cost. Diesel start fuel/cost is not modeled as a separate item. | Start counts/fuel may be reported, but there is no separate non-fuel $/start or start-cost total. Fuel used for a start should be priced once as fuel, not double-counted as both fuel and a start fee. |
| Turbine variable O&M | A $55/MWh catalogue parameter exists, explicitly labelled as an estimate of fuel + variable O&M (`gridsignal_parameters.json:1321–1332`). | It is used for merit order and the current simplified cost breakdown, not as a measured fuel bill. It must be split before adding measured fuel costs to avoid double counting. No independent sourced turbine O&M rate is present. |
| Turbine capital | $45,000/MW-year in `_COST_CFG_DEFAULTS` (`runtime/run_manager.py:963–971`), labelled CHOSEN. | Included in the simplified run cost model as duty-cycle-amortized capital (`core/cost_model.py:22–44`, `:239–245`). It is not a full fixed O&M or lifecycle cost. |
| BESS energy and degradation | Grid/charge energy price is modeled; the current cost formula prices charge energy and a round-trip-loss term (`core/cost_model.py:46–59`, `:246–250`). The dispatch catalogue's $38/MWh BESS marginal cost includes cycle amortization plus loss (`gridsignal_parameters.json:1391–1402`). | The $38 value is a dispatch-cost input; the run cost model does not add it as a separate cycling/degradation charge. To avoid double counting, separate charging energy from degradation if the latter is added. |
| Grid import energy | **Present** in the run cost breakdown. Default $120/MWh, explicitly a wholesale/direct-access fallback and excluding demand charges/TOU adders (`runtime/run_manager.py:949–963`, `core/cost_model.py:10–20`). Scenario overrides are supported (`api/schemas.py:2396–2433`). | REST `/energy-summary` returns `cost_breakdown` and `cost_model_config`, and its route comment says it is consumed by `ScenarioPlannerPage` (`api/routes/runs.py:1127–1138`, `:1188–1235`). This is the UI's existing cost channel. The current endpoint's aggregation uses turbine output and BESS output (`api/routes/runs.py:1159–1167`), so it is not yet a complete source-by-source cost ledger for fuel-cell/diesel generation. |
| Unserved energy / curtailment value | **Absent** as a dollar penalty/opportunity-cost model. | Energy and curtailment quantities are reported; no VOLL, customer interruption penalty, or curtailed-energy value is included in total cost. |
| Solar/fuel-cell generation cost | **Absent from the generic cost engine.** `core/cost_model.py:61–65` says solar and fuel-cell variable cost/capital are zero-modelled and their output only reduces grid import indirectly. Catalogue PPA values are not complete actual bills. | Per-source contracted PPA/actual fuel and asset cost need explicit inputs if a full operating-cost report is required. |

The run cost breakdown currently totals only grid-import cost, turbine capital-plus-variable generation cost, and BESS charge/loss cost (`core/cost_model.py:122–143`, `:223–268`; `runtime/run_manager.py:1036–1053`). It is useful as a comparison estimate, but it is not “true cost of power generation and operating the data center.” A defensible total needs source-specific fuel quantities and prices, separated O&M/capital/start costs, complete grid tariffs, and a defined policy for storage degradation and unserved load. Full data-center operating cost also needs non-energy inputs such as cooling/plant O&M, demand charges, network charges, and labor if those are in scope.

## F.3 — Proposal (not implemented)

### S10 turbine fuel model

**Option A — reuse the in-repo aeroderivative accounting curve.** The model is already available as `AERODERIVATIVE_FUEL_PARAMETERS` (`core/models.py:965–979`), with all curve/no-load/standby/start values labelled `Authored — PROPOSED_HERE`. Its nominal 15 MW scale matches S10's turbine rating, and it has all required accounting fields. However, S10's current turbine configuration resolves as frame/industrial, while the existing model is expressly aeroderivative. It is therefore a weaker equipment-type match and must not be presented as an S10 OEM curve.

**Option B — use a vendor full-load point for a 15 MW-class industrial unit, with proposed remainder.** Siemens Energy's official SGT-400 gas-turbine portfolio brochure identifies the SGT-400 as an industrial gas turbine, lists the “SGT-400 (15 MW)” configuration at **14.3 MW(e)** and **10,720 kJ/kWh**, and gives the product range as 10.5–14.3 MW(e). Source: [Siemens Energy, Gas Turbine Portfolio Brochure (2024)](https://assets.siemens-energy.com/dam/d7e01f44-f091-44f2-bf71-b20b010483e1/GT-Portfolio-Brochure-2024__FINAL_Low_Resolution-pdf_Original%20file.pdf). This is a close rating/class proxy, not evidence that S10 has Siemens equipment. Use the vendor point as the full-load point only; label the other heat-rate points/part-load shape, synchronized no-load, hot-standby, and hot/warm/cold start fuel **`PROPOSED_HERE`**, adapted from the existing in-repo model until actual fleet/OEM data is supplied.

**Recommendation:** Option B. It better matches the modeled industrial/frame class and approximately 15 MW rating. Keep S10's `gt_mode`, start durations, minimum stable output, ramps, dispatch costs and all other scenario fields unchanged; add only an explicit fuel-accounting block in a future generator-produced candidate. This preserves the accounting-only boundary. If the installed S10 turbine make/model is known, that equipment's datasheet should supersede the proxy before any customer-facing cost claim.

**Reproducible entry point:** in a future D6a continuation, add a generator option/template override that writes the per-turbine `fuel` object and records its source, labels, generator invocation, and input digest in generated metadata. Do not hand-edit the S10 JSON and do not change `demo-islanded-ramp`; its template belongs to D5.

### Minimal per-run cost reporting

Recommended itemization, with every input carrying `CITED`, `SITE_SPECIFIC`, or `PROPOSED_HERE` provenance:

1. **Natural-gas fuel:** `modeled gas MMBtu × configured $/MMBtu`; include load, no-load, hot-standby and start fuel once, with start fuel also shown as a subline. Reuse turbine/fuel-cell quantity telemetry; add a common, explicit site/scenario gas-price input (existing fuel-cell gas price is not a site-wide contract).
2. **Diesel fuel:** `diesel gallons × configured $/gal`. Reuse gallon telemetry; add a site/scenario diesel price.
3. **Start charges:** `starts × configured non-fuel $/start`, only if an actual service/maintenance charge is intended. Keep it distinct from priced start fuel. No such price exists today.
4. **Variable O&M:** `source MWh × source-specific $/MWh`, excluding fuel when actual fuel is billed separately. Reuse output-energy metrics; split the current $55/MWh turbine estimate rather than adding it on top of fuel. If a site has no vendor/contract O&M figure, label the estimate `PROPOSED_HERE`.
5. **Fixed O&M:** optional `operating/available hours × $/hour` or `rated MW × $/MW-year` using an explicitly chosen allocation rule. Current turbine capital amortization can be retained as a separately named estimate; it is not fixed O&M.
6. **Grid imports:** `import MWh × configured all-in energy price`. Reuse the existing price override/cost channel but distinguish wholesale fallback from a site tariff and include omitted tariff components only when supplied.
7. **BESS cycling:** optional discharged MWh × degradation-only $/MWh. Reuse BESS telemetry; split the catalogue's $38/MWh into degradation and loss before combining it with separately priced charge energy.
8. **Unserved energy:** optional `unserved MWh × configured VOLL/penalty`. No value is defined today; keep absent unless a customer/contract or an approved proposal supplies it.

For complete per-run access, expose the same itemized values and provenance in study metrics, the MCP `get_run_metrics` energy section, REST `/energy-summary`, and the existing Scenario Planner UI. MCP presently exposes fuel quantities and energy but not dollar totals (`mcp_server/server.py:607–643`); REST exposes the simplified cost breakdown (`api/routes/runs.py:1230–1235`). This is a moderate, cross-layer change: the largest risks are source attribution and double-counting, not formula complexity.

### Proposed gates for a later implementation

- Default-off/absent fuel and cost inputs preserve every existing scenario and its hashes/metrics. Only an explicitly opted-in generated S10 candidate receives the proposed fuel model.
- Compare the candidate against the current S10 physical hashes and energy metrics; fuel accounting must not affect turbine output, dispatch, reserve, BESS, frequency, served/unserved, or curtailment.
- Verify full-load heat-rate provenance and unit conversion, part-load interpolation, no-load/standby/start accounting, cost roll-up, and no double-counting between fuel, variable O&M, BESS charging, and degradation.
- Verify `null`/`not_modelled` remains distinct from numeric zero for every unmodelled source; test each price source and provenance through study metrics, MCP, REST, and UI.
- Do not make a customer-facing “true total cost” claim until site gas/diesel prices, tariffs, O&M, and the inclusion boundary for data-center operating costs are approved.

**Decision requested:** choose Option A, Option B, or provide S10's installed turbine make/model and the applicable fuel/price/O&M sources. No fuel model or cost implementation was selected or applied in this step.
