"""Addendum H Phase 1: scheduler-informed turbine fuel accounting."""

from __future__ import annotations

import pytest

from api.schemas import ScenarioSpec, TurbineFuelSpec, TurbineUnitSpec
from core.asset_modules import TurbineModule
from core.models import (
    AERODERIVATIVE_FUEL_PARAMETERS,
    ConfidenceBand,
    ThermalState,
    TurbineConfig,
    TurbineFuelParameters,
    TurbineState,
    TickResult,
)
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec


def _fuel(**overrides: float) -> TurbineFuelParameters:
    values = dict(
        part_load_heat_rate_btu_per_kwh=((0.25, 10000.0), (1.0, 10000.0)),
        synchronized_no_load_fuel_mmbtu_per_h=1.0,
        hot_standby_fuel_mmbtu_per_h=0.5,
        start_fuel_mmbtu_hot=2.0,
        start_fuel_mmbtu_warm=3.0,
        start_fuel_mmbtu_cold=4.0,
        low_load_threshold_pct=50.0,
    )
    values.update(overrides)
    return TurbineFuelParameters(**values)


def test_frame_without_fuel_parameters_is_not_modelled() -> None:
    turbine = TurbineModule(
        TurbineConfig(
            asset_id="frame-0",
            min_down_enabled=False,
            fuel=None,
        )
    )
    turbine.state = TurbineState.SYNCHRONISED
    turbine._current_output_mw = 5.0
    turbine.record_fuel_interval(3600.0, TurbineState.SYNCHRONISED)

    telemetry = turbine.fuel_telemetry()
    assert telemetry["fuel_status"] == "not_modelled"
    assert telemetry["total_fuel_mmbtu"] is None
    assert telemetry["load_fuel_mmbtu"] is None
    assert telemetry["start_count"] == 0


def test_aeroderivative_defaults_have_explicit_provenance() -> None:
    expected_fields = {
        "part_load_heat_rate_btu_per_kwh",
        "synchronized_no_load_fuel_mmbtu_per_h",
        "hot_standby_fuel_mmbtu_per_h",
        "start_fuel_mmbtu_hot",
        "start_fuel_mmbtu_warm",
        "start_fuel_mmbtu_cold",
        "low_load_threshold_pct",
    }
    assert set(AERODERIVATIVE_FUEL_PARAMETERS.provenance) == expected_fields
    assert all(
        value == "Authored — PROPOSED_HERE"
        for value in AERODERIVATIVE_FUEL_PARAMETERS.provenance.values()
    )
    assert AERODERIVATIVE_FUEL_PARAMETERS.low_load_threshold_pct == 50.0


def test_part_load_heat_rate_is_linearly_interpolated() -> None:
    fuel = _fuel(
        part_load_heat_rate_btu_per_kwh=((0.50, 10000.0), (1.0, 9000.0))
    )
    assert fuel.heat_rate_btu_per_kwh(0.75) == pytest.approx(9500.0)
    assert fuel.heat_rate_btu_per_kwh(0.25) == pytest.approx(10000.0)
    assert fuel.heat_rate_btu_per_kwh(1.25) == pytest.approx(9000.0)


def test_factory_applies_aeroderivative_fuel_defaults_without_scenario_edit() -> None:
    spec = ScenarioSpec(
        name="aero-fuel-default",
        description="",
        workload_events=[],
        bess_units=[],
        turbine_units=[
            TurbineUnitSpec(asset_id="aero-0", gt_mode="aero", rated_mw=10.0)
        ],
        end_sim_time=60.0,
    )
    context = build_run_context_from_spec(
        "aero-fuel-default-run",
        spec.model_dump(),
        playback_speed=0.0,
    )
    assert context.sim_state.turbines[0].config.fuel == AERODERIVATIVE_FUEL_PARAMETERS


def test_start_fuel_uses_the_selected_thermal_tier() -> None:
    turbine = TurbineModule(
        TurbineConfig(
            asset_id="warm-0",
            initial_thermal_state=ThermalState.WARM,
            fuel=_fuel(),
            min_down_enabled=False,
        )
    )
    turbine.command_start(0.0)

    telemetry = turbine.fuel_telemetry()
    assert turbine.state == TurbineState.STARTING
    assert telemetry["start_count"] == 1
    assert telemetry["start_fuel_mmbtu"] == pytest.approx(3.0)


def test_constant_load_accounts_for_load_no_load_headroom_and_low_load_time() -> None:
    turbine = TurbineModule(
        TurbineConfig(
            asset_id="loaded-0",
            rated_mw=10.0,
            fuel=_fuel(),
            min_down_enabled=False,
        )
    )
    turbine.state = TurbineState.SYNCHRONISED
    turbine._current_output_mw = 4.0
    turbine.record_fuel_interval(3600.0, TurbineState.SYNCHRONISED)

    telemetry = turbine.fuel_telemetry()
    assert telemetry["load_fuel_mmbtu"] == pytest.approx(40.0)
    assert telemetry["no_load_fuel_mmbtu"] == pytest.approx(1.0)
    assert telemetry["total_fuel_mmbtu"] == pytest.approx(41.0)
    assert telemetry["synchronized_headroom_mwh"] == pytest.approx(6.0)
    assert telemetry["minutes_below_low_load_threshold"] == pytest.approx(60.0)


def test_hot_standby_fuel_is_separate_from_synchronized_fuel() -> None:
    turbine = TurbineModule(
        TurbineConfig(
            asset_id="standby-0",
            hot_standby=True,
            fuel=_fuel(),
            min_down_enabled=False,
        )
    )
    turbine.record_fuel_interval(3600.0, TurbineState.OFFLINE)

    telemetry = turbine.fuel_telemetry()
    assert telemetry["hot_standby_fuel_mmbtu"] == pytest.approx(0.5)
    assert telemetry["no_load_fuel_mmbtu"] == pytest.approx(0.0)
    assert telemetry["total_fuel_mmbtu"] == pytest.approx(0.5)


def test_startup_interval_does_not_receive_a_full_synchronized_fuel_credit() -> None:
    turbine = TurbineModule(
        TurbineConfig(
            asset_id="starting-0",
            fuel=_fuel(),
            cold_start_s=1.0,
            min_down_enabled=False,
        )
    )
    turbine.command_start(0.0)
    turbine.advance(1.0, 1.0)
    assert turbine.state == TurbineState.SYNCHRONISED

    start_fuel = turbine.fuel_telemetry()["total_fuel_mmbtu"]
    turbine.record_fuel_interval(60.0, TurbineState.STARTING)
    assert turbine.fuel_telemetry()["total_fuel_mmbtu"] == pytest.approx(start_fuel)

    turbine._current_output_mw = 5.0
    turbine.record_fuel_interval(60.0, TurbineState.SYNCHRONISED)
    assert turbine.fuel_telemetry()["total_fuel_mmbtu"] > start_fuel


def test_fuel_fields_are_present_in_the_wire_payload() -> None:
    turbine = TurbineModule(
        TurbineConfig(asset_id="payload-0", fuel=_fuel(), min_down_enabled=False)
    )
    turbine.state = TurbineState.SYNCHRONISED
    turbine._current_output_mw = 4.0
    turbine.record_fuel_interval(60.0, TurbineState.SYNCHRONISED)
    row = turbine.fuel_telemetry()
    tick = TickResult(
        run_id="fuel-payload",
        tick_index=1,
        sim_time_seconds=60.0,
        p_compute_demand_mw=0.0,
        p_cooling_demand_mw=0.0,
        p_demand_mw=0.0,
        net_demand_mw=0.0,
        turbine_output_mw=4.0,
        bess_output_mw=0.0,
        bess_soc_fraction=1.0,
        confidence=ConfidenceBand(0.0, 0.0),
        turbine_fuel_telemetry=(row,),
        turbine_fuel_modelled=True,
        turbine_fuel_status="modelled",
        turbine_fuel_type="natural_gas",
        turbine_fuel_units="MMBtu",
        turbine_total_fuel_mmbtu=row["total_fuel_mmbtu"],
        turbine_start_count=row["start_count"],
        turbine_synchronized_headroom_mwh=row["synchronized_headroom_mwh"],
        turbine_minutes_below_low_load_threshold=row[
            "minutes_below_low_load_threshold"
        ],
        turbine_fuel_parameter_provenance={"payload-0": row["fuel_parameter_provenance"]},
    )

    payload = _tick_result_to_dict(tick)
    assert payload["turbine_fuel_status"] == "modelled"
    assert payload["turbine_total_fuel_mmbtu"] == pytest.approx(
        row["total_fuel_mmbtu"]
    )
    assert payload["turbine_fuel_telemetry"][0]["asset_id"] == "payload-0"
    assert payload["turbine_fuel_telemetry"][0]["fuel_units"] == "MMBtu"


def test_schema_accepts_optional_fuel_parameters_and_provenance() -> None:
    fuel = TurbineFuelSpec(
        part_load_heat_rate_btu_per_kwh=[(0.25, 10000.0), (1.0, 9000.0)],
        provenance={"part_load_heat_rate_btu_per_kwh": "Derived: test curve"},
    )
    unit = TurbineUnitSpec(asset_id="configured-0", fuel=fuel)
    assert unit.fuel is not None
    assert unit.fuel.provenance["part_load_heat_rate_btu_per_kwh"] == "Derived: test curve"
    assert unit.fuel.provenance["low_load_threshold_pct"] == "Authored — PROPOSED_HERE"