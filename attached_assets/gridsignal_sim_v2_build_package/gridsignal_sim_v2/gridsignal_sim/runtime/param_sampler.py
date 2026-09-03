"""
runtime/param_sampler.py — Seeded RNG parameter sampler for per-run variation.

Draws plant-side physics parameters (Δt_thermal, τ, α_max, r_asset, etc.) from
their documented ranges ONCE at run start, before the tick loop begins.  The
sampled values are stored in the generation_block and injected into spec_data
so that each run is a distinct point in the §6.1 sensitivity space without
requiring a nested sweep loop.

Design note (Random ≠ AI)
--------------------------
Seeded RNG is the correct tool here.  The sampling distribution is fully
specified by [min, max] in gridsignal_parameters.json — there is no temporal
structure that an LLM adds value to.  A seeded RNG gives:
  - Reproducibility: any run is exactly replayable from its seed alone.
  - Cheapness: no network call, no latency.
  - Transparency: the mapping from seed to sample is deterministic and auditable.

Validation (constraint)
-----------------------
Every sampled value is validated against gridsignal_parameters.json before
being stored.  A sample outside the documented range (which should not happen
for a correctly-read range, but guards against JSON drift) is rejected and the
documented default is substituted.

Split parameters
----------------
gridsignal_parameters.json marks some parameters split=true — they exist as
both plant and engine values.  The sampler draws INDEPENDENTLY for plant and
engine when told to sample both halves of a split parameter, so that the
resulting run exhibits plant/engine divergence naturally.
"""
from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

from runtime.generation_validator import (
    validate_generated_value,
    get_param_default,
    get_param_range,
    _load_params,  # internal — same lru_cache, not a new load
)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sampled parameter result
# ---------------------------------------------------------------------------

@dataclass
class SampledParams:
    """Result of sample_run_parameters().

    Fields
    ------
    values        — dict of {key: sampled_value}; ready to merge into spec_data.
    rejections    — list of (key, generated_value, reason) for any rejected draws.
    seed          — the RNG seed used; None for a time-seeded run.
    source        — "param_sampler/rng"
    """
    values:     dict[str, Any]
    rejections: list[tuple[str, Any, str]]
    seed:       Optional[int]
    source:     str = "param_sampler/rng"

    def to_generation_note(self) -> str:
        """Short human-readable summary for the generation_block."""
        if not self.values:
            return "no parameters sampled"
        summary = ", ".join(f"{k}={v}" for k, v in self.values.items())
        if self.rejections:
            rej = ", ".join(r[0] for r in self.rejections)
            return f"sampled [{summary}]; rejected [{rej}] — defaults substituted"
        return f"sampled [{summary}]"


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

# These keys are EXCLUDED from sampling — see gridsignal_parameters.json
# "excluded" and "locked" sections, plus parameters that must not vary
# (conformance constants, ladder ordering, arbitration outcomes).
_NEVER_SAMPLE: frozenset[str] = frozenset({
    "band_pct_calibrated",       # INV-2: calibration band is a site constant
    "band_mult_uncalibrated",    # site-level constant
    "band_mult_unmapped_hw",     # hardware-library constant
    "anchor_reserve_pct",        # PROTO-9: pending commissioning — don't randomise
    "soc_pct",                   # initial SOC: scenario-level intentional choice
    "bess_rated_mw",             # fleet sizing: not a per-run stochastic quantity
    "p_renewable_mw",            # measured/forecast input, not sampled
})


def sample_run_parameters(
    keys: list[str],
    *,
    seed: Optional[int] = None,
    sample_plant_split: bool = True,
) -> SampledParams:
    """Draw parameters from their documented [min, max] ranges using a seeded RNG.

    Parameters
    ----------
    keys                : parameter keys to sample (from gridsignal_parameters.json).
                          Keys in _NEVER_SAMPLE are silently skipped.
    seed                : RNG seed.  None = time-seeded (non-reproducible).
    sample_plant_split  : if True, split parameters draw independent plant and
                          engine values (producing plant/engine divergence).
                          If False, both halves share the same draw.

    Returns
    -------
    SampledParams with .values ready to merge into spec_data.

    Mapping from parameter key to ScenarioSpec field name
    ------------------------------------------------------
    The keys mirror gridsignal_parameters.json.  Translation to ScenarioSpec:
      "dt_thermal"  → "dt_thermal_seconds" (engine), "plant_dt_thermal_seconds" (plant)
      "alpha_max"   → "alpha_max" (engine), "plant_alpha_max" (plant)
      "tau"         → "tau_seconds" (engine), "plant_tau_seconds" (plant)
      "r_asset"     → not directly in ScenarioSpec (lives on TurbineUnitSpec);
                      sampled and stored in values for the caller to apply.
    The caller is responsible for the key→field translation when merging into
    spec_data, since ScenarioSpec field names differ slightly from JSON keys.
    """
    rng = random.Random(seed)
    all_params = _load_params()
    adjustable = {e["key"]: e for e in all_params.get("adjustable", [])}

    values: dict[str, Any]                      = {}
    rejections: list[tuple[str, Any, str]]      = []

    for key in keys:
        if key in _NEVER_SAMPLE:
            _log.debug("param_sampler: skipping %r (in _NEVER_SAMPLE)", key)
            continue

        entry = adjustable.get(key)
        if entry is None:
            _log.debug("param_sampler: %r not found in adjustable list — skipping", key)
            continue

        lo: Optional[float] = entry.get("min")
        hi: Optional[float] = entry.get("max")
        if lo is None or hi is None:
            _log.debug("param_sampler: %r has no min/max — skipping", key)
            continue

        is_split: bool = entry.get("split", False) is True

        # Draw engine value
        engine_val = lo + rng.random() * (hi - lo)
        # Round to step if documented
        step = entry.get("step")
        if step and step > 0:
            engine_val = round(round(engine_val / step) * step, 10)

        ok, reason = validate_generated_value(key, engine_val, source="param_sampler")
        if ok:
            _spec_key = _key_to_spec_field(key, plant=False)
            values[_spec_key] = engine_val
        else:
            rejections.append((key, engine_val, reason))
            default = get_param_default(key)
            if default is not None:
                values[_key_to_spec_field(key, plant=False)] = default

        # Draw independent plant value for split parameters
        if is_split and sample_plant_split:
            plant_val = lo + rng.random() * (hi - lo)
            if step and step > 0:
                plant_val = round(round(plant_val / step) * step, 10)

            ok_p, reason_p = validate_generated_value(key, plant_val, source="param_sampler/plant")
            if ok_p:
                _pkey = _key_to_spec_field(key, plant=True)
                values[_pkey] = plant_val
            else:
                rejections.append((f"plant_{key}", plant_val, reason_p))

    _log.info(
        "param_sampler: seed=%s → %d values, %d rejections",
        seed, len(values), len(rejections),
    )
    return SampledParams(values=values, rejections=rejections, seed=seed)


# ---------------------------------------------------------------------------
# Key → ScenarioSpec field name translation
# ---------------------------------------------------------------------------

# Maps gridsignal_parameters.json key → (engine_field, plant_field) in ScenarioSpec
_KEY_TO_FIELD: dict[str, tuple[str, str]] = {
    "dt_thermal": ("dt_thermal_seconds",  "plant_dt_thermal_seconds"),
    "alpha_max":  ("alpha_max",            "plant_alpha_max"),
    "tau":        ("tau_seconds",          "plant_tau_seconds"),
    # r_asset lives on TurbineUnitSpec, not ScenarioSpec directly.
    # Store under a namespaced key; the caller reads it explicitly.
    "r_asset":    ("_sampled_r_asset_mw_per_s", "_sampled_plant_r_asset_mw_per_s"),
    "pue_base":   ("pue_base",             "_sampled_plant_pue_base"),
    "dt_lead":    ("dt_lead_seconds",      "_sampled_plant_dt_lead_seconds"),
}


def _key_to_spec_field(key: str, *, plant: bool) -> str:
    """Translate a gridsignal_parameters.json key to its ScenarioSpec field name.

    Unknown keys are passed through as-is (engine) or prefixed with 'plant_'
    (plant side).
    """
    mapping = _KEY_TO_FIELD.get(key)
    if mapping:
        return mapping[1] if plant else mapping[0]
    return f"plant_{key}" if plant else key
