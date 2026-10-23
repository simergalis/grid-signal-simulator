"""Tests for the S10 scenario generator (DR-2026-10-19-SUPERCLOUD-INGEST §10).

Synthetic fixtures only.  Run from the repository root:
    python3 -m pytest tools/supercloud/test_make_scenario.py -q
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_scenario as ms  # noqa: E402
from test_convert_to_kube_trace import _row  # noqa: E402  (shared synthetic row builder)

DAY = date(2021, 8, 11)
D0 = int(datetime(2021, 8, 11, tzinfo=timezone.utc).timestamp())
TEMPLATE = {
    "name": "template", "hardware_profile_id": "enterprise_8gpu_air",
    "turbine_units": [{"asset_id": "gt-1", "rated_mw": 15.0}],
    "bess_units": [{"asset_id": "bess-0", "rated_mw": 18.0}],
    "kube_config": {"max_nodes": 1000}, "load_config": {"x": 1},
    "workload_floor_fraction": 0.5, "solar_rated_mw": 15.0,
    "gpu_load_profile": [[0.0, 0.5]], "assertions": [{"check": "max_p_total_mw"}],
    "workload_events": [{"job_id": "synthetic"}], "tenant_events": [{"t": 1}],
}


def _rows():
    return [
        _row(1, gpus=2, submit=D0 + 100, start=D0 + 200, end=D0 + 800),            # inside day
        _row(2, gpus=2, nodes=("gpu-b",), submit=D0 - 900, start=D0 - 500, end=D0 + 300),  # running at 00:00
        _row(3, gpus=1, nodes=("gpu-c",), submit=D0 + 80_000, start=D0 + 86_000, end=D0 + 90_000),  # past midnight
        _row(4, gpus=0, submit=D0 + 100),                                           # CPU-only: excluded
        _row(5, gpus=2, part="xeon-p8", submit=D0 + 100),                           # wrong partition
        _row(6, gpus=2, submit=D0 - 9000, start=D0 - 8000, end=D0 - 7000),          # previous day
        _row(7, gpus=4, nodes=("g1", "g2"), cpus=40, submit=D0 + 250, start=D0 + 250, end=D0 + 400),  # multi-node gang: kept
    ]


def test_selects_overlapping_gpu_jobs_with_real_times():
    jobs, skipped = ms.gpu_jobs_for_day(_rows(), DAY)
    assert skipped == {}
    assert [(j.start_s, j.end_s, j.gpus) for j in jobs] == [
        (0.0, 300.0, 2), (200.0, 800.0, 2), (250.0, 400.0, 4), (86_000.0, None, 1),
    ]
    assert sum(j.started_before_window for j in jobs) == 1


def test_peak_concurrency_ends_before_starts():
    assert ms.peak_concurrency([(0, 10, 5), (10, 20, 5)]) == 5
    assert ms.peak_concurrency([(0, 10, 5), (5, None, 3)]) == 8


def test_scaling_hits_target_peak_and_neutralises_synthetic_load():
    jobs, _ = ms.gpu_jobs_for_day(_rows(), DAY)
    spec, report = ms.build_scenario(jobs, TEMPLATE, day=DAY, peak_mw=50.0, rated_kw=10.2)
    # Peak concurrent GPUs = 8 (jobs 1+2+7 overlap 250..300); 50 MW / 10.2 kW / 8.
    assert report["peak_concurrent_gpus"] == 8
    assert report["peak_compute_mw_after_rounding"] == pytest.approx(50.0, abs=0.05)
    for key in ("kube_config", "load_config", "workload_floor_fraction"):
        assert spec[key] is None
    assert spec["solar_rated_mw"] == 0.0 and spec["gpu_load_profile"] == []
    assert spec["assertions"] == [] and spec["tenant_events"] == []
    assert spec["end_sim_time"] == 86_400.0
    assert spec["turbine_units"] == TEMPLATE["turbine_units"]   # power side copied
    assert TEMPLATE["kube_config"] == {"max_nodes": 1000}       # template not mutated


def test_events_pair_up_and_carry_no_dataset_ids():
    jobs, _ = ms.gpu_jobs_for_day(_rows(), DAY)
    spec, _ = ms.build_scenario(jobs, TEMPLATE, day=DAY, peak_mw=50.0, rated_kw=10.2)
    events = spec["workload_events"]
    starts = {e["job_id"] for e in events if e["event_type"] == "starting"}
    ends = {e["job_id"] for e in events if e["event_type"] == "job_end"}
    assert len(starts) == 4 and len(ends) == 3              # job past midnight has no end
    assert ends <= starts
    assert all(e["job_id"].startswith("s10-job-") for e in events)
    assert [e["timestamp"] for e in events] == sorted(e["timestamp"] for e in events)
    assert all(e["node_count"] >= 1 for e in events if e["event_type"] == "starting")


def test_empty_day_is_an_error():
    with pytest.raises(ValueError):
        ms.build_scenario([], TEMPLATE, day=DAY, peak_mw=50.0, rated_kw=10.2)
