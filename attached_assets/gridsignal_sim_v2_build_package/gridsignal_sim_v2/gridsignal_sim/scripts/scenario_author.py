"""scenario_author.py — Offline Mistral scenario authoring (§3.5).

GS-IMPL-PSP-002 §3.5 / §6.2 / §5.

OFFLINE ONLY.  This script runs once, before a simulation run starts, to
generate OperatorResponseProfile JSON files that PMSTestDouble consumes.
It MUST NOT be called during a run.  It MUST NOT be imported by core/ or
runtime/ (§1 import boundary, enforced by test_no_forbidden_imports.py).

Usage (CLI)
-----------
  python -m scripts.scenario_author \
      --persona "cautious night operator" \
      --requests '["approve rank 1", "reject rank 2"]' \
      --output profiles/cautious_night.json

The output JSON is the serialised OperatorResponseProfile dict, consumed
by PMSTestDouble at simulator startup via:
  profile = OperatorResponseProfile(**json.load(open("profiles/cautious_night.json")))
  pms = PMSTestDouble(profile)

Mistral API
-----------
  Uses the MISTRAL_API_KEY environment variable (via Replit secrets).
  Model: mistral-small-latest (fast, sufficient for persona generation).
  Only called once per persona — never during a simulation tick.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from runtime.pms_test_double import OperatorResponseProfile as _OperatorResponseProfile

logger = logging.getLogger(__name__)


# ── Prompt construction ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are generating a deterministic simulated operator response
profile for a power management system test double.  The profile must be a valid
JSON object with two optional fields:

  response_latency_s: dict[str, float]
    Keys are string rank positions ("1", "2", ...).
    Values are simulated response latencies in seconds.
    Omit a key to use the default (30 s).

  approve: dict[str, bool]
    Keys are string rank positions ("1", "2", ...).
    Values are whether the operator approves that ranked source.
    Omit a key to default to true (approve).

Return ONLY the JSON object, no prose, no markdown fences.
The profile must be reproducible — given the same persona and requests,
the same profile must be returned.  Do not add randomness."""


def _build_user_prompt(persona: str, requests: List[str]) -> str:
    requests_str = "\n".join(f"  - {r}" for r in requests)
    return (
        f"Persona: {persona}\n\n"
        f"Operator behaviour requests:\n{requests_str}\n\n"
        "Generate the OperatorResponseProfile JSON for this persona."
    )


# ── Mistral call ──────────────────────────────────────────────────────────────

def generate_operator_response_profile(
    persona: str,
    requests: List[str],
    model: str = "mistral-small-latest",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Call Mistral to generate an OperatorResponseProfile dict.

    Parameters
    ----------
    persona
        Plain-English description of the simulated operator's disposition.
        E.g. "cautious night operator who prefers grid over BESS".
    requests
        List of behavioural instructions for the persona.
        E.g. ["approve rank 1", "reject rank 3 with 120s delay"].
    model
        Mistral model to use.  Defaults to mistral-small-latest.
    api_key
        Mistral API key.  Defaults to MISTRAL_API_KEY environment variable.

    Returns
    -------
    dict
        Parsed OperatorResponseProfile dict with string keys converted to
        int for response_latency_s and approve.
    """
    try:
        from mistralai import Mistral  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "mistralai package is required for scenario_author.py. "
            "Install it with: pip install mistralai"
        ) from exc

    resolved_key = api_key or os.environ.get("MISTRAL_API_KEY")
    if not resolved_key:
        raise EnvironmentError(
            "MISTRAL_API_KEY is not set.  "
            "Set it as a Replit secret before running scenario_author.py."
        )

    client = Mistral(api_key=resolved_key)
    user_prompt = _build_user_prompt(persona, requests)

    logger.info("Calling Mistral (%s) to generate profile for persona: %s", model, persona)

    response = client.chat.complete(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.0,   # deterministic output
    )

    raw_json: str = response.choices[0].message.content.strip()
    logger.debug("Mistral raw response: %s", raw_json)

    try:
        profile_dict = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Mistral returned non-JSON output: {raw_json!r}"
        ) from exc

    # Convert string keys ("1", "2") to int keys (1, 2) for OperatorResponseProfile.
    normalised = _normalise_profile(profile_dict)

    # Phase 5 — wire to real schema: validate + serialise via OperatorResponseProfile.
    # Raises TypeError for unknown fields (Mistral hallucination guard).
    return _validate_against_schema(normalised)


def _normalise_profile(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert string rank keys to int in response_latency_s and approve."""
    result: Dict[str, Any] = {}
    for field_name in ("response_latency_s", "approve"):
        if field_name in raw:
            result[field_name] = {int(k): v for k, v in raw[field_name].items()}
    return result


def _validate_against_schema(profile_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Validate *profile_dict* against the real OperatorResponseProfile schema.

    Phase 5 (GS-IMPL-PSP-002): wire scenario_author to the real ScenarioSpec schema.

    Constructs an _OperatorResponseProfile instance from *profile_dict*.
    This raises TypeError for unknown fields (Mistral hallucination guard) and
    catches type mismatches early, at profile-generation time, rather than
    silently propagating a bad profile to PMSTestDouble at simulator startup.

    Returns a plain dict serialised via dataclasses.asdict() — including all
    fields with their defaults (default_latency_s, default_approve) — so the
    output JSON is a complete, validated schema snapshot:

        profile = OperatorResponseProfile(**json.load(open("profiles/x.json")))

    works correctly after a JSON round-trip (int keys survive as strings in JSON;
    callers should normalise via _normalise_profile before constructing).
    """
    validated = _OperatorResponseProfile(**profile_dict)
    return dataclasses.asdict(validated)


# ── CLI entry point ───────────────────────────────────────────────────────────

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an OperatorResponseProfile JSON using Mistral.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--persona", required=True,
                        help="Plain-English operator persona description.")
    parser.add_argument("--requests", required=True,
                        help="JSON array of behaviour request strings.")
    parser.add_argument("--output", required=True,
                        help="Output path for the generated profile JSON.")
    parser.add_argument("--model", default="mistral-small-latest",
                        help="Mistral model to use (default: mistral-small-latest).")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    args = _parse_args(argv)

    try:
        requests: List[str] = json.loads(args.requests)
    except json.JSONDecodeError as exc:
        logger.error("--requests must be a valid JSON array: %s", exc)
        sys.exit(1)

    profile = generate_operator_response_profile(
        persona=args.persona,
        requests=requests,
        model=args.model,
    )

    output_path = args.output
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, indent=2)
    logger.info("Profile written to %s", output_path)


if __name__ == "__main__":
    main()
