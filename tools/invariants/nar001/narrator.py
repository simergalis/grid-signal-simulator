"""Deterministic template narrator -- grammar over a FrameFact. No model.

This is the floor the feature cannot drop below, and it is built before any model
is wired in. If the template alone is not useful, a model will not rescue it.

Every numeral it writes is copied from the FrameFact. It originates none, infers
no trend, recommends no action, and when an invariant is failing it says so
first -- because prose over an unreconciled frame is worse than silence.
"""
from __future__ import annotations

from typing import Any

from .framefact import FrameFact

# Plain-language expansions. A facilities manager or an executive visitor is the
# reader, so jargon is expanded on first use.
GLOSS = {
    "I1": "the power going out does not match the power coming in",
    "I2a": "the individual sources do not add up to the reported total",
    "I2b": "compute draw does not match the number of nodes admitted",
    "I3_site": "served plus unserved load does not equal demand",
    "I3_compute": "the compute block's served and unserved figures do not "
                  "reconcile",
    "I3_cooling": "the cooling block's served and unserved figures do not "
                  "reconcile",
    "I4_turbine": "a generator is reported above its rated output",
    "I4_bess": "the battery is reported above its rated power",
    "I4_cooling": "cooling is reported above its rated capacity",
    "I5": "the battery's charge level and its measured power do not agree",
    "I6_committed": "the committed generation does not match the units on the bus",
    "I6_floor": "the reserve floor does not match a recomputation",
    "I6_agreement": "the reserve status disagrees with a recomputation from the "
                    "unit states",
}

DIRECTION_WORD = {"rising": "climbing", "falling": "falling",
                  "oscillating": "moving up and down without settling"}

DOMAIN_WORD = {"SCHED": "the job scheduler", "LOAD": "site load",
               "GEN": "generation", "DEMAND": "the forecast",
               "RENEW": "solar", "THERM": "cooling", "VERDICT": "status"}

# A domain word is too coarse to name a trend: describing bess_soc_fraction as
# "generation ... falling to 0.76 fraction" tells a non-technical reader that
# generation is failing when the battery is simply discharging.
SIGNAL_PHRASE = {
    "LOAD.p_demand_mw": "total site draw",
    "LOAD.p_compute_demand_mw": "compute draw",
    "LOAD.net_demand_mw": "the load the generators have to cover",
    "LOAD.p_served_mw": "load being served",
    "LOAD.p_unserved_mw": "load not being served",
    "THERM.p_cooling_demand_mw": "cooling draw",
    "THERM.ambient_avg_c": "ambient temperature",
    "THERM.compute_inlet_temp_c": "cooling inlet temperature",
    "GEN.turbine_output_mw": "generator output",
    "GEN.p_generation_mw": "total generation",
    "GEN.bess_output_mw": "battery output",
    "GEN.bess_soc_fraction": "battery charge level",
    "GEN.committed_rated_mw": "committed generating capacity",
    "GEN.reserve_floor_mw": "the reserve the site is required to hold",
    "GEN.frequency_hz": "grid frequency",
    "GEN.d4_balance_defect_mw": "the reported gap between supply and demand",
    "GEN.shed_required_mw": "the load that would have to be shed",
    "RENEW.p_renewable_mw": "solar output",
    "RENEW.p_expected_mw": "expected solar output",
    "DEMAND.forecast_mw": "the demand forecast",
    "SCHED.dt_lead_next_s": "the notice before the next compute step",
}

UNIT_WORD = {"MW": "MW", "fraction": "", "Hz": "Hz", "degC": "°C", "s": "seconds"}

# A reader cannot hold six named faults at once, and the point is that the
# figures are untrustworthy, not which six.
MAX_NAMED_FAULTS = 3


def _mw(v: Any) -> str:
    return "—" if v is None else f"{v:.2f} MW"


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def headline(ff: FrameFact) -> str:
    if ff.invariants_failed:
        return "Readings do not add up — treat the figures below with caution."
    if ff.state.get("hold_with_unsatisfied_reserve"):
        return "Reserve is short of its floor and no unit is being started."
    action = ff.state.get("commitment_action")
    if action == "commit":
        return "Starting another generator."
    if action == "decommit":
        return "Shutting a generator down."
    if not ff.changes and not ff.trends:
        return "Nothing changed in this window."
    n = len(ff.changes)
    return f"{n} {_plural(n, 'change', 'changes')} in this window."


def body(ff: FrameFact) -> str:
    parts: list[str] = []

    if ff.invariants_failed:
        named = ff.invariants_failed[:MAX_NAMED_FAULTS]
        extra = len(ff.invariants_failed) - len(named)
        names = [GLOSS.get(i, i) for i in named]
        tail = f", and {extra} other {_plural(extra, 'check', 'checks')}" if extra else ""
        parts.append(
            "The site's own numbers are inconsistent: "
            + "; ".join(names) + tail
            + ". Until that is resolved, the rest of this summary is not "
              "reliable.")
        resid = ff.state.get("power_balance_residual_mw")
        if resid not in (None, 0.0):
            parts.append(f"The gap between generation and demand is {_mw(resid)}.")

    dem = ff.state.get("p_demand_mw")
    gen = ff.state.get("p_generation_mw")
    if dem is not None:
        if gen is None:
            parts.append(f"The site is drawing {_mw(dem)}.")
        elif _mw(gen) == _mw(dem):
            # "26.48 MW against 26.48 MW" reads as though something is wrong
            parts.append(f"The site is drawing {_mw(dem)}, matched by generation.")
        else:
            parts.append(f"The site is drawing {_mw(dem)} against {_mw(gen)} "
                         f"of generation.")

    unserved = ff.state.get("p_unserved_mw")
    if unserved:
        parts.append(f"{_mw(unserved)} of demand is not being served.")

    for t in ff.trends[:2]:
        word = DIRECTION_WORD.get(t["direction"])
        if not word:
            continue
        subject = SIGNAL_PHRASE.get(
            t["signal"], DOMAIN_WORD.get(t["domain"], t["domain"]))
        s = (f"{subject} has been {word} "
             f"over the last {int(t['window_s'])} seconds")
        if t["direction"] in ("rising", "falling"):
            unit = UNIT_WORD.get(t["units"] or "", t["units"] or "")
            s += f", from {t['first']:.2f} to {t['last']:.2f} {unit}".rstrip()
            if t["step_count"]:
                s += (f", in {t['step_count']} "
                      f"{_plural(t['step_count'], 'step', 'steps')}")
        parts.append(s + ".")

    if ff.state.get("hold_with_unsatisfied_reserve"):
        parts.append(
            f"Committed generation is {_mw(ff.state.get('committed_rated_mw'))} "
            f"against a reserve floor of "
            f"{_mw(ff.state.get('reserve_floor_mw'))}, and the last decision was "
            f"to hold.")

    if ff.n_changes_dropped:
        parts.append(f"{ff.n_changes_dropped} further "
                     f"{_plural(ff.n_changes_dropped, 'change was', 'changes were')} "
                     f"not listed.")

    if not parts:
        parts.append("No readings moved far enough to report.")
    return " ".join(parts)


def narrate(ff: FrameFact) -> dict[str, Any]:
    """Return the same shape a model would be asked for, so the two are
    interchangeable and the fallback path is never a different code path."""
    h, b = headline(ff), body(ff)
    return {
        "headline": h,
        "body": b,
        "numbers_used": sorted(_numerals(h) | _numerals(b)),
        "source": "template",
        "as_of_s": ff.window_to_s if ff.window_to_s is not None
        else ff.state.get("sim_time_s"),
        "invariants_failed": list(ff.invariants_failed),
    }


def _numerals(text: str) -> set[str]:
    out, cur = set(), ""
    for ch in text:
        if ch.isdigit() or (ch == "." and cur) or (ch == "-" and not cur):
            cur += ch
        else:
            if cur.strip("-."):
                out.add(cur.rstrip("."))
            cur = ""
    if cur.strip("-."):
        out.add(cur.rstrip("."))
    return out
