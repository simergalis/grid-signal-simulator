"""Phase 0 -- the power balance identity, computed rather than declared.

The legacy `d4_balance_defect_mw` field is a routing decomposition check. This
module also computes the authoritative physical supply/load identity so the
quantity is evaluated once and can be reused by all consumers.

Nothing here enforces the identity. Enforcement is phases 1-4 (bounded droop,
swing forcing, bidirectional BESS, reachable UFLS). This phase makes the
violation visible and gates the console on it, so a run that does not close
cannot be rendered as though it did.

Pure functions. No I/O, no clock, no RNG.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

ISLANDED = "islanded"
GRID_TIE = "grid_tie"
ISLANDED_VERIFIED = "islanded_verified"
GRID_TIED_PROVISIONAL = "grid_tied_provisional"

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
    p_generation_mw: float          # aggregate local generation producer
    p_demand_mw: float              # total site demand before any shed
    p_unserved_mw: float = 0.0      # load shed by UFLS or curtailment
    grid_exchange_mw: float = 0.0   # zero when islanded
    p_losses_mw: float = 0.0        # zero unless the model represents losses
    island_mode: str = ISLANDED
    # The simulation already computes served/unserved load before the invariant
    # runs.  Keeping it optional preserves the older BalanceTerms API used by
    # calibration and unit tests; the physical invariant supplies it explicitly.
    p_served_mw: float | None = None
    # Independent source terms are diagnostic only; p_generation_mw remains the
    # authoritative aggregate producer and is never recomputed from consumers.
    p_turbine_mw: float = 0.0
    p_bess_mw: float = 0.0
    p_fuel_cell_mw: float = 0.0
    p_renewable_mw: float = 0.0


@dataclass(frozen=True)
class BalanceResult:
    defect_mw: float                # generation + import - served - losses
    served_mw: float
    import_mw: float
    closes: bool | None             # None when no tolerance was supplied
    tolerance_mw: float | None
    terms: BalanceTerms

    @property
    def independent(self) -> bool:
        """Whether the grid term comes from an independent physical boundary."""
        return str(self.terms.island_mode).lower() == ISLANDED

    @property
    def verification_mode(self) -> str:
        """Authority of this ledger result, not whether its residual is small."""
        return (
            ISLANDED_VERIFIED
            if self.independent
            else GRID_TIED_PROVISIONAL
        )

    @property
    def passed(self) -> bool:
        """Whether this evaluated identity closes at its supplied tolerance."""
        return self.closes is True

    @property
    def residual_magnitude_mw(self) -> float:
        """Absolute size of the signed identity defect."""
        return abs(self.defect_mw)

    @property
    def term_breakdown(self) -> dict[str, float]:
        """Plain, serializable ledger terms used by monitoring and persistence."""
        t = self.terms
        return {
            "generation_mw": t.p_generation_mw,
            "demand_mw": t.p_demand_mw,
            "turbine_mw": t.p_turbine_mw,
            "bess_mw": t.p_bess_mw,
            "fuel_cell_mw": t.p_fuel_cell_mw,
            "renewable_mw": t.p_renewable_mw,
            "grid_exchange_mw": t.grid_exchange_mw,
            "grid_import_mw": self.import_mw,
            "served_load_mw": self.served_mw,
            "unserved_load_mw": t.p_unserved_mw,
            "losses_mw": t.p_losses_mw,
            "supply_mw": t.p_generation_mw + self.import_mw,
            "accounted_load_mw": (
                self.served_mw + t.p_unserved_mw + t.p_losses_mw
            ),
            "source_sum_mw": (
                t.p_turbine_mw
                + t.p_bess_mw
                + t.p_fuel_cell_mw
                + t.p_renewable_mw
            ),
        }

    def to_dict(self) -> dict:
        """Return the stable wire/persistence representation of this result."""
        return {
            "passed": self.passed,
            "independent": self.independent,
            "verification_mode": self.verification_mode,
            "defect_mw": self.defect_mw,
            "residual_magnitude_mw": self.residual_magnitude_mw,
            "tolerance_mw": self.tolerance_mw,
            "terms": self.term_breakdown,
        }


def served_load_mw(terms: BalanceTerms) -> float:
    """Load actually carried: total demand less whatever was shed.

    The load-side value is intentionally independent of supply. A generation
    deficit remains visible in the balance residual and p_imbalance_mw rather
    than being silently absorbed into the served/unserved split.
    """
    if terms.p_served_mw is not None:
        return terms.p_served_mw
    return terms.p_demand_mw - terms.p_unserved_mw


def balance_defect_mw(terms: BalanceTerms) -> float:
    """Signed identity residual. Positive means surplus generation.

    Islanded, this quantity must be zero at every instant: there is nowhere for
    surplus to go and nothing to supply a deficit. A non-zero value is not a
    measurement of anything physical -- it is the amount by which the model has
    failed to close, and it should drive frequency once phase 2 lands.
    """
    imp = (
        0.0
        if str(terms.island_mode).lower() == ISLANDED
        else terms.grid_exchange_mw
    )
    if not GRID_EXCHANGE_POSITIVE_IS_IMPORT:
        imp = -imp
    return terms.p_generation_mw + imp - served_load_mw(terms) - terms.p_losses_mw


def evaluate(terms: BalanceTerms, tolerance_mw: float | None = None) -> BalanceResult:
    d = balance_defect_mw(terms)
    imp = (
        0.0
        if str(terms.island_mode).lower() == ISLANDED
        else terms.grid_exchange_mw
    )
    return BalanceResult(
        defect_mw=d,
        served_mw=served_load_mw(terms),
        import_mw=imp,
        closes=None if tolerance_mw is None else abs(d) <= tolerance_mw,
        tolerance_mw=tolerance_mw,
        terms=terms,
    )


def evaluate_physical_balance(
    terms: BalanceTerms,
    *,
    tolerance_mw: float,
) -> BalanceResult:
    """Evaluate the authoritative physical per-tick ledger invariant.

    Unlike the legacy D4 routing check, islanded mode compares independently
    computed supply and load ledger terms:

        generation + grid import
          = served load + unserved load + represented losses

    Grid-tied results remain provisional because current PCC exchange is routed
    from the same supply-demand residual. The serialized verification mode makes
    that distinction explicit. The tolerance is required at this boundary so
    callers cannot accidentally turn a missing catalogue value into an implicit
    pass.
    """
    if (
        tolerance_mw is None
        or not math.isfinite(tolerance_mw)
        or tolerance_mw < 0
    ):
        raise ValueError("physical balance invariant requires a non-negative tolerance")
    return evaluate(terms, tolerance_mw=tolerance_mw)


# ---------------------------------------------------------------------------
# Noise-floor calibration
#
# The tolerance is derived from recordings believed healthy, not chosen. Applying
# a guessed tolerance is how a real defect gets classified as rounding.
# ---------------------------------------------------------------------------
class DegenerateCalibration(ValueError):
    """Raised when a residual sample cannot support a noise floor.

    A sample of exact zeros is not a measured floor -- it is an absence of
    evidence. `demo-baseline` produces exactly this: 11 ticks of an idle site
    where the arithmetic happens to cancel, yielding a suggested tolerance of
    0.0. That tolerance would then block the first genuinely correct run whose
    MW-scale sums leave float rounding of order 1e-15.

    Calibrate instead on a residual that is structurally the same kind of sum and
    is actually exercised -- I2a (turbine + bess + renewable - p_generation_mw)
    across all recorded ticks is the intended source.
    """


@dataclass(frozen=True)
class NoiseFloor:
    n: int
    n_nonzero: int
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
    n_nonzero = sum(1 for v in vals if v != 0.0)
    if n_nonzero == 0:
        raise DegenerateCalibration(
            f"all {len(vals)} residuals in basis {basis!r} are exactly zero; a "
            f"floor of 0.0 would block the first correct run that leaves float "
            f"rounding. Calibrate on a residual that is actually exercised.")
    return NoiseFloor(
        n=len(vals),
        n_nonzero=n_nonzero,
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
