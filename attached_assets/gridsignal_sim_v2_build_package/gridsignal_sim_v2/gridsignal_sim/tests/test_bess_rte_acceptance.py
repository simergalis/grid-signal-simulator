"""DR-2026-09-06-BESS-RTE Phase 4e acceptance tests (TC-100..TC-108)."""

from __future__ import annotations

import contextlib
import dataclasses
import math
from pathlib import Path

import pytest

from core import site_parameters
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.asset_modules import BessModule, CoolingModule
from core.contingency import BessSnapshot, PlantState, evaluate_contingency
from core.models import BessConfig, IslandMode, SiteConfig
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from runtime.run_manager import _apply_soc_corruption
from runtime.telemetry_corruption import CorruptionEntry, TelemetryCorruptionSchedule


def _bess(
    *,
    round_trip_efficiency: float | None = None,
    rated_mw: float = 4.0,
    usable_mwh: float = 4.0,
    initial_soc_fraction: float = 1.0,
    grid_forming: bool = False,
    anchor_reserve_mw: float = 0.0,
) -> BessModule:
    kwargs = {}
    if round_trip_efficiency is not None:
        kwargs["bess_round_trip_efficiency"] = round_trip_efficiency
    return BessModule(
        BessConfig(
            asset_id="bess-rte-acceptance",
            rated_mw=rated_mw,
            usable_mwh=usable_mwh,
            initial_soc_fraction=initial_soc_fraction,
            bess_response_tau_s=0.0,
            grid_forming=grid_forming,
            p_anchor_reserve_mw=anchor_reserve_mw,
            **kwargs,
        )
    )


def _coverage(bess: BessModule):
    snapshot = BessSnapshot(
        asset_id=bess.asset_id,
        rated_mw=bess.config.rated_mw,
        soc_mwh=bess.soc_mwh,
        usable_mwh=bess.config.usable_mwh,
        p_anchor_reserve_mw=bess.config.p_anchor_reserve_mw,
        grid_forming=bess.config.grid_forming,
        discharge_efficiency=bess.config.discharge_efficiency,
    )
    return evaluate_contingency(
        PlantState(
            turbine_snapshots=(),
            bess_snapshots=(snapshot,),
            island_mode=IslandMode.ISLANDED,
            curtailable_capacity_mw=0.0,
            renewable_mw=0.0,
        )
    )


@contextlib.contextmanager
def _plane_guard_active():
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _simulation_state(*, bess: BessModule, demand_mw: float) -> SimulationState:
    site = SiteConfig(
        site_id="bess-rte-acceptance",
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        pue_base=1.03,
        island_mode=IslandMode.ISLANDED,
    )
    state = SimulationState(
        run_id="bess-rte-acceptance",
        site=site,
        gpu_modules=[],
        turbines=[],
        bess_units=[bess],
        solar_arrays=[],
        cooling=CoolingModule(asset_id="cooling", site=site),
    )
    state.compute_floor_mw = demand_mw
    return state


def _evaluate_one_tick(state: SimulationState, dt_seconds: float):
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


def test_tc100_discharge_energy_cost() -> None:
    bess = _bess()
    stored_before_mwh = bess.soc_mwh
    delivered_energy_mwh = bess.deliverable_energy_mwh()
    discharge_hours = delivered_energy_mwh / bess.config.rated_mw
    delivered_power_mw = bess.cover_shortfall(
        allocated_mw=bess.config.rated_mw,
        fleet_covered=False,
        dt_seconds=discharge_hours * 3600.0,
        power_ceiling_mw=bess.bridging_available_mw(IslandMode.ISLANDED),
    )
    delivered_to_bus_mwh = delivered_power_mw * discharge_hours
    stored_draw_mwh = stored_before_mwh - bess.soc_mwh
    expected_stored_draw_mwh = (
        delivered_to_bus_mwh / bess.config.discharge_efficiency
    )

    assert delivered_to_bus_mwh == pytest.approx(delivered_energy_mwh)
    assert stored_draw_mwh == pytest.approx(expected_stored_draw_mwh)


def test_tc101_round_trip_closure() -> None:
    bess = _bess(initial_soc_fraction=0.0)
    cycle_hours = bess.config.usable_mwh / bess.config.rated_mw
    absorbed_power_mw = bess.absorb_surplus(
        surplus_mw=bess.config.rated_mw,
        dt_seconds=cycle_hours * 3600.0,
    )
    absorbed_bus_energy_mwh = absorbed_power_mw * cycle_hours
    discharge_power_mw = bess.cover_shortfall(
        allocated_mw=bess.config.rated_mw,
        fleet_covered=False,
        dt_seconds=cycle_hours * 3600.0,
        power_ceiling_mw=bess.bridging_available_mw(IslandMode.ISLANDED),
    )
    returned_bus_energy_mwh = discharge_power_mw * cycle_hours
    expected_returned_mwh = (
        absorbed_bus_energy_mwh * bess.config.bess_round_trip_efficiency
    )

    assert returned_bus_energy_mwh == pytest.approx(
        expected_returned_mwh, rel=1e-9
    )


def test_tc102_sustainable_duration() -> None:
    bess = _bess(initial_soc_fraction=0.75)
    requested_power_mw = bess.config.rated_mw / 2.0
    expected_seconds = (
        bess.soc_mwh
        * bess.config.discharge_efficiency
        * 3600.0
        / requested_power_mw
    )

    assert bess.max_sustainable_seconds(
        requested_power_mw, IslandMode.ISLANDED
    ) == pytest.approx(expected_seconds)


def test_tc103_power_domain_invariance() -> None:
    for discharge_efficiency in (0.0, 0.25, 0.75, 1.0):
        bess = _bess(
            grid_forming=True,
            anchor_reserve_mw=1.0,
        )
        bess.config.discharge_efficiency = discharge_efficiency
        expected_power_ceiling_mw = (
            bess.config.rated_mw - bess.config.p_anchor_reserve_mw
        )

        assert bess.bridging_available_mw(
            IslandMode.ISLANDED
        ) == pytest.approx(expected_power_ceiling_mw)


def test_tc104_contingency_energy_is_deliverable() -> None:
    bess = _bess(initial_soc_fraction=0.75)
    expected_deliverable_mwh = (
        bess.soc_mwh * bess.config.discharge_efficiency
    )

    assert _coverage(bess).bess_usable_energy_mwh == pytest.approx(
        expected_deliverable_mwh
    )


def test_tc105_single_conversion_rule() -> None:
    catalogue_efficiency = site_parameters.value("bess_round_trip_efficiency")
    for round_trip_efficiency in (0.25, catalogue_efficiency, 1.0):
        dt_seconds = 3600.0
        core_bess = _bess(
            round_trip_efficiency=round_trip_efficiency,
            rated_mw=4.0,
            usable_mwh=4.0,
            initial_soc_fraction=0.25,
        )
        method_bess = _bess(
            round_trip_efficiency=round_trip_efficiency,
            rated_mw=core_bess.config.rated_mw,
            usable_mwh=core_bess.config.usable_mwh,
            initial_soc_fraction=core_bess.config.initial_soc_fraction,
        )
        state = _simulation_state(
            bess=core_bess,
            demand_mw=core_bess.config.rated_mw,
        )
        core_tick = _evaluate_one_tick(state, dt_seconds)
        method_ceiling_mw = method_bess.cover_shortfall(
            allocated_mw=method_bess.config.rated_mw,
            fleet_covered=False,
            dt_seconds=dt_seconds,
            power_ceiling_mw=method_bess.bridging_available_mw(
                IslandMode.ISLANDED
            ),
        )
        expected_ceiling_mw = (
            method_bess.config.usable_mwh
            * method_bess.config.initial_soc_fraction
            * method_bess.config.discharge_efficiency
            / (dt_seconds / 3600.0)
        )

        assert core_tick.bess_output_mw == pytest.approx(expected_ceiling_mw)
        assert method_ceiling_mw == pytest.approx(expected_ceiling_mw)
        assert core_tick.bess_output_mw == pytest.approx(method_ceiling_mw)


def test_tc106_corruption_precedes_efficiency_conversion() -> None:
    from runtime.scenario_factory import build_run_context

    ctx = build_run_context(
        run_id="tc106",
        job_id="tc106-job",
        node_count=500,
        turbine_count=2,
        turbine_rated_mw=15.0,
        r_asset_mw_per_s=0.2,
        bess_rated_mw=5.0,
        bess_usable_mwh=2.0,
        end_sim_time=300.0,
    )
    tick = ctx.step()
    bess = ctx.sim_state.bess_units[0]
    stored_soc_mwh = bess.config.usable_mwh * 0.75
    corruption_scale = 0.5
    bess.soc_mwh = stored_soc_mwh
    tick = dataclasses.replace(
        tick,
        bess_soc_fraction=stored_soc_mwh / bess.config.usable_mwh,
    )
    ctx._bess_soc_history = [stored_soc_mwh * corruption_scale]
    ctx.telemetry_corruption = TelemetryCorruptionSchedule(
        schedule=[
            CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
        ],
        seed=42,
        noise_sigma=0.0,
        dropout_prob=0.0,
        max_stale=1,
    )
    result = _apply_soc_corruption(ctx, tick)
    expected_corrupted_deliverable_mwh = (
        stored_soc_mwh
        * corruption_scale
        * bess.config.discharge_efficiency
    )
    expected_physics_fraction = stored_soc_mwh / bess.config.usable_mwh

    assert result.contingency_coverage is not None
    assert result.contingency_coverage.bess_usable_energy_mwh == pytest.approx(
        expected_corrupted_deliverable_mwh
    )
    assert bess.soc_mwh == pytest.approx(stored_soc_mwh)
    assert result.bess_soc_fraction == pytest.approx(expected_physics_fraction)


def test_tc107_efficiency_resolves_through_parameter_loader() -> None:
    config = BessConfig(asset_id="tc107")
    catalogue_efficiency = site_parameters.value("bess_round_trip_efficiency")
    asset_modules_source = Path(
        BessModule.__module__.replace(".", "/") + ".py"
    )
    asset_modules_source = Path(__file__).parents[1] / asset_modules_source
    source_text = asset_modules_source.read_text()
    round_trip_literal = format(config.bess_round_trip_efficiency, ".15g")
    one_way_literal = format(config.discharge_efficiency, ".15g")

    assert config.bess_round_trip_efficiency == pytest.approx(
        catalogue_efficiency
    )
    assert round_trip_literal not in source_text
    assert one_way_literal not in source_text


@pytest.fixture(params=[pytest.param(1.0, id="unity-round-trip-efficiency")])
def unity_efficiency_bess(request) -> BessModule:
    return _bess(
        round_trip_efficiency=request.param,
        rated_mw=4.0,
        usable_mwh=4.0,
        initial_soc_fraction=0.5,
    )


def test_tc108_unity_efficiency_restores_prechange_behaviour(
    unity_efficiency_bess: BessModule,
) -> None:
    bess = unity_efficiency_bess
    dt_seconds = 900.0
    dt_hours = dt_seconds / 3600.0
    delivered_power_mw = bess.config.rated_mw / 2.0
    delivered_energy_mwh = delivered_power_mw * dt_hours
    stored_before_discharge_mwh = bess.soc_mwh
    actual_delivered_power_mw = bess.cover_shortfall(
        allocated_mw=delivered_power_mw,
        fleet_covered=False,
        dt_seconds=dt_seconds,
        power_ceiling_mw=bess.bridging_available_mw(IslandMode.ISLANDED),
    )
    stored_draw_mwh = stored_before_discharge_mwh - bess.soc_mwh
    expected_stored_draw_mwh = (
        delivered_energy_mwh / bess.config.discharge_efficiency
    )

    assert actual_delivered_power_mw * dt_hours == pytest.approx(
        delivered_energy_mwh
    )
    assert stored_draw_mwh == pytest.approx(expected_stored_draw_mwh)

    stored_before_charge_mwh = bess.soc_mwh
    absorbed_power_mw = bess.absorb_surplus(
        surplus_mw=delivered_power_mw,
        dt_seconds=dt_seconds,
    )
    absorbed_energy_mwh = absorbed_power_mw * dt_hours
    stored_increment_mwh = bess.soc_mwh - stored_before_charge_mwh
    expected_increment_mwh = (
        absorbed_energy_mwh * bess.config.charge_efficiency
    )

    assert stored_increment_mwh == pytest.approx(expected_increment_mwh)

    requested_power_mw = bess.config.rated_mw / 2.0
    expected_sustainable_seconds = (
        bess.soc_mwh
        * bess.config.discharge_efficiency
        / requested_power_mw
        * 3600.0
    )

    assert bess.max_sustainable_seconds(
        requested_power_mw, IslandMode.ISLANDED
    ) == pytest.approx(expected_sustainable_seconds)

    expected_contingency_energy_mwh = (
        bess.soc_mwh * bess.config.discharge_efficiency
    )

    assert _coverage(bess).bess_usable_energy_mwh == pytest.approx(
        expected_contingency_energy_mwh
    )

    soc_floor_mwh = bess.soc_mwh / 4.0
    expected_energy_limited_ceiling_mw = (
        (bess.soc_mwh - soc_floor_mwh)
        * bess.config.discharge_efficiency
        / dt_hours
    )
    ceiling_bess = _bess(
        round_trip_efficiency=bess.config.bess_round_trip_efficiency,
        rated_mw=expected_energy_limited_ceiling_mw * 2.0,
        usable_mwh=bess.config.usable_mwh,
        initial_soc_fraction=bess.soc_fraction,
    )
    actual_energy_limited_ceiling_mw = ceiling_bess.cover_shortfall(
        allocated_mw=ceiling_bess.config.rated_mw,
        fleet_covered=False,
        dt_seconds=dt_seconds,
        power_ceiling_mw=ceiling_bess.bridging_available_mw(
            IslandMode.ISLANDED
        ),
        soc_floor_mwh=soc_floor_mwh,
    )

    assert actual_energy_limited_ceiling_mw == pytest.approx(
        expected_energy_limited_ceiling_mw
    )