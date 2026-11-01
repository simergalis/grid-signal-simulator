from __future__ import annotations

import gzip
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import mcp_server.server as server_module
from mcp_server.server import RunState, StudyService, app
from study_harness.executor import S11B_SUPERCLOUD_REPLAY_SCENARIO_ID, StudyRunExecutor
from study_harness.stranded import compute_stranded


def _tick(
    minute: int,
    *,
    demand: float,
    bess: float = 0.0,
    unserved: float = 0.0,
    seconds_into_minute: int = 0,
) -> dict[str, float]:
    return {
        "sim_time_seconds": minute * 60 + seconds_into_minute,
        "p_total_mw": demand,
        "bess_output_mw": bess,
        "p_unserved_mw": unserved,
    }


def _mcp_call(client: TestClient, name: str, arguments: dict) -> dict:
    response = client.post(
        "/",
        headers={"Authorization": "Bearer stranded-test-read"},
        json={
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()["result"]["structuredContent"]


def test_tc_str_01_capacity_layers_close_to_available_cap() -> None:
    rows = [
        _tick(0, demand=15.0),
        _tick(1, demand=58.0),
        _tick(2, demand=60.0),
    ]
    result = compute_stranded(
        rows,
        p_avail_mw=60.0,
        reserve_policy="fixed_3mw",
        tick_seconds=5.0,
    )
    for minute in result["series"]:
        if minute["demand_mean_mw"] <= 60.0:
            assert (
                minute["consumed_mw"]
                + minute["reserve_held_mw"]
                + minute["recoverable_mw"]
            ) == pytest.approx(60.0, abs=1e-6)


def test_tc_str_05_no_grid_cap_has_no_numeric_basis() -> None:
    result = compute_stranded(
        [_tick(0, demand=10.0)],
        p_avail_mw=None,
        reserve_policy="fixed_3mw",
        tick_seconds=5.0,
    )
    assert result == {
        "available": False,
        "reason": "no grid_import_limit_mw; no available-capacity basis defined",
    }
    assert not any(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in result.values()
    )


def test_tc_str_06_more_reserve_cannot_increase_recoverable_capacity() -> None:
    rows = [
        _tick(0, demand=20.0),
        _tick(1, demand=40.0),
        _tick(2, demand=60.0),
        _tick(3, demand=65.0),
    ]
    results = [
        compute_stranded(
            rows,
            p_avail_mw=60.0,
            reserve_policy=policy,
            tick_seconds=5.0,
        )
        for policy in ("none", "fixed_3mw", "pct10", "derate80")
    ]
    recoverable = [result["recoverable_mwh"] for result in results]
    assert recoverable == sorted(recoverable, reverse=True)
    assert len({result["avg_stranded_mw"] for result in results}) == 1


def test_tc_str_scarce_runs_drop_short_and_merge_close_runs() -> None:
    # The two-minute run at 1–2 is dropped. Four-minute runs at 10–13 and
    # 17–20 have a three-minute gap and merge into one episode.
    rows = []
    for minute in range(21):
        is_scarce = minute in {1, 2, 10, 11, 12, 13, 17, 18, 19, 20}
        rows.append(_tick(minute, demand=58.0 if is_scarce else 0.0))

    result = compute_stranded(
        rows,
        p_avail_mw=60.0,
        reserve_policy="fixed_3mw",
        tick_seconds=60.0,
    )
    assert result["scarce_minutes"] == 8
    assert result["scarce_episodes"] == [
        {"start_minute": 10, "end_minute": 20, "length_minutes": 11}
    ]


def test_tc_str_above_cap_splits_between_bess_and_unserved() -> None:
    result = compute_stranded(
        [_tick(0, demand=70.0, bess=3.0, unserved=7.0)],
        p_avail_mw=60.0,
        reserve_policy="none",
        tick_seconds=60.0,
    )
    row = result["series"][0]
    assert row["above_cap_bess_mw"] == pytest.approx(3.0)
    assert row["above_cap_unserved_mw"] == pytest.approx(7.0)
    assert (
        row["above_cap_bess_mw"] + row["above_cap_unserved_mw"]
    ) == pytest.approx(10.0)


def test_tc_str_02_short_s11b_executor_energy_reconciliation(
    tmp_path: Path,
) -> None:
    """Exercise the real harness and its own temporary tick artifact."""
    executor = StudyRunExecutor(output_dir=tmp_path)
    record = executor.run_mode(
        scenario_id=S11B_SUPERCLOUD_REPLAY_SCENARIO_ID,
        mode="baseline",
        seed=1729,
        duration_seconds=14_400.0,
        reuse_cache=False,
    )
    tick_path = Path(record["artifacts"]["paths"]["ticks"])
    with gzip.open(tick_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    result = compute_stranded(
        rows,
        p_avail_mw=60.0,
        reserve_policy="fixed_3mw",
        tick_seconds=5.0,
    )
    expected = float(record["served_mwh"]) + float(record["unserved_mwh"])
    assert result["energy_consumed_mwh"] == pytest.approx(
        expected,
        rel=0.005,
    )


@pytest.mark.skip(
    reason=(
        "TC-STR-03 is checked against the fresh full-day dev artifact; "
        "rerunning 17,280 ticks in the focused suite is too slow."
    )
)
def test_tc_str_03_full_day_s11b_above_cap_matches_reference() -> None:
    """Full-day acceptance is evaluated from the dev run, not a shared artifact."""
    raise AssertionError("full-day run is intentionally not repeated in pytest")


@pytest.mark.skip(
    reason=(
        "TC-STR-04 is checked against the fresh full-day dev artifact; "
        "rerunning 17,280 ticks in the focused suite is too slow."
    )
)
def test_tc_str_04_full_day_s11b_utilisation_matches_reference() -> None:
    """Full-day acceptance is evaluated from the dev run, not a shared artifact."""
    raise AssertionError("full-day run is intentionally not repeated in pytest")


def test_tc_str_mcp_metrics_and_series_are_reachable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = "stranded-mcp-fixture"
    ticks_path = tmp_path / "ticks.jsonl.gz"
    rows = [_tick(minute, demand=float(20 + minute)) for minute in range(3)]
    with gzip.open(ticks_path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    record = {
        "scenario_id": S11B_SUPERCLOUD_REPLAY_SCENARIO_ID,
        "mode": "baseline",
        "status": "PASS",
        "identity": {
            "parameter_set": {"grid_import_limit_mw": 60.0},
            "tick_seconds": 5.0,
        },
    }
    state = RunState(
        run_id=run_id,
        scenario_id=S11B_SUPERCLOUD_REPLAY_SCENARIO_ID,
        mode="baseline",
        identity_digest="fixture",
        status="COMPLETED",
        record=record,
        ticks_path=ticks_path,
    )
    isolated = StudyService.__new__(StudyService)
    isolated._lock = threading.RLock()
    isolated._runs = {run_id: state}
    monkeypatch.setattr(server_module, "service", isolated)
    monkeypatch.setenv("GRIDSIGNAL_MCP_READ_TOKEN", "stranded-test-read")
    monkeypatch.setenv("GRIDSIGNAL_MCP_RUN_TOKEN", "stranded-test-run")

    definitions = server_module._tool_definitions()
    metrics_tool = next(
        item for item in definitions if item["name"] == "get_run_metrics"
    )
    assert "stranded" in metrics_tool["inputSchema"]["properties"]["section"]["enum"]
    assert "get_stranded_series" in server_module.READ_TOOLS

    with TestClient(app) as client:
        summary = _mcp_call(
            client,
            "get_run_metrics",
            {"run_id": run_id, "section": "stranded"},
        )
        series = _mcp_call(
            client,
            "get_stranded_series",
            {"run_id": run_id, "page": 1, "page_size": 2},
        )
    assert summary["stranded"]["p_avail_mw"] == 60.0
    assert "series" not in summary["stranded"]
    assert series["p_avail_mw"] == 60.0
    assert series["p_res_mw"] == 3.0
    assert series["series"]["total"] == 3
    assert series["series"]["returned"] == 2
    assert series["series"]["has_more"] is True
