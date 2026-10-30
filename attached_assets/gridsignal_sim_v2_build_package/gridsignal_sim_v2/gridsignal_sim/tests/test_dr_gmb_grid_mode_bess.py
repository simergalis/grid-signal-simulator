"""Regression gates for grid-mode BESS rules D1/D2 (DR-2026-10-27-GRID-MODE-BESS)."""

from __future__ import annotations

import pytest

from runtime.scenario_factory import build_run_context_from_spec
from tests.test_forecast_path import _run_tick, _starting_signal


def _make_grid_bess_context(
    *,
    grid_import_limit_mw: float | None,
    soc_fraction: float = 0.95,
    island_mode: bool = False,
):
    spec = {
        "name": "dr-gmb-grid-mode-bess-test",
        "description": "Minimal grid/BESS dispatch regression case.",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 0.0,
        "workload_events": [],
        "bess_units": [
            {
                "asset_id": "bess-0",
                "rated_mw": 18.0,
                "usable_mwh": 14.0,
                "initial_soc_fraction": 0.95,
                "grid_forming": True,
                "p_anchor_reserve_mw": 1.0,
            }
        ],
        "bess_normal_dispatch_depth_fraction": 0.25,
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "island_mode": island_mode,
        "grid_import_limit_mw": grid_import_limit_mw,
        "grid_import_price_per_mwh": 0.0,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "pue_base": 1.03,
        "end_sim_time": 60.0,
    }
    ctx = build_run_context_from_spec("dr-gmb-grid-mode-bess-test", spec)
    bess = ctx.sim_state.bess_units[0]
    bess.soc_mwh = bess.config.usable_mwh * soc_fraction
    ctx.sim_state.apply_workload_signal(
        _starting_signal(nodes=2_000, ramp_s=1.0, timestamp=0.0),
        dt_lead_seconds=0.0,
    )
    return ctx


def test_tc_gmb_01_islanded_dispatch_is_unchanged_by_grid_cap() -> None:
    """TC-GMB-01: D1/D2 grid-mode branch leaves islanded dispatch unchanged."""
    uncapped_ctx = _make_grid_bess_context(
        grid_import_limit_mw=None,
        island_mode=True,
    )
    capped_ctx = _make_grid_bess_context(
        grid_import_limit_mw=80.0,
        island_mode=True,
    )

    uncapped = _run_tick(uncapped_ctx.sim_state, sim_time=5.0, dt=5.0)
    capped = _run_tick(capped_ctx.sim_state, sim_time=5.0, dt=5.0)

    assert uncapped.grid_exchange_mw == pytest.approx(0.0, abs=1e-10)
    assert capped.grid_exchange_mw == pytest.approx(0.0, abs=1e-10)
    for field in (
        "p_demand_mw",
        "p_unserved_mw",
        "bess_output_mw",
        "bess_soc_fraction",
        "d4_balance_defect_mw",
    ):
        assert getattr(capped, field) == pytest.approx(
            getattr(uncapped, field),
            abs=1e-10,
        )


def test_tc_gmb_02_capped_and_uncapped_grid_discharge_rule() -> None:
    """TC-GMB-02: D1 discharges only for demand beyond a configured PCC cap."""
    capped_ctx = _make_grid_bess_context(grid_import_limit_mw=5.0)
    capped = _run_tick(capped_ctx.sim_state, sim_time=5.0, dt=5.0)

    assert capped.p_demand_mw > 5.0
    assert -capped.grid_exchange_mw == pytest.approx(5.0, abs=1e-6)
    assert capped.bess_output_mw == pytest.approx(
        capped.p_demand_mw - 5.0,
        abs=1e-6,
    )
    assert capped.p_unserved_mw == pytest.approx(0.0, abs=1e-6)

    uncapped_ctx = _make_grid_bess_context(grid_import_limit_mw=None)
    uncapped = _run_tick(uncapped_ctx.sim_state, sim_time=5.0, dt=5.0)

    assert uncapped.bess_output_mw == pytest.approx(0.0, abs=1e-8)
    assert -uncapped.grid_exchange_mw == pytest.approx(
        uncapped.p_demand_mw,
        abs=1e-6,
    )


def test_tc_gmb_03_grid_recharge_respects_cap_target_and_balance() -> None:
    """TC-GMB-03: D2 recharges only below target and within PCC import headroom."""
    charge_ctx = _make_grid_bess_context(
        grid_import_limit_mw=25.0,
        soc_fraction=0.70,
    )
    charge_ticks = [
        _run_tick(charge_ctx.sim_state, sim_time=5.0 * index, dt=5.0)
        for index in range(1, 4)
    ]

    assert all(tick.bess_output_mw < 0.0 for tick in charge_ticks)
    assert charge_ticks[-1].bess_soc_fraction > charge_ticks[0].bess_soc_fraction
    for tick in charge_ticks:
        grid_import_mw = max(0.0, -tick.grid_exchange_mw)
        assert grid_import_mw <= 25.0 + 1e-8
        assert grid_import_mw == pytest.approx(
            tick.p_demand_mw - tick.bess_output_mw,
            abs=1e-6,
        )
        assert tick.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-8)

    at_target_ctx = _make_grid_bess_context(
        grid_import_limit_mw=25.0,
        soc_fraction=0.95,
    )
    at_target = _run_tick(at_target_ctx.sim_state, sim_time=5.0, dt=5.0)
    assert at_target.bess_output_mw == pytest.approx(0.0, abs=1e-8)
    assert -at_target.grid_exchange_mw <= 25.0 + 1e-8
    assert at_target.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-8)

    no_headroom_ctx = _make_grid_bess_context(
        grid_import_limit_mw=5.0,
        soc_fraction=0.70,
    )
    no_headroom = _run_tick(no_headroom_ctx.sim_state, sim_time=5.0, dt=5.0)
    assert no_headroom.p_demand_mw > 5.0
    assert no_headroom.bess_output_mw > 0.0
    assert -no_headroom.grid_exchange_mw <= 5.0 + 1e-8
    assert no_headroom.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-8)
