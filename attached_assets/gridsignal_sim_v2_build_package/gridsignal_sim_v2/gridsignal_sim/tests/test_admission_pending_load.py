import json
from pathlib import Path
from unittest.mock import patch

import pytest

from api.schemas import ScenarioSpec
from core.kube_demand import (
    KubeDemandAgent,
    KubeGridState,
    _FacilityAdmissionReservation,
)
from runtime.scenario_factory import build_run_context_from_spec


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
QUEUE_SCENARIO_PATH = (
    PACKAGE_ROOT / "config" / "scenarios" / "proxim8-5mw-24h-queue.json"
)
PINNED_CLOCK = 1792454400.0
TICK_SECONDS = 5


def test_consecutive_admission_bursts_reserve_unrealized_load() -> None:
    raw = json.loads(QUEUE_SCENARIO_PATH.read_text(encoding="utf-8"))
    raw["name"] = "admission-pending-unit"
    raw["end_sim_time"] = 600
    raw["workload_events"] = []
    raw["non_gpu_load_profile_mw"] = []
    k8s = next(
        cluster
        for cluster in raw["kube_clusters"]
        if cluster["scheduler_type"] == "K8S"
    )
    k8s["workload_share"] = 1.0
    k8s["scheduled_arrivals"] = [
        {
            "job_id": f"pending-load-{int(arrival_s)}-{index:03d}",
            "arrival_time_s": arrival_s,
            "duration_s": 300.0,
            "node_count": 2,
            "hardware_profile_id": "hopper_8gpu_air",
        }
        for arrival_s, count in ((5.0, 160), (10.0, 20))
        for index in range(count)
    ]
    raw["kube_clusters"] = [k8s]
    spec = ScenarioSpec.model_validate(raw)

    with patch(
        "runtime.run_manager._time_module.time",
        return_value=PINNED_CLOCK,
    ):
        ctx = build_run_context_from_spec(
            "admission-pending-unit",
            spec.model_dump(mode="json"),
            run_seed=1729,
        )
        ticks = [
            ctx.step()
            for _ in range(int(spec.end_sim_time // TICK_SECONDS))
        ]

    peak_demand_mw = max(tick.p_demand_mw for tick in ticks)
    peak_grid_import_mw = max(
        max(0.0, -tick.grid_exchange_mw) for tick in ticks
    )
    total_unserved_mwh = sum(
        tick.p_unserved_mw * TICK_SECONDS / 3600.0 for tick in ticks
    )

    assert peak_demand_mw <= 5.0 + 1e-6
    assert peak_grid_import_mw <= 5.0 + 1e-6
    assert total_unserved_mwh == 0.0
    assert any(
        tick.kube_metrics
        and tick.kube_metrics.queued_jobs > 0
        for tick in ticks
    )
    assert all(
        tick.requested_demand_mw is None
        or tick.requested_demand_mw + 1e-6 >= tick.p_demand_mw
        for tick in ticks
    )
    assert all(
        abs(tick.requested_demand_mw - tick.p_demand_mw) <= 1e-9
        for tick in ticks
        if not (
            tick.kube_metrics
            and any(
                "-gridcap-retry-" in job.event_id
                for job in tick.kube_metrics.pending_jobs
            )
        )
    )


def _configured_agent() -> KubeDemandAgent:
    raw = json.loads(QUEUE_SCENARIO_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    with patch(
        "runtime.run_manager._time_module.time",
        return_value=PINNED_CLOCK,
    ):
        ctx = build_run_context_from_spec(
            "admission-pending-unit",
            spec.model_dump(mode="json"),
            run_seed=1729,
        )
    return ctx.sim_state.kube_agents[0]


def _reservation(
    *,
    cohort_key: str,
    aggregate_job_id: str,
    ends_at: float = 300.0,
) -> _FacilityAdmissionReservation:
    return _FacilityAdmissionReservation(
        event_id="admitted-job",
        node_count=1,
        projected_increment_mw=0.015912,
        admitted_at=0.0,
        ends_at=ends_at,
        aggregate_job_id=aggregate_job_id,
        cohort_key=cohort_key,
        cohort_node_count=1,
        remaining_mw=0.015912,
    )


def test_tc_adm_5_scale_down_releases_gpu_and_settled_cooling_reservations() -> None:
    agent = _configured_agent()
    aggregate_job_id = "kube-admission-proxim8-k8s"
    removed_cohort_key = f"{aggregate_job_id}-cohort-2"
    reservation = _reservation(
        cohort_key=removed_cohort_key,
        aggregate_job_id=aggregate_job_id,
    )
    agent._facility_admission_reservations = [reservation]

    # Aggregate scale-down removed this cohort from the GPU draw map. The
    # remaining reservation is only the same future-cooling-minus-current tail.
    probes = agent.facility_admission_cooling_probe_cohort_keys(
        305.0, {aggregate_job_id: 0.015}
    )
    assert probes == {removed_cohort_key}
    agent.update_facility_admission_realization(
        compute_by_job_mw={aggregate_job_id: 0.015},
        cooling_by_job_mw={removed_cohort_key: 0.002},
        future_cooling_peak_by_job_mw={removed_cohort_key: 0.0035},
        sim_time=305.0,
        cooling_retention_s=190.0,
    )
    assert reservation.remaining_mw == pytest.approx(0.0015)
    assert agent.facility_admission_unrealized_mw == pytest.approx(0.0015)

    # Once the engine's retained cooling envelope has settled, no reservation
    # survives, even though aggregate scale-down removed the GPU cohort early.
    agent.update_facility_admission_realization(
        compute_by_job_mw={aggregate_job_id: 0.015},
        cooling_by_job_mw={},
        future_cooling_peak_by_job_mw={removed_cohort_key: 0.0},
        sim_time=496.0,
        cooling_retention_s=190.0,
    )
    assert agent.facility_admission_unrealized_mw == 0.0
    assert agent._facility_admission_reservations == []


def test_tc_adm_5_aggregate_scale_down_does_not_strand_live_job_reservation() -> None:
    raw = json.loads(QUEUE_SCENARIO_PATH.read_text(encoding="utf-8"))
    raw["end_sim_time"] = 600
    raw["workload_events"] = []
    raw["non_gpu_load_profile_mw"] = []
    k8s = next(
        cluster
        for cluster in raw["kube_clusters"]
        if cluster["scheduler_type"] == "K8S"
    )
    k8s["workload_share"] = 1.0
    k8s["scheduled_arrivals"] = [
        {
            "job_id": "scale-down-first",
            "arrival_time_s": 5.0,
            "duration_s": 40.0,
            "node_count": 1,
            "hardware_profile_id": "hopper_8gpu_air",
        },
        {
            "job_id": "scale-down-still-live",
            "arrival_time_s": 10.0,
            "duration_s": 300.0,
            "node_count": 1,
            "hardware_profile_id": "hopper_8gpu_air",
        },
    ]
    raw["kube_clusters"] = [k8s]
    spec = ScenarioSpec.model_validate(raw)

    with patch(
        "runtime.run_manager._time_module.time",
        return_value=PINNED_CLOCK,
    ):
        ctx = build_run_context_from_spec(
            "admission-scale-down-unit",
            spec.model_dump(mode="json"),
            run_seed=1729,
        )
        agent = ctx.sim_state.kube_agents[0]
        aggregate_nodes_after_thermal_settle = 0
        second_reservation_after_thermal_settle = True
        for _ in range(int(spec.end_sim_time // TICK_SECONDS)):
            tick = ctx.step()
            if tick.sim_time_seconds >= 250.0:
                aggregate_nodes_after_thermal_settle = sum(
                    ctx.sim_state.gpu_modules[0]._node_counts.values()
                )
                second_reservation_after_thermal_settle = any(
                    reservation.event_id.startswith("scale-down-still-live")
                    for reservation in agent._facility_admission_reservations
                )
                break

    assert aggregate_nodes_after_thermal_settle == 1
    assert not second_reservation_after_thermal_settle


def test_tc_adm_6_held_admission_unblocks_on_first_fitting_headroom() -> None:
    agent = _configured_agent()
    candidate = type("Candidate", (), {"node_count": 1})()
    increment_mw = agent._facility_admission_increment_mw(candidate)
    grid_state = KubeGridState(
        p_dispatch_required_mw=0.0,
        bess_soc_fraction=0.0,
        turbine_headroom_mw=0.0,
        bess_headroom_mw=0.0,
        facility_admission_headroom_mw=increment_mw - 1e-6,
    )
    assert agent._facility_cap_blocks(candidate, grid_state)

    grid_state.facility_admission_headroom_mw = increment_mw
    assert not agent._facility_cap_blocks(candidate, grid_state)


def test_tc_adm_7_realized_draw_is_not_counted_again_as_pending() -> None:
    agent = _configured_agent()
    aggregate_job_id = "kube-admission-proxim8-k8s"
    cohort_key = f"{aggregate_job_id}-cohort-1"
    reservation = _reservation(
        cohort_key=cohort_key,
        aggregate_job_id=aggregate_job_id,
        ends_at=600.0,
    )
    agent._facility_admission_reservations = [reservation]

    # 0.012 MW is already represented by previous-tick demand; only the
    # unrealized remainder belongs in the pending reservation sum.
    agent.update_facility_admission_realization(
        compute_by_job_mw={cohort_key: 0.010},
        cooling_by_job_mw={cohort_key: 0.002},
        future_cooling_peak_by_job_mw={},
        sim_time=5.0,
        cooling_retention_s=190.0,
    )
    assert reservation.remaining_mw == pytest.approx(0.003912)
    state = KubeGridState(
        p_dispatch_required_mw=0.0,
        bess_soc_fraction=0.0,
        turbine_headroom_mw=0.0,
        bess_headroom_mw=0.0,
        facility_admission_headroom_mw=1.0 - 0.012,
        facility_admission_pending_mw=agent.facility_admission_unrealized_mw,
    )
    assert state.remaining_facility_admission_headroom_mw() == pytest.approx(
        1.0 - 0.012 - 0.003912
    )
