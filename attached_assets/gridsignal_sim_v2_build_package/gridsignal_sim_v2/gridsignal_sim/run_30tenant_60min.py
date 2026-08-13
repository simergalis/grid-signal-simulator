#!/usr/bin/env python3
"""
run_30tenant_60min.py — Create and start a 60-min BESS+Grid+FuelCell run
with 30-tenant Kubernetes demand at maximum GPU node ceiling for the first
30 minutes, then reduced load for the second 30 minutes.

Usage:
    python3 run_30tenant_60min.py

The script:
  1. POSTs a new ScenarioSpec to /scenarios.
  2. POSTs /runs with the returned scenario_id.
  3. Prints the run_id and monitoring command.
"""

from __future__ import annotations
import json, sys, urllib.request, urllib.error

API = "http://localhost:22126"

# ── Scenario specification ────────────────────────────────────────────────────

SPEC = {
    # ── Identity ─────────────────────────────────────────────────────────────
    "name": "30-Tenant Max-GPU · BESS + Grid + Fuel Cell · 60 min",
    "description": (
        "60-minute run: Grid-tied (50 MW firm), 4-stack 20 MW Fuel Cell array, "
        "15 MW / 20 MWh BESS starting at 85 % SoC. No gas turbines, no solar. "
        "Kubernetes demand simulator fills cluster to 1 900 nodes (max ceiling) "
        "for first 30 min via fast-arriving gangs; gpu_load_profile steps down "
        "to 35 % at t=1800 s for the recovery window. "
        "30 tenants (A–E catalogued + 25 metered) represented proportionally "
        "via the demand fractions in ComputeRacksModal."
    ),

    # ── Hardware / timing ────────────────────────────────────────────────────
    "hardware_profile_id": "enterprise_8gpu_air",
    "dt_lead_seconds": 0.0,          # Kubernetes gives no advance notice
    "end_sim_time": 3600.0,          # 60 minutes
    "default_playback_speed": 1.0,

    # ── Generation fleet ─────────────────────────────────────────────────────
    "turbine_units": [],             # NO gas turbines
    "solar_rated_mw": 0.0,          # NO solar PV
    "irradiance_steps": [],

    "fuel_cell_enabled": True,
    "fuel_cell_rated_mw": 20.0,
    "fuel_cell_stack_count": 4,

    "bess_units": [
        {
            "asset_id": "bess-1",
            "rated_mw":             15.0,   # larger than base demo — no turbine headroom
            "usable_mwh":           20.0,
            "initial_soc_fraction": 0.85,
            "grid_forming":         False,
            "p_anchor_reserve_mw":  1.5,
        }
    ],

    # ── Site / grid ───────────────────────────────────────────────────────────
    "island_mode": False,            # grid-tied
    "frequency_nominal_hz": 60.0,
    "design_peak_load_mw": 40.0,    # FC 20 + BESS 15 + grid headroom

    # Grid procurement (firm 50 MW, reserved 10 MW, non-firm 5 MW)
    "procurement_config": {
        "firm_available_mw":      50.0,
        "reserved_available_mw":  10.0,
        "non_firm_available_mw":   5.0,
        "price_curve_seed":       42,
    },

    # ── GPU load profile ──────────────────────────────────────────────────────
    # Full load (1.0 = 100 %) for first 30 min; step down to 35 % for recovery.
    "gpu_load_profile": [
        [0.0,    1.0],   # t=0 — max ceiling
        [1800.0, 0.35],  # t=30 min — recovery / part-load
    ],

    # ── Kubernetes demand simulator ───────────────────────────────────────────
    # 1 900-node cluster, fast interarrival (15 s mean) → cluster fills quickly.
    # Large mean gang size (450 nodes) → discrete big jobs, not noise.
    # 30 tenants are represented implicitly: ComputeRacksModal apportions the
    # live p_compute_demand_mw across tenants A–E + 25 metered cages by frac.
    "kube_config": {
        "hardware_profile_id": "enterprise_8gpu_air",
        "max_nodes":            1900,
        "min_nodes":             200,
        "mean_interarrival_s":  15.0,   # fast arrivals → ceiling reached quickly
        "mean_job_nodes":        450,
        "job_node_std":          120.0,
        "min_job_nodes":         100,
        "mean_job_duration_s":   480.0, # 8-min mean job → sustained high load
        "min_job_duration_s":     60.0,
        "reorder_window_s":       10.0,
        "ntp_jitter_s":            2.0,
        "headroom_threshold_mw":   2.5,
        "rng_seed":               42,
        "step_config":            None,
        "load_config":            None,
    },

    # ── Thermal / physics parameters ──────────────────────────────────────────
    "power_factor":         0.85,
    "pue_base":             1.35,
    "dt_thermal_seconds":   90.0,
    "alpha_max":            0.2,
    "tau_seconds":          20.0,
    "anchor_reserve_pct":   0.0,
    "band_enabled":         False,
    "band_pct_calibrated":  0.0,
    "band_mult_uncalibrated": 2.0,
    "band_mult_unmapped_hw":  1.5,

    # ── Frontend GPU generator config (burst mode — all 3 scheduler tenants) ──
    # Tenants A (Slurm), B (Kubernetes), C (Ray) push jobs at max weight.
    "generator_config": {
        "ratePerMinute":        8,
        "burstMode":            True,
        "burstSize":            [5, 12],
        "burstIntervalSeconds": [30, 90],
        "tenantWeights":        {"a": 0.40, "b": 0.35, "c": 0.25},
        "jobSizes":             {"small": 0.20, "medium": 0.45, "large": 0.35},
        "maxJobsPerTenant":     20,
        "jobDurationRange":     [120, 480],
        "tenantContracts":      {"a": 1.40, "b": 1.00, "c": 0.60},
    },

    # ── Misc ──────────────────────────────────────────────────────────────────
    "calibrated":           False,
    "assertions":           [],
    "ambient_steps":        [],
    "dq_inject_events":     [],
    "workload_events":      [],
    "tenant_events":        [],
}


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[ERROR] {e.code} {e.reason}: {body}")
        sys.exit(1)


def main() -> None:
    print("── Step 1: Creating scenario ────────────────────────────────────────")
    scenario_resp = post_json("/scenarios", SPEC)
    scenario_id   = scenario_resp["scenario_id"]
    print(f"  scenario_id : {scenario_id}")
    print(f"  name        : {scenario_resp.get('name', SPEC['name'])}")

    print("\n── Step 2: Starting run ─────────────────────────────────────────────")
    run_resp = post_json("/runs", {"scenario_id": scenario_id})
    run_id   = run_resp["run_id"]
    print(f"  run_id      : {run_id}")

    print("\n── Step 3: Monitor command ──────────────────────────────────────────")
    print(f"  python3 monitor_live.py {run_id}")
    print()
    print(f"  Or stream ticks:  wscat -c ws://localhost:22126/ws/{run_id}")
    print()

    # Write run_id to a temp file so monitor can auto-pick it up
    with open("/tmp/gridsignal_last_run_id", "w") as f:
        f.write(run_id)
    print(f"  run_id saved to /tmp/gridsignal_last_run_id")


if __name__ == "__main__":
    main()
