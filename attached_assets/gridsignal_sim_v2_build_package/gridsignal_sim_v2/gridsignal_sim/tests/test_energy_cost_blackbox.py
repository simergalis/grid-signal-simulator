"""
tests/test_energy_cost_blackbox.py — GS-DIAG-COST-003 black-box verification

Ten tests that treat the turbine cost model and TOU rate schedule as black boxes:
supply inputs, assert outputs, with no inspection of internal implementation.

Coverage
--------
Tests 1–3:  DIAG-3 $/kWh-by-duty-cycle table (100%, 50%, 10% duty).
            Each verifies the combined capital+variable rate matches the table
            that was presented to the operator.
Test 4:     Capital is duty-invariant — different generation, same ownership cost.
Test 5:     Duty fraction output field is computed correctly (not an internal alias).
Test 6:     Accounting identity — total_cost == sum of its three components.
Test 7:     Round-trip storage loss contributes the correct additional cost.
Test 8:     Season boundary correctness — months 5/6 and 9/10 are the critical edges.
Test 9:     All three summer TOU bands return catalogue-exact rates.
Test 10:    Winter super off-peak boundary — month AND hour must both qualify;
            failing either condition falls back to off-peak or peak.

Ground truth
------------
DIAG-3 default inputs (from cost_model.py module docstring):
  turbine_capital_per_mw_year = $45,000
  turbine_variable_per_mwh    = $55

TOU rates (from live catalogue via site_parameters — pge_price_for_period docstring
and confirmed by python -c "... sp.value(k)"):
  summer peak           = $177.02/MWh  (hours 16–20)
  summer part-peak      = $142.27/MWh  (hours 14–15, 21–22)
  summer off-peak       = $114.82/MWh  (all other summer hours)
  winter peak           = $156.32/MWh  (hours 16–20, all winter months)
  winter off-peak       = $114.60/MWh  (all other winter hours)
  winter super off-peak = $ 58.72/MWh  (months 3–5 AND hours 9–13 only)

AT-7: all tests are synchronous, deterministic, and call no runtime RNG.
"""
from __future__ import annotations

import pytest

from core.cost_model import CostModelConfig, CostModelEngine
from core.economic_dispatch_loop import pge_price_for_period, season_from_month


# ---------------------------------------------------------------------------
# Shared fixture factory
# ---------------------------------------------------------------------------

_HOURS_PER_YEAR = 8_760.0

def _engine(
    *,
    capital_per_mw_year: float = 45_000.0,
    variable_per_mwh: float = 55.0,
    grid_import_price: float = 120.0,
    storage_charge_price: float = 60.0,
    storage_discharge_price: float = 0.0,
    roundtrip_efficiency: float = 0.85,
) -> CostModelEngine:
    """Return a CostModelEngine with DIAG-3 documented defaults unless overridden."""
    return CostModelEngine(CostModelConfig(
        grid_import_price_per_mwh=grid_import_price,
        turbine_capital_per_mw_year=capital_per_mw_year,
        turbine_variable_per_mwh=variable_per_mwh,
        storage_roundtrip_efficiency=roundtrip_efficiency,
        storage_charge_price_per_mwh=storage_charge_price,
        storage_discharge_price_per_mwh=storage_discharge_price,
    ))


# ---------------------------------------------------------------------------
# Tests 1–3: DIAG-3 $/kWh-by-duty-cycle table
# ---------------------------------------------------------------------------

class TestDiag3DutyCycleTable:
    """Black-box verification of the $/kWh-by-duty table from DIAG-3.

    Formula (derived from cost_model.py §21.2):
        capital_$/MWh   = $45,000 / (8760 × CF)
        variable_$/MWh  = $55
        combined_$/MWh  = capital_$/MWh + variable_$/MWh
        combined_$/kWh  = combined_$/MWh / 1000

    At CF=1.0:  ($45,000/8760 + $55) / 1000 = ($5.137 + $55) / 1000 = $0.06014/kWh
    At CF=0.50: ($45,000/4380 + $55) / 1000 = ($10.27  + $55) / 1000 = $0.06527/kWh
    At CF=0.10: ($45,000/876  + $55) / 1000 = ($51.37  + $55) / 1000 = $0.10637/kWh

    Table from DIAG-3:  100% → ~$0.060,  50% → ~$0.065,  10% → ~$0.106.
    All assertions use abs=0.001/kWh tolerance (±$1/MWh).

    Capacity factor == duty fraction for a full-year run (run_hours = 8760).
    """

    RATED_MW = 10.0  # 10 MW turbine; scales out — only the fraction matters

    def test_combined_cost_per_kwh_at_100pct_duty(self) -> None:
        """100% duty (baseload): combined ≈ $0.060/kWh per DIAG-3 table."""
        generation_mwh = self.RATED_MW * _HOURS_PER_YEAR  # full output, full year

        result = _engine().compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=generation_mwh,
            storage_charge_mwh=0.0,
            run_duration_hours=_HOURS_PER_YEAR,
            turbine_rated_mw=self.RATED_MW,
        )

        cost_per_kwh = result.generation_cost / (generation_mwh * 1_000.0)
        assert cost_per_kwh == pytest.approx(0.060, abs=0.001), (
            f"100% duty: expected ~$0.060/kWh from DIAG-3 table, "
            f"got ${cost_per_kwh:.4f}/kWh  "
            f"(generation_cost=${result.generation_cost:,.2f} over "
            f"{generation_mwh:,.0f} MWh)"
        )
        # duty fraction output must also reflect 100%
        assert result.generation_duty_fraction == pytest.approx(1.0, abs=1e-6)

    def test_combined_cost_per_kwh_at_50pct_duty(self) -> None:
        """50% duty (half-load peaker): combined ≈ $0.065/kWh per DIAG-3 table."""
        generation_mwh = self.RATED_MW * _HOURS_PER_YEAR * 0.50

        result = _engine().compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=generation_mwh,
            storage_charge_mwh=0.0,
            run_duration_hours=_HOURS_PER_YEAR,
            turbine_rated_mw=self.RATED_MW,
        )

        cost_per_kwh = result.generation_cost / (generation_mwh * 1_000.0)
        assert cost_per_kwh == pytest.approx(0.065, abs=0.001), (
            f"50% duty: expected ~$0.065/kWh from DIAG-3 table, "
            f"got ${cost_per_kwh:.4f}/kWh"
        )
        assert result.generation_duty_fraction == pytest.approx(0.50, abs=1e-6)

    def test_combined_cost_per_kwh_at_10pct_duty(self) -> None:
        """10% duty (bridging/staging profile): combined ≈ $0.106/kWh per DIAG-3 table.

        This is the most operationally relevant row — the typical deployment profile
        for this system.  The old "$0.005–$0.010/kWh" figure that DIAG-3 corrected
        omitted the $55/MWh variable component and assumed an unrealistically high
        capacity factor.  This test would have caught that error.
        """
        generation_mwh = self.RATED_MW * _HOURS_PER_YEAR * 0.10

        result = _engine().compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=generation_mwh,
            storage_charge_mwh=0.0,
            run_duration_hours=_HOURS_PER_YEAR,
            turbine_rated_mw=self.RATED_MW,
        )

        cost_per_kwh = result.generation_cost / (generation_mwh * 1_000.0)
        assert cost_per_kwh == pytest.approx(0.106, abs=0.001), (
            f"10% duty: expected ~$0.106/kWh from DIAG-3 table, "
            f"got ${cost_per_kwh:.4f}/kWh — "
            f"if this returns ~$0.005–$0.010 the variable component is being ignored"
        )
        assert result.generation_duty_fraction == pytest.approx(0.10, abs=1e-6)


# ---------------------------------------------------------------------------
# Test 4: Capital cost is invariant to how much the turbine generates
# ---------------------------------------------------------------------------

class TestCapitalDutyInvariance:
    """Capital is owed regardless of generation — only rated_mw and run_hours drive it.

    Running the turbine half as hard for the same run period does not halve the
    ownership cost.  The variable portion does halve; capital does not.
    This is the economic mechanic that makes low-duty deployment expensive per kWh.
    """

    def test_capital_portion_unchanged_when_generation_halved(self) -> None:
        """Halving generation_mwh does not change the capital portion."""
        RATED_MW   = 5.0
        RUN_HOURS  = 720.0   # 30-day run

        # High-duty run
        r_high = _engine().compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=RATED_MW * RUN_HOURS * 0.80,   # 80% duty
            storage_charge_mwh=0.0,
            run_duration_hours=RUN_HOURS,
            turbine_rated_mw=RATED_MW,
        )

        # Low-duty run — same turbine, same period, half the output
        r_low = _engine().compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=RATED_MW * RUN_HOURS * 0.40,   # 40% duty
            storage_charge_mwh=0.0,
            run_duration_hours=RUN_HOURS,
            turbine_rated_mw=RATED_MW,
        )

        # Expected capital: $45,000/MW·yr × 5 MW × (720 / 8760)
        expected_capital = 45_000.0 * RATED_MW * (RUN_HOURS / _HOURS_PER_YEAR)

        # Extract variable portions and derive implied capital for each run
        gen_mwh_high = RATED_MW * RUN_HOURS * 0.80
        gen_mwh_low  = RATED_MW * RUN_HOURS * 0.40
        implied_capital_high = r_high.generation_cost - gen_mwh_high * 55.0
        implied_capital_low  = r_low.generation_cost  - gen_mwh_low  * 55.0

        assert implied_capital_high == pytest.approx(expected_capital, rel=1e-6), (
            f"High-duty run: implied capital ${implied_capital_high:,.2f} "
            f"!= expected ${expected_capital:,.2f}"
        )
        assert implied_capital_low == pytest.approx(expected_capital, rel=1e-6), (
            f"Low-duty run: capital must be identical regardless of generation; "
            f"got ${implied_capital_low:,.2f}, expected ${expected_capital:,.2f}"
        )
        # The difference between the two total generation_costs is purely variable
        variable_delta = (gen_mwh_high - gen_mwh_low) * 55.0
        assert (r_high.generation_cost - r_low.generation_cost) == pytest.approx(
            variable_delta, rel=1e-6
        ), (
            "Cost difference between high- and low-duty runs must equal "
            "the variable cost of the additional MWh, nothing else"
        )


# ---------------------------------------------------------------------------
# Test 5: Duty fraction output is computed from the inputs, not an alias
# ---------------------------------------------------------------------------

class TestDutyFractionOutput:
    """generation_duty_fraction reflects the scenario's actual capacity factor."""

    def test_duty_fraction_is_computed_not_assumed(self) -> None:
        """Verify generation_duty_fraction = generation_mwh / (rated_mw × run_hours)."""
        RATED_MW       = 8.0
        RUN_HOURS      = 500.0
        GENERATION_MWH = 200.0   # 200 / (8 × 500) = 0.05 = 5% duty

        result = _engine().compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=GENERATION_MWH,
            storage_charge_mwh=0.0,
            run_duration_hours=RUN_HOURS,
            turbine_rated_mw=RATED_MW,
        )

        expected_duty = GENERATION_MWH / (RATED_MW * RUN_HOURS)   # = 0.05
        assert result.generation_duty_fraction == pytest.approx(expected_duty, rel=1e-6), (
            f"generation_duty_fraction should be {expected_duty:.4f} "
            f"({GENERATION_MWH} MWh / ({RATED_MW} MW × {RUN_HOURS} h)), "
            f"got {result.generation_duty_fraction:.6f}"
        )

    def test_duty_fraction_capped_at_1_when_generation_exceeds_nameplate(self) -> None:
        """generation_duty_fraction is clamped to 1.0; never exceeds 100%."""
        RATED_MW       = 5.0
        RUN_HOURS      = 100.0
        GENERATION_MWH = RATED_MW * RUN_HOURS * 1.5   # 150% — physically impossible but defensive

        result = _engine().compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=GENERATION_MWH,
            storage_charge_mwh=0.0,
            run_duration_hours=RUN_HOURS,
            turbine_rated_mw=RATED_MW,
        )

        assert result.generation_duty_fraction <= 1.0, (
            f"duty fraction must be clamped to ≤1.0; got {result.generation_duty_fraction}"
        )
        assert result.generation_duty_fraction == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 6: Accounting identity — total is the sum of its parts
# ---------------------------------------------------------------------------

class TestAccountingIdentity:
    """total_cost == grid_import_cost + generation_cost + storage_cost.

    Tests with all three streams active simultaneously.  If any stream is
    double-counted or omitted, the identity breaks.
    """

    def test_total_cost_equals_sum_of_components(self) -> None:
        """total_cost is the arithmetic sum of the three cost streams."""
        result = _engine(
            grid_import_price=130.0,
            storage_charge_price=65.0,
            roundtrip_efficiency=0.90,
        ).compute_run_cost(
            grid_import_mwh=50.0,
            generation_mwh=30.0,
            storage_charge_mwh=20.0,
            run_duration_hours=24.0,
            turbine_rated_mw=5.0,
        )

        expected_total = (
            result.grid_import_cost
            + result.generation_cost
            + result.storage_cost
        )
        assert result.total_cost == pytest.approx(expected_total, rel=1e-9), (
            f"total_cost {result.total_cost:.4f} != "
            f"grid {result.grid_import_cost:.4f} + "
            f"gen {result.generation_cost:.4f} + "
            f"storage {result.storage_cost:.4f} = {expected_total:.4f}"
        )


# ---------------------------------------------------------------------------
# Test 7: Round-trip storage loss adds the correct additional cost
# ---------------------------------------------------------------------------

class TestStorageRoundTripLoss:
    """The round-trip loss (charge × (1 − eff)) is billed at discharge_price.

    With discharge_price = $0 (BESS default), the loss is a physical waste but
    carries no extra dollar cost — only charge_mwh × charge_price is billed.
    With a non-zero discharge_price the loss becomes a real cost line item.
    """

    def test_loss_cost_is_zero_when_discharge_price_is_zero(self) -> None:
        """BESS default: discharge is negligible-cost; only charge price matters."""
        CHARGE_MWH     = 100.0
        CHARGE_PRICE   = 60.0
        EFFICIENCY     = 0.85

        result = _engine(
            storage_charge_price=CHARGE_PRICE,
            storage_discharge_price=0.0,
            roundtrip_efficiency=EFFICIENCY,
        ).compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=0.0,
            storage_charge_mwh=CHARGE_MWH,
            run_duration_hours=1.0,
            turbine_rated_mw=0.0,
        )

        expected_storage_cost = CHARGE_MWH * CHARGE_PRICE  # = $6,000
        assert result.storage_cost == pytest.approx(expected_storage_cost, rel=1e-9), (
            f"With discharge_price=$0, storage_cost must be "
            f"charge_mwh × charge_price = ${expected_storage_cost:,.2f}; "
            f"got ${result.storage_cost:,.2f}"
        )

    def test_loss_cost_is_nonzero_when_discharge_price_is_nonzero(self) -> None:
        """Non-zero discharge price: round-trip loss is billed as an additional cost."""
        CHARGE_MWH        = 100.0
        CHARGE_PRICE      = 60.0
        DISCHARGE_PRICE   = 10.0
        EFFICIENCY        = 0.85
        LOSS_MWH          = CHARGE_MWH * (1.0 - EFFICIENCY)   # = 15 MWh

        result = _engine(
            storage_charge_price=CHARGE_PRICE,
            storage_discharge_price=DISCHARGE_PRICE,
            roundtrip_efficiency=EFFICIENCY,
        ).compute_run_cost(
            grid_import_mwh=0.0,
            generation_mwh=0.0,
            storage_charge_mwh=CHARGE_MWH,
            run_duration_hours=1.0,
            turbine_rated_mw=0.0,
        )

        expected_storage_cost = (
            CHARGE_MWH * CHARGE_PRICE
            + LOSS_MWH * DISCHARGE_PRICE
        )  # 100×$60 + 15×$10 = $6,150
        assert result.storage_cost == pytest.approx(expected_storage_cost, rel=1e-9), (
            f"With discharge_price=${DISCHARGE_PRICE}, storage_cost must include "
            f"round-trip loss ({LOSS_MWH:.0f} MWh × ${DISCHARGE_PRICE}); "
            f"expected ${expected_storage_cost:,.2f}, got ${result.storage_cost:,.2f}"
        )


# ---------------------------------------------------------------------------
# Test 8: Season boundary months
# ---------------------------------------------------------------------------

class TestSeasonBoundaries:
    """season_from_month() at the two critical edges: May/June and September/October.

    The docstring specifies:
      Summer = months 6–9
      Winter = months 10–12 and 1–5

    May (5) and October (10) are winter; June (6) and September (9) are summer.
    An off-by-one error at either boundary produces wrong TOU pricing for an
    entire calendar month.
    """

    @pytest.mark.parametrize("month,expected_season", [
        (5,  "winter"),   # May — last winter month before summer begins
        (6,  "summer"),   # June — first summer month
        (9,  "summer"),   # September — last summer month
        (10, "winter"),   # October — first winter month after summer ends
        # Inner months for sanity
        (1,  "winter"),
        (7,  "summer"),
        (12, "winter"),
    ])
    def test_season_from_month_boundary_and_core(
        self, month: int, expected_season: str
    ) -> None:
        assert season_from_month(month) == expected_season, (
            f"season_from_month({month}) returned {season_from_month(month)!r}, "
            f"expected {expected_season!r}"
        )

    def test_season_boundary_drives_different_tou_rates(self) -> None:
        """Season change at June/May boundary produces a rate difference, not equality.

        Verifies that the season boundary is load-bearing for pricing — not just
        a label that's ignored downstream.
        """
        PEAK_HOUR = 17   # peak hour in both seasons

        summer_rate, summer_note = pge_price_for_period(PEAK_HOUR, month=6)  # June peak
        winter_rate, winter_note = pge_price_for_period(PEAK_HOUR, month=5)  # May peak

        assert summer_rate != pytest.approx(winter_rate), (
            f"Summer peak ({summer_rate}) and winter peak ({winter_rate}) at hour={PEAK_HOUR} "
            f"must differ; identical rates would mean the season boundary has no pricing effect"
        )
        assert "summer" in summer_note.lower(), (
            f"Cost basis note for month=6 should mention 'summer'; got {summer_note!r}"
        )
        assert "winter" in winter_note.lower(), (
            f"Cost basis note for month=5 should mention 'winter'; got {winter_note!r}"
        )


# ---------------------------------------------------------------------------
# Test 9: All three summer TOU bands return catalogue-exact rates
# ---------------------------------------------------------------------------

class TestSummerTOUBands:
    """pge_price_for_period() covers all three summer bands with exact catalogue values.

    Catalogue values confirmed from live site_parameters (2026-08-15):
      peak         = $177.02/MWh  (hours 16–20)
      part-peak    = $142.27/MWh  (hours 14–15 and 21–22)
      off-peak     = $114.82/MWh  (all other summer hours)

    One hour is sampled from each band; the note string is also validated so a
    catalogue key rename that produces a wrong note would be caught separately
    from a rate regression.
    """

    SUMMER_MONTH = 8   # August — unambiguously summer

    def test_summer_peak_rate(self) -> None:
        rate, note = pge_price_for_period(hour_of_day=18, month=self.SUMMER_MONTH)
        assert rate == pytest.approx(177.02, abs=0.01), (
            f"Summer peak (hour=18, month={self.SUMMER_MONTH}): "
            f"expected $177.02/MWh, got ${rate:.2f}/MWh"
        )
        assert "summer peak" in note.lower(), f"Note should mention 'summer peak': {note!r}"

    def test_summer_part_peak_rate_hour_14(self) -> None:
        rate, note = pge_price_for_period(hour_of_day=14, month=self.SUMMER_MONTH)
        assert rate == pytest.approx(142.27, abs=0.01), (
            f"Summer part-peak (hour=14, month={self.SUMMER_MONTH}): "
            f"expected $142.27/MWh, got ${rate:.2f}/MWh"
        )
        assert "part-peak" in note.lower() or "part_peak" in note.lower(), (
            f"Note should mention part-peak: {note!r}"
        )

    def test_summer_part_peak_rate_hour_22(self) -> None:
        """Part-peak wraps to hours 21–22 on the far side of the peak window."""
        rate, note = pge_price_for_period(hour_of_day=22, month=self.SUMMER_MONTH)
        assert rate == pytest.approx(142.27, abs=0.01), (
            f"Summer part-peak (hour=22, month={self.SUMMER_MONTH}): "
            f"expected $142.27/MWh, got ${rate:.2f}/MWh"
        )

    def test_summer_off_peak_rate(self) -> None:
        rate, note = pge_price_for_period(hour_of_day=2, month=self.SUMMER_MONTH)
        assert rate == pytest.approx(114.82, abs=0.01), (
            f"Summer off-peak (hour=2, month={self.SUMMER_MONTH}): "
            f"expected $114.82/MWh, got ${rate:.2f}/MWh"
        )
        assert "off-peak" in note.lower() or "off_peak" in note.lower(), (
            f"Note should mention off-peak: {note!r}"
        )

    def test_summer_rates_are_strictly_ordered(self) -> None:
        """Peak > part-peak > off-peak — rate ordering must hold across seasons.

        If any inversion exists the merit-order dispatch will prefer the wrong source.
        """
        peak,      _ = pge_price_for_period(hour_of_day=17, month=self.SUMMER_MONTH)
        part_peak, _ = pge_price_for_period(hour_of_day=15, month=self.SUMMER_MONTH)
        off_peak,  _ = pge_price_for_period(hour_of_day=3,  month=self.SUMMER_MONTH)

        assert peak > part_peak > off_peak, (
            f"Expected peak ({peak}) > part_peak ({part_peak}) > off_peak ({off_peak}); "
            f"rate ordering is inverted"
        )


# ---------------------------------------------------------------------------
# Test 10: Winter super off-peak requires BOTH month AND hour to qualify
# ---------------------------------------------------------------------------

class TestWinterSuperOffPeakBoundary:
    """Super off-peak requires months 3–5 AND hours 9–13 — both conditions must hold.

    Failing either:
      wrong month  → regular winter off-peak ($114.60) or peak ($156.32)
      wrong hour   → regular winter off-peak ($114.60) or peak ($156.32)

    This is the most complex rate boundary in the schedule.  A single-condition
    implementation (month only, or hour only) would produce wrong rates for
    roughly 5 months × 5 hours = 300 annual price decisions.
    """

    SUPER_OFF_PEAK_RATE = 58.72
    WINTER_OFF_PEAK_RATE = 114.60
    WINTER_PEAK_RATE = 156.32

    @pytest.mark.parametrize("month,hour", [
        (3,  9),   # March, first qualifying hour
        (3, 13),   # March, last qualifying hour
        (4, 11),   # April, mid window
        (5,  9),   # May, first qualifying hour
        (5, 13),   # May, last qualifying hour
    ])
    def test_super_off_peak_when_both_conditions_met(self, month: int, hour: int) -> None:
        rate, note = pge_price_for_period(hour_of_day=hour, month=month)
        assert rate == pytest.approx(self.SUPER_OFF_PEAK_RATE, abs=0.01), (
            f"pge_price_for_period(hour={hour}, month={month}): "
            f"expected super off-peak ${self.SUPER_OFF_PEAK_RATE}/MWh, "
            f"got ${rate:.2f}/MWh"
        )
        assert "super" in note.lower(), (
            f"Note should mention 'super' off-peak for month={month}, hour={hour}: {note!r}"
        )

    @pytest.mark.parametrize("month,hour,expected_rate,label", [
        # Month outside 3–5 (February, even though hour qualifies)
        (2, 11, 114.60, "Feb off-peak — month not in 3–5"),
        # Month outside 3–5 (June is summer, off-peak)
        (6,  11, 114.82, "June off-peak — summer season, not winter"),
        # Hour outside 9–13 (month qualifies, but hour is 14 → regular off-peak)
        (4, 14, 114.60, "Apr hour 14 — outside super off-peak window, falls to off-peak"),
        # Hour outside 9–13 and in peak window → winter peak
        (3, 17, 156.32, "Mar hour 17 — peak window, super off-peak does not apply"),
        # Month outside 3–5 (January) with qualifying hour → regular off-peak
        (1, 10, 114.60, "Jan off-peak — month not in 3–5"),
    ])
    def test_super_off_peak_not_applied_when_condition_fails(
        self, month: int, hour: int, expected_rate: float, label: str
    ) -> None:
        rate, _ = pge_price_for_period(hour_of_day=hour, month=month)
        assert rate == pytest.approx(expected_rate, abs=0.01), (
            f"[{label}] pge_price_for_period(hour={hour}, month={month}): "
            f"expected ${expected_rate}/MWh (not super off-peak), "
            f"got ${rate:.2f}/MWh — "
            f"super off-peak gate may be checking only month or only hour"
        )
