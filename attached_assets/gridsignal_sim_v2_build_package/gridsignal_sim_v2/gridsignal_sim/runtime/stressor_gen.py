"""
runtime/stressor_gen.py — LLM-driven fault and stressor timeline generator.

Pre-generates a compound fault / stressor event sequence ONCE at run start,
before the tick loop begins.  Results are merged into spec_data["workload_events"]
as SOLAR_STEP events (renewable curtailment / cloud front) and stored in the
generation_block for replay.

Why LLM here
------------
Compound failures are hard to specify by hand: "cloud front arrives, inverter
trips 90 seconds later, ambient spikes".  LLMs compose plausible correlated
sequences that a hand-written scenario library under-represents — exactly the
failure modes that stress test coverage misses.

What is representable now
--------------------------
The existing WorkloadEventSpec supports SOLAR_STEP events (renewable shortfall)
which model cloud fronts and inverter/solar-array trips.  These are the stressors
generated here.  Turbine trips and PMS shed events require additional injection
mechanisms; when those mechanisms exist, this generator's output format expands
to include them.

Constraints
-----------
- All timestamps validated before materialization
- renewable_shortfall_mw validated against solar_rated_mw (never exceeds it)
- RNG fallback when MISTRAL_API_KEY absent or call fails
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

_log = logging.getLogger(__name__)

_MISTRAL_ENDPOINT  = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL     = "mistral-small-latest"
_REQUEST_TIMEOUT_S = 12.0

_SYSTEM_PROMPT = """\
You are a grid-edge stressor scenario author for a solar+BESS+turbine microgrid.
Your job is to compose realistic compound stress events over a simulation window.

You can generate SOLAR_STEP events — sudden drops in renewable output caused by:
  - cloud fronts sweeping through (gradual over 20–120 s, maybe partial recovery)
  - inverter trips (sudden, partial or full loss of a string)
  - grid transients that cause a brief dip

Each event has:
  - "job_id": unique label (e.g. "cloud-front-1", "inverter-trip-a")
  - "event_type": always "solar_step"
  - "timestamp": when the event fires (sim_time_s)
  - "renewable_shortfall_mw": how much MW is lost at this moment (positive float)
  - "node_count": always 0

Compose 2–8 events. Events can cascade (inverter trip occurs 90 s after cloud
arrival; partial recovery at +60 s). Make them physically plausible.

Return ONLY valid JSON with no markdown fences:
{
  "description": "<one sentence describing the compound scenario>",
  "events": [
    {
      "job_id": "<label>",
      "event_type": "solar_step",
      "timestamp": <float>,
      "renewable_shortfall_mw": <float, 0.0–max_solar_mw>,
      "node_count": 0
    },
    ...
  ]
}

Rules:
- Timestamps in [0, sim_duration_s].
- renewable_shortfall_mw in [0.0, max_solar_mw].
- Order events by timestamp ascending.
- At least one event must have renewable_shortfall_mw > 0.2 × max_solar_mw
  (a meaningfully stressful event, not just noise).
"""


def _call_mistral(user_msg: str, api_key: str) -> str:
    payload = json.dumps({
        "model":        _MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens":  600,
        "temperature": 0.7,
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


def _parse_stressor_events(
    raw: str,
    *,
    sim_duration_s: float,
    max_solar_mw: float,
) -> tuple[list[dict], str]:
    """Parse Mistral response → (validated_events, description)."""
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()

        data: dict = json.loads(text)
        raw_events: list = data.get("events", [])
        description = str(data.get("description", ""))

        valid: list[dict] = []
        for i, evt in enumerate(raw_events):
            if evt.get("event_type") != "solar_step":
                _log.warning("stressor_gen: event[%d] REJECTED — event_type must be solar_step", i)
                continue
            try:
                ts = float(evt["timestamp"])
            except (TypeError, ValueError, KeyError):
                _log.warning("stressor_gen: event[%d] REJECTED — invalid timestamp", i)
                continue
            if not (0.0 <= ts <= sim_duration_s * 1.05):
                _log.warning("stressor_gen: event[%d] REJECTED — timestamp %.1f outside sim", i, ts)
                continue
            try:
                shortfall = float(evt["renewable_shortfall_mw"])
            except (TypeError, ValueError, KeyError):
                _log.warning("stressor_gen: event[%d] REJECTED — invalid renewable_shortfall_mw", i)
                continue
            if not (0.0 <= shortfall <= max_solar_mw * 1.05):
                _log.warning(
                    "stressor_gen: event[%d] REJECTED — shortfall %.2f MW exceeds max %.2f MW",
                    i, shortfall, max_solar_mw,
                )
                continue
            shortfall = min(shortfall, max_solar_mw)  # hard clamp at ceiling
            job_id = str(evt.get("job_id", f"stressor-{i}"))
            valid.append({
                "event_id": f"sg-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{job_id}-{ts:.1f}').hex[:8]}",
                "job_id":                  job_id,
                "event_type":              "solar_step",
                "timestamp":               round(ts, 1),
                "node_count":              0,
                "hardware_profile_id":     "enterprise_8gpu_air",
                "renewable_shortfall_mw":  round(shortfall, 3),
            })

        if not valid:
            raise ValueError("no valid stressor events after filtering")

        valid.sort(key=lambda e: e["timestamp"])
        _log.info(
            "stressor_gen: Mistral → %d valid events / %d raw", len(valid), len(raw_events)
        )
        return valid, description

    except Exception as exc:
        _log.warning("stressor_gen: Mistral parse failed (%s) — RNG fallback", exc)
        return [], ""


def _rng_stressor_events(
    sim_duration_s: float,
    max_solar_mw: float,
    n_events: int,
    rng: random.Random,
) -> list[dict]:
    """Simple seeded RNG stressor fallback: random cloud fronts."""
    if max_solar_mw <= 0.0:
        return []
    events: list[dict] = []
    for i in range(n_events):
        ts = rng.uniform(sim_duration_s * 0.1, sim_duration_s * 0.9)
        shortfall = rng.uniform(max_solar_mw * 0.15, max_solar_mw * 0.70)
        events.append({
            "event_id":               f"sg-rng-{uuid.uuid4().hex[:8]}",
            "job_id":                 f"cloud-rng-{i}",
            "event_type":             "solar_step",
            "timestamp":              round(ts, 1),
            "node_count":             0,
            "hardware_profile_id":    "enterprise_8gpu_air",
            "renewable_shortfall_mw": round(shortfall, 3),
        })
    events.sort(key=lambda e: e["timestamp"])
    return events


# ── Public API ────────────────────────────────────────────────────────────────

class StressorForecast:
    """Result of generate_stressor_forecast()."""
    __slots__ = ("events", "description", "source")

    def __init__(self, events: list[dict], description: str, source: str) -> None:
        self.events      = events
        self.description = description
        self.source      = source

    def __repr__(self) -> str:
        return (
            f"StressorForecast(events={len(self.events)}, "
            f"source={self.source!r})"
        )


def generate_stressor_forecast(
    sim_duration_s: float,
    *,
    description: str = "compound cloud-front and inverter-trip scenario",
    max_solar_mw: float = 0.0,
    rng_seed: Optional[int] = None,
    n_rng_events: int = 3,
    use_llm: bool = True,
) -> StressorForecast:
    """Generate a compound stressor timeline for one run.

    When ``max_solar_mw <= 0`` there is no solar asset to stress and an empty
    list is returned regardless of configuration.

    When ``use_llm=True`` and ``MISTRAL_API_KEY`` is present, Mistral composes
    correlated fault events.  Falls back to seeded RNG on failure.
    """
    if max_solar_mw <= 0.0:
        return StressorForecast(events=[], description="no solar asset", source="none")

    rng = random.Random(rng_seed)

    if use_llm:
        api_key: Optional[str] = os.environ.get("MISTRAL_API_KEY") or None
        if api_key:
            user_msg = (
                f"Scenario profile: {description}\n"
                f"Simulation duration: {sim_duration_s:.0f} seconds\n"
                f"Solar rated capacity: {max_solar_mw:.2f} MW\n"
            )
            try:
                raw = _call_mistral(user_msg, api_key)
                events, desc = _parse_stressor_events(
                    raw,
                    sim_duration_s=sim_duration_s,
                    max_solar_mw=max_solar_mw,
                )
                if events:
                    return StressorForecast(events=events, description=desc, source="mistral")
            except Exception as exc:
                _log.warning("stressor_gen: Mistral call failed (%s) — RNG fallback", exc)
        else:
            _log.info("stressor_gen: MISTRAL_API_KEY absent — using seeded RNG")

    events = _rng_stressor_events(sim_duration_s, max_solar_mw, n_rng_events, rng)
    return StressorForecast(
        events=events,
        description=f"Seeded RNG (seed={rng_seed}) — {description}",
        source="rng",
    )
