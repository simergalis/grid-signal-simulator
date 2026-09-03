"""
core/step_config.py — Configuration dataclasses for the stochastic step
scheduler and within-step load profile.

All numeric defaults are documented with a SPEC_DEFAULT tag when they
come directly from the spec, or CHOSEN when they are our prototype values
with no measured basis.  No magic numbers should appear in the simulation
loop itself — they are all referenced through these dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Step timing configuration (Part 1 of the stochastic-step spec)
# ---------------------------------------------------------------------------

@dataclass
class StepTimingConfig:
    """Parameters for the continuous-time stochastic step scheduler.

    All defaults are SPEC_DEFAULT from the stochastic-step spec document.

    Step duration is drawn lognormal(mu=ln(median_step_s), sigma) with an
    Ornstein-Uhlenbeck drift on mu, straggler outlier injection, and
    periodic checkpoint long-steps.

    The scheduler is tick-rate independent: next_step_time is stored in
    continuous sim seconds and never rounded to the tick grid (T7).
    """

    # ── 1.1 Lognormal base step duration ────────────────────────────────────
    # median_step_s — median inter-step gap in synchronous distributed training.
    #   Corresponds to mu = ln(median_step_s) of the lognormal.
    #   SPEC_DEFAULT: 0.70 s.
    median_step_s: float = 0.70

    # step_cv — coefficient of variation; determines lognormal sigma.
    #   sigma = sqrt(ln(1 + step_cv**2)).
    #   SPEC_DEFAULT: 0.08 (8% coefficient of variation).
    step_cv: float = 0.08

    # ── 1.2 OU drift on the log-median ──────────────────────────────────────
    # tau_drift_s — OU mean-reversion time constant (seconds).
    #   Slower than tau_gpu_s; represents cluster thermal / contention drift.
    #   SPEC_DEFAULT: 300.0 s.
    tau_drift_s: float = 300.0

    # sigma_drift — OU diffusion coefficient (dimensionless, applied to ln-space).
    #   ≈3% drift in median step time over the drift time-scale.
    #   SPEC_DEFAULT: 0.03.
    sigma_drift: float = 0.03

    # ── 1.3 Straggler outliers ───────────────────────────────────────────────
    # p_straggler — probability per step of injecting a straggler multiplier.
    #   SPEC_DEFAULT: 0.02 (2% of steps).
    p_straggler: float = 0.02

    # straggler_scale — scale parameter of the exponential straggler multiplier.
    #   Actual multiplier = 1.0 + Exp(straggler_scale).
    #   SPEC_DEFAULT: 1.5.
    straggler_scale: float = 1.5

    # straggler_max — hard cap on the straggler multiplier to avoid absurd tails.
    #   SPEC_DEFAULT: 10.0.
    straggler_max: float = 10.0

    # ── 1.4 Checkpoint / eval boundaries ────────────────────────────────────
    # ckpt_interval_steps — nominal steps between checkpoint long-steps.
    #   SPEC_DEFAULT: 400.
    ckpt_interval_steps: int = 400

    # ckpt_jitter_steps — ±uniform jitter on the checkpoint interval.
    #   SPEC_DEFAULT: 40.
    ckpt_jitter_steps: int = 40

    # ckpt_min_s — minimum duration for a checkpoint step (uniform lower bound).
    #   SPEC_DEFAULT: 5.0 s.
    ckpt_min_s: float = 5.0

    # ckpt_max_s — maximum duration for a checkpoint step (uniform upper bound).
    #   SPEC_DEFAULT: 30.0 s.
    ckpt_max_s: float = 30.0


# ---------------------------------------------------------------------------
# Load profile configuration (Part 2 of the stochastic-step spec)
# ---------------------------------------------------------------------------

@dataclass
class LoadProfileConfig:
    """Parameters for the within-step compute load profile.

    Each step has a compute phase (GPUs near TDP) and a communication phase
    (all-reduce; GPUs largely idle waiting on the network).  A first-order
    GPU lag smooths sharp transitions; phase coherence scales the depth of
    the oscillation across the fleet.

    All defaults are SPEC_DEFAULT.
    """

    # ── 2.1 Within-step power profile ───────────────────────────────────────
    # f_compute — fraction of the step spent in the compute phase at power 1.0.
    #   Remaining (1 - f_compute) fraction is the allreduce phase at p_comm_ratio.
    #   SPEC_DEFAULT: 0.72.
    f_compute: float = 0.72

    # p_comm_ratio — relative GPU power during the allreduce (communication) phase.
    #   0 = completely idle; 1 = same as compute.
    #   SPEC_DEFAULT: 0.55.
    p_comm_ratio: float = 0.55

    # ── 2.2 Transition smoothing ─────────────────────────────────────────────
    # tau_gpu_s — first-order lag time constant for GPU power transitions.
    #   Smooths the sharp compute↔allreduce edge.
    #   SPEC_DEFAULT: 0.06 s.
    tau_gpu_s: float = 0.06

    # ── 2.3 Fleet phase coherence ────────────────────────────────────────────
    # phase_coherence — fraction of the raw profile departure from 1.0 that
    #   survives in the fleet-wide signal.  0 = perfectly incoherent (flat);
    #   1 = fully coherent (full oscillation).
    #   effective_profile = 1 + phase_coherence * (raw_profile - 1)
    #   SPEC_DEFAULT: 0.85.
    phase_coherence: float = 0.85

    # noise_sigma_fraction — Gaussian noise sigma as a fraction of the base draw.
    #   Adds measurement-like noise to compute_load_mw.
    #   CHOSEN (PROTO): 0.005 (0.5% noise sigma).  Small enough to preserve
    #   checkpoint classifier thresholds (15% of per-job draw).
    noise_sigma_fraction: float = 0.005
