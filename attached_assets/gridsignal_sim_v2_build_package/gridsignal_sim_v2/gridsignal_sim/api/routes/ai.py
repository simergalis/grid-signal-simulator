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

_EXPLAIN_SYSTEM = (
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
    "No headings, no bullets, no markdown. Return only the 5 sentences as a single paragraph."
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


class ExplainResponse(BaseModel):
    explanation: str


def _call_anthropic_explain(req: ExplainRequest, api_key: str) -> str:
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

    payload = json.dumps({
        "model": _ANTHROPIC_MODEL,
        "max_tokens": 400,
        "system": _EXPLAIN_SYSTEM,
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
