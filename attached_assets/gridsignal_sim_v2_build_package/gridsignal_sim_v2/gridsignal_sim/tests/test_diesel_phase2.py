"""Standalone Addendum H Phase 2 diesel module/fleet coverage."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from api.schemas import DieselPowerBlockSpec, generate_diesel_fleet
from core.asset_modules import DieselModule
from core.diesel_fleet import DieselFleetCoordinator
from core.models import DieselConfig, DieselState


def _modules(
    *,
    target_capacity_mw: float = 3.0,
    unit_rating_mw: float = 3.0,
    delta_t_start_s: float = 1.0,
    f_block: float = 0.8,
    residual_ramp_s: float = 4.0,
    min_run_s: float = 0.0,
    min_down_s: float = 0.0,
    cooldown_s: float = 4.0,
    p_start: float = 0.985,
    target_reliability: float = 0.0,
) -> tuple[SimpleNamespace, DieselPowerBlockSpec]:
    block = DieselPowerBlockSpec(
        enabled=True,
        target_capacity_mw=target_capacity_mw,
        unit_rating_mw=unit_rating_mw,
        delta_t_start_s=delta_t_start_s,
        f_block=f_block,
        residual_ramp_s=residual_ramp_s,
        min_run_s=min_run_s,
        min_down_s=min_down_s,
        cooldown_s=cooldown_s,
        p_start=p_start,
        target_reliability=target_reliability,
    )
    specs = generate_diesel_fleet(block)
    modules = [
        DieselModule(
            DieselConfig(
                asset_id=spec.asset_id,
                rated_mw=spec.rated_mw,
                role=spec.role,
                p_start=block.p_start,
                start_offset_s=spec.start_offset_s,
                delta_t_start_s=spec.delta_t_start_s,
                f_block=spec.f_block,
                residual_ramp_s=spec.residual_ramp_s,
                min_stable_load_mw=spec.min_stable_load_mw,
                min_run_s=spec.min_run_s,
                min_down_s=spec.min_down_s,
                cooldown_s=spec.cooldown_s,
            )
        )
        for spec in specs
    ]
    return SimpleNamespace(diesel_units=modules), block


def _coordinator(
    state: SimpleNamespace,
    block: DieselPowerBlockSpec,
    *,
    debounce_s: float = 0.0,
    restore_hold_s: float = 3.0,
    fuel_burn: float = 230.0,
    min_fuel_runtime_hours: float = 48.0,
) -> DieselFleetCoordinator:
    return DieselFleetCoordinator(
        state.diesel_units,
        debounce_s=debounce_s,
        restore_hold_s=restore_hold_s,
        fuel_burn_gal_per_hr_per_unit_at_full_load=fuel_burn,
        min_fuel_runtime_hours=min_fuel_runtime_hours,
    )


def test_single_unit_output_matches_step_then_residual_ramp() -> None:
    unit = DieselModule(
        DieselConfig(
            asset_id="diesel-000",
            rated_mw=10.0,
            role="primary",
            delta_t_start_s=2.0,
            f_block=0.8,
            residual_ramp_s=5.0,
        )
    )

    unit.command_start(0.0, success_override=True)
    unit.advance(2.0, 2.0)
    assert unit.state == DieselState.SYNCHRONISED
    assert unit.output_mw() == pytest.approx(8.0)

    unit.advance(4.0, 2.0)
    assert unit.output_mw() == pytest.approx(8.8)
    unit.advance(7.0, 3.0)
    assert unit.output_mw() == pytest.approx(10.0)


def test_failed_primary_immediately_starts_a_standby_replacement() -> None:
    state, block = _modules(target_capacity_mw=3.0, target_reliability=0.999)
    fleet = _coordinator(state, block)

    fleet.step(
        gap_mw=1.0,
        sim_time=0.0,
        dt_seconds=0.0,
        success_overrides={"diesel-000": False},
    )
    snapshot = fleet.step(
        gap_mw=1.0,
        sim_time=1.0,
        dt_seconds=1.0,
        success_overrides={"diesel-001": True},
    )

    assert state.diesel_units[0].state == DieselState.FAILED_START
    assert state.diesel_units[1].state == DieselState.STARTING
    assert snapshot.state == "starting"

    snapshot = fleet.step(gap_mw=1.0, sim_time=2.0, dt_seconds=1.0)
    assert state.diesel_units[1].state == DieselState.SYNCHRONISED
    assert snapshot.state == "sustaining"


def test_insufficient_start_fires_once_when_failures_exhaust_standby() -> None:
    state, block = _modules(
        target_capacity_mw=6.0,
        target_reliability=0.999,
    )
    fleet = _coordinator(state, block)
    overrides = {
        "diesel-000": False,
        "diesel-001": False,
        "diesel-002": False,
    }

    fleet.step(1.0, 0.0, 0.0, success_overrides=overrides)
    fleet.step(1.0, 1.0, 1.0, success_overrides=overrides)
    fleet.step(1.0, 2.0, 1.0, success_overrides=overrides)
    snapshot = fleet.step(1.0, 3.0, 1.0, success_overrides=overrides)

    assert snapshot.state == "insufficient_start"
    assert snapshot.shortfall_mw == pytest.approx(6.0)
    assert len(fleet.insufficient_start_alerts) == 1

    snapshot = fleet.step(1.0, 3.0, 1.0, success_overrides=overrides)
    assert snapshot.state == "insufficient_start"
    assert len(fleet.insufficient_start_alerts) == 1


def test_gap_shorter_than_debounce_does_not_activate_fleet() -> None:
    state, block = _modules(target_capacity_mw=3.0, target_reliability=0.0)
    fleet = _coordinator(state, block, debounce_s=2.0)

    fleet.step(1.0, 0.0, 1.0)
    snapshot = fleet.step(0.0, 1.0, 1.0)

    assert snapshot.state == "idle"
    assert snapshot.episode_id is None
    assert all(unit.state == DieselState.OFFLINE for unit in state.diesel_units)


def test_unloading_reversal_preserves_run_start_episode_and_alert_state() -> None:
    state, block = _modules(
        target_capacity_mw=3.0,
        target_reliability=0.0,
        min_run_s=0.0,
    )
    fleet = _coordinator(state, block, restore_hold_s=5.0)

    fleet.step(1.0, 0.0, 0.0, success_overrides={"diesel-000": True})
    fleet.step(1.0, 1.0, 1.0)
    episode_id = fleet.episode_id
    run_start_s = state.diesel_units[0]._run_start_s

    unloading = fleet.step(0.0, 2.0, 1.0)
    assert unloading.state == "unloading"
    assert state.diesel_units[0].state == DieselState.UNLOADING

    sustaining = fleet.step(1.0, 3.0, 1.0)
    assert sustaining.state == "sustaining"
    assert state.diesel_units[0].state == DieselState.SYNCHRONISED
    assert fleet.episode_id == episode_id
    assert state.diesel_units[0]._run_start_s == run_start_s
    assert not fleet.insufficient_start_alerts


def test_synchronised_count_never_exceeds_active_target_during_multi_failure() -> None:
    state, block = _modules(
        target_capacity_mw=6.0,
        target_reliability=0.9999,
    )
    fleet = _coordinator(state, block)
    overrides = {
        "diesel-000": False,
        "diesel-001": True,
        "diesel-002": False,
        "diesel-003": True,
    }

    snapshots = [
        fleet.step(1.0, 0.0, 0.0, success_overrides=overrides),
        fleet.step(1.0, 1.0, 1.0, success_overrides=overrides),
        fleet.step(1.0, 2.0, 1.0, success_overrides=overrides),
        fleet.step(1.0, 3.0, 1.0, success_overrides=overrides),
    ]

    assert all(
        snapshot.synchronised_count <= snapshot.n_active
        for snapshot in snapshots
    )
    assert snapshots[-1].synchronised_count == 2


def test_fuel_depletes_only_from_actual_synchronised_output() -> None:
    state, block = _modules(
        target_capacity_mw=3.0,
        f_block=0.5,
        delta_t_start_s=1.0,
        residual_ramp_s=10.0,
        target_reliability=0.0,
    )
    fleet = _coordinator(
        state,
        block,
        fuel_burn=100.0,
        min_fuel_runtime_hours=1.0,
    )
    initial_fuel = fleet.fuel_remaining_gal

    fleet.step(0.0, 0.0, 1.0)
    assert fleet.fuel_remaining_gal == pytest.approx(initial_fuel)

    fleet.step(1.0, 1.0, 0.0, success_overrides={"diesel-000": True})
    assert fleet.fuel_remaining_gal == pytest.approx(initial_fuel)

    fleet.step(1.0, 2.0, 1.0)
    expected_consumption = (
        (3.0 * 0.5 / 3.0) * 100.0 * (1.0 / 3600.0)
    )
    assert fleet.fuel_remaining_gal == pytest.approx(
        initial_fuel - expected_consumption
    )
    assert state.diesel_units[0].output_mw() == pytest.approx(1.5)