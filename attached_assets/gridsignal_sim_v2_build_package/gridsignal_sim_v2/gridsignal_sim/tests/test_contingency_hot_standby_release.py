"""Phase 3b: contingency-triggered hot-standby turbine release."""

from __future__ import annotations

from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    TurbineModule,
    TurbineState,
)
from core.commitment import CommitmentConfig
from core.models import (
    BessConfig,
    ContingencyState,
    IslandMode,
    SiteConfig,
    ThermalState,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from runtime.run_manager import _tick_result_to_dict


def _make_state(*, hot_start_s: float = 5.0) -> SimulationState:
    site = SiteConfig(
        site_id="phase3b-test",
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        pue_base=1.0,
        alpha_max=0.0,
        tau_seconds=20.0,
        dt_thermal_seconds=90.0,
        island_mode=IslandMode.GRID_TIE,
    )
    turbines: list[TurbineModule] = []
    for asset_id, hot_standby, p_min, thermal_state in (
        ("turbine-0", False, 0.8, ThermalState.HOT),
        ("turbine-1", False, 0.8, ThermalState.HOT),
        ("turbine-2", False, 0.0, ThermalState.HOT),
        ("hot-standby-1", True, 0.4, ThermalState.HOT),
        ("hot-standby-2", True, 0.4, ThermalState.WARM),
    ):
        turbine = TurbineModule(
            TurbineConfig(
                asset_id=asset_id,
                rated_mw=10.0,
                r_asset_mw_per_s=0.2,
                hot_standby=hot_standby,
                initial_thermal_state=thermal_state,
                p_min_stable_frac=p_min,
                hot_start_s=hot_start_s,
                warm_start_s=hot_start_s,
                cold_start_s=hot_start_s,
                min_run_enabled=False,
                min_down_enabled=False,
            )
        )
        if not hot_standby:
            turbine.state = TurbineState.SYNCHRONISED
        turbines.append(turbine)

    state = SimulationState(
        run_id="phase3b-run",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library={})],
        turbines=turbines,
        bess_units=[
            BessModule(
                BessConfig(
                    asset_id="bess-0",
                    rated_mw=8.0,
                    usable_mwh=8.0,
                    initial_soc_fraction=1.0,
                    grid_forming=False,
                )
            )
        ],
        solar_arrays=[],
        cooling=CoolingModule(asset_id="cooling-0", site=site),
    )
    # Drive two active turbines to their 8 MW minimum-stable output.  The
    # third active turbine remains at 0 MW, giving a real pre-trip COVERED
    # state and a post-UNIT_TRIP COVERED_WITH_SHED state.
    state.compute_floor_mw = 16.0
    return state


def _tick(state: SimulationState, sim_time: float):
    clock = SimClock(
        sim_time=sim_time,
        dt_seconds=5.0,
        wall_stamp_utc=sim_time,
        rate=0.0,
        tick_seq=int(sim_time / 5.0) + 1,
    )
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        return evaluate_tick(state, clock)
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _trip(asset_id: str, sim_time: float) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"trip-{asset_id}",
        job_id=asset_id,
        event_type=WorkloadEventType.UNIT_TRIP,
        timestamp=sim_time,
        hardware_profile_id="",
        node_count=0,
        workload_class=WorkloadClass.OTHER,
        site_id="phase3b-test",
    )


def _warm_to_steady_state(state: SimulationState) -> list:
    return [_tick(state, sim_time) for sim_time in range(0, 50, 5)]


def test_phase3b_unit_trip_degrades_coverage_and_releases_one_hot_standby():
    """UNIT_TRIP produces a real COVERED → COVERED_WITH_SHED release episode."""
    state = _make_state(hot_start_s=120.0)
    pre_trip = _warm_to_steady_state(state)
    assert {tick.contingency_coverage.state for tick in pre_trip} == {
        ContingencyState.COVERED
    }

    state.apply_workload_signal(_trip("turbine-2", 50.0), dt_lead_seconds=0.0)
    post_trip = [_tick(state, sim_time) for sim_time in range(50, 66, 5)]

    assert post_trip[0].contingency_coverage.state == ContingencyState.COVERED_WITH_SHED
    release_ticks = [tick for tick in post_trip if tick.contingency_release_alert]
    assert len(release_ticks) == 1
    alert_tick = release_ticks[0]

    assert alert_tick.contingency_release_turbine_id == "hot-standby-1"
    assert (
        alert_tick.contingency_release_coverage_state
        == ContingencyState.COVERED_WITH_SHED.value
    )
    assert alert_tick.contingency_release_shed_mw == 6.0
    assert alert_tick.contingency_release_sim_time_s == 60.0
    released = next(t for t in state.turbines if t.asset_id == "hot-standby-1")
    assert released.state == TurbineState.STARTING
    assert released.config.hot_standby is False

    payload = _tick_result_to_dict(alert_tick)
    assert payload["contingency_release_alert"] is True
    assert payload["contingency_release_turbine_id"] == "hot-standby-1"
    assert payload["contingency_release_coverage_state"] == "COVERED_WITH_SHED"
    assert payload["contingency_release_shed_mw"] == 6.0
    assert payload["contingency_release_sim_time_s"] == 60.0


def test_phase3b_elevated_demand_without_trip_does_not_release_hot_standby():
    """Ordinary demand remains on the independent commitment path."""
    state = _make_state()
    ticks = _warm_to_steady_state(state)

    assert all(tick.contingency_coverage.state == ContingencyState.COVERED for tick in ticks)
    assert all(not tick.contingency_release_alert for tick in ticks)
    assert all(
        turbine.config.hot_standby
        for turbine in state.turbines
        if turbine.asset_id.startswith("hot-standby")
    )
    assert state._contingency_release_cond.sustained_s == 0.0
    assert state.site.cascade_commit_fraction is None


def test_phase3b_persistent_contingency_releases_only_one_hot_standby():
    """A bad episode cannot release a second standby while the first is starting."""
    state = _make_state(hot_start_s=120.0)
    _warm_to_steady_state(state)
    state.apply_workload_signal(_trip("turbine-2", 50.0), dt_lead_seconds=0.0)

    ticks = [_tick(state, sim_time) for sim_time in range(50, 151, 5)]
    release_ticks = [tick for tick in ticks if tick.contingency_release_alert]
    assert len(release_ticks) == 1
    assert release_ticks[0].contingency_release_turbine_id == "hot-standby-1"
    assert sum(
        not turbine.config.hot_standby
        for turbine in state.turbines
        if turbine.asset_id.startswith("hot-standby")
    ) == 1
    second = next(t for t in state.turbines if t.asset_id == "hot-standby-2")
    assert second.state == TurbineState.OFFLINE
    assert second.config.hot_standby is True


def test_phase3b_config_keeps_ordinary_commitment_and_phase3a_paths_separate():
    """The new timing knob is independent of ordinary and cascade controls."""
    cfg = CommitmentConfig.from_catalogue()
    assert cfg.contingency_release_confirm_s == 12.0
    assert cfg.commit_confirm_s == 30.0
    assert cfg.decommit_confirm_s == 300.0

    state = _make_state()
    assert state.site.cascade_commit_fraction is None
    assert state._pending_start.is_empty
    assert state._commit_cond.sustained_s == 0.0
    assert state._contingency_release_cond.sustained_s == 0.0