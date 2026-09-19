"""S1 engine-importing run executor and committed-artifact validation."""

from __future__ import annotations

import copy
import gzip
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from runtime.phase2b_reference import expand_phase2b_reference_spec
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec

from scripts.run_phase2b_stage1 import (
    TICK_SECONDS,
    _load_compact_spec,
    _signal_dict,
)

from .artifacts import ArtifactWriter
from .errors import error_payload
from .manifest import RunManifestCache, make_run_identity
from .metrics import MetricsCollector, collect_metrics


def _git_commit() -> str:
    configured = os.environ.get("GRIDSTUDY_ENGINE_COMMIT")
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            cwd=Path(__file__).resolve().parents[5],
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _deep_merge(target: dict[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if (
            isinstance(value, Mapping)
            and isinstance(target.get(key), dict)
        ):
            _deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _compact_tick(tick: Any) -> dict[str, Any]:
    row = _tick_result_to_dict(tick)
    keys = (
        "tick_index",
        "sim_time_seconds",
        "p_compute_mw",
        "p_cooling_mw",
        "p_total_mw",
        "p_generation_mw",
        "p_served_mw",
        "p_unserved_mw",
        "p_imbalance_mw",
        "p_dispatch_curtailed_mw",
        "turbine_output_mw",
        "bess_output_mw",
        "bess_soc_fraction",
        "turbine_fuel_telemetry",
        "turbine_units",
        "kube_metrics",
        "commitment_block",
        "forecast_mw",
    )
    return {key: row.get(key) for key in keys if key in row}


def _controller_metadata(ctx: Any) -> dict[str, Any]:
    controller = ctx.turbine_commitment_controller
    logs = (
        [record.as_dict() for record in controller.log]
        if controller is not None
        else []
    )
    starts = [
        record
        for record in logs
        if record.get("accepted")
        and record.get("changed_state")
        and record.get("action") in {"start", "release"}
    ]
    return {
        "starts": starts,
        "commitment_log": logs,
        "stop_floor_refusals": list(
            getattr(controller, "stop_floor_refusals", [])
        )
        if controller is not None
        else [],
        "stop_floor_refusal_count": len(
            getattr(controller, "stop_floor_refusals", [])
        )
        if controller is not None
        else 0,
        "constraints_valid": bool(
            getattr(controller, "constraints_valid", True)
        ),
        "hard_violations": list(
            getattr(controller, "constraint_violation_reasons", [])
        )
        if controller is not None
        else [],
        "forecast_misses": {
            "count": int(getattr(controller, "forecast_miss_count", 0)),
            "peak_mw": float(
                getattr(controller, "forecast_miss_peak_mw", 0.0)
            ),
        }
        if controller is not None
        else {"count": 0, "peak_mw": 0.0},
    }


def _bounded_records(
    records: list[dict[str, Any]],
    *,
    limit: int,
    reason: str,
) -> list[dict[str, Any]]:
    if len(records) <= limit:
        return records
    head = max(1, limit // 2)
    tail = max(1, limit - head - 1)
    return (
        records[:head]
        + [
            {
                "truncated": True,
                "omitted_record_count": len(records) - head - tail,
                "reason": reason,
            }
        ]
        + records[-tail:]
    )


class StudyRunExecutor:
    """Execute one scenario pair while importing the existing engine."""

    def __init__(
        self,
        *,
        output_dir: Path,
        engine_commit: str | None = None,
        harness_commit: str | None = None,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.engine_commit = engine_commit or _git_commit()
        self.harness_commit = harness_commit or _git_commit()
        self.tick_seconds = float(tick_seconds)
        self.writer = ArtifactWriter(self.output_dir / "artifacts")
        self.cache = RunManifestCache(self.output_dir / "cache")

    def _expanded_spec(
        self,
        scenario_id: str,
        parameter_overrides: Mapping[str, Any] | None,
        duration_seconds: float | None,
    ) -> dict[str, Any]:
        spec = expand_phase2b_reference_spec(_load_compact_spec(scenario_id))
        if duration_seconds is not None:
            spec["end_sim_time"] = float(duration_seconds)
        if parameter_overrides:
            _deep_merge(spec, parameter_overrides)
        return spec

    def _probe(
        self,
        spec: dict[str, Any],
        *,
        run_id: str,
    ) -> tuple[list[dict[str, Any]], list[tuple[float, float]]]:
        probe_spec = copy.deepcopy(spec)
        probe_spec["turbine_commitment_mode"] = "baseline"
        ctx = build_run_context_from_spec(run_id, probe_spec, playback_speed=0.0)
        ctx.sim_state.capture_workload_signal_trace = True
        tick_count = int(round(float(ctx.end_sim_time) / self.tick_seconds))
        demand_replay: list[tuple[float, float]] = []
        for _ in range(tick_count):
            tick = ctx.step()
            demand_replay.append(
                (
                    float(tick.p_compute_demand_mw),
                    float(tick.p_cooling_demand_mw),
                )
            )
        replay_events = [
            _signal_dict(signal)
            for signal in ctx.sim_state.workload_signal_trace
        ]
        if not replay_events:
            raise AssertionError(f"{run_id}: empty baseline workload trace")
        return replay_events, demand_replay

    def _run_mode(
        self,
        *,
        scenario_id: str,
        mode: str,
        spec: dict[str, Any],
        replay_events: list[dict[str, Any]],
        demand_replay: list[tuple[float, float]],
        seed: int | str | None,
    ) -> dict[str, Any]:
        run_spec = copy.deepcopy(spec)
        run_spec["turbine_commitment_mode"] = mode
        run_spec.pop("kube_clusters", None)
        run_spec.pop("slurm_config", None)
        run_spec["workload_events"] = replay_events
        duration_seconds = float(run_spec["end_sim_time"])
        identity_parameters = copy.deepcopy(run_spec)
        # The replay trace is an execution input, not a study parameter.  It
        # is intentionally excluded from identity and from bounded metadata;
        # the trace itself is represented by compute_trace_sha256.
        identity_parameters.pop("workload_events", None)
        identity = make_run_identity(
            scenario_id=scenario_id,
            mode=mode,
            parameter_set=identity_parameters,
            seed=seed,
            duration_seconds=duration_seconds,
            tick_seconds=self.tick_seconds,
            engine_commit=self.engine_commit,
            harness_commit=self.harness_commit,
        )

        def execute() -> dict[str, Any]:
            ctx = build_run_context_from_spec(
                f"{scenario_id}-{mode}-study-s1",
                run_spec,
                playback_speed=0.0,
            )
            ctx.sim_state.demand_replay_trace = demand_replay
            collector = MetricsCollector(self.tick_seconds)
            tick_rows: list[dict[str, Any]] = []
            tick_count = int(round(duration_seconds / self.tick_seconds))
            for _ in range(tick_count):
                tick = ctx.step()
                collector.add(tick)
                tick_rows.append(_compact_tick(tick))
            raw_metadata = _controller_metadata(ctx)
            raw_metadata.update(
                {
                    "scenario_id": scenario_id,
                    "mode": mode,
                    "engine_commit": self.engine_commit,
                    "harness_commit": self.harness_commit,
                }
            )
            metrics = collector.finalize(
                run_record=raw_metadata,
                commitment_log=raw_metadata["commitment_log"],
            )
            metadata = dict(raw_metadata)
            metadata["commitment_log_record_count"] = len(
                raw_metadata["commitment_log"]
            )
            metadata["commitment_log"] = _bounded_records(
                raw_metadata["commitment_log"],
                limit=120,
                reason="S1 artifact log is bounded; metrics used the full log",
            )
            metadata["stop_floor_refusal_count"] = len(
                raw_metadata["stop_floor_refusals"]
            )
            metadata["stop_floor_refusals"] = _bounded_records(
                raw_metadata["stop_floor_refusals"],
                limit=60,
                reason="S1 artifact refusal log is bounded; count is exact",
            )
            record = {
                **metadata,
                **metrics,
                "identity": identity.payload(),
                "identity_digest": identity.digest,
                "replay_strategy": "baseline demand trace replay",
            }
            artifacts = self.writer.write(
                identity=identity,
                record=record,
                summary=metrics,
                tick_rows=tick_rows,
            )
            record["artifacts"] = artifacts.as_dict()
            return record

        record, cache_hit = self.cache.get_or_execute(identity, execute)
        record = dict(record)
        record["cache_hit"] = cache_hit
        return record

    def run_pair(
        self,
        *,
        scenario_id: str,
        parameter_overrides: Mapping[str, Any] | None = None,
        seed: int | str | None = None,
        duration_seconds: float | None = None,
    ) -> dict[str, Any]:
        spec = self._expanded_spec(
            scenario_id,
            parameter_overrides,
            duration_seconds,
        )
        replay_events, demand_replay = self._probe(
            spec,
            run_id=f"{scenario_id}-study-s1-probe",
        )
        baseline = self._run_mode(
            scenario_id=scenario_id,
            mode="baseline",
            spec=spec,
            replay_events=replay_events,
            demand_replay=demand_replay,
            seed=seed,
        )
        informed = self._run_mode(
            scenario_id=scenario_id,
            mode="informed",
            spec=spec,
            replay_events=replay_events,
            demand_replay=demand_replay,
            seed=seed,
        )
        from .acceptance import compare_metrics

        comparison = compare_metrics(baseline, informed)
        return {
            "scenario_id": scenario_id,
            "runs": {"baseline": baseline, "informed": informed},
            "comparison": comparison,
        }


def _read_tick_rows(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def validate_committed_artifact(
    *,
    record_path: Path,
    tick_path: Path,
    minimum_down_seconds_by_unit: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Run S1 guards over a stored run without re-simulating it."""
    record = json.loads(Path(record_path).read_text())
    try:
        metrics = collect_metrics(
            _read_tick_rows(Path(tick_path)),
            run_record=record,
            commitment_log=record.get("commitment_log", []),
            tick_seconds=float(record.get("interval_seconds", TICK_SECONDS)),
            minimum_down_seconds_by_unit=minimum_down_seconds_by_unit,
        )
        return {"status": "PASS", "metrics": metrics, "guards_fired": []}
    except Exception as error:
        return {
            "status": "FAIL",
            "metrics": None,
            "guards_fired": [error_payload(error)],
        }