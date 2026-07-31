"""
core/corroboration.py — §25 Fabric-to-scheduler corroboration record.

Step 14.

For each predicted job start (from WorkloadSignal events), the corroboration
record tracks whether a corresponding fabric traffic rise was observed within
the expected window.

TC-51: A scheduler checkpoint_start event is AUTHORITATIVE.  Fabric evidence
  (a traffic rise in NetworkTelemetry) cannot override a checkpoint_start.
  Once a checkpoint_start is recorded for a job, the corroboration result is
  "authoritative_start" and subsequent fabric evidence only updates the
  fabric_rise_observed field — it cannot change the authoritative result.

TC-50: Fabric traffic rising sharply with NO preceding WorkloadSignal produces
  NO forecast change and NO staging action — only a missed-job corroboration
  finding.  The FabricCorroborator is a read-only observer of NetworkTelemetry;
  it never writes to SimulationState.

TC-73: Fabric corroboration does NOT count toward the §17.3 reconciliation
  threshold.  Throughput is not a magnitude proxy — a traffic rise cannot
  substitute for a WorkloadSignal in the §17.3 "distinct step-load events"
  count.  reconciliation_count is incremented only by WorkloadSignal events,
  never by NetworkTelemetry records.

Architecture invariant
----------------------
FabricCorroborator is a pure observer — it has no reference to SimulationState
and cannot modify the forecast or dispatch path.  This guarantees TC-50 at
the architecture level, not just by convention.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.network_telemetry import NetworkTelemetry


# ---------------------------------------------------------------------------
# Corroboration result states
# ---------------------------------------------------------------------------

class CorroborationResult(str, Enum):
    PENDING              = "pending"               # waiting for evidence or window expiry
    CORROBORATED         = "corroborated"          # fabric rise observed in window
    MISSED               = "missed"                # window expired, no fabric rise
    AUTHORITATIVE_START  = "authoritative_start"   # checkpoint_start received (TC-51)


# ---------------------------------------------------------------------------
# Corroboration record
# ---------------------------------------------------------------------------

@dataclass
class CorroborationRecord:
    """Per-job corroboration tracking.

    One record per predicted job start.  Updated by:
      1. register_predicted_start()  — creates the record (PENDING)
      2. apply_checkpoint_start()    — marks authoritative (TC-51)
      3. ingest_telemetry()          — tries to match a fabric traffic rise

    TC-51: once authoritative_event is set ("checkpoint_start"), the
    result field becomes "authoritative_start" and cannot be overwritten
    by fabric evidence.
    """
    job_id:                  str
    predicted_start_sim_time: float
    # Window during which a fabric traffic rise counts as corroboration.
    corroboration_window_s:  float = 30.0    # CHOSEN (PROTO-15): 30 s window

    # Set when a checkpoint_start event arrives (TC-51 — authoritative).
    authoritative_event: Optional[str] = None   # "checkpoint_start" when set

    # Set when a fabric traffic rise is observed.
    fabric_rise_observed:    bool  = False
    fabric_rise_sim_time:    Optional[float] = None

    # Final result.
    result: CorroborationResult = CorroborationResult.PENDING

    def mark_authoritative_start(self, sim_time: float) -> None:
        """TC-51: checkpoint_start is authoritative; result becomes fixed."""
        self.authoritative_event = "checkpoint_start"
        self.result = CorroborationResult.AUTHORITATIVE_START

    def try_corroborate_from_fabric(self, sim_time: float) -> bool:
        """Record a fabric traffic rise.  TC-51: does NOT override authoritative result."""
        self.fabric_rise_observed = True
        self.fabric_rise_sim_time = sim_time
        # TC-51: if authoritative_event is set, do not change the result.
        if self.authoritative_event is not None:
            return False
        # Only corroborate if we are still within the expected window.
        if sim_time <= self.predicted_start_sim_time + self.corroboration_window_s:
            self.result = CorroborationResult.CORROBORATED
            return True
        return False

    def expire_if_pending(self, sim_time: float) -> bool:
        """Mark as MISSED if window has elapsed and still PENDING."""
        if (self.result == CorroborationResult.PENDING
                and sim_time > self.predicted_start_sim_time + self.corroboration_window_s):
            self.result = CorroborationResult.MISSED
            return True
        return False


# ---------------------------------------------------------------------------
# Corroboration finding (emitted for unmatched fabric rises)
# ---------------------------------------------------------------------------

@dataclass
class FabricFinding:
    """A fabric traffic rise with no matching predicted job start.

    TC-50: produces no forecast change and no staging action — only this
    informational finding.
    """
    switch_id:       str
    interface_id:    str
    sim_time:        float
    throughput_bps:  float
    finding_type:    str = "unmatched_fabric_rise"   # TC-50 label


# ---------------------------------------------------------------------------
# FabricCorroborator
# ---------------------------------------------------------------------------

class FabricCorroborator:
    """Pure-observer corroboration tracker.

    Tracks predicted job starts and matches them against fabric traffic rises
    in NetworkTelemetry records.

    Architecture guarantees:
      • No reference to SimulationState — cannot modify the forecast path.
      • No call to evaluate_tick() or any dispatch function.
      • TC-73: reconciliation_count is NEVER incremented by telemetry.

    Traffic rise detection: a record is considered a "rise" when its
    throughput_rx_bps exceeds TRAFFIC_RISE_THRESHOLD_BPS.  This is a
    simplification (PROTO-15); a real system would compare against a rolling
    baseline.
    """

    # Simplistic threshold: a fabric record is a "rise" if RX throughput
    # exceeds this value.  CHOSEN (PROTO-15) — no measured basis.
    TRAFFIC_RISE_THRESHOLD_BPS: float = 1e9   # 1 Gbps

    def __init__(self) -> None:
        self._records: dict[str, CorroborationRecord] = {}   # job_id → record
        # TC-73: reconciliation_count is incremented by WorkloadSignal events only.
        self._reconciliation_count: int = 0
        self._findings: list[FabricFinding] = []

    @property
    def reconciliation_count(self) -> int:
        """TC-73: fabric telemetry NEVER increments this counter.

        Only WorkloadSignal events (via advance_reconciliation_count()) do.
        """
        return self._reconciliation_count

    def advance_reconciliation_count(self) -> None:
        """Record one §17.3-qualifying WorkloadSignal event.

        Called by the WorkloadSignal processing path.  NEVER called from
        the NetworkTelemetry path — that would violate TC-73.
        """
        self._reconciliation_count += 1

    def register_predicted_start(
        self,
        job_id: str,
        sim_time: float,
        corroboration_window_s: float = 30.0,
    ) -> CorroborationRecord:
        """Register a predicted job start; creates a PENDING record."""
        record = CorroborationRecord(
            job_id=job_id,
            predicted_start_sim_time=sim_time,
            corroboration_window_s=corroboration_window_s,
        )
        self._records[job_id] = record
        return record

    def apply_checkpoint_start(self, job_id: str, sim_time: float) -> None:
        """TC-51: checkpoint_start is authoritative.

        If a record exists for this job_id, it is marked as authoritative.
        If no predicted record exists (job came from the scheduler, not a
        WorkloadSignal prediction), we create one so the audit trail is complete.
        """
        if job_id not in self._records:
            self._records[job_id] = CorroborationRecord(
                job_id=job_id,
                predicted_start_sim_time=sim_time,
            )
        self._records[job_id].mark_authoritative_start(sim_time)

    def ingest_telemetry(
        self,
        telemetry: NetworkTelemetry,
        sim_time: Optional[float] = None,
    ) -> Optional[FabricFinding]:
        """Process a NetworkTelemetry record.

        TC-50: if no predicted start matches this traffic rise, emit a
        FabricFinding.  NO forecast change.  NO staging action.

        TC-73: reconciliation_count is NOT incremented here.

        Returns a FabricFinding if the rise is unmatched, or None if it
        was matched to a predicted job start.
        """
        effective_time = sim_time if sim_time is not None else telemetry.timestamp

        # Check for a traffic rise.
        is_rise = telemetry.throughput_rx_bps > self.TRAFFIC_RISE_THRESHOLD_BPS

        if not is_rise:
            return None

        # Expire stale pending records.
        for record in list(self._records.values()):
            record.expire_if_pending(effective_time)

        # Try to match the rise to a pending predicted start.
        matched = False
        for record in self._records.values():
            if record.result in (
                CorroborationResult.PENDING,
                CorroborationResult.AUTHORITATIVE_START,
            ):
                record.try_corroborate_from_fabric(effective_time)
                matched = True
                break

        # TC-50: no match → emit FabricFinding, no forecast change.
        if not matched:
            finding = FabricFinding(
                switch_id=telemetry.switch_id,
                interface_id=telemetry.interface_id,
                sim_time=effective_time,
                throughput_bps=telemetry.throughput_rx_bps,
                finding_type="unmatched_fabric_rise",
            )
            self._findings.append(finding)
            return finding

        return None

    def get_record(self, job_id: str) -> Optional[CorroborationRecord]:
        return self._records.get(job_id)

    def all_records(self) -> list[CorroborationRecord]:
        return list(self._records.values())

    def all_findings(self) -> list[FabricFinding]:
        """TC-50: unmatched fabric rise findings (informational only)."""
        return list(self._findings)
