#!/usr/bin/env python3
"""
run_and_monitor.py — Start a run at playback_speed=60 and monitor all
energy-consistency invariants in real-time, then print a full summary.

Usage:
    python3 run_and_monitor.py <scenario_id> [playback_speed]

Defaults: playback_speed=60 (1 min wall time for a 60-min sim)
"""

from __future__ import annotations
import asyncio, collections, json, sys, time, urllib.request, urllib.error

API      = "http://localhost:22126"
WS_HOST  = "ws://localhost:22126"
TOLS     = 1e-3

# BESS / FC constants for this run
BESS_RATED_MW   = 15.0
BESS_USABLE_MWH = 20.0
FC_RATED_MW     = 20.0
SIM_DURATION    = 3600.0   # 60 minutes

# ── ANSI ──────────────────────────────────────────────────────────────────────
R="\033[91m"; Y="\033[93m"; G="\033[92m"; C="\033[96m"
D="\033[2m";  B="\033[1m";  RST="\033[0m"
def red(s): return f"{R}{s}{RST}"
def ylw(s): return f"{Y}{s}{RST}"
def grn(s): return f"{G}{s}{RST}"
def dim(s): return f"{D}{s}{RST}"
def bld(s): return f"{B}{s}{RST}"

def mw(v):
    if v is None: return dim("    ——")
    return f"{v:+8.3f}"
def pct(v):
    if v is None: return dim("  ——")
    return f"{v*100:5.1f}%"

# ── Invariant checker ──────────────────────────────────────────────────────────

_prev_soc: float | None = None
_prev_t:   float | None = None

def check(t: dict) -> list[tuple[str, str]]:
    """Return list of (inv_id, message). Empty = clean tick."""
    global _prev_soc, _prev_t
    errs: list[tuple[str, str]] = []

    g   = t.get
    p_demand  = g("p_demand_mw")
    p_comp_d  = g("p_compute_demand_mw")
    p_cool_d  = g("p_cooling_demand_mw")
    p_served  = g("p_served_mw")
    p_comp_s  = g("p_compute_served_mw")
    p_cool_s  = g("p_cooling_served_mw")
    p_unserv  = g("p_unserved_mw")
    p_comp_u  = g("p_compute_unserved_mw")
    p_cool_u  = g("p_cooling_unserved_mw")
    p_gen     = g("p_generation_mw")
    p_imbala  = g("p_imbalance_mw")
    p_renew   = g("p_renewable_mw", 0.0)
    net_d     = g("net_demand_mw")
    bess_soc  = g("bess_soc_fraction")
    bess_out  = g("bess_output_mw")
    turb_out  = g("turbine_output_mw", 0.0)
    fc_out    = g("fuel_cell_output_mw")
    grid_ex   = g("grid_exchange_mw")      # positive = import
    conf_up   = g("confidence_upper_mw")
    kube_util = g("utilization")
    cont_cov  = g("contingency_coverage")
    sim_t     = g("sim_time_seconds", 0.0)

    def err(inv: str, msg: str) -> None:
        errs.append((inv, msg))

    # INV-1  demand decomposition
    if None not in (p_comp_d, p_cool_d, p_demand):
        exp = p_comp_d + p_cool_d
        if abs(exp - p_demand) > TOLS:
            err("INV-1", f"p_compute_d {mw(p_comp_d)} + p_cool_d {mw(p_cool_d)} "
                        f"= {mw(exp)} ≠ p_demand {mw(p_demand)}")

    # INV-2  served decomposition
    if None not in (p_comp_s, p_cool_s, p_served):
        exp = p_comp_s + p_cool_s
        if abs(exp - p_served) > TOLS:
            err("INV-2", f"p_compute_s {mw(p_comp_s)} + p_cool_s {mw(p_cool_s)} "
                        f"= {mw(exp)} ≠ p_served {mw(p_served)}")

    # INV-3  unserved decomposition
    if None not in (p_comp_u, p_cool_u, p_unserv):
        exp = p_comp_u + p_cool_u
        if abs(exp - p_unserv) > TOLS:
            err("INV-3", f"p_compute_u {mw(p_comp_u)} + p_cool_u {mw(p_cool_u)} "
                        f"= {mw(exp)} ≠ p_unserved {mw(p_unserv)}")

    # INV-4  served + unserved = demand
    if None not in (p_served, p_unserv, p_demand):
        if abs(p_served + p_unserv - p_demand) > TOLS:
            err("INV-4", f"p_served {mw(p_served)} + p_unserved {mw(p_unserv)} "
                        f"= {mw(p_served+p_unserv)} ≠ p_demand {mw(p_demand)}")

    # INV-5  generation ≥ 0
    if p_gen is not None and p_gen < -TOLS:
        err("INV-5", f"p_generation_mw {mw(p_gen)} < 0")

    # INV-6  SoC in [0, 1]
    if bess_soc is not None and (bess_soc < -0.001 or bess_soc > 1.001):
        err("INV-6", f"bess_soc_fraction {pct(bess_soc)} outside [0, 1]")

    # INV-7  served ≤ demand
    if None not in (p_served, p_demand) and p_served > p_demand + TOLS:
        err("INV-7", f"p_served {mw(p_served)} > p_demand {mw(p_demand)}")

    # INV-8  NO turbine output (turbine-free run)
    if turb_out is not None and abs(turb_out) > TOLS:
        err("INV-8", f"turbine_output_mw {mw(turb_out)} ≠ 0  (no turbines in spec!)")

    # INV-9  solar cosmetic leak — contingency renewable_mw must be 0
    if isinstance(cont_cov, dict):
        ren = cont_cov.get("renewable_mw", 0.0)
        if abs(ren) > TOLS:
            err("INV-9", f"contingency_coverage.renewable_mw {mw(ren)} ≠ 0 "
                        f"(solar cosmetic leak into physics — no solar in spec)")

    # INV-10  SoC continuity — delta bounded by rated power × elapsed time
    if bess_soc is not None and _prev_soc is not None and _prev_t is not None:
        dt = sim_t - _prev_t
        if dt > 0:
            dsoc = abs(bess_soc - _prev_soc)
            max_dsoc = (BESS_RATED_MW * dt) / (BESS_USABLE_MWH * 3600.0)
            if dsoc > max_dsoc * 1.10 + 1e-4:
                err("INV-10", f"|ΔSoC| {dsoc:.5f} exceeds rated bound {max_dsoc:.5f} "
                             f"(dt={dt:.0f}s, rated {BESS_RATED_MW} MW / {BESS_USABLE_MWH} MWh)")

    # INV-11  FC output ≥ 0
    if fc_out is not None and fc_out < -TOLS:
        err("INV-11", f"fuel_cell_output_mw {mw(fc_out)} < 0")

    # INV-12  FC output ≤ rated
    if fc_out is not None and fc_out > FC_RATED_MW + TOLS:
        err("INV-12", f"fuel_cell_output_mw {mw(fc_out)} > rated {FC_RATED_MW} MW")

    # INV-13  BESS output bounded by ±rated_mw
    if bess_out is not None and abs(bess_out) > BESS_RATED_MW + TOLS:
        err("INV-13", f"bess_output_mw {mw(bess_out)} exceeds ±{BESS_RATED_MW} MW rated")

    # INV-14  local generation = FC + BESS  (no turbine, no solar physics)
    if None not in (p_gen, fc_out, bess_out):
        exp = fc_out + bess_out
        if abs(p_gen - exp) > TOLS:
            err("INV-14", f"p_generation_mw {mw(p_gen)} ≠ fc {mw(fc_out)} + bess {mw(bess_out)} "
                         f"= {mw(exp)}  (diff {mw(p_gen-exp)})")

    # INV-15  net_demand = p_demand − p_renewable  (here p_renewable in physics = 0)
    if None not in (net_d, p_demand):
        exp_net = p_demand - 0.0   # no solar in physics path
        if abs(net_d - exp_net) > TOLS:
            err("INV-15", f"net_demand_mw {mw(net_d)} ≠ p_demand {mw(p_demand)} "
                         f"(should be equal — no solar physics)")

    # INV-16  confidence_upper_mw ≥ p_served  (band covers actual served load)
    if None not in (conf_up, p_served) and conf_up < p_served - 1.0:
        err("INV-16", f"confidence_upper_mw {mw(conf_up)} < p_served {mw(p_served)} − 1 MW")

    # INV-17  kube utilisation ∈ [0, 1]
    if kube_util is not None and (kube_util < -0.001 or kube_util > 1.001):
        err("INV-17", f"utilization {kube_util:.4f} outside [0, 1]")

    # INV-18  large imbalance warning  (> 5 MW in a grid-tied system is unusual)
    if p_imbala is not None and abs(p_imbala) > 5.0:
        err("INV-18", f"p_imbalance_mw {mw(p_imbala)} > 5 MW "
                     f"(grid-tied — large imbalance suggests UFLS or metering gap)")

    # ── bookkeeping ───────────────────────────────────────────────────────────
    if bess_soc is not None: _prev_soc = bess_soc
    _prev_t = sim_t
    return errs


# ── API helpers ────────────────────────────────────────────────────────────────

def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{API}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[ERROR] {e.code}: {body}")
        sys.exit(1)


# ── Main monitor loop ──────────────────────────────────────────────────────────

async def run_monitor(run_id: str) -> None:
    try:
        import websockets  # type: ignore
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets  # type: ignore

    url = f"{WS_HOST}/ws/{run_id}"

    tick_count   = 0
    err_ticks    = 0
    inv_hits: dict[str, int]   = collections.defaultdict(int)
    first_at: dict[str, float] = {}
    last_at:  dict[str, float] = {}
    row_data: list[dict]       = []   # sample rows for final table

    COLS = (f"{'t(s)':>6}  {'sim%':>5}  {'demand':>8}  {'p_gen':>8}  "
            f"{'fc':>8}  {'bess':>8}  {'grid':>8}  {'SoC':>6}  {'util%':>6}  {'status':>7}")
    print(bld(f"\n{'═'*90}"))
    print(bld(f"  GridSignal Energy Monitor · run {run_id}"))
    print(bld(f"  18 invariants · BESS 15 MW / FC 20 MW / Grid 50 MW · 60 min"))
    print(bld(f"{'═'*90}\n"))
    print(dim(COLS))
    print(dim("─" * 90))

    SAMPLE_EVERY = 5   # print a row every N ticks (every 25 sim-seconds)

    try:
        async with websockets.connect(url, ping_interval=30, open_timeout=15) as ws:
            async for raw in ws:
                t         = json.loads(raw)
                tick_count += 1
                sim_t     = t.get("sim_time_seconds", 0.0)
                p_demand  = t.get("p_demand_mw")
                p_gen     = t.get("p_generation_mw")
                fc_out    = t.get("fuel_cell_output_mw")
                bess_out  = t.get("bess_output_mw")
                grid_ex   = t.get("grid_exchange_mw")
                bess_soc  = t.get("bess_soc_fraction")
                kube_util = t.get("utilization")

                errs = check(t)
                row_data.append({**t, "_errs": errs})

                if errs:
                    err_ticks += 1
                    for inv_id, msg in errs:
                        inv_hits[inv_id] += 1
                        if inv_id not in first_at: first_at[inv_id] = sim_t
                        last_at[inv_id] = sim_t

                status_str = red(f"  {len(errs)}ERR") if errs else grn("   OK ")

                if tick_count % SAMPLE_EVERY == 1 or errs:
                    sim_pct  = f"{sim_t/SIM_DURATION*100:4.1f}%"
                    util_str = f"{kube_util*100:5.1f}%" if kube_util is not None else dim("   —")
                    soc_str  = pct(bess_soc) if bess_soc is not None else dim("   —")
                    row = (
                        f"{sim_t:6.0f}  {sim_pct:>5}  {mw(p_demand)}  {mw(p_gen)}  "
                        f"{mw(fc_out)}  {mw(bess_out)}  {mw(grid_ex)}  "
                        f"{soc_str}  {util_str}  {status_str}"
                    )
                    print(row)
                    for inv_id, msg in errs:
                        print(f"  {red('▶')} [{inv_id}] {msg}")

    except Exception as exc:
        print(red(f"\nWebSocket closed: {exc}"))

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'═'*90}")
    print(bld("  ENERGY CONSISTENCY SUMMARY"))
    print(f"{'═'*90}")
    print(f"  Ticks received   : {tick_count}")
    print(f"  Sim time covered : {tick_count * 5:.0f} s  ({tick_count * 5 / 60:.1f} min)")
    print(f"  Ticks with errors: {err_ticks}  ({err_ticks/max(tick_count,1)*100:.1f} %)")

    if inv_hits:
        print(f"\n  {'Invariant':<10}  {'Violations':>10}  {'First (s)':>10}  {'Last (s)':>10}  Description")
        print(f"  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*30}")
        desc = {
            "INV-1":  "demand decomp (compute+cool=demand)",
            "INV-2":  "served decomp (compute+cool=served)",
            "INV-3":  "unserved decomp",
            "INV-4":  "served+unserved=demand",
            "INV-5":  "generation ≥ 0",
            "INV-6":  "SoC in [0,1]",
            "INV-7":  "served ≤ demand",
            "INV-8":  "no turbine output",
            "INV-9":  "solar cosmetic not leaking to physics",
            "INV-10": "SoC continuity bounded by rated MW",
            "INV-11": "FC output ≥ 0",
            "INV-12": "FC output ≤ rated",
            "INV-13": "BESS output ≤ ±rated MW",
            "INV-14": "gen = FC + BESS (no turbine/solar)",
            "INV-15": "net_demand = demand (no solar physics)",
            "INV-16": "confidence band ≥ served",
            "INV-17": "kube util in [0,1]",
            "INV-18": "imbalance < 5 MW (grid-tied)",
        }
        for inv, cnt in sorted(inv_hits.items()):
            fa = first_at.get(inv, 0)
            la = last_at.get(inv, 0)
            colour = red if cnt > 5 else ylw
            d = desc.get(inv, "")
            print(f"  {colour(inv):<18}  {cnt:>10}  {fa:>10.0f}  {la:>10.0f}  {d}")
        print()
        print(red(f"  ✗ {len(inv_hits)} invariant(s) violated."))
    else:
        print(f"\n  {grn('✓ All 18 invariants passed on every tick — no energy inconsistencies found.')}")

    # ── Spot values at key sim times ──────────────────────────────────────────
    print(f"\n  Key sim-time snapshots:")
    print(f"  {'t(s)':>6}  {'demand':>8}  {'fc':>8}  {'bess':>8}  {'grid':>8}  {'SoC':>6}  {'util%':>6}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*6}  {'─'*6}")
    targets = {0, 300, 600, 900, 1200, 1500, 1800, 2100, 2400, 2700, 3000, 3300, 3595}
    seen = set()
    for row in row_data:
        st = row.get("sim_time_seconds", 0)
        bucket = round(st / 300) * 300
        if bucket in targets and bucket not in seen:
            seen.add(bucket)
            u = row.get("utilization")
            print(
                f"  {st:6.0f}  {mw(row.get('p_demand_mw'))}  "
                f"{mw(row.get('fuel_cell_output_mw'))}  "
                f"{mw(row.get('bess_output_mw'))}  "
                f"{mw(row.get('grid_exchange_mw'))}  "
                f"{pct(row.get('bess_soc_fraction'))}  "
                f"{f'{u*100:5.1f}%' if u is not None else dim('   —')}"
            )

    print(f"\n{'═'*90}\n")


async def main() -> None:
    scenario_id   = sys.argv[1] if len(sys.argv) > 1 else "c56c4bc1-662a-42c3-bcc7-feccec18cfa0"
    playback_speed = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

    print(f"Starting run for scenario {scenario_id}  (playback_speed={playback_speed}x) …")
    resp   = post_json("/runs", {"scenario_id": scenario_id, "playback_speed": playback_speed})
    run_id = resp["run_id"]
    print(f"run_id: {run_id}\n")

    # Connect immediately — no sleep. At any reasonable playback_speed the
    # tick loop takes many seconds, so even if we miss tick-1 we'll see 700+.
    await run_monitor(run_id)


if __name__ == "__main__":
    asyncio.run(main())
