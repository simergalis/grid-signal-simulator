"""Report generation: markdown plus a per-record JSONL."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .checkers import TickCtx, run_all
from .contracts import (EVALUATED, ONE_SIDED, UNIT_ASSUMPTIONS,
                        ResidualRecord)
from .load import Recording, constant_fields, load_recording, preflight
from .stats import distribution, shape_by_subject

INVARIANT_NOTES = {
    "I1": "Power balance: p_generation_mw + grid_exchange_mw - p_demand_mw. "
          "Carries the whole load-service question, since I3 cannot (see below).",
    "I1d": "Independent I1 residual minus the system's own d4_balance_defect_mw. "
           "Sign convention of the declared field is undocumented; both signs reported.",
    "I2a": "Supply summation: turbine + BESS + renewable - p_generation_mw.",
    "I2b": "Job attribution: p_compute_demand_mw vs admitted_nodes x kw_per_node.",
    "I3_site": "TAUTOLOGY. p_served_mw is defined as p_demand_mw minus cumulative "
               "shed and p_unserved_mw is that shed, so the sum is p_demand_mw by "
               "construction. Arithmetic-consistency check only; no physics content. "
               "Cannot detect under-delivery.",
    "I3_compute": "Per-block tri-field. Uses a proportional split, so unlike the "
                  "site form it can fail if block fractions do not sum to one.",
    "I3_cooling": "As I3_compute.",
    "I4_turbine": "Signed margin output_mw - rated_mw per unit. Positive is above nameplate.",
    "I4_bess": "|bess_output_mw| - bess_rated_mw, both directions.",
    "I4_cooling": "p_cooling_demand_mw - rated_cooling_mw.",
    "I5": "Storage energy: dSoC x usable_mwh vs integral of BESS power. "
          "Trapezoidal primary; rectangular variant in detail.",
    "I6_committed": "Recomputed on-bus rated sum vs reported committed_rated_mw. "
                    "Detail reconstructs floor_violated (never on the wire) and "
                    "compares it against reported reserve_satisfied.",
    "I6_floor": "Recomputed reserve floor vs reported. Both demand bases are "
                "computed because the basis used by the commitment path is not "
                "identifiable from the wire.",
}


def analyse(rec: Recording) -> tuple[list[ResidualRecord], dict[str, Any]]:
    records: list[ResidualRecord] = []
    prev: TickCtx | None = None
    for seq, payload in zip(rec.seqs, rec.ticks):
        ctx = TickCtx(run_id=rec.run_id, seq=seq, payload=payload, prev=prev)
        records.extend(run_all(ctx))
        prev = ctx

    by_inv: dict[str, list[ResidualRecord]] = {}
    for r in records:
        by_inv.setdefault(r.invariant, []).append(r)
    summary = {inv: {"distribution": distribution(rs),
                     "shapes": shape_by_subject(rs)}
               for inv, rs in sorted(by_inv.items())}
    return records, summary


def _fmt(v: Any, nd: int = 6) -> str:
    if isinstance(v, float):
        return f"{v:.{nd}g}"
    return "—" if v is None else str(v)


def write_report(recordings: list[Recording], out_md: Path, out_jsonl: Path) -> str:
    lines: list[str] = ["# NAR-001 Invariant Residuals", ""]
    all_records: list[ResidualRecord] = []

    lines += ["## 1. Units assumed", "",
              "No field in the source system declares its units. Every assumption "
              "this harness makes is listed here so a wrong one is caught in review.",
              "", "| Field | Assumed unit |", "|---|---|"]
    for k, u in sorted(UNIT_ASSUMPTIONS.items()):
        lines.append(f"| `{k}` | {u} |")
    lines += ["", "Further assumptions: on-bus means `state == 'synchronised'`; "
              "`hot_standby` is treated as False when the key is absent from a unit "
              "(the report states whether it appeared); I5 integrates trapezoidally.",
              "", "---", ""]

    lines += ["## 2. Runs analysed", "",
              "| Run | Ticks | Control msgs | Recorder events | Malformed | "
              "missed_leading_ticks |", "|---|---|---|---|---|---|"]
    for rec in recordings:
        m = rec.manifest or {}
        lines.append(
            f"| `{rec.run_id}` | {len(rec.ticks)} | {len(rec.control)} | "
            f"{len(rec.events)} | {rec.malformed_lines} | "
            f"{m.get('missed_leading_ticks', '—')} |")
    lines += ["", "---", ""]

    lines += ["## 3. Field availability (preflight)", ""]
    for rec in recordings:
        pf = preflight(rec)
        problems = {k: v for k, v in pf["fields"].items() if v["ok_fraction"] < 1.0}
        multi = {k: v for k, v in pf["fields"].items() if v["multiple_paths_answered"]}
        lines.append(f"**`{rec.run_id}`** — {len(pf['fields']) - len(problems)} of "
                     f"{len(pf['fields'])} canonical fields resolved on every tick.")
        lines.append("")
        if problems:
            lines += ["| Field | ok fraction | states |", "|---|---|---|"]
            for k, v in sorted(problems.items()):
                lines.append(f"| `{k}` | {v['ok_fraction']:.2f} | {v['states']} |")
            lines.append("")
        if multi:
            lines.append(f"More than one alias answered for: "
                         f"{', '.join('`%s`' % k for k in sorted(multi))} — values "
                         f"should be identical; a divergence would be a defect.")
            lines.append("")
    lines += ["---", ""]

    lines += ["## 4. Residual distributions", ""]
    for rec in recordings:
        records, summary = analyse(rec)
        all_records.extend(records)
        lines += [f"### `{rec.run_id}`", "",
                  "| Invariant | n eval | n skip | max abs | p95 abs | p50 abs | "
                  "min | max | n>0 | unit |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for inv, s in summary.items():
            d = s["distribution"]
            if d["n_evaluated"]:
                lines.append(
                    f"| {inv} | {d['n_evaluated']} | {d['n_skipped']} | "
                    f"{_fmt(d['max_abs'])} | {_fmt(d['p95_abs'])} | {_fmt(d['p50_abs'])} | "
                    f"{_fmt(d['min'])} | {_fmt(d['max'])} | {d['n_positive']} | "
                    f"{d['unit'] or '—'} |")
            else:
                lines.append(f"| {inv} | 0 | {d['n_skipped']} | — | — | — | — | — | — | — |")
        lines.append("")

        lines += ["**Shape of the evaluated series** (per subject; pooling assets "
                  "would produce meaningless reversal counts)", "",
                  "| Invariant | subject | first | last | stdev | max step | "
                  "reversals | monotonic frac | distinct |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for inv, s in summary.items():
            for subj, sh in s["shapes"].items():
                if sh.get("n", 0) >= 2:
                    lines.append(
                        f"| {inv} | {subj or '—'} | {_fmt(sh['first'])} | "
                        f"{_fmt(sh['last'])} | {_fmt(sh['stdev'])} | "
                        f"{_fmt(sh['max_abs_step'])} | {sh['n_sign_reversals']} | "
                        f"{sh['monotonic_fraction']:.2f} | {sh['n_distinct_values']} |")
        lines.append("")

        worst_lines = []
        for inv, s in summary.items():
            d = s["distribution"]
            key = "worst_high" if inv in ONE_SIDED else "worst_abs"
            w = d.get(key)
            if not w or w["value"] in (None, 0.0):
                continue
            label = "largest exceedance" if inv in ONE_SIDED else "largest magnitude"
            worst_lines.append(
                f"- **{inv}** {label} {_fmt(w['value'])} at sim_time "
                f"{_fmt(w['sim_time_s'])}s"
                + (f" ({w['subject']})" if w["subject"] else "")
                + f" — terms: {json.dumps(w['terms'], default=str)[:400]}")
        if worst_lines:
            lines += ["**Extreme residual per invariant**", "",
                      "One-sided invariants (I4) report the largest signed value, "
                      "since only exceedance above a rating is a finding; the "
                      "largest magnitude there would be the most idle asset.",
                      ""] + worst_lines + [""]

        skips = {inv: s["distribution"]["skip_reasons"]
                 for inv, s in summary.items() if s["distribution"]["skip_reasons"]}
        if skips:
            lines += ["**Skips by reason**", ""]
            for inv, rs in skips.items():
                lines.append(f"- **{inv}**: " + "; ".join(f"{k} ×{v}" for k, v in rs.items()))
            lines.append("")

        dis = [r for r in records
               if r.invariant == "I6_committed" and r.detail.get("agree") is False]
        hold = [r for r in records
                if r.invariant == "I6_committed"
                and r.detail.get("hold_with_unsatisfied_reserve")]
        lines += ["**I6 reconstruction**", "",
                  f"- Ticks where reconstructed `floor_violated` disagrees with reported "
                  f"`reserve_satisfied`: **{len(dis)}**"
                  + (f" (first at sim_time {_fmt(dis[0].sim_time_s)}s)" if dis else ""),
                  f"- Ticks with `reserve_satisfied == False` alongside "
                  f"`action == 'hold'`: **{len(hold)}**"
                  + (f" (first at sim_time {_fmt(hold[0].sim_time_s)}s)" if hold else ""),
                  ""]

        floor_recs = [r for r in records if r.invariant == "I6_floor"
                      and r.status == EVALUATED]
        if floor_recs:
            dp = [abs(r.detail["residual_using_p_demand_mw"]) for r in floor_recs
                  if r.detail.get("residual_using_p_demand_mw") is not None]
            dn = [abs(r.detail["residual_using_net_demand_mw"]) for r in floor_recs
                  if r.detail.get("residual_using_net_demand_mw") is not None]
            if dp and dn:
                mp, mn = sum(dp) / len(dp), sum(dn) / len(dn)
                better = "p_demand_mw" if mp < mn else "net_demand_mw"
                lines += [f"- Reserve-floor demand basis: mean |residual| is "
                          f"{_fmt(mp)} using `p_demand_mw` and {_fmt(mn)} using "
                          f"`net_demand_mw`. The reported floor is better reproduced by "
                          f"**`{better}`**.", ""]

        i1d = [r for r in records if r.invariant == "I1d" and r.status == EVALUATED]
        if i1d:
            a = sum(abs(r.value) for r in i1d) / len(i1d)
            b = sum(abs(r.detail["delta_if_declared_negated"]) for r in i1d) / len(i1d)
            if a == b:
                allzero = all(r.terms.get("d4_balance_defect_mw") == 0.0 for r in i1d)
                why = ("the declared field is identically zero across the run"
                       if allzero else "both conventions fit equally well")
                lines += [f"- `d4_balance_defect_mw` sign convention: "
                          f"**indeterminate** — {why} (mean |delta| {_fmt(a)} either "
                          f"way).", ""]
            else:
                conv = "as-emitted" if a < b else "negated"
                lines += [f"- `d4_balance_defect_mw` sign convention: mean |delta| is "
                          f"{_fmt(a)} as emitted and {_fmt(b)} negated, so the "
                          f"convention consistent with an independent recomputation "
                          f"is **{conv}**.", ""]

        cf = constant_fields(rec)
        lines += [f"- Constant fields: {len(cf['constant'])}; varying: "
                  f"{len(cf['varying'])}.", "", "---", ""]

    lines += ["## 5. Invariant notes", ""]
    for inv, note in INVARIANT_NOTES.items():
        lines.append(f"- **{inv}** — {note}")
    lines += ["", "---", "",
              "## 6. What this run could not determine", "",
              "- Any invariant showing 0 evaluated records above was not exercised by "
              "this data. It is not passing; it is untested.",
              "- Residual magnitudes are reported without tolerances. Tolerances must be "
              "set from these distributions, not chosen in advance.",
              "- `p_served_mw` is demand minus commanded shed, not delivered power. "
              "A site physically unable to serve its load reports zero unserved until "
              "a shed is commanded, so I3 cannot detect under-delivery and I1 is the "
              "only load-service check here.", ""]

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines))
    with out_jsonl.open("w") as fh:
        for r in all_records:
            fh.write(json.dumps(r.to_dict(), default=str) + "\n")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="NAR-001 invariant residual harness")
    ap.add_argument("recordings", nargs="+",
                    help="recorder JSONL files, or directories containing them")
    ap.add_argument("--out-md", default="reports/NAR-001_invariant_residuals.md")
    ap.add_argument("--out-jsonl", default="reports/NAR-001_residuals.jsonl")
    ap.add_argument("--preflight", action="store_true",
                    help="report field availability and exit without checking")
    args = ap.parse_args(argv)

    paths: list[Path] = []
    for raw in args.recordings:
        q = Path(raw)
        paths.extend(sorted(q.glob("*.jsonl")) if q.is_dir() else [q])
    if not paths:
        print("no .jsonl recordings found")
        return 1

    recs = [load_recording(p) for p in paths]

    if args.preflight:
        for rec in recs:
            pf = preflight(rec)
            print(f"\n{rec.run_id}: {pf['tick_count']} ticks, "
                  f"{rec.malformed_lines} malformed, "
                  f"events={pf['recorder_events'] or 'none'}")
            for key, v in sorted(pf["fields"].items()):
                if v["ok_fraction"] < 1.0:
                    print(f"  {key:24s} ok={v['ok_fraction']:.2f} {v['states']}")
                elif v["multiple_paths_answered"]:
                    print(f"  {key:24s} MULTIPLE ALIASES ANSWERED "
                          f"{list(v['paths_used'])}")
            ok = sum(1 for v in pf["fields"].values() if v["ok_fraction"] == 1.0)
            print(f"  -> {ok}/{len(pf['fields'])} canonical fields on every tick")
        return 0

    write_report(recs, Path(args.out_md), Path(args.out_jsonl))
    total = sum(len(r.ticks) for r in recs)
    print(f"analysed {total} ticks across {len(recs)} recording(s)")
    print(f"wrote {args.out_md} and {args.out_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
