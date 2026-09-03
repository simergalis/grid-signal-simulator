"""
tests/test_contingency.py — §16.14 acceptance tests for §7.4/§7.5 contingency coverage.

TC-77  Deficit is current output, not nameplate
TC-78  Power and energy tests are independent
TC-79  Anchor duty reduces both tests
TC-80  Non-closable deficit states the shed
TC-81  Solar is excluded from contingency arithmetic
TC-82  DISPATCHABLE excludes solar and anchor reserve
TC-83  Hot standby is not a ramp rate
TC-85  Re-rated assets counted at re-rated ramp capability
"""

import math
import pytest

from core.contingency import (
    BessSnapshot,
    FuelCellSnapshot,
    PlantState,
    TurbineSnapshot,
    evaluate_contingency,
)
from core.models import ContingencyState, IslandMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turbine(asset_id: str, output_mw: float, rated_mw: float,
             r_mw_per_s: float = 0.2, synchronized: bool = True) -> TurbineSnapshot:
    return TurbineSnapshot(
        asset_id=asset_id,
        current_output_mw=output_mw,
        rated_mw=rated_mw,
        r_asset_mw_per_s=r_mw_per_s,
        is_synchronized=synchronized,
    )


def _bess(asset_id: str = "bess-0", rated_mw: float = 10.0, soc_mwh: float = 5.0,
          usable_mwh: float = 10.0, anchor_mw: float = 1.0,
          grid_forming: bool = True) -> BessSnapshot:
    return BessSnapshot(
        asset_id=asset_id,
        rated_mw=rated_mw,
        soc_mwh=soc_mwh,
        usable_mwh=usable_mwh,
        p_anchor_reserve_mw=anchor_mw,
        grid_forming=grid_forming,
    )


def _plant(turbines, bess_units, island_mode=IslandMode.ISLANDED,
           curtailable=37.0, renewable_mw=0.0) -> PlantState:
    return PlantState(
        turbine_snapshots=tuple(turbines),
        bess_snapshots=tuple(bess_units),
        island_mode=island_mode,
        curtailable_capacity_mw=curtailable,
        renewable_mw=renewable_mw,
    )


# ---------------------------------------------------------------------------
# TC-77: Deficit is current output, not nameplate rating
# ---------------------------------------------------------------------------

def test_tc77_deficit_is_current_output_not_nameplate():
    """Largest online unit rated 7 MW, currently producing 4.2 MW.
    P_deficit_0 must be 4.2 MW.  The 7 MW nameplate must not appear."""
    # Two turbines: tripped one has highest current output
    turbines = [
        _turbine("t-0", output_mw=4.2, rated_mw=7.0),  # will be selected as tripped
        _turbine("t-1", output_mw=2.0, rated_mw=7.0),
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess))

    assert result.tripped_unit_id == "t-0"
    assert abs(result.deficit_mw - 4.2) < 1e-6, (
        f"deficit_mw should be current output (4.2), not nameplate (7.0); "
        f"got {result.deficit_mw}"
    )


def test_tc77_deterministic():
    """Called twice with identical PlantState → identical ContingencyCoverage."""
    turbines = [_turbine("t-0", output_mw=4.2, rated_mw=7.0)]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    ps = _plant(turbines, bess)
    r1 = evaluate_contingency(ps)
    r2 = evaluate_contingency(ps)
    assert r1 == r2


# ---------------------------------------------------------------------------
# TC-78: Power and energy tests are independent
# ---------------------------------------------------------------------------

def test_tc78_power_passes_energy_fails():
    """BESS with ample power rating but depleted SoC; deficit within power capability.
    Power test must pass, energy test must fail, state must NOT be COVERED."""
    # deficit = 5 MW (one turbine tripping at 5 MW output)
    # surviving headroom = 7-3 = 4 MW → not closable (4 < 5)
    # BESS rated 10 MW, anchor 0 → bridging = 10 MW ≥ 5 → power test passes
    # soc = 0.001 MWh (essentially depleted) → energy test fails
    turbines = [
        _turbine("t-0", output_mw=5.0, rated_mw=7.0),  # tripped
        _turbine("t-1", output_mw=3.0, rated_mw=7.0),  # surviving; headroom = 4 MW
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=0.001, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess, curtailable=37.0))

    assert result.power_test_passes is True, (
        f"Power test should pass (bridging {result.bess_bridging_available_mw:.1f} MW "
        f"≥ deficit {result.deficit_mw:.1f} MW)"
    )
    assert result.energy_test_passes is False, (
        "Energy test should fail (SoC nearly depleted)"
    )
    assert result.state != ContingencyState.COVERED, (
        "State must not be COVERED when energy test fails"
    )


def test_tc78_results_are_separate_fields():
    """Power and energy test results must be separate boolean fields on the return value."""
    turbines = [_turbine("t-0", output_mw=3.0, rated_mw=7.0)]
    bess = [_bess(rated_mw=5.0, soc_mwh=2.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess))

    assert hasattr(result, "power_test_passes")
    assert hasattr(result, "energy_test_passes")
    assert isinstance(result.power_test_passes, bool)
    assert isinstance(result.energy_test_passes, bool)


# ---------------------------------------------------------------------------
# TC-79: Anchor duty reduces both tests
# ---------------------------------------------------------------------------

def test_tc79_anchor_reduces_bridging_available():
    """Same contingency run twice: grid-following vs islanded anchor.
    Anchor run must report strictly lower bess_bridging_available_mw."""
    turbines = [
        _turbine("t-0", output_mw=5.0, rated_mw=7.0),
        _turbine("t-1", output_mw=3.0, rated_mw=7.0),
    ]
    bess_spec = dict(asset_id="bess-0", rated_mw=10.0, soc_mwh=5.0,
                     usable_mwh=10.0, p_anchor_reserve_mw=2.0, grid_forming=True)

    # Grid-following (anchor deduction = 0)
    bess_following = BessSnapshot(**{**bess_spec, "grid_forming": False})
    result_following = evaluate_contingency(
        _plant(turbines, [bess_following], island_mode=IslandMode.ISLANDED)
    )

    # Islanded anchor (anchor deduction = 2 MW)
    bess_anchor = BessSnapshot(**bess_spec)
    result_anchor = evaluate_contingency(
        _plant(turbines, [bess_anchor], island_mode=IslandMode.ISLANDED)
    )

    assert result_anchor.bess_bridging_available_mw < result_following.bess_bridging_available_mw, (
        f"Anchor bridging {result_anchor.bess_bridging_available_mw:.1f} should be "
        f"strictly less than grid-following {result_following.bess_bridging_available_mw:.1f}"
    )


def test_tc79_grid_tie_does_not_deduct_anchor():
    """In GRID_TIE mode, anchor deduction is zero regardless of grid_forming flag."""
    turbines = [_turbine("t-0", output_mw=3.0, rated_mw=7.0)]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=2.0, grid_forming=True)]
    result = evaluate_contingency(
        _plant(turbines, bess, island_mode=IslandMode.GRID_TIE)
    )
    # In grid-tie, anchor deduction = 0 → full rated_mw available
    assert abs(result.bess_bridging_available_mw - 10.0) < 1e-6


# ---------------------------------------------------------------------------
# TC-80: Non-closable deficit states the shed
# ---------------------------------------------------------------------------

def test_tc80_shed_required_when_not_closable():
    """Surviving headroom 2.0 MW against a 6.0 MW deficit.
    shed_required must be 4.0 MW and state must indicate shed."""
    turbines = [
        _turbine("t-0", output_mw=6.0, rated_mw=7.0),   # tripped
        _turbine("t-1", output_mw=5.0, rated_mw=7.0),   # surviving headroom = 2 MW
    ]
    # BESS has enough power to bridge but gap is not closable by generation
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess, curtailable=37.0))

    assert not result.closable, "headroom (2 MW) < deficit (6 MW): not closable"
    assert abs(result.shed_required_mw - 4.0) < 1e-6, (
        f"shed_required should be 6 − 2 = 4.0 MW, got {result.shed_required_mw}"
    )
    # State must be COVERED_WITH_SHED (shed 4 MW ≤ 37 MW curtailable) or CANNOT_CARRY,
    # not a bare failure string (§7.4 constraint).
    assert result.state in (ContingencyState.COVERED_WITH_SHED, ContingencyState.CANNOT_CARRY)


def test_tc80_covered_with_shed_when_curtailable():
    """Shed within curtailable capacity → COVERED_WITH_SHED."""
    turbines = [
        _turbine("t-0", output_mw=6.0, rated_mw=7.0),
        _turbine("t-1", output_mw=5.0, rated_mw=7.0),  # headroom 2 MW
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess, curtailable=37.0))
    # shed = 4 MW; curtailable = 37 MW → COVERED_WITH_SHED
    assert result.state == ContingencyState.COVERED_WITH_SHED, (
        f"Expected COVERED_WITH_SHED (shed {result.shed_required_mw:.1f} ≤ 37 curtailable), "
        f"got {result.state}"
    )


def test_tc80_cannot_carry_when_shed_exceeds_curtailable():
    """Shed exceeds curtailable capacity → CANNOT_CARRY."""
    # Huge deficit, tiny fleet headroom, tiny curtailable budget
    turbines = [
        _turbine("t-0", output_mw=20.0, rated_mw=22.0),
        _turbine("t-1", output_mw=21.0, rated_mw=22.0),  # headroom 1 MW
    ]
    bess = [_bess(rated_mw=5.0, soc_mwh=2.0, anchor_mw=0.0, grid_forming=False)]
    # curtailable = 2 MW but shed_required = 20 − 1 = 19 MW → CANNOT_CARRY
    result = evaluate_contingency(_plant(turbines, bess, curtailable=2.0))
    assert result.state == ContingencyState.CANNOT_CARRY, (
        f"Expected CANNOT_CARRY (shed {result.shed_required_mw:.1f} > 2 curtailable), "
        f"got {result.state}"
    )


# ---------------------------------------------------------------------------
# TC-81: Solar is excluded from the contingency arithmetic
# ---------------------------------------------------------------------------

def test_tc81_solar_excluded_from_coverage():
    """Contingency evaluated with solar producing.  Solar reduces served load
    but contributes zero to coverage, ride-through, or the closability test."""
    turbines = [
        _turbine("t-0", output_mw=5.0, rated_mw=7.0),
        _turbine("t-1", output_mw=3.0, rated_mw=7.0),
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]

    # Same plant, two evaluations: with and without solar.
    # Solar lives in renewable_mw; it must not change deficit, headroom, or state.
    result_no_solar = evaluate_contingency(
        _plant(turbines, bess, renewable_mw=0.0)
    )
    result_with_solar = evaluate_contingency(
        _plant(turbines, bess, renewable_mw=1.69)
    )

    # Coverage arithmetic must be identical — solar changes only the display term
    assert abs(result_no_solar.deficit_mw - result_with_solar.deficit_mw) < 1e-9
    assert abs(result_no_solar.headroom_surviving_mw - result_with_solar.headroom_surviving_mw) < 1e-9
    assert abs(result_no_solar.bess_bridging_available_mw - result_with_solar.bess_bridging_available_mw) < 1e-9
    assert result_no_solar.state == result_with_solar.state

    # Solar IS preserved as a pass-through display field (not discarded)
    assert abs(result_with_solar.renewable_mw - 1.69) < 1e-6
    assert abs(result_no_solar.renewable_mw) < 1e-9


# ---------------------------------------------------------------------------
# TC-82: DISPATCHABLE excludes solar and anchor reserve
# ---------------------------------------------------------------------------

def test_tc82_dispatchable_excludes_solar():
    """dispatchable_mw must not include renewable output."""
    turbines = [_turbine("t-0", output_mw=5.0, rated_mw=7.0)]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]

    result = evaluate_contingency(
        _plant(turbines, bess, renewable_mw=4.99)
    )
    # dispatchable = online turbine rated (7) + BESS bridging (10) = 17 MW
    # Must NOT be 17 + 4.99 = 21.99 MW
    assert abs(result.dispatchable_mw - 17.0) < 1e-6, (
        f"dispatchable_mw should be turbine(7)+BESS(10)=17, got {result.dispatchable_mw}"
    )


def test_tc82_dispatchable_deducts_anchor_reserve():
    """dispatchable_mw must subtract anchor reserve from BESS contribution."""
    turbines = [_turbine("t-0", output_mw=5.0, rated_mw=7.0)]
    # anchor = 2 MW on a 10 MW BESS → bridging = 8 MW
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=2.0, grid_forming=True)]

    result = evaluate_contingency(
        _plant(turbines, bess, island_mode=IslandMode.ISLANDED)
    )
    # dispatchable = 7 (turbine rated) + 8 (BESS 10 − anchor 2) = 15 MW
    assert abs(result.dispatchable_mw - 15.0) < 1e-6, (
        f"dispatchable_mw should be turbine(7)+BESS(10−2)=15, got {result.dispatchable_mw}"
    )


def test_tc82_dispatchable_uses_rated_not_current_output():
    """dispatchable_mw uses turbine RATED capacity (not current output) for online units."""
    # Turbine at 50% load — but its rated capacity is what's dispatchable
    turbines = [_turbine("t-0", output_mw=3.5, rated_mw=7.0)]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess))
    # dispatchable = rated(7) + bess(10) = 17 MW; not output(3.5) + 10 = 13.5
    assert abs(result.dispatchable_mw - 17.0) < 1e-6


def test_legacy_aggregate_fuel_cell_snapshot_retains_rated_capacity_credit():
    """A scalar legacy snapshot has no block-readiness signal to narrow it."""
    turbines = [_turbine("t-0", output_mw=5.0, rated_mw=7.0)]
    plant = _plant(turbines, [])
    plant = PlantState(
        turbine_snapshots=plant.turbine_snapshots,
        bess_snapshots=plant.bess_snapshots,
        island_mode=plant.island_mode,
        curtailable_capacity_mw=plant.curtailable_capacity_mw,
        renewable_mw=plant.renewable_mw,
        fuel_cell_snapshots=(FuelCellSnapshot(rated_mw=4.0),),
    )

    result = evaluate_contingency(plant)

    assert result.fuel_cell_available_mw == pytest.approx(4.0)
    assert result.headroom_surviving_mw == pytest.approx(4.0)
    assert result.dispatchable_mw == pytest.approx(11.0)


# ---------------------------------------------------------------------------
# TC-83: Hot standby is not a ramp rate
# ---------------------------------------------------------------------------

def test_tc83_hot_standby_excluded_from_r_surviving():
    """A hot-standby unit (is_synchronized=False) must contribute zero to r_surviving."""
    turbines = [
        _turbine("t-0", output_mw=5.0, rated_mw=7.0),             # tripped (highest output)
        _turbine("t-1", output_mw=3.0, rated_mw=7.0, r_mw_per_s=0.2),  # online surviving
        _turbine("t-2", output_mw=0.0, rated_mw=7.0, r_mw_per_s=0.2, synchronized=False),  # hot standby
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess))

    # r_surviving should count only t-1 (0.2 MW/s); t-2 contributes zero
    assert abs(result.r_surviving_mw_per_s - 0.2) < 1e-6, (
        f"r_surviving should be 0.2 (t-1 only); hot-standby t-2 must not contribute. "
        f"Got {result.r_surviving_mw_per_s}"
    )


def test_tc83_hot_standby_not_online():
    """A hot-standby unit is not selected as the tripped unit."""
    turbines = [
        _turbine("t-0", output_mw=5.0, rated_mw=7.0),                        # online
        _turbine("t-1", output_mw=0.0, rated_mw=7.0, synchronized=False),    # hot standby
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess))

    # t-1 (standby, output=0) should not be selected even though it has a high
    # rated_mw.  Tripped = t-0 (only online unit).
    assert result.tripped_unit_id == "t-0", (
        "Hot-standby unit must not be selected as the tripped unit"
    )


def test_tc83_hot_standby_not_in_dispatchable():
    """Hot-standby unit rated capacity must not appear in dispatchable_mw."""
    turbines = [
        _turbine("t-0", output_mw=3.0, rated_mw=7.0),              # online
        _turbine("t-1", output_mw=0.0, rated_mw=7.0, synchronized=False),  # standby
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess))
    # dispatchable = t-0 rated(7) + bess(10) = 17, NOT 7+7+10 = 24
    assert abs(result.dispatchable_mw - 17.0) < 1e-6, (
        f"dispatchable_mw should be 17 (online t-0 only + bess), "
        f"not 24 (including standby t-1). Got {result.dispatchable_mw}"
    )


# ---------------------------------------------------------------------------
# TC-85: Re-rated assets counted at re-rated ramp capability
# ---------------------------------------------------------------------------

def test_tc85_re_rated_ramp_used_for_closability():
    """Surviving unit carries an applied re-rating (lower r_asset).
    Closability and t_close must use the re-rated ramp rate, consistent with TC-58."""
    # Deficit 6 MW, surviving unit headroom = 7 − 3 = 4 MW < 6 → not closable
    # But with headroom = 7 − 1 = 6 MW = deficit → exactly closable
    turbines = [
        _turbine("t-0", output_mw=6.0, rated_mw=7.0),                         # tripped
        _turbine("t-1", output_mw=1.0, rated_mw=7.0, r_mw_per_s=0.16),       # re-rated (was 0.2)
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    result = evaluate_contingency(_plant(turbines, bess))

    # Exactly closable (headroom = 6 MW = deficit)
    assert result.closable, "headroom (6 MW) = deficit (6 MW): should be closable"
    # t_close must use re-rated r=0.16, not the nominal 0.2
    expected_t_close = 6.0 / 0.16   # = 37.5 s
    assert abs(result.time_to_close_s - expected_t_close) < 1e-3, (
        f"time_to_close_s should use re-rated r=0.16 → {expected_t_close:.1f}s, "
        f"got {result.time_to_close_s:.1f}s"
    )
    assert abs(result.r_surviving_mw_per_s - 0.16) < 1e-6


def test_tc85_higher_ramp_closes_faster():
    """Higher re-rated ramp rate → shorter t_close (sanity check)."""
    turbines_fast = [
        _turbine("t-0", output_mw=4.0, rated_mw=7.0),
        _turbine("t-1", output_mw=1.0, rated_mw=7.0, r_mw_per_s=0.40),  # fast
    ]
    turbines_slow = [
        _turbine("t-0", output_mw=4.0, rated_mw=7.0),
        _turbine("t-1", output_mw=1.0, rated_mw=7.0, r_mw_per_s=0.10),  # slow
    ]
    bess = [_bess(rated_mw=10.0, soc_mwh=5.0, anchor_mw=0.0, grid_forming=False)]
    r_fast = evaluate_contingency(_plant(turbines_fast, bess))
    r_slow = evaluate_contingency(_plant(turbines_slow, bess))

    if r_fast.closable and r_slow.closable:
        assert r_fast.time_to_close_s < r_slow.time_to_close_s
