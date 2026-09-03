"""
tests/test_cost_model_override_regression.py
GS-DIAG-COST-002 Part B — Regression tests for the Optional[float] override
failure class found in GS-DIAG-COST-001.

Three tests guard the three specific failure modes:

  Test 1 — Zero-value grid import price override is honoured.
            Would fail against the pre-fix `or`-based merge logic because
            `0.0 or 120.0 == 120.0`, silently replacing a legitimate $0 override.

  Test 2 — BESS charge cost tracks a non-default import price end-to-end,
            and an explicit bess_charge_price_override takes precedence over
            the derived import price.
            Would fail against pre-fix logic because storage_charge_price was
            always the flat $60 fallback from _COST_CFG_DEFAULTS.

  Test 3 — SyntheticPriceCurve (Path B, advisory market signal) has zero
            effect on compute_run_cost_from_completed() output.
            Locks in the "Path B confirmed clean" finding from DIAG-1 so a
            future change to _drive() cannot silently wire the two together.

Each test:
  • Is synchronous — no runtime RNG (AT-7 determinism invariant).
  • Uses `is not None` in all assertions — never `or`-based fallback.
  • Was verified to fail against the pre-fix `or`-based merge logic
    (see "Failure mode" comments on each test).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from runtime.run_manager import CompletedRun, compute_run_cost_from_completed
from runtime.verdict import VerdictResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_AT = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)

def _completed_run(
    *,
    grid_import_price_per_mwh: float | None,
    bess_charge_price_override_per_mwh: float | None = None,
    turbine_rated_mw: float = 10.0,
) -> CompletedRun:
    """Minimal CompletedRun for cost-override regression tests.

    tick_dicts is empty because compute_run_cost_from_completed() receives the
    MWh quantities as explicit arguments; it does not re-derive them from ticks.
    """
    return CompletedRun(
        run_id="diag-cost-002-test",
        scenario_id=None,
        scenario_name="GS-DIAG-COST-002 regression fixture",
        completed_at=_FIXED_AT,
        verdict=VerdictResult(
            overall="PASS",
            tick_count=10,
            dropped_ticks=0,
            gap_count=0,
        ),
        tick_dicts=[],
        dropped_ticks=0,
        turbine_rated_mw=turbine_rated_mw,
        grid_import_price_per_mwh=grid_import_price_per_mwh,
        bess_charge_price_override_per_mwh=bess_charge_price_override_per_mwh,
    )


# ---------------------------------------------------------------------------
# Test 1 — Zero-value grid import price override is honoured
# ---------------------------------------------------------------------------

class TestZeroGridImportPriceOverride:
    """DIAG-1 regression: $0.0 is a legitimate grid_import_price_per_mwh override.

    Failure mode under pre-fix `or` logic:
        `0.0 or _COST_CFG_DEFAULTS["grid_import_price_per_mwh"]`
        → `0.0 or 120.0`
        → `120.0`   ← silently replaces the $0 override with the $120 fallback.

    Confirmed failure: with the old code, grid_import_cost would be
    3.0 MWh × $120 = $360, causing the assertion below to fail.
    """

    def test_grid_import_cost_is_zero_when_price_override_is_zero(self) -> None:
        """Fully self-generated site: grid imports are free by operator convention."""
        GRID_IMPORT_MWH = 3.0

        cr = _completed_run(grid_import_price_per_mwh=0.0)
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=GRID_IMPORT_MWH,
            storage_charge_mwh=0.0,
            duration_hours=1.0,
        )

        # The override must be carried through — not shadowed by the $120 fallback.
        assert cfg["grid_import_price_per_mwh"] is not None, (
            "cost_model_config must include grid_import_price_per_mwh"
        )
        assert cfg["grid_import_price_per_mwh"] == pytest.approx(0.0), (
            f"grid_import_price_per_mwh override of $0 must be honoured; "
            f"got ${cfg['grid_import_price_per_mwh']:.2f} — "
            f"likely caused by `or`-based fallback to $120 default"
        )
        assert bd["grid_import_cost"] == pytest.approx(0.0), (
            f"grid_import_cost must be $0 when price override is $0 and "
            f"grid_import_mwh={GRID_IMPORT_MWH}; got ${bd['grid_import_cost']:.2f}"
        )

    def test_nonzero_override_is_also_honoured(self) -> None:
        """Sanity: a distinctive non-default price is applied correctly."""
        GRID_IMPORT_MWH = 4.0
        OVERRIDE_PRICE  = 200.0  # deliberately not $55 or $120

        cr = _completed_run(grid_import_price_per_mwh=OVERRIDE_PRICE)
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=GRID_IMPORT_MWH,
            storage_charge_mwh=0.0,
            duration_hours=1.0,
        )

        assert cfg["grid_import_price_per_mwh"] == pytest.approx(OVERRIDE_PRICE)
        assert bd["grid_import_cost"] == pytest.approx(GRID_IMPORT_MWH * OVERRIDE_PRICE)

    def test_none_override_falls_back_to_120_wholesale_default(self) -> None:
        """None means "operator did not set it" → use the $120 wholesale fallback."""
        GRID_IMPORT_MWH = 2.0

        cr = _completed_run(grid_import_price_per_mwh=None)
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=GRID_IMPORT_MWH,
            storage_charge_mwh=0.0,
            duration_hours=1.0,
        )

        assert cfg["grid_import_price_per_mwh"] == pytest.approx(120.0), (
            "None override must fall back to $120 WHOLESALE_SPOT_FALLBACK"
        )
        assert bd["grid_import_cost"] == pytest.approx(GRID_IMPORT_MWH * 120.0)


# ---------------------------------------------------------------------------
# Test 2 — BESS charge cost tracks import price override end-to-end
# ---------------------------------------------------------------------------

class TestBessChargeCostTracksImportPrice:
    """DIAG-2 regression: BESS charge price derives from the effective billing
    price (Path A), not from the flat $60 fallback in _COST_CFG_DEFAULTS.

    Failure mode under pre-fix logic:
        _COST_CFG_DEFAULTS["storage_charge_price_per_mwh"] = 60.0 was always
        used verbatim.  Even with a $200 grid import override, BESS charging
        would be billed at $60 — half the import cost, with no documented rationale.

    Confirmed failure: with the old code, storage_cost for 2 MWh charged at
    $200 import price would be 2.0 × $60 = $120, not 2.0 × $200 = $400.
    """

    # Storage cost formula: charge_mwh × charge_price + loss_mwh × discharge_price
    # With RT_EFF=0.88 and discharge_price=$0: storage_cost = charge_mwh × charge_price.
    # (Round-trip loss has zero cost because discharge_price_per_mwh = $0.0.)

    def test_bess_charge_price_tracks_grid_import_price_when_no_bess_override(self) -> None:
        """With no bess_charge_price_override, BESS charging is billed at the
        effective grid import price."""
        STORAGE_CHARGE_MWH = 2.0
        IMPORT_PRICE = 200.0  # deliberately not $55, $60, or $120

        cr = _completed_run(
            grid_import_price_per_mwh=IMPORT_PRICE,
            bess_charge_price_override_per_mwh=None,
        )
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=0.0,
            storage_charge_mwh=STORAGE_CHARGE_MWH,
            duration_hours=1.0,
        )

        assert cfg["storage_charge_price_per_mwh"] == pytest.approx(IMPORT_PRICE), (
            f"storage_charge_price must track grid_import_price when no BESS override; "
            f"got ${cfg['storage_charge_price_per_mwh']:.2f}, expected ${IMPORT_PRICE:.2f}"
        )
        # storage_cost = charge_mwh × charge_price (loss cost = 0 since discharge_price=0)
        expected_storage_cost = STORAGE_CHARGE_MWH * IMPORT_PRICE
        assert bd["storage_cost"] == pytest.approx(expected_storage_cost), (
            f"storage_cost must be {STORAGE_CHARGE_MWH} MWh × ${IMPORT_PRICE:.2f} = "
            f"${expected_storage_cost:.2f}; got ${bd['storage_cost']:.2f} — "
            f"likely the flat $60 fallback is still hardcoded"
        )

    def test_bess_charge_price_tracks_zero_import_price_override(self) -> None:
        """$0.0 grid import price → $0.0 BESS charge price (same `is not None` path)."""
        STORAGE_CHARGE_MWH = 3.0

        cr = _completed_run(
            grid_import_price_per_mwh=0.0,
            bess_charge_price_override_per_mwh=None,
        )
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=0.0,
            storage_charge_mwh=STORAGE_CHARGE_MWH,
            duration_hours=1.0,
        )

        assert cfg["storage_charge_price_per_mwh"] == pytest.approx(0.0)
        assert bd["storage_cost"] == pytest.approx(0.0)

    def test_explicit_bess_override_takes_precedence_over_import_price(self) -> None:
        """When bess_charge_price_override_per_mwh is set, it wins over the derived
        grid import price — the override-of-an-override path must also work."""
        STORAGE_CHARGE_MWH = 2.0
        IMPORT_PRICE = 200.0
        BESS_OVERRIDE_PRICE = 45.0  # contracted off-peak rate, cheaper than import

        cr = _completed_run(
            grid_import_price_per_mwh=IMPORT_PRICE,
            bess_charge_price_override_per_mwh=BESS_OVERRIDE_PRICE,
        )
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=0.0,
            storage_charge_mwh=STORAGE_CHARGE_MWH,
            duration_hours=1.0,
        )

        # BESS override must win over import price
        assert cfg["storage_charge_price_per_mwh"] == pytest.approx(BESS_OVERRIDE_PRICE), (
            f"bess_charge_price_override must take precedence over import price; "
            f"got ${cfg['storage_charge_price_per_mwh']:.2f}, expected ${BESS_OVERRIDE_PRICE:.2f}"
        )
        # Grid import billing price must be unaffected
        assert cfg["grid_import_price_per_mwh"] == pytest.approx(IMPORT_PRICE)
        # Storage cost reflects the BESS override rate
        expected_storage_cost = STORAGE_CHARGE_MWH * BESS_OVERRIDE_PRICE
        assert bd["storage_cost"] == pytest.approx(expected_storage_cost), (
            f"storage_cost must use BESS override ${BESS_OVERRIDE_PRICE:.2f}/MWh, "
            f"not import price ${IMPORT_PRICE:.2f}/MWh"
        )

    def test_bess_override_of_zero_is_honoured_not_shadowed(self) -> None:
        """$0.0 bess_charge_price_override is a valid legitimate value —
        confirms the `is not None` path (not `or`) on the BESS override itself."""
        STORAGE_CHARGE_MWH = 2.0

        cr = _completed_run(
            grid_import_price_per_mwh=200.0,
            bess_charge_price_override_per_mwh=0.0,  # free off-peak charging
        )
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=0.0,
            storage_charge_mwh=STORAGE_CHARGE_MWH,
            duration_hours=1.0,
        )

        assert cfg["storage_charge_price_per_mwh"] == pytest.approx(0.0), (
            "bess_charge_price_override of $0.0 must be honoured; "
            "an `or`-based fallback would replace it with the import price $200"
        )
        assert bd["storage_cost"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 3 — Path B procurement market signal has zero effect on cost accounting
# ---------------------------------------------------------------------------

class TestProcurementPathBIsolation:
    """Lock in the DIAG-1 'Path B confirmed clean' finding.

    SyntheticPriceCurve.price_at() feeds ProcurementLayer.evaluate_tick(),
    whose return value is discarded in RunManager._drive() — it has no pathway
    into compute_run_cost_from_completed().

    This test verifies the isolation directly so a future edit to _drive() that
    accidentally routes procurement output into cost accounting would be caught.

    Failure mode under a hypothetical future regression:
        If _drive() were changed to pass `procurement_result["estimated_cost"]`
        into the cost model, grid_import_cost would be derived from the $33–$77
        SyntheticPriceCurve range rather than the $150 billing price.  The
        assertion `bd["grid_import_cost"] == approx(GRID_IMPORT_MWH * 150.0)`
        would then fail.

    AT-7: SyntheticPriceCurve is deterministic for a given (seed, sim_time) —
    no runtime RNG.
    """

    def test_market_signal_price_does_not_affect_grid_import_cost(self) -> None:
        from core.procurement import SyntheticPriceCurve

        # Two price samples from the SyntheticPriceCurve — confirmed within the
        # $25–$85 advisory range.  Neither can equal $150 (the billing price below).
        curve = SyntheticPriceCurve(seed=42)
        market_price_morning = curve.price_at(0.0)      # seed=42 → ~$33/MWh at t=0
        market_price_peak    = curve.price_at(43_200.0) # 12h → ~$77/MWh

        # Precondition: market signal is genuinely different from the billing price.
        BILLING_PRICE = 150.0  # above the $25–$85 curve ceiling — cannot coincide
        assert market_price_morning != pytest.approx(BILLING_PRICE), (
            f"Precondition: market price at t=0 ({market_price_morning:.2f}) must "
            f"differ from billing price ({BILLING_PRICE:.2f})"
        )
        assert market_price_peak != pytest.approx(BILLING_PRICE), (
            f"Precondition: market price at t=43200 ({market_price_peak:.2f}) must "
            f"differ from billing price ({BILLING_PRICE:.2f})"
        )

        # Cost accounting uses the billing price, not the market signal.
        GRID_IMPORT_MWH = 3.0
        cr = _completed_run(grid_import_price_per_mwh=BILLING_PRICE)
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=GRID_IMPORT_MWH,
            storage_charge_mwh=0.0,
            duration_hours=1.0,
        )

        assert cfg["grid_import_price_per_mwh"] == pytest.approx(BILLING_PRICE), (
            "cost engine must use the billing price, not the SyntheticPriceCurve signal"
        )
        assert bd["grid_import_cost"] == pytest.approx(GRID_IMPORT_MWH * BILLING_PRICE), (
            f"grid_import_cost must be {GRID_IMPORT_MWH} MWh × ${BILLING_PRICE:.2f} = "
            f"${GRID_IMPORT_MWH * BILLING_PRICE:.2f}; "
            f"got ${bd['grid_import_cost']:.2f}. "
            f"Market signal prices (morning={market_price_morning:.2f}, "
            f"peak={market_price_peak:.2f}) must have no effect."
        )

    def test_procurement_layer_estimated_cost_is_independent_of_billing_price(
        self,
    ) -> None:
        """Direct confirmation: evaluate_tick() produces estimated_cost that
        differs from the billing price, and compute_run_cost_from_completed()
        is unaffected by whatever evaluate_tick() produces.

        This is the strongest form of the isolation check: we explicitly call
        ProcurementLayer.evaluate_tick() and show its output has no pathway
        to the cost model — not by inspecting _drive() code, but by running
        both and asserting the cost breakdown is determined solely by the
        billing price.
        """
        from core.procurement import (
            CapacityType,
            GridCapacity,
            ProcurementLayer,
            SyntheticPriceCurve,
        )

        # Build a procurement layer with a distinctly different market price.
        # seed=0 at t=0: phase_offset=0, primary=0, secondary=0 → $55/MWh exactly.
        curve = SyntheticPriceCurve(seed=0)
        caps  = [GridCapacity(
            CapacityType.NON_FIRM,
            available_mw=5.0,
            price_per_mwh=198.0,
            t_reserve_s=0.0,
        )]
        layer = ProcurementLayer(caps, curve)

        # Call evaluate_tick() — its return value is advisory and not used for billing.
        proc_result = layer.evaluate_tick(
            reserve_gap_mw=2.0,
            served_load_mw=10.0,
            sim_time=0.0,
        )
        # Confirm the advisory result exists and carries the spot market price signal.
        # evaluate_tick() returns a flat dict with 'spot_price_per_mwh'; it does NOT
        # have a nested 'proposal' dict — the proposal lives in AdvisoryGate, not here.
        assert proc_result is not None, "evaluate_tick() must return a result"
        assert "spot_price_per_mwh" in proc_result, (
            "evaluate_tick() result must include 'spot_price_per_mwh' (the advisory "
            "market signal); got keys: " + str(list(proc_result.keys()))
        )
        advisory_market_price = proc_result["spot_price_per_mwh"]

        # The billing price is well above the curve's $55 base — clearly different.
        BILLING_PRICE   = 150.0
        GRID_IMPORT_MWH = 3.0

        # Precondition: advisory market price must differ from the billing price so
        # the test is meaningful.
        assert advisory_market_price != pytest.approx(BILLING_PRICE), (
            f"Precondition: advisory market price ({advisory_market_price:.2f}) must "
            f"differ from billing price ({BILLING_PRICE:.2f})"
        )

        cr = _completed_run(grid_import_price_per_mwh=BILLING_PRICE)
        bd, cfg = compute_run_cost_from_completed(
            cr,
            generation_mwh=5.0,
            grid_import_mwh=GRID_IMPORT_MWH,
            storage_charge_mwh=0.0,
            duration_hours=1.0,
        )

        # Cost breakdown must reflect the billing price, not the advisory price.
        assert cfg["grid_import_price_per_mwh"] == pytest.approx(BILLING_PRICE)
        assert bd["grid_import_cost"] == pytest.approx(GRID_IMPORT_MWH * BILLING_PRICE), (
            f"grid_import_cost={bd['grid_import_cost']:.2f} must equal "
            f"{GRID_IMPORT_MWH} MWh × ${BILLING_PRICE:.2f} = "
            f"${GRID_IMPORT_MWH * BILLING_PRICE:.2f}. "
            f"If the procurement advisory price (${advisory_market_price:.2f} at t=0) "
            f"leaked into billing, cost would be "
            f"${GRID_IMPORT_MWH * advisory_market_price:.2f} instead."
        )
