"""
core/kube_demand.py — Autonomous Kubernetes demand agent.

Generates stochastic GPU-cluster demand using an Ornstein-Uhlenbeck process
(mean-reverting random walk) smoothed by an Exponential Moving Average.

The agent emits WorkloadSignal(STARTING) on its first tick, then SCALE events
whenever the smoothed utilisation crosses a hysteresis band. When grid headroom
falls below a configurable threshold the agent enforces a power-cap by capping
the scale target at its current node count (or forcing a step-down when headroom
goes negative).

No LLM is used: all demand is generated from seeded random-number arithmetic.
Pass rng_seed for deterministic replay; rng_seed=None gives time-seeded variety.

Design goals
------------
* Closes the compute-to-grid gap: the generation side reacts to scheduler
  decisions rather than discovering them from current sensors.
* dt_lead = 0 for all emitted signals — Kubernetes gives no advance notice to
  the grid.  BESS must bridge the ramp; this is exactly the GridSignal value.
* Fully isolated from I/O: tick() is synchronous, state-only — safe to call
  inside the evaluate_tick() purity guard.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Optional

from .models import KubeMetrics, WorkloadClass, WorkloadEventType, WorkloadSignal

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class KubeConfig:
    """Configuration for the Kubernetes demand agent (one instance per run)."""

    # Job identity — must not collide with any scripted job_id in the scenario.
    job_id: str = "kube-job-0"
    hardware_profile_id: str = "enterprise_8gpu_air"

    # Fleet sizing
    max_nodes: int = 1900
    min_nodes: int = 200

    # Ornstein-Uhlenbeck process parameters
    # μ: long-run mean utilisation (targeting ~72% GPU util is a common cloud target)
    target_utilization: float = 0.72
    # θ: mean-reversion rate (per sim-second). θ=0.04 → half-life ≈ 17 s.
    ou_theta: float = 0.04
    # σ: volatility (std dev per √(sim-second))
    ou_sigma: float = 0.08

    # EMA smoothing factor α ∈ (0, 1].  Lower = smoother.
    # α=0.18 gives a ~5-tick lag at the 5-s tick cadence.
    ema_alpha: float = 0.18

    # Hysteresis bands — avoid churn by only acting outside the dead-band
    scale_up_threshold: float = 0.80    # scale up when smoothed util > this
    scale_down_threshold: float = 0.62  # scale down when smoothed util < this

    # Step size per scale decision (fraction of max_nodes, rounded to int)
    scale_step_fraction: float = 0.05

    # Minimum sim-seconds between scale decisions (cooldown)
    scale_cooldown_s: float = 30.0

    # Grid headroom below which power-cap activates (MW)
    headroom_threshold_mw: float = 2.5

    # RNG seed for deterministic replay; None = time-seeded
    rng_seed: Optional[int] = 42


# ---------------------------------------------------------------------------
# Grid state snapshot (passed in from evaluate_tick; uses previous tick's values)
# ---------------------------------------------------------------------------

@dataclass
class KubeGridState:
    """Snapshot of grid-side metrics passed to KubeDemandAgent each tick.

    Values are from the *previous* tick — the scheduler reads the last known
    grid state, mirrors the real-world latency between Kubernetes and the EMS.
    """
    p_dispatch_required_mw: float
    bess_soc_fraction: float
    turbine_headroom_mw: float   # rated_mw_total − turbine_output_mw
    bess_headroom_mw: float      # available BESS discharge headroom


# KubeMetrics is defined in core/models.py to avoid a circular import
# (models.py ← kube_demand.py ← models.py).  It is imported above.


# ---------------------------------------------------------------------------
# KubeDemandAgent
# ---------------------------------------------------------------------------

class KubeDemandAgent:
    """Autonomous Kubernetes demand agent.

    Call tick() once per sim tick inside evaluate_tick().  Returns a list of
    WorkloadSignals to apply to SimulationState and a KubeMetrics snapshot.

    Thread safety: not thread-safe; designed for single-threaded use inside
    the synchronous evaluate_tick() function.
    """

    def __init__(self, config: KubeConfig, site_id: str = "site-0") -> None:
        self.config = config
        self.site_id = site_id
        self._rng = random.Random(config.rng_seed)

        # Ornstein-Uhlenbeck state: start at target utilisation
        self._ou_state: float = config.target_utilization
        # EMA state: aligned with OU at t=0
        self._ema_state: float = config.target_utilization

        # Scheduling state
        self._current_nodes: int = round(config.target_utilization * config.max_nodes)
        self._job_started: bool = False
        self._last_scale_sim_time: float = -9999.0

        # Grid state from the previous tick (None on tick 0)
        self._last_grid_state: Optional[KubeGridState] = None

        # Metrics for the most recent tick
        self._last_metrics: Optional[KubeMetrics] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick(
        self,
        sim_time: float,
        dt_seconds: float,
        grid_state: Optional[KubeGridState] = None,
    ) -> tuple[list[WorkloadSignal], KubeMetrics]:
        """Advance demand model by one tick.

        Returns:
            signals: list of WorkloadSignals to feed into
                     SimulationState.apply_workload_signal(signal, dt_lead=0.0).
                     May be empty if no scale decision fires this tick.
            metrics: KubeMetrics snapshot for this tick.
        """
        # ── 1. Advance stochastic demand model ─────────────────────────
        self._ou_state = self._advance_ou(dt_seconds)
        self._ema_state = (
            self.config.ema_alpha * self._ou_state
            + (1.0 - self.config.ema_alpha) * self._ema_state
        )
        smoothed_util = max(0.10, min(1.0, self._ema_state))

        # ── 2. Compute grid headroom (from last tick's grid state) ─────
        headroom_mw = 999.0
        power_cap_active = False
        if grid_state is not None:
            headroom_mw = grid_state.turbine_headroom_mw + grid_state.bess_headroom_mw

        # ── 3. First tick: emit STARTING ────────────────────────────────
        if not self._job_started:
            initial_nodes = _clamp(
                round(smoothed_util * self.config.max_nodes),
                self.config.min_nodes,
                self.config.max_nodes,
            )
            self._current_nodes = initial_nodes
            self._job_started = True
            self._last_scale_sim_time = sim_time

            _log.info(
                "kube: STARTING %s — %d nodes (util=%.2f) at sim_time=%.1f",
                self.config.job_id, initial_nodes, smoothed_util, sim_time,
            )

            metrics = KubeMetrics(
                utilization=smoothed_util,
                node_count=initial_nodes,
                power_cap_active=False,
                headroom_mw=headroom_mw,
            )
            self._last_metrics = metrics
            return [self._make_signal(WorkloadEventType.STARTING, initial_nodes, sim_time)], metrics

        # ── 4. Power-cap logic ─────────────────────────────────────────
        target_nodes = _clamp(
            round(smoothed_util * self.config.max_nodes),
            self.config.min_nodes,
            self.config.max_nodes,
        )

        if headroom_mw < self.config.headroom_threshold_mw:
            power_cap_active = True
            if headroom_mw < 0.0:
                # Critically tight: force a 10% step-down regardless of util
                forced_nodes = max(
                    self.config.min_nodes,
                    round(self._current_nodes * 0.90),
                )
                target_nodes = min(target_nodes, forced_nodes)
                _log.debug(
                    "kube: power-cap CRITICAL headroom=%.2f MW → cap to %d nodes",
                    headroom_mw, target_nodes,
                )
            else:
                # Tight: hold current node count; block scale-ups
                target_nodes = min(target_nodes, self._current_nodes)
                _log.debug(
                    "kube: power-cap SOFT headroom=%.2f MW → hold at %d nodes",
                    headroom_mw, self._current_nodes,
                )

        # ── 5. Hysteresis + cooldown decision ─────────────────────────
        cooldown_elapsed = (sim_time - self._last_scale_sim_time) >= self.config.scale_cooldown_s
        step = max(1, round(self.config.scale_step_fraction * self.config.max_nodes))

        new_nodes = self._current_nodes
        if cooldown_elapsed:
            if not power_cap_active and smoothed_util > self.config.scale_up_threshold:
                # Scale up toward target in one step
                new_nodes = min(self._current_nodes + step, target_nodes, self.config.max_nodes)
            elif smoothed_util < self.config.scale_down_threshold or (
                power_cap_active and target_nodes < self._current_nodes
            ):
                # Scale down toward target in one step
                new_nodes = max(self._current_nodes - step, target_nodes, self.config.min_nodes)

        signals: list[WorkloadSignal] = []
        if new_nodes != self._current_nodes:
            self._current_nodes = new_nodes
            self._last_scale_sim_time = sim_time
            signals.append(
                self._make_signal(WorkloadEventType.SCALE, new_nodes, sim_time)
            )
            _log.debug(
                "kube: SCALE %s → %d nodes (util=%.3f, cap=%s) at sim_time=%.1f",
                self.config.job_id, new_nodes, smoothed_util, power_cap_active, sim_time,
            )

        metrics = KubeMetrics(
            utilization=smoothed_util,
            node_count=self._current_nodes,
            power_cap_active=power_cap_active,
            headroom_mw=headroom_mw,
        )
        self._last_metrics = metrics
        return signals, metrics

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _advance_ou(self, dt_seconds: float) -> float:
        """One step of the Ornstein-Uhlenbeck process.

        dX = θ(μ − X)dt + σ√dt · ε,   ε ~ N(0,1)

        Clamped to [0.10, 1.0] before returning (hard floor at 10% — a
        cluster is never fully idle in this model).
        """
        cfg = self.config
        mean_reversion = cfg.ou_theta * (cfg.target_utilization - self._ou_state) * dt_seconds
        diffusion = cfg.ou_sigma * math.sqrt(dt_seconds) * self._rng.gauss(0.0, 1.0)
        return max(0.10, min(1.0, self._ou_state + mean_reversion + diffusion))

    def _make_signal(
        self,
        event_type: WorkloadEventType,
        node_count: int,
        sim_time: float,
    ) -> WorkloadSignal:
        cfg = self.config
        return WorkloadSignal(
            event_id=f"{cfg.job_id}-{event_type.value}-{round(sim_time)}",
            job_id=cfg.job_id,
            event_type=event_type,
            timestamp=sim_time,
            hardware_profile_id=cfg.hardware_profile_id,
            node_count=node_count,
            workload_class=WorkloadClass.TRAINING,
            site_id=self.site_id,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))
