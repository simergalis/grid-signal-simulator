"""
core/kube_demand.py — Kubernetes gang-admission demand simulator (Steps 1–2).

Simulates the path from pod admission to WorkloadSignal:
  1. OBSERVE:  An in-cluster informer watches Kueue Workload / Volcano PodGroup
     objects.  Gang admission is the trigger — the allocation decision exists,
     but no power has been drawn yet.
  2. MAP TO CONTRACT: Each admission is mapped to a WorkloadSignal with
     node_count (from the admitted spec), hardware_profile_id (from node
     labels / resource requests), workload_class, site_id, and a deterministic
     event_id.  Timestamps hold ±ntp_jitter_s — skew eats Δt_lead directly.

Steps 3–8 (validate → translate to MW → band → net against supply → arbitrate
→ command) are already implemented in the scheduler-agnostic core pipeline:
  • SimulationState.apply_workload_signal  — applies node_count
  • GPUModule.advance                     — P_compute = Σ[nodes × kW] × PUE / 1000
  • CoolingModule.advance                 — P_cooling = α(t) × P_compute(t − Δt_thermal)
  • BESS / turbine dispatch               — bridges the step, ramps at r_asset

Swapping Slurm for Kubernetes changes this file and nothing else.

Design goals
------------
* Gang admission is the trigger: each job is a discrete event (node_count from
  the pod spec), not a continuous utilisation signal.
* 10-second reorder buffer: simulates NTP jitter and the ordering guarantee.
* Dedup on event_id: idempotent — replaying the same admission is safe.
* Capacity validation: admissions that would exceed max_nodes are dropped.
* Power-cap feedback: when grid headroom < headroom_threshold_mw, new
  admissions are held; critical headroom (< 0) evicts the largest running job.
* dt_lead = 0 throughout: Kubernetes gives no advance notice to the grid.
  BESS must bridge every ramp — this is the GridSignal value proposition.
* Fully synchronous: tick() has no I/O.  Safe inside evaluate_tick().
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .models import KubeMetrics, WorkloadClass, WorkloadEventType, WorkloadSignal
from .step_config import LoadProfileConfig, StepTimingConfig
from .step_scheduler import StepScheduler

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class KubeConfig:
    """Configuration for the Kubernetes gang-admission demand simulator.

    One instance per run; created by scenario_factory from KubeConfigSpec.
    """

    # Fleet sizing
    max_nodes: int = 1900
    min_nodes: int = 200           # idle baseline — cluster is never fully empty
    hardware_profile_id: str = "enterprise_8gpu_air"

    # Gang-admission arrival pattern (Poisson process)
    # mean_interarrival_s is the average simulated seconds between successive
    # Kueue/Volcano gang admissions.  60 s → ~1 new job per minute on average.
    mean_interarrival_s: float = 60.0

    # Job size distribution (Gaussian, clipped to [min_job_nodes, max_nodes/2])
    # Gaussian is a practical approximation; real GPU cluster job sizes are
    # closer to log-normal but Gaussian is easier to reason about for demos.
    mean_job_nodes: int = 200
    job_node_std: float = 80.0
    min_job_nodes: int = 50        # floor — no trivial admissions

    # Job duration distribution (exponential, clipped at floor)
    mean_job_duration_s: float = 300.0   # 5 min mean — typical short GPU job
    min_job_duration_s: float = 30.0     # floor — no sub-30 s jobs

    # Reorder buffer: drain events only after this window has elapsed.
    # The real system guarantees ordering within a 10 s window; the simulator
    # honours the same constraint.
    reorder_window_s: float = 10.0

    # NTP jitter applied to event timestamps (±seconds, uniform).
    # Timestamps must hold ±2 s NTP — skew here eats Δt_lead directly.
    ntp_jitter_s: float = 2.0

    # Grid headroom below which power-cap activates (MW)
    headroom_threshold_mw: float = 2.5

    # RNG seed for deterministic replay; None = time-seeded
    rng_seed: Optional[int] = 42

    # ── Stochastic step timing / load coupling ────────────────────────────────
    # step_config — when set, a StepScheduler is wired to the agent.
    #   None = step scheduler off (default; all existing kube tests unaffected).
    # load_config — when set, GPUModules receive within-step power profiling.
    #   None = no load profile (default; all existing tests unaffected).
    step_config: Optional[StepTimingConfig] = None
    load_config: Optional[LoadProfileConfig] = None


# ---------------------------------------------------------------------------
# Grid state snapshot
# ---------------------------------------------------------------------------

@dataclass
class KubeGridState:
    """Snapshot of grid-side metrics passed to the agent each tick.

    Values are from the *previous* tick — the scheduler reads the last known
    grid state, mirroring the real-world latency between Kubernetes and the EMS.
    """
    p_dispatch_required_mw: float
    bess_soc_fraction: float
    turbine_headroom_mw: float   # rated_mw_total − turbine_output_mw
    bess_headroom_mw: float      # available BESS discharge headroom


# ---------------------------------------------------------------------------
# Internal job representations
# ---------------------------------------------------------------------------

@dataclass
class _PendingAdmission:
    """An event sitting in the reorder buffer, not yet admitted."""
    event_id: str
    node_count: int
    hardware_profile_id: str
    # sim_time when the informer observed the Workload/PodGroup object
    observed_at: float
    # timestamp carried on the event (observed_at + NTP jitter); used for ordering
    event_timestamp: float
    duration_s: float


@dataclass
class _ActiveJob:
    """A gang-admitted workload currently running."""
    event_id: str
    node_count: int
    hardware_profile_id: str
    admitted_at: float
    ends_at: float


# ---------------------------------------------------------------------------
# KubeDemandAgent
# ---------------------------------------------------------------------------

class KubeDemandAgent:
    """Kubernetes gang-admission demand simulator — Steps 1–2 only.

    tick() is called once per sim tick from evaluate_tick() Step 0.
    It drives the reorder buffer, admits jobs, retires completed jobs,
    and emits WorkloadSignals whenever the total admitted node count changes.

    The downstream pipeline (GPUModule → CoolingModule → dispatch) handles
    Steps 3–8 without any knowledge of Kubernetes.

    Thread safety: not thread-safe; designed for single-threaded use inside
    the synchronous evaluate_tick() function.
    """

    def __init__(
        self,
        config: KubeConfig,
        site_id: str = "site-0",
        rng_step: Optional[np.random.Generator] = None,
        rng_load: Optional[np.random.Generator] = None,
    ) -> None:
        self.config = config
        self.site_id = site_id
        # Job-scheduling RNG: keep random.Random for backward compatibility so
        # existing kube tests that assert specific output values continue to pass.
        # The random.Random sequence is identical regardless of whether the step
        # scheduler is active, preserving all existing determinism guarantees.
        self._rng = random.Random(config.rng_seed)

        # ── Numpy generators for step scheduler and load noise ────────────────
        # Created from SeedSequence.spawn(2) so the two streams are independent
        # and adding a draw to rng_step never affects rng_load (D3 isolation).
        # Callers may inject generators explicitly (e.g. acceptance tests).
        _ss = np.random.SeedSequence(config.rng_seed)
        _children = _ss.spawn(2)
        self._rng_step: np.random.Generator = (
            rng_step if rng_step is not None
            else np.random.default_rng(_children[0])
        )
        # rng_load is public — simulation_core reads it to inject into GPUModules
        # so the load noise stream is housed on the agent but applied per-module.
        self.rng_load: np.random.Generator = (
            rng_load if rng_load is not None
            else np.random.default_rng(_children[1])
        )

        # ── StepScheduler ─────────────────────────────────────────────────────
        # Instantiated only when step_config is set; all existing tests that
        # construct KubeDemandAgent without step_config are unaffected.
        self._step_scheduler: Optional[StepScheduler] = (
            StepScheduler(config.step_config)
            if config.step_config is not None else None
        )

        # Expose current step state so simulation_core can stamp it on TickResult.
        self.current_step_phase: float = 0.0
        self.current_step_kind: str = "training"

        # Step 1 state — admission pipeline
        self._reorder_buffer: list[_PendingAdmission] = []
        self._active_jobs: list[_ActiveJob] = []
        self._seen_event_ids: set[str] = set()
        self._job_counter: int = 0
        # Next sim_time at which a new job arrives at the informer
        self._next_arrival_sim_time: float = 0.0

        # Signal emission state
        self._last_total_nodes: int = -1   # -1 forces emission on tick 0
        self._started: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick(
        self,
        sim_time: float,
        dt_seconds: float,
        grid_state: Optional[KubeGridState] = None,
    ) -> tuple[list[WorkloadSignal], KubeMetrics]:
        """Advance the admission simulator by one tick.

        Steps executed in order:
          1a. Generate Poisson arrivals observed by the informer up to sim_time.
          1b. Retire completed jobs.
          1c. Drain the reorder buffer (events whose window has elapsed),
              sorted by event_timestamp (ordering guarantee).
          2.  Map each drained event to a WorkloadSignal after validation:
              dedup → capacity check → power-cap hold.
          2c. Critical headroom eviction (headroom < 0 → evict largest job).
          Emit a STARTING or SCALE WorkloadSignal if node count changed.

        Returns:
            signals: list of WorkloadSignals for SimulationState.apply_workload_signal.
                     Empty when no admission changes node count this tick.
            metrics: KubeMetrics snapshot for this tick (wire + UI).
        """
        # ── Grid headroom from previous tick ─────────────────────────────
        headroom_mw = 999.0
        power_cap_active = False
        if grid_state is not None:
            headroom_mw = grid_state.turbine_headroom_mw + grid_state.bess_headroom_mw
            power_cap_active = headroom_mw < self.config.headroom_threshold_mw

        # ── Step 1a: OBSERVE — advance Poisson arrivals ───────────────────
        # Generate all jobs whose informer-observation time ≤ sim_time.
        arrivals_this_tick: int = 0
        while self._next_arrival_sim_time <= sim_time:
            self._job_counter += 1
            event_id = f"kube-job-{self._job_counter}"

            # Gang size: Gaussian, clipped to [min_job_nodes, max_nodes/2]
            node_count = int(round(max(
                float(self.config.min_job_nodes),
                min(
                    float(self.config.max_nodes // 2),
                    self._rng.gauss(
                        float(self.config.mean_job_nodes),
                        float(self.config.job_node_std),
                    ),
                ),
            )))

            # Duration: exponential, clipped at floor
            duration_s = max(
                self.config.min_job_duration_s,
                self._rng.expovariate(1.0 / self.config.mean_job_duration_s),
            )

            # NTP jitter on the event timestamp (±ntp_jitter_s)
            jitter = self._rng.uniform(-self.config.ntp_jitter_s, self.config.ntp_jitter_s)
            event_timestamp = self._next_arrival_sim_time + jitter

            self._reorder_buffer.append(_PendingAdmission(
                event_id=event_id,
                node_count=node_count,
                hardware_profile_id=self.config.hardware_profile_id,
                observed_at=self._next_arrival_sim_time,
                event_timestamp=event_timestamp,
                duration_s=duration_s,
            ))
            arrivals_this_tick += 1

            _log.debug(
                "kube: informer observed %s — %d nodes, duration=%.0f s, "
                "event_ts=%.2f (jitter=%.2fs)",
                event_id, node_count, duration_s, event_timestamp, jitter,
            )

            # Sample next Poisson inter-arrival time
            iat = self._rng.expovariate(1.0 / self.config.mean_interarrival_s)
            self._next_arrival_sim_time += iat

        # ── Step 1b: Retire completed jobs ────────────────────────────────
        before = len(self._active_jobs)
        self._active_jobs = [j for j in self._active_jobs if j.ends_at > sim_time]
        retired = before - len(self._active_jobs)
        if retired:
            _log.debug("kube: %d job(s) completed at sim_time=%.1f", retired, sim_time)

        # ── Step 1c: Drain reorder buffer ─────────────────────────────────
        # Ready = observed_at + reorder_window_s ≤ sim_time.
        # Sort ready events by event_timestamp to honour ordering guarantee.
        ready = sorted(
            (pa for pa in self._reorder_buffer
             if pa.observed_at + self.config.reorder_window_s <= sim_time),
            key=lambda pa: pa.event_timestamp,
        )
        self._reorder_buffer = [
            pa for pa in self._reorder_buffer
            if pa.observed_at + self.config.reorder_window_s > sim_time
        ]

        # ── Step 2: MAP TO CONTRACT — validate and admit ──────────────────
        newly_admitted: list[_ActiveJob] = []
        requeued_this_tick: int = 0
        for pa in ready:
            # Dedup: idempotent on event_id
            if pa.event_id in self._seen_event_ids:
                _log.debug("kube: dedup drop %s", pa.event_id)
                continue
            self._seen_event_ids.add(pa.event_id)

            # Capacity validation
            current_nodes = (
                sum(j.node_count for j in self._active_jobs)
                + sum(j.node_count for j in newly_admitted)
            )
            if current_nodes + pa.node_count > self.config.max_nodes:
                _log.debug(
                    "kube: capacity reject %s (%d nodes, current=%d, max=%d)",
                    pa.event_id, pa.node_count, current_nodes, self.config.max_nodes,
                )
                continue

            # Power-cap hold: re-queue with a short delay; never drops the job
            if power_cap_active:
                retry_id = f"{pa.event_id}-retry"
                if retry_id not in self._seen_event_ids:
                    self._reorder_buffer.append(_PendingAdmission(
                        event_id=retry_id,
                        node_count=pa.node_count,
                        hardware_profile_id=pa.hardware_profile_id,
                        observed_at=sim_time + 5.0,   # re-enter buffer in 5 s
                        event_timestamp=sim_time + 5.0,
                        duration_s=pa.duration_s,
                    ))
                requeued_this_tick += 1
                _log.debug(
                    "kube: power-cap hold %s (headroom=%.2f MW) → queued retry",
                    pa.event_id, headroom_mw,
                )
                continue

            job = _ActiveJob(
                event_id=pa.event_id,
                node_count=pa.node_count,
                hardware_profile_id=pa.hardware_profile_id,
                admitted_at=sim_time,
                ends_at=sim_time + pa.duration_s,
            )
            newly_admitted.append(job)
            _log.info(
                "kube: ADMITTED %s — %d nodes, ends_at=%.1f s",
                pa.event_id, pa.node_count, job.ends_at,
            )

        self._active_jobs.extend(newly_admitted)

        # ── Step 2c: Critical headroom eviction ───────────────────────────
        # headroom < 0 → evict the largest running job to recover headroom fastest.
        if headroom_mw < 0.0 and self._active_jobs:
            self._active_jobs.sort(key=lambda j: j.node_count, reverse=True)
            evicted = self._active_jobs.pop(0)
            _log.warning(
                "kube: EVICT %s (%d nodes) — critical headroom %.2f MW",
                evicted.event_id, evicted.node_count, headroom_mw,
            )

        # ── Derive metrics ────────────────────────────────────────────────
        admitted_nodes = sum(j.node_count for j in self._active_jobs)
        # min_nodes is the idle baseline — cluster is never fully drained
        total_nodes = max(self.config.min_nodes, admitted_nodes)
        active_jobs = len(self._active_jobs)
        utilization = total_nodes / self.config.max_nodes

        # ── Emit WorkloadSignal when node count changes ───────────────────
        # STARTING on the first emission (tick 0); SCALE on subsequent changes.
        signals: list[WorkloadSignal] = []
        if not self._started or total_nodes != self._last_total_nodes:
            event_type = (
                WorkloadEventType.STARTING if not self._started
                else WorkloadEventType.SCALE
            )
            signals.append(WorkloadSignal(
                event_id=f"kube-signal-t{int(sim_time * 10)}",
                job_id=f"kube-admission-{self._job_counter}",
                event_type=event_type,
                timestamp=sim_time,
                hardware_profile_id=self.config.hardware_profile_id,
                node_count=total_nodes,
                workload_class=WorkloadClass.TRAINING,
                site_id=self.site_id,
            ))
            self._started = True
            self._last_total_nodes = total_nodes
            _log.debug(
                "kube: signal %s → %d nodes (util=%.3f, jobs=%d) at sim_time=%.1f",
                event_type.value, total_nodes, utilization, active_jobs, sim_time,
            )

        # ── Step scheduler ────────────────────────────────────────────────────
        # Tick the continuous-time step scheduler; update current_step_phase and
        # current_step_kind so simulation_core can stamp them on TickResult and
        # propagate step_phase to GPUModules before gpu.advance() runs.
        if self._step_scheduler is not None:
            _fired, _phase, _kind = self._step_scheduler.tick(
                sim_time, dt_seconds, self._rng_step
            )
            self.current_step_phase = _phase
            self.current_step_kind = _kind

        metrics = KubeMetrics(
            utilization=utilization,
            node_count=total_nodes,
            power_cap_active=power_cap_active,
            headroom_mw=headroom_mw,
            active_jobs=active_jobs,
            admitted_nodes=admitted_nodes,
            arrivals_this_tick=arrivals_this_tick,
            requeued_this_tick=requeued_this_tick,
            queued_jobs=len(self._reorder_buffer),
        )
        return signals, metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))
