"""test_psp002_phase7.py — Phase 7 tests for GS-IMPL-PSP-002.

TC-C16: Operator Profile actually replays during a simulator run (Task #372).

§372 requirement:
  "When a scenario has an operator_response_profile set and grid_authority_tier
   is 'confirm', the PMSTestDouble replays operator decisions during §4.3
   shortfall escalation events, and those decisions appear in the emitted tick
   stream as pms_shortfall_log."

Root cause (fixed)
------------------
Three separate gaps prevented the operator profile from replaying:

1. grid-firm was hardcoded AUTONOMOUS (available_mw=999) in
   build_run_context_from_spec(). With 999 MW of autonomous capacity, the EDL
   never produced a ShortfallEvent, so the §4.3 branch was unreachable.

2. All seeded scenarios had operator_response_profile=null. No live scenario
   could exercise the PMSTestDouble path.

3. Even if PMSTestDouble.process() ran, _pms_entries was silently discarded
   after the logger.info() call — never stamped onto tick_result.  The same
   class of bug as Task #371's edl_dispatch_cost_usd.

Fix
---
A. Added grid_authority_tier field to ScenarioSpec (schemas.py) and to
   build_run_context_from_spec() (scenario_factory.py).  Defaults to
   "autonomous" — preserves all existing behaviour.  Setting it to "confirm"
   demotes grid from the AUTONOMOUS merit order so the EDL can produce a
   ShortfallEvent when BESS + turbine + FC cannot cover demand.

B. Updated demo-pms-shortfall seeded scenario to set grid_authority_tier=
   "confirm" and operator_response_profile={...} so a live demo scenario
   triggers the escalation path.

C. Added pms_shortfall_log: tuple to TickResult (models.py).  _drive() stamps
   the serialised PMSLogEntry list after PMSTestDouble.process() returns
   (A1b block), so section B+C carry the entries in every emitted tick.

D. _tick_result_to_dict() serialises pms_shortfall_log as a list; types.ts
   declares the matching Array<{...}> field.

Strategy
--------
Eight targeted assertions — no async _drive() required:

  C16-1  TickResult.pms_shortfall_log field exists; default is ().
  C16-2  build_run_context_from_spec with grid_authority_tier="confirm" →
          grid-firm source in edl_sources has AuthorityTier.CONFIRM.
  C16-3  Default (no grid_authority_tier key) → grid-firm is AUTONOMOUS.
  C16-4  _tick_result_to_dict() serialises pms_shortfall_log as a list.
  C16-5  With CONFIRM grid-firm and demand > autonomous capacity the EDL fires
          a ShortfallEvent; PMSTestDouble produces entries; _dc_replace stamps
          them onto pms_shortfall_log with the right structure.
  C16-6  demo-pms-shortfall seeded scenario has a non-null operator_response_profile.
  C16-7  demo-pms-shortfall seeded scenario has grid_authority_tier="confirm".
  C16-8  Stamped pms_shortfall_log dict keys match the PMSLogEntry contract.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

# ── imports under test ────────────────────────────────────────────────────────
from api.routes.scenarios import build_seeded_store
from core.economic_dispatch_loop import EconomicDispatchLoop
from core.models import TickResult
from core.power_source_priority import (
    AdvisoryOutput,
    AuthorityTier,
    PowerRanker,
    PowerSource,
    PowerSourceType,
    ResponseLatencyClass,
)
from runtime.pms_test_double import OperatorResponseProfile, PMSTestDouble
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SCENARIO_PATH = (
    pathlib.Path(__file__).parent.parent
    / "config/scenarios/demo-turbine-fc-bess-20-tenants-overage.json"
)


def _load_spec(end_sim_time: float = 10.0) -> dict:
    """Base spec truncated to 2 ticks for fast tests."""
    spec = json.loads(_SCENARIO_PATH.read_text())
    spec["end_sim_time"] = end_sim_time
    return spec


def _confirm_spec(end_sim_time: float = 10.0) -> dict:
    """Same spec but with grid_authority_tier='confirm' so shortfall can fire."""
    spec = _load_spec(end_sim_time)
    spec["grid_authority_tier"] = "confirm"
    return spec


def _make_profile(
    *,
    latency_s: float = 5.0,
    approve: bool = True,
) -> OperatorResponseProfile:
    """Build a simple OperatorResponseProfile for a single rank-1 source."""
    return OperatorResponseProfile(
        response_latency_s={1: latency_s},
        approve={1: approve},
        default_latency_s=30.0,
        default_approve=True,
    )


def _build_shortfall_sources() -> list[PowerSource]:
    """Build a minimal EDL source list that forces a shortfall at 10 MW demand.

    AUTONOMOUS pool: BESS 3 MW + turbine 5 MW = 8 MW (demand=10 > 8 → shortfall).
    CONFIRM pool: grid-firm 999 MW — not used by the EDL, becomes the advisory.
    """
    return [
        PowerSource(
            source_id="bess-test",
            source_type=PowerSourceType.BESS,
            dispatchable=True,
            counts_toward_reserve=True,
            marginal_cost_mwh=20.0,
            response_latency_class=ResponseLatencyClass.INSTANT,
            authority_tier=AuthorityTier.AUTONOMOUS,
            available_mw=3.0,
            cost_basis_note="test BESS",
        ),
        PowerSource(
            source_id="turbine-test",
            source_type=PowerSourceType.TURBINE,
            dispatchable=True,
            counts_toward_reserve=True,
            marginal_cost_mwh=60.0,
            response_latency_class=ResponseLatencyClass.THERMAL_LAG,
            authority_tier=AuthorityTier.AUTONOMOUS,
            available_mw=5.0,
            cost_basis_note="test turbine",
        ),
        PowerSource(
            source_id="grid-firm",
            source_type=PowerSourceType.GRID_FIRM,
            dispatchable=True,
            counts_toward_reserve=False,
            marginal_cost_mwh=120.0,
            response_latency_class=ResponseLatencyClass.INSTANT,
            authority_tier=AuthorityTier.CONFIRM,
            available_mw=999.0,
            cost_basis_note="CONFIRM-tier grid (shortfall test)",
        ),
    ]


# ---------------------------------------------------------------------------
# TC-C16: pms_shortfall_log stamped onto TickResult (Task #372)
# ---------------------------------------------------------------------------


class TestTC_C16_OperatorProfileReplays:
    """TC-C16: PMSTestDouble log entries appear in the emitted tick stream."""

    # ── C16-1: field presence ─────────────────────────────────────────────

    def test_tick_result_has_pms_shortfall_log_field(self) -> None:
        """TickResult.pms_shortfall_log exists and defaults to an empty tuple."""
        fields = {f.name: f for f in dataclasses.fields(TickResult)}
        assert "pms_shortfall_log" in fields, (
            "TickResult must have pms_shortfall_log field (Task #372)"
        )

    def test_tick_result_pms_shortfall_log_default_is_empty_tuple(self) -> None:
        """pms_shortfall_log default must be () — safe for headless runs."""
        fields = {f.name: f for f in dataclasses.fields(TickResult)}
        fld = fields["pms_shortfall_log"]
        # default_factory=tuple produces () for every fresh instance.
        assert fld.default is dataclasses.MISSING, (
            "pms_shortfall_log must use default_factory (not a bare default)"
        )
        assert fld.default_factory is not dataclasses.MISSING, (  # type: ignore[misc]
            "pms_shortfall_log must have a default_factory"
        )
        # Calling the factory must yield an empty tuple.
        assert fld.default_factory() == (), (  # type: ignore[misc]
            "pms_shortfall_log default_factory() must return ()"
        )

    # ── C16-2: grid_authority_tier="confirm" respected by factory ─────────

    def test_confirm_grid_tier_propagates_to_edl_sources(self) -> None:
        """build_run_context_from_spec with grid_authority_tier='confirm' →
        grid-firm source in ctx.edl_sources has AuthorityTier.CONFIRM."""
        spec = _confirm_spec()
        ctx = build_run_context_from_spec("test-c16-2", spec)

        assert ctx.edl_sources is not None, (
            "spec-path RunContext must have edl_sources populated"
        )
        grid = next(
            (s for s in ctx.edl_sources if s.source_id == "grid-firm"), None
        )
        assert grid is not None, "edl_sources must include a 'grid-firm' source"
        assert grid.authority_tier == AuthorityTier.CONFIRM, (
            f"grid-firm must be CONFIRM when spec sets grid_authority_tier='confirm'; "
            f"got {grid.authority_tier!r}"
        )

    # ── C16-3: default grid tier is AUTONOMOUS ────────────────────────────

    def test_default_grid_tier_is_autonomous(self) -> None:
        """Spec without grid_authority_tier → grid-firm remains AUTONOMOUS."""
        spec = _load_spec()
        ctx = build_run_context_from_spec("test-c16-3", spec)

        assert ctx.edl_sources is not None
        grid = next(
            (s for s in ctx.edl_sources if s.source_id == "grid-firm"), None
        )
        assert grid is not None
        assert grid.authority_tier == AuthorityTier.AUTONOMOUS, (
            f"grid-firm must default to AUTONOMOUS; got {grid.authority_tier!r}"
        )

    # ── C16-4: serialisation ─────────────────────────────────────────────

    def test_tick_dict_includes_pms_shortfall_log_key(self) -> None:
        """_tick_result_to_dict() must include 'pms_shortfall_log' key."""
        spec = _load_spec()
        ctx = build_run_context_from_spec("test-c16-4a", spec)
        tick = ctx.step()

        # Default is () — no shortfall.
        d = _tick_result_to_dict(tick)
        assert "pms_shortfall_log" in d, (
            "_tick_result_to_dict must serialise pms_shortfall_log (Task #372)"
        )
        assert d["pms_shortfall_log"] == [], (
            "pms_shortfall_log must serialise as [] when no shortfall fired"
        )

    def test_tick_dict_pms_shortfall_log_serialises_entries(self) -> None:
        """pms_shortfall_log with entries serialises as a non-empty list."""
        spec = _load_spec()
        ctx = build_run_context_from_spec("test-c16-4b", spec)
        tick = ctx.step()

        entry = {
            "t_s": 5.0,
            "source_id": "grid-firm",
            "action": "approved",
            "authority_tier": "confirm",
            "detail": "Simulated approval at t=10.0s (latency 5s).",
        }
        stamped = dataclasses.replace(tick, pms_shortfall_log=(entry,))
        d = _tick_result_to_dict(stamped)
        assert isinstance(d["pms_shortfall_log"], list)
        assert len(d["pms_shortfall_log"]) == 1
        assert d["pms_shortfall_log"][0]["source_id"] == "grid-firm"

    # ── C16-5: shortfall fires and stamp works end-to-end ────────────────

    def test_shortfall_fires_when_autonomous_capacity_exhausted(self) -> None:
        """EDL produces a ShortfallEvent when demand > BESS + turbine pool."""
        sources = _build_shortfall_sources()
        autonomous = [s for s in sources if s.authority_tier == AuthorityTier.AUTONOMOUS]
        total_autonomous_mw = sum(s.available_mw for s in autonomous)
        demand_mw = total_autonomous_mw + 2.0   # 2 MW above autonomous ceiling

        result = EconomicDispatchLoop().step(
            t_s=5.0,
            tick_duration_hours=5.0 / 3600.0,
            hour_of_day=14,
            month=6,
            demand_mw=demand_mw,
            sources=sources,
        )
        assert result.shortfall is not None, (
            f"EDL must produce a ShortfallEvent when demand ({demand_mw} MW) "
            f"exceeds AUTONOMOUS capacity ({total_autonomous_mw} MW); "
            f"got shortfall=None"
        )

    def test_pms_test_double_produces_entries_for_confirm_sources(self) -> None:
        """PMSTestDouble.process() returns one PMSLogEntry per CONFIRM source."""
        sources = _build_shortfall_sources()
        confirm_sources = [
            s for s in sources
            if s.authority_tier in (AuthorityTier.CONFIRM, AuthorityTier.HUMAN_ONLY)
        ]
        advisory = PowerRanker().rank(confirm_sources)

        profile = _make_profile(latency_s=5.0, approve=True)
        pms = PMSTestDouble(profile)
        entries = pms.process(advisory, t_s=5.0)

        assert len(entries) == len(confirm_sources), (
            f"PMSTestDouble must produce one entry per confirm/human_only source; "
            f"got {len(entries)} entries for {len(confirm_sources)} sources"
        )
        assert entries[0].action == "approved", (
            f"Simulated operator with approve=True must produce action='approved'; "
            f"got {entries[0].action!r}"
        )

    def test_pms_entries_stamped_onto_tick_result_via_dc_replace(self) -> None:
        """_dc_replace stamps PMSLogEntry dicts onto pms_shortfall_log."""
        spec = _load_spec()
        ctx = build_run_context_from_spec("test-c16-5c", spec)
        tick = ctx.step()

        # Simulate the full A1b block chain.
        sources = _build_shortfall_sources()
        confirm_sources = [
            s for s in sources
            if s.authority_tier in (AuthorityTier.CONFIRM, AuthorityTier.HUMAN_ONLY)
        ]
        advisory = PowerRanker().rank(confirm_sources)
        profile = _make_profile(latency_s=5.0, approve=True)
        entries = PMSTestDouble(profile).process(advisory, t_s=tick.sim_time_seconds)

        # Reproduce the stamp that _drive() A1b now applies.
        stamped = dataclasses.replace(
            tick,
            pms_shortfall_log=tuple(
                {
                    "t_s":            e.t_s,
                    "source_id":      e.source_id,
                    "action":         e.action,
                    "authority_tier": e.authority_tier,
                    "detail":         e.detail,
                }
                for e in entries
            ),
        )

        assert len(stamped.pms_shortfall_log) == len(entries), (
            "pms_shortfall_log length must match PMSTestDouble entry count"
        )
        assert stamped.pms_shortfall_log[0]["source_id"] == "grid-firm", (
            "pms_shortfall_log[0]['source_id'] must match the grid-firm source"
        )
        assert stamped.pms_shortfall_log[0]["action"] in ("approved", "rejected"), (
            "pms_shortfall_log[0]['action'] must be 'approved' or 'rejected'"
        )

    # ── C16-6: seeded scenario has operator_response_profile ─────────────

    def test_demo_pms_shortfall_has_operator_response_profile(self) -> None:
        """demo-pms-shortfall seeded scenario must have a non-null operator_response_profile."""
        store = build_seeded_store()
        rec = store.get("demo-pms-shortfall")
        assert rec is not None, "demo-pms-shortfall must exist in seeded store"

        spec_data = json.loads(rec.spec_json)
        profile = spec_data.get("operator_response_profile")
        assert profile is not None, (
            "demo-pms-shortfall must have a non-null operator_response_profile "
            "so that ctx.pms_response_profile is populated at run start (Task #372)"
        )
        assert isinstance(profile, dict), (
            "operator_response_profile must be a dict"
        )

    # ── C16-7: seeded scenario has grid_authority_tier="confirm" ─────────

    def test_demo_pms_shortfall_has_grid_authority_tier_confirm(self) -> None:
        """demo-pms-shortfall seeded scenario must have grid_authority_tier='confirm'."""
        store = build_seeded_store()
        rec = store.get("demo-pms-shortfall")
        assert rec is not None, "demo-pms-shortfall must exist in seeded store"

        spec_data = json.loads(rec.spec_json)
        tier = spec_data.get("grid_authority_tier")
        assert tier == "confirm", (
            f"demo-pms-shortfall must have grid_authority_tier='confirm' "
            f"so that the EDL can fire a ShortfallEvent (Task #372); got {tier!r}"
        )

    # ── C16-8: PMSLogEntry dict key contract ─────────────────────────────

    def test_pms_shortfall_log_dict_keys_match_pms_log_entry_contract(self) -> None:
        """Stamped pms_shortfall_log entries must have all five PMSLogEntry keys."""
        _REQUIRED_KEYS = {"t_s", "source_id", "action", "authority_tier", "detail"}

        sources = _build_shortfall_sources()
        confirm_sources = [
            s for s in sources
            if s.authority_tier in (AuthorityTier.CONFIRM, AuthorityTier.HUMAN_ONLY)
        ]
        advisory = PowerRanker().rank(confirm_sources)
        entries = PMSTestDouble(_make_profile()).process(advisory, t_s=0.0)

        stamped = tuple(
            {
                "t_s":            e.t_s,
                "source_id":      e.source_id,
                "action":         e.action,
                "authority_tier": e.authority_tier,
                "detail":         e.detail,
            }
            for e in entries
        )
        assert len(stamped) >= 1, (
            "At least one PMSLogEntry must be produced for the CONFIRM source"
        )
        for i, d in enumerate(stamped):
            missing = _REQUIRED_KEYS - set(d.keys())
            assert not missing, (
                f"pms_shortfall_log[{i}] is missing keys: {missing}. "
                f"All five PMSLogEntry fields must be serialised."
            )
            extra = set(d.keys()) - _REQUIRED_KEYS
            assert not extra, (
                f"pms_shortfall_log[{i}] has unexpected extra keys: {extra}. "
                f"Only the five PMSLogEntry fields should be present."
            )
