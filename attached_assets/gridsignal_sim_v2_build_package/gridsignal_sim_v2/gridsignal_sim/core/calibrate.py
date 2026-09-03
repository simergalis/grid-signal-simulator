"""Derive `balance_defect_tolerance_mw` from recorded residuals.

Separate from `power_balance.py` so that module stays free of I/O. This one reads
files; nothing here is called from the tick path.

DR-BAL-2 was closed with a tolerance of 0.0 calibrated from `demo-baseline`. That
is a degenerate result: 11 ticks of an idle site where the arithmetic cancels
exactly. A floor of 0.0 blocks the first genuinely correct run whose MW-scale
sums leave float rounding of order 1e-15.

The right source is **I2a** from the Phase A' harness --
`turbine + bess + renewable - p_generation_mw`. It is structurally the same kind
of sum as the balance identity, it is exercised on every one of the 869 recorded
ticks, and it is known to close: the harness measured a p99 magnitude of roughly
3.55e-15 MW, which is float noise on that many terms and nothing else.

    python3 -m core.calibrate reports/NAR-001_residuals.jsonl --invariant I2a
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator

from .power_balance import DegenerateCalibration, NoiseFloor, calibrate_noise_floor

EVALUATED = "evaluated"


def read_residuals(path: str | Path) -> Iterator[dict]:
    """Yield residual records from the harness JSONL, skipping malformed lines."""
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def values_for(records: Iterable[dict], invariant: str,
               *, run_id: str | None = None) -> list[float]:
    """Evaluated residual magnitudes for one invariant.

    Records with `status != evaluated` are skipped rather than counted as zero --
    a not-evaluable tick carries no information about the noise floor, and
    treating it as a clean sample would drag the floor down.
    """
    out: list[float] = []
    for r in records:
        if r.get("invariant") != invariant:
            continue
        if r.get("status") != EVALUATED:
            continue
        if run_id is not None and r.get("run_id") != run_id:
            continue
        v = r.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
    return out


def calibrate(path: str | Path, invariant: str = "I2a",
              *, headroom_multiple: float = 10.0,
              run_id: str | None = None) -> NoiseFloor:
    vals = values_for(read_residuals(path), invariant, run_id=run_id)
    if not vals:
        raise ValueError(
            f"no evaluated {invariant} records in {path}"
            + (f" for run {run_id}" if run_id else ""))
    basis = f"{invariant} from {Path(path).name}" + (f" ({run_id})" if run_id else "")
    return calibrate_noise_floor(vals, headroom_multiple=headroom_multiple,
                                 basis=basis)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("residuals", help="harness residuals JSONL")
    ap.add_argument("--invariant", default="I2a")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--headroom-multiple", type=float, default=10.0)
    args = ap.parse_args(argv)

    try:
        nf = calibrate(args.residuals, args.invariant,
                       headroom_multiple=args.headroom_multiple,
                       run_id=args.run_id)
    except DegenerateCalibration as e:
        print(f"REFUSED: {e}")
        return 2

    print(f"basis                    {nf.basis}")
    print(f"samples                  {nf.n} ({nf.n_nonzero} non-zero)")
    print(f"max |residual|           {nf.max_abs:.6g} MW")
    print(f"p99 |residual|           {nf.p99_abs:.6g} MW")
    print(f"p99.9 |residual|         {nf.p999_abs:.6g} MW")
    print(f"suggested tolerance      {nf.suggested_tolerance_mw:.6g} MW"
          f"   (p99.9 x {args.headroom_multiple:g})")
    print()
    print("For review, not for automatic application. Sanity check: the value "
          "must be far below any defect it has to catch -- the measured "
          "violations are 14.34 MW and 18.05 MW.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
