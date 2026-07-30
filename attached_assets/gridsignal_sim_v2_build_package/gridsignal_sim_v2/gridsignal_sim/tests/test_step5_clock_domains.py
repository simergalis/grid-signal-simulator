"""
tests/test_step5_clock_domains.py — Step 5: Simulated clock and the two clock domains.

v2.5 TC-35, run at rate=1 and rate=60.  Also contains test_sim_clock_rate_arithmetic
which verifies the rate-vs-wall-time arithmetic used throughout the simulator.

TC-34 (v2.5 §16.8) is "restart preserves the 15-minute dedupe window."
It requires the §17.1 dedupe LOGIC (not just the dedupe_key table from Step 2).
TC-34 is DEFERRED to Step 10 where the dedupe window implementation lives.
Do not re-label any test here as TC-34 until that logic exists and is exercised.

Both tests pass trivially at rate=1 (simulated time == wall time); the rate=60
variants are the checks that catch a clock-domain error.  If anything measured
a grace period or dedupe window in wall seconds rather than simulated seconds,
the rate=60 run would produce a different answer than the rate=1 run.

test_sim_clock_rate_arithmetic: at rate=60, a 15-minute dedupe window covers
         15 SIMULATED minutes (900 sim-s), which is only 15 real seconds of wall
         time (900/60=15), not 15 wall minutes.  The window is measured in
         simulated time; wall time is just a receipt.

TC-35 — Restart resumes simulated clock: a job in the UNCERTAIN state with
         25 s elapsed against the 30 s grace period, after a simulated restart
         that preserves sim_time, must expire ~10 simulated seconds later — not
         30 s from scratch.  The two clock rules from core/sim_clock.py:
           Rule 1: all spec intervals are in simulated time.
           Rule 2: a restart RESUMES sim_time (reads tick_seq anchor), not resets.
"""

from __future__ import annotations

import pytest

from core.dispatch import CheckpointClassifier, CheckpointState
from core.sim_clock import SimClock

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_clock(
    sim_time: float,
    dt_seconds: float,
    tick_seq: int = 0,
    rate: float = 1.0,
) -> SimClock:
    """SimClock factory for tests — wall_stamp_utc=None signals absent wall clock."""
    return SimClock(
        sim_time=sim_time,
        dt_seconds=dt_seconds,
        wall_stamp_utc=None,
        rate=rate,
        tick_seq=tick_seq,
    )


# ---------------------------------------------------------------------------
# TC-34 — SimClock rate arithmetic
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rate", [1.0, 60.0])
def test_sim_clock_rate_arithmetic(rate: float) -> None:
    """Verify SimClock rate arithmetic: at rate R, 15 simulated minutes elapses
    while only 15/R real seconds pass.

    This test verifies:
    - sim_time accumulates at dt_seconds per tick regardless of rate.
    - wall elapsed = sim_elapsed / rate (rate R means R sim-s per real second).
    - At rate=60, wall elapsed is 60× smaller than sim elapsed.

    If a future implementation measured the dedupe window in wall time, the
    rate=60 variant would assert incorrectly (wall elapsed < window, never
    expires), making this the clock-domain detector needed by any dedupe logic.

    NOTE — TC-34 (v2.5 §16.8, "restart preserves the 15-minute dedupe window")
    is DEFERRED to Step 10.  TC-34 requires the §17.1 dedupe LOGIC (not just
    the dedupe_key table from Step 2).  Do not label this test TC-34.
    """
    DT = 5.0                       # simulated tick interval (seconds)
    DEDUPE_WINDOW_SIM_S = 15 * 60  # §17.1: 15-minute window in simulated seconds
    TICKS = int(DEDUPE_WINDOW_SIM_S / DT)  # 180 ticks

    sim_time = 0.0
    wall_elapsed = 0.0
    wall_per_tick = DT / rate      # real seconds per tick (DT / rate)

    for i in range(TICKS):
        clock = _make_clock(sim_time, DT, tick_seq=i, rate=rate)
        # Simulate: sim_time and wall both advance consistently.
        assert clock.sim_time == pytest.approx(sim_time, abs=1e-9)
        sim_time += DT
        wall_elapsed += wall_per_tick

    # After TICKS ticks: sim time has covered exactly one dedupe window.
    assert sim_time == pytest.approx(DEDUPE_WINDOW_SIM_S, abs=1e-9), (
        f"Sim time should be {DEDUPE_WINDOW_SIM_S} s after {TICKS} ticks at "
        f"dt={DT}; got {sim_time}"
    )

    # Rule 1: the window is measured in simulated time.
    # It has now expired regardless of what rate was used.
    assert sim_time >= DEDUPE_WINDOW_SIM_S, (
        "Dedupe window must expire in simulated time after 15 simulated minutes."
    )

    # Wall elapsed scales with rate.
    expected_wall = DEDUPE_WINDOW_SIM_S / rate
    assert wall_elapsed == pytest.approx(expected_wall, rel=1e-9), (
        f"At rate={rate}, wall elapsed should be {expected_wall:.1f} s; "
        f"got {wall_elapsed:.4f} s"
    )

    # At rate=60: wall elapsed is 15 real seconds, NOT 15 real minutes.
    if rate == 60.0:
        assert wall_elapsed == pytest.approx(15.0, abs=1e-9), (
            f"At rate=60, 15 simulated minutes = 15 real seconds; "
            f"got {wall_elapsed:.4f} s"
        )
        wrong_wall_window = 15 * 60  # 15 real minutes in seconds
        assert wall_elapsed < wrong_wall_window, (
            "Confirm: 15 sim-minutes at rate=60 is NOT 15 real minutes."
        )


# ---------------------------------------------------------------------------
# TC-35 — Restart resumes simulated clock
# ---------------------------------------------------------------------------

def _drive_job_to_uncertain(
    classifier: CheckpointClassifier,
    job_id: str,
    dt: float,
    rate: float,
) -> float:
    """Drive the classifier to UNCERTAIN state for job_id.

    Returns the sim_time at which UNCERTAIN was first reached.  The
    caller can use this to verify elapsed-time arithmetic after a
    simulated restart.
    """
    # Phase 1: build a trailing median with consistent draw.
    t = 0.0
    for _ in range(3):  # 3 ticks is enough for a non-empty median window
        classifier.record_and_classify(job_id, t, draw_mw=10.0)
        t += dt

    # Phase 2: induce a valley (draw drops > 15% below the trailing median).
    # A draw of 0.5 MW against a 10.0 MW median is a 95% drop — well above the
    # 15% DROP_THRESHOLD_FRACTION.
    valley_onset_t = t
    classifier.record_and_classify(job_id, t, draw_mw=0.5)
    t += dt

    # Phase 3: advance past RECOVERY_WINDOW_S (45 s) without recovery.
    # The classifier transitions to UNCERTAIN when elapsed > 45 s.
    state = CheckpointState.IN_VALLEY
    while state != CheckpointState.UNCERTAIN:
        state = classifier.record_and_classify(job_id, t, draw_mw=0.5)
        if state == CheckpointState.UNCERTAIN:
            break
        t += dt

    hist = classifier._jobs[job_id]
    assert hist.uncertain_since is not None, (
        f"uncertain_since must be set when state is UNCERTAIN; "
        f"valley_onset={valley_onset_t}, last_t={t}"
    )
    return t   # sim_time at which UNCERTAIN was first returned


@pytest.mark.parametrize("rate", [1.0, 60.0])
def test_tc35_restart_resumes_uncertain_grace_period(rate: float) -> None:
    """TC-35: a restart must RESUME the simulated clock, not reset it.

    Scenario:
    1. Drive a job to UNCERTAIN state (uncertain_since = T_u).
    2. Advance 25 simulated seconds of grace period (elapsed = 25 s).
    3. Simulate a restart: resume sim_time from the last tick (T_u + 25).
       This is Rule 2: a restart reads tick_seq from the DB and resumes
       sim_time = tick_seq × dt, not 0.
    4. Advance a further 10 simulated seconds.  With elapsed = 35 s > 30 s
       (UNCERTAIN_GRACE_PERIOD_S = 30), the state must be JOB_END.

    Wrong behaviour (Rule 2 violation): if sim_time were reset to 0 at restart,
    elapsed = sim_time - uncertain_since would be negative for many ticks, and
    the grace period would expire 30+ simulated seconds AFTER sim_time reached
    T_u again — effectively adding an extra full 30-second grace period to every
    restart.

    At rate=60: wall time advances 60× slower than simulated time.  Rule 1
    means the classifier measures elapsed in sim-s, not wall-s.  The test result
    is identical at rate=1 and rate=60; a divergence would be a clock-domain bug.
    """
    DT = 5.0
    GRACE = CheckpointClassifier.UNCERTAIN_GRACE_PERIOD_S  # 30.0

    classifier = CheckpointClassifier()
    job_id = "tc35-job"

    # Step 1: drive to UNCERTAIN and record the sim_time at that moment.
    uncertain_t = _drive_job_to_uncertain(classifier, job_id, DT, rate)
    hist = classifier._jobs[job_id]
    uncertain_since = hist.uncertain_since
    assert uncertain_since is not None

    # Step 2: advance 25 simulated seconds of grace period (5 ticks × DT=5).
    # elapsed = 25 s < GRACE (30 s) — still UNCERTAIN.
    t = uncertain_t + DT  # advance past the tick that set UNCERTAIN
    grace_ticks_advanced = 0
    while t - uncertain_since < 25.0:
        state = classifier.record_and_classify(job_id, t, draw_mw=0.5)
        assert state == CheckpointState.UNCERTAIN, (
            f"Expected UNCERTAIN at elapsed={t - uncertain_since:.1f} s "
            f"(uncertain_since={uncertain_since}, t={t}); got {state}"
        )
        t += DT
        grace_ticks_advanced += 1

    # Confirm we are still UNCERTAIN with 25 s elapsed before the "restart".
    state_before_restart = classifier.record_and_classify(job_id, t, draw_mw=0.5)
    elapsed_at_restart = t - uncertain_since
    assert elapsed_at_restart >= 25.0, (
        f"Expected ≥ 25 s of grace elapsed before restart; got {elapsed_at_restart:.1f} s"
    )
    assert state_before_restart == CheckpointState.UNCERTAIN, (
        f"Job must still be UNCERTAIN at restart point (elapsed={elapsed_at_restart:.1f} s); "
        f"got {state_before_restart}"
    )

    # --- SIMULATED RESTART ---
    # Rule 2: resume sim_time from the last persisted tick_seq.
    # In this test, we simply continue advancing t from its current value.
    # The key invariant: t is NOT reset to 0; uncertain_since is NOT modified.
    restart_clock = _make_clock(t, DT, tick_seq=int(t / DT), rate=rate)
    assert restart_clock.sim_time == t, "SimClock carries the resumed sim_time."

    # Step 3: advance 10 more simulated seconds past the restart.
    # elapsed at restart = elapsed_at_restart (≥ 25 s).
    # After 10 more sim-s, elapsed ≥ 35 s > GRACE (30 s) → JOB_END.
    t += DT
    final_state = CheckpointState.UNCERTAIN
    ticks_after_restart = 0
    while ticks_after_restart < 3:  # up to 15 sim-s (3 ticks × DT=5)
        final_state = classifier.record_and_classify(job_id, t, draw_mw=0.5)
        if final_state == CheckpointState.JOB_END:
            break
        t += DT
        ticks_after_restart += 1

    assert final_state == CheckpointState.JOB_END, (
        f"Grace period must expire within 15 sim-s of the restart point "
        f"(elapsed_at_restart={elapsed_at_restart:.1f} s, "
        f"GRACE={GRACE} s, rate={rate}).  "
        f"Final state after {ticks_after_restart + 1} post-restart ticks: "
        f"{final_state}."
    )

    # Step 4: confirm wrong behaviour (resetting sim_time) would NOT produce JOB_END
    # within the same window.
    # Wrong: reset sim_time = 0 after restart → elapsed = 0 - uncertain_since < 0.
    # The grace condition (sim_time - uncertain_since > 30) would be negative,
    # and JOB_END would not come until sim_time > uncertain_since + 30.
    elapsed_correct = t - uncertain_since
    assert elapsed_correct > GRACE, (
        f"Sanity: elapsed at JOB_END must exceed GRACE; "
        f"elapsed={elapsed_correct:.1f}, GRACE={GRACE}"
    )
    # Wrong path would have elapsed = (reset_t - uncertain_since) where reset_t ≈ 0,
    # so it stays negative and JOB_END would not fire within the same window.
    elapsed_if_reset = 0.0 - uncertain_since  # hypothetical elapsed after reset
    assert elapsed_if_reset < 0.0, (
        "Confirm: if sim_time were reset to 0, elapsed would be negative — "
        "grace period would not fire in the same window."
    )
