"""economic_dispatch_loop.py — EconomicDispatchLoop: per-tick steady-state dispatch.

GS-IMPL-PSP-002 §3.2 / §2.3.

This is the Phase 1 reference implementation.  It contains two known defects
that Phase 2 will correct:

  DEFECT-1 (§2.3.1): The `total_cost_per_hour` field on DispatchResult assumes
    a full hour of dispatch at every tick.  Phase 2 renames it to `cost_this_tick`
    and requires it be computed as Σ(allocated_mw × price × tick_duration_hours),
    where tick_duration_hours is passed into step() explicitly.

  DEFECT-2 (PSP-5 / §3.2.1): `_pge_price_for_hour()` is summer-only.  Phase 2
    adds a `season` parameter and a `month` parameter to correctly handle winter
    TOU periods, including the Super Off-Peak window (Mar–May, 9am–2pm) that
    cannot be expressed by season alone.

Do not fix either defect in this file during Phase 1.  Phase 2's diff must show
the before/after clearly.

Import boundary (§1)
--------------------
  This file lives in core/.  It MAY import from:
    - core/ (parameter catalogue, other core modules)
    - standard library
  It MUST NOT import from runtime/ or scripts/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.power_source_priority import (
    AdvisoryOutput,
    AuthorityTier,
    PowerRanker,
    PowerSource,
    PowerSourceType,
    RankedSource,
)


# ── Output data contracts (§2.3) ──────────────────────────────────────────────

@dataclass
class DispatchAllocation:
    """One source's allocation for this tick (§2.3)."""
    t_s: float          # simulated seconds since run start
    source_id: str
    allocated_mw: float
    price_mwh: float


@dataclass
class ShortfallEvent:
    """Emitted when autonomous sources cannot cover demand (§2.3 / §4.3)."""
    t_s: float
    demand_mw: float
    covered_mw: float
    shortfall_mw: float


@dataclass
class DispatchResult:
    """Full output of one EconomicDispatchLoop.step() call (§2.3).

    DEFECT-1 NOTE: `total_cost_per_hour` is the Phase 1 name.  It will be
    renamed to `cost_this_tick` in Phase 2, and the computation will change
    from the current "assume 1 hour" assumption to an explicit tick_duration_hours
    argument.  Do not introduce callers that depend on the field name before
    Phase 2 is complete.
    """
    t_s: float
    allocations: List[DispatchAllocation]
    total_cost_per_hour: float   # DEFECT-1: renamed + recomputed in Phase 2
    shortfall: Optional[ShortfallEvent]


# ── TOU pricing helper (summer-only — DEFECT-2, corrected in Phase 2) ─────────

# Phase 1 hardcoded summer rates.
# NOTE: These values are WRONG (pre-March-2026 tariff).
# Phase 2 replaces them with catalogue reads from site_parameters.value()
# using the corrected Cal. PUC Sheet 61081-E values catalogued in Phase 0.
_SUMMER_PEAK_MWH: float      = 177.02   # hour_of_day 16–20
_SUMMER_PART_PEAK_MWH: float = 142.27   # hour_of_day 14–15, 21–22
_SUMMER_OFF_PEAK_MWH: float  = 114.82   # all other summer hours


def _pge_price_for_hour(hour_of_day: int) -> float:
    """Return the PG&E B-20 summer energy rate for *hour_of_day* (0–23).

    DEFECT-2: Summer-only.  Phase 2 adds season + month parameters and reads
    the full winter table (including Super Off-Peak) from the parameter catalogue.

    Hour boundaries (Cal. PUC Sheet 61081-E, effective 2026-03-01):
      Peak:       16–20  (4pm–9pm)
      Part-peak:  14–15  (2pm–4pm) and 21–22 (9pm–11pm)
      Off-peak:   all remaining hours
    """
    if hour_of_day in (16, 17, 18, 19, 20):
        return _SUMMER_PEAK_MWH
    if hour_of_day in (14, 15, 21, 22):
        return _SUMMER_PART_PEAK_MWH
    return _SUMMER_OFF_PEAK_MWH


# ── EconomicDispatchLoop ──────────────────────────────────────────────────────

class EconomicDispatchLoop:
    """Steady-state economic dispatch after §7 Dispatch Arbitration (§3.2 / §4.2).

    This loop runs AFTER §7 Dispatch Arbitration has resolved the current tick's
    transient response.  It reallocates the resulting steady-state load across
    autonomous-tier sources in merit order.  It is NOT a replacement for §7 and
    MUST NOT be inserted before or interleaved with §7 (§6.4 / §4.2 ordering).

    Stateless — each step() call is independent.

    Phase 1 defects (corrected in Phase 2)
    ---------------------------------------
    DEFECT-1: total_cost_per_hour assumes 1 hour of dispatch per tick.
    DEFECT-2: _pge_price_for_hour is summer-only; no season or month awareness.
    """

    def step(
        self,
        t_s: float,
        hour_of_day: int,
        demand_mw: float,
        sources: List[PowerSource],
    ) -> DispatchResult:
        """Dispatch one tick.

        Parameters
        ----------
        t_s
            Simulated time in seconds since run start.
        hour_of_day
            Local hour (0–23) of the simulated calendar time, for TOU pricing.
            DEFECT-2: Phase 2 adds `season` and `month` alongside this.
        demand_mw
            Steady-state demand to cover (P_total(t) after §7 has resolved).
        sources
            All sources available this tick, at all authority tiers.
            EconomicDispatchLoop filters to autonomous-tier only (step 3).

        Returns
        -------
        DispatchResult
            allocations + total_cost_per_hour (DEFECT-1) + optional shortfall.
        """
        # Step 1: reprice grid sources for current TOU period.
        repriced: List[PowerSource] = []
        for src in sources:
            if src.source_type in (
                PowerSourceType.GRID_FIRM,
                PowerSourceType.GRID_RESERVED,
                PowerSourceType.GRID_SPOT,
            ):
                tou_price = _pge_price_for_hour(hour_of_day)
                repriced.append(PowerSource(
                    source_id=src.source_id,
                    source_type=src.source_type,
                    dispatchable=src.dispatchable,
                    counts_toward_reserve=src.counts_toward_reserve,
                    marginal_cost_mwh=tou_price,
                    response_latency_class=src.response_latency_class,
                    authority_tier=src.authority_tier,
                    available_mw=src.available_mw,
                    cost_basis_note=f"PG&E B-20 summer, hour_of_day={hour_of_day}",
                ))
            else:
                repriced.append(src)

        # Step 2: rank all repriced sources.
        advisory: AdvisoryOutput = PowerRanker().rank(repriced)

        # Step 3: filter to autonomous tier only — this filter is NOT optional
        # and NOT configurable (§6.3 / §3.2 step 3).
        autonomous_ranked: List[RankedSource] = [
            rs for rs in advisory.ranked_sources
            if rs.authority_tier == AuthorityTier.AUTONOMOUS
        ]

        # Step 4: greedy allocation, cheapest-first.
        allocations: List[DispatchAllocation] = []
        remaining_mw: float = demand_mw

        for ranked_src in autonomous_ranked:
            if remaining_mw <= 0.0:
                break
            allocated_mw = min(ranked_src.available_mw, remaining_mw)
            allocations.append(DispatchAllocation(
                t_s=t_s,
                source_id=ranked_src.source_id,
                allocated_mw=allocated_mw,
                price_mwh=ranked_src.marginal_cost_mwh,
            ))
            remaining_mw -= allocated_mw

        covered_mw = demand_mw - remaining_mw

        # Step 5: cost calculation.
        # DEFECT-1: Assumes 1 hour of dispatch per tick.  Phase 2 replaces
        # with: Σ(allocated_mw × price × tick_duration_hours), where
        # tick_duration_hours is passed in as an explicit argument.
        total_cost_per_hour: float = sum(
            a.allocated_mw * a.price_mwh
            for a in allocations
        )

        # Step 6: emit ShortfallEvent if demand unmet.  Do not raise, do not
        # retry, do not reach for confirm/human_only — return and let the
        # caller handle escalation per §4.3.
        shortfall: Optional[ShortfallEvent] = None
        if remaining_mw > 1e-9:   # tolerance for floating-point noise
            shortfall = ShortfallEvent(
                t_s=t_s,
                demand_mw=demand_mw,
                covered_mw=covered_mw,
                shortfall_mw=remaining_mw,
            )

        return DispatchResult(
            t_s=t_s,
            allocations=allocations,
            total_cost_per_hour=total_cost_per_hour,
            shortfall=shortfall,
        )
