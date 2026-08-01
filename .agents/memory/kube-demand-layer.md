---
name: kube-demand-layer
description: Architecture of the Kubernetes gang-admission demand simulator — steps 1-2 only; steps 3-8 are scheduler-agnostic core pipeline.
---

## What was built

`core/kube_demand.py` — `KubeDemandAgent`: a discrete gang-admission simulator
replacing the earlier OU continuous process.

## The design boundary

**Steps 1–2 only** live in `kube_demand.py`:
1. OBSERVE: Poisson-arrival jobs enter a 10-second reorder buffer (simulates
   informer watching Kueue/Volcano PodGroup objects + NTP jitter).
2. MAP TO CONTRACT: Each drained event maps to a `WorkloadSignal(node_count,
   hardware_profile_id, workload_class, site_id, event_id)`.

**Steps 3–8 are already in the scheduler-agnostic core pipeline** — unchanged:
- `GPUModule.advance()` → P_compute = Σ[nodes × kW] × PUE / 1000
- `CoolingModule.advance()` → P_cooling = α(t) × P_compute(t − Δt_thermal)
- BESS/turbine dispatch → bridges the step, ramps at r_asset

Swapping Slurm for Kubernetes changes `kube_demand.py` and nothing else.

## Key design rules

**Import order (no circular):** `models.py` ← `kube_demand.py` ← `simulation_core.py`.
`KubeMetrics` is defined in `models.py` (not `kube_demand.py`) so `TickResult` can
carry it without a cycle.

**Opt-in:** `kube_config` in `ScenarioSpec` → `sim_state.kube_agent` set. All existing
scenarios and 417 tests are unaffected (`kube_agent=None` path is the no-op default).

**Step 0 in evaluate_tick:** kube agent runs BEFORE `gpu.advance()`. Uses
`state._kube_grid_state` from the PREVIOUS tick (correct — mirrors real-world EMS latency).

**dt_lead=0 always:** STARTING and SCALE signals use `dt_lead_seconds=0.0`. Kubernetes
gives no advance notice — BESS must bridge every ramp.

**Gang admission is the trigger**: discrete events (Poisson inter-arrivals, Gaussian job
sizes, exponential durations). NOT a continuous utilisation signal.

**Reorder buffer**: events drain only after `reorder_window_s` (default 10 s) has elapsed
since observation. Sorted by `event_timestamp` (NTP-jittered) for ordering guarantee.

**Dedup**: on `event_id` (`f"kube-job-{counter}"`) — idempotent replay.

**Capacity validation**: admissions that would exceed `max_nodes` are dropped.

**Power-cap**: hold new admissions when headroom < threshold (re-queue with +5 s delay).
Critical (headroom < 0) evicts the largest active job.

**min_nodes baseline**: `total_nodes = max(min_nodes, admitted_nodes)` — cluster never
fully drains; always emits at least min_nodes worth of load.

## KubeMetrics fields (core/models.py)

```python
utilization: float      # total_nodes / max_nodes
node_count: int         # max(min_nodes, admitted_nodes)
power_cap_active: bool  # headroom < headroom_threshold_mw
headroom_mw: float      # prev-tick turbine + bess headroom
active_jobs: int        # gang-admitted workloads currently running
admitted_nodes: int     # sum node_count across active jobs (pre-floor)
```

## Wire serialization (runtime/run_manager.py)

`_tick_result_to_dict` emits all 6 fields. Frontend `KubeMetrics` interface
has all 6 fields. Compute panel shows `active_jobs` and `admitted_nodes` rows.

## KubeConfig fields (api/schemas.py KubeConfigSpec)

New fields replacing OU params:
- `mean_interarrival_s` (Poisson arrival rate)
- `mean_job_nodes`, `job_node_std`, `min_job_nodes` (gang size dist)
- `mean_job_duration_s`, `min_job_duration_s` (exponential duration)
- `reorder_window_s`, `ntp_jitter_s` (reorder buffer)

Removed: `target_utilization`, `ou_theta`, `ou_sigma`, `ema_alpha`,
`scale_up_threshold`, `scale_down_threshold`, `scale_step_fraction`, `scale_cooldown_s`.

**Why:** scenario_factory uses `KubeConfig.__dataclass_fields__` intersection with spec
dict — old field names are ignored, new fields are picked up automatically.

## Demo scenario (demo-kube)

Built-in seed: 60 s mean inter-arrival, 200-node mean gang, 300 s mean duration,
10 s reorder window, 2 s NTP jitter. Turbine 25 MW, BESS 18 MW / 8 MWh, seed=42.
At 120 ticks (600 s): 14 admission/retirement events, 0–5 concurrent jobs,
admitted_nodes 0–981, p_compute 0.06–46.75 MW.
