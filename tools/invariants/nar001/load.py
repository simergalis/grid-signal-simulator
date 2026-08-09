"""Read recorder JSONL and report field availability before checking anything.

The preflight exists so that a wire-name mismatch produces a report rather than
a KeyError halfway through a run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .access import resolve, leaf_paths
from .contracts import ALIASES


@dataclass
class Recording:
    path: Path
    run_id: str
    ticks: list[dict[str, Any]] = field(default_factory=list)      # payloads carrying sim_time_seconds
    control: list[dict[str, Any]] = field(default_factory=list)    # sentinels, non-tick messages
    events: list[dict[str, Any]] = field(default_factory=list)     # recorder markers
    seqs: list[int] = field(default_factory=list)                  # seq per tick, parallel to ticks
    manifest: dict[str, Any] | None = None
    malformed_lines: int = 0


def load_recording(jsonl_path: str | Path) -> Recording:
    p = Path(jsonl_path)
    rec = Recording(path=p, run_id=p.stem)

    mpath = p.with_suffix("")
    mpath = mpath.with_name(mpath.name + ".manifest.json")
    if mpath.exists():
        try:
            rec.manifest = json.loads(mpath.read_text())
            if isinstance(rec.manifest, dict) and rec.manifest.get("run_id"):
                rec.run_id = str(rec.manifest["run_id"])
        except (json.JSONDecodeError, OSError):
            rec.manifest = None

    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                rec.malformed_lines += 1
                continue
            if not isinstance(obj, dict):
                rec.malformed_lines += 1
                continue
            if "event" in obj and "payload" not in obj:
                rec.events.append(obj)
                continue
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                rec.malformed_lines += 1
                continue
            if "sim_time_seconds" in payload:
                rec.ticks.append(payload)
                rec.seqs.append(int(obj.get("seq", -1)))
            else:
                rec.control.append(payload)
    return rec


def preflight(rec: Recording) -> dict[str, Any]:
    """Per canonical key: which alias answered, and on what fraction of ticks."""
    n = len(rec.ticks)
    rows: dict[str, Any] = {}
    for key, aliases in ALIASES.items():
        states: dict[str, int] = {}
        path_used: dict[str, int] = {}
        for t in rec.ticks:
            r = resolve(t, *aliases)
            states[r.state] = states.get(r.state, 0) + 1
            if r.ok and r.path:
                path_used[r.path] = path_used.get(r.path, 0) + 1
        rows[key] = {
            "aliases": list(aliases),
            "states": states,
            "ok_fraction": (states.get("ok", 0) / n) if n else 0.0,
            "paths_used": path_used,
            "multiple_paths_answered": len(path_used) > 1,
        }
    return {"run_id": rec.run_id, "tick_count": n, "fields": rows,
            "malformed_lines": rec.malformed_lines,
            "recorder_events": [e.get("event") for e in rec.events]}


def constant_fields(rec: Recording) -> dict[str, Any]:
    """Fields present on every tick with an identical value across the recording."""
    if not rec.ticks:
        return {"constant": {}, "varying": [], "note": "no ticks"}
    first = dict(leaf_paths(rec.ticks[0]))
    candidates = dict(first)
    varying: set[str] = set()
    for t in rec.ticks[1:]:
        cur = dict(leaf_paths(t))
        for k in list(candidates):
            if k not in cur or cur[k] != candidates[k]:
                varying.add(k)
                del candidates[k]
        for k in cur:
            if k not in first:
                varying.add(k)
    return {"constant": candidates, "varying": sorted(varying),
            "note": ("workload event schedules and irradiance profiles are resolved "
                     "before t=0 and never appear on the wire; this fingerprint "
                     "covers physical configuration only")}
