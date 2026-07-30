"""
core/sim_clock.py — Simulated clock and the two clock domains.

Step 5 / Design Spec §4.3 / v2.5 §22.8 (ST-4).

Two rules govern every time measurement in this simulator.  They are
stated here because they are easy to get backwards:

  Rule 1 — ALL SPECIFICATION INTERVALS ARE MEASURED IN SIMULATED TIME.
  The 15-minute dedupe window, the 45 s recovery window, the 30 s
  uncertain grace period, the 120 s curtailment dwell, the 10 s BESS
  taper hold, and — from Step 3 — the Δt_lead ramp progress, the
  Δt_thermal cooling lag, the τ thermal rise, and the dt_thermal + 5·τ
  envelope retention rule are all measured in simulated seconds.

  A simulation running at rate=60 covers 60 simulated seconds for every
  1 real (wall-clock) second.  A 15-minute dedupe window expires after
  15 simulated minutes, not after 15 wall seconds.

  Rule 2 — A RESTART RESUMES THE SIMULATED CLOCK RATHER THAN JUMPING
  FORWARD.  The persisted tick_seq is the restart anchor.  After a
  restart, sim_time resumes from tick_seq × dt rather than from 0.

  If a restart reset sim_time to 0 while in-flight uncertain_since or
  drop_onset_time values remained positive, the elapsed calculations
  (sim_time − uncertain_since) would become negative, and a grace period
  that was nearly expired would appear to have just started.

Wall-clock stamps are recorded alongside simulated time on every
persisted row because forecast-error attribution against real latency
needs both.  The wall_stamp_utc field is a UTC Unix timestamp (float)
set by the runtime caller (RunContext.step in runtime/run_manager.py)
before passing the SimClock into evaluate_tick().  core/ never reads
the wall clock — Step 4's static gate enforces this.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimClock:
    """Carrier for all clock information for one tick.

    Constructed by the runtime layer (RunContext.step) and injected into
    evaluate_tick().  core/ never constructs a SimClock with a live wall
    clock — wall_stamp_utc is always supplied by the caller.

    Attributes
    ----------
    sim_time     : float — monotonic simulated seconds since scenario t₀.
                   All specification interval checks compare against this.
    dt_seconds   : float — simulated duration of this tick (typically
                   TICK_INTERVAL_SIM_SECONDS = 5.0 s from run_manager.py).
    wall_stamp_utc : float — UTC Unix timestamp at the start of this tick,
                   supplied by the runtime caller.  0.0 is the safe sentinel
                   for tests that do not need a real wall stamp.
    rate         : float — playback speed multiplier (≤ 0 means max speed /
                   no artificial sleep).  Informational; core/ does not use it.
    tick_seq     : int — monotonic tick counter.  The persistence layer writes
                   this alongside every RunTimeseries row.  On restart, the
                   runtime layer reads the highest persisted tick_seq and sets
                   sim_time = tick_seq × dt_seconds so that Rule 2 holds.

    Two-domain timestamp design (F5)
    ---------------------------------
    SimClock carries the INTERVAL-START timestamp for use by evaluate_tick()
    internals.  TickResult carries the INTERVAL-END timestamp for persistence
    and the wire.  These are different by design:

    SimClock.sim_time = START of the evaluation interval [sim_time, sim_time+dt).
    TickResult.sim_time_seconds = sim_time + dt_seconds = END of the interval.

    Why the split:
      • evaluate_tick() checks elapsed time against specification thresholds
        (e.g. "has the 45 s ramp window expired?").  These checks compare
        clock.sim_time against stored timestamps, so they must use the
        interval-start value — the same reference point the timestamps were
        recorded against.
      • TickResult is an instantaneous reading taken AFTER asset advance() calls
        have consumed dt_seconds of simulated time.  The state it describes is
        genuinely at t = sim_time + dt, not at t = sim_time.  Labeling it with
        the interval-start would introduce a systematic 5 s bias on every row
        stored in persistence — a problem for FR-1.5 MAPE calculations and for
        Step 8 forecast-vs-measured attribution that aligns on timestamps.

    Concretely: tick_index=1, SimClock.sim_time=0.0 → TickResult.sim_time_seconds=5.0.
    dt_lead_next_s=40.0 means "40 s of ramp remain at t=5 s (the reading instant)."

    Step 8 / attribution rule
    -------------------------
    Always align forecast and measured rows by TickResult.sim_time_seconds (the
    interval-end value stored in persistence).  Never add or subtract dt_seconds
    in query code — the offset is already baked into the stored field.
    """

    sim_time: float
    dt_seconds: float
    wall_stamp_utc: float   # UTC Unix timestamp; 0.0 sentinel for tests
    rate: float             # playback multiplier; ≤ 0 = max speed
    tick_seq: int           # persisted restart anchor
