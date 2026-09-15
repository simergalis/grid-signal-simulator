# Revised Ray Integration Plan for GridSignal

## Review result

The Rev 2 integration model confirms the central direction of the current
plan: Ray is a nested execution scheduler, not a third infrastructure
scheduler alongside Slurm and Kubernetes.

The plan is revised in four important ways:

1. Kubernetes has an explicit batch admission layer.
2. Ray autoscaling applies to KubeRay, not generally to Ray-on-Slurm.
3. Ray resource requests are logical scheduling metadata, not physical CPU or
   memory enforcement.
4. Power enforcement is a separate layer from capacity admission.

## Current Phase 1 status

The completed Phase 1 implementation covers:

- nested infrastructure allocation → Ray cluster → Ray workload identity;
- Kubernetes/Slurm backend identity;
- logical resource vectors;
- cluster capacity bounds;
- workload capacity validation;
- duplicate allocation detection;
- compatibility with legacy `scheduler_type="RAY"` signals.

This remains valid.

Rev 2 adds three contract concepts that must be represented before runtime
implementation begins:

- Kubernetes admission provider;
- autoscaling capability and upper-bound policy;
- separate power-enforcement policy and observed power state.

Therefore, Phase 1 is complete for its original scope, but a small Phase 1
contract refinement is required before Phase 2.

No implementation phase should treat the existing Phase 1 contracts as Ray
lifecycle, autoscaling, task scheduling, or power-enforcement support.

---

## Phase 0 — Boundary and terminology lock

Preserve these rules throughout the implementation:

```text
GridSignal
  ├── capacity policy and observability
  ├── infrastructure admission budgets
  └── power enforcement policy

Slurm or Kubernetes admission
  └── infrastructure allocation

Ray cluster
  └── Ray tasks, actors, placement groups
```

Ray is never treated as a third infrastructure scheduler.

The simulator remains deterministic and must not:

- launch Ray;
- execute Slurm commands;
- call Kubernetes;
- access NVML, DCGM, or RAPL directly;
- mutate real cluster state.

External systems may be represented through adapters and telemetry payloads,
but controls remain simulated metadata unless a separate integration boundary
is explicitly added later.

---

## Phase 1 — Contract foundation

### Completed

The existing Phase 1 implementation provides:

- `InfrastructureAllocation`;
- `RayClusterSpec`;
- `RayWorkloadSpec`;
- `RayPlacementGroupSpec`;
- logical resource vectors;
- nested IDs on `WorkloadSignal`;
- resource ownership and overcommit validation;
- legacy Ray signal compatibility.

### Phase 1 refinement required before Phase 2

Add explicit contract fields for the Rev 2 distinctions.

### Kubernetes admission provider

A Ray-on-Kubernetes cluster should declare which admission layer owns
infrastructure admission:

```text
kueue
volcano
yunicorn
none / legacy
```

The ordinary Kubernetes scheduler must not be described as a batch queue.
Kubernetes leaves unschedulable Pods pending; queueing, quotas, gang
admission, and priority belong to Kueue, Volcano, or YuniKorn.

### Admission identity

Contracts should distinguish:

```text
admission_domain_id
admission_queue_id
capacity_budget_id
infrastructure_allocation_id
```

This allows GridSignal budgets to be applied at the correct layer.

### Autoscaling capability

The cluster contract should distinguish:

```text
kubernetes_kuberay:
    elastic = true
    min_workers
    max_workers

slurm:
    elastic = false by default
    fixed_allocation = true
```

A Slurm-backed Ray cluster normally has a fixed upper bound determined by its
Slurm allocation. It should not automatically enter the KubeRay autoscaling
path.

### Power enforcement policy

Add a separate declaration for simulated power controls:

```text
gpu_power_cap
cpu_power_limit
node_power_state
capacity_only
```

This is not the same as workload admission. A cluster may be admitted while
its GPUs are power-capped or its CPUs are throttled.

### Logical versus measured resources

The contract should make this distinction explicit:

```text
logical_requested_resources
measured_cpu_usage
measured_memory_usage
assigned_gpu_devices
measured_gpu_utilization
measured_gpu_power
```

Ray's CPU and memory values are placement hints, not hard runtime enforcement.
GPU assignment is more concrete, but actual GPU power still requires measured
or simulated telemetry.

---

## Phase 2 — Infrastructure admission layer

This phase precedes Ray cluster lifecycle work.

### Kubernetes path

Add an explicit admission abstraction:

```text
KubernetesAdmissionEngine
- provider: KUEUE | VOLCANO | YUNIKORN
- queue
- quota
- priority
- gang admission
- preemption
- admission delay
- allocation result
```

The existing `KubeSchedulerEngine` can remain useful for Pod placement, but it
must not be treated as the complete batch admission layer.

The Kubernetes flow becomes:

```text
RayCluster/RayJob request
  → Kueue/Volcano/YuniKorn admission queue
  → admission decision
  → Kubernetes Pod scheduling
  → Ray head/worker startup
```

GridSignal's capacity budget affects the admission decision, not raw Ray task
placement.

### Slurm path

Use the existing Slurm scheduler as the infrastructure admission layer:

```text
Slurm pending queue
  → partition/QOS/reservation decision
  → fixed node allocation
  → Ray process startup
```

GridSignal controls should be represented through:

- job holds;
- QOS;
- reservations;
- GRES limits;
- partition limits.

### Slurm-on-Kubernetes

The Rev 2 model identifies Slinky as a possible additional topology:

```text
Kubernetes
  └── Slurm operator
        └── Slurm allocation
              └── Ray cluster
```

This is not part of the first implementation. Treat it as a later topology
extension after direct Kubernetes and direct Slurm paths are stable.

---

## Phase 3 — Ray cluster startup and readiness

Implement a `RayClusterEngine` after infrastructure admission exists.

Responsibilities:

1. Submit an infrastructure admission request.
2. Wait for admission.
3. Wait for head startup.
4. Wait for worker Pod scheduling or Slurm process startup.
5. Wait for worker registration.
6. Expose ready logical resources.
7. Record startup delay separately from queue delay.

Lifecycle:

```text
REQUESTED
  → ADMISSION_QUEUED
  → ADMITTED
  → HEAD_STARTING
  → HEAD_READY
  → WORKERS_STARTING
  → READY
  → DRAINING
  → TERMINATED
```

Timing metrics remain separate:

```text
infrastructure_admission_delay
cluster_startup_delay
ray_workload_queue_delay
```

For Slurm, the allocation is normally fixed. For KubeRay, worker groups may
be added later through autoscaling.

---

## Phase 4 — Ray execution scheduler

Implement tasks, actors, placement groups, and Ray workload lifecycle only
after a Ray cluster has ready workers.

### Ray owns

- task placement;
- actor placement;
- placement-group admission;
- dependency readiness;
- retries;
- spillback;
- logical resource accounting;
- workload phase transitions.

### Ray does not own

- physical node allocation;
- Kubernetes admission;
- Slurm queue placement;
- hard CPU or memory enforcement;
- site power enforcement.

### Required workload behavior

Support:

- tasks;
- long-lived actors;
- distributed training workers;
- inference workers;
- data-processing tasks;
- hyperparameter trials;
- Ray Jobs;
- Serve-style replicas;
- Train-style worker groups.

### Placement groups

Model:

- bundles;
- pack/spread strategies;
- strict placement;
- locality constraints;
- gang admission;
- placement wait time.

### Resource semantics

Use logical resources for placement:

```text
Ray request fits within ready logical capacity
```

Separately track actual usage:

```text
requested GPU count ≠ active GPU count
requested CPU count ≠ measured CPU usage
requested memory ≠ measured memory usage
```

---

## Phase 5 — KubeRay autoscaling feedback loop

Autoscaling applies only to the Kubernetes/KubeRay path.

```text
Ray pending work
  → Ray autoscaler request
  → KubeRay worker replica request
  → Kubernetes admission queue
  → Pod placement
  → worker registration
  → increased Ray capacity
```

Required controls:

- minimum worker replicas;
- maximum worker replicas;
- worker-group-specific limits;
- admission quota;
- scale-up delay;
- scale-down idle delay;
- failed-worker replacement;
- power-budget rejection or throttling.

The autoscaler request returns to the Kubernetes admission layer. It does not
bypass Kueue, Volcano, YuniKorn, or GridSignal capacity policy.

### Slurm behavior

Ray-on-Slurm initially remains fixed:

```text
Slurm allocation establishes the maximum cluster footprint.
Ray workloads use capacity inside that allocation.
```

Dynamic Slurm resizing, if ever added, must be a separate explicit feature and
must not be shared automatically with KubeRay autoscaling.

---

## Phase 6 — Separate power-enforcement layer

Capacity controls answer:

```text
How much infrastructure or work may be admitted?
```

Power controls answer:

```text
How many watts may the hardware draw?
```

Implement a separate simulated power-enforcement layer with inputs such as:

- measured GPU utilization;
- estimated GPU power;
- CPU utilization;
- memory activity;
- node state;
- workload phase;
- current site power budget.

Possible simulated controls:

```text
GPU power cap
CPU package power limit
Node suspend/resume state
GPU throttling state
Power-cap event
```

The engine should produce deterministic control metadata such as:

```text
power_cap_requested
power_cap_applied
gpu_throttled
cpu_limited
node_power_state
power_limit_reason
```

It must not call NVML, DCGM, or RAPL directly in the simulator.

### Integration with GridSignal physics

The power layer feeds the existing physical demand path through simulated draw
values:

```text
Ray workload phase
  → measured/simulated utilization
  → power enforcement adjustment
  → GPU/CPU draw
  → site demand
  → GridSignal dispatch and reserve logic
```

Capacity admission and power enforcement remain independently observable.

---

## Phase 7 — External ingestion and observability

Add ingestion for the nested layers rather than a single flat Ray event stream.

Recommended payload groups:

```text
POST /api/ingest/ray/infrastructure
POST /api/ingest/ray/cluster
POST /api/ingest/ray/workload
POST /api/ingest/ray/power
```

### Admission telemetry

- Slurm pending time;
- Kueue/Volcano/YuniKorn pending time;
- admission decision;
- quota or budget reason.

### Startup telemetry

- head startup delay;
- worker startup delay;
- worker registration delay;
- ready versus desired workers.

### Ray execution telemetry

- pending tasks;
- pending actors;
- placement-group wait;
- retries;
- failures;
- spillback;
- dependencies;
- logical requested resources;
- assigned GPU devices.

### Autoscaling telemetry

- autoscaler request;
- KubeRay desired replicas;
- admitted replicas;
- pending replicas;
- scale-up and scale-down delay.

### Power telemetry

- estimated versus measured draw;
- GPU utilization;
- GPU power cap;
- CPU limit;
- node power state;
- throttling;
- workload phase.

---

## Phase 8 — Scenario coverage

### Scenario A — Ray on Slurm, fixed allocation

Test:

- Slurm queue delay;
- fixed node/GPU ceiling;
- Ray head and worker startup;
- pending Ray tasks;
- placement-group wait;
- task retries;
- no Slurm node double-counting;
- no autoscaling request beyond the allocation.

### Scenario B — Ray on Kubernetes with Kueue

Test:

- admission queue delay;
- gang admission;
- KubeRay worker startup;
- Ray workload queueing;
- autoscaling request returning to Kueue;
- max-replica enforcement;
- GridSignal budget rejection.

### Scenario C — Ray on Kubernetes with Volcano or YuniKorn

Verify that the admission-provider abstraction is not hardcoded to Kueue.

### Scenario D — Power enforcement

Test:

- capacity admitted while GPU power is capped;
- CPU power limiting while workload remains logically scheduled;
- node power-state transition;
- throttling changing actual draw without changing Ray logical capacity;
- GridSignal dispatch reacting to physical demand rather than logical
  resource requests.

### Scenario E — Mixed backends

Run:

- one KubeRay cluster;
- one Slurm-backed Ray cluster;
- independent admission paths;
- shared GridSignal site budget;
- separate power-enforcement state.

---

## Revised dependency order

```text
1. Phase 1 contract refinement
   - admission provider
   - fixed versus elastic cluster behavior
   - power policy
   - logical versus measured resources

2. Kubernetes and Slurm infrastructure admission
   - Kueue/Volcano/YuniKorn abstraction
   - existing Slurm queue integration

3. Ray cluster startup
   - head and worker readiness
   - startup-delay telemetry

4. Ray task/actor/placement scheduling
   - logical resource placement
   - retries, dependencies, spillback

5. KubeRay autoscaling
   - autoscaler-to-admission feedback loop
   - no automatic Slurm autoscaling

6. Separate power-enforcement simulation
   - GPU caps
   - CPU limits
   - node states
   - throttling telemetry

7. External ingestion and dashboard telemetry

8. Mixed-backend scenarios and regression coverage
```

## Updated implementation boundary

The revised plan distinguishes three independent mechanisms:

```text
Admission controls:
    decide whether infrastructure is allocated

Ray scheduling:
    decides how application work uses ready Ray resources

Power enforcement:
    limits physical draw after or while work is admitted
```

This separation is the primary revision introduced by the Rev 2 integration
model.