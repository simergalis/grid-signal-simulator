# D6-F — gated implementation and validation record

**Status: STOP at F-4 after one added full-suite failure.**
The initial F-1 stop and its approved resumption are preserved below. F-1 parity passed after the approved reporting-field exclusions; focused tests passed. F-4 seed 1 then found one added failure, so seed 2 and the remaining F-6 commits/workflow restart were not performed. The D6b phase was not started.

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

### F-2 surface and focused tests

- REST `/energy-summary` adds `operating_cost` at `P/api/routes/runs.py:1268–1269`.
- MCP `get_run_metrics` energy output adds `operating_cost` at `P/mcp_server/server.py:644–645`.
- Scenario Planner renders the read-only itemized table and excluded-total details at `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/components/ScenarioPlannerPage.tsx:657–708`.
- Focused operating-cost tests passed: `10 passed`; generator tests passed: `10 passed`; frontend build passed. This does not override the F-4 suite stop below.

## F-4 full-suite gate — STOP

The real package suite ran to completion once with `PYTHONHASHSEED=1`:

| Passed | Failed | Skipped | Xfailed | Warnings | Duration |
|---:|---:|---:|---:|---:|---:|
| 2,242 | 16 | 3 | 23 | 54 | 1,002.18 s |

JUnit: `tools/dr_isl/d6f/FULL_SUITE_SEED1.xml`. Exact failing IDs: `tools/dr_isl/d6f/FULL_SUITE_SEED1_FAILING_TESTS.txt`. Summary and set comparison: `tools/dr_isl/d6f/FULL_SUITE_SEED1_SUMMARY.json`.

Against the 16 IDs in `tools/dr_isl/PHASE_6C_FAILING_TESTS.txt`, there are 15 common failures, one added failure, and one removed failure:

- **Added:** `tests/test_dr_isl_frequency_feedback.py::test_tc_isl_29_grid_tied_frequency_is_not_feedback_even_when_protection_is_reported`.
- **Removed:** `tests/test_gpu_load_profile.py::test_gpu_load_profile` (it passed in this full-suite run; the IMPL-SSH-07 waiver was not needed).
- All three Gridley failures remain: `test_gridley_logs_no_match_with_question_and_scenario_context`, `test_gridley_retrieves_operator_knowledge_for_natural_variants`, and `test_gridley_uses_grounded_operator_benefits_fallback_without_claude`.

The added failure is a test-fixture/API-shape incompatibility, not a frequency assertion: `tests/test_dr_isl_frequency_feedback.py:232` calls `get_energy_summary`; `P/api/routes/runs.py:1213` reads `completed.operating_cost`; the test's `SimpleNamespace` fixture at `tests/test_dr_isl_frequency_feedback.py:208–228` has no `operating_cost` attribute. The exact exception is `AttributeError: 'types.SimpleNamespace' object has no attribute 'operating_cost'`. Per the gate, no test or application change was made and the `PYTHONHASHSEED=987654321` suite was not run.

No D6-F implementation, test, or documentation commit was made after this added failure. The only new commit for this stop is report/evidence-only; no application workflow restart, publish, deploy, or push was performed. The package S10 scenario JSON was not edited, and no SuperCloud raw data or row-level extract is tracked. D6b was not started.

## R-1/R-2 resumed completion

### R-1 fixture correction

The fixture-only correction is in `P/tests/test_dr_isl_frequency_feedback.py:229–234`. It adds the real no-fuel defaults without changing TC-ISL-29's assertions:

- `operating_cost=None` and `operating_cost_inputs=None`: `CompletedRun` defaults at `P/runtime/run_manager.py:1985–1986`.
- `turbine_fuel_heat_rate_basis_by_unit={}`: default factory at `P/runtime/run_manager.py:1987–1989`.
- `diesel_fuel_consumed_gal=None`: default at `P/runtime/run_manager.py:1990`.
- `turbine_rated_mw=0.0`: default at `P/runtime/run_manager.py:1951`.

The legacy database restore path is `P/api/routes/runs.py:85–171`; it constructs `CompletedRun` at line 137 and leaves absent optional operating-cost properties to the dataclass defaults. TC-ISL-33 verifies the restored legacy frequency fields remain unknown (`None`).

When `operating_cost` and `operating_cost_inputs` are both `None`, the REST energy summary does not include the `operating_cost` key (`P/api/routes/runs.py:1268–1269`). TC-ISL-29's four frequency-field assertions were left unchanged and passed.

Focused verification: `python -m pytest -q tests/test_dr_isl_frequency_feedback.py tests/test_operating_cost.py` — **25 passed in 9.83 s**. This covers TC-ISL-29–33, TC-ISL-60/61, and the operating-cost tests.

### R-2 full-suite runs

Both completed against the real package; the only baseline delta is the waived IMPL-SSH-07 GPU test passing:

| `PYTHONHASHSEED` | Passed | Failed | Skipped | Xfailed | Warnings | Duration |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2,243 | 15 | 3 | 23 | 54 | 1,036.14 s |
| 987654321 | 2,243 | 15 | 3 | 23 | 54 | 1,010.52 s |

For each run, **15 failures are common with `tools/dr_isl/PHASE_6C_FAILING_TESTS.txt`; added = 0; removed = `tests/test_gpu_load_profile.py::test_gpu_load_profile`**. The two current failing-ID sets are identical. The GPU test passed in both full-suite runs; the three known Gridley failures remain. Exact lists and machine-readable summaries are `tools/dr_isl/d6f/FULL_SUITE_RESUME_SEED1_FAILING_TESTS.txt`, `FULL_SUITE_RESUME_SEED1_SUMMARY.json`, `FULL_SUITE_RESUME_SEED987654321_FAILING_TESTS.txt`, and `FULL_SUITE_RESUME_SEED987654321_SUMMARY.json`.

The original F-4 stop above is historical and superseded by this R-1/R-2 completion. No endpoint or other application code was changed for this resumption; the test fixture was the only tracked source edit. The tracked S10 scenario remains unchanged. The broad command `git ls-files | grep -i -E 'slurm|channels.csv|gridsignal.db'` returns 54 existing code, documentation, scenario, and test paths (for example `core/slurm_scheduler.py` and `scenario-h2-slurm-24h.json`); it does not return raw `slurm-log.csv`, `tres-mapping.txt`, `*.channels.csv`, or `gridsignal.db`.

The operating-cost module, documentation, and Scenario Planner table are recorded in their implementation commit; the test changes are recorded separately. No production workflow restart, publish, deploy, or push was performed. D6b was not started.

### R-3 commit record

- Implementation: `ed0b54bd066461e998cf243d53ce24bb1f188be2` — `D6-F: add opt-in itemized operating-cost reporting`. Files: `P/runtime/operating_cost.py:1–321`, `P/docs/operating-cost-model.md:1–81`, and `frontend/src/components/ScenarioPlannerPage.tsx:657–713` (read-only itemized table). REST/MCP exposure was already committed at `0ba855a`; REST lines `P/api/routes/runs.py:1213–1228,1268–1269`, MCP lines `P/mcp_server/server.py:643–645`.
- Tests: `2a0f1fbb3dbf0a1a75cc3bc07e1947e971cd9986` — `D6-F: cover operating-cost accounting and legacy energy-summary fixture`. Files: `P/tests/test_operating_cost.py:1–278` and `P/tests/test_dr_isl_frequency_feedback.py:229–234`.
- The S10 fuel candidate and `COST_INPUTS.json` were already tracked in the earlier D6-F generator/evidence commits; the source S10 scenario remains unchanged.
- R-2 evidence committed under `tools/dr_isl/d6f/` consists of the two failing-ID lists and their JSON summaries named above. JUnit XML was generated and parsed for the run comparison, then removed after extracting those durable results.
- `git ls-files | grep -i -E 'slurm|channels.csv|gridsignal.db'` has 54 path matches because the repository tracks Slurm-related source, tests, docs, scenarios, and earlier reports. The more specific tracked-data check for `slurm-log.csv`, `tres-mapping.txt`, `*.channels.csv`, and `gridsignal.db` is empty.
- No deployment workflow was restarted. No publish, deploy, or push occurred. D6b was not started.
