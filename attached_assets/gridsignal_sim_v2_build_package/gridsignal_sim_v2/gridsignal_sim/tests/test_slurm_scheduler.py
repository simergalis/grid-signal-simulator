"""Deterministic internal Slurm scheduler and run-loop tests."""

from __future__ import annotations

import pytest

from core.models import WorkloadEventType
from core.slurm_scheduler import (
    ImpossibleJobError,
    SlurmJobSpec,
    SlurmNode,
    SlurmPhaseSpec,
    SlurmSchedulerError,
    SlurmSchedulerEngine,
)
from api.schemas import SlurmConfigSpec, SlurmJobConfigSpec
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


def test_job_arrays_honor_maximum_concurrency() -> None:
    engine = SlurmSchedulerEngine(
        [SlurmNode(node_id="n01", gpus=0, cpus=4, memory_mb=100)]
    )
    base = SlurmJobSpec(
        job_id="array",
        duration=5.0,
        cpus_per_node=2,
        array_parent_id="array",
        array_max_concurrent=1,
    )
    engine.submit_array(base, start=0, end=2, max_concurrent=1)
    engine.advance(0.0)
    assert [job.job_id for job in engine.running_snapshot()] == ["array_0"]
    engine.advance(5.0)
    assert [job.job_id for job in engine.running_snapshot()] == ["array_1"]


def test_heterogeneous_components_start_as_one_allocation_decision() -> None:
    engine = SlurmSchedulerEngine(
        [
            SlurmNode(node_id="n01", cpus=4, memory_mb=100),
            SlurmNode(node_id="n02", cpus=8, memory_mb=200),
        ]
    )
    engine.submit(SlurmJobSpec(
        job_id="hetero-0",
        node_count=1,
        cpus_per_node=4,
        hetero_group_id="hetero",
        hetero_component=0,
    ))
    engine.submit(SlurmJobSpec(
        job_id="hetero-1",
        node_count=1,
        cpus_per_node=8,
        hetero_group_id="hetero",
        hetero_component=1,
    ))
    events = engine.advance(0.0)
    assert [event.job_id for event in events if event.event_type == WorkloadEventType.RUNNING] == [
        "hetero-0",
        "hetero-1",
    ]


def test_license_and_burst_buffer_capacity_are_released_on_completion() -> None:
    engine = SlurmSchedulerEngine(
        [SlurmNode(node_id="n01", cpus=8, memory_mb=1000)],
        config={
            "licenses": [{"name": "sim-license", "count": 1}],
            "burst_buffers": [{"name": "bb", "capacity_mb": 100}],
        },
    )
    engine.submit(SlurmJobSpec(
        job_id="license-holder",
        duration=5.0,
        licenses={"sim-license": 1},
        burst_buffer="bb",
        burst_buffer_mb=100,
    ))
    engine.submit(SlurmJobSpec(
        job_id="license-waiter",
        licenses={"sim-license": 1},
        burst_buffer="bb",
        burst_buffer_mb=100,
    ))
    engine.advance(0.0)
    assert engine.summary("license-holder").state == "RUNNING"
    assert engine.summary("license-waiter").state == "PENDING"
    engine.advance(5.0)
    assert engine.summary("license-waiter").state == "RUNNING"
    assert engine.metrics().burst_buffer_mb == 100


def test_preemption_requeues_lower_priority_job_and_checkpoint_signals_are_emitted() -> None:
    engine = SlurmSchedulerEngine(
        [SlurmNode(node_id="n01", gpus=8, gpu_model="h100")],
        config={"preempt_mode": "requeue"},
    )
    engine.submit(SlurmJobSpec(job_id="low", duration=20.0, gpus_per_node=8, priority=1.0))
    engine.advance(0.0)
    engine.submit(SlurmJobSpec(
        job_id="high",
        duration=5.0,
        gpus_per_node=8,
        priority=10.0,
        checkpoint_interval_s=2.0,
    ))
    events = engine.advance(2.0)
    assert engine.summary("low").state == "PENDING"
    assert engine.summary("high").state == "RUNNING"
    events = engine.advance(4.0)
    assert any(event.event_type == WorkloadEventType.CHECKPOINT_START for event in events)


def test_virtual_runner_binds_gpus_and_reports_phase_energy() -> None:
    engine = _engine()
    engine.submit(SlurmJobSpec(
        job_id="phased",
        duration=99.0,
        gpus_per_node=8,
        phases=(
            SlurmPhaseSpec(
                kind="load",
                duration_s=2.0,
                gpu_utilization=0.25,
                gpu_memory_mb=1024,
                power_multiplier=0.5,
            ),
            SlurmPhaseSpec(
                kind="train",
                duration_s=3.0,
                gpu_utilization=0.9,
                gpu_memory_mb=8192,
            ),
        ),
    ))
    running = engine.advance(0.0)
    running_signal = next(
        event for event in running if event.event_type == WorkloadEventType.RUNNING
    )
    assert running_signal.phase_kind == "load"
    assert running_signal.gpu_ids == tuple(f"n00:gpu-{i}" for i in range(8))

    phase_events = engine.advance(2.0)
    phase_update = next(
        event for event in phase_events
        if event.event_type == WorkloadEventType.PHASE_UPDATE
    )
    assert phase_update.phase_kind == "train"
    assert phase_update.gpu_utilization == 0.9

    engine.advance(5.0)
    telemetry = engine.metrics().job_telemetry["phased"]
    assert telemetry["utilization"] == pytest.approx((0.25 * 2 + 0.9 * 3) / 5)
    assert telemetry["energy_mwh"] > 0.0
    assert telemetry["energy_mwh_per_gpu"] == pytest.approx(
        telemetry["energy_mwh"] / 8
    )
    assert engine.summary("phased").state == "COMPLETED"


def test_virtual_runner_has_deterministic_failure_and_timeout_outcomes() -> None:
    engine = _engine()
    engine.submit(SlurmJobSpec(
        job_id="fails",
        gpus_per_node=8,
        phases=(
            SlurmPhaseSpec(kind="warmup", duration_s=1.0),
            SlurmPhaseSpec(kind="bad", duration_s=2.0, failure=True),
        ),
    ))
    engine.advance(0.0)
    events = engine.advance(3.0)
    assert any(event.event_type == WorkloadEventType.JOB_FAILED for event in events)
    assert engine.summary("fails").state == "FAILED"

    timeout = SlurmSchedulerEngine([
        SlurmNode(node_id="n00", gpus=8, gpu_model="h100"),
    ])
    timeout.submit(SlurmJobSpec(
        job_id="timeout",
        gpus_per_node=8,
        time_limit_s=2.0,
        phases=(SlurmPhaseSpec(kind="long", duration_s=5.0),),
    ))
    timeout.advance(0.0)
    events = timeout.advance(2.0)
    assert any(event.event_type == WorkloadEventType.JOB_TIMEOUT for event in events)
    assert timeout.summary("timeout").state == "TIMEOUT"


def test_slurm_schema_rejects_unmodeled_options_and_invalid_array_ranges() -> None:
    with pytest.raises(ValueError):
        SlurmJobConfigSpec(job_id="bad", array_start=4, array_end=1)
    with pytest.raises(ValueError):
        SlurmConfigSpec(
            nodes=[{"node_id": "n01"}],
            jobs=[{"job_id": "bad", "not_a_slurm_option": True}],
        )
    phase_job = SlurmJobConfigSpec(
        job_id="phase-job",
        phases=[{
            "kind": "checkpoint",
            "duration_s": 2.0,
            "gpu_utilization": 0.2,
            "gpu_memory_mb": 256,
            "power_multiplier": 0.4,
        }],
    )
    assert phase_job.phases[0].kind == "checkpoint"