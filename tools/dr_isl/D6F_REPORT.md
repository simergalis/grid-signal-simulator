# D6-F — implementation stopped at the F-1 gate

**Status: STOP; no implementation, test, documentation, candidate, or report commit was made.**  
Base HEAD: `fd3bc85`. This report records the failure of the required accounting-only parity gate. No full-suite runs or workflow restart were performed after the gate failed. The D6b phase was not started.

## F-1 gate result

Compared the unmodified `(a)+(c)` candidate at `tools/dr_isl/d6/S10_2021-08-11_cpu_candidate_a_plus_c.json` with the fuel candidate at `tools/dr_isl/d6/S10_2021-08-11_cpu_soc_fuel_candidate.json`, using seed `1729`, pinned wall clock `1792454400.0`, and the RunManager path. Each input was run twice. The physical identity hashes repeated within each input:

| Input | Physical SHA-256 | Ticks |
|---|---|---:|
| No-fuel candidate, repetitions 1 and 2 | `87b7877a9c1f3bc2e6b547d823866ef8f7a9c42b9908f7409729dedbb6408803` | 17,280 |
| Fuel candidate, repetitions 1 and 2 | `4e33ec591dbf46a41a8d3518f891a7b7f7b1096ad3ca7bbf2a7afc27ab3f2029` | 17,280 |

The raw physical hashes differ because fuel telemetry is now present. A direct in-memory tick comparison is saved in `tools/dr_isl/d6f/F1_PARITY_DIAGNOSTIC.json`; it writes no per-tick export.

**F-1 fails:** the first differing non-fuel summary field is `turbine_synchronized_headroom_mwh` at tick 1: baseline `0.0 MWh`; fuel candidate `0.013541666666666667 MWh`. This field differs on all `17,280` ticks. It is an existing headroom metric, not a fuel quantity, so it cannot be treated as a fuel-only difference under the requirement that existing non-fuel metrics remain unchanged.

The comparison also found the expected fuel telemetry differences: for each turbine, `fuel_modelled` changes `false → true`, fuel status changes `not_modelled → modelled`, fuel quantities and provenance become populated, and `fuel_low_load_threshold_pct` changes `null → 50.0`. The last field was not removed by the initial helper’s nested-field filter; the direct field-level comparison identifies it as fuel telemetry. No other non-fuel tick fields differed.

The shared energy metrics remained equal in the compared repetitions: demand `621.8578481855576 MWh`, served `616.3220787729296 MWh`, unserved `5.535769412629438 MWh`, dispatch curtailment `45.77100963468485 MWh`, turbine energy `669.9665561792048 MWh`, BESS AC throughput `158.73523332738998 MWh`, and `37` turbine starts.

### Source trace for the changed headroom metric

- `core/asset_modules.py:1252–1254`: `record_fuel_interval` returns immediately when `self.config.fuel is None`.
- `core/asset_modules.py:1279–1285`: inside that fuel-gated method, synchronized turbines accumulate headroom as `max(0.0, rated_mw - output_mw) * interval_hours`.
- `core/asset_modules.py:1325–1329`: the headroom is emitted in the per-turbine fuel telemetry record.
- `core/simulation_core.py:3868–3875`: the code describes start/headroom telemetry as meaningful for frame-only runs, then collects the per-turbine records.
- `core/simulation_core.py:4155–4162`: the records are summed into the existing `TickResult.turbine_synchronized_headroom_mwh` and low-load-time fields.
- `core/models.py:1611–1615`: those are separate TickResult fields; headroom is not a fuel-consumption field.
- `runtime/run_manager.py:693–695`: the existing headroom field is exposed in tick telemetry.

The observed change is therefore a reporting-path difference caused by adding the opt-in fuel block: the fuel-accounting branch begins accumulating the existing headroom metric. It does not demonstrate a dispatch or energy-balance change, but it violates the F-1 non-fuel-metric gate. Per the request, work stopped rather than changing the metric, the comparison exclusions, or simulator code.

## Other work completed before the stop

- The user-selected SGT-400 brochure row is `10,103 kJ/kWh` at `14.3 MW(e)` for the 15 MW-class unit. The brochure basis is not stated; the candidate labels the heat-rate basis `ASSUMED LHV, PROPOSED_HERE`.
- Conversion used: `10,103 × 0.947817 = 9,575.795151 Btu/kWh`, rounded to `9,576`; the aeroderivative curve scale is `9,576 / 8,500 = 1.126588235294`.
- The generated fuel candidate adds the requested fuel block to five turbines and an `operating_cost_inputs` block. The tracked `config/scenarios/S10_mit_supercloud_2021-08-11.json` was not edited.
- The first fuel-candidate run reported `7,785.288838528619 MMBtu` turbine fuel: load `7,310.208838528641`, synchronized no-load `111.08`, hot standby `0`, starts `364`. The per-unit values are in `tools/dr_isl/d6f/F1_FUEL_REP1.json`.
- That run’s provisional itemized cost was `$50,128.168126`: gas `$44,344.975194`, turbine VOM `$3,818.809370`, FOM `$1,964.383562`; diesel, non-fuel starts, BESS degradation, and unserved-energy value were null. These are candidate-run figures only, not a completed F-5 acceptance result.
- The eight existing-scenario hash checks and the base-demo/H1/H2 seed-42 study gates were recorded as passing before F-1 in `tools/dr_isl/d6f/EXISTING_SCENARIO_HASHES.json` and `tools/dr_isl/d6f/STUDY_GATES.json`; compare-runs passed 10/10 for each protected study pair. They do not override the F-1 stop.
- Focused operating-cost tests (`8 passed`), generator tests (`10 passed`), and the frontend build passed before the F-1 stop. The requested two full-suite runs were not started.

## Working-tree state

No D6-F code or test commit was made. The application implementation and tests remain uncommitted under the git-ignored `attached_assets/` tree; the candidate and evidence files under `tools/dr_isl/` are local and uncommitted. No publish, deploy, push, or workflow restart was performed. The immediate blocker is the headroom metric delta above; resolving whether that existing metric must remain identical requires a decision before resuming the gated work.

## Resumption — F-1 amendment and read-only consumer audit

On 2026-10-24 Lloyd approved classifying the synchronized-headroom fields and low-load diagnostic fields as fuel-model reporting for opt-in fuel candidates. Before excluding them, an exact-name search was run across the package. Results:

- Producers: `core/asset_modules.py:1252–1254, 1279–1285, 1325–1327`; `core/simulation_core.py:4155–4162`.
- Tick model and wire/restore serialization: `core/models.py:1613–1614`; `runtime/run_manager.py:398–402, 693–697, 1981–1982, 3815–3822`; `api/routes/runs.py:1251–1255`.
- The per-unit low-load threshold is also materialized by `runtime/scenario_factory.py:2166`.
- The search found no matching reads in dispatch, commitment, reserve, forecasts, ledger reconciliation, study metrics used by `compare_runs`, or alert logic. The remaining matches are definitions, recording, serialization/restoration, and tests.

Accordingly, the parity helper now explicitly excludes these reporting-only fields in addition to fuel quantities/provenance: top-level `turbine_synchronized_headroom_mwh`, `turbine_minutes_below_low_load_threshold`, and `turbine_fuel_telemetry`; and per-unit `fuel_low_load_threshold_pct`, `synchronized_headroom_mwh`, `minutes_below_low_load_threshold`, and the fuel-model/status/quantity/provenance fields listed in `tools/dr_isl/d6f/run_operating_cost.py`. No producer or simulator behavior was changed. The amended paired parity result is recorded below.

#### F-1 amended parity run

The first attempt using relative paths exited with `FileNotFoundError`: after the no-fuel baseline run, the helper changed its working directory to the package and resolved the candidate path there. Re-running with absolute paths completed both 17,280-tick runs.

- No-fuel candidate SHA-256: `87b7877a9c1f3bc2e6b547d823866ef8f7a9c42b9908f7409729dedbb6408803`.
- Fuel candidate SHA-256: `4e33ec591dbf46a41a8d3518f891a7b7f7b1096ad3ca7bbf2a7afc27ab3f2029`.
- Amended non-fuel SHA-256, both paths: `808873c0bd14974ae4a605c49df4a43e7ba349831689d00399c5a2063da68f9e`; `nonfuel_equal=true`.
- Equal non-fuel metrics: demand `621.8578481855576 MWh`; served `616.3220787729296 MWh`; unserved `5.535769412629438 MWh`; curtailment `45.77100963468485 MWh`; turbine output `669.9665561792048 MWh`; BESS AC throughput `158.73523332738998 MWh`; starts `37`.
- The candidate's modelled turbine fuel is `7,785.288838528619 MMBtu`; the unmodelled baseline correctly reports fuel as null.

The exact exclusions in `tools/dr_isl/d6f/run_operating_cost.py` are:

- Top-level: `turbine_fuel_status`, `turbine_fuel_type`, `turbine_fuel_units`, `turbine_fuel_modelled`, `turbine_fuel_telemetry`, `turbine_fuel_parameter_provenance`, `turbine_total_fuel_mmbtu`, `turbine_synchronized_headroom_mwh`, `turbine_minutes_below_low_load_threshold`.
- Each `turbine_units[]` entry: `fuel_modelled`, `fuel_status`, `fuel_type`, `fuel_units`, `fuel_mmbtu_this_tick`, `load_fuel_mmbtu`, `no_load_fuel_mmbtu`, `hot_standby_fuel_mmbtu`, `start_fuel_mmbtu`, `total_fuel_mmbtu`, `fuel_parameter_provenance`, `low_load_threshold_pct`, `fuel_low_load_threshold_pct`, `synchronized_headroom_mwh`, `minutes_below_low_load_threshold`.
- The whole top-level `turbine_fuel_telemetry` list is removed, so its per-unit fuel quantities/status/provenance and the headroom/low-load diagnostic counterparts are excluded as one payload.

All 103 raw field differences in the diagnostic are contained in these fuel/reporting fields; the filtered tick digest and the listed physical/energy metrics are equal.

Focused verification after the exclusion update: `tests/test_operating_cost.py` — 10 passed in 8.05 s; `tools/supercloud/test_make_scenario.py` — 10 passed in 0.21 s. The two added tests are TC-ISL-60 (F-1 headroom-reporting exclusion and no-fuel zero behavior) and TC-ISL-61 (Scenario Planner itemized operating-cost table is present).

### Fuel totals and itemized cost (pinned seed 1729)

The repeated fuel-candidate result is 7,785.288838528619 MMBtu total: load 7,310.208838528641; synchronized no-load 111.079999999978; hot standby 0; starts 364.

| Unit | Load MMBtu | No-load MMBtu | Start MMBtu | Total MMBtu |
|---|---:|---:|---:|---:|
| turbine-0 | 2,130.965863 | 28.800000 | 0 | 2,159.765863 |
| turbine-1 | 1,992.497159 | 28.680000 | 12 | 2,033.177159 |
| turbine-2 | 1,517.154976 | 23.503333 | 56 | 1,596.658309 |
| turbine-3 | 884.589624 | 15.281667 | 144 | 1,043.871291 |
| turbine-4 | 785.001216 | 14.815000 | 152 | 951.816216 |

For the S10 candidate, gas price is `$5.140790743/MMBtu HHV` from EIA `$5.331/Mcf ÷ 1.037 MMBtu/Mcf`; the July-2026 sensitivity is `$4.416586307/MMBtu HHV` from `$4.58/Mcf ÷ 1.037`. Diesel is `$6.276/gal` from EIA's 2026-10-19 on-highway price, including road taxes; S10 has no diesel, so its diesel-cost line is null. Turbine VOM is `$5.70/MWh` and FOM `$9.56/kW-year`, cited EIA AEO2025 proxy values in 2023 dollars. The reported currency basis is mixed 2023 USD O&M / 2026 USD fuel, with no inflation normalization.

| Cost line | Amount |
|---|---:|
| Gas fuel (7,785.288839 MMBtu LHV × 1.108 = 8,626.100033 MMBtu HHV) | `$44,344.975194` |
| Turbine variable O&M | `$3,818.809370` |
| Turbine fixed O&M allocation | `$1,964.383562` |
| **Included total** | **`$50,128.168126`** |
| Diesel fuel, non-fuel starts, BESS degradation, unserved-energy value | null; no quantity or price input |

The total includes only gas fuel, turbine VOM and turbine FOM. It excludes diesel fuel, non-fuel start cost, BESS degradation, unserved-energy value, grid import, fuel-cell fuel, solar/PPA contracts, cooling labor and other site O&M. The separate `operating_cost` is not added to the existing `cost_breakdown`.

At served energy `616.322078773 MWh`, the included total is `$81.334370214/MWh served`; at IT load `515.163556304 MWh`, it is `$97.305346065/MWh IT`. July-2026 gas price sensitivity with the 1.108 LHV→HHV conversion gives total `$43,881.108218`, `$71.198338871/MWh served`, `$85.178983802/MWh IT`. Assuming the heat-rate quantity is already HHV (no conversion) at the 12-month price gives total `$45,805.733721`, `$74.321098170/MWh served`, `$88.914934219/MWh IT`.

### IMPL-ISL-24 (report only)

Synchronized headroom (stranded capacity) is currently accumulated only in the fuel-gated `record_fuel_interval` path. Scenarios without a fuel model therefore report `0` for this existing headroom metric, which is misleading. Decouple headroom measurement from the fuel model only as a separate, gated change because it would change reported headroom for existing scenarios. No change was made for IMPL-ISL-24 in D6-F.
