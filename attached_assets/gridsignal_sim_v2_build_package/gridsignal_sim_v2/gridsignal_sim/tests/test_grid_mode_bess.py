"""Grid-first BESS dispatch and headroom charging regression tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec
from tests.test_forecast_path import _run_tick, _starting_signal


def _grid_bess_tick(
    *,
    grid_import_limit_mw: float | None,
    soc_fraction: float = 0.95,
    island_mode: bool = False,
    grid_import_price_per_mwh: float = 0.0,
):
    spec = {
        "name": "dr-gmb-grid-mode-bess-test",
        "description": "Minimal grid/BESS dispatch regression case.",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 0.0,
        "workload_events": [],
        "bess_units": [{
            "asset_id": "bess-0",
            "rated_mw": 18.0,
            "usable_mwh": 14.0,
            "initial_soc_fraction": 0.95,
            "grid_forming": True,
            "p_anchor_reserve_mw": 1.0,
        }],
        "bess_normal_dispatch_depth_fraction": 0.25,
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "island_mode": island_mode,
        "grid_import_limit_mw": grid_import_limit_mw,
        "grid_import_price_per_mwh": grid_import_price_per_mwh,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "pue_base": 1.03,
        "end_sim_time": 60.0,
    }
    ctx = build_run_context_from_spec("dr-gmb-grid-mode-bess-test", spec)
    ctx.sim_state.bess_units[0].soc_mwh = (
        ctx.sim_state.bess_units[0].config.usable_mwh * soc_fraction
    )
    ctx.sim_state.apply_workload_signal(
        _starting_signal(nodes=2_000, ramp_s=1.0, timestamp=0.0),
        dt_lead_seconds=0.0,
    )
    return ctx, _run_tick(ctx.sim_state, sim_time=5.0, dt=5.0)


def test_grid_serves_load_before_bess_when_import_is_under_cap() -> None:
    _ctx, tick = _grid_bess_tick(grid_import_limit_mw=80.0)

    assert tick.p_demand_mw > 0.0
    assert tick.bess_output_mw == pytest.approx(0.0, abs=1e-8)
    assert tick.grid_exchange_mw == pytest.approx(-tick.p_demand_mw, abs=1e-8)
    assert tick.p_unserved_mw == pytest.approx(0.0, abs=1e-8)


def test_bess_covers_only_grid_import_above_the_pcc_cap() -> None:
    _ctx, tick = _grid_bess_tick(grid_import_limit_mw=5.0)

    assert tick.p_demand_mw > 5.0
    assert tick.grid_exchange_mw == pytest.approx(-5.0, abs=1e-8)
    assert tick.bess_output_mw == pytest.approx(
        tick.p_demand_mw - 5.0,
        abs=1e-6,
    )
    assert tick.p_unserved_mw == pytest.approx(0.0, abs=1e-6)


def test_uncapped_grid_prevents_normal_bess_discharge() -> None:
    _ctx, tick = _grid_bess_tick(grid_import_limit_mw=None)

    assert tick.bess_output_mw == pytest.approx(0.0, abs=1e-8)
    assert tick.grid_exchange_mw == pytest.approx(-tick.p_demand_mw, abs=1e-8)


def test_grid_headroom_recharges_bess_to_initial_soc_target_without_price_arbitrage() -> None:
    ctx, tick = _grid_bess_tick(
        grid_import_limit_mw=25.0,
        soc_fraction=0.70,
        grid_import_price_per_mwh=1_000_000.0,
    )

    assert tick.bess_output_mw < 0.0
    assert abs(tick.grid_exchange_mw) <= 25.0 + 1e-8
    assert tick.grid_exchange_mw == pytest.approx(-25.0, abs=1e-6)
    assert tick.bess_soc_fraction > 0.70
    assert tick.bess_soc_fraction < 0.95
    assert tick.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-8)


def test_grid_recharge_stops_at_configured_initial_soc_target() -> None:
    _ctx, tick = _grid_bess_tick(
        grid_import_limit_mw=25.0,
        soc_fraction=0.9499,
    )

    assert tick.bess_output_mw < 0.0
    assert tick.bess_soc_fraction == pytest.approx(0.95, abs=1e-7)


def test_grid_mode_change_does_not_apply_to_islanded_bess_dispatch() -> None:
    _ctx, tick = _grid_bess_tick(
        grid_import_limit_mw=80.0,
        island_mode=True,
    )

    assert tick.grid_exchange_mw == pytest.approx(0.0, abs=1e-8)
    assert tick.bess_output_mw > 0.0


def test_grid_tick_payload_exposes_positive_import_and_export_meters() -> None:
    _ctx, importing_tick = _grid_bess_tick(grid_import_limit_mw=80.0)
    import_payload = _tick_result_to_dict(importing_tick)

    assert import_payload["grid_import_mw"] == pytest.approx(
        -importing_tick.grid_exchange_mw,
        abs=1e-5,
    )
    assert import_payload["grid_export_mw"] == pytest.approx(0.0, abs=1e-8)

    exporting_tick = replace(importing_tick, grid_exchange_mw=0.75)
    export_payload = _tick_result_to_dict(exporting_tick)
    assert export_payload["grid_import_mw"] == pytest.approx(0.0, abs=1e-8)
    assert export_payload["grid_export_mw"] == pytest.approx(0.75, abs=1e-8)
