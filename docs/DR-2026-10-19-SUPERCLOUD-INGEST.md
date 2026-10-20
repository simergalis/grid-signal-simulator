# DR-2026-10-19-SUPERCLOUD-INGEST — MIT SuperCloud Slurm log as replay input

**Status:** Gate 1 complete 2026-10-19 (§8). Gate 2 approved by Lloyd 2026-10-20. Gate 3 complete 2026-10-20 (§9); **stopped** on IMPL-SC-1 before any results are interpreted.
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
| Ray execution path | `core/ray_execution_scheduler.py` (Phase 4, 845 lines) plus Phases 5–7 modules in `core/ray_*.py` | **Exists.** Corrected 2026-10-20: the original entry relied on `docs/ray-integration-plan-revised.md`, which is stale. A job-level Ray target is available. |

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

- ~~No converter is built until the Phase 4 Ray execution scheduler defines a job-level input contract.~~ Corrected 2026-10-20: `core/ray_execution_scheduler.py` exists, so a target is available (§3).
- Ray stays deferred, now as a **sequencing** decision: K8s replay first (Gate 2, CAV-SC-4).
- The SuperCloud labelled DNN jobs are the intended source. Note from §9 that 31% of them are multi-node, so a Ray converter needs a placement-group mapping rather than quarantine.

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

## 8. Gate 1 results (2026-10-19)

### Run details

- **Input:** `slurm-log.csv` from `s3://…/datacenter-challenge/202201/`, 103,165,427 bytes, matching the S3 object size.
- **Supporting files:** `tres-mapping.txt` and `labelled_jobids.csv` from the same prefix.
- **Report:** `reports/supercloud-profile/profile.md`, aggregates only.
- **Command:** `tools/supercloud/profile_slurm_log.py`.

### Snapshot facts

| Fact | Value | Note |
|---|---|---|
| Rows | 395,914 | **Not 460,497.** The README's figure covers the full dataset; this snapshot is a subset. |
| GPU rows (TRES 1001/1002) | 98,176 | README says 98,177. |
| GPU mix | 98,170 volta (1002), 6 tesla (1001) | |
| Time span | 2021-01-01T21:15Z → 2021-10-01T15:12Z | About 9 months. |
| Partitions | `normal`, `test`, `gaia`, `xeon-p8`, `db` | |
| Job types | `OTHER`, `LLSUB:BATCH`, `LLSUB:INTERACTIVE`, `LLMAPREDUCE:MAP` | |

### Labelled jobs

- **`labelled-slurm-log.csv` does not exist in this snapshot.** The labelled file is `labelled_jobids.csv` (`id_job,model`, 3,430 rows).
- **All 3,430 join to `slurm-log.csv`**, and all of them are GPU jobs.
- States: 3,414 COMPLETED, 10 TIMEOUT, 6 CANCELLED.
- By family: U-Net 1,431, VGG 560, Inception 484, ResNet 463, BERT/DistilBERT 361, and GNNs 131 (SchNet 39, DimeNet 33, NNConv 32, PNA 27).

### Hypothesis outcomes

| ID | Result | Resolution |
|---|---|---|
| H0 | PASS | Header is exactly the 29 notebook columns. |
| H1 | PASS | `time_*` are epoch seconds. No `time_start = 0` rows: the snapshot holds terminal jobs only. |
| H2 | PASS | `tres_req`/`tres_alloc` = `id=count,…`, 0 malformed. `tres_alloc` also carries id 3 (energy) on 47,724 rows. |
| H3 | PASS | `timelimit` is minutes: 100% of COMPLETED runtimes fit as minutes, 79% as seconds. **Sentinels:** `4294967295` = INFINITE on 173,875 rows (44%); `525600` = 1 year. |
| H4 | **PASS, refined** | Bit 63 set (346,766 rows): `mem_req` − 2^63 = **MB per CPU**, × `cpus_req`. Flag clear: `mem_req` = **MB per node**, × `nodes_alloc`. Decoded total equals TRES mem (id 2) in 395,715/395,863 rows. The 148 residuals are all flag-clear multi-node rows where per-node × `nodes_alloc` reconciles. The converter rule must apply both cases. |
| H5 | PASS | Numeric slurmdbd enum. COMPLETED 309,037; CANCELLED 53,980; FAILED 21,349; TIMEOUT 7,089; OUT_OF_MEMORY 4,414; NODE_FAIL 44. One row has value `1024` (0x400, JOB_REQUEUE flag, base state 0); quarantine it. |
| H6 | N/A | `gres_used` is empty in every row. GPU identity comes from TRES only. |
| H7 | PASS | 0 timestamp-ordering violations. |
| H8 | PASS | `id_job` is unique, 0 duplicates. Array jobs are distinguished by `id_array_job` / `id_array_task`; `4294967294` = not an array task. |
| H9 | PASS | `nodelist` is a Python-list string, e.g. `['r9189566-n911952']`. Entry count equals `nodes_alloc` in 395,914/395,914 rows. |

### Converter-relevant shape

- **Multi-node rows:** 6,561 (1.7%) overall; 2,365 of the 98,176 GPU rows (2.4%). The largest job is 891 nodes.
- **GPUs per node (GPU rows):** 1 GPU/node 79,875; 2 GPUs/node 18,162. 44 rows evenly divide to 4/node and 95 rows don't divide evenly, e.g. 1 GPU across 2 nodes. Those 139 rows need a rule (CAV-SC-7).

### Mapping changes required at Gate 2 (amends §5)

1. **`memory_mib`:** use the two-case H4 rule. Slurm "MB" is MiB, so no unit conversion.
2. **Never-started exclusion:** dead in this snapshot, but keep it as a guard.
3. **Quarantine** the `state = 1024` row (requeue flag).
4. **`timelimit`:** not used by the K8s replay. If it's carried as metadata, map `4294967295` to null.
5. **`node_id`:** strip the list syntax from `nodelist`.
6. **Multi-node GPU jobs (2.4%):** small enough that quarantining them in the first replay is low-cost. This is the recommended answer to CAV-SC-2.

### New open item

| ID | Item |
|---|---|
| CAV-SC-7 | 139 GPU rows whose GPU count is not 1 or 2 per node (44 at 4/node, 95 fractional). Check whether `tres_req` GPU counts are per job or per node on these rows before deciding; quarantine pending that check. |


## 9. Gate 2 decisions and Gate 3 results (2026-10-20)

### Gate 2 decisions (approved by Lloyd)

| Item | Decision |
|---|---|
| Mapping | §5 as amended by §8 is approved. Fixtures must cover both memory encodings, INFINITE time limit, `state = 1024` and `nodelist` stripping. |
| CAV-SC-2 | Quarantine multi-node jobs for the first replay. |
| CAV-SC-3 | `priority` → replay priority; `partition` selects the node pool only. |
| CAV-SC-4 | Slurm-native replay deferred until K8s replay results show whether it's needed. |

### Pre-build check: priority vs partition (CAV-SC-3 closed)

Priorities fall into two bands, about 10,0xx–11,xxx and about 110,xxx–120,000.

- **The +100,000 band is not partition-driven.** `normal` has jobs in both bands.
- **It is an interactive-job boost.** All 7,101 `LLSUB:INTERACTIVE` jobs are in the high band.
- **Real waits differ accordingly:** median 1 s in the high band vs 122 s in the low band.

Using `priority` as-is therefore preserves the cluster's real ordering, including the interactive boost.

### Implementation choices

Each was made against the data, and each is tested.

**`creation_time` = `time_eligible`, not `time_submit`.**
A job held on a dependency or begin-time is not waiting for resources. Using `time_submit` would make the simulator look faster for the wrong reason.

**Node inventory is derived, not hard-coded** (`derive_nodes`).
- Capacity is the peak *concurrent* allocation per node, over **single-node jobs only**.
- An earlier even-split of multi-node jobs inflated peaks to 50–65 cores on 40- and 48-core classes. 1,471 of 6,561 multi-node jobs don't divide evenly, so it was rejected.
- Each node takes its majority partition as its class. Its capacity is lifted to the class mode where its own peak is lower.
- Nodes seen only in multi-node jobs (424) take the class capacity.
- The inventory is derived from the whole partition-scoped trace, not the replay window: hardware is not windowed. A 1-day window had produced 78 nodes instead of 231.

Derived classes (cores / MiB / GPUs):

| Class | Cores | MiB | GPUs |
|---|---|---|---|
| `normal` (GPU nodes) | 40 | 383,300 | 2 |
| `xeon-p8` | 48 | 192,000 | 0 |
| `db` | 32 | 120,000 | 0 |
| `test` | 28 | 105,000 | 2 |

The `test` partition also has one node with 4 GPUs. Overall: 1,135 nodes, 231 with GPUs, 464 GPUs.

This remains a **lower bound** on hardware. It is not a TX-GAIA spec.

**Tesla jobs (6 rows) are quarantined as `gpu_type_tesla_ambiguous`.**
The nodes they ran on also ran V100 jobs, so their GPU type can't be resolved.

**CAV-SC-7 is resolved.**
- All 44 four-GPU jobs ran on the single 4-GPU node in `test`. They are legitimate.
- The fixed 2-GPU limit was replaced by `gpu_count_exceeds_inventory`, checked after the inventory is derived. It fired on 0 rows.

### Full-trace conversion (all partitions)

| | Count |
|---|---|
| Source rows | 395,914 |
| Pods | 389,347 (95,805 GPU) |
| Quarantined | 6,567: `multi_node` 6,560, `gpu_type_tesla_ambiguous` 6, `state_flag_bits` 1 |
| Rows rejected when loaded by `load_kube_trace()` | 0 (TC-SC-01 holds on real data) |

### Cost of CAV-SC-2 for labelled jobs

**1,062 of the 3,430 labelled DNN jobs (31%) are multi-node.** Quarantine is cheap for GPU jobs overall (2.4%), but not for the labelled set. Any study that leans on the labelled jobs needs gang admission or a placement-group mapping first.

### Data observation

GPU jobs are nearly absent before 2021-W06; the first is in early February 2021. Before then, the `normal` partition shows CPU-only TRES. The cause (GPU TRES tracking start vs. GPU usage start) is not determinable from this file. **Use windows from February 2021 onward for GPU studies.**

### Tests

`tools/supercloud/test_convert_to_kube_trace.py` has 11 tests, all passing:

- TC-SC-01…05, plus encoding unit tests, inventory derivation and window semantics.
- Fixtures are synthetic only.
- The existing `tests/test_kube_trace_replay.py` passes unchanged (7/7). The engine was not modified.

### First replay: 2021-W35 (2021-08-30 → 2021-09-06), partitions `normal,gaia,test`

| | |
|---|---|
| Pods | 6,595 (6,359 scored in-window; 236 warm-start) |
| Nodes | 231 |
| Quarantined | 20 (multi-node) |
| Runtime | 10.1 s |
| Engine | Unmodified, via `tools/supercloud/run_replay.py` |
| Aggregate report | `reports/supercloud-replay/2021-W35/` |

### IMPL-SC-1 — `deletion_time` semantics bias Slurm replays (BLOCKING)

`replay_kube_trace` passes `completion_time = deletion_time`. `KubeSchedulerEngine` then ends each pod at that **absolute** time, whenever it actually started. This is correct for the Alibaba trace, where deletion is an external event. For Slurm jobs:

    simulated runtime − actual runtime = actual wait − simulated wait

Measured on W35 (GPU pods, both scheduled):

| Metric | Value |
|---|---|
| Actual GPU-hours | 52,507 |
| Inflated by early start | **+20,221 GPU-hours (38%)**, across 3,160 pods |
| Truncated by late start | −940 GPU-hours, across 478 pods |
| Expired (never placed before their real end time) | 780 pods (12%) |

**Effect:** occupancy, and therefore contention, is materially overstated. The simulated-vs-actual wait comparison is **not interpretable until this is resolved**. Per the stop-and-report gate, no wait-time conclusions are drawn here.

### Proposed fix (requires approval: it touches the replay engine)

- Add an opt-in `completion_mode` to `replay_kube_trace`:
  - `"deletion_time"`: current behaviour, the default. The Alibaba path is unchanged.
  - `"runtime"`: `completion_time = None` and `duration_s = deletion − scheduled`. The pod then runs for its real runtime from its simulated start.
- Expiry does not apply in `runtime` mode: Slurm never-started jobs are absent from this snapshot.
- Needs new tests for both modes. The existing 7 tests must pass unchanged.
- Converter output is unaffected. The runtime is already derivable from `scheduled_time` and `deletion_time`.

### New open item

| ID | Item |
|---|---|
| CAV-SC-8 | Real W35 waits have a long tail: p90 8.7 h, p99 37.7 h. That tail may reflect site policy absent from the trace, such as per-user limits or fair-share. **Unverified.** Assess only after IMPL-SC-1 is fixed, because the current simulated waits are not comparable. |

### Next gate (4)

Approve IMPL-SC-1 → implement `completion_mode` with tests → rerun W35 → **STOP** and report the wait comparison.

## 10. Scenario S10 — real GPU day, H100-equivalent shape (2026-10-20)

**Approved by Lloyd 2026-10-20:**

- A new scenario. S9 (`S9_islanded_ramp_protection`) is unchanged.
- The H100-equivalent route.
- Automatic day selection.
- Generator committed, scenario not committed.
- Sample values stripped from the public report.

### Method

`tools/supercloud/make_scenario.py`, with 5 tests in `test_make_scenario.py`.

- **Workload.** Every real GPU job (partitions `normal,gaia,test`) overlapping the chosen UTC day becomes one `starting`/`job_end` pair at its **real** start and end times. This is not the replay, so IMPL-SC-1 does not apply.
  - Multi-node gang jobs are kept as single events. This is a load timeline, not a scheduling replay.
  - Job IDs are sequential (`s10-job-NNNNN`); no dataset IDs are carried.
- **Scaling.** Each job's V100 count × (peak MW / 10.2 kW / peak concurrent GPUs) gives `hopper_8gpu_air` chassis.
  - `--peak-mw` defaults to **50 MW, `PROPOSED_HERE`**. This matches the 50 MW design-manual site and sets magnitude only.
  - The real timing is preserved. V100 power physics are not modelled.
- **Power side.** Copied from `demo-islanded-ramp`: 5 × 15 MW GT and an 18 MW / 14 MWh grid-forming BESS.
- **Synthetic load sources neutralised:** `kube_config`, `load_config`, `cluster_gen_config`, `workload_floor_fraction` (template 0.5), `gpu_load_profile`, solar (template 15 MW) and assertions.
- **Other settings:** `end_sim_time` = 86,400 s; `design_peak_load_mw` = scaled peak.

### Day selection: 2021-08-11 (UTC)

Days were scored by the maximum 15-minute rise in concurrent GPUs, from February 2021 onward.

The top three days (08-10, 08-11, 09-16) all follow a **maintenance drain**. 180 GPU jobs were cancelled together at 03:00 UTC on 08-10, and 179 at 04:00 on 09-16. Each drain is followed by a **whole-cluster scaling campaign**: completed gang jobs of 64 → 128 → 182 → 196 → 212 nodes (up to 424 GPUs = the entire GPU partition), each running 5–60 minutes.

**08-11 is a benchmark-campaign day, not typical production.**

| | |
|---|---|
| GPU jobs | 154 (4 at 424 GPUs, 2 at 392, 7 at 256) |
| Events | 239 |
| Jobs running at 00:00 | 1 |
| Jobs running past 24:00 | 69 |
| Scaling | 11.56 chassis per GPU; peak 50.0 MW after rounding |

The steepest *ordinary production* day is **2021-09-17** (15-minute rise of 125 GPUs, range 121–376). It is available with `--date 2021-09-17`.

### Validation

**Schema.** `ScenarioSpec` accepts S10.

**Environment limit.** The GitHub snapshot (last push 2026-09-16) is missing three modules present on Replit: `runtime/fuel_cell_defaults.py`, `runtime/reference_forecast.py` and `core/infrastructure_admission.py`. The snapshot cannot import `api.schemas` without them.

Validation therefore ran in a scratch copy: the snapshot plus the first two modules, read from Replit. That copy is never committed. Replit's 133 KB `schemas.py` exceeds the read limit, so schema drift against live code could not be checked. **The authoritative check is `POST /scenarios` on the live app.**

**Headless run (scratch copy).**

- S10 runs, and load follows the trace: 0 → 31 → 0 → 47.6 MW steps.
- The island collapses after 2,369 ticks (`island_collapse_no_grid_forming_source`).
- **The unmodified template `demo-islanded-ramp` collapses the same way** (1,333 ticks): turbine output plateaus well below committed capacity and the BESS carries the gap until it is empty.
- Also seen in both runs:
  - Frequency readings of 71–592 Hz on load drops.
  - Repeated `start 'turbine-3' silently dropped … state=OFFLINE`.

**Conclusion.** The collapse is **not attributable to S10**. It reproduces on the baseline template in this snapshot. Whether it also occurs on live Replit code is unknown (IMPL-SC-2). No simulator code was changed (diagnostic before fix).

### Open items

| ID | Item |
|---|---|
| IMPL-SC-2 | In the GitHub snapshot (plus two Replit modules), `demo-islanded-ramp` collapses headless: turbines don't follow load, the BESS drains, frequency readings are unphysical. **Check first:** run the template on live Replit; if it is clean there, the snapshot is stale and GitHub needs a sync. Then run S10 live. |
| CAV-SC-9 | The GitHub repo `grid-signal-simulator` is **public**. The earlier commit `d4b8895` contains a profile report with up to 5 anonymised sample values per column (job IDs, node names). The current report has none (profiler default changed), but **branch history still holds them**. Removing them requires rewriting the branch history (force-push). That is Lloyd's decision. |


### Integration into the live Replit app (2026-10-20)

Lloyd asked for the scenario to be integrated through the Replit connector, with ID and name **`S10_mit_supercloud_2021-08-11`**. It was regenerated with `make_scenario.py --name` and registered in the **dev workspace only**. Not published, not in GitHub.

**Transport.**
- Two attempts to have the Replit agent transcribe a gzip+base64 asset (7,116 characters, sent in hash-checked chunks) failed the SHA-256 gate: chunk 1 hashed `914e74…` vs `4cacee…`. The agent deleted the file and stopped as instructed.
- **LLM transcription of opaque blobs is unreliable.** Use a user upload for data assets.
- Lloyd then uploaded the plain JSON (SHA-256 `8126ee38…f7ad`).

**Verification.**

| Check | Result |
|---|---|
| Upload and byte-for-byte copy in `config/scenarios/S10_mit_supercloud_2021-08-11.json` | Both hash `8126ee38…f7ad` |
| Events 0, 100, 238 | Match local reference |
| `api/routes/scenarios.py` diff (read directly) | Exactly two added lines: the comment and the `_JSON_ENTRIES` entry |
| `GET /scenarios` | Lists S10: 239 events, `end_sim_time` 86,400 |
| `Failed to seed` warning | None |

**Seed warning.** S10 produces a turbine starting-count warning: `base_load_mw` is unset, so first-burst coverage was checked against the 0.24 MW burst alone. It is benign; it reflects the template's `initial_spinning_count = 1` and the near-idle start of the day.

**Pre-existing test failure, not caused by S10.** `tests/test_step8_scenarios.py::TestScenarioCRUD::test_list_includes_seeded_and_created` (line 402) asserts `"demo-alert" in names`, but live display names are now numbered (`"46 demo-alert"`). Each catalogue entry is seeded independently, so adding one cannot remove a name. Result: 73 pass, 1 fail. Logged as IMPL-SC-3; the test was not changed.

### IMPL-SC-2 resolved as a live defect (not snapshot staleness)

Headless runs on **live Replit code** (instant playback, no changes):

| | demo-islanded-ramp | S10 |
|---|---|---|
| Ticks | 1,276 (6,380 s) | 2,369 (11,845 s) |
| Collapse | `no_grid_forming_source` | `no_grid_forming_source` |
| Max compute MW | 66.05 | 47.61 |
| Min BESS SoC | 0.0 | 0.0 |
| Max turbine MW | 45.0 | 44.78 |
| Frequency range (Hz) | −122.9 to 60.0 | 58.87 to 592.2 |

- **S10's collapse tick is identical live and in the snapshot**, so the snapshot faithfully represents live behaviour for S10.
- The template differs slightly (1,276 vs 1,333 ticks), which reflects code drift, but the failure mode is the same.
- **The baseline demo scenario does not complete on live code.** In both runs, turbine output plateaus below committed capacity, the BESS drains to 0, and frequency reaches physically impossible values (negative, and nearly 10× nominal).
- This is a simulator defect, independent of S10. It needs a diagnostic-only pass before any fix. No simulator code was changed here.

| ID | Item |
|---|---|
| IMPL-SC-2 | **Live defect.** `demo-islanded-ramp` collapses on live code; turbines don't pick up load; frequency is unphysical. Next step: a diagnostic-only audit of turbine dispatch/commitment (`start … silently dropped … state=OFFLINE`) and the frequency integrator. |
| IMPL-SC-3 | Update the `test_step8` name assertions to the numbered display names. |

## 11. GS-DIAG-ISL-001 — islanded-collapse diagnostic, Phases A–C (2026-10-20)

**Method.**
- Diagnostic-only prompt (project doc `claude/GS-DIAG-ISL-001_Islanded-Collapse-Diagnostic-Prompt.md`), run by the Replit agent on live code at commit `dd2350c`. No changes; `git status` clean.
- Each phase was checked against source and against independent runs in the scratch snapshot copy.
- Live and snapshot agree on every conclusion below.

| ID | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | Cost-ranked dispatch serves the BESS before incremental turbine output, holding committed GTs at p_min | **CONFIRMED** | `_cost_ranked_dispatch_allocations` greedy by marginal cost. `bess_marginal_cost_mwh` = 38 and `turbine_variable_per_mwh` = 55, both `PROPOSED_HERE`. Live tick 900: 5 GTs at 5.25 MW with 9.75 MW headroom each while the BESS discharges. Plateau 2,175–6,380 s (842 ticks). |
| H2 | Setpoints not applied or overwritten | INCONCLUSIVE, moot | Setpoint = output = 5.25 MW at the plateau. The plateau is fully explained by the dispatch request (H1). |
| H3 | Commitment re-targets a unit inside min-down | **Plausible, S10 only** | Not present in the template (no decommit). S10 snapshot: `turbine-3` start dropped 234 × between 5,345 and 10,050 s; `t_min_down_s` = 900; last stop 9,155 s. Needs a Phase D trace. |
| H4 | Frequency integrator diverges | **Split.** Missing bounds: CONFIRMED. Numerical instability: NOT SUPPORTED | Null protection resolves to no UF/OF/UFLS/81U trip and no generic frequency saturation, so frequency reaches −127 Hz (template) and −751 to 2,842 Hz (S10 with reserve). The Euler step is damped (multiplier 0.99984); the excursions are forced by a sustained deficit (2 GTs on bus, BESS at its 17 MW cap during commitment lag). With S9's protection copied in memory, the template trips `island_collapse_uf` at tick 133 (665 s). |
| **H5** | No energy reserve for the only grid-forming BESS | **CONFIRMED — root cause of `no_grid_forming_source`** | `soc_floor_mwh` = max(diesel floor, depth reserve) = max(0, 0): no diesel, and `bess_normal_dispatch_depth_fraction` defaults to 0.0 (`scenario_factory`). With 0.03 in memory: the template runs the full 10,800 s, no collapse, min SoC 0.60 (live) / 0.59 (snapshot); S10 runs the full 86,400 s, min SoC 0.32, GT up to 61.8 MW. |

### Repeatability (IMPL-ISL-1)

Unchanged runs of `demo-islanded-ramp` diverge: 751 and 1,280 ticks live; 770 and 763 snapshot. Sources:

1. **Main source.** `kube_config.rng_seed: null` in the template. `scenario_factory` uses `.get("rng_seed", 42)`, which returns the stored `None` instead of the default, so `random.Random(None)` / `SeedSequence(None)` seed from OS entropy (`core/kube_demand.py:335–351`).
2. The default fabric engine is seeded with `hash(run_id)`. Python salts string hashes per process, so this is not reproducible across processes.
3. `wall_stamp_utc` = `time.time()`.
4. Advisory-agent cadence uses wall time (`advisory/agents/base.py`).

**Pinned runs are identical** on all physical fields: seed 42 gives 1,263/1,263 ticks (snapshot); seed 1729 plus a pinned clock gives 771/771 (live, excluding `advisory_telemetry`).

**S10 is deterministic** (no `kube_config`): 2,369/2,369 ticks.

### Open items

| ID | Item |
|---|---|
| IMPL-ISL-1 | Run-to-run non-determinism from null kube seed, `hash(run_id)` fabric seed, wall clock and advisory cadence. A diagnostic and A/B-validity risk (cf. GS-TP-AB-001). |
| IMPL-ISL-2 | Islanded sites with no diesel and `bess_normal_dispatch_depth_fraction` unset have a zero energy floor on their only grid-forming source (H5). |
| IMPL-ISL-3 | No physical frequency bounds when protection thresholds are null; impossible values reach `TickResult` and the UI. |
| IMPL-ISL-4 | With S9-class protection, the template under-frequency trips at 665 s: a sustained deficit during commitment lag while the BESS is at its power cap. This is an adequacy finding about the template site, not a model defect. |
| IMPL-ISL-5 | H3 trace on S10 (`turbine-3` repeated dropped starts). |

**Status.** No fixes made. The fix direction is for the Phase D report and a separate DR (DR-2026-10-2x-ISLAND-COLLAPSE).

### Phase D (2026-10-20) — S10, H3, final verdicts

The live results (commit `dd2350c`, git clean) match the independent snapshot runs value for value:

| S10 run | Ticks | Outcome | Min SoC | GT MW | Frequency (Hz) |
|---|---|---|---|---|---|
| Unchanged (×2, physically identical) | 2,369 | `no_grid_forming_source` | 0.0 | 5.25–44.78 | 58.87–592.24 |
| Depth fraction 0.03 | 17,280 (full 24 h) | no collapse | 0.320 | 5.25–61.80 | **−750.57–2,841.81** |
| 0.03 + S9 protection | 1 | `island_collapse_of` at 62.0 Hz | 1.0 | 5.25 | 62.0 |

**H3 — CONFIRMED (contributing).**
- All 234 dropped starts are `turbine-3`, and all are min-down rejections (elapsed time < 900 s).
- The candidate list `_offline_turbines_by_thermal_priority` (`core/simulation_core.py`) filters on state only. `UnitAvailability` carries no min-down eligibility, and `core/commitment.py` takes `offline[0]` (verified in source).
- In 50 of those ticks `turbine-4` was eligible but was not chosen. That caused two avoidable 125 s start delays, with the BESS at its 17 MW cap throughout.
- The contribution to the collapse has not been isolated (no counterfactual run).

**H5 — CONFIRMED (primary) for S10 too.** `soc_floor_mwh` = 0.0 MWh; same mechanism as the template.

**Correction to §11.** `bess_normal_dispatch_depth_fraction = 0.03` is a **3% normal-dispatch depth** (it retains 14 × (1 − 0.03) = 13.58 MWh, about 97% SoC), not a 3% floor. The experiment prevents collapse mainly by removing the BESS from routine economic dispatch. The emergency-release path can still discharge below that level (S10 min SoC 0.32). It demonstrates the mechanism; it is not an operating policy.

**IMPL-ISL-6 (new) — S10 initial state is infeasible under protection.**
- At tick 1, demand is 0.007 MW. The initial spinning GT is held at 5.25 MW must-run, and the BESS at 100% SoC cannot absorb the surplus (full-charge guard).
- The result is +5.24 MW of surplus forcing: 71.1 Hz unprotected, or an OF trip at tick 1 with S9 thresholds.
- S10's high-frequency excursions between gang jobs come from the same mechanism.
- This is a scenario/initialisation adequacy issue inherited from the template, not grounds to weaken any guard.

### Final register

| ID | Defect | Fix direction (Phase D; any new constant `PROPOSED_HERE`) |
|---|---|---|
| IMPL-ISL-1 | Non-determinism | Persist explicit seeds; no process-dependent seed derivation; separate physical replay identity from wall-clock/advisory metadata. |
| IMPL-ISL-2 | Zero grid-forming energy floor (H5, **primary**) | A justified grid-forming reserve policy applied ahead of economic dispatch, with explicit emergency-release semantics. |
| IMPL-ISL-3 | Unbounded frequency with null protection (H4) | Make unprotected islanded operation explicit, and stop invalid frequency output being presented as credible operation. |
| IMPL-ISL-4 | Template protected trip at 665 s | A validated demand/startup/reserve/site-adequacy review of the template. |
| IMPL-ISL-5 | Ineligible restart target (H3) | Apply the asset's start guards when forming and selecting candidates; choose another eligible unit. |
| IMPL-ISL-6 | S10 protected initial-state infeasibility | Reconcile initial must-run generation, initial demand and absorption headroom under validated protection criteria. |

**H1** (cost order BESS 38 < GT 55, both `PROPOSED_HERE`) is contributing. **H2** is moot.

**Next:** a fix DR (DR-2026-10-2x-ISLAND-COLLAPSE) for Lloyd's sign-off. No implementation until then.
