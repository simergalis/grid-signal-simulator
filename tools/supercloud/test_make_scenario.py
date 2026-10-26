"""Tests for the S10 scenario generator (DR-2026-10-19-SUPERCLOUD-INGEST §10).

Synthetic fixtures only.  Run from the repository root:
    python3 -m pytest tools/supercloud/test_make_scenario.py -q
"""

from __future__ import annotations

import copy
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


def test_cpu_only_load_counts_all_supported_partitions_and_not_gpu_rows():
    rows = [
        _row(2001, nodes=("cpu-n",), part="normal", cpus=4,
             start=D0 + 100, end=D0 + 200),
        _row(2002, nodes=("cpu-p8",), part="xeon-p8", cpus=8,
             start=D0 + 150, end=D0 + 250),
        _row(2003, nodes=("cpu-db",), part="db", cpus=2,
             start=D0 + 200, end=D0 + 300),
        _row(2004, nodes=("gpu-n",), part="normal", cpus=4, gpus=1,
             start=D0 + 100, end=D0 + 300),
    ]
    jobs, skipped = ms.cpu_only_jobs_for_day(rows, DAY)
    assert skipped == {}
    assert [(job.partition, job.allocated_cores) for job in jobs] == [
        ("normal", 4),
        ("xeon-p8", 8),
        ("db", 2),
    ]
    assert len(jobs) == 3  # the GPU row is not double-counted as CPU-only
    assert sum(
        job.allocated_cores * (job.end_s - job.start_s) / 3600
        for job in jobs
    ) == pytest.approx(14 / 36)


def test_cpu_profile_uses_gpu_scale_and_records_rate_labels():
    rows = [
        _row(2011, nodes=("cpu-n",), part="normal", cpus=4,
             start=D0 + 100, end=D0 + 200),
        _row(2012, nodes=("cpu-p8",), part="xeon-p8", cpus=8,
             start=D0 + 150, end=D0 + 250),
        _row(2013, nodes=("cpu-db",), part="db", cpus=2,
             start=D0 + 200, end=D0 + 300),
        _row(2014, nodes=("gpu-n",), part="normal", cpus=4, gpus=1,
             start=D0 + 100, end=D0 + 300),
    ]
    cpu_jobs, _ = ms.cpu_only_jobs_for_day(rows, DAY)
    gpu_jobs, _ = ms.gpu_jobs_for_day(rows, DAY)
    profile = ms.cpu_load_profile_mw(cpu_jobs, chassis_per_gpu=2.0)
    assert all(load_mw >= 0.0 for _, load_mw in profile)
    assert profile == [
        [0.0, 0.0],
        [100.0, pytest.approx(0.00006)],
        [150.0, pytest.approx(0.00017)],
        [200.0, pytest.approx(0.00014)],
        [250.0, pytest.approx(0.00003)],
        [300.0, pytest.approx(0.0)],
    ]
    base_spec, _ = ms.build_scenario(
        gpu_jobs,
        TEMPLATE,
        day=DAY,
        peak_mw=50.0,
        rated_kw=10.2,
    )
    spec, report = ms.build_scenario(
        gpu_jobs,
        TEMPLATE,
        day=DAY,
        peak_mw=50.0,
        rated_kw=10.2,
        cpu_jobs=cpu_jobs,
        gpu_partitions=("normal", "gaia", "test"),
        generator_commit="source-test-commit",
        input_sha256="a" * 64,
        template_name="demo-islanded-ramp.json",
    )
    assert spec["workload_events"] == base_spec["workload_events"]
    assert len([e for e in spec["workload_events"] if e["event_type"] == "starting"]) == 1
    assert spec["non_gpu_load_profile_mw"] == report["cpu_load_profile_mw"]
    assert report["invocation"]["generator_commit"] == "source-test-commit"
    assert report["invocation"]["input_sha256"] == "a" * 64
    assert report["cpu_watts_per_core"]["normal"]["status"] == "INFERRED"
    assert report["cpu_watts_per_core"]["db"]["status"] == "INFERRED"
    assert report["cpu_watts_per_core"]["xeon-p8"]["status"] == "CITED"


def test_derived_initial_soc_is_written_and_recorded_in_invocation():
    gpu_jobs, _ = ms.gpu_jobs_for_day(_rows(), DAY)
    cpu_jobs, _ = ms.cpu_only_jobs_for_day(
        [
            _row(2051, nodes=("cpu-n",), part="normal", cpus=4,
                 start=D0 + 100, end=D0 + 200),
        ],
        DAY,
    )
    derivation = {
        "curtailment_energy_mwh": 4.2,
        "usable_bess_mwh": 14.0,
        "minimum_soc_fraction": 0.0,
        "formula": "max(minimum_soc_fraction, 1 - energy / usable_mwh)",
    }
    spec, report = ms.build_scenario(
        gpu_jobs,
        TEMPLATE,
        day=DAY,
        peak_mw=50.0,
        rated_kw=10.2,
        cpu_jobs=cpu_jobs,
        initial_soc_fraction=0.7,
        soc_derivation=derivation,
    )
    assert spec["bess_units"][0]["initial_soc_fraction"] == 0.7
    assert report["initial_soc_fraction_override"] == 0.7
    assert report["soc_derivation"] == derivation
    assert report["invocation"]["initial_soc_by_bess"] == {"bess-0": 0.7}
    assert report["invocation"]["soc_derivation"] == derivation
    assert "PROPOSED_HERE" in spec["description"]
    assert "D6a.4" in spec["description"]

    with pytest.raises(ValueError, match=r"finite and in \[0, 1\]"):
        ms.build_scenario(
            gpu_jobs,
            TEMPLATE,
            day=DAY,
            peak_mw=50.0,
            rated_kw=10.2,
            initial_soc_fraction=1.01,
        )


def test_cpu_only_unknown_partition_fails_closed():
    rows = [
        _row(2021, nodes=("cpu-unknown",), part="unknown-partition", cpus=4,
             start=D0 + 100, end=D0 + 200),
    ]
    with pytest.raises(ValueError, match="unsupported partition"):
        ms.cpu_only_jobs_for_day(rows, DAY)


def test_tc_isl_60_fuel_model_is_explicit_opt_in_and_records_provenance():
    """TC-ISL-60 — D6-F generator option adds only fuel/cost accounting blocks."""
    jobs = [ms.GpuJob(start_s=0.0, end_s=300.0, gpus=2, started_before_window=False)]
    cpu_jobs = [ms.CpuJob(start_s=0.0, end_s=300.0, allocated_cores=4, partition="normal")]
    without_fuel, _ = ms.build_scenario(
        jobs,
        TEMPLATE,
        day=DAY,
        peak_mw=50.0,
        rated_kw=10.2,
        cpu_jobs=cpu_jobs,
        generator_commit="test-source-commit",
        input_sha256="test-input-hash",
        template_name="demo-islanded-ramp.json",
    )
    with_fuel, report = ms.build_scenario(
        jobs,
        TEMPLATE,
        day=DAY,
        peak_mw=50.0,
        rated_kw=10.2,
        cpu_jobs=cpu_jobs,
        generator_commit="test-source-commit",
        input_sha256="test-input-hash",
        template_name="demo-islanded-ramp.json",
        fuel_model="siemens-sgt-400-proxy",
    )
    assert "fuel" not in without_fuel["turbine_units"][0]
    assert "operating_cost_inputs" not in without_fuel
    assert with_fuel["turbine_units"][0]["fuel"]["heat_rate_basis"] == "LHV"
    assert with_fuel["operating_cost_inputs"]["gas_price_basis"] == "HHV"
    assert report["invocation"]["fuel_model"] == "siemens-sgt-400-proxy"
    assert report["invocation"]["generator_commit"] == "test-source-commit"
    assert report["invocation"]["input_sha256"] == "test-input-hash"
    assert report["invocation"]["gpu_partitions_status"].startswith("INFERRED")
    assert report["fuel_model"]["option"] == "siemens-sgt-400-proxy"
    assert report["fuel_model"]["full_load_conversion"]["converted_btu_per_kwh"] == pytest.approx(
        9575.795151
    )
    assert with_fuel["workload_events"] == without_fuel["workload_events"]
    assert with_fuel["turbine_units"][0]["rated_mw"] == without_fuel["turbine_units"][0]["rated_mw"]


def test_tc_isl_95_s10_submit_times_use_source_time_submit_only():
    """TC-ISL-95 — D6 stage 2 adds submit_time_s without changing other scenario fields."""
    starts = [100, 527, 900, 1500, 3000, 7000, 9569, 12000, 16771]
    submits = [0, -3428, 300, 400, 500, 600, 9569, 800, 13812]
    rows = [
        _row(
            i + 1,
            gpus=1,
            submit=D0 + submits[i],
            start=D0 + starts[i],
            end=D0 + starts[i] + 100,
        )
        for i in range(len(starts))
    ]
    jobs, skipped = ms.gpu_jobs_for_day(rows, DAY)
    assert skipped == {}
    regenerated, _ = ms.build_scenario(jobs, TEMPLATE, day=DAY, peak_mw=50.0, rated_kw=10.2)

    existing = copy.deepcopy(regenerated)
    for event in existing["workload_events"]:
        if event["event_type"] == "starting":
            event.pop("submit_time_s")
    merged = ms.merge_submit_times_into_existing(existing, regenerated)
    starts_by_job = {
        event["job_id"]: event
        for event in merged["workload_events"]
        if event["event_type"] == "starting"
    }

    assert starts_by_job["s10-job-00002"]["submit_time_s"] == -3428.0
    assert starts_by_job["s10-job-00007"]["submit_time_s"] == starts_by_job["s10-job-00007"]["timestamp"]
    assert starts_by_job["s10-job-00009"]["submit_time_s"] == 13812.0
    assert merged == regenerated
