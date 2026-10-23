"""Single canonical physical-tick identity hash contract."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum
from typing import Any, Iterable, Mapping


# PROPOSED_HERE: preserve the established baseline-runner contract while
# excluding only known observation/advisory fields. Source: DR Phase 0b
# physical hash contract; D4 requires one shared definition.
PHYSICAL_TICK_HASH_EXCLUSIONS = frozenset(
    {
        "advisory_telemetry",
        "fabric_modal",
        "wall_stamp_utc",
        "insufficient_reserve_proposal_id",
    }
)


def plain(value: Any) -> Any:
    """Convert simulator values to the baseline runner's JSON-safe form."""
    if dataclasses.is_dataclass(value):
        return plain(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (plain(item) for item in value),
            key=lambda item: json.dumps(
                item, sort_keys=True, allow_nan=True
            ),
        )
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return plain(value.value)
    return value


def physical_tick_json(tick: Any) -> bytes:
    row = plain(tick)
    if not isinstance(row, Mapping):
        raise TypeError("physical tick must serialize to a mapping")
    physical = {
        key: value
        for key, value in row.items()
        if key not in PHYSICAL_TICK_HASH_EXCLUSIONS
    }
    return json.dumps(
        physical,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
    ).encode("utf-8") + b"\n"


class PhysicalIdentityHasher:
    """Incremental SHA-256 over ordered physical tick records."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256()
        self.tick_count = 0

    def update(self, tick: Any) -> None:
        self._digest.update(physical_tick_json(tick))
        self.tick_count += 1

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def physical_identity_hash(ticks: Iterable[Any]) -> str:
    hasher = PhysicalIdentityHasher()
    for tick in ticks:
        hasher.update(tick)
    return hasher.hexdigest()
