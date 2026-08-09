"""End-to-end smoke: recording -> preflight -> calibrate -> detect -> trend ->
FrameFact -> narration.

Every stage prints what it produced and stops the moment one produces nothing.
Six components wired from a README is where an integration mismatch first
surfaces, and a stage that silently yields an empty list looks like success.

    python3 -m nar001.smoke recordings/run-x.jsonl
    python3 -m nar001.smoke recordings/run-x.jsonl --catalogue bands.json

Without a catalogue it runs stages 1-2 and stops, because bands must be read off
a calibration curve rather than chosen.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .calibration import scan
from .checkers import TickCtx, run_all
from .contracts import EVALUATED
from .cooccurrence import redundant_pairs, summarise
from .detector import ChangeDetector, MissingParameters, required_parameters
from .framefact import CAP_KEY, SPREAD_KEY, assemble
from .load import constant_fields, load_recording, preflight
from .narrator import narrate
from .trend import TrendAggregator, notable, trend_parameters

# Without these, nothing downstream can work: they are the terms of the power
# balance and the clock every window is measured against. A recording where two
# of the three are missing is a payload-shape mismatch, not a quiet run -- and
# "some field resolved" is too weak a guard, since sim_time_seconds alone would
# pass it while every checker starves.
CORE_FIELDS = ("sim_time_seconds", "p_demand_mw", "p_generation_mw")


class StageFailure(RuntimeError):
    pass


def _head(n: int, title: str) -> None:
    print(f"\n{'=' * 72}\n  STAGE {n} — {title}\n{'=' * 72}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StageFailure(message)


def stage_1_load(path: Path):
    _head(1, "load recording")
    rec = load_recording(path)
    print(f"  run_id            {rec.run_id}")
    print(f"  tick payloads     {len(rec.ticks)}")
    print(f"  control messages  {len(rec.control)}")
    print(f"  recorder events   {[e.get('event') for e in rec.events] or 'none'}")
    print(f"  malformed lines   {rec.malformed_lines}")
    if rec.manifest:
        for k in ("scenario_id", "playback_speed", "missed_leading_ticks",
                  "observed_tick_interval_s", "stop_reason"):
            if k in rec.manifest:
                print(f"  {k:17s} {rec.manifest[k]}")
        if rec.manifest.get("stop_reason") == "dropped":
            print("  WARNING: stop_reason is 'dropped' — this recording is "
                  "truncated and its tail is not evidence of anything.")
    _require(rec.ticks, "no tick payloads found; is this a recorder JSONL with "
                        "{'seq','received_wall_utc','payload'} lines?")
    return rec


def stage_2_preflight(rec) -> None:
    _head(2, "field availability")
    pf = preflight(rec)
    absent = {k: v for k, v in pf["fields"].items() if v["ok_fraction"] == 0.0}
    partial = {k: v for k, v in pf["fields"].items()
               if 0.0 < v["ok_fraction"] < 1.0}
    multi = {k: v for k, v in pf["fields"].items() if v["multiple_paths_answered"]}
    ok = len(pf["fields"]) - len(absent) - len(partial)
    print(f"  {ok}/{len(pf['fields'])} canonical fields resolve on every tick")
    for label, group in (("ABSENT on every tick", absent),
                         ("INTERMITTENT", partial)):
        if group:
            print(f"  {label}:")
            for k, v in sorted(group.items()):
                print(f"    {k:26s} ok={v['ok_fraction']:.2f} {v['states']}")
    if multi:
        print(f"  more than one alias answered for: {', '.join(sorted(multi))}")
    cf = constant_fields(rec)
    print(f"  constant fields {len(cf['constant'])}, varying {len(cf['varying'])}")
    core_ok = [k for k in CORE_FIELDS
               if pf["fields"].get(k, {}).get("ok_fraction", 0.0) > 0.0]
    print(f"  core fields present: {', '.join(core_ok) or 'none'}")
    _require(len(core_ok) >= 2,
             f"only {len(core_ok)} of {len(CORE_FIELDS)} core fields resolved "
             f"({', '.join(CORE_FIELDS)}) — the payload shape differs from what "
             f"this package assumes; correct contracts.py:ALIASES before going "
             f"further")
    if len(absent) > 3:
        print(f"  NOTE: {len(absent)} fields absent throughout. If these are wire "
              f"names this package has wrong, fix ALIASES rather than the "
              f"checkers.")


def stage_3_invariants(rec) -> None:
    _head(3, "invariant residuals")
    prev = None
    per_inv: dict[str, list[float]] = {}
    skipped: dict[str, int] = {}
    for i, payload in enumerate(rec.ticks):
        ctx = TickCtx(run_id=rec.run_id, seq=i, payload=payload, prev=prev)
        for r in run_all(ctx):
            if r.status == EVALUATED and r.value is not None:
                per_inv.setdefault(r.invariant, []).append(r.value)
            else:
                skipped[r.invariant] = skipped.get(r.invariant, 0) + 1
        prev = ctx
    for inv in sorted(set(per_inv) | set(skipped)):
        vals = per_inv.get(inv, [])
        if vals:
            worst = max(vals, key=abs)
            print(f"  {inv:16s} n={len(vals):5d}  max|residual|={abs(worst):.6g}  "
                  f"range {min(vals):.4g}..{max(vals):.4g}")
        else:
            print(f"  {inv:16s} n=    0  SKIPPED ×{skipped[inv]} — untested, "
                  f"not passing")
    _require(per_inv, "every invariant was skipped; check stage 2 for the fields "
                      "that did not resolve")


def stage_4_calibration(rec) -> dict[str, Any]:
    _head(4, "deadband calibration")
    result = scan(rec.ticks)
    rows = [r for r in result["signals"] if r.get("curve")]
    for r in rows:
        tr = r.get("travel_ratio")
        tag = f"travel {tr:.2f}" if tr is not None else "static"
        pts = "  ".join(f"{c['band']:.4g}->{c['emissions']}" for c in r["curve"])
        print(f"  {r['signal']:32s} [{tag:11s}] {pts}")
        if r.get("note"):
            print(f"      {r['note']}")
    print(f"\n  {len(rows)} signal(s) have a band to calibrate.")
    print("  Read a band off each curve for the emission rate the feed can carry.")
    print("  Nothing here proposes a value; record the choice in a DR.")
    _require(rows, "no signal produced a calibration curve — either nothing moved "
                   "in this recording, or no deadbanded signal resolved")
    return result


def stage_5_detect(rec, catalogue):
    _head(5, "change detection")
    det = ChangeDetector(dict(catalogue))
    records, history = [], []
    for i, payload in enumerate(rec.ticks):
        recs = det.step(rec.run_id, rec.seqs[i], payload)
        records.append(recs)
        history.extend(recs)
    print(summarise(history))
    red = redundant_pairs(history)
    if red:
        print(f"\n  {len(red)} always-co-firing pair(s); the FrameFact will fold "
              f"these to one representative each.")
    _require(history, "the detector emitted nothing across the whole recording — "
                      "the bands in the catalogue are almost certainly too wide")
    return records, history


def stage_6_trends(rec, catalogue):
    _head(6, "trends")
    agg = TrendAggregator(dict(catalogue))
    for payload in rec.ticks:
        agg.update(payload)
    facts = agg.facts(rec.run_id, len(rec.ticks) - 1)
    keep = notable(facts)
    print(f"  {len(facts)} fact(s) computed, {len(keep)} notable "
          f"({len(facts) - len(keep)} flat or insufficient)")
    for f in keep[:12]:
        print(f"  {f.signal:30s} w={f.window_s:6.0f}s  {f.direction:12s} "
              f"slope={f.slope_per_min:9.4f}/min  steps={f.step_count:3d}  "
              f"pct_from_peak="
              f"{'—' if f.pct_from_run_peak is None else format(f.pct_from_run_peak, '.1f')}")
    _require(facts, "no trend facts were produced — no deadbanded numeric signal "
                    "resolved on two or more ticks")
    return agg


def stage_7_narrate(rec, catalogue, records, history, agg) -> None:
    _head(7, "FrameFact and narration")
    last = len(rec.ticks) - 1
    ff = assemble(rec.run_id, last, payload=rec.ticks[last],
                  changes=records[last], trends=agg.facts(rec.run_id, last),
                  catalogue=catalogue,
                  prev_payload=rec.ticks[last - 1] if last else None,
                  change_history=history)
    print(f"  invariants_ok      {ff.invariants_ok}")
    print(f"  invariants_failed  {ff.invariants_failed or 'none'}")
    print(f"  invariants_skipped {ff.invariants_skipped or 'none'}")
    print(f"  changes            {len(ff.changes)} kept of {ff.n_changes_total} "
          f"({len(ff.folded)} folded, {ff.n_changes_dropped} dropped)")
    print(f"  trends             {len(ff.trends)}")
    for n in ff.notes:
        print(f"  note: {n}")
    out = narrate(ff)
    print(f"\n  HEADLINE  {out['headline']}")
    print(f"  BODY      {out['body']}")
    print(f"\n  source={out['source']}  as_of_s={out['as_of_s']}  "
          f"numbers_used={len(out['numbers_used'])}")
    print("\n  This is the Phase C gate. If the text above is not useful enough "
          "to read,\n  a model will not rescue it.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NAR-001 end-to-end smoke")
    ap.add_argument("recording")
    ap.add_argument("--catalogue", help="JSON of band values; stages 5-7 need it")
    args = ap.parse_args(argv)

    try:
        rec = stage_1_load(Path(args.recording))
        stage_2_preflight(rec)
        stage_3_invariants(rec)
        stage_4_calibration(rec)

        if not args.catalogue:
            print("\n" + "=" * 72)
            print("  STOPPING after stage 4: no --catalogue supplied.")
            print("  Bands must be read off the curves above, not chosen. Required:")
            for k in sorted(set(required_parameters()) | set(trend_parameters())
                            | {CAP_KEY, SPREAD_KEY}):
                print(f"    {k}")
            print("=" * 72)
            return 0

        catalogue = json.loads(Path(args.catalogue).read_text())
        missing = [k for k in (CAP_KEY, SPREAD_KEY) if k not in catalogue]
        _require(not missing, f"catalogue is missing: {', '.join(missing)}")
        records, history = stage_5_detect(rec, catalogue)
        agg = stage_6_trends(rec, catalogue)
        stage_7_narrate(rec, catalogue, records, history, agg)
        print("\nAll seven stages produced output.")
        return 0

    except MissingParameters as exc:
        print(f"\nSTAGE FAILED: {exc}", file=sys.stderr)
        return 2
    except StageFailure as exc:
        print(f"\nSTAGE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
