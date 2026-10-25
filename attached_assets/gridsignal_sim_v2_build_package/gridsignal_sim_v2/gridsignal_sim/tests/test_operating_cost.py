"""Opt-in itemized operating-cost reporting tests for DR D6-F."""

from __future__ import annotations

import asyncio
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.routes.runs import _legacy_grid_import_mw, get_energy_summary
from api.schemas import OperatingCostInputs, ScenarioSpec
from core.asset_modules import TurbineModule
from core.models import TurbineConfig, TurbineFuelParameters, TurbineState
from mcp_server.server import RunState, StudyService
from runtime.operating_cost import (
    NATURAL_GAS_LHV_TO_HHV_MMBTU,
    compute_operating_cost,
)
from runtime.run_manager import (
    CompletedRun,
    _completed_diesel_fuel_gallons,
    _rest_turbine_unit_payload,
)
from runtime.verdict import VerdictResult


def _inputs(**overrides):
    values = {
        "gas_price_usd_per_mmbtu": 5.0,
        "gas_price_basis": "HHV",
        "gas_price_usd_per_mmbtu_provenance": "CITED: test fixture",
        "gas_price_basis_provenance": "CITED: test fixture",
        "diesel_price_usd_per_gal": 6.0,
        "diesel_price_usd_per_gal_provenance": "CITED: test fixture",
        "turbine_variable_om_usd_per_mwh": 5.7,
        "turbine_variable_om_usd_per_mwh_provenance": "CITED: test fixture",
        "turbine_fixed_om_usd_per_kw_yr": 9.56,
        "turbine_fixed_om_usd_per_kw_yr_provenance": "CITED: test fixture",
        "turbine_start_cost_usd_per_start": 100.0,
        "turbine_start_cost_usd_per_start_provenance": "PROPOSED_HERE: test fixture",
        "bess_degradation_usd_per_mwh": 2.0,
        "bess_degradation_usd_per_mwh_provenance": "PROPOSED_HERE: test fixture",
        "unserved_energy_value_usd_per_mwh": 200.0,
        "unserved_energy_value_usd_per_mwh_provenance": "PROPOSED_HERE: test fixture",
        "currency_year": "2026",
        "currency_year_provenance": "PROPOSED_HERE: test fixture",
    }
    values.update(overrides)
    return values


def _ticks():
    return [{
        "turbine_output_mw": 10.0,
        "bess_output_mw": -2.0,
        "p_served_mw": 8.0,
        "p_unserved_mw": 0.5,
        "p_compute_mw": 5.0,
        "p_non_gpu_demand_mw": 1.0,
    }]


def _compute(inputs=None, **kwargs):
    return compute_operating_cost(
        inputs,
        _ticks(),
        interval_seconds=3600.0,
        turbine_fuel_by_unit_mmbtu={"gt-1": 20.0},
        fuel_basis_by_unit={"gt-1": "LHV"},
        fuel_quantity_complete=True,
        diesel_fuel_gallons=100.0,
        turbine_rated_mw=15.0,
        turbine_start_count=2,
        **kwargs,
    )


def test_tc_isl_52_costs_convert_units_and_interpolate_fuel_curve():
    """TC-ISL-52 — LHV/HHV conversion and configured heat-rate interpolation."""
    assert NATURAL_GAS_LHV_TO_HHV_MMBTU == 1.108
    params = TurbineFuelParameters(
        part_load_heat_rate_btu_per_kwh=(
            (0.25, 13149.0),
            (0.50, 11715.0),
            (0.75, 10758.0),
            (1.00, 10161.0),
        ),
        synchronized_no_load_fuel_mmbtu_per_h=1.2,
        hot_standby_fuel_mmbtu_per_h=0.25,
        start_fuel_mmbtu_hot=8.0,
        start_fuel_mmbtu_warm=12.0,
        start_fuel_mmbtu_cold=20.0,
    )
    assert params.heat_rate_btu_per_kwh(0.375) == pytest.approx(12432.0)
    assert params.heat_rate_btu_per_kwh(0.875) == pytest.approx(10459.5)


def test_tc_isl_53_lhv_fuel_is_priced_on_hhv_basis():
    """TC-ISL-53 — the conversion factor is explicit in the gas line."""
    result = _compute(_inputs())
    gas = next(line for line in result["lines"] if line["key"] == "turbine_gas_fuel")
    assert gas["quantity"] == pytest.approx(20.0 * 1.108)
    assert gas["unit_price"] == 5.0
    assert gas["amount_usd"] == pytest.approx(20.0 * 1.108 * 5.0)
    assert gas["conversion_factor"] == 1.108
    assert "LHV to HHV" in gas["conversion_note"]


def test_tc_isl_54_each_operating_cost_line_uses_its_quantity_and_price():
    """TC-ISL-54 — all seven requested itemized lines are calculated."""
    result = _compute(_inputs())
    lines = {line["key"]: line for line in result["lines"]}
    assert lines["turbine_gas_fuel"]["amount_usd"] == pytest.approx(110.8)
    assert lines["diesel_fuel"]["amount_usd"] == pytest.approx(600.0)
    assert lines["turbine_variable_om"]["amount_usd"] == pytest.approx(57.0)
    assert lines["turbine_fixed_om"]["quantity"] == pytest.approx(15000 / 8760)
    assert lines["turbine_fixed_om"]["amount_usd"] == pytest.approx(15000 / 8760 * 9.56)
    assert lines["turbine_nonfuel_start"]["amount_usd"] == pytest.approx(200.0)
    assert lines["bess_degradation"]["quantity"] == pytest.approx(2.0)
    assert lines["bess_degradation"]["amount_usd"] == pytest.approx(4.0)
    assert lines["unserved_energy"]["amount_usd"] == pytest.approx(100.0)


def test_tc_isl_55_null_inputs_remain_null_and_are_excluded_from_total():
    """TC-ISL-55 — missing quantity or price produces a null line amount."""
    result = _compute(_inputs(
        diesel_price_usd_per_gal=None,
        diesel_price_usd_per_gal_provenance="No cited value; intentionally null.",
        turbine_start_cost_usd_per_start=None,
        turbine_start_cost_usd_per_start_provenance="No cited value; intentionally null.",
    ))
    lines = {line["key"]: line for line in result["lines"]}
    assert lines["diesel_fuel"]["amount_usd"] is None
    assert lines["turbine_nonfuel_start"]["amount_usd"] is None
    assert "diesel_fuel" not in result["total_includes"]
    assert any(row["key"] == "diesel_fuel" for row in result["total_excludes"])


def test_tc_isl_56_total_is_separate_from_legacy_cost_breakdown():
    """TC-ISL-56 — no legacy §21.2 cost is added to itemized operating cost."""
    result = _compute(_inputs())
    expected = sum(line["amount_usd"] for line in result["lines"] if line["amount_usd"] is not None)
    assert result["total_usd"] == pytest.approx(expected)
    assert "cost_breakdown" not in result
    assert result["total_excludes"]
    assert {row["key"] for row in result["total_excludes"]} >= {
        "grid_import", "fuel_cell_fuel", "solar_or_ppa"
    }


def test_tc_isl_57_absent_cost_block_preserves_legacy_payload():
    """TC-ISL-57 — opt-in absent means no new cost payload."""
    assert _compute(None) is None
    spec_path = "config/scenarios/demo-islanded-ramp.json"
    import json
    from pathlib import Path

    raw = json.loads(Path(spec_path).read_text())
    spec = ScenarioSpec.model_validate(raw)
    assert spec.operating_cost_inputs is None
    assert "operating_cost_inputs" not in spec.model_dump(
        mode="json", exclude_none=True
    )


def test_tc_isl_58_rest_and_mcp_expose_itemized_cost_without_mutating_legacy():
    """TC-ISL-58 — the REST and MCP energy surfaces carry the separate section."""
    expected = _compute(_inputs())
    completed = CompletedRun(
        run_id="op-cost-test",
        scenario_id="test",
        scenario_name="Operating cost fixture",
        completed_at=datetime.now(timezone.utc),
        verdict=VerdictResult("PASS", 1, 0, 0),
        tick_dicts=_ticks(),
        dropped_ticks=0,
        turbine_rated_mw=15.0,
        operating_cost_inputs=_inputs(),
        operating_cost=expected,
    )

    class Manager:
        def get_context(self, _run_id):
            return None

        def get_completed(self, _run_id):
            return completed

    rest = asyncio.run(get_energy_summary("op-cost-test", manager=Manager()))
    assert rest["operating_cost"] == expected
    assert rest["cost_breakdown"] is not None

    service = object.__new__(StudyService)
    service._lock = threading.RLock()
    service._runs = {
        "op-cost-test": RunState(
            run_id="op-cost-test",
            scenario_id="scenario-h1-k8s-ray-24h",
            mode="baseline",
            identity_digest="test",
            record={
                    "study_class": "addendum_h",
                "operating_cost": expected,
                "served_mwh": 8.0,
                "unserved_mwh": 0.5,
                "fuel_by_component_mmbtu": {},
                "turbine_fuel_mmbtu": 0.0,
            },
        )
    }
    mcp = service.metrics(
        "op-cost-test", section="energy", page=1, page_size=10
    )
    assert mcp["energy"]["operating_cost"] == expected


def test_tc_isl_59_schema_keeps_cost_inputs_opt_in_and_provenance_required():
    """TC-ISL-59 — configured numeric inputs require explicit provenance."""
    parsed = OperatingCostInputs.model_validate(_inputs())
    assert parsed.gas_price_usd_per_mmbtu == 5.0
    with pytest.raises(ValueError, match="provenance"):
        OperatingCostInputs.model_validate({
            "gas_price_usd_per_mmbtu": 5.0,
            "gas_price_basis": "HHV",
        })


def test_tc_isl_60_fuel_reporting_fields_are_excluded_and_no_fuel_is_unchanged():
    """TC-ISL-60 — amended F-1 classification; no-fuel telemetry stays zero."""
    workspace = Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(workspace / "tools/dr_isl/d6f"))
    from run_operating_cost import nonfuel_tick

    tick = {
        "turbine_synchronized_headroom_mwh": 1.25,
        "turbine_minutes_below_low_load_threshold": 3.0,
        "turbine_fuel_telemetry": [{
            "synchronized_headroom_mwh": 1.25,
            "minutes_below_low_load_threshold": 3.0,
            "low_load_threshold_pct": 50.0,
        }],
        "turbine_units": [{
            "rated_mw": 10.0,
            "fuel_low_load_threshold_pct": 50.0,
        }],
        "turbine_output_mw": 4.0,
    }
    filtered = nonfuel_tick(tick)
    assert "turbine_synchronized_headroom_mwh" not in filtered
    assert "turbine_minutes_below_low_load_threshold" not in filtered
    assert "turbine_fuel_telemetry" not in filtered
    assert filtered["turbine_units"] == [{"rated_mw": 10.0}]
    assert filtered["turbine_output_mw"] == 4.0

    no_fuel = TurbineModule(
        TurbineConfig(asset_id="no-fuel-headroom-test", rated_mw=10.0)
    )
    no_fuel.state = TurbineState.SYNCHRONISED
    no_fuel._current_output_mw = 4.0
    no_fuel.record_fuel_interval(3600.0, TurbineState.SYNCHRONISED)
    telemetry = no_fuel.fuel_telemetry()
    assert telemetry["fuel_modelled"] is False
    assert telemetry["synchronized_headroom_mwh"] == 0.0
    assert telemetry["minutes_below_low_load_threshold"] == 0.0


def test_tc_isl_61_scenario_planner_exposes_itemized_cost_table():
    """TC-ISL-61 — the existing planner visibly renders the opt-in table."""
    workspace = Path(__file__).resolve().parents[5]
    component = (
        workspace
        / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/"
        "frontend/src/components/ScenarioPlannerPage.tsx"
    )
    source = component.read_text()
    assert "operating_cost" in source
    # D6c replaces the old generic label and folds the legacy estimate when
    # cited operating-cost data exists.
    assert "Operating cost (cited prices)" in source
    assert "Indicative estimate (placeholder rates)" in source
    assert "<details" in source
    assert "open={!runs[Math.min(selectedRunIdx, runs.length - 1)]?.operating_cost}" in source
    assert "Excluded from total:" in source


def test_tc_isl_62_diesel_quantity_is_null_without_fleet_and_zero_for_idle_fleet():
    """TC-ISL-62 — D6c keeps absence distinct from a configured idle fleet."""
    def context(units):
        return SimpleNamespace(
            sim_state=SimpleNamespace(
                diesel_units=units,
                diesel_fleet_coordinator=SimpleNamespace(fuel_remaining_gal=100.0),
            ),
            diesel_fuel_initial_gal=100.0,
        )

    no_fleet_gallons = _completed_diesel_fuel_gallons(context([]))
    idle_fleet_gallons = _completed_diesel_fuel_gallons(context([object()]))
    assert no_fleet_gallons is None
    assert idle_fleet_gallons == 0.0

    def diesel_line(gallons):
        result = compute_operating_cost(
            _inputs(),
            _ticks(),
            interval_seconds=3600.0,
            turbine_fuel_by_unit_mmbtu={"gt-1": 20.0},
            fuel_basis_by_unit={"gt-1": "LHV"},
            fuel_quantity_complete=True,
            diesel_fuel_gallons=gallons,
            turbine_rated_mw=15.0,
            turbine_start_count=2,
        )
        return result, next(line for line in result["lines"] if line["key"] == "diesel_fuel")

    no_fleet_result, no_fleet_line = diesel_line(no_fleet_gallons)
    assert no_fleet_line["quantity"] is None
    assert no_fleet_line["amount_usd"] is None
    assert "diesel_fuel" not in no_fleet_result["total_includes"]
    assert any(row["key"] == "diesel_fuel" for row in no_fleet_result["total_excludes"])

    idle_result, idle_line = diesel_line(idle_fleet_gallons)
    assert idle_line["quantity"] == 0.0
    assert idle_line["amount_usd"] == 0.0
    assert "diesel_fuel" in idle_result["total_includes"]


def test_tc_isl_63_rest_breaker_uses_physical_tick_for_offline_starting_and_synced():
    """TC-ISL-63 — D6c reports the core tick breaker state, not the static default."""
    states = (
        (TurbineState.OFFLINE, False),
        (TurbineState.STARTING, False),
        (TurbineState.SYNCHRONISED, True),
    )
    for index, (state, physical_breaker) in enumerate(states):
        module = TurbineModule(
            TurbineConfig(asset_id=f"d6c-breaker-{index}", rated_mw=10.0)
        )
        module.state = state
        payload = _rest_turbine_unit_payload(
            {"asset_id": module.config.asset_id, "breaker_closed": not physical_breaker},
            module,
            {"asset_id": module.config.asset_id, "breaker_closed": physical_breaker},
        )
        assert payload["breaker_closed"] is physical_breaker


def test_tc_isl_64_energy_summary_only_counts_import_on_grid_connected_ticks():
    """TC-ISL-64 — D6c excludes islanded shortfall but preserves the grid-tied formula."""
    base_tick = {
        "net_demand_mw": 10.0,
        "turbine_output_mw": 3.0,
        "bess_output_mw": 2.0,
        "contingency_coverage": {"grid_connected": False},
    }
    assert _legacy_grid_import_mw(base_tick) == 0.0
    grid_tick = {
        **base_tick,
        "contingency_coverage": {"grid_connected": True},
    }
    assert _legacy_grid_import_mw(grid_tick) == 5.0

    async def summary(grid_connected):
        completed = CompletedRun(
            run_id=f"d6c-grid-{grid_connected}",
            scenario_id="d6c-grid-test",
            scenario_name="D6c grid-import test",
            completed_at=datetime.now(timezone.utc),
            verdict=VerdictResult("PASS", 1, 0, 0),
            tick_dicts=[{
                **base_tick,
                "contingency_coverage": {"grid_connected": grid_connected},
            }],
            dropped_ticks=0,
        )

        class Manager:
            def get_context(self, _run_id):
                return None

            def get_completed(self, _run_id):
                return completed

        return await get_energy_summary(completed.run_id, manager=Manager())

    islanded = asyncio.run(summary(False))
    grid_tied = asyncio.run(summary(True))
    assert islanded["grid_import_mwh"] == 0.0
    assert grid_tied["grid_import_mwh"] == pytest.approx(0.0069)
