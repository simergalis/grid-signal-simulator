"""Stage S1 scenario-study harness.

The harness is deliberately an importer of the simulator engine.  It owns
study identity, metric collection, acceptance comparison, and artifacts; it
does not duplicate simulator physics or controller policy.
"""

from .acceptance import compare_metrics
from .artifacts import ArtifactWriter
from .errors import (
    ArtifactPathError,
    ArtifactSizeError,
    BuildParityMismatchError,
    FuelComponentReconciliationError,
    FuelModelAbsentError,
    HarnessGuardError,
    StartFuelReconciliationError,
    UnsupportedScenarioError,
)
from .manifest import RunIdentity, RunManifestCache, make_run_identity
from .metrics import MetricsCollector, collect_metrics

__all__ = [
    "ArtifactPathError",
    "ArtifactSizeError",
    "BuildParityMismatchError",
    "FuelComponentReconciliationError",
    "FuelModelAbsentError",
    "HarnessGuardError",
    "MetricsCollector",
    "RunIdentity",
    "RunManifestCache",
    "StartFuelReconciliationError",
    "ArtifactWriter",
    "collect_metrics",
    "compare_metrics",
    "make_run_identity",
    "UnsupportedScenarioError",
]