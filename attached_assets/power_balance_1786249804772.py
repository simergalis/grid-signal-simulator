"""Phase 0 -- the power balance identity, computed rather than declared.

`d4_balance_defect_mw` currently reads 0.0 on every tick of every recording while
an independent recomputation shows up to 18.05 MW. This module computes the
identity so the field carries the quantity its name claims.

Nothing here enforces the identity. Enforcement is phases 1-4 (bounded droop,
swing forcing, bidirectional BESS, reachable UFLS). This phase makes the
violation visible and gates the console on it, so a run that does not close
cannot be rendered as though it did.

Pure functions. No I/O, no clock, no RNG.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

ISLANDED = "islanded"
GRID_TIE = "grid_tie"

# Sign convention for grid_exchange_mw: positive means import into the site.
#
# UNVERIFIED. Every recording captured so far is islanded, so grid_exchange_mw is
# identically 0.0 and the convention cannot be determined from data. It must be
# confirmed against the first grid-connected recording before any grid-tie
# balance figure is trusted. Recorded here as a named constant rather than an
# assumption buried in an expression.
GRID_EXCHANGE_POSITIVE_IS_IMPORT = True


@dataclass(frozen=True)
class BalanceTerms:
    """Inputs to the identity, in MW except where noted."""
    p_generation_mw: float          # turbine + BESS + renewable, as p_generation_mw
    p_demand_mw: float              # total site demand before any shed
    p_unserved_mw: float = 0.0      # load shed by UFLS or curtailment
    grid_exchange_mw: float = 0.0   # zero when islanded
    p_losses_mw: float = 0.0        # zero unless the model represents losses
    island_mode: str = ISLANDED


@dataclass(frozen=True)
class BalanceResult:
    defect_mw: float                # generation + import - served - losses
    served_mw: float
    import_mw: float
    closes: bool | None             # None when no tolerance was supplied
    tolerance_mw: float | None
    terms: BalanceTerms


def served_load_mw(terms: BalanceTerms) -> float:
    """Load actually carried: total demand less whatever was shed.

    `p_served_mw` on the wire is not this quantity in any useful sense -- it is
    demand minus commanded shed, so it equals demand whenever nothing has been
    commanded, regardless of whether the generation existed. That definition is
    why an 18 MW deficit reports as fully served. This function reconstructs the
    intended meaning from demand and shed directly.
    """
    return terms.p_demand_mw - terms.p_unserved_mw


def balance_defect_mw(terms: BalanceTerms) -> float:
    """Signed identity residual. Positive means surplus generation.

    Islanded, this quantity must be zero at every instant: there is nowhere for
    surplus to go and nothing to supply a deficit. A non-zero value is not a
    measurement of anything physical -- it is the amount by which the model has
    failed to close, and it should drive frequency once phase 2 lands.
    """
    imp = terms.grid_exchange_mw if terms.island_mode != ISLANDED else 0.0
    if not GRID_EXCHANGE_POSITIVE_IS_IMPORT:
        imp = -imp
    return terms.p_generation_mw + imp - served_load_mw(terms) - terms.p_losses_mw


def evaluate(terms: BalanceTerms, tolerance_mw: float | None = None) -> BalanceResult:
    d = balance_defect_mw(terms)
    imp = terms.grid_exchange_mw if terms.island_mode != ISLANDED else 0.0
    return BalanceResult(
        defect_mw=d,
        served_mw=served_load_mw(terms),
        import_mw=imp,
        closes=None if tolerance_mw is None else abs(d) <= tolerance_mw,
        tolerance_mw=tolerance_mw,
        terms=terms,
    )


# ---------------------------------------------------------------------------
# Noise-floor calibration
#
# The tolerance is derived from recordings believed healthy, not chosen. Applying
# a guessed tolerance is how a real defect gets classified as rounding.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class NoiseFloor:
    n: int
    max_abs: float
    p99_abs: float
    p999_abs: float
    suggested_tolerance_mw: float
    basis: str


def calibrate_noise_floor(defects: Sequence[float], *,
                          headroom_multiple: float = 10.0,
                          basis: str = "unspecified") -> NoiseFloor:
    """Suggest a tolerance from residuals on runs believed to close.

    The suggestion is `headroom_multiple` times the p99.9 magnitude, so genuine
    floating-point noise passes with room to spare while anything of physical
    size does not. It is an output for review, never applied automatically: a
    tolerance derived from a run that itself violates the identity would
    enshrine the violation.
    """
    vals = sorted(abs(float(d)) for d in defects)
    if not vals:
        raise ValueError("no residuals supplied")
    return NoiseFloor(
        n=len(vals),
        max_abs=vals[-1],
        p99_abs=_quantile(vals, 0.99),
        p999_abs=_quantile(vals, 0.999),
        suggested_tolerance_mw=_quantile(vals, 0.999) * headroom_multiple,
        basis=basis,
    )


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


# ---------------------------------------------------------------------------
# Console gate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GateVerdict:
    renderable: bool
    reason: str | None
    worst_defect_mw: float
    worst_index: int | None
    n_violating: int


def gate_run(defects: Iterable[float], tolerance_mw: float) -> GateVerdict:
    """Decide whether a completed run may be presented.

    A run whose identity does not close is not a run with one bad number in it;
    every derived figure on the console -- reserve margin, N-1 firm capacity,
    served load -- rests on the same terms. Rendering it implies a consistency
    that is absent.
    """
    worst, worst_i, n_bad = 0.0, None, 0
    for i, d in enumerate(defects):
        if abs(d) > tolerance_mw:
            n_bad += 1
        if abs(d) > abs(worst):
            worst, worst_i = float(d), i
    if n_bad == 0:
        return GateVerdict(True, None, worst, worst_i, 0)
    return GateVerdict(
        False,
        (f"power balance identity does not close on {n_bad} tick(s); worst "
         f"{worst:+.4g} MW at index {worst_i} against a tolerance of "
         f"{tolerance_mw:g} MW"),
        worst, worst_i, n_bad,
    )
