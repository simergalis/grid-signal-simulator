"""Regression coverage for physical BESS dispatch around fuel-cell output."""

from __future__ import annotations

import contextlib

import pytest

from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import BessModule, CoolingModule
from core.fuel_cell_module import FuelCellConfig, FuelCellModule, FuelCellState
from core.models import BessConfig, IslandMode, SiteConfig
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick


@contextlib.contextmanager
def _plane_guard_active():
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _state(*, demand_mw: float, bess: BessModule) -> SimulationState:
    site = SiteConfig(
        site_id="fc-bess-physical-dispatch",
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        pue_base=1.03,
        island_mode=IslandMode.ISLANDED,
    )
    state = SimulationState(
        run_id="fc-bess-physical-dispatch",
        site=site,
        gpu_modules=[],
        turbines=[],
        bess_units=[bess],
        solar_arrays=[],
        cooling=CoolingModule(asset_id="cooling", site=site),
    )
    state.compute_floor_mw = demand_mw
    return state


def _tick(state: SimulationState, *, dt_seconds: float = 5.0):
    with _plane_guard_active():
        return evaluate_tick(
            state,
            SimClock(
                sim_time=0.0,
                dt_seconds=dt_seconds,
                wall_stamp_utc=None,
                rate=1.0,
                tick_seq=0,
            ),
        )


def test_fc_achieved_output_equal_to_demand_does_not_dispatch_bess() -> None:
    """An FC adjusted to physical demand does not cause baseline BESS output."""
    bess = BessModule(BessConfig(
        asset_id="bess",
        rated_mw=10.0,
        usable_mwh=100.0,
        initial_soc_fraction=0.5,
        bess_response_tau_s=0.0,
    ))
    state = _state(demand_mw=5.0, bess=bess)
    state.fuel_cell_module = FuelCellModule(
        FuelCellConfig(
            asset_id="fc",
            rated_mw=10.0,
            min_stable_frac=0.1,
            ramp_rate_mw_per_s=1.0,
            ramp_down_rate_mw_per_s=0.01,
            load_following=True,
        ),
        state=FuelCellState.RUNNING,
        _current_output_mw=5.0,
    )
    state.fuel_cell_rated_mw = 10.0

    tick = _tick(state)

    assert tick.fuel_cell_achieved_output_mw == pytest.approx(tick.p_demand_mw)
    assert tick.bess_setpoint_mw == pytest.approx(0.0)
    assert tick.bess_output_mw == pytest.approx(0.0)
    # Command and achievement are independently retained for telemetry.
    assert tick.fuel_cell_commanded_output_mw == pytest.approx(5.0)
    assert tick.fuel_cell_achieved_output_mw == pytest.approx(5.0)


def test_fixed_fc_surplus_is_absorbed_by_bess() -> None:
    """Signed physical FC surplus retains the existing BESS charging path."""
    bess = BessModule(BessConfig(
        asset_id="bess",
        rated_mw=10.0,
        usable_mwh=100.0,
        initial_soc_fraction=0.5,
        bess_response_tau_s=0.0,
    ))
    state = _state(demand_mw=5.0, bess=bess)
    state.fuel_cell_module = FuelCellModule(
        FuelCellConfig(
            asset_id="fixed-fc",
            rated_mw=10.0,
            min_stable_frac=0.1,
            ramp_rate_mw_per_s=1.0,
            load_following=False,
            baseload_target_mw=10.0,
        ),
        state=FuelCellState.RUNNING,
        _current_output_mw=10.0,
    )
    state.fuel_cell_rated_mw = 10.0

    tick = _tick(state)

    assert tick.fuel_cell_achieved_output_mw == pytest.approx(10.0)
    assert tick.bess_setpoint_mw == pytest.approx(-5.0)
    assert tick.bess_output_mw == pytest.approx(-5.0)
    assert tick.p_unserved_mw == pytest.approx(0.0)
    assert tick.physical_balance is not None
    assert tick.physical_balance.passed is True


def test_grid_forming_anchor_ceiling_leaves_excess_load_unserved() -> None:
    """A 60 MW grid-forming BESS with 1 MW anchor delivers at most 59 MW."""
    bess = BessModule(BessConfig(
        asset_id="anchor-bess",
        rated_mw=60.0,
        usable_mwh=100.0,
        initial_soc_fraction=1.0,
        p_anchor_reserve_mw=1.0,
        grid_forming=True,
        bess_response_tau_s=0.0,
    ))
    state = _state(demand_mw=60.0, bess=bess)

    tick = _tick(state)

    assert tick.bess_output_mw == pytest.approx(59.0)
    assert tick.p_unserved_mw == pytest.approx(1.0)
    assert tick.p_served_mw == pytest.approx(59.0)