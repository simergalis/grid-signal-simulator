"""
core/contingency.py — Contingency coverage computation (§7.4, §7.5).

Implements `evaluate_contingency(plant_state) -> ContingencyCoverage`:
a pure function with no I/O, no clock access, and no simulation state
mutation.  Called once per tick from evaluate_tick() in simulation_core.py
after dispatch arbitration is complete.

Two independent tests per §7.4:
  Power test  — can the BESS carry the instantaneous deficit?
  Energy test — does the BESS have stored energy to sustain until turbines close?

The two are kept separate through the ContingencyCoverage return value so
the display layer (TC-78) and tests can inspect them individually.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import ContingencyCoverage, ContingencyState, IslandMode


# ---------------------------------------------------------------------------
# Input snapshot types — read-only views of simulation state
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TurbineSnapshot:
    """Read-only view of one turbine for the contingency computation.

    is_synchronized: True when the unit is ramping or at target (RAMPING or
    AT_TARGET state); False for OFFLINE (hot standby or not commissioned).
    Hot-standby units must not contribute to r_surviving — their start time
    is a separate quantity that must not be folded into a ramp rate.
    """
    asset_id: str
    current_output_mw: float
    rated_mw: float
    r_asset_mw_per_s: float
    is_synchronized: bool


@dataclass(frozen=True)
class BessSnapshot:
    """Read-only view of one BESS unit for the contingency computation."""
    asset_id: str
    rated_mw: float
    soc_mwh: float           # current usable state of charge
    usable_mwh: float        # nameplate usable capacity
    p_anchor_reserve_mw: float
    grid_forming: bool


@dataclass(frozen=True)
class PlantState:
    """Complete read-only plant state snapshot for one contingency evaluation.

    turbine_snapshots: all turbines (online and standby) — the function
      selects online ones internally.
    bess_snapshots:    all BESS units.
    curtailable_capacity_mw: sum of §23.2 curtailment tier capacities
      (A+B+C+D, read from CurtailmentLadder.total_capacity_mw()).
    renewable_mw: current solar output — passed through to ContingencyCoverage
      so the UI can display it as a separate non-firm term (§7.5), but never
      enters any coverage arithmetic.
    """
    turbine_snapshots: tuple  # tuple[TurbineSnapshot, ...]
    bess_snapshots: tuple     # tuple[BessSnapshot, ...]
    island_mode: IslandMode
    curtailable_capacity_mw: float
    renewable_mw: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bess_bridging_mw(snap: BessSnapshot, island_mode: IslandMode) -> float:
    """Anchor-adjusted BESS power ceiling per §7.1.2.

    The anchor deduction applies only when BOTH:
      1. grid_forming is True (this unit is the designated anchor).
      2. The site is ISLANDED.
    In grid-tie mode or for grid-following units the deduction is zero.
    """
    anchor = (
        snap.p_anchor_reserve_mw
        if snap.grid_forming and island_mode == IslandMode.ISLANDED
        else 0.0
    )
    return max(0.0, snap.rated_mw - anchor)


# ---------------------------------------------------------------------------
# Core pure function
# ---------------------------------------------------------------------------

def evaluate_contingency(plant_state: PlantState) -> ContingencyCoverage:
    """Evaluate N−1 contingency coverage per §7.4 and §7.5.

    Deterministic: given identical PlantState inputs, returns identical
    ContingencyCoverage outputs (TC-77 / TC-82 property).

    Args:
        plant_state: frozen snapshot of the plant at the current tick.

    Returns:
        ContingencyCoverage with all intermediate results preserved so
        tests and display layers can inspect them individually.
    """
    island_mode = plant_state.island_mode

    # §7.5: dispatchable = online turbine rated capacity + anchor-adj BESS bridging.
    # "online turbine capacity" = rated MW of synchronized units (not hot standby).
    # Solar is EXCLUDED per §7.1.1 — it reduces the load the fleet must serve but
    # may never be credited toward closing a supply-side gap.
    bess_bridging_available_mw = sum(
        _bess_bridging_mw(b, island_mode) for b in plant_state.bess_snapshots
    )
    bess_usable_energy_mwh = sum(b.soc_mwh for b in plant_state.bess_snapshots)

    # Synchronized online = contributing to generation (not hot standby)
    online: list[TurbineSnapshot] = [
        t for t in plant_state.turbine_snapshots if t.is_synchronized
    ]

    dispatchable_mw = (
        sum(t.rated_mw for t in online) + bess_bridging_available_mw
    )

    # Degenerate case: no online turbines — no contingency to select
    if not online:
        return ContingencyCoverage(
            tripped_unit_id=None,
            deficit_mw=0.0,
            headroom_surviving_mw=0.0,
            r_surviving_mw_per_s=0.0,
            bess_bridging_available_mw=bess_bridging_available_mw,
            bess_usable_energy_mwh=bess_usable_energy_mwh,
            power_test_passes=True,
            energy_test_passes=True,
            closable=True,
            time_to_close_s=0.0,
            shed_required_mw=0.0,
            ride_through_s=(
                bess_usable_energy_mwh * 3600.0 / 1e-9 if bess_usable_energy_mwh else math.inf
            ),
            state=ContingencyState.COVERED,
            dispatchable_mw=dispatchable_mw,
            renewable_mw=plant_state.renewable_mw,
        )

    # §7.4 — contingency selection: online dispatchable with greatest CURRENT output.
    # Selection is by current output, not rated capacity (TC-77).
    tripped = max(online, key=lambda t: t.current_output_mw)
    deficit_mw = tripped.current_output_mw

    # Surviving synchronized units (all online except the tripped unit)
    surviving: list[TurbineSnapshot] = [
        t for t in online if t.asset_id != tripped.asset_id
    ]

    # Surviving headroom: Σ(rated_i − current_output_i) for surviving online units
    headroom_surviving_mw = sum(
        max(0.0, t.rated_mw - t.current_output_mw) for t in surviving
    )

    # Surviving ramp capability: synchronized units ONLY (TC-83).
    # Hot-standby units are already excluded from `online`; this is a no-op guard
    # that makes the exclusion explicit for reviewers.
    r_surviving_mw_per_s = sum(t.r_asset_mw_per_s for t in surviving)

    # Power test (§7.4): can the BESS carry the instantaneous deficit?
    power_test_passes = bess_bridging_available_mw >= deficit_mw

    # Closability (§7.4): can surviving turbines reach the deficit?
    # If headroom is insufficient, no amount of BESS energy closes it.
    closable = headroom_surviving_mw >= deficit_mw

    # Time to close and energy test (§7.4)
    if closable and r_surviving_mw_per_s > 0.0:
        # Deficit declines linearly at r_surviving → triangular wedge
        time_to_close_s = deficit_mw / r_surviving_mw_per_s
        e_required_mwh = 0.5 * deficit_mw * time_to_close_s / 3600.0
        energy_test_passes = bess_usable_energy_mwh >= e_required_mwh
    else:
        # Not closable, or closable but surviving ramp rate is zero:
        # deficit never returns to zero → energy requirement is infinite
        time_to_close_s = math.inf
        energy_test_passes = False

    # Shed required when deficit is not closable by generation alone
    shed_required_mw = max(0.0, deficit_mw - headroom_surviving_mw)

    # Ride-through duration (§7.4): approximate time BESS can hold the deficit
    if deficit_mw > 0.0:
        ride_through_s = bess_usable_energy_mwh * 3600.0 / deficit_mw
    else:
        ride_through_s = math.inf

    # State (§7.4): three states, each with conditions
    if closable and power_test_passes and energy_test_passes:
        state = ContingencyState.COVERED
    elif shed_required_mw <= plant_state.curtailable_capacity_mw:
        # Curtailment can close the gap (including the closable-but-BESS-fails
        # case, where shed_required_mw = 0 so this always passes)
        state = ContingencyState.COVERED_WITH_SHED
    else:
        state = ContingencyState.CANNOT_CARRY

    return ContingencyCoverage(
        tripped_unit_id=tripped.asset_id,
        deficit_mw=deficit_mw,
        headroom_surviving_mw=headroom_surviving_mw,
        r_surviving_mw_per_s=r_surviving_mw_per_s,
        bess_bridging_available_mw=bess_bridging_available_mw,
        bess_usable_energy_mwh=bess_usable_energy_mwh,
        power_test_passes=power_test_passes,
        energy_test_passes=energy_test_passes,
        closable=closable,
        time_to_close_s=time_to_close_s,
        shed_required_mw=shed_required_mw,
        ride_through_s=ride_through_s,
        state=state,
        dispatchable_mw=dispatchable_mw,
        renewable_mw=plant_state.renewable_mw,
    )
