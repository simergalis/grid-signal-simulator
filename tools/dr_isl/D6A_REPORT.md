# D6a candidate regeneration — revised provenance passed; D6a-X implemented

Package root `P`: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

**Status:** D6a.2r passes after ScenarioSpec normalization, and the 60-tick physical hashes match. The additive `non_gpu_load_profile_mw` field has now been implemented and gated in D6a-X. D6a.3 CPU candidate generation is complete; the pinned full-day D6a.5 RunManager repetitions are in progress. D6a.4 SoC derivation and the (a)+(c) runs remain gated on the CPU-only candidate's startup-surplus measurement.

## D6a.1 — generator import

- Source branch: `supercloud-ingest-gate1`, commit `0aac1a42ec95ba6d6ba612bf3272bb71868662a5` (2026-10-20 11:30:18 -07:00; author Claude).
- Imported unchanged; source Git blob IDs matched for the imported files. Import commit: `46cd94e00e073a542ad2452df64e5be671c20678` — `D6a: import SuperCloud generator from supercloud-ingest-gate1 @0aac1a42ec95ba6d6ba612bf3272bb71868662a5`.
- Files: `tools/supercloud/{.gitignore,make_scenario.py,convert_to_kube_trace.py,profile_slurm_log.py,run_replay.py,test_make_scenario.py,test_convert_to_kube_trace.py}`.
- Tests: `python3 -m pytest -q tools/supercloud/test_make_scenario.py tools/supercloud/test_convert_to_kube_trace.py` → **16 passed in 0.95s**. `profile_slurm_log.py --help` and `run_replay.py --help` both exited 0.

## D6a.2 — original raw-JSON gate (superseded by D6a.2r)

Input settings and sources:

- Date: `2021-08-11`, in the current S10 name/description (`P/config/scenarios/S10_mit_supercloud_2021-08-11.json:1`).
- Template: `demo-islanded-ramp.json`; the generator-introduction commit `a4fae997d7ff42f9ce181fa7bdcedd112b2a4eba` states it was built “on the demo-islanded-ramp power side.”
- Peak: `design_peak_load_mw: 50.0` and the description states 50.0 MW (`P/config/scenarios/S10_mit_supercloud_2021-08-11.json:1`); the same introduction commit states “peak 50 MW PROPOSED_HERE.”
- Profile: `hopper_8gpu_air` in the current scenario JSON (`P/config/scenarios/S10_mit_supercloud_2021-08-11.json:1`); `tools/supercloud/make_scenario.py:58` defines that profile as the generator default.
- Partitions: the current S10 JSON does not store the partition filter, and the branch history has no saved invocation listing it. The unchanged generator defaults to `normal,gaia,test` at `tools/supercloud/make_scenario.py:59,232`; that default was used for this reproduction, but the original invocation’s partition argument cannot be independently confirmed.
- The current name `S10_mit_supercloud_2021-08-11` was supplied from the scenario JSON using the generator’s `--name` option (`tools/supercloud/make_scenario.py:234`).

Reproduction summary: **154 GPU jobs**, **239 events** (154 starts, 85 ends), **424** peak concurrent V100s, `chassis_per_gpu=11.5612`, target and rounded peak **50.0 MW**, profile `hopper_8gpu_air`, rated profile power `10.2 kW`, no skipped rows. These aggregates match the current S10 description. The aggregate build record is `tools/dr_isl/d6/D6A_2_PROVENANCE_REPRO.build.json`.

Canonical comparison used UTF-8 JSON with sorted keys and compact separators:

- Current S10 canonical SHA-256: `28f3607147b51a752b4c6df418a423eebe669d5e22808135803cdc0da7025973`.
- Generator output canonical SHA-256: `d54befa859e407e4547327f19b6b87d5cd18181778106dbca6df0668c47ee472`.
- **Not identical as raw JSON. First difference:** `$.base_load_mw`; current S10 has the key with value `null`, while the unchanged generator output omits the key. This raw difference alone does not establish a semantic mismatch; D6a.2r below performs the revised normalized comparison. Raw-file hashes and the first-difference record are in `tools/dr_isl/d6/D6A_2_PROVENANCE.json`.

The original gate compared raw JSON and stopped on schema-default shape differences. The user’s revised D6a.2r explicitly allows a same-path ScenarioSpec normalization comparison; the result is below. No application code, generator, test, or scenario configuration was changed.

## D6a.2r — revised provenance gate

The unchanged generator was rerun with date `2021-08-11`, template `demo-islanded-ramp.json`, peak `50.0 MW`, profile `hopper_8gpu_air`, partitions `normal,gaia,test`, scenario name `S10_mit_supercloud_2021-08-11`, source commit `0aac1a42ec95ba6d6ba612bf3272bb71868662a5`, and input SHA-256 `27259e5b8e6daecd80b7853126af40ba759bc25edc9053fc174ef7a4f186aa01`. The partition list is **INFERRED**, not a saved historical invocation; the aggregate match is 154 GPU jobs, 239 events, peak 424 V100s, `chassis_per_gpu=11.5612`, and 50.0 MW.

The raw canonical documents differ in **64 path patterns**: 33 patterns / 3,365 occurrences are current-S10 null-valued keys absent from generated JSON; 31 patterns / 753 occurrences are current non-null keys absent from generated JSON. The full path-by-path list, counts, and current values are in `tools/dr_isl/d6/D6A_2R_DIFF.json`. These include `$.base_load_mw` (null/absent), omitted defaults such as site coordinates, BESS/turbine settings, and repeated workload-event defaults (`gpus_per_unit=1`, `renewable_shortfall_mw=0.0`, `workload_class="training"`); the evidence file lists every path and occurrence count.

Both files were normalized as `ScenarioSpec.model_validate(json.loads(file)).model_dump(mode="json")`, with default options and no exclusions. The seeder reads each JSON and validates with `ScenarioSpec.model_validate_json(_raw)` at `P/api/routes/scenarios.py:1444–1455`; `ScenarioStore._seed` serializes the validated model via `model_dump_json()` at `P/api/routes/scenarios.py:130–136`. Cross-checking `model_validate` against `model_validate_json`, and `model_dump(mode="json")` against the seeder’s `model_dump_json()`, produced equal canonical documents for each input.

**Gate: PASS.** The normalized documents are identical; both canonical normalized SHA-256 values are `f8345bbece33731115bcac9f699741c941c80bbd4e5a007deff093a8a1d492ff`. The current S10 raw canonical hash is `28f3607147b51a752b4c6df418a423eebe669d5e22808135803cdc0da7025973`; the regenerated raw canonical hash is `d54befa859e407e4547327f19b6b87d5cd18181778106dbca6df0668c47ee472`.

Both normalized documents were built through `build_run_context_from_spec` and run with the headless `RunManager` path used by `tools/dr_isl/baseline_runner.py`, explicit seed `42`, Python/NumPy seeded to `42`, and wall clock pinned to `1792454400.0`. Contexts were built for the full scenario; only after build, the RunManager stop time was set to 300 seconds to capture the first 60 five-second ticks. Both completed 60 ticks with zero physical-balance failures and physical hash `01bde90a117c760c9f31cbd00c70feb65ac5e386ac51c9e012c907d07849c4aa`. Details: `tools/dr_isl/d6/D6A_2R_60TICK_SUMMARY.json`.

## D6a.3 — accepted CPU assumptions (originally stopped at schema gate; superseded by D6a-X)

Lloyd’s 2026-10-23 ruling resolves the CPU model assumptions for this candidate. These values are all **PROPOSED_HERE**:

| Slurm partition | CPU-only jobs | Allocated cores | Core-hours | GPU-allocated jobs in partition |
|---|---:|---:|---:|---:|
| `normal` | 9 | 1–25 | 554.402500 | 154 |
| `xeon-p8` | 416 | 1–384 | 9,360.002500 | 0 |
| `db` | 1 | 32 | 4.568889 | 0 |

| Partition | Per-core package power | Label / basis |
|---|---:|---|
| `xeon-p8` | 6.875 W/core | **CITED** — Platinum 8260, 165 W / 24 cores; MIT Dataset paper Table II and MIT systems page |
| `normal` | 7.5 W/core | **INFERRED** — **PROPOSED_HERE**, Lloyd ruling; Gold 6248, 150 W / 20 cores. `normal` carries all 154 GPU jobs, consistent with the Gold 6248 GPU nodes; this is not a citable partition mapping |
| `db` | 7.5 W/core | **INFERRED** — **PROPOSED_HERE**, Lloyd ruling; same Gold 6248 basis |

The MIT Supercloud Dataset paper, Table II (https://arxiv.org/abs/2108.02037), identifies the GPU-accelerated nodes as dual Intel Xeon Gold 6248 and CPU-only nodes as dual Intel Xeon Platinum 8260. The MIT SuperCloud systems page (https://mit-supercloud.github.io/supercloud-docs/systems-and-software/) maps `xeon-p8` to Platinum 8260 and `xeon-g6-volta` to Gold 6248. Intel ARK gives Gold 6248 as 150 W / 20 cores = 7.5 W/core, and Platinum 8260 as 165 W / 24 cores = 6.875 W/core:

- Gold 6248: https://www.intel.com/content/www/us/en/products/sku/192446/intel-xeon-gold-6248-processor-27-5m-cache-2-50-ghz/specifications.html
- Platinum 8260: https://www.intel.com/content/www/us/en/products/sku/192474/intel-xeon-platinum-8260-processor-35-75m-cache-2-40-ghz/specifications.html

The aggregate scan covers all partitions and jobs overlapping 2021-08-11 UTC; CPU-only means allocated TRES id 1 cores and neither GPU TRES id 1001 nor id 1002. It found **426 jobs / 9,918.973889 core-hours**. `gaia` and `test` had no CPU-only rows that day. Aggregate-only evidence (no row-level extract) is in `tools/dr_isl/d6/D6A_3_CPU_PARTITION_AGGREGATES.json`.

**Schema gate finding:** existing scenario fields cannot express this CPU timeline as an additive CPU load without changing their established GPU meaning:

- `P/api/schemas.py:199–255` defines `WorkloadEventSpec`: `starting` / `job_end` are GPU job events; the event has `node_count`, `hardware_profile_id`, and `workload_class`, but no CPU-power or additive-MW value. `P/runtime/scenario_factory.py:1701–1718` turns those fields into a `WorkloadSignal`. `P/core/asset_modules.py:464–495` calculates its draw from `nodes × hardware_profile.rated_kw × PUE_base / 1000`; `workload_class` selects ramp timing (`:450–458`), not CPU watts.
- `P/api/schemas.py:1579–1603` describes `TenantWorkloadEvent` as a scripted GPU burst with an integer `gpus` count. `P/core/simulation_core.py:1247–1266` adds `gpus × 0.0007 MW`; this is not CPU package power.
- `P/api/schemas.py:1752–1759` defines `base_load_mw` as steady site load before the first burst, not a time series.
- `P/api/schemas.py:1906–1913` defines `gpu_load_profile` as a multiplier. `P/core/simulation_core.py:1223–1245` builds demand from GPU modules and applies that multiplier to all compute draws; using it as a separate additive CPU timeline would alter the existing GPU staircase.

At the time of the original stop, faithfully representing this profile required an additive field and runtime handling. The subsequent approved D6a-X amendment below authorizes that narrowly scoped additive field; this original stop record is retained for provenance.

The user resolved the scope gap by authorizing `non_gpu_load_profile_mw` in D6a-X. CPU rows are not encoded as GPU `starting` events, tenant GPU bursts, or a multiplier.

## D6a.2r evidence files

- `tools/dr_isl/d6/S10_D6A_PROVENANCE_REPRO.json` — regenerated S10-derived candidate JSON; not the raw CSV or a row-level extract.
- `tools/dr_isl/d6/S10_D6A_PROVENANCE_REPRO.build.json` — aggregate generator result.
- `tools/dr_isl/d6/D6A_2R_DIFF.json` — exhaustive canonical diff patterns and normalized comparison.
- `tools/dr_isl/d6/D6A_2R_PROVENANCE.json` — file hashes and invocation/settings.
- `tools/dr_isl/d6/D6A_2R_60TICK_SUMMARY.json` — matching first-60-tick RunManager hashes.
- `tools/dr_isl/d6/D6A_3_CPU_PARTITION_AGGREGATES.json` — partition-level aggregates only.

## Data handling and workspace

- Input `attached_assets/supercloud/slurm-log.csv`: **103,165,427 bytes**, SHA-256 `27259e5b8e6daecd80b7853126af40ba759bc25edc9053fc174ef7a4f186aa01`.
- Input `attached_assets/supercloud/tres-mapping.txt`: **111 bytes**, SHA-256 `4897c5cf1575664217f93d9c66cda3c06cae9d90f827a5dadc5483044dd64a51`.
- `git check-ignore -v` confirms both inputs are ignored by `.gitignore:52`; neither input is tracked. No raw CSV or row-level extract was added.
- The original tracked `P/config/scenarios/S10_mit_supercloud_2021-08-11.json` remains untouched. Current D6a-X, generator and candidate details follow in the resumed-work sections below.

## D6a-X — additive non-GPU load profile

- The authorized additive field is `ScenarioSpec.non_gpu_load_profile_mw`, optional and absent by default (`P/api/schemas.py:1916–1922`); validation enforces finite non-negative MW, non-negative strictly increasing times, and the scenario horizon (`:2529–2548`). Lookup is zero before the first point and zero-order hold thereafter (`P/core/simulation_core.py:1358–1375`).
- It enters demand once at `P/core/simulation_core.py:1365–1368` as measured IT load; existing GPU/compute telemetry remains separate. Cooling consumes per-GPU job draws at `:1246–1256, 1275–1277`; when this profile is configured, the CPU IT term is also sent through the existing scalar IT-load input at `:1356–1363` (`record_compute_sample`). It is not modeled as a GPU job draw. Although the code comment at `:1258–1260` describes this as separate from GPU job envelopes, the full-day candidate exposed shared-envelope interference; see the D6a STOP finding below.
- `p_non_gpu_demand_mw` is `None` when unused (not numeric zero), is persisted/wire-serialized only when configured (`P/core/models.py:1341–1344`, `P/runtime/persistence.py:123–124`, `P/runtime/run_manager.py:437–438`), and therefore is omitted from physical identity when absent (`P/core/physical_identity.py:55–59`). Configured profile ticks include their numeric value, including explicit zero.
- The frontend type was updated only; no scenario-view UI was changed. The current frontend has a GPU profile editor, but no straightforward read-only time-series view for this CPU profile; this remains a separate UI follow-up.
- TC-ISL-44–49 cover validation, zero-order-hold boundaries, additive demand with unchanged GPU fields, ledger/unserved behavior, forecast exclusion, and absent-field identity. D6a-X full-suite runs: `PYTHONHASHSEED=1` and `987654321` each reported **2,231 passed, 15 failed, 3 skipped, 23 xfailed** (JUnit totals 2,275, with xfails included in skipped); the 15 failing IDs were identical, with **0 added** relative to Phase 6c and only the waived `test_gpu_load_profile` removed in these runs. Evidence is in `tools/dr_isl/d6/phase6ax/D6AX_SUITE_COMPARISON.json`.
- Commit sequence: `ac45beef3e127c009a81b9bdd7184ed68fcd4b8d` implementation; `a5a1a525aaf8761307bf951d07e48b1d0ad9e392` tests; `22fa650e3a3b6dfa2395c99f3e52bb4b5114d84d` docs. The D6a-X docs are `docs/d6a-x-non-gpu-load-profile.md`.

## D6a.3–D6a.6 — resumed candidate generation and runs

The user authorized D6a-X and instructed continuation from D6a.3. The CPU candidate uses all active partitions and the invocation recorded by the generator. Partitions with no CPU-only rows were not assigned a power value; any unsupported partition with a CPU-only row makes generation fail.

- The unchanged GPU scaling factor is `11.561228264890863` chassis/GPU, derived as `(50.0 MW × 1000 kW/MW ÷ 10.2 kW/chassis) ÷ 424 peak GPUs`. CPU watts use the same chassis/GPU multiplier as the GPU profile.
- CPU-only activity: **426 jobs**, **9,918.973889 core-hours** total. `xeon-p8`: 416 jobs / 9,360.002500 core-hours; `normal`: 9 / 554.402500; `db`: 1 / 4.568889; `gaia` and `test`: 0. Only these three partitions appeared in CPU-only rows.
- CPU-only package-load profile (320 event-boundary points): min/mean/p95/max **0 / 0.0330180503 / 0.2838281539 / 0.2940815182 MW**, **0.7924332062 MWh**. GPU profile: min/mean/p95/max **0 / 20.9608758056 / 50.0004000000 / 50.0004000000 MW**, **503.0610193333 MWh**. CPU is **0.1572745%** of total IT energy (`0.7924332062 / (0.7924332062 + 503.0610193333)`).
- Sensitivity with `normal` and `db` changed from 7.5 to 6.875 W/core, keeping `xeon-p8` at 6.875: CPU energy **0.7883942088 MWh**, a delta of **−0.0040389974 MWh**; total IT demand changes by the same **−0.0040389974 MWh**.
- Generator evidence: `tools/dr_isl/d6/D6A_3_CPU_GENERATOR_REPORT.json`, `D6A_3_CPU_PARTITION_AGGREGATES.json`, `S10_2021-08-11_cpu_candidate.build.json`, and `S10_2021-08-11_cpu_candidate.json`. Generator tests after the D6a generator changes: **20 passed in 0.60s** (`D6A_GENERATOR_TESTS_FINAL.log`).

## D6a.3–D6a.6 — historical STOP at the additivity gate (pre-X2; superseded below)

The four pinned RunManager runs completed: current S10 twice and the CPU-only candidate (option (a)) twice. Each run completed 17,280 ticks / 86,400 s, with zero physical-balance failures and no island collapse. Repetitions were deterministic within each case:

| Case | Repetitions | Physical SHA-256 | Demand MWh | Served MWh | Unserved MWh | Peak demand MW | Peak unserved MW | Dispatch curtailment MWh | Starts / stop transitions | BESS SoC min / max / final | Invalid-frequency fraction | Hz min / max |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| Current S10 | 1–2 | `3e24904fd7e8f71afa1f5b30ec2f2958a6b43e7670ab9fefae04f3440aa57bff` | 620.9086288248269 | 612.4446369086435 | 8.463991916183423 | 61.8004944 | 29.800477993748466 | 48.51928134811006 | 38 / 70 | 0 / 1 / 0.9999999647449559 | 0.034375 | −749.6905479257669 / 60.54595734564584 |
| CPU-only candidate (a) | 1–2 | `dfbdfa4f9750880e367db375d8a8924daf4f3f2dd6f958dff8cc92167a2ea721` | 545.5274187544242 | 541.3373787346858 | 4.190040019738433 | 61.74367333190125 | 25.135510124196273 | 62.23000989991306 | 40 / 74 | 0 / 1 / 0.9999999966596756 | 0.09947916666666666 | −620.2810117444672 / 60.54594906943219 |

`turbine_fuel_mmbtu` is `null` in all four runner summaries; this runner did not provide a turbine-fuel total. Neither case collapsed; each had 0 balance failures and 0 reserve-floor refusals. Full aggregate records are `tools/dr_isl/d6/D6A_5_CURRENT_REP1.json`, `D6A_5_CURRENT_REP2.json`, `D6A_5_CPU_REP1.json`, and `D6A_5_CPU_REP2.json`.

**STOP: option (a) is not additive to the existing GPU/cooling demand.** The CPU-only profile contributes 0.792433206207994 MWh, but total demand in the candidate is 75.3812100704027 MWh *lower* than current S10 (545.5274187544242 versus 620.9086288248269 MWh). The candidate also changes served, unserved, curtailment, starts, frequency, and the physical hash. Do not derive or apply the initial SoC and do not run option (a)+(c) until this is resolved. The tracked S10 scenario was not edited.

A short, in-memory 200-tick comparison (same seed and wall-clock pin, with the package working directory set) found:

| Tick / sim time | GPU compute MW, current → candidate | Non-GPU MW, current → candidate | Cooling MW, current → candidate | Total demand MW, current → candidate |
|---|---|---|---|---|
| 1 / 5 s | 0.006712166666666666 → 0.006712166666666666 | absent → 0.00007948344432112468 | 0 → 0 | 0.006712166666666666 → 0.006791650110987791 |
| 200 / 1,000 s | 31.339397999999996 → 31.339397999999996 | absent → 0 | 6.267879561488238 → 0.0483276 | 37.60727756148823 → 31.387725599999996 |

The code path identifies the cause: `simulation_core.py:1355–1359` records GPU job draws and then sends the CPU series through `CoolingModule.record_compute_sample`. In `core/asset_modules.py:787–805`, a scalar-path step-down walks the shared `_envelopes` collection in reverse and closes the youngest live envelope without distinguishing synthetic scalar envelopes from GPU job envelopes. The CPU profile has a zero transition at 527 s, the same time as a GPU workload start in the generated event series; the scalar step-down can therefore close a GPU cooling envelope. That contradicts the D6a-X requirement that the CPU term not change GPU cooling/workload semantics.

This was the state before the approved D6a-X2 resumption below; the shared-envelope issue is now corrected in the candidate implementation.

## D6a-X2 / IMPL-ISL-23 — per-job cooling isolation

- The profile uses one per-job key, `non_gpu_it`, declared at `P/core/models.py:47` with a `PROPOSED_HERE` rationale. The factory creates that envelope only when the profile is configured (`P/runtime/scenario_factory.py:1303–1306`). Each tick adds the measured CPU IT value to the existing per-job draw map and makes one `record_job_compute` call (`P/core/simulation_core.py:1351–1362`); only the CPU key is ended at the final zero point (`:1369–1374`). The former scalar `record_compute_sample` call was removed.
- Cooling envelope lifecycle supports the required profile shape: `record_job_start` creates a keyed envelope (`P/core/asset_modules.py:710–716`); `record_job_compute` updates only keys supplied and ends omitted active job keys (`:728–756`); `register_job_end(job_id, end_t)` ends the named envelope (`:718–726`). The CPU key is present in every configured per-tick map, including intermediate zero values, so a CPU step-down cannot end a GPU key. The test places a GPU start on the same tick as CPU step-down, then verifies both GPU histories remain unchanged and only `non_gpu_it` has `end_t=25.0` (TC-ISL-50).
- TC-ISL-51 runs both current S10 and the full CPU-profile candidate for 17,280 ticks with seed 1729. GPU compute energy is identical; the GPU-attributable cooling trajectory is computed by summing the candidate's non-`non_gpu_it` envelopes after each step and comparing it tick-by-tick with current S10 cooling. Its maximum MW difference is required to be ≤ `1e-9`; the total-demand increase must equal CPU IT energy plus CPU-envelope cooling within `1e-6 MWh` (`PROPOSED_HERE`, 1 Wh tolerance). Both TC-ISL-50 and TC-ISL-51 passed; the focused module passed **8/8**.
- The 1 Wh comparison tolerance is declared in the test at `P/tests/test_d6a_non_gpu_load_profile.py:227–229`; it is above accumulated floating-point noise and negligible relative to the measured energies. TC IDs checked: **TC-ISL-50** and **TC-ISL-51** had no collision.

### IMPL-ISL-23 — read-only scalar/per-job interaction diagnosis

- Current `record_compute_sample` call sites are tests only: `P/tests/test_classifier.py:277`; `P/tests/test_formulas.py:102,103,116,1033,1043,1092,1102`; `P/tests/test_13_5_criteria.py:65,146`; `P/tests/test_cooling_mw_blackbox.py:93`; and `P/tests/test_cooling_lag_tc03.py:76`. There is no production caller after X2.
- Current `record_job_compute` call sites are `P/core/simulation_core.py:1362`; `P/tests/test_d6a_non_gpu_load_profile.py:151,157,165,173,181,189`; `P/tests/test_forecast_path.py:1121,1126,1162,1242,1255`; and `P/tests/test_formulas.py:1145`.
- No seeded scenario JSON contains `non_gpu_load_profile_mw`. Before X2, the D6a CPU candidate was the only scenario run that used both APIs in one run; after X2, no production run uses both. The aggregate inventory and call-site list are in `tools/dr_isl/d6/D6AX2_IMPL_ISL_23.json`.
- Scratch counterfactual, direct `ctx.step()` path, 17,280 ticks: original shared scalar step-down yielded GPU compute **514.3713154094444 MWh**, CPU IT **0.7922408944087328 MWh**, cooling **30.363862450571027 MWh**, total demand **545.5274187544242 MWh**. Restricting the experimental scalar step-down to `_syn_*` envelopes yielded the same GPU and CPU IT energy, cooling **106.69541020299484 MWh**, total demand **621.858966506848 MWh**. Cooling and demand each increased **76.33154775242381 MWh**. This is a scratch counterfactual, not a proposed second cooling implementation.
- The pinned-run evidence helper now sums cumulative per-unit `turbine_fuel_telemetry` rows when modelled, rather than relying only on the aggregate tick field (`tools/dr_isl/d6/d6a_run_pinned.py`). The current S10 config declares five frame turbines with no fuel model (`config/scenarios/S10_mit_supercloud_2021-08-11.json`); therefore the correct telemetry is `turbine_fuel_modelled=false`, status `not_modelled`, and total MMBtu `null`. A non-null fuel value cannot be produced by an evidence-script correction without inventing a fuel model or changing the scenario, both outside this approval.

### D6a-X2 gate status

Both real-package full-suite runs completed. With `PYTHONHASHSEED=1`: 2,233 passed, 15 failed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed (807.19 s). With `PYTHONHASHSEED=987654321`: 2,233 passed, 15 failed, 3 skipped, 23 xfailed, 54 warnings, 3 subtests passed (810.57 s). Both failing-ID sets are identical to the Phase 6c baseline minus only the waived `tests/test_gpu_load_profile.py::test_gpu_load_profile`; added failures = 0, removed = that waived node, remaining = the other 15 baseline failures. The focused D6a-X module passed 8/8, including TC-ISL-50 and TC-ISL-51. Logs, JUnit, the failing-ID sets, and comparison JSON are in `tools/dr_isl/d6/`.

## D6a.4 — initial SoC derivation

The corrected X2 CPU candidate was run through the pinned RunManager path for 200 ticks (1,000 s), seed 1729, wall clock 1792454400.0. This covers the specified startup-surplus window through its crossing at tick 112 / 560 s; no full-day result is claimed. The 200-tick physical hash is `c27b81e38b960ec4936562556034378db0aae4c49f49c5ed01c33c829068b576`.

- At the first demand-above-on-bus-turbine-MSL point, demand is **27.966987896684998 MW** and on-bus turbine MSL is **26.25 MW**. Dispatch curtailment from t=0 up to that point is **1.0016770896947318 MWh** (`tools/dr_isl/d6/D6AX2_D6A4_SOC_DERIVATION.json`).
- Usable BESS energy is **14.0 MWh**. `BessUnitSpec.initial_soc_fraction` has schema bound `ge=0.1` (`P/api/schemas.py:471–476`); `BessConfig` declares no separate runtime minimum-SoC field (`P/core/models.py:1000–1024`). Treating the explicit schema lower bound as the requested floor, the calculation is `max(0.1, 1 − 1.0016770896947318 / 14.0) = 0.9284516364503763`; the floor does not bind. If a distinct physical minimum was intended, it is not represented in the current model.
- The generator produced `tools/dr_isl/d6/S10_2021-08-11_cpu_candidate_a_plus_c.json` with `initial_soc_fraction=0.9284516364503763`; compared with the (a)-only candidate, all top-level fields outside `bess_units` and `description` are equal, and the only BESS value change is that initial SoC fraction. SHA-256: `6dfbd4986323ae7a1085bf84f15f912ac492a919dd8720723796a808ae13273e`. Formula evidence is `tools/dr_isl/d6/D6AX2_D6A4_SOC_FORMULA.json`.

## D6a.5 fuel-model finding (historical hold; superseded by user approval)

The evidence helper now reads the final per-unit `turbine_fuel_telemetry` rows, but the successful 200-tick S10 run reports `turbine_fuel_modelled=false`, `turbine_fuel_status="not_modelled"`, and `turbine_fuel_mmbtu=null` for all five units. The scenario's frame-turbine fuel input is absent; `P/runtime/scenario_factory.py:909–917` returns `None` for a frame turbine with no `fuel` object, and `P/core/asset_modules.py:1298–1323` intentionally emits null fuel values when `config.fuel is None`. Therefore correcting the evidence script cannot populate MMBtu. Adding a fuel model to the generated candidate would require a sourced model assumption, not an evidence-script correction.

The user then approved continuing with turbine fuel reported as `null` / `not_modelled`; this supersedes the earlier stop. No fuel assumption was added.

## D6a.5 — completed pinned full-day candidate runs

All six requested runs used the pinned RunManager path (`build_run_context_from_spec(..., execution_mode="headless")`, then `RunManager.start_run(ctx)` in `tools/dr_isl/d6/d6a_run_pinned.py:95–107` and its run loop). Each completed 17,280 ticks / 86,400 s with seed 1729 and wall clock 1792454400.0. The two physical hashes match within each case. The complete run records, start/stop event timelines, seed manifests and hashes are in `tools/dr_isl/d6/D6A5_FINAL_RUNS.json` (SHA-256 `4742f6d2faf6628c54667592219387cd14799a8995437a8970aaae9103ce8e66`).

| Case | Repetition physical SHA-256 | Demand / peak MW | Served / unserved MWh | Peak unserved MW | Dispatch curtailment MWh | Turbine fuel MMBtu | Starts / stops | BESS SoC start / min / max / final | Reserve refusals | Collapse | Invalid ticks / fraction | Hz min / max | Balance failures |
|---|---|---|---|---:|---:|---|---:|---|---:|---|---|---|---:|
| Current S10 | 1–2: `3e24904fd7e8f71afa1f5b30ec2f2958a6b43e7670ab9fefae04f3440aa57bff` | 620.9086288248269 / 61.8004944 | 612.4446369086435 / 8.463991916183423 | 29.800477993748466 | 48.51928134811006 | `null` (`not_modelled`) | 38 / 70 | 1.0 / 0.0 / 1.0 / 0.9999999647449559 | 0 | No | 594 / 0.034375 | −749.6905479257669 / 60.54595734564584 | 0 |
| CPU-only candidate (a) | 1–2: `e819540659528686bd40c706290dc09883d87b865e25df17da970f4550fefa1b` | 621.8578481855469 / 61.8004944 | 616.3219971384977 / 5.5358510470491495 | 16.800494399999998 | 46.772686724380485 | `null` (`not_modelled`) | 37 / 68 | 1.0 / 0.0 / 1.0 / 0.9999999644397214 | 0 | No | 521 / 0.030150462962962962 | −139.16266514361757 / 60.54594906943219 | 0 |
| CPU candidate (a)+(c) | 1–2: `87b7877a9c1f3bc2e6b547d823866ef8f7a9c42b9908f7409729dedbb6408803` | 621.8578481855469 / 61.8004944 | 616.3220787729175 / 5.535769412629417 | 16.800494399999998 | 45.771009634685754 | `null` (`not_modelled`) | 37 / 68 | 0.9284516364503763 / 0.0 / 0.9999999939221045 / 0.9999999644397214 | 0 | No | 519 / 0.030034722222222223 | −139.16266514361757 / 60.48104317148639 | 0 |

`turbine_fuel_mmbtu` is null for all five frame turbines in all cases (`turbine_fuel_modelled=false`); this is the observed model output, not a substituted estimate. The per-unit fuel statuses and the full start/stop timelines (146 transition rows for current S10; 142 for each candidate) are recorded per repetition in the JSON evidence.

Changes:
- Current S10 → (a): total demand rises **0.9492193607200079 MWh**. The sampled non-GPU IT contribution is **0.7922408944087328 MWh** (`tools/dr_isl/d6/D6AX2_IMPL_ISL_23.json`); the remaining **0.1569784663112751 MWh** is the CPU-envelope cooling contribution. This is consistent with the X2 full-scale additivity test: GPU compute and GPU-attributable cooling are unchanged. Served energy rises **3.8773602298542755 MWh** and unserved falls **2.928140869134273 MWh**; peak unserved falls by **12.999983593748468 MW**; curtailment falls **1.7465946237295782 MWh**. Starts/stops change from **38/70** to **37/68**. Both runs retain zero balance failures and no collapse.
- (a) → (a)+(c): demand and peak demand are unchanged. The starting SoC is reduced from **1.0** to **0.9284516364503763**, the D6a.4-derived value. Curtailment falls by **1.0016770896947307 MWh**, matching the measured startup-surplus window used in the derivation. Unserved changes by **−0.00008163441973252361 MWh**; starts/stops, minimum SoC, refusals, collapse status and balance-failure count are unchanged. Invalid ticks decrease from **521** to **519**.
- Current S10 → (a)+(c): demand rises **0.9492193607200079 MWh**, unserved falls **2.9282225035540055 MWh**, curtailment falls **2.748271713424309 MWh**, and starts/stops change from **38/70** to **37/68**. Fuel remains unmodelled in each case.

The active advisory backend returned no proposal on the full-run invocations. The RunManager comment states advisory agents write only to the gate and dispatch is bit-identical with agents on or off (`P/runtime/run_manager.py:3260–3264`); `AdvisoryRouter` returns `None` both on backend failure and immediately when no keys are configured (`P/runtime/advisory_router.py:82–88, 124–145`). A separate 200-tick no-backend CPU-candidate run matched the pinned D6a.4 hash `c27b81e38b960ec4936562556034378db0aae4c49f49c5ed01c33c829068b576`; an additional full-day no-backend CPU run also matched the active-backend CPU hash. These parity checks are in `D6A5_ADVISORY_NOOP_PARITY.json` and `D6AX2_D6A5_CPU_REP2.json`.

The first combined runner invocation completed the first current-S10 repetition, then stopped before the next scenario because a relative input path was resolved after the helper changed its working directory. That completed result was retained; remaining invocations used absolute input paths. A separate no-backend A+C attempt timed out before writing a summary and is not included. The six reported runs above all completed.

The tracked `P/config/scenarios/S10_mit_supercloud_2021-08-11.json` was not edited. Raw `slurm-log.csv`, `tres-mapping.txt`, and row-level extracts remain untracked.
