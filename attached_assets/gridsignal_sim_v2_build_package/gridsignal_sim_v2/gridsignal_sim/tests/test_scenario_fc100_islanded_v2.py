"""End-to-end Addendum G-1 reference acceptance regression."""
from __future__ import annotations

import json

import pytest

from api.routes.scenarios import build_seeded_store
from runtime.scenario_factory import build_run_context_from_spec
from runtime.verdict import EvalRow, evaluate_verdict


SCENARIO_ID = "scenario-fc100-islanded-v2"
ZERO_HOT_SCENARIO_ID = "scenario-fc100-islanded-zero-hot-v2"


def test_fc100_reference_is_registered_and_exercises_block_deficit():
    record = build_seeded_store().get(SCENARIO_ID)
    assert record is not None
    spec = json.loads(record.spec_json)
    unit = spec["fuel_cell_units"][0]
    assert (unit["block_count"], unit["block_rated_mw"]) == (246, .325)
    assert (unit["initial_running_blocks"], unit["initial_hot_standby_blocks"]) == (62, 92)
    # This is a total-site-load fixture, not a thermal-response fixture.
    assert spec["alpha_max"] == 0

    context = build_run_context_from_spec("fc100-acceptance", spec, playback_speed=0)
    ticks = [context.step() for _ in range(int(spec["end_sim_time"] / 5))]

    # The peak STARTING event is submitted at t=30 and its 30-second GPU ramp
    # lands the 80 MW load at t=60.  The settled baseline cannot bank unused
    # start-rate credit for the peak.
    peak_event = next(e for e in spec["workload_events"] if e["event_id"] == "fc-peak-start")
    base_event = next(e for e in spec["workload_events"] if e["event_id"] == "fc-base-start")
    assert base_event["event_type"] == "running"
    assert (peak_event["timestamp"], spec["dt_lead_seconds"]) == (30, 30)
    assert any(
        30 < t.sim_time_seconds < 60 and t.dt_lead_next_s > 0
        for t in ticks
    )
    peak_declining = [
        t for t in ticks
        if t.fuel_cell_declining_reserve_alert
        and t.sim_time_seconds >= 30
    ]
    assert peak_declining
    assert peak_declining[0].sim_time_seconds == pytest.approx(60)
    assert [t.sim_time_seconds for t in peak_declining] == pytest.approx(
        list(range(60, 125, 5))
    )
    first_declining = peak_declining[0].fuel_cell_declining_reserve_alert
    assert first_declining["event_fast_window_s"] == pytest.approx(0)
    # At the physical 80 MW load arrival, 62 HOT blocks remain.  This
    # closable 20.15 MW is separate from the irreducible ~29.95 MW deficit.
    assert first_declining["shortfall_mw"] == pytest.approx(50.0986, abs=.325)
    assert first_declining["closing_mw"] == pytest.approx(62 * .325)
    assert first_declining["remaining_mw"] == pytest.approx(29.95, abs=.325)
    assert first_declining["eventual_hot_closure_mw"] == pytest.approx(62 * .325)
    # Decommit is deliberately disabled for this fixed 20→80 MW exercise:
    # all initially running blocks remain online and every hot block commits.
    settled_baseline = [t for t in ticks if 5 <= t.sim_time_seconds <= 30]
    assert all(t.fuel_cell_running_blocks == 62 for t in settled_baseline)
    assert all(t.bess_output_mw == pytest.approx(0.0, abs=1e-9) for t in settled_baseline)
    assert not any(t.fuel_cell_declining_reserve_alert for t in settled_baseline)
    assert not any(t.fuel_cell_persistent_reserve_alert for t in settled_baseline)
    assert next(
        t.fuel_cell_running_blocks for t in ticks if t.sim_time_seconds == 60
    ) == 92
    assert next(
        t.fuel_cell_achieved_output_mw for t in ticks if t.sim_time_seconds == 60
    ) == pytest.approx(29.9)
    assert next(
        t.sim_time_seconds for t in ticks
        if t.fuel_cell_achieved_output_mw == pytest.approx(50.05)
    ) == pytest.approx(125)
    assert not next(
        t for t in ticks if t.sim_time_seconds == 125
    ).fuel_cell_declining_reserve_alert

    # Cold/warming blocks make an explicit zero contingency contribution.
    plateau = [t for t in ticks if 125 <= t.sim_time_seconds <= 1260]
    assert max(t.fuel_cell_achieved_output_mw for t in plateau) == pytest.approx(50.05)
    assert all(
        t.fuel_cell_commanded_output_mw - t.fuel_cell_achieved_output_mw
        == pytest.approx(29.95, abs=.325)
        for t in plateau
    )
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
    assert any(t.fuel_cell_declining_reserve_alert for t in ticks)
    assert any(t.fuel_cell_persistent_reserve_alert for t in plateau)
    physical_peak = [
        t for t in ticks if 60 <= t.sim_time_seconds < 1260
    ]
    assert all(t.fuel_cell_persistent_reserve_alert for t in physical_peak)
    assert all(
        t.fuel_cell_persistent_reserve_alert["persistent_shortfall_mw"]
        == pytest.approx(29.95, abs=.325)
        for t in physical_peak
    )
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
    assert ticks[-1].bess_soc_fraction == pytest.approx(.691, abs=.01)
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
                t.fuel_cell_cold_warming_contingency_contribution_mw,
                t.fuel_cell_declining_reserve_alert)
        for t in ticks
    ]
    verdict = evaluate_verdict(spec["assertions"], rows, dropped_ticks=0)
    assert verdict.overall == "PASS"


def test_fc100_zero_hot_variant_exposes_physical_bess_ceiling_and_unserved_load():
    record = build_seeded_store().get(ZERO_HOT_SCENARIO_ID)
    assert record is not None
    spec = json.loads(record.spec_json)
    assert spec["fuel_cell_units"][0]["initial_hot_standby_blocks"] == 0
    assert next(
        e["event_type"] for e in spec["workload_events"]
        if e["event_id"] == "fc-base-start"
    ) == "running"

    context = build_run_context_from_spec("fc100-zero-hot-acceptance", spec, playback_speed=0)
    ticks = [context.step() for _ in range(int(spec["end_sim_time"] / 5))]
    peak = [t for t in ticks if 60 <= t.sim_time_seconds < 1260]
    baseline = [t for t in ticks if 5 <= t.sim_time_seconds <= 30]
    assert all(t.bess_output_mw == pytest.approx(0.0, abs=1e-9) for t in baseline)
    assert not any(t.fuel_cell_declining_reserve_alert for t in baseline)
    assert not any(t.fuel_cell_persistent_reserve_alert for t in baseline)

    # With no initially-hot blocks, the cold-start horizon prevents the array
    # from materially increasing beyond its 62 running blocks (20.15 MW).
    assert max(t.fuel_cell_achieved_output_mw for t in peak) == pytest.approx(20.15)
    # The physical BESS path retains its 1 MW grid-forming anchor reserve.
    assert max(t.bess_output_mw for t in peak) == pytest.approx(59.0)
    assert all(t.bess_output_mw <= 59.0 + 1e-9 for t in peak)
    assert not any(t.fuel_cell_declining_reserve_alert for t in peak)
    assert all(
        t.fuel_cell_persistent_reserve_alert
        and t.fuel_cell_persistent_reserve_alert["persistent_shortfall_mw"]
        == pytest.approx(59.9, abs=.325)
        for t in peak
    )

    # Residual site demand is explicitly shed/unserved, not fabricated supply.
    constrained = [t for t in peak if t.p_unserved_mw and t.p_unserved_mw > 0]
    assert constrained
    assert all(t.p_imbalance_mw == pytest.approx(0.0, abs=1e-9) for t in constrained)
    assert all(
        t.p_generation_mw + t.p_unserved_mw == pytest.approx(t.p_demand_mw)
        for t in constrained
    )