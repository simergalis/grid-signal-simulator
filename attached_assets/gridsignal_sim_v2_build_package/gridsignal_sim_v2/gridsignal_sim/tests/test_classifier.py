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
    Eventually classified job_end after uncertain grace period expires
    (UNCERTAIN at 45s + JOB_END after 30s grace = 75s+ from onset).
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
    Status = uncertain; staging held for additional 30s grace period;
    dashboard flag set.
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
