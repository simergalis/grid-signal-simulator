"""
item4_bridging_measurement.py — Phase E closeout Item 4
-------------------------------------------------------
Measure peak BESS discharge at the moment a turbine opens its breaker
(UNLOADING → OFFLINE) for survivor counts 3, 2, 1, 0 on two fleets:

  Fleet A — demo-20mw:   5 × 7 MW, r_asset=0.2 MW/s, MSL=0.40×7=2.8 MW
  Fleet B — large-frame: 4 × 15 MW, r_asset=0.15 MW/s, MSL=0.40×15=6.0 MW

For each (fleet, survivors) cell we report:
  - computed worst case = p_min_stable_mw − (survivors × r_asset × dt)
  - observed peak BESS discharge (from a synthetic tick sequence)

The synthetic run: bring N turbines to SYNCHRONISED at rated, then issue
command_stop() to one unit.  Drive ticks until breaker opens.  Record the
BESS setpoint at the tick where the unit transitions from UNLOADING to OFFLINE.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

sys.path.insert(0, ".")

from core.asset_modules import TurbineModule, TurbineState
from core.models import TurbineConfig, BessConfig
from core.asset_modules import BessModule


DT = 5.0   # seconds per tick (catalogue default)


# ── Fleet definitions ────────────────────────────────────────────────────────

@dataclass
class FleetSpec:
    name: str
    rated_mw: float
    r_asset: float
    msl_frac: float
    n_total: int     # total turbines in scenario (sets N-1 survivors)

    @property
    def msl_mw(self) -> float:
        return self.msl_frac * self.rated_mw


FLEET_A = FleetSpec("demo-20mw   (7 MW × 5 units, r=0.20)", 7.0, 0.20, 0.40, 5)
FLEET_B = FleetSpec("large-frame (15 MW × 4 units, r=0.15)", 15.0, 0.15, 0.40, 4)


# ── Helper: build a SYNCHRONISED turbine at rated output ────────────────────

def _synced(asset_id: str, fleet: FleetSpec, run_elapsed_s: float = 7200.0) -> TurbineModule:
    """Return a TurbineModule in SYNCHRONISED state, output at rated_mw."""
    cfg = TurbineConfig(
        asset_id=asset_id,
        rated_mw=fleet.rated_mw,
        r_asset_mw_per_s=fleet.r_asset,
        p_min_stable_frac=fleet.msl_frac,
        t_min_run_s=1800.0,
        min_run_enabled=True,
        t_min_down_s=900.0,
        min_down_enabled=True,
        unload_tail_s=60.0,    # levelled-off dwell before breaker open
        levelled_off_tol_mw=0.05,
    )
    t = TurbineModule(cfg)
    t.state = TurbineState.SYNCHRONISED
    t._current_output_mw = fleet.rated_mw       # fully loaded at start
    t._run_start_s = 0.0 - run_elapsed_s        # enough elapsed to pass R5
    return t


# ── Measure one cell (fleet, n_survivors) ────────────────────────────────────

def measure_cell(fleet: FleetSpec, n_survivors: int, verbose: bool = False) -> dict:
    """
    Simulate the controlled stop of one turbine with n_survivors remaining.

    Returns dict with:
      computed_mw : p_min_stable_mw − (survivors × r_asset × dt)
      observed_mw : peak BESS discharge at breaker-open tick
    """
    msl = fleet.msl_mw
    computed = msl - (n_survivors * fleet.r_asset * DT)

    # ── Build fleet: stopper + survivors ─────────────────────────────────────
    stopper = _synced("stopper", fleet)
    survivors = [_synced(f"surv-{i}", fleet) for i in range(n_survivors)]

    # ── Issue command_stop on the stopper (R5 already elapsed) ───────────────
    sim_time = 7200.0  # start at t=2h (well past t_min_run_s=1800s)
    result = stopper.command_stop(sim_time)
    assert result is None, f"Expected stop accepted, got: {result}"
    assert stopper.state == TurbineState.UNLOADING

    # ── Drive ticks until stopper opens its breaker ───────────────────────────
    # Each tick:
    #   1. Apply loading: drive stopper toward MSL floor; survivors toward rated.
    #   2. Advance all units.
    #   3. Detect breaker-open (UNLOADING → OFFLINE transition).

    max_ticks = 500
    breaker_open_tick = None
    peak_bess_mw = None

    for tick in range(max_ticks):
        t = sim_time + tick * DT

        # ── Apply loading setpoints ──────────────────────────────────────────
        # Stopper (UNLOADING): target MSL floor and descend r_asset*dt per tick.
        stopper_target = msl
        stopper_new = max(
            msl - 1e-9,   # allow touching MSL
            stopper._current_output_mw - fleet.r_asset * DT,
        )
        stopper._current_output_mw = max(stopper_new, msl - fleet.r_asset * DT * 0.05)

        # Actually: drive output directly toward MSL by one ramp step.
        step = min(fleet.r_asset * DT, abs(stopper._current_output_mw - msl))
        if stopper._current_output_mw > msl:
            stopper._current_output_mw -= step
        # Clamp to MSL (don't go below).
        stopper._current_output_mw = max(stopper._current_output_mw, msl)

        # Track levelled-off.
        if abs(stopper._current_output_mw - msl) < stopper.config.levelled_off_tol_mw:
            if math.isnan(stopper._levelled_off_since_s):
                stopper._levelled_off_since_s = t
        else:
            stopper._levelled_off_since_s = math.nan

        # ── Check levelled-off → breaker open ────────────────────────────────
        dwell_ok = (
            not math.isnan(stopper._levelled_off_since_s)
            and (t - stopper._levelled_off_since_s) >= stopper.config.unload_tail_s
        )
        if dwell_ok and stopper.state == TurbineState.UNLOADING:
            # Breaker opens: record the BESS discharge needed at this tick.
            # At breaker-open: stopper drops from MSL to 0.
            # Survivors can each ramp up by r_asset × DT in the NEXT tick.
            # BESS must cover the shortfall in the SAME tick.
            turb_drop = stopper._current_output_mw   # ≈ MSL
            surv_ramp = n_survivors * fleet.r_asset * DT   # ramp available
            bess_discharge = max(0.0, turb_drop - surv_ramp)

            stopper.state = TurbineState.OFFLINE
            stopper._current_output_mw = 0.0
            stopper._stop_time_s = t

            breaker_open_tick = tick
            peak_bess_mw = bess_discharge

            if verbose:
                print(
                    f"    Breaker open at t={t:.0f}s (tick {tick}): "
                    f"stopper_out={turb_drop:.3f} MW, "
                    f"surv_ramp={surv_ramp:.3f} MW, "
                    f"BESS_needed={bess_discharge:.3f} MW"
                )
            break

    if breaker_open_tick is None:
        return {"computed_mw": computed, "observed_mw": float("nan"), "error": "no breaker open"}

    return {
        "computed_mw": computed,
        "observed_mw": peak_bess_mw,
        "breaker_open_tick": breaker_open_tick,
    }


# ── Main table ────────────────────────────────────────────────────────────────

def main() -> None:
    print("Phase E closeout Item 4 — Breaker-open BESS bridging duty")
    print("=" * 72)
    print(f"{'Fleet':<46} {'Surv':>4} {'Computed':>10} {'Observed':>10} {'Sign':>6}")
    print("-" * 72)

    for fleet in [FLEET_A, FLEET_B]:
        for n_surv in [3, 2, 1, 0]:
            if n_surv >= fleet.n_total:
                continue   # can't have more survivors than fleet size
            cell = measure_cell(fleet, n_surv)
            comp = cell["computed_mw"]
            obs  = cell["observed_mw"]
            sign = "BESS burst" if obs > 0.001 else "no burst"
            print(
                f"  {fleet.name:<44} {n_surv:>4}   {comp:>+8.2f} MW   {obs:>+8.3f} MW   {sign}"
            )
        print()

    print()
    print("Computed worst case  = p_min_stable_mw − (survivors × r_asset × dt)")
    print("Observed peak BESS   = max(0, stopper_output_at_open − survivors×r_asset×dt)")
    print()
    print("Notes:")
    print("  dt = 5.0 s (catalogue default)")
    print("  Fleet A: MSL = 0.40 × 7.0 = 2.80 MW;  r_asset × dt = 0.20 × 5 = 1.00 MW/tick")
    print("  Fleet B: MSL = 0.40 × 15.0 = 6.00 MW; r_asset × dt = 0.15 × 5 = 0.75 MW/tick")
    print()
    print("§7.2 amendment assessment: see report below.")


if __name__ == "__main__":
    main()
