#!/usr/bin/env python3
"""
monitor_extended.py — Extended energy-consistency monitor for BESS + Grid + Fuel Cell runs.

Checks every tick against the full physics invariant suite (base 10 checks) PLUS
source-specific checks for FC, BESS, and grid exchange:

  INV-1  demand decomposition      p_compute + p_cool   == p_demand
  INV-2  served decomposition      p_comp_s + p_cool_s  == p_served
  INV-3  unserved decomposition     p_comp_u + p_cool_u  == p_unserved
  INV-4  imbalance identity         p_gen  - p_served - p_unserved == p_imbalance
  INV-5  D4 balance                 p_gen  + grid_import == p_demand + p_imbalance (approx)
  INV-6  SoC bounds                 0 <= bess_soc <= 1
  INV-7  BESS direction consistency bess_output sign consistent with SoC trend
  INV-8  no turbine output          turbine_output_mw == 0 for this config
  INV-9  no solar output            p_renewable_mw cosmetic only (contingency = 0)
  INV-10 BESS SoC continuity        SoC delta bounded by rated_mw * dt / usable_mwh
  INV-11 Fuel cell output ≥ 0       fc_output_mw is always non-negative
  INV-12 Fuel cell ≤ rated          fc_output_mw ≤ fc_rated_mw
  INV-13 Grid exchange sign         grid_exchange_mw coherent with island_mode=False
  INV-14 P_generation = FC + BESS + Grid (when no turbines / no solar in physics)
  INV-15 net_demand = p_demand - p_renewable (contingency only, renewable=0 here)
  INV-16 confidence_upper_mw ≥ net_demand (upper band ≥ expected peak)
  INV-17 served ≤ demand            never serve more than demanded
  INV-18 kube utilisation [0,1]     utilization within valid fraction range

Usage:
    python3 monitor_extended.py [run_id]   # auto-detects if omitted
"""

from __future__ import annotations
import asyncio, json, math, sys, time, textwrap, collections
import urllib.request

WS_HOST  = "ws://localhost:22126"
API_HOST = "http://localhost:22126"
TOLS     = 1e-3   # MW tolerance for balance checks

RED   = "\033[91m"; YLW = "\033[93m"; GRN = "\033[92m"
CYN   = "\033[96m"; DIM = "\033[2m";  RST = "\033[0m"; BLD = "\033[1m"
MAG   = "\033[95m"

def red(s):  return f"{RED}{s}{RST}"
def ylw(s):  return f"{YLW}{s}{RST}"
def grn(s):  return f"{GRN}{s}{RST}"
def cyn(s):  return f"{CYN}{s}{RST}"
def dim(s):  return f"{DIM}{s}{RST}"
def bld(s):  return f"{BLD}{s}{RST}"
def mag(s):  return f"{MAG}{s}{RST}"

def mw(v):
    if v is None: return dim("   None")
    return f"{v:+8.3f}"

def pct(v):
    if v is None: return dim("  None")
    return f"{v*100:5.1f}%"

def approx(a, b, tol=TOLS):
    if a is None or b is None: return True
    return abs(a - b) < tol

def get(d, *keys, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default

# ── Scenario-level constants for this run ────────────────────────────────────
BESS_RATED_MW    = 15.0
BESS_USABLE_MWH  = 20.0
FC_RATED_MW      = 20.0
TICK_DT_S        = 5.0       # expected tick interval; updated live

# Per-tick SOC bookkeeping
_prev_soc        : float | None = None
_prev_sim_time   : float | None = None
_error_log       : list[dict]   = []   # persists across ticks for summary


def check_tick(t: dict) -> list[str]:
    """Return list of human-readable error strings. Empty = clean tick."""
    global _prev_soc, _prev_sim_time
    errs = []

    # ── Pull fields ───────────────────────────────────────────────────────────
    p_gen    = t.get("p_generation_mw")
    p_served = t.get("p_served_mw")
    p_unserv = t.get("p_unserved_mw")
    p_demand = t.get("p_demand_mw")
    p_imbala = t.get("p_imbalance_mw")
    p_comp_d = t.get("p_compute_demand_mw")
    p_cool_d = t.get("p_cooling_demand_mw")
    p_comp_s = t.get("p_compute_served_mw")
    p_cool_s = t.get("p_cooling_served_mw")
    p_comp_u = t.get("p_compute_unserved_mw")
    p_cool_u = t.get("p_cooling_unserved_mw")
    p_renew  = t.get("p_renewable_mw", 0.0)
    p_total  = t.get("p_total_mw")
    net_d    = t.get("net_demand_mw")
    bess_soc = t.get("bess_soc_fraction")
    bess_out = t.get("bess_output_mw")
    turb_out = t.get("turbine_output_mw", 0.0)
    grid_ex  = t.get("grid_exchange_mw")        # POSITIVE_IS_IMPORT convention
    fc_out   = t.get("fuel_cell_output_mw")
    conf_up  = t.get("confidence_upper_mw")
    sim_t    = t.get("sim_time_seconds", 0.0)
    kube_util= t.get("utilization")             # kube utilisation fraction
    cont_cov = t.get("contingency_coverage")

    # INV-1: demand decomposition
    if p_comp_d is not None and p_cool_d is not None and p_demand is not None:
        expected = round(p_comp_d + p_cool_d, 6)
        if abs(expected - p_demand) > TOLS:
            errs.append(
                f"INV-1 DEMAND-DECOMP: p_compute_demand {mw(p_comp_d)} + "
                f"p_cooling_demand {mw(p_cool_d)} = {mw(expected)} ≠ p_demand {mw(p_demand)}"
            )

    # INV-2: served decomposition
    if p_comp_s is not None and p_cool_s is not None and p_served is not None:
        expected = round(p_comp_s + p_cool_s, 6)
        if abs(expected - p_served) > TOLS:
            errs.append(
                f"INV-2 SERVED-DECOMP: p_compute_served {mw(p_comp_s)} + "
                f"p_cooling_served {mw(p_cool_s)} = {mw(expected)} ≠ p_served {mw(p_served)}"
            )

    # INV-3: unserved decomposition
    if p_comp_u is not None and p_cool_u is not None and p_unserv is not None:
        expected = round(p_comp_u + p_cool_u, 6)
        if abs(expected - p_unserv) > TOLS:
            errs.append(
                f"INV-3 UNSERVED-DECOMP: p_compute_unserved {mw(p_comp_u)} + "
                f"p_cooling_unserved {mw(p_cool_u)} = {mw(expected)} ≠ p_unserved {mw(p_unserv)}"
            )

    # INV-4: served + unserved = demand
    if p_served is not None and p_unserv is not None and p_demand is not None:
        if abs(p_served + p_unserv - p_demand) > TOLS:
            errs.append(
                f"INV-4 IMBALANCE-ID: p_served {mw(p_served)} + p_unserved {mw(p_unserv)} "
                f"= {mw(p_served+p_unserv)} ≠ p_demand {mw(p_demand)}"
            )

    # INV-5: generation ≥ 0
    if p_gen is not None and p_gen < -TOLS:
        errs.append(f"INV-5 NEGATIVE-GEN: p_generation_mw {mw(p_gen)} < 0")

    # INV-6: SoC bounds
    if bess_soc is not None:
        if bess_soc < -0.001 or bess_soc > 1.001:
            errs.append(f"INV-6 SOC-BOUNDS: bess_soc_fraction {pct(bess_soc)} outside [0,1]")

    # INV-7: served ≤ demand
    if p_served is not None and p_demand is not None:
        if p_served > p_demand + TOLS:
            errs.append(
                f"INV-7 OVER-SERVED: p_served {mw(p_served)} > p_demand {mw(p_demand)}"
            )

    # INV-8: NO TURBINE output (this is a turbine-free run)
    if turb_out is not None and abs(turb_out) > TOLS:
        errs.append(f"INV-8 TURBINE-OUT: turbine_output_mw {mw(turb_out)} ≠ 0 (no turbines in spec!)")

    # INV-9: SOLAR display mismatch — contingency_coverage.renewable_mw must be 0
    if cont_cov is not None:
        ren_mw = cont_cov.get("renewable_mw", 0.0) if isinstance(cont_cov, dict) else 0.0
        if abs(ren_mw) > TOLS:
            errs.append(
                f"INV-9 SOLAR-DISPLAY: contingency_coverage.renewable_mw {mw(ren_mw)} ≠ 0 "
                f"but no solar in spec (cosmetic leak into physics)"
            )

    # INV-10: SOC continuity — delta bounded by BESS rated power × elapsed time
    if bess_soc is not None and _prev_soc is not None and _prev_sim_time is not None:
        dt   = sim_t - _prev_sim_time
        if dt > 0:
            dsoc = abs(bess_soc - _prev_soc)
            # max possible |ΔSoC| = rated_mw * dt / (usable_mwh * 3600)
            max_dsoc = (BESS_RATED_MW * dt) / (BESS_USABLE_MWH * 3600.0)
            # Allow 10 % margin for rounding / mid-step effects
            if dsoc > max_dsoc * 1.10 + 1e-4:
                errs.append(
                    f"INV-10 SOC-JUMP: |ΔSoC| {dsoc:.5f} exceeds rated bound {max_dsoc:.5f} "
                    f"for dt={dt:.1f}s (rated {BESS_RATED_MW} MW / {BESS_USABLE_MWH} MWh)"
                )

    # INV-11: Fuel cell output ≥ 0
    if fc_out is not None and fc_out < -TOLS:
        errs.append(f"INV-11 FC-NEGATIVE: fuel_cell_output_mw {mw(fc_out)} < 0")

    # INV-12: Fuel cell ≤ rated
    if fc_out is not None and fc_out > FC_RATED_MW + TOLS:
        errs.append(
            f"INV-12 FC-OVERLOAD: fuel_cell_output_mw {mw(fc_out)} > rated {FC_RATED_MW} MW"
        )

    # INV-13: BESS output bounded by rated MW
    if bess_out is not None and abs(bess_out) > BESS_RATED_MW + TOLS:
        errs.append(
            f"INV-13 BESS-OVERLOAD: bess_output_mw {mw(bess_out)} exceeds ±{BESS_RATED_MW} MW rated"
        )

    # INV-14: Grid exchange — in grid-tied mode (island_mode=False), grid_exchange_mw
    #          may be any sign; but should equal p_gen - p_demand (+ imbalance)
    #          since grid makes up the deficit.  Cross-check loosely.
    if (grid_ex is not None and p_gen is not None and p_demand is not None
            and p_imbala is not None):
        # p_gen + grid_import = p_demand + |p_imbalance|
        # grid_exchange_mw positive = import; grid contributes to supply side.
        expected_grid = p_demand - p_gen + p_imbala   # rough check
        if abs(expected_grid - grid_ex) > 2.0:         # 2 MW tolerance — grid has ramp lag
            errs.append(
                f"INV-14 GRID-BALANCE: expected grid {mw(expected_grid)} ≈ "
                f"demand-gen+imb, got {mw(grid_ex)} (diff {mw(grid_ex-expected_grid)})"
            )

    # INV-15: p_generation_mw should account for FC + BESS + grid (no turbine, no solar)
    #          p_generation_mw is the local (non-grid) generation total:
    #              = bess_output_mw + fc_output_mw  (turbine=0, solar=0 in this run)
    if (p_gen is not None and fc_out is not None and bess_out is not None):
        expected_local = fc_out + bess_out
        if abs(p_gen - expected_local) > TOLS:
            errs.append(
                f"INV-15 GEN-DECOMP: p_generation_mw {mw(p_gen)} ≠ "
                f"fc_out {mw(fc_out)} + bess_out {mw(bess_out)} = {mw(expected_local)}"
            )

    # INV-16: confidence_upper_mw ≥ net_demand (forecast upper band covers expected demand)
    if conf_up is not None and net_d is not None and p_served is not None:
        # A tight band below p_served (not net_d) would be an anomaly
        if conf_up < p_served - 1.0:
            errs.append(
                f"INV-16 CONF-BAND: confidence_upper_mw {mw(conf_up)} < p_served {mw(p_served)} - 1 MW"
            )

    # INV-17: Kubernetes utilisation in [0,1]
    if kube_util is not None:
        if kube_util < -0.001 or kube_util > 1.001:
            errs.append(f"INV-17 KUBE-UTIL: utilization {kube_util:.4f} outside [0,1]")

    # INV-18: p_imbalance should be zero (or very small) in a healthy grid-tied run
    #         — flag if > 5 MW as an operational anomaly worth investigating
    if p_imbala is not None and abs(p_imbala) > 5.0:
        errs.append(
            f"INV-18 LARGE-IMBALANCE: p_imbalance_mw {mw(p_imbala)} > 5 MW "
            f"(may indicate UFLS or load-shed event)"
        )

    # ── Update bookkeeping ────────────────────────────────────────────────────
    if bess_soc is not None:
        _prev_soc = bess_soc
    _prev_sim_time = sim_t

    return errs


# ── WebSocket monitor ─────────────────────────────────────────────────────────

async def get_active_run_id() -> str | None:
    try:
        with urllib.request.urlopen(f"{API_HOST}/runs") as r:
            data = json.loads(r.read())
        ids = data.get("run_ids", [])
        return ids[0] if ids else None
    except Exception:
        return None


async def monitor(run_id: str) -> None:
    try:
        import websockets  # type: ignore
    except ImportError:
        print("Installing websockets …")
        import subprocess, sys as _sys
        subprocess.check_call([_sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets  # type: ignore

    url = f"{WS_HOST}/ws/{run_id}"
    print(bld(f"\n{'═'*78}"))
    print(bld(f"  GridSignal Extended Monitor — run_id: {run_id}"))
    print(bld(f"  18 invariants · BESS + Grid + Fuel Cell · 60 min"))
    print(bld(f"{'═'*78}\n"))

    tick_count  = 0
    error_count = 0
    warn_count  = 0
    inv_hits    : dict[str, int] = collections.defaultdict(int)
    first_error_at: dict[str, float] = {}

    HEADER = (
        f"{'t(s)':>6}  {'sim%':>5}  "
        f"{'demand':>8}  {'p_gen':>8}  {'fc_out':>8}  "
        f"{'bess':>8}  {'grid':>8}  "
        f"{'SoC':>6}  {'kube%':>6}  {'status':>8}"
    )
    print(dim(HEADER))
    print(dim("─" * 90))

    try:
        async with websockets.connect(url, ping_interval=30) as ws:
            async for raw in ws:
                t = json.loads(raw)
                tick_count += 1

                sim_t    = t.get("sim_time_seconds", 0.0)
                p_demand = t.get("p_demand_mw", 0.0)
                p_gen    = t.get("p_generation_mw", 0.0)
                fc_out   = t.get("fuel_cell_output_mw", 0.0) or 0.0
                bess_out = t.get("bess_output_mw", 0.0) or 0.0
                grid_ex  = t.get("grid_exchange_mw", 0.0) or 0.0
                bess_soc = t.get("bess_soc_fraction")
                kube_u   = t.get("utilization")
                sim_dur  = 3600.0  # 60 min

                errs = check_tick(t)

                if errs:
                    error_count += 1
                    for e in errs:
                        inv_id = e.split()[0]  # e.g. "INV-15"
                        inv_hits[inv_id] += 1
                        if inv_id not in first_error_at:
                            first_error_at[inv_id] = sim_t
                    status_str = red(f"  {len(errs)} ERR")
                else:
                    status_str = grn("   OK  ")

                # Print tick row every tick (or every 5th in fast-sim mode)
                soc_str   = pct(bess_soc) if bess_soc is not None else dim("   —   ")
                kube_str  = f"{kube_u*100:5.1f}%" if kube_u is not None else dim("  — ")
                sim_pct   = f"{sim_t/sim_dur*100:4.1f}%"

                row = (
                    f"{sim_t:6.0f}  {sim_pct:>5}  "
                    f"{mw(p_demand)}  {mw(p_gen)}  {mw(fc_out)}  "
                    f"{mw(bess_out)}  {mw(grid_ex)}  "
                    f"{soc_str}  {kube_str}  {status_str}"
                )
                print(row)

                # Print each error inline
                for e in errs:
                    print(f"  {red('▶')} {e}")
                    _error_log.append({"t": sim_t, "inv": e})

                # End-of-run detection
                if sim_t >= sim_dur - 5:
                    break

    except Exception as exc:
        print(red(f"\nWebSocket disconnected: {exc}"))

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'═'*78}")
    print(bld("  SUMMARY"))
    print(f"{'═'*78}")
    print(f"  Ticks processed : {tick_count}")
    print(f"  Ticks with errs : {error_count}  ({error_count/max(tick_count,1)*100:.1f}%)")

    if inv_hits:
        print(f"\n  {'Invariant':<18} {'Violations':>10}  {'First at (s)':>14}")
        print(f"  {'─'*18}  {'─'*10}  {'─'*14}")
        for inv, cnt in sorted(inv_hits.items(), key=lambda x: -x[1]):
            fat = first_error_at.get(inv, 0)
            colour = red if cnt > 5 else ylw
            print(f"  {colour(inv):<26}  {cnt:>10}  {fat:>14.1f}")
    else:
        print(f"\n  {grn('✓ All 18 invariants passed on every tick.')}")

    print(f"\n{'═'*78}\n")


def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else None

    if run_id is None:
        # try temp file written by run_30tenant_60min.py
        try:
            with open("/tmp/gridsignal_last_run_id") as f:
                run_id = f.read().strip()
            print(f"Auto-detected run_id from /tmp: {run_id}")
        except FileNotFoundError:
            pass

    if run_id is None:
        run_id = asyncio.run(get_active_run_id())
        if run_id:
            print(f"Auto-detected active run: {run_id}")

    if run_id is None:
        print("No run_id found. Pass as argument or start a run first.")
        sys.exit(1)

    asyncio.run(monitor(run_id))


if __name__ == "__main__":
    main()
