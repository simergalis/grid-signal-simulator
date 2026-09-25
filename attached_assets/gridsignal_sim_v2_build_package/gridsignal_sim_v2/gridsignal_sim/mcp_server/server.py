"""Streamable-HTTP MCP boundary for the S1 study harness.

This module deliberately contains transport, authorization, pagination, and
serialization only.  Simulation behavior remains in ``study_harness`` and the
engine it imports.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from study_harness.acceptance import compare_metrics
from study_harness.errors import (
    BuildParityMismatchError,
    FuelModelAbsentError,
    HarnessGuardError,
    StudyClassMismatchError,
    error_payload,
)
from study_harness.executor import (
    BASE_DEMO_SCENARIO_ID,
    STUDY_CLASS_BASE_DEMO,
    StudyRunExecutor,
    make_study_run_identity,
    study_class_for_scenario,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[5]
SCENARIO_ROOT = PACKAGE_ROOT / "config" / "scenarios"
RESULTS_ROOT = REPO_ROOT / "docs" / "addendum-h-phase2b-results"
DATA_ROOT = REPO_ROOT / ".study-mcp-data"

PROTOCOL_VERSION = "2025-03-26"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_TICK_ROWS = 1000
TRACE_TOLERANCE = 1e-9
ESTIMATED_SECONDS_PER_TICK = 0.02  # PROPOSED_HERE: conservative local estimate.

REFERENCE_SCENARIOS = (
    "scenario-h1-k8s-ray-24h",
    "scenario-h1-k8s-ray-7d",
    "scenario-h2-slurm-24h",
    "scenario-h2-slurm-7d",
)
BASE_SCENARIO = BASE_DEMO_SCENARIO_ID
# PROPOSED_HERE: This is the explicit MCP allowlist for the five S1 study scenarios.
STUDY_SCENARIOS = (*REFERENCE_SCENARIOS, BASE_SCENARIO)
SCENARIO_IDS = STUDY_SCENARIOS


class McpBoundaryError(Exception):
    """A typed tool-level error serialized as JSON, never prose-only."""

    code = "MCP_ERROR"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {
            "error": {
                "type": self.code,
                "message": str(self),
                **self.details,
            }
        }


class NotFoundIdentifierError(McpBoundaryError):
    code = "NOT_FOUND_IDENTIFIER"


class ReplayTraceMismatchError(McpBoundaryError):
    code = "REPLAY_TRACE_MISMATCH"


class BuildParityBoundaryError(McpBoundaryError):
    code = "BUILD_PARITY_MISMATCH"


class IncompleteSourceListError(McpBoundaryError):
    code = "INCOMPLETE_SOURCE_LIST"


class FailedRunError(McpBoundaryError):
    code = "FAILED_RUN"


class AuthorizationError(McpBoundaryError):
    code = "UNAUTHORIZED"


class RateLimitError(McpBoundaryError):
    code = "RATE_LIMITED"


class InvalidArgumentError(McpBoundaryError):
    code = "INVALID_ARGUMENT"


@dataclass
class RunState:
    run_id: str
    scenario_id: str
    mode: str
    identity_digest: str
    status: str = "QUEUED"
    cache_hit: bool = False
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    simulated_time_seconds: float = 0.0
    total_time_seconds: float = 0.0
    checkpoints: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None
    record: dict[str, Any] | None = None
    ticks_path: Path | None = None
    future: Future[Any] | None = None

    def status_payload(self) -> dict[str, Any]:
        now = time.time()
        started = self.started_at or now
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "mode": self.mode,
            "status": self.status,
            "cache_hit": self.cache_hit,
            "progress": (
                min(1.0, self.simulated_time_seconds / self.total_time_seconds)
                if self.total_time_seconds > 0
                else (1.0 if self.status == "COMPLETED" else 0.0)
            ),
            "simulated_time_seconds": self.simulated_time_seconds,
            "total_time_seconds": self.total_time_seconds,
            "wall_clock_elapsed_seconds": max(
                0.0,
                (self.finished_at or now) - started,
            ),
            "checkpoints": list_page(self.checkpoints, page_size=MAX_PAGE_SIZE),
            "error": self.error,
        }


def list_page(
    items: Iterable[Any],
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    total_override: int | None = None,
    source_truncated: bool = False,
    omitted_source_count: int = 0,
) -> dict[str, Any]:
    """Return an explicit pagination envelope for every list-shaped payload."""
    page = max(1, int(page))
    page_size = min(MAX_PAGE_SIZE, max(1, int(page_size)))
    materialized = list(items)
    total = len(materialized) if total_override is None else int(total_override)
    start = (page - 1) * page_size
    selected = materialized[start : start + page_size]
    return {
        "items": selected,
        "total": total,
        "returned": len(selected),
        "page": page,
        "page_size": page_size,
        "has_more": start + len(selected) < total,
        "source_truncated": bool(source_truncated),
        "omitted_source_count": max(0, int(omitted_source_count)),
    }


def _json(value: Any) -> Any:
    """Make dataclass-ish harness values JSON-compatible."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as error:
        raise NotFoundIdentifierError(
            "identifier source was not found",
            identifier=str(path),
            kind="file",
        ) from error


def _scenario_path(scenario_id: str) -> Path:
    if scenario_id not in SCENARIO_IDS:
        raise NotFoundIdentifierError(
            "scenario identifier was not found",
            identifier=scenario_id,
            kind="scenario",
        )
    return SCENARIO_ROOT / f"{scenario_id}.json"


def _committed_run_paths(run_id: str) -> tuple[Path, Path] | None:
    for scenario_id in (*REFERENCE_SCENARIOS,):
        for mode in ("baseline", "informed"):
            candidate = f"{scenario_id}-{mode}"
            if candidate == run_id:
                return (
                    RESULTS_ROOT / f"{candidate}.json",
                    RESULTS_ROOT / f"{candidate}_ticks.jsonl.gz",
                )
    return None


def _run_id_for(scenario_id: str, mode: str, digest: str) -> str:
    return f"{scenario_id}-{mode}-{digest[:16]}"


def _compact_committed_record(record: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    record = copy.deepcopy(record)
    record.setdefault("run_id", run_id)
    record.setdefault("status", "COMPLETED")
    record.setdefault("cache_hit", True)
    # S1 committed artifacts predate commit fields; retaining explicit
    # "unknown" values makes parity behavior fail closed rather than inventing
    # provenance.
    record.setdefault("engine_commit", "unknown")
    record.setdefault("harness_commit", "unknown")
    return record


def _iter_tick_rows(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


class RateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, int(limit))
        self._lock = threading.Lock()
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def check(self, principal: str) -> None:
        now = time.time()
        with self._lock:
            calls = self._calls[principal]
            while calls and now - calls[0] >= 60.0:
                calls.popleft()
            if len(calls) >= self.limit:
                raise RateLimitError(
                    "start_run rate limit exceeded",
                    principal=principal,
                    limit_per_minute=self.limit,
                    retry_after_seconds=max(1, int(60 - (now - calls[0]))),
                )
            calls.append(now)


class StudyService:
    def __init__(self) -> None:
        self.executor = StudyRunExecutor(output_dir=DATA_ROOT)
        self._lock = threading.RLock()
        self._runs: dict[str, RunState] = {}
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, int(os.environ.get("GRIDSIGNAL_MCP_MAX_WORKERS", "1"))),
            thread_name_prefix="gridstudy-mcp",
        )
        self._rate_limiter = RateLimiter(
            int(os.environ.get("GRIDSIGNAL_MCP_RATE_LIMIT_PER_MINUTE", "4"))
        )
        self._load_committed_runs()

    def _load_committed_runs(self) -> None:
        for scenario_id in REFERENCE_SCENARIOS:
            for mode in ("baseline", "informed"):
                run_id = f"{scenario_id}-{mode}"
                record_path, ticks_path = _committed_run_paths(run_id) or (None, None)
                if not record_path or not record_path.is_file():
                    continue
                record = _compact_committed_record(
                    _read_json(record_path),
                    run_id=run_id,
                )
                total = float(record.get("duration_seconds") or 0.0)
                if not total:
                    total = float(record.get("sim_time_seconds") or 0.0)
                self._runs[run_id] = RunState(
                    run_id=run_id,
                    scenario_id=scenario_id,
                    mode=mode,
                    identity_digest=str(record.get("identity_digest", "")),
                    status="COMPLETED",
                    cache_hit=True,
                    started_at=None,
                    finished_at=None,
                    simulated_time_seconds=total,
                    total_time_seconds=total,
                    checkpoints=["loaded_committed_record", "completed"],
                    record=record,
                    ticks_path=ticks_path if ticks_path.is_file() else None,
                )

    def scenario_list(self, *, page: int, page_size: int) -> dict[str, Any]:
        scenarios: list[dict[str, Any]] = []
        for scenario_id in STUDY_SCENARIOS:
            path = _scenario_path(scenario_id)
            spec = _read_json(path)
            scenarios.append(
                {
                    "scenario_id": scenario_id,
                    "name": spec.get("name", scenario_id),
                    "description": spec.get("description", ""),
                    "kind": "addendum_h" if scenario_id in REFERENCE_SCENARIOS else "base",
                    "study_supported": scenario_id in STUDY_SCENARIOS,
                    "study_class": study_class_for_scenario(scenario_id),
                }
            )
        return {"scenarios": list_page(scenarios, page=page, page_size=page_size)}

    def scenario(self, scenario_id: str) -> dict[str, Any]:
        path = _scenario_path(scenario_id)
        return {
            "scenario_id": scenario_id,
            "source": str(path.relative_to(REPO_ROOT)),
            "spec": _read_json(path),
        }

    def _record(self, run_id: str) -> tuple[RunState, dict[str, Any]]:
        with self._lock:
            state = self._runs.get(run_id)
        if state is None:
            raise NotFoundIdentifierError(
                "run identifier was not found",
                identifier=run_id,
                kind="run",
            )
        if state.status == "FAILED":
            raise FailedRunError(
                "run failed",
                run_id=run_id,
                status=state.status,
                run_error=state.error,
            )
        if state.record is None:
            raise FailedRunError(
                "run has not completed",
                run_id=run_id,
                status=state.status,
            )
        return state, state.record

    def status(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._runs.get(run_id)
        if state is None:
            raise NotFoundIdentifierError(
                "run identifier was not found",
                identifier=run_id,
                kind="run",
            )
        payload = state.status_payload()
        payload["study_class"] = (
            state.record.get("study_class")
            if state.record and state.record.get("study_class")
            else study_class_for_scenario(state.scenario_id)
        )
        return payload

    def _identity(
        self,
        *,
        scenario_id: str,
        mode: str,
        parameter_overrides: Mapping[str, Any] | None,
        seed: int | str | None,
    ):
        spec = self.executor._expanded_spec(scenario_id, parameter_overrides, None)
        return make_study_run_identity(
            scenario_id=scenario_id,
            mode=mode,
            spec=spec,
            seed=seed,
            tick_seconds=self.executor.tick_seconds,
            engine_commit=self.executor.engine_commit,
            harness_commit=self.executor.harness_commit,
        )

    def start(
        self,
        *,
        scenario_id: str,
        mode: str,
        parameter_overrides: Mapping[str, Any] | None,
        seed: int | str | None,
        reuse_cache: bool,
        principal: str,
    ) -> dict[str, Any]:
        if scenario_id not in STUDY_SCENARIOS:
            raise InvalidArgumentError(
                "start_run supports the listed study scenarios only",
                scenario_id=scenario_id,
                supported_scenarios=list_page(STUDY_SCENARIOS),
            )
        if mode not in {"baseline", "informed"}:
            raise InvalidArgumentError(
                "mode must be baseline or informed",
                mode=mode,
            )
        self._rate_limiter.check(principal)
        identity = self._identity(
            scenario_id=scenario_id,
            mode=mode,
            parameter_overrides=parameter_overrides,
            seed=seed,
        )
        run_id = _run_id_for(scenario_id, mode, identity.digest)
        cached = self.executor.cache.get(identity) if reuse_cache else None
        if cached is not None:
            record = dict(cached)
            record["cache_hit"] = True
            artifact_paths = record.get("artifacts", {}).get("paths", {})
            ticks_path = artifact_paths.get("ticks")
            state = RunState(
                run_id=run_id,
                scenario_id=scenario_id,
                mode=mode,
                identity_digest=identity.digest,
                status="COMPLETED",
                cache_hit=True,
                simulated_time_seconds=float(identity.duration_seconds),
                total_time_seconds=float(identity.duration_seconds),
                checkpoints=["cache_lookup", "completed"],
                record=record,
                ticks_path=Path(ticks_path) if ticks_path else None,
            )
            with self._lock:
                self._runs[run_id] = state
            return {
                "run_id": run_id,
                "status": "COMPLETED",
                "cache_hit": True,
                "estimated_wall_clock_seconds": 0.0,
            }

        state = RunState(
            run_id=run_id,
            scenario_id=scenario_id,
            mode=mode,
            identity_digest=identity.digest,
            total_time_seconds=float(identity.duration_seconds),
            checkpoints=["queued"],
        )
        with self._lock:
            self._runs[run_id] = state
        state.future = self._pool.submit(
            self._execute,
            state,
            parameter_overrides,
            seed,
            reuse_cache,
        )
        estimate = max(
            1.0,
            identity.duration_seconds / self.executor.tick_seconds
            * ESTIMATED_SECONDS_PER_TICK,
        )
        return {
            "run_id": run_id,
            "status": "QUEUED",
            "cache_hit": False,
            "estimated_wall_clock_seconds": round(estimate, 3),
        }

    def _execute(
        self,
        state: RunState,
        parameter_overrides: Mapping[str, Any] | None,
        seed: int | str | None,
        reuse_cache: bool,
    ) -> None:
        with self._lock:
            state.status = "RUNNING"
            state.started_at = time.time()
            state.checkpoints = ["probe", "simulation"]

        def progress(simulated_seconds: float) -> None:
            with self._lock:
                state.simulated_time_seconds = min(
                    state.total_time_seconds,
                    float(simulated_seconds),
                )

        try:
            record = self.executor.run_mode(
                scenario_id=state.scenario_id,
                mode=state.mode,
                parameter_overrides=parameter_overrides,
                seed=seed,
                reuse_cache=reuse_cache,
                progress_callback=progress,
            )
            with self._lock:
                state.record = dict(record)
                artifact_paths = (
                    state.record.get("artifacts", {}).get("paths", {})
                )
                ticks_path = artifact_paths.get("ticks")
                state.ticks_path = Path(ticks_path) if ticks_path else None
                state.status = "COMPLETED"
                state.cache_hit = bool(record.get("cache_hit", False))
                state.simulated_time_seconds = state.total_time_seconds
                state.finished_at = time.time()
                state.checkpoints = [
                    "probe",
                    "simulation",
                    "metrics",
                    "artifacts",
                    "completed",
                ]
        except Exception as error:
            payload = _typed_error_payload(error)
            with self._lock:
                state.status = "FAILED"
                state.error = payload["error"]
                state.finished_at = time.time()
                state.checkpoints.append("failed")

    def metrics(
        self,
        run_id: str,
        *,
        section: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        state, record = self._record(run_id)
        reconciliation = self._reconciliation(record)
        sections = {
            "fuel": {
                key: record.get(key)
                for key in (
                    "fuel_by_component_mmbtu",
                    "turbine_fuel_mmbtu",
                    "fuel_reconciled",
                    "start_fuel_reconciliation",
                    "dispatch_curtailment_interval_exposure_fuel_mmbtu",
                    "dispatch_curtailment_attributable_fuel_mmbtu",
                )
                if key in record
            },
            "commitment": {"commitment": record.get("commitment")},
            "forecast": {"forecast": record.get("forecast")},
            "energy": {
                key: record.get(key)
                for key in (
                    "served_mwh",
                    "unserved_mwh",
                    "peak_unserved_mw",
                    "energy_balance",
                    "dispatch_curtailment_mwh",
                )
                if key in record
            },
            "daily": {
                "daily_breakdown": list_page(
                    record.get("daily_breakdown", []),
                    page=page,
                    page_size=page_size,
                )
            },
        }
        if section is not None and section not in sections:
            raise InvalidArgumentError(
                "unknown metric section",
                section=section,
                allowed_sections=list_page(sorted(sections)),
            )
        payload: dict[str, Any] = {
            "run_id": run_id,
            "status": record.get("status", "COMPLETED"),
            "study_class": (
                record.get("study_class")
                or study_class_for_scenario(state.scenario_id)
            ),
            "engine_commit": record.get("engine_commit", "unknown"),
            "harness_commit": record.get("harness_commit", "unknown"),
        }
        selected = sections if section is None else {section: sections[section]}
        for name, values in selected.items():
            payload[name] = _json(values)
        # These guards are included even when a caller asks for another section.
        payload["reconciliation"] = _json(reconciliation)
        return payload

    @staticmethod
    def _reconciliation(record: Mapping[str, Any]) -> dict[str, Any]:
        components = {
            str(key): float(value)
            for key, value in (record.get("fuel_by_component_mmbtu") or {}).items()
        }
        component_sum = sum(components.values())
        reported_total = float(record.get("turbine_fuel_mmbtu", component_sum))
        component_difference = component_sum - reported_total
        fuel_reconciled = bool(
            record.get("fuel_reconciled", abs(component_difference) <= 1e-6)
        )
        start_reconciliation = record.get("start_fuel_reconciliation")
        if start_reconciliation is None:
            start_reconciliation = {
                "passed": bool(record.get("start_count_reconciled", False)),
                "evidence_complete": False,
                "source": "legacy_stage1_record",
                "reported_start_fuel_mmbtu": components.get(
                    "start_fuel_mmbtu", 0.0
                ),
                "recorded_event_count": len(record.get("starts", []) or []),
            }
        interval_exposure = float(
            record.get("dispatch_curtailment_interval_exposure_fuel_mmbtu", 0.0)
        )
        attributable = float(
            record.get("dispatch_curtailment_attributable_fuel_mmbtu", 0.0)
        )
        return {
            "fuel_components_mmbtu": components,
            "fuel_component_sum_mmbtu": component_sum,
            "reported_turbine_fuel_mmbtu": reported_total,
            "fuel_component_difference_mmbtu": component_difference,
            "fuel_reconciled": fuel_reconciled,
            "start_fuel_reconciliation": _json(start_reconciliation),
            "curtailment_range_check": {
                "passed": 0.0 <= attributable <= interval_exposure + 1e-9,
                "interval_exposure_fuel_mmbtu": interval_exposure,
                "attributable_fuel_mmbtu": attributable,
                "plausible_range_mmbtu": [0.0, interval_exposure],
            },
            "fuel_guard": _json(record.get("fuel_guard")),
        }

    def _trace_difference(self, left: RunState, right: RunState) -> float:
        if not left.ticks_path or not right.ticks_path:
            return float("inf")
        difference = 0.0
        for left_row, right_row in zip_longest(
            _iter_tick_rows(left.ticks_path),
            _iter_tick_rows(right.ticks_path),
            fillvalue=None,
        ):
            if left_row is None or right_row is None:
                return float("inf")
            difference = max(
                difference,
                abs(
                    float(left_row.get("p_compute_mw", 0.0))
                    - float(right_row.get("p_compute_mw", 0.0))
                ),
            )
        return difference

    @staticmethod
    def _trace_digest(state: RunState) -> str | None:
        if not state.ticks_path or not state.ticks_path.is_file():
            return None
        digest = hashlib.sha256()
        count = 0
        for row in _iter_tick_rows(state.ticks_path):
            count += 1
            compute = float(
                row.get("p_compute_demand_mw", row.get("p_compute_mw", 0.0))
            )
            digest.update(f"{count}:{compute:.17g}\n".encode("utf-8"))
        return digest.hexdigest()

    def compare(self, baseline_run_id: str, informed_run_id: str) -> dict[str, Any]:
        baseline_state, baseline = self._record(baseline_run_id)
        informed_state, informed = self._record(informed_run_id)
        baseline_study_class = (
            baseline.get("study_class")
            or study_class_for_scenario(baseline_state.scenario_id)
        )
        informed_study_class = (
            informed.get("study_class")
            or study_class_for_scenario(informed_state.scenario_id)
        )
        if baseline_study_class != informed_study_class:
            raise StudyClassMismatchError(
                baseline_study_class=str(baseline_study_class),
                informed_study_class=str(informed_study_class),
                baseline_run_id=baseline_run_id,
                informed_run_id=informed_run_id,
            )
        baseline_for_compare = dict(baseline)
        informed_for_compare = dict(informed)
        baseline_for_compare.setdefault(
            "fuel_reconciled",
            self._reconciliation(baseline)["fuel_reconciled"],
        )
        informed_for_compare.setdefault(
            "fuel_reconciled",
            self._reconciliation(informed)["fuel_reconciled"],
        )
        baseline_for_compare.setdefault(
            "compute_trace_sha256",
            self._trace_digest(baseline_state),
        )
        informed_for_compare.setdefault(
            "compute_trace_sha256",
            self._trace_digest(informed_state),
        )
        try:
            comparison = compare_metrics(baseline_for_compare, informed_for_compare)
        except BuildParityMismatchError as error:
            raise BuildParityBoundaryError(
                str(error),
                baseline_engine_commit=error.baseline_engine_commit,
                informed_engine_commit=error.informed_engine_commit,
                baseline_harness_commit=error.baseline_harness_commit,
                informed_harness_commit=error.informed_harness_commit,
            ) from error
        if not comparison["conditions"]["identical_compute_trace"]:
            measured = self._trace_difference(baseline_state, informed_state)
            raise ReplayTraceMismatchError(
                "replay traces differ",
                measured_difference=measured,
                tolerance=TRACE_TOLERANCE,
                baseline_trace_sha256=baseline_for_compare.get("compute_trace_sha256"),
                informed_trace_sha256=informed_for_compare.get("compute_trace_sha256"),
            )
        conditions = []
        numeric_inputs = {
            "baseline_unserved_mwh": float(baseline.get("unserved_mwh", 0.0)),
            "informed_unserved_mwh": float(informed.get("unserved_mwh", 0.0)),
            "baseline_peak_unserved_mw": float(
                baseline.get("peak_unserved_mw", 0.0)
            ),
            "informed_peak_unserved_mw": float(
                informed.get("peak_unserved_mw", 0.0)
            ),
        }
        for name in comparison["condition_order"]:
            conditions.append(
                {
                    "name": name,
                    "passed": bool(comparison["conditions"][name]),
                    "inputs": {
                        **numeric_inputs,
                        "baseline_engine_commit": baseline.get("engine_commit"),
                        "informed_engine_commit": informed.get("engine_commit"),
                        "baseline_harness_commit": baseline.get("harness_commit"),
                        "informed_harness_commit": informed.get("harness_commit"),
                        "baseline_trace_sha256": baseline_for_compare.get(
                            "compute_trace_sha256"
                        ),
                        "informed_trace_sha256": informed_for_compare.get(
                            "compute_trace_sha256"
                        ),
                    },
                }
            )
        payload = {
            "baseline_run_id": baseline_run_id,
            "informed_run_id": informed_run_id,
            "study_class": baseline_study_class,
            "verdict": comparison["verdict"],
            "conditions": list_page(conditions, page_size=MAX_PAGE_SIZE),
            "numeric_inputs": numeric_inputs,
        }
        if baseline_study_class == STUDY_CLASS_BASE_DEMO:
            payload["claim_note"] = "demonstration scenario; not an Addendum H study result"
        return payload

    def commitment(
        self,
        run_id: str,
        *,
        unit_id: str | None,
        action: str | None,
        source: str | None,
        accepted: bool | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        state, record = self._record(run_id)
        raw = list(record.get("commitment_log", []) or [])
        exact_total = record.get("commitment_log_record_count")
        source_truncated = bool(exact_total is not None and int(exact_total) > len(raw))
        selected = [
            item
            for item in raw
            if (unit_id is None or item.get("unit_id") == unit_id)
            and (action is None or item.get("action") == action)
            and (source is None or item.get("source") == source)
            and (accepted is None or bool(item.get("accepted")) is accepted)
        ]
        if unit_id is None and action is None and source is None and accepted is None:
            total_override = int(exact_total) if exact_total is not None else None
        else:
            if source_truncated:
                raise IncompleteSourceListError(
                    "filtered commitment totals are unavailable because the "
                    "committed S1 source log is bounded",
                    run_id=run_id,
                    available_entry_count=len(raw),
                    true_unfiltered_entry_count=int(exact_total),
                    filters={
                        "unit_id": unit_id,
                        "action": action,
                        "source": source,
                        "accepted": accepted,
                    },
                )
            total_override = None
        return {
            "run_id": run_id,
            "entries": list_page(
                selected,
                page=page,
                page_size=page_size,
                total_override=total_override,
                source_truncated=source_truncated,
                omitted_source_count=(
                    max(0, int(exact_total) - len(raw))
                    if exact_total is not None
                    else 0
                ),
            ),
            "source_complete": not source_truncated,
            "source_note": (
                "S1 committed record contains a bounded representative log; "
                "total is the exact recorded event count."
                if source_truncated
                else None
            ),
        }

    def ticks(
        self,
        run_id: str,
        *,
        start_seconds: float | None,
        end_seconds: float | None,
        fields: list[str],
        stride: int,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        state, _ = self._record(run_id)
        if not fields:
            raise InvalidArgumentError(
                "fields must contain at least one explicit field",
                field_count=0,
            )
        if stride < 1:
            raise InvalidArgumentError("stride must be at least 1", stride=stride)
        if state.ticks_path is None or not state.ticks_path.is_file():
            raise NotFoundIdentifierError(
                "tick artifact was not found",
                identifier=run_id,
                kind="ticks",
            )
        rows: list[dict[str, Any]] = []
        matched = 0
        for row in _iter_tick_rows(state.ticks_path):
            timestamp = float(
                row.get("sim_time_seconds", row.get("sim_time_s", 0.0))
            )
            if start_seconds is not None and timestamp < start_seconds:
                continue
            if end_seconds is not None and timestamp > end_seconds:
                continue
            if matched % stride == 0:
                rows.append({field: row.get(field) for field in fields})
            matched += 1
        total = (matched + stride - 1) // stride
        return {
            "run_id": run_id,
            "ticks": list_page(
                rows,
                page=page,
                page_size=min(page_size, MAX_TICK_ROWS),
                total_override=total,
                source_truncated=False,
            ),
            "row_cap": MAX_TICK_ROWS,
            "stride": stride,
            "fields": list_page(fields, page_size=MAX_PAGE_SIZE),
        }


def _typed_error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, McpBoundaryError):
        return error.payload()
    if isinstance(error, StudyClassMismatchError):
        return {
            "error": {
                "type": error.code,
                "message": str(error),
                "baseline_study_class": error.baseline_study_class,
                "informed_study_class": error.informed_study_class,
                "baseline_run_id": error.baseline_run_id,
                "informed_run_id": error.informed_run_id,
            }
        }
    if isinstance(error, BuildParityMismatchError):
        return {
            "error": {
                "type": "BUILD_PARITY_MISMATCH",
                "message": str(error),
                "baseline_engine_commit": error.baseline_engine_commit,
                "informed_engine_commit": error.informed_engine_commit,
                "baseline_harness_commit": error.baseline_harness_commit,
                "informed_harness_commit": error.informed_harness_commit,
            }
        }
    if isinstance(error, FuelModelAbsentError):
        return {
            "error": {
                "type": "FUEL_MODEL_ABSENT",
                "message": str(error),
                "unit_ids": list_page(error.unit_ids),
            }
        }
    if isinstance(error, HarnessGuardError):
        return {
            "error": {
                "type": "FAILED_RUN",
                "message": str(error),
                "guard": error_payload(error),
            }
        }
    return {
        "error": {
            "type": "FAILED_RUN",
            "message": str(error),
            "exception_type": type(error).__name__,
        }
    }


def _auth_tokens() -> tuple[str | None, str | None]:
    return (
        os.environ.get("GRIDSIGNAL_MCP_READ_TOKEN"),
        os.environ.get("GRIDSIGNAL_MCP_RUN_TOKEN"),
    )


def _authorize(request: Request, *, needs_run: bool) -> str:
    read_token, run_token = _auth_tokens()
    supplied = request.headers.get("authorization", "")
    token = supplied.removeprefix("Bearer ").strip()
    if needs_run:
        if not run_token:
            raise AuthorizationError(
                "MCP authorization is not configured",
                required_scope="run",
            )
        if token != run_token:
            raise AuthorizationError(
                "authorization token does not grant the required scope",
                required_scope="run",
            )
        return "run"

    # A single remote MCP connector commonly uses one bearer token for both
    # tools/list and tools/call.  The run token is therefore read-capable as
    # well as run-capable; otherwise a Claude connector using the run token
    # cannot discover any tools before it attempts start_run.
    if token and run_token and token == run_token:
        return "run"
    if token and read_token and token == read_token:
        return "read"
    if not read_token and not run_token:
        raise AuthorizationError(
            "MCP authorization is not configured",
            required_scope="read",
        )
    raise AuthorizationError(
        "authorization token does not grant the required scope",
        required_scope="read",
    )


READ_TOOLS = {
    "list_scenarios",
    "get_scenario",
    "get_run_status",
    "get_run_metrics",
    "compare_runs",
    "get_commitment_log",
    "get_ticks",
}


def _tool_definitions() -> list[dict[str, Any]]:
    # Schemas are intentionally explicit so connector UIs can render them
    # without importing the Python harness.
    return [
        {
            "name": "list_scenarios",
            "description": "List Addendum H study scenarios and the base scenario.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
                },
            },
        },
        {
            "name": "get_scenario",
            "description": "Return one scenario specification.",
            "inputSchema": {
                "type": "object",
                "required": ["scenario_id"],
                "properties": {"scenario_id": {"type": "string"}},
            },
        },
        {
            "name": "get_run_status",
            "description": "Return asynchronous study-run progress and errors.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {"run_id": {"type": "string"}},
            },
        },
        {
            "name": "get_run_metrics",
            "description": "Return S1 metrics and reconciliation guards.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "section": {
                        "type": "string",
                        "enum": ["fuel", "commitment", "forecast", "energy", "daily"],
                    },
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
                },
            },
        },
        {
            "name": "compare_runs",
            "description": "Return every S1 acceptance condition and its inputs.",
            "inputSchema": {
                "type": "object",
                "required": ["baseline_run_id", "informed_run_id"],
                "properties": {
                    "baseline_run_id": {"type": "string"},
                    "informed_run_id": {"type": "string"},
                },
            },
        },
        {
            "name": "get_commitment_log",
            "description": "Return a filtered, explicitly paginated commitment log.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "unit_id": {"type": "string"},
                    "action": {"type": "string"},
                    "source": {"type": "string"},
                    "accepted": {"type": "boolean"},
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 200},
                },
            },
        },
        {
            "name": "get_ticks",
            "description": "Return selected tick fields in an explicit time range and stride.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id", "fields"],
                "properties": {
                    "run_id": {"type": "string"},
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "fields": {"type": "array", "items": {"type": "string"}},
                    "stride": {"type": "integer", "minimum": 1},
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
            },
        },
        {
            "name": "start_run",
            "description": "Start one asynchronous baseline or informed study-harness run.",
            "inputSchema": {
                "type": "object",
                "required": ["scenario_id", "mode"],
                "properties": {
                    "scenario_id": {"type": "string"},
                    "mode": {"type": "string", "enum": ["baseline", "informed"]},
                    "parameter_overrides": {"type": "object"},
                    "seed": {"type": ["integer", "string", "null"]},
                    "reuse_cache": {"type": "boolean", "default": True},
                },
            },
        },
    ]


service = StudyService()
app = FastAPI(title="GridSignal Study Harness MCP", version="S3")
_sessions: set[str] = set()


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    encoded = json.dumps(_json(payload), sort_keys=True, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": encoded}],
        "structuredContent": _json(payload),
        "isError": is_error,
    }


def _call_tool(name: str, arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    needs_run = name == "start_run"
    principal = _authorize(request, needs_run=needs_run)
    page = int(arguments.get("page", 1))
    page_size = int(arguments.get("page_size", DEFAULT_PAGE_SIZE))
    if name == "list_scenarios":
        return service.scenario_list(page=page, page_size=page_size)
    if name == "get_scenario":
        return service.scenario(str(arguments["scenario_id"]))
    if name == "get_run_status":
        return service.status(str(arguments["run_id"]))
    if name == "get_run_metrics":
        return service.metrics(
            str(arguments["run_id"]),
            section=arguments.get("section"),
            page=page,
            page_size=page_size,
        )
    if name == "compare_runs":
        return service.compare(
            str(arguments["baseline_run_id"]),
            str(arguments["informed_run_id"]),
        )
    if name == "get_commitment_log":
        return service.commitment(
            str(arguments["run_id"]),
            unit_id=arguments.get("unit_id"),
            action=arguments.get("action"),
            source=arguments.get("source"),
            accepted=arguments.get("accepted"),
            page=page,
            page_size=page_size,
        )
    if name == "get_ticks":
        return service.ticks(
            str(arguments["run_id"]),
            start_seconds=arguments.get("start_seconds"),
            end_seconds=arguments.get("end_seconds"),
            fields=[str(value) for value in arguments["fields"]],
            stride=int(arguments.get("stride", 1)),
            page=page,
            page_size=min(int(arguments.get("page_size", DEFAULT_PAGE_SIZE)), MAX_TICK_ROWS),
        )
    if name == "start_run":
        return service.start(
            scenario_id=str(arguments["scenario_id"]),
            mode=str(arguments["mode"]),
            parameter_overrides=arguments.get("parameter_overrides"),
            seed=arguments.get("seed"),
            reuse_cache=bool(arguments.get("reuse_cache", True)),
            principal=principal,
        )
    raise NotFoundIdentifierError(
        "tool identifier was not found",
        identifier=name,
        kind="tool",
    )


@app.api_route("/", methods=["GET", "POST"])
async def mcp_endpoint(request: Request) -> Response:
    if request.method == "GET":
        return JSONResponse(
            {
                "transport": "streamable_http",
                "endpoint": "/mcp",
                "protocol_version": PROTOCOL_VERSION,
            }
        )
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32700, "message": "invalid JSON"}},
            status_code=400,
        )
    if not isinstance(body, dict):
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32600, "message": "invalid request"}},
            status_code=400,
        )
    request_id = body.get("id")
    method = body.get("method")
    if method == "notifications/initialized":
        return Response(status_code=202)
    if method == "initialize":
        session_id = request.headers.get("mcp-session-id") or uuid.uuid4().hex
        _sessions.add(session_id)
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "gridsignal-study-harness",
                        "version": "S3",
                    },
                },
            },
            headers={"Mcp-Session-Id": session_id},
        )
    if method == "tools/list":
        try:
            _authorize(request, needs_run=False)
            result = {"tools": _tool_definitions()}
            return JSONResponse(
                {"jsonrpc": "2.0", "id": request_id, "result": result}
            )
        except Exception as error:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result(_typed_error_payload(error), is_error=True),
                },
                status_code=200,
            )
    if method == "tools/call":
        params = body.get("params") or {}
        name = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        try:
            result = _call_tool(name, arguments, request)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result(result),
                }
            )
        except Exception as error:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result(_typed_error_payload(error), is_error=True),
                }
            )
    return JSONResponse(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": "method not found",
                "method": method,
            },
        },
        status_code=404,
    )