from __future__ import annotations

import pytest

from core.fuel_cell_module import (
    FuelCellConfig,
    FuelCellModule,
    FuelCellState,
)


def make_module(**overrides: object) -> FuelCellModule:
    config_values: dict[str, object] = {
        "asset_id": "fc-array-1",
        "rated_mw": 10.0,
        "ramp_rate_mw_per_s": 0.02,
        "min_stable_frac": 0.4,
        "cold_start_s": 7_200.0,
        "controlled_cooling_s": 1_800.0,
        "min_setpoint_interval_s": 900.0,
    }
    config_values.update(overrides)
    return FuelCellModule(FuelCellConfig(**config_values))


def test_state_enum_has_the_five_sofc_states() -> None:
    assert [state.value for state in FuelCellState] == [
        "cold",
        "warming",
        "hot_standby",
        "running",
        "controlled_cooling",
    ]


def test_cold_start_is_non_interruptible_and_ends_in_hot_standby() -> None:
    module = make_module(cold_start_s=7_200.0)

    assert module.state is FuelCellState.COLD
    assert module.command_start(0.0)
    assert module.state is FuelCellState.WARMING
    assert module.output_mw() == 0.0
    assert not module.command_stop(1.0)

    module.advance(3_600.0, 3_600.0)
    assert module.state is FuelCellState.WARMING
    assert module.time_remaining_s == 3_600.0
    assert module.output_mw() == 0.0

    module.advance(7_200.0, 3_600.0)
    assert module.state is FuelCellState.HOT_STANDBY
    assert module.time_to_ready_s == 0.0
    assert module.output_mw() == 0.0


def test_running_output_is_rate_limited_by_fuel_cell_specific_rate() -> None:
    module = make_module(
        cold_start_s=1.0,
        ramp_rate_mw_per_s=0.02,
        min_stable_frac=0.4,
    )
    assert module.command_start(0.0)
    module.advance(1.0, 1.0)
    assert module.command_run(1.0)
    assert module.state is FuelCellState.RUNNING
    assert module.output_mw() == 4.0

    module.advance(2.0, 10.0)
    assert module.output_mw() == pytest.approx(4.2)
    assert module.output_mw() <= 4.0 + (0.02 * 10.0)


def test_below_minimum_stable_setpoint_starts_controlled_cooling() -> None:
    module = make_module(cold_start_s=1.0)
    assert module.command_start(0.0)
    module.advance(1.0, 1.0)
    assert module.command_run(1.0)

    assert module.command_stop(2.0)
    assert module.state is FuelCellState.CONTROLLED_COOLING
    assert module.output_mw() == 0.0
    assert not module.command_start(3.0)

    module.advance(3.0, 1_800.0)
    assert module.state is FuelCellState.COLD


def test_hot_array_cannot_transition_directly_to_cold() -> None:
    module = make_module(cold_start_s=1.0, controlled_cooling_s=10.0)
    assert module.command_start(0.0)
    module.advance(1.0, 1.0)
    assert module.state is FuelCellState.HOT_STANDBY
    assert not module.command_start(2.0)
    assert module.state is FuelCellState.HOT_STANDBY

    assert module.command_stop(2.0)
    assert module.state is FuelCellState.CONTROLLED_COOLING
    module.advance(3.0, 10.0)
    assert module.state is FuelCellState.COLD


def test_setpoint_change_interval_is_enforced() -> None:
    module = make_module(
        cold_start_s=1.0,
        min_setpoint_interval_s=900.0,
        baseload_target_mw=7.0,
    )
    assert module.command_start(0.0)
    module.advance(1.0, 1.0)
    assert module.command_run(1.0)

    # Phase 2 fixes the baseload target in configuration.  The old runtime
    # setpoint request path is intentionally gone.
    assert module.target_output_mw == 7.0
    module.advance(10.0, 10.0)
    assert module.target_output_mw == 7.0
    assert module.output_mw() == pytest.approx(4.2)


def test_baseload_target_defaults_to_full_nameplate() -> None:
    module = make_module()

    assert module.config.baseload_target_mw == 10.0
    assert module.target_output_mw == 10.0


def test_monitoring_only_flag_is_stored_without_wiring_the_control_plane() -> None:
    module = make_module(monitoring_only=True)

    assert module.config.monitoring_only is True
    assert "monitoring_only" in module.config.__dataclass_fields__
    assert module.config.baseload_target_mw == module.config.rated_mw