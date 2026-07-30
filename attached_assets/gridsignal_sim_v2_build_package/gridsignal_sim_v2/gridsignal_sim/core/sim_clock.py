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

    sim_time labeling convention — INTERVAL-START
    ---------------------------------------------
    sim_time is the START of the interval this tick covers: [sim_time, sim_time+dt_seconds).
    RunContext.step() passes sim_time to SimClock BEFORE calling evaluate_tick(), and
    increments self.sim_time AFTER evaluate_tick() returns.  Inside evaluate_tick(),
    asset advance() calls run BEFORE any measurement is taken, so every quantity in
    TickResult (power, SoC, dt_lead_next_s, bridging_seconds, …) reflects the physical
    state at sim_time + dt_seconds — the END of the interval, not the start.

    Concretely: the tick labeled sim_time=0.0 (tick_index=1) describes state after the
    first 5 simulated seconds have elapsed.  dt_lead_next_s=40.0 on that tick means
    "40 s of ramp remain at t=5 s", not at t=0 s.

    Step 8 / plotting convention
    ----------------------------
    When rendering a time-series chart with sim_time_seconds on the x-axis, interpret
    each point as "state measured at the end of the interval starting at sim_time."
    Two valid options for the x-axis coordinate:

      (A) Interval-start labeling (current) — plot at x = sim_time.
          Simple; matches the persisted field value.
          Visually the first point appears at x=0 but physically represents t=5s state.

      (B) Interval-end labeling — plot at x = sim_time + dt_seconds.
          Physically accurate; the first point appears at x=5.
          Requires every query/chart to add dt_seconds to the label.

    This codebase uses convention (A) throughout.  Attribution code in Step 8 and
    later steps must apply the same convention — do NOT mix (A) for storage and (B)
    for attribution, or tick-to-forecast alignment will be off by one interval.

    The chosen convention is deliberate and consistent; the only semantic trap is
    forgetting that sim_time=0.0 does NOT mean "no time has elapsed yet."
    """

    sim_time: float
    dt_seconds: float
    wall_stamp_utc: float   # UTC Unix timestamp; 0.0 sentinel for tests
    rate: float             # playback multiplier; ≤ 0 = max speed
    tick_seq: int           # persisted restart anchor
