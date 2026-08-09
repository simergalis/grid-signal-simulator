"""Co-occurrence analysis over a ChangeRecord stream.

Not part of detection. Detection reports what moved; this reports which signals
move *together*, which is the input the salience question needs (NAR-3).

The motivating observation: on a staircase run, `LOAD.p_demand_mw`,
`LOAD.p_compute_demand_mw` and `GEN.reserve_floor_mw` each emitted on the same 52
ticks, because reserve_floor is demand plus a constant. Three lines in the feed
for one event. A feed that shows every derived signal alongside its driver is
unreadable, and a FrameFact capped at N changes will be filled with restatements
of one movement while something else is dropped.

This module measures that. It does not decide what to do about it.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from .detector import ChangeRecord


def by_tick(records: Iterable[ChangeRecord]) -> dict[int, set[str]]:
    groups: dict[int, set[str]] = defaultdict(set)
    for r in records:
        groups[r.seq].add(r.signal)
    return dict(groups)


def co_occurrence(records: Iterable[ChangeRecord]) -> dict[str, Any]:
    """Per signal pair: how often they fire on the same tick, and the Jaccard
    overlap of the tick sets they fire on."""
    recs = list(records)
    groups = by_tick(recs)
    counts = Counter(r.signal for r in recs)

    ticks_by_signal: dict[str, set[int]] = defaultdict(set)
    for seq, sigs in groups.items():
        for s in sigs:
            ticks_by_signal[s].add(seq)

    pairs: list[dict[str, Any]] = []
    names = sorted(ticks_by_signal)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ta, tb = ticks_by_signal[a], ticks_by_signal[b]
            inter = len(ta & tb)
            if not inter:
                continue
            union = len(ta | tb)
            pairs.append({
                "a": a, "b": b, "co_ticks": inter,
                "jaccard": inter / union if union else 0.0,
                "a_only": len(ta - tb), "b_only": len(tb - ta),
                "a_implies_b": inter / len(ta) if ta else 0.0,
                "b_implies_a": inter / len(tb) if tb else 0.0,
            })
    pairs.sort(key=lambda d: (-d["jaccard"], -d["co_ticks"]))

    return {
        "n_records": len(recs),
        "n_ticks_with_change": len(groups),
        "records_per_changed_tick": (len(recs) / len(groups)) if groups else 0.0,
        "emissions_by_signal": dict(counts.most_common()),
        "pairs": pairs,
    }


def redundant_pairs(records: Iterable[ChangeRecord], *,
                    min_co_ticks: int = 2) -> list[dict[str, Any]]:
    """Pairs that always fire together in both directions.

    `min_co_ticks` guards against declaring a relationship from a single
    coincidence; it is a reporting floor, not a threshold on any measurement.
    """
    return [p for p in co_occurrence(records)["pairs"]
            if p["co_ticks"] >= min_co_ticks
            and p["a_implies_b"] == 1.0 and p["b_implies_a"] == 1.0]


def summarise(records: Iterable[ChangeRecord]) -> str:
    """Short text summary for a report or a console."""
    co = co_occurrence(records)
    lines = [
        f"{co['n_records']} change records across "
        f"{co['n_ticks_with_change']} changed ticks "
        f"({co['records_per_changed_tick']:.2f} per changed tick)",
        "",
        "Most active signals:",
    ]
    for sig, n in list(co["emissions_by_signal"].items())[:10]:
        lines.append(f"  {n:6d}  {sig}")
    red = redundant_pairs(records)
    if red:
        lines += ["", "Signals that always co-fire (each implies the other):"]
        for p in red[:15]:
            lines.append(f"  {p['co_ticks']:5d} ticks  {p['a']}  <->  {p['b']}")
    return "\n".join(lines)
