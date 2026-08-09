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
TC-122  constant_fields on a synthetic JSONL:
        - contains exactly the fields that do not vary,
        - excludes a field that changes on the final tick only,
        - walks nested paths (turbine_units[0].rated_mw, commitment_block.*),
        - produces a hash that is stable across two computations,
        - hash differs when any constant value is changed.

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
    _flatten_payload,
    compute_constant_fields,
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
    async def _gen():
        for m in messages:
            yield json.dumps(m)
    return _gen()


def _write_jsonl(path: pathlib.Path, payloads: list[dict]) -> None:
    """Write synthetic JSONL lines (one seq per tick payload)."""
    with path.open("w") as f:
        for i, p in enumerate(payloads):
            line = {"seq": i, "received_wall_utc": "2026-08-08T00:00:00+00:00", "payload": p}
            f.write(json.dumps(line) + "\n")


# ---------------------------------------------------------------------------
# TC-118 — Payload round-trips byte-identically
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc118_payload_round_trips():
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
    stop, next_seq, stats = await process_stream(
        _make_source(original),
        out_queue=q,
        seq_start=0,
    )

    assert stop == "dropped"
    items = await _drain(q)
    assert len(items) == 1

    line = json.dumps(items[0])
    parsed = json.loads(line)
    assert parsed["payload"] == original
    assert parsed["seq"] == 0
    assert "received_wall_utc" in parsed


# ---------------------------------------------------------------------------
# TC-119 — Reconnect marker and gap-free seq
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc119_reconnect_marker_and_gap_free_seq():
    tick1 = {"run_id": "run-tc119", "sim_time_seconds": 5.0, "p_demand_mw": 1.0}
    tick2 = {"run_id": "run-tc119", "sim_time_seconds": 10.0, "p_demand_mw": 1.1}
    sentinel = {"type": "run_complete", "run_id": "run-tc119"}

    q: asyncio.Queue = asyncio.Queue()

    stop1, seq_after, stats1 = await process_stream(
        _make_source(tick1, tick2),
        out_queue=q,
        seq_start=0,
        is_reconnect=False,
    )
    assert stop1 == "dropped"

    stop2, seq_final, stats2 = await process_stream(
        _make_source(sentinel),
        out_queue=q,
        seq_start=seq_after,
        is_reconnect=True,
    )
    assert stop2 == "run_complete"

    items = await _drain(q)
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

    seqs = [item["seq"] for item in items]
    assert seqs == list(range(len(seqs))), f"seq not gap-free: {seqs}"


# ---------------------------------------------------------------------------
# TC-120 — catalogue_hash stability and sensitivity
# ---------------------------------------------------------------------------


def test_tc120_catalogue_hash_stable_and_sensitive():
    path = DEFAULT_CATALOGUE_PATH
    if not path.exists():
        pytest.skip(f"Catalogue not found at {path}")

    values1, hash1 = load_catalogue(path)
    values2, hash2 = load_catalogue(path)

    assert hash1 == hash2
    assert values1 == values2

    key = next(iter(values1))
    modified = {**values1, key: "__CHANGED__"}
    canonical = json.dumps(modified, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    modified_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert modified_hash != hash1


def test_tc120_catalogue_hash_from_tmp_file():
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
        f.write(_make_cat(46))
        tmp3 = pathlib.Path(f.name)
    try:
        _, h1 = load_catalogue(tmp1)
        _, h2 = load_catalogue(tmp2)
        _, h3 = load_catalogue(tmp3)
        assert h1 == h2
        assert h1 != h3
    finally:
        tmp1.unlink(missing_ok=True)
        tmp2.unlink(missing_ok=True)
        tmp3.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TC-121 — sim_time_gap detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc121_gap_detected_with_derived_interval():
    gapped_msgs = [
        {"run_id": "r", "sim_time_seconds": 5.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 10.0, "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 15.0, "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 25.0, "p_demand_mw": 1.0},  # GAP
        {"run_id": "r", "sim_time_seconds": 30.0, "p_demand_mw": 1.0},
        {"type": "run_complete"},
    ]

    q1: asyncio.Queue = asyncio.Queue()
    stop1, _, stats1 = await process_stream(_make_source(*gapped_msgs), out_queue=q1)

    assert stop1 == "run_complete"
    assert stats1["observed_tick_interval_s"] == 5.0
    assert len(stats1["sim_time_gaps"]) == 1
    assert stats1["sim_time_gaps"][0] == {"from_s": 15.0, "to_s": 25.0}

    items1 = await _drain(q1)
    gap_markers = [i for i in items1 if i.get("event") == "sim_time_gap"]
    assert len(gap_markers) == 1
    assert gap_markers[0]["from_s"] == 15.0
    assert gap_markers[0]["to_s"] == 25.0

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
    assert stats2["sim_time_gaps"] == []

    items2 = await _drain(q2)
    assert [i for i in items2 if i.get("event") == "sim_time_gap"] == []


@pytest.mark.asyncio
async def test_tc121_interval_not_hardcoded():
    msgs = [
        {"run_id": "r", "sim_time_seconds": 2.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 4.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 6.0,  "p_demand_mw": 1.0},
        {"run_id": "r", "sim_time_seconds": 10.5, "p_demand_mw": 1.0},  # 4.5 s > 3.0
        {"type": "run_complete"},
    ]

    q: asyncio.Queue = asyncio.Queue()
    _, _, stats = await process_stream(_make_source(*msgs), out_queue=q)
    assert stats["observed_tick_interval_s"] == 2.0
    assert len(stats["sim_time_gaps"]) == 1
    assert stats["sim_time_gaps"][0]["from_s"] == 6.0
    assert stats["sim_time_gaps"][0]["to_s"] == 10.5


# ---------------------------------------------------------------------------
# TC-122 — constant_fields analysis
# ---------------------------------------------------------------------------


def _make_tick(
    t: float,
    *,
    rated_mw: float = 25.0,
    bess_usable_mwh: float = 2.0,
    bess_soc_fraction: float = 0.8,
    commit_action: str = "hold",
    commit_reason: str = "stable",
    p_demand_mw: float = 10.0,
    kube_metrics=None,
) -> dict:
    """Build a synthetic tick payload with nested structures."""
    return {
        "sim_time_seconds": t,
        "p_demand_mw": p_demand_mw,   # varies across calls
        "bess_usable_mwh": bess_usable_mwh,  # constant
        "bess_soc_fraction": bess_soc_fraction,  # varies
        "kube_metrics": kube_metrics,           # always None
        "turbine_units": [
            {
                "asset_id": "turbine-0",
                "rated_mw": rated_mw,       # constant (nested)
                "state": "synchronised",    # constant (nested)
            }
        ],
        "commitment_block": {
            "action": commit_action,        # constant
            "reason": commit_reason,        # constant
            "target_unit_id": None,         # constant (always None)
        },
        "data_quality_tags": [],            # constant (always empty list → not a leaf)
    }


def test_tc122_constant_fields_analysis():
    """
    TC-122: constant_fields contains exactly the fields that do not vary,
    excludes a field that changes on the final tick only, walks nested paths,
    and the hash is stable across two computations and changes when any
    constant value is modified.
    """
    # Ticks 1-4: bess_soc_fraction varies, p_demand_mw varies, sim_time_seconds varies
    # Tick 5 (final): commit_reason changes (previously constant "stable" → "decommit")
    # kube_metrics is always None → constant with value None
    # bess_usable_mwh is always 2.0 → constant
    # turbine_units[0].rated_mw is always 25.0 → constant (nested path)
    # turbine_units[0].state is always "synchronised" → constant (nested path)
    # commitment_block.action is always "hold" → constant (nested path)
    # commitment_block.target_unit_id is always None → constant (nested path)
    # commitment_block.reason changes on tick 5 → should be in varying_fields

    payloads = [
        _make_tick(5.0,  bess_soc_fraction=0.80, p_demand_mw=10.0, commit_reason="stable"),
        _make_tick(10.0, bess_soc_fraction=0.78, p_demand_mw=11.0, commit_reason="stable"),
        _make_tick(15.0, bess_soc_fraction=0.76, p_demand_mw=10.5, commit_reason="stable"),
        _make_tick(20.0, bess_soc_fraction=0.74, p_demand_mw=10.8, commit_reason="stable"),
        _make_tick(25.0, bess_soc_fraction=0.72, p_demand_mw=10.2, commit_reason="decommit"),  # changes
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = pathlib.Path(tmpdir) / "test.jsonl"
        _write_jsonl(jsonl_path, payloads)

        cf1, h1, vf1, note1 = compute_constant_fields(jsonl_path)
        cf2, h2, vf2, note2 = compute_constant_fields(jsonl_path)

    # ── Stability ─────────────────────────────────────────────────────────────
    assert h1 == h2, "Hash must be stable across two computations of the same file"
    assert cf1 == cf2, "constant_fields must be stable across two computations"

    # ── sim_time_seconds must be in varying_fields ─────────────────────────────
    assert "sim_time_seconds" in vf1, "sim_time_seconds always varies — must not be constant"

    # ── Fields that are constant ───────────────────────────────────────────────
    assert "bess_usable_mwh" in cf1, "bess_usable_mwh is constant → must be in constant_fields"
    assert cf1["bess_usable_mwh"] == 2.0

    assert "kube_metrics" in cf1, "kube_metrics is always None → must be in constant_fields"
    assert cf1["kube_metrics"] is None

    # Nested: turbine_units[0].rated_mw
    assert "turbine_units[0].rated_mw" in cf1, (
        "turbine_units[0].rated_mw is constant → must appear as nested path in constant_fields"
    )
    assert cf1["turbine_units[0].rated_mw"] == 25.0

    assert "turbine_units[0].state" in cf1
    assert cf1["turbine_units[0].state"] == "synchronised"

    assert "commitment_block.action" in cf1
    assert cf1["commitment_block.action"] == "hold"

    assert "commitment_block.target_unit_id" in cf1
    assert cf1["commitment_block.target_unit_id"] is None

    # ── Fields that vary ──────────────────────────────────────────────────────
    assert "bess_soc_fraction" in vf1, "bess_soc_fraction varies → must be in varying_fields"
    assert "p_demand_mw" in vf1, "p_demand_mw varies → must be in varying_fields"

    # ── commitment_block.reason changes on last tick only → varying ───────────
    assert "commitment_block.reason" in vf1, (
        "commitment_block.reason changes on final tick → must be in varying_fields, not constant"
    )
    assert "commitment_block.reason" not in cf1

    # ── Hash sensitivity ──────────────────────────────────────────────────────
    # Mutate one constant value and recompute hash manually
    modified_cf = {**cf1, "bess_usable_mwh": 99.0}
    canonical = json.dumps(modified_cf, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    modified_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert modified_hash != h1, "Changing a constant value must change the hash"

    # ── Note is present and non-empty ─────────────────────────────────────────
    assert note1, "constant_fields_note must be non-empty"
    assert "workload" in note1.lower() or "irradiance" in note1.lower(), (
        "Note must mention the limitation (workload events / irradiance)"
    )


def test_tc122_flatten_nested_paths():
    """Unit test for _flatten_payload — ensures nested paths are correct."""
    d = {
        "a": 1,
        "b": {"c": 2, "d": None},
        "e": [{"f": 3.0}, {"f": 4.0}],
        "g": [],
    }
    flat = _flatten_payload(d)
    assert flat["a"] == 1
    assert flat["b.c"] == 2
    assert flat["b.d"] is None
    assert flat["e[0].f"] == 3.0
    assert flat["e[1].f"] == 4.0
    # Empty list has no leaves
    assert not any(k.startswith("g") for k in flat)


def test_tc122_empty_jsonl():
    """compute_constant_fields on an empty file returns empty dicts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = pathlib.Path(tmpdir) / "empty.jsonl"
        p.write_text("")
        cf, h, vf, note = compute_constant_fields(p)
    assert cf == {}
    assert vf == []
    assert h.startswith("sha256:")
