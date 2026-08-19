"""Regression coverage for the grid-limited Kubernetes scenario."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.routes.scenarios import build_seeded_store
from api.schemas import ScenarioSpec
from runtime.scenario_factory import build_run_context_from_spec
from tests.test_forecast_path import _run_tick, _starting_signal


_SCENARIO_ID = "scenario-kube-grid-limited-24mw-fc"
_SCENARIO_PATH = (
    Path(__file__).parents[1]
    / "config"
    / "scenarios"
    / f"{_SCENARIO_ID}.json"
)
_SOURCE_PATH = (
    Path(__file__).parents[1]
    / "config"
    / "scenarios"
    / "scenario-kube-peak-overage.json"
)


def _load_raw(path: Path) -> dict:
    return json.loads(path.read_text())


def _grid_only_tick(grid_import_limit_mw: float | None):
    spec = {
        "name": "grid-import-limit-physics-test",
        "description": "Grid-only balance test.",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 0.0,
        "workload_events": [],
        "bess_units": [],
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "island_mode": False,
        "grid_import_limit_mw": grid_import_limit_mw,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "pue_base": 1.03,
        "end_sim_time": 60.0,
    }
    ctx = build_run_context_from_spec("grid-cap-test", spec)
    signal = _starting_signal(nodes=2000, ramp_s=1.0, timestamp=0.0)
    ctx.sim_state.apply_workload_signal(signal, dt_lead_seconds=0.0)
    return _run_tick(ctx.sim_state, sim_time=5.0, dt=5.0)


def test_scenario_schema_and_requested_capacities() -> None:
    spec = ScenarioSpec.model_validate_json(_SCENARIO_PATH.read_text())

    assert spec.island_mode is False
    assert spec.grid_import_limit_mw == pytest.approx(10.0)
    assert len(spec.bess_units) == 1
    assert spec.bess_units[0].rated_mw == pytest.approx(30.0)
    assert spec.bess_units[0].usable_mwh == pytest.approx(60.0)
    assert spec.fuel_cell_rated_mw * spec.fuel_cell_stack_count == pytest.approx(24.0)


def test_scenario_preserves_generator_timing_and_caps_each_job_below_7mw() -> None:
    scenario = _load_raw(_SCENARIO_PATH)
    source = _load_raw(_SOURCE_PATH)
    kube = scenario["kube_config"]
    source_kube = source["kube_config"]

    timing_fields = (
        "mean_interarrival_s",
        "mean_job_duration_s",
        "min_job_duration_s",
        "reorder_window_s",
        "ntp_jitter_s",
        "rng_seed",
    )
    assert {key: kube[key] for key in timing_fields} == {
        key: source_kube[key] for key in timing_fields
    }
    assert scenario["generator_config"] == source["generator_config"]

    max_job_nodes = kube["max_nodes"] // 2
    max_job_mw_including_pue = (
        max_job_nodes * 10.2 * scenario["pue_base"] / 1000.0
    )
    assert max_job_nodes == 600
    assert max_job_mw_including_pue == pytest.approx(6.3036)
    assert max_job_mw_including_pue < 7.0


def test_seeded_store_exposes_scenario_and_factory_wires_grid_limit() -> None:
    record = build_seeded_store().get(_SCENARIO_ID)
    assert record is not None
    spec = ScenarioSpec.model_validate_json(record.spec_json)
    assert spec.grid_import_limit_mw == pytest.approx(10.0)

    ctx = build_run_context_from_spec(
        "grid-limited-seed-test",
        spec.model_dump(mode="json"),
    )
    assert ctx.sim_state.site.grid_import_limit_mw == pytest.approx(10.0)


def test_grid_import_is_physically_capped_and_d4_remains_balanced() -> None:
    tick = _grid_only_tick(10.0)

    assert tick.p_demand_mw > 10.0
    assert tick.grid_exchange_mw == pytest.approx(-10.0, abs=1e-9)
    assert tick.frequency_forcing_mw < 0.0
    # The physical D4 defect reports the generation deficit rather than treating
    # unmet demand as served.  It therefore matches the residual that could not
    # pass through the capped PCC.
    assert tick.d4_balance_defect_mw == pytest.approx(
        tick.frequency_forcing_mw,
        abs=1e-9,
    )
    assert tick.p_unserved_mw == pytest.approx(-tick.frequency_forcing_mw, abs=1e-9)
    assert tick.p_generation_mw == pytest.approx(10.0, abs=1e-9)


def test_unset_grid_import_limit_preserves_unlimited_grid_balancing() -> None:
    tick = _grid_only_tick(None)

    assert tick.p_demand_mw > 10.0
    assert -tick.grid_exchange_mw == pytest.approx(tick.p_demand_mw, abs=1e-9)
    assert tick.frequency_forcing_mw == 0.0
    assert tick.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-9)


def test_grid_import_limit_does_not_cap_export() -> None:
    spec = {
        "name": "grid-export-uncapped-physics-test",
        "description": "A synchronised turbine exports surplus through a zero-import PCC.",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 0.0,
        "workload_events": [],
        "bess_units": [],
        "turbine_units": [
            {
                "asset_id": "turbine-0",
                "rated_mw": 25.0,
                "r_asset_mw_per_s": 0.2,
                "p_min_stable_frac": 0.4,
                "hot_standby": False,
            }
        ],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "island_mode": False,
        "grid_import_limit_mw": 0.0,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "pue_base": 1.03,
        "end_sim_time": 60.0,
    }
    ctx = build_run_context_from_spec("grid-export-test", spec)
    tick = _run_tick(ctx.sim_state, sim_time=5.0, dt=5.0)

    assert tick.turbine_output_mw > 0.0
    assert tick.grid_exchange_mw == pytest.approx(
        tick.turbine_output_mw - tick.p_demand_mw,
        abs=1e-9,
    )
    assert tick.grid_exchange_mw > 0.0
    assert tick.frequency_forcing_mw == 0.0