"""
runtime/generation_validator.py — Validate LLM / RNG generated values against
the authoritative gridsignal_parameters.json ranges before materialization.

All generators call validate_generated_value() before storing any output.
A value outside its documented range is REJECTED and logged — never silently
clamped — so out-of-range generation is an observable event, not an invisible
parameter change.

Design contract (from design note in generation architecture doc)
-----------------------------------------------------------------
Random ≠ AI.  For distributions you already know — arrival times, sensor noise,
SOC start — a seeded RNG is better: cheaper, reproducible by seed alone, no
network dependency.  Reach for a model only where the value is correlated
structure over time you cannot specify as a distribution.

Generated values must be validated against gridsignal_parameters.json BEFORE
materialization.  A model returning alpha_max = 0.5 must be rejected against
the [0.10, 0.30] range, and the rejection logged — not silently clamped.
Otherwise an out-of-range generation becomes an invisible parameter change.

Module isolation
----------------
This module does not import from core/ or api/ — it is a pure utility callable
from any layer without creating circular dependencies.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Optional

_log = logging.getLogger(__name__)

# Path relative to this file: runtime/ → parent → gridsignal_sim/
_PARAMS_JSON = os.path.join(
    os.path.dirname(__file__), "..", "gridsignal_parameters.json"
)


@lru_cache(maxsize=1)
def _load_params() -> dict:
    """Load gridsignal_parameters.json once; cached for the process lifetime."""
    path = os.path.normpath(_PARAMS_JSON)
    with open(path) as fh:
        return json.load(fh)


def _get_adjustable_entry(key: str) -> Optional[dict]:
    """Return the full 'adjustable' entry for the given parameter key, or None."""
    data = _load_params()
    for entry in data.get("adjustable", []):
        if entry.get("key") == key:
            return entry
    return None


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate_generated_value(
    key: str,
    value: Any,
    *,
    source: str = "generator",
) -> tuple[bool, str]:
    """Check that a generated value is within its documented range.

    Parameters
    ----------
    key    : parameter key as in gridsignal_parameters.json (e.g. "alpha_max")
    value  : the generated numeric value to check
    source : label for the generator shown in log output (e.g. "param_sampler",
             "cluster_gen/mistral")

    Returns
    -------
    (True,  "")           — within range, or key has no documented range
    (False, reason_str)   — out of range; reason describes the violation

    The caller is responsible for acting on False: typically discarding the
    generated value, logging the rejection, and substituting the parameter's
    documented default.  Callers MUST NOT silently clamp — clamping hides
    generation defects and makes out-of-range generation invisible in logs.
    """
    entry = _get_adjustable_entry(key)
    if entry is None:
        # Key not in the adjustable list — accept with an informational note.
        _log.debug("generation_validator: %s=%r — key not in adjustable list; accepted", key, value)
        return True, ""

    lo: Optional[float] = entry.get("min")
    hi: Optional[float] = entry.get("max")

    try:
        v = float(value)
    except (TypeError, ValueError):
        reason = f"{source}: {key}={value!r} is not numeric"
        _log.warning("generation_validator: REJECTED %s", reason)
        return False, reason

    if lo is not None and v < lo:
        reason = f"{source}: {key}={v} below minimum {lo}"
        _log.warning("generation_validator: REJECTED %s", reason)
        return False, reason
    if hi is not None and v > hi:
        reason = f"{source}: {key}={v} above maximum {hi}"
        _log.warning("generation_validator: REJECTED %s", reason)
        return False, reason

    return True, ""


def validated_or_default(
    key: str,
    value: Any,
    *,
    source: str = "generator",
) -> tuple[Any, bool]:
    """Validate *value* and return it if valid; return the documented default if not.

    Returns
    -------
    (result_value, was_accepted)
    - was_accepted=True  → result_value is the original value
    - was_accepted=False → result_value is the documented default (may be None
                           if no default is documented)
    """
    ok, _ = validate_generated_value(key, value, source=source)
    if ok:
        return value, True
    entry = _get_adjustable_entry(key)
    default = entry.get("default") if entry else None
    _log.info(
        "generation_validator: substituting default %r for rejected %s=%r",
        default, key, value,
    )
    return default, False


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def get_param_default(key: str) -> Any:
    """Return the documented default for a parameter key, or None if not found."""
    entry = _get_adjustable_entry(key)
    return entry.get("default") if entry else None


def get_param_range(key: str) -> tuple[Optional[float], Optional[float]]:
    """Return (min, max) for a parameter key; (None, None) if undocumented."""
    entry = _get_adjustable_entry(key)
    if entry is None:
        return None, None
    return entry.get("min"), entry.get("max")
