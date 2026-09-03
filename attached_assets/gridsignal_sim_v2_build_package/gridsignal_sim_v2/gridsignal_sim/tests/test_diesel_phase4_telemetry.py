"""Phase 4 diesel aggregate telemetry and wire serialization coverage."""

from __future__ import annotations

from runtime.run_manager import _tick_result_to_dict
from tests.test_diesel_phase3 import _context, _tick


def test_disabled_diesel_telemetry_is_idle_and_zero() -> None:
    result = _tick(_context(diesel_enabled=False).sim_state, 0)
    payload = _tick_result_to_dict(result)

    assert result.diesel_enabled is False
    assert result.diesel_output_mw == 0.0
    assert result.diesel_n_synced == 0
    assert result.diesel_n_active_target == 0
    assert result.diesel_n_standby_available == 0
    assert result.diesel_n_out_of_service == 0
    assert result.diesel_fleet_state == "idle"
    assert result.diesel_activation_episode_id is None
    assert result.diesel_time_in_state_s == 0.0
    assert result.diesel_fuel_remaining_gal == 0.0
    assert result.diesel_fuel_runtime_hours_remaining is None
    assert result.diesel_insufficient_start_shortfall_mw is None

    assert payload["diesel_enabled"] is False
    assert payload["diesel_output_mw"] == 0.0
    assert payload["diesel_fleet_state"] == "idle"
    assert payload["diesel_activation_episode_id"] is None
    assert payload["diesel_fuel_runtime_hours_remaining"] is None
    assert payload["diesel_insufficient_start_shortfall_mw"] is None


def test_enabled_diesel_telemetry_comes_from_single_tick_snapshot() -> None:
    ctx = _context(diesel_enabled=True)
    result = _tick(ctx.sim_state, 0)
    snapshot = ctx.sim_state.diesel_fleet_coordinator.snapshot()
    payload = _tick_result_to_dict(result)

    assert result.diesel_enabled is True
    assert result.diesel_output_mw == snapshot.output_mw
    assert result.diesel_n_synced == snapshot.synchronised_count
    assert result.diesel_n_active_target == snapshot.n_active
    assert result.diesel_n_standby_available == snapshot.n_standby_available
    assert result.diesel_n_out_of_service == snapshot.n_out_of_service
    assert result.diesel_fleet_state == snapshot.state
    assert result.diesel_activation_episode_id == snapshot.episode_id
    assert result.diesel_fuel_remaining_gal == snapshot.fuel_remaining_gal
    assert result.diesel_fuel_runtime_hours_remaining == snapshot.fuel_runtime_hours_remaining
    assert result.diesel_insufficient_start_shortfall_mw is None

    assert payload["diesel_output_mw"] == round(snapshot.output_mw, 4)
    assert payload["diesel_fuel_remaining_gal"] == round(snapshot.fuel_remaining_gal, 4)