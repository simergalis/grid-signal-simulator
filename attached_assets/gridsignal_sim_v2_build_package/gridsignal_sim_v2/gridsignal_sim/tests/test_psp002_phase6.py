"""test_psp002_phase6.py — Phase 6 tests for GS-IMPL-PSP-002.

TC-C15: EDL dispatch cost stamped onto every TickResult (Task #371).

§371 requirement:
  "edl_dispatch_cost_usd appears in every tick emitted by a spec-path run
   — making the EDL *observable*, not just silently executed."

Root cause (fixed)
------------------
Before this fix _drive() called EconomicDispatchLoop().step() every tick and
logged the result, but never stamped _edl_result.cost_this_tick onto
tick_result.  The EDL was running but its output was thrown away before
sink.append() / broadcast() — invisible to dashboards, playback, and audit.

Fix
---
After _EconomicDispatchLoop().step() in the A1b block, _drive() now calls:

    tick_result = _dc_replace(
        tick_result,
        edl_dispatch_cost_usd=_edl_result.cost_this_tick,
    )

This runs before section B (thermal, fabric) and section C (sink + broadcast)
so every emitted tick carries a non-None edl_dispatch_cost_usd.

Strategy
--------
Five targeted assertions — no async _drive() required:

  C15-1  TickResult.edl_dispatch_cost_usd field exists; default is None.
  C15-2  _dc_replace stamps the EDL cost onto a real tick from ctx.step().
  C15-3  _tick_result_to_dict() serialises the field under "edl_dispatch_cost_usd".
  C15-4  Cost is strictly positive for a realistic non-zero-demand scenario.
  C15-5  Field stays None when edl_sources is not wired (headless path).
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

# ── imports under test ────────────────────────────────────────────────────────
from core.economic_dispatch_loop import EconomicDispatchLoop
from core.models import TickResult
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SCENARIO_PATH = (
    pathlib.Path(__file__).parent.parent
    / "config/scenarios/demo-turbine-fc-bess-20-tenants-overage.json"
)


def _load_short_spec(end_sim_time: float = 10.0) -> dict:
    """Return the demo-overage spec truncated to 2 ticks (10 s)."""
    spec = json.loads(_SCENARIO_PATH.read_text())
    spec["end_sim_time"] = end_sim_time
    return spec


# ---------------------------------------------------------------------------
# TC-C15: EDL dispatch cost stamped onto TickResult
# ---------------------------------------------------------------------------


class TestTC_C15_EDLCostStampedOntoTickResult:
    """TC-C15: every spec-path tick carries edl_dispatch_cost_usd."""

    # ── C15-1: field presence ─────────────────────────────────────────────

    def test_tick_result_has_edl_dispatch_cost_usd_field(self) -> None:
        """TickResult.edl_dispatch_cost_usd exists with a default of None."""
        fields = {f.name: f for f in dataclasses.fields(TickResult)}
        assert "edl_dispatch_cost_usd" in fields, (
            "TickResult must have edl_dispatch_cost_usd field (Task #371)"
        )

    def test_tick_result_edl_field_default_is_none(self) -> None:
        """edl_dispatch_cost_usd default must be None (headless-safe)."""
        fields = {f.name: f for f in dataclasses.fields(TickResult)}
        default = fields["edl_dispatch_cost_usd"].default
        assert default is None, (
            f"edl_dispatch_cost_usd default must be None, got {default!r}"
        )

    def test_tick_result_edl_field_is_optional_float(self) -> None:
        """edl_dispatch_cost_usd annotation must be Optional[float]."""
        hints = TickResult.__dataclass_fields__["edl_dispatch_cost_usd"]
        # annotation string contains "float" and allows None
        ann = str(hints.type)
        assert "float" in ann or hints.type in (float, type(None)), (
            f"edl_dispatch_cost_usd should be Optional[float], got {hints.type!r}"
        )

    # ── C15-2: stamp via _dc_replace ─────────────────────────────────────

    def test_dc_replace_stamps_edl_cost_onto_tick_result(self) -> None:
        """_dc_replace correctly sets edl_dispatch_cost_usd on a real tick."""
        spec = _load_short_spec()
        ctx = build_run_context_from_spec("test-c15-2", spec)

        tick_result = ctx.step()
        assert tick_result.edl_dispatch_cost_usd is None, (
            "tick fresh from ctx.step() must have edl_dispatch_cost_usd=None "
            "before the A1b stamp"
        )

        # Simulate what the A1b block does inside _drive().
        assert ctx.edl_sources is not None
        edl_result = EconomicDispatchLoop().step(
            tick_result.sim_time_seconds,
            tick_duration_hours=5.0 / 3600.0,
            hour_of_day=int(tick_result.sim_time_seconds / 3600.0) % 24,
            month=ctx.edl_calendar_month,
            demand_mw=tick_result.p_demand_mw,
            sources=ctx.edl_sources,
        )

        stamped = dataclasses.replace(tick_result, edl_dispatch_cost_usd=edl_result.cost_this_tick)
        assert stamped.edl_dispatch_cost_usd is not None, (
            "edl_dispatch_cost_usd must be non-None after the A1b stamp"
        )
        assert stamped.edl_dispatch_cost_usd >= 0.0, (
            "edl_dispatch_cost_usd must be ≥ 0"
        )

    # ── C15-3: serialisation ─────────────────────────────────────────────

    def test_tick_dict_includes_edl_dispatch_cost_usd_key(self) -> None:
        """_tick_result_to_dict() must include 'edl_dispatch_cost_usd' key."""
        spec = _load_short_spec()
        ctx = build_run_context_from_spec("test-c15-3a", spec)
        tick_result = ctx.step()

        # Stamp with a known value.
        stamped = dataclasses.replace(tick_result, edl_dispatch_cost_usd=0.123456)
        d = _tick_result_to_dict(stamped)

        assert "edl_dispatch_cost_usd" in d, (
            "_tick_result_to_dict must serialise edl_dispatch_cost_usd (Task #371)"
        )

    def test_tick_dict_edl_cost_rounds_to_six_places(self) -> None:
        """edl_dispatch_cost_usd is rounded to 6 decimal places in the dict."""
        spec = _load_short_spec()
        ctx = build_run_context_from_spec("test-c15-3b", spec)
        tick_result = ctx.step()

        stamped = dataclasses.replace(tick_result, edl_dispatch_cost_usd=0.1234567891)
        d = _tick_result_to_dict(stamped)
        assert d["edl_dispatch_cost_usd"] == round(0.1234567891, 6)

    def test_tick_dict_edl_cost_none_when_field_is_none(self) -> None:
        """edl_dispatch_cost_usd serialises as null (None) on headless path."""
        spec = _load_short_spec()
        ctx = build_run_context_from_spec("test-c15-3c", spec)
        tick_result = ctx.step()

        # default is None — headless / direct job-id path.
        assert tick_result.edl_dispatch_cost_usd is None
        d = _tick_result_to_dict(tick_result)
        assert d["edl_dispatch_cost_usd"] is None, (
            "null edl_dispatch_cost_usd must serialise as None, not raise"
        )

    # ── C15-4: positive cost for non-zero demand ──────────────────────────

    def test_edl_cost_is_positive_for_nonzero_demand_scenario(self) -> None:
        """With real demand, EDL cost must be > 0 after the A1b stamp."""
        spec = _load_short_spec()
        ctx = build_run_context_from_spec("test-c15-4", spec)

        assert ctx.edl_sources is not None, (
            "spec-path RunContext must have edl_sources populated"
        )

        # Run two ticks and verify cost > 0 on each.
        for tick_n in range(2):
            tick_result = ctx.step()
            edl_result = EconomicDispatchLoop().step(
                tick_result.sim_time_seconds,
                tick_duration_hours=5.0 / 3600.0,
                hour_of_day=int(tick_result.sim_time_seconds / 3600.0) % 24,
                month=ctx.edl_calendar_month,
                demand_mw=tick_result.p_demand_mw,
                sources=ctx.edl_sources,
            )
            stamped = dataclasses.replace(
                tick_result, edl_dispatch_cost_usd=edl_result.cost_this_tick
            )
            assert stamped.edl_dispatch_cost_usd > 0.0, (
                f"tick {tick_n}: edl_dispatch_cost_usd should be > 0 "
                f"when demand ({tick_result.p_demand_mw:.3f} MW) is non-zero"
            )

    def test_edl_cost_appears_in_tick_dict_as_positive_value(self) -> None:
        """End-to-end: stamped tick → dict → edl_dispatch_cost_usd > 0."""
        spec = _load_short_spec()
        ctx = build_run_context_from_spec("test-c15-4b", spec)

        tick_result = ctx.step()
        edl_result = EconomicDispatchLoop().step(
            tick_result.sim_time_seconds,
            tick_duration_hours=5.0 / 3600.0,
            hour_of_day=int(tick_result.sim_time_seconds / 3600.0) % 24,
            month=ctx.edl_calendar_month,
            demand_mw=tick_result.p_demand_mw,
            sources=ctx.edl_sources,
        )
        stamped = dataclasses.replace(
            tick_result, edl_dispatch_cost_usd=edl_result.cost_this_tick
        )
        d = _tick_result_to_dict(stamped)
        assert d["edl_dispatch_cost_usd"] is not None
        assert d["edl_dispatch_cost_usd"] > 0.0

    # ── C15-5: headless path leaves field None ────────────────────────────

    def test_edl_cost_stays_none_when_edl_sources_not_wired(self) -> None:
        """TickResult default is None; headless ticks must not raise."""
        spec = _load_short_spec()
        ctx = build_run_context_from_spec("test-c15-5", spec)

        # Detach edl_sources to simulate the headless/direct path.
        ctx.edl_sources = None

        tick_result = ctx.step()
        # The A1b block is guarded by `if ctx.edl_sources is not None:` so
        # no stamp occurs.  Field must remain at its default (None).
        assert tick_result.edl_dispatch_cost_usd is None, (
            "tick_result from a headless context must have edl_dispatch_cost_usd=None"
        )
        # Serialisation must not raise.
        d = _tick_result_to_dict(tick_result)
        assert d["edl_dispatch_cost_usd"] is None
