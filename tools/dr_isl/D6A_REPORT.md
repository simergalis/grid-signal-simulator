# D6a candidate regeneration — stopped at provenance gate

Package root `P`: `attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/`.

**Status:** STOP at D6a.2. The unchanged generator output does not match the existing S10 scenario after canonical JSON sorting. D6a.3–D6a.6 were not started.

## D6a.1 — generator import

- Source branch: `supercloud-ingest-gate1`, commit `0aac1a42ec95ba6d6ba612bf3272bb71868662a5` (2026-10-20 11:30:18 -07:00; author Claude).
- Imported unchanged; source Git blob IDs matched for the imported files. Import commit: `46cd94e00e073a542ad2452df64e5be671c20678` — `D6a: import SuperCloud generator from supercloud-ingest-gate1 @0aac1a42ec95ba6d6ba612bf3272bb71868662a5`.
- Files: `tools/supercloud/{.gitignore,make_scenario.py,convert_to_kube_trace.py,profile_slurm_log.py,run_replay.py,test_make_scenario.py,test_convert_to_kube_trace.py}`.
- Tests: `python3 -m pytest -q tools/supercloud/test_make_scenario.py tools/supercloud/test_convert_to_kube_trace.py` → **16 passed in 0.95s**. `profile_slurm_log.py --help` and `run_replay.py --help` both exited 0.

## D6a.2 — provenance gate

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
- **Not identical. First difference:** `$.base_load_mw`; current S10 has the key with value `null`, while the unchanged generator output omits the key. This is a semantic shape difference, not JSON key ordering. Raw-file hashes and the first-difference record are in `tools/dr_isl/d6/D6A_2_PROVENANCE.json`.

Because D6a.2 requires an unchanged-generator match, the provenance gate failed. I did not modify the generator, any scenario/config/test file, or simulator code; did not create a CPU-load or SoC candidate; and did not run simulations. The generated per-job scenario reproduction was removed after comparison, so no row-level extract is retained.

## Data handling and workspace

- Input `attached_assets/supercloud/slurm-log.csv`: **103,165,427 bytes**, SHA-256 `27259e5b8e6daecd80b7853126af40ba759bc25edc9053fc174ef7a4f186aa01`.
- Input `attached_assets/supercloud/tres-mapping.txt`: **111 bytes**, SHA-256 `4897c5cf1575664217f93d9c66cda3c06cae9d90f827a5dadc5483044dd64a51`.
- `git check-ignore -v` confirms both inputs are ignored by `.gitignore:52`; neither input is tracked. No raw CSV or row-level extract was added.
- No edits were made to `config/scenarios/`; no D6a.3–D6a.6 work was performed. The generator import commit is present; this report and its aggregate evidence are report-only changes.
