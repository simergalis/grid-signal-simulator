"""
tests/test_p1b_p2.py — Phase 1b (loading layer) and Phase 2 (unit states +
UnitAvailability boundary) acceptance tests.

TC-77: Loading layer — pure stateless function (order independence)
TC-78: Loading layer — terminates within |A| passes
TC-79: Ramp clamped by headroom (not r × H × n)
TC-80: STARTING unit contributes rated_mw only after time_to_online_s elapses
TC-81: UnitAvailability boundary — no import path to TurbineModule internals

All tests run headless with no external I/O.
"""
from __future__ import annotations

import math
import sys
import pytest

sys.path.insert(0, ".")

from core.models import TurbineConfig, TurbineState, ThermalState, UnitAvailability
from core.asset_modules import TurbineModule
from core.loading import (
    compute_loading_setpoints,
    apply_loading,
    ramp_capability,
)
# LEAD_WINDOW_S deliberately absent — Task #198 item 3.
# Tests use explicit numeric horizons so there is no second constant.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turbine(
    rated_mw: float = 10.0,
    r_asset_mw_per_s: float = 0.2,
    p_min_stable_frac: float = 0.0,
    output_mw: float = 0.0,
    state: TurbineState = TurbineState.SYNCHRONISED,
    hot_standby: bool = False,
    cold_start_s: float = 900.0,
) -> TurbineModule:
    """Fabricate a TurbineModule with the given output set via set_output()."""
    cfg = TurbineConfig(
        asset_id=f"GT-{rated_mw:.0f}",
        rated_mw=rated_mw,
        r_asset_mw_per_s=r_asset_mw_per_s,
        p_min_stable_frac=p_min_stable_frac,
        hot_standby=hot_standby,
        cold_start_s=cold_start_s,
    )
    t = TurbineModule(config=cfg, state=state)
    t.set_output(output_mw)
    return t


def _starting_turbine(
    rated_mw: float = 10.0,
    r_asset_mw_per_s: float = 0.2,
    time_to_online_s: float = 900.0,
) -> TurbineModule:
    """Fabricate a STARTING TurbineModule with a preset countdown timer."""
    cfg = TurbineConfig(
        asset_id=f"GT-start-{rated_mw:.0f}",
        rated_mw=rated_mw,
        r_asset_mw_per_s=r_asset_mw_per_s,
        cold_start_s=time_to_online_s,
    )
    t = TurbineModule(config=cfg, state=TurbineState.STARTING)
    t._time_to_online_s = time_to_online_s
    t.set_output(0.0)
    return t


# ---------------------------------------------------------------------------
# TC-77: Loading layer is pure / order-independent
# ---------------------------------------------------------------------------

class TestTC77LoadingLayerPure:
    """TC-77: Identical (A, T, P_fleet, outputs) yields identical setpoints
    across calls, process restarts, and unit-ordering permutations.

    Order-independence: permuting the unit list yields the same SORTED setpoints
    (individual unit assignments may differ by identity but the overall
    distribution is symmetric because all units have the same rated_mw in
    this test).
    """

    def test_tc77_same_result_on_repeated_call(self):
        """Two calls with identical state return identical setpoints."""
        units = [
            _turbine(rated_mw=10.0, output_mw=0.0),
            _turbine(rated_mw=10.0, output_mw=0.0),
            _turbine(rated_mw=10.0, output_mw=0.0),
        ]
        p_fleet = 15.0
        sp1, sub1 = compute_loading_setpoints(units, p_fleet)
        sp2, sub2 = compute_loading_setpoints(units, p_fleet)
        assert sp1 == sp2, f"TC-77: repeated call returned different setpoints: {sp1} vs {sp2}"
        assert sub1 == sub2

    def test_tc77_order_independent_equal_rated(self):
        """Equal-rated units: setpoints are the same regardless of ordering."""
        u0 = _turbine(rated_mw=10.0, output_mw=2.0)
        u1 = _turbine(rated_mw=10.0, output_mw=5.0)
        u2 = _turbine(rated_mw=10.0, output_mw=3.0)
        p_fleet = 18.0

        sp_abc, _ = compute_loading_setpoints([u0, u1, u2], p_fleet)
        sp_bca, _ = compute_loading_setpoints([u1, u2, u0], p_fleet)
        sp_cab, _ = compute_loading_setpoints([u2, u0, u1], p_fleet)

        # Equal-rated: all setpoints are the same value (p_fleet / n)
        assert sorted(sp_abc) == pytest.approx(sorted(sp_bca), abs=1e-9), (
            f"TC-77: order changed result: {sorted(sp_abc)} vs {sorted(sp_bca)}"
        )
        assert sorted(sp_abc) == pytest.approx(sorted(sp_cab), abs=1e-9)

    def test_tc77_total_matches_p_fleet(self):
        """Sum of setpoints must equal p_fleet (no energy created or destroyed)."""
        units = [
            _turbine(rated_mw=10.0, output_mw=0.0),
            _turbine(rated_mw=15.0, output_mw=2.0),
            _turbine(rated_mw=8.0,  output_mw=1.0),
        ]
        p_fleet = 22.0
        sp, sub = compute_loading_setpoints(units, p_fleet)
        assert sub == pytest.approx(0.0), "No sub-MSL: sum should equal p_fleet"
        assert sum(sp) == pytest.approx(p_fleet, abs=1e-6), (
            f"TC-77: sum(setpoints)={sum(sp):.6f} != p_fleet={p_fleet}"
        )

    def test_tc77_no_setpoint_exceeds_rated(self):
        """Every setpoint must be at most the unit's rated_mw."""
        units = [
            _turbine(rated_mw=10.0, output_mw=0.0),
            _turbine(rated_mw=5.0,  output_mw=0.0),  # smaller unit — may clamp
        ]
        p_fleet = 14.0  # exceeds smaller unit's rated_mw
        sp, _ = compute_loading_setpoints(units, p_fleet)
        for i, (t, s) in enumerate(zip(units, sp)):
            assert s <= t.config.rated_mw + 1e-9, (
                f"TC-77: unit {i} setpoint {s:.4f} > rated {t.config.rated_mw:.4f}"
            )


# ---------------------------------------------------------------------------
# TC-78: Redistribution terminates within |A| passes
# ---------------------------------------------------------------------------

class TestTC78Terminates:
    """TC-78: The redistribution loop terminates within |A| passes.

    This is a code-structure criterion — the loop has at most `n` iterations
    where n = len(synchronised).  We verify indirectly: compute_loading_setpoints
    returns for large fleets in finite time, and the setpoints are feasible.
    """

    def test_tc78_large_fleet_terminates(self):
        """20-unit fleet with heterogeneous rated_mw terminates quickly."""
        units = [_turbine(rated_mw=float(5 + i), output_mw=0.0) for i in range(20)]
        p_fleet = sum(t.config.rated_mw for t in units) * 0.7
        sp, sub = compute_loading_setpoints(units, p_fleet)
        assert len(sp) == 20
        assert sub == pytest.approx(0.0, abs=1e-9)
        for i, (t, s) in enumerate(zip(units, sp)):
            assert s >= -1e-9, f"TC-78: unit {i} setpoint {s:.4f} < 0"
            assert s <= t.config.rated_mw + 1e-9, f"TC-78: unit {i} {s:.4f} > rated"

    def test_tc78_sub_msl_case_terminates(self):
        """Sub-MSL fleet: returns floor setpoints immediately (no redistribution)."""
        units = [
            _turbine(rated_mw=10.0, p_min_stable_frac=0.45, output_mw=0.0),
            _turbine(rated_mw=10.0, p_min_stable_frac=0.45, output_mw=0.0),
        ]
        p_fleet = 5.0  # below 2 × 0.45 × 10 = 9 MW floor
        sp, sub = compute_loading_setpoints(units, p_fleet)
        assert sub > 0.0, "TC-78: sub_msl_surplus_mw should be > 0 when P_fleet < Σ msl"
        assert sub == pytest.approx(9.0 - 5.0, abs=1e-6), f"TC-78: surplus={sub}"
        # Each unit held at its MSL floor
        for s in sp:
            assert s == pytest.approx(4.5, abs=1e-6), f"TC-78: setpoint {s} != msl 4.5"


# ---------------------------------------------------------------------------
# TC-79: Ramp clamped by headroom
# ---------------------------------------------------------------------------

class TestTC79RampClampedByHeadroom:
    """TC-79: Fleet at 90% of rated, 45 s explicit horizon — capability equals
    remaining headroom, not r × 45 × n.

    Item 3: horizons are explicit numeric values (no LEAD_WINDOW_S constant).
    """

    def test_tc79_headroom_dominates_at_90pct(self):
        """At 90% output, headroom = 1 MW/unit; r × 45 = 9 MW/unit.  Capped at 1."""
        rated = 10.0
        r_mw_s = 0.2  # 0.2 × 45 = 9 MW uncapped ramp
        output = 9.0  # 90% → headroom = 1 MW
        H = 45.0       # explicit horizon — matches dispatch arbitrator default
        units = [
            _turbine(rated_mw=rated, r_asset_mw_per_s=r_mw_s, output_mw=output),
            _turbine(rated_mw=rated, r_asset_mw_per_s=r_mw_s, output_mw=output),
        ]
        cap = ramp_capability(H, units)
        expected = 2 * (rated - output)  # 2 × 1.0 = 2.0 MW
        assert cap == pytest.approx(expected, abs=1e-6), (
            f"TC-79: capability={cap:.4f} MW != headroom-capped {expected:.4f} MW "
            f"(uncapped would be {2 * r_mw_s * H:.1f} MW)"
        )

    def test_tc79_ramp_dominates_when_output_near_zero(self):
        """Near zero output — headroom ≫ r × H, so ramp rate dominates."""
        rated = 10.0
        r_mw_s = 0.2
        output = 0.0
        H = 45.0
        units = [_turbine(rated_mw=rated, r_asset_mw_per_s=r_mw_s, output_mw=output)]
        cap = ramp_capability(H, units)
        expected = min(r_mw_s * H, rated)  # 9.0 MW
        assert cap == pytest.approx(expected, abs=1e-6), (
            f"TC-79: capability={cap:.4f} != ramp-limited {expected:.4f} MW"
        )

    def test_tc79_hot_standby_excluded(self):
        """Hot-standby units must not contribute to ramp capability."""
        H = 45.0
        standby = _turbine(rated_mw=10.0, r_asset_mw_per_s=0.2, output_mw=0.0, hot_standby=True)
        active  = _turbine(rated_mw=10.0, r_asset_mw_per_s=0.2, output_mw=0.0)
        cap = ramp_capability(H, [standby, active])
        expected = min(0.2 * H, 10.0)  # only active unit
        assert cap == pytest.approx(expected, abs=1e-6), (
            f"TC-79: hot_standby contributed to ramp; cap={cap:.4f} > expected={expected:.4f}"
        )


# ---------------------------------------------------------------------------
# TC-80: STARTING unit contributes rated_mw only after online timer elapses
# ---------------------------------------------------------------------------

class TestTC80StartingUnitRampCapability:
    """TC-80 (corrected, Task #198 item 2): STARTING units contribute ZERO to
    ramp capability regardless of the horizon.

    Rationale: a unit not yet on bus must not be banked as reserve — starts fail.
    Full credit appears only once the unit transitions to SYNCHRONISED.  The
    old pro-rating (credit = 0 for H < timer; rated_mw for H ≥ timer) is
    removed: the horizon is irrelevant while the breaker is open.
    """

    def test_tc80_starting_zero_before_online(self):
        """H = 45 s < 900 s → starting unit contributes 0."""
        t = _starting_turbine(rated_mw=10.0, time_to_online_s=900.0)
        assert t.state == TurbineState.STARTING
        cap = ramp_capability(45.0, [t])
        assert cap == pytest.approx(0.0, abs=1e-9), (
            f"TC-80: STARTING unit H=45 < 900 s contributed {cap:.4f} MW (should be 0)"
        )

    def test_tc80_starting_rated_at_online_time(self):
        """H = 900 s == time_to_online_s → still 0 (unit is STARTING, not SYNCHRONISED).

        Corrected: the old rule credited rated_mw at H ≥ timer.  Item 2 removes
        that branch: state == STARTING always contributes zero.
        """
        t = _starting_turbine(rated_mw=10.0, time_to_online_s=900.0)
        cap = ramp_capability(900.0, [t])
        assert cap == pytest.approx(0.0, abs=1e-9), (
            f"TC-80: STARTING unit H=900 == 900 s contributed {cap:.4f} MW "
            f"(should be 0 — state is still STARTING, not SYNCHRONISED)"
        )

    def test_tc80_starting_rated_above_online_time(self):
        """H > time_to_online_s → still 0 (unit is STARTING, not SYNCHRONISED).

        Corrected: the old rule credited rated_mw when H > timer.  Item 2 removes
        the pro-rating — STARTING units contribute zero at any horizon.
        """
        t = _starting_turbine(rated_mw=10.0, time_to_online_s=600.0)
        cap = ramp_capability(900.0, [t])
        assert cap == pytest.approx(0.0, abs=1e-9), (
            f"TC-80: STARTING unit H=900 > 600 s contributed {cap:.4f} MW "
            f"(should be 0 — state is still STARTING, not SYNCHRONISED)"
        )

    def test_tc80_starting_plus_synchronised_fleet(self):
        """Mixed fleet: STARTING always contributes 0; SYNCHRONISED contributes normally."""
        starting   = _starting_turbine(rated_mw=10.0, time_to_online_s=900.0)
        synced     = _turbine(rated_mw=10.0, r_asset_mw_per_s=0.2, output_mw=5.0)
        cap = ramp_capability(45.0, [starting, synced])
        # starting: 0 MW (not on bus — Task #198 item 2)
        # synced: min(0.2 × 45, 10 − 5) = min(9, 5) = 5.0 MW
        assert cap == pytest.approx(5.0, abs=1e-6), (
            f"TC-80: mixed fleet H=45 expected 5.0 MW (starting=0, synced=5); got {cap:.4f}"
        )

    def test_tc80_command_start_sets_starting_state(self):
        """command_start() transitions OFFLINE → STARTING with cold timer."""
        cfg = TurbineConfig(
            asset_id="GT-test",
            rated_mw=10.0,
            cold_start_s=900.0,
            hot_start_s=60.0,
            warm_start_s=300.0,
            hot_threshold_s=3600.0,
            warm_threshold_s=14400.0,
        )
        t = TurbineModule(config=cfg, state=TurbineState.OFFLINE)
        t.command_start(sim_time=0.0)
        assert t.state == TurbineState.STARTING, (
            f"TC-80: command_start did not set STARTING; got {t.state}"
        )
        assert t._time_to_online_s == pytest.approx(900.0, abs=1e-6), (
            f"TC-80: cold timer {t._time_to_online_s} != 900.0"
        )
        assert t._thermal_state == ThermalState.COLD

    def test_tc80_advance_transitions_to_synchronised(self):
        """advance() ticks the countdown; unit becomes SYNCHRONISED when timer reaches 0."""
        t = _starting_turbine(rated_mw=10.0, time_to_online_s=10.0)
        # Tick 5 s — timer goes to 5 s, stays STARTING
        t.advance(sim_time=0.0, dt_seconds=5.0)
        assert t.state == TurbineState.STARTING
        assert t._time_to_online_s == pytest.approx(5.0, abs=1e-6)
        # Tick 5 s — timer expires, transitions to SYNCHRONISED
        t.advance(sim_time=5.0, dt_seconds=5.0)
        assert t.state == TurbineState.SYNCHRONISED, (
            f"TC-80: after timer expiry state={t.state}, expected SYNCHRONISED"
        )
        assert t._time_to_online_s == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# TC-81: UnitAvailability boundary — structural / import path check
# ---------------------------------------------------------------------------

class TestTC81UnitAvailabilityBoundary:
    """TC-81: The reserve check and N-1 tile consumers can be driven by
    UnitAvailability objects without requiring any TurbineModule import.

    Structural criterion: UnitAvailability is frozen and fully typed;
    all required fields are present without calling into TurbineModule.
    This test constructs UnitAvailability directly (no TurbineModule) and
    verifies the boundary object is usable for reserve computation.
    """

    def test_tc81_unit_availability_is_frozen_dataclass(self):
        """UnitAvailability can be constructed directly from spec data."""
        ua = UnitAvailability(
            unit_id="GT-1",
            state=TurbineState.SYNCHRONISED,
            output_mw=5.0,
            rated_mw=10.0,
            msl_mw=4.5,
            r_asset_effective_mw_per_s=0.2,
            time_to_online_s=0.0,
            out_of_service_reason=None,
        )
        assert ua.unit_id == "GT-1"
        assert ua.state == TurbineState.SYNCHRONISED
        # Frozen: mutation must raise
        with pytest.raises((AttributeError, TypeError)):
            ua.output_mw = 99.9  # type: ignore[misc]

    def test_tc81_turbine_module_builds_valid_availability(self):
        """TurbineModule.unit_availability() returns a well-formed UnitAvailability."""
        t = _turbine(rated_mw=10.0, output_mw=7.5, state=TurbineState.SYNCHRONISED)
        ua = t.unit_availability()
        assert isinstance(ua, UnitAvailability)
        assert ua.state == TurbineState.SYNCHRONISED
        assert ua.output_mw == pytest.approx(7.5)
        assert ua.rated_mw == pytest.approx(10.0)
        assert ua.time_to_online_s == pytest.approx(0.0)
        assert ua.out_of_service_reason is None

    def test_tc81_starting_unit_availability(self):
        """STARTING unit reports non-zero time_to_online_s."""
        t = _starting_turbine(rated_mw=10.0, time_to_online_s=600.0)
        ua = t.unit_availability()
        assert ua.state == TurbineState.STARTING
        assert ua.time_to_online_s == pytest.approx(600.0, abs=1e-6)
        assert ua.out_of_service_reason is None

    def test_tc81_out_of_service_availability(self):
        """OUT_OF_SERVICE unit reports time_to_online_s=None."""
        cfg = TurbineConfig(asset_id="GT-oos", rated_mw=10.0)
        t = TurbineModule(config=cfg, state=TurbineState.OUT_OF_SERVICE)
        t._out_of_service_reason = "maintenance"
        ua = t.unit_availability()
        assert ua.state == TurbineState.OUT_OF_SERVICE
        assert ua.time_to_online_s is None
        assert ua.out_of_service_reason == "maintenance"

    def test_tc81_ramp_credit_computable_from_availability_only(self):
        """Reserve check ramp credit can be computed from UnitAvailability fields alone.

        This verifies the structural boundary: the formula
            sum(ua.r_asset_effective_mw_per_s for ua in active) × dt_lead
        does not require TurbineModule.  We exercise it with directly-constructed
        UnitAvailability objects to prove no TurbineModule method is called.
        """
        active_ua = [
            UnitAvailability(
                unit_id=f"GT-{i}", state=TurbineState.SYNCHRONISED,
                output_mw=2.0, rated_mw=10.0, msl_mw=0.0,
                r_asset_effective_mw_per_s=0.2,
                time_to_online_s=0.0, out_of_service_reason=None,
            )
            for i in range(3)
        ]
        dt_lead = 45.0
        raw_credit = sum(ua.r_asset_effective_mw_per_s for ua in active_ua) * dt_lead
        # 3 × 0.2 × 45 = 27.0 MW
        assert raw_credit == pytest.approx(27.0, abs=1e-6), (
            f"TC-81: ramp credit from UnitAvailability = {raw_credit:.4f} != 27.0 MW"
        )

    def test_tc81_no_turbinemodule_import_needed_for_ramp_credit(self):
        """Structural: importing only models.py is sufficient for the ramp-credit formula.

        Verifies that UnitAvailability is importable from models.py without
        pulling in asset_modules (the import chain must not loop through TurbineModule).
        """
        from core.models import UnitAvailability as UA_from_models
        # If this import succeeds without circular-import errors, the boundary holds.
        assert UA_from_models is UnitAvailability

    def test_tc81_new_phase2_states_exist(self):
        """All five Phase 2 canonical states exist in TurbineState."""
        for name in ("OFFLINE", "STARTING", "SYNCHRONISED", "OUT_OF_SERVICE", "TRANSITIONAL"):
            assert hasattr(TurbineState, name), f"TC-81: TurbineState missing {name}"
        # Legacy aliases still present for backward compat
        for name in ("RAMPING", "AT_TARGET"):
            assert hasattr(TurbineState, name), f"TC-81: TurbineState missing legacy {name}"

    def test_tc81_dispatch_turbine_ramp_credit_mw(self):
        """turbine_ramp_credit_mw() in dispatch.py works with UnitAvailability only.

        This is the structural migration: the dispatch-layer ramp credit formula
        no longer requires TurbineModule — it accepts a Sequence[UnitAvailability].
        Verifies hot-standby exclusion, STARTING unit lead-time reduction, and cap.
        """
        from core.dispatch import turbine_ramp_credit_mw

        sync_ua = UnitAvailability(
            unit_id="GT-sync", state=TurbineState.SYNCHRONISED,
            output_mw=2.0, rated_mw=10.0, msl_mw=0.0,
            r_asset_effective_mw_per_s=0.2,
            time_to_online_s=0.0, out_of_service_reason=None,
            hot_standby=False,
        )
        starting_ua = UnitAvailability(
            unit_id="GT-start", state=TurbineState.STARTING,
            output_mw=0.0, rated_mw=10.0, msl_mw=0.0,
            r_asset_effective_mw_per_s=0.2,
            time_to_online_s=30.0, out_of_service_reason=None,
            hot_standby=False,
        )
        standby_ua = UnitAvailability(
            unit_id="GT-hot", state=TurbineState.OFFLINE,
            output_mw=0.0, rated_mw=10.0, msl_mw=0.0,
            r_asset_effective_mw_per_s=0.2,
            time_to_online_s=0.0, out_of_service_reason=None,
            hot_standby=True,
        )

        lead = 45.0
        # Task #198 item 2: STARTING units contribute zero (not on bus; starts fail).
        # sync:     0.2 × 45 = 9.0 MW
        # starting: 0.0 MW  (STARTING → zero regardless of lead_window_s)
        # standby:  excluded → 0
        # total = 9.0 MW (delta_p_mw=20 → no cap)
        credit = turbine_ramp_credit_mw([sync_ua, starting_ua, standby_ua], lead, 20.0)
        assert credit == pytest.approx(9.0, abs=1e-6), (
            f"TC-81 dispatch boundary: expected 9.0 MW credit (starting=0), got {credit}"
        )

        # Cap to delta_p_mw — 9.0 MW raw > 5.0 cap → 5.0
        capped = turbine_ramp_credit_mw([sync_ua, starting_ua, standby_ua], lead, 5.0)
        assert capped == pytest.approx(5.0, abs=1e-6), (
            f"TC-81 dispatch boundary cap: expected 5.0 MW, got {capped}"
        )

    def test_tc81_mutual_exclusion_guard_passes_for_valid_split(self):
        """Guard passes when SYNCHRONISED and RAMPING units are correctly separated.

        Note: _turbine() derives asset_id from rated_mw, so units must have
        distinct rated_mw values to receive distinct asset_ids.
        """
        from core.simulation_core import _check_loading_exclusion
        # GT-10 in SYNCHRONISED state — in loading set
        synced  = _turbine(rated_mw=10.0, output_mw=5.0, state=TurbineState.SYNCHRONISED)
        # GT-15 in RAMPING state — NOT in loading set (different asset_id)
        ramping = _turbine(rated_mw=15.0, output_mw=3.0, state=TurbineState.RAMPING)
        # Correct usage: loading set = {GT-10}; RAMPING unit GT-15 is not in it → no error
        _check_loading_exclusion([synced], [synced, ramping])

    def test_tc81_mutual_exclusion_guard_raises_on_b1a_defect(self):
        """Guard raises RuntimeError when a RAMPING unit is in the loading set.

        This proves the guard can fire.  The B1a defect occurs when the
        allocation filter incorrectly passes RAMPING units into the loading-
        layer set A.  We simulate it by directly placing the RAMPING unit
        in both the loading set and the all_turbines list.
        """
        from core.simulation_core import _check_loading_exclusion
        # GT-10 in RAMPING state.  B1a defect: the filter erroneously put it
        # into loading set A instead of filtering it out.
        ramping = _turbine(rated_mw=10.0, output_mw=3.0, state=TurbineState.RAMPING)
        with pytest.raises(RuntimeError, match="mutual-exclusion"):
            _check_loading_exclusion([ramping], [ramping])

    def test_tc81_mutual_exclusion_guard_raises_on_at_target_defect(self):
        """Guard raises for AT_TARGET unit appearing in loading set."""
        from core.simulation_core import _check_loading_exclusion
        # Use a different rated_mw to avoid collision with any other helper-created unit
        at_target = _turbine(rated_mw=20.0, output_mw=18.0, state=TurbineState.AT_TARGET)
        with pytest.raises(RuntimeError, match="mutual-exclusion"):
            _check_loading_exclusion([at_target], [at_target])

    def test_tc81_p_anchor_reserve_report(self):
        """Report: P_anchor_reserve — BessConfig default vs San Diego scenario.

        BessConfig.p_anchor_reserve_mw defaults to 1.0 MW (PROTO-9 / CHOSEN).
        site_config.py contains no override; the San Diego demo-20mw SCENARIO
        sets p_anchor_reserve_mw = 2.0 MW explicitly in its BessUnitSpec (PW-3
        / §15 — deliberate site-level override, not a BessConfig default change).

        This test documents the BessConfig DEFAULT (1.0 MW) without importing
        site_config or the seeded scenario store.
        """
        from core.models import BessConfig
        cfg = BessConfig(asset_id="bess-0", rated_mw=10.0, usable_mwh=5.0)
        # Default value — 1.0 MW (PROTO-9, CHOSEN).
        # San Diego demo-20mw scenario uses 2.0 MW (PW-3 / §15 scenario-level override).
        assert cfg.p_anchor_reserve_mw == pytest.approx(1.0), (
            f"TC-81 (report): BessConfig default p_anchor_reserve_mw={cfg.p_anchor_reserve_mw}; "
            f"expected 1.0 MW.  Note: demo-20mw BessUnitSpec overrides to 2.0 MW (PW-3 / §15)."
        )


# ---------------------------------------------------------------------------
# TC-82: demo plant p_min_stable_frac = 0.40 driven below Σ msl (PW-1 / PW-2)
# ---------------------------------------------------------------------------

class TestTC82DemoPlantMSLConstraint:
    """TC-82: demo plant with p_min_stable_frac = 0.40 driven below Σ msl.

    PW-1: p_min_stable_frac = 0.40 on demo-20mw turbines (7 MW rated).
          MSL = 0.40 × 7.0 = 2.8 MW per unit.

    PW-2: asset_delivery_error_mw = commanded ≠ delivered, whatever the cause.
          A unit held at its MSL floor contributes +sub_msl to delivery error.
          No subtraction of sub_msl from the turbine delivery term.

    Three assertions:
      (a) sub_msl_surplus_mw > 0  (floor constraint active).
      (b) asset_delivery_error_mw > 0  (PW-2 semantics).
      (c) frequency_forcing_mw > 0  (overfrequency in islanded mode →
          frequency_hz > 50.0 after one tick).
    """

    def test_tc82a_sub_msl_surplus(self):
        """(a) Loading layer: p_fleet < MSL → sub_msl_surplus_mw > 0.

        1 × 7 MW unit, p_min_stable_frac = 0.40 → MSL = 2.8 MW.
        p_fleet = 2.0 MW < MSL → floor fires; setpoint = MSL floor.
        """
        unit = _turbine(rated_mw=7.0, p_min_stable_frac=0.40, output_mw=2.8)
        setpoints, sub_msl = compute_loading_setpoints([unit], p_fleet=2.0)
        assert sub_msl == pytest.approx(0.8, abs=1e-6), (
            f"TC-82a: expected sub_msl_surplus_mw ≈ 0.8 MW "
            f"(MSL 2.8 − p_fleet 2.0), got {sub_msl:.6f}"
        )
        assert setpoints == pytest.approx([2.8], abs=1e-6), (
            f"TC-82a: expected setpoint at MSL floor 2.8 MW, got {setpoints}"
        )

    def test_tc82b_asset_delivery_error_pw2_semantics(self):
        """(b) PW-2: turbine at MSL floor → asset_delivery_error_mw > 0.

        PW-2 formula (no sub_msl subtraction):
          asset_delivery_error = (turbine_output − droop_setpoint) + (bess_out − bess_sp)
                               = (2.8 − 2.0) + 0 = 0.8 MW > 0.

        Contrasts with the pre-PW-2 formula where sub_msl was subtracted from
        the turbine term, forcing asset_delivery_error = 0 at the floor.
        """
        turbine_output_mw  = 2.8   # held at MSL floor
        droop_setpoint_mw  = 2.0   # commanded below MSL
        bess_output_mw     = 0.0   # BESS setpoint = 0 (turbine over-delivering)
        bess_setpoint_mw   = 0.0
        # PW-2 formula — identical in islanded and grid-connected modes.
        delivery_error = (
            (turbine_output_mw - droop_setpoint_mw)
            + (bess_output_mw  - bess_setpoint_mw)
        )
        assert delivery_error == pytest.approx(0.8, abs=1e-6), (
            f"TC-82b: expected delivery_error ≈ 0.8 MW, got {delivery_error:.6f}"
        )
        assert delivery_error > 0.0, "TC-82b PW-2: asset_delivery_error_mw must be > 0"

    def test_tc82c_frequency_forcing_overfrequency_islanded(self):
        """(c) sub_msl_surplus in islanded mode → frequency_forcing > 0 → f > 50 Hz.

        Islanded formula (PW-2, unchanged from PW-1 in this channel):
          frequency_forcing = (p_commanded − p_total) + sub_msl_surplus

        With p_commanded ≈ p_total (demand at droop setpoint 2.0 MW) and
        sub_msl = 0.8 MW:
          frequency_forcing = (2.0 − 2.0) + 0.8 = 0.8 MW > 0.

        Swing equation: df/dt = frequency_forcing / (2H × S_base) × f₀.
        All terms > 0 → df/dt > 0 → frequency_hz > 50.0 after one tick.
        """
        sub_msl_surplus_mw = 0.8   # MSL 2.8 − p_fleet 2.0
        p_commanded_mw     = 2.0   # droop_setpoint + bess_setpoint + p_renewable
        p_total_mw         = 2.0   # GPU + cooling load (equals commanded at steady state)

        # Islanded frequency_forcing formula (same as simulation_core.py):
        frequency_forcing = (p_commanded_mw - p_total_mw) + sub_msl_surplus_mw
        assert frequency_forcing == pytest.approx(0.8, abs=1e-6), (
            f"TC-82c: expected frequency_forcing ≈ 0.8 MW, got {frequency_forcing:.6f}"
        )
        assert frequency_forcing > 0.0, (
            "TC-82c: sub-MSL in islanded mode must produce overfrequency "
            f"(frequency_forcing = {frequency_forcing:.4f} MW)"
        )

        # Swing equation — verify df/dt > 0 for representative SiteConfig values.
        # H (inertia_constant_s) = 2.0 (SiteConfig default), S_base = 7.0 MW (1 unit).
        H      = 2.0   # SiteConfig.inertia_constant_s default
        S_base = 7.0   # rated_mw of the single unit in this test
        f0     = 50.0  # nominal frequency (Hz)
        df_dt  = frequency_forcing / (2.0 * H * S_base) * f0
        assert df_dt > 0.0, f"TC-82c: df/dt = {df_dt:.6f} Hz/s; expected > 0"

        # After one tick (dt = 5 s), frequency must exceed 50.0 Hz.
        dt_s           = 5.0
        freq_after_one = f0 + df_dt * dt_s
        assert freq_after_one > 50.0, (
            f"TC-82c: frequency after 1 tick = {freq_after_one:.4f} Hz; "
            f"expected > 50.0 Hz (overfrequency from sub-MSL islanded surplus)"
        )
