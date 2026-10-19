# DR-2026-10-19-SUPERCLOUD-INGEST — MIT SuperCloud Slurm log as replay input

**Status:** PROPOSED. Gate 1 (schema profile on real data) not yet run.
**Author:** Claude, for Lloyd Spencer
**Date:** 2026-10-19

## 1. Context

We want real scheduler traces to drive GridSignal's Kubernetes, Slurm and Ray
paths. The MIT SuperCloud Dataset (TX-GAIA cluster) is the best public AI/HPC
trace with GPU jobs:

- 460,497 jobs, of which 98,177 requested GPUs.
- 3,425 jobs are labelled DNN workloads.
- Per-job CPU time series at 10 s and GPU time series at 100 ms, including `power_draw_W`.

The data is Slurm-native only. The release materials do not mention
Kubernetes or Ray.

- **Location:** `s3://mit-supercloud-dataset/datacenter-challenge/202201/`, us-west-2, anonymous (`--no-sign-request`), about 2 TB in total.
- **Licence:** CC BY-NC-ND 4.0 per the AWS Open Data registry. The GitHub repo's MIT licence covers its scripts only.
- **Version 2:** published as "The MIT AI Systems Dataset", HPEC 2026. It is listed as coming October 2026 and will require a data-use agreement.

## 2. What is established vs. assumed

### Established (column names)

The `slurm-log.csv` header comes from a printout of the real file in
`MIT-AI-Accelerator/MIT-Supercloud-Dataset/notebooks/Intro-to-MIT-Supercloud-Dataset.ipynb`.
It has 29 columns:

`id_job, id_array_job, id_array_task, id_user, kill_requid, nodes_alloc,
nodelist, cpus_req, derived_ec, exit_code, gres_used, array_max_tasks,
array_task_pending, constraints, flags, mem_req, partition, priority, state,
timelimit, time_submit, time_eligible, time_start, time_end, time_suspended,
track_steps, tres_alloc, tres_req, job_type`

`tres-mapping.txt` maps the TRES IDs as follows (from the README):

| ID | Resource |
|---|---|
| 1 | cpu |
| 2 | mem |
| 3 | energy |
| 4 | node |
| 5 | billing |
| 6 | fs |
| 7 | vmem |
| 8 | pages |
| 1001 | gpu:tesla |
| 1002 | gpu:volta |

The notebook identifies GPU jobs by the presence of `1001` or `1002` in `tres_req`.

### Discrepancies noted

- The notebook reads `scheduler-log.csv`, but the README names the file `slurm-log.csv`.
- The README describes `labelled-slurm-log.csv` but does not list its header. Gate 1 diffs it against the main log.

### Assumed (value encodings)

These must be confirmed at Gate 1 before any converter code. They follow
slurmdbd `job_table` conventions and are tested as H1–H9 by
`tools/supercloud/profile_slurm_log.py`:

| ID | Hypothesis |
|---|---|
| H1 | `time_*` are Unix epoch seconds; `time_start = 0` means the job never started. |
| H2 | `tres_req` and `tres_alloc` use the format `id=count,id=count`. |
| H3 | `timelimit` is in minutes. |
| H4 | `mem_req` is in MB (Slurm MB = MiB). Bit 63 set means per-CPU; then per-job memory = (`mem_req` − 2^63) × `cpus_req`. |
| H5 | `state` is the numeric slurmdbd enum, read from the low byte. |
| H6 | `gres_used` format: unknown. |
| H7 | Timestamps are ordered `submit ≤ eligible ≤ start ≤ end`. |
| H8 | `id_job` is unique per row, with array semantics to be checked. |
| H9 | `nodes_alloc` is consistent with `nodelist`. |

## 3. Existing code inventory (no dual implementations)

| Module | What it does | Fit for SuperCloud |
|---|---|---|
| `runtime/slurm_ingest.py` | Translates **live slurmrestd snapshots** into `WorkloadSignal` | **Does not fit.** Expects string TRES `gres/gpu:h100=N`; only H100 is mapped and the GPU count must be divisible by 8. Every SuperCloud GPU job (V100/tesla, numeric IDs) would raise `unmapped_hardware`. It is a live-event translator, not a batch replay loader. |
| `runtime/kube_trace_replay.py` | Offline replay of an **Alibaba-style node CSV + pod CSV** through `KubeSchedulerEngine`. Compares simulated waits against the trace's `scheduled_time`. | **Fits as the K8s target.** Column aliases are already tolerant. |
| `runtime/periodic_trace_import.py` | Aggregate per-interval site counts, including `ray_node_count` | Aggregate only; not a job-level target. |
| Ray execution path | Phase 4 of `docs/ray-integration-plan-revised.md`; not implemented | **No target exists yet.** |

## 4. Decisions

**D1 — The K8s path converts to the existing replay CSV contract.**

- The converter emits `pods.csv` and `nodes.csv` that `load_kube_trace()` accepts unchanged.
- No new replay engine is added.
- SuperCloud `time_start` maps to `scheduled_time`, which the replay uses for comparison only. This gives a direct check of simulated queue wait against real Slurm queue wait.

**D2 — Do not extend `slurm_ingest.py` for batch replay.**

- It stays the live-snapshot translator.
- If a Slurm-native replay is wanted, it gets its own loader that feeds `core/slurm_scheduler`, decided at Gate 2 (open item CAV-SC-4).
- No V100 profile is added to `_TRES_PROFILE_BY_MODEL` in this DR. A hardware profile is a model constant and needs its own review.

**D3 — Ray is deferred.**

- No converter is built until the Phase 4 Ray execution scheduler defines a job-level input contract.
- The SuperCloud labelled DNN jobs are the intended source when it does.

**D4 — Data handling.**

- Raw CSVs and row-level extracts are never committed (licence is NC-ND).
- Only aggregate profile reports are committed, with at most 5 sample values per column.
- Commercial or external use of derived results needs review first (CAV-SC-5).

## 5. Proposed column mapping, SuperCloud → `pods.csv` (D1)

The mapping applies after Gate 1 confirms H1–H5.

| `pods.csv` | Source | Rule |
|---|---|---|
| `pod_id` | `id_job` | Add `-<id_array_task>` when the job is an array task. |
| `workload_id` | `id_array_job` or `id_job` | Array parent if non-zero, else the job ID. |
| `cpu_milli` | `cpus_req` | × 1000 |
| `memory_mib` | `mem_req`, `cpus_req` | Decode per H4. |
| `num_gpu` | `tres_req` | Sum of counts for IDs 1001 and 1002. |
| `gpu_milli` | — | `num_gpu` × 1000; SuperCloud has no fractional GPUs. |
| `gpu_spec` | `tres_req` | `tesla` and/or `volta`, joined with `\|`. |
| `qos` | `priority` | Numeric. `_qos_priority()` already parses ints. Scale suitability is CAV-SC-3. |
| `creation_time` | `time_submit` | Epoch seconds (H1). |
| `scheduled_time` | `time_start` | Comparison only. |
| `deletion_time` | `time_end` | |
| `node_id` | `nodelist` | Single-node jobs only. |

### Exclusions

These rows are **quarantined with a reason, never silently dropped**:

- `time_start = 0` (never ran).
- `time_end < time_start`.
- Malformed `tres_req`.
- Multi-node jobs while Phase A has no gang admission (CAV-SC-2).

### `nodes.csv`

- Node identities come from the distinct `nodelist` values.
- Per-node capacity is **derived from the data**, not hard-coded:
  - CPU: max `cpus_req`/`nodes_alloc` observed on that node.
  - GPU: max GPU count per single-node job.
  - Model: from the TRES ID.
- A published TX-GAIA spec may be used only to cross-check, tagged `PROPOSED_HERE` with its source.

## 6. Gates

| Gate | Work | Exit criterion |
|---|---|---|
| **1** | Get `slurm-log.csv`, `labelled-slurm-log.csv` and `tres-mapping.txt` into the workspace. Run the profiler. Commit `reports/supercloud-profile/profile.md` (aggregates only). | Every H1–H9 is PASS or has a recorded resolution. **STOP and report.** |
| **2** | Lock the mapping in §5 against the observed encodings. Resolve CAV-SC-2…4. | Lloyd approves the revised mapping. **STOP.** |
| **3** | Implement `tools/supercloud/convert_to_kube_trace.py` with fixture tests TC-SC-01…. Run `kube_trace_replay` on the output. | Parser report shows accepted and quarantined counts by reason. Replay completes. **STOP and report.** |

### Proposed acceptance tests (Gate 3)

These are numbered TC-SC-xx to avoid colliding with the main TC sequence; renumber on merge.

- **TC-SC-01:** Converter output loads through `load_kube_trace()` with zero `missing required columns` errors.
- **TC-SC-02:** Pod count equals source rows minus quarantined rows, and quarantine reasons are enumerated.
- **TC-SC-03:** GPU pod count reconciles to the profiler's H2 GPU-row count, less GPU rows quarantined.
- **TC-SC-04:** A fixture covering a per-CPU memory row (H4), an array task, a never-started job and a multi-node job produces the expected pod and quarantine rows.
- **TC-SC-05:** No raw SuperCloud row data appears in any committed file.

## 7. Open items

| ID | Item |
|---|---|
| CAV-SC-1 | Workspace egress blocks `mit-supercloud-dataset.s3.us-west-2.amazonaws.com`. Either allow the domain (claude.ai → Settings → Capabilities) or attach the three files manually. |
| CAV-SC-2 | Multi-node and gang jobs. Options: quarantine; split into per-node pods with a shared `workload_id`; or wait for gang admission. The share of multi-node jobs (from H9) decides it. |
| CAV-SC-3 | Is `priority` (multifactor) a usable proxy for the replay's QoS priority, or should `partition` map to a QoS class? |
| CAV-SC-4 | Is a Slurm-native replay (through `core/slurm_scheduler`) needed in addition to the K8s replay? |
| CAV-SC-5 | Licence review (CC BY-NC-ND) before any external or commercial use of derived results. |
| CAV-SC-6 | Power linkage. Per-job GPU `power_draw_W` exists in `gpu/` time series and could calibrate hardware power profiles. This is a separate DR; it touches patent-sensitive profile methodology. |
