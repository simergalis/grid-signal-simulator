"""
core/ingest.py — §17.1-17.2 shared ingest machinery.

Step 14: NetworkTelemetry is a SECOND ingest class that shares this
machinery with WorkloadSignal.  A second ingestion path with different
validation/dedupe/quarantine rules would be a second set of bugs.

All ingest classes use:
  • Deduplicator      — §17.1 idempotency by event_id; 15-minute rolling window
  • Quarantine        — §17.2 quarantine store; raw_payload is TEXT (not JSON)
  • validate_domain() — per-class domain rule hook; called after schema check

IMPORTANT: this module is core/ — it has no imports from runtime/ api/ advisory/.

TC-74 guarantee: NetworkTelemetry is dispatch-path ineligible by contract.
  NetworkTelemetryIngestor raises NetworkTelemetryDispatchError if anyone
  attempts to route a validated telemetry record into the forecast path.
  The error is a TypeError subclass (non-conforming use, not misconfiguration).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

class IngestStatus(str, Enum):
    ACCEPTED     = "accepted"
    QUARANTINED  = "quarantined"   # §17.2 — validation failure
    DUPLICATE    = "duplicate"     # §17.1 — idempotency hit


@dataclass
class IngestResult:
    """Result of passing one record through the ingest pipeline."""
    status:    IngestStatus
    event_id:  str
    reason:    str  = ""
    # §17.2: raw_payload stored as TEXT — a malformed event may not be valid
    # JSON at all; storing parsed JSON would silently succeed and lose the
    # original bytes.
    raw_payload: str = ""


# ---------------------------------------------------------------------------
# §17.1 Deduplicator
# ---------------------------------------------------------------------------

# Rolling window size matches the spec's §17.1 15-minute simulated window.
_DEFAULT_WINDOW_S: float = 900.0   # 15 min × 60 s


class Deduplicator:
    """§17.1 idempotency gate keyed by event_id.

    A 15-minute (900 s) rolling window in simulated time.  Events older than
    the window are evicted on purge() or the next check() call that advances
    the cursor past them.

    Design choice (PROTO-14): store first-seen sim_time, not wall time.
    Simulated time is the authoritative timeline for this codebase; wall time
    is for latency measurement only.
    """

    def __init__(self, window_sim_s: float = _DEFAULT_WINDOW_S) -> None:
        self._window_s = window_sim_s
        self._seen: dict[str, float] = {}   # event_id → first_seen_sim_time

    def is_duplicate(self, event_id: str, sim_time: float) -> bool:
        """Return True if event_id was seen within the rolling window.

        Side-effect: registers the event_id on first sight (not on duplicate).
        Also purges events that have aged out of the window.
        """
        self._purge_before(sim_time - self._window_s)
        if event_id in self._seen:
            return True
        self._seen[event_id] = sim_time
        return False

    def _purge_before(self, cutoff: float) -> None:
        stale = [k for k, v in self._seen.items() if v < cutoff]
        for k in stale:
            del self._seen[k]

    @property
    def seen_count(self) -> int:
        return len(self._seen)


# ---------------------------------------------------------------------------
# §17.2 Quarantine
# ---------------------------------------------------------------------------

@dataclass
class QuarantineRecord:
    event_id:    str
    raw_payload: str    # TEXT — not parsed JSON
    reason:      str
    sim_time:    float
    # Optional parsed JSON sidecar — may be absent if the event was not
    # valid JSON at all.  §17.2 requires the raw bytes be preserved.
    parsed_sidecar: Optional[dict[str, Any]] = None


class Quarantine:
    """§17.2 quarantine store.

    raw_payload is stored as TEXT (not JSON) because a malformed event may
    not be parseable at all.  The optional parsed_sidecar is set when the
    event was syntactically valid JSON but failed domain validation.

    Shared by all ingest classes — one quarantine per run context.
    """

    def __init__(self) -> None:
        self._records: list[QuarantineRecord] = []

    def add(
        self,
        event_id: str,
        raw_payload: str,
        reason: str,
        sim_time: float,
        parsed_sidecar: Optional[dict[str, Any]] = None,
    ) -> None:
        self._records.append(QuarantineRecord(
            event_id=event_id,
            raw_payload=raw_payload,
            reason=reason,
            sim_time=sim_time,
            parsed_sidecar=parsed_sidecar,
        ))

    def all_records(self) -> list[QuarantineRecord]:
        return list(self._records)

    @property
    def count(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# Base ingestor — shared §17.1-17.2 pipeline
# ---------------------------------------------------------------------------

class BaseIngestor:
    """Shared §17.1-17.2 pipeline that all ingest classes extend.

    Subclasses MUST implement validate_domain() — the per-class domain rule
    hook that runs after schema and field-presence checks.

    Pipeline order:
      1. Serialize the record to raw_payload (TEXT — §17.2 store requirement)
      2. §17.1 deduplicate by event_id
      3. validate_domain() — subclass hook
      4. Quarantine on any failure; return IngestStatus.ACCEPTED on success

    The pipeline is synchronous and pure (no I/O, no asyncio).  Call-sites
    that need async wrappers add them in the api/ or runtime/ layers.
    """

    def __init__(
        self,
        deduplicator: Optional[Deduplicator] = None,
        quarantine: Optional[Quarantine] = None,
    ) -> None:
        self._dedup = deduplicator if deduplicator is not None else Deduplicator()
        self._quarantine = quarantine if quarantine is not None else Quarantine()

    @property
    def quarantine(self) -> Quarantine:
        return self._quarantine

    @property
    def deduplicator(self) -> Deduplicator:
        return self._dedup

    def _ingest(self, record: Any, event_id: str, sim_time: float) -> IngestResult:
        """Run the shared pipeline on any record that has an event_id."""
        # Step 1: serialise to TEXT for quarantine store.
        try:
            raw = json.dumps(record if isinstance(record, dict) else vars(record),
                             default=str)
        except Exception:
            raw = repr(record)

        # Step 2: §17.1 idempotency check.
        if self._dedup.is_duplicate(event_id, sim_time):
            return IngestResult(
                status=IngestStatus.DUPLICATE,
                event_id=event_id,
                reason="duplicate event_id within rolling window",
            )

        # Step 3: domain validation hook.
        failure_reason = self.validate_domain(record, sim_time)
        if failure_reason:
            try:
                parsed = record if isinstance(record, dict) else vars(record)
            except Exception:
                parsed = None
            self._quarantine.add(
                event_id=event_id,
                raw_payload=raw,
                reason=failure_reason,
                sim_time=sim_time,
                parsed_sidecar=parsed,
            )
            return IngestResult(
                status=IngestStatus.QUARANTINED,
                event_id=event_id,
                reason=failure_reason,
                raw_payload=raw,
            )

        return IngestResult(status=IngestStatus.ACCEPTED, event_id=event_id)

    def validate_domain(self, record: Any, sim_time: float) -> str:
        """Domain-rule hook.  Return non-empty reason string to quarantine.

        Override in subclasses.  Default accepts everything (useful for tests).
        """
        return ""
