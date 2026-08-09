"""Record schema and the field alias table.

A ResidualRecord carries a magnitude and never a verdict. There is deliberately
no `passed` field, no threshold, and no tolerance anywhere in this package --
the residual distributions are what set tolerances later, which cannot happen
if the data has already been thresholded.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

EVALUATED = "evaluated"
NOT_EVALUABLE = "not_evaluable"

# Invariants where only a positive residual is a finding. I4 emits a signed
# margin against a rating, so a negative value means an asset is below
# nameplate -- the normal case, and not an anomaly.
ONE_SIDED = frozenset({"I4_turbine", "I4_bess", "I4_cooling"})

# Comparisons rather than identities: informational, and derivative of an
# invariant that is itself reported, so they are not counted as findings.
INFORMATIONAL = frozenset({"I1d"})


@dataclass(frozen=True)
class ResidualRecord:
    invariant: str
    run_id: str
    seq: int
    sim_time_s: float | None
    status: str
    value: float | None = None
    unit: str | None = None
    subject: str | None = None          # e.g. "turbine_units[2]" for per-asset checks
    terms: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluated(inv, ctx, value, unit, *, subject=None, terms=None, detail=None) -> ResidualRecord:
    return ResidualRecord(
        invariant=inv, run_id=ctx.run_id, seq=ctx.seq, sim_time_s=ctx.sim_time_s,
        status=EVALUATED, value=value, unit=unit, subject=subject,
        terms=terms or {}, detail=detail or {},
    )


def not_evaluable(inv, ctx, reason, *, subject=None, terms=None) -> ResidualRecord:
    return ResidualRecord(
        invariant=inv, run_id=ctx.run_id, seq=ctx.seq, sim_time_s=ctx.sim_time_s,
        status=NOT_EVALUABLE, value=None, unit=None, subject=subject,
        terms=terms or {}, reason=reason,
    )


# ---------------------------------------------------------------------------
# Alias table.
#
# Three quantities are emitted on the wire under two names each. The ORM
# attribute names are canonical; the wire-alias names are the fallback. Which
# name actually answered is recorded on every ResidualRecord so a divergence
# between the two would be visible rather than silent.
# ---------------------------------------------------------------------------
ALIASES: dict[str, tuple[str, ...]] = {
    "p_demand_mw":          ("p_demand_mw", "p_total_mw"),
    "p_compute_demand_mw":  ("p_compute_demand_mw", "p_compute_mw"),
    "p_cooling_demand_mw":  ("p_cooling_demand_mw", "p_cooling_mw"),
    "p_generation_mw":      ("p_generation_mw",),
    "d4_balance_defect_mw": ("d4_balance_defect_mw",),
    "grid_exchange_mw":     ("grid_exchange_mw",),
    "turbine_output_mw":    ("turbine_output_mw",),
    "bess_output_mw":       ("bess_output_mw",),
    "p_renewable_mw":       ("p_renewable_mw",),
    "p_served_mw":          ("p_served_mw",),
    "p_unserved_mw":        ("p_unserved_mw",),
    "p_compute_served_mw":  ("p_compute_served_mw",),
    "p_compute_unserved_mw": ("p_compute_unserved_mw",),
    "p_cooling_served_mw":  ("p_cooling_served_mw",),
    "p_cooling_unserved_mw": ("p_cooling_unserved_mw",),
    "bess_soc_fraction":    ("bess_soc_fraction",),
    "bess_usable_mwh":      ("bess_usable_mwh",),
    "bess_rated_mw":        ("bess_rated_mw",),
    "rated_cooling_mw":     ("rated_cooling_mw",),
    "net_demand_mw":        ("net_demand_mw",),
    "sim_time_seconds":     ("sim_time_seconds",),
    "committed_rated_mw":   ("commitment_block.committed_rated_mw", "committed_rated_mw"),
    "reserve_floor_mw":     ("commitment_block.reserve_floor_mw", "reserve_floor_mw"),
    "reserve_satisfied":    ("commitment_block.reserve_satisfied", "reserve_satisfied"),
    "commitment_action":    ("commitment_block.action", "commitment_action"),
    "turbine_units":        ("turbine_units",),
    "kube_metrics":         ("kube_metrics",),
    "kw_per_node":          ("kube_metrics.kw_per_node", "kw_per_node", "hardware_kw_per_node"),
    "admitted_nodes":       ("kube_metrics.admitted_nodes",),
}

# Units are declared nowhere in the source system. Every assumption this
# package makes is listed here and printed at the top of the report so a wrong
# one is caught in review rather than silently propagating into a residual.
UNIT_ASSUMPTIONS: dict[str, str] = {
    "p_demand_mw": "MW", "p_compute_demand_mw": "MW", "p_cooling_demand_mw": "MW",
    "p_generation_mw": "MW", "d4_balance_defect_mw": "MW", "grid_exchange_mw": "MW",
    "turbine_output_mw": "MW", "bess_output_mw": "MW", "p_renewable_mw": "MW",
    "p_served_mw": "MW", "p_unserved_mw": "MW", "p_compute_served_mw": "MW",
    "p_compute_unserved_mw": "MW", "p_cooling_served_mw": "MW",
    "p_cooling_unserved_mw": "MW", "bess_soc_fraction": "fraction 0-1",
    "bess_usable_mwh": "MWh", "bess_rated_mw": "MW", "rated_cooling_mw": "MW",
    "net_demand_mw": "MW", "sim_time_seconds": "s",
    "committed_rated_mw": "MW", "reserve_floor_mw": "MW",
    "turbine_units[].output_mw": "MW", "turbine_units[].rated_mw": "MW",
    "admitted_nodes": "count", "kw_per_node": "kW",
}
