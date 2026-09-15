"""Phase 7 external Ray ingestion and observability tests."""

from __future__ import annotations

import pytest

from core.ray_external_ingestion import (
    RayExternalIngestor,
    RayExternalSnapshot,
    RayExternalSource,
    RayExternalWorkloadObservation,
    RayObservedWorkloadState,
)
from core.ray_models import RayMeasuredUsage
from core.ray_models import PowerEnforcementPolicy
from core.ray_observability import (
    RayIngestionFreshness,
    RayObservabilityCollector,
    RayObservabilityError,
)
from core.ray_power_enforcement import (
    RayPowerEnforcementPolicySpec,
    RayPowerEnforcer,
)


def _snapshot(
    event_id: str,
    sequence: int,
    observed_at: float,
    *,
    source: RayExternalSource = RayExternalSource.RAY_STATE_API,
) -> RayExternalSnapshot:
    return RayExternalSnapshot(
        event_id=event_id,
        source=source,
        cluster_id="ray-1",
        observed_at=observed_at,
        source_sequence=sequence,
        worker_count=2,
        workloads=(
            RayExternalWorkloadObservation(
                "queued-1", RayObservedWorkloadState.QUEUED
            ),
            RayExternalWorkloadObservation(
                "running-1",
                RayObservedWorkloadState.RUNNING,
                RayMeasuredUsage(gpu_power_kw=6.0),
            ),
            RayExternalWorkloadObservation(
                "failed-1", RayObservedWorkloadState.FAILED
            ),
        ),
    )


def test_external_snapshots_are_deduplicated_and_latest_is_monotonic():
    ingestor = RayExternalIngestor()
    first = ingestor.ingest(_snapshot("event-1", 1, 0.0), sim_time=0.0)
    duplicate = ingestor.ingest(_snapshot("event-1", 1, 0.0), sim_time=1.0)
    stale = ingestor.ingest(_snapshot("event-2", 1, 0.5), sim_time=1.0)
    second = ingestor.ingest(_snapshot("event-3", 2, 1.0), sim_time=1.0)

    assert first.status.value == "accepted"
    assert duplicate.status.value == "duplicate"
    assert stale.status.value == "quarantined"
    assert second.status.value == "accepted"
    assert ingestor.latest_snapshot("ray-1").source_sequence == 2
    assert ingestor.health("ray-1", RayExternalSource.RAY_STATE_API).quarantined_count == 1


def test_external_ingestion_quarantines_invalid_clock_and_preserves_payload():
    ingestor = RayExternalIngestor()
    result = ingestor.ingest(_snapshot("future", 1, 5.0), sim_time=4.0)

    assert result.status.value == "quarantined"
    assert ingestor.quarantine.count == 1
    assert "ahead" in ingestor.quarantine.all_records()[0].reason


def test_sources_have_independent_ordering_and_cluster_latest_is_observation_latest():
    ingestor = RayExternalIngestor()
    ingestor.ingest(_snapshot("kube-1", 1, 3.0, source=RayExternalSource.KUBERAY), 3.0)
    ingestor.ingest(_snapshot("ray-1", 1, 4.0), 4.0)

    latest = ingestor.latest_snapshot("ray-1")

    assert latest is not None
    assert latest.source is RayExternalSource.RAY_STATE_API
    assert ingestor.health("ray-1", RayExternalSource.KUBERAY).accepted_count == 1


def test_observability_reports_freshness_workloads_and_power_status():
    ingestor = RayExternalIngestor()
    ingestor.ingest(_snapshot("event-1", 1, 10.0), sim_time=10.0)
    power = RayPowerEnforcer(
        {
            "ray-1": RayPowerEnforcementPolicySpec(
                policy=PowerEnforcementPolicy.GPU_POWER_CAP,
                power_budget_kw=5.0,
                gpu_power_cap_kw=100.0,
            )
        }
    )
    power.observe_usage(
        "ray-1", "running-1", RayMeasuredUsage(gpu_power_kw=6.0)
    )
    power.enforce("ray-1", now=10.0)
    collector = RayObservabilityCollector(
        ingestor,
        power_enforcer=power,
        stale_after_s=2.0,
    )

    report = collector.collect("ray-1", now=11.0)

    assert report.ingestion_freshness is RayIngestionFreshness.FRESH
    assert report.running_workloads == 1
    assert report.queued_workloads == 1
    assert report.failed_workloads == 1
    assert report.observed_power_kw == 6.0
    assert report.effective_power_kw == 5.0
    assert report.power_over_budget is True
    assert report.event_counts["power_events"] == 1


def test_observability_marks_old_external_data_stale_and_no_data_explicitly():
    ingestor = RayExternalIngestor()
    collector = RayObservabilityCollector(ingestor, stale_after_s=2.0)

    empty = collector.collect("missing", now=0.0)
    assert empty.ingestion_freshness is RayIngestionFreshness.NO_DATA

    ingestor.ingest(_snapshot("event-1", 1, 1.0), sim_time=1.0)
    stale = collector.collect("ray-1", now=4.0)
    assert stale.ingestion_freshness is RayIngestionFreshness.STALE
    assert stale.ingestion_lag_s == 3.0


def test_observability_validates_query_clock():
    collector = RayObservabilityCollector(RayExternalIngestor())

    with pytest.raises(RayObservabilityError, match="non-negative"):
        collector.collect("ray-1", now=-1.0)