"""test_psp002_phase5.py — Phase 5 tests for GS-IMPL-PSP-002.

TC-C14: Deterministic replay.

§9 requirement:
  "Same ScenarioSpec + OperatorResponseProfile, two simulator runs →
   byte-identical PMSLogEntry and DispatchResult sequences."

Strategy
--------
Full end-to-end replay of a complete run is expensive and fragile for a unit
test.  TC-C14's invariant is on the *subsystem* boundary, not the run runner:

  1. EconomicDispatchLoop.step() — same inputs → same DispatchResult.
     This is the dispatch half of "byte-identical DispatchResult sequences."

  2. PMSTestDouble.process() — same inputs → same PMSLogEntry list.
     This is the PMS half of "byte-identical PMSLogEntry sequences."

Both are deterministic by construction (no random, no clock, no I/O), so the
tests confirm that the implementation honours the contract without accidentally
breaking it — e.g. by adding wall-clock timestamps or random tie-breaking.

Structural tests also confirm:
  - DispatchResult and PMSLogEntry are @dataclasses (value equality via __eq__).
  - scenario_author._validate_against_schema() is called from
    generate_operator_response_profile() (schema wiring, Phase 5 §5).
"""
from __future__ import annotations

import dataclasses
import inspect
from typing import List

import pytest

from core.economic_dispatch_loop import (
    DispatchResult,
    EconomicDispatchLoop,
    ShortfallEvent,
)
from core.power_source_priority import (
    ADVISORY_NOTE,
    AdvisoryOutput,
    AuthorityTier,
    PowerSource,
    PowerSourceType,
    RankedSource,
    ResponseLatencyClass,
)
from runtime.pms_test_double import (
    OperatorResponseProfile,
    PMSLogEntry,
    PMSTestDouble,
)


# ── Shared fixtures ──────────────────────────────────────────────────────────

def _bess_source(source_id: str = "bess-1", available_mw: float = 5.0) -> PowerSource:
    """Autonomous BESS source — cheapest in merit order, repriced by PowerRanker."""
    return PowerSource(
        source_id=source_id,
        source_type=PowerSourceType.BESS,
        dispatchable=True,
        counts_toward_reserve=True,
        marginal_cost_mwh=50.0,   # will be overridden by catalogue in rank()
        response_latency_class=ResponseLatencyClass.INSTANT,
        authority_tier=AuthorityTier.AUTONOMOUS,
        available_mw=available_mw,
    )


def _grid_source(source_id: str = "grid-1", available_mw: float = 10.0) -> PowerSource:
    """Autonomous grid-firm source — TOU-repriced by step()."""
    return PowerSource(
        source_id=source_id,
        source_type=PowerSourceType.GRID_FIRM,
        dispatchable=True,
        counts_toward_reserve=True,
        marginal_cost_mwh=200.0,  # placeholder; step() reprices via TOU
        response_latency_class=ResponseLatencyClass.RAMP_LIMITED,
        authority_tier=AuthorityTier.AUTONOMOUS,
        available_mw=available_mw,
    )


def _confirm_grid_source(
    source_id: str = "grid-confirm-1",
    available_mw: float = 8.0,
    rank: int = 1,
) -> RankedSource:
    """Pre-ranked confirm-tier grid source for PMS advisory tests."""
    return RankedSource(
        rank=rank,
        source_id=source_id,
        source_type=PowerSourceType.GRID_FIRM,
        marginal_cost_mwh=220.0,
        available_mw=available_mw,
        reserve_eligible=True,
        authority_tier=AuthorityTier.CONFIRM,
        cost_basis_note="test/summer_peak",
    )


def _advisory(*ranked: RankedSource) -> AdvisoryOutput:
    return AdvisoryOutput(
        ranked_sources=list(ranked),
        excluded_non_dispatchable=[],
        note=ADVISORY_NOTE,
    )


# ── TC-C14-A: EconomicDispatchLoop determinism ────────────────────────────────

class TestTC_C14_EDLDeterministicReplay:
    """Two identical EconomicDispatchLoop.step() calls return equal DispatchResults.

    TC-C14 (dispatch half): deterministic replay invariant for the EDL subsystem.
    """

    _SOURCES = [_bess_source(), _grid_source()]
    _STEP_KWARGS: dict = dict(
        tick_duration_hours=5 / 3600,
        hour_of_day=17,
        month=7,
        demand_mw=3.0,
        sources=_SOURCES,
    )

    def test_edl_step_identical_on_two_calls(self) -> None:
        """Two EDL.step() calls with identical inputs produce equal DispatchResults."""
        edl = EconomicDispatchLoop()
        r1: DispatchResult = edl.step(10.0, **self._STEP_KWARGS)
        r2: DispatchResult = edl.step(10.0, **self._STEP_KWARGS)
        assert r1 == r2, (
            "EconomicDispatchLoop.step() is not deterministic: "
            f"first call → {r1!r}, second call → {r2!r}"
        )

    def test_edl_fresh_instance_same_output(self) -> None:
        """Two fresh EconomicDispatchLoop instances produce equal results for same inputs.

        EconomicDispatchLoop is stateless — a new instance must be
        indistinguishable from a reused one (TC-C14 replay invariant).
        """
        r1 = EconomicDispatchLoop().step(10.0, **self._STEP_KWARGS)
        r2 = EconomicDispatchLoop().step(10.0, **self._STEP_KWARGS)
        assert r1 == r2

    def test_edl_dispatch_result_is_dataclass(self) -> None:
        """DispatchResult is a dataclass (value equality via auto-generated __eq__)."""
        assert dataclasses.is_dataclass(DispatchResult), (
            "DispatchResult must be a @dataclass so TC-C14 byte-identical "
            "comparison works via == without custom __eq__."
        )

    def test_edl_shortfall_event_is_dataclass(self) -> None:
        """ShortfallEvent is a dataclass (value equality)."""
        assert dataclasses.is_dataclass(ShortfallEvent)

    def test_edl_determinism_with_shortfall(self) -> None:
        """Determinism holds even when demand exceeds supply (ShortfallEvent path)."""
        sources = [_bess_source(available_mw=1.0)]  # 1 MW vs 10 MW demand → shortfall
        kwargs = dict(
            tick_duration_hours=5 / 3600,
            hour_of_day=10,
            month=3,
            demand_mw=10.0,
            sources=sources,
        )
        r1 = EconomicDispatchLoop().step(0.0, **kwargs)
        r2 = EconomicDispatchLoop().step(0.0, **kwargs)
        assert r1 == r2
        assert r1.shortfall is not None, "Expected ShortfallEvent on this test case"

    def test_edl_different_inputs_differ(self) -> None:
        """Sanity: different tick inputs produce different DispatchResults."""
        r1 = EconomicDispatchLoop().step(10.0, **self._STEP_KWARGS)
        r2 = EconomicDispatchLoop().step(
            10.0,
            tick_duration_hours=5 / 3600,
            hour_of_day=17,
            month=7,
            demand_mw=6.0,   # <-- different demand
            sources=self._SOURCES,
        )
        assert r1 != r2, (
            "Different demand_mw must produce different DispatchResult "
            "(sanity check for the equality mechanism itself)."
        )


# ── TC-C14-B: PMSTestDouble determinism ────────────────────────────────────────

class TestTC_C14_PMSDeterministicReplay:
    """Two identical PMSTestDouble.process() calls return equal PMSLogEntry lists.

    TC-C14 (PMS half): deterministic replay invariant for the simulator escalation path.
    """

    _PROFILE = OperatorResponseProfile(
        response_latency_s={1: 45.0, 2: 90.0},
        approve={1: True, 2: False},
    )
    _ADVISORY = _advisory(
        _confirm_grid_source(source_id="grid-confirm-1", rank=1),
        _confirm_grid_source(source_id="grid-confirm-2", rank=2),
    )

    def test_pms_process_identical_on_two_calls(self) -> None:
        """Two PMSTestDouble.process() calls with same inputs produce equal log lists."""
        pms = PMSTestDouble(self._PROFILE)
        entries1: List[PMSLogEntry] = pms.process(self._ADVISORY, t_s=60.0)
        entries2: List[PMSLogEntry] = pms.process(self._ADVISORY, t_s=60.0)
        assert entries1 == entries2, (
            "PMSTestDouble.process() is not deterministic: "
            f"first call → {entries1!r}, second call → {entries2!r}"
        )

    def test_pms_fresh_instance_same_output(self) -> None:
        """Two fresh PMSTestDouble instances with same profile produce equal output."""
        pms1 = PMSTestDouble(self._PROFILE)
        pms2 = PMSTestDouble(self._PROFILE)
        entries1 = pms1.process(self._ADVISORY, t_s=60.0)
        entries2 = pms2.process(self._ADVISORY, t_s=60.0)
        assert entries1 == entries2

    def test_pms_log_entry_is_dataclass(self) -> None:
        """PMSLogEntry is a dataclass (value equality via auto-generated __eq__)."""
        assert dataclasses.is_dataclass(PMSLogEntry), (
            "PMSLogEntry must be a @dataclass so TC-C14 byte-identical "
            "comparison works via == without custom __eq__."
        )

    def test_pms_log_entry_equality_is_field_based(self) -> None:
        """PMSLogEntry == compares all fields, not object identity."""
        e1 = PMSLogEntry(t_s=60.0, source_id="s1", action="approved",
                         authority_tier="confirm", detail="d1")
        e2 = PMSLogEntry(t_s=60.0, source_id="s1", action="approved",
                         authority_tier="confirm", detail="d1")
        assert e1 == e2
        assert e1 is not e2   # different objects
        e3 = PMSLogEntry(t_s=61.0, source_id="s1", action="approved",
                         authority_tier="confirm", detail="d1")
        assert e1 != e3, "Different t_s must not compare equal"

    def test_pms_determinism_with_empty_advisory(self) -> None:
        """Determinism holds for empty advisory (no ranked sources)."""
        advisory = _advisory()   # no sources
        pms = PMSTestDouble(self._PROFILE)
        entries1 = pms.process(advisory, t_s=0.0)
        entries2 = pms.process(advisory, t_s=0.0)
        assert entries1 == entries2
        assert entries1 == []

    def test_pms_different_t_s_differs(self) -> None:
        """Sanity: different t_s produces entries with different timestamps."""
        pms = PMSTestDouble(self._PROFILE)
        entries1 = pms.process(self._ADVISORY, t_s=60.0)
        entries2 = pms.process(self._ADVISORY, t_s=120.0)
        assert entries1 != entries2, (
            "Different t_s must produce different PMSLogEntry.detail strings "
            "(sanity check for the equality mechanism)."
        )


# ── TC-C14-C: Structural — scenario_author schema wiring ─────────────────────

class TestTC_C14_ScenarioAuthorSchemaWiring:
    """Phase 5 structural: scenario_author._validate_against_schema() is wired.

    Verifies that generate_operator_response_profile() calls
    _validate_against_schema() before returning, so schema drift in
    OperatorResponseProfile is caught at profile-generation time, not at
    simulator startup.
    """

    def test_validate_against_schema_defined_in_scenario_author(self) -> None:
        """_validate_against_schema is a module-level function in scenario_author."""
        import scripts.scenario_author as sa
        assert hasattr(sa, "_validate_against_schema"), (
            "scripts/scenario_author.py must define _validate_against_schema() "
            "(Phase 5 — schema wiring of OperatorResponseProfile)."
        )
        assert callable(sa._validate_against_schema)

    def test_generate_profile_calls_validate_against_schema(self) -> None:
        """generate_operator_response_profile() source references _validate_against_schema.

        AST-free source check — acceptable because the function name is
        intentionally unique within the module.
        """
        import scripts.scenario_author as sa
        src = inspect.getsource(sa.generate_operator_response_profile)
        assert "_validate_against_schema" in src, (
            "generate_operator_response_profile() must call "
            "_validate_against_schema() to wire the OperatorResponseProfile "
            "schema validation (Phase 5 spec requirement)."
        )

    def test_scenario_author_imports_operator_response_profile(self) -> None:
        """scenario_author imports OperatorResponseProfile from runtime.pms_test_double."""
        import scripts.scenario_author as sa
        module_src = inspect.getsource(sa)
        assert "OperatorResponseProfile" in module_src, (
            "scenario_author.py must import OperatorResponseProfile from "
            "runtime.pms_test_double (Phase 5 schema-wiring requirement)."
        )
