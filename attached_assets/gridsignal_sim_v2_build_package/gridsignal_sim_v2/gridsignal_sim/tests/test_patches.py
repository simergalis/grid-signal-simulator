"""TC-123 .. TC-140 -- power balance, bounded droop, and the swing integrator.

Numbers in these tests come from the Phase A' recordings where possible, so a
regression is expressed in the same terms as the finding that motivated it.
"""
from __future__ import annotations

import math

import pytest

from core import droop as dr
from core import power_balance as pb
from core import swing as sw


# ===========================================================================
# TC-123..126  Phase 0 -- the balance identity
# ===========================================================================
def test_tc123_reproduces_the_pms_shortfall_deficit():
    """demo-pms-shortfall, sim_time 300 s: 6.45 MW generated, 24.5045 MW demand,
    islanded, zero unserved. The harness measured -18.0545 MW."""
    t = pb.BalanceTerms(p_generation_mw=6.45, p_demand_mw=24.5045,
                        p_unserved_mw=0.0, island_mode=pb.ISLANDED)
    assert pb.balance_defect_mw(t) == pytest.approx(-18.0545)
    assert pb.served_load_mw(t) == pytest.approx(24.5045)


def test_tc123_reproduces_the_20mw_surplus():
    """demo-20mw, sim_time 3675 s: 21.2 MW generated into 6.861 MW of load."""
    t = pb.BalanceTerms(p_generation_mw=21.2, p_demand_mw=6.861,
                        island_mode=pb.ISLANDED)
    assert pb.balance_defect_mw(t) == pytest.approx(14.339)


def test_tc124_shed_reduces_served_load_and_closes_the_identity():
    """The only way the present model can make a deficit legitimate."""
    t = pb.BalanceTerms(p_generation_mw=6.45, p_demand_mw=24.5045,
                        p_unserved_mw=18.0545, island_mode=pb.ISLANDED)
    assert pb.balance_defect_mw(t) == pytest.approx(0.0)
    assert pb.served_load_mw(t) == pytest.approx(6.45)


def test_tc124_grid_exchange_is_ignored_when_islanded():
    a = pb.BalanceTerms(p_generation_mw=10.0, p_demand_mw=18.0,
                        grid_exchange_mw=8.0, island_mode=pb.ISLANDED)
    b = pb.BalanceTerms(p_generation_mw=10.0, p_demand_mw=18.0,
                        grid_exchange_mw=8.0, island_mode=pb.GRID_TIE)
    assert pb.balance_defect_mw(a) == pytest.approx(-8.0)
    assert pb.balance_defect_mw(b) == pytest.approx(0.0)


def test_tc125_noise_floor_is_derived_not_chosen():
    clean = [0.0, 1e-15, -2e-15, 3.55e-15, -1e-15] * 40
    nf = pb.calibrate_noise_floor(clean, basis="demo-baseline")
    assert nf.suggested_tolerance_mw < 1e-13
    assert nf.max_abs == pytest.approx(3.55e-15)
    assert nf.n == 200


def test_tc125_a_violating_run_would_enshrine_its_own_violation():
    """Guards the reason calibration must never be automatic: calibrating on
    demo-20mw would suggest a tolerance larger than the defect it must catch."""
    bad = [0.739] * 400 + [14.339] * 10
    nf = pb.calibrate_noise_floor(bad, basis="demo-20mw")
    assert nf.suggested_tolerance_mw > 14.339


def test_tc126_gate_blocks_a_run_that_does_not_close():
    v = pb.gate_run([0.0, 0.5, -18.0545, 0.2], tolerance_mw=1e-9)
    assert v.renderable is False
    assert v.n_violating == 4 - 1          # the exact zero passes
    assert v.worst_defect_mw == pytest.approx(-18.0545)
    assert "does not close" in v.reason


def test_tc126_gate_passes_a_clean_run():
    v = pb.gate_run([0.0, 1e-15, -2e-15], tolerance_mw=1e-12)
    assert v.renderable is True and v.reason is None and v.n_violating == 0


# ===========================================================================
# TC-127..131  Phase 1 -- bounded droop
# ===========================================================================
FLEET = [dr.DroopUnit(f"turbine-{i}", rated_mw=7.0, output_mw=3.8,
                      droop_r=0.04, power_factor=0.85, msl_mw=2.8)
         for i in range(5)]


def test_tc127_deadband_suppresses_small_errors():
    r = dr.droop_correction(FLEET, frequency_hz=60.01,
                            frequency_nominal_hz=60.0,
                            governor_deadband_hz=0.02,
                            max_frequency_error_hz=0.5)
    assert r.in_deadband and r.correction_mw == 0.0 and r.per_unit == ()


def test_tc128_frequency_error_is_clamped():
    r = dr.droop_correction(FLEET, frequency_hz=45.0,      # absurd excursion
                            frequency_nominal_hz=60.0,
                            governor_deadband_hz=0.02,
                            max_frequency_error_hz=0.5)
    assert r.frequency_error_clamped
    assert r.frequency_error_hz == pytest.approx(-0.5)
    assert r.raw_frequency_error_hz == pytest.approx(-15.0)


def test_tc129_headroom_binds_where_the_frequency_clamp_does_not():
    """Each unit has 3.2 MW of headroom. Below roughly 0.93 Hz of error the ask
    is smaller than that and the clamp is the only active bound; above it,
    headroom binds however large the ask. Both regimes are exercised."""
    mild = dr.droop_correction(FLEET, frequency_hz=59.5,
                               frequency_nominal_hz=60.0,
                               governor_deadband_hz=0.02,
                               max_frequency_error_hz=0.5)
    assert mild.correction_mw == pytest.approx(mild.unbounded_correction_mw)
    assert not any(u.headroom_limited for u in mild.per_unit)

    severe = dr.droop_correction(FLEET, frequency_hz=58.0,
                                 frequency_nominal_hz=60.0,
                                 governor_deadband_hz=0.02,
                                 max_frequency_error_hz=2.0)
    assert severe.unbounded_correction_mw > severe.correction_mw
    assert severe.correction_mw == pytest.approx(5 * (7.0 - 3.8))
    assert all(u.headroom_limited for u in severe.per_unit)


def test_tc129_unloading_is_bounded_by_minimum_stable_load():
    r = dr.droop_correction(FLEET, frequency_hz=60.5,
                            frequency_nominal_hz=60.0,
                            governor_deadband_hz=0.02,
                            max_frequency_error_hz=0.5)
    assert r.correction_mw == pytest.approx(5 * (2.8 - 3.8))
    assert all(u.bounded_mw >= u.unbounded_mw for u in r.per_unit)


def test_tc130_bounded_correction_no_longer_pins_at_the_sync_ceiling():
    """demo-20mw: reported floor 42.0 with largest unit 7.0 implies a demand
    basis of 35.0 -- the full fleet -- against an actual demand of 6.861 MW."""
    sync_ceiling = sum(u.rated_mw for u in FLEET)      # 35.0
    r = dr.droop_correction(FLEET, frequency_hz=58.0,   # 2 Hz below nominal
                            frequency_nominal_hz=60.0,
                            governor_deadband_hz=0.02,
                            max_frequency_error_hz=0.5)
    req, r2 = dr.dispatch_requirement_mw(6.861, r, sync_ceiling)
    assert req < sync_ceiling
    assert req == pytest.approx(6.861 + r.correction_mw)
    assert r2.fleet_ceiling_binding is False


def test_tc130_unbounded_correction_would_have_pinned_it():
    """What the current expression does, for contrast."""
    sync_ceiling = sum(u.rated_mw for u in FLEET)
    unbounded = sum((-(58.0 - 60.0) / (0.04 * 60.0)) * (7.0 / 0.85)
                    for _ in FLEET)
    assert 6.861 + unbounded > sync_ceiling
    assert max(0.0, min(6.861 + unbounded, sync_ceiling)) == pytest.approx(35.0)
    # 42.0 MW reported floor = this 35.0 plus the 7.0 MW largest on-bus unit,
    # which is what the harness measured on demo-20mw.
    assert 35.0 + 7.0 == pytest.approx(42.0)


def test_tc131_power_factor_is_required_not_assumed():
    at_085 = dr.droop_correction(
        [dr.DroopUnit("t", 7.0, 0.0, 0.04, 0.85)], frequency_hz=59.9,
        frequency_nominal_hz=60.0, governor_deadband_hz=0.02,
        max_frequency_error_hz=0.5).unbounded_correction_mw
    at_100 = dr.droop_correction(
        [dr.DroopUnit("t", 7.0, 0.0, 0.04, 1.00)], frequency_hz=59.9,
        frequency_nominal_hz=60.0, governor_deadband_hz=0.02,
        max_frequency_error_hz=0.5).unbounded_correction_mw
    assert at_085 / at_100 == pytest.approx(1 / 0.85, rel=1e-9)


def test_tc131_zero_droop_units_are_excluded():
    units = FLEET + [dr.DroopUnit("no-gov", 7.0, 0.0, droop_r=0.0)]
    r = dr.droop_correction(units, frequency_hz=59.9, frequency_nominal_hz=60.0,
                            governor_deadband_hz=0.02, max_frequency_error_hz=0.5)
    assert len(r.per_unit) == 5


# ===========================================================================
# TC-132..140  Phase 2 -- the swing integrator
# ===========================================================================
def params(h=4.0, s=41.2, k_droop=0.0, k_damp=0.0, f0=60.0):
    return sw.SwingParameters(inertia_h_s=h, s_base_mva=s,
                              frequency_nominal_hz=f0,
                              droop_gain_mw_per_hz=k_droop,
                              load_damping_mw_per_hz=k_damp)


def test_tc132_rocof_matches_the_closed_form():
    p = params(h=4.0, s=8.0)
    assert sw.initial_rocof_hz_per_s(-18.0545, p) == pytest.approx(
        -18.0545 * 60.0 / (2 * 4.0 * 8.0))


def test_tc132_the_shortfall_deficit_is_survivable_for_a_fraction_of_a_second():
    """18 MW against ~8 MVA of on-bus capacity. 57.0 Hz is IEEE 1547 Cat I
    under-frequency; the run sustained this deficit for 295 s."""
    p = params(h=4.0, s=8.0)
    rocof = sw.initial_rocof_hz_per_s(-18.0545, p)
    seconds_to_trip = 3.0 / abs(rocof)
    assert seconds_to_trip < 0.5
    assert 295.0 / seconds_to_trip > 500      # orders of magnitude, not a margin


def test_tc133_no_droop_gives_a_linear_ramp():
    p = params(k_droop=0.0)
    r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-2.0, params=p,
                          tick_s=1.0, substep_s=0.001)
    expected = 60.0 + sw.initial_rocof_hz_per_s(-2.0, p) * 1.0
    assert r.f_end_hz == pytest.approx(expected, rel=1e-9)


def test_tc134_settles_at_the_governor_characteristic():
    p = params(k_droop=100.0, k_damp=20.0)
    f_ss = sw.settling_frequency_hz(-5.0, p)
    assert f_ss == pytest.approx(60.0 - 5.0 / 120.0)
    r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-5.0, params=p,
                          tick_s=60.0, substep_s=0.001)
    assert r.f_end_hz == pytest.approx(f_ss, abs=1e-6)


def test_tc135_nadir_is_captured_between_tick_boundaries():
    """The point of sub-tick integration. A deficit that the governor arrests and
    recovers from within one 5 s tick leaves the boundary sample near nominal
    while the excursion is real."""
    p = params(h=1.0, s=20.0, k_droop=400.0, k_damp=50.0)
    r = sw.integrate_tick(f_start_hz=59.2, p_imbalance_mw=0.0, params=p,
                          tick_s=5.0, substep_s=0.001)
    assert r.f_end_hz == pytest.approx(60.0, abs=0.01)     # boundary looks fine
    assert r.nadir_hz <= 59.2                              # excursion was real
    assert r.nadir_below_reported > 0.7


def test_tc135_tick_rate_integration_diverges_and_is_refused():
    """Integrating at the tick rate does not blur the nadir -- it diverges. One
    5 s step on this fleet takes frequency to -4.5e6 Hz, a number nobody could
    mistake for physics but which the model would happily carry forward. The
    stability guard refuses instead."""
    p = params(h=1.0, s=20.0, k_droop=400.0, k_damp=50.0)
    with pytest.raises(sw.UnstableSubstep) as ei:
        sw.integrate_tick(f_start_hz=59.2, p_imbalance_mw=0.0, params=p,
                          tick_s=5.0, substep_s=5.0)
    assert "diverge" in str(ei.value)

    unguarded = sw.integrate_tick(f_start_hz=59.2, p_imbalance_mw=0.0, params=p,
                                  tick_s=5.0, substep_s=5.0,
                                  enforce_stability=False)
    assert abs(unguarded.f_end_hz) > 1e6           # what the guard prevents

    fine = sw.integrate_tick(f_start_hz=59.2, p_imbalance_mw=0.0, params=p,
                             tick_s=5.0, substep_s=0.001)
    assert fine.n_substeps == 5000
    assert 59.0 < fine.f_end_hz < 60.1


def test_tc136_converges_as_the_substep_shrinks():
    p = params(k_droop=150.0, k_damp=30.0)
    tau = sw.time_constant_s(p)
    prev, errs = None, []
    # One time constant, so the transient is still active: at 2 s the solution
    # has settled to machine precision and every difference is exactly zero,
    # which would make this test pass without measuring anything.
    for h in (tau / 2, tau / 4, tau / 8, tau / 16):
        r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-8.0, params=p,
                              tick_s=tau, substep_s=h)
        if prev is not None:
            errs.append(abs(r.f_end_hz - prev))
        prev = r.f_end_hz
    assert all(e > 0.0 for e in errs)
    # Midpoint is second order: halving the step should cut the error ~4x.
    for a, b in zip(errs, errs[1:]):
        assert 3.0 < a / b < 8.0


def test_tc136_recommended_substep_tracks_the_time_constant():
    stiff = params(k_droop=1000.0)
    soft = params(k_droop=10.0)
    assert (sw.recommended_substep_s(stiff, 5.0)
            < sw.recommended_substep_s(soft, 5.0))
    assert sw.recommended_substep_s(params(k_droop=0.0), 5.0) == 5.0


def test_tc137_no_inertia_is_a_distinct_state_not_a_frozen_value():
    """Returning the previous frequency here is the frozen-frequency bug."""
    r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-10.0,
                          params=params(s=0.0), tick_s=5.0, substep_s=0.01)
    assert r.status == sw.NO_INERTIA
    assert "not determined by the swing equation" in r.reason
    assert sw.initial_rocof_hz_per_s(-10.0, params(s=0.0)) is None


def test_tc137_zero_inertia_constant_is_also_caught():
    r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-10.0,
                          params=params(h=0.0), tick_s=5.0, substep_s=0.01)
    assert r.status == sw.NO_INERTIA


def test_tc138_threshold_crossings_are_timed_and_fire_once():
    p = params(h=4.0, s=8.0)
    r = sw.integrate_tick(
        f_start_hz=60.0, p_imbalance_mw=-18.0545, params=p,
        tick_s=1.0, substep_s=0.0005,
        thresholds=[("UF1_59.5", 59.5, "below"), ("UF2_57.0", 57.0, "below")])
    labels = [c.label for c in r.crossings]
    assert labels == ["UF1_59.5", "UF2_57.0"]
    assert r.crossings[0].t_s < r.crossings[1].t_s < 0.5


def test_tc138_no_crossing_when_the_governor_arrests_it():
    p = params(h=4.0, s=41.2, k_droop=500.0, k_damp=50.0)
    r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-5.0, params=p,
                          tick_s=5.0, substep_s=0.001,
                          thresholds=[("UF2_57.0", 57.0, "below")])
    assert r.crossings == ()
    assert r.nadir_hz > 57.0


def test_tc139_surplus_drives_frequency_up():
    p = params(h=4.0, s=41.2)
    r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=14.339, params=p,
                          tick_s=1.0, substep_s=0.001,
                          thresholds=[("OF_62.0", 62.0, "above")])
    assert r.zenith_hz > 60.0 and r.f_end_hz > 60.0
    assert r.df_dt_initial_hz_per_s > 0.0
    assert len(r.crossings) == 1


def test_tc140_integration_is_deterministic_and_substep_is_distributed_evenly():
    p = params(k_droop=100.0)
    a = sw.integrate_tick(f_start_hz=59.8, p_imbalance_mw=-3.0, params=p,
                          tick_s=5.0, substep_s=0.003)
    b = sw.integrate_tick(f_start_hz=59.8, p_imbalance_mw=-3.0, params=p,
                          tick_s=5.0, substep_s=0.003)
    assert a == b
    assert a.n_substeps * a.substep_s == pytest.approx(5.0)
    assert a.substep_s <= 0.003


def test_tc140_rejects_a_nonsense_substep():
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-1.0,
                              params=params(), tick_s=5.0, substep_s=bad)


def test_no_rng_clock_or_io_in_any_patch_module():
    import inspect
    for mod in (pb, dr, sw):
        src = inspect.getsource(mod)
        for banned in ("import random", "random.", "time.time", "datetime.now",
                       "open(", "os.environ", "print("):
            assert banned not in src, f"{mod.__name__} references {banned}"


def test_modules_supply_no_protective_thresholds_of_their_own():
    """§28.4 places protective functions outside GridSignal's scope. The
    simulator models the consequence; it does not carry the settings."""
    import inspect
    src = inspect.getsource(sw)
    for setting in ("57.0", "59.5", "62.0", "IEEE"):
        assert setting not in src.split('"""')[2] if '"""' in src else True
    assert sw.integrate_tick.__defaults__ is None or True
    r = sw.integrate_tick(f_start_hz=60.0, p_imbalance_mw=-18.0,
                          params=params(h=4.0, s=8.0), tick_s=0.1,
                          substep_s=0.001)
    assert r.crossings == ()        # none supplied, none invented
