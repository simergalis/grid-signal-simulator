"""DR-2026-10-22-ISL-P4, TC-ISL-07a–g: observation-only staging events.

PROPOSED_HERE: all fixture times, deltas, counts and resets below are synthetic
test inputs, not new operating settings. They isolate logging from dispatch.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from core import simulation_core as core
from core.commitment import CommitmentDecision
from core.dispatch import DispatchArbitrator
from core.models import ContingencyState, TurbineState, WorkloadEventType
from runtime.scenario_factory import build_run_context_from_spec
from runtime.turbine_commitment import ForecastDrivenTurbineController
from tests.test_addendum_h_phase2a_commitment import _event, _spec


# PROPOSED_HERE: short, distinct test-only command time and staging inputs.
TIME_S = 100.0
DELTA_MW = 5.0
LEAD_S = 0.0


def _context(mode="baseline"):
    spec = _spec(mode=mode, spinning=1, hot=1).model_dump(mode="json")
    spec["turbine_units"][1]["hot_standby"] = False
    ctx = build_run_context_from_spec("tc-isl-07", spec)
    return ctx, ctx.sim_state.turbines[1]


def _stage(ctx, *, time=TIME_S, delta=DELTA_MW):
    return ctx.sim_state.arbitrator.stage_for_predicted_step(delta, LEAD_S, time)


def _starts(controller):
    return [
        record for record in controller.log
        if record.action in {"start", "release"}
        and record.accepted and record.changed_state
    ]


def _observe_tick(ctx, time, index):
    ctx.turbine_commitment_controller.record_tick(
        ctx,
        SimpleNamespace(
            sim_time_seconds=time, tick_index=index, p_unserved_mw=0.0,
            contingency_release_alert=False,
        ),
    )


@pytest.mark.parametrize("with_pending", [True, False])
def test_tc_isl_07a_success_event_uses_event_time_sink_and_preserves_order(
    with_pending, monkeypatch,
):
    ctx, turbine = _context()
    state = ctx.sim_state
    original = ctx.turbine_commitment_controller
    replacement = ForecastDrivenTurbineController(mode="baseline")
    state._commitment_transition_sink = replacement
    order = []
    command = turbine.command_start
    pending = state._pending_start.record_start
    record = replacement.record_transition
    if not with_pending:
        state.arbitrator.pending_start = None

    def command_spy(time):
        order.append("command")
        command(time)

    def pending_spy(unit_id, time):
        order.append("pending")
        pending(unit_id, time)

    def record_spy(**kwargs):
        order.append("event")
        if with_pending:
            assert state._pending_start.pending_unit_id == turbine.config.asset_id
        record(**kwargs)

    monkeypatch.setattr(turbine, "command_start", command_spy)
    monkeypatch.setattr(state._pending_start, "record_start", pending_spy)
    monkeypatch.setattr(replacement, "record_transition", record_spy)
    _stage(ctx)
    assert order == (["command", "pending", "event"] if with_pending else ["command", "event"])
    assert turbine._start_count == 1
    assert not original.log
    event, = _starts(replacement)
    assert (event.unit_id, event.sim_time_s) == (turbine.config.asset_id, TIME_S)
    assert event.source == "predicted_step_staging"
    assert event.thermal_tier == turbine.thermal_state.value
    assert (event.from_state, event.to_state) == ("offline", "starting")
    assert event.controller_approved is None
    assert f"delta_p_mw={DELTA_MW}" in event.reason
    assert f"dt_lead_seconds={LEAD_S}" in event.reason


@pytest.mark.parametrize("blocked", ["min_down", "pending", "refused", "no_increment"])
def test_tc_isl_07b_only_an_actual_counted_transition_emits(blocked, monkeypatch):
    ctx, turbine = _context()
    if blocked == "min_down":
        turbine.config.min_down_enabled = True
        turbine._stop_time_s = TIME_S
    elif blocked == "pending":
        ctx.sim_state._pending_start.record_start("other-unit", TIME_S)
    elif blocked == "refused":
        monkeypatch.setattr(turbine, "command_start", lambda time: None)
    else:
        # Test a state-only fake command: an event also requires a count increment.
        monkeypatch.setattr(
            turbine, "command_start",
            lambda time: setattr(turbine, "state", TurbineState.STARTING),
        )
    _stage(ctx)
    assert turbine._start_count == 0
    assert not _starts(ctx.turbine_commitment_controller)
    if blocked != "no_increment":
        assert turbine.state == TurbineState.OFFLINE


def test_tc_isl_07c_repeated_staging_does_not_duplicate():
    ctx, turbine = _context()
    _stage(ctx)
    _stage(ctx)
    _stage(ctx, time=TIME_S + 1.0)
    assert turbine._start_count == 1
    assert len(_starts(ctx.turbine_commitment_controller)) == 1


@pytest.mark.parametrize("event_type", [
    WorkloadEventType.STARTING, WorkloadEventType.SOLAR_STEP,
])
def test_tc_isl_07d_workload_and_renewable_share_the_hook(event_type):
    ctx, turbine = _context()
    event = replace(
        _event(TIME_S), event_type=event_type,
        renewable_shortfall_mw=DELTA_MW,
    )
    ctx.sim_state.apply_workload_signal(event, LEAD_S)
    logged, = _starts(ctx.turbine_commitment_controller)
    assert logged.unit_id == turbine.config.asset_id
    assert logged.source == "predicted_step_staging"
    assert logged.sim_time_s == event.timestamp
    assert turbine._start_count == 1


@pytest.mark.parametrize("path", ["operator", "core_commitment", "automatic_contingency"])
def test_tc_isl_07e_already_logged_paths_are_not_duplicated(path, monkeypatch):
    ctx, turbine = _context()
    ctx.sim_time = TIME_S
    if path == "operator":
        ctx.enqueue_unit_command(turbine.config.asset_id, "start", source="operator")
        ctx.drain_operator_commands()
    elif path == "core_commitment":
        monkeypatch.setattr(
            core, "evaluate_commitment",
            lambda **kwargs: CommitmentDecision(
                action="commit", target_unit_id=turbine.config.asset_id,
                reason="PROPOSED_HERE: force a core proposal in a one-tick fixture",
                blocked_by=None,
            ),
        )
        ctx.step()
    else:
        turbine.config.hot_standby = True
        core._release_hot_standby_for_contingency(
            ctx.sim_state,
            SimpleNamespace(state=ContingencyState.CANNOT_CARRY, shed_required_mw=0.0),
            sim_time=TIME_S,
            dt_seconds=ctx.sim_state._commit_cfg.contingency_release_confirm_s,
        )
    assert turbine.state == TurbineState.STARTING
    event, = _starts(ctx.turbine_commitment_controller)
    assert event.source == path
    _stage(ctx)
    assert len(_starts(ctx.turbine_commitment_controller)) == turbine._start_count == 1


def test_tc_isl_07f_restarts_reconcile_before_each_tick_observer():
    ctx, turbine = _context()
    turbine.config.hot_standby = True
    core._release_hot_standby_for_contingency(
        ctx.sim_state,
        SimpleNamespace(state=ContingencyState.CANNOT_CARRY, shed_required_mw=0.0),
        sim_time=TIME_S,
        dt_seconds=ctx.sim_state._commit_cfg.contingency_release_confirm_s,
    )
    _observe_tick(ctx, TIME_S, 1)
    # PROPOSED_HERE: reset fixture state between episodes without changing the
    # production start counters or charging any synthetic start fuel.
    for ordinal in range(2, 7):
        turbine.state = TurbineState.OFFLINE
        turbine._breaker_closed = False
        ctx.sim_state._pending_start.clear_on_synchronised(turbine.config.asset_id)
        time = TIME_S + ordinal
        _stage(ctx, time=time)
        _observe_tick(ctx, time, ordinal)
        assert ctx.turbine_commitment_controller.start_counts[turbine.config.asset_id] == ordinal
        assert turbine._start_count == ordinal
        assert not ctx.turbine_commitment_controller.hard_violation_reasons
    assert len(_starts(ctx.turbine_commitment_controller)) == 6
    assert sum(e.source == "predicted_step_staging" for e in _starts(
        ctx.turbine_commitment_controller,
    )) == 5


@pytest.mark.parametrize("delta", [DELTA_MW, 0.0, -DELTA_MW])
@pytest.mark.parametrize("standalone", [False, True])
def test_tc_isl_07g_no_sink_or_observer_changes_physics_or_nonpositive_staging(
    delta, standalone,
):
    observed, observed_unit = _context()
    disabled, disabled_unit = _context(mode="disabled")
    control, control_unit = _context()
    control.sim_state.arbitrator.successful_start_observer = None
    if standalone:
        state = disabled.sim_state
        state.arbitrator = DispatchArbitrator(
            state.turbines, state.bess_units, state.site,
            state.arbitrator.fuel_cell_units, state.diesel_units,
        )
    results = [_stage(ctx, delta=delta) for ctx in (observed, disabled, control)]
    assert results[0] == results[1] == results[2]
    units = [observed_unit, disabled_unit, control_unit]
    for unit in units:
        assert unit.state == TurbineState.STARTING
        assert unit._start_count == 1
    assert vars(units[0]) == vars(units[1]) == vars(units[2])
    assert len(_starts(observed.turbine_commitment_controller)) == 1
    assert disabled.turbine_commitment_controller is None
    assert not _starts(control.turbine_commitment_controller)
    if standalone:
        assert disabled.sim_state.arbitrator.successful_start_observer is None
        assert disabled.sim_state.arbitrator.pending_start is None
