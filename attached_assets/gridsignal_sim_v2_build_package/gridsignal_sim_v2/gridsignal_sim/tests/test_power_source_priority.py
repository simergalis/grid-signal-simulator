"""test_power_source_priority.py — PowerRanker unit tests.

GS-IMPL-PSP-002 §9 / Phase 1 / Phase 5.

Tests covered
-------------
  TC-C1: Solar never ranked — excluded from AdvisoryOutput.ranked_sources
         regardless of marginal cost.
  TC-C2: Non-reserve-eligible source flagged, not excluded —
         reserve_eligible=False, source still appears in ranked list.
  TC-C3: EconomicDispatchLoop never allocates to confirm/human_only —
         ShortfallEvent produced instead of an allocation to a non-autonomous
         source.
         (TC-C3 involves EconomicDispatchLoop; the PowerRanker test here only
         checks that confirm/human_only sources ARE included in the advisory
         output — the filter lives in EconomicDispatchLoop, not here.)

Additional coverage
-------------------
  - Zero-available sources excluded from ranking.
  - Non-dispatchable (non-solar) excluded from ranking and excluded list.
  - Correct ascending sort by marginal_cost_mwh.
  - Advisory note is always present.
  - Empty source list returns empty AdvisoryOutput without error.
"""
from __future__ import annotations

import pytest

import core.site_parameters as _sp
from core.power_source_priority import (
    ADVISORY_NOTE,
    AdvisoryOutput,
    AuthorityTier,
    PowerRanker,
    PowerSource,
    PowerSourceType,
    RankedSource,
    ResponseLatencyClass,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_source(
    source_id: str = "src-1",
    source_type: PowerSourceType = PowerSourceType.GRID_FIRM,
    dispatchable: bool = True,
    counts_toward_reserve: bool = True,
    marginal_cost_mwh: float = 100.0,
    authority_tier: AuthorityTier = AuthorityTier.AUTONOMOUS,
    available_mw: float = 10.0,
    cost_basis_note: str | None = None,
) -> PowerSource:
    return PowerSource(
        source_id=source_id,
        source_type=source_type,
        dispatchable=dispatchable,
        counts_toward_reserve=counts_toward_reserve,
        marginal_cost_mwh=marginal_cost_mwh,
        response_latency_class=ResponseLatencyClass.INSTANT,
        authority_tier=authority_tier,
        available_mw=available_mw,
        cost_basis_note=cost_basis_note,
    )


# ── TC-C1: Solar never ranked ─────────────────────────────────────────────────

class TestTC_C1_SolarNeverRanked:
    """Solar sources must never appear in ranked_sources, regardless of cost."""

    def test_solar_excluded_from_ranked_sources(self) -> None:
        solar = _make_source(
            source_id="solar-1",
            source_type=PowerSourceType.SOLAR,
            dispatchable=False,
            marginal_cost_mwh=0.01,   # would be cheapest if included
            available_mw=50.0,
        )
        grid = _make_source(source_id="grid-1", marginal_cost_mwh=150.0)

        result = PowerRanker().rank([solar, grid])

        ranked_ids = [rs.source_id for rs in result.ranked_sources]
        assert "solar-1" not in ranked_ids, (
            "Solar source must not appear in ranked_sources (TC-C1)"
        )

    def test_solar_appears_in_excluded_non_dispatchable(self) -> None:
        solar = _make_source(
            source_id="solar-1",
            source_type=PowerSourceType.SOLAR,
            dispatchable=False,
        )

        result = PowerRanker().rank([solar])

        assert "solar-1" in result.excluded_non_dispatchable, (
            "Solar source must appear in excluded_non_dispatchable (TC-C1)"
        )
        assert result.ranked_sources == [], (
            "ranked_sources must be empty when only source is solar (TC-C1)"
        )

    def test_solar_excluded_even_with_zero_cost(self) -> None:
        """Cost doesn't matter — solar is excluded by type, not by economics."""
        solar = _make_source(
            source_id="solar-free",
            source_type=PowerSourceType.SOLAR,
            dispatchable=False,
            marginal_cost_mwh=0.0,
        )
        result = PowerRanker().rank([solar])
        assert "solar-free" not in [rs.source_id for rs in result.ranked_sources]
        assert "solar-free" in result.excluded_non_dispatchable

    def test_multiple_solar_sources_all_excluded(self) -> None:
        sources = [
            _make_source(source_id=f"solar-{i}", source_type=PowerSourceType.SOLAR,
                         dispatchable=False, marginal_cost_mwh=float(i))
            for i in range(3)
        ]
        result = PowerRanker().rank(sources)
        assert result.ranked_sources == []
        assert len(result.excluded_non_dispatchable) == 3


# ── TC-C2: Non-reserve-eligible flagged, not excluded ────────────────────────

class TestTC_C2_NonReserveEligibleFlagged:
    """A non-reserve-eligible source must appear in ranked output with
    reserve_eligible=False, not be silently dropped."""

    def test_non_reserve_eligible_appears_in_ranked(self) -> None:
        fuel_cell = _make_source(
            source_id="fc-1",
            source_type=PowerSourceType.FUEL_CELL,
            counts_toward_reserve=False,   # PSP-3: defaults conservatively False
            marginal_cost_mwh=65.0,
        )
        result = PowerRanker().rank([fuel_cell])

        assert len(result.ranked_sources) == 1, (
            "Non-reserve-eligible source must appear in ranked_sources (TC-C2)"
        )
        assert result.ranked_sources[0].reserve_eligible is False, (
            "reserve_eligible must be False for counts_toward_reserve=False source (TC-C2)"
        )
        assert result.ranked_sources[0].source_id == "fc-1"

    def test_reserve_eligible_source_correctly_flagged_true(self) -> None:
        grid = _make_source(
            source_id="grid-firm",
            source_type=PowerSourceType.GRID_FIRM,
            counts_toward_reserve=True,
        )
        result = PowerRanker().rank([grid])
        assert result.ranked_sources[0].reserve_eligible is True

    def test_mixed_reserve_eligibility_both_ranked(self) -> None:
        """Non-reserve-eligible and reserve-eligible sources both rank."""
        sources = [
            _make_source("fc-1", PowerSourceType.FUEL_CELL,
                         counts_toward_reserve=False, marginal_cost_mwh=65.0),
            _make_source("grid-1", PowerSourceType.GRID_FIRM,
                         counts_toward_reserve=True, marginal_cost_mwh=100.0),
        ]
        result = PowerRanker().rank(sources)
        assert len(result.ranked_sources) == 2
        ranked_by_id = {rs.source_id: rs for rs in result.ranked_sources}
        assert ranked_by_id["fc-1"].reserve_eligible is False
        assert ranked_by_id["grid-1"].reserve_eligible is True


# ── TC-C3 (partial): confirm/human_only included in advisory ranking ──────────

class TestTC_C3_NonAutonomousInAdvisory:
    """confirm and human_only sources are included in the advisory output.

    The autonomous-only filter lives in EconomicDispatchLoop, not here.
    PowerRanker must surface non-autonomous sources so the escalation path
    (§4.3) can pass them to PMSTestDouble.
    """

    def test_confirm_tier_included_in_ranked(self) -> None:
        confirm_src = _make_source(
            source_id="diesel-1",
            source_type=PowerSourceType.TURBINE,
            authority_tier=AuthorityTier.CONFIRM,
            marginal_cost_mwh=200.0,
        )
        result = PowerRanker().rank([confirm_src])
        assert len(result.ranked_sources) == 1
        assert result.ranked_sources[0].authority_tier == AuthorityTier.CONFIRM

    def test_human_only_tier_included_in_ranked(self) -> None:
        human_src = _make_source(
            source_id="emergency-gen",
            source_type=PowerSourceType.TURBINE,
            authority_tier=AuthorityTier.HUMAN_ONLY,
            marginal_cost_mwh=500.0,
        )
        result = PowerRanker().rank([human_src])
        assert len(result.ranked_sources) == 1
        assert result.ranked_sources[0].authority_tier == AuthorityTier.HUMAN_ONLY


# ── Sorting and ranking correctness ───────────────────────────────────────────

class TestRankingSort:
    """Merit order must be ascending by marginal_cost_mwh."""

    def test_cheapest_is_rank_1(self) -> None:
        sources = [
            _make_source("bess-1", PowerSourceType.BESS,
                         marginal_cost_mwh=38.0),
            _make_source("fc-1", PowerSourceType.FUEL_CELL,
                         marginal_cost_mwh=65.0, counts_toward_reserve=False),
            _make_source("grid-1", PowerSourceType.GRID_FIRM,
                         marginal_cost_mwh=114.82),
        ]
        result = PowerRanker().rank(sources)
        assert result.ranked_sources[0].source_id == "bess-1"
        assert result.ranked_sources[0].rank == 1
        assert result.ranked_sources[1].source_id == "fc-1"
        assert result.ranked_sources[1].rank == 2
        assert result.ranked_sources[2].source_id == "grid-1"
        assert result.ranked_sources[2].rank == 3

    def test_rank_matches_position(self) -> None:
        sources = [
            _make_source(f"src-{i}", marginal_cost_mwh=float(100 + i))
            for i in range(5)
        ]
        result = PowerRanker().rank(sources)
        for i, rs in enumerate(result.ranked_sources):
            assert rs.rank == i + 1, f"rank at position {i} should be {i+1}, got {rs.rank}"


# ── Zero-available sources ────────────────────────────────────────────────────

class TestZeroAvailable:
    def test_zero_available_mw_excluded(self) -> None:
        offline = _make_source("bess-offline", available_mw=0.0)
        online = _make_source("grid-1", marginal_cost_mwh=150.0, available_mw=10.0)
        result = PowerRanker().rank([offline, online])
        ranked_ids = [rs.source_id for rs in result.ranked_sources]
        assert "bess-offline" not in ranked_ids
        assert "grid-1" in ranked_ids

    def test_negative_available_mw_excluded(self) -> None:
        """Negative available_mw (e.g. a source in maintenance) is treated as zero."""
        src = _make_source("turbine-maint", available_mw=-1.0)
        result = PowerRanker().rank([src])
        assert result.ranked_sources == []


# ── Advisory note ─────────────────────────────────────────────────────────────

class TestAdvisoryNote:
    def test_note_always_present(self) -> None:
        result = PowerRanker().rank([])
        assert result.note == ADVISORY_NOTE

    def test_note_is_advisory_only_disclaimer(self) -> None:
        result = PowerRanker().rank([_make_source()])
        assert "advisory" in result.note.lower()


# ── Empty input ───────────────────────────────────────────────────────────────

class TestEmptyInput:
    def test_empty_source_list_returns_empty_output(self) -> None:
        result = PowerRanker().rank([])
        assert result.ranked_sources == []
        assert result.excluded_non_dispatchable == []
        assert result.note == ADVISORY_NOTE

    def test_all_solar_returns_empty_ranked(self) -> None:
        sources = [
            _make_source(f"solar-{i}", PowerSourceType.SOLAR, dispatchable=False)
            for i in range(3)
        ]
        result = PowerRanker().rank(sources)
        assert result.ranked_sources == []
        assert len(result.excluded_non_dispatchable) == 3


# ── Cost basis note passthrough ───────────────────────────────────────────────

class TestCostBasisNote:
    def test_cost_basis_note_passes_through(self) -> None:
        src = _make_source(
            source_id="grid-1",
            cost_basis_note="PG&E B-20, off_peak_summer",
        )
        result = PowerRanker().rank([src])
        assert result.ranked_sources[0].cost_basis_note == "PG&E B-20, off_peak_summer"

    def test_none_cost_basis_note_passes_through(self) -> None:
        src = _make_source(source_id="bess-1", cost_basis_note=None)
        result = PowerRanker().rank([src])
        assert result.ranked_sources[0].cost_basis_note is None


# ── BESS catalogue repricing in rank() — post-review correction ───────────────

class TestBESSCatalogueRepricingInRank:
    """PowerRanker.rank() must reprice BESS from the parameter catalogue (§3.1 / §7).

    Post-review correction: BESS catalogue-sourcing moved from step() into rank()
    so that both the autonomous dispatch path (through step()) and the §4.3
    escalation path (which calls rank() directly on confirm/human_only sources)
    see the same catalogue-sourced cost.  A human operator advisory must never
    show a BESS cost that differs from what the autonomous loop used.
    """

    def _bess_src(self, source_id: str = "bess-1", marginal_cost_mwh: float = 999.0,
                  authority_tier: AuthorityTier = AuthorityTier.AUTONOMOUS) -> PowerSource:
        return _make_source(
            source_id=source_id,
            source_type=PowerSourceType.BESS,
            marginal_cost_mwh=marginal_cost_mwh,
            available_mw=5.0,
            authority_tier=authority_tier,
        )

    def test_bess_ranked_cost_matches_catalogue(self) -> None:
        """rank() must override caller-supplied BESS cost with catalogue value."""
        src = self._bess_src(marginal_cost_mwh=999.0)  # caller-supplied: wrong
        result = PowerRanker().rank([src])

        assert result.ranked_sources, "BESS should appear in ranked output"
        actual = result.ranked_sources[0].marginal_cost_mwh
        expected = _sp.value("bess_marginal_cost_mwh")

        assert actual == pytest.approx(expected), (
            f"rank() must reprice BESS to catalogue value ({expected}), "
            f"not caller-supplied 999.0; got {actual}"
        )

    def test_bess_cost_basis_note_set_to_catalogue(self) -> None:
        """cost_basis_note on the repriced BESS RankedSource must reference catalogue."""
        src = self._bess_src()
        result = PowerRanker().rank([src])

        note = result.ranked_sources[0].cost_basis_note
        assert note is not None and "catalogue" in note.lower(), (
            f"BESS cost_basis_note should reference catalogue, got: {note!r}"
        )

    def test_bess_repriced_same_regardless_of_caller_value(self) -> None:
        """Two BESS sources with different caller-supplied costs rank at the same price."""
        bess_a = self._bess_src("bess-a", marginal_cost_mwh=1.0)
        bess_b = self._bess_src("bess-b", marginal_cost_mwh=999.0)
        result = PowerRanker().rank([bess_a, bess_b])

        prices = {rs.source_id: rs.marginal_cost_mwh for rs in result.ranked_sources}
        assert prices["bess-a"] == pytest.approx(prices["bess-b"]), (
            "Both BESS sources must be repriced to the same catalogue value, "
            f"regardless of caller-supplied cost. Got: {prices}"
        )

    def test_bess_confirm_tier_still_repriced(self) -> None:
        """A BESS source at CONFIRM tier (§4.3 escalation path) is also repriced.
        This is the exact path that step() cannot cover — confirming rank() handles it."""
        bess_confirm = self._bess_src(
            source_id="bess-confirm",
            marginal_cost_mwh=50.0,   # plausible-looking but wrong
            authority_tier=AuthorityTier.CONFIRM,
        )
        result = PowerRanker().rank([bess_confirm])

        assert result.ranked_sources, "CONFIRM BESS must appear in ranked output"
        actual = result.ranked_sources[0].marginal_cost_mwh
        expected = _sp.value("bess_marginal_cost_mwh")

        assert actual == pytest.approx(expected), (
            "§4.3 escalation path: CONFIRM-tier BESS must be repriced by rank() "
            f"to catalogue ({expected}), not caller-supplied 50.0; got {actual}"
        )

    def test_non_bess_sources_not_repriced_by_rank(self) -> None:
        """rank() must not override costs for non-BESS sources (grid, fuel cell, turbine)."""
        grid = _make_source("grid-1", source_type=PowerSourceType.GRID_FIRM,
                            marginal_cost_mwh=177.02, available_mw=50.0)
        fc = _make_source("fc-1", source_type=PowerSourceType.FUEL_CELL,
                          marginal_cost_mwh=65.0, available_mw=20.0)

        result = PowerRanker().rank([grid, fc])
        prices = {rs.source_id: rs.marginal_cost_mwh for rs in result.ranked_sources}

        assert prices["grid-1"] == pytest.approx(177.02), (
            "rank() must not reprice grid sources — TOU is step()'s responsibility"
        )
        assert prices["fc-1"] == pytest.approx(65.0), (
            "rank() must not reprice fuel cell sources"
        )
