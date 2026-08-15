"""Tests for core.source_audit — per-tick source-level bounds audit.

Four measurement targets (per the implementation proposal):
  TP-1  A known-bad input (solar 3× rated) fires a renewable_over_rated violation.
  TN-1  A clean tick at nominal values produces zero violations.
  AGG-1 A tick where turbine+bess+fc+solar ≠ p_generation_mw fires
        generation_sum_mismatch.
  PG-1  payload guard: source_audit_violations is declared in TickPayload
        (covered by test_payload_guard.py — not repeated here).

Additional per-check tests cover every individual bound in audit_tick().
"""
from __future__ import annotations

import pytest
from core.source_audit import (
    SourceAuditTerms,
    SourceAuditResult,
    audit_tick,
    gate_run,
    _ceiling,
    _HEADROOM_FRAC,
    _HEADROOM_FLOOR_MW,
    _AGGREGATION_TOLERANCE_MW,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_terms(**overrides) -> SourceAuditTerms:
    """Return a SourceAuditTerms that should produce zero violations.

    Default values represent a 20 MW turbine + 4 MW BESS + 5 MW solar site
    operating at 50 % load — well within all bounds.
    """
    defaults = dict(
        p_renewable_mw=2.5,
        turbine_output_mw=10.0,
        bess_output_mw=1.0,
        fuel_cell_output_mw=0.0,
        p_generation_mw=13.5,   # turbine + bess + fc + solar = 10+1+0+2.5
        solar_rated_mw=5.0,
        turbine_rated_mw=20.0,
        bess_rated_mw=4.0,
        fc_rated_mw=0.0,
    )
    defaults.update(overrides)
    return SourceAuditTerms(**defaults)


def _violation_kinds(result: SourceAuditResult) -> list[str]:
    """Return the kind prefix for each violation string."""
    return [v.split(":")[0] for v in result.violations]


# ---------------------------------------------------------------------------
# TP-1: True positive — Task #403 condition (solar 3× rated)
# ---------------------------------------------------------------------------

class TestTP1_SolarOverRated:
    """Audit must fire when solar reports above its rated capacity."""

    def test_solar_3x_rated_fires_renewable_over_rated(self):
        """Exact Task #403 condition: p_renewable_mw = 3 × solar_rated_mw."""
        terms = _clean_terms(
            solar_rated_mw=5.0,
            p_renewable_mw=15.0,          # 3× rated
            p_generation_mw=26.0,          # turbine(10) + bess(1) + fc(0) + solar(15)
        )
        result = audit_tick(terms)
        assert "renewable_over_rated" in _violation_kinds(result), (
            "Expected renewable_over_rated violation for solar 3× rated"
        )

    def test_solar_at_exactly_rated_is_clean(self):
        terms = _clean_terms(
            solar_rated_mw=5.0,
            p_renewable_mw=5.0,
            p_generation_mw=16.0,
        )
        result = audit_tick(terms)
        assert "renewable_over_rated" not in _violation_kinds(result)

    def test_solar_within_headroom_is_clean(self):
        """1 % headroom must not fire."""
        solar_rated = 5.0
        ceiling = _ceiling(solar_rated)
        terms = _clean_terms(
            solar_rated_mw=solar_rated,
            p_renewable_mw=ceiling - 0.001,
            p_generation_mw=10.0 + 1.0 + 0.0 + (ceiling - 0.001),
        )
        result = audit_tick(terms)
        assert "renewable_over_rated" not in _violation_kinds(result)

    def test_solar_one_watt_above_ceiling_fires(self):
        """One watt above the ceiling must fire."""
        solar_rated = 5.0
        ceiling = _ceiling(solar_rated)
        p_ren = ceiling + 0.0001
        terms = _clean_terms(
            solar_rated_mw=solar_rated,
            p_renewable_mw=p_ren,
            p_generation_mw=10.0 + 1.0 + 0.0 + p_ren,
        )
        result = audit_tick(terms)
        assert "renewable_over_rated" in _violation_kinds(result)


# ---------------------------------------------------------------------------
# TN-1: True negative — clean scenarios produce zero violations
# ---------------------------------------------------------------------------

class TestTN1_CleanTick:
    """All sources within bounds + aggregation identity = no violations."""

    def test_clean_nominal_tick_no_violations(self):
        result = audit_tick(_clean_terms())
        assert result.violations == (), (
            f"Expected zero violations for clean tick; got: {result.violations}"
        )

    def test_zero_generation_is_clean(self):
        """All sources at zero is valid (e.g. idle tick)."""
        terms = _clean_terms(
            p_renewable_mw=0.0,
            turbine_output_mw=0.0,
            bess_output_mw=0.0,
            fuel_cell_output_mw=0.0,
            p_generation_mw=0.0,
        )
        result = audit_tick(terms)
        assert result.violations == ()

    def test_bess_discharging_at_rated_is_clean(self):
        bess_rated = 4.0
        terms = _clean_terms(
            bess_output_mw=bess_rated,
            p_generation_mw=10.0 + bess_rated + 0.0 + 2.5,
        )
        result = audit_tick(terms)
        assert result.violations == ()

    def test_bess_charging_at_rated_is_clean(self):
        """Negative bess_output_mw within rated is valid (charge)."""
        bess_rated = 4.0
        terms = _clean_terms(
            bess_output_mw=-bess_rated,
            p_generation_mw=10.0 + (-bess_rated) + 0.0 + 2.5,
        )
        result = audit_tick(terms)
        assert result.violations == ()

    def test_fuel_cell_at_rated_is_clean(self):
        fc_rated = 3.0
        terms = _clean_terms(
            fuel_cell_output_mw=fc_rated,
            fc_rated_mw=fc_rated,
            p_generation_mw=10.0 + 1.0 + fc_rated + 2.5,
        )
        result = audit_tick(terms)
        assert result.violations == ()


# ---------------------------------------------------------------------------
# AGG-1: Aggregation identity mismatch
# ---------------------------------------------------------------------------

class TestAGG1_AggregationIdentity:
    """Σ sources ≠ p_generation_mw must fire generation_sum_mismatch."""

    def test_deliberate_delta_above_tolerance_fires(self):
        """0.1 MW mismatch — well above the 100 W tolerance."""
        base = _clean_terms()
        # Tweak p_generation_mw by 0.1 MW without changing individual sources
        terms = SourceAuditTerms(
            p_renewable_mw=base.p_renewable_mw,
            turbine_output_mw=base.turbine_output_mw,
            bess_output_mw=base.bess_output_mw,
            fuel_cell_output_mw=base.fuel_cell_output_mw,
            p_generation_mw=base.p_generation_mw + 0.1,
            solar_rated_mw=base.solar_rated_mw,
            turbine_rated_mw=base.turbine_rated_mw,
            bess_rated_mw=base.bess_rated_mw,
            fc_rated_mw=base.fc_rated_mw,
        )
        result = audit_tick(terms)
        assert "generation_sum_mismatch" in _violation_kinds(result)

    def test_delta_within_tolerance_is_clean(self):
        """Float-rounding noise below 100 W must not fire."""
        base = _clean_terms()
        terms = SourceAuditTerms(
            p_renewable_mw=base.p_renewable_mw,
            turbine_output_mw=base.turbine_output_mw,
            bess_output_mw=base.bess_output_mw,
            fuel_cell_output_mw=base.fuel_cell_output_mw,
            p_generation_mw=base.p_generation_mw + (_AGGREGATION_TOLERANCE_MW * 0.5),
            solar_rated_mw=base.solar_rated_mw,
            turbine_rated_mw=base.turbine_rated_mw,
            bess_rated_mw=base.bess_rated_mw,
            fc_rated_mw=base.fc_rated_mw,
        )
        result = audit_tick(terms)
        assert "generation_sum_mismatch" not in _violation_kinds(result)

    def test_mismatch_message_contains_delta(self):
        """Violation string must mention the delta for diagnostics."""
        base = _clean_terms()
        terms = SourceAuditTerms(
            p_renewable_mw=base.p_renewable_mw,
            turbine_output_mw=base.turbine_output_mw,
            bess_output_mw=base.bess_output_mw,
            fuel_cell_output_mw=base.fuel_cell_output_mw,
            p_generation_mw=base.p_generation_mw + 5.0,
            solar_rated_mw=base.solar_rated_mw,
            turbine_rated_mw=base.turbine_rated_mw,
            bess_rated_mw=base.bess_rated_mw,
            fc_rated_mw=base.fc_rated_mw,
        )
        result = audit_tick(terms)
        mismatch_viols = [v for v in result.violations if v.startswith("generation_sum")]
        assert mismatch_viols, "generation_sum_mismatch violation missing"
        assert "delta" in mismatch_viols[0]


# ---------------------------------------------------------------------------
# Per-bound checks
# ---------------------------------------------------------------------------

class TestIndividualBounds:
    """One test per remaining bound (turbine, BESS, FC, negative checks)."""

    def test_turbine_over_rated_fires(self):
        ceil = _ceiling(20.0)
        terms = _clean_terms(
            turbine_output_mw=ceil + 0.1,
            p_generation_mw=(ceil + 0.1) + 1.0 + 0.0 + 2.5,
        )
        result = audit_tick(terms)
        assert "turbine_over_rated" in _violation_kinds(result)

    def test_turbine_negative_fires(self):
        terms = _clean_terms(
            turbine_output_mw=-0.5,
            p_generation_mw=-0.5 + 1.0 + 0.0 + 2.5,
        )
        result = audit_tick(terms)
        assert "turbine_negative" in _violation_kinds(result)

    def test_bess_over_rated_fires(self):
        bess_rated = 4.0
        ceil = _ceiling(bess_rated)
        terms = _clean_terms(
            bess_output_mw=ceil + 0.1,
            p_generation_mw=10.0 + (ceil + 0.1) + 0.0 + 2.5,
        )
        result = audit_tick(terms)
        assert "bess_over_rated" in _violation_kinds(result)

    def test_bess_charge_over_rated_fires(self):
        bess_rated = 4.0
        ceil = _ceiling(bess_rated)
        terms = _clean_terms(
            bess_output_mw=-(ceil + 0.1),
            p_generation_mw=10.0 + (-(ceil + 0.1)) + 0.0 + 2.5,
        )
        result = audit_tick(terms)
        assert "bess_charge_over_rated" in _violation_kinds(result)

    def test_fc_over_rated_fires(self):
        fc_rated = 3.0
        ceil = _ceiling(fc_rated)
        terms = _clean_terms(
            fc_rated_mw=fc_rated,
            fuel_cell_output_mw=ceil + 0.1,
            p_generation_mw=10.0 + 1.0 + (ceil + 0.1) + 2.5,
        )
        result = audit_tick(terms)
        assert "fc_over_rated" in _violation_kinds(result)

    def test_fc_negative_fires(self):
        terms = _clean_terms(
            fc_rated_mw=3.0,
            fuel_cell_output_mw=-0.1,
            p_generation_mw=10.0 + 1.0 + (-0.1) + 2.5,
        )
        result = audit_tick(terms)
        assert "fc_negative" in _violation_kinds(result)

    def test_renewable_negative_fires(self):
        terms = _clean_terms(
            p_renewable_mw=-0.1,
            p_generation_mw=10.0 + 1.0 + 0.0 + (-0.1),
        )
        result = audit_tick(terms)
        assert "renewable_negative" in _violation_kinds(result)


# ---------------------------------------------------------------------------
# gate_run
# ---------------------------------------------------------------------------

class TestGateRun:
    """gate_run(violations_per_tick) correctly gates completed runs."""

    def test_all_clean_ticks_renderable(self):
        renderable, reason, n_bad = gate_run([(), (), ()])
        assert renderable is True
        assert reason is None
        assert n_bad == 0

    def test_one_bad_tick_not_renderable(self):
        renderable, reason, n_bad = gate_run([
            (),
            ("renewable_over_rated: p_renewable_mw=15.0 MW exceeds ...",),
            (),
        ])
        assert renderable is False
        assert n_bad == 1
        assert reason is not None
        assert "renewable_over_rated" in reason

    def test_multiple_kinds_all_appear_in_reason(self):
        renderable, reason, n_bad = gate_run([
            ("renewable_over_rated: ...",),
            ("turbine_over_rated: ...",),
        ])
        assert renderable is False
        assert "renewable_over_rated" in reason
        assert "turbine_over_rated" in reason
        assert n_bad == 2

    def test_empty_sequence_renderable(self):
        renderable, reason, n_bad = gate_run([])
        assert renderable is True
        assert n_bad == 0


# ---------------------------------------------------------------------------
# TickResult integration: source_audit_violations field exists
# ---------------------------------------------------------------------------

class TestTickResultField:
    """source_audit_violations is present on TickResult with the right default."""

    def test_field_exists_with_empty_tuple_default(self):
        from core.models import TickResult, ConfidenceBand
        tick = TickResult(
            run_id="test",
            tick_index=0,
            sim_time_seconds=0.0,
            p_compute_demand_mw=5.0,
            p_cooling_demand_mw=2.0,
            p_demand_mw=7.0,
            net_demand_mw=4.5,
            turbine_output_mw=7.0,
            bess_output_mw=0.0,
            bess_soc_fraction=0.8,
            confidence=ConfidenceBand(
                point_estimate_mw=7.0,
                plus_minus_fraction=0.1,
            ),
        )
        assert hasattr(tick, "source_audit_violations")
        assert tick.source_audit_violations == ()

    def test_field_can_be_set_via_dc_replace(self):
        from dataclasses import replace
        from core.models import TickResult, ConfidenceBand
        tick = TickResult(
            run_id="test",
            tick_index=0,
            sim_time_seconds=0.0,
            p_compute_demand_mw=5.0,
            p_cooling_demand_mw=2.0,
            p_demand_mw=7.0,
            net_demand_mw=4.5,
            turbine_output_mw=7.0,
            bess_output_mw=0.0,
            bess_soc_fraction=0.8,
            confidence=ConfidenceBand(
                point_estimate_mw=7.0,
                plus_minus_fraction=0.1,
            ),
        )
        viols = ("renewable_over_rated: ...",)
        updated = replace(tick, source_audit_violations=viols)
        assert updated.source_audit_violations == viols
        # original unchanged (frozen)
        assert tick.source_audit_violations == ()
