"""
test_tc95_msl_floor_allocation
--------------------------------
Phase E Item 8 — TC-95: MSL floors the allocation; the sub-MSL surplus is
reported, not discarded.

Spec §7.1.3.6 / Item 8: after enabling p_min_stable_frac=0.40, every on-bus
unit's setpoint must be at or above its MSL floor.  When fleet demand falls
below Σ MSL, the surplus above the physical floor is reported as
sub_msl_surplus_mw so the caller knows the system cannot absorb the demand
deficit without a decommit.  The surplus must be > 0 and the setpoints must
all be exactly at MSL (not higher, not lower).

These are distinct from TC-96 (which tests per-unit utilisation divergence
under the sequential-base-loading normal case) — TC-95 tests the sub-MSL
guard path.
"""

from __future__ import annotations

import pytest

from core.asset_modules import TurbineModule, TurbineState
from core.loading import compute_loading_setpoints
from core.models import TurbineConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PMF = 0.40          # Phase E Item 8 default: p_min_stable_frac
_RATED = 7.0         # demo-20mw frame: 7 MW per unit
_MSL   = _PMF * _RATED   # 2.8 MW


def _sync(asset_id: str, rated_mw: float = _RATED, pmf: float = _PMF) -> TurbineModule:
    t = TurbineModule(TurbineConfig(asset_id=asset_id, rated_mw=rated_mw,
                                    p_min_stable_frac=pmf))
    t.state = TurbineState.SYNCHRONISED
    return t


# ---------------------------------------------------------------------------
# TC-95 — sub-MSL surplus path
# ---------------------------------------------------------------------------

class TestTC95MslFloorAllocation:

    def test_tc95_single_unit_demand_at_msl_no_surplus(self) -> None:
        """Fleet demand exactly at MSL: unit gets setpoint = MSL, no surplus."""
        u0 = _sync("u0")
        setpoints, surplus = compute_loading_setpoints([u0], _MSL)
        assert surplus == pytest.approx(0.0, abs=1e-9), (
            f"TC-95: demand == MSL must yield zero surplus. Got {surplus:.4f}."
        )
        assert setpoints[0] == pytest.approx(_MSL, abs=1e-6), (
            f"TC-95: setpoint at MSL demand must equal MSL. Got {setpoints[0]:.4f}."
        )

    def test_tc95_single_unit_demand_below_msl_surplus_reported(self) -> None:
        """Fleet demand below MSL: setpoint is held at MSL, surplus is reported."""
        u0 = _sync("u0")
        p_fleet = _MSL - 1.0   # 1.8 MW — below MSL 2.8 MW
        setpoints, surplus = compute_loading_setpoints([u0], p_fleet)

        assert surplus == pytest.approx(1.0, abs=1e-6), (
            f"TC-95: surplus must be MSL - p_fleet = {_MSL - p_fleet:.4f} MW. "
            f"Got {surplus:.4f} MW."
        )
        assert setpoints[0] == pytest.approx(_MSL, abs=1e-6), (
            f"TC-95: setpoint must be held at MSL even when demand < MSL. "
            f"Got {setpoints[0]:.4f} MW."
        )

    def test_tc95_two_units_demand_below_sum_msl(self) -> None:
        """With 2 units, demand below Σ MSL (5.6 MW): both units held at MSL."""
        u0 = _sync("u0")
        u1 = _sync("u1")
        sum_msl = 2 * _MSL     # 5.6 MW
        p_fleet = 4.0           # 1.6 MW below Σ MSL

        setpoints, surplus = compute_loading_setpoints([u0, u1], p_fleet)

        assert surplus == pytest.approx(sum_msl - p_fleet, abs=1e-6), (
            f"TC-95: surplus must be Σ MSL - p_fleet = {sum_msl - p_fleet:.4f} MW. "
            f"Got {surplus:.4f} MW."
        )
        # Both units must be at MSL — surplus is not solved here.
        assert setpoints[0] == pytest.approx(_MSL, abs=1e-6), (
            f"TC-95: u0 setpoint must be at MSL. Got {setpoints[0]:.4f}."
        )
        assert setpoints[1] == pytest.approx(_MSL, abs=1e-6), (
            f"TC-95: u1 setpoint must be at MSL. Got {setpoints[1]:.4f}."
        )

    def test_tc95_surplus_not_discarded_caller_sees_it(self) -> None:
        """The surplus return value must be > 0 when demand < Σ MSL.

        'Not discarded' means the caller receives the surplus; it is not silently
        absorbed or redistributed within compute_loading_setpoints().  The caller
        (simulation_core.py) decides whether to decommit or curtail.
        """
        u0 = _sync("u0")
        u1 = _sync("u1")
        u2 = _sync("u2")
        sum_msl = 3 * _MSL   # 8.4 MW

        # Demand well below Σ MSL.
        p_fleet = 5.0
        setpoints, surplus = compute_loading_setpoints([u0, u1, u2], p_fleet)

        # Must be non-zero and approximately correct.
        expected = sum_msl - p_fleet   # 3.4 MW
        assert surplus == pytest.approx(expected, abs=1e-6), (
            f"TC-95 FAIL: surplus must be reported as {expected:.4f} MW, not discarded. "
            f"Got {surplus:.4f} MW."
        )
        # Σ setpoints = Σ MSL, not p_fleet.
        assert abs(sum(setpoints) - sum_msl) < 1e-6, (
            f"TC-95: Σ setpoints must equal Σ MSL when sub-MSL. "
            f"Got {sum(setpoints):.4f}, expected {sum_msl:.4f}."
        )

    def test_tc95_zero_msl_no_surplus_possible(self) -> None:
        """With p_min_stable_frac=0.0, MSL=0 for all units: surplus is always zero.

        This is the pre-Item-8 behaviour (constraint disabled).  TC-95 asserts
        only the sub-MSL guard path, which requires a positive MSL floor.
        """
        u0 = TurbineModule(TurbineConfig(asset_id="u0", rated_mw=7.0,
                                          p_min_stable_frac=0.0))
        u0.state = TurbineState.SYNCHRONISED
        u1 = TurbineModule(TurbineConfig(asset_id="u1", rated_mw=7.0,
                                          p_min_stable_frac=0.0))
        u1.state = TurbineState.SYNCHRONISED

        # Any non-negative demand: no sub-MSL surplus because MSL = 0.
        setpoints, surplus = compute_loading_setpoints([u0, u1], 0.0)
        assert surplus == pytest.approx(0.0, abs=1e-9), (
            f"TC-95: p_min_stable_frac=0 must never produce surplus. Got {surplus:.4f}."
        )

    def test_tc95_setpoints_at_msl_not_below(self) -> None:
        """In the sub-MSL path, setpoints are floored at MSL — never below it.

        This is the 'floors the allocation' part of the TC-95 description.
        The loading layer may not allocate negative output or output below the
        combustion-stability floor to a SYNCHRONISED unit.
        """
        u0 = _sync("u0")
        # Extreme sub-MSL: demand is zero (no load).
        setpoints, surplus = compute_loading_setpoints([u0], 0.0)

        assert setpoints[0] >= _MSL - 1e-9, (
            f"TC-95 FAIL: setpoint must be >= MSL even at p_fleet=0. "
            f"Got setpoints[0]={setpoints[0]:.4f} MW, MSL={_MSL:.4f} MW."
        )
        assert surplus > 0.0, (
            f"TC-95: p_fleet=0 with positive MSL must report a positive surplus."
        )
