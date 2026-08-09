"""
api/routes/ai.py — AI-assisted scenario copy generation.

POST /api/ai/improve-description
  Takes the current demo copy draft plus scenario metadata and calls Mistral
  to write / improve the operator-facing "What this demonstrates" blurb shown
  in the DemoBar.  Falls back to a 502 with a clear message when the key is absent.

POST /api/ai/explain-scenario
  Takes scenario parameters and calls Claude (Anthropic) to generate a rich,
  plain-English educational explanation for new-hire operators:  what physical
  processes are at play, what to watch on screen, and what GridSignal is doing.
  Falls back to 502 when ANTHROPIC_API_KEY is absent.
"""

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

_MISTRAL_ENDPOINT = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL    = "mistral-small-latest"
_TIMEOUT_S        = 15

_SYSTEM_PROMPT = (
    "You are writing operator-facing presentation copy for an energy grid simulation dashboard. "
    "Write exactly 2 short, clear sentences (combined max 220 characters) that explain what "
    "this simulation scenario demonstrates to a non-technical operations manager watching it "
    "live on screen. Focus on the key behaviour the scenario shows — prediction, staging, "
    "reserves, or whatever makes it interesting. Use plain, confident language. "
    "Return only the 2 sentences, no headings, no bullets, no quotes, no preamble."
)


# ── Request / response models ─────────────────────────────────────────────────

class ImproveRequest(BaseModel):
    text: str                       # current draft (may be empty)
    scenario_name: str = ""
    scenario_description: str = ""  # technical spec description


class ImproveResponse(BaseModel):
    improved: str


# ── Mistral helper (blocking — run in thread pool) ────────────────────────────

def _call_mistral(name: str, description: str, draft: str, api_key: str) -> str:
    parts: list[str] = []
    if name:
        parts.append(f"Scenario name: {name}")
    if description:
        parts.append(f"Technical description: {description}")
    if draft:
        parts.append(f"Current draft copy (improve or rewrite): {draft}")
    if not parts:
        parts.append("No details provided — write a brief generic grid simulation description.")
    user_msg = "\n".join(parts) + "\n\nWrite the 2-sentence operator copy:"

    payload = json.dumps({
        "model": _MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": 300,
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
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = json.loads(resp.read())
        return body["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Mistral HTTP {exc.code}: {exc.read()[:200]}") from exc


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/improve-description", response_model=ImproveResponse)
async def improve_description(req: ImproveRequest) -> ImproveResponse:
    """Call Mistral to write or improve the scenario's demo-bar copy."""
    api_key = os.environ.get("MISTRAL_API_KEY") or ""
    if not api_key:
        raise HTTPException(503, detail="MISTRAL_API_KEY is not configured on this server.")

    try:
        improved = await asyncio.get_event_loop().run_in_executor(
            None,
            _call_mistral,
            req.scenario_name,
            req.scenario_description,
            req.text,
            api_key,
        )
    except Exception as exc:
        log.warning("ai: improve-description failed: %s", exc)
        raise HTTPException(502, detail=f"AI call failed: {exc}") from exc

    return ImproveResponse(improved=improved)


# ── /explain-scenario — Claude educational narration ─────────────────────────

_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_MODEL    = "claude-haiku-4-5"

_DEMONSTRATES_SYSTEM = (
    "You are an expert energy operations trainer writing the 'WHAT THIS DEMONSTRATES' "
    "panel for new-hire operators watching a live data centre power simulation on screen. "
    "Write exactly 5 sentences in plain, vivid English covering ALL of the following:\n\n"
    "  Sentence 1 — what physical situation or crisis this scenario recreates.\n"
    "  Sentence 2 — why the Compute Racks tile rises in incremental pulses rather than a single jump: "
    "GPU jobs are admitted in waves by the Kubernetes scheduler — each wave of nodes powers up together, "
    "creating a staircase of demand. Explain this clearly for someone who has never seen it before.\n"
    "  Sentence 3 — what to observe about power production: which sources (gas turbines, solar PV, "
    "BESS battery) are contributing, how their MW outputs shift in response to each compute pulse, "
    "and what the colour or movement of the tiles signals.\n"
    "  Sentence 4 — what GridSignal is actively doing to improve overall performance: how far ahead "
    "it pre-stages generation (the lead time), how it sequences turbine ramp and battery dispatch to "
    "keep voltage stable across every pulse, and how it avoids over- or under-shooting supply.\n"
    "  Sentence 5 — what would go wrong without GridSignal (frequency dip, thermal overload, or "
    "emergency load-shedding) and what that would mean for the GPU jobs running at the time.\n\n"
    "Use accessible language. Define any jargon inline the first time "
    "(e.g. 'BESS — the on-site battery storage', 'frequency — the heartbeat of the power grid'). "
    "No headings, no bullets, no markdown. Do NOT start with or include the phrase "
    "'WHAT THIS DEMONSTRATES' anywhere in your response. "
    "Return only the 5 sentences as a single paragraph."
)

_WATCHING_SYSTEM = (
    "You are an expert energy operations trainer writing the 'WHAT YOU ARE WATCHING' "
    "panel shown to new-hire operators while a live data centre power simulation runs on screen. "
    "The simulation has just started. Write exactly 4 sentences in plain, vivid, present-tense English:\n\n"
    "  Sentence 1 — what is happening right now in this specific scenario: what the compute demand "
    "profile looks like (how it ramps, holds, and releases), and what the total peak load will be.\n"
    "  Sentence 2 — what the operator will see on the Compute Racks tile: describe the staircase "
    "of GPU node waves being admitted by the Kubernetes scheduler and why each pulse appears.\n"
    "  Sentence 3 — what the power sources are doing in response: which turbines are committing, "
    "how the BESS (battery) is bridging each gap, and what role solar is playing.\n"
    "  Sentence 4 — what GridSignal is doing in the background to keep the site stable: "
    "the lead time it uses to pre-stage generation, how it sequences turbine start-up and "
    "battery dispatch, and what success looks like (no frequency excursion, no load-shed).\n\n"
    "Use present tense throughout ('the turbines are committing', 'the battery is bridging'). "
    "Use accessible language. Define any jargon inline the first time. "
    "No headings, no bullets, no markdown. Do NOT start with 'WHAT YOU ARE WATCHING'. "
    "Return only the 4 sentences as a single paragraph."
)


class ExplainRequest(BaseModel):
    scenario_name: str = ""
    scenario_description: str = ""
    turbine_count: int = 0
    turbine_rated_mw: float = 0.0
    bess_rated_mw: float = 0.0
    bess_usable_mwh: float = 0.0
    solar_rated_mw: float = 0.0
    node_count_max: int = 0
    run_duration_s: int = 300
    island_mode: bool = True
    dt_lead_seconds: float = 60.0
    demo_description: str = ""
    mode: str = "demonstrates"   # "demonstrates" (idle) | "watching" (run active)


class ExplainResponse(BaseModel):
    explanation: str


def _call_anthropic_explain(req: ExplainRequest, api_key: str) -> str:  # noqa: C901
    parts = []
    if req.scenario_name:
        parts.append(f"Scenario: {req.scenario_name}")
    if req.scenario_description:
        parts.append(f"Description: {req.scenario_description}")
    if req.demo_description:
        parts.append(f"Demo copy hint: {req.demo_description}")
    parts.append(
        f"Fleet: {req.turbine_count} gas turbine{'s' if req.turbine_count != 1 else ''} "
        f"× {req.turbine_rated_mw:.0f} MW each · "
        f"BESS {req.bess_rated_mw:.0f} MW / {req.bess_usable_mwh:.0f} MWh · "
        f"Solar {req.solar_rated_mw:.2f} MW rated"
    )
    parts.append(
        f"Workload: up to {req.node_count_max} GPU nodes · "
        f"run lasts {req.run_duration_s} s · "
        f"GridSignal lead time {req.dt_lead_seconds:.0f} s · "
        f"{'islanded (no grid connection)' if req.island_mode else 'grid-connected'}"
    )
    user_msg = "\n".join(parts) + "\n\nWrite the 4-sentence educational paragraph:"

    system_prompt = _WATCHING_SYSTEM if req.mode == "watching" else _DEMONSTRATES_SYSTEM

    payload = json.dumps({
        "model": _ANTHROPIC_MODEL,
        "max_tokens": 400,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_msg}],
    }).encode()

    req_http = urllib.request.Request(
        _ANTHROPIC_ENDPOINT,
        data=payload,
        headers={
            "Content-Type":    "application/json",
            "x-api-key":       api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req_http, timeout=20) as resp:
            body = json.loads(resp.read())
        return body["content"][0]["text"].strip()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Anthropic HTTP {exc.code}: {exc.read()[:200]}") from exc


# ── /scheduler-summary — Claude layman's summary of the Scheduler Feed ───────

_SUMMARY_SYSTEM = (
    "You are explaining a live data-centre power grid simulation to a non-technical "
    "audience — think of them as an intelligent executive who has never seen a power "
    "dashboard before.\n\n"
    "You will receive:\n"
    "  1. A chronological 'Scheduler Feed' log — events showing GPU job admissions, "
    "turbine start-ups, battery (BESS) activity, and power-cap pauses.\n"
    "  2. Current live sensor readings from the simulation.\n\n"
    "Write a clear, friendly summary (4–6 sentences, single paragraph) covering:\n"
    "  · What happened in order — what jobs ran, what the turbines and battery did.\n"
    "  · How the system is performing right now — comfortable or stressed?\n"
    "  · Any anomalies — unserved loads, power caps, admission stalls, frequency drift.\n"
    "  · One sentence on what this means operationally for the data centre.\n\n"
    "Rules:\n"
    "  · Plain English only — no bullet lists, no headings, no markdown.\n"
    "  · Convert MW to something relatable when it helps "
    "(e.g. '15 MW — enough to power about 12,000 homes').\n"
    "  · Define any technical term the first time you use it.\n"
    "  · Be honest: if the feed is empty or data is sparse, say so.\n"
    "  · Single paragraph, 4–6 sentences."
)


class SchedulerSummaryRequest(BaseModel):
    feed_entries: list[dict] = []   # [{ts: str, body: str}, ...]
    tick: dict | None = None        # full current tick snapshot


class SchedulerSummaryResponse(BaseModel):
    summary: str


def _call_anthropic_summary(req_data: "SchedulerSummaryRequest", api_key: str) -> str:
    parts: list[str] = []

    # Feed log
    if req_data.feed_entries:
        lines = "\n".join(
            f"  {e.get('ts', '?')}  {e.get('body', '')}"
            for e in req_data.feed_entries
        )
        parts.append(f"SCHEDULER FEED LOG:\n{lines}")
    else:
        parts.append("SCHEDULER FEED LOG:\n  (empty — no events recorded yet)")

    # Live sensor readings from the current tick
    if req_data.tick:
        t = req_data.tick
        readings: list[str] = []

        def _fmt(key: str, label: str, unit: str = "MW") -> None:
            val = t.get(key)
            if val is not None:
                fmt_val = f"{val:.2f}" if isinstance(val, float) else str(val)
                readings.append(f"  {label}: {fmt_val} {unit}")

        _fmt("sim_time_seconds",       "Simulation time",                         "s")
        _fmt("p_generation_mw",        "Total generation")
        _fmt("turbine_output_mw",      "Gas turbine output")
        _fmt("p_renewable_mw",         "Solar PV output")
        _fmt("bess_output_mw",         "BESS (+ discharge / − charge)")
        _fmt("p_demand_mw",            "Total site demand")
        _fmt("p_served_mw",            "Served load")
        _fmt("p_unserved_mw",          "Unserved load (amber = stressed)")
        _fmt("frequency_hz",           "Grid frequency",                          "Hz")
        _fmt("confidence_upper_mw",    "Forecast step-load (upper bound)")
        _fmt("turbine_ramp_credit_mw", "Turbine ramp credit this tick")

        units_on = t.get("units_on_bus_count")
        if units_on is not None:
            readings.append(f"  Turbine units on bus (generating): {units_on}")

        cap = t.get("power_cap_active")
        if cap is not None:
            readings.append(f"  Power cap active (admission paused): {'yes' if cap else 'no'}")

        kube = t.get("kube_metrics") or {}
        if kube:
            readings.append(f"  Kube active GPU jobs: {kube.get('active_jobs', 0)}")
            readings.append(f"  Kube admitted nodes: {kube.get('admitted_nodes', 0)}")
            readings.append(f"  Kube queued jobs: {kube.get('queued_jobs', 0)}")

        if readings:
            parts.append("LIVE SENSOR READINGS:\n" + "\n".join(readings))

    user_msg = "\n\n".join(parts) + "\n\nWrite the plain-English summary paragraph:"

    payload = json.dumps({
        "model": _ANTHROPIC_MODEL,   # claude-haiku-4-5 (fast, cost-effective)
        "max_tokens": 600,
        "system": _SUMMARY_SYSTEM,
        "messages": [{"role": "user", "content": user_msg}],
    }).encode()

    req_http = urllib.request.Request(
        _ANTHROPIC_ENDPOINT,
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req_http, timeout=25) as resp:
            body = json.loads(resp.read())
        return body["content"][0]["text"].strip()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Anthropic HTTP {exc.code}: {exc.read()[:200]}") from exc


@router.post("/scheduler-summary", response_model=SchedulerSummaryResponse)
async def scheduler_summary(req: SchedulerSummaryRequest) -> SchedulerSummaryResponse:
    """Call Claude to produce a layman's summary of the Scheduler Feed + live tick data."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key:
        raise HTTPException(503, detail="ANTHROPIC_API_KEY is not configured on this server.")

    try:
        summary = await asyncio.get_event_loop().run_in_executor(
            None,
            _call_anthropic_summary,
            req,
            api_key,
        )
    except Exception as exc:
        log.warning("ai: scheduler-summary failed: %s", exc)
        raise HTTPException(502, detail=f"AI call failed: {exc}") from exc

    return SchedulerSummaryResponse(summary=summary)


@router.post("/explain-scenario", response_model=ExplainResponse)
async def explain_scenario(req: ExplainRequest) -> ExplainResponse:
    """Call Claude to generate an educational 4-sentence explanation of a scenario."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key:
        raise HTTPException(503, detail="ANTHROPIC_API_KEY is not configured on this server.")

    try:
        explanation = await asyncio.get_event_loop().run_in_executor(
            None,
            _call_anthropic_explain,
            req,
            api_key,
        )
    except Exception as exc:
        log.warning("ai: explain-scenario failed: %s", exc)
        raise HTTPException(502, detail=f"AI call failed: {exc}") from exc

    return ExplainResponse(explanation=explanation)
