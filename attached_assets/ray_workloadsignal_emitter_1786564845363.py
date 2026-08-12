"""
ray_workloadsignal_emitter.py

Minimal reference implementation of a GridSignal WorkloadSignal emitter for
Ray. Hooks two independent sources:

  1. The Ray Jobs API, polled for status transitions -> queued / starting /
     running / job_end / cancelled / scale.
  2. Ray Train checkpoint callbacks -> checkpoint_start / checkpoint_end.

This is adapter-layer code, not part of the GridSignal engine. It produces
events conforming to Section 10 of the Forecast Engine Functional Spec and
is responsible for everything the spec explicitly leaves to the adapter:
event_id generation, hardware_profile_id mapping, and node_count derivation.

Requires: pip install ray requests ulid-py
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests
import ulid
from ray.job_submission import JobSubmissionClient, JobStatus

logger = logging.getLogger("workloadsignal_emitter")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GRIDSIGNAL_INGEST_URL = "https://ingest.gridsgnl.com/v1/workload-signal"
SITE_ID = "site-us-east-04"
POLL_INTERVAL_SECONDS = 5

# Adapter-owned mapping from Ray's reported accelerator_type to GridSignal's
# hardware profile library (Section 5). Unmapped values must fall through
# to the Section 5.1 fallback profile rather than raise -- a missing entry
# here is an integration gap, not a reason to drop the event.
ACCELERATOR_TO_PROFILE = {
    "H100": "nvidia-h100-sxm5-8way",
    "A100": "nvidia-a100-sxm4-8way",
    "H200": "nvidia-h200-sxm5-8way",
}
FALLBACK_PROFILE_ID = "unmapped-fallback"

# Ray JobStatus -> WorkloadSignal event_type. Ray has no native concept of
# "starting" vs "running" as distinct states, so the emitter tracks whether
# this is the first RUNNING observation for a given job_id.
_STATUS_TO_EVENT_TYPE = {
    JobStatus.PENDING: "queued",
    JobStatus.STOPPED: "cancelled",
    JobStatus.SUCCEEDED: "job_end",
    JobStatus.FAILED: "job_end",
}


@dataclass
class _JobState:
    last_status: Optional[JobStatus] = None
    seen_running: bool = False
    last_node_count: int = 0


class WorkloadSignalEmitter:
    def __init__(
        self,
        ray_dashboard_address: str,
        ingest_url: str = GRIDSIGNAL_INGEST_URL,
        site_id: str = SITE_ID,
        session: Optional[requests.Session] = None,
    ):
        self._client = JobSubmissionClient(ray_dashboard_address)
        self._ingest_url = ingest_url
        self._site_id = site_id
        self._session = session or requests.Session()
        self._job_states: dict[str, _JobState] = {}

    # -- Public entry points -------------------------------------------------

    def poll_once(self) -> None:
        """Single polling pass over all jobs known to the Ray cluster."""
        for job_details in self._client.list_jobs():
            self._process_job(job_details)

    def run_forever(self, interval_seconds: int = POLL_INTERVAL_SECONDS) -> None:
        while True:
            try:
                self.poll_once()
            except Exception:
                logger.exception("poll cycle failed; continuing")
            time.sleep(interval_seconds)

    def emit_checkpoint_start(self, job_id: str, hardware_profile_id: str, node_count: int) -> None:
        self._emit(job_id, "checkpoint_start", hardware_profile_id, node_count)

    def emit_checkpoint_end(self, job_id: str, hardware_profile_id: str, node_count: int) -> None:
        self._emit(job_id, "checkpoint_end", hardware_profile_id, node_count)

    # -- Internals -------------------------------------------------------------

    def _process_job(self, job_details) -> None:
        job_id = job_details.submission_id
        status = job_details.status
        state = self._job_states.setdefault(job_id, _JobState())

        hardware_profile_id = self._resolve_hardware_profile(job_details)
        node_count = self._resolve_node_count(job_details)

        event_type = self._derive_event_type(state, status, node_count)
        if event_type is None:
            return  # No state change worth emitting.

        self._emit(job_id, event_type, hardware_profile_id, node_count)

        state.last_status = status
        state.last_node_count = node_count
        if status == JobStatus.RUNNING:
            state.seen_running = True

    def _derive_event_type(
        self, state: _JobState, status: JobStatus, node_count: int
    ) -> Optional[str]:
        if status == JobStatus.RUNNING:
            if not state.seen_running:
                return "starting"
            if node_count != state.last_node_count:
                return "scale"
            return None  # steady-state RUNNING with no change: don't re-emit
        if status == state.last_status:
            return None  # already reported this terminal/queued state
        return _STATUS_TO_EVENT_TYPE.get(status)

    def _resolve_hardware_profile(self, job_details) -> str:
        accel = getattr(job_details, "entrypoint_resources", {}) or {}
        accel_type = accel.get("accelerator_type")
        return ACCELERATOR_TO_PROFILE.get(accel_type, FALLBACK_PROFILE_ID)

    def _resolve_node_count(self, job_details) -> int:
        # Reference implementation: count workers reported in job metadata.
        # A production adapter should cross-check against ray.nodes() /
        # cluster resource state rather than trusting job metadata alone.
        return int(getattr(job_details, "metadata", {}).get("node_count", 1))

    def _emit(
        self,
        job_id: str,
        event_type: str,
        hardware_profile_id: str,
        node_count: int,
        workload_class: str = "training",
    ) -> None:
        payload = {
            "job_id": job_id,
            "event_id": str(ulid.new()),  # producer-assigned, globally unique
            "event_type": event_type,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "hardware_profile_id": hardware_profile_id,
            "node_count": node_count,
            "workload_class": workload_class,
            "site_id": self._site_id,
        }
        try:
            resp = self._session.post(self._ingest_url, json=payload, timeout=5)
            if resp.status_code >= 400:
                # Per Section 17.2, a 4xx here means the event was quarantined
                # with a structured rejection body -- log it, don't retry blindly.
                logger.warning(
                    "WorkloadSignal rejected (%s): %s", resp.status_code, resp.text
                )
        except requests.RequestException:
            logger.exception("failed to deliver WorkloadSignal event_id=%s", payload["event_id"])


# ---------------------------------------------------------------------------
# Ray Train checkpoint hook (sketch)
# ---------------------------------------------------------------------------
#
# Wire this into a Ray Train callback (e.g. a custom `ray.train.UserCallback`
# or the reporting hook around `train.report(..., checkpoint=...)`) so that
# checkpoint_start fires immediately before the checkpoint write begins and
# checkpoint_end fires once it's durably written. Without this hook, checkpoint
# events never reach GridSignal and Section 6.2's checkpoint-valley
# classification falls back to the power-shape heuristic for this job.
#
# emitter = WorkloadSignalEmitter(ray_dashboard_address="http://127.0.0.1:8265")
# emitter.emit_checkpoint_start(job_id, hardware_profile_id, node_count)
# ... perform checkpoint write ...
# emitter.emit_checkpoint_end(job_id, hardware_profile_id, node_count)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    emitter = WorkloadSignalEmitter(ray_dashboard_address="http://127.0.0.1:8265")
    emitter.run_forever()
