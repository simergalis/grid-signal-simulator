#!/usr/bin/env python3
"""Measure E1-style zeroed active jobs across base/H informed study runs."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = (
    REPO_ROOT
    / "attached_assets"
    / "gridsignal_sim_v2_build_package"
    / "gridsignal_sim_v2"
    / "gridsignal_sim"
)
OUTPUT_PATH = REPO_ROOT / "tools" / "dr_isl" / "d6e" / "E3_SCOPE.json"
SCENARIOS = [
    {
        "label": "base demo (2 h)",
        "scenario_id": "scenario-uneven-multisched-01",
        "duration_seconds": 7200.0,
    },
    {
        "label": "H1-24h",
        "scenario_id": "scenario-h1-k8s-ray-24h",
        "duration_seconds": None,
    },
    {
        "label": "H2-24h",
        "scenario_id": "scenario-h2-slurm-24h",
        "duration_seconds": None,
    },
]
TICK_SECONDS = 5.0
START_TYPES = {"starting", "running", "scale"}

sys.path.insert(0, str(PACKAGE_ROOT))
from runtime.run_manager import RunContext, TICK_INTERVAL_SIM_SECONDS  # noqa: E402
from runtime.turbine_commitment import (  # noqa: E402
    ForecastDrivenTurbineController,
)
from study_harness.executor import StudyRunExecutor  # noqa: E402

assert float(TICK_INTERVAL_SIM_SECONDS) == TICK_SECONDS


def _value(item: Any) -> Any:
    return getattr(item, "value", item)


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "event_id": str(event.event_id),
        "job_id": str(event.job_id),
        "event_type": str(_value(event.event_type)),
        "timestamp_s": float(event.timestamp),
        "node_count": int(event.node_count),
        "hardware_profile_id": str(event.hardware_profile_id),
    }


def _profile_power(ctx: RunContext, event: Any, original_callback: Any) -> float:
    return float(original_callback(ctx, event))


class _NoArtifactWriter:
    class _ArtifactRef:
        def as_dict(self) -> dict[str, str]:
            return {}

    def write(self, **_: Any) -> "_NoArtifactWriter._ArtifactRef":
        return self._ArtifactRef()


def _write_progress(data: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _boundary_summary(spec: dict[str, Any]) -> dict[str, Any]:
    starts = [
        event
        for event in spec.get("workload_events", [])
        if str(event.get("event_type")) in START_TYPES
    ]
    boundary = [
        event
        for event in starts
        if abs(
            float(event["timestamp"]) / TICK_SECONDS
            - round(float(event["timestamp"]) / TICK_SECONDS)
        )
        <= 1e-9
    ]
    between = [event for event in starts if event not in boundary]
    return {
        "event_types_counted": sorted(START_TYPES),
        "tick_seconds": TICK_SECONDS,
        "start_like_event_count": len(starts),
        "on_tick_boundary_count": len(boundary),
        "between_tick_count": len(between),
        "boundary_examples_s": [
            float(event["timestamp"]) for event in boundary[:5]
        ],
        "between_tick_examples_s": [
            float(event["timestamp"]) for event in between[:5]
        ],
    }


def main() -> None:
    active_step: dict[str, Any] | None = None
    current_case: dict[str, Any] | None = None
    remembered_events: dict[str, Any] = {}

    original_step = RunContext.step
    original_callback = RunContext._event_power_mw
    original_job_state = ForecastDrivenTurbineController._job_state_at
    original_queue = ForecastDrivenTurbineController._queue
    original_refused = ForecastDrivenTurbineController._refused

    def wrapped_job_state(
        controller: Any,
        *,
        timestamp: float,
        events: list[Any],
        power_for_event: Any,
    ):
        for event in events:
            remembered_events[str(event.event_id)] = event
        result = original_job_state(
            controller,
            timestamp=timestamp,
            events=events,
            power_for_event=power_for_event,
        )
        if (
            active_step is None
            or abs(float(timestamp) - active_step["sim_time_s"]) > 1e-6
        ):
            return result

        ctx = active_step["ctx"]
        by_id = {str(event.event_id): event for event in events}
        by_id.update(remembered_events)
        for job_id, (state_power, event_id, event_time) in result.items():
            if abs(float(state_power)) > 1e-12:
                continue
            event = by_id.get(str(event_id))
            if event is None:
                continue
            callback_mw = _profile_power(ctx, event, original_callback)
            if callback_mw <= 0.0:
                continue
            occurrence_key = str(event_id)
            if occurrence_key in active_step["zeroed_by_event"]:
                continue
            cooling_fraction = max(0.0, float(active_step["cooling_fraction"]))
            active_step["zeroed_by_event"][occurrence_key] = {
                **_event_payload(event),
                "job_state_power_mw": float(state_power),
                "job_state_event_time_s": float(event_time),
                "callback_mw": callback_mw,
                "forecast_mw_missing_at_sample": callback_mw
                * (1.0 + cooling_fraction),
                "cooling_fraction": cooling_fraction,
            }
        return result

    def wrapped_queue(controller: Any, *args: Any, **kwargs: Any) -> None:
        ctx = kwargs.get("ctx", args[0] if args else None)
        turbine = kwargs.get("turbine", args[1] if len(args) > 1 else None)
        action = kwargs.get("action", args[2] if len(args) > 2 else None)
        reason = kwargs.get("reason", args[3] if len(args) > 3 else None)
        if active_step is not None and ctx is active_step["ctx"]:
            active_step["decisions"].append(
                {
                    "source": "forecast_commitment",
                    "action": str(action),
                    "unit_id": str(turbine.config.asset_id),
                    "accepted": True,
                    "reason": str(reason),
                }
            )
        return original_queue(controller, *args, **kwargs)

    def wrapped_refused(controller: Any, *args: Any, **kwargs: Any) -> None:
        ctx = kwargs.get("ctx")
        turbine = kwargs.get("turbine")
        action = kwargs.get("action")
        reason = kwargs.get("reason")
        if active_step is not None and ctx is active_step["ctx"]:
            active_step["decisions"].append(
                {
                    "source": "forecast_commitment",
                    "action": str(action),
                    "unit_id": str(turbine.config.asset_id),
                    "accepted": False,
                    "reason": str(reason),
                }
            )
        return original_refused(controller, *args, **kwargs)

    def wrapped_step(ctx: RunContext):
        nonlocal active_step
        controller = ctx.turbine_commitment_controller
        is_informed = (
            controller is not None
            and str(getattr(controller, "mode", "")) == "informed"
        )
        if not is_informed:
            return original_step(ctx)
        if current_case is not None:
            current_case["controller_evaluations"] += 1
            current_case["announcement_lead_seconds"].add(
                float(controller.forecast_lead_seconds)
            )
        step_record = {
            "ctx": ctx,
            "sim_time_s": float(ctx.sim_time),
            "cooling_fraction": float(
                getattr(ctx.sim_state.site, "alpha_max", 0.0)
            ),
            "zeroed_by_event": {},
            "decisions": [],
        }
        active_step = step_record
        try:
            tick = original_step(ctx)
        finally:
            active_step = None
        tick_action = str(getattr(tick, "commitment_action", "") or "")
        tick_target = getattr(tick, "commitment_target_unit_id", None)
        tick_reason = getattr(tick, "commitment_reason", None)
        if tick_action.lower() in {"start", "stop", "trip"}:
            step_record["decisions"].append(
                {
                    "source": "tick_result",
                    "action": tick_action,
                    "unit_id": tick_target,
                    "accepted": True,
                    "reason": tick_reason,
                }
            )
        if current_case is not None and step_record["zeroed_by_event"]:
            decisions = step_record["decisions"]
            decision_taken = any(
                str(item["action"]).lower() in {"start", "stop", "trip"}
                for item in decisions
            )
            missing = sum(
                float(item["forecast_mw_missing_at_sample"])
                for item in step_record["zeroed_by_event"].values()
            )
            current_case["affected_evaluation_count"] += 1
            current_case["zeroed_job_evaluation_count"] += len(
                step_record["zeroed_by_event"]
            )
            current_case["total_missing_mw_evaluations"] += missing
            current_case["maximum_missing_mw_in_one_evaluation"] = max(
                current_case["maximum_missing_mw_in_one_evaluation"], missing
            )
            if decision_taken:
                current_case["affected_evaluations_with_start_stop_decision"] += 1
            for item in step_record["zeroed_by_event"].values():
                occurrence = {
                    "time_s": step_record["sim_time_s"],
                    "job_id": item["job_id"],
                    "event_id": item["event_id"],
                    "callback_mw": item["callback_mw"],
                    "forecast_mw_missing_at_current_sample": item[
                        "forecast_mw_missing_at_sample"
                    ],
                    "start_stop_decision_taken": decision_taken,
                    "decisions": decisions,
                }
                if len(current_case["first_10_occurrences"]) < 10:
                    current_case["first_10_occurrences"].append(occurrence)
        return tick

    RunContext.step = wrapped_step
    ForecastDrivenTurbineController._job_state_at = wrapped_job_state
    ForecastDrivenTurbineController._queue = wrapped_queue
    ForecastDrivenTurbineController._refused = wrapped_refused

    results: list[dict[str, Any]] = []
    progress: dict[str, Any] = {
        "purpose": "D6e E3 scope probe; informed controller only",
        "seed": 42,
        "tick_seconds": TICK_SECONDS,
        "status": "running",
        "completed_scenarios": results,
    }
    _write_progress(progress)

    try:
        with tempfile.TemporaryDirectory(prefix="d6e_e3_") as output_dir:
            executor = StudyRunExecutor(output_dir=Path(output_dir))
            executor.writer = _NoArtifactWriter()
            for case in SCENARIOS:
                spec = executor._expanded_spec(
                    case["scenario_id"],
                    None,
                    case["duration_seconds"],
                )
                summary: dict[str, Any] = {
                    "label": case["label"],
                    "scenario_id": case["scenario_id"],
                    "mode": "informed",
                    "seed": 42,
                    "duration_seconds": float(spec.get("end_sim_time", 0.0)),
                    "controller_evaluations": 0,
                    "affected_evaluation_count": 0,
                    "zeroed_job_evaluation_count": 0,
                    "affected_evaluations_with_start_stop_decision": 0,
                    "total_missing_mw_evaluations": 0.0,
                    "maximum_missing_mw_in_one_evaluation": 0.0,
                    "first_10_occurrences": [],
                    "announcement_lead_seconds": set(),
                    "job_start_time_alignment": _boundary_summary(spec),
                }
                current_case = summary
                print(
                    json.dumps(
                        {
                            "scenario_started": case["scenario_id"],
                            "duration_seconds": summary["duration_seconds"],
                        }
                    ),
                    flush=True,
                )
                run_record = executor.run_mode(
                    scenario_id=case["scenario_id"],
                    mode="informed",
                    seed=42,
                    duration_seconds=case["duration_seconds"],
                    reuse_cache=False,
                )
                current_case = None
                summary["status"] = run_record.get("status")
                summary["identity_digest"] = run_record.get("identity_digest")
                summary["announcement_lead_seconds"] = sorted(
                    summary["announcement_lead_seconds"]
                )
                summary["total_missing_mw_evaluations"] = round(
                    float(summary["total_missing_mw_evaluations"]), 9
                )
                summary["maximum_missing_mw_in_one_evaluation"] = round(
                    float(summary["maximum_missing_mw_in_one_evaluation"]), 9
                )
                summary["total_missing_definition"] = (
                    "Sum across affected controller evaluations of each zeroed "
                    "active job's callback MW multiplied by (1 + cooling_fraction); "
                    "this is an MW-evaluation sum, not energy."
                )
                results.append(summary)
                progress["completed_scenarios"] = results
                progress["status"] = "running"
                _write_progress(progress)
                print(
                    json.dumps(
                        {
                            "scenario_finished": case["scenario_id"],
                            "controller_evaluations": summary[
                                "controller_evaluations"
                            ],
                            "affected_evaluations": summary[
                                "affected_evaluation_count"
                            ],
                        }
                    ),
                    flush=True,
                )
        progress["status"] = "complete"
        _write_progress(progress)
        print(json.dumps({"output": str(OUTPUT_PATH), "status": "complete"}), flush=True)
    finally:
        RunContext.step = original_step
        ForecastDrivenTurbineController._job_state_at = original_job_state
        ForecastDrivenTurbineController._queue = original_queue
        ForecastDrivenTurbineController._refused = original_refused


if __name__ == "__main__":
    main()
