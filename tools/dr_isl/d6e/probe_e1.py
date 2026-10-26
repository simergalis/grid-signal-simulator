#!/usr/bin/env python3
"""Compact, in-memory D6e E1 forecast/event-power probe for S10."""

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
OUTPUT_PATH = REPO_ROOT / "tools" / "dr_isl" / "d6e" / "E1_INPUTS.json"
SCENARIO_JSON = (
    PACKAGE_ROOT
    / "config"
    / "scenarios"
    / "S10_mit_supercloud_2021-08-11.json"
)
TARGET_TIMES = {13680.0, 16775.0}
TARGET_EVENT_IDS = {
    "evt-s10-job-00008-start",
    "evt-s10-job-00009-start",
}

sys.path.insert(0, str(PACKAGE_ROOT))

from runtime.run_manager import RunContext  # noqa: E402
from runtime.turbine_commitment import (  # noqa: E402
    ForecastDrivenTurbineController,
)
from study_harness.executor import StudyRunExecutor  # noqa: E402


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "event_id": str(event.event_id),
        "job_id": str(event.job_id),
        "event_type": str(_enum_value(event.event_type)),
        "start_time_s": float(event.timestamp),
        "node_count_as_read": int(event.node_count),
        "hardware_profile_id": str(event.hardware_profile_id),
        "workload_class": (
            None
            if getattr(event, "workload_class", None) is None
            else str(_enum_value(event.workload_class))
        ),
    }


def _resolve_profile(ctx: RunContext, profile_id: str) -> tuple[float, str | None]:
    libraries = [
        module.hardware_library
        for module in ctx.sim_state.gpu_modules
        if getattr(module, "hardware_library", None)
    ]
    profile = next(
        (
            library.get(profile_id)
            for library in libraries
            if library.get(profile_id) is not None
        ),
        None,
    )
    return (
        float(profile.rated_kw) if profile is not None else 12.0,
        None if profile is None else str(profile.profile_id),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


class _NoArtifactWriter:
    """Keep StudyRunExecutor's path while preventing any tick artifact writes."""

    class _ArtifactRef:
        def as_dict(self) -> dict[str, str]:
            return {}

    def write(self, **_: Any) -> "_NoArtifactWriter._ArtifactRef":
        return self._ArtifactRef()


def main() -> None:
    active_eval: dict[str, Any] | None = None
    callback_calls: list[dict[str, Any]] = []
    forecast_records: list[dict[str, Any]] = []
    seen_callback_keys: set[tuple[Any, ...]] = set()
    authored = json.loads(SCENARIO_JSON.read_text(encoding="utf-8"))
    authored_end_by_job = {
        str(event["job_id"]): float(event["timestamp"])
        for event in authored.get("workload_events", [])
        if event.get("event_type") == "job_end"
    }

    original_callback = RunContext._event_power_mw
    original_forecast = ForecastDrivenTurbineController.forecast
    original_announced = ForecastDrivenTurbineController._announced_start_times
    original_job_state = ForecastDrivenTurbineController._job_state_at

    def wrapped_callback(self: RunContext, event: Any) -> float:
        result = float(original_callback(self, event))
        announced_jobs = (
            set(active_eval.get("announced_start_times_returned", {}))
            if active_eval is not None
            else set()
        )
        if (
            str(event.event_id) in TARGET_EVENT_IDS
            or (
                active_eval is not None
                and str(event.job_id) in announced_jobs
            )
        ):
            rated_kw, resolved_profile_id = _resolve_profile(
                self, str(event.hardware_profile_id)
            )
            pue_base = float(self.sim_state.site.pue_base)
            evaluation_kind = (
                "post_forecast_diagnostic"
                if active_eval is not None
                and active_eval.get("diagnostic_callback_evaluation")
                else "forecast_execution"
            )
            callback_key = (
                str(event.event_id),
                evaluation_kind,
                (
                    float(active_eval["controller_eval_time_s"])
                    if evaluation_kind == "post_forecast_diagnostic"
                    and active_eval is not None
                    else None
                ),
            )
            if callback_key not in seen_callback_keys:
                seen_callback_keys.add(callback_key)
                callback_calls.append(
                    {
                    "controller_sim_time_s": float(self.sim_time),
                    **_event_payload(event),
                    "resolved_profile_id": resolved_profile_id,
                    "rated_kw_resolved": rated_kw,
                    "pue_base": pue_base,
                    "callback_formula": (
                        "node_count_as_read * rated_kw_resolved * pue_base / 1000"
                    ),
                    "callback_returned_mw": result,
                    "evaluation_kind": evaluation_kind,
                    }
                )
        return result

    def wrapped_announced(self: Any, *, sim_time_s: float, events: list[Any]):
        result = original_announced(self, sim_time_s=sim_time_s, events=events)
        if active_eval is not None:
            active_eval["announced_start_times_returned"] = {
                str(job_id): float(timestamp) for job_id, timestamp in result.items()
            }
            active_eval["announced_event_job_ids"] = list(
                active_eval["announced_start_times_returned"]
            )
            active_eval["announced_cutoff_s"] = (
                float(sim_time_s) + float(self.forecast_lead_seconds)
            )
        return result

    def wrapped_job_state(
        self: Any,
        *,
        timestamp: float,
        events: list[Any],
        power_for_event: Any,
    ):
        result = original_job_state(
            self,
            timestamp=timestamp,
            events=events,
            power_for_event=power_for_event,
        )
        if (
            active_eval is not None
            and float(sim_time_s := active_eval["sim_time_s"])
            <= float(timestamp)
            <= sim_time_s + float(active_eval["forecast_horizon_s"])
        ):
            target_jobs = set(active_eval.get("announced_event_job_ids", []))
            state_rows = {}
            for job_id in target_jobs:
                state = result.get(job_id)
                if state is not None:
                    state_rows[str(job_id)] = {
                        "state_power_mw": float(state[0]),
                        "state_event_id": str(state[1]),
                        "state_event_timestamp_s": float(state[2]),
                    }
            if state_rows:
                active_eval["job_state_samples"].append(
                    {
                        "sample_time_s": float(timestamp),
                        "job_state": state_rows,
                    }
                )
        return result

    def wrapped_forecast(
        self: Any,
        *,
        sim_time_s: float,
        events: list[Any],
        measured_history: list[tuple[float, float]],
        power_for_event: Any,
        cooling_fraction: float = 0.0,
        horizon_seconds: float | None = None,
        step_seconds: float = 5.0,
    ):
        nonlocal active_eval
        if float(sim_time_s) not in TARGET_TIMES:
            return original_forecast(
                self,
                sim_time_s=sim_time_s,
                events=events,
                measured_history=measured_history,
                power_for_event=power_for_event,
                cooling_fraction=cooling_fraction,
                horizon_seconds=horizon_seconds,
                step_seconds=step_seconds,
            )

        horizon = (
            float(self.stop_lookahead_seconds)
            if horizon_seconds is None
            else max(0.0, float(horizon_seconds))
        )
        record: dict[str, Any] = {
            "controller_eval_time_s": float(sim_time_s),
            "sim_time_s": float(sim_time_s),
            "forecast_profile_window_start_s": float(sim_time_s),
            "forecast_horizon_s": horizon,
            "forecast_profile_window_end_s": float(sim_time_s) + horizon,
            "forecast_sample_step_s": float(step_seconds),
            "forecast_lead_seconds": float(self.forecast_lead_seconds),
            "cooling_fraction": float(cooling_fraction),
            "announced_event_job_ids": [],
            "announced_start_times_returned": {},
            "job_state_samples": [],
        }
        active_eval = record
        try:
            result = original_forecast(
                self,
                sim_time_s=sim_time_s,
                events=events,
                measured_history=measured_history,
                power_for_event=power_for_event,
                cooling_fraction=cooling_fraction,
                horizon_seconds=horizon_seconds,
                step_seconds=step_seconds,
            )
            # Evaluate the real RunContext callback once for each announced
            # event after the forecast has been built. This records its inputs
            # and output without changing the forecast or timeline cache.
            starts = record.get("announced_start_times_returned", {})
            record["diagnostic_callback_evaluation"] = True
            for event in events:
                if (
                    str(event.job_id) in starts
                    and str(_enum_value(event.event_type))
                    in {"starting", "running", "scale"}
                ):
                    power_for_event(event)
            record["diagnostic_callback_evaluation"] = False
        finally:
            active_eval = None

        announced_ids = [str(event_id) for event_id in result.announced_event_ids]
        announced_id_set = set(announced_ids)
        starts = record["announced_start_times_returned"]
        record["announced_event_ids_in_forecast_result"] = announced_ids
        record["announced_event_count"] = len(announced_ids)
        record["profile_point_count"] = len(result.profile)
        record["forecast_peak_mw"] = float(result.peak_forecast_mw)
        record["announced_workload_mw"] = float(result.announced_workload_mw)

        relevant_events: list[Any] = []
        for event in events:
            if str(event.event_id) in announced_id_set:
                relevant_events.append(event)

        events_by_job: dict[str, list[Any]] = {}
        for event in events:
            events_by_job.setdefault(str(event.job_id), []).append(event)

        event_records: list[dict[str, Any]] = []
        sample_by_time = {
            float(timestamp): float(mw) for timestamp, mw in result.profile
        }
        for event in relevant_events:
            payload = _event_payload(event)
            job_id = str(event.job_id)
            job_events = events_by_job.get(job_id, [])
            end_event = next(
                (
                    candidate
                    for candidate in job_events
                    if str(_enum_value(candidate.event_type))
                    in {"job_end", "cancelled", "job_failed", "job_timeout"}
                    and float(candidate.timestamp) > float(event.timestamp)
                ),
                None,
            )
            end_time_s = (
                float(end_event.timestamp)
                if end_event is not None
                else authored_end_by_job.get(job_id)
            )
            payload["end_time_s"] = end_time_s
            payload["end_time_source"] = (
                str(end_event.event_id)
                if end_event is not None
                else (
                    "authored_scenario_workload_events"
                    if end_time_s is not None
                    else None
                )
            )
            payload["event_id_in_forecast_announced_ids"] = (
                str(event.event_id) in announced_id_set
            )
            payload["job_id_in_announced_start_times"] = job_id in starts
            payload["announced_start_time_s"] = starts.get(job_id)
            payload["announced_window_test"] = {
                "event_type_is_load": str(_enum_value(event.event_type))
                in {"starting", "running", "scale"},
                "event_timestamp_s": float(event.timestamp),
                "controller_eval_time_s": float(sim_time_s),
                "announced_cutoff_s": record.get("announced_cutoff_s"),
                "timestamp_within_forecast_lead": (
                    float(event.timestamp)
                    <= float(sim_time_s) + float(self.forecast_lead_seconds)
                ),
                "start_timestamp_not_after_eval": (
                    float(event.timestamp) <= float(sim_time_s)
                ),
                "profile_window_test": (
                    float(sim_time_s)
                    <= float(event.timestamp)
                    <= float(sim_time_s) + horizon
                ),
            }

            matching_calls = [
                call
                for call in callback_calls
                if call["event_id"] == str(event.event_id)
            ]
            latest_call = matching_calls[-1] if matching_calls else None
            rated_kw = (
                float(latest_call["rated_kw_resolved"])
                if latest_call is not None
                else 0.0
            )
            resolved_profile_id = (
                None if latest_call is None else latest_call["resolved_profile_id"]
            )
            payload["callback_inputs"] = {
                "event_type": str(_enum_value(event.event_type)),
                "node_count_as_read": int(event.node_count),
                "hardware_profile_id": str(event.hardware_profile_id),
                "resolved_profile_id": resolved_profile_id,
                "rated_kw_resolved": rated_kw,
                "pue_base": None if latest_call is None else latest_call["pue_base"],
            }
            payload["callback_observations"] = matching_calls

            relevant_samples = []
            for sample in record["job_state_samples"]:
                state = sample["job_state"].get(job_id)
                if state is None:
                    continue
                state_power = float(state["state_power_mw"])
                included = job_id in starts
                used_mw = (
                    state_power * (1.0 + max(0.0, float(cooling_fraction)))
                    if included
                    else 0.0
                )
                sample_time = float(sample["sample_time_s"])
                relevant_samples.append(
                    {
                        "sample_time_s": sample_time,
                        "in_profile_window": (
                            float(sim_time_s) <= sample_time <= float(sim_time_s) + horizon
                        ),
                        "event_active_at_sample": (
                            float(event.timestamp) <= sample_time
                            and (
                                payload["end_time_s"] is None
                                or sample_time < float(payload["end_time_s"])
                            )
                        ),
                        **state,
                        "job_id_in_announced_start_times": included,
                        "forecast_contribution_used_mw": used_mw,
                        "aggregate_forecast_sample_mw": sample_by_time.get(sample_time),
                    }
                )
                if len(relevant_samples) >= 2:
                    break
            payload["forecast_sample_observations"] = relevant_samples
            payload["callback_formula_mw_recomputed"] = (
                float(event.node_count) * rated_kw
                * float(payload["callback_inputs"]["pue_base"] or 0.0)
                / 1000.0
            )
            event_records.append(payload)

        record["announced_event_inputs"] = event_records
        compact_record = {
            key: value
            for key, value in record.items()
            if key != "job_state_samples"
        }
        compact_record["captured_sample_time_count"] = len(
            record["job_state_samples"]
        )
        forecast_records.append(_json_safe(compact_record))
        return result

    RunContext._event_power_mw = wrapped_callback
    ForecastDrivenTurbineController._announced_start_times = wrapped_announced
    ForecastDrivenTurbineController._job_state_at = wrapped_job_state
    ForecastDrivenTurbineController.forecast = wrapped_forecast

    try:
        with tempfile.TemporaryDirectory(prefix="d6e_e1_") as output_dir:
            executor = StudyRunExecutor(output_dir=Path(output_dir))
            executor.writer = _NoArtifactWriter()
            result = executor.run_pair(
                scenario_id="S10_mit_supercloud_2021-08-11",
                seed=42,
                duration_seconds=16805.0,
            )
        output = {
            "purpose": "D6e E1 event-power and forecast-sample inputs only",
            "scenario_id": result["scenario_id"],
            "study_class": result["study_class"],
            "seed": 42,
            "run_duration_seconds": 16805.0,
            "tick_count_per_arm": 3361,
            "instrumented_controller_evaluations": forecast_records,
            "callback_observations_for_target_events": callback_calls,
            "note": (
                "Only target-time event/callback/sample evidence is saved; "
                "the executor's per-tick artifacts were disabled and its "
                "temporary output directory was removed."
            ),
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(_json_safe(output), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "output": str(OUTPUT_PATH),
                    "target_evaluations": len(forecast_records),
                    "target_callback_calls": len(callback_calls),
                    "announced_event_counts": [
                        item["announced_event_count"] for item in forecast_records
                    ],
                },
                sort_keys=True,
            )
        )
    finally:
        RunContext._event_power_mw = original_callback
        ForecastDrivenTurbineController._announced_start_times = original_announced
        ForecastDrivenTurbineController._job_state_at = original_job_state
        ForecastDrivenTurbineController.forecast = original_forecast


def _resolve_profile_from_events(
    event: Any,
    events: list[Any],
    calls: list[dict[str, Any]],
) -> tuple[float, str | None]:
    matching = next(
        (call for call in reversed(calls) if call["event_id"] == str(event.event_id)),
        None,
    )
    if matching is not None:
        return float(matching["rated_kw_resolved"]), matching["resolved_profile_id"]
    # Normally a callback call is observed while the job enters the controller's
    # timeline. This fallback reports the S10 runtime profile resolution if the
    # timeline cache already held the value before the target evaluation.
    # The target callback formula is evaluated from the same context by the
    # RunContext wrapper whenever the event is actually processed.
    return 0.0, None


if __name__ == "__main__":
    main()
