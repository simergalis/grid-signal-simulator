"""Validated external Ray/Kubernetes snapshot ingestion.

External snapshots are observations only.  This module never submits
admission requests, starts workers, changes logical placement, or applies
power enforcement.  It shares the repository's deduplication and quarantine
pipeline with the other ingest paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .ingest import (
    BaseIngestor,
    Deduplicator,
    IngestResult,
    IngestStatus,
    Quarantine,
)
from .ray_models import RayContractError, RayMeasuredUsage


class RayExternalIngestionError(RayContractError):
    """Raised when an external Ray observation cannot be queried."""


class RayExternalSource(str, Enum):
    RAY_STATE_API = "ray_state_api"
    KUBERAY = "kuberay"
    PROMETHEUS = "prometheus"
    DCGM = "dcgm"


class RayObservedWorkloadState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RayExternalWorkloadObservation:
    workload_id: str
    state: RayObservedWorkloadState
    measured_usage: Optional[RayMeasuredUsage] = None

    def __post_init__(self) -> None:
        if not self.workload_id:
            raise RayExternalIngestionError("workload_id must not be empty")
        try:
            object.__setattr__(
                self, "state", RayObservedWorkloadState(self.state)
            )
        except ValueError as exc:
            raise RayExternalIngestionError(
                "unsupported observed Ray workload state"
            ) from exc
        if self.measured_usage is not None and not isinstance(
            self.measured_usage, RayMeasuredUsage
        ):
            raise RayExternalIngestionError(
                "measured_usage must be a RayMeasuredUsage instance or None"
            )


@dataclass(frozen=True)
class RayExternalSnapshot:
    """One externally observed Ray cluster snapshot."""

    event_id: str
    source: RayExternalSource
    cluster_id: str
    observed_at: float
    source_sequence: int
    worker_count: int
    workloads: tuple[RayExternalWorkloadObservation, ...] = ()

    def __post_init__(self) -> None:
        if not self.event_id:
            raise RayExternalIngestionError("event_id must not be empty")
        if not self.cluster_id:
            raise RayExternalIngestionError("cluster_id must not be empty")
        try:
            object.__setattr__(self, "source", RayExternalSource(self.source))
        except ValueError as exc:
            raise RayExternalIngestionError(
                "unsupported external Ray source"
            ) from exc
        if not math.isfinite(float(self.observed_at)) or self.observed_at < 0.0:
            raise RayExternalIngestionError(
                "observed_at must be finite and non-negative"
            )
        if self.source_sequence < 0:
            raise RayExternalIngestionError(
                "source_sequence must be non-negative"
            )
        if self.worker_count < 0:
            raise RayExternalIngestionError(
                "worker_count must be non-negative"
            )
        workload_ids = [workload.workload_id for workload in self.workloads]
        if len(set(workload_ids)) != len(workload_ids):
            raise RayExternalIngestionError(
                "external snapshot workload IDs must be unique"
            )


@dataclass(frozen=True)
class RayExternalIngestionHealth:
    cluster_id: str
    source: RayExternalSource
    latest_sequence: Optional[int]
    latest_observed_at: Optional[float]
    accepted_count: int
    duplicate_count: int
    quarantined_count: int


class RayExternalIngestor(BaseIngestor):
    """Ingest external Ray snapshots with source-scoped ordering."""

    def __init__(
        self,
        *,
        deduplicator: Optional[Deduplicator] = None,
        quarantine: Optional[Quarantine] = None,
    ) -> None:
        super().__init__(deduplicator=deduplicator, quarantine=quarantine)
        self._records: list[RayExternalSnapshot] = []
        self._latest: dict[tuple[RayExternalSource, str], RayExternalSnapshot] = {}
        self._counts: dict[
            tuple[RayExternalSource, str], dict[IngestStatus, int]
        ] = {}
        self._last_sim_time = 0.0

    def ingest(
        self, snapshot: RayExternalSnapshot, sim_time: float
    ) -> IngestResult:
        if not math.isfinite(float(sim_time)) or sim_time < 0.0:
            raise RayExternalIngestionError(
                "sim_time must be finite and non-negative"
            )
        if sim_time < self._last_sim_time:
            raise RayExternalIngestionError(
                "external ingestion clock cannot move backwards"
            )
        self._last_sim_time = float(sim_time)
        result = self._ingest(
            snapshot, event_id=snapshot.event_id, sim_time=sim_time
        )
        key = (snapshot.source, snapshot.cluster_id)
        counts = self._counts.setdefault(
            key,
            {
                IngestStatus.ACCEPTED: 0,
                IngestStatus.DUPLICATE: 0,
                IngestStatus.QUARANTINED: 0,
            },
        )
        counts[result.status] += 1
        if result.status is IngestStatus.ACCEPTED:
            self._records.append(snapshot)
            self._latest[key] = snapshot
        return result

    def validate_domain(
        self, record: RayExternalSnapshot, sim_time: float
    ) -> str:
        if not isinstance(record, RayExternalSnapshot):
            return f"unexpected type: {type(record).__name__}"
        if record.observed_at > sim_time:
            return "external observation is ahead of the simulator clock"
        key = (record.source, record.cluster_id)
        previous = self._latest.get(key)
        if previous is not None:
            if record.source_sequence <= previous.source_sequence:
                return (
                    "external source sequence is not newer than the latest "
                    "accepted snapshot"
                )
            if record.observed_at < previous.observed_at:
                return (
                    "external observation timestamp is older than the latest "
                    "accepted snapshot"
                )
        return ""

    def latest_snapshot(
        self,
        cluster_id: str,
        source: Optional[RayExternalSource] = None,
    ) -> Optional[RayExternalSnapshot]:
        """Return the newest accepted snapshot for a cluster."""
        if source is not None:
            try:
                source = RayExternalSource(source)
            except ValueError as exc:
                raise RayExternalIngestionError(
                    "unsupported external Ray source"
                ) from exc
            return self._latest.get((source, cluster_id))
        candidates = [
            snapshot
            for (candidate_source, candidate_cluster), snapshot in self._latest.items()
            if candidate_cluster == cluster_id
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda snapshot: (
                snapshot.observed_at,
                snapshot.source_sequence,
                snapshot.source.value,
            ),
        )

    def all_records(self) -> tuple[RayExternalSnapshot, ...]:
        return tuple(self._records)

    def health(
        self,
        cluster_id: str,
        source: RayExternalSource,
    ) -> RayExternalIngestionHealth:
        try:
            source = RayExternalSource(source)
        except ValueError as exc:
            raise RayExternalIngestionError(
                "unsupported external Ray source"
            ) from exc
        key = (source, cluster_id)
        counts = self._counts.get(
            key,
            {
                IngestStatus.ACCEPTED: 0,
                IngestStatus.DUPLICATE: 0,
                IngestStatus.QUARANTINED: 0,
            },
        )
        latest = self._latest.get(key)
        return RayExternalIngestionHealth(
            cluster_id=cluster_id,
            source=source,
            latest_sequence=(
                latest.source_sequence if latest is not None else None
            ),
            latest_observed_at=(
                latest.observed_at if latest is not None else None
            ),
            accepted_count=counts[IngestStatus.ACCEPTED],
            duplicate_count=counts[IngestStatus.DUPLICATE],
            quarantined_count=counts[IngestStatus.QUARANTINED],
        )