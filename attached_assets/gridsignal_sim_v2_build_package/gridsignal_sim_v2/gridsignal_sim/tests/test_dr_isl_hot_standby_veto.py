"""DR D2-a: TC-ISL-06e accepts the hot-standby core-proposal veto."""
from types import SimpleNamespace

from runtime.scenario_factory import build_run_context_from_spec
from tests.test_addendum_h_phase2a_commitment import _spec


def test_tc_isl_06e_hot_standby_core_proposal_is_vetoed():
    # Base 1345380 approved this proposal, then silently dropped command_start:
    # core/asset_modules.py:1069–1070; core/simulation_core.py:2383–2387.
    ctx = build_run_context_from_spec(
        "tc-isl-06e", _spec(mode="informed", spinning=1, hot=1).model_dump(),
    )
    target = ctx.sim_state.turbines[1]
    assert target.config.hot_standby is True
    assert target.start_eligibility(0.0) == (False, "hot_standby")
    assert ctx.turbine_commitment_controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=SimpleNamespace(
            action="commit", target_unit_id=target.config.asset_id,
            reason="measured reserve shortfall", floor_violated=True,
        ),
        sim_time_s=0.0, synchronized_capacity_mw=10.0,
        bess_soc_fraction=0.5,
    ) is False
    record = ctx.turbine_commitment_controller.log[-1]
    assert "hot_standby" in record.refusal_reason
    assert record.controller_approved is False
