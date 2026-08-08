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

    The hash is computed over the resolved values dict, not the raw file
    bytes, so it remains stable regardless of comment or whitespace changes
    in the source JSON that do not affect values.
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
# (used by both the live recorder and the unit tests)
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
                      Defaults to datetime.datetime.now(utc).isoformat().

    Returns:
        (stop_reason, next_seq, stats)
        stop_reason: "run_complete" | "dropped" | "error:<msg>"
        next_seq:    First seq number not yet used (pass as seq_start on reconnect).
        stats:       Dict with per-stream telemetry (see body).
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

    # Reconnect marker — emitted before any messages from this stream.
    if is_reconnect:
        out_queue.put_nowait({"seq": seq, "event": "reconnect"})
        seq += 1

    try:
        async for raw in source:
            received_wall_utc = wall_fn()

            # Deserialise — verbatim pass-through; never transform.
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                payload = {"_raw": str(raw)}

            # ── run_complete sentinel ──────────────────────────────────────
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

            # ── sim_time_seconds tracking and gap detection ────────────────
            if isinstance(payload, dict) and "sim_time_seconds" in payload:
                try:
                    st = float(payload["sim_time_seconds"])
                except (TypeError, ValueError):
                    st = None

                if st is not None:
                    if stats["first_sim_time_s"] is None:
                        stats["first_sim_time_s"] = st
                        # "Missed leading ticks" = first observed sim_time is
                        # materially above zero (more than one expected tick
                        # interval).  5.0 is the fallback before derivation.
                        if st > 5.0:
                            stats["missed_leading_ticks"] = True

                    prev = stats["prev_sim_time_s"]
                    if prev is not None:
                        delta = round(st - prev, 6)
                        if delta > 0:
                            samples = stats["interval_samples"]
                            samples.append(delta)
                            # Derive median interval after ≥3 samples.
                            # Expected spacing comes from the data, not from
                            # an assumed 5.0 s or from TICK_INTERVAL_SIM_SECONDS.
                            if (
                                stats["observed_tick_interval_s"] is None
                                and len(samples) >= 3
                            ):
                                stats["observed_tick_interval_s"] = sorted(samples)[
                                    len(samples) // 2
                                ]

                        expected = stats["observed_tick_interval_s"] or 5.0
                        # Gap: interval > 1.5× expected AND interval derivation
                        # is already stable (≥3 samples collected).
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

            # ── Write JSONL record ─────────────────────────────────────────
            out_queue.put_nowait(
                {
                    "seq": seq,
                    "received_wall_utc": received_wall_utc,
                    "payload": payload,  # verbatim — nulls, nested objects, all of it
                }
            )
            seq += 1
            stats["message_count"] += 1

        # Iterator exhausted cleanly → connection closed without sentinel.
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


async def _ws_messages(ws_uri: str, timeout_s: float) -> AsyncIterator[str]:
    """
    Yield raw JSON strings from a WebSocket until timeout, clean closure,
    or an error.

    The generator handles ConnectionClosed internally so process_stream
    sees a clean iterator exhaustion (→ "dropped") rather than an exception
    (→ "error").

    Timeout is wall-clock based.  The generator returns without yielding if
    the connection cannot be opened within 15 s.
    """
    deadline = time.monotonic() + timeout_s
    try:
        async with websockets.connect(ws_uri, open_timeout=15.0) as ws:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return  # wall-clock timeout
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30.0))
                    yield msg
                except asyncio.TimeoutError:
                    return
                except ConnectionClosed:
                    return
    except (ConnectionClosed, InvalidHandshake, OSError):
        return  # connection never opened or closed during open


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

    The WebSocket is opened immediately after POST returns to minimise the
    subscribe race (Refinement 1).  Messages are received into an in-memory
    queue and written to disk by a separate task so a slow filesystem never
    stalls the socket read (Refinement 2).

    Args:
        base_url:      HTTP base URL of the simulator, e.g. "http://localhost:22126".
        request_body:  Body for POST /runs (StartRunRequest).
        output_dir:    Where to write <run_id>.jsonl and <run_id>.manifest.json.
        catalogue_path: Path to gridsignal_parameters.json.
        timeout_s:     Wall-clock limit per connection attempt.

    Returns:
        (run_id, jsonl_path, manifest_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    catalogue_values, catalogue_hash = load_catalogue(catalogue_path)
    code_rev = _get_code_rev()

    playback_speed = float(request_body.get("playback_speed", 1.0))
    end_sim_time = float(request_body.get("end_sim_time", 300.0))
    scenario_id = request_body.get("scenario_id") or ""
    scenario_version: Optional[str] = None  # not exposed by current API

    recorder_start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ── POST /runs ────────────────────────────────────────────────────────────
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        resp = await client.post("/runs", json=request_body)
        resp.raise_for_status()
        start_resp = resp.json()

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

    # ── In-memory queue → disk writer ─────────────────────────────────────────
    # Unbounded queue: a slow disk write never causes the socket to be dropped.
    q: asyncio.Queue = asyncio.Queue()
    writer_task = asyncio.create_task(_disk_writer(jsonl_path, q))

    # ── State accumulated across reconnect attempts ───────────────────────────
    all_first_sim_time_s: Optional[float] = None
    all_last_sim_time_s: Optional[float] = None
    all_message_count = 0
    all_sim_time_gaps: list[dict] = []
    all_missed_leading_ticks = False
    all_interval_samples: list[float] = []
    all_observed_tick_interval_s: Optional[float] = None

    final_stop_reason = "error:no_attempt"
    seq = 0

    # ── Reconnect loop ────────────────────────────────────────────────────────
    for attempt in range(_MAX_RECONNECT_ATTEMPTS + 1):
        is_reconnect = attempt > 0
        try:
            source = _ws_messages(ws_uri, timeout_s)
            stop_reason, seq, stream_stats = await process_stream(
                source,
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

        # Merge stream_stats into accumulated state.
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

        if stop_reason == "run_complete":
            break
        if stop_reason == "timeout":
            break
        if stop_reason.startswith("error"):
            break
        # "dropped" → retry if attempts remain

    # Signal disk writer to flush and exit.
    q.put_nowait(None)
    await writer_task

    recorder_stop_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Finalise observed_tick_interval_s from all samples if not yet derived.
    obi = all_observed_tick_interval_s
    if obi is None and all_interval_samples:
        s = sorted(all_interval_samples)
        obi = s[len(s) // 2]

    # ── Write manifest ────────────────────────────────────────────────────────
    manifest = {
        "run_id": run_id,
        "scenario_id": scenario_id,
        "scenario_version": scenario_version,
        "playback_speed": playback_speed,
        "end_sim_time_requested": end_sim_time,
        "soc_floor_pct": soc_floor_pct,
        "soc_ceil_pct": soc_ceil_pct,
        "first_sim_time_s": all_first_sim_time_s,
        "last_sim_time_s": all_last_sim_time_s,
        "message_count": all_message_count,
        "recorder_start_utc": recorder_start_utc,
        "recorder_stop_utc": recorder_stop_utc,
        "stop_reason": final_stop_reason,
        "missed_leading_ticks": all_missed_leading_ticks,
        "observed_tick_interval_s": obi,
        "sim_time_gaps": all_sim_time_gaps,
        "code_rev": code_rev,
        "catalogue_hash": catalogue_hash,
        "catalogue_values": catalogue_values,
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

    # Run-start options (scenario_id path)
    p.add_argument("--scenario-id", default=None)

    # Run-start options (direct path)
    p.add_argument("--job-id", default=None)
    p.add_argument("--node-count", type=int, default=None)
    p.add_argument("--hardware-profile-id", default=None)

    # Common
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
        print(f"sim_time_gaps      : {len(m['sim_time_gaps'])}")
        print(f"catalogue_hash     : {m['catalogue_hash']}")
        print(f"catalogue_keys     : {len(m['catalogue_values'])}")
        print(f"jsonl              : {jsonl_path}")
        print(f"manifest           : {manifest_path}")
        print(f"{'─'*60}\n")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
