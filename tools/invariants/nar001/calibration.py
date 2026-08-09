"""Calibration scan -- derive deadbands from data instead of choosing them.

The detector requires nine catalogue parameters and supplies none of them. This
module reports, per signal, the observed value distribution, the tick-to-tick
delta distribution, and -- for each candidate band -- the exact number of records
the detector would emit. A band is then read off a curve rather than picked.

Emission counts are produced by running the real ChangeDetector, not by a
separate calculation. Counting `|delta| >= band` would be wrong, because
hysteresis is against the last reported value rather than the last tick, and a
second implementation of that rule is exactly the defect class this project keeps
finding.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

from .access import resolve_number
from .detector import (EDGE, LEVEL, RATE, REGISTRY, ChangeDetector, SignalSpec,
                       band_parameters, confirmation_parameters)
from .stats import _percentile

CANDIDATE_PERCENTILES = (50, 75, 90, 95, 99)

# Multiples of the observed noise floor, swept to give the curve resolution.
# On a signal with uniform steps every percentile collapses to the same value and
# the curve degenerates to a single point, which cannot be read. These are grid
# spacing, not proposals: the quantity being multiplied still comes from the data.
NOISE_MULTIPLES = (0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 100.0)

# A band large enough that a signal cannot emit. Used to silence signals that are
# not the subject of a sweep so the sweep measures one thing at a time.
DISABLED = float("inf")

# Used only so a sweep of one signal can construct a detector; the swept
# signal's own confirmation count comes from base_catalogue when supplied.
DEFAULT_CONFIRMATIONS = 2


def _series(payloads: Sequence[dict], spec: SignalSpec,
            aliases: tuple[str, ...]) -> list[float]:
    out = []
    for p in payloads:
        r = resolve_number(p, *aliases)
        if r.ok:
            out.append(r.value)
    return out


def _deltas(values: Sequence[float]) -> list[float]:
    return [abs(b - a) for a, b in zip(values, values[1:])]


def _dist(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    s = sorted(values)
    return {
        "n": len(s), "min": s[0], "max": s[-1],
        "mean": sum(s) / len(s),
        **{f"p{p}": _percentile(s, p) for p in CANDIDATE_PERCENTILES},
        "n_distinct": len(set(s)),
    }


def emissions_at(payloads: Sequence[dict], spec: SignalSpec, band: float,
                 base_catalogue: dict[str, Any] | None = None) -> int:
    """Exact number of records the detector emits for one signal at one band.

    Runs the real detector with every other band disabled, so the count is the
    detector's behaviour rather than a model of it.
    """
    if spec.band_key is None:
        return 0
    cat: dict[str, Any] = {k: DISABLED for k in band_parameters()}
    # Confirmation counts are integers, not magnitudes. Disabling a rate signal
    # is expressed through its band, never by writing DISABLED into its count.
    cat.update({k: DEFAULT_CONFIRMATIONS for k in confirmation_parameters()})
    cat.update(base_catalogue or {})
    cat[spec.band_key] = band
    det = ChangeDetector(cat)
    n = 0
    for i, p in enumerate(payloads):
        for r in det.step("calib", i, p):
            if r.signal == spec.signal or r.signal.startswith(spec.signal + "["):
                if r.kind in (LEVEL, RATE):
                    n += 1
    return n


def scan_signal(payloads: Sequence[dict], spec: SignalSpec) -> dict[str, Any]:
    values = _series(payloads, spec, spec.aliases)
    row: dict[str, Any] = {
        "signal": spec.signal, "domain": spec.domain, "kind": spec.kind,
        "band_key": spec.band_key, "units": spec.units,
        "values": _dist(values),
    }
    if spec.kind not in (LEVEL, RATE):
        row["note"] = "not deadbanded; no band to calibrate"
        return row
    if len(values) < 2:
        row["note"] = "fewer than two resolvable values; nothing to calibrate"
        return row

    deltas = _deltas(values)
    nonzero = [d for d in deltas if d > 0.0]
    row["deltas"] = _dist(deltas)
    row["nonzero_deltas"] = _dist(nonzero)
    row["still_fraction"] = 1.0 - (len(nonzero) / len(deltas)) if deltas else 1.0

    # Candidates come from the observed nonzero deltas, so they are read off the
    # data. A flat signal yields none, which is the correct answer.
    floor = _percentile(sorted(nonzero), 50) if nonzero else None
    cands = set()
    if nonzero:
        cands |= {round(_percentile(sorted(nonzero), p), 12)
                  for p in CANDIDATE_PERCENTILES}
        if floor and floor > 0:
            cands |= {round(floor * m, 12) for m in NOISE_MULTIPLES}
    cands = sorted(c for c in cands if c > 0.0)
    curve = []
    n_ticks = len(payloads)
    for band in cands:
        if band <= 0.0:
            continue
        n = emissions_at(payloads, spec, band)
        curve.append({"band": band, "emissions": n,
                      "per_100_ticks": 100.0 * n / n_ticks if n_ticks else 0.0})
    row["curve"] = curve
    row["noise_floor_estimate"] = floor
    # Dither and drift are indistinguishable by still_fraction -- an alternating
    # signal never repeats a value either. The discriminator is how much of the
    # distance travelled ends up as net displacement: a dither retraces its steps
    # (ratio near 0), a drift does not (ratio near 1). Reported as a number, with
    # no cut points, because the boundary between them is a reading not a fact.
    path_len = sum(deltas)
    row["travel_ratio"] = (abs(values[-1] - values[0]) / path_len
                           if path_len > 0 else None)
    if spec.kind == RATE and all(c["emissions"] == 0 for c in curve):
        row["note"] = ("no emissions at any candidate band; a rate signal is "
                       "structurally blind to single-tick steps (see detector "
                       "docstring) -- confirm the signal is meant to be sustained")
    return row


def scan(payloads: Sequence[dict],
         registry: Iterable[SignalSpec] = REGISTRY) -> dict[str, Any]:
    rows = [scan_signal(payloads, s) for s in registry if not s.per_unit]
    by_key: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("band_key") and r.get("curve"):
            by_key.setdefault(r["band_key"], []).append(r)
    return {"n_ticks": len(payloads), "signals": rows, "by_band_key": by_key}


def format_scan(result: dict[str, Any]) -> str:
    n = result["n_ticks"]
    out = [f"# Deadband calibration scan", "",
           f"{n} ticks. Candidate bands are percentiles of each signal's observed "
           f"non-zero tick-to-tick deltas. Emission counts are produced by running "
           f"the detector at that band, not estimated.", "",
           "Nothing here proposes a value. Read a band off the curve for the "
           "emission rate the feed can carry, and record the choice in a DR.", "",
           "Travel ratio is net displacement over total distance travelled, and "
           "it tells you which kind of curve you are reading. Near 0 the signal "
           "retraces its steps -- it dithers, and the curve shows a cliff where a "
           "band just above the dither silences it entirely. That cliff is the "
           "band. Near 1 the signal drifts and there is no cliff: every band "
           "trades resolution against volume smoothly, so the choice is a "
           "reporting policy rather than a noise threshold and should be recorded "
           "as one.", ""]

    for row in result["signals"]:
        if not row.get("curve"):
            continue
        v, d = row["values"], row["nonzero_deltas"]
        out += [f"## `{row['signal']}` ({row['units'] or 'unit undeclared'})", "",
                f"- band key: `{row['band_key']}`",
                f"- value range {v['min']:.6g} .. {v['max']:.6g}, "
                f"{v['n_distinct']} distinct",
                f"- unchanged on {row['still_fraction']*100:.1f}% of tick pairs; "
                f"travel ratio {row['travel_ratio']:.3f}"
                if row["travel_ratio"] is not None else
                f"- unchanged on {row['still_fraction']*100:.1f}% of tick pairs",
                f"- non-zero delta p50 {d['p50']:.6g}, p95 {d['p95']:.6g}, "
                f"max {d['max']:.6g}",
                f"- noise floor estimate (delta p50): "
                f"{row['noise_floor_estimate']:.6g}", "",
                "| candidate band | records | per 100 ticks |", "|---|---|---|"]
        for c in row["curve"]:
            out.append(f"| {c['band']:.6g} | {c['emissions']} | "
                       f"{c['per_100_ticks']:.2f} |")
        out.append("")

    out += ["## Signals sharing a band key", "",
            "One key serves several signals, so a band chosen for one is imposed "
            "on all of them. These are the groups where that trade-off applies.",
            ""]
    for key, rows in sorted(result["by_band_key"].items()):
        out.append(f"- `{key}`: " + ", ".join(f"`{r['signal']}`" for r in rows))
    out.append("")
    return "\n".join(out)
