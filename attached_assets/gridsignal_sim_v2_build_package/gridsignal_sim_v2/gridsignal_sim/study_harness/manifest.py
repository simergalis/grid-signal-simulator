"""Run identity and persistent cache for study-harness executions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class RunIdentity:
    scenario_id: str
    mode: str
    parameter_set: dict[str, Any]
    seed: int | str | None
    duration_seconds: float
    tick_seconds: float
    engine_commit: str
    harness_commit: str

    def payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.payload(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def make_run_identity(
    *,
    scenario_id: str,
    mode: str,
    parameter_set: dict[str, Any] | None,
    seed: int | str | None,
    duration_seconds: float,
    tick_seconds: float,
    engine_commit: str,
    harness_commit: str,
) -> RunIdentity:
    return RunIdentity(
        scenario_id=scenario_id,
        mode=mode,
        parameter_set=dict(parameter_set or {}),
        seed=seed,
        duration_seconds=float(duration_seconds),
        tick_seconds=float(tick_seconds),
        engine_commit=str(engine_commit),
        harness_commit=str(harness_commit),
    )


class RunManifestCache:
    """A small JSON manifest whose cache hit never invokes the executor."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.manifest_path = self.root / "manifest.json"
        self.records_dir = self.root / "records"

    def _read(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            return {"version": 1, "runs": {}}
        return json.loads(self.manifest_path.read_text())

    def get(self, identity: RunIdentity) -> dict[str, Any] | None:
        manifest = self._read()
        entry = manifest.get("runs", {}).get(identity.digest)
        if not isinstance(entry, dict):
            return None
        path = self.root / str(entry.get("record_path", ""))
        if not path.is_file():
            return None
        return json.loads(path.read_text())

    def put(self, identity: RunIdentity, record: dict[str, Any]) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        self.records_dir.mkdir(parents=True, exist_ok=True)
        path = self.records_dir / f"{identity.digest}.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        manifest = self._read()
        manifest.setdefault("version", 1)
        manifest.setdefault("runs", {})[identity.digest] = {
            "identity": identity.payload(),
            "record_path": str(path.relative_to(self.root)),
            "record_size_bytes": path.stat().st_size,
        }
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        return record

    def get_or_execute(
        self,
        identity: RunIdentity,
        execute: Callable[[], dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        cached = self.get(identity)
        if cached is not None:
            return cached, True
        record = execute()
        return self.put(identity, record), False