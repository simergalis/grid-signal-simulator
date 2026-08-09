"""SC-20-shaped synthetic run: staircase admission, commit/decommit, a solar
field going null, and a transient data-quality tag. Used to exercise the
detector at realistic length. Not a model of the real system."""
from fixtures import tick

def build(n=800):
    payloads = []
    for i in range(n):
        t = 10.0 + 5.0 * i
        batches = min(int(max(0.0, t - 100) // 35), 26)
        if t > 2400: batches = max(0, 26 - int((t - 2400) // 35))
        compute = 5.0 + batches * 0.75
        cooling = 0.9 + compute * 0.19
        demand = compute + cooling
        on_bus = 2 if 900 <= t < 3600 else 1
        units = [{"unit_id": f"turbine-{u}",
                  "state": "synchronised" if u < on_bus else "offline",
                  "output_mw": round(min(7.0, demand / max(on_bus,1)),3) if u < on_bus else 0.0,
                  "rated_mw": 7.0, "hot_standby": False} for u in range(5)]
        tags = ["UNCALIBRATED_SITE"] + (["WORKLOAD_SIGNAL_STALE"] if 1500 < t < 1700 else [])
        payloads.append(tick(
            sim_time_seconds=t, p_demand_mw=demand, p_total_mw=demand,
            p_compute_demand_mw=compute, p_compute_mw=compute,
            p_cooling_demand_mw=cooling, p_cooling_mw=cooling,
            p_generation_mw=demand, turbine_output_mw=7.0*on_bus*0.8,
            p_served_mw=demand, p_unserved_mw=0.0,
            p_compute_served_mw=compute, p_compute_unserved_mw=0.0,
            p_cooling_served_mw=cooling, p_cooling_unserved_mw=0.0,
            rated_cooling_mw=12.0, bess_rated_mw=15.0, bess_usable_mwh=8.0,
            bess_output_mw=2.0 if 900 <= t < 3600 else 0.0,
            bess_soc_fraction=round(0.95 - i*0.0004, 6),
            turbine_units=units, data_quality_tags=tags,
            d4_balance_defect_mw=0.0, grid_exchange_mw=0.0,
            asset_delivery_error_mw=0.0, frequency_forcing_mw=0.0,
            protection_provisional=True,
            p_expected_mw=None if t > 3000 else 4.0,
            frequency_hz=round(60.0 + (0.02 if i % 3 else -0.02), 4),
            commitment_block={"action": "commit" if t==900 else ("decommit" if t==3600 else "hold"),
                              "committed_rated_mw": 7.0*on_bus,
                              "reserve_floor_mw": demand + 7.0,
                              "reserve_satisfied": (7.0*on_bus) >= (demand+7.0),
                              "utilisation": 0.8}))
    return payloads
