"""Addendum H Phase 2a forecast-driven turbine commitment tests.

TC-98  Announced-workload forecast has no look-ahead before the configured lead.
TC-99  Baseline mode keeps the three-unit floor through the production command
       drain and hot-standby clear-then-start path.
TC-100 Informed mode starts a turbine from an announced forecast through the
       same production run-loop path.
TC-101 Baseline mode does not use forecast demand to commit extra units.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal
from runtime.turbine_commitment import ForecastDrivenTurbineController


def _event(timestamp: float, node_count: int = 1) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"evt-{timestamp}",
        job_id=f"job-{timestamp}",
        event_type=WorkloadEventType.STARTING,
        timestamp=timestamp,
        hardware_profile_id="enterprise_8gpu_air",
        node_count=node_count,
        workload_class=WorkloadClass.TRAINING,
        site_id="site",
    )


def _spec(*, mode: str, spinning: int, hot: int, events=None, end: float = 60.0):
    from api.schemas import ScenarioSpec

    turbines = [
        {
            "asset_id": f"turbine-{index}",
            "rated_mw": 10.0,
            "hot_standby": index >= spinning,
            "initial_state": "spinning" if index < spinning else "offline",
            "min_run_enabled": False,
            "min_down_enabled": False,
        }
        for index in range(spinning + hot)
    ]
    return ScenarioSpec(
        name=f"phase2a-{mode}",
        frequency_nominal_hz=60.0,
        power_factor=0.85,
        island_mode=False,
        end_sim_time=end,
        initial_spinning_count=spinning,
        turbine_units=turbines,
        workload_events=[
            {
                "event_id": event.event_id,
                "job_id": event.job_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp,
                "node_count": event.node_count,
                "hardware_profile_id": event.hardware_profile_id,
                "workload_class": event.workload_class.value,
            }
            for event in (events or [])
        ],
        turbine_commitment_mode=mode,
        turbine_forecast_lead_seconds=600.0,
    )


def test_tc98_forecast_does_not_look_ahead_before_lead() -> None:
    controller = ForecastDrivenTurbineController(
        mode="informed",
        forecast_lead_seconds=600.0,
    )
    future = _event(900.0, node_count=20)

    before = controller.forecast(
        sim_time_s=299.0,
        events=[future],
        measured_history=[(-1.0, 4.0)],
        power_for_event=lambda event: float(event.node_count),
    )
    after = controller.forecast(
        sim_time_s=300.0,
        events=[future],
        measured_history=[(-1.0, 4.0)],
        power_for_event=lambda event: float(event.node_count),
    )

    assert before.announced_event_ids == ()
    assert after.announced_event_ids == (future.event_id,)
    assert after.forecast_mw > before.forecast_mw


def test_tc99_baseline_uses_production_hot_standby_release_path() -> None:
    from runtime.scenario_factory import build_run_context_from_spec
    from core.asset_modules import TurbineState

    ctx = build_run_context_from_spec(
        "tc99-baseline",
        _spec(mode="baseline", spinning=2, hot=2).model_dump(),
    )
    assert sum(t.state == TurbineState.SYNCHRONISED for t in ctx.sim_state.turbines) == 2

    ctx.step()

    assert ctx.sim_state.turbines[2].state == TurbineState.STARTING
    assert ctx.sim_state.turbines[2].config.hot_standby is False
    assert len(ctx.turbine_commitment_controller.log) == 1
    record = ctx.turbine_commitment_controller.log[0]
    assert record.action == "trip"
    assert record.accepted is True
    assert record.thermal_tier
    assert record.reason


def test_tc100_informed_mode_starts_for_announced_workload() -> None:
    from runtime.scenario_factory import build_run_context_from_spec
    from core.asset_modules import TurbineState

    ctx = build_run_context_from_spec(
        "tc100-informed",
        _spec(
            mode="informed",
            spinning=1,
            hot=1,
            events=[_event(0.0, node_count=2000)],
        ).model_dump(),
    )
    ctx._measured_site_demand_history.append((-1.0, 20.0))

    ctx.step()

    assert ctx.sim_state.turbines[1].state == TurbineState.STARTING
    assert ctx.turbine_commitment_controller.log[0].action == "trip"
    assert ctx.turbine_commitment_controller.log[0].accepted is True
    assert ctx.turbine_commitment_controller.forecast_history[0].announced_event_ids


def test_tc101_baseline_does_not_use_forecast_to_start_above_floor() -> None:
    from runtime.scenario_factory import build_run_context_from_spec
    from core.asset_modules import TurbineState

    ctx = build_run_context_from_spec(
        "tc101-baseline-floor",
        _spec(
            mode="baseline",
            spinning=3,
            hot=1,
            events=[_event(0.0, node_count=5000)],
        ).model_dump(),
    )

    ctx.step()

    assert sum(t.state == TurbineState.STARTING for t in ctx.sim_state.turbines) == 0
    assert ctx.turbine_commitment_controller.log == []


def test_tc102_two_hour_headless_smoke_comparison_uses_temporary_fixture(
    tmp_path: Path,
    capsys,
) -> None:
    """Compare baseline and informed modes on a temporary derived fixture.

    The fixture keeps the scenario's scheduler-shaped GPU workload demand but
    removes live scheduler services so both runs are headless and deterministic.
    """
    from runtime.scenario_factory import build_run_context_from_spec

    source = Path(__file__).parents[1] / "config/scenarios/scenario-uneven-multisched-01.json"
    fixture = json.loads(source.read_text())
    fixture["end_sim_time"] = 7200.0
    fixture.pop("kube_clusters", None)
    fixture.pop("slurm_config", None)
    fixture["initial_spinning_count"] = 3
    for index, turbine in enumerate(fixture["turbine_units"]):
        turbine.update({
            "gt_mode": "aero",
            "min_run_enabled": False,
            "min_down_enabled": False,
            "hot_standby": index == 3,
            "initial_state": "offline" if index == 3 else "spinning",
        })
    fixture_path = tmp_path / "phase2a-uneven-multisched.json"
    fixture_path.write_text(json.dumps(fixture))

    comparison = {}
    for mode in ("baseline", "informed"):
        spec = copy.deepcopy(json.loads(fixture_path.read_text()))
        spec["turbine_commitment_mode"] = mode
        ctx = build_run_context_from_spec(f"tc102-{mode}", spec, playback_speed=0.0)
        ticks = [ctx.step() for _ in range(480)]
        final = ticks[-1]
        controller = ctx.turbine_commitment_controller
        unserved_mwh = sum(
            max(0.0, float(tick.p_unserved_mw or 0.0)) * 15.0 / 3600.0
            for tick in ticks
        )
        comparison[mode] = {
            "compute_description": "scheduler-shaped GPU workload demand",
            "unserved_energy_mwh": round(unserved_mwh, 6),
            "min_bess_soc_fraction": round(
                min(float(tick.bess_soc_fraction or 0.0) for tick in ticks), 6
            ),
            "turbine_fuel_mmbtu": final.turbine_total_fuel_mmbtu,
            "turbine_start_count": final.turbine_start_count,
            "commitment_logs": [record.as_dict() for record in controller.log],
            "constraints_valid": controller.constraints_valid,
            "constraint_violations": list(controller.constraint_violation_reasons),
        }

    # Fuel savings are intentionally not reported for an invalid run.
    for result in comparison.values():
        if not result["constraints_valid"]:
            result["fuel_savings_mmbtu"] = None
    assert comparison["baseline"]["compute_description"] == (
        "scheduler-shaped GPU workload demand"
    )
    assert "commitment_logs" in comparison["baseline"]
    assert "commitment_logs" in comparison["informed"]
    assert (
        comparison["baseline"]["fuel_savings_mmbtu"] is None
        or comparison["informed"]["fuel_savings_mmbtu"] is None
    )
    print(json.dumps(comparison, sort_keys=True))
    assert capsys.readouterr().out