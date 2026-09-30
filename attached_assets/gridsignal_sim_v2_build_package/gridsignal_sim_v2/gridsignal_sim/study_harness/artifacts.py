"""Bounded study-harness artifact output with hard path verification."""

from __future__ import annotations

import copy
import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import ArtifactPathError, ArtifactSizeError


DEFAULT_JSON_CAP_BYTES = 100 * 1024
TRUNCATABLE_DETAIL_KEYS = {
    "record": (
        "starts",
        "measured_start_events",
        "commitment_log",
        "stop_floor_refusals",
        "unserved_intervals",
        "hard_violations",
    ),
    "summary": ("unserved_intervals", "hard_violations"),
}
DETAIL_LIST_FLOOR = 3  # PROPOSED_HERE: one head, marker, and one tail record is the smallest useful compact list.
DETAIL_LIMIT_REDUCTION_DIVISOR = 2  # PROPOSED_HERE: deterministic halving reaches the floor quickly while retaining the largest details first.
DETERMINISTIC_GZIP_MTIME = 0  # PROPOSED_HERE: fixed gzip timestamps make repeated writes byte-identical.
DETAIL_TRUNCATION_REASON = (
    "artifact detail list compacted; complete values are in the detail sidecar"
)


def _bounded_records(
    records: list[Any],
    *,
    limit: int,
    reason: str,
) -> list[Any]:
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


@dataclass(frozen=True)
class ArtifactWriteResult:
    paths: dict[str, str]
    sizes_bytes: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "paths": dict(self.paths),
            "sizes_bytes": dict(self.sizes_bytes),
        }


class ArtifactWriter:
    def __init__(
        self,
        root: Path,
        *,
        json_cap_bytes: int = DEFAULT_JSON_CAP_BYTES,
    ) -> None:
        self.root = Path(root)
        self.json_cap_bytes = int(json_cap_bytes)

    @staticmethod
    def _encoded_value_size(value: Any) -> int:
        return len(
            json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
        )

    @classmethod
    def _top_level_key_sizes(cls, payload: dict[str, Any]) -> str:
        sizes = [
            (
                len(
                    json.dumps(
                        {key: value}, indent=2, sort_keys=True
                    ).encode("utf-8")
                ),
                str(key),
            )
            for key, value in payload.items()
        ]
        sizes.sort(key=lambda item: (-item[0], item[1]))
        return ", ".join(f"{key}={size}B" for size, key in sizes)

    def _encode(self, payload: dict[str, Any], label: str) -> str:
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        size = len(encoded.encode("utf-8"))
        if size >= self.json_cap_bytes:
            raise ArtifactSizeError(
                f"{label} is {size} bytes; cap is {self.json_cap_bytes}; "
                "top-level key sizes: "
                f"{self._top_level_key_sizes(payload)}"
            )
        return encoded

    def _fit_payload(
        self,
        payload: dict[str, Any],
        label: str,
        *,
        detail_keys: tuple[str, ...],
        detail_sidecar_name: str,
    ) -> tuple[str, dict[str, dict[str, int]]]:
        working = copy.deepcopy(payload)
        original_lists = {
            key: copy.deepcopy(working[key])
            for key in detail_keys
            if isinstance(working.get(key), list)
        }
        limits = {key: len(records) for key, records in original_lists.items()}
        key_order = {key: index for index, key in enumerate(detail_keys)}
        truncations: dict[str, dict[str, int]] = {}

        while True:
            try:
                return self._encode(working, label), truncations
            except ArtifactSizeError as size_error:
                candidates = [
                    key
                    for key in detail_keys
                    if key in original_lists and limits[key] > DETAIL_LIST_FLOOR
                ]
                if not candidates:
                    raise size_error

            key = max(
                candidates,
                key=lambda item: (
                    self._encoded_value_size(working[item]),
                    -key_order[item],
                ),
            )
            limits[key] = max(
                DETAIL_LIST_FLOOR,
                limits[key] // DETAIL_LIMIT_REDUCTION_DIVISOR,
            )
            compacted = _bounded_records(
                original_lists[key],
                limit=limits[key],
                reason=DETAIL_TRUNCATION_REASON,
            )
            original_count = len(original_lists[key])
            kept_count = len(compacted) - 1
            working[key] = compacted
            working[f"{key}_count"] = original_count
            truncations[key] = {
                "original_count": original_count,
                "kept_count": kept_count,
            }
            working["artifact_truncation"] = copy.deepcopy(truncations)
            working["detail_sidecar_file"] = detail_sidecar_name

    @staticmethod
    def _write_gzip_chunks(path: Path, chunks: Iterable[bytes]) -> None:
        with path.open("wb") as raw_handle:
            with gzip.GzipFile(
                fileobj=raw_handle,
                mode="wb",
                filename="",
                mtime=DETERMINISTIC_GZIP_MTIME,
            ) as compressed:
                for chunk in chunks:
                    compressed.write(chunk)

    def write(
        self,
        *,
        identity: Any,
        record: dict[str, Any],
        summary: dict[str, Any],
        tick_rows: Iterable[dict[str, Any]],
    ) -> ArtifactWriteResult:
        digest = str(identity.digest)
        record_path = self.root / f"run-{digest}.json"
        summary_path = self.root / f"summary-{digest}.json"
        ticks_path = self.root / f"ticks-{digest}.jsonl.gz"
        detail_path = self.root / f"detail-{digest}.json.gz"

        encoded_record, record_truncations = self._fit_payload(
            record,
            "run record",
            detail_keys=TRUNCATABLE_DETAIL_KEYS["record"],
            detail_sidecar_name=detail_path.name,
        )
        encoded_summary, summary_truncations = self._fit_payload(
            summary,
            "run summary",
            detail_keys=TRUNCATABLE_DETAIL_KEYS["summary"],
            detail_sidecar_name=detail_path.name,
        )

        has_truncations = bool(record_truncations or summary_truncations)
        detail_bytes: bytes | None = None
        if has_truncations:
            detail_values = {
                "record": {
                    key: copy.deepcopy(record[key])
                    for key in TRUNCATABLE_DETAIL_KEYS["record"]
                    if isinstance(record.get(key), list)
                },
                "summary": {
                    key: copy.deepcopy(summary[key])
                    for key in TRUNCATABLE_DETAIL_KEYS["summary"]
                    if isinstance(summary.get(key), list)
                },
            }
            detail_bytes = json.dumps(
                detail_values,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")

        # Both capped JSON documents are fully checked before any file is written.
        self.root.mkdir(parents=True, exist_ok=True)
        if detail_bytes is not None:
            self._write_gzip_chunks(detail_path, (detail_bytes,))
        record_path.write_text(encoded_record)
        summary_path.write_text(encoded_summary)
        self._write_gzip_chunks(
            ticks_path,
            (
                (
                    json.dumps(row, separators=(",", ":")).encode("utf-8")
                    + b"\n"
                )
                for row in tick_rows
            ),
        )

        paths = {
            "record": str(record_path),
            "summary": str(summary_path),
            "ticks": str(ticks_path),
        }
        if has_truncations:
            paths["detail"] = str(detail_path)
        sizes: dict[str, int] = {}
        missing: list[str] = []
        for label, raw_path in paths.items():
            path = Path(raw_path)
            if not path.is_file():
                missing.append(raw_path)
            else:
                sizes[label] = path.stat().st_size
        if missing:
            raise ArtifactPathError(
                "artifact writer reported paths that do not exist: "
                + ", ".join(missing)
            )
        return ArtifactWriteResult(paths=paths, sizes_bytes=sizes)