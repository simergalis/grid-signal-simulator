"""S1 engine-importing run executor and committed-artifact validation."""

from __future__ import annotations

import copy
import gzip
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from api.schemas import ScenarioSpec
from runtime.phase2b_reference import (
    apply_study_fuel_model,
    expand_phase2b_reference_spec,
)
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec
from runtime.seed_resolution import (
    SEED_DERIVATION_VERSION,
    resolve_run_seed_manifest,
    seed_consumers_for_spec,
)
from core.physical_identity import PhysicalIdentityHasher

from scripts.run_phase2b_stage1 import (
    REFERENCE_IDS,
    TICK_SECONDS,
    _load_compact_spec,
    _signal_dict,
)

from .artifacts import ArtifactWriter
from .errors import (
    HarnessGuardError,
    StartFuelReconciliationError,
    UnsupportedScenarioError,
    error_payload,
)
from .manifest import RunIdentity, RunManifestCache, make_run_identity
from .metrics import MetricsCollector, collect_metrics, FREQUENCY_REPORTING_METRICS_VERSION
from runtime.operating_cost import compute_operating_cost


# PROPOSED_HERE: The base scenario ID and study-class labels are harness metadata.
BASE_DEMO_SCENARIO_ID = "scenario-uneven-multisched-01"
STUDY_CLASS_ADDENDUM_H = "addendum_h"
STUDY_CLASS_BASE_DEMO = "base_demo"
BUILD_INFO_PATH = Path(__file__).resolve().parents[1] / "build_info.json"  # PROPOSED_HERE
# PROPOSED_HERE: bump the study identity when resolved RNG inputs become part
# of a run's reproducibility contract. Source: DR Phase 6 D4.
STUDY_IDENTITY_VERSION = 3


def seed_cache_bypass_reason(
    *,
    reuse_cache: bool,
    requested_seed: int | str | None,
) -> str | None:
    """Return the shared cache-bypass reason for an unseeded request.

    DR D4 records a fresh root seed when the request omits one. DR Phase 6c
    requires such a request to execute freshly rather than looking up a result
    under a seed the caller did not provide.
    """
    if reuse_cache and requested_seed is None:
        return "seed_not_provided"
    return None


def study_class_for_scenario(scenario_id: str) -> str:
    if scenario_id in REFERENCE_IDS:
        return STUDY_CLASS_ADDENDUM_H
    if scenario_id == BASE_DEMO_SCENARIO_ID:
        return STUDY_CLASS_BASE_DEMO
    raise UnsupportedScenarioError(
        scenario_id=scenario_id,
        supported_ids=[*REFERENCE_IDS, BASE_DEMO_SCENARIO_ID],
    )


def make_study_run_identity(
    *,
    scenario_id: str,
    mode: str,
    spec: Mapping[str, Any],
    seed: int | str | None,
    tick_seconds: float,
    engine_commit: str,
    harness_commit: str,
) -> RunIdentity:
    identity_parameters = copy.deepcopy(dict(spec))
    identity_parameters["turbine_commitment_mode"] = mode
    identity_parameters.pop("kube_clusters", None)
    identity_parameters.pop("slurm_config", None)
    # The replay trace is an execution input; its content is separately hashed.
    identity_parameters.pop("workload_events", None)
    identity_parameters["study_class"] = study_class_for_scenario(scenario_id)
    # DR D3: invalidate old metric caches without changing the execution spec.
    identity_parameters["frequency_reporting_metrics_version"] = FREQUENCY_REPORTING_METRICS_VERSION
    identity_parameters["study_identity_version"] = STUDY_IDENTITY_VERSION
    identity_parameters["seed_derivation_version"] = SEED_DERIVATION_VERSION
    return make_run_identity(
        scenario_id=scenario_id,
        mode=mode,
        parameter_set=identity_parameters,
        seed=seed,
        duration_seconds=float(spec["end_sim_time"]),
        tick_seconds=tick_seconds,
        engine_commit=engine_commit,
        harness_commit=harness_commit,
    )


def _build_info_commit(field: str) -> str | None:
    try:
        build_info = json.loads(BUILD_INFO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(build_info, dict):
        return None
    value = build_info.get(field)
    if value is None:
        return None
    commit = str(value).strip()
    return commit or None


def _live_git_commit() -> str | None:
    repo_root = Path(__file__).resolve().parents[5]
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            cwd=repo_root,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    if not commit:
        return "unknown"
    try:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            text=True,
            cwd=repo_root,
        ).strip()
        return f"{commit}-dirty" if dirty else commit
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _git_commit() -> str:
    configured = os.environ.get("GRIDSTUDY_ENGINE_COMMIT")
    if configured is not None and configured.strip():
        return configured.strip()
    live_git_commit = _live_git_commit()
    if live_git_commit is not None:
        return live_git_commit
    build_info_commit = _build_info_commit("engine_commit")
    return build_info_commit if build_info_commit is not None else "unknown"


def _harness_commit() -> str:
    live_git_commit = _live_git_commit()
    if live_git_commit is not None:
        return live_git_commit
    build_info_commit = _build_info_commit("harness_commit")
    return build_info_commit if build_info_commit is not None else "unknown"


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
        "frequency_valid",
        "protection_configured",
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
        self.engine_commit = (
            engine_commit if engine_commit is not None else _git_commit()
        )
        self.harness_commit = (
            harness_commit if harness_commit is not None else _harness_commit()
        )
        self.tick_seconds = float(tick_seconds)
        self.writer = ArtifactWriter(self.output_dir / "artifacts")
        self.cache = RunManifestCache(self.output_dir / "cache")

    @staticmethod
    def _study_class_for_scenario(scenario_id: str) -> str:
        return study_class_for_scenario(scenario_id)

    def _expanded_spec(
        self,
        scenario_id: str,
        parameter_overrides: Mapping[str, Any] | None,
        duration_seconds: float | None,
    ) -> dict[str, Any]:
        study_class = self._study_class_for_scenario(scenario_id)
        if study_class == STUDY_CLASS_ADDENDUM_H:
            # Keep the existing compact H catalogue loading and expansion path.
            spec = expand_phase2b_reference_spec(
                _load_compact_spec(scenario_id)
            )
        else:
            base_path = (
                Path(__file__).resolve().parents[1]
                / "config"
                / "scenarios"
                / f"{BASE_DEMO_SCENARIO_ID}.json"
            )
            # DR D8 supersedes DR-2026-09-24-BASE-STUDY Phase 1.2 raw loading.
            # H references deliberately retain their separate expansion above.
            spec = ScenarioSpec.model_validate_json(
                base_path.read_bytes()
            ).model_dump(mode="json")
            spec["turbine_units"] = apply_study_fuel_model(
                spec.get("turbine_units", [])
            )
            # PROPOSED_HERE: provenance labels describe overrides, not control parameters.
            spec["study_input_provenance"] = {
                "canonicalised": True,
                "validation": "ScenarioSpec.model_validate_json -> model_dump(mode=json)",
                "source": f"config/scenarios/{BASE_DEMO_SCENARIO_ID}.json",
                "post_validation_overrides": [
                    {"field": "turbine_units", "operation": "apply_study_fuel_model"},
                ],
            }
        if duration_seconds is not None:
            spec["end_sim_time"] = float(duration_seconds)
        if parameter_overrides:
            _deep_merge(spec, parameter_overrides)
        if study_class == STUDY_CLASS_BASE_DEMO:
            overrides = spec["study_input_provenance"]["post_validation_overrides"]
            if duration_seconds is not None:
                overrides.append({"field": "end_sim_time", "value": float(duration_seconds)})
            if parameter_overrides:
                overrides.append({"operation": "parameter_overrides", "value": copy.deepcopy(parameter_overrides)})
        return spec

    @staticmethod
    def resolve_seed_manifest(
        spec: Mapping[str, Any],
        seed: int | str | None,
    ) -> dict[str, Any]:
        seed_names, configured_seeds = seed_consumers_for_spec(spec)
        return resolve_run_seed_manifest(
            seed,
            consumer_names=seed_names,
            configured_seeds=configured_seeds,
        )

    def _probe(
        self,
        spec: dict[str, Any],
        *,
        run_id: str,
        seed_manifest: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[tuple[float, float]]]:
        probe_spec = copy.deepcopy(spec)
        probe_spec["turbine_commitment_mode"] = "baseline"
        ctx = build_run_context_from_spec(
            run_id,
            probe_spec,
            playback_speed=0.0,
            run_seed=seed_manifest["root_seed"],
            seed_manifest=seed_manifest,
            execution_mode="study",
        )
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
        seed_manifest: dict[str, Any],
        allow_guard_failure: bool = False,
        reuse_cache: bool = True,
        progress_callback: Any | None = None,
        identity: RunIdentity | None = None,
    ) -> dict[str, Any]:
        study_class = self._study_class_for_scenario(scenario_id)
        run_spec = copy.deepcopy(spec)
        run_spec["turbine_commitment_mode"] = mode
        run_spec.pop("kube_clusters", None)
        run_spec.pop("slurm_config", None)
        run_spec["workload_events"] = replay_events
        duration_seconds = float(run_spec["end_sim_time"])
        if identity is None:
            identity = make_study_run_identity(
                scenario_id=scenario_id,
                mode=mode,
                spec=run_spec,
                seed=seed_manifest["root_seed"],
                tick_seconds=self.tick_seconds,
                engine_commit=self.engine_commit,
                harness_commit=self.harness_commit,
            )
        elif (
            identity.scenario_id != scenario_id
            or identity.mode != mode
            or str(identity.seed) != str(seed_manifest["root_seed"])
        ):
            raise ValueError("prepared study identity does not match run inputs")

        def execute() -> dict[str, Any]:
            ctx = build_run_context_from_spec(
                f"{scenario_id}-{mode}-study-s1",
                run_spec,
                playback_speed=0.0,
                run_seed=seed_manifest["root_seed"],
                seed_manifest=seed_manifest,
                execution_mode="study",
            )
            ctx.sim_state.demand_replay_trace = demand_replay
            frequency_feedback = bool(
                ctx.metadata.get("frequency_feedback_configured", False)
            )
            collector = MetricsCollector(
                self.tick_seconds,
                frequency_feedback_configured=frequency_feedback,
            )
            tick_rows: list[dict[str, Any]] = []
            physical_hasher = PhysicalIdentityHasher()
            tick_count = int(round(duration_seconds / self.tick_seconds))
            diesel_fleet = ctx.sim_state.diesel_fleet_coordinator
            diesel_fuel_initial_gal = (
                float(diesel_fleet.fuel_remaining_gal)
                if diesel_fleet is not None
                else None
            )
            for _ in range(tick_count):
                tick = ctx.step()
                physical_hasher.update(tick)
                collector.add(tick)
                compact = _compact_tick(tick)
                # Keep the additive CPU IT quantity in opt-in study artifacts
                # only; absent profiles leave the established compact schema alone.
                if run_spec.get("non_gpu_load_profile_mw") is not None:
                    compact["p_non_gpu_demand_mw"] = float(
                        getattr(tick, "p_non_gpu_demand_mw", 0.0) or 0.0
                    )
                tick_rows.append(compact)
                if progress_callback is not None and (
                    len(tick_rows) == tick_count
                    or len(tick_rows) % 100 == 0
                ):
                    progress_callback(len(tick_rows) * self.tick_seconds)
            raw_metadata = _controller_metadata(ctx)
            raw_metadata["build_warnings"] = ctx.metadata.get("build_warnings", [])
            raw_metadata["frequency_feedback_configured"] = frequency_feedback
            raw_metadata["seed_manifest"] = copy.deepcopy(
                ctx.metadata.get("seed_manifest", seed_manifest)
            )
            raw_metadata["physical_identity_sha256"] = physical_hasher.hexdigest()
            if "study_input_provenance" in spec:
                provenance = copy.deepcopy(spec["study_input_provenance"])
                provenance["post_validation_overrides"].extend([
                    {"field": "turbine_commitment_mode", "value": mode},
                    {"operation": "baseline_demand_replay", "tick_count": len(demand_replay)},
                    {"operation": "baseline_workload_replay", "event_count": len(replay_events),
                     "removed_fields": ["kube_clusters", "slurm_config"]},
                ])
                raw_metadata["study_input_provenance"] = provenance
            raw_metadata.update(
                {
                    "run_id": f"{scenario_id}-{mode}-{identity.digest[:16]}",
                    "scenario_id": scenario_id,
                    "study_class": study_class,
                    "mode": mode,
                    "engine_commit": self.engine_commit,
                    "harness_commit": self.harness_commit,
                }
            )
            guard_failure: dict[str, Any] | None = None
            try:
                metrics = collector.finalize(
                    run_record=raw_metadata,
                    commitment_log=raw_metadata["commitment_log"],
                )
            except HarnessGuardError as error:
                if not allow_guard_failure:
                    raise
                if not isinstance(error, StartFuelReconciliationError):
                    raise
                # Preserve the hard guard and the original recorded list, but
                # use measured tick telemetry only to finish diagnostic
                # accounting.  This allows a failed run to publish its total
                # without converting missing controller events into a pass.
                guard_failure = error_payload(error)
                diagnostic_record = dict(raw_metadata)
                diagnostic_record["starts"] = [
                    {
                        "action": "start",
                        "accepted": True,
                        "changed_state": True,
                        "sim_time_s": event["sim_time_s"],
                        "unit_id": event["unit_id"],
                        "tier_fuel_mmbtu": event["tier_fuel_mmbtu"],
                    }
                    for event in collector.measured_start_events
                ]
                metrics = collector.finalize(
                    run_record=diagnostic_record,
                    commitment_log=raw_metadata["commitment_log"],
                )
                reconciliation = metrics["start_fuel_reconciliation"]
                reconciliation["passed"] = False
                reconciliation["recorded_event_count"] = (
                    error.recorded_event_count
                )
                reconciliation["measured_event_count"] = (
                    error.measured_event_count
                )
            operating_cost_inputs = run_spec.get("operating_cost_inputs")
            if operating_cost_inputs is not None:
                fuel_basis_by_unit = {
                    str(unit.get("asset_id") or f"turbine-{i}"): (
                        (unit.get("fuel") or {}).get("heat_rate_basis")
                    )
                    for i, unit in enumerate(run_spec.get("turbine_units", []))
                }
                fuel_by_unit = {
                    str(unit_id): sum(
                        float(component or 0.0)
                        for component in components.values()
                    )
                    for unit_id, components in collector.previous_cumulative.items()
                }
                fuel_rows = list(collector.last_telemetry.values())
                fuel_complete = bool(fuel_rows) and all(
                    row.get("fuel_modelled") is True for row in fuel_rows
                )
                diesel_fuel_used_gal = None
                if (
                    diesel_fuel_initial_gal is not None
                    and ctx.sim_state.diesel_fleet_coordinator is not None
                ):
                    diesel_fuel_used_gal = max(
                        0.0,
                        diesel_fuel_initial_gal
                        - float(
                            ctx.sim_state.diesel_fleet_coordinator.fuel_remaining_gal
                        ),
                    )
                operating_cost = compute_operating_cost(
                    operating_cost_inputs,
                    tick_rows,
                    interval_seconds=self.tick_seconds,
                    turbine_fuel_by_unit_mmbtu=fuel_by_unit,
                    fuel_basis_by_unit=fuel_basis_by_unit,
                    fuel_quantity_complete=fuel_complete,
                    diesel_fuel_gallons=diesel_fuel_used_gal,
                    turbine_rated_mw=sum(
                        float(unit.get("rated_mw", 0.0))
                        for unit in run_spec.get("turbine_units", [])
                    ),
                    turbine_start_count=sum(
                        int(getattr(turbine, "_start_count", 0))
                        for turbine in ctx.sim_state.turbines
                    ),
                )
                if operating_cost is not None:
                    metrics["operating_cost"] = operating_cost

            metadata = dict(raw_metadata)
            metadata["commitment_log_record_count"] = len(
                raw_metadata["commitment_log"]
            )
            metadata["stop_floor_refusal_count"] = len(
                raw_metadata["stop_floor_refusals"]
            )
            record = {
                **metadata,
                **metrics,
                # Telemetry is the complete event evidence.  Keep the
                # controller's original starts list untouched so a recording
                # defect remains visible, while emitting the measured event
                # sequence for downstream metrics and audit work.
                "measured_start_event_count": len(
                    collector.measured_start_events
                ),
                "measured_start_events": collector.measured_start_events,
                "identity": identity.payload(),
                "identity_digest": identity.digest,
                "replay_strategy": "baseline demand trace replay",
            }
            if guard_failure is not None:
                record["status"] = "FAIL"
                record["guard_failures"] = [guard_failure]
            else:
                record["status"] = "PASS"
            artifacts = self.writer.write(
                identity=identity,
                record=record,
                summary=metrics,
                tick_rows=tick_rows,
            )
            record["artifacts"] = artifacts.as_dict()
            return record

        if reuse_cache:
            record, cache_hit = self.cache.get_or_execute(identity, execute)
        else:
            record = self.cache.put(identity, execute())
            cache_hit = False
        record = dict(record)
        record["cache_hit"] = cache_hit
        return record

    def run_mode(
        self,
        *,
        scenario_id: str,
        mode: str,
        parameter_overrides: Mapping[str, Any] | None = None,
        seed: int | str | None = None,
        duration_seconds: float | None = None,
        allow_guard_failures: bool = False,
        reuse_cache: bool = True,
        progress_callback: Any | None = None,
        seed_manifest: dict[str, Any] | None = None,
        identity: RunIdentity | None = None,
    ) -> dict[str, Any]:
        """Execute one mode through the same S1 probe/replay path as run_pair."""
        if mode not in {"baseline", "informed"}:
            raise ValueError("mode must be baseline or informed")
        if seed_cache_bypass_reason(
            reuse_cache=reuse_cache,
            requested_seed=seed,
        ):
            reuse_cache = False
        spec = self._expanded_spec(
            scenario_id,
            parameter_overrides,
            duration_seconds,
        )
        if seed_manifest is None:
            seed_manifest = self.resolve_seed_manifest(spec, seed)
        else:
            manifest_seed = seed_manifest.get("root_seed")
            if manifest_seed is None:
                raise ValueError("prepared seed manifest has no root_seed")
            if seed is not None and str(seed) != str(manifest_seed):
                raise ValueError("seed does not match prepared seed manifest")
            seed = manifest_seed
        replay_events, demand_replay = self._probe(
            spec,
            run_id=f"{scenario_id}-study-s1-probe",
            seed_manifest=seed_manifest,
        )
        return self._run_mode(
            scenario_id=scenario_id,
            mode=mode,
            spec=spec,
            replay_events=replay_events,
            demand_replay=demand_replay,
            seed=seed_manifest["root_seed"],
            seed_manifest=seed_manifest,
            allow_guard_failure=allow_guard_failures,
            reuse_cache=reuse_cache,
            progress_callback=progress_callback,
            identity=identity,
        )

    def run_pair(
        self,
        *,
        scenario_id: str,
        parameter_overrides: Mapping[str, Any] | None = None,
        seed: int | str | None = None,
        duration_seconds: float | None = None,
        allow_guard_failures: bool = False,
    ) -> dict[str, Any]:
        cache_bypass_reason = seed_cache_bypass_reason(
            reuse_cache=True,
            requested_seed=seed,
        )
        reuse_cache = cache_bypass_reason is None
        spec = self._expanded_spec(
            scenario_id,
            parameter_overrides,
            duration_seconds,
        )
        seed_manifest = self.resolve_seed_manifest(spec, seed)
        replay_events, demand_replay = self._probe(
            spec,
            run_id=f"{scenario_id}-study-s1-probe",
            seed_manifest=seed_manifest,
        )
        baseline = self._run_mode(
            scenario_id=scenario_id,
            mode="baseline",
            spec=spec,
            replay_events=replay_events,
            demand_replay=demand_replay,
            seed=seed,
            seed_manifest=seed_manifest,
            allow_guard_failure=allow_guard_failures,
            reuse_cache=reuse_cache,
        )
        informed = self._run_mode(
            scenario_id=scenario_id,
            mode="informed",
            spec=spec,
            replay_events=replay_events,
            demand_replay=demand_replay,
            seed=seed,
            seed_manifest=seed_manifest,
            allow_guard_failure=allow_guard_failures,
            reuse_cache=reuse_cache,
        )
        from .acceptance import compare_metrics

        comparison = compare_metrics(baseline, informed)
        return {
            "scenario_id": scenario_id,
            "study_class": self._study_class_for_scenario(scenario_id),
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
    detail_path: Path | None = None,
    minimum_down_seconds_by_unit: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Run S1 guards over a stored run without re-simulating it."""
    record = json.loads(Path(record_path).read_text())
    if detail_path is not None:
        with gzip.open(Path(detail_path), "rt", encoding="utf-8") as handle:
            details = json.load(handle)
        if not isinstance(details, Mapping):
            raise ValueError("detail sidecar must contain a JSON object")
        record_details = details.get("record", {})
        if not isinstance(record_details, Mapping):
            raise ValueError("detail sidecar record section must be an object")
        record.update(record_details)
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