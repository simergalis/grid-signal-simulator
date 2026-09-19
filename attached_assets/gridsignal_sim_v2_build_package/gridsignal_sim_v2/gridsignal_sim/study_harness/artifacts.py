"""Bounded study-harness artifact output with hard path verification."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import ArtifactPathError, ArtifactSizeError


DEFAULT_JSON_CAP_BYTES = 100 * 1024


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

    def _encode(self, payload: dict[str, Any], label: str) -> str:
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        size = len(encoded.encode("utf-8"))
        if size >= self.json_cap_bytes:
            raise ArtifactSizeError(
                f"{label} is {size} bytes; cap is {self.json_cap_bytes}"
            )
        return encoded

    def write(
        self,
        *,
        identity: Any,
        record: dict[str, Any],
        summary: dict[str, Any],
        tick_rows: Iterable[dict[str, Any]],
    ) -> ArtifactWriteResult:
        digest = str(identity.digest)
        self.root.mkdir(parents=True, exist_ok=True)
        record_path = self.root / f"run-{digest}.json"
        summary_path = self.root / f"summary-{digest}.json"
        ticks_path = self.root / f"ticks-{digest}.jsonl.gz"
        record_path.write_text(self._encode(record, "run record"))
        summary_path.write_text(self._encode(summary, "run summary"))
        with gzip.open(ticks_path, "wt", encoding="utf-8") as handle:
            for row in tick_rows:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")

        paths = {
            "record": str(record_path),
            "summary": str(summary_path),
            "ticks": str(ticks_path),
        }
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