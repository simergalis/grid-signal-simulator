"""Phase 1 raw scenario-sweep driver.

The driver intentionally calls ``DispatchArbitrator.stage_for_predicted_step``,
``DispatchArbitrator.tick``, ``BessModule.bridging_available_mw``, and the
existing turbine module APIs.  It does not reproduce any shortfall or
bridging formula and does not calculate percentiles, maxima, or recommendations.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from core.asset_modules import BessModule, TurbineModule
from core.dispatch import DispatchArbitrator
from core.models import TurbineState

from .models import (
    AnchorMode,
    BessSizingFleetConfig,
    BessSizingScenario,
    BessSizingSweepResult,
    ScenarioTrace,
    StageTrace,
    TickTrace,
)


def _materialize_fleet(
    site_fleet: BessSizingFleetConfig,
    scenario: BessSizingScenario,
) -> BessSizingFleetConfig:
    """Resolve scenario-owned fleet fields, falling back to the supplied fleet."""

    turbines = scenario.turbine_fleet or site_fleet.turbine_configs
    bess_configs = scenario.bess_fleet or site_fleet.bess_configs
    site = scenario.site_config or site_fleet.site_config

    if scenario.anchor_mode == AnchorMode.GRID_FORMING:
        anchor_id = scenario.anchor_bess_asset_id
        if anchor_id is None and bess_configs:
            anchor_id = bess_configs[0].asset_id
        bess_configs = tuple(
            replace(
                config,
                grid_forming=(config.asset_id == anchor_id),
                p_anchor_reserve_mw=(
                    scenario.p_anchor_reserve_mw
                    if config.asset_id == anchor_id
                    else config.p_anchor_reserve_mw
                ),
            )
            for config in bess_configs
        )
    else:
        bess_configs = tuple(
            replace(config, grid_forming=False) for config in bess_configs
        )

    return BessSizingFleetConfig(
        site_config=site,
        turbine_configs=tuple(turbines),
        bess_configs=tuple(bess_configs),
    )


def _materialize_turbines(scenario: BessSizingScenario) -> list[TurbineModule]:
    states = scenario.initial_turbine_states or tuple(
        TurbineState.OFFLINE for _ in scenario.turbine_fleet
    )
    outputs = scenario.initial_turbine_outputs_mw or tuple(
        0.0 for _ in scenario.turbine_fleet
    )
    turbines = [
        TurbineModule(
            config=replace(
                config,
                initial_thermal_state=scenario.turbine_initial_thermal_state,
            ),
            state=state,
            _current_output_mw=output,
        )
        for config, state, output in zip(
            scenario.turbine_fleet,
            states,
            outputs,
        )
    ]
    return turbines


def _set_unavailable_turbines(
    turbines: Sequence[TurbineModule],
    unavailable_ids: Sequence[str],
) -> None:
    unavailable = set(unavailable_ids)
    for turbine in turbines:
        if turbine.asset_id in unavailable:
            turbine.state = TurbineState.OUT_OF_SERVICE
            turbine._current_output_mw = 0.0


def run_bess_sizing_scenario(
    site_fleet: BessSizingFleetConfig,
    scenario: BessSizingScenario,
) -> ScenarioTrace:
    """Run one scenario and return only raw stage and per-tick traces."""

    fleet = _materialize_fleet(site_fleet, scenario)
    turbines = _materialize_turbines(
        replace(scenario, turbine_fleet=fleet.turbine_configs)
    )
    bess_units = [BessModule(config) for config in fleet.bess_configs]
    arbitrator = DispatchArbitrator(
        turbines=turbines,
        bess_units=bess_units,
        site=fleet.site_config,
    )

    stage_traces: list[StageTrace] = []
    tick_traces: list[TickTrace] = []
    steps = tuple(sorted(scenario.dispatch_steps, key=lambda step: step.time_s))
    next_step = 0
    p_dispatch_required_mw = scenario.initial_dispatch_required_mw
    sim_time = 0.0

    while sim_time <= scenario.horizon_s + 1e-9:
        while next_step < len(steps) and steps[next_step].time_s <= sim_time + 1e-9:
            step = steps[next_step]
            if (
                step.time_s <= 1e-9
                and scenario.unavailable_turbine_ids
            ):
                _set_unavailable_turbines(
                    turbines,
                    scenario.unavailable_turbine_ids,
                )
            alert, credit_mw, peak_shortfall_mw = (
                arbitrator.stage_for_predicted_step(
                    delta_p_mw=step.delta_p_mw,
                    dt_lead_seconds=step.dt_lead_seconds,
                    sim_time=sim_time,
                )
            )
            stage_traces.append(
                StageTrace(
                    time_s=sim_time,
                    step_label=step.label,
                    alert_shortfall_mw=(
                        alert.shortfall_mw if alert is not None else None
                    ),
                    alert_gap_duration_s=(
                        alert.gap_duration_s if alert is not None else None
                    ),
                    already_ramped_mw=credit_mw,
                    peak_shortfall_mw=peak_shortfall_mw,
                )
            )
            p_dispatch_required_mw += step.delta_p_mw
            next_step += 1

        turbine_output_mw, bess_output_mw, _setpoint_mw, _candidates = (
            arbitrator.tick(
                p_dispatch_required_mw=p_dispatch_required_mw,
                dt_seconds=scenario.tick_seconds,
            )
        )
        bridging_by_unit = tuple(
            bess.bridging_available_mw(fleet.site_config.island_mode)
            for bess in bess_units
        )
        tick_traces.append(
            TickTrace(
                time_s=sim_time,
                p_dispatch_required_mw=p_dispatch_required_mw,
                turbine_output_mw=turbine_output_mw,
                bess_output_mw=bess_output_mw,
                bridging_capacity_mw=sum(bridging_by_unit),
                bridging_capacity_by_unit_mw=bridging_by_unit,
            )
        )
        sim_time += scenario.tick_seconds

    return ScenarioTrace(
        scenario_id=scenario.scenario_id,
        scenario_type=scenario.scenario_type,
        stage_traces=tuple(stage_traces),
        tick_traces=tuple(tick_traces),
    )


def run_bess_sizing_sweep(
    site_fleet: BessSizingFleetConfig,
    scenarios: Sequence[BessSizingScenario],
) -> BessSizingSweepResult:
    """Run the supplied scenario set and collect raw traces only."""

    traces = tuple(
        run_bess_sizing_scenario(site_fleet, scenario)
        for scenario in scenarios
    )
    return BessSizingSweepResult(traces=traces)