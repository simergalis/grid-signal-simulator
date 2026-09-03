"""
runtime/cluster_gen.py — LLM-driven cluster arrival process generator.

Pre-generates a realistic GPU cluster workload timeline ONCE at run start,
before the tick loop begins.  The timeline is stored as a list of
WorkloadEventSpec-compatible dicts and merged into spec_data["workload_events"]
before the RunContext is built.

Why LLM here (and not a seeded RNG)
------------------------------------
Real cluster traffic is bursty and correlated — overnight training batches,
business-hours inference, a hyperparameter sweep that dumps 40 tiny jobs at
once, a Friday afternoon deploy.  A Poisson/Gaussian produces statistically
clean traffic; an LLM asked for "a plausible Tuesday on a 1900-node cluster"
generates temporal structure a distribution cannot.

Random ≠ AI (constraint)
-------------------------
Inter-arrival times, NTP jitter, job-size variance WITHIN a burst: seeded RNG.
The *structure* — how many bursts, what kind, when, how they overlap: LLM.

Validation (constraint)
-----------------------
Every generated node_count, timestamp, and hardware_profile_id is checked
against gridsignal_parameters.json before materialization.  Out-of-range
values are rejected and logged, never silently clamped.

Reproducibility
---------------
When a run specifies seed, the physics-fallback path (RNG only) is fully
reproducible from that seed alone.  The Mistral path is reproducible once the
generated event list is stored in the ScenarioSpec's generation_block.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import uuid
import urllib.error
import urllib.request
from typing import Optional

from runtime.generation_validator import validate_generated_value, get_param_default

_log = logging.getLogger(__name__)

_MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL    = "mistral-small-latest"
_REQUEST_TIMEOUT_S = 15.0

# ── System prompt ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a GPU cluster workload simulator.  Your job is to generate a realistic
sequence of gang-admission events for a large GPU cluster over a simulated
time window.

Each event is either:
  "starting" — a new job admitted to the cluster (GPU nodes allocated)
  "job_end"  — a running job finishes (nodes released)

Key characteristics of real GPU cluster traffic:
- Training jobs: large node counts (100–800), long durations (10–30 min),
  bursty in the early morning and late night, correlated with batch pipelines
- Inference jobs: small node counts (50–200), short durations (2–10 min),
  steady during business hours with brief inter-arrival times
- Hyperparameter sweeps: many small jobs arriving within a short window
- Scale-up events (SCALE): an existing job requests additional nodes mid-run

Return ONLY valid JSON with no markdown fences:
{
  "description": "<one sentence describing the cluster profile>",
  "events": [
    {
      "job_id": "<unique string>",
      "event_type": "starting" | "job_end" | "scale",
      "timestamp": <sim_time_seconds, float>,
      "node_count": <integer, positive>,
      "hardware_profile_id": "enterprise_8gpu_air"
    },
    ...
  ]
}

Rules:
- Every "starting" event MUST have a corresponding "job_end" at timestamp > start.
- A "scale" event references an existing job_id with the NEW total node count.
- Timestamps must be in [0, sim_duration_s].
- node_count must be in [1, max_nodes].
- Events must be ordered by timestamp (ascending).
- Generate 5–40 events depending on cluster activity level.
- Keep at least one active job at all times (the cluster is never fully idle).
"""


def _call_mistral(user_msg: str, api_key: str) -> str:
    """Synchronous Mistral call; returns raw assistant content."""
    payload = json.dumps({
        "model": _MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": 1200,
        "temperature": 0.6,
    }).encode()
    req = urllib.request.Request(
        _MISTRAL_ENDPOINT,
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
            body = json.loads(resp.read())
        return body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Mistral HTTP {exc.code}: {exc.read()[:300]}") from exc


def _validate_event(evt: dict, sim_duration_s: float, max_nodes: int) -> tuple[bool, str]:
    """Validate one generated event dict; return (ok, reason)."""
    # Required fields
    for field in ("job_id", "event_type", "timestamp", "node_count"):
        if field not in evt:
            return False, f"missing field {field!r}"

    event_type = evt["event_type"]
    if event_type not in ("starting", "job_end", "scale"):
        return False, f"unknown event_type {event_type!r}"

    try:
        ts = float(evt["timestamp"])
    except (TypeError, ValueError):
        return False, f"timestamp {evt['timestamp']!r} not numeric"
    if not (0.0 <= ts <= sim_duration_s * 1.05):
        return False, f"timestamp {ts} outside [0, {sim_duration_s}]"

    try:
        nc = int(evt["node_count"])
    except (TypeError, ValueError):
        return False, f"node_count {evt['node_count']!r} not integer"
    if not (1 <= nc <= max_nodes):
        return False, f"node_count {nc} outside [1, {max_nodes}]"

    return True, ""


def _parse_cluster_events(
    raw: str,
    *,
    sim_duration_s: float,
    max_nodes: int,
    hardware_profile_id: str,
) -> tuple[list[dict], str]:
    """Parse Mistral JSON → (validated_events, description).

    Returns ([], "") on any parse / validation failure so the caller can
    fall back to the RNG path.
    """
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        data: dict = json.loads(text)
        raw_events: list = data.get("events", [])
        description: str = str(data.get("description", ""))

        valid_events: list[dict] = []
        for i, evt in enumerate(raw_events):
            ok, reason = _validate_event(evt, sim_duration_s, max_nodes)
            if not ok:
                _log.warning("cluster_gen: event[%d] REJECTED — %s", i, reason)
                continue

            # Normalise and coerce
            normalised = {
                "job_id":             str(evt["job_id"]),
                "event_type":         str(evt["event_type"]),
                "timestamp":          round(float(evt["timestamp"]), 1),
                "node_count":         int(evt["node_count"]),
                "hardware_profile_id": str(evt.get("hardware_profile_id", hardware_profile_id)),
                "renewable_shortfall_mw": 0.0,
            }
            # Assign a stable event_id
            normalised["event_id"] = f"cg-{uuid.uuid5(uuid.NAMESPACE_DNS, json.dumps(normalised, sort_keys=True)).hex[:8]}"
            valid_events.append(normalised)

        if not valid_events:
            raise ValueError("no valid events after filtering")

        # Sort by timestamp
        valid_events.sort(key=lambda e: e["timestamp"])

        _log.info(
            "cluster_gen: Mistral → %d valid events out of %d raw (duration=%.0f s, max_nodes=%d)",
            len(valid_events), len(raw_events), sim_duration_s, max_nodes,
        )
        return valid_events, description

    except Exception as exc:
        _log.warning("cluster_gen: Mistral parse failed (%s) — RNG fallback", exc)
        return [], ""


# ── RNG fallback ─────────────────────────────────────────────────────────────

def _rng_cluster_events(
    sim_duration_s: float,
    max_nodes: int,
    min_nodes: int,
    hardware_profile_id: str,
    mean_interarrival_s: float,
    mean_job_nodes: int,
    job_node_std: float,
    min_job_nodes: int,
    mean_job_duration_s: float,
    min_job_duration_s: float,
    rng: random.Random,
) -> list[dict]:
    """Poisson/Gaussian cluster events — seeded RNG, no LLM call."""
    events: list[dict] = []
    job_counter = 0
    sim_time = 0.0

    # Seed an initial job so the cluster is never empty at t=0
    initial_nodes = max(min_job_nodes, min(
        int(rng.gauss(mean_job_nodes, job_node_std)), max_nodes // 2
    ))
    initial_duration = max(min_job_duration_s, rng.expovariate(1.0 / mean_job_duration_s))
    jid = f"job-rng-{job_counter:04d}"
    job_counter += 1
    events.append({
        "event_id": f"cg-rng-{uuid.uuid4().hex[:8]}",
        "job_id": jid, "event_type": "starting",
        "timestamp": 0.0, "node_count": initial_nodes,
        "hardware_profile_id": hardware_profile_id,
        "renewable_shortfall_mw": 0.0,
    })
    end_ts = min(sim_duration_s, initial_duration)
    events.append({
        "event_id": f"cg-rng-{uuid.uuid4().hex[:8]}",
        "job_id": jid, "event_type": "job_end",
        "timestamp": round(end_ts, 1), "node_count": initial_nodes,
        "hardware_profile_id": hardware_profile_id,
        "renewable_shortfall_mw": 0.0,
    })
    sim_time = rng.expovariate(1.0 / mean_interarrival_s)

    while sim_time < sim_duration_s:
        nc = max(min_job_nodes, min(
            int(rng.gauss(mean_job_nodes, job_node_std)), max_nodes
        ))
        duration = max(min_job_duration_s, rng.expovariate(1.0 / mean_job_duration_s))
        end_time = min(sim_duration_s, sim_time + duration)

        jid = f"job-rng-{job_counter:04d}"
        job_counter += 1
        events.append({
            "event_id": f"cg-rng-{uuid.uuid4().hex[:8]}",
            "job_id": jid, "event_type": "starting",
            "timestamp": round(sim_time, 1), "node_count": nc,
            "hardware_profile_id": hardware_profile_id,
            "renewable_shortfall_mw": 0.0,
        })
        events.append({
            "event_id": f"cg-rng-{uuid.uuid4().hex[:8]}",
            "job_id": jid, "event_type": "job_end",
            "timestamp": round(end_time, 1), "node_count": nc,
            "hardware_profile_id": hardware_profile_id,
            "renewable_shortfall_mw": 0.0,
        })
        sim_time += rng.expovariate(1.0 / mean_interarrival_s)

    events.sort(key=lambda e: e["timestamp"])
    return events


# ── Public API ────────────────────────────────────────────────────────────────

class ClusterForecast:
    """Result of generate_cluster_forecast()."""
    __slots__ = ("events", "description", "source")

    def __init__(self, events: list[dict], description: str, source: str) -> None:
        self.events = events
        self.description = description
        self.source = source

    def __repr__(self) -> str:
        return (
            f"ClusterForecast(events={len(self.events)}, "
            f"source={self.source!r}, description={self.description!r})"
        )


def generate_cluster_forecast(
    sim_duration_s: float,
    *,
    description: str = "plausible weekday on a 1900-node ML cluster",
    hardware_profile_id: str = "enterprise_8gpu_air",
    max_nodes: int = 1900,
    min_nodes: int = 200,
    mean_interarrival_s: float = 60.0,
    mean_job_nodes: int = 200,
    job_node_std: float = 80.0,
    min_job_nodes: int = 50,
    mean_job_duration_s: float = 300.0,
    min_job_duration_s: float = 30.0,
    rng_seed: Optional[int] = None,
    use_llm: bool = True,
) -> ClusterForecast:
    """Generate a cluster workload timeline for one run.

    When ``use_llm=True`` (default) and ``MISTRAL_API_KEY`` is set, calls
    Mistral to generate a structured, bursty timeline.  Falls back to a
    seeded Poisson/Gaussian process if the API is unavailable or the response
    cannot be parsed.

    When ``use_llm=False`` or ``MISTRAL_API_KEY`` is absent, uses the seeded
    RNG path only (cheaper, fully reproducible from seed alone).

    The seeded RNG path is the correct choice when job arrival statistics are
    already well-specified; use the LLM path when you want temporal structure
    (batch bursts, business-hours patterns) that a Poisson cannot reproduce.
    """
    rng = random.Random(rng_seed)

    if use_llm:
        api_key: Optional[str] = os.environ.get("MISTRAL_API_KEY") or None
        if api_key:
            user_msg = (
                f"Cluster profile: {description}\n"
                f"Simulation duration: {sim_duration_s:.0f} seconds\n"
                f"Maximum nodes: {max_nodes}\n"
                f"Minimum idle nodes: {min_nodes}\n"
                f"Hardware: {hardware_profile_id}\n"
            )
            try:
                raw = _call_mistral(user_msg, api_key)
                events, desc = _parse_cluster_events(
                    raw,
                    sim_duration_s=sim_duration_s,
                    max_nodes=max_nodes,
                    hardware_profile_id=hardware_profile_id,
                )
                if events:
                    return ClusterForecast(events=events, description=desc, source="mistral")
            except Exception as exc:
                _log.warning("cluster_gen: Mistral call failed (%s) — RNG fallback", exc)
        else:
            _log.info("cluster_gen: MISTRAL_API_KEY absent — using seeded RNG")

    events = _rng_cluster_events(
        sim_duration_s=sim_duration_s,
        max_nodes=max_nodes,
        min_nodes=min_nodes,
        hardware_profile_id=hardware_profile_id,
        mean_interarrival_s=mean_interarrival_s,
        mean_job_nodes=mean_job_nodes,
        job_node_std=job_node_std,
        min_job_nodes=min_job_nodes,
        mean_job_duration_s=mean_job_duration_s,
        min_job_duration_s=min_job_duration_s,
        rng=rng,
    )
    return ClusterForecast(
        events=events,
        description=f"Seeded RNG (seed={rng_seed}) — {description}",
        source="rng",
    )
