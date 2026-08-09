"""
tools/invariants/record.py — WebSocket tick recorder for the GridSignal invariant harness.

Standalone: imports nothing from core/, runtime/, or renewable/.
Connects as an ordinary WebSocket client to GET /ws/{run_id}.
Writes one JSONL line per received message, then a manifest JSON alongside it.

JSONL line format:
    {"seq": N, "received_wall_utc": "...", "payload": {<verbatim message>}}

Marker lines (no payload, no received_wall_utc):
    {"seq": N, "event": "reconnect"}
    {"seq": N, "event": "sim_time_gap", "from_s": ..., "to_s": ...}

Usage (CLI):
    python -m tools.invariants.record \\
        --base-url http://localhost:22126 \\
        --scenario-id demo-baseline \\
        --end-sim-time 120 --playback-speed 5

    python -m tools.invariants.record \\
        --base-url http://localhost:22126 \\
        --job-id smoke-001 --node-count 50 \\
        --end-sim-time 60 --playback-speed 10

DO NOT rules (NAR-001):
    - Import nothing from core/, runtime/, or renewable/.
    - Do not read from InMemoryTimeseriesSink or any in-process object.
    - Do not transform payload. verbatim means verbatim, including nulls.
    - Do not filter by message type. Record everything.
    - Do not compute, derive, or add fields to the payload.
    - Do not conflate received_wall_utc with wall_stamp_utc (excluded from wire).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import AsyncIterator, Optional

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, InvalidHandshake

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = pathlib.Path(__file__).resolve().parent
RECORDINGS_DIR = _HERE / "recordings"

_SIM_ROOT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "attached_assets"
    / "gridsignal_sim_v2_build_package"
    / "gridsignal_sim_v2"
    / "gridsignal_sim"
)
DEFAULT_CATALOGUE_PATH = _SIM_ROOT / "gridsignal_parameters.json"

# ---------------------------------------------------------------------------
# Catalogue loader (no server-side accessor; reads the JSON directly)
# ---------------------------------------------------------------------------


def load_catalogue(catalogue_path: pathlib.Path) -> tuple[dict, str]:
    """
    Read gridsignal_parameters.json and return (resolved_values, catalogue_hash).

    resolved_values:
        Flat dict of key → default/value for all entries in the
        "adjustable", "enumerated", and "locked" sections.

    catalogue_hash:
        "sha256:<hex>" of the canonical JSON of resolved_values
        (keys sorted, no whitespace).  Stable across reads of an
        unchanged file; changes when any value changes.
    """
    raw = catalogue_path.read_bytes()
    d = json.loads(raw)

    values: dict = {}
    for entry in d.get("adjustable", []):
        values[entry["key"]] = entry["default"]
    for entry in d.get("enumerated", []):
        values[entry["key"]] = entry.get("default", entry.get("options_source"))
    for entry in d.get("locked", []):
        values[entry["key"]] = entry["value"]

    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return values, f"sha256:{sha}"


# ---------------------------------------------------------------------------
# Payload flattener (for constant_fields computation)
# ---------------------------------------------------------------------------


def _flatten_payload(d, prefix: str = "") -> dict:
    """
    Recursively flatten a dict or list into {dotted[i].path: value}.

    dict keys are joined with ".", list indices are written as "[i]".
    Only leaf (non-container) values are emitted as keys.  None is a
    leaf — it is kept as-is to distinguish "always null" from "absent".
    """
    result: dict = {}
    if isinstance(d, dict):
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                result.update(_flatten_payload(v, path))
            else:
                result[path] = v
    elif isinstance(d, list):
        for i, v in enumerate(d):
            path = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                result.update(_flatten_payload(v, path))
            else:
                result[path] = v
    else:
        # Scalar reached via recursive call (shouldn't happen directly)
        result[prefix] = d
    return result


def compute_constant_fields(jsonl_path: pathlib.Path) -> tuple[dict, str, list[str], str]:
    """
    Read all tick payloads from a JSONL file and classify every leaf field
    (including nested paths) as either constant or varying.

    A field is constant iff:
        1. It appears in EVERY tick payload (not just some).
        2. Its value is identical across all ticks (None counts as a value).

    Returns:
        constant_fields:      {dotted.path: value} for constant fields.
        constant_fields_hash: "sha256:<hex>" of canonical JSON of constant_fields.
        varying_fields:       sorted list of dotted paths that vary or are absent.
        note:                 human-readable limitation note.
    """
    ticks: list[dict] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if (
            "payload" in item
            and isinstance(item["payload"], dict)
            and "sim_time_seconds" in item["payload"]
        ):
            ticks.append(item["payload"])

    if not ticks:
        return {}, "sha256:" + hashlib.sha256(b"{}").hexdigest(), [], "no tick payloads"

    # Flatten each tick
    flattened: list[dict] = [_flatten_payload(t) for t in ticks]

    # Union of all paths
    all_paths: set[str] = set()
    for f in flattened:
        all_paths.update(f.keys())

    constant_fields: dict = {}
    varying_fields: list[str] = []

    for path in sorted(all_paths):
        # Present in every tick?
        present_in_all = all(path in f for f in flattened)
        if not present_in_all:
            varying_fields.append(path)
            continue
        # Same value in every tick?
        first_val = flattened[0][path]
        if all(f[path] == first_val for f in flattened):
            constant_fields[path] = first_val
        else:
            varying_fields.append(path)

    canonical = json.dumps(
        constant_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    constant_fields_hash = f"sha256:{sha}"

    note = (
        "constant_fields captures physical configuration fields that are "
        "empirically stable across every tick in this run. It does NOT include "
        "workload event schedules, irradiance profiles, or generator seeds, "
        "which are resolved before the run starts and never appear on the wire. "
        "Use constant_fields_hash to compare physical configuration between runs, "
        "not to assert full scenario reproducibility."
    )

    return constant_fields, constant_fields_hash, varying_fields, note


# ---------------------------------------------------------------------------
# Seed / determinism probe
# ---------------------------------------------------------------------------


async def _probe_scenario_seeds(
    base_url: str, scenario_id: str
) -> tuple[bool, dict]:
    """
    Fetch the scenario spec via GET /scenarios/{scenario_id} and check
    whether integer seeds are set on any generator config.

    Returns:
        (rng_seed_present, seed_detail)
        rng_seed_present: True if at least one integer seed is set.
        seed_detail: dict mapping config_name → seed value for all non-None seeds.
    """
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            r = await client.get(f"/scenarios/{scenario_id}")
            if r.status_code != 200:
                return False, {"error": f"HTTP {r.status_code}"}
            spec = r.json().get("spec", {})
    except Exception as exc:  # noqa: BLE001
        return False, {"error": str(exc)}

    seeds: dict = {}
    # Top-level seed fields
    for key in ("seed", "rng_seed"):
        val = spec.get(key)
        if val is not None:
            seeds[key] = val

    # Per-generator config blocks
    for cfg_name in (
        "cluster_gen_config",
        "stressor_gen_config",
        "param_sampling_config",
        "telemetry_corruption_config",
    ):
        cfg = spec.get(cfg_name) or {}
        if isinstance(cfg, dict):
            for k, v in cfg.items():
                if "seed" in k.lower() and v is not None:
                    seeds[f"{cfg_name}.{k}"] = v

    rng_seed_present = any(isinstance(v, int) for v in seeds.values())
    return rng_seed_present, seeds


# ---------------------------------------------------------------------------
# Code revision
# ---------------------------------------------------------------------------


def _get_code_rev() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_HERE,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Transport-agnostic stream processor
# ---------------------------------------------------------------------------


async def process_stream(
    source: AsyncIterator[str],
    *,
    out_queue: asyncio.Queue,
    seq_start: int = 0,
    is_reconnect: bool = False,
    wall_fn=None,
) -> tuple[str, int, dict]:
    """
    Consume an async iterator of raw JSON strings, writing JSONL records to
    out_queue.  Returns when the stream ends or a run_complete sentinel arrives.

    Args:
        source:       Async iterator yielding raw JSON strings (one per message).
        out_queue:    Queue consumed by the disk-writer task.
        seq_start:    First seq number to use (enables gap-free chaining on reconnect).
        is_reconnect: When True, emits a {"seq": N, "event": "reconnect"} marker
                      before processing any messages.
        wall_fn:      Callable returning an ISO-8601 UTC timestamp string.

    Returns:
        (stop_reason, next_seq, stats)
        stop_reason: "run_complete" | "dropped" | "timeout" | "error:<msg>"
        next_seq:    First seq number not yet used.
        stats:       Per-stream telemetry dict.
    """
    if wall_fn is None:

        def wall_fn() -> str:
            return datetime.datetime.now(datetime.timezone.utc).isoformat()

    seq = seq_start
    stats: dict = {
        "first_sim_time_s": None,
        "last_sim_time_s": None,
        "prev_sim_time_s": None,
        "interval_samples": [],
        "observed_tick_interval_s": None,
        "sim_time_gaps": [],
        "message_count": 0,
        "missed_leading_ticks": False,
    }

    if is_reconnect:
        out_queue.put_nowait({"seq": seq, "event": "reconnect"})
        seq += 1

    try:
        async for raw in source:
            received_wall_utc = wall_fn()

            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                payload = {"_raw": str(raw)}

            if isinstance(payload, dict) and payload.get("type") == "run_complete":
                out_queue.put_nowait(
                    {
                        "seq": seq,
                        "received_wall_utc": received_wall_utc,
                        "payload": payload,
                    }
                )
                seq += 1
                stats["message_count"] += 1
                return "run_complete", seq, stats

            if isinstance(payload, dict) and "sim_time_seconds" in payload:
                try:
                    st = float(payload["sim_time_seconds"])
                except (TypeError, ValueError):
                    st = None

                if st is not None:
                    if stats["first_sim_time_s"] is None:
                        stats["first_sim_time_s"] = st
                        if st > 5.0:
                            stats["missed_leading_ticks"] = True

                    prev = stats["prev_sim_time_s"]
                    if prev is not None:
                        delta = round(st - prev, 6)
                        if delta > 0:
                            samples = stats["interval_samples"]
                            samples.append(delta)
                            if (
                                stats["observed_tick_interval_s"] is None
                                and len(samples) >= 3
                            ):
                                stats["observed_tick_interval_s"] = sorted(samples)[
                                    len(samples) // 2
                                ]

                        expected = stats["observed_tick_interval_s"] or 5.0
                        if delta > expected * 1.5 and len(stats["interval_samples"]) >= 3:
                            gap_marker = {
                                "seq": seq,
                                "event": "sim_time_gap",
                                "from_s": prev,
                                "to_s": st,
                            }
                            out_queue.put_nowait(gap_marker)
                            seq += 1
                            stats["sim_time_gaps"].append({"from_s": prev, "to_s": st})

                    stats["prev_sim_time_s"] = st
                    stats["last_sim_time_s"] = st

            out_queue.put_nowait(
                {
                    "seq": seq,
                    "received_wall_utc": received_wall_utc,
                    "payload": payload,
                }
            )
            seq += 1
            stats["message_count"] += 1

        return "dropped", seq, stats

    except Exception as exc:  # noqa: BLE001
        return f"error:{exc}", seq, stats


# ---------------------------------------------------------------------------
# Disk-writer coroutine
# ---------------------------------------------------------------------------


async def _disk_writer(path: pathlib.Path, q: asyncio.Queue) -> None:
    """Drain the queue and write each item as a JSONL line.  None = sentinel."""
    with path.open("w", encoding="utf-8") as f:
        while True:
            item = await q.get()
            if item is None:
                break
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            f.flush()
            q.task_done()


# ---------------------------------------------------------------------------
# WebSocket async-generator (live transport)
# ---------------------------------------------------------------------------


async def _ws_messages(
    ws_uri: str,
    timeout_s: float,
    *,
    connected_event: Optional[asyncio.Event] = None,
) -> AsyncIterator[str]:
    """
    Yield raw JSON strings from a WebSocket until timeout, clean closure, or error.

    connected_event: if provided, set() as soon as the WS handshake completes
                     (before any messages are received).  Callers use this to
                     record ws_subscribed_utc precisely.
    """
    deadline = time.monotonic() + timeout_s
    try:
        async with websockets.connect(ws_uri, open_timeout=15.0) as ws:
            if connected_event is not None:
                connected_event.set()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30.0))
                    yield msg
                except asyncio.TimeoutError:
                    return
                except ConnectionClosed:
                    return
    except (ConnectionClosed, InvalidHandshake, OSError):
        if connected_event is not None and not connected_event.is_set():
            connected_event.set()  # unblock any waiter even on failure
        return


# ---------------------------------------------------------------------------
# Top-level recorder
# ---------------------------------------------------------------------------

_MAX_RECONNECT_ATTEMPTS = 3


async def record(
    base_url: str,
    request_body: dict,
    *,
    output_dir: pathlib.Path = RECORDINGS_DIR,
    catalogue_path: pathlib.Path = DEFAULT_CATALOGUE_PATH,
    timeout_s: float = 600.0,
) -> tuple[str, pathlib.Path, pathlib.Path]:
    """
    Start a run via POST /runs, subscribe to its WebSocket, and write JSONL
    + manifest to output_dir.

    Returns:
        (run_id, jsonl_path, manifest_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    catalogue_values, catalogue_hash = load_catalogue(catalogue_path)
    code_rev = _get_code_rev()
    mistral_key_present = bool(os.environ.get("MISTRAL_API_KEY"))

    playback_speed = float(request_body.get("playback_speed", 1.0))
    end_sim_time = float(request_body.get("end_sim_time", 300.0))
    scenario_id = request_body.get("scenario_id") or ""

    # ── Seed probe ────────────────────────────────────────────────────────────
    rng_seed_present: Optional[bool] = None
    seed_detail: dict = {}
    if scenario_id:
        rng_seed_present, seed_detail = await _probe_scenario_seeds(
            base_url, scenario_id
        )

    recorder_start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ── POST /runs ────────────────────────────────────────────────────────────
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        resp = await client.post("/runs", json=request_body)
        resp.raise_for_status()
        start_resp = resp.json()

    post_returned_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    run_id = start_resp["run_id"]
    soc_floor_pct = start_resp.get("soc_floor_pct", 10.0)
    soc_ceil_pct = start_resp.get("soc_ceil_pct", 95.0)

    # ── Output paths ──────────────────────────────────────────────────────────
    safe_id = run_id.replace("/", "_")
    jsonl_path = output_dir / f"{safe_id}.jsonl"
    manifest_path = output_dir / f"{safe_id}.manifest.json"

    # ── WebSocket URL ─────────────────────────────────────────────────────────
    ws_base = (
        base_url.rstrip("/")
        .replace("http://", "ws://")
        .replace("https://", "wss://")
    )
    ws_uri = f"{ws_base}/ws/{run_id}"

    # ── Queue → disk writer ───────────────────────────────────────────────────
    q: asyncio.Queue = asyncio.Queue()
    writer_task = asyncio.create_task(_disk_writer(jsonl_path, q))

    # ── Accumulated state ─────────────────────────────────────────────────────
    all_first_sim_time_s: Optional[float] = None
    all_last_sim_time_s: Optional[float] = None
    all_message_count = 0
    all_sim_time_gaps: list[dict] = []
    all_missed_leading_ticks = False
    all_interval_samples: list[float] = []
    all_observed_tick_interval_s: Optional[float] = None

    final_stop_reason = "error:no_attempt"
    ws_subscribed_utc: Optional[str] = None
    seq = 0

    # ── Reconnect loop ────────────────────────────────────────────────────────
    for attempt in range(_MAX_RECONNECT_ATTEMPTS + 1):
        is_reconnect = attempt > 0
        connected_event = asyncio.Event()

        # Capture ws_subscribed_utc on the first successful connection.
        async def _timed_source(_uri=ws_uri, _ts=timeout_s, _ev=connected_event):
            nonlocal ws_subscribed_utc
            async for msg in _ws_messages(_uri, _ts, connected_event=_ev):
                if ws_subscribed_utc is None and _ev.is_set():
                    ws_subscribed_utc = datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                yield msg

        try:
            stop_reason, seq, stream_stats = await process_stream(
                _timed_source(),
                out_queue=q,
                seq_start=seq,
                is_reconnect=is_reconnect,
            )
        except Exception as exc:  # noqa: BLE001
            stop_reason = f"error:{exc}"
            stream_stats = {
                "first_sim_time_s": None,
                "last_sim_time_s": None,
                "interval_samples": [],
                "observed_tick_interval_s": None,
                "sim_time_gaps": [],
                "message_count": 0,
                "missed_leading_ticks": False,
            }

        if all_first_sim_time_s is None:
            all_first_sim_time_s = stream_stats["first_sim_time_s"]
        if stream_stats["last_sim_time_s"] is not None:
            all_last_sim_time_s = stream_stats["last_sim_time_s"]
        all_message_count += stream_stats["message_count"]
        all_sim_time_gaps.extend(stream_stats["sim_time_gaps"])
        if stream_stats["missed_leading_ticks"]:
            all_missed_leading_ticks = True
        all_interval_samples.extend(stream_stats["interval_samples"])
        if stream_stats["observed_tick_interval_s"] is not None:
            all_observed_tick_interval_s = stream_stats["observed_tick_interval_s"]

        final_stop_reason = stop_reason

        if stop_reason in ("run_complete", "timeout"):
            break
        if stop_reason.startswith("error"):
            break
        # "dropped" → retry if attempts remain

    # Signal disk writer to flush and exit.
    q.put_nowait(None)
    await writer_task

    recorder_stop_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ── Subscribe timing ──────────────────────────────────────────────────────
    subscribe_window_ms: Optional[float] = None
    if ws_subscribed_utc and post_returned_utc:
        try:
            t_post = datetime.datetime.fromisoformat(post_returned_utc)
            t_ws = datetime.datetime.fromisoformat(ws_subscribed_utc)
            subscribe_window_ms = round((t_ws - t_post).total_seconds() * 1000, 1)
        except Exception:  # noqa: BLE001
            pass

    # ── Observed tick interval ────────────────────────────────────────────────
    obi = all_observed_tick_interval_s
    if obi is None and all_interval_samples:
        s = sorted(all_interval_samples)
        obi = s[len(s) // 2]

    # ── Constant/varying field analysis ───────────────────────────────────────
    constant_fields: dict = {}
    constant_fields_hash: str = ""
    varying_fields: list[str] = []
    constant_fields_note: str = ""
    if jsonl_path.exists():
        constant_fields, constant_fields_hash, varying_fields, constant_fields_note = (
            compute_constant_fields(jsonl_path)
        )

    # ── Write manifest ────────────────────────────────────────────────────────
    manifest = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_version": None,
        "playback_speed": playback_speed,
        "end_sim_time_requested": end_sim_time,
        "soc_floor_pct": soc_floor_pct,
        "soc_ceil_pct": soc_ceil_pct,
        # Timing
        "recorder_start_utc": recorder_start_utc,
        "post_returned_utc": post_returned_utc,
        "ws_subscribed_utc": ws_subscribed_utc,
        "subscribe_window_ms": subscribe_window_ms,
        "recorder_stop_utc": recorder_stop_utc,
        # Run outcome
        "stop_reason": final_stop_reason,
        "message_count": all_message_count,
        # Leading tick race
        "missed_leading_ticks": all_missed_leading_ticks,
        "first_sim_time_s": all_first_sim_time_s,
        "last_sim_time_s": all_last_sim_time_s,
        "observed_tick_interval_s": obi,
        "sim_time_gaps": all_sim_time_gaps,
        # Determinism facts
        "rng_seed_present": rng_seed_present,
        "seed_detail": seed_detail,
        "mistral_key_present": mistral_key_present,
        # Catalogue
        "catalogue_hash": catalogue_hash,
        "catalogue_values": catalogue_values,
        # Physical configuration fingerprint (empirical; see note)
        "constant_fields": constant_fields,
        "constant_fields_hash": constant_fields_hash,
        "varying_fields": varying_fields,
        "constant_fields_note": constant_fields_note,
        # Provenance
        "code_rev": code_rev,
        "run_start_request": request_body,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    return run_id, jsonl_path, manifest_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Record a GridSignal run to JSONL via WebSocket."
    )
    p.add_argument("--base-url", default="http://localhost:22126")
    p.add_argument("--output-dir", default=str(RECORDINGS_DIR))
    p.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE_PATH))
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--scenario-id", default=None)
    p.add_argument("--job-id", default=None)
    p.add_argument("--node-count", type=int, default=None)
    p.add_argument("--hardware-profile-id", default=None)
    p.add_argument("--end-sim-time", type=float, default=300.0)
    p.add_argument("--playback-speed", type=float, default=1.0)
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.scenario_id:
        body: dict = {
            "scenario_id": args.scenario_id,
            "end_sim_time": args.end_sim_time,
            "playback_speed": args.playback_speed,
        }
    elif args.job_id and args.node_count:
        body = {
            "job_id": args.job_id,
            "node_count": args.node_count,
            "end_sim_time": args.end_sim_time,
            "playback_speed": args.playback_speed,
        }
        if args.hardware_profile_id:
            body["hardware_profile_id"] = args.hardware_profile_id
    else:
        parser.error("Provide --scenario-id OR (--job-id + --node-count).")

    async def _run() -> None:
        run_id, jsonl_path, manifest_path = await record(
            args.base_url,
            body,
            output_dir=pathlib.Path(args.output_dir),
            catalogue_path=pathlib.Path(args.catalogue),
            timeout_s=args.timeout,
        )
        with open(manifest_path) as f:
            m = json.load(f)

        print(f"\n{'─'*60}")
        print(f"run_id             : {run_id}")
        print(f"stop_reason        : {m['stop_reason']}")
        print(f"message_count      : {m['message_count']}")
        print(f"first_sim_time_s   : {m['first_sim_time_s']}")
        print(f"last_sim_time_s    : {m['last_sim_time_s']}")
        print(f"observed_interval  : {m['observed_tick_interval_s']} s")
        print(f"missed_leading     : {m['missed_leading_ticks']}")
        print(f"subscribe_window   : {m['subscribe_window_ms']} ms")
        print(f"sim_time_gaps      : {len(m['sim_time_gaps'])}")
        print(f"rng_seed_present   : {m['rng_seed_present']}  {m['seed_detail']}")
        print(f"mistral_key        : {m['mistral_key_present']}")
        print(f"constant_fields    : {len(m['constant_fields'])} fields")
        print(f"varying_fields     : {len(m['varying_fields'])} fields")
        print(f"constant_hash      : {m['constant_fields_hash']}")
        print(f"catalogue_hash     : {m['catalogue_hash']}")
        print(f"catalogue_keys     : {len(m['catalogue_values'])}")
        print(f"jsonl              : {jsonl_path}")
        print(f"manifest           : {manifest_path}")
        print(f"{'─'*60}\n")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
