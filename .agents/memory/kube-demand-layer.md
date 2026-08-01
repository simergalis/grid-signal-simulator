---
name: kube-demand-layer
description: Architecture of the Kubernetes demand agent — stochastic GPU cluster load, OU process, grid headroom power-cap, and integration points.
---

## What was built

`core/kube_demand.py` — `KubeDemandAgent` with Ornstein-Uhlenbeck process + EMA smoother.

## Key design rules

**Import order (no circular):** `models.py` ← `kube_demand.py` ← `simulation_core.py`. `KubeMetrics` is defined in `models.py` (not `kube_demand.py`) so `TickResult` can carry it without a cycle.

**Opt-in:** `kube_config` in `ScenarioSpec` → `sim_state.kube_agent` is set. All existing scenarios and all 417 tests are unaffected (kube_agent=None path is the default).

**Step 0 in evaluate_tick:** kube agent runs BEFORE `gpu.advance()` so demand changes affect the current tick's power calculation. Uses `state._kube_grid_state` from the PREVIOUS tick (correct — mirrors real-world EMS latency).

**dt_lead=0 always:** all STARTING and SCALE signals from the kube agent use `dt_lead_seconds=0.0`. Kubernetes gives no advance notice to the grid — BESS must bridge the ramp.

**SCALE events:** first tick emits `WorkloadEventType.STARTING`, subsequent ticks emit `SCALE` (which snaps `_ramp_progress=1.0` on GPUModule — no cold-start ramp for scale events).

**Stochastic model:** OU process `dX = θ(μ-X)dt + σ√dt·N(0,1)` with `θ=0.04`, `σ=0.08`, `μ=target_utilization`. EMA filter `α=0.18`. Hysteresis bands 80%/62%, cooldown 30s, step 5% of max_nodes.

**Power cap:** when `turbine_headroom + bess_headroom < headroom_threshold_mw`, scheduler holds node count (soft) or forces 10% step-down (critical when headroom < 0).

## Wire format addition

`_tick_result_to_dict` serializes `kube_metrics: {utilization, node_count, power_cap_active, headroom_mw}` or `null`. `TickPayload` TypeScript interface has `kube_metrics: KubeMetrics | null`.

## Frontend compute panel

`compute.ts` shows kube utilization as hero value, K8s rows in stat table, power-cap state (red). State label: KUBE / HIGH / CAP depending on utilization and cap state.

## Demo scenario

`demo-kube` in built-in `_SEEDED`: no scripted events, `dt_lead_seconds=0.0`, 600s run, `rng_seed=42`. `max_nodes=1900` (≈20 MW peak), turbine 25 MW, BESS 18 MW/8 MWh.

**Why:** `rng_seed=None` in `KubeConfigSpec` gives time-seeded variety; `rng_seed=42` is the demo default for deterministic replay.
