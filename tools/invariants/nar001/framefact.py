"""FrameFact assembler -- the window digest handed to a narrator.

The narrator never sees the simulator, the wire, or the detector. It sees this.

Two properties matter more than the schema:

1. Failing invariants are **named**, not collapsed to a boolean, so narration and
   template alike can say *which* reading is not to be trusted.
2. The change cap is applied after redundancy folding. Four signals firing on the
   identical tick because each is an affine function of the others would
   otherwise fill a cap of N with restatements of one movement while an unrelated
   change is dropped.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from .checkers import TickCtx, run_all
from .contracts import EVALUATED, INFORMATIONAL, ONE_SIDED
from .cooccurrence import redundant_pairs
from .detector import AVAILABILITY, EDGE, ChangeRecord
from .trend import TrendFact, notable

CAP_KEY = "framefact_change_cap"
SPREAD_KEY = "fold_ratio_spread_max"
FRAMEFACT_PARAMETERS = (CAP_KEY, SPREAD_KEY)

# Kinds that are never folded away as redundant: a discrete transition or a field
# going null is not a restatement of a neighbouring level move.
UNFOLDABLE = (EDGE, AVAILABILITY)


@dataclass(frozen=True)
class FrameFact:
    run_id: str
    seq: int
    window_from_s: float | None
    window_to_s: float | None
    changes: list[dict[str, Any]] = field(default_factory=list)
    trends: list[dict[str, Any]] = field(default_factory=list)
    invariants_ok: bool = True
    invariants_failed: list[str] = field(default_factory=list)
    invariants_skipped: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    n_changes_total: int = 0
    n_changes_dropped: int = 0
    folded: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MissingFrameFactParameters(KeyError):
    def __init__(self, keys: list[str]):
        self.keys = sorted(keys)
        super().__init__("catalogue is missing: " + ", ".join(self.keys))


def _delta_ratio_spread(hist: Sequence[ChangeRecord], a: str, b: str) -> float | None:
    """Relative spread of delta_a / delta_b across the ticks where both fired.

    Co-timing alone is not evidence of a relationship. On a run where every
    signal moves on every tick, every pair implies every other and the whole
    frame collapses to one change -- including genuinely unrelated signals. An
    affine relationship additionally holds the *ratio* of the deltas constant,
    which unrelated signals do not.
    """
    da = {r.seq: r.delta for r in hist if r.signal == a and isinstance(r.delta, (int, float))}
    db = {r.seq: r.delta for r in hist if r.signal == b and isinstance(r.delta, (int, float))}
    ratios = [da[s] / db[s] for s in sorted(set(da) & set(db)) if db[s]]
    if len(ratios) < 2:
        return None
    lo, hi = min(ratios), max(ratios)
    mean = sum(ratios) / len(ratios)
    return abs(hi - lo) / abs(mean) if mean else None


def fold_redundant(changes: Sequence[ChangeRecord],
                   history: Sequence[ChangeRecord] | None = None,
                   *, spread_max: float | None = None
                   ) -> tuple[list[ChangeRecord], list[dict[str, Any]]]:
    """Collapse groups of changes that are restatements of one another.

    Two conditions, both required. The signals must co-fire in both directions
    across `history` -- the run so far, not the window alone, because one
    coincidence is a coincidence and a hundred is a relationship. And the ratio of
    their deltas must be stable, which is what distinguishes an affine
    relationship from two unrelated signals that happen to be busy at the same
    time.

    The representative is the first member in arrival order. The others go into
    `folded`, so nothing disappears silently.

    Known limitation: two genuinely unrelated signals that both happen to ramp
    linearly over the same interval hold a constant delta ratio and will fold.
    Nothing here can tell that apart from a causal link -- only a longer history
    can, since unrelated ramps eventually diverge. Folding is therefore reported
    rather than silent, and the representative is always retained.
    """
    hist = list(history if history is not None else changes)
    pairs = redundant_pairs(hist, min_co_ticks=2)
    if spread_max is not None:
        kept_pairs = []
        for pr in pairs:
            spread = _delta_ratio_spread(hist, pr["a"], pr["b"])
            if spread is not None and spread <= spread_max:
                kept_pairs.append(pr)
        pairs = kept_pairs
    if not pairs:
        return list(changes), []

    # union-find over mutually implied signals
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for p in pairs:
        union(p["a"], p["b"])

    kept: list[ChangeRecord] = []
    folded: list[dict[str, Any]] = []
    seen_group_at_seq: set[tuple[str, int]] = set()
    for rec in changes:
        if rec.kind in UNFOLDABLE or rec.signal not in parent:
            kept.append(rec)
            continue
        key = (find(rec.signal), rec.seq)
        if key in seen_group_at_seq:
            folded.append({"signal": rec.signal, "seq": rec.seq,
                           "represented_by": key[0]})
            continue
        seen_group_at_seq.add(key)
        kept.append(rec)
    return kept, folded


def assemble(run_id: str, seq: int, *, payload: dict[str, Any],
             changes: Sequence[ChangeRecord], trends: Iterable[TrendFact],
             catalogue: dict[str, Any],
             prev_payload: dict[str, Any] | None = None,
             change_history: Sequence[ChangeRecord] | None = None) -> FrameFact:
    missing = [k for k in FRAMEFACT_PARAMETERS if k not in catalogue]
    if missing:
        raise MissingFrameFactParameters(missing)
    cap = int(catalogue[CAP_KEY])

    prev_ctx = (TickCtx(run_id=run_id, seq=seq - 1, payload=prev_payload)
                if prev_payload is not None else None)
    residuals = run_all(TickCtx(run_id=run_id, seq=seq, payload=payload,
                                prev=prev_ctx))

    failed, skipped = [], []
    for r in residuals:
        if r.status != EVALUATED:
            if r.invariant not in skipped:
                skipped.append(r.invariant)
            continue
        if r.invariant in INFORMATIONAL or r.value is None:
            continue
        # No tolerance is applied; zero is unambiguous and needs none. But a
        # one-sided invariant is only a finding above its rating -- I4 emits a
        # signed margin, so a turbine running below nameplate is the normal case
        # and reporting it as an anomaly would make every clean frame look bad.
        hit = r.value > 0.0 if r.invariant in ONE_SIDED else r.value != 0.0
        if hit and r.invariant not in failed:
            failed.append(r.invariant)

    # I6's reconstruction disagreement is a boolean finding, not a residual, so
    # it would otherwise be invisible in the failed list.
    for r in residuals:
        if r.invariant == "I6_committed" and r.detail.get("agree") is False:
            if "I6_agreement" not in failed:
                failed.append("I6_agreement")

    kept, folded = fold_redundant(changes, change_history,
                                  spread_max=float(catalogue[SPREAD_KEY]))
    dropped = 0
    if len(kept) > cap:
        dropped = len(kept) - cap
        kept = kept[:cap]

    tl = [f.to_dict() for f in notable(trends)]
    times = [c.t_sim_s for c in changes if c.t_sim_s is not None]

    notes: list[str] = []
    if folded:
        notes.append(f"{len(folded)} change(s) folded as redundant restatements "
                     f"of a co-firing signal")
    if dropped:
        notes.append(f"{dropped} change(s) dropped by the cap of {cap}; ordering "
                     f"is arrival order, which is not a salience ranking (NAR-3)")
    if skipped:
        notes.append("invariants not evaluable on this frame: " + ", ".join(skipped))

    return FrameFact(
        run_id=run_id, seq=seq,
        window_from_s=min(times) if times else None,
        window_to_s=max(times) if times else None,
        changes=[c.to_dict() for c in kept],
        trends=tl,
        invariants_ok=not failed,
        invariants_failed=failed,
        invariants_skipped=skipped,
        state=_state(payload, residuals),
        n_changes_total=len(changes),
        n_changes_dropped=dropped,
        folded=folded,
        notes=notes,
    )


def _state(payload: dict[str, Any], residuals) -> dict[str, Any]:
    """The handful of figures a narrator may quote, plus the two contradictions
    it must not be able to paper over."""
    from .access import resolve, resolve_number
    from .contracts import ALIASES

    def num(key):
        r = resolve_number(payload, *ALIASES.get(key, (key,)))
        return r.value if r.ok else None

    def raw(key):
        r = resolve(payload, *ALIASES.get(key, (key,)))
        return r.value if r.ok else None

    i1 = next((r for r in residuals if r.invariant == "I1"
               and r.status == EVALUATED), None)
    i1d = next((r for r in residuals if r.invariant == "I1d"
                and r.status == EVALUATED), None)
    i6 = next((r for r in residuals if r.invariant == "I6_committed"), None)

    return {
        "sim_time_s": num("sim_time_seconds"),
        "p_demand_mw": num("p_demand_mw"),
        "p_generation_mw": num("p_generation_mw"),
        "p_unserved_mw": num("p_unserved_mw"),
        "committed_rated_mw": num("committed_rated_mw"),
        "reserve_floor_mw": num("reserve_floor_mw"),
        "reserve_satisfied": raw("reserve_satisfied"),
        "commitment_action": raw("commitment_action"),
        "bess_soc_fraction": num("bess_soc_fraction"),
        "power_balance_residual_mw": i1.value if i1 else None,
        # Informational: whether an independent recomputation agrees with the
        # system's own declared balance defect.
        "declared_defect_delta_mw": i1d.value if i1d else None,
        # Both surfaced deliberately: reserve unsatisfied alongside a hold, and a
        # reconstruction that disagrees with the reported flag, are exactly the
        # contradictions a fluent narrator would smooth over.
        "reconstructed_floor_violated": (i6.detail.get("reconstructed_floor_violated")
                                         if i6 else None),
        "hold_with_unsatisfied_reserve": (i6.detail.get("hold_with_unsatisfied_reserve")
                                          if i6 else None),
    }
