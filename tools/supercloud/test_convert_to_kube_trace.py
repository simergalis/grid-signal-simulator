"""Gate 3 acceptance tests for the SuperCloud -> kube_trace_replay converter.

TC-SC-01..05 from DR-2026-10-19-SUPERCLOUD-INGEST §6, plus unit tests for the
encodings confirmed at Gate 1.  Every fixture row is synthetic; no SuperCloud
data is used or committed.

Run from the repository root:
    python3 -m pytest tools/supercloud/test_convert_to_kube_trace.py -q
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SIM_ROOT = REPO / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SIM_ROOT))

import convert_to_kube_trace as conv  # noqa: E402
from runtime.kube_trace_replay import load_kube_trace, replay_kube_trace  # noqa: E402

COLUMNS = (
    "id_job,id_array_job,id_array_task,id_user,kill_requid,nodes_alloc,nodelist,"
    "cpus_req,derived_ec,exit_code,gres_used,array_max_tasks,array_task_pending,"
    "constraints,flags,mem_req,partition,priority,state,timelimit,time_submit,"
    "time_eligible,time_start,time_end,time_suspended,track_steps,tres_alloc,"
    "tres_req,job_type"
).split(",")
FLAG = 1 << 63
T0 = 1_610_000_000
NO_ARRAY = "4294967294"
INFINITE = "4294967295"


def _row(id_job, *, nodes=("gpu-a",), cpus=20, mem_req=None, part="normal", prio=10200,
         state=3, timelimit="720", submit=T0, eligible=None, start=None, end=None,
         gpus=0, gpu_id=1002, array_job="111", array_task=NO_ARRAY, tres_mem=None,
         tres_req=None, job_type="LLSUB:BATCH"):
    eligible = submit if eligible is None else eligible
    start = eligible + 60 if start is None else start
    end = start + 3600 if end is None else end
    mem_req = (FLAG + 8500) if mem_req is None else mem_req
    decoded = conv.decode_memory_mib(mem_req, cpus, len(nodes))
    tm = decoded if tres_mem is None else tres_mem
    gpu = f",{gpu_id}={gpus}" if gpus else ""
    tres = tres_req if tres_req is not None else f"1={cpus},2={tm},4={len(nodes)},5={cpus}{gpu}"
    alloc = f"1={cpus},2={tm},4={len(nodes)},5={cpus}{gpu}"
    return {
        "id_job": str(id_job), "id_array_job": array_job, "id_array_task": array_task,
        "id_user": "1", "kill_requid": "0", "nodes_alloc": str(len(nodes)),
        "nodelist": str(list(nodes)), "cpus_req": str(cpus), "derived_ec": "0",
        "exit_code": "0", "gres_used": "", "array_max_tasks": "0",
        "array_task_pending": "0", "constraints": "xeon-g6", "flags": "4",
        "mem_req": str(mem_req), "partition": part, "priority": str(prio),
        "state": str(state), "timelimit": timelimit, "time_submit": str(submit),
        "time_eligible": str(eligible), "time_start": str(start), "time_end": str(end),
        "time_suspended": "0", "track_steps": "0", "tres_alloc": alloc,
        "tres_req": tres, "job_type": job_type,
    }


def _fixture_rows():
    return [
        # 1 GPU job, per-CPU memory flag, 2 GPUs, labelled, with a dependency hold.
        _row(1001, gpus=2, mem_req=FLAG + 8500, cpus=20, submit=T0, eligible=T0 + 300),
        # 2 CPU job, flat per-node memory, INFINITE time limit.
        _row(1002, nodes=("cpu-a",), part="xeon-p8", cpus=48, mem_req=192000,
             timelimit=INFINITE),
        # 3 requeue flag in state -> quarantine.
        _row(1003, nodes=("gpu-q",), state=1024),
        # 4 multi-node GPU job -> quarantine, but its nodes still join the inventory.
        _row(1004, nodes=("gpu-b", "gpu-c"), gpus=4, cpus=40, mem_req=FLAG + 8500),
        # 5 array task.
        _row(1005, nodes=("cpu-a",), part="xeon-p8", cpus=4, array_job="777", array_task="3"),
        # 6 tesla GPU type -> quarantine.
        _row(1006, nodes=("gpu-q",), gpus=1, gpu_id=1001),
        # 7 4-GPU job on the one 4-GPU node -> kept (CAV-SC-7 resolved).
        _row(1007, nodes=("gpu-4",), part="test", gpus=4, cpus=8),
        # 8 memory decode disagrees with TRES -> quarantine.
        _row(1008, nodes=("gpu-q",), mem_req=64000, tres_mem=99999),
        # 9 malformed TRES -> parse-level quarantine (never in scope).
        _row(1009, tres_req="garbage"),
        # 10 second GPU job on gpu-a, overlapping job 1 (concurrency peak).
        _row(1010, gpus=0, cpus=20, start=T0 + 400, end=T0 + 2000),
    ]


@pytest.fixture()
def converted(tmp_path):
    src = tmp_path / "slurm-log.csv"
    with src.open("w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        w.writerows(_fixture_rows())
    labels = tmp_path / "labelled_jobids.csv"
    labels.write_text("id_job,model\n1001,resnet50\n1004,U3-64\n", encoding="utf-8")
    out = tmp_path / "out"
    summary = conv.convert(src, out, labels_path=labels)
    pods = {r["pod_id"]: r for r in csv.DictReader((out / "pods.csv").open())}
    nodes = {r["node_id"]: r for r in csv.DictReader((out / "nodes.csv").open())}
    quarantine = list(csv.DictReader((out / "quarantine.csv").open()))
    return summary, pods, nodes, quarantine, out


# --- Encoding unit tests -----------------------------------------------------

def test_memory_decode_per_cpu_flag():
    assert conv.decode_memory_mib(FLAG + 8500, 20, 1) == 170_000


def test_memory_decode_flat_is_per_node():
    assert conv.decode_memory_mib(65536, 80, 2) == 131_072


def test_parse_tres_and_nodelist():
    assert conv.parse_tres("1=20,2=170000,4=1,5=20,1002=2", "t") == {1: 20, 2: 170000, 4: 1, 5: 20, 1002: 2}
    with pytest.raises(conv.Quarantine):
        conv.parse_tres("1=20,bad", "t")
    assert conv.parse_nodelist("['r1-n1', 'r2-n2']") == ("r1-n1", "r2-n2")


# --- TC-SC-01 -----------------------------------------------------------------

def test_tc_sc_01_output_loads_through_existing_replay_loader(converted):
    _summary, _pods, _nodes, _q, out = converted
    dataset = load_kube_trace(out / "nodes.csv", out / "pods.csv")
    assert dataset.parser_report()["quarantined_rows"] == 0
    report = replay_kube_trace(dataset)
    assert report["replay"]["pod_count"] == len(dataset.pods)


# --- TC-SC-02 -----------------------------------------------------------------

def test_tc_sc_02_accounting_and_enumerated_reasons(converted):
    summary, pods, _nodes, quarantine, _out = converted
    assert summary["source_rows"] == 10
    assert summary["in_scope_rows"] == 9            # malformed TRES never enters scope
    assert summary["pods_emitted"] == len(pods) == 5
    assert summary["quarantine_by_reason"] == {
        "malformed_tres": 1, "state_flag_bits": 1, "multi_node": 1,
        "gpu_type_tesla_ambiguous": 1, "memory_decode_mismatch": 1,
    }
    assert summary["quarantined"] == len(quarantine) == 5


# --- TC-SC-03 -----------------------------------------------------------------

def test_tc_sc_03_gpu_rows_reconcile(converted):
    summary, pods, _nodes, _q, _out = converted
    gpu_source_rows_in_scope = 4                     # 1001, 1004, 1006, 1007
    gpu_quarantined = sum(summary["gpu_quarantine_by_reason"].values())
    assert summary["gpu_pods_emitted"] == gpu_source_rows_in_scope - gpu_quarantined == 2
    assert {p for p, r in pods.items() if int(r["num_gpu"])} == {"sc-1001", "sc-1007"}


# --- TC-SC-04 -----------------------------------------------------------------

def test_tc_sc_04_field_mapping(converted):
    _summary, pods, _nodes, _q, _out = converted
    gpu = pods["sc-1001"]
    assert gpu["memory_mib"] == "170000"            # per-CPU flag decoded
    assert gpu["cpu_milli"] == "20000"
    assert (gpu["num_gpu"], gpu["gpu_milli"], gpu["gpu_spec"]) == ("2", "2000", "V100")
    assert gpu["creation_time"] == str(T0 + 300)     # time_eligible, not time_submit
    assert gpu["scheduled_time"] == str(T0 + 360)
    assert gpu["node_id"] == "gpu-a"                 # list syntax stripped
    assert gpu["qos"] == "10200"
    assert gpu["dnn_model"] == "resnet50"
    assert gpu["workload_id"] == "sc-1001"
    cpu = pods["sc-1002"]
    assert cpu["memory_mib"] == "192000"             # flat per-node memory
    assert cpu["timelimit_min"] == ""                # INFINITE -> null
    assert cpu["gpu_spec"] == ""
    assert pods["sc-1005"]["workload_id"] == "sc-arr-777"
    assert pods["sc-1007"]["num_gpu"] == "4"         # fits the 4-GPU node


def test_tc_sc_04_node_inventory(converted):
    _summary, _pods, nodes, _q, _out = converted
    # gpu-a: jobs 1001 (20 cpu, 2 gpu) and 1010 (20 cpu) overlap -> peak 40 cpu.
    # Quarantined rows that ran on a node still count toward its capacity
    # (they occupied real hardware); the fixture puts them on gpu-q.
    assert nodes["gpu-a"]["cpu_milli"] == "40000"
    assert nodes["gpu-a"]["gpu_count"] == "2"
    assert nodes["gpu-a"]["model"] == "V100"
    # gpu-b/gpu-c appear only in a multi-node job: class capacity, no even split.
    assert nodes["gpu-b"]["cpu_milli"] == nodes["gpu-a"]["cpu_milli"]
    assert nodes["gpu-4"]["gpu_count"] == "4"
    assert nodes["cpu-a"]["model"] == "none"


def test_gpu_request_beyond_inventory_is_quarantined(tmp_path):
    src = tmp_path / "slurm-log.csv"
    with src.open("w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        w.writerows([_row(1, gpus=2), _row(2, nodes=("gpu-b",), gpus=8, start=T0 + 99999)])
    summary = conv.convert(src, tmp_path / "out")
    # gpu-b's own observed peak is 8, so the inventory grows to fit it: the
    # rule only fires for requests no derived node can hold.
    assert summary["quarantine_by_reason"] == {}


def test_window_keeps_overlapping_jobs_and_flags_in_window(tmp_path):
    src = tmp_path / "slurm-log.csv"
    with src.open("w", newline="") as fh:
        w = csv.DictWriter(fh, COLUMNS)
        w.writeheader()
        w.writerows([
            _row(1, submit=T0 - 5000, start=T0 - 4000, end=T0 + 100),  # running at window start
            _row(2, submit=T0 + 10),                                    # inside window
            _row(3, submit=T0 + 999_999),                               # after window
            _row(4, submit=T0 - 9000, start=T0 - 8000, end=T0 - 7000),  # finished before
        ])
    summary = conv.convert(src, tmp_path / "out", start=T0, end=T0 + 86_400)
    assert summary["out_of_scope"] == {"after_window": 1, "before_window": 1}
    assert summary["pods_emitted"] == 2
    assert summary["pods_in_window"] == 1


# --- TC-SC-05 -----------------------------------------------------------------

RAW_NAMES = {"slurm-log.csv", "scheduler-log.csv", "labelled-slurm-log.csv",
             "labelled_jobids.csv", "node-data.csv", "pods.csv", "nodes.csv",
             "quarantine.csv"}


def test_tc_sc_05_no_raw_supercloud_data_tracked():
    try:
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files"], check=True,
                                 capture_output=True, text=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    offenders = [p for p in tracked
                 if Path(p).name in RAW_NAMES
                 or (p.startswith(("tools/supercloud/", "reports/supercloud")) and p.endswith(".csv"))]
    assert offenders == []
    for report in (REPO / "reports").glob("supercloud*/**/*.json"):
        data = json.loads(report.read_text())
        assert "pods" not in data and "scheduler_events" not in data, report
