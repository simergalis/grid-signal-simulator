# DR-2026-10-20-ISLAND-COLLAPSE — Phase 2c STOP report

Status: STOPPED at the unchanged-H identity gate, before application implementation.
Base: 2b39685a885d945f91cba1ffa8dcaec36f084985.

## Triggered constraint

Hard constraint 3 requires all four H expansion paths, study identities, cache entries and results to remain unchanged; any identity change is STOP-and-report. Item 2c.3 requires the shared base JSON diesel start to change from 3600.0 to 10.0 seconds.

The existing H expander reads that very base JSON. These requirements cannot both be met by leaving the existing H expansion path unchanged.

## Source evidence

- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/phase2b_reference.py:95–106: reads the configured/default base JSON and deep-copies it into every H expanded spec.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/phase2b_reference.py:117–121: replaces the H description; the requested base-description append does not explain the observed H identity delta.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/runtime/phase2b_reference.py:161–164: removes compact-reference metadata keys; it does not remove or pin diesel_power_block.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py:256–261: all four H references keep this expansion path.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/executor.py:66–81: identity retains the expanded parameter_set, excluding kube_clusters, slurm_config and workload_events but NOT diesel_power_block.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/study_harness/manifest.py:23–33: serializes that identity payload with sorted keys and computes SHA-256.
- attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/config/scenarios/scenario-uneven-multisched-01.json:191–194: current diesel start=3600.0, residual ramp=60.0, advisory_only.

## Read-only controlled check

Scratch script: /tmp/DR-ISL-phase2c/preflight.py.
Printed output: /tmp/DR-ISL-phase2c/preflight-identities.json and preflight.log.

The script called the real StudyRunExecutor._expanded_spec and make_study_run_identity, without executing a probe, constructing a run context, stepping the engine, starting RunManager or using a cache.
It expanded each H reference once with the current base and once with ONLY the approved 2c.3 change represented by an in-memory Path.read_text substitution. The proposed description append was also present in that in-memory base. The file itself was never written.

Controlled identity inputs were held fixed in both conditions: seed=42, tick_seconds=5.0, engine_commit=harness_commit=2b39685a885d945f91cba1ffa8dcaec36f084985. These are dependency-test digests, NOT claims about the identifiers of archived certified records. Holding the commit arguments fixed isolates the scenario-input change.

For every reference the entire expanded-spec diff consists of exactly:

    $.diesel_power_block.delta_t_start_s: 3600.0 -> 10.0

| Scenario | Arm | Current identity digest | Proposed identity digest | Identical |
|---|---|---|---|---|
| scenario-h1-k8s-ray-24h | baseline | ea9edfd7050f6c25616287ff225628406d15819b3cc6c6dbd9af45ade9e70d43 | 4298830f1884f2993686abb41c037555d2d0669c48cf96a8443157255657d786 | false |
| scenario-h1-k8s-ray-24h | informed | 762b022a034fad345759358dcdc0c27d0a71560f40bbe895d896db7aef83b79b | 966a4d15d0122c61ac2a10d27bf65e6b6bbeec5b0134e1e760fd666ad47994d2 | false |
| scenario-h1-k8s-ray-7d | baseline | 073cc424d8245472ff2fa278b63350a4949cfe710a583142a623a6ef82683ffe | cd705935375abb95c6c8deb2963e9361414a225411d801632337d48007a6fcdf | false |
| scenario-h1-k8s-ray-7d | informed | 4492f3689c3b76898f4e9cc06c1068e7a3bcef9b9d985c0d82a4986645845884 | cb479b93e2f482d33d7136ee31f75f237c0a746c67b3b4988d26f5f75d0392a8 | false |
| scenario-h2-slurm-24h | baseline | 0870547fd37c31d2e3721aa616be4f6b543dd8bb5e4e777371fd7418a3a7cd92 | eed021fb47c3b58bf25fd001e4847cad46ab36ab1ed9a24237edb380fba28ce9 | false |
| scenario-h2-slurm-24h | informed | c67ecdab5b4d602b789bfc0db799dadb7e9287b93b9daf566c5c75265f0cdcd4 | 38c7ae999ffbc5c2e65286ebe28fe135119e16530b0bfc4d5dbb6efcfcef7daa | false |
| scenario-h2-slurm-7d | baseline | 7e2987d4c829b2747066db93df38a8051ca7f7343d8ead4859862b54729149e5 | 98bbdc93af95c62a1ed78f7a1e543a433637a01f8cc2bc8a4cda10f8f0b11bcd | false |
| scenario-h2-slurm-7d | informed | 36f24855cdd81647c0ac74e934ba80de979554912ea181497ff5091e01a6f9da | c92b4d63c38a5abc36fc1265f964ef110065bc247e7d07408d9b75bac256a63d | false |

Result: 8/8 identity comparisons differ. This satisfies the explicit STOP condition; no H metrics rerun is necessary to establish that the identity gate fails. No inference is made that numerical H metrics must change, because no simulation was run.

## 2c.1–2c.7 disposition

- 2c.1 D8: NOT IMPLEMENTED; base-demo canonicalization and provenance metadata not changed.
- 2c.2 D9b: NOT IMPLEMENTED; build/API/study warning metadata and UI unchanged.
- 2c.3 D9c: NOT WRITTEN; the on-disk start remains 3600.0 seconds and the description is unchanged. The proposed value was used only by the read-only dependency check.
- 2c.4: TC-ISL-17/18 not added; no existing tests edited or executed.
- 2c.5: No simulations, study pairs, cache resets or regression runs started. H cache entries and stored results remain untouched. No new energy, fuel, physical hash, compare_runs or reserve-refusal figures are claimed.
- 2c.6: Full suite NOT RUN because the pre-implementation gate stopped the phase.
- 2c.7: No implementation commit. The STOP report is copied to tools/dr_isl/PHASE_2C_REPORT.md and committed separately; report-only commit hash and final git status are supplied in the final chat response.

## Integrity and permitted outputs

Base JSON SHA-256 before and after the in-memory check: ea32ac762d06311320e377f0d1e8daa86c9560317098d725d1a66dc8499c6292.
preflight.py asserts byte equality of the base file after the check.
Printed counters: production_files_changed=0, simulation_runs=0, cache_operations=0.
Initial HEAD was verified as the requested base; initial git status was empty.

Only repository output: tools/dr_isl/PHASE_2C_REPORT.md. Scratch files are confined to /tmp/DR-ISL-phase2c/. No app/config/scenario/test/parameter/runner file was modified. No publish, deploy, push or Phase 3 work occurred.

## Required clarification before resumption

Preserving the old H identity inputs while correcting the shared base needs an explicitly authorized exception, such as preserving the H legacy diesel block in the reference expansion or using a frozen legacy reference base. Either changes the presently mandated unchanged expansion/input dependency or requires an additional asset. Neither is implemented or selected here. Alternatively, accepting new H identities would relax constraint 3. Authorization must resolve this conflict before resuming; no identity field was suppressed to hide the delta.

STOP — END OF PHASE 2c ATTEMPT. No implementation or later phase started.
