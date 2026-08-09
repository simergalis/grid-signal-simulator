"""Invariant checkers I1-I6.

Every checker is a pure function of one tick payload (and its predecessor, for
I5). Each returns a list of ResidualRecord. No checker compares runs, defines a
tolerance, or emits a verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .access import resolve, resolve_number, get_path
from .contracts import ALIASES, ResidualRecord, evaluated, not_evaluable

SYNCHRONISED = "synchronised"


@dataclass(frozen=True)
class TickCtx:
    run_id: str
    seq: int
    payload: dict[str, Any]
    prev: "TickCtx | None" = None

    @property
    def sim_time_s(self) -> float | None:
        r = resolve_number(self.payload, *ALIASES["sim_time_seconds"])
        return r.value if r.ok else None


def _nums(payload, *keys):
    """Resolve several canonical keys at once.

    Returns (values_by_key, paths_by_key, first_failure_reason_or_None).
    """
    vals, paths = {}, {}
    for k in keys:
        r = resolve_number(payload, *ALIASES[k])
        if not r.ok:
            return vals, paths, r.reason()
        vals[k], paths[k] = r.value, r.path
    return vals, paths, None


# --------------------------------------------------------------------------
# I1 -- power balance, and agreement with the system's own declared defect
# --------------------------------------------------------------------------
def check_i1(ctx: TickCtx) -> list[ResidualRecord]:
    v, p, bad = _nums(ctx.payload, "p_generation_mw", "grid_exchange_mw", "p_demand_mw")
    if bad:
        return [not_evaluable("I1", ctx, bad)]
    residual = v["p_generation_mw"] + v["grid_exchange_mw"] - v["p_demand_mw"]
    out = [evaluated("I1", ctx, residual, "MW", terms={**v, "_paths": p})]

    d = resolve_number(ctx.payload, *ALIASES["d4_balance_defect_mw"])
    if d.ok:
        # Sign convention of the declared defect is not documented. Both are
        # carried; the report picks whichever is consistently smaller and says so.
        out.append(evaluated(
            "I1d", ctx, residual - d.value, "MW",
            terms={"residual_i1": residual, "d4_balance_defect_mw": d.value},
            detail={"delta_if_declared_negated": residual + d.value},
        ))
    else:
        out.append(not_evaluable("I1d", ctx, d.reason()))
    return out


# --------------------------------------------------------------------------
# I2a -- supply summation;  I2b -- job attribution
# --------------------------------------------------------------------------
def check_i2a(ctx: TickCtx) -> list[ResidualRecord]:
    v, p, bad = _nums(ctx.payload, "turbine_output_mw", "bess_output_mw",
                      "p_renewable_mw", "p_generation_mw")
    if bad:
        return [not_evaluable("I2a", ctx, bad)]
    residual = (v["turbine_output_mw"] + v["bess_output_mw"] + v["p_renewable_mw"]
                - v["p_generation_mw"])
    return [evaluated("I2a", ctx, residual, "MW", terms={**v, "_paths": p})]


def check_i2b(ctx: TickCtx) -> list[ResidualRecord]:
    km = resolve(ctx.payload, *ALIASES["kube_metrics"])
    if not km.ok:
        return [not_evaluable("I2b", ctx, f"kube path unavailable ({km.reason()})")]
    v, p, bad = _nums(ctx.payload, "p_compute_demand_mw", "admitted_nodes", "kw_per_node")
    if bad:
        return [not_evaluable("I2b", ctx, bad)]
    node_mw = v["admitted_nodes"] * v["kw_per_node"] / 1000.0
    return [evaluated("I2b", ctx, v["p_compute_demand_mw"] - node_mw, "MW",
                      terms={**v, "node_derived_mw": node_mw, "_paths": p})]


# --------------------------------------------------------------------------
# I3 -- tri-field.
#
# Site level is a tautology: p_served_mw is defined as p_demand_mw minus
# cumulative shed, and p_unserved_mw is that shed, so the sum is p_demand_mw by
# construction. It is retained as an arithmetic-consistency check with no
# physics content. The per-block form carries slightly more, because it applies
# a proportional split whose fractions could fail to sum to one.
# --------------------------------------------------------------------------
def _tri(ctx, name, served_key, unserved_key, demand_key):
    v, p, bad = _nums(ctx.payload, served_key, unserved_key, demand_key)
    if bad:
        return not_evaluable(name, ctx, bad)
    residual = v[served_key] + v[unserved_key] - v[demand_key]
    return evaluated(name, ctx, residual, "MW", terms={**v, "_paths": p})


def check_i3(ctx: TickCtx) -> list[ResidualRecord]:
    return [
        _tri(ctx, "I3_site", "p_served_mw", "p_unserved_mw", "p_demand_mw"),
        _tri(ctx, "I3_compute", "p_compute_served_mw", "p_compute_unserved_mw",
             "p_compute_demand_mw"),
        _tri(ctx, "I3_cooling", "p_cooling_served_mw", "p_cooling_unserved_mw",
             "p_cooling_demand_mw"),
    ]


# --------------------------------------------------------------------------
# I4 -- asset rating. Signed margin is emitted; positive means above nameplate.
# Ratings are read from the tick itself, never from the catalogue, because they
# are per-scenario.
# --------------------------------------------------------------------------
def check_i4(ctx: TickCtx) -> list[ResidualRecord]:
    out: list[ResidualRecord] = []

    units = resolve(ctx.payload, *ALIASES["turbine_units"])
    if not units.ok or not isinstance(units.value, list):
        out.append(not_evaluable("I4_turbine", ctx, units.reason() or "turbine_units not a list"))
    else:
        for i, _ in enumerate(units.value):
            subject = f"turbine_units[{i}]"
            o = resolve_number(ctx.payload, f"turbine_units[{i}].output_mw")
            r = resolve_number(ctx.payload, f"turbine_units[{i}].rated_mw")
            if not o.ok or not r.ok:
                out.append(not_evaluable("I4_turbine", ctx,
                                         (o if not o.ok else r).reason(), subject=subject))
                continue
            margin = o.value - r.value
            out.append(evaluated("I4_turbine", ctx, margin, "MW", subject=subject,
                                 terms={"output_mw": o.value, "rated_mw": r.value},
                                 detail={"exceedance_mw": max(0.0, margin)}))

    b_out = resolve_number(ctx.payload, *ALIASES["bess_output_mw"])
    b_rat = resolve_number(ctx.payload, *ALIASES["bess_rated_mw"])
    if b_out.ok and b_rat.ok:
        margin = abs(b_out.value) - b_rat.value
        out.append(evaluated("I4_bess", ctx, margin, "MW", subject="bess",
                             terms={"bess_output_mw": b_out.value,
                                    "bess_rated_mw": b_rat.value},
                             detail={"exceedance_mw": max(0.0, margin),
                                     "direction": "charge" if b_out.value < 0 else "discharge"}))
    else:
        out.append(not_evaluable("I4_bess", ctx,
                                 (b_out if not b_out.ok else b_rat).reason(), subject="bess"))

    c_dem = resolve_number(ctx.payload, *ALIASES["p_cooling_demand_mw"])
    c_rat = resolve_number(ctx.payload, *ALIASES["rated_cooling_mw"])
    if c_dem.ok and c_rat.ok:
        margin = c_dem.value - c_rat.value
        out.append(evaluated("I4_cooling", ctx, margin, "MW", subject="cooling",
                             terms={"p_cooling_demand_mw": c_dem.value,
                                    "rated_cooling_mw": c_rat.value},
                             detail={"exceedance_mw": max(0.0, margin)}))
    else:
        out.append(not_evaluable("I4_cooling", ctx,
                                 (c_dem if not c_dem.ok else c_rat).reason(), subject="cooling"))
    return out


# --------------------------------------------------------------------------
# I5 -- storage energy accounting. Needs a predecessor tick.
# Primary integration is trapezoidal; the rectangular variant is carried in
# detail so the choice of scheme is visible rather than assumed.
# --------------------------------------------------------------------------
def check_i5(ctx: TickCtx) -> list[ResidualRecord]:
    if ctx.prev is None:
        return [not_evaluable("I5", ctx, "no predecessor tick (first tick of recording)")]
    v, p, bad = _nums(ctx.payload, "bess_soc_fraction", "bess_output_mw",
                      "bess_usable_mwh", "sim_time_seconds")
    if bad:
        return [not_evaluable("I5", ctx, bad)]
    pv, _, pbad = _nums(ctx.prev.payload, "bess_soc_fraction", "bess_output_mw",
                        "sim_time_seconds")
    if pbad:
        return [not_evaluable("I5", ctx, f"predecessor: {pbad}")]

    dt = v["sim_time_seconds"] - pv["sim_time_seconds"]
    if dt <= 0:
        return [not_evaluable("I5", ctx, f"non-positive dt ({dt})")]

    energy_soc = (pv["bess_soc_fraction"] - v["bess_soc_fraction"]) * v["bess_usable_mwh"]
    p_avg = (pv["bess_output_mw"] + v["bess_output_mw"]) / 2.0
    energy_trap = p_avg * dt / 3600.0
    energy_rect = v["bess_output_mw"] * dt / 3600.0

    return [evaluated(
        "I5", ctx, energy_soc - energy_trap, "MWh",
        terms={"dt_s": dt, "soc_prev": pv["bess_soc_fraction"],
               "soc_now": v["bess_soc_fraction"],
               "bess_usable_mwh": v["bess_usable_mwh"],
               "p_avg_mw": p_avg, "_paths": p},
        detail={"energy_from_soc_mwh": energy_soc,
                "energy_from_power_trapezoid_mwh": energy_trap,
                "energy_from_power_rectangular_mwh": energy_rect,
                "residual_rectangular_mwh": energy_soc - energy_rect},
    )]


# --------------------------------------------------------------------------
# I6 -- fleet capacity and reserve-floor reconstruction.
#
# floor_violated never reaches the wire, so it is reconstructed here and the
# reconstruction is compared against the reported reserve_satisfied. The demand
# basis the commitment path actually uses is not documented on the wire, so both
# candidates are computed and the report says which one reproduces the reported
# floor.
# --------------------------------------------------------------------------
def check_i6(ctx: TickCtx) -> list[ResidualRecord]:
    units = resolve(ctx.payload, *ALIASES["turbine_units"])
    if not units.ok or not isinstance(units.value, list):
        return [not_evaluable("I6_committed", ctx, units.reason() or "turbine_units not a list"),
                not_evaluable("I6_floor", ctx, units.reason() or "turbine_units not a list")]

    on_bus_rated: list[float] = []
    hot_standby_seen = False
    for i, u in enumerate(units.value):
        if not isinstance(u, dict):
            continue
        state = u.get("state")
        if not isinstance(state, str) or state.strip().lower() != SYNCHRONISED:
            continue
        if "hot_standby" in u:
            hot_standby_seen = True
            if bool(u.get("hot_standby")):
                continue
        r = resolve_number(ctx.payload, f"turbine_units[{i}].rated_mw")
        if not r.ok:
            return [not_evaluable("I6_committed", ctx, r.reason()),
                    not_evaluable("I6_floor", ctx, r.reason())]
        on_bus_rated.append(r.value)

    recomputed_committed = sum(on_bus_rated)
    largest = max(on_bus_rated) if on_bus_rated else 0.0

    rep_c = resolve_number(ctx.payload, *ALIASES["committed_rated_mw"])
    rep_f = resolve_number(ctx.payload, *ALIASES["reserve_floor_mw"])
    rep_s = resolve(ctx.payload, *ALIASES["reserve_satisfied"])
    action = resolve(ctx.payload, *ALIASES["commitment_action"])
    p_dem = resolve_number(ctx.payload, *ALIASES["p_demand_mw"])
    n_dem = resolve_number(ctx.payload, *ALIASES["net_demand_mw"])

    shared_detail = {
        "on_bus_count": len(on_bus_rated),
        "largest_on_bus_rated_mw": largest,
        "hot_standby_present_on_wire": hot_standby_seen,
    }

    out: list[ResidualRecord] = []

    if rep_c.ok:
        floor_p = p_dem.value + largest if p_dem.ok else None
        violated = (recomputed_committed < floor_p) if floor_p is not None else None
        satisfied = rep_s.value if rep_s.ok and isinstance(rep_s.value, bool) else None
        agree = (None if violated is None or satisfied is None
                 else ((not violated) == satisfied))
        out.append(evaluated(
            "I6_committed", ctx, recomputed_committed - rep_c.value, "MW",
            terms={"recomputed_committed_mw": recomputed_committed,
                   "reported_committed_rated_mw": rep_c.value},
            detail={**shared_detail,
                    "reconstructed_floor_violated": violated,
                    "reported_reserve_satisfied": satisfied,
                    "agree": agree,
                    "commitment_action": action.value if action.ok else None,
                    "hold_with_unsatisfied_reserve":
                        (satisfied is False
                         and isinstance(action.value, str)
                         and action.value.strip().lower() == "hold") if action.ok else None},
        ))
    else:
        out.append(not_evaluable("I6_committed", ctx, rep_c.reason()))

    if rep_f.ok and (p_dem.ok or n_dem.ok):
        d_p = (p_dem.value + largest - rep_f.value) if p_dem.ok else None
        d_n = (n_dem.value + largest - rep_f.value) if n_dem.ok else None
        primary = d_p if d_p is not None else d_n
        out.append(evaluated(
            "I6_floor", ctx, primary, "MW",
            terms={"reported_reserve_floor_mw": rep_f.value,
                   "largest_on_bus_rated_mw": largest,
                   "p_demand_mw": p_dem.value if p_dem.ok else None,
                   "net_demand_mw": n_dem.value if n_dem.ok else None},
            detail={**shared_detail,
                    "residual_using_p_demand_mw": d_p,
                    "residual_using_net_demand_mw": d_n},
        ))
    else:
        reason = rep_f.reason() if not rep_f.ok else "no demand basis available"
        out.append(not_evaluable("I6_floor", ctx, reason))

    return out


CHECKERS: dict[str, Callable[[TickCtx], list[ResidualRecord]]] = {
    "I1": check_i1, "I2a": check_i2a, "I2b": check_i2b,
    "I3": check_i3, "I4": check_i4, "I5": check_i5, "I6": check_i6,
}


def run_all(ctx: TickCtx) -> list[ResidualRecord]:
    out: list[ResidualRecord] = []
    for fn in CHECKERS.values():
        out.extend(fn(ctx))
    return out
