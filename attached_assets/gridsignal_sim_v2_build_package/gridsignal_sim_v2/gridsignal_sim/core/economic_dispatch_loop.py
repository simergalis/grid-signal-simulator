"""economic_dispatch_loop.py — EconomicDispatchLoop: per-tick steady-state dispatch.

GS-IMPL-PSP-002 §3.2 / §2.3.

Phase 2 corrects three defects from the Phase 1 reference implementation.
Phase 2 post-review applies two additional corrections before Phase 3:

  DEFECT-1 (§2.3.1) — RESOLVED:
    Phase 1 had `total_cost_per_hour` assuming a full hour per tick.
    Phase 2 renames to `cost_this_tick` and computes:
      Σ(allocated_mw × price_mwh × tick_duration_hours)
    where `tick_duration_hours` is passed into step() explicitly.

  DEFECT-2 (PSP-5 / §3.2.1) — RESOLVED:
    Phase 1 had `_pge_price_for_hour()` which was summer-only and used
    hardcoded rates from an older tariff.
    Phase 2: sources all rates from the parameter catalogue; handles the
    Winter Super Off-Peak window (Mar–May, hours 9–13) requiring month.

  DEFECT-3 (PSP-6 / §7) — RESOLVED in PowerRanker.rank() (not here):
    BESS catalogue-sourcing belongs in PowerRanker.rank() so both the
    autonomous dispatch path AND the §4.3 escalation path (which calls
    rank() directly, bypassing step()) see the same catalogue cost.
    step() no longer overrides BESS cost — that was the wrong scope.

  POST-REVIEW CORRECTION A — `season` dropped from step() signature:
    `season` is fully derivable from `month` (6–9 → summer, 10–5 → winter);
    no month value is ambiguous about season.  Carrying both as independent
    parameters created a silent-wrong-value risk (month=7, season="winter"
    would not raise).  `season` is now derived inside `_season_from_month()`
    from `month`.  This shrinks the signature back toward Phase 1's shape
    plus only the two new required fields (tick_duration_hours, month).

  POST-REVIEW CORRECTION B — BESS repricing removed from step():
    step() now reprices grid sources only (TOU is legitimately tick-context-
    dependent).  BESS repricing is PowerRanker.rank()'s responsibility.

New signature (keyword-only after t_s — §1 / Phase 2 review note)
------------------------------------------------------------------
  step(t_s, *, tick_duration_hours, hour_of_day, month, demand_mw, sources)

  The bare `*` after `t_s` is intentional: any positional caller after t_s
  receives TypeError immediately.  Zero callers existed at Phase 2 gate.

Import boundary (§1)
--------------------
  This file lives in core/.  It MAY import from:
    - core/ (parameter catalogue, other core modules)
    - standard library
  It MUST NOT import from runtime/ or scripts/.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

import core.site_parameters as _sp
from core.power_source_priority import (
    AdvisoryOutput,
    AuthorityTier,
    PowerRanker,
    PowerSource,
    PowerSourceType,
    RankedSource,
)


# ── Output data contracts (§2.3 / §2.3.1 Phase 2 correction) ─────────────────

@dataclass
class DispatchAllocation:
    """One source's allocation for this tick (§2.3)."""
    t_s: float
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

    Phase 2 changes vs. Phase 1
    ----------------------------
    - `total_cost_per_hour` renamed to `cost_this_tick` (§2.3.1).
    - `cost_this_tick` = Σ(allocated_mw × price_mwh × tick_duration_hours)
      where tick_duration_hours is the actual duration of this tick in hours,
      NOT assumed to be 1.0.
    """
    t_s: float
    allocations: List[DispatchAllocation]
    cost_this_tick: float          # USD; was total_cost_per_hour in Phase 1
    shortfall: Optional[ShortfallEvent]


# ── TOU pricing helpers (post-review corrections) ─────────────────────────────

def _season_from_month(month: int) -> Literal["summer", "winter"]:
    """Derive the PG&E B-20 season from calendar month.

    Summer: Jun 1 – Sep 30  (months 6–9)
    Winter: Oct 1 – May 31  (months 10–12 and 1–5)

    month is the single authoritative input.  season is presentation-layer,
    fully derivable — there is no month value that is ambiguous about season.
    Carrying both as independent parameters would allow silent wrong-value bugs
    (e.g. month=7, season="winter") without a TypeError.
    """
    return "summer" if month in (6, 7, 8, 9) else "winter"


def _pge_price_for_period(hour_of_day: int, month: int) -> tuple[float, str]:
    """Return (rate_mwh, cost_basis_note) for the given hour and month.

    All rates read from the parameter catalogue (GS-IMPL-PSP-002 §7).
    No hardcoded fallback — if a catalogue read fails, the exception propagates
    to the caller (§7 / ParameterUnavailable).

    Season derived internally via _season_from_month().  Callers supply only
    month — post-review correction A removes season from the public API.

    Period classification per Cal. P.U.C. Sheet 61081-E (eff. 2026-03-01)
    -----------------------------------------------------------------------
    Summer (months 6–9):
      Peak         hour_of_day 16–20  ($177.02/MWh)
      Part-peak    hour_of_day 14–15 and 21–22  ($142.27/MWh)
      Off-peak     all other summer hours  ($114.82/MWh)

    Winter (months 10–12, 1–5):
      Super Off-Peak  months 3–5 AND hour_of_day 9–13  ($58.72/MWh)
      Peak            hour_of_day 16–20  ($156.32/MWh)
      Off-peak        all other winter hours  ($114.60/MWh)
    """
    season = _season_from_month(month)

    if season == "summer":
        if hour_of_day in (16, 17, 18, 19, 20):
            rate = _sp.value("pge_tou_summer_peak_mwh")
            note = f"PG&E B-20 summer peak (hour {hour_of_day})"
        elif hour_of_day in (14, 15, 21, 22):
            rate = _sp.value("pge_tou_summer_part_peak_mwh")
            note = f"PG&E B-20 summer part-peak (hour {hour_of_day})"
        else:
            rate = _sp.value("pge_tou_summer_off_peak_mwh")
            note = f"PG&E B-20 summer off-peak (hour {hour_of_day})"
    else:  # winter
        if month in (3, 4, 5) and hour_of_day in (9, 10, 11, 12, 13):
            rate = _sp.value("pge_tou_winter_super_off_peak_mwh")
            note = f"PG&E B-20 winter super off-peak (month {month}, hour {hour_of_day})"
        elif hour_of_day in (16, 17, 18, 19, 20):
            rate = _sp.value("pge_tou_winter_peak_mwh")
            note = f"PG&E B-20 winter peak (month {month}, hour {hour_of_day})"
        else:
            rate = _sp.value("pge_tou_winter_off_peak_mwh")
            note = f"PG&E B-20 winter off-peak (month {month}, hour {hour_of_day})"

    return rate, note


# ── EconomicDispatchLoop ──────────────────────────────────────────────────────

class EconomicDispatchLoop:
    """Steady-state economic dispatch after §7 Dispatch Arbitration (§3.2 / §4.2).

    This loop runs AFTER §7 Dispatch Arbitration has resolved the current tick's
    transient response.  It reallocates the resulting steady-state load across
    autonomous-tier sources in merit order.  It is NOT a replacement for §7 and
    MUST NOT be inserted before or interleaved with §7 (§6.4 / §4.2 ordering).

    Stateless — each step() call is independent.

    Post-review changes (applied before Phase 3)
    ---------------------------------------------
    - `season` dropped from step() signature; derived internally from `month`.
    - BESS repricing removed from step(); now in PowerRanker.rank() so both
      the autonomous dispatch path and the §4.3 escalation path see the same cost.
    - step() reprices grid sources only (TOU is legitimately tick-context-dependent).
    """

    def step(
        self,
        t_s: float,
        *,                          # all remaining args are keyword-only
        tick_duration_hours: float, # (§2.3.1) — duration of this tick in hours
        hour_of_day: int,           # local hour (0–23) for TOU classification
        month: int,                 # calendar month (1–12); season derived internally
        demand_mw: float,           # steady-state demand after §7 resolves
        sources: List[PowerSource], # all sources, all authority tiers
    ) -> DispatchResult:
        """Dispatch one tick.

        Parameters
        ----------
        t_s
            Simulated time in seconds since run start.
        tick_duration_hours
            Duration of this tick in hours.  E.g. a 5-second tick = 5/3600 h.
            Used in cost_this_tick = Σ(allocated_mw × price × tick_duration_hours).
        hour_of_day
            Local hour (0–23) of the simulated calendar time.
        month
            Calendar month (1–12) of the simulated date.  Season is derived
            internally via _season_from_month() — callers do not supply season
            separately (post-review correction A).
        demand_mw
            Steady-state demand to cover (P_total(t) after §7 has resolved).
        sources
            All sources available this tick, at all authority tiers.
            This method filters to autonomous-tier only (step 3 — mandatory,
            not configurable per §6.3).

        Returns
        -------
        DispatchResult
            allocations + cost_this_tick + optional shortfall.
        """
        # Step 1: reprice grid sources for current TOU period.
        # BESS is repriced by PowerRanker.rank() — not here (post-review correction B).
        repriced: List[PowerSource] = []
        for src in sources:
            if src.source_type in (
                PowerSourceType.GRID_FIRM,
                PowerSourceType.GRID_RESERVED,
                PowerSourceType.GRID_SPOT,
            ):
                tou_price, tou_note = _pge_price_for_period(hour_of_day, month)
                repriced.append(PowerSource(
                    source_id=src.source_id,
                    source_type=src.source_type,
                    dispatchable=src.dispatchable,
                    counts_toward_reserve=src.counts_toward_reserve,
                    marginal_cost_mwh=tou_price,
                    response_latency_class=src.response_latency_class,
                    authority_tier=src.authority_tier,
                    available_mw=src.available_mw,
                    cost_basis_note=tou_note,
                ))
            else:
                repriced.append(src)

        # Step 2: rank all repriced sources.
        advisory: AdvisoryOutput = PowerRanker().rank(repriced)

        # Step 3: filter to autonomous tier only — mandatory, not configurable (§6.3).
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

        # Step 5: cost calculation (§2.3.1 Phase 2 correction).
        # cost_this_tick = Σ(allocated_mw × price_mwh × tick_duration_hours)
        # tick_duration_hours is the actual tick length, NOT assumed to be 1.0.
        cost_this_tick: float = sum(
            a.allocated_mw * a.price_mwh * tick_duration_hours
            for a in allocations
        )

        # Step 6: emit ShortfallEvent if demand unmet.  Do not raise, do not
        # retry, do not reach for confirm/human_only — return and let the
        # caller handle escalation per §4.3.
        shortfall: Optional[ShortfallEvent] = None
        if remaining_mw > 1e-9:
            shortfall = ShortfallEvent(
                t_s=t_s,
                demand_mw=demand_mw,
                covered_mw=covered_mw,
                shortfall_mw=remaining_mw,
            )

        return DispatchResult(
            t_s=t_s,
            allocations=allocations,
            cost_this_tick=cost_this_tick,
            shortfall=shortfall,
        )
