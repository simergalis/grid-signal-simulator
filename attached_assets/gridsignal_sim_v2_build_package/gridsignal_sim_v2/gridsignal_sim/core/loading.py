"""
core/loading.py — Phase 1b: Loading layer (pure stateless function).

Evaluated every tick.  No instance attributes, no module globals, no
memoisation, no cached shares between calls.

Acceptance (TC-77): identical (A, T, P_fleet, outputs) yields identical
setpoints across calls, process restarts, and unit-ordering permutations.
The redistribution loop is order-independent: each unit's adjustment
depends only on its rated_mw (a property of the unit, not its list position)
and the sum of unclamped units' rated_mw.

Spec references: §1b (Task #196 Phase 1b).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .asset_modules import TurbineModule


# No module-level lead-time constant.
# ramp_capability() takes horizon_s as a parameter so there is exactly one
# lead-time source: the dispatch arbitrator's runtime dt_lead_seconds.
# (Task #198 item 3 — deleted LEAD_WINDOW_S to prevent dual-path divergence.)


# ---------------------------------------------------------------------------
# Core pure function
# ---------------------------------------------------------------------------

def compute_loading_setpoints(
    synchronised: "list[TurbineModule]",
    p_fleet: float,
) -> tuple[list[float], float]:
    """Compute per-unit setpoints for units in A.  Pure — no side effects.

    Args:
        synchronised: units with state SYNCHRONISED (allocated set A).
                      T (TRANSITIONAL) is empty until Phase 3;
                      P_allocated == P_fleet in this build.
        p_fleet:      fleet setpoint (gt_setpoint_mw from the droop block).

    Returns:
        (setpoints, sub_msl_surplus_mw)
        sub_msl_surplus_mw > 0 when P_fleet < Σ msl_i.  The fleet holds at
        the floor; the surplus is reported and not resolved here.

    Invariants:
        TC-77: order-independent — permuting synchronised yields the same
               setpoints (redistribution loop depends only on rated_mw values).
        TC-78: terminates within |A| passes (monotone residual, bounded set).
        sub_msl_surplus_mw populated and setpoints at floor when sub-MSL.
    """
    if not synchronised:
        return [], 0.0

    # P_allocated = P_fleet − Σ_{i∈T} output_i.  T is empty until Phase 3.
    p_allocated = p_fleet

    total_rated = sum(t.config.rated_mw for t in synchronised)
    if total_rated < 1e-9:
        return [0.0] * len(synchronised), 0.0

    msl_i = [t.config.p_min_stable_frac * t.config.rated_mw for t in synchronised]
    sum_msl = sum(msl_i)

    # ── Sub-MSL: feasible band lower bound ───────────────────────────────────
    if p_allocated < sum_msl - 1e-9:
        # Fleet cannot absorb demand below Σ msl without de-committing.
        # Hold at the floor; report surplus; do not route or resolve.
        sub_msl_surplus_mw = sum_msl - p_allocated
        return list(msl_i), sub_msl_surplus_mw

    # ── Normal case: P_allocated ∈ [Σ msl, Σ rated] ─────────────────────────
    # Initial share — matched droop: share_i = rated_i / Σ rated_j.
    shares = [t.config.rated_mw / total_rated for t in synchronised]
    setpoints = [s * p_allocated for s in shares]

    # ── Residual redistribution — terminates within |A| passes ───────────────
    # Each pass: identify clamped units, accumulate residual, redistribute
    # proportionally (by rated_mw) among unclamped units.
    # Order-independence: residual and unclamped_rated depend only on rated_mw
    # values, not on list position.
    n = len(synchronised)
    for _ in range(n):
        residual = 0.0
        unclamped: list[int] = []
        for i, t in enumerate(synchronised):
            lo = msl_i[i]
            hi = t.config.rated_mw
            if setpoints[i] < lo - 1e-9:
                residual += lo - setpoints[i]   # positive: we under-allocated
                setpoints[i] = lo
            elif setpoints[i] > hi + 1e-9:
                residual += hi - setpoints[i]   # negative: we over-allocated
                setpoints[i] = hi
            else:
                unclamped.append(i)
        if abs(residual) < 1e-9 or not unclamped:
            break
        unclamped_rated = sum(synchronised[i].config.rated_mw for i in unclamped)
        if unclamped_rated < 1e-9:
            break
        for i in unclamped:
            setpoints[i] += residual * synchronised[i].config.rated_mw / unclamped_rated

    return setpoints, 0.0


# ---------------------------------------------------------------------------
# Apply loading to SYNCHRONISED units (has side effects on output_mw)
# ---------------------------------------------------------------------------

def apply_loading(
    synchronised: "list[TurbineModule]",
    p_fleet: float,
    dt_seconds: float,
) -> float:
    """Compute setpoints and advance SYNCHRONISED unit outputs toward them.

    Movement toward setpoint, all units, both directions:
        output_i ← output_i + clamp(setpoint_i − output_i, −r_i·Δt, +r_i·Δt)

    Returns sub_msl_surplus_mw (0.0 when P_fleet ≥ Σ msl_i).
    No stored state — calling twice with the same inputs is idempotent for the
    setpoint computation, though output_mw will advance twice.
    """
    setpoints, sub_msl_surplus_mw = compute_loading_setpoints(synchronised, p_fleet)
    for t, sp in zip(synchronised, setpoints):
        delta = sp - t.output_mw()
        max_step = t.config.r_asset_mw_per_s * dt_seconds
        step = max(-max_step, min(max_step, delta))
        t.set_output(t.output_mw() + step)
    return sub_msl_surplus_mw


# ---------------------------------------------------------------------------
# Ramp capability over horizon H
# ---------------------------------------------------------------------------

def ramp_capability(horizon_s: float, turbines: "list[TurbineModule]") -> float:
    """Fleet ramp capability (MW) over horizon *horizon_s* seconds.

    Only units that are fully on-bus contribute; STARTING units contribute zero
    regardless of horizon (Task #198 item 2 — a unit not yet closed its breaker
    must not be banked as reserve; starts fail).

    For SYNCHRONISED (and legacy RAMPING / AT_TARGET — in A):
        contribution = min(r_i × horizon_s, max(0, rated_i − output_i))
    STARTING, OFFLINE, OUT_OF_SERVICE, TRANSITIONAL, and hot-standby units: 0.

    TC-79: headroom dominates when output_i ≈ 0.9 × rated_i — capability equals
           (rated_i − output_i), not r_i × horizon_s × n.
    TC-80 (corrected): STARTING units always contribute 0, regardless of horizon.
           Full credit appears only once the unit transitions to SYNCHRONISED.
    """
    from .asset_modules import TurbineState   # local import — avoids circular at module level

    total = 0.0
    for t in turbines:
        if t.config.hot_standby:
            continue
        if t.state == TurbineState.STARTING:
            pass   # zero — not on bus; starts fail; must not be banked as reserve
        elif t.is_synchronised:
            headroom = max(0.0, t.config.rated_mw - t.output_mw())
            total += min(t.config.r_asset_mw_per_s * horizon_s, headroom)
        # OFFLINE / OUT_OF_SERVICE / TRANSITIONAL: contribute 0
    return total
