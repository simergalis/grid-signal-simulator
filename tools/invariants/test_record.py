"""
tools/invariants/test_record.py — Unit tests for the tick recorder.

TC-118  Synthetic message round-trips byte-identically.
TC-119  Simulated disconnect+reconnect produces an explicit reconnect marker;
        seq is gap-free across the boundary.
TC-120  catalogue_hash is stable across two reads of an unchanged file and
        changes when any value changes.
TC-121  A stream with a missing tick produces a sim_time_gap marker with
        correct from_s/to_s, and the gap appears in the manifest stats.
        A stream with no gaps produces neither marker nor gap in stats.
        Expected interval is derived from the stream, not hardcoded.

All tests use synthetic messages and a fake transport. No test opens a real
socket or starts a run.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib
import tempfile

import pytest

from tools.invariants.record import (
    DEFAULT_CATALOGUE_PATH,
    load_catalogue,
    process_stream,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _drain(q: asyncio.Queue) -> list[dict]:
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def _make_source(*messages: dict):
    """Return an async generator that yields JSON-encoded dicts."""

    async def _gen():
        for m in messages:
            yield json.dumps(m)

    return _gen()


# ---------------------------------------------------------------------------
# TC-118 — Payload round-trips byte-identically
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc118_payload_round_trips():
    """
    Encode a message to JSON, pass it through process_stream, and assert that
    json.loads(line)["payload"] == original_message — including nulls, nested
    objects, empty collections, and floats.  No network required.
    """
    original = {
        "run_id": "run-tc118",
        "sim_time_seconds": 5.0,
        "p_demand_mw": 12.3456,
        "kube_metrics": None,
        "data_quality_tags": [],
        "turbine_units": [
            {"asset_id": "t1", "rated_mw": 10.0, "state": "synchronised"}
        ],
        "nested": {"a": 1, "b": None, "c": [1.0, 2.0, 0.0]},
        "checkpoint_states": {},
        "bess_soc_fraction": 0.8750,
        "insufficient_reserve_alert": False,
    }

    q: asyncio.Queue = asyncio.Queue()
    # Source yields only the one message; iterator exhausts → "dropped".
    stop, next_seq, stats = await process_stream(
        _make_source(original),
        out_queue=q,
        seq_start=0,
    )

    assert stop == "dropped"
    items = await _drain(q)
    assert len(items) == 1

    line = json.dumps(items[0])  # simulate writing to JSONL
    parsed = json.loads(line)
    assert parsed["payload"] == original, (
        "Payload did not round-trip identically. "
        f"Got: {parsed['payload']!r}"
    )
    assert parsed["seq"] == 0
    assert "received_wall_utc" in parsed


# ---------------------------------------------------------------------------
# TC-119 — Disconnect and reconnect produces reconnect marker; seq gap-free
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc119_reconnect_marker_and_gap_free_seq():
    """
    Simulated disconnect: first stream yields two tick messages and exhausts
    (simulating a dropped connection before run_complete).  Second stream
    starts with is_reconnect=True and yields the run_complete sentinel.

    Assertions:
    - A {"event": "reconnect"} marker is emitted as the first item of the
      second stream, consuming a seq number.
    - seq values across both streams form a gapless sequence starting at 0.
    """
    tick1 = {"run_id": "run-tc119", "sim_time_seconds": 5.0, "p_demand_mw": 1.0}
    tick2 = {"run_id": "run-tc119", "sim_time_seconds": 10.0, "p_demand_mw": 1.1}
    sentinel = {"type": "run_complete", "run_id": "run-tc119"}

    q: asyncio.Queue = asyncio.Queue()

    # ── First connection: two ticks, then "dropped" ───────────────────────
    stop1, seq_after, stats1 = await process_stream(
        _make_source(tick1, tick2),
        out_queue=q,
        seq_start=0,
        is_reconnect=False,
    )
    assert stop1 == "dropped"

    # ── Second connection: reconnect=True, then run_complete ──────────────
    stop2, seq_final, stats2 = await process_stream(
        _make_source(sentinel),
        out_queue=q,
        seq_start=seq_after,
        is_reconnect=True,
    )
    assert stop2 == "run_complete"

    # ── Inspect the queue ─────────────────────────────────────────────────
    items = await _drain(q)

    # Expected order: tick1(0), tick2(1), reconnect_marker(2), sentinel(3)
    assert len(items) == 4, f"Expected 4 items, got {len(items)}: {items}"

    assert items[0]["seq"] == 0
    assert items[0]["payload"] == tick1

    assert items[1]["seq"] == 1
    assert items[1]["payload"] == tick2

    assert items[2]["seq"] == 2
    assert items[2].get("event") == "reconnect"
    assert "payload" not in items[2]
    assert "received_wall_utc" not in items[2]

    assert items[3]["seq"] == 3
    assert items[3]["payload"] == sentinel

    # seq is gap-free across both streams
    seqs = [item["seq"] for item in items]
    assert seqs == list(range(len(seqs))), f"seq not gap-free: {seqs}"


# ---------------------------------------------------------------------------
# TC-120 — catalogue_hash stability and sensitivity
# ---------------------------------------------------------------------------


def test_tc120_catalogue_hash_stable_and_sensitive():
    """
    catalogue_hash is stable across two reads of an unchanged file and
    changes when any value in the resolved values dict changes.
    """
    path = DEFAULT_CATALOGUE_PATH
    if not path.exists():
        pytest.skip(f"Catalogue not found at {path}")

    values1, hash1 = load_catalogue(path)
    values2, hash2 = load_catalogue(path)

    # Stability across two reads
    assert hash1 == hash2, "Hash changed between two reads of the same file"
    assert values1 == values2, "Values changed between two reads of the same file"

    # Sensitivity: mutate one value, recompute hash, must differ
    key = next(iter(values1))  # first key
    modified = {**values1, key: "__CHANGED__"}
    canonical = json.dumps(modified, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    modified_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    assert modified_hash != hash1, (
        f"Hash did not change after modifying key {key!r}"
    )


def test_tc120_catalogue_hash_from_tmp_file():
    """
    Verify hash sensitivity using a temporary catalogue file, so the test
    does not depend on the real catalogue being present.
    """
    def _make_cat(dt_lead_value):
        return json.dumps({
            "adjustable": [
                {"key": "dt_lead", "default": dt_lead_value},
                {"key": "alpha_max", "default": 0.2},
            ],
            "enumerated": [],
            "locked": [
                {"key": "checkpoint_drop_pct", "value": 15},
            ],
        })

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(_make_cat(45))
        tmp1 = pathlib.Path(f.name)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(_make_cat(45))
        tmp2 = pathlib.Path(f.name)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(_make_cat(46))  # dt_lead changed
        tmp3 = pathlib.Path(f.name)

    try:
        _, h1 = load_catalogue(tmp1)
        _, h2 = load_catalogue(tmp2)
        _, h3 = load_catalogue(tmp3)

        assert h1 == h2, "Same content → same hash"
        assert h1 != h3, "Changed content → different hash"
    finally:
        tmp1.unlink(missing_ok=True)
        tmp2.unlink(missing_ok=True)
        tmp3.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TC-121 — sim_time_gap detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc121_gap_detected_with_derived_interval():
    """
    A stream with a missing tick (gap > 1.5× derived interval) produces:
    - A sim_time_gap marker in the JSONL output with correct from_s / to_s.
    - The gap in stats["sim_time_gaps"].
    - stats["observed_tick_interval_s"] is derived from the stream (5.0),
      not hardcoded.

    A stream with no gaps produces neither marker nor any entry in sim_time_gaps.
    """
    # ── Gapped stream ─────────────────────────────────────────────────────────
    # Ticks at 5, 10, 15, 25, 30. Interval derived after 3 samples: median of
    # [5, 5, 10] = 5.0. Gap at 25-15=10 > 5*1.5=7.5 → marker expected.
    gapped_msgs = [
        {"run_id": "r", "sim_time_seconds": 5.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 10.0, "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 15.0, "p_demand_mw": 1.0},  # 3 deltas now
        {"run_id": "r", "sim_time_seconds": 25.0, "p_demand_mw": 1.0},  # GAP
        {"run_id": "r", "sim_time_seconds": 30.0, "p_demand_mw": 1.0},
        {"type": "run_complete"},
    ]

    q1: asyncio.Queue = asyncio.Queue()
    stop1, _, stats1 = await process_stream(_make_source(*gapped_msgs), out_queue=q1)

    assert stop1 == "run_complete"
    assert stats1["observed_tick_interval_s"] == 5.0, (
        f"Expected derived interval 5.0, got {stats1['observed_tick_interval_s']}"
    )
    assert len(stats1["sim_time_gaps"]) == 1, (
        f"Expected 1 gap, got {stats1['sim_time_gaps']}"
    )
    assert stats1["sim_time_gaps"][0] == {"from_s": 15.0, "to_s": 25.0}

    items1 = await _drain(q1)
    gap_markers = [i for i in items1 if i.get("event") == "sim_time_gap"]
    assert len(gap_markers) == 1
    assert gap_markers[0]["from_s"] == 15.0
    assert gap_markers[0]["to_s"] == 25.0

    # ── No-gap stream ─────────────────────────────────────────────────────────
    clean_msgs = [
        {"run_id": "r", "sim_time_seconds": 5.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 10.0, "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 15.0, "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 20.0, "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 25.0, "p_demand_mw": 1.0},
        {"type": "run_complete"},
    ]

    q2: asyncio.Queue = asyncio.Queue()
    stop2, _, stats2 = await process_stream(_make_source(*clean_msgs), out_queue=q2)

    assert stop2 == "run_complete"
    assert stats2["sim_time_gaps"] == [], (
        f"Expected no gaps, got {stats2['sim_time_gaps']}"
    )

    items2 = await _drain(q2)
    gap_markers2 = [i for i in items2 if i.get("event") == "sim_time_gap"]
    assert gap_markers2 == [], f"Expected no gap markers, got {gap_markers2}"


@pytest.mark.asyncio
async def test_tc121_interval_not_hardcoded():
    """
    Confirm the expected interval is derived from the stream, not from any
    hardcoded constant.  A stream with a 2-second tick interval must derive
    2.0 s, not 5.0 s, and flag a gap at 4.5 s (> 2*1.5=3.0 s).
    """
    msgs = [
        {"run_id": "r", "sim_time_seconds": 2.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 4.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 6.0,  "p_demand_mw": 1.0},   # 3 deltas; interval=2.0
        {"run_id": "r", "sim_time_seconds": 10.5, "p_demand_mw": 1.0},   # 4.5 s > 3.0 → gap
        {"type": "run_complete"},
    ]

    q: asyncio.Queue = asyncio.Queue()
    _, _, stats = await process_stream(_make_source(*msgs), out_queue=q)

    assert stats["observed_tick_interval_s"] == 2.0, (
        f"Derived interval should be 2.0, got {stats['observed_tick_interval_s']}"
    )
    assert len(stats["sim_time_gaps"]) == 1
    assert stats["sim_time_gaps"][0]["from_s"] == 6.0
    assert stats["sim_time_gaps"][0]["to_s"] == 10.5
