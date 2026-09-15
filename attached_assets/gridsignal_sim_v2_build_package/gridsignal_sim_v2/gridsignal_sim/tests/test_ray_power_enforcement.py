"""Phase 6 separate Ray physical power-enforcement tests."""

from __future__ import annotations

import pytest

from core.ray_autoscaler import RayAutoscaler, RayAutoscalingPolicy
from core.ray_cluster_engine import RayClusterEngine, RayClusterLifecycleState
from core.ray_execution_scheduler import RayExecutionScheduler
from core.ray_models import (
    InfrastructureBackend,
    PowerEnforcementPolicy,
    RayMeasuredUsage,
    RayResourceRequest,
)
from core.ray_power_enforcement import (
    PowerEnforcementEngine,
    RayPowerAction,
    RayPowerEnforcementError,
    RayPowerEnforcementPolicySpec,
    RayPowerEnforcer,
)


def _usage(gpu: float = 0.0, cpu: float = 0.0) -> RayMeasuredUsage:
    return RayMeasuredUsage(
        cpu_cores=4,
        gpu_utilization=0.8 if gpu else 0.0,
        gpu_power_kw=gpu,
        cpu_power_kw=cpu,
    )


def test_gpu_cap_enforces_measured_power_without_rewriting_logical_requests():
    enforcer = RayPowerEnforcer(
        {
            "ray-1": RayPowerEnforcementPolicySpec(
                policy=PowerEnforcementPolicy.GPU_POWER_CAP,
                gpu_power_cap_kw=8.0,
            )
        }
    )
    enforcer.observe_usage("ray-1", "workload-1", _usage(gpu=12.0, cpu=1.0))

    events = enforcer.enforce("ray-1")

    assert events[0].action is RayPowerAction.GPU_POWER_CAPPED
    assert events[0].effective_usage.gpu_power_kw == 8.0
    assert events[0].effective_usage.cpu_power_kw == 1.0
    assert events[0].observed_usage.gpu_power_kw == 12.0


def test_cluster_budget_throttles_deterministically_and_stays_within_budget():
    enforcer = RayPowerEnforcer(
        {
            "ray-1": RayPowerEnforcementPolicySpec(
                policy=PowerEnforcementPolicy.GPU_POWER_CAP,
                gpu_power_cap_kw=20.0,
                power_budget_kw=10.0,
            )
        }
    )
    enforcer.observe_usage("ray-1", "b", _usage(gpu=8.0))
    enforcer.observe_usage("ray-1", "a", _usage(gpu=8.0))

    events = enforcer.enforce("ray-1")

    assert [event.workload_id for event in events] == ["a", "b"]
    assert all(event.action is RayPowerAction.BUDGET_THROTTLED for event in events)
    assert enforcer.status("ray-1").effective_cluster_power_kw == pytest.approx(10.0)


def test_capacity_only_reports_violation_without_physical_mutation():
    enforcer = RayPowerEnforcer(
        {
            "ray-1": RayPowerEnforcementPolicySpec(
                power_budget_kw=5.0,
            )
        }
    )
    enforcer.observe_usage("ray-1", "workload-1", _usage(gpu=7.0))

    event = enforcer.enforce("ray-1")[0]

    assert event.action is RayPowerAction.BUDGET_VIOLATION
    assert event.effective_usage == event.observed_usage
    assert enforcer.status("ray-1").effective_cluster_power_kw == 7.0


def test_node_power_state_sheds_an_over_limit_workload():
    enforcer = RayPowerEnforcer(
        {
            "ray-1": RayPowerEnforcementPolicySpec(
                policy=PowerEnforcementPolicy.NODE_POWER_STATE,
                node_power_limit_kw=5.0,
            )
        }
    )
    enforcer.observe_usage("ray-1", "workload-1", _usage(gpu=6.0))

    event = enforcer.enforce("ray-1")[0]

    assert event.action is RayPowerAction.NODE_POWER_SHED
    assert event.effective_usage.gpu_power_kw == 0.0
    assert event.throttle_fraction == 0.0


def test_power_enforcement_does_not_enter_autoscaler_or_logical_scheduler():
    assert PowerEnforcementEngine is RayPowerEnforcer
    assert not hasattr(RayAutoscaler, "enforce_power")
    assert not hasattr(RayExecutionScheduler, "enforce_power")
    assert RayClusterLifecycleState.READY.value == "ready"


def test_policy_requirements_and_unknown_cluster_are_explicit():
    with pytest.raises(RayPowerEnforcementError, match="gpu_power_cap_kw"):
        RayPowerEnforcementPolicySpec(
            policy=PowerEnforcementPolicy.GPU_POWER_CAP
        )

    enforcer = RayPowerEnforcer(
        {"ray-1": RayPowerEnforcementPolicySpec()}
    )
    with pytest.raises(RayPowerEnforcementError, match="no power-enforcement"):
        enforcer.observe_usage("missing", "workload-1", _usage(gpu=1.0))