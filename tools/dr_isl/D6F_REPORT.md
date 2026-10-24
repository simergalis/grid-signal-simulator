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
