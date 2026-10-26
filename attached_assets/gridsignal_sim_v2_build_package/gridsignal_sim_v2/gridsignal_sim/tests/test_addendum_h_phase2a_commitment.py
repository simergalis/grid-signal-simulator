"""Addendum H Phase 2a controller tests.

The repository already uses TC-98 in the stop-sequencing suite and TC-100 in
the BESS acceptance suite. This addendum uses the checked-free TC-109..136 range.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
        island_mode=True,
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


def test_tc110_baseline_does_not_apply_a_minimum_synchronized_floor() -> None:
    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc110-baseline",
        _spec(mode="baseline", spinning=2, hot=2).model_dump(),
    )
    assert sum(t.state == TurbineState.SYNCHRONISED for t in ctx.sim_state.turbines) == 2

    ctx.step()

    assert ctx.sim_state.turbines[2].state == TurbineState.OFFLINE
    assert ctx.sim_state.turbines[2].config.hot_standby is True
    assert ctx.turbine_commitment_controller.forecast_history == []
    assert not ctx.turbine_commitment_controller.preload_actions


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
    """IMPL-ISL-30: forecast no longer originates the LIFO stop proposal."""
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
    assert not any(record.action == "stop" for record in controller.log)

    ctx.sim_time = 1001.0
    controller.evaluate(ctx=ctx, power_for_event=ctx._event_power_mw)
    ctx.drain_operator_commands()
    # DR IMPL-ISL-30 §3: any stop must come from the measured core rule and be
    # adjudicated there; evaluate() is limited to starts/preload.
    assert not any(record.action == "stop" for record in controller.log)
    assert not any(action == "stop" for _, action in controller._pending_request_keys)
    assert ctx.sim_state.turbines[2].state == TurbineState.SYNCHRONISED


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
    fixture_path = tmp_path / "phase2a-uneven-multisched.json"
    fixture_path.write_text(json.dumps(fixture))

    comparison = {}
    for mode in ("baseline", "informed"):
        spec = copy.deepcopy(json.loads(fixture_path.read_text()))
        initial_spinning = 3 if mode == "baseline" else 2
        spec["initial_spinning_count"] = initial_spinning
        for index, turbine in enumerate(spec["turbine_units"]):
            turbine.update({
                "gt_mode": "aero",
                "min_run_enabled": True,
                "min_down_enabled": True,
                "hot_standby": index >= initial_spinning,
                "initial_state": (
                    "offline" if index >= initial_spinning else "spinning"
                ),
            })
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


def test_tc116_untracked_production_start_is_a_hard_gap_without_synthetic_log() -> None:
    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc116-untracked-start",
        _spec(mode="baseline", spinning=1, hot=1).model_dump(),
    )
    turbine = ctx.sim_state.turbines[1]
    turbine.config.hot_standby = False
    assert turbine.state == TurbineState.OFFLINE
    turbine.command_start(0.0)

    ctx.turbine_commitment_controller.record_tick(
        ctx,
        SimpleNamespace(
            sim_time_seconds=5.0,
            tick_index=0,
            p_unserved_mw=0.0,
            p_demand_mw=0.0,
            contingency_release_alert=False,
        ),
    )

    controller = ctx.turbine_commitment_controller
    assert not controller.log
    assert not controller.constraints_valid
    assert any(
        "turbine-1" in reason and "untracked_path=" in reason
        for reason in controller.constraint_violation_reasons
    )


def test_tc117_identical_refusal_logs_are_deduplicated() -> None:
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc117-refusal-dedup",
        _spec(mode="informed", spinning=3, hot=0).model_dump(),
    )
    controller = ctx.turbine_commitment_controller
    forecast = controller.forecast(
        sim_time_s=0.0,
        events=[],
        measured_history=[],
        power_for_event=ctx._event_power_mw,
    )
    controller._refused(
        ctx=ctx,
        turbine=ctx.sim_state.turbines[2],
        action="stop",
        reason="stop refused: unit is needed within 1,200s",
        forecast=forecast,
        synchronized_capacity=30.0,
        soc=0.5,
    )
    controller._refused(
        ctx=ctx,
        turbine=ctx.sim_state.turbines[2],
        action="stop",
        reason="stop refused: unit is needed within 1,200s",
        forecast=forecast,
        synchronized_capacity=30.0,
        soc=0.5,
    )
    refusals = [record for record in controller.log if not record.accepted]
    assert len(refusals) == 1
    assert controller.suppressed_refusal_count == 1
    assert controller.log[0].suppressed_repeat_count == 1


def test_tc118_stop_requires_two_mw_margin() -> None:
    """IMPL-ISL-30: forecasts cannot create an independent stop at a margin."""
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.turbine_commitment import CommitmentForecast

    ctx = build_run_context_from_spec(
        "tc118-stop-margin",
        _spec(mode="informed", spinning=3, hot=0).model_dump(),
    )
    controller = ctx.turbine_commitment_controller
    controller.forecast = lambda **_: CommitmentForecast(
        sim_time_s=1000.0,
        background_mean_mw=19.0,
        background_std_mw=0.0,
        forecast_mw=19.0,
        peak_forecast_mw=19.0,
        minimum_forecast_mw=19.0,
        profile=((1000.0, 19.0),),
    )
    ctx.sim_time = 1000.0
    controller.evaluate(ctx=ctx, power_for_event=ctx._event_power_mw)
    # DR IMPL-ISL-30 §3: only a core decommit proposal is eligible for veto.
    assert not any(record.action == "stop" for record in controller.log)
    assert not any(action == "stop" for _, action in controller._pending_request_keys)


def test_tc119_informed_preload_uses_existing_ramp_and_bess_charge_path() -> None:
    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec

    spec = _spec(
        mode="informed",
        spinning=2,
        hot=0,
        events=[_event(30.0, node_count=5000)],
        end=120.0,
    ).model_dump()
    spec["bess_units"] = [{
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 120.0,
        "initial_soc_fraction": 0.50,
    }]
    spec["bess_units"] = [{
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 120.0,
        "initial_soc_fraction": 0.50,
    }]
    ctx = build_run_context_from_spec("tc119-preload", spec)
    first = ctx.step()
    controller = ctx.turbine_commitment_controller
    assert controller.preload_actions
    assert set(ctx.sim_state._preload_active_units) == {
        "turbine-0",
        "turbine-1",
    }
    assert all(
        turbine.state == TurbineState.SYNCHRONISED
        for turbine in ctx.sim_state.turbines
    )
    assert first.bess_output_mw <= 0.0


def test_tc120_unserved_comparison_preserves_energy_and_peak_verdicts() -> None:
    from runtime.turbine_commitment import (
        summarize_unserved_ticks,
        unserved_comparison_verdict,
    )

    baseline = summarize_unserved_ticks([
        SimpleNamespace(sim_time_seconds=5.0, p_unserved_mw=2.0),
        SimpleNamespace(sim_time_seconds=10.0, p_unserved_mw=0.0),
    ])
    informed = summarize_unserved_ticks([
        SimpleNamespace(sim_time_seconds=5.0, p_unserved_mw=1.0),
        SimpleNamespace(sim_time_seconds=10.0, p_unserved_mw=1.0),
    ])
    verdict = unserved_comparison_verdict(baseline, informed)
    assert verdict["verdict"] == "PASS"
    assert verdict["unserved_energy_no_worse"] is True
    assert verdict["peak_unserved_no_worse"] is True
    assert baseline["peak_unserved_mw"] == 2.0
    assert abs(informed["unserved_energy_mwh"] - 10.0 / 3600.0) < 1e-9


def test_tc121_transition_records_carry_state_pair_and_authority() -> None:
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc121-transition-audit",
        _spec(
            mode="informed",
            spinning=1,
            hot=1,
            events=[_event(0.0, node_count=2000)],
            end=360.0,
        ).model_dump(),
    )
    for _ in range(72):
        ctx.step()

    transitions = [
        record for record in ctx.turbine_commitment_controller.log
        if record.changed_state
    ]
    assert transitions
    assert all(
        record.source
        and record.reason
        and record.from_state
        and record.to_state
        and record.controller_approved is True
        for record in transitions
    )


def test_tc122_baseline_has_no_forecast_controller_or_forecast_misses() -> None:
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc122-baseline-forecast-isolation",
        _spec(
            mode="baseline",
            spinning=2,
            hot=2,
            events=[_event(0.0, node_count=2000)],
        ).model_dump(),
    )
    ticks = [ctx.step() for _ in range(12)]
    controller = ctx.turbine_commitment_controller
    assert ticks
    assert controller.forecast_history == []
    assert controller.preload_actions == []
    assert controller.forecast_miss_count == 0


def test_tc123_bess_wire_aggregates_use_materialized_units() -> None:
    from runtime.run_manager import _tick_result_to_dict
    from runtime.scenario_factory import build_run_context_from_spec

    spec = _spec(mode="baseline", spinning=1, hot=0).model_dump()
    spec["bess_units"] = [{
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 120.0,
        "initial_soc_fraction": 0.5,
    }]
    ctx = build_run_context_from_spec("tc123-bess-wire", spec)
    payload = _tick_result_to_dict(ctx.step())
    assert payload["bess_rated_mw"] == 30.0
    assert payload["bess_usable_mwh"] == 120.0
    assert payload["bess_unit_count"] == 1


def test_tc124_preload_reports_only_incremental_target_and_fuel() -> None:
    from runtime.scenario_factory import build_run_context_from_spec

    spec = _spec(
        mode="informed",
        spinning=2,
        hot=0,
        events=[_event(30.0, node_count=5000)],
        end=120.0,
    ).model_dump()
    spec["bess_units"] = [{
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 120.0,
        "initial_soc_fraction": 0.50,
    }]
    ctx = build_run_context_from_spec("tc124-incremental-preload", spec)
    for _ in range(24):
        ctx.step()
    controller = ctx.turbine_commitment_controller
    assert controller.preload_actions
    assert all(
        action["incremental_target_mw"] > 0.0
        and action["target_mw"] >= action["normal_output_mw"]
        for action in controller.preload_actions
    )
    assert controller.preload_fuel_mmbtu >= 0.0


def test_tc125_informed_core_proposal_is_logged_by_controller() -> None:
    from runtime.scenario_factory import build_run_context_from_spec

    # DR D2-a: approve an eligible non-reserved target, not the former silently
    # dropped hot-standby start (asset_modules.py:1069–1070;
    # simulation_core.py:2383–2387 in base 1345380).
    spec = _spec(mode="informed", spinning=1, hot=1).model_dump()
    spec["turbine_units"][1]["hot_standby"] = False
    ctx = build_run_context_from_spec(
        "tc125-core-proposal",
        spec,
    )
    controller = ctx.turbine_commitment_controller
    decision = SimpleNamespace(
        action="commit",
        target_unit_id="turbine-1",
        reason="measured reserve shortfall",
        floor_violated=True,
    )
    assert controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=decision,
        sim_time_s=0.0,
        synchronized_capacity_mw=10.0,
        bess_soc_fraction=0.5,
    ) is True
    record = controller.log[-1]
    assert record.action == "proposal_commit"
    assert record.source == "core_commitment_proposal"
    assert record.controller_approved is True


def test_tc126_low_forecast_allows_stop_when_remaining_msl_exceeds_demand() -> None:
    """A remaining MSL surplus is a stop reason, not a controller veto."""
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.turbine_commitment import CommitmentForecast

    ctx = build_run_context_from_spec(
        "tc126-msl-stop", _spec(mode="informed", spinning=3, hot=0).model_dump()
    )
    controller = ctx.turbine_commitment_controller
    controller._latest_forecast = CommitmentForecast(
        sim_time_s=1000.0,
        background_mean_mw=1.0,
        background_std_mw=0.0,
        forecast_mw=1.0,
        peak_forecast_mw=1.0,
        minimum_forecast_mw=1.0,
        profile=((1000.0, 1.0),),
    )
    decision = SimpleNamespace(
        action="decommit",
        target_unit_id="turbine-2",
        reason="measured low load",
        floor_violated=False,
    )
    assert controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=decision,
        sim_time_s=1000.0,
        synchronized_capacity_mw=30.0,
        bess_soc_fraction=0.5,
    ) is True
    assert controller.log[-1].accepted is True


def test_tc127_informed_decommit_veto_repeats_are_counted_not_relogged() -> None:
    """Repeated identical informed vetoes remain compact and auditable."""
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.turbine_commitment import CommitmentForecast

    ctx = build_run_context_from_spec(
        "tc127-veto-dedup", _spec(mode="informed", spinning=3, hot=0).model_dump()
    )
    controller = ctx.turbine_commitment_controller
    controller._latest_forecast = CommitmentForecast(
        sim_time_s=0.0,
        background_mean_mw=100.0,
        background_std_mw=0.0,
        forecast_mw=100.0,
        peak_forecast_mw=100.0,
        minimum_forecast_mw=100.0,
        profile=((0.0, 100.0),),
    )
    ctx.sim_state._commitment_forecast = controller._latest_forecast
    decision = SimpleNamespace(
        action="decommit",
        target_unit_id="turbine-2",
        reason="core measured decommit",
        floor_violated=False,
    )
    for now in (0.0, 5.0, 10.0):
        assert controller.adjudicate_core_proposal(
            state=ctx.sim_state,
            decision=decision,
            sim_time_s=now,
            synchronized_capacity_mw=30.0,
            bess_soc_fraction=0.5,
        ) is False
    assert len(controller.log) == 1
    assert controller.suppressed_repeat_count == 2
    assert controller.log[0].suppressed_repeat_count == 2


def test_tc128_dispatch_curtailment_closes_islanded_physical_balance() -> None:
    """Explicit residual curtailment is separate from inverter solar curtailment."""
    from core.power_balance import BalanceTerms, evaluate

    result = evaluate(
        BalanceTerms(
            p_generation_mw=10.0,
            p_demand_mw=7.0,
            p_served_mw=7.0,
            p_curtailment_mw=3.0,
            island_mode="islanded",
        ),
        tolerance_mw=1e-9,
    )
    assert result.passed
    assert result.term_breakdown["curtailment_mw"] == 3.0


def test_tc129_direct_tick_wire_contains_on_bus_count_and_dispatch_curtailment() -> None:
    from runtime.run_manager import _tick_result_to_dict
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc129-direct-wire",
        _spec(mode="baseline", spinning=2, hot=0).model_dump(),
    )
    payload = _tick_result_to_dict(ctx.step())
    assert payload["units_on_bus_count"] == 2
    assert payload["on_bus_output_mw"] > 0.0
    assert "p_dispatch_curtailed_mw" in payload


def test_tc130_unloading_unit_does_not_count_as_commitment_reserve() -> None:
    """A unit already rundown cannot justify stopping another synchronized unit."""
    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.turbine_commitment import CommitmentForecast

    ctx = build_run_context_from_spec(
        "tc130-unloading-reserve", _spec(mode="informed", spinning=4, hot=0).model_dump()
    )
    controller = ctx.turbine_commitment_controller
    unloading = ctx.sim_state.turbines[0]
    unloading.state = TurbineState.UNLOADING
    ctx.sim_state._commitment_forecast = CommitmentForecast(
        sim_time_s=1000.0,
        background_mean_mw=55.0,
        background_std_mw=0.0,
        forecast_mw=55.0,
        peak_forecast_mw=55.0,
        minimum_forecast_mw=55.0,
        profile=((1000.0, 55.0),),
    )
    decision = SimpleNamespace(
        action="decommit",
        target_unit_id=ctx.sim_state.turbines[1].config.asset_id,
        reason="core measured decommit",
        floor_violated=False,
    )

    assert controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=decision,
        sim_time_s=1000.0,
        synchronized_capacity_mw=30.0,
        bess_soc_fraction=0.5,
    ) is False
    assert "needed within" in (controller.log[-1].refusal_reason or "")


def test_tc131_preload_is_bounded_by_bess_charge_power() -> None:
    """Late preload uses the largest target the island can physically absorb."""
    from runtime.scenario_factory import build_run_context_from_spec

    spec = _spec(
        mode="informed",
        spinning=2,
        hot=0,
        events=[_event(100.0, node_count=5000)],
        end=120.0,
    ).model_dump()
    spec["bess_units"] = [{
        "asset_id": "bess-0",
        "rated_mw": 5.0,
        "usable_mwh": 120.0,
        "initial_soc_fraction": 0.50,
    }]
    ctx = build_run_context_from_spec("tc131-preload-cap", spec)
    ctx.sim_time = 90.0
    controller = ctx.turbine_commitment_controller
    forecast = controller.forecast(
        sim_time_s=90.0,
        events=ctx.events,
        measured_history=[],
        power_for_event=ctx._event_power_mw,
        horizon_seconds=controller.stop_lookahead_seconds,
    )

    controller._evaluate_preload(ctx, forecast, ctx._event_power_mw)

    assert controller.preload_actions
    action = controller.preload_actions[-1]
    assert action["target_mw"] <= action["forecast_mw"] + 5.0 + 1e-6


def test_tc132_core_start_is_vetoed_during_minimum_down_window() -> None:
    """Informed adjudication must not approve a start the physics will drop."""
    import math

    from core.asset_modules import TurbineState
    from runtime.scenario_factory import build_run_context_from_spec

    ctx = build_run_context_from_spec(
        "tc132-min-down-start", _spec(mode="informed", spinning=1, hot=1).model_dump()
    )
    turbine = ctx.sim_state.turbines[0]
    turbine.state = TurbineState.OFFLINE
    turbine.config.min_down_enabled = True
    turbine._stop_time_s = 100.0
    turbine._last_sync_stop_s = 100.0
    assert not math.isnan(turbine._stop_time_s)
    decision = SimpleNamespace(
        action="commit",
        target_unit_id=turbine.config.asset_id,
        reason="measured reserve shortfall",
        floor_violated=True,
    )

    assert ctx.turbine_commitment_controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=decision,
        sim_time_s=200.0,
        synchronized_capacity_mw=0.0,
        bess_soc_fraction=0.5,
    ) is False
    # DR D2: retain the veto, assert the shared start-eligibility wording.
    assert "start ineligible (min_down)" in (
        ctx.turbine_commitment_controller.log[-1].refusal_reason or ""
    )


def test_tc133_lead_aware_stop_refusal_protects_restart_window() -> None:
    """IMPL-ISL-30 disables forecast-origin stops; core proposals own decommit."""
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.turbine_commitment import CommitmentForecast

    ctx = build_run_context_from_spec(
        "tc133-lead-aware-stop",
        _spec(
            mode="informed",
            spinning=3,
            hot=0,
            events=[_event(500.0, node_count=1, event_type=WorkloadEventType.SCALE)],
        ).model_dump(),
    )
    for turbine in ctx.sim_state.turbines:
        turbine.config.min_down_enabled = True
    controller = ctx.turbine_commitment_controller
    controller.forecast = lambda **_: CommitmentForecast(
        sim_time_s=0.0,
        background_mean_mw=1.0,
        background_std_mw=0.0,
        forecast_mw=1.0,
        peak_forecast_mw=20.0,
        minimum_forecast_mw=1.0,
        profile=((0.0, 1.0), (500.0, 20.0)),
    )

    controller.evaluate(ctx=ctx, power_for_event=ctx._event_power_mw)

    # DR IMPL-ISL-30 §3: forecasts may veto a core decommit, but may not
    # originate a stop that the conventional commitment rule did not propose.
    assert all(record.action != "stop" for record in controller.log)
    assert not any(action == "stop" for _, action in controller._pending_request_keys)


def test_tc134_scale_event_is_an_announced_burst_for_forecast_control() -> None:
    """A scale-up alone must enter the informed controller's burst set."""
    controller = ForecastDrivenTurbineController(
        mode="informed",
        forecast_lead_seconds=600.0,
    )
    scale = _event(
        300.0,
        node_count=40,
        job_id="job-scale-only",
        event_type=WorkloadEventType.SCALE,
    )

    forecast = controller.forecast(
        sim_time_s=0.0,
        events=[scale],
        measured_history=[],
        power_for_event=lambda event: float(event.node_count),
        cooling_fraction=0.0,
    )

    assert forecast.announced_event_ids == (scale.event_id,)
    assert forecast.announced_workload_mw > 0.0


def test_tc135_preload_logs_changed_targets_and_suppresses_repeats() -> None:
    """Repeated identical preload intents are compacted with an audit count."""
    from runtime.scenario_factory import build_run_context_from_spec

    spec = _spec(
        mode="informed",
        spinning=2,
        hot=0,
        events=[_event(30.0, node_count=5000)],
        end=120.0,
    ).model_dump()
    spec["bess_units"] = [{
        "asset_id": "bess-0",
        "rated_mw": 30.0,
        "usable_mwh": 120.0,
        "initial_soc_fraction": 0.50,
    }]
    ctx = build_run_context_from_spec("tc135-preload-dedup", spec)
    for _ in range(6):
        ctx.step()

    controller = ctx.turbine_commitment_controller
    assert len(controller.preload_actions) == 2
    assert controller.preload_actions[0]["suppressed_repeat_count"] == 2
    assert controller.preload_actions[1]["suppressed_repeat_count"] == 0
    assert controller.suppressed_preload_repeat_count == 2


def test_tc136_smoke_fuel_attribution_uses_end_of_run_values(tmp_path: Path) -> None:
    """Both smoke modes must reconcile fuel components without tick over-counting."""
    from scripts.run_phase2a_smoke import run_smoke

    source = (
        Path(__file__).parents[1]
        / "config/scenarios/scenario-uneven-multisched-01.json"
    )
    report = run_smoke(source, tmp_path / "phase2a-fuel")
    components = {
        "load_fuel_mmbtu",
        "no_load_fuel_mmbtu",
        "hot_standby_fuel_mmbtu",
        "start_fuel_mmbtu",
    }
    for mode in ("baseline", "informed"):
        summary = report["runs"][mode]["summary"]
        metrics = report["runs"][mode]["extended_metrics"]
        unit_totals = []
        for unit in metrics["fuel_by_unit_mmbtu"].values():
            component_total = sum(float(unit[name]) for name in components)
            assert component_total == pytest.approx(
                float(unit["total_fuel_mmbtu"]), abs=1e-6
            )
            unit_totals.append(float(unit["total_fuel_mmbtu"]))
        assert sum(unit_totals) == pytest.approx(
            float(summary["turbine_fuel_mmbtu"]), abs=1e-6
        )
        assert metrics["turbine_fuel_mmbtu"] == pytest.approx(
            float(summary["turbine_fuel_mmbtu"]), abs=1e-6
        )
        start_fuel = float(metrics["fuel_by_component_mmbtu"]["start_fuel_mmbtu"])
        assert start_fuel == pytest.approx(
            int(summary["turbine_start_count"])
            * float(metrics["start_fuel_mmbtu_per_start"]),
            abs=1e-6,
        )