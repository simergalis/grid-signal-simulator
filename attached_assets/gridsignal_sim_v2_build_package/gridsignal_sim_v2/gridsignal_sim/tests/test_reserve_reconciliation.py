"""DR-2026-09-02-RESERVE-RECONCILIATION coverage."""

from __future__ import annotations

import contextlib

import pytest

from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import BessModule, CoolingModule, DieselModule
from core.dispatch import DispatchArbitrator, MARGIN_MULTIPLIER
from core.models import BessConfig, DieselConfig, IslandMode, SiteConfig
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick


@contextlib.contextmanager
def _plane_guard_active():
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _site(depth_fraction: float = 0.0) -> SiteConfig:
    return SiteConfig(
        site_id="reserve-reconciliation",
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        pue_base=1.03,
        island_mode=IslandMode.ISLANDED,
        bess_normal_dispatch_depth_fraction=depth_fraction,
    )


def _diesel(
    *,
    rated_mw: float = 5.0,
    delta_t_start_s: float = 10.0,
    residual_ramp_s: float = 8.0,
) -> DieselModule:
    return DieselModule(
        DieselConfig(
            asset_id="diesel-reserve",
            rated_mw=rated_mw,
            role="primary",
            delta_t_start_s=delta_t_start_s,
            residual_ramp_s=residual_ramp_s,
        )
    )


def _bess(
    *,
    rated_mw: float = 10.0,
    usable_mwh: float = 10.0,
    initial_soc_fraction: float = 1.0,
) -> BessModule:
    return BessModule(
        BessConfig(
            asset_id="bess-reserve",
            rated_mw=rated_mw,
            usable_mwh=usable_mwh,
            initial_soc_fraction=initial_soc_fraction,
            bess_response_tau_s=0.0,
        )
    )


def test_tc_r1_zero_depth_nonzero_diesel_uses_diesel_floor() -> None:
    bess = _bess(rated_mw=4.0, usable_mwh=4.0)
    arbitrator = DispatchArbitrator(
        [], [bess], _site(0.0), diesel_units=[_diesel(
            delta_t_start_s=20.0,
            residual_ramp_s=8.0,
        )]
    )

    expected = MARGIN_MULTIPLIER * 4.0 * (28.0 / 3600.0)
    assert arbitrator.soc_floor_mwh(bess) == pytest.approx(expected)


def test_tc_r2_depth_reserve_wins_when_diesel_floor_is_smaller() -> None:
    bess = _bess(rated_mw=10.0, usable_mwh=100.0, initial_soc_fraction=0.95)
    arbitrator = DispatchArbitrator(
        [], [bess], _site(0.03), diesel_units=[_diesel(
            delta_t_start_s=10.0,
            residual_ramp_s=8.0,
        )]
    )

    depth_reserve = 100.0 * (0.95 - 0.03)
    diesel_floor = MARGIN_MULTIPLIER * 10.0 * (18.0 / 3600.0)
    assert diesel_floor < depth_reserve
    assert arbitrator.soc_floor_mwh(bess) == pytest.approx(depth_reserve)


def test_tc_r3_diesel_floor_wins_when_depth_reserve_is_smaller() -> None:
    bess = _bess(rated_mw=4.0, usable_mwh=10.0, initial_soc_fraction=0.95)
    arbitrator = DispatchArbitrator(
        [], [bess], _site(0.03), diesel_units=[_diesel(
            rated_mw=4.0,
            delta_t_start_s=2000.0,
            residual_ramp_s=1600.0,
        )]
    )

    depth_reserve = 10.0 * (0.95 - 0.03)
    diesel_floor = MARGIN_MULTIPLIER * 4.0
    assert depth_reserve < diesel_floor
    assert arbitrator.soc_floor_mwh(bess) == pytest.approx(diesel_floor)


def _live_state(*, depth_fraction: float, soc_mwh: float) -> SimulationState:
    site = _site(depth_fraction)
    bess = _bess(rated_mw=10.0, usable_mwh=20.0)
    bess.soc_mwh = soc_mwh
    state = SimulationState(
        run_id="reserve-reconciliation-live",
        site=site,
        gpu_modules=[],
        turbines=[],
        bess_units=[bess],
        solar_arrays=[],
        cooling=CoolingModule(asset_id="cooling-reserve", site=site),
        diesel_units=[_diesel(
            rated_mw=10.0,
            delta_t_start_s=1000.0,
            residual_ramp_s=440.0,
        )],
    )
    state.compute_floor_mw = 10.0
    return state


def _run_live_tick(state: SimulationState) -> tuple[dict, object]:
    captured: dict = {}
    original_tick = state.arbitrator.tick

    def capture_tick(*args, **kwargs):
        captured.update(kwargs)
        return original_tick(*args, **kwargs)

    state.arbitrator.tick = capture_tick  # type: ignore[method-assign]
    with _plane_guard_active():
        result = evaluate_tick(
            state,
            SimClock(
                sim_time=0.0,
                dt_seconds=3600.0,
                wall_stamp_utc=None,
                rate=1.0,
                tick_seq=0,
            ),
        )
    return captured, result


def test_tc_r4_emergency_release_authorizes_both_layers() -> None:
    # At the reconciled 10 MWh diesel floor, normal energy is exhausted.
    # The 10 MW compute floor creates a positive emergency gap.
    state = _live_state(depth_fraction=0.0, soc_mwh=10.0)
    captured, result = _run_live_tick(state)

    assert captured["bess_dispatch_ceilings_mw"] == pytest.approx([10.0])
    assert captured["bess_soc_floors_mwh"] == pytest.approx([0.0])
    assert result.bess_output_mw == pytest.approx(10.0)


def test_tc_r5_routine_dispatch_keeps_reconciled_floor() -> None:
    # With 20 MWh available and a 10 MWh reconciled floor, normal dispatch
    # has 10 MW available and the emergency branch must remain closed.
    state = _live_state(depth_fraction=0.0, soc_mwh=20.0)
    captured, result = _run_live_tick(state)

    assert captured["bess_dispatch_ceilings_mw"] == pytest.approx([10.0])
    assert captured["bess_soc_floors_mwh"] == pytest.approx([10.0])
    assert result.bess_output_mw == pytest.approx(10.0)
    assert state.bess_units[0].soc_mwh == pytest.approx(10.0)