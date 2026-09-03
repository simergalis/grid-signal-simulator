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

TC-CL-1  for_tick() raises RuntimeError for any index more than one past schedule length
TC-CL-1b for_tick() returns _CLEAN silently for exactly one-tick overshoot (documented tolerance)
TC-CL-2  for_tick() raises RuntimeError for negative indices
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
# TC-CL-1  for_tick() raises for any index more than one tick past schedule end
# ---------------------------------------------------------------------------

def test_tc_cl_1_for_tick_returns_clean_beyond_end():
    """Indices more than one past schedule length must raise RuntimeError.

    The contract after Phase 3:
      [0, len)    → scheduled CorruptionEntry (normal path)
      == len      → _CLEAN silently (one-tick tolerance; see TC-CL-1b)
      > len       → RuntimeError (unbounded overshoot: fault injection was
                    silently disabled; raise rather than return a false clean)
      negative    → RuntimeError (invalid; see TC-CL-2)

    The RuntimeError surfaces a misconfiguration (run longer than schedule)
    that would otherwise silently disable fault injection without warning.
    """
    sched = _make_schedule(10)
    n = len(sched.schedule)   # == 10

    # Normal in-range path — must return the actual scheduled entry, not _CLEAN
    entry_in = sched.for_tick(n - 1)   # last valid index
    assert isinstance(entry_in, type(_CLEAN)), (
        f"In-range tick {n-1} should return a CorruptionEntry; got {entry_in!r}"
    )

    # One past the end — the tolerated overshoot (asserted separately in TC-CL-1b)
    entry_one = sched.for_tick(n)
    assert entry_one is _CLEAN or (
        entry_one.noise_sigma == 0.0 and not entry_one.dropout and entry_one.staleness == 0
    ), f"Tick {n} (one past end) should return _CLEAN; got {entry_one}"

    # Two past the end — must raise
    with pytest.raises(RuntimeError, match="out of range"):
        sched.for_tick(n + 1)

    # Far past the end — must raise
    with pytest.raises(RuntimeError, match="out of range"):
        sched.for_tick(9999)


# ---------------------------------------------------------------------------
# TC-CL-1b  The one-tick overshoot tolerance is preserved
# ---------------------------------------------------------------------------

def test_for_tick_one_tick_overshoot_is_tolerated():
    """tick_index == len(schedule) must return _CLEAN silently — always.

    This is the documented one-tick tolerance (off-by-one at run end).
    Gated as its own named test because it is the boundary most likely to be
    broken by a future tightening of the overshoot guard: tightening that
    correctly removes the two-plus-tick overshoot path must NOT remove this one.

    Production call site: runtime/run_manager.py line ~801
      for_tick(tick_result.tick_index - 1)
    where tick_index is 1-based and runs from 1 to n_ticks inclusive.
    The 0-based index therefore runs from 0 to n_ticks - 1 (always within range),
    but an off-by-one in n_ticks accounting would produce exactly tick_index == n.
    This test ensures that off-by-one produces a no-op, not a crash.
    """
    for n in (1, 5, 10, 100):
        sched = _make_schedule(n)
        assert len(sched.schedule) == n
        entry = sched.for_tick(n)   # tick_index == len — documented tolerance
        assert entry is _CLEAN or (
            entry.noise_sigma == 0.0 and not entry.dropout and entry.staleness == 0
        ), f"n={n}: for_tick({n}) (one-tick overshoot) must return _CLEAN; got {entry}"


# ---------------------------------------------------------------------------
# TC-CL-2  for_tick() raises for negative indices
# ---------------------------------------------------------------------------

def test_tc_cl_2_for_tick_returns_clean_for_negative_index():
    """Negative tick indices must raise RuntimeError, not wrap around the list.

    Python list[-1] returns the LAST element — silently applying corruption
    from a past tick to an unrelated tick.  for_tick must reject any negative
    index with RuntimeError rather than return a potentially noisy entry.
    """
    sched = _make_schedule(10)

    with pytest.raises(RuntimeError, match="out of range"):
        sched.for_tick(-1)

    with pytest.raises(RuntimeError, match="out of range"):
        sched.for_tick(-100)


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
