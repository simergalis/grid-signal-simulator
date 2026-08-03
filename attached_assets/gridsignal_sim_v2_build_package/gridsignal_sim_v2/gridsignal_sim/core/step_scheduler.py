"""
core/step_scheduler.py — Continuous-time stochastic ML training-step scheduler.

Replaces the tick-counter modulo (tick % 7 == 0) with a seeded stochastic
process in continuous sim time.  next_step_time is stored in sim seconds and
never rounded to the tick grid, so the step period is tick-rate independent
(T7 acceptance criterion).

Algorithm (spec Part 1):
  1. Base step duration: lognormal with OU drift on the log-median.
  2. OU drift: Ornstein-Uhlenbeck on x_t = deviation from mu_0 = ln(median_step_s).
     Integration uses the step duration as dt (one OU step per ML step) so the
     OU trajectory is the same regardless of simulation tick rate.
  3. Straggler outliers: with probability p_straggler, multiply the drawn
     duration by 1 + Exp(straggler_scale), capped at straggler_max.
  4. Checkpoint long-steps: every ckpt_interval_steps ± ckpt_jitter_steps steps,
     draw duration from Uniform(ckpt_min_s, ckpt_max_s) and set step_kind to
     "checkpoint" so the existing checkpoint-valley classifier can detect it.

Thread safety: not thread-safe; designed for single-threaded use inside
evaluate_tick().
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from .step_config import StepTimingConfig

if TYPE_CHECKING:
    pass  # avoid circular imports


@dataclass
class StepScheduler:
    """Continuous-time stochastic step scheduler.

    One instance per KubeDemandAgent (fleet-level; not per GPU module).

    Usage:
        fired, step_phase, step_kind = scheduler.tick(sim_time, dt, rng)

    step_phase ∈ [0, 1) gives the fractional position within the current
    step — 0 at the moment the step fires, approaching 1 just before the
    next step fires.  This is the signal that drives the within-step power
    profile in GPUModule.

    step_kind is "training" for normal steps and "checkpoint" for the
    periodic long-steps injected by §1.4.
    """

    config: StepTimingConfig
    _initial_sim_time: float = 0.0  # sim time when the scheduler is first ticked

    # ── Continuous-time state ─────────────────────────────────────────────────
    # next_step_time — sim seconds at which the next step fires.
    #   Never rounded to the tick grid.
    next_step_time: float = field(default=0.0, init=False)

    # _last_step_time — sim time of the most recently fired step.
    _last_step_time: float = field(default=0.0, init=False)

    # _last_step_duration — duration drawn for the most recently fired step.
    #   Used to compute step_phase on subsequent ticks.
    _last_step_duration: float = field(default=0.0, init=False)

    # ── OU process state ──────────────────────────────────────────────────────
    # x_t — current OU deviation from mu_0 = ln(median_step_s).
    #   mu_eff = mu_0 + x_t is the log-median for the next step's lognormal draw.
    _x_t: float = field(default=0.0, init=False)

    # ── Step counter ──────────────────────────────────────────────────────────
    _n_steps: int = field(default=0, init=False)

    # _next_ckpt_at — step number at which the next checkpoint fires.
    _next_ckpt_at: int = field(default=0, init=False)

    # ── Current step kind (last fired) ───────────────────────────────────────
    _current_step_kind: str = field(default="training", init=False)

    # ── Initialisation guard ──────────────────────────────────────────────────
    _initialised: bool = field(default=False, init=False)

    def _initialise(self, sim_time: float, rng: np.random.Generator) -> None:
        """Set up the scheduler on the first tick.

        next_step_time is anchored to sim_time so that the first step fires
        roughly one median step after the run starts.  The first checkpoint
        is scheduled at the configured ckpt_interval_steps.
        """
        # Draw the first step duration (without OU drift — x_t=0 at start).
        sigma = math.sqrt(math.log(1.0 + self.config.step_cv ** 2))
        mu_0 = math.log(self.config.median_step_s)
        D = math.exp(rng.normal(mu_0, sigma))
        self._last_step_time = sim_time
        self._last_step_duration = D
        self.next_step_time = sim_time + D

        # Schedule first checkpoint.
        self._next_ckpt_at = self.config.ckpt_interval_steps
        self._initialised = True

    # ── Public API ────────────────────────────────────────────────────────────

    def tick(
        self,
        sim_time: float,
        dt: float,
        rng: np.random.Generator,
    ) -> tuple[bool, float, str]:
        """Advance the scheduler by one simulation tick.

        Parameters
        ----------
        sim_time : float
            Current sim time at the START of this tick (seconds).
        dt : float
            Tick duration (seconds).  Used only for logging context; the
            scheduler uses continuous time and is dt-independent.
        rng : np.random.Generator
            The dedicated step-stream generator (rng_step).  Must be the
            ONLY stream used by this method — stream isolation (D3).

        Returns
        -------
        fired : bool
            True if a step boundary was crossed this tick.
        step_phase : float
            Position within the current step, ∈ [0, 1).  0.0 immediately
            after a step fires; approaches 1.0 just before the next step.
        step_kind : str
            "training" for normal steps; "checkpoint" for long-steps.
        """
        if not self._initialised:
            self._initialise(sim_time, rng)
            # Return immediately: first step fires on the NEXT tick at earliest.
            return False, 0.0, self._current_step_kind

        # ── Compute step_phase before any state mutation ──────────────────────
        if self._last_step_duration > 0.0:
            elapsed = sim_time - self._last_step_time
            step_phase = min(elapsed / self._last_step_duration, 0.9999)
        else:
            step_phase = 0.0

        # ── Check whether a step fires this tick ──────────────────────────────
        if sim_time < self.next_step_time:
            return False, step_phase, self._current_step_kind

        # ── A step fires ──────────────────────────────────────────────────────
        # OU update — dt here is the elapsed sim time since the last step (the
        # step duration), NOT the tick interval.  This makes the OU trajectory
        # identical at any tick rate (required for T7).
        dt_ou = sim_time - self._last_step_time
        if dt_ou > 0.0:
            drift   = -(self._x_t / self.config.tau_drift_s) * dt_ou
            diffuse = (
                self.config.sigma_drift
                * math.sqrt(2.0 * dt_ou / self.config.tau_drift_s)
                * rng.standard_normal()
            )
            self._x_t += drift + diffuse

        # Advance state for the fired step.
        self._last_step_time = sim_time
        self._n_steps += 1

        # ── Draw next step duration ───────────────────────────────────────────
        if self._n_steps == self._next_ckpt_at:
            # §1.4 — checkpoint long-step.
            D = rng.uniform(self.config.ckpt_min_s, self.config.ckpt_max_s)
            self._current_step_kind = "checkpoint"
            # Schedule the next checkpoint (interval ± uniform jitter).
            jitter = int(rng.integers(
                -self.config.ckpt_jitter_steps,
                self.config.ckpt_jitter_steps + 1,
            ))
            self._next_ckpt_at = (
                self._n_steps
                + max(1, self.config.ckpt_interval_steps + jitter)
            )
        else:
            # §1.1 — lognormal draw.
            sigma = math.sqrt(math.log(1.0 + self.config.step_cv ** 2))
            mu_eff = math.log(self.config.median_step_s) + self._x_t  # §1.2 OU shift
            D = math.exp(rng.normal(mu_eff, sigma))

            # §1.3 — straggler outlier.
            if rng.random() < self.config.p_straggler:
                mult = 1.0 + rng.exponential(self.config.straggler_scale)
                mult = min(mult, self.config.straggler_max)
                D *= mult

            self._current_step_kind = "training"

        self._last_step_duration = D
        # §1.5 — carry fractional remainder forward; do NOT round to tick grid.
        self.next_step_time += D

        return True, 0.0, self._current_step_kind

    @property
    def step_count(self) -> int:
        """Total steps fired so far (read-only)."""
        return self._n_steps
