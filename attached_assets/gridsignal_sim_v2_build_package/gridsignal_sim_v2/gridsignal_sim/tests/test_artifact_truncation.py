from __future__ import annotations

import copy
import gzip
import json
import time
from pathlib import Path
from typing import Any

import pytest

from study_harness.acceptance import compare_metrics
from study_harness.artifacts import (
    DEFAULT_JSON_CAP_BYTES,
    TRUNCATABLE_DETAIL_KEYS,
    ArtifactWriter,
)
from study_harness.errors import ArtifactPathError, ArtifactSizeError
from study_harness.executor import (
    StudyRunExecutor,
    validate_committed_artifact,
)
from study_harness.manifest import RunManifestCache, make_run_identity


_DETAIL_KEYS = TRUNCATABLE_DETAIL_KEYS["record"]
_BASE_DEMO_SCENARIO_ID = "scenario-uneven-multisched-01"


def _identity(seed: int = 17):
    return make_run_identity(
        scenario_id="synthetic-artifact-truncation",
        mode="baseline",
        parameter_set={},
        seed=seed,
        duration_seconds=5,
        tick_seconds=5,
        engine_commit="test-engine",
        harness_commit="test-harness",
    )


def _encoded_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _synthetic_detail_records(
    key: str,
    *,
    count: int = 50,
    detail_chars: int = 100,
) -> list[dict[str, Any]]:
    return [
        {"index": index, "detail": "x" * detail_chars, "source": key}
        for index in range(count)
    ]


def _oversized_record() -> dict[str, Any]:
    record: dict[str, Any] = {
        "scenario_id": "synthetic-artifact-truncation",
        "mode": "baseline",
        "interval_seconds": 5.0,
        "status": "PASS",
        "scalar_metric": 12.5,
        "energy_balance": {"closure_status": True, "residual_mwh": 0.0},
        "fuel_by_component_mmbtu": {"load_fuel_mmbtu": 5.0},
        "metrics_blob": {"opaque": "m" * 96_000},
    }
    for key in _DETAIL_KEYS:
        record[key] = _synthetic_detail_records(key)
    return record


def _large_summary() -> dict[str, Any]:
    return {
        "status": "PASS",
        "energy_balance": {"closure_status": True, "residual_mwh": 0.0},
        "unserved_intervals": [
            {"index": index, "detail": "u" * 220} for index in range(400)
        ],
        "hard_violations": [
            {"index": index, "detail": "h" * 180} for index in range(350)
        ],
    }


def _writer_executor(
    output_dir: Path,
    *,
    cap_bytes: int | None = None,
) -> StudyRunExecutor:
    executor = StudyRunExecutor(output_dir=output_dir)
    if cap_bytes is not None:
        executor.writer = ArtifactWriter(
            output_dir / "artifacts",
            json_cap_bytes=cap_bytes,
        )
    return executor


def test_tc165_under_cap_keeps_legacy_record_encoding_and_writes_no_sidecar(
    tmp_path: Path,
) -> None:
    identity = _identity()
    record = {
        "mode": "baseline",
        "starts": [{"action": "start", "unit_id": "gt-01"}],
        "metric": 1.25,
    }
    summary = {"status": "PASS", "fuel_mmbtu": 2.5}

    result = ArtifactWriter(tmp_path).write(
        identity=identity,
        record=record,
        summary=summary,
        tick_rows=[{"tick_index": 1}],
    )

    stored_record = json.loads(Path(result.paths["record"]).read_text())
    stored_summary = json.loads(Path(result.paths["summary"]).read_text())
    assert Path(result.paths["record"]).read_bytes() == _encoded_json(record)
    assert Path(result.paths["summary"]).read_bytes() == _encoded_json(summary)
    assert not ({"artifact_truncation", "detail_sidecar_file"} & stored_record.keys())
    assert not ({"artifact_truncation", "detail_sidecar_file"} & stored_summary.keys())
    assert all(f"{key}_count" not in stored_record for key in _DETAIL_KEYS)
    assert all(f"{key}_count" not in stored_summary for key in TRUNCATABLE_DETAIL_KEYS["summary"])
    assert "detail" not in result.paths
    assert not list(tmp_path.glob("detail-*.json.gz"))


def test_tc166_synthetic_oversize_truncates_declared_detail_lists_exactly(
    tmp_path: Path,
) -> None:
    identity = _identity()
    record = _oversized_record()
    original = copy.deepcopy(record)
    encoded_input_size = len(_encoded_json(record))
    assert 140_000 <= encoded_input_size <= 160_000

    result = ArtifactWriter(tmp_path).write(
        identity=identity,
        record=record,
        summary={"status": "PASS"},
        tick_rows=[{"tick_index": 1}],
    )

    record_path = Path(result.paths["record"])
    stored = json.loads(record_path.read_text())
    assert record_path.stat().st_size < DEFAULT_JSON_CAP_BYTES
    assert set(stored["artifact_truncation"]) == set(_DETAIL_KEYS)
    for key, value in original.items():
        if key not in _DETAIL_KEYS:
            assert stored[key] == value

    for key in _DETAIL_KEYS:
        original_count = len(original[key])
        values = stored[key]
        markers = [
            row
            for row in values
            if isinstance(row, dict) and row.get("truncated") is True
        ]
        assert len(markers) == 1
        kept_count = len(values) - 1
        assert markers[0]["omitted_record_count"] == original_count - kept_count
        assert stored[f"{key}_count"] == original_count
        assert stored["artifact_truncation"][key] == {
            "original_count": original_count,
            "kept_count": kept_count,
        }
        assert kept_count == len(values) - 1


def test_tc167_write_does_not_mutate_caller_record_or_summary(
    tmp_path: Path,
) -> None:
    identity = _identity()
    record = _oversized_record()
    summary = _large_summary()
    record_before = copy.deepcopy(record)
    summary_before = copy.deepcopy(summary)

    ArtifactWriter(tmp_path).write(
        identity=identity,
        record=record,
        summary=summary,
        tick_rows=[{"tick_index": 1}],
    )

    assert record == record_before
    assert summary == summary_before


def test_tc168_repeated_oversize_writes_are_byte_identical(
    tmp_path: Path,
) -> None:
    identity = _identity()
    record = _oversized_record()
    summary = _large_summary()
    tick_rows = [{"tick_index": index, "value": index / 10} for index in range(4)]

    first = ArtifactWriter(tmp_path / "first").write(
        identity=identity,
        record=record,
        summary=summary,
        tick_rows=tick_rows,
    )
    second = ArtifactWriter(tmp_path / "second").write(
        identity=identity,
        record=record,
        summary=summary,
        tick_rows=tick_rows,
    )

    assert set(first.paths) == set(second.paths)
    for label in first.paths:
        assert Path(first.paths[label]).read_bytes() == Path(second.paths[label]).read_bytes()


@pytest.mark.parametrize(
    "overflowing_document",
    ["record", "summary"],
    ids=["record-metrics-over-cap", "summary-metrics-over-cap"],
)
def test_tc169_non_detail_metrics_over_cap_leave_no_artifacts(
    tmp_path: Path,
    overflowing_document: str,
) -> None:
    identity = _identity()
    oversized_metrics = {
        "opaque_metric": {"payload": "x" * (DEFAULT_JSON_CAP_BYTES + 512)}
    }
    record = (
        {"scenario_id": "synthetic", **oversized_metrics}
        if overflowing_document == "record"
        else {"scenario_id": "synthetic", "status": "PASS"}
    )
    summary = (
        {"status": "PASS", **oversized_metrics}
        if overflowing_document == "summary"
        else {"status": "PASS"}
    )
    writer = ArtifactWriter(tmp_path)

    with pytest.raises(ArtifactSizeError) as raised:
        writer.write(
            identity=identity,
            record=record,
            summary=summary,
            tick_rows=[{"tick_index": 1}],
        )

    message = str(raised.value)
    assert "top-level key sizes:" in message
    assert "opaque_metric=" in message
    for name in (
        f"run-{identity.digest}.json",
        f"summary-{identity.digest}.json",
        f"detail-{identity.digest}.json.gz",
        f"ticks-{identity.digest}.jsonl.gz",
    ):
        assert not (tmp_path / name).exists()


def test_tc170_detail_sidecar_restores_original_record_and_summary_lists(
    tmp_path: Path,
) -> None:
    identity = _identity()
    record = _oversized_record()
    summary = _large_summary()

    result = ArtifactWriter(tmp_path).write(
        identity=identity,
        record=record,
        summary=summary,
        tick_rows=[{"tick_index": 1}],
    )

    assert "detail" in result.paths
    with gzip.open(result.paths["detail"], "rt", encoding="utf-8") as handle:
        details = json.load(handle)
    assert set(details) == {"record", "summary"}
    for key in _DETAIL_KEYS:
        assert details["record"][key] == record[key]
    for key in TRUNCATABLE_DETAIL_KEYS["summary"]:
        assert details["summary"][key] == summary[key]


def _record_with_encoded_size(
    target_bytes: int,
    fields: dict[str, Any],
) -> dict[str, Any]:
    record = dict(fields)
    record["padding"] = ""
    base_size = len(_encoded_json(record))
    assert base_size <= target_bytes
    record["padding"] = "x" * (target_bytes - base_size)
    assert len(_encoded_json(record)) == target_bytes
    return record


def test_tc171_cap_boundary_uses_strictly_less_than_cap(
    tmp_path: Path,
) -> None:
    identity = _identity()
    cap = 4096
    below_cap = _record_with_encoded_size(
        cap - 1,
        {"scenario_id": "boundary", "scalar_metric": 1.0},
    )
    below_result = ArtifactWriter(tmp_path / "below", json_cap_bytes=cap).write(
        identity=identity,
        record=below_cap,
        summary={"status": "PASS"},
        tick_rows=[],
    )
    below_stored = json.loads(Path(below_result.paths["record"]).read_text())
    assert Path(below_result.paths["record"]).stat().st_size == cap - 1
    assert "artifact_truncation" not in below_stored
    assert "detail" not in below_result.paths

    exact_cap = _record_with_encoded_size(
        cap,
        {
            "scenario_id": "boundary",
            "status": "PASS",
            "starts": [
                {"index": index, "detail": "s" * 80} for index in range(12)
            ],
        },
    )
    exact_result = ArtifactWriter(
        tmp_path / "exact",
        json_cap_bytes=cap,
    ).write(
        identity=identity,
        record=exact_cap,
        summary={"status": "PASS"},
        tick_rows=[],
    )
    exact_stored = json.loads(Path(exact_result.paths["record"]).read_text())
    assert len(_encoded_json(exact_cap)) == cap
    assert Path(exact_result.paths["record"]).stat().st_size < cap
    assert "starts" in exact_stored["artifact_truncation"]
    assert "detail" in exact_result.paths


def test_tc172_missing_detail_sidecar_raises_artifact_path_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = _identity()
    writer = ArtifactWriter(tmp_path)
    real_write_gzip_chunks = writer._write_gzip_chunks

    def skip_detail(path: Path, chunks: Any) -> None:
        if Path(path).name.startswith("detail-"):
            return
        real_write_gzip_chunks(path, chunks)

    monkeypatch.setattr(writer, "_write_gzip_chunks", skip_detail)

    with pytest.raises(ArtifactPathError, match="detail-"):
        writer.write(
            identity=identity,
            record=_oversized_record(),
            summary={"status": "PASS"},
            tick_rows=[{"tick_index": 1}],
        )


def test_tc173_executor_run_validates_from_truncated_record_and_sidecar(
    tmp_path: Path,
) -> None:
    default_run = _writer_executor(tmp_path / "default-cap").run_mode(
        scenario_id=_BASE_DEMO_SCENARIO_ID,
        mode="baseline",
        seed=42,
        reuse_cache=False,
    )
    default_paths = default_run["artifacts"]["paths"]
    default_record_path = Path(default_paths["record"])
    untruncated_record_size = default_record_path.stat().st_size
    small_cap_bytes = untruncated_record_size - 1

    # PROPOSED_HERE: derive the cap just below this run's default artifact size,
    # then preflight the writer so this test forces truncation without choosing
    # a cap too small for the base-demo record's non-detail fields and list floor.
    assert small_cap_bytes < untruncated_record_size
    untruncated_record = json.loads(default_record_path.read_text())
    assert "artifact_truncation" not in untruncated_record
    default_summary = json.loads(Path(default_paths["summary"]).read_text())
    identity = make_run_identity(**untruncated_record["identity"])
    try:
        preflight = ArtifactWriter(
            tmp_path / "small-cap-preflight",
            json_cap_bytes=small_cap_bytes,
        ).write(
            identity=identity,
            record=untruncated_record,
            summary=default_summary,
            tick_rows=[],
        )
    except ArtifactSizeError as error:
        pytest.fail(
            "TC-173 minimum-size preflight failed after detail-list truncation: "
            f"untruncated_record_bytes={untruncated_record_size}, "
            f"derived_small_cap_bytes={small_cap_bytes}; {error}",
            pytrace=False,
        )
    minimum_record_path = Path(preflight.paths["record"])
    minimum_record_size = minimum_record_path.stat().st_size
    minimum_record = json.loads(minimum_record_path.read_text())
    assert "detail" in preflight.paths
    assert set(minimum_record.get("artifact_truncation", {})) & set(_DETAIL_KEYS)
    assert minimum_record_size < small_cap_bytes, (
        "TC-173 minimum-size preflight did not fit: "
        f"untruncated_record_bytes={untruncated_record_size}, "
        f"derived_small_cap_bytes={small_cap_bytes}, "
        f"minimum_detail_truncated_record_bytes={minimum_record_size}"
    )
    print(
        "TC-173 sizes: "
        f"untruncated_record_bytes={untruncated_record_size}, "
        f"derived_small_cap_bytes={small_cap_bytes}, "
        f"minimum_detail_truncated_record_bytes={minimum_record_size}"
    )

    record = _writer_executor(
        tmp_path / "small-cap",
        cap_bytes=small_cap_bytes,
    ).run_mode(
        scenario_id=_BASE_DEMO_SCENARIO_ID,
        mode="baseline",
        seed=42,
        reuse_cache=False,
    )

    assert record["status"] == "PASS"
    paths = record["artifacts"]["paths"]
    assert "detail" in paths
    with_detail = validate_committed_artifact(
        record_path=Path(paths["record"]),
        tick_path=Path(paths["ticks"]),
        detail_path=Path(paths["detail"]),
    )
    assert with_detail["status"] == "PASS"
    assert with_detail["metrics"] is not None
    for key, value in with_detail["metrics"].items():
        assert key in record
        assert record[key] == value

    without_detail = validate_committed_artifact(
        record_path=Path(paths["record"]),
        tick_path=Path(paths["ticks"]),
    )
    print(f"TC-173 validation without detail_path: {without_detail['status']}")
    if without_detail["status"] == "FAIL":
        print(
            "TC-173 validation without detail_path guards: "
            + json.dumps(without_detail["guards_fired"], sort_keys=True)
        )


def test_tc174_small_cap_preserves_base_demo_pair_acceptance(
    tmp_path: Path,
) -> None:
    default_pair = _writer_executor(tmp_path / "default-cap").run_pair(
        scenario_id=_BASE_DEMO_SCENARIO_ID,
        seed=42,
    )
    for mode, run in default_pair["runs"].items():
        default_record = json.loads(
            Path(run["artifacts"]["paths"]["record"]).read_text()
        )
        default_truncation = default_record.get("artifact_truncation")
        print(
            f"TC-174 default-cap {mode} artifact_truncation: "
            f"{json.dumps(default_truncation, sort_keys=True) if default_truncation else 'none'}"
        )
    default_record_sizes = {
        mode: Path(run["artifacts"]["paths"]["record"]).stat().st_size
        for mode, run in default_pair["runs"].items()
    }
    small_cap_bytes = min(default_record_sizes.values()) - 1
    assert all(small_cap_bytes < size for size in default_record_sizes.values())
    print(
        "TC-174 sizes: "
        f"baseline_default_record_bytes={default_record_sizes['baseline']}, "
        f"informed_default_record_bytes={default_record_sizes['informed']}, "
        f"derived_small_cap_bytes={small_cap_bytes}"
    )

    small_pair = _writer_executor(
        tmp_path / "small-cap",
        cap_bytes=small_cap_bytes,
    ).run_pair(
        scenario_id=_BASE_DEMO_SCENARIO_ID,
        seed=42,
    )

    for mode, run in small_pair["runs"].items():
        small_record = json.loads(
            Path(run["artifacts"]["paths"]["record"]).read_text()
        )
        small_truncation = small_record.get("artifact_truncation")
        print(
            f"TC-174 small-cap {mode} artifact_truncation: "
            f"{json.dumps(small_truncation, sort_keys=True) if small_truncation else 'none'}"
        )
        assert "detail" in run["artifacts"]["paths"]
    default_comparison = compare_metrics(
        default_pair["runs"]["baseline"],
        default_pair["runs"]["informed"],
    )
    small_comparison = compare_metrics(
        small_pair["runs"]["baseline"],
        small_pair["runs"]["informed"],
    )
    assert default_comparison["verdict"] == small_comparison["verdict"]
    assert default_comparison["condition_order"] == small_comparison["condition_order"]
    for condition in default_comparison["condition_order"]:
        assert (
            default_comparison["conditions"][condition]
            == small_comparison["conditions"][condition]
        )
    assert (
        default_comparison["informed_vs_baseline"]
        == small_comparison["informed_vs_baseline"]
    )


def test_tc175_large_artifact_and_manifest_size_measurement(
    tmp_path: Path,
) -> None:
    refusal_records = []
    for index in range(100_000):
        sim_time_s = float(index * 5)
        refusal_records.append(
            {
                "sim_time_s": sim_time_s,
                "forecast_time_s": sim_time_s + 60.0,
                "demand_mw": 75.0,
                "post_stop_floor_mw": 62.5,
                "remaining_turbine_capacity_mw": 50.0,
                "reserve_deficit_mw": 12.5,
                "restart_window_end_s": sim_time_s + 300.0,
                "stop_lookahead_end_s": sim_time_s + 600.0,
                "bess_included_in_floor": False,
            }
        )
    commitment_records = [
        {
            "sim_time_s": float(index * 60),
            "unit_id": f"gt-{index % 4 + 1:02d}",
            "action": "stop" if index % 2 else "start",
            "source": "controller",
            "accepted": False,
            "changed_state": False,
        }
        for index in range(400)
    ]
    record = {
        "scenario_id": "synthetic-artifact-size-measurement",
        "mode": "informed",
        "stop_floor_refusal_count": len(refusal_records),
        "commitment_log_record_count": len(commitment_records),
        "stop_floor_refusals": refusal_records,
        "commitment_log": commitment_records,
    }
    identity = make_run_identity(
        scenario_id="synthetic-artifact-size-measurement",
        mode="informed",
        parameter_set={},
        seed=175,
        duration_seconds=5,
        tick_seconds=5,
        engine_commit="test-engine",
        harness_commit="test-harness",
    )

    writer = ArtifactWriter(tmp_path / "writer")
    started = time.perf_counter()
    result = writer.write(
        identity=identity,
        record=record,
        summary={"status": "PASS"},
        tick_rows=[],
    )
    writer_seconds = time.perf_counter() - started

    record_path = Path(result.paths["record"])
    detail_path = Path(result.paths["detail"])
    cache = RunManifestCache(tmp_path / "cache")
    cache.put(identity, record)
    cache_path = cache.records_dir / f"{identity.digest}.json"
    in_memory_record_bytes = len(_encoded_json(record))

    assert record_path.stat().st_size < DEFAULT_JSON_CAP_BYTES
    print(
        "TC-175 measurement: "
        f"writer_seconds={writer_seconds:.6f} "
        f"record_bytes={record_path.stat().st_size} "
        f"detail_bytes={detail_path.stat().st_size} "
        f"cache_bytes={cache_path.stat().st_size} "
        f"in_memory_record_json_bytes={in_memory_record_bytes}"
    )
