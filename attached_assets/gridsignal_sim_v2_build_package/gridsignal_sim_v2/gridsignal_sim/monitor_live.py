#!/usr/bin/env python3
"""
GridSignal real-time energy variable monitor.

Connects to the live WebSocket tick stream and checks every tick against
a suite of physics / balance invariants, printing a compact table and
flagging anomalies as they occur.

Usage:
    python monitor_live.py [run_id]   # run_id optional; auto-detects if omitted
"""

from __future__ import annotations
import asyncio, json, math, sys, time, textwrap
import urllib.request

WS_HOST  = "ws://localhost:22126"
API_HOST = "http://localhost:22126"
TOLS     = 1e-3   # MW tolerance for balance checks

# ── ANSI colours ─────────────────────────────────────────────────────────────
RED   = "\033[91m"; YLW = "\033[93m"; GRN = "\033[92m"
CYN   = "\033[96m"; DIM = "\033[2m";  RST = "\033[0m"; BLD = "\033[1m"

def red(s):  return f"{RED}{s}{RST}"
def ylw(s):  return f"{YLW}{s}{RST}"
def grn(s):  return f"{GRN}{s}{RST}"
def cyn(s):  return f"{CYN}{s}{RST}"
def dim(s):  return f"{DIM}{s}{RST}"
def bld(s):  return f"{BLD}{s}{RST}"

# ── helpers ───────────────────────────────────────────────────────────────────
def mw(v):
    """Format MW value: right-justified 7 chars with 3 dp."""
    if v is None: return dim("   None")
    return f"{v:7.3f}"

def pct(v):
    if v is None: return dim("  None")
    return f"{v*100:5.1f}%"

def approx(a, b):
    if a is None or b is None: return True   # can't check; skip
    return abs(a - b) < TOLS

def get(d, *keys, default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default

# ── invariant suite ───────────────────────────────────────────────────────────
def check_tick(t: dict) -> list[str]:
    """Return list of human-readable error strings. Empty = clean tick."""
    errs = []

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
    turb_out = t.get("turbine_output_mw")
    alert    = t.get("insufficient_reserve_alert", False)

    # INV-1: demand decomposition
    if p_comp_d is not None and p_cool_d is not None and p_demand is not None:
        expected = round(p_comp_d + p_cool_d, 6)
        if abs(expected - p_demand) > TOLS:
            errs.append(
                f"INV-1 demand-split: compute({p_comp_d:.3f})+cooling({p_cool_d:.3f})"
                f"={expected:.3f} ≠ p_demand({p_demand:.3f}), gap={expected-p_demand:+.4f} MW"
            )

    # INV-2: served decomposition
    if p_comp_s is not None and p_cool_s is not None and p_served is not None:
        expected = round(p_comp_s + p_cool_s, 6)
        if abs(expected - p_served) > TOLS:
            errs.append(
                f"INV-2 served-split: compute_served({p_comp_s:.3f})+cooling_served({p_cool_s:.3f})"
                f"={expected:.3f} ≠ p_served({p_served:.3f}), gap={expected-p_served:+.4f} MW"
            )

    # INV-3: unserved decomposition
    if p_comp_u is not None and p_cool_u is not None and p_unserv is not None:
        expected = round(p_comp_u + p_cool_u, 6)
        if abs(expected - p_unserv) > TOLS:
            errs.append(
                f"INV-3 unserved-split: compute_unserved({p_comp_u:.3f})+cooling_unserved({p_cool_u:.3f})"
                f"={expected:.3f} ≠ p_unserved({p_unserv:.3f}), gap={expected-p_unserv:+.4f} MW"
            )

    # INV-4: served + unserved == demand
    if p_served is not None and p_unserv is not None and p_demand is not None:
        total = round(p_served + p_unserv, 6)
        if abs(total - p_demand) > TOLS:
            errs.append(
                f"INV-4 served+unserved: {p_served:.3f}+{p_unserv:.3f}={total:.3f}"
                f" ≠ p_demand({p_demand:.3f}), gap={total-p_demand:+.4f} MW"
            )

    # INV-5: imbalance identity — p_generation - p_served == p_imbalance
    if p_gen is not None and p_served is not None and p_imbala is not None:
        expected = round(p_gen - p_served, 6)
        if abs(expected - p_imbala) > TOLS:
            errs.append(
                f"INV-5 imbalance: gen({p_gen:.3f})-served({p_served:.3f})"
                f"={expected:.3f} ≠ p_imbalance({p_imbala:.3f}), gap={expected-p_imbala:+.4f} MW"
            )

    # INV-6: served ≤ demand (cannot serve more than demanded)
    if p_served is not None and p_demand is not None:
        if p_served > p_demand + TOLS:
            errs.append(
                f"INV-6 over-served: p_served({p_served:.3f}) > p_demand({p_demand:.3f})"
            )

    # INV-7: non-negative quantities
    for name, val in [
        ("p_served_mw",    p_served),
        ("p_unserved_mw",  p_unserv),
        ("p_demand_mw",    p_demand),
        ("p_renewable_mw", p_renew),
        ("bess_soc",       bess_soc),
    ]:
        if val is not None and val < -TOLS:
            errs.append(f"INV-7 negative: {name}={val:.4f}")

    # INV-8: BESS SoC in [0, 1]
    if bess_soc is not None and (bess_soc < -TOLS or bess_soc > 1.0 + TOLS):
        errs.append(f"INV-8 SoC-range: bess_soc={bess_soc:.4f} out of [0,1]")

    # INV-9: net demand ≈ total – renewable  (within BESS-curtailment tolerance)
    #
    # IMPORTANT SCOPE NOTE: p_renewable_mw in the tick is overwritten by
    # solar_sim.live_aggregate_mw() in run_manager AFTER physics completes.
    # When no solar arrays are wired into the physics engine for the current
    # scenario, solar_sim reports the sun's theoretical output but it does NOT
    # offset dispatch — net_demand_mw correctly equals p_demand_mw.
    # We detect this via contingency_coverage.renewable_mw == 0: that field
    # comes from the physics state (not solar_sim) and is 0 when no physical
    # arrays are present.
    _cc  = t.get("contingency_coverage") or {}
    _phy_renew = _cc.get("renewable_mw", 0.0) or 0.0
    _solar_in_physics = (_phy_renew > TOLS) or (net_d is not None and p_total is not None and p_renew is not None and abs(p_total - net_d - p_renew) < TOLS)
    if net_d is not None and p_total is not None and p_renew is not None:
        if _solar_in_physics:
            # Solar IS wired into physics — check the identity
            expected = max(0.0, round(p_total - p_renew, 6))
            if abs(net_d - expected) > TOLS:
                errs.append(
                    f"INV-9 net_demand: p_total({p_total:.3f})-renewable({p_renew:.3f})"
                    f"={expected:.3f} ≠ net_demand({net_d:.3f}), gap={net_d-expected:+.4f} MW"
                )
        elif p_renew > TOLS and abs(net_d - p_total) < TOLS:
            # Solar_sim is live but NOT in physics — flag as design mismatch
            errs.append(
                f"⚠ SOLAR-DISPLAY-ONLY: solar_sim={p_renew:.3f} MW visible on dashboard "
                f"but NOT offsetting dispatch (no physics solar arrays). "
                f"net_demand={net_d:.3f} MW = full demand. Scenario needs solar_arrays wired."
            )

    # INV-10: generation ≥ 0 (can't have negative local generation)
    if p_gen is not None and p_gen < -TOLS:
        errs.append(
            f"INV-10 negative-gen: p_generation_mw={p_gen:.4f} (grid import should be a separate field)"
        )

    # INV-11: alert correlation — if alert fires, BESS bridging should be finite and low
    if alert:
        bridging = t.get("bess_bridging_seconds", 0)
        errs.append(
            f"⚡ RESERVE-ALERT: insufficient reserve (bess_bridging_seconds={bridging:.0f}s)"
        )

    return errs

# ── display helpers ───────────────────────────────────────────────────────────
HEADER_INTERVAL = 20   # print header every N ticks

def print_header():
    hdr = (
        f"{'t':>6s} │ {'DEMAND':>7s} {'SERVED':>7s} {'UNSERV':>7s} │"
        f" {'GEN':>7s} {'IMBALA':>7s} │"
        f" {'TURB':>6s} {'BESS':>6s} {'RENEW':>6s} │"
        f" {'SoC':>6s} │ STATUS"
    )
    sep = "─" * len(hdr)
    print(bld(cyn(sep)))
    print(bld(cyn(hdr)))
    print(bld(cyn(sep)))

def print_tick(t: dict, errs: list[str], tick_n: int):
    if tick_n % HEADER_INTERVAL == 0:
        print_header()

    ts   = t.get("sim_time_seconds", 0)
    ok   = len(errs) == 0
    flag = grn("  OK") if ok else red(f"  {len(errs)} ERR")

    line = (
        f"{ts:6.0f} │"
        f" {mw(t.get('p_demand_mw'))}"
        f" {mw(t.get('p_served_mw'))}"
        f" {mw(t.get('p_unserved_mw'))}"
        f" │"
        f" {mw(t.get('p_generation_mw'))}"
        f" {mw(t.get('p_imbalance_mw'))}"
        f" │"
        f" {mw(t.get('turbine_output_mw'))}"
        f" {mw(t.get('bess_output_mw'))}"
        f" {mw(t.get('p_renewable_mw'))}"
        f" │"
        f" {pct(t.get('bess_soc_fraction'))}"
        f" │{flag}"
    )
    print(line)
    for e in errs:
        print(f"         {red('→')} {e}")

# ── run detection ─────────────────────────────────────────────────────────────
def detect_run_id() -> str:
    resp = urllib.request.urlopen(f"{API_HOST}/runs", timeout=5)
    data = json.load(resp)
    ids  = data.get("run_ids", [])
    if not ids:
        print(ylw("⚠ No active runs found. Start a run in the UI first."))
        sys.exit(1)
    return ids[0]

# ── main loop ─────────────────────────────────────────────────────────────────
async def monitor(run_id: str):
    import websockets  # type: ignore

    url = f"{WS_HOST}/ws/{run_id}"
    print(bld(f"\n{'='*60}"))
    print(bld(f" GridSignal Live Monitor — run: {run_id}"))
    print(bld(f" Checking {10} physics invariants per tick"))
    print(bld(f"{'='*60}\n"))

    error_counts: dict[str, int] = {}
    tick_count = 0
    error_ticks = 0
    t0 = time.time()

    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            async for raw in ws:
                msg = json.loads(raw)
                # WS messages may be wrapped: {type:"tick", payload:{...}} or raw tick
                if "payload" in msg:
                    t = msg["payload"]
                elif "tick_index" in msg:
                    t = msg
                else:
                    continue   # heartbeat or other control frame

                errs = check_tick(t)
                tick_count += 1
                if errs:
                    error_ticks += 1
                for e in errs:
                    key = e[:40]
                    error_counts[key] = error_counts.get(key, 0) + 1

                print_tick(t, errs, tick_count)

    except websockets.exceptions.ConnectionClosed as exc:
        print(ylw(f"\nWebSocket closed: {exc}"))
    except KeyboardInterrupt:
        pass
    finally:
        elapsed = time.time() - t0
        print(bld(f"\n{'='*60}"))
        print(bld(f" SUMMARY — {tick_count} ticks in {elapsed:.1f}s"))
        print(f"  Clean ticks:  {grn(str(tick_count - error_ticks))}")
        print(f"  Error ticks:  {(red if error_ticks else grn)(str(error_ticks))}")
        if error_counts:
            print(bld("\n  Error type counts:"))
            for k, v in sorted(error_counts.items(), key=lambda x: -x[1]):
                print(f"    {v:3d}×  {k}…")
        print(bld(f"{'='*60}\n"))

if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else detect_run_id()
    asyncio.run(monitor(rid))
