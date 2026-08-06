"""
api/routes/ai.py — AI-assisted scenario copy generation.

POST /api/ai/improve-description
  Takes the current demo copy draft plus scenario metadata and calls Mistral
  to write / improve the operator-facing "What this demonstrates" blurb shown
  in the DemoBar.  Falls back to a 502 with a clear message when the key is absent.
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
