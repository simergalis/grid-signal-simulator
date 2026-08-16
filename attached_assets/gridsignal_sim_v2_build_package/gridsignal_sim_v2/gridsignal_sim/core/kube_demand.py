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

§6.2 Power-Cap Activation Policy
----------------------------------
The admission power-cap (power_cap_active) is an **emergency-only, last-resort**
control action — not a routine curtailment signal.  The v2.5 spec treats power
curtailment as a laddered, progressively-engaged reliability resource
(curtailment_proposal_tiers: A defer → B power-cap → C suspend → D shed).  The
binary hold implemented here corresponds to curtailment tier B and MUST only
engage under genuine grid-headroom duress, not in response to normal job-churn.

Activation conditions (both are sufficient to hold new admissions):
  (a) Raw headroom below threshold:
        turbine_headroom_mw + bess_headroom_mw < headroom_threshold_mw (2.5 MW)
  (b) Post-recovery hysteresis window:
        sim_time < _power_cap_hold_until
        where _power_cap_hold_until is set on the raw-cap True→False transition
        to sim_time + power_cap_hysteresis_s (default 90 s).

Anti-oscillation constraint (§6.2 / TC-NO1):
  power_cap_active MUST NOT toggle more than 5 times in any 300-second simulation
  window.  The 90 s post-recovery hold guarantees this across all tested RNG seeds.

Why hysteresis is required:
  Without it, the cap toggles at the job-completion frequency (~0.1 Hz with
  short-duration test jobs).  A 91 % compute-draw drop lasting 5 s with recovery
  within 45 s satisfies the §6.2 checkpoint-valley definition, permanently arming
  turbine pre-staging (r_asset = 0.2 MW/s, 18 MW swing → ~91 s to engage) from
  a stimulus that looks nothing like a real 10–30 s checkpoint plateau.
  Δt_thermal = 90 s and τ = 20 s cannot track a 5 s oscillation — the cooling
  double-lag differentiator becomes invisible, and the BESS cycles at 0.1 Hz.

Minimum hold duration:
  power_cap_hysteresis_s = 90 s ≥ 30 s (the spec minimum for emergency holds).
  Setting power_cap_hysteresis_s = 0.0 disables hysteresis and reverts to the
  raw headroom threshold; this is permitted only in test configurations that
  deliberately reproduce the oscillation pathology (TC-NO1 RED baseline).

Relationship to curtailment_proposal_tiers:
  The cap hold here operates at admission time (Step 2) before any compute draw
  occurs.  Tier-A (defer) and tier-C/D (suspend/shed) actions are handled by the
  curtailment ladder in the dispatch layer and are orthogonal to this gate.
  TickResult.curtailment_proposal_tiers carries tier labels for the UI; when
  power_cap_active=True, callers may include "B:power-cap" in that tuple to make
  the curtailment tier visible to operators.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .models import (
    KubeMetrics,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
    QueuedJobSummary,
    ActiveJobSummary,
)
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

    # Anti-oscillation hysteresis: once the power-cap activates, keep it
    # active for at least this many simulated seconds after headroom recovers.
    # Without hysteresis the cap toggles at the job-completion frequency
    # (~0.1 Hz with short test jobs), permanently arming turbine pre-staging
    # from a stimulus that looks nothing like a real 10–30 s checkpoint plateau.
    # 90 s gives ≤ 5 toggles per 300 s window across all tested seeds.
    # Set to 0.0 to disable hysteresis (reverts to raw headroom threshold).
    power_cap_hysteresis_s: float = 90.0

    # RNG seed for deterministic replay; None = time-seeded
    rng_seed: Optional[int] = 42

    # ── Multi-tenant identity (Phase B, JOBQ-001) ─────────────────────────────
    # One KubeDemandAgent instance per tenant; these values are fixed per agent
    # and stamped on every job the agent produces.  PROPOSED_HERE — ported from
    # gpuGeneratorStore.ts (tenantWeights: A/SLURM=0.40, B/K8S=0.35, C/RAY=0.25).
    tenant_id: str = "default"
    scheduler_type: str = "K8S"   # "SLURM" | "K8S" | "RAY"

    # kW per GPU node, used to derive est_draw_mw on per-job summaries.
    # SENTINEL DEFAULT — the factory (scenario_factory.py) MUST overwrite this
    # from DEFAULT_HARDWARE_LIBRARY[hardware_profile_id].rated_kw at agent
    # construction time.  The default 0.0 produces est_draw_mw = 0.0, which is
    # a visible-wrong signal rather than a silently-plausible value.
    # Do NOT change this to 10.2 — that would recreate the second source of
    # truth this sentinel exists to prevent.
    rated_kw_per_node: float = 0.0

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
    # Multi-tenant identity — stamped from the agent's KubeConfig at arrival time.
    tenant_id: str = "default"
    scheduler_type: str = "K8S"
    # Addendum 1: first-queued timestamp preserved across power-cap re-queues.
    # On the original arrival, first_queued_at == observed_at.  On every
    # subsequent power-cap retry, first_queued_at is carried forward unchanged
    # so the frontend can compute a monotonically-increasing wait time.
    first_queued_at: float = 0.0
    # Number of times the power-cap has held and re-queued this job (0 = fresh).
    requeue_count: int = 0


@dataclass
class _ActiveJob:
    """A gang-admitted workload currently running."""
    event_id: str
    node_count: int
    hardware_profile_id: str
    admitted_at: float
    ends_at: float
    # Multi-tenant identity — threaded from _PendingAdmission at admission time.
    tenant_id: str = "default"
    scheduler_type: str = "K8S"


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

        # Anti-oscillation: transition-based post-recovery hold.
        # _power_cap_hold_until is set on the raw-cap True→False edge
        # (i.e. when headroom first recovers above the threshold).  The cap
        # stays enforced for exactly power_cap_hysteresis_s after that edge,
        # preventing burst re-admission at the job-completion frequency.
        # (~0.1 Hz in stress tests → permanent §6.2 checkpoint-valley arming).
        self._power_cap_hold_until: float = -1.0
        # Tracks whether raw headroom was below threshold on the previous tick
        # so we can detect the True→False recovery transition.
        self._prev_raw_cap: bool = False

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
        already_admitted_nodes: int = 0,
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
            raw_cap = headroom_mw < self.config.headroom_threshold_mw

            # Anti-oscillation hysteresis (transition-based post-recovery hold).
            #
            # The cap enforces on two conditions:
            #   (a) raw_cap=True  — headroom is currently below threshold.
            #   (b) sim_time < _power_cap_hold_until — within the post-recovery
            #       window set on the most recent raw-cap True→False transition.
            #
            # Crucially, hold_until is updated ONLY on the recovery edge, not
            # on every raw-cap tick.  This guarantees exactly power_cap_hysteresis_s
            # of post-recovery suppression regardless of how long the raw cap lasted.
            # Rolling the hold forward every raw-cap tick would shorten the
            # post-recovery window to at most one tick.
            if not raw_cap and self._prev_raw_cap:
                # Headroom just recovered: start the post-recovery hold now.
                self._power_cap_hold_until = sim_time + self.config.power_cap_hysteresis_s
            self._prev_raw_cap = raw_cap

            power_cap_active = raw_cap or (sim_time < self._power_cap_hold_until)

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
                tenant_id=self.config.tenant_id,
                scheduler_type=self.config.scheduler_type,
                first_queued_at=self._next_arrival_sim_time,  # stamped once; never overwritten on retry
                requeue_count=0,
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
                + already_admitted_nodes          # cross-agent committed nodes (§ JOBQ-001 Phase B)
            )
            if current_nodes + pa.node_count > self.config.max_nodes:
                _log.debug(
                    "kube: capacity reject %s (%d nodes, current=%d, max=%d)",
                    pa.event_id, pa.node_count, current_nodes, self.config.max_nodes,
                )
                continue

            # Power-cap hold: re-queue with one-tick delay; never drops the job.
            # Previously hardcoded to 5.0 s (== TICK_INTERVAL_SIM_SECONDS), which
            # locked re-admission to every tick and caused 0.1 Hz BESS cycling.
            # Now uses dt_seconds (the actual tick interval) so the delay scales
            # correctly regardless of how the caller configures the tick rate.
            # The anti-oscillation hysteresis on power_cap_active (above) is the
            # primary fix; this change removes the brittle literal.
            if power_cap_active:
                # Derive a stable base ID by stripping any previous "-retry-N" suffix,
                # then append the new requeue count.  This prevents the ID from growing
                # as "job-retry-retry-retry-…" across successive power-cap holds.
                base_id = pa.event_id.split("-retry")[0]
                next_count = pa.requeue_count + 1
                retry_id = f"{base_id}-retry-{next_count}"
                if retry_id not in self._seen_event_ids:
                    self._reorder_buffer.append(_PendingAdmission(
                        event_id=retry_id,
                        node_count=pa.node_count,
                        hardware_profile_id=pa.hardware_profile_id,
                        observed_at=sim_time + dt_seconds,   # re-enter after one tick
                        event_timestamp=sim_time + dt_seconds,
                        duration_s=pa.duration_s,
                        tenant_id=pa.tenant_id,
                        scheduler_type=pa.scheduler_type,
                        first_queued_at=pa.first_queued_at,  # preserved — never advances on retry
                        requeue_count=next_count,
                    ))
                requeued_this_tick += 1
                _log.debug(
                    "kube: power-cap hold %s (headroom=%.2f MW) → queued retry-%d",
                    base_id, headroom_mw, next_count,
                )
                continue

            job = _ActiveJob(
                event_id=pa.event_id,
                node_count=pa.node_count,
                hardware_profile_id=pa.hardware_profile_id,
                admitted_at=sim_time,
                ends_at=sim_time + pa.duration_s,
                tenant_id=pa.tenant_id,
                scheduler_type=pa.scheduler_type,
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

        _kw = self.config.rated_kw_per_node
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
            queued_nodes=sum(pa.node_count for pa in self._reorder_buffer),
            pending_jobs=tuple(
                QueuedJobSummary(
                    event_id=pa.event_id,
                    tenant_id=pa.tenant_id,
                    scheduler_type=pa.scheduler_type,
                    node_count=pa.node_count,
                    hardware_profile_id=pa.hardware_profile_id,
                    observed_at=pa.observed_at,
                    duration_s=pa.duration_s,
                    est_draw_mw=round(pa.node_count * _kw / 1000.0, 4),
                    queued_since_s=pa.first_queued_at,
                    requeue_count=pa.requeue_count,
                )
                for pa in self._reorder_buffer
            ),
            active_jobs_detail=tuple(
                ActiveJobSummary(
                    event_id=j.event_id,
                    tenant_id=j.tenant_id,
                    scheduler_type=j.scheduler_type,
                    node_count=j.node_count,
                    hardware_profile_id=j.hardware_profile_id,
                    admitted_at=j.admitted_at,
                    ends_at=j.ends_at,
                    est_draw_mw=round(j.node_count * _kw / 1000.0, 4),
                )
                for j in self._active_jobs
            ),
        )
        return signals, metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))
