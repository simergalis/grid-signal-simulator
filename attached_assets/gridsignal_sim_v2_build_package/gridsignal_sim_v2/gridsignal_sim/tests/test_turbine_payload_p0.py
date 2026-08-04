"""
Phase 0 turbine payload self-consistency tests.

TC-P0-1  units_synchronised_count == len([u for u in turbine_units if u["breaker_closed"]]).
TC-P0-2  synchronised_output_mw equals turbine_output_mw when any unit has breaker_closed=True.
TC-P0-3  All breaker_closed=True → count equals unit list length; MW equals fleet total.
TC-P0-4  All breaker_closed=False → count=0, synchronised_output_mw=0.
TC-P0-5  Old dicts without breaker_closed key default to True (backward-compatible).

Acceptance criterion (Phase 0 gate):
  Every _tick_result_to_dict() payload includes units_synchronised_count and
  synchronised_output_mw, and both are self-consistent with the turbine_units array.
"""

import contextlib
import dataclasses


# ── plane-guard context manager (required by evaluate_tick) ──────────────────

@contextlib.contextmanager
def _plane_guard():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


# ── minimal tick builder ─────────────────────────────────────────────────────

def _make_tick(turbine_unit_specs: tuple, turbine_output_mw: float = 5.0):
    """Build a minimal TickResult via evaluate_tick (the authorised path),
    then replace turbine_units and turbine_output_mw with the test fixtures."""
    from core.asset_modules import (
        GPUModule, TurbineModule, BessModule, SolarModule, CoolingModule,
        IrradianceProfile,
    )
    from core.models import (
        SiteConfig, IslandMode, HardwareProfile,
        TurbineConfig, BessConfig, SolarConfig,
    )
    from core.sim_clock import SimClock
    from core.simulation_core import SimulationState, evaluate_tick

    site = SiteConfig(
        site_id="p0-test", pue_base=1.03, uncalibrated=False,
        island_mode=IslandMode.ISLANDED,
    )
    hw      = {"hw-a": HardwareProfile("hw-a", rated_kw=10.0)}
    gpu     = GPUModule(asset_id="gpu-0", site=site, hardware_library=hw)
    turbine = TurbineModule(TurbineConfig(asset_id="t-0", rated_mw=10.0, r_asset_mw_per_s=0.5))
    bess    = BessModule(BessConfig(asset_id="bess-0", rated_mw=10.0, usable_mwh=5.0,
                                    grid_forming=False))
    solar   = SolarModule(SolarConfig(asset_id="sol-0", rated_mw=0.0),
                          irradiance_profile=IrradianceProfile([(0.0, 0.0)]))
    cooling = CoolingModule(asset_id="cool-0", site=site)
    state   = SimulationState(
        run_id="p0-test", site=site, gpu_modules=[gpu],
        turbines=[turbine], bess_units=[bess],
        solar_arrays=[solar], cooling=cooling,
    )
    clock = SimClock(sim_time=0.0, dt_seconds=5.0, wall_stamp_utc=None, rate=1.0, tick_seq=0)

    with _plane_guard():
        base = evaluate_tick(state, clock)

    return dataclasses.replace(
        base,
        turbine_units=turbine_unit_specs,
        turbine_output_mw=turbine_output_mw,
    )


# ── fixtures ─────────────────────────────────────────────────────────────────

# 3 units: t-0 and t-1 on bus (breaker_closed=True), t-2 hot standby (breaker_closed=False).
_MIXED = (
    {"asset_id": "t-0", "rated_mw": 7.0, "r_asset_mw_per_s": 0.2,
     "run_hours_h": None, "gt_mode": "frame", "hot_standby": False,
     "breaker_closed": True,  "no_load_mw": 0.0, "msl_mw": 0.0},
    {"asset_id": "t-1", "rated_mw": 7.0, "r_asset_mw_per_s": 0.2,
     "run_hours_h": None, "gt_mode": "frame", "hot_standby": False,
     "breaker_closed": True,  "no_load_mw": 0.0, "msl_mw": 0.0},
    {"asset_id": "t-2", "rated_mw": 7.0, "r_asset_mw_per_s": 0.2,
     "run_hours_h": None, "gt_mode": "frame", "hot_standby": True,
     "breaker_closed": False, "no_load_mw": 0.0, "msl_mw": 0.0},
)

# 2 units — all on bus, aeroderivative class, non-zero no_load_mw / msl_mw.
_ALL_ONLINE = (
    {"asset_id": "t-0", "rated_mw": 7.0, "r_asset_mw_per_s": 0.2,
     "run_hours_h": None, "gt_mode": "aero", "hot_standby": False,
     "breaker_closed": True, "no_load_mw": 0.5, "msl_mw": 2.0},
    {"asset_id": "t-1", "rated_mw": 7.0, "r_asset_mw_per_s": 0.2,
     "run_hours_h": None, "gt_mode": "aero", "hot_standby": False,
     "breaker_closed": True, "no_load_mw": 0.5, "msl_mw": 2.0},
)

# 1 unit — hot standby, nothing on bus.
_ALL_STANDBY = (
    {"asset_id": "t-0", "rated_mw": 7.0, "r_asset_mw_per_s": 0.2,
     "run_hours_h": None, "gt_mode": "frame", "hot_standby": True,
     "breaker_closed": False, "no_load_mw": 0.0, "msl_mw": 0.0},
)

# Old-format spec dict — no breaker_closed key (pre-Phase-0 scenario JSON).
_LEGACY = (
    {"asset_id": "t-0", "rated_mw": 7.0, "r_asset_mw_per_s": 0.2, "run_hours_h": None},
)


# ── TC-P0-1: mixed fleet — count self-consistency ────────────────────────────

def test_tc_p0_1_mixed_count_equals_filtered_list():
    """units_synchronised_count must equal len([u ... if u["breaker_closed"]]) — §0.2/0.3."""
    from runtime.run_manager import _tick_result_to_dict

    tick    = _make_tick(_MIXED, turbine_output_mw=8.0)
    payload = _tick_result_to_dict(tick)

    synced = [u for u in _MIXED if u["breaker_closed"]]
    assert payload["units_synchronised_count"] == len(synced) == 2, (
        f"Expected count=2, got {payload['units_synchronised_count']}"
    )


# ── TC-P0-2: mixed fleet — MW is non-zero when units are on bus ──────────────

def test_tc_p0_2_mixed_mw_nonzero_when_units_on_bus():
    """synchronised_output_mw equals turbine_output_mw when any unit has breaker_closed=True."""
    from runtime.run_manager import _tick_result_to_dict

    tick    = _make_tick(_MIXED, turbine_output_mw=8.0)
    payload = _tick_result_to_dict(tick)

    assert payload["synchronised_output_mw"] == pytest_approx(8.0), (
        f"Expected synchronised_output_mw=8.0, got {payload['synchronised_output_mw']}"
    )


# ── TC-P0-3: all online — count equals fleet size ────────────────────────────

def test_tc_p0_3_all_online_count_equals_fleet_size():
    """All breaker_closed=True → units_synchronised_count == len(turbine_units)."""
    from runtime.run_manager import _tick_result_to_dict

    tick    = _make_tick(_ALL_ONLINE, turbine_output_mw=10.0)
    payload = _tick_result_to_dict(tick)

    assert payload["units_synchronised_count"] == 2
    assert payload["synchronised_output_mw"] == pytest_approx(10.0)


# ── TC-P0-4: all standby — count zero, MW zero ───────────────────────────────

def test_tc_p0_4_all_standby_zero_count_and_mw():
    """All breaker_closed=False → count=0 and synchronised_output_mw=0.0."""
    from runtime.run_manager import _tick_result_to_dict

    tick    = _make_tick(_ALL_STANDBY, turbine_output_mw=0.0)
    payload = _tick_result_to_dict(tick)

    assert payload["units_synchronised_count"] == 0, (
        f"Expected count=0, got {payload['units_synchronised_count']}"
    )
    assert payload["synchronised_output_mw"] == 0.0, (
        f"Expected MW=0.0, got {payload['synchronised_output_mw']}"
    )


# ── TC-P0-5: backward compatibility — old dicts without breaker_closed ────────

def test_tc_p0_5_legacy_dict_defaults_to_on_bus():
    """Old turbine_units dicts without breaker_closed key default to True (all on bus)."""
    from runtime.run_manager import _tick_result_to_dict

    tick    = _make_tick(_LEGACY, turbine_output_mw=5.0)
    payload = _tick_result_to_dict(tick)

    # Missing breaker_closed → defaults True → treated as synchronised
    assert payload["units_synchronised_count"] == 1, (
        f"Expected legacy unit counted as synchronised, got {payload['units_synchronised_count']}"
    )
    assert payload["synchronised_output_mw"] == pytest_approx(5.0)


# ── helper: pytest.approx for float comparison ───────────────────────────────

def pytest_approx(value: float, abs: float = 1e-4):
    """Thin wrapper so test assertions read clearly without importing pytest at top-level."""
    import pytest
    return pytest.approx(value, abs=abs)


# ── TC-P0-6: sync_relay_state present and correct ────────────────────────────

def test_tc_p0_6_sync_relay_state_from_factory():
    """TC-P0-6: build_run_context_from_spec populates sync_relay_state in each
    per-unit spec dict, derived from hot_standby (Phase 0 static derivation).
      hot_standby=False → "permissive"  (relay granted closure; unit on bus)
      hot_standby=True  → "checking"   (relay matching V/f/θ; not yet on bus)

    Uses build_run_context_from_spec (the authorised factory path) so the test
    covers scenario_factory.py's derivation logic, not just data pass-through.
    """
    import sys, pathlib as _pl
    sys.path.insert(0, str(_pl.Path(__file__).parents[1]))
    from runtime.scenario_factory import build_run_context_from_spec

    _MINIMAL_SPEC = {
        "name": "p0-relay-test",
        "description": "",
        "hardware_profile_id": "hpc-datacenter",
        "dt_lead_seconds": 30,
        "bess_units": [
            {"asset_id": "bess-0", "rated_mw": 10.0, "usable_mwh": 2.0,
             "initial_soc_fraction": 0.9, "grid_forming": True}
        ],
        "turbine_units": [
            {"asset_id": "gt-0", "rated_mw": 10.0, "r_asset_mw_per_s": 0.3,
             "hot_standby": False},
            {"asset_id": "gt-1", "rated_mw": 10.0, "r_asset_mw_per_s": 0.3,
             "hot_standby": True},
        ],
        "solar_rated_mw": 0.0,
        "irradiance_steps": [],
        "island_mode": True,
        "pue_base": 1.03,
        "run_duration_s": 60,
        "location": "Auckland",
        "workload_events": [],
    }

    ctx   = build_run_context_from_spec("test-relay", _MINIMAL_SPEC)
    units = list(ctx.turbine_unit_specs)

    u0 = next(u for u in units if u["asset_id"] == "gt-0")
    u1 = next(u for u in units if u["asset_id"] == "gt-1")

    assert "sync_relay_state" in u0, "gt-0 missing sync_relay_state"
    assert "sync_relay_state" in u1, "gt-1 missing sync_relay_state"
    assert u0["sync_relay_state"] == "permissive", (
        "gt-0: expected 'permissive' (hot_standby=False), got " + repr(u0["sync_relay_state"])
    )
    assert u1["sync_relay_state"] == "checking", (
        "gt-1: expected 'checking' (hot_standby=True), got " + repr(u1["sync_relay_state"])
    )
