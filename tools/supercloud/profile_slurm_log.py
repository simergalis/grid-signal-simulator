#!/usr/bin/env python3
"""Profile MIT SuperCloud Slurm accounting CSVs before any converter is built.

Purpose (DR-2026-10-19-SUPERCLOUD-INGEST, Gate 1):
    The column NAMES of slurm-log.csv are known from MIT's own intro notebook
    (a printout of the real file).  The VALUE ENCODINGS are not documented.
    This script tests each encoding hypothesis (H1..H9) against the real data
    and reports PASS / FAIL / INCONCLUSIVE with evidence, so the converter is
    written against observed values rather than assumptions.

Usage:
    python3 tools/supercloud/profile_slurm_log.py slurm-log.csv \
        [--labelled labelled-slurm-log.csv] [--tres-mapping tres-mapping.txt] \
        [--out-dir reports/supercloud-profile] [--limit N]

Stdlib only; streams rows, so the full 460K-row file is fine.

Data licence note: the dataset is CC BY-NC-ND 4.0 (AWS Open Data registry).
Do not commit the raw CSVs or row-level extracts to this repository.  The
profile report contains only aggregates and up to 5 sample values per column.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Column list observed in MIT-AI-Accelerator/MIT-Supercloud-Dataset,
# notebooks/Intro-to-MIT-Supercloud-Dataset.ipynb (printed output of
# scheduler_log_df.columns on the real file).
EXPECTED_COLUMNS = (
    "id_job", "id_array_job", "id_array_task", "id_user", "kill_requid",
    "nodes_alloc", "nodelist", "cpus_req", "derived_ec", "exit_code",
    "gres_used", "array_max_tasks", "array_task_pending", "constraints",
    "flags", "mem_req", "partition", "priority", "state", "timelimit",
    "time_submit", "time_eligible", "time_start", "time_end",
    "time_suspended", "track_steps", "tres_alloc", "tres_req", "job_type",
)

TIME_COLUMNS = ("time_submit", "time_eligible", "time_start", "time_end")

# Hypothesis thresholds.  These are profiling heuristics, not model constants.
EPOCH_S_MIN = 946_684_800      # 2000-01-01 UTC
EPOCH_S_MAX = 2_000_000_000    # 2033-05-18 UTC
MEM_PER_CPU_FLAG = 1 << 63     # slurmdbd MEM_PER_CPU bit (hypothesis H4)
TRES_PAIR_RE = re.compile(r"^\d+=\d+$")
SAMPLE_N = 5
NUMERIC_SAMPLE_CAP = 200_000   # cap stored values per column for quantiles

# slurmdbd job_state base enum (low byte), hypothesis H5.
SLURMDB_STATE = {
    0: "PENDING", 1: "RUNNING", 2: "SUSPENDED", 3: "COMPLETED",
    4: "CANCELLED", 5: "FAILED", 6: "TIMEOUT", 7: "NODE_FAIL",
    8: "PREEMPTED", 9: "BOOT_FAIL", 10: "DEADLINE", 11: "OUT_OF_MEMORY",
}


def _as_int(raw: str) -> int | None:
    raw = raw.strip()
    if raw == "" or raw.lower() in {"nan", "none", "null"}:
        return None
    try:
        return int(raw)
    except ValueError:
        try:
            f = float(raw)
        except ValueError:
            return None
        return int(f) if math.isfinite(f) and f.is_integer() else None


def _quantiles(values: list[int]) -> dict[str, Any]:
    if not values:
        return {}
    v = sorted(values)
    pick = lambda q: v[min(len(v) - 1, int(q * (len(v) - 1)))]
    return {"min": v[0], "p01": pick(0.01), "p50": pick(0.5), "p99": pick(0.99), "max": v[-1]}


class ColumnStats:
    def __init__(self) -> None:
        self.blank = 0
        self.numeric = 0
        self.non_numeric = 0
        self.samples: list[str] = []
        self.distinct: Counter[str] = Counter()
        self.distinct_overflow = False
        self.values: list[int] = []

    def add(self, raw: str) -> None:
        if raw.strip() == "" or raw.strip().lower() in {"nan", "none", "null"}:
            self.blank += 1
            return
        if len(self.samples) < SAMPLE_N and raw not in self.samples:
            self.samples.append(raw)
        if not self.distinct_overflow:
            self.distinct[raw] += 1
            if len(self.distinct) > 5000:
                self.distinct_overflow = True
                self.distinct.clear()
        n = _as_int(raw)
        if n is None:
            self.non_numeric += 1
        else:
            self.numeric += 1
            if len(self.values) < NUMERIC_SAMPLE_CAP:
                self.values.append(n)

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "blank": self.blank, "numeric": self.numeric,
            "non_numeric": self.non_numeric, "samples": self.samples,
            "distinct": ">5000" if self.distinct_overflow else len(self.distinct),
        }
        if not self.distinct_overflow and 0 < len(self.distinct) <= 25:
            out["value_counts"] = dict(self.distinct.most_common())
        if self.values:
            out["quantiles"] = _quantiles(self.values)
        return out


def _verdict(passed: bool | None, evidence: str) -> dict[str, Any]:
    status = "INCONCLUSIVE" if passed is None else ("PASS" if passed else "FAIL")
    return {"status": status, "evidence": evidence}


def profile(path: Path, limit: int | None) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        stats = {c: ColumnStats() for c in header}
        rows = 0
        # Cross-column checks.
        time_order_violations = 0
        start_zero = 0
        start_zero_states: Counter[str] = Counter()
        tres_req_bad = 0
        tres_ids: Counter[int] = Counter()
        tres_alloc_ids: Counter[int] = Counter()
        mem_flagged = 0
        id_job_seen: set[str] = set()
        id_job_dupes = 0
        gpu_jobs = 0
        tl_pairs: list[tuple[int, int]] = []  # (runtime_s, timelimit) for COMPLETED
        for row in reader:
            rows += 1
            for c in header:
                stats[c].add(row.get(c) or "")
            # H1/H7: time ordering on rows where all four are populated & > 0
            t = {c: _as_int(row.get(c, "")) for c in TIME_COLUMNS if c in row}
            if t.get("time_start") == 0:
                start_zero += 1
                start_zero_states[row.get("state", "")] += 1
            if all(t.get(c) for c in TIME_COLUMNS):
                if not (t["time_submit"] <= t["time_eligible"] <= t["time_start"] <= t["time_end"]):
                    time_order_violations += 1
            # H3 evidence: runtime vs timelimit for COMPLETED jobs
            st_i = _as_int(row.get("state", ""))
            tl_i = _as_int(row.get("timelimit", ""))
            if (st_i is not None and (st_i & 0xFF) == 3 and tl_i and tl_i > 0
                    and t.get("time_start") and t.get("time_end")
                    and len(tl_pairs) < NUMERIC_SAMPLE_CAP):
                tl_pairs.append((t["time_end"] - t["time_start"], tl_i))
            # H2: tres_req format id=count,id=count
            tr = (row.get("tres_req") or "").strip()
            if tr:
                parts = tr.split(",")
                if all(TRES_PAIR_RE.match(p.strip()) for p in parts):
                    ids = {int(p.split("=")[0]) for p in parts}
                    tres_ids.update(ids)
                    if ids & {1001, 1002}:
                        gpu_jobs += 1
                else:
                    tres_req_bad += 1
            ta = (row.get("tres_alloc") or "").strip()
            if ta and all(TRES_PAIR_RE.match(p.strip()) for p in ta.split(",")):
                tres_alloc_ids.update(int(p.split("=")[0]) for p in ta.split(","))
            # H4: MEM_PER_CPU flag bit
            m = _as_int(row.get("mem_req", ""))
            if m is not None and m >= MEM_PER_CPU_FLAG:
                mem_flagged += 1
            # H8: id_job uniqueness
            jid = row.get("id_job", "")
            if jid in id_job_seen:
                id_job_dupes += 1
            else:
                id_job_seen.add(jid)
            if limit and rows >= limit:
                break

    cols = {c: stats[c].summary() for c in header}
    missing = [c for c in EXPECTED_COLUMNS if c not in header]
    extra = [c for c in header if c not in EXPECTED_COLUMNS]

    hyp: dict[str, Any] = {}
    hyp["H0_header_matches_notebook"] = _verdict(
        not missing and not extra,
        f"missing={missing} extra={extra}",
    )
    # H1: time_* are Unix epoch seconds.
    in_range, total = 0, 0
    for c in TIME_COLUMNS:
        for v in stats.get(c, ColumnStats()).values:
            if v == 0:
                continue
            total += 1
            in_range += EPOCH_S_MIN <= v <= EPOCH_S_MAX
    hyp["H1_times_epoch_seconds"] = _verdict(
        None if total == 0 else in_range / total > 0.999,
        f"{in_range}/{total} non-zero time values within 2000..2033 as epoch seconds; "
        f"time_start==0 rows={start_zero} by state={dict(start_zero_states.most_common(10))}",
    )
    # H2: tres_req is "id=count,..." with ids from tres-mapping.txt.
    hyp["H2_tres_req_id_eq_count"] = _verdict(
        None if not cols.get("tres_req") else tres_req_bad == 0,
        f"malformed={tres_req_bad}; ids seen={dict(sorted(tres_ids.items()))}; "
        f"rows with 1001/1002 (GPU)={gpu_jobs} (README states 98,177 GPU jobs)",
    )
    hyp["H2b_tres_alloc_same_format"] = _verdict(
        None if not tres_alloc_ids else True,
        f"ids seen in tres_alloc={dict(sorted(tres_alloc_ids.items()))}",
    )
    # H3: timelimit is minutes (Slurm accounting convention).
    tl = cols.get("timelimit", {}).get("quantiles", {})
    if tl_pairs:
        n = len(tl_pairs)
        # Slurm enforces the limit with a small grace; allow 2 minutes slack.
        fit_min = sum(r <= (lim + 2) * 60 for r, lim in tl_pairs) / n
        fit_sec = sum(r <= lim + 120 for r, lim in tl_pairs) / n
        h3 = fit_min > 0.99 and fit_sec < fit_min - 0.05
        h3_ev = (f"COMPLETED jobs checked={n}; runtime within limit if minutes={fit_min:.4f}, "
                 f"if seconds={fit_sec:.4f}; timelimit quantiles={tl}")
    else:
        h3, h3_ev = None, f"no COMPLETED rows with times; timelimit quantiles={tl}"
    hyp["H3_timelimit_minutes"] = _verdict(h3, h3_ev)
    # H4: mem_req is MB with MEM_PER_CPU high-bit flag.
    hyp["H4_mem_req_mb_with_per_cpu_flag"] = _verdict(
        None,
        f"rows with bit 63 set={mem_flagged}; quantiles={cols.get('mem_req', {}).get('quantiles')}. "
        "If flagged rows > 0, mem per job = (mem_req - 2^63) * cpus_req.",
    )
    # H5: state is numeric slurmdbd enum.
    st = cols.get("state", {})
    vc = st.get("value_counts", {})
    numeric_states = all(_as_int(k) is not None for k in vc) if vc else None
    mapped = {k: SLURMDB_STATE.get((_as_int(k) or 0) & 0xFF, "?") for k in vc} if numeric_states else {}
    hyp["H5_state_numeric_enum"] = _verdict(
        numeric_states,
        f"value_counts={vc}; low-byte mapping={mapped}" if vc else "no state column / too many distinct values",
    )
    hyp["H6_gres_used_format"] = _verdict(None, f"samples={cols.get('gres_used', {}).get('samples')}")
    hyp["H7_time_ordering"] = _verdict(
        time_order_violations == 0,
        f"rows violating submit<=eligible<=start<=end (all >0): {time_order_violations}",
    )
    hyp["H8_id_job_unique"] = _verdict(
        id_job_dupes == 0,
        f"duplicate id_job rows={id_job_dupes} (array jobs may legitimately repeat; see id_array_*)",
    )
    hyp["H9_nodes_alloc_vs_nodelist"] = _verdict(
        None,
        f"nodes_alloc quantiles={cols.get('nodes_alloc', {}).get('quantiles')}; "
        f"nodelist samples={cols.get('nodelist', {}).get('samples')}",
    )
    return {
        "file": str(path), "rows_profiled": rows, "limit": limit,
        "header": header, "hypotheses": hyp, "columns": cols,
    }


def compare_labelled(main: dict[str, Any], labelled: dict[str, Any]) -> dict[str, Any]:
    a, b = set(main["header"]), set(labelled["header"])
    return {
        "only_in_slurm_log": sorted(a - b),
        "only_in_labelled": sorted(b - a),
        "shared": len(a & b),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# SuperCloud Slurm log profile", ""]
    for key in ("slurm_log", "labelled_slurm_log"):
        rep = report.get(key)
        if not rep:
            continue
        lines += [f"## {key}: `{rep['file']}`", "", f"Rows profiled: {rep['rows_profiled']}", "",
                  "| Hypothesis | Status | Evidence |", "|---|---|---|"]
        for h, v in rep["hypotheses"].items():
            ev = str(v["evidence"]).replace("|", "\\|")
            lines.append(f"| {h} | **{v['status']}** | {ev} |")
        lines += ["", "| Column | blank | numeric | non-numeric | distinct | samples |",
                  "|---|---|---|---|---|---|"]
        for c, s in rep["columns"].items():
            smp = ", ".join(f"`{x}`" for x in s["samples"]).replace("|", "\\|")
            lines.append(f"| {c} | {s['blank']} | {s['numeric']} | {s['non_numeric']} | {s['distinct']} | {smp} |")
        lines.append("")
    if "header_diff" in report:
        lines += ["## Header diff (slurm-log vs labelled)", "", "```", json.dumps(report["header_diff"], indent=2), "```", ""]
    if "tres_mapping" in report:
        lines += ["## tres-mapping.txt", "", "```", report["tres_mapping"], "```", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slurm_log", type=Path)
    ap.add_argument("--labelled", type=Path)
    ap.add_argument("--tres-mapping", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("reports/supercloud-profile"))
    ap.add_argument("--limit", type=int, default=None, help="profile only the first N rows")
    args = ap.parse_args(argv)

    report: dict[str, Any] = {"slurm_log": profile(args.slurm_log, args.limit)}
    if args.labelled:
        report["labelled_slurm_log"] = profile(args.labelled, args.limit)
        report["header_diff"] = compare_labelled(report["slurm_log"], report["labelled_slurm_log"])
    if args.tres_mapping:
        report["tres_mapping"] = args.tres_mapping.read_text(encoding="utf-8").strip()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "profile.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (args.out_dir / "profile.md").write_text(render_markdown(report), encoding="utf-8")
    for key in ("slurm_log", "labelled_slurm_log"):
        if key in report:
            print(f"[{key}] rows={report[key]['rows_profiled']}")
            for h, v in report[key]["hypotheses"].items():
                print(f"  {v['status']:<12} {h}")
    print(f"wrote {args.out_dir/'profile.md'} and profile.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
