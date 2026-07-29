"""
Step 1b acceptance tests — the four defects found by the skeleton audit,
encoded as executable checks.

Every test in this file EXCEPT test_effective_pue_identity is expected to
FAIL against the unmodified skeleton. That is the point: Build Plan v2.1
Step 1b requires "a test that fails against the current code and passes
after," because "tests still pass" does not demonstrate a fixed bug.

Run from gridsignal_sim/:
    PYTHONPATH=.:../audit_tests python -m pytest ../audit_tests/test_step1b_findings.py -v

Expected on the unmodified skeleton:  4 failed, 1 passed
Expected after Step 1b:               5 passed
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from core.asset_modules import CoolingModule
from core.dispatch import CheckpointClassifier, CheckpointState
from core.models import SiteConfig

SITE = SiteConfig(site_id="s1", pue_base=1.03, alpha_max=0.20,
                  tau_seconds=20.0, dt_thermal_seconds=90.0)


def _settle(clf: CheckpointClassifier, job: str, draw: float,
            n: int = 60, step: float = 5.0, t0: float = 0.0) -> float:
    """Establish a trailing median for `job` at `draw` MW."""
    t = t0
    for _ in range(n):
        clf.record_and_classify(job, t, draw)
        t += step
    return t


# ---------------------------------------------------------------------------
# B-1 — apply_explicit_event() crashes the next tick
# ---------------------------------------------------------------------------

def test_explicit_checkpoint_event_does_not_crash():
    """v2.5 §6.2: an explicit checkpoint_start/checkpoint_end pair is the
    AUTHORITATIVE signal and no heuristic is needed when present.

    Skeleton defect: apply_explicit_event() sets IN_VALLEY but leaves
    drop_onset_time and pre_drop_draw_mw as None, so the next tick trips
    the assertion at the top of the IN_VALLEY branch.

    Note the assert is stripped under `python -O`, which would convert this
    crash into silent None arithmetic on a control path. The fix must use a
    real guard, not an assert.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0, n=20)

    clf.apply_explicit_event("j1", is_checkpoint_start=True, sim_time=t)

    t += 5.0
    state = clf.record_and_classify("j1", t, 8.0)  # raises AssertionError today

    assert state in (CheckpointState.IN_VALLEY, CheckpointState.CHECKPOINT), (
        "an explicit checkpoint_start must leave the job in a checkpoint-ish "
        f"state, got {state}"
    )

    clf.apply_explicit_event("j1", is_checkpoint_start=False, sim_time=t)
    t += 5.0
    assert clf.record_and_classify("j1", t, 10.0) is CheckpointState.CHECKPOINT


# ---------------------------------------------------------------------------
# B-2 — UNCERTAIN is unreachable dead code
# ---------------------------------------------------------------------------

def test_uncertain_state_is_reachable():
    """v2.5 §6.2 / TC-08: a drop that neither recovers to >=90% nor carries a
    scheduler job_end event within 45 s is classified `uncertain`; staging is
    held for a further 30 s grace period and the job is flagged.

    Skeleton defect: the branch assigns JOB_END, then tests
    `elif recovered_fraction < 0.90` — reachable only when recovery SUCCEEDED.
    Contradiction, so UNCERTAIN is never assigned and the grace-period block
    below it is dead code.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)

    clf.record_and_classify("j1", t, 8.4)          # 16% drop -> IN_VALLEY
    for _ in range(12):                            # hold low, past 45 s, no recovery
        t += 5.0
        clf.record_and_classify("j1", t, 8.4)

    assert clf.state_of("j1") is CheckpointState.UNCERTAIN, (
        "45 s expiry with no recovery and no scheduler job_end must classify "
        f"`uncertain`, got {clf.state_of('j1')}"
    )


def test_uncertain_grace_period_then_job_end():
    """After the 30 s grace period expires with still no recovery, §6.2 allows
    the classification to settle to job_end."""
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)
    clf.record_and_classify("j1", t, 8.4)
    for _ in range(12):
        t += 5.0
        clf.record_and_classify("j1", t, 8.4)
    assert clf.state_of("j1") is CheckpointState.UNCERTAIN

    for _ in range(8):                             # push past the 30 s grace period
        t += 5.0
        clf.record_and_classify("j1", t, 8.4)
    assert clf.state_of("j1") is CheckpointState.JOB_END


# ---------------------------------------------------------------------------
# B-3 — JOB_END is not terminal; classification oscillates
# ---------------------------------------------------------------------------

def test_job_end_is_terminal():
    """v2.5 §6.2 exists to stop a controller prematurely ramping turbines down
    mid-job. A classification that oscillates between job_end and in_valley on
    alternating ticks — with no change in input — would start and abort
    ramp-down repeatedly.

    Skeleton defect: JOB_END sits in the re-entry branch alongside NORMAL and
    CHECKPOINT, so a classified job re-enters drop detection against a trailing
    median now depressed by its own post-drop samples.
    """
    clf = CheckpointClassifier()
    t = _settle(clf, "j1", 10.0)
    clf.record_and_classify("j1", t, 8.4)

    seen: list[CheckpointState] = []
    for _ in range(30):
        t += 5.0
        seen.append(clf.record_and_classify("j1", t, 8.4))

    if CheckpointState.JOB_END in seen:
        first = seen.index(CheckpointState.JOB_END)
        after = set(seen[first:])
        assert after == {CheckpointState.JOB_END}, (
            "JOB_END must be terminal for a job_id; observed transitions after "
            f"first JOB_END: {[s.value for s in seen[first:]]}"
        )


# ---------------------------------------------------------------------------
# B-5 — core/ must not import from runtime/
# ---------------------------------------------------------------------------

def test_core_does_not_import_runtime():
    """Design Spec §2 principle 2 / §4.3, and v2.5 §21.1: core/ is the
    deterministic control plane. It must not depend on the concurrency layer.

    Skeleton defect: core/scenario_factory.py:30 imports from
    runtime.run_manager. This single edge would fail Build Plan v2.1 Step 4's
    purity gate on day one.
    """
    core_dir = Path(__file__).resolve().parents[1] / "gridsignal_sim" / "core"
    offenders: list[str] = []

    for path in sorted(core_dir.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("runtime"):
                offenders.append(f"{path.name}:{node.lineno} -> from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("runtime"):
                        offenders.append(f"{path.name}:{node.lineno} -> import {alias.name}")

    assert not offenders, "core/ imports from runtime/:\n  " + "\n  ".join(offenders)


# ---------------------------------------------------------------------------
# §12 — effective PUE identity. THIS ONE PASSES TODAY. Keep it that way.
# ---------------------------------------------------------------------------

def test_effective_pue_identity():
    """v2.5 §12: a site's fully-loaded effective PUE at steady state is
    PUE_base x (1 + alpha).

    This currently holds to ~2e-12 and nothing in the suite asserts it. It is
    the cheapest available guard against the alpha/PUE double-count that v1.6
    was written to eliminate reappearing — in particular under the Step 3
    superposition change, which rewrites how P_cooling is composed.

    Expected: PASSES on the unmodified skeleton, and must keep passing.
    """
    cooling = CoolingModule(asset_id="c1", site=SITE)
    nodes, rated_kw = 100, 10.2
    raw_it_mw = nodes * rated_kw / 1000.0
    p_compute = raw_it_mw * SITE.pue_base

    t = 0.0
    while t < 600.0:                                # >> dt_thermal + 5*tau
        cooling.record_compute_sample(t, p_compute)
        cooling.advance(t, 5.0)
        t += 5.0

    effective_pue = (p_compute + cooling.output_mw()) / raw_it_mw
    expected = SITE.pue_base * (1 + SITE.alpha_max)

    assert math.isclose(effective_pue, expected, rel_tol=1e-6), (
        f"effective PUE {effective_pue:.6f} != PUE_base x (1+alpha) {expected:.6f} "
        "— an alpha/PUE double-count has been reintroduced"
    )
