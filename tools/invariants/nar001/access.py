"""Field access with explicit absent/null/non-numeric discrimination.

The null rule lives here. A field that is absent, null, or non-numeric never
becomes 0.0 -- it produces a Resolved carrying the reason, and every checker
that touches one returns NOT_EVALUABLE.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

OK = "ok"
ABSENT = "absent"
NULL = "null"
NON_NUMERIC = "non_numeric"

_SEGMENT = re.compile(r"^([^\[\]]*)((?:\[\d+\])*)$")
_INDEX = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Resolved:
    """Outcome of looking a field up. `state` is one of OK/ABSENT/NULL/NON_NUMERIC."""

    state: str
    value: Any = None
    path: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == OK

    def reason(self) -> str:
        if self.state == ABSENT:
            return f"field absent: {self.path}"
        if self.state == NULL:
            return f"field null: {self.path}"
        if self.state == NON_NUMERIC:
            return f"field non-numeric: {self.path}={self.value!r}"
        return ""


def get_path(obj: Any, path: str) -> Resolved:
    """Resolve a dotted path with optional [n] indices, e.g. turbine_units[0].rated_mw."""
    cur: Any = obj
    for raw in path.split("."):
        m = _SEGMENT.match(raw)
        if m is None:
            return Resolved(ABSENT, path=path)
        key, idx_part = m.group(1), m.group(2)
        if key:
            if not isinstance(cur, dict) or key not in cur:
                return Resolved(ABSENT, path=path)
            cur = cur[key]
        for idx in _INDEX.findall(idx_part):
            i = int(idx)
            if cur is None:
                return Resolved(NULL, path=path)
            if not isinstance(cur, (list, tuple)) or i >= len(cur):
                return Resolved(ABSENT, path=path)
            cur = cur[i]
        if cur is None and raw != path.split(".")[-1]:
            # a null partway along the path blocks everything beneath it
            return Resolved(NULL, path=path)
    if cur is None:
        return Resolved(NULL, path=path)
    return Resolved(OK, cur, path)


def resolve(payload: Any, *aliases: str) -> Resolved:
    """Try each alias in order. Prefer a present value, then a null, then absent.

    Aliases exist because the wire carries duplicate names for three quantities
    (p_demand_mw / p_total_mw and friends). The path actually used is recorded so
    the report can say which one answered.
    """
    best: Resolved | None = None
    for path in aliases:
        r = get_path(payload, path)
        if r.ok:
            return r
        if best is None or (best.state == ABSENT and r.state == NULL):
            best = r
    return best if best is not None else Resolved(ABSENT, path=None)


def resolve_number(payload: Any, *aliases: str) -> Resolved:
    """As resolve(), but a present non-numeric value is reported as NON_NUMERIC."""
    r = resolve(payload, *aliases)
    if not r.ok:
        return r
    if isinstance(r.value, bool) or not isinstance(r.value, (int, float)):
        return Resolved(NON_NUMERIC, r.value, r.path)
    return Resolved(OK, float(r.value), r.path)


def leaf_paths(obj: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    """Yield (path, value) for every leaf, walking dicts and lists."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaf_paths(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from leaf_paths(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj
