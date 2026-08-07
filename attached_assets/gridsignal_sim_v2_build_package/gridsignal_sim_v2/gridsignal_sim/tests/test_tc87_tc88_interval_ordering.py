"""
tests/test_tc87_tc88_interval_ordering.py — Interval-ordering correctness tests.

TC-87  Ramp is rate-determined, not setpoint-determined.
       A SYNCHRONISED unit driven by apply_loading() toward a constant HIGH
       setpoint accumulates output at exactly n × r_asset × dt per tick,
       independent of the setpoint value.
       (Phase D repair: RAMPING state deleted; equivalent test uses SYNCHRONISED
       + begin_interval() + apply_loading().)

TC-88  A unit promoted STARTING → SYNCHRONISED during advance() is NOT loaded
       in the interval of its promotion.  Its first loaded interval is the next
       tick.

Both tests are part of Phase B of DR-2026-08-06 (interval-entry state snapshot).

Spec numbers reserved:
  TC-87 = "output at interval n equals accumulated integral"
  TC-88 = "a unit promoted during advance() is not loaded in that interval"

TC-88 uses evaluate_tick() directly so it exercises the production code path in
simulation_core.py.  The pre-fix vs. post-fix difference is driven by Item 1 of
Phase B: _synchronised_units built from entry states (not live states).

Pre-fix confirmation (required by spec):
  Run TC-88 BEFORE implementing Item 1 → it must FAIL.
  Run TC-88 AFTER implementing Item 1 → it must PASS.
  Both results must be reported.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# TC-87 — ramp output equals the accumulated integral at every interval
# ---------------------------------------------------------------------------

def test_tc87_ramp_output_equals_accumulated_integral():
    """TC-87 — ramp is rate-determined, not setpoint-determined.

    A RAMPING turbine is given a CONSTANT HIGH setpoint equal to rated_mw
    (7.0 MW).  At each interval n the output must equal the accumulated
    rate integral n × r_asset × dt, regardless of how far the setpoint
    exceeds the current output.

    Why a constant HIGH setpoint proves rate-determination
    -------------------------------------------------------
    If the setpoint were rising in lock-step with the ramp (setpoint_n =
    n × r_asset × dt), a wrong implementation that snaps to the setpoint
    would also produce the correct numerical answer — the test would be
    satisfied for the wrong reason.

    With setpoint = rated_mw = 7.0 MW (constant, always above the ramp):
      correct (rate-limited): output_1 = 1.0 MW, output_2 = 2.0 MW, …
      wrong  (setpoint-snap): output_1 = 7.0 MW — fails immediately at n=1.

    The test is therefore demonstrably NOT satisfiable by a setpoint-tracking
    implementation.

    Transition tick (n=7)
    ---------------------
    At n=7 the ramp reaches rated_mw and advance() transitions the unit
    RAMPING → SYNCHRONISED.  The test verifies the output at this tick
    still equals the accumulated integral (7.0 MW = 7 × 1.0 MW/tick).

    Spec ref: DR-2026-08-06 Phase B, §7.1.3.1 rate-determination requirement.
    """
    from core.asset_modules import TurbineModule, TurbineState
    from core.models import TurbineConfig
    from core.loading import apply_loading

    rated_mw  = 7.0
    r_asset   = 0.2      # MW/s
    dt        = 5.0      # s  (standard tick)
    max_delta = r_asset * dt   # 1.0 MW per tick

    t = TurbineModule(
        TurbineConfig(asset_id="t-tc87", rated_mw=rated_mw, r_asset_mw_per_s=r_asset)
    )
    # Phase D repair: RAMPING state deleted; set SYNCHRONISED directly so
    # apply_loading() can drive the unit at the rate-limited step r_asset × dt.
    t.state = TurbineState.SYNCHRONISED

    for n in range(1, 8):    # 7 ticks to reach rated_mw (7.0 / 1.0 = 7 ticks)
        t.begin_interval()
        apply_loading([t], rated_mw, dt)
        expected = min(rated_mw, n * max_delta)
        actual   = t.output_mw()
        assert abs(actual - expected) < 1e-6, (
            f"TC-87 FAIL at tick {n}: output={actual:.6f} MW ≠ {expected:.6f} MW "
            f"(accumulated integral = n×r×dt = {n}×{r_asset}×{dt}={expected:.4f}). "
            f"Ramp must be RATE-LIMITED, not setpoint-clamped. "
            f"A wrong setpoint-snap implementation would give {rated_mw:.1f} MW "
            f"at tick 1 (setpoint) instead of {max_delta:.1f} MW (rate integral)."
        )

    # Post-condition: unit remains SYNCHRONISED throughout (no transition in this test).
    assert t.state == TurbineState.SYNCHRONISED, (
        f"TC-87 post-condition: turbine must be SYNCHRONISED, got {t.state.value}"
    )


# ---------------------------------------------------------------------------
# TC-88 — promoted unit is not loaded in the promotion interval
# ---------------------------------------------------------------------------

def test_tc88_promoted_unit_not_loaded_in_promotion_interval():
    """TC-88 — a unit promoted RAMPING → SYNCHRONISED during advance() is
    NOT loaded in the interval of its promotion.

    Setup
    -----
    A single turbine starts the interval at 2.0 MW, RAMPING toward 3.0 MW.
    One advance() call raises output to 3.0 MW and transitions the state to
    SYNCHRONISED.

    With net demand ≈ 0 (no GPU load, no solar), the loading-layer would
    drive the unit from 3.0 MW DOWN toward 0 MW (at r_asset × dt = 1.0 MW/tick),
    giving output = 2.0 MW.

    PRE-FIX (this test FAILS):
      simulation_core.py builds _synchronised_units from LIVE state after advance().
      The promoted unit (entry state = RAMPING, live state = SYNCHRONISED) is
      included.  apply_loading() steps it from 3.0 → 2.0 MW.
      Assertion 3.0 MW fails.

    POST-FIX (this test PASSES):
      _synchronised_units built from interval-entry states captured before advance().
      Entry state = RAMPING → unit excluded.  apply_loading() is not called on it.
      Ramp endpoint 3.0 MW is preserved.  Output = 3.0 MW.

    This test calls evaluate_tick() directly to exercise the real production
    code path in simulation_core.py.  The pre-fix vs. post-fix outcome is
    driven exclusively by the Item 1 change in that file.

    Spec ref: DR-2026-08-06 Phase B, Item 1 "interval-entry state snapshot."
    Confirmation required: TC-88 must FAIL before Item 1 and PASS after.
    Both results must be reported.
    """
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    from core.asset_modules import (
        BessModule, CoolingModule, IrradianceProfile,
        SolarModule, TurbineModule, TurbineState,
    )
    from core.models import (
        BessConfig, IslandMode, SiteConfig, SolarConfig,
        TurbineConfig,
    )
    from core.simulation_core import SimulationState, evaluate_tick
    from core.sim_clock import SimClock

    dt = 5.0   # s

    site = SiteConfig(
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        site_id="tc88-site",
        pue_base=1.03,
        dt_thermal_seconds=90.0,
        tau_seconds=20.0,
        alpha_max=0.9,
    )

    rated_mw = 7.0
    r_asset  = 0.2          # MW/s  → max_delta = 1.0 MW per tick

    # Unit at 3.0 MW STARTING with exactly dt remaining to SYNCHRONISED.
    # Phase D repair: RAMPING state deleted; use STARTING with _time_to_online_s = dt
    # so one advance() call decrements to 0 and promotes to SYNCHRONISED.
    # _current_output_mw=3.0 is the value that must be preserved through promotion.
    turbine = TurbineModule(
        TurbineConfig(asset_id="t-tc88", rated_mw=rated_mw, r_asset_mw_per_s=r_asset)
    )
    turbine.command_start(sim_time=0.0)        # OFFLINE → STARTING; sets _time_to_online_s
    turbine._time_to_online_s = dt             # override: exactly one tick to SYNCHRONISED
    turbine._current_output_mw = 3.0           # ramp endpoint to be preserved

    state = SimulationState(
        run_id="tc88-run",
        site=site,
        gpu_modules=[],          # no GPU load → net_demand ≈ 0
        turbines=[turbine],
        bess_units=[
            BessModule(BessConfig(
                asset_id="bess-tc88",
                rated_mw=18.0,
                usable_mwh=8.0,
                initial_soc_fraction=0.95,
                grid_forming=True,
            ))
        ],
        solar_arrays=[
            SolarModule(
                config=SolarConfig(asset_id="solar-tc88", rated_mw=0.0),
                irradiance_profile=IrradianceProfile([(0.0, 0.0)]),
            )
        ],
        cooling=CoolingModule(asset_id="cooling-tc88", site=site),
    )

    clock = SimClock(sim_time=0.0, dt_seconds=dt, wall_stamp_utc=0.0, rate=0.0, tick_seq=1)

    # Grant plane permission (test callers must manage the sentinel directly).
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        evaluate_tick(state, clock)
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)

    # Post-condition 1: turbine must have promoted to SYNCHRONISED.
    assert turbine.state == TurbineState.SYNCHRONISED, (
        f"TC-88 pre-condition: advance() must promote unit to SYNCHRONISED. "
        f"Got: {turbine.state.value}.  "
        f"Check: command_start(); _time_to_online_s=dt, _current_output_mw=3.0 "
        f"→ should promote to SYNCHRONISED after one advance()."
    )

    # Post-condition 2: output must equal the ramp endpoint (3.0 MW).
    #
    # With net_demand ≈ 0, the loading layer would step the unit from
    # 3.0 MW toward 0 MW at rate 1.0 MW/tick → output = 2.0 MW (pre-fix).
    # Any deviation from 3.0 MW means apply_loading() ran on the promoted unit
    # in the promotion interval — the Item 1 defect.
    assert abs(turbine.output_mw() - 3.0) < 1e-6, (
        f"TC-88 FAIL: promoted unit output = {turbine.output_mw():.6f} MW ≠ 3.0 MW. "
        f"apply_loading() ran on the unit in its promotion interval, overwriting "
        f"_current_output_mw.  "
        f"PRE-FIX cause: _synchronised_units built from live state after advance(); "
        f"promoted unit (entry=STARTING, live=SYNCHRONISED) is included. "
        f"FIX (Item 1): snapshot entry states before advance(); build "
        f"_synchronised_units from entry states so promoted units are excluded "
        f"until the NEXT interval."
    )
