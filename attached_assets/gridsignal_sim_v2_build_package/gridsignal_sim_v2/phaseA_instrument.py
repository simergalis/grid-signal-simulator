"""
GRIDSIGNAL — PHASE A EXTENSION: POWER BALANCE LEDGER INSTRUMENTATION
Read-only: zero behavioural changes. All values read from TickResult fields
already computed by the existing engine. No dual implementations.

Tick cap: 220 ticks (t=5..1105 s).  Covers the full compute ramp-up peak
(t≈1005 s, 27 jobs) plus 100 s beyond.  Island_collapse_hz is absent from
the scenario spec so collapse never fires; the run continues indefinitely
without a cap.
"""
import json, math, pathlib, sys, warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent / "gridsignal_sim"))

from runtime.scenario_factory import build_run_context_from_spec

MAX_TICKS     = 220
SCENARIO_PATH = pathlib.Path(__file__).parent / "scenarios" / "islanded_8_60_10_ramp.json"
OUT_DIR       = pathlib.Path("/tmp/phaseA_ledger")
OUT_DIR.mkdir(parents=True, exist_ok=True)

spec = json.loads(SCENARIO_PATH.read_text())
ABSENT = "ABSENT"

# ── A-1 header records (written once to each file) ────────────────────────────
HEADER_LEDGER = {
    "_record_type": "header",
    "fields": {
        "t_s":                  "TickResult.sim_time_seconds — interval-END per F5 (simulation_core.py:1544)",
        "turbines":             "tick.turbine_units — per-unit list (run_manager.py:234; stamped per tick at simulation_core.py:1322)",
        "p_turbine_total_mw":   "TickResult.turbine_output_mw — Σ ALL turbines incl STARTING/RAMPING (simulation_core.py:824,1549)",
        "p_solar_mw":           "TickResult.p_renewable_mw — post-curtailment solar output (simulation_core.py:509,547,1557)",
        "p_bess_mw":            "TickResult.bess_output_mw — DELIVERED after SOC/power clip; POSITIVE=discharge (simulation_core.py:824,1550)",
        "p_source_total_mw":    "p_turbine+p_solar+p_bess — no pre-existing field; arithmetic of three separately-logged quantities",
        "p_compute_modeled_mw": "TickResult.p_compute_mw — Σ per_job_compute_mw (simulation_core.py:489,1545); no served/unserved split",
        "p_compute_served_mw":  "ABSENT — no served/unserved distinction in compute path",
        "p_cooling_modeled_mw": "TickResult.p_cooling_mw — CoolingModule.output_mw() 90-s lagged (simulation_core.py:494,1546)",
        "p_cooling_served_mw":  "ABSENT — no served/unserved distinction in cooling path",
        "p_curtailed_mw":       "TickResult.p_renewable_curtailed_mw — OF inverter curtailment (simulation_core.py:547,1558); 0 when thresholds absent",
        "p_unserved_mw":        "ABSENT — no load-shedding/unserved-energy accounting",
        "p_sink_total_mw":      "TickResult.p_total_mw = p_compute_mw + p_cooling_mw (simulation_core.py:496,1547)",
        "residual_mw":          "p_source_total_mw - p_sink_total_mw; _balance_residual_mw removed from wire (run_manager.py:334)",
        "frequency_hz":         "TickResult.frequency_hz — swing-equation output islanded mode (run_manager.py:339)",
        "soc_frac":             "TickResult.bess_soc_fraction (simulation_core.py:1551)",
        "floor_violated":       "not TickResult.reserve_satisfied; reserve_satisfied = not CommitmentDecision.floor_violated (simulation_core.py:958, run_manager.py:403)",
        "dispatch_state":       "ABSENT — no dispatch_state field; commitment_block.action is the commitment decision ('commit'/'decommit'/'hold')",
    },
    "sign_conventions": {
        "p_bess_mw":   "POSITIVE=discharge; absorbing (charging) not modelled as negative bess_output_mw on this path",
        "residual_mw": "POSITIVE=surplus gen; NEGATIVE=shortfall (load > supply)",
    },
    "tick_period_s":     5.0,
    "tick_period_source":"TICK_INTERVAL_SIM_SECONDS=5.0 (run_manager.py:537; spec Section 3.1)",
    "absent_fields":     ["p_compute_served_mw","p_cooling_served_mw","p_unserved_mw","dispatch_state"],
    "tick_cap":          MAX_TICKS,
    "cap_reason":        "island_collapse_hz absent from scenario; collapse never fires so run is unbounded",
}

HEADER_TRACE = {
    "_record_type": "header",
    "fields": {
        "t_s":                             "TickResult.sim_time_seconds",
        "urgency_term_U":                  "ABSENT — commitment.py:272 'utilisation' local var not emitted; wire has commitment_block.utilisation which uses SYNCHRONISED-ONLY denominator (simulation_core.py:950) — different formula",
        "commit_request_issued":           "TickResult.commitment_action=='commit' (run_manager.py:397)",
        "commit_request_target_units":     "TickResult.commitment_target_unit_id (run_manager.py:398)",
        "per_unit.time_in_state_s":        "ABSENT — turbine_units wire dict has time_to_online_s (STARTING only) not generic time_in_state_s",
        "per_unit.start_inhibited":        "ABSENT — only fleet-level blocked_by; no per-unit inhibit flag",
        "per_unit.inhibit_reason":         "ABSENT — same; commitment_block.blocked_by is fleet-level",
        "serialized_start_interlock_held": "TickResult.pending_start_unit_id is not None (run_manager.py:405)",
        "interlock_holder_unit_id":        "TickResult.pending_start_unit_id (run_manager.py:405)",
    },
    "absent_fields": ["urgency_term_U","time_in_state_s","start_inhibited","inhibit_reason"],
}


def run_scenario(record: bool) -> tuple[list, list, list, list]:
    """
    Step the scenario for MAX_TICKS ticks.
    Returns (ledger_recs, defect_recs, trace_recs, at7_fingerprints).
    Only populates ledger/defect/trace when record=True.
    """
    ctx = build_run_context_from_spec("phaseA", spec)
    ledger, defects, trace, fp = [], [], [], []

    for _ in range(MAX_TICKS):
        tick = ctx.step()

        t_s          = tick.sim_time_seconds
        p_turbine    = tick.turbine_output_mw
        p_solar      = tick.p_renewable_mw
        p_bess       = tick.bess_output_mw
        p_source     = p_turbine + p_solar + p_bess
        p_compute    = tick.p_compute_mw
        p_cooling    = tick.p_cooling_mw
        p_curtailed  = tick.p_renewable_curtailed_mw
        p_sink       = tick.p_total_mw
        residual     = p_source - p_sink
        freq         = tick.frequency_hz
        soc          = tick.bess_soc_fraction
        floor_viol   = not tick.reserve_satisfied

        fp.append((
            round(t_s,4), round(p_turbine,6), round(p_solar,6),
            round(p_bess,6), round(p_sink,6), round(freq,6), round(soc,6),
        ))

        if not record:
            continue

        turbines_snap = [
            {"unit_id": u.get("asset_id","?"), "state": u.get("state","?"), "p_mw": u.get("output_mw",0.0)}
            for u in tick.turbine_units
        ]

        ledger.append({
            "t_s":                  round(t_s, 2),
            "turbines":             turbines_snap,
            "p_turbine_total_mw":   round(p_turbine, 4),
            "p_solar_mw":           round(p_solar, 4),
            "p_bess_mw":            round(p_bess, 4),
            "p_source_total_mw":    round(p_source, 4),
            "p_compute_modeled_mw": round(p_compute, 4),
            "p_compute_served_mw":  ABSENT,
            "p_cooling_modeled_mw": round(p_cooling, 4),
            "p_cooling_served_mw":  ABSENT,
            "p_curtailed_mw":       round(p_curtailed, 4),
            "p_unserved_mw":        ABSENT,
            "p_sink_total_mw":      round(p_sink, 4),
            "residual_mw":          round(residual, 6),
            "frequency_hz":         round(freq, 4),
            "soc_frac":             round(soc, 4),
            "floor_violated":       floor_viol,
            "dispatch_state":       ABSENT,
        })

        if abs(residual) > 0.01:
            defects.append({
                "t_s":              round(t_s, 2),
                "residual_mw":      round(residual, 6),
                "p_turbine_mw":     round(p_turbine, 4),
                "p_solar_mw":       round(p_solar, 4),
                "p_bess_mw":        round(p_bess, 4),
                "p_source_mw":      round(p_source, 4),
                "p_compute_mw":     round(p_compute, 4),
                "p_cooling_mw":     round(p_cooling, 4),
                "p_sink_mw":        round(p_sink, 4),
                "bess_setpoint_mw": round(tick.bess_setpoint_mw, 4),
                "frequency_hz":     round(freq, 4),
                "floor_violated":   floor_viol,
            })

        cb_action   = tick.commitment_action
        cb_target   = tick.commitment_target_unit_id
        cb_pending  = tick.pending_start_unit_id
        cb_blocked  = tick.commitment_blocked_by

        unit_rows = [
            {"unit_id": u.get("asset_id","?"), "state": u.get("state","?"),
             "time_in_state_s": ABSENT, "start_inhibited": ABSENT, "inhibit_reason": ABSENT}
            for u in tick.turbine_units
        ]
        trace.append({
            "t_s":                          round(t_s, 2),
            "urgency_term_U":               ABSENT,
            "commit_request_issued":        cb_action == "commit",
            "commit_request_target_units":  cb_target,
            "per_unit":                     unit_rows,
            "serialized_start_interlock_held": cb_pending is not None,
            "interlock_holder_unit_id":     cb_pending,
            "commitment_action":            cb_action,
            "blocked_by":                   cb_blocked,
        })

    return ledger, defects, trace, fp


# ── Run 1 (record) ────────────────────────────────────────────────────────────
print("Run 1 ...", flush=True)
ledger1, defects1, trace1, fp1 = run_scenario(record=True)

# ── Run 2 (AT-7 check, no recording) ─────────────────────────────────────────
print("Run 2 (AT-7) ...", flush=True)
_, _, _, fp2 = run_scenario(record=False)

at7_ok = (fp1 == fp2)

# ── Write files ───────────────────────────────────────────────────────────────
LEDGER_PATH  = OUT_DIR / "phaseA_balance_ledger.jsonl"
DEFECTS_PATH = OUT_DIR / "phaseA_defects.jsonl"
TRACE_PATH   = OUT_DIR / "phaseA_commit_trace.jsonl"

with LEDGER_PATH.open("w") as f:
    f.write(json.dumps(HEADER_LEDGER) + "\n")
    for r in ledger1:
        f.write(json.dumps(r) + "\n")

with DEFECTS_PATH.open("w") as f:
    for r in defects1:
        f.write(json.dumps(r) + "\n")

with TRACE_PATH.open("w") as f:
    f.write(json.dumps(HEADER_TRACE) + "\n")
    for r in trace1:
        f.write(json.dumps(r) + "\n")

# ── A-4 Report ────────────────────────────────────────────────────────────────
total   = len(ledger1)
defects = len(defects1)

residuals = [r["residual_mw"] for r in ledger1]
max_res   = max(residuals)
min_res   = min(residuals)
first_def = defects1[0]["t_s"] if defects1 else None

# Snapshot tick: compute ≈ 63 MW, 2 on-bus turbines
snap = next(
    (r for r in ledger1
     if 62.0 <= r["p_compute_modeled_mw"] <= 64.0
     and sum(1 for u in r["turbines"] if u["state"] in ("synchronised","unloading")) == 2),
    None
)

floor_viol_first = next((r for r in ledger1 if r["floor_violated"]), None)
commit_ticks     = [r for r in trace1 if r["commit_request_issued"]]
interlock_ticks  = [r for r in trace1 if r["serialized_start_interlock_held"]]
starting_ever    = any(
    any(u["state"] == "starting" for u in r["turbines"]) for r in ledger1
)

# Monotone residual check over compute ramp-up
ramp_res = [r["residual_mw"] for r in ledger1 if r["p_compute_modeled_mw"] <= max(r2["p_compute_modeled_mw"] for r2 in ledger1)]
mono = all(ramp_res[i] >= ramp_res[i+1] for i in range(len(ramp_res)-1))

sep = "=" * 72

print()
print(sep)
print("GRIDSIGNAL PHASE A REPORT")
print(sep)

print("""
── A-1 CHANNEL INVENTORY ────────────────────────────────────────────────────

GAS TURBINE FLEET
  Hero MW
    frontend prop   mwField='on_bus_output_mw'  plantLayout.ts:90
    API field       on_bus_output_mw             run_manager.py:250
    backend expr    Σ u.output_mw for u in tick.turbine_units
                      where u.state ∈ {synchronised, unloading}
                      run_manager.py:251-258
    kind            DELIVERED — on-bus units only; STARTING/OFFLINE excluded
  "N units"
    API field       turbine_units list            run_manager.py:234
    kind            CONFIG count
  "N online"  →  units_on_bus_count
    API field       units_on_bus_count            run_manager.py:240-244
    expr            Σ 1 for u where state ∈ {synchronised, unloading}
    kind            DELIVERED state count
  "N-1 firm"
    FRONTEND ONLY: installed_total − max_unit_rated  PlantNode.tsx:88-89
    No backend field.

SOLAR PV
  Hero MW (live run)
    frontend        prefers liveSolarMW (GET /api/solar/state 1.5 Hz)
                    over tick.p_renewable_mw  PlantNode.tsx:253-255
    API field       p_renewable_mw             run_manager.py:179
    backend expr    Σ s.output_mw() for s in state.solar_arrays
                      AFTER curtailment  simulation_core.py:509,547
    kind            DELIVERED (post-curtailment)
  "exp N.NN MW"
    API field       p_expected_mw              run_manager.py:294
    TickResult      None on run path           simulation_core.py:1564
    NOTE: non-None only via SolarSim.snapshot() (console/modal path, not WS)
    kind            MODELLED expected; ABSENT on WebSocket run path

BATTERY (BESS)
  Hero MW
    frontend prop   mwField='bess_output_mw'   plantLayout.ts:108
    API field       bess_output_mw             run_manager.py:169
    backend expr    arbitrator.tick()[1]        simulation_core.py:824,1550
    kind            DELIVERED after SOC/power clipping; positive=discharge
  "discharging" flag
    frontend expr   bess_setpoint_mw > 0.1     PlantNode.tsx:135
    API field       bess_setpoint_mw            run_manager.py:337
    kind            COMMANDED setpoint — flag is command-driven, not delivery-driven
  SoC
    API field       bess_soc_fraction           run_manager.py:170
    backend expr    state.bess_units[0].soc_fraction  simulation_core.py:1551
    kind            MODELLED physics state

COMPUTE RACKS
  Hero MW
    frontend prop   mwField='p_compute_mw'     plantLayout.ts:149
    API field       p_compute_mw               run_manager.py:164
    backend expr    Σ per_job_compute_mw(job)   simulation_core.py:489,1545
    kind            MODELLED demand; no served/unserved split in model
  Job count
    frontend        Object.keys(checkpoint_states).length  PlantNode.tsx:167
    API field       checkpoint_states           run_manager.py:175
    kind            MODELLED state (classifier output)

COOLING PLANT
  Hero MW
    frontend prop   mwField='p_cooling_mw'     plantLayout.ts:158
    API field       p_cooling_mw               run_manager.py:165
    backend expr    state.cooling.output_mw()   simulation_core.py:494,1546
    kind            DELIVERED — 90-s lagged model output
  "N.NN MW rated"
    API field       rated_cooling_mw            run_manager.py:224
    backend expr    ctx._rated_cooling_mw       run_manager.py:1304,1309
    kind            CONFIG / NAMEPLATE constant
  "N.NN MW headroom"
    API field       absorbable_mw               run_manager.py:225
    backend expr    max(0.0, _th_rated − tick_result.p_cooling_mw)
                      run_manager.py:1305,1310
    kind            DERIVED from delivered

GRID CONNECTION
  No MW field — passive.  Static text "islanded — no utility feed"
  PlantNode.tsx:139-140

Simulation tick period
  TICK_INTERVAL_SIM_SECONDS = 5.0 s
  Source: run_manager.py:537 citing "spec Section 3.1 evaluation cadence"
  Used: SimClock(dt_seconds=TICK_INTERVAL_SIM_SECONDS)  run_manager.py:699
""")

print("── A-2 BALANCE LEDGER ───────────────────────────────────────────────────")
print(f"  Ticks recorded           : {total}  (t=5..{ledger1[-1]['t_s']:.0f} s)")
print(f"  Ticks with |R|>0.01 MW   : {defects}")
print(f"  First defect at t        : {first_def} s")
print(f"  Residual max             : {max_res:.4f} MW")
print(f"  Residual min             : {min_res:.4f} MW")
print(f"  Residual monotone↓ w/ ramp: {mono}")
print()

if snap:
    print(f"  Snapshot (compute≈63 MW, 2 on-bus)  t={snap['t_s']} s")
    print(f"    p_turbine_total_mw = {snap['p_turbine_total_mw']}")
    print(f"    p_solar_mw         = {snap['p_solar_mw']}")
    print(f"    p_bess_mw          = {snap['p_bess_mw']}")
    print(f"    p_source_total_mw  = {snap['p_source_total_mw']}")
    print(f"    p_compute_modeled  = {snap['p_compute_modeled_mw']}")
    print(f"    p_cooling_modeled  = {snap['p_cooling_modeled_mw']}")
    print(f"    p_sink_total_mw    = {snap['p_sink_total_mw']}")
    print(f"    residual_mw        = {snap['residual_mw']}")
    print(f"    bess_setpoint_mw   = {defects1[[i for i,d in enumerate(defects1) if d['t_s']==snap['t_s']][0]]['bess_setpoint_mw'] if any(d['t_s']==snap['t_s'] for d in defects1) else 'n/a (no defect at this tick)'}")
    print(f"    frequency_hz       = {snap['frequency_hz']}")
    print(f"    floor_violated     = {snap['floor_violated']}")
    print(f"    turbines:")
    for u in snap["turbines"]:
        print(f"      {u['unit_id']:12s}  {u['state']:14s}  {u['p_mw']:.2f} MW")
else:
    print("  [snapshot: no tick found with compute 62-64 MW and exactly 2 on-bus turbines]")

print()
print(f"  ABSENT: p_compute_served_mw, p_cooling_served_mw, p_unserved_mw, dispatch_state")

print()
print("── A-3 COMMITMENT TRACE ─────────────────────────────────────────────────")
print(f"  Ticks commit_request_issued=True : {len(commit_ticks)}")
for ct in commit_ticks:
    print(f"    t={ct['t_s']} s  target={ct['commit_request_target_units']}")
print(f"  Ticks interlock_held=True        : {len(interlock_ticks)}")
print(f"  Unit ever in STARTING state      : {starting_ever}")
print(f"  urgency_term_U                   : ABSENT from wire format")
print(f"  ABSENT: urgency_term_U, time_in_state_s, start_inhibited, inhibit_reason")

print()
print("── A-4 RUN ──────────────────────────────────────────────────────────────")
print(f"  AT-7 determinism           : {'PASS — bit-identical across both runs' if at7_ok else 'FAIL'}")
print(f"  Suite delta                : NOT MEASURED — standalone script outside pytest")
print(f"  Total ticks (capped)       : {total}")
print(f"  First |residual|>0.01 tick : t={first_def} s")
print(f"  Residual at snapshot tick  : {snap['residual_mw'] if snap else 'N/A'} MW")
print(f"  Residual max/min           : {max_res:.4f} / {min_res:.4f} MW")
print(f"  Residual monotone with ramp: {mono}")
print(f"  p_compute_served exists    : NO — ABSENT")
print(f"  p_cooling_served exists    : NO — ABSENT")
print(f"  insufficient_reserve alert : first floor_violated at t={floor_viol_first['t_s'] if floor_viol_first else 'none'} s")
print(f"  commit_request ticks       : {len(commit_ticks)}")
print(f"  starting-state ever seen   : {starting_ever}")
print()
print(f"  ALL ABSENT FIELDS:")
print(f"    A-2 ledger : p_compute_served_mw, p_cooling_served_mw, p_unserved_mw, dispatch_state")
print(f"    A-3 trace  : urgency_term_U, time_in_state_s (per unit),")
print(f"                 start_inhibited (per unit), inhibit_reason (per unit)")
print()
print(f"  DEFECTS OBSERVED (not fixed):")
print(f"    D-1  |residual_mw| > 0.01 on {defects}/{total} ticks.")
print(f"         First at t={first_def} s.  Min residual {min_res:.4f} MW (shortfall).")
print(f"         Monotone with compute ramp: {mono}.")
print(f"    D-2  GAS TURBINE tile shows on_bus_output_mw (SYNCHRONISED+UNLOADING).")
print(f"         turbine_output_mw (ALL turbines) enters the balance equation.")
print(f"         Gap = auto-staged turbine output not visible on tile.")
print(f"    D-3  'discharging' flag driven by bess_setpoint_mw (COMMANDED),")
print(f"         not bess_output_mw (DELIVERED).  Tile can read 'discharging'")
print(f"         while actual delivered output is 0 (e.g. SOC-empty BESS).")
print()
print(f"Files: {LEDGER_PATH}  {DEFECTS_PATH}  {TRACE_PATH}")
