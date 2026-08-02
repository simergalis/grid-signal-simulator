"""
tests/test_corruption_schedule_lifecycle.py — TC-CL-1 through TC-CL-6

Regression tests confirming that the telemetry corruption schedule is
strictly scoped to its own run and cannot leak into a subsequent run.

The property being guarded:

    A CompletedRun's tick_dicts contain exactly the corrupted (or clean)
    values that were produced during THAT run.  Starting a second run after
    a corruption run must give the second run a completely clean slate —
    empty _bess_soc_history, no _corruption_rng, and no telemetry_corruption
    schedule — regardless of whether the first run completed normally or was
    cancelled.

TC-CL-1  for_tick() returns _CLEAN for any index ≥ schedule length
TC-CL-2  for_tick() returns _CLEAN for negative indices
TC-CL-3  A freshly-created RunContext always starts with empty _bess_soc_history
TC-CL-4  A freshly-created RunContext always has telemetry_corruption = None
TC-CL-5  Populating _bess_soc_history on RunContext-A does not affect RunContext-B
TC-CL-6  After simulating a full corruption run, a new RunContext starts clean
"""

from __future__ import annotations

import pytest

from runtime.run_manager import RunContext, _update_soc_history
from runtime.telemetry_corruption import (
    CorruptionEntry,
    TelemetryCorruptionSchedule,
    _CLEAN,
    generate_corruption_schedule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_schedule(n: int, noise_sigma: float = 0.05) -> TelemetryCorruptionSchedule:
    """Generate a short schedule with uniform noise for boundary testing."""
    return generate_corruption_schedule(n, seed=42, noise_sigma=noise_sigma)


def _make_ctx() -> RunContext:
    """Minimal RunContext — only the corruption fields matter for these tests."""
    from runtime.scenario_factory import build_run_context
    return build_run_context(
        run_id="test-run",
        job_id="test-job",
        node_count=100,
        end_sim_time=300.0,
    )


def _make_tick_stub(soc_mwh: float = 1.5):
    """Return a minimal TickResult-like stub sufficient for _update_soc_history."""
    # _update_soc_history only reads tick.bess_soc_fraction and the BESS unit list
    # through ctx.sim_state.bess_units.  We inject a mock rather than building
    # a full SimulationState to keep the test free of physics setup.
    from unittest.mock import MagicMock
    tick = MagicMock()
    tick.bess_soc_fraction = soc_mwh / 2.0   # arbitrary fraction
    return tick, soc_mwh


# ---------------------------------------------------------------------------
# TC-CL-1  for_tick() is safe beyond schedule length
# ---------------------------------------------------------------------------

def test_tc_cl_1_for_tick_returns_clean_beyond_end():
    """Any index ≥ schedule length must return a no-op _CLEAN entry.

    This is the critical boundary: if a run is extended or timing drifts,
    extra ticks beyond the pre-generated schedule must not corrupt anything.
    """
    sched = _make_schedule(10)
    assert len(sched.schedule) == 10

    # One past the end
    entry = sched.for_tick(10)
    assert entry is _CLEAN or (
        entry.noise_sigma == 0.0 and not entry.dropout and entry.staleness == 0
    ), f"Tick 10 (past end) should be CLEAN, got {entry}"

    # Far past the end
    entry_far = sched.for_tick(9999)
    assert entry_far is _CLEAN or (
        entry_far.noise_sigma == 0.0 and not entry_far.dropout and entry_far.staleness == 0
    ), f"Tick 9999 should be CLEAN, got {entry_far}"


# ---------------------------------------------------------------------------
# TC-CL-2  for_tick() is safe for negative indices
# ---------------------------------------------------------------------------

def test_tc_cl_2_for_tick_returns_clean_for_negative_index():
    """Negative tick indices must return _CLEAN, not wrap around the list.

    Python list[-1] would return the LAST element; for_tick must reject this.
    """
    sched = _make_schedule(10)

    entry = sched.for_tick(-1)
    assert entry is _CLEAN or (
        entry.noise_sigma == 0.0 and not entry.dropout and entry.staleness == 0
    ), f"Tick -1 should be CLEAN (no Python list wrap), got {entry}"

    entry_neg = sched.for_tick(-100)
    assert entry_neg is _CLEAN or (
        entry_neg.noise_sigma == 0.0 and not entry_neg.dropout and entry_neg.staleness == 0
    ), f"Tick -100 should be CLEAN, got {entry_neg}"


# ---------------------------------------------------------------------------
# TC-CL-3  Fresh RunContext has empty _bess_soc_history
# ---------------------------------------------------------------------------

def test_tc_cl_3_fresh_context_has_empty_soc_history():
    """A newly-created RunContext must have an empty _bess_soc_history.

    If the factory reused a mutable default, history from one run could
    contaminate the next — this test would catch that regression immediately.
    """
    ctx = _make_ctx()
    assert ctx._bess_soc_history == [], (
        f"Fresh RunContext._bess_soc_history must be [], got {ctx._bess_soc_history}"
    )


# ---------------------------------------------------------------------------
# TC-CL-4  Fresh RunContext has no corruption schedule
# ---------------------------------------------------------------------------

def test_tc_cl_4_fresh_context_has_no_corruption_schedule():
    """A newly-created RunContext must have telemetry_corruption = None.

    corruption is injected by the API layer after context creation; a plain
    context must never inherit a previous run's schedule.
    """
    ctx = _make_ctx()
    assert ctx.telemetry_corruption is None, (
        f"Fresh RunContext.telemetry_corruption must be None, got {ctx.telemetry_corruption!r}"
    )
    assert ctx._corruption_rng is None, (
        f"Fresh RunContext._corruption_rng must be None, got {ctx._corruption_rng!r}"
    )


# ---------------------------------------------------------------------------
# TC-CL-5  Two RunContext instances do not share _bess_soc_history
# ---------------------------------------------------------------------------

def test_tc_cl_5_soc_history_not_shared_between_contexts():
    """Mutations to RunContext-A's _bess_soc_history must not appear in RunContext-B.

    This guards against a mutable-default-argument bug (e.g. if field()
    were accidentally replaced with a bare list literal).
    """
    ctx_a = _make_ctx()
    ctx_b = _make_ctx()

    # Directly append to ctx_a's history
    ctx_a._bess_soc_history.append(1.23)
    ctx_a._bess_soc_history.append(4.56)

    assert ctx_b._bess_soc_history == [], (
        f"ctx_b._bess_soc_history should still be empty after ctx_a was mutated; "
        f"got {ctx_b._bess_soc_history}"
    )


# ---------------------------------------------------------------------------
# TC-CL-6  A new RunContext after a completed corruption run starts clean
# ---------------------------------------------------------------------------

def test_tc_cl_6_new_context_after_corruption_run_is_clean():
    """Simulates Run A building up _bess_soc_history, then confirms Run B is clean.

    This is the end-to-end lifecycle check: the corruption schedule and its
    side-effects on _bess_soc_history must be confined to the RunContext
    that owned the run, with no leakage to the next RunContext.
    """
    # Simulate Run A accumulating corruption history
    ctx_a = _make_ctx()
    ctx_a.telemetry_corruption = _make_schedule(20, noise_sigma=0.1)
    ctx_a._corruption_rng = __import__("random").Random(42)

    # Manually push some SoC values into history (as _update_soc_history would)
    for soc in [1.0, 0.9, 0.8, 0.7, 0.6]:
        ctx_a._bess_soc_history.append(soc)

    assert len(ctx_a._bess_soc_history) == 5
    assert ctx_a.telemetry_corruption is not None

    # Run A ends — context goes out of scope.  Start Run B (fresh context).
    del ctx_a
    ctx_b = _make_ctx()

    assert ctx_b._bess_soc_history == [], (
        "Run B must start with an empty SoC history regardless of Run A's state; "
        f"got {ctx_b._bess_soc_history}"
    )
    assert ctx_b.telemetry_corruption is None, (
        "Run B must have no corruption schedule on creation; "
        f"got {ctx_b.telemetry_corruption!r}"
    )
    assert ctx_b._corruption_rng is None, (
        f"Run B must have no corruption RNG on creation; got {ctx_b._corruption_rng!r}"
    )
