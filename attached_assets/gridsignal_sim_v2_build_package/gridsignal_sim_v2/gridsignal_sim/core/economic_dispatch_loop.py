"""economic_dispatch_loop.py — EconomicDispatchLoop: per-tick steady-state dispatch.

GS-IMPL-PSP-002 §3.2 / §2.3.

Phase 2 corrects two defects that were present in the Phase 1 reference
implementation and are now resolved:

  DEFECT-1 (§2.3.1) — RESOLVED:
    Phase 1 had `total_cost_per_hour` assuming a full hour per tick.
    Phase 2 renames to `cost_this_tick` and computes:
      Σ(allocated_mw × price_mwh × tick_duration_hours)
    where `tick_duration_hours` is passed into step() explicitly.

  DEFECT-2 (PSP-5 / §3.2.1) — RESOLVED:
    Phase 1 had `_pge_price_for_hour()` which was summer-only and used
    hardcoded rates from an older tariff.
    Phase 2:
      - Sources all rates from the parameter catalogue via site_parameters.value().
      - Takes `season` and `month` as explicit parameters.
      - Handles the Winter Super Off-Peak window (Mar–May, hours 9–13) which
        requires month, not just season, to price correctly.

  DEFECT-3 (PSP-6 / §7) — RESOLVED:
    BESS sources now receive their marginal cost from the catalogue
    (`bess_marginal_cost_mwh`) rather than whatever was on PowerSource at
    construction time.  This ensures the catalogue's provisional $38/MWh
    Method-A value is the authoritative cost basis, not a caller-supplied guess.

New signature (keyword-only after t_s — §1 / Phase 2 review note)
------------------------------------------------------------------
  step(t_s, *, tick_duration_hours, hour_of_day, month, season, demand_mw, sources)

  The bare `*` after `t_s` is intentional: tick_duration_hours (2nd) and month
  (4th) are inserted into what was a positional argument list.  Any caller
  supplying arguments positionally will receive a TypeError immediately rather
  than silently computing wrong costs.  There are currently zero callers to
  migrate (confirmed by grep at Phase 2 gate).

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


# ── TOU pricing helper (Phase 2 — season+month-aware, catalogue-sourced) ──────

def _pge_price_for_period(
    hour_of_day: int,
    month: int,
    season: Literal["summer", "winter"],
) -> tuple[float, str]:
    """Return (rate_mwh, cost_basis_note) for the given time period.

    All rates read from the parameter catalogue (GS-IMPL-PSP-002 §7).
    No hardcoded fallback — if a catalogue read fails, the exception propagates
    to the caller, which is the correct behaviour (§7 / ParameterUnavailable).

    Season boundaries (caller's responsibility, per §3.2.1)
    -------------------------------------------------------
      Summer: Jun 1 – Sep 30  (months 6–9)
      Winter: Oct 1 – May 31  (months 10–12, 1–5)

    Period classification per Cal. P.U.C. Sheet 61081-E (eff. 2026-03-01)
    -----------------------------------------------------------------------
    Summer (months 6–9):
      Peak       hour_of_day 16–20  ($177.02/MWh)
      Part-peak  hour_of_day 14–15 and 21–22  ($142.27/MWh)
      Off-peak   all other summer hours  ($114.82/MWh)

    Winter (months 10–12, 1–5):
      Super Off-Peak  months 3–5 AND hour_of_day 9–13  ($58.72/MWh)
      Peak            hour_of_day 16–20  ($156.32/MWh)
      Off-peak        all other winter hours  ($114.60/MWh)

    The Super Off-Peak window requires month, not just season — this is why
    the Phase 1 `season: Literal["summer","winter"]` signature was insufficient
    and Phase 2 adds `month: int` explicitly.
    """
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


def _bess_marginal_cost() -> float:
    """Return the BESS marginal dispatch cost from the parameter catalogue.

    DEFECT-3 resolution: BESS cost is no longer caller-supplied.  The catalogue
    entry `bess_marginal_cost_mwh` ($38.00/MWh provisional, Method A) is the
    authoritative source.  If PSP-6 were still open, this would raise
    ParameterUnavailable, propagating loudly rather than silently defaulting.
    """
    return _sp.value("bess_marginal_cost_mwh")


# ── EconomicDispatchLoop ──────────────────────────────────────────────────────

class EconomicDispatchLoop:
    """Steady-state economic dispatch after §7 Dispatch Arbitration (§3.2 / §4.2).

    This loop runs AFTER §7 Dispatch Arbitration has resolved the current tick's
    transient response.  It reallocates the resulting steady-state load across
    autonomous-tier sources in merit order.  It is NOT a replacement for §7 and
    MUST NOT be inserted before or interleaved with §7 (§6.4 / §4.2 ordering).

    Stateless — each step() call is independent.

    Phase 2 changes vs. Phase 1
    ----------------------------
    - step() signature: added `tick_duration_hours`, `month`, `season` (keyword-only).
    - DispatchResult: `total_cost_per_hour` → `cost_this_tick` (correct formula).
    - Grid pricing: reads from catalogue via `_pge_price_for_period()` (season+month).
    - BESS pricing: reads from catalogue via `_bess_marginal_cost()`.
    """

    def step(
        self,
        t_s: float,
        *,                              # all remaining args are keyword-only
        tick_duration_hours: float,     # NEW (§2.3.1) — duration of this tick in hours
        hour_of_day: int,               # local hour (0–23) for TOU classification
        month: int,                     # calendar month (1–12) for Super Off-Peak
        season: Literal["summer", "winter"],  # NEW (§3.2.1) — derived by caller
        demand_mw: float,               # steady-state demand after §7 resolves
        sources: List[PowerSource],     # all sources, all authority tiers
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
            Calendar month (1–12) of the simulated date.  Required to distinguish
            the Winter Super Off-Peak window (Mar–May, 9am–2pm) from regular
            winter off-peak — a distinction season alone cannot express.
        season
            "summer" (Jun–Sep) or "winter" (Oct–May).  The caller derives this
            from the simulated calendar date; this module does not read a clock
            (§3.2.1 / §6.2 no-runtime-clock-reads rule).
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
        # Step 1: reprice grid and BESS sources for current TOU period.
        repriced: List[PowerSource] = []
        for src in sources:
            if src.source_type in (
                PowerSourceType.GRID_FIRM,
                PowerSourceType.GRID_RESERVED,
                PowerSourceType.GRID_SPOT,
            ):
                tou_price, tou_note = _pge_price_for_period(hour_of_day, month, season)
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
            elif src.source_type == PowerSourceType.BESS:
                # DEFECT-3 resolution: BESS cost from catalogue, not caller.
                bess_cost = _bess_marginal_cost()
                repriced.append(PowerSource(
                    source_id=src.source_id,
                    source_type=src.source_type,
                    dispatchable=src.dispatchable,
                    counts_toward_reserve=src.counts_toward_reserve,
                    marginal_cost_mwh=bess_cost,
                    response_latency_class=src.response_latency_class,
                    authority_tier=src.authority_tier,
                    available_mw=src.available_mw,
                    cost_basis_note="catalogue: bess_marginal_cost_mwh (Method A, provisional)",
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
