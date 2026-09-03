from dataclasses import replace
from types import SimpleNamespace

import asyncio

from core.models import ConfidenceBand, TickResult
from runtime.advisory_gate import AdvisoryGate
from runtime.run_manager import _attach_reserve_alert_proposal, _tick_result_to_dict
from api.routes import advisory


def _alert_tick() -> TickResult:
    return TickResult(
        run_id="run-reserve-test",
        tick_index=1,
        sim_time_seconds=5.0,
        p_compute_demand_mw=10.0,
        p_cooling_demand_mw=1.0,
        p_demand_mw=11.0,
        net_demand_mw=11.0,
        turbine_output_mw=0.0,
        bess_output_mw=5.0,
        bess_soc_fraction=0.8,
        confidence=ConfidenceBand(
            point_estimate_mw=11.0,
            plus_minus_fraction=0.05,
            tags=frozenset(),
        ),
        insufficient_reserve_alert=True,
        peak_shortfall_mw=4.0,
        checkpoint_states={},
    )


def _request(manager):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(run_manager=manager)))


def test_alert_firing_creates_retrievable_generation_proposal_without_physics_mutation():
    original = _alert_tick()
    ctx = SimpleNamespace(registry=None, reserve_alert_proposal_ids={})
    enriched = _attach_reserve_alert_proposal(ctx, original)

    assert enriched.insufficient_reserve_proposal_id
    assert enriched.insufficient_reserve_alert is True
    assert enriched.peak_shortfall_mw == original.peak_shortfall_mw
    proposal = ctx.registry.get_gate().get(enriched.insufficient_reserve_proposal_id)
    assert proposal is not None
    assert proposal.kind == "turbine_ramp_rate"
    assert proposal.originating_agent == "generation"
    assert proposal.state.value == "pending"
    assert _tick_result_to_dict(enriched)["insufficient_reserve_proposal_id"] == proposal.proposal_id


def test_approve_is_visible_as_accepted_via_independent_registry_get():
    ctx = SimpleNamespace(registry=None, reserve_alert_proposal_ids={})
    enriched = _attach_reserve_alert_proposal(ctx, _alert_tick())
    proposal_id = enriched.insufficient_reserve_proposal_id
    manager = SimpleNamespace(
        _contexts={},
        _registries={"run-reserve-test": ctx.registry},
        get_registry=lambda run_id: ctx.registry if run_id == "run-reserve-test" else None,
        get_context=lambda _run_id: None,
        get_completed=lambda _run_id: None,
    )
    asyncio.run(advisory.accept_proposal(
        proposal_id,
        advisory.AcceptBody(reviewer_id="operator@example.com"),
        _request(manager),
    ))
    listed = asyncio.run(advisory.list_proposals("run-reserve-test", _request(manager)))
    assert listed.proposals[0].state == "accepted"
    assert listed.proposals[0].reviewer_id == "operator@example.com"
    assert listed.proposals[0].accepted_at_sim_time == 0.0


def test_reject_is_visible_as_rejected_via_independent_registry_get():
    ctx = SimpleNamespace(registry=None, reserve_alert_proposal_ids={})
    enriched = _attach_reserve_alert_proposal(ctx, _alert_tick())
    proposal_id = enriched.insufficient_reserve_proposal_id
    manager = SimpleNamespace(
        _contexts={},
        _registries={"run-reserve-test": ctx.registry},
        get_registry=lambda run_id: ctx.registry if run_id == "run-reserve-test" else None,
        get_context=lambda _run_id: None,
        get_completed=lambda _run_id: None,
    )
    asyncio.run(advisory.reject_proposal(
        proposal_id,
        advisory.RejectBody(
            reason="operator rejected",
            reviewer_id="operator@example.com",
        ),
        _request(manager),
    ))
    listed = asyncio.run(advisory.list_proposals("run-reserve-test", _request(manager)))
    assert listed.proposals[0].state == "rejected"
    assert listed.proposals[0].reviewer_id == "operator@example.com"
    assert listed.proposals[0].rejected_at_sim_time == 0.0


def test_review_enrichment_does_not_change_dispatch_fields():
    original = _alert_tick()
    ctx = SimpleNamespace(registry=None, reserve_alert_proposal_ids={})
    enriched = _attach_reserve_alert_proposal(ctx, original)
    assert replace(enriched, insufficient_reserve_proposal_id=None) == original


def test_unactioned_alert_proposal_remains_pending():
    ctx = SimpleNamespace(registry=None, reserve_alert_proposal_ids={})
    enriched = _attach_reserve_alert_proposal(ctx, _alert_tick())
    proposal = ctx.registry.get_gate().get(enriched.insufficient_reserve_proposal_id)
    assert proposal.state.value == "pending"