"""Deterministic internal Slurm scheduler and run-loop tests."""

from __future__ import annotations

import pytest

from core.models import WorkloadEventType
from core.slurm_scheduler import (
    ImpossibleJobError,
    SlurmJobSpec,
    SlurmNode,
    SlurmSchedulerError,
    SlurmSchedulerEngine,
)
from runtime.scenario_factory import build_run_context_from_spec


def _job(job_id: str, **overrides: object) -> SlurmJobSpec:
    values = {
        "job_id": job_id,
        "arrival_time": 0.0,
        "duration": 5.0,
        "node_count": 1,
        "gpus_per_node": 8,
        "gpu_model": "h100",
        "partition": "gpu",
    }
    values.update(overrides)
    return SlurmJobSpec(**values)


def _engine(*, node_count: int = 1) -> SlurmSchedulerEngine:
    return SlurmSchedulerEngine(
        SlurmNode(
            node_id=f"n{i:02d}",
            partition="gpu",
            gpus=8,
            gpu_model="h100",
            cpus=96,
            memory_mb=100_000,
            features=frozenset({"h100", "nvlink"}),
        )
        for i in range(node_count)
    )


def test_priority_qos_and_fair_share_order_same_timestamp() -> None:
    engine = _engine()
    engine.qos_weights.update({"urgent": 10.0, "normal": 1.0})
    engine.submit(_job("low", priority=1.0, qos="normal", fair_share_usage=0.9))
    engine.submit(_job("urgent", priority=10.0, qos="urgent", fair_share_usage=0.1))
    engine.advance(0.0)

    running = [event for event in engine.events() if event.event_type == WorkloadEventType.RUNNING]
    assert [event.job_id for event in running] == ["urgent"]
    assert engine.summary("low").state == "PENDING"
    assert engine.summary("low").reason is None


def test_dependency_unblocks_after_success_and_releases_nodes() -> None:
    engine = _engine()
    engine.submit(_job("train", duration=5.0))
    engine.submit(_job("eval", dependencies=("afterok:train",)))
    engine.advance(0.0)
    assert engine.summary("train").state == "RUNNING"
    assert engine.summary("eval").state == "PENDING"

    events = engine.advance(5.0)
    assert [event.event_type for event in events] == [
        WorkloadEventType.JOB_END,
        WorkloadEventType.RUNNING,
    ]
    assert engine.summary("eval").state == "RUNNING"
    assert engine.metrics().allocated_nodes == 1


def test_cancellation_releases_allocation_and_terminal_state_is_stable() -> None:
    engine = _engine()
    engine.submit(_job("cancel-me", duration=50.0, priority=10.0))
    engine.submit(_job("waiter", priority=1.0))
    engine.advance(0.0)
    cancel = engine.cancel("cancel-me", now=2.0)
    assert cancel.event_type == WorkloadEventType.CANCELLED
    assert engine.summary("cancel-me").state == "CANCELLED"
    assert engine.metrics().allocated_nodes == 0

    engine.advance(2.0)
    assert engine.summary("waiter").state == "RUNNING"
    with pytest.raises(SlurmSchedulerError):
        engine.cancel("cancel-me", now=3.0)


def test_constraints_and_reservations_control_eligibility() -> None:
    engine = SlurmSchedulerEngine(
        [
            SlurmNode(
                node_id="reserved",
                partition="gpu",
                gpus=8,
                gpu_model="h100",
                features=frozenset({"h100", "nvlink"}),
            ),
            SlurmNode(
                node_id="general",
                partition="gpu",
                gpus=8,
                gpu_model="h100",
                features=frozenset({"h100"}),
            ),
        ],
        reservations={"maint": (0.0, 10.0, ("reserved",))},
    )
    engine.submit(_job("reserved-job", reservation="maint", features=("nvlink",)))
    engine.submit(_job("general-job", features=("nvlink",)))
    engine.advance(0.0)

    assert engine.allocations["reserved-job"].node_ids == ("reserved",)
    assert engine.summary("general-job").state == "PENDING"
    assert engine.summary("general-job").reason is None

    with pytest.raises(ImpossibleJobError):
        engine.submit(_job("wrong-gpu", gpu_model="a100"))


def test_backfill_is_explicit_and_can_be_disabled() -> None:
    nodes = [
        SlurmNode(node_id="n01", partition="gpu", gpus=8, gpu_model="h100"),
        SlurmNode(node_id="n02", partition="gpu", gpus=8, gpu_model="h100"),
    ]
    for backfill, expected in ((True, "RUNNING"), (False, "PENDING")):
        engine = SlurmSchedulerEngine(nodes, backfill=backfill)
        engine.submit(_job("blocker", node_count=1, priority=20.0, duration=10.0))
        engine.submit(_job("wide", node_count=2, priority=10.0, duration=20.0))
        engine.submit(_job("small", node_count=1, priority=1.0, duration=2.0))
        engine.advance(0.0)
        assert engine.summary("small").state == expected


def test_run_context_emits_queue_running_completion_and_power() -> None:
    spec = {
        "name": "internal-slurm-test",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 30.0,
        "bess_units": [],
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "irradiance_steps": [],
        "island_mode": False,
        "pue_base": 1.03,
        "run_duration_s": 30.0,
        "workload_events": [],
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "slurm_config": {
            "nodes": [
                {
                    "node_id": "n01",
                    "partition": "gpu",
                    "gpus": 8,
                    "gpu_model": "h100",
                }
            ],
            "jobs": [
                {
                    "job_id": "first",
                    "arrival_time": 0.0,
                    "duration": 5.0,
                    "node_count": 1,
                    "gpus_per_node": 8,
                    "gpu_model": "h100",
                    "partition": "gpu",
                    "priority": 1.0,
                },
                {
                    "job_id": "second",
                    "arrival_time": 0.0,
                    "duration": 5.0,
                    "node_count": 1,
                    "gpus_per_node": 8,
                    "gpu_model": "h100",
                    "partition": "gpu",
                    "priority": 10.0,
                },
            ],
        },
    }
    ctx = build_run_context_from_spec("run-internal-slurm-test", spec)

    first_tick = ctx.step()
    assert first_tick.slurm_metrics is not None
    assert first_tick.slurm_metrics["running"] == 1
    assert first_tick.slurm_metrics["queued"] == 1
    assert first_tick.p_compute_demand_mw > 0.0

    second_tick = ctx.step()
    assert second_tick.slurm_metrics["completed"] == 1
    assert second_tick.slurm_metrics["running"] == 1
    assert second_tick.p_compute_demand_mw > 0.0

    third_tick = ctx.step()
    assert third_tick.slurm_metrics["completed"] == 2
    assert third_tick.slurm_metrics["running"] == 0
    assert third_tick.p_compute_demand_mw == 0.0


def test_internal_scheduler_state_does_not_leak_between_runs() -> None:
    base = {
        "name": "isolated-slurm-test",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 30.0,
        "bess_units": [],
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "irradiance_steps": [],
        "island_mode": False,
        "pue_base": 1.03,
        "run_duration_s": 20.0,
        "workload_events": [],
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "slurm_config": {
            "nodes": [{"node_id": "n01", "gpus": 8, "gpu_model": "h100"}],
            "jobs": [{
                "job_id": "only-job",
                "arrival_time": 0.0,
                "duration": 5.0,
                "node_count": 1,
                "gpus_per_node": 8,
                "gpu_model": "h100",
                "hardware_profile_id": "enterprise_8gpu_air",
            }],
        },
    }
    first = build_run_context_from_spec("run-a", base)
    second = build_run_context_from_spec("run-b", base)
    first_tick = first.step()
    second_tick = second.step()
    assert first_tick.slurm_metrics["running"] == 1
    assert second_tick.slurm_metrics["running"] == 1
    first.step()
    assert first.slurm_scheduler is not second.slurm_scheduler
    assert first.slurm_scheduler.summary("only-job").state == "COMPLETED"
    assert second.slurm_scheduler.summary("only-job").state == "RUNNING"