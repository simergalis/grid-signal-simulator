"""Read-only observability snapshots for the Ray control and physical planes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional

from .ray_autoscaler import RayAutoscaler
from .ray_cluster_engine import RayClusterEngine, RayClusterLifecycleState
from .ray_external_ingestion import (
    RayExternalIngestor,
    RayExternalSnapshot,
    RayObservedWorkloadState,
)
from .ray_power_enforcement import RayPowerEnforcer


class RayObservabilityError(ValueError):
    """Raised when an observability query is invalid."""


class RayIngestionFreshness(str, Enum):
    NO_DATA = "no_data"
    FRESH = "fresh"
    STALE = "stale"


@dataclass(frozen=True)
class RayObservabilitySnapshot:
    cluster_id: str
    captured_at: float
    ingestion_freshness: RayIngestionFreshness
    external_source: Optional[str]
    external_sequence: Optional[int]
    external_observed_at: Optional[float]
    ingestion_lag_s: Optional[float]
    lifecycle_state: Optional[RayClusterLifecycleState]
    registered_workers: Optional[int]
    observed_workloads: int
    running_workloads: int
    queued_workloads: int
    failed_workloads: int
    observed_power_kw: Optional[float]
    effective_power_kw: Optional[float]
    power_budget_kw: Optional[float]
    power_over_budget: Optional[bool]
    autoscaling_in_flight: Optional[bool]
    event_counts: Mapping[str, int]


class RayObservabilityCollector:
    """Combine read-only snapshots from ingestion and control-plane engines."""

    def __init__(
        self,
        external_ingestor: RayExternalIngestor,
        *,
        cluster_engine: Optional[RayClusterEngine] = None,
        autoscaler: Optional[RayAutoscaler] = None,
        power_enforcer: Optional[RayPowerEnforcer] = None,
        stale_after_s: float = 60.0,
    ) -> None:
        if stale_after_s < 0.0 or not math.isfinite(float(stale_after_s)):
            raise RayObservabilityError(
                "stale_after_s must be finite and non-negative"
            )
        self.external_ingestor = external_ingestor
        self.cluster_engine = cluster_engine
        self.autoscaler = autoscaler
        self.power_enforcer = power_enforcer
        self.stale_after_s = float(stale_after_s)

    def collect(
        self, cluster_id: str, now: float
    ) -> RayObservabilitySnapshot:
        if not cluster_id:
            raise RayObservabilityError("cluster_id must not be empty")
        if not math.isfinite(float(now)) or now < 0.0:
            raise RayObservabilityError(
                "now must be finite and non-negative"
            )
        external = self.external_ingestor.latest_snapshot(cluster_id)
        freshness, lag = self._freshness(external, float(now))

        lifecycle_state: Optional[RayClusterLifecycleState] = None
        registered_workers: Optional[int] = None
        autoscaling_in_flight: Optional[bool] = None
        lifecycle_events = 0
        autoscaler_events = 0
        if self.cluster_engine is not None:
            try:
                status = self.cluster_engine.status(cluster_id)
            except KeyError:
                status = None
            if status is not None:
                lifecycle_state = status.state
                registered_workers = status.registered_workers
                lifecycle_events = sum(
                    event.cluster_id == cluster_id
                    for event in self.cluster_engine.events
                )
                autoscaling_in_flight = (
                    self.cluster_engine.scaling_in_flight(cluster_id)
                )
        if self.autoscaler is not None:
            try:
                autoscaler_status = self.autoscaler.status(cluster_id)
            except Exception:
                autoscaler_status = None
            if autoscaler_status is not None:
                autoscaling_in_flight = autoscaler_status.scale_in_flight
            autoscaler_events = sum(
                event.cluster_id == cluster_id
                for event in self.autoscaler.events
            )

        power_status = None
        power_events = 0
        if self.power_enforcer is not None:
            try:
                power_status = self.power_enforcer.status(cluster_id)
            except Exception:
                power_status = None
            power_events = sum(
                event.cluster_id == cluster_id
                for event in self.power_enforcer.events
            )

        counts = self._workload_counts(external)
        return RayObservabilitySnapshot(
            cluster_id=cluster_id,
            captured_at=float(now),
            ingestion_freshness=freshness,
            external_source=external.source.value if external else None,
            external_sequence=external.source_sequence if external else None,
            external_observed_at=external.observed_at if external else None,
            ingestion_lag_s=lag,
            lifecycle_state=lifecycle_state,
            registered_workers=registered_workers,
            observed_workloads=counts["observed"],
            running_workloads=counts["running"],
            queued_workloads=counts["queued"],
            failed_workloads=counts["failed"],
            observed_power_kw=(
                power_status.observed_cluster_power_kw
                if power_status is not None
                else None
            ),
            effective_power_kw=(
                power_status.effective_cluster_power_kw
                if power_status is not None
                else None
            ),
            power_budget_kw=(
                power_status.power_budget_kw
                if power_status is not None
                else None
            ),
            power_over_budget=(
                power_status.over_budget if power_status is not None else None
            ),
            autoscaling_in_flight=autoscaling_in_flight,
            event_counts={
                "external_accepted": (
                    self._external_count(cluster_id, "accepted")
                ),
                "external_duplicates": (
                    self._external_count(cluster_id, "duplicate")
                ),
                "external_quarantined": (
                    self._external_count(cluster_id, "quarantined")
                ),
                "lifecycle_events": lifecycle_events,
                "autoscaler_events": autoscaler_events,
                "power_events": power_events,
            },
        )

    def _freshness(
        self, external: Optional[RayExternalSnapshot], now: float
    ) -> tuple[RayIngestionFreshness, Optional[float]]:
        if external is None:
            return RayIngestionFreshness.NO_DATA, None
        lag = max(0.0, now - external.observed_at)
        return (
            (
                RayIngestionFreshness.FRESH
                if lag <= self.stale_after_s
                else RayIngestionFreshness.STALE
            ),
            lag,
        )

    @staticmethod
    def _workload_counts(
        external: Optional[RayExternalSnapshot],
    ) -> dict[str, int]:
        counts = {
            "observed": 0,
            "running": 0,
            "queued": 0,
            "failed": 0,
        }
        if external is None:
            return counts
        counts["observed"] = len(external.workloads)
        for workload in external.workloads:
            if workload.state is RayObservedWorkloadState.RUNNING:
                counts["running"] += 1
            elif workload.state is RayObservedWorkloadState.QUEUED:
                counts["queued"] += 1
            elif workload.state is RayObservedWorkloadState.FAILED:
                counts["failed"] += 1
        return counts

    def _external_count(self, cluster_id: str, name: str) -> int:
        snapshots = [
            self.external_ingestor.health(cluster_id, source)
            for source in (
                "ray_state_api",
                "kuberay",
                "prometheus",
                "dcgm",
            )
        ]
        attribute = {
            "accepted": "accepted_count",
            "duplicate": "duplicate_count",
            "quarantined": "quarantined_count",
        }[name]
        return sum(getattr(health, attribute) for health in snapshots)