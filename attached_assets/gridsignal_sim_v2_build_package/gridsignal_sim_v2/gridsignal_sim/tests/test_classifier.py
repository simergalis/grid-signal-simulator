"""
Acceptance tests for the checkpoint-valley classifier — Forecast Engine
Functional Spec v2.5 Addendum A §16.2, TC-05 through TC-09.

Also includes the §12 effective-PUE identity regression test, which guards
against the α/PUE double-count reappearing under any future change to
CoolingModule — in particular the Step 3 superposition rewrite.

Run from gridsignal_sim/:
    PYTHONPATH=. python -m pytest tests/test_classifier.py -v
"""

from __future__ import annotations

import math

from core.asset_modules import CoolingModule
from core.dispatch import CheckpointClassifier, CheckpointState
from core.models import SiteConfig


TICK_S = 5.0  # §3.1 evaluation cadence

_SITE = SiteConfig(
    site_id="s1",
    pue_base=1.03,
    alpha_max=0.20,
    tau_seconds=20.0,
    dt_thermal_seconds=90.0,
)


def _settle(
    clf: CheckpointClassifier,
    job_id: str,
    draw_mw: float,
    n: int = 60,
    step: float = TICK_S,
    t0: float = 0.0,
) -> float:
    """Run n ticks at draw_mw to establish a stable trailing median.
    Returns the sim_time of the next (not-yet-recorded) tick."""
    t = t0
    for _ in range(n):
        clf.record_and_classify(job_id, t, draw_mw)
        t += step
    return t


# ---------------------------------------------------------------------------
# TC-05 — Explicit scheduler event (primary signal)
# ---------------------------------------------------------------------------

def test_tc05_explicit_checkpoint_event():
    """TC-05: checkpoint_start / checkpoint_end pair brackets a compute drop.
    Classified checkpoint (primary signal); shape heuristic bypassed entirely.

    The explicit event pair is §6.2's authoritative path.  It must work
    regardless of what the power shape looks like.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)

    # Explicit checkpoint_start arrives: authoritative signal, no heuristic
    clf.apply_explicit_event("j1", is_checkpoint_start=True, sim_time=t)
    t += TICK_S
    mid = clf.record_and_classify("j1", t, 8.0)
    assert mid in (CheckpointState.IN_VALLEY, CheckpointState.CHECKPOINT), (
        f"explicit checkpoint_start must leave job in IN_VALLEY or CHECKPOINT; got {mid}"
    )

    # Explicit checkpoint_end closes the gate: must classify as CHECKPOINT
    clf.apply_explicit_event("j1", is_checkpoint_start=False, sim_time=t)
    t += TICK_S
    final = clf.record_and_classify("j1", t, 10.0)
    assert final is CheckpointState.CHECKPOINT, (
        f"explicit checkpoint_end must classify as CHECKPOINT; got {final}"
    )


# ---------------------------------------------------------------------------
# TC-06 — Heuristic positive match
# ---------------------------------------------------------------------------

def test_tc06_heuristic_positive_match():
    """TC-06: 18% drop, 20s duration, recovers to 92% within 40s.
    Classified checkpoint (fallback heuristic signal)."""
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)
    onset = t

    drop_draw = 10.0 * 0.82   # 18% below baseline — 8.2 MW
    clf.record_and_classify("j1", t, drop_draw)
    assert clf.state_of("j1") is CheckpointState.IN_VALLEY, (
        "18% drop must trigger IN_VALLEY"
    )

    # Hold 20 s (4 more ticks)
    for _ in range(4):
        t += TICK_S
        clf.record_and_classify("j1", t, drop_draw)

    # Recover to 92% — elapsed = 25s < 45s window
    t += TICK_S
    assert abs((t - onset) - 25.0) < 1e-9
    state = clf.record_and_classify("j1", t, 10.0 * 0.92)  # 9.2 MW
    assert state is CheckpointState.CHECKPOINT, (
        f"18% drop recovered to 92% within 25s should be CHECKPOINT; got {state}"
    )


# ---------------------------------------------------------------------------
# TC-07 — Heuristic negative match (job end)
# ---------------------------------------------------------------------------

def test_tc07_heuristic_negative_match_job_end():
    """TC-07: 15% drop, 30s duration, recovers to only 85% by 45s.
    Classified job_end.

    D3 — test honesty: TC-07 and TC-08 share the identical code path.
    Both enter IN_VALLEY on the same 15%-threshold drop, both transit to
    UNCERTAIN when elapsed > 45s without recovery, and both would reach
    JOB_END if observed long enough.  They differ only in when the test
    stops asserting:

      TC-08 asserts the UNCERTAIN hold *before* the 30s grace expires
            (60s total elapsed, ~10s into the grace period).
      TC-07 asserts the JOB_END terminal state *after* the grace expires
            (85s total elapsed, 35s into the grace period).

    §6.2 states two bullets — "ambiguous case → uncertain" and
    "no recovery → job_end" — that describe the same input state at
    different points in time.  This implementation reads the first bullet
    as a staging-hold behaviour (keep turbines staged during the grace
    period) and the second as the eventual classification (JOB_END once
    grace expires).  TC-07 and TC-08 each assert one half of that pair.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)
    onset = t

    drop_draw = 10.0 * 0.85   # exactly 15% below — boundary is inclusive
    clf.record_and_classify("j1", t, drop_draw)

    # Advance well past 45s window + 30s grace (> 80s) at the depressed level;
    # draw stays at 85%, never reaches the 90% recovery threshold.
    while (t - onset) < 85.0:
        t += TICK_S
        clf.record_and_classify("j1", t, drop_draw)

    assert clf.state_of("j1") is CheckpointState.JOB_END, (
        f"15% drop with no 90%+ recovery should reach JOB_END; "
        f"got {clf.state_of('j1')} at elapsed={t - onset:.0f}s"
    )


# ---------------------------------------------------------------------------
# TC-08 — Ambiguous case (uncertain)
# ---------------------------------------------------------------------------

def test_tc08_ambiguous_uncertain():
    """TC-08: 16% drop, no recovery and no job_end event by 45s.
    Status = uncertain; staging held for additional 30s grace period.

    D3 — test honesty: TC-07 and TC-08 share the identical code path.
    Both enter IN_VALLEY on the same 15%-threshold drop (TC-08 uses 16%,
    which is above the threshold in the same direction), both transit to
    UNCERTAIN when elapsed > 45s without a >=90% recovery, and both
    would reach JOB_END if the test continued past the 30s grace period.
    They differ only in when the test stops asserting:

      TC-08 asserts the UNCERTAIN hold *before* the 30s grace expires
            (60s total elapsed, ~10s into the grace period).
      TC-07 asserts the JOB_END terminal state *after* the grace expires
            (85s total elapsed, 35s into the grace period).

    §6.2 states two bullets — "ambiguous case → uncertain" and
    "no recovery → job_end" — that describe the same input state at
    different points in time.  This implementation reads the first bullet
    as a staging-hold behaviour (keep turbines staged during the grace
    period) and the second as the eventual classification (JOB_END once
    grace expires).  TC-08 asserts the hold; TC-07 asserts the terminal.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)

    drop_draw = 10.0 * 0.84   # 16% below baseline — 8.4 MW
    clf.record_and_classify("j1", t, drop_draw)

    # Advance 60s past the drop onset (> 45s window) without recovery
    for _ in range(12):   # 12 * 5s = 60s
        t += TICK_S
        clf.record_and_classify("j1", t, drop_draw)

    # §6.2: must be UNCERTAIN, not JOB_END — staging is held
    assert clf.state_of("j1") is CheckpointState.UNCERTAIN, (
        f"16% drop with no recovery past 45s must be UNCERTAIN; "
        f"got {clf.state_of('j1')}"
    )
    assert clf.state_of("j1") is not CheckpointState.JOB_END, (
        "JOB_END must not fire while the 30s grace period is still in force"
    )


# ---------------------------------------------------------------------------
# TC-09 — Boundary condition: thresholds are inclusive (≥/≤, not >/< )
# ---------------------------------------------------------------------------

def test_tc09_boundary_thresholds_inclusive():
    """TC-09: drop exactly 15.0%, duration exactly 30s, recovery exactly
    90.0% at exactly 45s → classified checkpoint.

    Verifies that DROP_THRESHOLD_FRACTION and RECOVERY_THRESHOLD_FRACTION
    are evaluated with ≤ and ≥ (inclusive), not strict < and > (exclusive).
    A strict-inequality implementation would classify this as IN_VALLEY
    (no drop triggered) or as UNCERTAIN (recovery missed), not CHECKPOINT.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)
    onset = t   # 300.0 with default _settle params

    # Drop exactly 15%: draw = 10.0 * (1 - 0.15) = 8.5.
    # Condition: 8.5 <= 10.0 * 0.85 = 8.5 → True (inclusive ≤).
    exact_drop = 10.0 * (1.0 - CheckpointClassifier.DROP_THRESHOLD_FRACTION)  # 8.5
    clf.record_and_classify("j1", t, exact_drop)
    assert clf.state_of("j1") is CheckpointState.IN_VALLEY, (
        "exact 15% drop must trigger IN_VALLEY (drop threshold is inclusive ≤)"
    )

    # Advance to exactly onset + 45s, holding at the depressed level on every
    # tick before the boundary tick.  TICK_S=5, so ticks at +5, +10, ..., +40
    # are in-valley; the boundary tick at +45 carries the recovery.
    t += TICK_S   # t = onset + 5
    while t < onset + CheckpointClassifier.RECOVERY_WINDOW_S:
        clf.record_and_classify("j1", t, exact_drop)
        t += TICK_S
    # t is now exactly onset + 45.0
    assert abs(t - (onset + CheckpointClassifier.RECOVERY_WINDOW_S)) < 1e-9, (
        f"expected t = onset + 45s; got elapsed = {t - onset:.3f}s"
    )

    # Recovery exactly 90%: draw = 10.0 * 0.90 = 9.0.
    # Condition: 9.0 / 10.0 = 0.90 ≥ 0.90 → True (inclusive ≥).
    # Also: elapsed = 45s ≤ 45s → True (inclusive ≤).
    exact_recovery = 10.0 * CheckpointClassifier.RECOVERY_THRESHOLD_FRACTION  # 9.0
    state = clf.record_and_classify("j1", t, exact_recovery)
    assert state is CheckpointState.CHECKPOINT, (
        f"exact 15% drop with exact 90% recovery at exact 45s must be CHECKPOINT "
        f"(all thresholds are inclusive); got {state}"
    )


# ---------------------------------------------------------------------------
# §12 effective-PUE identity — regression guard
# ---------------------------------------------------------------------------

def test_effective_pue_identity():
    """§12: at steady state with cooling settled, P_total / raw_IT_load
    must equal PUE_base × (1 + alpha_max).

    This is the cheapest available guard against the α/PUE double-count
    that v1.6 was written to eliminate reappearing — specifically under
    the Step 3 superposition change which rewrites how P_cooling is
    composed across concurrent jobs.

    Also present in audit_tests/test_step1b_findings.py; duplicated here
    so it runs as part of the normal CI suite (PYTHONPATH=. pytest tests/).
    """
    cooling = CoolingModule(asset_id="c1", site=_SITE)
    nodes, rated_kw = 100, 10.2
    raw_it_mw = nodes * rated_kw / 1000.0
    p_compute = raw_it_mw * _SITE.pue_base   # P_compute includes PUE_base

    t = 0.0
    while t < 600.0:   # >> dt_thermal + 5 * tau, so cooling is fully settled
        cooling.record_compute_sample(t, p_compute)
        cooling.advance(t, TICK_S)
        t += TICK_S

    effective_pue = (p_compute + cooling.output_mw()) / raw_it_mw
    expected = _SITE.pue_base * (1.0 + _SITE.alpha_max)

    assert math.isclose(effective_pue, expected, rel_tol=1e-6), (
        f"effective PUE {effective_pue:.8f} ≠ PUE_base × (1+α_max) = {expected:.8f} "
        "— an α/PUE double-count has been reintroduced"
    )


# ---------------------------------------------------------------------------
# D1 — explicit hold must suppress RECOVERY_WINDOW_S timeout
# ---------------------------------------------------------------------------

def test_d1_explicit_hold_survives_45s_timeout():
    """D1: checkpoint_start must suppress the RECOVERY_WINDOW_S timeout entirely.

    §6.2: the explicit scheduler event is the authoritative (primary) signal.
    A checkpoint write longer than 45s must stay IN_VALLEY until checkpoint_end
    arrives — the heuristic fallback timer must not override an authoritative
    scheduler event.

    Current defect: explicit_active is consumed after tick 1.  From tick 2 the
    IN_VALLEY branch's elapsed > RECOVERY_WINDOW_S check runs normally, and at
    tick 10 (50s elapsed) transitions to UNCERTAIN, overriding the scheduler.

    Fix required: a separate explicit_hold flag (set on checkpoint_start, cleared
    on checkpoint_end) that causes the IN_VALLEY branch to skip the timeout check.
    explicit_active (single-tick bypass of the re-entry drop-detection) does a
    different job and must be kept.

    This test fails today at tick 10 (50s elapsed).
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)

    clf.apply_explicit_event("j1", is_checkpoint_start=True, sim_time=t)

    # 24 ticks = 120s — well past the 45s heuristic window — at 80% draw
    for i in range(24):
        t += TICK_S
        state = clf.record_and_classify("j1", t, 8.0)
        assert state is CheckpointState.IN_VALLEY, (
            f"tick {i + 1} (elapsed={(i + 1) * TICK_S:.0f}s): explicit_hold must "
            f"suppress RECOVERY_WINDOW_S timeout; got {state}"
        )

    # checkpoint_end arrives after the long write
    clf.apply_explicit_event("j1", is_checkpoint_start=False, sim_time=t)
    t += TICK_S
    final = clf.record_and_classify("j1", t, 10.0)
    assert final is CheckpointState.CHECKPOINT, (
        f"explicit checkpoint_end must classify as CHECKPOINT; got {final}"
    )


# ---------------------------------------------------------------------------
# D2 — terminal guard bypass in apply_explicit_event
# ---------------------------------------------------------------------------

def test_d2_late_checkpoint_end_after_job_end_discarded():
    """D2: apply_explicit_event must honour the JOB_END terminal guard.

    §11.3's reordering buffer makes late or duplicate events expected in
    production.  A checkpoint_end arriving after JOB_END must be discarded —
    resurrecting a terminal job to CHECKPOINT is incorrect and would re-stage
    turbines for a job that has already ended.

    Current defect: apply_explicit_event writes hist.state directly with no
    JOB_END check, so the late checkpoint_end sets state=CHECKPOINT and the
    next record_and_classify returns CHECKPOINT instead of JOB_END.

    This test fails today because state becomes CHECKPOINT after the call.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)
    onset = t

    # Drive to JOB_END via the heuristic path
    drop_draw = 10.0 * 0.85   # 15% drop; stays below 90% throughout
    clf.record_and_classify("j1", t, drop_draw)
    while (t - onset) < 85.0:
        t += TICK_S
        clf.record_and_classify("j1", t, drop_draw)

    assert clf.state_of("j1") is CheckpointState.JOB_END, "setup failed: expected JOB_END"

    # Late / duplicate checkpoint_end arrives after the job is already terminal
    clf.apply_explicit_event("j1", is_checkpoint_start=False, sim_time=t)

    # apply_explicit_event must not override JOB_END
    assert clf.state_of("j1") is CheckpointState.JOB_END, (
        f"apply_explicit_event must discard late checkpoint_end when state is "
        f"JOB_END (terminal); got {clf.state_of('j1')}"
    )

    # record_and_classify on the next tick must also stay JOB_END
    t += TICK_S
    state = clf.record_and_classify("j1", t, 10.0)
    assert state is CheckpointState.JOB_END, (
        f"record_and_classify after discarded checkpoint_end must stay JOB_END; "
        f"got {state}"
    )


# ---------------------------------------------------------------------------
# D4 — explicit_hold must release after MAX_EXPLICIT_HOLD_S
# ---------------------------------------------------------------------------

def test_d4_explicit_hold_releases_after_max():
    """D4: explicit_hold must not hold IN_VALLEY indefinitely when checkpoint_end
    never arrives.

    §11.3's reordering buffer and §17.2's quarantine make a missing checkpoint_end
    an expected production condition.  §23.6 (curtailment): "a partitioned
    controller must not be able to hold a customer's fleet down indefinitely" —
    same failure class applied here to turbine ramp-down staging.

    Fix: MAX_EXPLICIT_HOLD_S (default 900.0 — CHOSEN value, no measured basis).
    When explicit_hold is True and elapsed > MAX_EXPLICIT_HOLD_S, clear the hold
    and let the heuristic resume.  The normal 45s/30s path then applies: since
    elapsed is already >> 45s, UNCERTAIN fires on the release tick, and JOB_END
    follows after UNCERTAIN_GRACE_PERIOD_S.

    The D1 test (checkpoint_end arriving before max hold) must still pass unchanged.

    This test fails today with AttributeError: MAX_EXPLICIT_HOLD_S not defined.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)
    onset = t

    clf.apply_explicit_event("j1", is_checkpoint_start=True, sim_time=t)

    # Advance past MAX_EXPLICIT_HOLD_S at 80% draw — no checkpoint_end ever arrives.
    # The hold must expire; the heuristic must resume.
    while (t - onset) <= CheckpointClassifier.MAX_EXPLICIT_HOLD_S:
        t += TICK_S
        clf.record_and_classify("j1", t, 8.0)
    # t - onset is now just over MAX_EXPLICIT_HOLD_S; hold should have released
    # and, since elapsed >> 45s, the IN_VALLEY → UNCERTAIN transition fires
    # on the same tick.

    assert clf.state_of("j1") is CheckpointState.UNCERTAIN, (
        f"after MAX_EXPLICIT_HOLD_S ({CheckpointClassifier.MAX_EXPLICIT_HOLD_S:.0f}s) "
        f"with no checkpoint_end, explicit_hold must release and heuristic must "
        f"resume to UNCERTAIN; got {clf.state_of('j1')}"
    )
    uncertain_entered_at = t   # sim_time at which UNCERTAIN was entered

    # Advance past the 30s grace period — must reach JOB_END on normal timings
    while (t - uncertain_entered_at) <= CheckpointClassifier.UNCERTAIN_GRACE_PERIOD_S:
        t += TICK_S
        clf.record_and_classify("j1", t, 8.0)

    assert clf.state_of("j1") is CheckpointState.JOB_END, (
        f"after UNCERTAIN grace period expires, must reach JOB_END; "
        f"got {clf.state_of('j1')}"
    )
