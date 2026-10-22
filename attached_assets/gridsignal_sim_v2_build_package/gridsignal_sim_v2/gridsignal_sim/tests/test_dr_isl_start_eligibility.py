"""DR D2 / IMPL-ISL-5, TC-ISL-06: one unchanged turbine start interlock."""
import ast
from dataclasses import replace
import inspect
import logging
import textwrap
from types import SimpleNamespace

from core.asset_modules import TurbineModule
from core.commitment import (
    CommitmentConfig, PendingStartRegister, SustainedCondition, evaluate_commitment,
)
from core.dispatch import DispatchArbitrator
from core.models import TurbineConfig, TurbineState
from core.simulation_core import (
    _log_start_ineligibility_episode, _offline_turbines_by_thermal_priority,
    _releasable_hot_standby_turbines,
)
from runtime.run_manager import RunContext
from runtime.turbine_commitment import ForecastDrivenTurbineController


def _calls(fn):
    return {
        node.func.attr for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(fn))))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def _unit(name, stopped=False):
    # PROPOSED_HERE: synthetic fixture timestamps straddle the existing 900 s
    # minimum-down interlock; these are not new operational settings.
    unit = TurbineModule(TurbineConfig(
        asset_id=name, min_down_enabled=True, t_min_down_s=900.0,
    ))
    if stopped:
        unit._stop_time_s = 0.0
    return unit


def _decision(units, time):
    roster = _offline_turbines_by_thermal_priority(units, time, include_blocked=True)
    return evaluate_commitment(
        on_bus=[], offline=[u.unit_availability(time) for u in roster],
        p_demand_mw=20.0, pending=PendingStartRegister(),
        commit_cond=SustainedCondition(), decommit_cond=SustainedCondition(),
        cfg=replace(CommitmentConfig.from_catalogue(), inter_start_settle_s=0.0),
        dt_s=5.0, sim_time=time,
    )


def test_tc_isl_06a_single_guard_call_graph():
    for fn in (TurbineModule.command_start, TurbineModule.unit_availability,
               _offline_turbines_by_thermal_priority, _releasable_hot_standby_turbines):
        assert "start_eligibility" in _calls(fn)
    # Inspect the entire arbitrator: staging must call the same predicate.
    assert "start_eligibility" in _calls(DispatchArbitrator)
    assert "start_eligibility" in _calls(ForecastDrivenTurbineController._candidate_start)
    assert "start_eligibility" in _calls(ForecastDrivenTurbineController.adjudicate_core_proposal)
    assert "start_eligibility" in _calls(RunContext.drain_operator_commands)
    source = inspect.getsource(TurbineModule.command_start)
    assert "self.config.hot_standby" not in source
    assert "elapsed < self.config.t_min_down_s" not in source
    assert "self.state != TurbineState.OFFLINE" not in source
    assert "unit.start_eligible" in inspect.getsource(evaluate_commitment)
    assert "target_unit_id=offline[0]" not in inspect.getsource(evaluate_commitment)


def test_tc_isl_06b_skip_min_down_start_alternate():
    cooling, alternate = _unit("cooling", True), _unit("alternate")
    assert cooling.start_eligibility(100.0) == (False, "min_down")
    assert alternate.start_eligibility(100.0) == (True, "eligible")
    decision = _decision([cooling, alternate], 100.0)
    assert decision.action == "commit"
    assert decision.target_unit_id == "alternate"
    alternate.command_start(100.0)
    assert alternate.state == TurbineState.STARTING
    assert cooling.state == TurbineState.OFFLINE
    # The certified study's forecast selector must skip the same interlock.
    alternate.state = TurbineState.OFFLINE
    assert ForecastDrivenTurbineController._candidate_start(
        None, [cooling, alternate], 100.0,
    ) is alternate


def test_tc_isl_06c_no_eligible_one_log_per_episode(caplog):
    units = [_unit("one", True), _unit("two", True)]
    state = SimpleNamespace(_start_ineligible_episode_logged=False)
    with caplog.at_level(logging.INFO, logger="core.simulation_core"):
        for time in (100.0, 105.0, 110.0):
            decision = _decision(units, time)
            assert decision.action == "hold"
            assert decision.target_unit_id is None
            assert "one=min_down" in decision.blocked_by
            assert "two=min_down" in decision.blocked_by
            _log_start_ineligibility_episode(state, decision, time)
        logs = [r for r in caplog.records if "no eligible turbine:" in r.message]
        assert len(logs) == 1
        assert all(u.state == TurbineState.OFFLINE and u._start_count == 0 for u in units)
        # Clearing the blocked condition rearms the logger, not the guard.
        _log_start_ineligibility_episode(state, _decision(units, 900.0), 900.0)
        _log_start_ineligibility_episode(state, _decision(units, 100.0), 100.0)
        assert sum("no eligible turbine:" in r.message for r in caplog.records) == 2
        assert not any("silently dropped" in r.message for r in caplog.records)


def test_tc_isl_06_guard_boundaries_unchanged():
    unit = _unit("boundary", True)
    assert unit.start_eligibility(899.0) == (False, "min_down")
    assert unit.start_eligibility(900.0) == (True, "eligible")
    unit.config.min_down_enabled = False
    assert unit.start_eligibility(0.0) == (True, "eligible")
    unit.config.hot_standby = True
    unit.state = TurbineState.STARTING
    assert unit.start_eligibility(0.0) == (False, "hot_standby")
    unit.config.hot_standby = False
    assert unit.start_eligibility(0.0) == (False, "state")
