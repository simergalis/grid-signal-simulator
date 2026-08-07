"""
test_tc96_sequential_base_loading
----------------------------------
Phase E Item 7 — TC-96: per-unit utilisation diverges from fleet utilisation.

Sequential base-loading replaces proportional sharing in compute_loading_setpoints().
Under proportional sharing every unit's utilisation equals fleet utilisation (they
are a scalar multiple).  Sequential base-loading breaks this symmetry: the most-
senior unit is fully loaded first; the marginal unit receives the residual.  So
per-unit utilisation always diverges from fleet utilisation when more than one unit
is on the bus and fleet demand is between Σ MSL and Σ rated.

The property (not the arithmetic): there exists at least one unit whose utilisation
fraction differs from the fleet utilisation fraction.  TC-96 tests the property,
not the specific setpoint values — so it remains valid if parameters change.
"""

from __future__ import annotations

import pytest

from core.asset_modules import TurbineModule
from core.loading import compute_loading_setpoints
from core.models import TurbineConfig, TurbineState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_turb(
    asset_id: str,
    rated_mw: float = 7.0,
    p_min_stable_frac: float = 0.0,
) -> TurbineModule:
    t = TurbineModule(TurbineConfig(
        asset_id=asset_id,
        rated_mw=rated_mw,
        p_min_stable_frac=p_min_stable_frac,
    ))
    t.state = TurbineState.SYNCHRONISED
    return t


# ---------------------------------------------------------------------------
# TC-96: per-unit utilisation diverges from fleet utilisation
# ---------------------------------------------------------------------------

class TestTC96SequentialBaseLoading:

    def test_tc96_two_units_zero_msl_senior_unit_runs_at_rated(self) -> None:
        """With 2 equal units and demand = 1 × rated, unit-0 runs at 100 %
        while unit-1 runs at 0 % — both differ from fleet 50 %.

        This is the clearest expression of the sequential property: the first
        committed unit absorbs all demand before the second receives anything.
        """
        u0 = _make_turb("u0", rated_mw=7.0)
        u1 = _make_turb("u1", rated_mw=7.0)

        p_fleet = 7.0   # exactly one unit's rated output
        setpoints, sub_msl = compute_loading_setpoints([u0, u1], p_fleet)

        assert sub_msl == pytest.approx(0.0, abs=1e-9)

        fleet_util = p_fleet / (u0.config.rated_mw + u1.config.rated_mw)  # 0.5

        util_u0 = setpoints[0] / u0.config.rated_mw
        util_u1 = setpoints[1] / u1.config.rated_mw

        assert util_u0 == pytest.approx(1.0, abs=1e-6), (
            f"TC-96: unit-0 (most senior) must be at rated (100 % util). "
            f"Got setpoint={setpoints[0]:.4f} MW (util={util_u0:.4f})."
        )
        assert util_u1 == pytest.approx(0.0, abs=1e-6), (
            f"TC-96: unit-1 (marginal) must be at MSL=0 when residual is zero. "
            f"Got setpoint={setpoints[1]:.4f} MW (util={util_u1:.4f})."
        )
        # Key property: per-unit utilisation diverges from fleet utilisation.
        assert abs(util_u0 - fleet_util) > 1e-6, (
            f"TC-96 FAIL: unit-0 util ({util_u0:.4f}) == fleet util ({fleet_util:.4f}). "
            f"Sequential base-loading must make senior unit run ABOVE fleet util."
        )

    def test_tc96_two_units_with_msl_senior_fully_loaded_marginal_at_msl(self) -> None:
        """With 2 units, p_min_stable_frac=0.40, and mid-range demand:
        unit-0 (senior) is fully loaded; unit-1 (marginal) stays near MSL.

        Fleet utilisation is the average; neither per-unit utilisation matches it.
        """
        u0 = _make_turb("u0", rated_mw=7.0, p_min_stable_frac=0.40)  # msl = 2.8 MW
        u1 = _make_turb("u1", rated_mw=7.0, p_min_stable_frac=0.40)  # msl = 2.8 MW

        # Demand: above Σ MSL (5.6 MW) but below Σ rated (14.0 MW).
        # Sequential: u0 fills to rated (7.0), then u1 gets the rest.
        p_fleet = 9.0   # 9.0 > 5.6 (Σ MSL); 9.0 < 14.0 (Σ rated)
        setpoints, sub_msl = compute_loading_setpoints([u0, u1], p_fleet)

        assert sub_msl == pytest.approx(0.0, abs=1e-9)

        fleet_util = p_fleet / 14.0   # 0.643

        util_u0 = setpoints[0] / 7.0
        util_u1 = setpoints[1] / 7.0

        # u0 should have higher utilisation than fleet; u1 lower.
        assert util_u0 > fleet_util + 1e-6, (
            f"TC-96 FAIL: unit-0 util {util_u0:.4f} not above fleet util {fleet_util:.4f}. "
            f"Senior unit must be more loaded than fleet average under sequential allocation."
        )
        assert util_u1 < fleet_util - 1e-6, (
            f"TC-96 FAIL: unit-1 util {util_u1:.4f} not below fleet util {fleet_util:.4f}. "
            f"Marginal unit must be less loaded than fleet average under sequential allocation."
        )

        # Both units must be at or above MSL.
        msl_mw = 2.8
        assert setpoints[0] >= msl_mw - 1e-9, (
            f"TC-96: unit-0 setpoint {setpoints[0]:.4f} MW is below MSL {msl_mw} MW."
        )
        assert setpoints[1] >= msl_mw - 1e-9, (
            f"TC-96: unit-1 setpoint {setpoints[1]:.4f} MW is below MSL {msl_mw} MW."
        )

    def test_tc96_three_units_marginal_is_third(self) -> None:
        """With 3 units and mid-range demand, units 0 and 1 are fully loaded;
        unit 2 is the marginal unit below rated.

        Per-unit utilisation for unit-2 differs from fleet and from units 0/1.
        """
        u0 = _make_turb("u0", rated_mw=7.0, p_min_stable_frac=0.40)
        u1 = _make_turb("u1", rated_mw=7.0, p_min_stable_frac=0.40)
        u2 = _make_turb("u2", rated_mw=7.0, p_min_stable_frac=0.40)

        # Demand: fills u0 and u1 to rated and gives u2 a partial residual above MSL.
        # Each unit headroom above MSL = 7.0 - 2.8 = 4.2 MW.
        # With p_fleet=17.0: residual = 17.0 - 8.4 = 8.6 MW.
        #   u0: fill min(8.6, 4.2) = 4.2 → 7.0 MW; residual = 4.4
        #   u1: fill min(4.4, 4.2) = 4.2 → 7.0 MW; residual = 0.2
        #   u2: fill min(0.2, 4.2) = 0.2 → 3.0 MW (marginal, between MSL and rated)
        p_fleet = 17.0   # Σ MSL = 8.4; Σ rated = 21.0

        setpoints, sub_msl = compute_loading_setpoints([u0, u1, u2], p_fleet)

        assert sub_msl == pytest.approx(0.0, abs=1e-9)

        fleet_util = p_fleet / 21.0   # ≈ 0.810

        # u0 and u1 at rated (full utilisation > fleet).
        assert setpoints[0] == pytest.approx(7.0, abs=1e-6), (
            f"TC-96: u0 (most senior) must be at rated=7.0 MW. Got {setpoints[0]:.4f}."
        )
        assert setpoints[1] == pytest.approx(7.0, abs=1e-6), (
            f"TC-96: u1 must be at rated=7.0 MW. Got {setpoints[1]:.4f}."
        )

        # u2 is the marginal unit — between MSL and rated.
        msl_mw = 2.8
        assert setpoints[2] >= msl_mw - 1e-9, (
            f"TC-96: u2 must be >= MSL {msl_mw:.1f} MW. Got {setpoints[2]:.4f}."
        )
        assert setpoints[2] < 7.0 - 1e-6, (
            f"TC-96: u2 (marginal) must be below rated=7.0 MW. Got {setpoints[2]:.4f}."
        )

        # Residual check: Σ setpoints == p_fleet.
        assert abs(sum(setpoints) - p_fleet) < 1e-6, (
            f"TC-96: setpoints sum to {sum(setpoints):.4f} MW, expected {p_fleet} MW."
        )

        # Per-unit utilisation divergence: u2 is below fleet util.
        util_u2 = setpoints[2] / 7.0
        assert util_u2 < fleet_util - 1e-6, (
            f"TC-96 FAIL: u2 util {util_u2:.4f} not below fleet util {fleet_util:.4f}. "
            f"Sequential allocation must produce divergent per-unit utilisation."
        )

    def test_tc96_proportional_control(self) -> None:
        """Regression guard: if sequential loading is reverted to proportional,
        this test must FAIL — it asserts the property that distinguishes them.

        With proportional sharing: setpoints = rated_i / Σ rated × p_fleet for all i.
        Per-unit utilisation is then identical to fleet utilisation for all i.
        TC-96 asserts divergence → if sharing is proportional, it fails.
        """
        u0 = _make_turb("u0", rated_mw=7.0)
        u1 = _make_turb("u1", rated_mw=7.0)

        p_fleet = 5.0   # mid-range; proportional would give [2.5, 2.5]

        setpoints, _ = compute_loading_setpoints([u0, u1], p_fleet)
        fleet_util = p_fleet / 14.0

        # With sequential: u0 gets 5.0 (util=0.714), u1 gets 0.0 (util=0.0).
        # Fleet util = 5.0/14.0 = 0.357.
        # Divergence: u0 util (0.714) ≠ fleet util (0.357). ✓
        # With proportional: u0 gets 2.5 (util=0.357) = fleet util. ✗ (test would fail)
        at_least_one_differs = any(
            abs(sp / u.config.rated_mw - fleet_util) > 1e-6
            for sp, u in zip(setpoints, [u0, u1])
        )
        assert at_least_one_differs, (
            "TC-96 FAIL: all units have identical utilisation == fleet utilisation. "
            "This indicates proportional sharing is still active. "
            "Sequential base-loading must make at least one unit's utilisation "
            "differ from the fleet average."
        )

    def test_tc96_single_unit_no_divergence_possible(self) -> None:
        """With a single on-bus unit, per-unit utilisation == fleet utilisation
        by definition.  Sequential allocation is identical to proportional here.
        TC-96 does NOT assert divergence for a singleton fleet.
        """
        u0 = _make_turb("u0", rated_mw=7.0)
        setpoints, sub_msl = compute_loading_setpoints([u0], 5.0)

        assert sub_msl == pytest.approx(0.0, abs=1e-9)
        assert setpoints[0] == pytest.approx(5.0, abs=1e-6), (
            f"TC-96: single-unit setpoint must equal p_fleet. Got {setpoints[0]:.4f}."
        )

    def test_tc96_sub_msl_case_unchanged(self) -> None:
        """Sub-MSL allocation returns all units at MSL and reports the surplus.
        Sequential base-loading does not change this path (only the normal case
        initial allocation changes; the sub-MSL guard fires first).
        """
        u0 = _make_turb("u0", rated_mw=7.0, p_min_stable_frac=0.40)  # msl=2.8
        u1 = _make_turb("u1", rated_mw=7.0, p_min_stable_frac=0.40)  # msl=2.8

        p_fleet = 4.0   # below Σ MSL = 5.6 → sub-MSL case
        setpoints, sub_msl = compute_loading_setpoints([u0, u1], p_fleet)

        assert sub_msl > 0.0, (
            f"TC-96: sub-MSL demand must yield sub_msl_surplus_mw > 0. Got {sub_msl:.4f}."
        )
        # Units held at MSL.
        assert setpoints[0] == pytest.approx(2.8, abs=1e-6)
        assert setpoints[1] == pytest.approx(2.8, abs=1e-6)
