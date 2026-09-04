"""End-to-end Addendum G-1 reference acceptance regression."""
from __future__ import annotations

import json

import pytest

from api.routes.scenarios import build_seeded_store
from api.schemas import ScenarioSpec
from runtime.scenario_factory import build_run_context_from_spec
from runtime.verdict import EvalRow, evaluate_verdict


SCENARIO_ID = "scenario-fc100-islanded-v2"
ZERO_HOT_SCENARIO_ID = "scenario-fc100-islanded-zero-hot-v2"


def test_fc100_reference_is_registered_and_exercises_all_hot_standby_ramp():
    record = build_seeded_store().get(SCENARIO_ID)
    assert record is not None
    spec = json.loads(record.spec_json)
    assert spec["fuel_cell_enabled"] is True
    unit = spec["fuel_cell_units"][0]
    assert (unit["block_count"], unit["block_rated_mw"]) == (246, .325)
    assert (unit["initial_running_blocks"], unit["initial_hot_standby_blocks"]) == (62, 184)
    # The total-site fixture explicitly includes the cooling required by the
    # GPU load instead of treating cooling power as free.
    assert spec["alpha_max"] == pytest.approx(.2)

    context = build_run_context_from_spec("fc100-acceptance", spec, playback_speed=0)
    ticks = [context.step() for _ in range(int(spec["end_sim_time"] / 5))]

    # The peak STARTING event is submitted at t=30 and its 30-second GPU ramp
    # lands the 66.67 MW compute load at t=60. Cooling follows after its
    # thermal delay and the total site settles at 80 MW. The settled baseline
    # cannot bank unused start-rate credit for the peak.
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
        list(range(60, 220, 5))
    )
    first_declining = peak_declining[0].fuel_cell_declining_reserve_alert
    assert first_declining["event_fast_window_s"] == pytest.approx(0)
    # All non-running blocks are HOT, so the initial gap is fully closable.
    assert first_declining["shortfall_mw"] == pytest.approx(38.3922, abs=.325)
    assert first_declining["closing_mw"] == pytest.approx(38.3922, abs=.325)
    assert first_declining["remaining_mw"] == pytest.approx(0.0, abs=.325)
    assert first_declining["eventual_hot_closure_mw"] == pytest.approx(159 * .325)
    # Decommit is deliberately disabled for this fixed 20→80 MW exercise:
    # all initially running blocks remain online and every hot block commits.
    settled_baseline = [t for t in ticks if 5 <= t.sim_time_seconds <= 30]
    assert all(t.fuel_cell_running_blocks == 62 for t in settled_baseline)
    assert all(t.bess_output_mw == pytest.approx(0.0, abs=1e-9) for t in settled_baseline)
    assert not any(t.fuel_cell_declining_reserve_alert for t in settled_baseline)
    assert not any(t.fuel_cell_persistent_reserve_alert for t in settled_baseline)
    assert next(
        t.fuel_cell_running_blocks for t in ticks if t.sim_time_seconds == 60
    ) == 87
    assert next(
        t.fuel_cell_achieved_output_mw for t in ticks if t.sim_time_seconds == 60
    ) == pytest.approx(28.275)
    assert next(
        t.sim_time_seconds for t in ticks
        if t.fuel_cell_achieved_output_mw >= 50.0
    ) == pytest.approx(130)
    assert not next(
        t for t in ticks if t.sim_time_seconds == 220
    ).fuel_cell_declining_reserve_alert

    # Every non-running block began hot and all 246 blocks eventually run.
    plateau = [t for t in ticks if 195 <= t.sim_time_seconds <= 1260]
    assert max(t.fuel_cell_achieved_output_mw for t in plateau) == pytest.approx(79.95)
    assert all(t.p_cooling_demand_mw > 0 for t in plateau)
    assert all(t.bess_bridging_seconds > 0 for t in plateau)
    settled_tick = next(t for t in ticks if t.sim_time_seconds == 1260)
    assert settled_tick.p_compute_demand_mw == pytest.approx(66.6672, abs=.01)
    assert settled_tick.p_cooling_demand_mw == pytest.approx(13.3334, abs=.01)
    assert settled_tick.p_demand_mw == pytest.approx(80.0, abs=.01)
    assert all(not t.fuel_cell_cold_blocks and not t.fuel_cell_warming_blocks for t in plateau)
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
    assert not any(t.fuel_cell_persistent_reserve_alert for t in plateau)
    physical_peak = [
        t for t in ticks if 60 <= t.sim_time_seconds < 1260
    ]
    assert not any(t.fuel_cell_persistent_reserve_alert for t in physical_peak)
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
    assert ticks[-1].bess_soc_fraction == pytest.approx(.924, abs=.01)
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
    assert not any(proposal.kind == "pre_staging" for proposal in proposals)

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
    assert spec["fuel_cell_enabled"] is True
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
    settled_tick = next(t for t in ticks if t.sim_time_seconds == 1260)
    assert settled_tick.p_cooling_demand_mw == pytest.approx(13.3334, abs=.01)
    assert settled_tick.p_demand_mw == pytest.approx(80.0, abs=.01)

    # With no initially-hot blocks, the cold-start horizon prevents the array
    # from materially increasing beyond its 62 running blocks (20.15 MW).
    assert max(t.fuel_cell_achieved_output_mw for t in peak) == pytest.approx(20.15)
    # The physical BESS path retains its 1 MW grid-forming anchor reserve.
    assert max(t.bess_output_mw for t in peak) == pytest.approx(59.0)
    assert all(t.bess_output_mw <= 59.0 + 1e-9 for t in peak)
    assert all(
        t.bess_bridging_seconds == pytest.approx(0.0)
        for t in peak if t.sim_time_seconds >= 200
    )
    assert not any(t.fuel_cell_declining_reserve_alert for t in peak)
    assert all(
        t.fuel_cell_persistent_reserve_alert
        and t.fuel_cell_persistent_reserve_alert["persistent_shortfall_mw"]
        == pytest.approx(59.9, abs=.325)
        for t in peak if t.sim_time_seconds >= 200
    )

    # Residual site demand is explicitly shed/unserved, not fabricated supply.
    constrained = [t for t in peak if t.p_unserved_mw and t.p_unserved_mw > 0]
    assert constrained
    assert all(t.p_imbalance_mw == pytest.approx(0.0, abs=1e-9) for t in constrained)
    assert all(
        t.p_generation_mw + t.p_unserved_mw == pytest.approx(t.p_demand_mw)
        for t in constrained
    )