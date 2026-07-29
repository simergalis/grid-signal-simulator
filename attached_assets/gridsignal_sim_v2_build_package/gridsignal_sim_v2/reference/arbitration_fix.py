"""B-9 remediation: deterministic selection. v2.5 §26.4, TC-49."""
from dataclasses import dataclass, replace

SELECTION_ORDER = ("storage_discharge", "turbine_ramp", "firm_grid_import",
                   "reserved_grid_purchase", "curtail_ladder_ab", "curtail_ladder_cd")
_RANK = {k: i for i, k in enumerate(SELECTION_ORDER)}
CLOSURE_EPSILON_MW = 0.01

@dataclass(frozen=True)
class Rec:
    recommendation_id: str
    kind: str
    originating_agent: str
    estimated_impact_mw: float
    contribution_mw: float = 0.0

@dataclass(frozen=True)
class Capability:
    headroom: dict
    def headroom_for(self, kind): return self.headroom.get(kind, 0.0)

# ---------- v0.1 AS WRITTEN (defective) ----------
def select_v01(shortfall_mw, recs, capability):
    remaining, selected = shortfall_mw, []
    by_kind = {r.kind: r for r in recs}          # silent overwrite; order-dependent
    for kind in SELECTION_ORDER:
        if remaining <= CLOSURE_EPSILON_MW: break
        rec = by_kind.get(kind)
        if rec is None: continue
        head = capability.headroom_for(kind)
        if head <= 0: continue
        c = min(head, remaining)
        selected.append(replace(rec, contribution_mw=c)); remaining -= c
    return selected

# ---------- FIX ----------
def _total_order(r):
    """Total order: ladder position, then impact desc, then id. No ties possible,
    because recommendation_id is unique. Reproducible from the set alone."""
    return (_RANK.get(r.kind, len(SELECTION_ORDER)), -r.estimated_impact_mw,
            r.recommendation_id)

def select_fixed(shortfall_mw, recs, capability):
    """Same-kind collisions are RANKED, not dropped: both may contribute, in
    total order, until that kind's headroom is exhausted. Nothing is silently lost."""
    remaining, selected = shortfall_mw, []
    used_by_kind: dict[str, float] = {}
    for rec in sorted(recs, key=_total_order):          # <-- the fix
        if remaining <= CLOSURE_EPSILON_MW: break
        if rec.kind not in _RANK: continue
        head = capability.headroom_for(rec.kind) - used_by_kind.get(rec.kind, 0.0)
        if head <= 0: continue
        c = min(head, remaining)
        selected.append(replace(rec, contribution_mw=c))
        used_by_kind[rec.kind] = used_by_kind.get(rec.kind, 0.0) + c
        remaining -= c
    return selected
