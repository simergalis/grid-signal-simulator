"""
tests/test_plane_separation.py — Step 4: Control-plane purity gate.

Two independent enforcement layers (Design Spec §4.3 / Build Plan v2.2 Step 4):

LAYER 1 — STATIC  (AST import scan, build-breaking in CI)
  Parses every core/*.py with the stdlib ast module.  Fails if any core
  module imports from runtime.* or from a forbidden I/O / async-transport
  package.  Covers ALL import nodes regardless of nesting depth, so a late
  `import asyncio` inside a function body is caught as reliably as one at
  module level.

  Wired into CI: this file is part of the pytest suite; pytest returns
  non-zero on any assertion failure.  Also callable standalone via
  scripts/check_plane_separation.py.

LAYER 2 — RUNTIME  (ContextVar sentinel)
  evaluate_tick() reads core._plane_guard._EVALUATE_TICK_PERMITTED at
  entry and raises RuntimeError when the sentinel is absent or False.
  The sentinel is SET BY THE CALLER: runtime/run_manager.py:RunContext.step()
  wraps each evaluate_tick() call in a set/reset pair.  evaluate_tick()
  itself never sets it — that would be self-signing and would defeat the
  purpose of the guard.

Both guards are demonstrated FAILING before they are demonstrated PASSING.
A guard nobody has seen fail is a guard nobody knows works.
"""

from __future__ import annotations

import contextlib
import pathlib
import textwrap

import pytest

# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------

CORE_DIR = pathlib.Path(__file__).parent.parent / "core"

# Re-use the scanner from the standalone script so the two are always in sync.
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from scripts.check_plane_separation import scan_source, check_all, FORBIDDEN_TOP_LEVEL  # noqa: E402


@contextlib.contextmanager
def _plane_guard_active():
    """Context manager for test code that calls evaluate_tick() directly.

    Sets _EVALUATE_TICK_PERMITTED for the duration of the with-block, then
    resets it — identical to what RunContext.step() does in production.
    Tests that go through RunContext.step() do NOT need this.
    """
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _minimal_sim_state():
    """A minimal but valid SimulationState for runtime-layer tests."""
    from runtime.scenario_factory import build_run_context
    ctx = build_run_context(
        "plane-sep-test", job_id="j0", node_count=1, end_sim_time=5.0
    )
    return ctx.sim_state, ctx


# ===========================================================================
# LAYER 1 — Static guard
# ===========================================================================

class TestStaticLayer:
    """AST import scanner (Layer 1).

    Each test either DEMONSTRATES THE GUARD FAILING (injecting a violation
    into synthetic source) or DEMONSTRATES THE GUARD PASSING (scanning the
    real core/ files).  Both demonstrations are required so the guard's
    behaviour is directly observable, not assumed.
    """

    # -----------------------------------------------------------------------
    # DEMONSTRATE FAILING — module-level I/O import
    # -----------------------------------------------------------------------

    def test_static_guard_catches_module_level_io_import(self):
        """DEMONSTRATE FAILING (Layer 1):

        Inject 'import httpx' at the top of core/dispatch.py source and
        verify the scanner reports a violation.

        This is the canonical injection from the build plan.  If this test
        fails to assert violations, the scanner is broken.
        """
        original = (CORE_DIR / "dispatch.py").read_text()
        poisoned = "import httpx\n" + original

        violations = scan_source("dispatch.py", poisoned)

        assert violations, (
            "SCANNER IS BROKEN: 'import httpx' injected into dispatch.py "
            "produced no violation.  The static guard must catch it."
        )
        assert any("httpx" in v for v in violations), (
            f"Expected an httpx violation; got: {violations}"
        )

    def test_static_guard_catches_runtime_import(self):
        """DEMONSTRATE FAILING (Layer 1):

        Inject 'from runtime import run_manager' into core/dispatch.py source.
        The guard must catch the cross-plane dependency.
        """
        original = (CORE_DIR / "dispatch.py").read_text()
        poisoned = "from runtime import run_manager\n" + original

        violations = scan_source("dispatch.py", poisoned)

        assert violations, (
            "SCANNER IS BROKEN: 'from runtime import run_manager' injected "
            "into dispatch.py produced no violation."
        )
        assert any("runtime" in v for v in violations), violations

    # -----------------------------------------------------------------------
    # DEMONSTRATE FAILING — late import inside a function body
    # -----------------------------------------------------------------------

    def test_static_guard_catches_late_import_inside_function(self):
        """DEMONSTRATE FAILING (Layer 1) — late import, inside a function body:

        A naive grep or module-level-only AST scan would MISS this case.
        This test proves the scanner uses ast.walk() over all nodes so a
        'import asyncio' buried inside evaluate_tick() is caught just as
        reliably as one at the top of the file.

        This is the second injection from the build plan ('Add a late import
        inside evaluate_tick()').  The static guard catches it here; the
        complementary runtime guard (Layer 2) catches unauthorised callers —
        the two layers cover orthogonal failure modes.
        """
        poisoned = textwrap.dedent("""
            # Synthetic snippet mimicking evaluate_tick with a late import.
            def evaluate_tick(state, sim_time, dt_seconds):
                import asyncio          # late import — inside function body
                import httpx            # a second late import
                return None
        """)

        violations = scan_source("synthetic_late_import.py", poisoned)

        assert violations, (
            "SCANNER IS BROKEN: late imports inside a function body were not "
            "caught.  The scanner must use ast.walk() over ALL AST nodes, "
            "not just top-level statements."
        )
        assert any("asyncio" in v for v in violations), (
            f"Expected asyncio violation from late import; got: {violations}"
        )
        assert any("httpx" in v for v in violations), (
            f"Expected httpx violation from late import; got: {violations}"
        )

    # -----------------------------------------------------------------------
    # DEMONSTRATE PASSING — real core/ files are clean
    # -----------------------------------------------------------------------

    def test_static_guard_clean_core_passes(self):
        """DEMONSTRATE PASSING (Layer 1):

        The real core/*.py files must be violation-free.  This is the
        CI-breaking check: if any core module develops a forbidden import
        this assertion fires and the build fails.
        """
        all_violations = check_all(CORE_DIR)

        assert not all_violations, (
            "core/ import violations found — build fails:\n"
            + "\n".join(f"  {v}" for v in all_violations)
        )

    def test_forbidden_set_covers_key_packages(self):
        """Sanity-check: the FORBIDDEN_TOP_LEVEL set contains the packages
        that matter most, so a reviewer can see the contract at a glance."""
        required = {"runtime", "asyncio", "httpx", "aiohttp", "requests",
                    "websockets", "fastapi"}
        missing = required - FORBIDDEN_TOP_LEVEL
        assert not missing, (
            f"FORBIDDEN_TOP_LEVEL is missing expected entries: {missing}"
        )


# ===========================================================================
# LAYER 2 — Runtime guard (ContextVar sentinel)
# ===========================================================================

class TestRuntimeLayer:
    """ContextVar sentinel (Layer 2).

    The sentinel is SET BY THE CALLER (runtime/run_manager.py:RunContext.step),
    not by evaluate_tick() itself.  Tests that call evaluate_tick() directly
    must use _plane_guard_active() or manage the token manually.
    """

    # -----------------------------------------------------------------------
    # DEMONSTRATE FAILING — bare call without the sentinel
    # -----------------------------------------------------------------------

    def test_runtime_guard_rejects_bare_call(self):
        """DEMONSTRATE FAILING (Layer 2):

        Call evaluate_tick() WITHOUT setting the ContextVar sentinel.
        The guard must raise RuntimeError, proving it fires when bypassed.

        This is the runtime-layer analogue of the static injection tests.
        A guard that is never seen to fail cannot be trusted to protect.
        """
        from core._plane_guard import _EVALUATE_TICK_PERMITTED
        from core.simulation_core import evaluate_tick

        state, _ctx = _minimal_sim_state()

        # Explicitly ensure the sentinel is absent in this context.
        token = _EVALUATE_TICK_PERMITTED.set(False)
        try:
            with pytest.raises(RuntimeError, match="runtime guard"):
                evaluate_tick(state, sim_time=0.0, dt_seconds=5.0)
        finally:
            _EVALUATE_TICK_PERMITTED.reset(token)

    # -----------------------------------------------------------------------
    # DEMONSTRATE PASSING — guarded direct call
    # -----------------------------------------------------------------------

    def test_runtime_guard_permits_guarded_direct_call(self):
        """DEMONSTRATE PASSING (Layer 2):

        evaluate_tick() succeeds when the sentinel is active — as it is
        when called via RunContext.step() in production.  This uses the
        _plane_guard_active() helper, which mirrors the set/reset logic
        in RunContext.step().
        """
        from core.simulation_core import evaluate_tick

        state, _ctx = _minimal_sim_state()

        with _plane_guard_active():
            result = evaluate_tick(state, sim_time=0.0, dt_seconds=5.0)

        assert result is not None
        assert result.tick_index == 1

    # -----------------------------------------------------------------------
    # DEMONSTRATE PASSING — via RunContext.step() (production path)
    # -----------------------------------------------------------------------

    def test_runtime_guard_passes_via_run_context_step(self):
        """DEMONSTRATE PASSING (Layer 2) via production path:

        RunContext.step() sets the sentinel, calls evaluate_tick(), and
        resets it.  This is the normal production call path — verifies the
        wiring in run_manager.py is correct and existing runs are unaffected
        by the guard.
        """
        _state, ctx = _minimal_sim_state()
        result = ctx.step()

        assert result is not None
        assert result.tick_index == 1

    # -----------------------------------------------------------------------
    # DEMONSTRATE: sentinel is reset AFTER step() returns
    # -----------------------------------------------------------------------

    def test_runtime_layer_sentinel_reset_after_step(self):
        """RunContext.step() must RESET the sentinel after evaluate_tick returns.

        A bare call immediately after step() must still fail — confirming
        the sentinel is scoped to the call, not leaked into the surrounding
        context.  This prevents a misbehaving caller from relying on a
        previously set token.
        """
        from core.simulation_core import evaluate_tick

        _state, ctx = _minimal_sim_state()
        ctx.step()  # sets sentinel, calls evaluate_tick, resets sentinel

        # Sentinel must now be False (default) again.
        with pytest.raises(RuntimeError, match="runtime guard"):
            evaluate_tick(ctx.sim_state, sim_time=5.0, dt_seconds=5.0)

    # -----------------------------------------------------------------------
    # DEMONSTRATE: sentinel is ContextVar-scoped (concurrency isolation)
    # -----------------------------------------------------------------------

    def test_runtime_layer_sentinel_is_context_scoped(self):
        """The ContextVar must be isolated per asyncio task / thread context.

        Set the sentinel True in a copy_context(), then verify the outer
        context still reads False.  This ensures concurrent runs cannot
        accidentally cross-contaminate each other's sentinel state — a
        critical property for the multi-run concurrency model (Design Spec
        §4.2).
        """
        import contextvars
        from core._plane_guard import _EVALUATE_TICK_PERMITTED

        # Outer context: sentinel is False.
        assert _EVALUATE_TICK_PERMITTED.get() is False

        inner_saw: list[bool] = []

        def _inner():
            token = _EVALUATE_TICK_PERMITTED.set(True)
            inner_saw.append(_EVALUATE_TICK_PERMITTED.get())
            _EVALUATE_TICK_PERMITTED.reset(token)

        ctx = contextvars.copy_context()
        ctx.run(_inner)

        # Outer context must still be False.
        assert _EVALUATE_TICK_PERMITTED.get() is False, (
            "ContextVar leaked into outer context — sentinel is not properly "
            "scoped to the inner context."
        )
        assert inner_saw == [True], (
            "Inner context did not see True — ContextVar not set correctly."
        )
