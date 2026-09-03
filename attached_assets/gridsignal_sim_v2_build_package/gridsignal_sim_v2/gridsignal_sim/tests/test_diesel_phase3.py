"""Phase 3 live diesel dispatch and balance integration tests."""

from __future__ import annotations

import pytest

from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import DieselState
from core.sim_clock import SimClock
from core.simulation_core import evaluate_tick
from runtime.scenario_factory import build_run_context_from_spec
from tests.test_forecast_path import _starting_signal


_DIESEL_UNIT = {
    "asset_id": "diesel-1",
    "rated_mw": 3.0,
    "role": "primary",
    "start_offset_s": None,
    "delta_t_start_s": 1.0,
    "f_block": 0.80,
    "residual_ramp_s": 1.0,
    "min_stable_load_mw": 0.0,
    "min_run_s": 0.0,
    "min_down_s": 0.0,
    "cooldown_s": 0.0,
}


def _spec(*, diesel_enabled: bool, islanded: bool = True) -> dict:
    return {
        "name": "diesel-phase3-test",
        "description": "",
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.95,
        "pue_base": 1.03,
        "island_mode": islanded,
        "calibrated": True,
        "turbine_units": [
            {
                "asset_id": "gt-1",
                "rated_mw": 3.0,
                "p_min_stable_frac": 0.0,
                "droop_r": 0.05,
                "power_factor": 0.95,
                "hot_start_s": 300,
                "warm_start_s": 600,
                "cold_start_s": 900,
            }
        ],
        "bess_units": [
            {
                "asset_id": "bess-1",
                "rated_mw": 1.0,
                "usable_mwh": 2.0,
                "initial_soc_fraction": 0.9,
                "p_anchor_reserve_mw": 0.0,
                "grid_forming": False,
            }
        ],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "workload_events": [],
        "end_sim_time": 300.0,
        "diesel_power_block": {
            "enabled": diesel_enabled,
            "target_capacity_mw": 3.0,
            "unit_rating_mw": 3.0,
            "debounce_s": 0.0,
            "restore_hold_s": 300.0,
            "min_run_s": 0.0,
            "min_down_s": 0.0,
            "cooldown_s": 0.0,
            "fuel_burn_gal_per_hr_per_unit_at_full_load": 230.0,
            "min_fuel_runtime_hours": 48.0,
        },
        "diesel_units": [_DIESEL_UNIT] if diesel_enabled else [],
    }


def _context(*, diesel_enabled: bool, islanded: bool = True):
    ctx = build_run_context_from_spec(
        run_id=f"diesel-phase3-{diesel_enabled}-{islanded}",
        spec_data=_spec(diesel_enabled=diesel_enabled, islanded=islanded),
    )
    if diesel_enabled:
        diesel = ctx.sim_state.diesel_units[0]
        diesel.state = DieselState.SYNCHRONISED
        diesel._current_output_mw = 3.0
    ctx.sim_state.apply_workload_signal(
        _starting_signal(nodes=3000, ramp_s=1.0, timestamp=0.0),
        dt_lead_seconds=0.0,
    )
    return ctx


def _tick(state, tick_index: int):
    sim_time = float(tick_index) * 5.0
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        return evaluate_tick(
            state,
            SimClock(
                sim_time=sim_time,
                dt_seconds=5.0,
                wall_stamp_utc=sim_time,
                rate=1.0,
                tick_seq=tick_index,
            ),
        )
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def test_live_diesel_output_reduces_remaining_gap_before_curtailment() -> None:
    disabled = _context(diesel_enabled=False)
    enabled = _context(diesel_enabled=True)
    captured: dict[str, float] = {}

    original = enabled.sim_state.curtailment_ladder.generate_candidates

    def capture_gap(*, gap_mw, is_low_confidence, operating_tier, sim_time):
        captured["gap_mw"] = gap_mw
        return original(
            gap_mw=gap_mw,
            is_low_confidence=is_low_confidence,
            operating_tier=operating_tier,
            sim_time=sim_time,
        )

    enabled.sim_state.curtailment_ladder.generate_candidates = capture_gap

    disabled_tick = _tick(disabled.sim_state, tick_index=5)
    enabled_tick = _tick(enabled.sim_state, tick_index=5)

    expected_diesel_mw = enabled.sim_state.diesel_fleet_coordinator.output_mw
    assert disabled.sim_state.diesel_fleet_coordinator.output_mw == 0.0
    assert expected_diesel_mw == pytest.approx(3.0)
    assert captured["gap_mw"] < disabled_tick.p_demand_mw
    assert captured["gap_mw"] == pytest.approx(
        max(
            0.0,
            enabled_tick.p_demand_mw
            - enabled_tick.turbine_output_mw
            - enabled_tick.bess_output_mw
            - expected_diesel_mw,
        )
        - enabled_tick.p_renewable_mw,
        abs=1e-6,
    )


def test_live_diesel_output_increases_generation_and_balance_residual() -> None:
    disabled = _context(diesel_enabled=False)
    enabled = _context(diesel_enabled=True)

    disabled_tick = _tick(disabled.sim_state, tick_index=0)
    enabled_tick = _tick(enabled.sim_state, tick_index=0)
    diesel_output_mw = enabled.sim_state.diesel_fleet_coordinator.output_mw

    assert diesel_output_mw == pytest.approx(3.0)
    assert enabled_tick.p_generation_mw - disabled_tick.p_generation_mw == pytest.approx(
        diesel_output_mw
    )
    assert enabled_tick.p_imbalance_mw - disabled_tick.p_imbalance_mw == pytest.approx(
        diesel_output_mw
    )


def test_live_diesel_is_less_aggressive_than_disabled_before_curtailment() -> None:
    disabled = _context(diesel_enabled=False, islanded=False)
    enabled = _context(diesel_enabled=True, islanded=False)

    disabled_ticks = [_tick(disabled.sim_state, i) for i in range(26)]
    enabled_ticks = [_tick(enabled.sim_state, i) for i in range(26)]

    disabled_tiers = disabled_ticks[-1].curtailment_proposal_tiers
    enabled_tiers = enabled_ticks[-1].curtailment_proposal_tiers

    assert disabled_tiers
    assert not enabled_tiers
