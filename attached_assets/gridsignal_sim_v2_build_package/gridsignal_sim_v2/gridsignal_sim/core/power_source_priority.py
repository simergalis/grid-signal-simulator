"""power_source_priority.py — PowerRanker: merit-order source ranking advisory.

GS-IMPL-PSP-002 §3.1 / Functional Spec §29.

This module provides the *advisory* ranking of dispatchable power sources by
marginal cost.  It has no side effects, holds no state, and makes no southbound
writes (§6.1).  The output is strictly advisory — dispatch decisions rest with
the operator and the PMS (see ADVISORY_NOTE below).

Data contract
-------------
  Input:  list[PowerSource]   — all sources known to the dispatcher this tick
  Output: AdvisoryOutput      — ranked dispatchable sources + excluded list

Import boundary (§1)
--------------------
  This file lives in core/.  It MAY import from:
    - core/ (parameter catalogue, other core models)
    - standard library
  It MUST NOT import from runtime/ or scripts/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import core.site_parameters as _sp


# ── Source type / authority enumerations ──────────────────────────────────────

class PowerSourceType(str, Enum):
    """Taxonomy of dispatchable and non-dispatchable power sources (§2.1)."""
    SOLAR        = "solar"
    GRID_FIRM    = "grid_firm"
    GRID_RESERVED = "grid_reserved"
    GRID_SPOT    = "grid_spot"
    BESS         = "bess"
    TURBINE      = "turbine"
    FUEL_CELL    = "fuel_cell"


class AuthorityTier(str, Enum):
    """Dispatch authority tier per §23.4 / §24.3.

    Only AUTONOMOUS sources are allocated by EconomicDispatchLoop (§3.2 step 3).
    CONFIRM and HUMAN_ONLY sources appear in the advisory ranking but are never
    autonomously dispatched — they surface as escalation candidates after a
    ShortfallEvent (§4.3).
    """
    AUTONOMOUS  = "autonomous"
    CONFIRM     = "confirm"
    HUMAN_ONLY  = "human_only"


class ResponseLatencyClass(str, Enum):
    """Response-speed metadata for §2.1 (metadata only — not read by ranking logic).

    PSP-7 notes this is stored but not validated against the §7 asset table.
    It is present on PowerSource for future use and for human review, not
    for algorithmic selection.
    """
    INSTANT       = "instant"
    RAMP_LIMITED  = "ramp_limited"
    THERMAL_LAG   = "thermal_lag"
    NOT_COMMANDED = "not_commanded"


# ── Data contracts ─────────────────────────────────────────────────────────────

@dataclass
class PowerSource:
    """One power source as seen by the dispatcher this tick (§2.1).

    Fields
    ------
    source_id
        Unique per instance within a simulation run.
    source_type
        Determines eligibility for ranking (solar is always excluded).
    dispatchable
        Solar is always False; all other types default True.
    counts_toward_reserve
        Per §7.1 / §24.1.  Fuel cell and firmed-solar default False
        pending PSP-3 resolution.
    marginal_cost_mwh
        Current-period cost in USD/MWh.  For grid sources this is
        TOU-varying; for PPA sources (fuel cell, solar) it is flat.
        EconomicDispatchLoop reprices grid sources before calling rank().
    response_latency_class
        Metadata only — not read by ranking logic (PSP-7).
    authority_tier
        Determines whether EconomicDispatchLoop may allocate autonomously.
    available_mw
        Live telemetry.  Sources with available_mw <= 0 are excluded from
        the ranked list (they cannot contribute to demand coverage).
    cost_basis_note
        Human-readable provenance string, e.g. "PG&E B-20, off_peak_summer".
        Passed through to RankedSource unchanged.
    """
    source_id: str
    source_type: PowerSourceType
    dispatchable: bool
    counts_toward_reserve: bool
    marginal_cost_mwh: float
    response_latency_class: ResponseLatencyClass
    authority_tier: AuthorityTier
    available_mw: float
    cost_basis_note: Optional[str] = None


@dataclass
class RankedSource:
    """One source in the merit-order ranking (§2.2).

    Direct annotation of PowerSource — no new information beyond what was
    already in the source object.  Rank 1 = cheapest available dispatchable.
    """
    rank: int
    source_id: str
    source_type: PowerSourceType
    marginal_cost_mwh: float
    available_mw: float
    reserve_eligible: bool
    authority_tier: AuthorityTier
    cost_basis_note: Optional[str]


@dataclass
class AdvisoryOutput:
    """Output of PowerRanker.rank() (§2.2).

    ranked_sources
        Merit-ordered list of dispatchable sources, ascending by
        marginal_cost_mwh.  Solar and zero-available sources excluded.
    excluded_non_dispatchable
        source_ids of solar sources that were excluded from ranking
        (dispatchable=False by definition).
    note
        Fixed advisory-only disclaimer.  Must not be omitted from any
        surface that presents this output to an operator.
    """
    ranked_sources: List[RankedSource]
    excluded_non_dispatchable: List[str]   # solar source_ids
    note: str


# Fixed disclaimer — must appear on every advisory surface (§6.1 / §29.5).
ADVISORY_NOTE: str = (
    "This ranking is an advisory output only. "
    "GridSignal does not execute southbound writes. "
    "All dispatch decisions rest with the operator and the Power Management System."
)


# ── PowerRanker ───────────────────────────────────────────────────────────────

class PowerRanker:
    """Merit-order ranking of dispatchable power sources (§3.1).

    Stateless — every call to rank() is independent.  No hardware access,
    no side effects, no imports from runtime/ (§1 import boundary).

    Ranking algorithm
    -----------------
    1. Exclude solar (source_type == SOLAR) → excluded_non_dispatchable.
    2. Exclude dispatchable=False (handles any future non-dispatchable type).
    3. Exclude available_mw <= 0 (cannot contribute; avoids zero-MW phantom ranks).
    4. Reprice BESS sources from the parameter catalogue (§7 / §3.1 spec note).
    5. Sort remaining sources ascending by marginal_cost_mwh.
    6. Annotate each with its rank (1 = cheapest).
    7. Return AdvisoryOutput with ADVISORY_NOTE.

    **BESS catalogue repricing (step 4):** BESS `marginal_cost_mwh` is sourced
    here, in rank(), not in EconomicDispatchLoop.step().  This ensures both call
    paths — autonomous dispatch (step()) and human escalation (§4.3's fresh
    rank() over confirm/human_only sources) — see the same catalogue-sourced
    cost.  If BESS cost were only overridden inside step(), an operator advisory
    in the escalation path could show a different BESS cost than what the
    autonomous dispatch loop was actually using — a "two sources of truth" defect
    for a number that has exactly one authoritative source (§7).

    Note: sources with AuthorityTier.CONFIRM or HUMAN_ONLY are *included* in
    the ranked output.  EconomicDispatchLoop (§3.2 step 3) applies the
    autonomous-only filter itself; this module does not second-guess it.  The
    ranked output covers all authority tiers so the escalation path (§4.3) can
    use a fresh rank() call restricted to confirm/human_only sources without
    needing a separate module.
    """

    def rank(self, sources: List[PowerSource]) -> AdvisoryOutput:
        """Return a merit-ordered AdvisoryOutput for *sources*.

        Parameters
        ----------
        sources
            All sources known to the dispatcher for this tick.  May be
            empty; an empty list returns an empty ranked output (not an error).
        """
        excluded_non_dispatchable: List[str] = []
        eligible: List[PowerSource] = []

        # Load BESS catalogue cost once — applies to all BESS sources this tick.
        # Loaded lazily here rather than at import time so tests can reload
        # the catalogue (site_parameters.reload()) without module re-import.
        _bess_cost: Optional[float] = None

        for src in sources:
            if src.source_type == PowerSourceType.SOLAR:
                excluded_non_dispatchable.append(src.source_id)
            elif not src.dispatchable:
                excluded_non_dispatchable.append(src.source_id)
            elif src.available_mw <= 0.0:
                pass  # silently drop — zero-available is not an error
            else:
                # Step 4: reprice BESS from catalogue (§3.1 / §7).
                if src.source_type == PowerSourceType.BESS:
                    if _bess_cost is None:
                        _bess_cost = _sp.value("bess_marginal_cost_mwh")
                    src = PowerSource(
                        source_id=src.source_id,
                        source_type=src.source_type,
                        dispatchable=src.dispatchable,
                        counts_toward_reserve=src.counts_toward_reserve,
                        marginal_cost_mwh=_bess_cost,
                        response_latency_class=src.response_latency_class,
                        authority_tier=src.authority_tier,
                        available_mw=src.available_mw,
                        cost_basis_note="catalogue: bess_marginal_cost_mwh (Method A, provisional)",
                    )
                eligible.append(src)

        eligible.sort(key=lambda s: s.marginal_cost_mwh)

        ranked_sources: List[RankedSource] = [
            RankedSource(
                rank=i + 1,
                source_id=src.source_id,
                source_type=src.source_type,
                marginal_cost_mwh=src.marginal_cost_mwh,
                available_mw=src.available_mw,
                reserve_eligible=src.counts_toward_reserve,
                authority_tier=src.authority_tier,
                cost_basis_note=src.cost_basis_note,
            )
            for i, src in enumerate(eligible)
        ]

        return AdvisoryOutput(
            ranked_sources=ranked_sources,
            excluded_non_dispatchable=excluded_non_dispatchable,
            note=ADVISORY_NOTE,
        )
