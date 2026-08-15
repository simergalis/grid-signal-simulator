"""Source-level generation bounds audit (per-tick).

Complements the D4 aggregate balance check (power_balance.py) by verifying that
each generation source reports a physically plausible value independently.

D4 only catches a mismatch between *total* supply and *total* demand; a single
source over-reporting by ΔMW while the grid slack absorbs the excess is invisible
to D4.  This module checks every source against its rated capacity and verifies
that the individual source outputs sum to the declared p_generation_mw aggregate.

Concrete failure D4 misses but this catches:
  solar reporting 3× rated_mw (Task #403) — p_renewable_mw > solar_ceiling

Pure functions. No I/O, no clock, no RNG.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# ---------------------------------------------------------------------------
# Headroom / tolerance constants
# ---------------------------------------------------------------------------

# Relative headroom beyond rated capacity before a violation is flagged.
# 1 % accounts for rounding / unit-conversion artefacts without hiding real
# over-reports.
_HEADROOM_FRAC: float = 0.01

# Absolute floor for headroom when rated_mw is very small (MW).
# Prevents false negatives on tiny assets where 1 % is sub-kW noise.
_HEADROOM_FLOOR_MW: float = 0.01

# Absolute tolerance for the aggregation identity:
#   turbine + bess + fc + solar ≈ p_generation_mw
# 100 W — tight enough to catch accounting bugs, wide enough to ignore float
# rounding across four additions.
_AGGREGATION_TOLERANCE_MW: float = 1e-4


def _ceiling(rated_mw: float) -> float:
    """Effective upper bound for a rated capacity, in MW."""
    return rated_mw + max(rated_mw * _HEADROOM_FRAC, _HEADROOM_FLOOR_MW)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceAuditTerms:
    """Rated capacities and measured outputs for one tick (all in MW).

    Callers supply both the measured tick fields and the rated capacities from
    the RunContext / TickResult config fields.  The audit function is then a
    pure function of this record.
    """
    # ── measured outputs (from TickResult) ─────────────────────────────────
    p_renewable_mw: float       # solar / wind output after curtailment
    turbine_output_mw: float    # gas turbine fleet actual output
    bess_output_mw: float       # BESS net output; discharge +, charge −
    fuel_cell_output_mw: float  # H₂ fuel cell output; 0.0 when absent
    p_generation_mw: float      # declared aggregate (already on TickResult)

    # ── rated capacities (from RunContext / TickResult config fields) ───────
    solar_rated_mw: float       # scenario solar nameplate (Σ SolarArray rated_mw)
    turbine_rated_mw: float     # Σ turbine unit rated_mw (ctx.turbine_rated_mw)
    bess_rated_mw: float        # Σ BESS unit rated_mw (tick.bess_rated_mw)
    fc_rated_mw: float          # fuel cell rated_mw; 0.0 when disabled


@dataclass(frozen=True)
class SourceAuditResult:
    """Outcome of one per-tick source audit."""
    violations: tuple[str, ...]  # empty tuple = clean tick
    terms: SourceAuditTerms


# ---------------------------------------------------------------------------
# Core audit function
# ---------------------------------------------------------------------------

def audit_tick(terms: SourceAuditTerms) -> SourceAuditResult:
    """Return a SourceAuditResult listing every bound violation for this tick.

    Checks performed:
      1. p_renewable_mw ≤ solar_rated_mw × (1 + ε)      — solar over-report
      2. p_renewable_mw ≥ 0                              — solar negative
      3. turbine_output_mw ≤ turbine_rated_mw × (1 + ε) — turbine over-rated
      4. turbine_output_mw ≥ 0                           — turbine negative
      5. bess_output_mw ≤ bess_rated_mw × (1 + ε)       — BESS discharge cap
      6. bess_output_mw ≥ −(bess_rated_mw × (1 + ε))    — BESS charge cap
      7. fuel_cell_output_mw ≤ fc_rated_mw × (1 + ε)    — FC over-rated
      8. fuel_cell_output_mw ≥ 0                         — FC negative
      9. turbine+bess+fc+solar ≈ p_generation_mw         — aggregation identity

    An empty violations tuple means the tick is clean.
    """
    viols: list[str] = []

    # ── 1 & 2: Solar / renewable ─────────────────────────────────────────────
    solar_ceil = _ceiling(terms.solar_rated_mw)
    if terms.p_renewable_mw > solar_ceil:
        viols.append(
            f"renewable_over_rated: p_renewable_mw={terms.p_renewable_mw:.4g} MW "
            f"exceeds solar_rated_mw={terms.solar_rated_mw:.4g} MW "
            f"(ceiling={solar_ceil:.4g} MW)"
        )
    if terms.p_renewable_mw < 0.0:
        viols.append(
            f"renewable_negative: p_renewable_mw={terms.p_renewable_mw:.4g} MW"
        )

    # ── 3 & 4: Turbine ───────────────────────────────────────────────────────
    turbine_ceil = _ceiling(terms.turbine_rated_mw)
    if terms.turbine_output_mw > turbine_ceil:
        viols.append(
            f"turbine_over_rated: turbine_output_mw={terms.turbine_output_mw:.4g} MW "
            f"exceeds turbine_rated_mw={terms.turbine_rated_mw:.4g} MW "
            f"(ceiling={turbine_ceil:.4g} MW)"
        )
    if terms.turbine_output_mw < 0.0:
        viols.append(
            f"turbine_negative: turbine_output_mw={terms.turbine_output_mw:.4g} MW"
        )

    # ── 5 & 6: BESS (signed: discharge positive, charge negative) ───────────
    bess_ceil = _ceiling(terms.bess_rated_mw)
    if terms.bess_output_mw > bess_ceil:
        viols.append(
            f"bess_over_rated: bess_output_mw={terms.bess_output_mw:.4g} MW "
            f"exceeds bess_rated_mw={terms.bess_rated_mw:.4g} MW "
            f"(ceiling={bess_ceil:.4g} MW)"
        )
    if terms.bess_output_mw < -bess_ceil:
        viols.append(
            f"bess_charge_over_rated: bess_output_mw={terms.bess_output_mw:.4g} MW "
            f"exceeds charge limit −{bess_ceil:.4g} MW"
        )

    # ── 7 & 8: Fuel cell ─────────────────────────────────────────────────────
    fc_ceil = _ceiling(terms.fc_rated_mw)
    if terms.fuel_cell_output_mw > fc_ceil:
        viols.append(
            f"fc_over_rated: fuel_cell_output_mw={terms.fuel_cell_output_mw:.4g} MW "
            f"exceeds fc_rated_mw={terms.fc_rated_mw:.4g} MW "
            f"(ceiling={fc_ceil:.4g} MW)"
        )
    if terms.fuel_cell_output_mw < 0.0:
        viols.append(
            f"fc_negative: fuel_cell_output_mw={terms.fuel_cell_output_mw:.4g} MW"
        )

    # ── 9: Aggregation identity ───────────────────────────────────────────────
    computed_gen = (
        terms.turbine_output_mw
        + terms.bess_output_mw
        + terms.fuel_cell_output_mw
        + terms.p_renewable_mw
    )
    agg_delta = abs(computed_gen - terms.p_generation_mw)
    if agg_delta > _AGGREGATION_TOLERANCE_MW:
        viols.append(
            f"generation_sum_mismatch: "
            f"turbine+bess+fc+solar={computed_gen:.6g} MW "
            f"≠ p_generation_mw={terms.p_generation_mw:.6g} MW "
            f"(delta={agg_delta:.3g} MW)"
        )

    return SourceAuditResult(violations=tuple(viols), terms=terms)


# ---------------------------------------------------------------------------
# Post-run gate
# ---------------------------------------------------------------------------

def gate_run(
    violations_per_tick: Sequence[tuple[str, ...]],
) -> tuple[bool, str | None, int]:
    """Decide whether a completed run may be presented.

    Returns (renderable, reason, n_violating_ticks).

    A run with any source violation is non-renderable: derived figures such as
    reserve margin and N-1 firm capacity depend on the generation values being
    physically meaningful.
    """
    n_bad = sum(1 for v in violations_per_tick if v)
    if n_bad == 0:
        return True, None, 0

    # Collect unique violation kinds (the word before the first ':') for the
    # summary message so the reason is readable without listing all ticks.
    seen_kinds: list[str] = []
    for tick_viols in violations_per_tick:
        for v in tick_viols:
            kind = v.split(":")[0]
            if kind not in seen_kinds:
                seen_kinds.append(kind)

    reason = (
        f"source audit failed on {n_bad} tick(s); "
        f"violation kind(s): {', '.join(seen_kinds)}"
    )
    return False, reason, n_bad
