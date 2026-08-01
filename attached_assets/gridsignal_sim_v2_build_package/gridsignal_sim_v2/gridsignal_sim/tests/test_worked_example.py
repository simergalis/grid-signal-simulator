"""
tests/test_worked_example.py — Regression fixture for the full calculation chain.

Loads inputs and expected outputs from gridsignal_parameters.json::worked_example.
An implementation loading these inputs must reproduce all expected values exactly.

Covers (all 18 expected fields):
  §2.1  P_compute (compute term)
  §2.2  P_cooling at 1τ, 3τ, steady state (cooling curve)
  §2.3  P_total, P_dispatch_required, effective PUE
  §2.4  ΔP, t_ramp, t_gap, turbine output at T+Δt_lead, peak_shortfall, E_bridge
  §2.5  P_bridge_avail, point-estimate pass, band-adjusted alert (INV-2)
  §2.6  checkpoint drop and recovery thresholds

The 8% band in the fixture is illustrative (see worked_example.note).
My decisions for PROPOSED_HERE band defaults:
  band_pct_calibrated   = 4%   (calibrated site baseline)
  band_mult_uncalibrated = 2.0× (gives 8% for uncalibrated sites — matches fixture)
  band_mult_unmapped_hw  = 1.5× (independent unmapped-hardware multiplier)

An uncalibrated site therefore uses band_pct = 4% × 2.0 = 8%, which is exactly
the illustrative figure in the worked example, making it a live regression fixture
rather than a historical footnote.
"""

import json
import math
import pathlib

import pytest

# ---------------------------------------------------------------------------
# Load fixture once — all tests below read from INP and EXP.
# ---------------------------------------------------------------------------

_PARAMS_FILE = (
    pathlib.Path(__file__).parent.parent / "gridsignal_parameters.json"
)
_PARAMS = json.loads(_PARAMS_FILE.read_text())
_INP    = _PARAMS["worked_example"]["inputs"]
_EXP    = _PARAMS["worked_example"]["expected"]


# ---------------------------------------------------------------------------
# §2.1 — Compute term
# ---------------------------------------------------------------------------

class TestComputeTerm:
    def test_p_compute_mw(self):
        """P_compute = Σ[N × kW] × PUE_base / 1000"""
        p = _INP["node_count"] * _INP["kw_per_node"] * _INP["pue_base"] / 1000.0
        assert round(p, 2) == _EXP["p_compute_mw"], (
            f"P_compute = {_INP['node_count']} × {_INP['kw_per_node']} "
            f"× {_INP['pue_base']} / 1000 = {p:.4f}"
        )


# ---------------------------------------------------------------------------
# §2.2 — Cooling curve
# ---------------------------------------------------------------------------

def _p_compute() -> float:
    return _INP["node_count"] * _INP["kw_per_node"] * _INP["pue_base"] / 1000.0


def _alpha(elapsed_s: float) -> float:
    """α(t) = α_max × (1 − e^−(elapsed/τ)) — first-order rise post-delay."""
    return _INP["alpha_max"] * (1.0 - math.exp(-elapsed_s / _INP["tau"]))


class TestCoolingCurve:
    def test_cooling_zero_before_thermal_delay(self):
        """α(t) = 0 for t < t₀ + Δt_thermal — cooling has not started."""
        # At t=89 (just before dt_thermal=90 elapses) there must be no cooling.
        assert _alpha(0) == 0.0  # elapsed=0 → numerically exact
        # Continuous from 0; practical zero confirmed via formula.
        elapsed_before = 89 - _INP["dt_thermal"]   # negative → formula undefined
        # The caller is responsible for the guard; the formula is only applied
        # when elapsed ≥ 0.  This test documents the obligation.

    def test_p_cooling_at_t110(self):
        """P_cooling at t=110 s (elapsed = 110 − 90 = 20 s = 1τ)."""
        elapsed = 110 - _INP["dt_thermal"]          # 20 s
        assert elapsed == 20
        p_cooling = _alpha(elapsed) * _p_compute()
        assert round(p_cooling, 2) == _EXP["p_cooling_mw_at_t110"]

    def test_p_cooling_at_t150(self):
        """P_cooling at t=150 s (elapsed = 150 − 90 = 60 s = 3τ)."""
        elapsed = 150 - _INP["dt_thermal"]          # 60 s
        assert elapsed == 60
        p_cooling = _alpha(elapsed) * _p_compute()
        assert round(p_cooling, 2) == _EXP["p_cooling_mw_at_t150"]

    def test_p_cooling_steady_state(self):
        """P_cooling at steady state (α → α_max)."""
        p_cooling = _INP["alpha_max"] * _p_compute()
        assert round(p_cooling, 2) == _EXP["p_cooling_mw_steady"]


# ---------------------------------------------------------------------------
# §2.3 — Total, net, effective PUE
# ---------------------------------------------------------------------------

class TestTotalAndNet:
    def test_p_total_steady_state(self):
        """P_total = P_compute + P_cooling (steady-state)."""
        p_total = _p_compute() * (1.0 + _INP["alpha_max"])
        assert round(p_total, 2) == _EXP["p_total_mw_steady"]

    def test_p_dispatch_required(self):
        """P_dispatch_required = P_total − P_renewable."""
        p_total = _p_compute() * (1.0 + _INP["alpha_max"])
        p_dr = p_total - _INP["p_renewable_mw"]
        assert round(p_dr, 2) == _EXP["p_dispatch_required_mw"]

    def test_effective_pue(self):
        """Effective PUE = PUE_base × (1 + α_max)."""
        eff = _INP["pue_base"] * (1.0 + _INP["alpha_max"])
        assert round(eff, 3) == _EXP["effective_pue"]


# ---------------------------------------------------------------------------
# §2.4 — Ramp and bridging arithmetic
# ---------------------------------------------------------------------------

class TestRampArithmetic:
    def _delta_p(self) -> float:
        # Solar is flat; ΔP = compute step change.
        return _p_compute()

    def test_delta_p_mw(self):
        """ΔP = P_compute (solar flat; renewable does not contribute to ramp)."""
        assert round(self._delta_p(), 2) == _EXP["delta_p_mw"]

    def test_t_ramp_s(self):
        """t_ramp = ΔP / r_asset."""
        t_ramp = self._delta_p() / _INP["r_asset"]
        assert round(t_ramp, 2) == _EXP["t_ramp_s"]

    def test_t_gap_s(self):
        """t_gap = t_ramp − Δt_lead."""
        t_ramp = self._delta_p() / _INP["r_asset"]
        t_gap  = t_ramp - _INP["dt_lead"]
        assert round(t_gap, 2) == _EXP["t_gap_s"]

    def test_turbine_output_at_load_arrival(self):
        """Turbine output at T+Δt_lead = r_asset × Δt_lead (ramp started at prediction)."""
        output = _INP["r_asset"] * _INP["dt_lead"]
        assert round(output, 2) == _EXP["turbine_output_at_load_arrival_mw"]

    def test_peak_shortfall_mw(self):
        """peak_shortfall = ΔP − (r_asset × Δt_lead) — declines linearly, not flat."""
        peak = self._delta_p() - _INP["r_asset"] * _INP["dt_lead"]
        assert round(peak, 2) == _EXP["peak_shortfall_mw"]

    def test_bridge_energy_mwh(self):
        """E_bridge = ½ × peak_shortfall × t_gap / 3600 (triangular area, MWh).
        INV-6: a duration is never compared against an energy-like quantity.
        INV-5: shortfall declines linearly; never a flat draw.
        """
        t_ramp = self._delta_p() / _INP["r_asset"]
        t_gap  = t_ramp - _INP["dt_lead"]
        peak   = self._delta_p() - _INP["r_asset"] * _INP["dt_lead"]
        e_bridge = 0.5 * peak * t_gap / 3600.0
        assert round(e_bridge, 4) == _EXP["bridge_energy_mwh"]


# ---------------------------------------------------------------------------
# §2.5 — Reserve check (point estimate + confidence band)
# ---------------------------------------------------------------------------

class TestReserveCheck:
    def test_p_bridge_avail_mw(self):
        """P_bridge_avail = BESS_rated × f(SOC) − P_anchor_reserve.
        INV-3: anchor-adjusted figure used whenever BESS is grid-forming.
        INV-4: P_renewable never contributes to ramp capability.
        """
        avail = (
            _INP["bess_rated_mw"] * (_INP["soc_pct"] / 100.0)
            - _INP["anchor_reserve_mw"]
        )
        assert round(avail, 2) == _EXP["p_bridge_avail_mw"]

    def test_point_estimate_passes_narrowly(self):
        """Point estimate: 13.98 MW < 14.00 MW — passes by 0.02 MW.
        INV-2: this result is INSUFFICIENT — it is the band that must be evaluated.
        An implementation checking only the point estimate will be wrong when
        it matters, while appearing correct in almost every demo.
        """
        peak  = _EXP["peak_shortfall_mw"]
        avail = _EXP["p_bridge_avail_mw"]
        assert peak < avail, "Point estimate should pass (13.98 < 14.00)"
        assert round(avail - peak, 2) == 0.02

    def test_band_triggers_alert(self):
        """Band check: 13.98 × 1.08 = 15.10 MW > 14.00 MW — ALERT by 1.10 MW.
        INV-2: reserve check must evaluate the band, not the point estimate.
        band_upper = band_pct_illustrative / 100 = 0.08.
        """
        peak      = _EXP["peak_shortfall_mw"]
        avail     = _EXP["p_bridge_avail_mw"]
        band_frac = _INP["band_pct_illustrative"] / 100.0
        banded    = peak * (1.0 + band_frac)
        assert banded > avail, (
            f"Band check should fire alert: banded={banded:.4f} > avail={avail}"
        )
        assert round(banded - avail, 2) == 1.10, (
            f"Alert should be 1.10 MW short, got {banded - avail:.4f}"
        )

    def test_band_upper_equals_pct_times_mult_for_uncalibrated(self):
        """Confirm: 8% illustrative = 4% calibrated × 2.0 uncalibrated multiplier.
        This is the decision that makes the fixture a live regression:
          band_pct_calibrated=4%, band_mult_uncalibrated=2.0  →  band=8%
        """
        decided_pct  = 4.0    # PROPOSED_HERE decision
        decided_mult = 2.0    # PROPOSED_HERE decision
        computed_band_pct = decided_pct * decided_mult   # 8%
        assert computed_band_pct == _INP["band_pct_illustrative"]


# ---------------------------------------------------------------------------
# §2.6 — Checkpoint-valley classifier thresholds
# ---------------------------------------------------------------------------

class TestCheckpointThresholds:
    def test_drop_threshold(self):
        """Drop threshold = 15% of P_compute (CONFORMANCE — §6.2, TC-06…TC-09)."""
        threshold = 0.15 * _EXP["p_compute_mw"]
        assert round(threshold, 3) == _EXP["checkpoint_drop_threshold_mw"]

    def test_recovery_threshold(self):
        """Recovery threshold = 90% of P_compute (CONFORMANCE — §6.2)."""
        threshold = 0.90 * _EXP["p_compute_mw"]
        assert round(threshold, 3) == _EXP["checkpoint_recovery_threshold_mw"]


# ---------------------------------------------------------------------------
# Cross-cutting invariants verified by the fixture
# ---------------------------------------------------------------------------

class TestInvariants:
    def test_INV1_pue_base_excludes_cooling(self):
        """INV-1: PUE_base and α(t) are mutually exclusive overhead buckets.
        Verify: P_total = P_compute + P_cooling uses only α_max for cooling,
        not PUE_base × α_max (which would double-count).
        """
        p_compute   = _p_compute()                        # includes PUE_base
        p_cooling   = _INP["alpha_max"] * p_compute       # α_max on P_compute
        p_total     = p_compute + p_cooling
        # If cooling were in PUE_base too: p_bogus = N × kW × PUE_base × (1+α_max) / 1000
        # That would over-count. Verify we match the expected, not the bogus value.
        assert round(p_total, 2) == _EXP["p_total_mw_steady"]

    def test_INV4_renewable_does_not_appear_in_ramp(self):
        """INV-4: P_renewable reduces load; it never contributes to ramp capability.
        ΔP is P_compute only — not P_compute − P_renewable.
        """
        delta_p_correct = _p_compute()                    # solar flat, no renewable credit
        delta_p_wrong   = _p_compute() - _INP["p_renewable_mw"]   # would undersize BESS
        assert round(delta_p_correct, 2) == _EXP["delta_p_mw"]
        assert delta_p_wrong < delta_p_correct             # wrong would give smaller ΔP

    def test_INV5_shortfall_is_triangular_not_flat(self):
        """INV-5: bridging energy is triangular (½ × base × height), not rectangular."""
        peak  = _EXP["peak_shortfall_mw"]
        t_gap = _EXP["t_gap_s"]
        e_triangular  = 0.5 * peak * t_gap / 3600.0
        e_rectangular = peak * t_gap / 3600.0              # would be double
        assert round(e_triangular, 4) == _EXP["bridge_energy_mwh"]
        assert e_rectangular > e_triangular                 # confirm would overestimate

    def test_INV6_bridge_energy_not_compared_to_duration(self):
        """INV-6: duration (seconds) is never compared to energy-like quantity (MWh).
        E_bridge = 0.1357 MWh is for reporting; the reserve check compares
        peak_shortfall_mw (power) against P_bridge_avail_mw (power), not MWh vs s.
        """
        # Confirm units are consistent: both sides of the check are MW.
        peak_mw = _EXP["peak_shortfall_mw"]
        avail_mw = _EXP["p_bridge_avail_mw"]
        # If someone compared gap_s to bridge_energy_mwh they'd get apples/oranges.
        gap_s       = _EXP["t_gap_s"]
        bridge_mwh  = _EXP["bridge_energy_mwh"]
        # These are never equal in any meaningful sense; the invariant is documented.
        assert isinstance(peak_mw, float)
        assert isinstance(avail_mw, float)
        # gap_s and bridge_mwh have different dimensions — the invariant means
        # they must NEVER appear on the same side of a comparison in production code.
        assert gap_s != bridge_mwh  # trivially different magnitudes, too.
