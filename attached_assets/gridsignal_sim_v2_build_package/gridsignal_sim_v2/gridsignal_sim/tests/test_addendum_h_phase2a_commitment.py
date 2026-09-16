"""Addendum H Phase 2a controller tests.

The repository already uses TC-98 in the stop-sequencing suite and TC-100 in
the BESS acceptance suite. This addendum therefore uses the free TC-109..115
range; the range was checked across the complete tests tree before naming.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal
from runtime.turbine_commitment import ForecastDrivenTurbineController


def _event(
    timestamp: float,
    node_count: int = 1,
    *,
    job_id: str | None = None,
    event_type: WorkloadEventType = WorkloadEventType.STARTING,
) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=f"{event_type.value}-{timestamp}-{job_id or timestamp}",
        job_id=job_id or f"job-{timestamp}",
        event_type=event_type,
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


def test_tc109_forecast_is_profiled_announced_and_deduplicated() -> None:
    controller = ForecastDrivenTurbineController(
        mode="informed",
        forecast_lead_seconds=600.0,
    )
    start = _event(900.0, node_count=20, job_id="job-a")
    duplicate_scale = _event(
        930.0,
        node_count=25,
        job_id="job-a",
        event_type=WorkloadEventType.SCALE,
    )
    end = _event(
        1200.0,
        node_count=0,
        job_id="job-a",
        event_type=WorkloadEventType.JOB_END,
    )
    before = controller.forecast(
        sim_time_s=299.0,
        events=[start, duplicate_scale, end],
        measured_history=[(-1.0, 4.0)],
        power_for_event=lambda event: float(event.node_count),
        cooling_fraction=0.2,
    )
    after = controller.forecast(
        sim_time_s=300.0,
        events=[start, duplicate_scale, end],
        measured_history=[(-1.0, 4.0)],
        power_for_event=lambda event: float(event.node_count),
        cooling_fraction=0.2,
    )

    assert before.announced_event_ids == ()
    assert after.announced_event_ids == (start.event_id,)
    assert after.peak_forecast_mw > before.peak_forecast_mw
    # SCALE replaces the job's target instead of adding a second copy.
    assert after.peak_forecast_mw == 4.0 + 25.0 * 1.2
    # Matching JOB_END removes the event from later profile points.
    assert after.profile[-1][1] == 4.0


def test_tc110_baseline_uses_production_hot_standby_release_path() -> None:
    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc110-baseline",
        _spec(mode="baseline", spinning=2, hot=2).model_dump(),
    )
    assert sum(t.state == TurbineState.SYNCHRONISED for t in ctx.sim_state.turbines) == 2

    ctx.step()

    assert ctx.sim_state.turbines[2].state == TurbineState.STARTING
    assert ctx.sim_state.turbines[2].config.hot_standby is False
    record = ctx.turbine_commitment_controller.log[0]
    assert record.action == "release"
    assert record.accepted is True
    assert record.changed_state is True
    assert record.source == "forecast_commitment"


def test_tc111_informed_mode_starts_for_announced_workload() -> None:
    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc111-informed",
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
    record = ctx.turbine_commitment_controller.log[0]
    assert record.action == "release"
    assert record.accepted is True
    assert ctx.turbine_commitment_controller.forecast_history[0].announced_event_ids


def test_tc112_stop_uses_lifo_actual_start_order_and_minimum_run_gate() -> None:
    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc112-stop-gates",
        _spec(mode="informed", spinning=3, hot=0).model_dump(),
    )
    for index, turbine in enumerate(ctx.sim_state.turbines):
        turbine.config.p_min_stable_frac = 0.0
        turbine.config.min_run_enabled = True
        turbine.config.t_min_run_s = 300.0
        turbine._run_start_s = float(index * 100)
    controller = ctx.turbine_commitment_controller
    assert controller._candidate_stop(ctx.sim_state.turbines).config.asset_id == "turbine-2"

    ctx.sim_time = 101.0
    controller.evaluate(ctx=ctx, power_for_event=ctx._event_power_mw)
    assert controller.log[-1].unit_id == "turbine-2"
    assert controller.log[-1].accepted is False
    assert "minimum run" in controller.log[-1].refusal_reason

    ctx.sim_time = 1001.0
    controller.evaluate(ctx=ctx, power_for_event=ctx._event_power_mw)
    ctx.drain_operator_commands()
    assert controller.log[-1].unit_id == "turbine-2"
    assert controller.log[-1].action == "stop"
    assert controller.log[-1].accepted is True
    assert ctx.sim_state.turbines[2].state == TurbineState.UNLOADING


def test_tc113_bess_anchor_is_a_power_hard_check_not_a_soc_check() -> None:
    from runtime.scenario_factory import build_run_context_from_spec

    spec = _spec(mode="informed", spinning=1, hot=0).model_dump()
    spec["bess_units"] = [{
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 60.0,
        "initial_soc_fraction": 0.95,
        "grid_forming": True,
        "p_anchor_reserve_mw": 1.0,
    }]
    ctx = build_run_context_from_spec("tc113-anchor", spec)
    bess = ctx.sim_state.bess_units[0]
    bess.soc_mwh = 0.1 * bess.config.usable_mwh
    bess._current_output_mw = 0.0
    controller = ctx.turbine_commitment_controller
    result = SimpleNamespace(
        sim_time_seconds=5.0,
        tick_index=0,
        p_unserved_mw=0.0,
        contingency_release_alert=False,
    )
    controller.record_tick(ctx, result)
    assert not any("bess_anchor_reserve_power" in reason for reason in controller.constraint_violation_reasons)

    bess._current_output_mw = bess.config.rated_mw
    controller.record_tick(ctx, result)
    assert any("bess_anchor_reserve_power" in reason for reason in controller.constraint_violation_reasons)


def test_tc114_logs_external_start_and_refused_stop_with_reconciled_count() -> None:
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc114-command-audit",
        _spec(mode="baseline", spinning=2, hot=2).model_dump(),
    )
    controller = ctx.turbine_commitment_controller
    ctx.sim_state.turbines[2].config.hot_standby = False
    ctx.enqueue_unit_command("turbine-2", "start", source="operator")
    ctx.drain_operator_commands()
    assert controller.log[-1].source == "operator"
    assert controller.log[-1].action == "start"
    assert controller.log[-1].changed_state is True

    ctx.sim_time = 1.0
    turbine = ctx.sim_state.turbines[0]
    turbine.config.min_run_enabled = True
    turbine._run_start_s = 0.0
    ctx.enqueue_unit_command(
        "turbine-0",
        "stop",
        source="operator",
        metadata={"reason": "operator stop request"},
    )
    ctx.drain_operator_commands()
    assert controller.log[-1].accepted is False
    assert controller.log[-1].refusal_reason

    controller.record_tick(
        ctx,
        SimpleNamespace(
            sim_time_seconds=5.0,
            tick_index=0,
            p_unserved_mw=0.0,
            contingency_release_alert=False,
        ),
    )
    assert controller.constraints_valid
    assert controller.start_counts["turbine-2"] == 1


def test_tc115_two_hour_headless_smoke_uses_correct_five_second_integration(
    tmp_path: Path,
    capsys,
) -> None:
    """The fixture is headless because scheduler service clocks are stochastic.

    Removing kube/Slurm services is explicit: this isolates the scripted
    workload/controller comparison and avoids treating scheduler randomness as
    controller behavior. The physics workload events remain unchanged.
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
        ctx = build_run_context_from_spec(f"tc115-{mode}", spec, playback_speed=0.0)
        ticks = [ctx.step() for _ in range(1440)]
        final = ticks[-1]
        controller = ctx.turbine_commitment_controller
        unserved_mwh = sum(
            max(0.0, float(tick.p_unserved_mw or 0.0)) * 5.0 / 3600.0
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

    assert comparison["baseline"]["compute_description"] == (
        "scheduler-shaped GPU workload demand"
    )
    assert "commitment_logs" in comparison["baseline"]
    assert "commitment_logs" in comparison["informed"]
    print(json.dumps(comparison, sort_keys=True))
    assert capsys.readouterr().out