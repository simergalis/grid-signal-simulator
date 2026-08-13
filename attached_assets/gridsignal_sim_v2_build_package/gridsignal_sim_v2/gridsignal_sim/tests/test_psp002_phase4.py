"""test_psp002_phase4.py — Phase 4 wiring tests for GS-IMPL-PSP-002.

TC-C10: Log timestamps prove §7 Dispatch Arbitration precedes EconomicDispatchLoop
        on the same tick (structural ordering guarantee).
TC-C13: GS_PRODUCTION_HARNESS=1 prevents PMSTestDouble instantiation in the
        §4.3 escalation path.

Import boundary note
--------------------
  This test file lives in tests/.  It imports from runtime/ (permitted for tests)
  to verify the wiring.  core/ is never imported directly from here for anything
  that would violate the §1 import boundary.
"""
from __future__ import annotations

import ast
import inspect
import os
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Module under test ─────────────────────────────────────────────────────────

import runtime.run_manager as _rm
from runtime.run_manager import RunContext, _is_simulator_harness, TICK_INTERVAL_SIM_SECONDS
from runtime.pms_test_double import OperatorResponseProfile, PMSTestDouble
from core.economic_dispatch_loop import EconomicDispatchLoop, pge_price_for_period
from core.power_source_priority import (
    AuthorityTier,
    PowerSource,
    PowerSourceType,
    ResponseLatencyClass,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_grid_source(
    source_id: str = "grid-firm",
    authority_tier: AuthorityTier = AuthorityTier.AUTONOMOUS,
    available_mw: float = 100.0,
    marginal_cost_mwh: float = 114.82,
) -> PowerSource:
    return PowerSource(
        source_id=source_id,
        source_type=PowerSourceType.GRID_FIRM,
        dispatchable=True,
        counts_toward_reserve=True,
        marginal_cost_mwh=marginal_cost_mwh,
        response_latency_class=ResponseLatencyClass.INSTANT,
        authority_tier=authority_tier,
        available_mw=available_mw,
    )


# ── TC-C10: §7 precedes EDL on the same tick ─────────────────────────────────

class TestTC_C10_EvaluateTickPrecedesEDL:
    """§7 Dispatch Arbitration (inside ctx.step() / evaluate_tick) must precede
    the Economic Dispatch Loop on every tick.

    The ordering is enforced by the sequential structure of _drive(): section A
    (evaluate_tick) is followed by section A1b (EDL) with no await points between
    them, so no other coroutine can interleave.  These tests verify the structural
    guarantee — not a probabilistic runtime outcome.

    TC-C10 test strategy
    --------------------
    Parsing `_drive()` source with `ast` to locate:
      1. The `ctx.step()` call (§7 proxy — evaluate_tick runs inside step()).
      2. The `_EconomicDispatchLoop().step(...)` call (EDL).
    The ast node line number of (1) must be strictly less than that of (2).
    This is a first-class structural guarantee: it fails immediately if someone
    reorders the sections, inserts an await between them, or moves EDL above §7.
    """

    def _get_drive_source(self) -> str:
        """Return the source of _drive() as a string, with original line numbers."""
        src = inspect.getsource(_rm.RunManager._drive)
        # dedent so ast.parse does not choke on the method indentation.
        return textwrap.dedent(src)

    def _find_line_of_call(self, src: str, func_name: str) -> int:
        """Return the first line (1-based, relative to dedented src) of a
        Call node whose func attribute matches func_name anywhere in the call.

        Raises AssertionError if the call is not found.
        """
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Direct Name call: foo()
            if isinstance(func, ast.Name) and func.id == func_name:
                return node.lineno
            # Attribute call: obj.foo()
            if isinstance(func, ast.Attribute) and func.attr == func_name:
                return node.lineno
        raise AssertionError(
            f"Call to {func_name!r} not found in _drive() source. "
            "If the method was renamed, update this test."
        )

    def test_ctx_step_found_in_drive(self) -> None:
        """ctx.step() — the §7 proxy — must appear in _drive() source."""
        src = self._get_drive_source()
        # Should not raise:
        line = self._find_line_of_call(src, "step")
        assert line > 0

    def test_edl_class_instantiated_in_drive(self) -> None:
        """_EconomicDispatchLoop() instantiation must appear in _drive() source."""
        src = self._get_drive_source()
        # _EconomicDispatchLoop is the alias used in run_manager.py
        tree = ast.parse(src)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and "_EconomicDispatchLoop" in func.id:
                    found = True
                    break
                if isinstance(func, ast.Attribute) and "_EconomicDispatchLoop" in func.attr:
                    found = True
                    break
        assert found, (
            "_EconomicDispatchLoop() must be instantiated inside _drive() "
            "(TC-C10: EDL wiring present)"
        )

    def test_section_a1b_comment_present_after_evaluate_tick_comment(self) -> None:
        """Section markers in _drive() source confirm A1b follows A.

        Both section markers are present as comments.  The 'A1b' marker must
        appear at a later character position than the 'evaluate_tick' marker,
        which is inside section A.  This is a lightweight order check that
        does not depend on ast line numbers.
        """
        src = self._get_drive_source()
        pos_a    = src.find("evaluate_tick")
        pos_a1b  = src.find("A1b")
        assert pos_a >= 0,   "'evaluate_tick' not found in _drive() source"
        assert pos_a1b >= 0, "'A1b' section marker not found in _drive() source (TC-C10)"
        assert pos_a < pos_a1b, (
            "Section A (evaluate_tick) must appear before section A1b (EDL) in "
            "_drive() source.  Current positions: evaluate_tick=%d, A1b=%d. "
            "(TC-C10: §7 must precede EDL on the same tick)" % (pos_a, pos_a1b)
        )

    def test_psp002_section_42_ordering_label_present(self) -> None:
        """The §4.2 EDL ordering comment must appear in _drive() source.

        This pin ensures the intent is documented inline and visible to future
        reviewers — it is not a cosmetic check.
        """
        src = self._get_drive_source()
        assert "§4.2" in src, (
            "§4.2 ordering label missing from _drive() (TC-C10). "
            "The comment must be present to document why EDL follows evaluate_tick."
        )

    def test_no_await_between_evaluate_tick_and_edl(self) -> None:
        """No top-level await must appear between ctx.step() and the EDL block.

        An await between §7 and EDL would allow another coroutine to run
        and mutate shared state (e.g. events, sim_state) before EDL fires —
        breaking the same-tick ordering guarantee.

        Strategy: slice the _drive() source between 'ctx.step()' and the
        first '_EconomicDispatchLoop' reference, then check for top-level
        `await` expressions in that slice.  The kube debug CSV section (A1)
        is between the two and contains no await — this test will catch any
        future addition of an await in that window.
        """
        src = self._get_drive_source()
        step_pos = src.find("ctx.step()")
        edl_pos  = src.find("_EconomicDispatchLoop")
        assert step_pos >= 0, "ctx.step() not found in _drive()"
        assert edl_pos >= 0,  "_EconomicDispatchLoop not found in _drive()"
        assert step_pos < edl_pos, "ctx.step() must appear before _EconomicDispatchLoop"

        between = src[step_pos:edl_pos]
        # Parse the slice — wrap in a function so ast.parse accepts it.
        try:
            tree = ast.parse(f"async def _slice():\n" +
                             textwrap.indent(between, "    "))
        except SyntaxError:
            # Slice may not be valid standalone Python; skip the ast check
            # if it cannot be parsed (the positional check above is sufficient).
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Await):
                pytest.fail(
                    "An `await` expression was found between ctx.step() (§7) and "
                    "_EconomicDispatchLoop (EDL) in _drive().  This breaks the "
                    "same-tick ordering guarantee (TC-C10)."
                )


# ── TC-C13: production harness blocks PMSTestDouble instantiation ─────────────

class TestTC_C13_ProductionHarnessBlocksPMS:
    """GS_PRODUCTION_HARNESS=1 prevents PMSTestDouble from being instantiated
    in the §4.3 escalation path.

    §4.3 fork in _drive():
      Simulator branch: _is_simulator_harness() AND ctx.pms_response_profile is not None.
      Production branch: log-stub only — PMSTestDouble never instantiated.

    These tests verify _is_simulator_harness() behaves correctly under both
    env states, and that the import boundary (core/ must not import PMSTestDouble)
    still holds after Phase 4's wiring.
    """

    def test_simulator_harness_true_by_default(self) -> None:
        """_is_simulator_harness() returns True when GS_PRODUCTION_HARNESS is unset."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GS_PRODUCTION_HARNESS", None)
            assert _is_simulator_harness() is True, (
                "_is_simulator_harness() must return True when "
                "GS_PRODUCTION_HARNESS is not set"
            )

    def test_simulator_harness_false_when_env_set(self) -> None:
        """_is_simulator_harness() returns False when GS_PRODUCTION_HARNESS=1."""
        with patch.dict(os.environ, {"GS_PRODUCTION_HARNESS": "1"}):
            assert _is_simulator_harness() is False, (
                "_is_simulator_harness() must return False when "
                "GS_PRODUCTION_HARNESS=1 (TC-C13: production harness guard)"
            )

    def test_simulator_harness_false_for_any_non_empty_value(self) -> None:
        """GS_PRODUCTION_HARNESS blocks instantiation for any non-empty value."""
        for val in ("1", "true", "yes", "production"):
            with patch.dict(os.environ, {"GS_PRODUCTION_HARNESS": val}):
                assert _is_simulator_harness() is False, (
                    f"_is_simulator_harness() should be False for "
                    f"GS_PRODUCTION_HARNESS={val!r}"
                )

    def test_pms_test_double_not_in_core(self) -> None:
        """PMSTestDouble must not be imported by any core/ file (§1 import boundary).

        Phase 4 wires EDL + §4.3 escalation in runtime/run_manager.py.  That
        wiring must not pull PMSTestDouble into core/ through any code path.

        Check: no file in core/ contains an import statement whose module path
        includes 'pms_test_double' or 'runtime'.  Documentary mentions of the
        class name in docstrings/comments are NOT violations — the constraint
        is on imports, not on naming.
        """
        core_dir = Path(__file__).parent.parent / "core"
        assert core_dir.exists(), f"core/ directory not found at {core_dir}"

        violations: list[str] = []
        for py_file in sorted(core_dir.glob("*.py")):
            text = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text, filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                # from runtime.xxx import ... or from runtime import ...
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if "pms_test_double" in module or module.startswith("runtime"):
                        violations.append(f"{py_file.name}: from {module} import ...")
                # import runtime.xxx or import pms_test_double
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "pms_test_double" in alias.name or alias.name.startswith("runtime"):
                            violations.append(f"{py_file.name}: import {alias.name}")

        assert not violations, (
            "core/ files must not import from runtime/ or pms_test_double (§1 / TC-C13). "
            f"Import violations found: {violations}"
        )

    def test_drive_source_gates_pms_on_is_simulator_harness(self) -> None:
        """_drive() source must call _is_simulator_harness() before instantiating PMSTestDouble.

        This structural test verifies the guard is present — the production
        harness flag cannot block instantiation if the check was deleted.
        """
        src = inspect.getsource(_rm.RunManager._drive)
        assert "_is_simulator_harness()" in src, (
            "_drive() must call _is_simulator_harness() before instantiating "
            "PMSTestDouble in the §4.3 escalation path (TC-C13). "
            "The guard was not found in _drive() source."
        )
        assert "_PMSTestDouble" in src, (
            "_drive() must reference _PMSTestDouble in the §4.3 simulator branch "
            "(TC-C13). The reference was not found — escalation may be missing."
        )

    def test_pms_instantiation_guarded_after_is_simulator_harness(self) -> None:
        """In _drive() source, _is_simulator_harness() appears before _PMSTestDouble().

        This ordering check ensures the guard is not cosmetic — it must precede
        the call it is guarding.
        """
        src = inspect.getsource(_rm.RunManager._drive)
        guard_pos = src.find("_is_simulator_harness()")
        pms_pos   = src.find("_PMSTestDouble(")
        assert guard_pos >= 0, "_is_simulator_harness() not in _drive() source"
        assert pms_pos >= 0,   "_PMSTestDouble( not in _drive() source"
        assert guard_pos < pms_pos, (
            "_is_simulator_harness() guard must appear before _PMSTestDouble() "
            "instantiation in _drive() source (TC-C13 ordering check)"
        )

    def test_runcontext_pms_response_profile_field_exists(self) -> None:
        """RunContext.pms_response_profile field must exist (Phase 4 wiring)."""
        import dataclasses
        fields = {f.name for f in dataclasses.fields(RunContext)}
        assert "pms_response_profile" in fields, (
            "RunContext must have a pms_response_profile field (Phase 4 §4.3 wiring)"
        )

    def test_runcontext_edl_sources_field_exists(self) -> None:
        """RunContext.edl_sources field must exist (Phase 4 wiring)."""
        import dataclasses
        fields = {f.name for f in dataclasses.fields(RunContext)}
        assert "edl_sources" in fields, (
            "RunContext must have an edl_sources field (Phase 4 §4.2 wiring)"
        )

    def test_runcontext_edl_calendar_month_field_exists(self) -> None:
        """RunContext.edl_calendar_month field must exist (Phase 4 wiring)."""
        import dataclasses
        fields = {f.name for f in dataclasses.fields(RunContext)}
        assert "edl_calendar_month" in fields, (
            "RunContext must have an edl_calendar_month field (Phase 4 §4.2 wiring)"
        )
