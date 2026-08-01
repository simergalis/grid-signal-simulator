"""
runtime/telemetry_corruption.py — Pre-generated telemetry corruption schedule.

Sits conceptually between the plant simulator and the engine's ingestor:
corrupts WorkloadSignal timestamps and telemetry record values to stress the
§17.2 quarantine / confidence-widening path, NTP-skew handling, and
out-of-order delivery logic.

Design
------
The corruption schedule is generated ONCE at run start from a seeded RNG,
producing a per-tick manifest of:
  - noise_fraction  : ±σ multiplicative noise to apply to a metric value
  - dropout         : True → suppress the record entirely (simulates packet loss)
  - staleness_ticks : N → repeat the reading from N ticks ago (stale sensor)

The tick loop reads TelemetryCorruptionSchedule.for_tick(tick_index) to get
the CorruptionEntry for that tick, then applies it before passing data to the
ingestor.

Why seeded RNG (not LLM)
--------------------------
Sensor noise, dropout probability, and staleness are well-characterised
distributions.  There is no temporal structure a model adds value to.
A seeded schedule is reproducible by seed alone, cheap, and auditable.

Module isolation
----------------
Does not import from core/ or api/ — callable from runtime/ and tests.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Optional

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-tick corruption entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CorruptionEntry:
    """Corruption applied to one tick's telemetry.

    noise_sigma   : if > 0, multiply reading by (1 + N(0, noise_sigma))
    dropout       : if True, suppress the record entirely
    staleness     : if > 0, substitute the reading from this many ticks ago

    All three can be active simultaneously; application order is:
      1. staleness (substitute old reading)
      2. noise (add Gaussian noise to that reading)
      3. dropout (suppress the corrupted reading)
    """
    noise_sigma:  float = 0.0
    dropout:      bool  = False
    staleness:    int   = 0   # ticks


# ── Null entry — used when corruption is disabled for a tick ─────────────────
_CLEAN = CorruptionEntry()


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@dataclass
class TelemetryCorruptionSchedule:
    """Pre-generated per-tick corruption plan for one run.

    Attributes
    ----------
    schedule    : list of CorruptionEntry, one per tick index (0-based).
                  Length equals the number of ticks in the run.
    seed        : RNG seed used to generate the schedule.
    noise_sigma : noise level parameter used at generation time.
    dropout_prob: per-tick dropout probability used at generation time.
    max_stale   : maximum staleness window used at generation time.
    source      : "telemetry_corruption/rng"
    """
    schedule:    list[CorruptionEntry]
    seed:        Optional[int]
    noise_sigma: float
    dropout_prob: float
    max_stale:   int
    source:      str = "telemetry_corruption/rng"

    def for_tick(self, tick_index: int) -> CorruptionEntry:
        """Return the CorruptionEntry for the given zero-based tick index.

        Returns a clean (no-op) entry if tick_index is out of range —
        the schedule silently covers any overshoot (e.g. off-by-one at run end).
        """
        if 0 <= tick_index < len(self.schedule):
            return self.schedule[tick_index]
        return _CLEAN

    def summary(self) -> str:
        """Short human-readable summary for the generation_block."""
        n_drop    = sum(1 for e in self.schedule if e.dropout)
        n_noisy   = sum(1 for e in self.schedule if e.noise_sigma > 0)
        n_stale   = sum(1 for e in self.schedule if e.staleness > 0)
        total     = len(self.schedule)
        return (
            f"seed={self.seed}, ticks={total}, "
            f"dropout={n_drop} ({100*n_drop/max(1,total):.1f}%), "
            f"noisy={n_noisy}, stale={n_stale}"
        )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_corruption_schedule(
    n_ticks: int,
    *,
    seed:         Optional[int] = None,
    noise_sigma:  float = 0.0,
    dropout_prob: float = 0.0,
    max_stale:    int   = 0,
) -> TelemetryCorruptionSchedule:
    """Pre-generate a per-tick telemetry corruption schedule.

    Parameters
    ----------
    n_ticks      : total number of ticks in the run.
    seed         : RNG seed for reproducible replay.
    noise_sigma  : 1-σ of multiplicative Gaussian noise (e.g. 0.05 → ±5%).
                   0.0 = no noise.
    dropout_prob : probability [0, 1) that any given tick's record is suppressed.
                   0.0 = no dropout.
    max_stale    : maximum number of ticks of staleness.  0 = no staleness.
                   When > 0, each tick has a 15% chance of being stale by
                   uniform([1, max_stale]) ticks.

    Returns
    -------
    TelemetryCorruptionSchedule — one CorruptionEntry per tick.
    """
    rng = random.Random(seed)
    schedule: list[CorruptionEntry] = []

    for _ in range(n_ticks):
        dropout = dropout_prob > 0.0 and rng.random() < dropout_prob

        sigma = 0.0
        if noise_sigma > 0.0:
            # Gaussian noise active this tick; actual noise is applied at read time
            # using a separate RNG draw so the schedule itself stores σ, not the
            # specific noise sample — that keeps the schedule compact and lets the
            # caller regenerate the exact sample from the same seed if needed.
            sigma = noise_sigma

        stale = 0
        if max_stale > 0 and rng.random() < 0.15:
            stale = rng.randint(1, max_stale)

        schedule.append(CorruptionEntry(noise_sigma=sigma, dropout=dropout, staleness=stale))

    sched = TelemetryCorruptionSchedule(
        schedule=schedule,
        seed=seed,
        noise_sigma=noise_sigma,
        dropout_prob=dropout_prob,
        max_stale=max_stale,
    )
    _log.info("telemetry_corruption: generated schedule — %s", sched.summary())
    return sched


# ---------------------------------------------------------------------------
# Application helper
# ---------------------------------------------------------------------------

def apply_corruption(
    value: float,
    entry: CorruptionEntry,
    *,
    stale_value: Optional[float],
    rng: random.Random,
) -> tuple[Optional[float], bool]:
    """Apply one CorruptionEntry to a single metric reading.

    Parameters
    ----------
    value       : the clean current-tick value.
    entry       : CorruptionEntry from the schedule.
    stale_value : the reading from entry.staleness ticks ago (None if unavailable).
    rng         : a per-run Random instance for the noise draw.

    Returns
    -------
    (result, suppressed)
    - result     : corrupted value, or None when suppressed.
    - suppressed : True when dropout=True (record should not be ingested).
    """
    # Step 1: staleness — substitute historical reading
    working = value
    if entry.staleness > 0 and stale_value is not None:
        working = stale_value

    # Step 2: Gaussian noise
    if entry.noise_sigma > 0.0:
        working = working * (1.0 + rng.gauss(0.0, entry.noise_sigma))

    # Step 3: dropout — suppress the record
    if entry.dropout:
        return None, True

    return working, False
