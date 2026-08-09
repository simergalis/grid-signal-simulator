"""Distribution and shape summaries.

Descriptive only. Nothing here classifies a residual as acceptable or
unacceptable, and no constant in this module is a threshold -- the percentile
list is a reporting choice, not a bound.
"""
from __future__ import annotations

from typing import Any, Iterable

from .contracts import EVALUATED, ResidualRecord

PERCENTILES = (50, 95, 99)


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def distribution(records: Iterable[ResidualRecord]) -> dict[str, Any]:
    recs = list(records)
    evaluated = [r for r in recs if r.status == EVALUATED and r.value is not None]
    skipped = [r for r in recs if r.status != EVALUATED]

    reasons: dict[str, int] = {}
    for r in skipped:
        key = (r.reason or "unspecified").split("(")[0].strip()
        reasons[key] = reasons.get(key, 0) + 1

    out: dict[str, Any] = {
        "n_total": len(recs),
        "n_evaluated": len(evaluated),
        "n_skipped": len(skipped),
        "skip_fraction": (len(skipped) / len(recs)) if recs else 0.0,
        "skip_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "unit": next((r.unit for r in evaluated if r.unit), None),
    }
    if not evaluated:
        return out

    vals = sorted(r.value for r in evaluated)
    abs_vals = sorted(abs(v) for v in vals)
    out.update({
        "min": vals[0], "max": vals[-1],
        "mean": sum(vals) / len(vals),
        "max_abs": abs_vals[-1],
        **{f"p{p}_abs": _percentile(abs_vals, p) for p in PERCENTILES},
        "n_nonzero": sum(1 for v in vals if v != 0.0),
        "n_positive": sum(1 for v in vals if v > 0.0),
    })
    def _pick(rec):
        return {"sim_time_s": rec.sim_time_s, "seq": rec.seq, "value": rec.value,
                "subject": rec.subject, "terms": rec.terms}

    # Two extremes, because they answer different questions. For a two-sided
    # residual (I1, I5) the largest magnitude is what matters. For a one-sided
    # one (I4, where only exceedance above nameplate is meaningful) the largest
    # magnitude is the most *idle* asset, which is not a finding at all.
    out["worst_abs"] = _pick(max(evaluated, key=lambda r: abs(r.value)))
    out["worst_high"] = _pick(max(evaluated, key=lambda r: r.value))
    return out


def shape_by_subject(records: Iterable[ResidualRecord]) -> dict[str, Any]:
    """Shape per subject. Pooling subjects into one series produces meaningless
    reversal counts, because consecutive records belong to different assets."""
    recs = [r for r in records if r.status == EVALUATED and r.value is not None]
    groups: dict[Any, list[ResidualRecord]] = {}
    for r in recs:
        groups.setdefault(r.subject, []).append(r)
    return {("" if k is None else k): shape(v) for k, v in sorted(
        groups.items(), key=lambda kv: (kv[0] is not None, kv[0]))}


def shape(records: Iterable[ResidualRecord]) -> dict[str, Any]:
    """Descriptive time-series characterisation. No classification, no cutoffs."""
    series = [(r.sim_time_s, r.value) for r in records
              if r.status == EVALUATED and r.value is not None and r.sim_time_s is not None]
    series.sort(key=lambda tv: tv[0])
    if len(series) < 2:
        return {"n": len(series)}

    vals = [v for _, v in series]
    deltas = [b - a for a, b in zip(vals, vals[1:])]
    nonzero = [d for d in deltas if d != 0.0]
    signs = [1 if d > 0 else -1 for d in nonzero]
    reversals = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    dominant = 0.0
    if signs:
        pos = sum(1 for s in signs if s > 0)
        dominant = max(pos, len(signs) - pos) / len(signs)

    return {
        "n": len(series),
        "first": vals[0], "last": vals[-1],
        "mean": mean, "stdev": var ** 0.5,
        "max_abs_step": max((abs(d) for d in deltas), default=0.0),
        "n_sign_reversals": reversals,
        "monotonic_fraction": dominant,
        "n_distinct_values": len(set(vals)),
        "span_s": series[-1][0] - series[0][0],
    }
