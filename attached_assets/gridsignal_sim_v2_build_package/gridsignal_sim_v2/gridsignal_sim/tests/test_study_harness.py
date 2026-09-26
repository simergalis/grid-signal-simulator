from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from study_harness.acceptance import AcceptanceCondition, compare_metrics
from study_harness.artifacts import ArtifactWriter
from study_harness.errors import (
    BuildParityMismatchError,
    FuelComponentReconciliationError,
    ProvenanceUnknownError,
    StartFuelReconciliationError,
)
import study_harness.executor as executor_module
from study_harness.executor import StudyRunExecutor
from study_harness.manifest import RunManifestCache, make_run_identity
from study_harness.metrics import collect_metrics
from runtime.turbine_commitment import ForecastDrivenTurbineController


def _row(
    *,
    total: float,
    start_fuel: float = 0.0,
    no_load_fuel: float = 0.0,
    start_count: int = 0,
    fuel_this_tick: float = 0.0,
) -> dict:
    return {
        "asset_id": "gt-01",
        "fuel_modelled": True,
        "load_fuel_mmbtu": total - start_fuel - no_load_fuel,
        "no_load_fuel_mmbtu": no_load_fuel,
        "hot_standby_fuel_mmbtu": 0.0,
        "start_fuel_mmbtu": start_fuel,
        "total_fuel_mmbtu": total,
        "start_count": start_count,
        "fuel_mmbtu_this_tick": fuel_this_tick,
    }


def _tick(
    time_s: float,
    row: dict,
    *,
    unserved: float = 0.0,
    curtailed: float = 0.0,
    output: float = 10.0,
    forecast: float | None = None,
) -> dict:
    result = {
        "sim_time_seconds": time_s,
        "p_compute_demand_mw": 10.0,
        "p_total_mw": 10.0,
        "p_generation_mw": 10.0 - unserved,
        "p_served_mw": 10.0 - unserved,
        "p_unserved_mw": unserved,
        "p_imbalance_mw": 0.0,
        "p_dispatch_curtailed_mw": curtailed,
        "bess_soc_fraction": 0.8,
        "turbine_fuel_telemetry": [row],
        "turbine_units": [
            {
                "asset_id": "gt-01",
                "state": "synchronised",
                "breaker_closed": True,
                "output_mw": output,
                "rated_mw": 25.0,
            }
        ],
    }
    if forecast is not None:
        result["forecast_mw"] = forecast
    return result


def _record(
    *,
    start_events: list[dict] | None = None,
    total: float = 10.0,
    start_fuel: float = 0.0,
) -> dict:
    return {
        "scenario_id": "test",
        "mode": "baseline",
        "engine_commit": "engine",
        "harness_commit": "harness",
        "turbine_fuel_mmbtu": total,
        "fuel_by_component_mmbtu": {
            "load_fuel_mmbtu": total - start_fuel,
            "no_load_fuel_mmbtu": 0.0,
            "hot_standby_fuel_mmbtu": 0.0,
            "start_fuel_mmbtu": start_fuel,
        },
        "starts": start_events or [],
    }


def test_metric_reconciliation_and_start_fuel_tier_arithmetic() -> None:
    ticks = [
        _tick(5.0, _row(total=4.0, start_fuel=8.0, start_count=1, fuel_this_tick=4.0)),
        _tick(10.0, _row(total=10.0, start_fuel=20.0, start_count=2, fuel_this_tick=6.0)),
    ]
    record = _record(
        total=10.0,
        start_fuel=20.0,
        start_events=[
            {"action": "start", "tier_fuel_mmbtu": 8.0},
            {"action": "release", "tier_fuel_mmbtu": 12.0},
        ],
    )
    metrics = collect_metrics(ticks, run_record=record)
    assert metrics["fuel_reconciled"] is True
    assert metrics["start_fuel_reconciliation"]["tier_sum_mmbtu"] == 20.0

    with pytest.raises(StartFuelReconciliationError):
        collect_metrics(
            ticks,
            run_record={
                **record,
                "starts": [{"action": "start", "tier_fuel_mmbtu": 8.0}],
            },
        )

    with pytest.raises(FuelComponentReconciliationError):
        collect_metrics(
            ticks,
            run_record={
                **record,
                "turbine_fuel_mmbtu": 11.0,
            },
        )


def test_curtailment_is_range_checked_and_attributed_separately() -> None:
    metrics = collect_metrics(
        [
            _tick(
                5.0,
                _row(total=0.2, no_load_fuel=0.1, fuel_this_tick=0.2),
                curtailed=2.0,
            )
        ],
        run_record=_record(total=0.2),
    )
    assert metrics["dispatch_curtailment_mwh"] > 0.0
    assert metrics["dispatch_curtailment_interval_exposure_fuel_mmbtu"] == 0.2
    assert metrics["dispatch_curtailment_attributable_fuel_mmbtu"] == pytest.approx(
        0.02
    )
    assert (
        metrics["dispatch_curtailment_interval_exposure_fuel_mmbtu"]
        != metrics["dispatch_curtailment_attributable_fuel_mmbtu"]
    )


def test_unserved_energy_is_supply_sensitive() -> None:
    baseline = collect_metrics(
        [
            _tick(5.0, _row(total=1.0), unserved=0.0),
            _tick(10.0, _row(total=2.0), unserved=2.0),
        ],
        run_record=_record(total=2.0),
    )
    informed = collect_metrics(
        [
            _tick(5.0, _row(total=1.0), unserved=0.0),
            _tick(10.0, _row(total=2.0), unserved=0.5),
        ],
        run_record=_record(total=2.0),
    )
    assert informed["unserved_mwh"] < baseline["unserved_mwh"]


def test_induced_forecast_miss_is_reported() -> None:
    metrics = collect_metrics(
        [_tick(5.0, _row(total=1.0), forecast=1.0)],
        run_record=_record(total=1.0),
    )
    assert metrics["forecast"]["miss_count"] == 1
    assert metrics["forecast"]["miss_peak_mw"] == 9.0


def test_commitment_distinct_key_keeps_same_action_at_different_times() -> None:
    metrics = collect_metrics(
        [_tick(5.0, _row(total=1.0))],
        run_record={
            **_record(total=1.0),
            "commitment_log": [
                {
                    "unit_id": "gt-01",
                    "action": "stop",
                    "source": "core_commitment",
                    "sim_time_s": 5.0,
                    "reason": "same",
                    "accepted": True,
                    "changed_state": True,
                },
                {
                    "unit_id": "gt-01",
                    "action": "stop",
                    "source": "core_commitment",
                    "sim_time_s": 10.0,
                    "reason": "same",
                    "accepted": True,
                    "changed_state": True,
                },
            ],
        },
    )
    assert metrics["commitment"]["distinct_event_count"] == 2
    assert metrics["commitment"]["suppressed_repeat_count"] == 0


def test_acceptance_has_fixed_enumeration_and_fails_worse_informed() -> None:
    baseline = {
        "engine_commit": "e",
        "harness_commit": "h",
        "constraints_valid": True,
        "fuel_reconciled": True,
        "energy_balance": {"closure_status": True},
        "unserved_mwh": 1.0,
        "peak_unserved_mw": 1.0,
        "compute_trace_sha256": "same",
    }
    informed = {
        **baseline,
        "mode": "informed",
        "unserved_mwh": 2.0,
        "peak_unserved_mw": 2.0,
    }
    comparison = compare_metrics(baseline, informed)
    assert comparison["verdict"] == "FAIL"
    assert set(comparison["conditions"]) == {
        condition.value for condition in AcceptanceCondition
    }
    assert comparison["conditions"]["informed_unserved_energy_no_worse"] is False


def test_acceptance_refuses_mismatched_build_parity() -> None:
    baseline = {
        "engine_commit": "e1",
        "harness_commit": "h",
    }
    informed = {"engine_commit": "e2", "harness_commit": "h"}
    with pytest.raises(BuildParityMismatchError) as raised:
        compare_metrics(baseline, informed)
    assert raised.value.baseline_engine_commit == "e1"
    assert raised.value.informed_engine_commit == "e2"


def test_identity_and_cache_make_identical_runs_non_executing(tmp_path: Path) -> None:
    identity = make_run_identity(
        scenario_id="s",
        mode="baseline",
        parameter_set={"alpha": 1},
        seed=7,
        duration_seconds=10,
        tick_seconds=5,
        engine_commit="e",
        harness_commit="h",
    )
    cache = RunManifestCache(tmp_path)
    calls = []

    def execute() -> dict:
        calls.append("executed")
        return {"identity_digest": identity.digest, "value": 42}

    first, first_hit = cache.get_or_execute(identity, execute)
    second, second_hit = cache.get_or_execute(identity, execute)
    assert first["value"] == second["value"] == 42
    assert first_hit is False
    assert second_hit is True
    assert calls == ["executed"]
    assert json.loads((tmp_path / "manifest.json").read_text())["runs"]


def test_artifact_writer_verifies_existing_bounded_outputs(tmp_path: Path) -> None:
    identity = make_run_identity(
        scenario_id="s",
        mode="baseline",
        parameter_set={},
        seed=None,
        duration_seconds=5,
        tick_seconds=5,
        engine_commit="e",
        harness_commit="h",
    )
    result = ArtifactWriter(tmp_path, json_cap_bytes=10_000).write(
        identity=identity,
        record={"identity_digest": identity.digest},
        summary={"status": "PASS"},
        tick_rows=[{"tick_index": 1}],
    )
    assert all(Path(path).is_file() for path in result.paths.values())
    assert all(size > 0 for size in result.sizes_bytes.values())


class _UnboundedForecastHistory(list):
    """Test-only history that keeps an unbounded logical length.

    The controller reads only ``forecast_history[-1]``. Keep the two live
    snapshots physically, but retain the logical append count so this test
    does not spend quadratic time retaining millions of profile tuples.
    """

    def __init__(self, values=()):
        super().__init__(values)
        self.logical_length = list.__len__(self)

    def append(self, value):
        super().append(value)
        self.logical_length += 1

    def __len__(self):
        return self.logical_length

    def __delitem__(self, key):
        if isinstance(key, slice):
            list.__delitem__(self, key)
            return
        super().__delitem__(key)
        self.logical_length -= 1


def test_h1_informed_is_deterministic_with_bounded_forecast_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two-snapshot diagnostic bound must not change H-1 physics."""
    scenario_id = "scenario-h1-k8s-ray-24h"
    bounded_executor = StudyRunExecutor(output_dir=tmp_path / "bounded")
    spec = bounded_executor._expanded_spec(scenario_id, None, None)
    replay_events, demand_replay = bounded_executor._probe(
        spec,
        run_id="h1-forecast-bound-determinism-probe",
    )
    bounded = bounded_executor._run_mode(
        scenario_id=scenario_id,
        mode="informed",
        spec=spec,
        replay_events=replay_events,
        demand_replay=demand_replay,
        seed=None,
    )

    original_init = ForecastDrivenTurbineController.__init__
    unbounded_controllers = []

    def preserve_forecast_history(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.forecast_history = _UnboundedForecastHistory(self.forecast_history)
        unbounded_controllers.append(self)

    monkeypatch.setattr(
        ForecastDrivenTurbineController,
        "__init__",
        preserve_forecast_history,
    )
    unbounded = StudyRunExecutor(
        output_dir=tmp_path / "unbounded",
    )._run_mode(
        scenario_id=scenario_id,
        mode="informed",
        spec=spec,
        replay_events=replay_events,
        demand_replay=demand_replay,
        seed=None,
    )

    metric_keys = (
        "fuel_by_component_mmbtu",
        "turbine_fuel_mmbtu",
        "dispatch_curtailment_mwh",
        "dispatch_curtailment_interval_exposure_fuel_mmbtu",
        "dispatch_curtailment_attributable_fuel_mmbtu",
        "unserved_mwh",
        "peak_unserved_mw",
        "served_mwh",
        "energy_balance",
        "bess_soc_min",
        "bess_soc_max",
        "bess_soc_final",
        "commitment",
        "forecast",
        "compute_trace_sha256",
        "compute_trace_count",
        "daily_breakdown",
    )
    for key in metric_keys:
        assert bounded[key] == unbounded[key], (
            f"bounded forecast history changed metric {key}: "
            f"{bounded[key]!r} != {unbounded[key]!r}"
        )
    assert unbounded_controllers
    assert len(unbounded_controllers[0].forecast_history) > 2


def test_tc_ssh08_01_commit_resolution_order_and_separate_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """TC-SSH08-01: engine env override, then build info, then Git, then unknown."""
    build_info_path = tmp_path / "build_info.json"
    build_info_path.write_text(
        json.dumps(
            {
                "engine_commit": "engine-from-build",
                "harness_commit": "harness-from-build",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(executor_module, "BUILD_INFO_PATH", build_info_path)
    monkeypatch.setenv("GRIDSTUDY_ENGINE_COMMIT", "engine-from-env")

    def unexpected_git_call(*args, **kwargs):
        raise AssertionError("a higher-priority commit source was available")

    monkeypatch.setattr(executor_module.subprocess, "check_output", unexpected_git_call)
    assert executor_module._git_commit() == "engine-from-env"
    assert executor_module._harness_commit() == "harness-from-build"

    monkeypatch.delenv("GRIDSTUDY_ENGINE_COMMIT")
    assert executor_module._git_commit() == "engine-from-build"

    build_info_path.unlink()

    def clean_git_output(command, **kwargs):
        if command[1:] == ["rev-parse", "HEAD"]:
            return "git-commit\n"
        if command[1:] == ["status", "--porcelain", "--untracked-files=all"]:
            return ""
        raise AssertionError(command)

    monkeypatch.setattr(executor_module.subprocess, "check_output", clean_git_output)
    assert executor_module._git_commit() == "git-commit"
    assert executor_module._harness_commit() == "git-commit"

    def unavailable_git(command, **kwargs):
        raise subprocess.CalledProcessError(128, command)

    monkeypatch.setattr(executor_module.subprocess, "check_output", unavailable_git)
    assert executor_module._git_commit() == "unknown"
    assert executor_module._harness_commit() == "unknown"


def test_tc_ssh08_02_build_info_capture_marks_dirty_worktree(
    tmp_path: Path,
) -> None:
    """TC-SSH08-02: the production build writer records HEAD and the dirty suffix."""
    import runpy

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(
        ["git", "init", str(repo_root)],
        check=True,
        capture_output=True,
        text=True,
    )

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    git("config", "user.name", "GridSignal Test")
    git("config", "user.email", "gridsignal-test@example.invalid")
    source_file = repo_root / "tracked.txt"
    source_file.write_text("initial\n", encoding="utf-8")
    git("add", "tracked.txt")
    git("commit", "-m", "initial")
    head = git("rev-parse", "HEAD")

    writer_path = Path(__file__).resolve().parents[5] / "scripts" / (
        "write_gridstudy_build_info.py"
    )
    write_build_info = runpy.run_path(str(writer_path))["write_build_info"]
    output_path = tmp_path / "backend" / "build_info.json"

    clean_info, clean_dirty = write_build_info(repo_root, output_path)
    assert clean_dirty is False
    assert clean_info == {
        "engine_commit": head,
        "harness_commit": head,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == clean_info

    source_file.write_text("modified\n", encoding="utf-8")
    dirty_info, dirty = write_build_info(repo_root, output_path)
    assert dirty is True
    assert dirty_info == {
        "engine_commit": f"{head}-dirty",
        "harness_commit": f"{head}-dirty",
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == dirty_info


@pytest.mark.parametrize(
    ("side", "field", "invalid_value", "remove"),
    [
        pytest.param(
            side,
            field,
            value,
            remove,
            id=f"{side}-{field}-{label}",
        )
        for side in ("baseline", "informed")
        for field in ("engine_commit", "harness_commit")
        for value, remove, label in (
            ("unknown", False, "unknown"),
            ("", False, "empty"),
            (None, False, "null"),
            (None, True, "missing"),
        )
    ],
)
def test_tc_ssh08_03_acceptance_rejects_incomplete_provenance(
    side: str,
    field: str,
    invalid_value: str | None,
    remove: bool,
) -> None:
    """TC-SSH08-03: every absent/empty/unknown commit fails closed."""
    baseline = {
        "run_id": "baseline-ssh08-03",
        "engine_commit": "engine-sha",
        "harness_commit": "harness-sha",
    }
    informed = {
        "run_id": "informed-ssh08-03",
        "engine_commit": "engine-sha",
        "harness_commit": "harness-sha",
    }
    target = baseline if side == "baseline" else informed
    if remove:
        target.pop(field)
    else:
        target[field] = invalid_value

    with pytest.raises(ProvenanceUnknownError) as raised:
        compare_metrics(baseline, informed)

    error = raised.value
    assert error.code == "PROVENANCE_UNKNOWN"
    assert error.baseline_run_id == "baseline-ssh08-03"
    assert error.informed_run_id == "informed-ssh08-03"
    assert error.baseline_engine_commit == str(
        baseline.get("engine_commit") or ""
    ).strip()
    assert error.informed_engine_commit == str(
        informed.get("engine_commit") or ""
    ).strip()
    assert error.baseline_harness_commit == str(
        baseline.get("harness_commit") or ""
    ).strip()
    assert error.informed_harness_commit == str(
        informed.get("harness_commit") or ""
    ).strip()


def test_tc_ssh08_04_executor_run_pair_refuses_unknown_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """TC-SSH08-04: executor run_pair uses the same fail-closed gate."""
    executor = StudyRunExecutor(
        output_dir=tmp_path,
        engine_commit="unknown",
        harness_commit="harness-sha",
    )
    monkeypatch.setattr(executor, "_expanded_spec", lambda *args, **kwargs: {})
    monkeypatch.setattr(executor, "_probe", lambda *args, **kwargs: ([], []))

    def fake_run_mode(*, scenario_id: str, mode: str, **kwargs) -> dict:
        return {
            "run_id": f"{scenario_id}-{mode}",
            "engine_commit": "unknown",
            "harness_commit": "harness-sha",
        }

    monkeypatch.setattr(executor, "_run_mode", fake_run_mode)
    with pytest.raises(ProvenanceUnknownError) as raised:
        executor.run_pair(scenario_id="scenario-uneven-multisched-01")

    assert raised.value.code == "PROVENANCE_UNKNOWN"
    assert raised.value.baseline_run_id.endswith("-baseline")
    assert raised.value.informed_run_id.endswith("-informed")
    assert raised.value.baseline_engine_commit == "unknown"
    assert raised.value.informed_engine_commit == "unknown"
    assert raised.value.baseline_harness_commit == "harness-sha"
    assert raised.value.informed_harness_commit == "harness-sha"