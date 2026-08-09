"""CLI: run the detector over recordings, or calibrate its bands.

    python3 -m nar001.feed recordings/ --calibrate
    python3 -m nar001.feed recordings/ --catalogue bands.json --out feed.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .calibration import format_scan, scan
from .cooccurrence import summarise
from .detector import ChangeDetector, MissingParameters, required_parameters
from .load import load_recording


def _paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in args:
        q = Path(raw)
        out.extend(sorted(q.glob("*.jsonl")) if q.is_dir() else [q])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NAR-001 change detector")
    ap.add_argument("recordings", nargs="+",
                    help="recorder JSONL files, or directories containing them")
    ap.add_argument("--calibrate", action="store_true",
                    help="report deadband candidate curves and exit")
    ap.add_argument("--catalogue", help="JSON file of band values")
    ap.add_argument("--out", help="write the change feed as JSONL")
    ap.add_argument("--out-calibration", help="write the calibration scan as markdown")
    args = ap.parse_args(argv)

    paths = _paths(args.recordings)
    if not paths:
        print("no .jsonl recordings found")
        return 1
    recs = [load_recording(p) for p in paths]

    if args.calibrate:
        for rec in recs:
            result = scan(rec.ticks)
            text = f"<!-- {rec.run_id} -->\n" + format_scan(result)
            if args.out_calibration:
                p = Path(args.out_calibration)
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a") as fh:
                    fh.write(text + "\n")
            calibratable = [r for r in result["signals"] if r.get("curve")]
            print(f"\n{rec.run_id}: {len(rec.ticks)} ticks, "
                  f"{len(calibratable)} signals with a band to calibrate")
            for r in calibratable:
                # Raw counts, not a rate: a signal changing twice in 800 ticks
                # is 0.25 per 100 and would round away to zero.
                pts = "  ".join(f"{c['band']:.4g}->{c['emissions']}"
                                for c in r["curve"])
                tr = r.get("travel_ratio")
                tag = f"travel {tr:.2f}" if tr is not None else "static    "
                print(f"  {r['signal']:32s} [{tag:11s}] {pts}")
                if r.get("note"):
                    print(f"      note: {r['note']}")
        if args.out_calibration:
            print(f"\nwrote {args.out_calibration}")
        return 0

    if not args.catalogue:
        print("a --catalogue is required to run the detector.\n"
              "Required keys (values must come from a calibration scan, not "
              "from judgement):")
        for k in required_parameters():
            print(f"  {k}")
        print("\nRun with --calibrate first.")
        return 2

    catalogue = json.loads(Path(args.catalogue).read_text())
    try:
        detectors = {rec.run_id: ChangeDetector(dict(catalogue)) for rec in recs}
    except MissingParameters as exc:
        print(exc)
        return 2

    all_records = []
    for rec in recs:
        det = detectors[rec.run_id]
        records = []
        for i, payload in enumerate(rec.ticks):
            records.extend(det.step(rec.run_id, rec.seqs[i], payload))
        all_records.extend(records)
        print(f"\n{rec.run_id}: {len(rec.ticks)} ticks")
        print(summarise(records))

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as fh:
            for r in all_records:
                fh.write(json.dumps(r.to_dict(), default=str) + "\n")
        print(f"\nwrote {args.out} ({len(all_records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
