"""End-to-end Addendum G-1 reference acceptance regression."""
from __future__ import annotations

import json

import pytest

from api.routes.scenarios import build_seeded_store
from runtime.scenario_factory import build_run_context_from_spec
from runtime.verdict import EvalRow, evaluate_verdict


SCENARIO_ID = "scenario-fc100-islanded-v2"


def test_fc100_reference_is_registered_and_exercises_block_deficit():
    record = build_seeded_store().get(SCENARIO_ID)
    assert record is not None
    spec = json.loads(record.spec_json)
    unit = spec["fuel_cell_units"][0]
    assert (unit["block_count"], unit["block_rated_mw"]) == (246, .325)
    assert (unit["initial_running_blocks"], unit["initial_hot_standby_blocks"]) == (62, 92)

    context = build_run_context_from_spec("fc100-acceptance", spec, playback_speed=0)
    ticks = [context.step() for _ in range(int(spec["end_sim_time"] / 5))]

    # This is a zero-lead scenario: hot standby receives no fast credit and
    # requires its full configured transition before reaching the plateau.
    assert all(t.dt_lead_next_s == 0 for t in ticks)
    # available_fast reports physical hot readiness, not credited reserve;
    # a zero event window must therefore produce no declining/fast credit.
    assert not any(t.fuel_cell_declining_reserve_alert for t in ticks)
    assert max(
        t.fuel_cell_achieved_output_mw
        for t in ticks if 60 < t.sim_time_seconds < 120
    ) < 50.05
    assert next(
        t.sim_time_seconds for t in ticks
        if t.fuel_cell_achieved_output_mw == pytest.approx(50.05)
    ) == pytest.approx(125)

    # Cold/warming blocks make an explicit zero contingency contribution.
    plateau = [t for t in ticks if 125 <= t.sim_time_seconds <= 1260]
    assert max(t.fuel_cell_achieved_output_mw for t in plateau) == pytest.approx(50.05)
    assert any(t.fuel_cell_cold_blocks or t.fuel_cell_warming_blocks for t in plateau)
    # RUNNING blocks credit only their upward margin; already-achieved output
    # is generation, not reserve.
    assert all(t.fuel_cell_available_now_mw == pytest.approx(
        max(0.0, t.fuel_cell_running_blocks * .325 - t.fuel_cell_achieved_output_mw)
    ) for t in plateau)
    assert all(
        t.fuel_cell_cold_warming_contingency_contribution_mw == 0
        for t in ticks
    )
    # This scenario has no scheduler lead.  Its hot blocks need 60 s, so none
    # can be manufactured into fast/declining reserve by an evaluation tick.
    assert not any(t.fuel_cell_declining_reserve_alert for t in ticks)
    assert any(t.fuel_cell_persistent_reserve_alert for t in plateau)
    for tick in ticks:
        for alert in (
            tick.fuel_cell_declining_reserve_alert,
            tick.fuel_cell_persistent_reserve_alert,
        ):
            if alert is not None:
                assert alert["event_fast_window_s"] == pytest.approx(
                    tick.dt_lead_next_s
                )
    assert min(t.bess_soc_fraction for t in ticks) < .95
    assert max(t.diesel_output_mw for t in ticks) == 0
    # Diesel is advisory-only and must not appear in firm fuel-cell reserve.
    assert all(
        not alert or "diesel" not in alert
        for tick in ticks
        for alert in (
            tick.fuel_cell_declining_reserve_alert,
            tick.fuel_cell_persistent_reserve_alert,
        )
    )
    proposals = context.registry.get_gate().all_proposals()
    assert proposals and all(proposal.requires_confirmation for proposal in proposals)

    rows = [
        EvalRow(t.tick_index, t.p_demand_mw, t.bess_soc_fraction,
                t.insufficient_reserve_alert, t.fuel_cell_commanded_output_mw,
                t.fuel_cell_achieved_output_mw, t.fuel_cell_available_now_mw,
                t.fuel_cell_running_blocks, t.fuel_cell_cold_blocks,
                t.fuel_cell_warming_blocks, t.sim_time_seconds,
                t.fuel_cell_cold_warming_contingency_contribution_mw)
        for t in ticks
    ]
    verdict = evaluate_verdict(spec["assertions"], rows, dropped_ticks=0)
    assert verdict.overall == "PASS"