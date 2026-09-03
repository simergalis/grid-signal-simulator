"""Phase 3 H.10 output-only BESS sizing recommendation records.

This module consumes Phase 2 aggregation output and the original scenarios.
It writes only JSON beneath ``tools/bess_sizing/`` and deliberately does not
connect to the existing advisory proposal path or mutate simulator state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .aggregation import (
    DEFAULT_MARGIN_PCT,
    BessSizingAggregation,
)
from .models import BessSizingScenario
from .soc_policy import (
    DEFAULT_EMERGENCY_RESERVE_FLOOR_PCT,
    DEFAULT_NORMAL_DISPATCH_DEPTH_PCT,
    resolve_soc_cycling_policy,
)


_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_RECOMMENDATION_OUTPUT_PATH = _OUTPUT_DIR / "recommendation.json"


def _generated_at_iso(generated_at: datetime | str | None) -> str:
    if generated_at is None:
        value = datetime.now(timezone.utc)
    elif isinstance(generated_at, str):
        return generated_at
    else:
        value = generated_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unvalidated_inputs(
    scenarios: Sequence[BessSizingScenario],
    *,
    normal_defaulted: bool,
    emergency_defaulted: bool,
) -> list[str]:
    flags: set[str] = {
        "DEFAULT_MARGIN_PCT (PROPOSED_HERE; Addendum H BSZ-2)",
        "dt_lead_distribution_s (PROPOSED_HERE)",
        "thermal_parameters.alpha_max (PROPOSED_HERE)",
        "thermal_parameters.tau_seconds (PROPOSED_HERE)",
        "thermal_parameters.dt_thermal_seconds (PROPOSED_HERE)",
    }
    if normal_defaulted:
        flags.add(
            "normal_dispatch_depth_pct (PROPOSED_HERE; SJ-1-derived default)"
        )
    if emergency_defaulted:
        flags.add(
            "emergency_reserve_floor_pct (PROPOSED_HERE; SJ-1-derived default)"
        )
    if any(scenario.site_config.uncalibrated for scenario in scenarios):
        flags.add("site_config.uncalibrated (unvalidated)")
    return sorted(flags)


def _scenario_policy_defaults(
    scenarios: Sequence[BessSizingScenario],
) -> tuple[bool, bool]:
    normal_defaulted = False
    emergency_defaulted = False
    for scenario in scenarios:
        effective = resolve_soc_cycling_policy(
            scenario.soc_cycling_policy
        )
        normal_defaulted = normal_defaulted or effective.normal_defaulted
        emergency_defaulted = emergency_defaulted or effective.emergency_defaulted
    return normal_defaulted, emergency_defaulted


def build_recommendation_record(
    aggregation: BessSizingAggregation,
    scenarios: Sequence[BessSizingScenario],
    *,
    generated_at: datetime | str | None = None,
    evidence_trail_ref: str = "tools/bess_sizing/output/raw_sweep_traces.json",
) -> dict[str, object]:
    """Build a JSON-serializable H.10 recommendation record.

    The p50 and p100 recommendations use their corresponding un-margined
    Phase 2 values.  The p95 recommendation uses Phase 2's margin-adjusted
    P95.  Usable-energy ratings divide each energy requirement by the
    normal-dispatch depth only; the emergency floor is never counted as
    routine coverage.
    """

    if not scenarios:
        raise ValueError("cannot build a recommendation from no scenarios")
    site_ids = {scenario.site_config.site_id for scenario in scenarios}
    if len(site_ids) != 1:
        raise ValueError("all recommendation scenarios must belong to one site")

    normal_defaulted, emergency_defaulted = _scenario_policy_defaults(scenarios)
    effective_depths = {
        resolve_soc_cycling_policy(
            scenario.soc_cycling_policy
        ).normal_dispatch_depth_pct
        for scenario in scenarios
    }
    if len(effective_depths) != 1:
        raise ValueError(
            "all scenarios must use one normal dispatch depth for one record"
        )
    normal_depth = next(iter(effective_depths))
    if normal_depth <= 0.0:
        raise ValueError("normal dispatch depth must be greater than zero")

    driving_metric = max(
        aggregation.per_scenario,
        key=lambda metric: metric.peak_power_mw,
    )
    return {
        "site_id": next(iter(site_ids)),
        "generated_at": _generated_at_iso(generated_at),
        "recommended_rated_mw": {
            "p50": aggregation.power_mw.p50,
            "p95": aggregation.power_mw.p95,
            "p95_with_margin": aggregation.power_mw.p95_with_margin,
            "p100": aggregation.power_mw.p100,
        },
        "recommended_usable_mwh": {
            "p50": aggregation.energy_mwh.p50 / normal_depth,
            "p95": aggregation.energy_mwh.p95 / normal_depth,
            "p95_with_margin": (
                aggregation.energy_mwh.p95_with_margin / normal_depth
            ),
            "p100": aggregation.energy_mwh.p100 / normal_depth,
        },
        "margin_applied_pct": DEFAULT_MARGIN_PCT,
        "scenarios_swept": [
            scenario.scenario_id for scenario in scenarios
        ],
        "driving_scenario_id": driving_metric.scenario_id,
        "unvalidated_inputs": _unvalidated_inputs(
            scenarios,
            normal_defaulted=normal_defaulted,
            emergency_defaulted=emergency_defaulted,
        ),
        "evidence_trail_ref": evidence_trail_ref,
    }


def write_recommendation_record(
    record: Mapping[str, object],
    output_path: str | Path = DEFAULT_RECOMMENDATION_OUTPUT_PATH,
) -> Path:
    """Write one recommendation record beneath ``tools/bess_sizing/`` only."""

    destination = Path(output_path).resolve()
    output_root = _OUTPUT_DIR.resolve()
    try:
        destination.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(
            "recommendation output must remain under tools/bess_sizing/output"
        ) from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return destination


__all__ = [
    "DEFAULT_EMERGENCY_RESERVE_FLOOR_PCT",
    "DEFAULT_NORMAL_DISPATCH_DEPTH_PCT",
    "DEFAULT_RECOMMENDATION_OUTPUT_PATH",
    "build_recommendation_record",
    "write_recommendation_record",
]