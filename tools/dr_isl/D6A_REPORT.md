# D6a candidate regeneration — revised provenance passed; stopped at CPU hardware gate

Package root `P`: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

**Status:** The original raw-JSON stop was superseded by D6a.2r. D6a.2r passes after ScenarioSpec normalization, and the 60-tick physical hashes match. STOP at D6a.3 because the published sources do not identify the CPU model for every partition containing CPU-only work. No generator extension, CPU candidate, SoC candidate, or full candidate runs were made.

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

## D6a.3 — STOP: CPU-model provenance incomplete

The aggregate scan covered all partitions and all jobs overlapping 2021-08-11 UTC; a CPU-only row has allocated TRES id 1 cores and neither GPU TRES id 1001 nor id 1002. It found **426 jobs / 9,918.973889 core-hours**:

| Slurm partition | CPU-only jobs | Allocated cores | Core-hours | GPU-allocated jobs in partition |
|---|---:|---:|---:|---:|
| `normal` | 9 | 1–25 | 554.402500 | 154 |
| `xeon-p8` | 416 | 1–384 | 9,360.002500 | 0 |
| `db` | 1 | 32 | 4.568889 | 0 |

Aggregate evidence only (no row-level extract) is in `tools/dr_isl/d6/D6A_3_CPU_PARTITION_AGGREGATES.json`. `gaia` and `test` had no CPU-only rows during the day.

The MIT Supercloud Dataset paper, Table II (https://arxiv.org/abs/2108.02037), identifies the physical GPU-accelerated nodes as dual Intel Xeon Gold 6248 and the CPU-only nodes as dual Intel Xeon Platinum 8260. MIT SuperCloud’s systems page (https://mit-supercloud.github.io/supercloud-docs/systems-and-software/) maps `xeon-p8` to Platinum 8260 and `xeon-g6-volta` to Gold 6248. Intel ARK gives Gold 6248 as 150 W / 20 cores = **7.5 W/core**, and Platinum 8260 as 165 W / 24 cores = **6.875 W/core**:

- Gold 6248: https://www.intel.com/content/www/us/en/products/sku/192446/intel-xeon-gold-6248-processor-27-5m-cache-2-50-ghz/specifications.html
- Platinum 8260: https://www.intel.com/content/www/us/en/products/sku/192474/intel-xeon-platinum-8260-processor-35-75m-cache-2-40-ghz/specifications.html

Those sources do not map the observed `db` Slurm partition to either processor model. They also do not explicitly map the `normal` Slurm label to a physical node type; although `normal` has GPU-allocated jobs in this trace, that alone does not establish the CPU model for its CPU-only jobs. Because D6a.3 requires a citable CPU model for every partition and forbids guessing, **STOP here**. I did not calculate a complete CPU MW profile or CPU share, change `tools/supercloud/`, add CPU events, derive a new initial SoC, run the three candidate cases, or begin D6a.4–D6a.6.

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
- No edits were made to `config/scenarios/`, simulator code, tests, or the generator. The generator import commit is present; the D6a.2r candidate/evidence and this report are the only new files.
