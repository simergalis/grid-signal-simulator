"""Separate physical power-enforcement layer for Ray workloads.

This module consumes measured workload usage and produces deterministic
effective usage plus enforcement events.  It does not admit infrastructure,
resize KubeRay clusters, or mutate logical Ray placement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum
from typing import Mapping, Optional

from .ray_models import (
    PowerEnforcementPolicy,
    RayContractError,
    RayMeasuredUsage,
)


class RayPowerEnforcementError(RayContractError):
    """Raised when a physical power-enforcement transition is invalid."""


class RayPowerAction(str, Enum):
    OBSERVED = "observed"
    GPU_POWER_CAPPED = "gpu_power_capped"
    CPU_POWER_LIMITED = "cpu_power_limited"
    NODE_POWER_SHED = "node_power_shed"
    BUDGET_THROTTLED = "budget_throttled"
    BUDGET_VIOLATION = "budget_violation"


@dataclass(frozen=True)
class RayPowerEnforcementPolicySpec:
    """Physical limits for one Ray cluster.

    ``power_budget_kw`` is an enforcement budget over the measured workload
    total.  The per-workload limits are applied before the cluster budget.
    ``CAPACITY_ONLY`` reports an over-budget condition but leaves usage
    unchanged; it is useful when measurement is advisory.
    """

    policy: PowerEnforcementPolicy = PowerEnforcementPolicy.CAPACITY_ONLY
    power_budget_kw: Optional[float] = None
    gpu_power_cap_kw: Optional[float] = None
    cpu_power_limit_kw: Optional[float] = None
    node_power_limit_kw: Optional[float] = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self, "policy", PowerEnforcementPolicy(self.policy)
            )
        except ValueError as exc:
            raise RayPowerEnforcementError(
                "unsupported power enforcement policy"
            ) from exc
        for name in (
            "power_budget_kw",
            "gpu_power_cap_kw",
            "cpu_power_limit_kw",
            "node_power_limit_kw",
        ):
            value = getattr(self, name)
            if value is not None and (
                not math.isfinite(float(value)) or float(value) < 0.0
            ):
                raise RayPowerEnforcementError(
                    f"{name} must be finite and non-negative or None"
                )
        if (
            self.policy is PowerEnforcementPolicy.GPU_POWER_CAP
            and self.gpu_power_cap_kw is None
        ):
            raise RayPowerEnforcementError(
                "GPU_POWER_CAP requires gpu_power_cap_kw"
            )
        if (
            self.policy is PowerEnforcementPolicy.CPU_POWER_LIMIT
            and self.cpu_power_limit_kw is None
        ):
            raise RayPowerEnforcementError(
                "CPU_POWER_LIMIT requires cpu_power_limit_kw"
            )
        if (
            self.policy is PowerEnforcementPolicy.NODE_POWER_STATE
            and self.node_power_limit_kw is None
        ):
            raise RayPowerEnforcementError(
                "NODE_POWER_STATE requires node_power_limit_kw"
            )


@dataclass(frozen=True)
class RayPowerEnforcementEvent:
    cluster_id: str
    workload_id: str
    timestamp: float
    action: RayPowerAction
    observed_usage: RayMeasuredUsage
    effective_usage: RayMeasuredUsage
    throttle_fraction: float
    observed_cluster_power_kw: float
    effective_cluster_power_kw: float
    power_budget_kw: Optional[float]
    reason: str


@dataclass(frozen=True)
class RayPowerEnforcementStatus:
    cluster_id: str
    observed_cluster_power_kw: float
    effective_cluster_power_kw: float
    power_budget_kw: Optional[float]
    over_budget: bool
    workload_count: int


def _usage_power_kw(usage: RayMeasuredUsage) -> float:
    return usage.gpu_power_kw + usage.cpu_power_kw


def _scale_usage(usage: RayMeasuredUsage, fraction: float) -> RayMeasuredUsage:
    fraction = max(0.0, min(1.0, float(fraction)))
    return replace(
        usage,
        cpu_cores=usage.cpu_cores * fraction,
        memory_gib=usage.memory_gib * fraction,
        gpu_utilization=usage.gpu_utilization * fraction,
        gpu_power_kw=usage.gpu_power_kw * fraction,
        cpu_power_kw=usage.cpu_power_kw * fraction,
    )


class RayPowerEnforcer:
    """Apply physical power policy to measured Ray workload usage.

    Usage is explicitly submitted to this layer.  The enforcer never derives
    physical power from logical CPU/GPU requests and never calls admission or
    placement APIs.
    """

    def __init__(
        self,
        policies: Mapping[str, RayPowerEnforcementPolicySpec],
    ) -> None:
        if not policies:
            raise RayPowerEnforcementError(
                "at least one Ray power policy is required"
            )
        self.policies = dict(policies)
        self._usage: dict[str, dict[str, RayMeasuredUsage]] = {}
        self._effective: dict[str, dict[str, RayMeasuredUsage]] = {}
        self._events: list[RayPowerEnforcementEvent] = []
        self.time = 0.0

    @property
    def events(self) -> tuple[RayPowerEnforcementEvent, ...]:
        return tuple(self._events)

    def observe_usage(
        self,
        cluster_id: str,
        workload_id: str,
        usage: RayMeasuredUsage,
    ) -> None:
        """Replace one workload's latest measured physical usage."""
        self._policy(cluster_id)
        if not workload_id:
            raise RayPowerEnforcementError("workload_id must not be empty")
        if not isinstance(usage, RayMeasuredUsage):
            raise RayPowerEnforcementError(
                "usage must be a RayMeasuredUsage instance"
            )
        self._usage.setdefault(cluster_id, {})[workload_id] = usage

    def clear_usage(
        self, cluster_id: str, workload_id: Optional[str] = None
    ) -> None:
        """Remove a workload or all workloads from the measurement snapshot."""
        self._policy(cluster_id)
        if workload_id is None:
            self._usage.pop(cluster_id, None)
            self._effective.pop(cluster_id, None)
            return
        self._usage.get(cluster_id, {}).pop(workload_id, None)
        self._effective.get(cluster_id, {}).pop(workload_id, None)

    def enforce(
        self, cluster_id: str, now: Optional[float] = None
    ) -> tuple[RayPowerEnforcementEvent, ...]:
        policy = self._policy(cluster_id)
        timestamp = self.time if now is None else float(now)
        if timestamp < self.time or not math.isfinite(timestamp):
            raise RayPowerEnforcementError(
                "power-enforcement clock cannot move backwards or be non-finite"
            )
        self.time = timestamp

        observed = dict(sorted(self._usage.get(cluster_id, {}).items()))
        observed_total = sum(_usage_power_kw(usage) for usage in observed.values())
        effective = dict(observed)
        actions: dict[str, RayPowerAction] = {
            workload_id: RayPowerAction.OBSERVED
            for workload_id in observed
        }
        reasons: dict[str, str] = {
            workload_id: "measured usage within configured limits"
            for workload_id in observed
        }

        for workload_id, usage in observed.items():
            if (
                policy.policy is PowerEnforcementPolicy.GPU_POWER_CAP
                and policy.gpu_power_cap_kw is not None
                and usage.gpu_power_kw > policy.gpu_power_cap_kw
            ):
                gpu_fraction = (
                    policy.gpu_power_cap_kw / usage.gpu_power_kw
                    if usage.gpu_power_kw
                    else 1.0
                )
                effective[workload_id] = replace(
                    usage,
                    gpu_utilization=usage.gpu_utilization * gpu_fraction,
                    gpu_power_kw=policy.gpu_power_cap_kw,
                )
                actions[workload_id] = RayPowerAction.GPU_POWER_CAPPED
                reasons[workload_id] = "GPU power cap applied to measured usage"
            elif (
                policy.policy is PowerEnforcementPolicy.CPU_POWER_LIMIT
                and policy.cpu_power_limit_kw is not None
                and usage.cpu_power_kw > policy.cpu_power_limit_kw
            ):
                cpu_fraction = (
                    policy.cpu_power_limit_kw / usage.cpu_power_kw
                    if usage.cpu_power_kw
                    else 1.0
                )
                effective[workload_id] = replace(
                    usage,
                    cpu_cores=usage.cpu_cores * cpu_fraction,
                    cpu_power_kw=policy.cpu_power_limit_kw,
                )
                actions[workload_id] = RayPowerAction.CPU_POWER_LIMITED
                reasons[workload_id] = "CPU power limit applied to measured usage"
            elif (
                policy.policy is PowerEnforcementPolicy.NODE_POWER_STATE
                and policy.node_power_limit_kw is not None
                and _usage_power_kw(usage) > policy.node_power_limit_kw
            ):
                effective[workload_id] = _scale_usage(usage, 0.0)
                actions[workload_id] = RayPowerAction.NODE_POWER_SHED
                reasons[workload_id] = (
                    "node power state enforcement shed the workload"
                )

        effective_total = sum(
            _usage_power_kw(usage) for usage in effective.values()
        )
        if (
            policy.power_budget_kw is not None
            and effective_total > policy.power_budget_kw
        ):
            if policy.policy is PowerEnforcementPolicy.CAPACITY_ONLY:
                for workload_id in observed:
                    if actions[workload_id] is RayPowerAction.OBSERVED:
                        actions[workload_id] = RayPowerAction.BUDGET_VIOLATION
                        reasons[workload_id] = (
                            "measured cluster usage exceeds power budget"
                        )
            elif effective_total > 0.0:
                fraction = policy.power_budget_kw / effective_total
                for workload_id, usage in effective.items():
                    if fraction < 1.0:
                        effective[workload_id] = _scale_usage(usage, fraction)
                        if actions[workload_id] is RayPowerAction.OBSERVED:
                            actions[workload_id] = RayPowerAction.BUDGET_THROTTLED
                            reasons[workload_id] = (
                                "cluster power budget throttled measured usage"
                            )
                        else:
                            reasons[workload_id] += (
                                "; cluster power budget applied"
                            )
                effective_total = sum(
                    _usage_power_kw(usage) for usage in effective.values()
                )

        self._effective[cluster_id] = effective
        emitted = tuple(
            self._emit(
                cluster_id=cluster_id,
                workload_id=workload_id,
                timestamp=timestamp,
                action=actions[workload_id],
                observed_usage=observed[workload_id],
                effective_usage=effective[workload_id],
                throttle_fraction=(
                    _usage_power_kw(effective[workload_id])
                    / _usage_power_kw(observed[workload_id])
                    if _usage_power_kw(observed[workload_id]) > 0.0
                    else 1.0
                ),
                observed_cluster_power_kw=observed_total,
                effective_cluster_power_kw=effective_total,
                power_budget_kw=policy.power_budget_kw,
                reason=reasons[workload_id],
            )
            for workload_id in observed
        )
        return emitted

    def effective_usage(
        self, cluster_id: str, workload_id: str
    ) -> RayMeasuredUsage:
        self._policy(cluster_id)
        try:
            return self._effective[cluster_id][workload_id]
        except KeyError as exc:
            raise RayPowerEnforcementError(
                "no enforced usage snapshot exists for this workload"
            ) from exc

    def status(self, cluster_id: str) -> RayPowerEnforcementStatus:
        policy = self._policy(cluster_id)
        observed_total = sum(
            _usage_power_kw(usage)
            for usage in self._usage.get(cluster_id, {}).values()
        )
        effective_total = sum(
            _usage_power_kw(usage)
            for usage in self._effective.get(cluster_id, {}).values()
        )
        return RayPowerEnforcementStatus(
            cluster_id=cluster_id,
            observed_cluster_power_kw=observed_total,
            effective_cluster_power_kw=effective_total,
            power_budget_kw=policy.power_budget_kw,
            over_budget=(
                policy.power_budget_kw is not None
                and observed_total > policy.power_budget_kw
            ),
            workload_count=len(self._usage.get(cluster_id, {})),
        )

    def _emit(self, **kwargs: object) -> RayPowerEnforcementEvent:
        event = RayPowerEnforcementEvent(**kwargs)  # type: ignore[arg-type]
        self._events.append(event)
        return event

    def _policy(self, cluster_id: str) -> RayPowerEnforcementPolicySpec:
        try:
            return self.policies[cluster_id]
        except KeyError as exc:
            raise RayPowerEnforcementError(
                f"no power-enforcement policy for Ray cluster {cluster_id!r}"
            ) from exc


PowerEnforcementEngine = RayPowerEnforcer