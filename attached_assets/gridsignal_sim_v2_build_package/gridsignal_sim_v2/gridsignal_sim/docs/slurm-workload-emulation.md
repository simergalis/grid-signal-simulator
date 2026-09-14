# Slurm workload emulation

GridSignal supports two separate Slurm paths:

1. an external-state ingestion adapter that accepts Slurm job snapshots and
   translates them into the simulator's `WorkloadSignal` stream; and
2. an opt-in deterministic internal scheduler configured with `slurm_config`.

Both paths model queued and running customer workloads and their facility power
impact without running `sbatch` jobs or executing customer application code.

## Ingestion endpoint

```http
POST /api/ingest/slurm?run_id=<run-id>
X-Admin-Key: <server-to-server admin key>
Content-Type: application/json
```

The `run_id` identifies the active simulation that should respond to the
workload. It may be omitted only when exactly one run is active. Start the
scenario before sending job snapshots; ingestion does not create a run.

The request accepts the required `slurmrestd` job fields:

```json
{
  "job_id": 481516,
  "job_state": ["RUNNING"],
  "node_count": 16,
  "tres_req_str": "cpu=1536,mem=184320G,gres/gpu=128,gres/gpu:h100=128",
  "tres_alloc_str": "cpu=1536,mem=184320G,gres/gpu=128,gres/gpu:h100=128",
  "account": "customer-a",
  "partition": "gpu"
}
```

Additional Slurm fields are accepted and ignored by the adapter so the payload
can be forwarded from `slurmrestd`.

## State mapping

| Slurm state | GridSignal event | Physical effect |
|---|---|---|
| `PENDING` | `queued` | Records requested TRES; no running compute load |
| `RUNNING` | `running` | Adds the allocated compute load on the next simulation tick |
| `COMPLETING` / `COMPLETED` | `job_end` | Releases the running job's compute load |
| `CANCELLED`, `FAILED`, `TIMEOUT`, `NODE_FAIL`, `PREEMPTED` | `cancelled` | Removes the job's compute load |

Pending jobs use `tres_req_str`. Running jobs use `tres_alloc_str`, because
allocated resources—not requested resources—determine the physical load.
Terminal snapshots may use either field so deallocation cleanup does not lose
the job's hardware identity.

## Validation and deduplication

The adapter currently maps H100 Slurm allocations to the
`h100-sxm5-8way-nvl4` GridSignal hardware profile. It validates that:

- the GPU model is supported;
- the GPU count is positive;
- H100 GPU allocations are divisible by eight;
- `node_count` matches the implied eight-GPU-per-node topology;
- a pending job has requested TRES;
- a running job has allocated TRES.

The generated event ID is state-specific:

```text
slurm-<job-id>-<event>
```

Repeated polling of the same job state therefore returns a duplicate instead
of adding load twice, while a normal transition such as
`PENDING -> RUNNING -> COMPLETING` creates separate lifecycle events. A
delayed event after a terminal event is rejected as stale.

Invalid state, hardware, resource, or topology data returns HTTP 422 with a
machine-readable error code. Missing authentication returns HTTP 403, and
inactive or ambiguous runs return HTTP 409 or 422 as appropriate.

## Timestamped replay

The pure translation function
`runtime.slurm_ingest.translate_slurm_job(...)` accepts an explicit simulation
timestamp. Offline replay tools can use it to submit ordered transitions and
measure queue intervals or reconstruct submit/start metadata. The live HTTP
endpoint timestamps accepted events at the target run's current simulation
time, because Slurm wall-clock timestamps are not the same clock as a
simulation run.

## Scope

The snapshot ingestion path is workload emulation and power-impact simulation.
It does not:

- make independent Slurm priority, backfill, fair-share, or preemption
  decisions;
- launch real `sbatch` jobs;
- execute application code on a Slurm cluster.

## Internal deterministic scheduler

Add a `slurm_config` block to a scenario to enable the internal scheduler:

```json
{
  "slurm_config": {
    "nodes": [
      {
        "node_id": "gpu-01",
        "partition": "gpu",
        "gpus": 8,
        "gpu_model": "h100",
        "cpus": 96,
        "memory_mb": 100000,
        "features": ["h100", "nvlink"]
      }
    ],
    "qos_weights": {"normal": 1.0, "urgent": 10.0},
    "backfill": true,
    "reservations": [
      {
        "name": "customer-window",
        "start_time": 0,
        "end_time": 900,
        "nodes": ["gpu-01"]
      }
    ],
    "jobs": [
      {
        "job_id": "training-01",
        "arrival_time": 0,
        "duration": 300,
        "node_count": 1,
        "gpus_per_node": 8,
        "gpu_model": "h100",
        "partition": "gpu",
        "priority": 100,
        "qos": "urgent",
        "hardware_profile_id": "enterprise_8gpu_air",
        "command": "python train.py"
      }
    ]
  }
}
```

The engine evaluates pending jobs at each simulation boundary using:

- priority, QoS weight, fair-share usage, age, and deterministic submission
  order;
- optional backfill of lower-priority jobs when currently idle nodes can serve
  them;
- `afterok`, `afterany`, `aftercorr`, and `after` dependencies;
- partitions, node features, GPU model, CPU, memory, and node count;
- named time-bounded reservations; and
- simulated node/GPU/CPU/memory allocation and release at completion;
- typed job arrays with maximum-concurrency limits;
- heterogeneous job components, which start atomically;
- finite licenses and burst-buffer capacity pools;
- node state and topology constraints, including drain/down nodes;
- account associations, TRES limits, QOS limits, and usage-weighted fair-share;
- configurable preemption with cancellation or requeue;
- checkpoint lifecycle signals at configured intervals; and
- explicit federation/cluster routing validation.

Queued jobs emit no running workload and therefore add no compute load. Running
jobs emit `RUNNING`; completion emits `JOB_END`. The resulting scheduler view is
included in each tick as `slurm_metrics`, including queue depth, allocations,
and per-job state.

Jobs may also declare a `phases` list. Each phase is deterministic and
simulation-only:

```json
{
  "kind": "checkpoint",
  "duration_s": 20,
  "gpu_utilization": 0.35,
  "gpu_memory_mb": 24576,
  "power_multiplier": 0.6,
  "checkpoint": true
}
```

The runner advances phases from simulation time, binds each allocated GPU to a
stable identifier such as `node-01:gpu-3`, and emits `PHASE_UPDATE` signals
without executing `command` or starting a host process. A phase may request a
deterministic failure. A job whose `time_limit_s` expires emits `JOB_TIMEOUT`;
phase failures emit `JOB_FAILED`; preemption emits `JOB_PREEMPTED` and may
requeue the job according to policy. `slurm_metrics.jobs` and
`slurm_metrics.job_telemetry` expose the current phase, per-GPU binding and
utilization, and accumulated modeled GPU energy in MWh.

Runtime submission is available to an authenticated operator for an active
internal-scheduler run:

```http
POST /api/ingest/slurm/submit?run_id=<run-id>
X-Admin-Key: <server-to-server admin key>
Content-Type: application/json
```

The `command` and `environment` fields are metadata only. They are not passed
to a shell, and no arbitrary host process is launched. The duration models
simulated application execution.

The internal configuration is a typed compatibility contract, not a claim of
binary compatibility with every Slurm release. The simulator now rejects
unknown fields in the modeled node, job, partition, QOS, account, license,
burst-buffer, federation, and cluster-policy blocks instead of silently
dropping them. Fields that affect host execution, such as `command`,
`environment`, and cgroup enforcement, remain simulation metadata or
deterministic resource accounting; they do not create host processes or Linux
cgroups.

The behavior is covered by `tests/test_slurm_ingest.py` and
`tests/test_slurm_scheduler.py`, including state mapping, H100 validation,
topology validation, priority/QoS ordering, dependencies, reservations,
constraints, resource release, authentication, idempotent poll retries,
stale-event rejection, and next-tick compute-load changes.