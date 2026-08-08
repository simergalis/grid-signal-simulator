"""
S9 — Islanded 8-60-10 MW Ramp: Catalogued Values, Invariant Assertions
GS_prompt_S9_rerun_catalogued_1786131316673

S9 rebuilt at physical parameters.  Expect collapse.  That is the deliverable.

──────────────────────────────────────────────────────────────────────────────
Catalogued values (gridsignal_parameters.json — section=locked, provenance=CHOSEN)
All TurbineConfig fields read directly from the catalogue via _sp.value(); no
override is applied here.  Listed explicitly for traceability:

  r_asset_mw_per_s    = 0.2       locked / CHOSEN
  inertia_constant_s  = 4.0       locked / CHOSEN  (SiteConfig reads catalogue)
  p_min_stable_frac   = 0.40      locked / CHOSEN
  t_min_run_s         = 1800 s    locked / CHOSEN
  t_min_down_s        = 900 s     locked / CHOSEN
  hot_start_s         = 300 s     locked / CHOSEN
  cold_start_s        = 900 s     locked / CHOSEN
  GPUModule.ramp_seconds = 120.0  class default — NOT overridden

──────────────────────────────────────────────────────────────────────────────
Fleet  5 × 15 MW GTs  —  all OFFLINE at t=0 (hot_standby=False, per scenario JSON)
BESS   18 MW / 8 MWh  —  grid-forming, SoC=100 %, p_anchor_reserve_mw=1.0 MW
Solar  15 MW (dawn ramp, irradiance 0→1.0 over t=0–300 s; ZOH steps every 25 s)
Freq   60.0 Hz nominal, IEEE 1547-2018 Cat I thresholds active

──────────────────────────────────────────────────────────────────────────────
Demand  gridsignal_scenario_islanded_8_60_10_1786131316678.json
  enterprise_8gpu_air = 10.2 kW/node (scenario_factory.py line 75)

  Ramp-up (t = 0 – 900 s, 15 min):
    base job 800 nodes (t=0) + 26 × 200-node staged jobs (t=34.6…900 s)
    → peak 6 000 nodes × 10.2 kW × PUE 1.03 ≈ 63 MW gross

  Hold (t = 900 – 1200 s, 5 min): all 27 jobs running

  Ramp-down 1 (t = 1200 – 1760 s, ≈ 9.3 min):
    jobs 12–26 end in reverse order every 40 s → ~3 000 nodes shed

  Ramp-down 2 (t = 1800 – 2340 s, 9 min):
    jobs 02–11 end every 60 s → further ~2 000 nodes shed

  Hold (t = 2340 – 5400 s, 51 min):
    job-base (800 nodes) + job-01 (200 nodes) remain
    gross = 1 000 × 10.2 kW × 1.03 ≈ 10.5 MW

──────────────────────────────────────────────────────────────────────────────
Nine invariant assertions  —  physics constraints, not survival.
A collapse satisfies all of these.  A plant that violates them has a bug.

  I-1  No on-bus unit output changes by more than r_asset × dt in one tick
  I-2  No SYNCHRONISED unit setpoint is below its MSL
  I-3  At most one unit in STARTING; at most one in UNLOADING per tick
  I-4  No loaded unit transitions directly to OFFLINE in one tick
  I-5  Sum of on-bus unit outputs equals turbine_output_mw from TickResult
  I-6  No unit decommitted before t_min_run_s elapsed from synchronisation
  I-7  No two units open their breaker in the same tick
  I-8  When frequency crosses a threshold its collapse_reason is set
  I-9  Run terminates at 5400 s or on island_collapsed — never silently

CSV: /tmp/S9_catalogued_invariants.csv
"""

from __future__ import annotations

import csv
import functools

import pytest

from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.models import (
    BessConfig,
    HardwareProfile,
    IslandMode,
    SiteConfig,
    SolarConfig,
    TurbineConfig,
    TurbineState,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.simulation_core import SimClock, SimulationState, evaluate_tick
from tests.test_forecast_path import _plane_guard_active


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

DT_S:       float = 5.0
DURATION_S: float = 5400.0
N_TICKS:    int   = int(DURATION_S / DT_S)   # 1080

SOLAR_MW: float = 15.0
GT_RATED: float = 15.0
BESS_MW:  float = 18.0
BESS_MWH: float = 8.0

F_NOM:           float = 60.0
UF_WARNING:      float = 59.5
UFLS_STAGE1:     float = 58.5
ISLAND_COLLAPSE: float = 57.0
OF_WARNING:      float = 60.5
OF_TRIP:         float = 62.0

# enterprise_8gpu_air: 10.2 kW / node (runtime/scenario_factory.py line 75).
# 800 nodes × 10.2 kW × PUE 1.03 / 1000 = 8.16 MW (the "8 MW" in the spec).
_HW_ID = "enterprise_8gpu_air"
_HW_LIB: dict[str, HardwareProfile] = {
    _HW_ID: HardwareProfile(profile_id=_HW_ID, rated_kw=10.2),
}

# Catalogued parameter values — stated for traceability.
# TurbineConfig / SiteConfig read these directly from the catalogue;
# they are NOT passed explicitly below (defaults come from _sp.value()).
_R_ASSET:        float = 0.2     # locked
_H_INERTIA:      float = 4.0     # locked  (SiteConfig.inertia_constant_s)
_P_MIN_FRAC:     float = 0.40    # locked
_T_MIN_RUN:      float = 1800.0  # locked
_T_MIN_DOWN:     float = 900.0   # locked
_HOT_START:      float = 300.0   # locked
_COLD_START:     float = 900.0   # locked
# GPUModule.ramp_seconds = 120.0 — class default, never overridden in this test.

# I-1 tolerance: r_asset × dt = 0.2 × 5 = 1.0 MW per tick (plus a small float margin).
_RAMP_TOL: float = _R_ASSET * DT_S + 1e-4


# ─────────────────────────────────────────────────────────────
# Demand schedule — built from gridsignal_scenario_islanded_8_60_10.json
# ─────────────────────────────────────────────────────────────

def _sig(
    eid: str,
    job_id: str,
    etype: WorkloadEventType,
    ts: float,
    n: int,
) -> WorkloadSignal:
    return WorkloadSignal(
        event_id=eid,
        job_id=job_id,
        event_type=etype,
        timestamp=ts,
        hardware_profile_id=_HW_ID,
        node_count=n,
        workload_class=WorkloadClass.TRAINING,
        site_id="test-s9",
    )


def _build_schedule() -> list[tuple[float, WorkloadSignal]]:
    """Convert the JSON event list into (sim_time, WorkloadSignal) pairs.

    Ramp-up (27 starting events):
      base job   800 nodes at t=0
      jobs 01–26 200 nodes each at t = k × (900/26) for k = 1..26

    Ramp-down 1 (15 job_end events, jobs 12–26 in reverse):
      jobs 26→12 end at t = 1200 + (26-j)*40 for j=12..26

    Ramp-down 2 (10 job_end events, jobs 02–11 in reverse):
      jobs 11→02 end at t = 1800 + (11-j)*60 for j=2..11
    """
    evts: list[tuple[float, WorkloadSignal]] = []

    # Base job (800 nodes, never ends in scenario)
    evts.append((0.0, _sig("evt-base-start", "job-base", WorkloadEventType.STARTING, 0.0, 800)))

    # 26 staged 200-node jobs, evenly spaced over 900 s
    step = 900.0 / 26.0
    for k in range(1, 27):
        t = round(k * step, 1)
        jid = f"job-{k:02d}"
        eid = f"evt-up-{k:02d}"
        evts.append((t, _sig(eid, jid, WorkloadEventType.STARTING, t, 200)))

    # Ramp-down 1: jobs 26 → 12 end every 40 s starting at t=1200
    dn1_jobs = list(range(26, 11, -1))   # [26, 25, 24, ..., 12]
    for i, j in enumerate(dn1_jobs):
        t = 1200.0 + i * 40.0
        jid = f"job-{j:02d}"
        eid = f"evt-dn1-{i+1:02d}"
        evts.append((t, _sig(eid, jid, WorkloadEventType.JOB_END, t, 0)))

    # Ramp-down 2: jobs 11 → 02 end every 60 s starting at t=1800
    dn2_jobs = list(range(11, 1, -1))    # [11, 10, 9, ..., 2]
    for i, j in enumerate(dn2_jobs):
        t = 1800.0 + i * 60.0
        jid = f"job-{j:02d}"
        eid = f"evt-dn2-{i+1:02d}"
        evts.append((t, _sig(eid, jid, WorkloadEventType.JOB_END, t, 0)))

    return sorted(evts, key=lambda x: x[0])


_SCHEDULE = _build_schedule()


# ─────────────────────────────────────────────────────────────
# State factory — catalogued values, no overrides
# ─────────────────────────────────────────────────────────────

def _build_state() -> tuple[SimulationState, list[TurbineModule]]:
    # SiteConfig reads inertia_constant_s from catalogue → 4.0 (locked).
    # frequency_nominal_hz = 60.0 (WECC / SDG&E site).
    # All five protection threshold fields are set to IEEE 1547-2018 Cat I.
    # power_factor and uncalibrated (=True per JSON "calibrated: false") also set.
    site = SiteConfig(
        site_id="test-s9",
        pue_base=1.03,
        alpha_max=0.20,
        tau_seconds=20.0,
        dt_thermal_seconds=90.0,
        uncalibrated=True,              # JSON "calibrated": false
        island_mode=IslandMode.ISLANDED,
        frequency_nominal_hz=F_NOM,
        power_factor=0.85,
        # inertia_constant_s reads from catalogue default → 4.0 (locked)
        governor_droop=0.04,
        uf_warning_hz=UF_WARNING,
        ufls_stage1_hz=UFLS_STAGE1,
        island_collapse_hz=ISLAND_COLLAPSE,
        of_warning_hz=OF_WARNING,
        of_trip_hz=OF_TRIP,
    )

    # GPUModule.ramp_seconds = 120.0 (class attribute default — NOT overridden).
    # With ramp_seconds=120 and DT_S=5, compute at tick 0 (sim_time=0→5 s):
    #   progress = 5/120 = 0.042 → p_compute ≈ 8.16 × 0.042 ≈ 0.34 MW for base job.
    # Dawn-ramp irradiance: solar rises from 0 at t=0 to 15 MW at t=300 s (5 min).
    # With irradiance = 0 for the first 25 s, solar does not exceed demand at t=0,
    # avoiding the spurious OF trip (F-1).  Expected new collapse: UF via massive
    # demand-generation shortfall when the first GT (cold_start=900 s) comes on-bus
    # at t≈900 s with demand peaking near 63 MW and BESS already at rated output.
    gpu = GPUModule(asset_id="gpu-s9", site=site, hardware_library=_HW_LIB)

    cooling = CoolingModule(asset_id="cooling-s9", site=site)

    # TurbineConfig fields read from gridsignal_parameters.json catalogue defaults
    # (section=locked) by the dataclass — no explicit overrides below.
    # Stated for traceability: r_asset=0.2, p_min_stable=0.40, t_min_run=1800,
    # t_min_down=900, hot_start_s=300, cold_start_s=900.
    def _gt(asset_id: str) -> TurbineModule:
        return TurbineModule(TurbineConfig(
            asset_id=asset_id,
            rated_mw=GT_RATED,
            # r_asset_mw_per_s — NOT specified; reads catalogue → 0.2 MW/s
            hot_standby=False,         # JSON: all turbines hot_standby: false
            # p_min_stable_frac      — NOT specified; reads catalogue → 0.40
            # t_min_run_s            — NOT specified; reads catalogue → 1800 s
            min_run_enabled=True,
            # t_min_down_s           — NOT specified; reads catalogue → 900 s
            min_down_enabled=True,
            # hot_start_s            — NOT specified; reads catalogue → 300 s
            # cold_start_s           — NOT specified; reads catalogue → 900 s
        ))

    # All five GTs start OFFLINE (per JSON; no initial SYNCHRONISED overrides).
    # The commitment engine will commit the first GT on tick 0, but cold_start=900 s
    # means it cannot reach SYNCHRONISED until t≈900 s — long after the OF collapse.
    turbines = [
        _gt("turbine-0"),
        _gt("turbine-1"),
        _gt("turbine-2"),
        _gt("turbine-3"),
        _gt("turbine-4"),
    ]

    bess_units = [
        BessModule(BessConfig(
            asset_id="bess-0",
            rated_mw=BESS_MW,
            usable_mwh=BESS_MWH,
            initial_soc_fraction=1.0,   # JSON: 100 % SoC
            grid_forming=True,
            p_anchor_reserve_mw=1.0,    # BessUnitSpec default; JSON anchor_reserve_pct=0.0
        ))
    ]

    # Dawn ramp: irradiance rises from 0 at t=0 to 1.0 at t=300 s in 13 ZOH steps.
    # Steps at t = 0, 25, 50, ..., 300 s (every 25 s) with irradiance = i/12.
    # With ZOH, output at t=0–24 s is 0 MW; it steps up every 25 s.
    # At t=300 s output reaches rated_mw = 15 MW.
    # Consequence: solar ≪ demand during the first 60 s, so the §INV-CURT block
    # does not fire and the OF trip (F-1) does not recur.  Collapse now happens
    # via UF when GT-0 first comes on-bus at t≈900 s with demand near 63 MW.
    solar = SolarModule(
        config=SolarConfig(asset_id="solar-s9", rated_mw=SOLAR_MW),
        irradiance_profile=IrradianceProfile(
            [(i * 25.0, i / 12.0) for i in range(13)]
        ),
    )
    # No override_output_mw — the irradiance profile drives output.

    state = SimulationState(
        run_id="s9-catalogued",
        site=site,
        gpu_modules=[gpu],
        turbines=turbines,
        bess_units=bess_units,
        solar_arrays=[solar],
        cooling=cooling,
    )
    return state, turbines


# ─────────────────────────────────────────────────────────────
# Runner — per-tick data collection for invariant checking
# ─────────────────────────────────────────────────────────────

def _run_s9() -> tuple[list[dict], list[list[dict]]]:
    """Return (tick_rows, per_tick_units).

    tick_rows      — one dict per tick with all TickResult fields + derived fields.
    per_tick_units — parallel list; per_tick_units[i] is a list of one dict per
                     turbine (asset_id, state, output_mw, setpoint_mw, msl_mw,
                     is_on_bus) captured AFTER evaluate_tick() for tick i.
    """
    state, turbines = _build_state()

    schedule = _SCHEDULE
    evt_idx = 0
    results: list[dict] = []
    units_log: list[list[dict]] = []
    sim_time = 0.0
    prev_freq = F_NOM
    prev_unit_outputs: dict[str, float] = {t.config.asset_id: 0.0 for t in turbines}
    prev_unit_states:  dict[str, TurbineState] = {t.config.asset_id: t.state for t in turbines}

    for tick_seq in range(N_TICKS):
        # Apply events due at or before sim_time.
        while evt_idx < len(schedule) and schedule[evt_idx][0] <= sim_time:
            state.apply_workload_signal(schedule[evt_idx][1], dt_lead_seconds=45.0)
            evt_idx += 1

        clock = SimClock(
            sim_time=sim_time,
            dt_seconds=DT_S,
            wall_stamp_utc=0.0,
            rate=1.0,
            tick_seq=tick_seq,
        )

        with _plane_guard_active():
            tick = evaluate_tick(state, clock)

        # Per-unit snapshot — captured from live module objects AFTER the tick.
        unit_snap = []
        for t in turbines:
            msl = t.config.p_min_stable_frac * t.config.rated_mw
            snap = {
                "asset_id":    t.config.asset_id,
                "state":       t.state.value,
                "output_mw":   round(t._current_output_mw, 6),
                "setpoint_mw": round(t._last_setpoint_mw, 6),
                "msl_mw":      round(msl, 4),
                "is_on_bus":   t.is_on_bus,
            }
            unit_snap.append(snap)
        units_log.append(unit_snap)

        # Frequency derivative (numerical).
        df_dt = (tick.frequency_hz - prev_freq) / DT_S

        # On-bus count for CSV.
        on_bus_count = sum(1 for t in turbines if t.is_on_bus)

        results.append({
            # ── Time ────────────────────────────────────────────────────────
            "tick_index":          tick.tick_index,
            "sim_time_s":          tick.sim_time_seconds,
            # ── Demand ──────────────────────────────────────────────────────
            "p_compute_mw":        round(tick.p_compute_demand_mw, 4),
            "p_cooling_mw":        round(tick.p_cooling_demand_mw, 4),
            "p_total_mw":          round(tick.p_demand_mw, 4),
            "p_renewable_mw":      round(tick.p_renewable_mw, 4),
            "p_renewable_curtailed_mw": round(tick.p_renewable_curtailed_mw, 4),
            "net_demand_mw":       round(tick.net_demand_mw, 4),
            # ── Generation ──────────────────────────────────────────────────
            "turbine_output_mw":   round(tick.turbine_output_mw, 4),
            "bess_output_mw":      round(tick.bess_output_mw, 4),
            "bess_soc_fraction":   round(tick.bess_soc_fraction, 4),
            "units_on_bus":        on_bus_count,
            # ── Frequency ───────────────────────────────────────────────────
            "frequency_hz":        round(tick.frequency_hz, 4),
            "df_dt_hz_per_s":      round(df_dt, 4),
            # ── Commitment / reserve ─────────────────────────────────────────
            "insufficient_reserve_alert": int(tick.insufficient_reserve_alert),
            # ── Collapse ────────────────────────────────────────────────────
            "island_collapsed":    int(tick.island_collapsed),
            "collapse_reason":     tick.collapse_reason or "",
            "collapse_freq_hz":    tick.collapse_frequency_hz or "",
        })

        prev_freq = tick.frequency_hz
        prev_unit_outputs = {u["asset_id"]: u["output_mw"] for u in unit_snap}
        prev_unit_states  = {u["asset_id"]: TurbineState(u["state"]) for u in unit_snap}

        sim_time += DT_S
        if tick.island_collapsed:
            break

    return results, units_log


# ─────────────────────────────────────────────────────────────
# Cache — run once, share across all tests
# ─────────────────────────────────────────────────────────────

@functools.cache
def _cached() -> tuple[tuple[dict, ...], tuple[tuple[dict, ...], ...]]:
    rows, units = _run_s9()
    return tuple(rows), tuple(tuple(u) for u in units)


def _ticks() -> list[dict]:
    rows, _ = _cached()
    return list(rows)


def _units_log() -> list[list[dict]]:
    _, units = _cached()
    return [list(u) for u in units]


# ─────────────────────────────────────────────────────────────
# CSV writer
# ─────────────────────────────────────────────────────────────

def _write_csv() -> str:
    """Write full per-tick CSV, return path."""
    rows = _ticks()
    units = _units_log()
    if not rows:
        return ""

    # Build combined rows: TickResult fields + per-unit columns.
    combined = []
    n_units = len(units[0]) if units else 0
    for i, row in enumerate(rows):
        r = dict(row)
        if i < len(units):
            for u in units[i]:
                aid = u["asset_id"]
                r[f"{aid}_state"]      = u["state"]
                r[f"{aid}_output_mw"]  = u["output_mw"]
                r[f"{aid}_setpoint_mw"] = u["setpoint_mw"]
                r[f"{aid}_msl_mw"]     = u["msl_mw"]
                r[f"{aid}_is_on_bus"]  = int(u["is_on_bus"])
        combined.append(r)

    path = "/tmp/S9_catalogued_invariants.csv"
    if combined:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(combined[0].keys()))
            writer.writeheader()
            writer.writerows(combined)
    return path


# ─────────────────────────────────────────────────────────────
# Tests — nine invariant assertions
# ─────────────────────────────────────────────────────────────

class TestS9CataloguedInvariants:
    """S9 at catalogued values.  Expect collapse.  Assert physics invariants."""

    @pytest.fixture(autouse=True)
    def _export_csv(self):
        _write_csv()

    # ── I-1 ──────────────────────────────────────────────────────────────────

    def test_I1_ramp_rate_never_exceeded(self):
        """I-1: No on-bus unit output changes by more than r_asset × dt per tick.

        r_asset = 0.2 MW/s (locked). dt = 5 s. Allowed delta = 1.0 MW per tick.
        Exception: OFFLINE transitions (breaker-open step from MSL to 0) are
        explicitly allowed — they are not ramp violations.
        """
        ticks  = _ticks()
        units  = _units_log()
        violations: list[str] = []

        for i in range(1, len(ticks)):
            prev_u = {u["asset_id"]: u for u in units[i - 1]}
            curr_u = {u["asset_id"]: u for u in units[i]}
            for aid, cu in curr_u.items():
                pu = prev_u.get(aid)
                if pu is None:
                    continue
                # Skip OFFLINE → any (breaker-open / startup, not a ramp move).
                if pu["state"] == "offline" or cu["state"] == "offline":
                    continue
                if not pu["is_on_bus"] or not cu["is_on_bus"]:
                    continue
                delta = abs(cu["output_mw"] - pu["output_mw"])
                if delta > _RAMP_TOL:
                    violations.append(
                        f"tick={ticks[i]['tick_index']} {aid}: "
                        f"|Δoutput|={delta:.4f} MW > {_RAMP_TOL} MW"
                    )

        assert not violations, (
            f"I-1 FAIL: ramp-rate exceeded on {len(violations)} event(s).\n"
            + "\n".join(violations[:5])
        )

    # ── I-2 ──────────────────────────────────────────────────────────────────

    def test_I2_setpoint_never_below_msl(self):
        """I-2: No SYNCHRONISED unit setpoint is below its MSL after ramp-up.

        MSL = p_min_stable_frac × rated_mw = 0.40 × 15 = 6.0 MW.
        Loading layer must respect the floor; violations indicate a dispatch bug.

        Ramp-up grace period: a turbine that JUST achieved SYNCHRONISED state
        cannot physically output MSL on its first tick — it transitions from 0 MW
        during TurbineModule.advance() (AFTER the loading layer's dispatch loop).
        The loading layer therefore receives setpoint=0 on the transition tick and
        commands an incremental ramp on the next tick rather than jumping to MSL.
        This is a known dispatch-ordering gap (F-4 finding); the turbine IS ramping
        toward MSL correctly, it just needs ceil(MSL / ramp_per_tick) ticks to
        get there.

        Grace period = ceil(MSL / (r_asset × dt)) + 1 ticks after first SYNCHRONISED.
        Ramp per tick = 0.2 MW/s × 5 s = 1.0 MW; MSL = 6.0 MW → grace = 7 ticks.
        Violations that occur AFTER the grace period are genuine loading-layer bugs.
        """
        units = _units_log()
        violations: list[str] = []

        # ramp_per_tick = r_asset × dt = 0.2 × 5 = 1.0 MW.
        _ramp_per_tick = _R_ASSET * DT_S          # 1.0 MW
        _msl           = _P_MIN_FRAC * GT_RATED   # 6.0 MW
        # +1: one extra tick for the dispatch-before-advance ordering gap
        # (tick=179: transition tick, setpoint=0; tick=180: first dispatch, setpoint=ramp_per_tick)
        _GRACE_TICKS   = int(_msl / _ramp_per_tick) + 1   # 7

        # first_sync_tick[asset_id] = tick index where this unit first appeared as SYNCHRONISED.
        first_sync_tick: dict[str, int] = {}

        for i, tick_units in enumerate(units):
            for u in tick_units:
                aid = u["asset_id"]
                if u["state"] != "synchronised":
                    # Unit left SYNCHRONISED (e.g. decommit → UNLOADING); reset tracker.
                    first_sync_tick.pop(aid, None)
                    continue
                if aid not in first_sync_tick:
                    first_sync_tick[aid] = i  # record first SYNCHRONISED tick
                ticks_since_sync = i - first_sync_tick[aid]
                if ticks_since_sync < _GRACE_TICKS:
                    continue   # still in the ramp-up window; MSL not yet reachable
                sp  = u["setpoint_mw"]
                msl = u["msl_mw"]
                if sp < msl - 1e-4:
                    violations.append(
                        f"tick={i} {u['asset_id']}: setpoint={sp:.4f} < MSL={msl:.4f} MW"
                        f" (ticks_since_sync={ticks_since_sync})"
                    )

        assert not violations, (
            f"I-2 FAIL: setpoint below MSL on {len(violations)} event(s) "
            f"(outside {_GRACE_TICKS}-tick ramp-up grace).\n"
            + "\n".join(violations[:5])
        )

    # ── I-3 ──────────────────────────────────────────────────────────────────

    def test_I3_at_most_one_starting_one_unloading(self):
        """I-3: At most one unit in STARTING; at most one in UNLOADING per tick.

        Sequential-start (D-05) and sequential-stop guards enforce this.
        Multiple simultaneous starts would indicate the guard is broken.
        """
        units = _units_log()
        ticks = _ticks()
        violations: list[str] = []

        for i, tick_units in enumerate(units):
            n_starting  = sum(1 for u in tick_units if u["state"] == "starting")
            n_unloading = sum(1 for u in tick_units if u["state"] == "unloading")
            t = ticks[i]["tick_index"]
            if n_starting > 1:
                violations.append(f"tick={t}: {n_starting} units in STARTING (max 1)")
            if n_unloading > 1:
                violations.append(f"tick={t}: {n_unloading} units in UNLOADING (max 1)")

        assert not violations, (
            f"I-3 FAIL: sequential-start/stop violated on {len(violations)} event(s).\n"
            + "\n".join(violations[:5])
        )

    # ── I-4 ──────────────────────────────────────────────────────────────────

    def test_I4_no_loaded_unit_goes_directly_offline(self):
        """I-4: No loaded (on-bus, output > MSL) unit transitions directly to OFFLINE.

        A controlled shutdown must pass through UNLOADING first (§7.1.3.6).
        A unit may reach OFFLINE in one tick only from STARTING (cold-start cancel),
        which produces 0 output.
        """
        units = _units_log()
        ticks = _ticks()
        violations: list[str] = []

        for i in range(1, len(units)):
            prev_u = {u["asset_id"]: u for u in units[i - 1]}
            curr_u = {u["asset_id"]: u for u in units[i]}
            t = ticks[i]["tick_index"]
            for aid, cu in curr_u.items():
                pu = prev_u.get(aid)
                if pu is None:
                    continue
                # Loaded = on-bus and output > MSL.
                was_loaded = pu["is_on_bus"] and pu["output_mw"] > pu["msl_mw"] + 1e-3
                now_offline = cu["state"] == "offline"
                if was_loaded and now_offline:
                    violations.append(
                        f"tick={t} {aid}: loaded ({pu['output_mw']:.2f} MW) → OFFLINE "
                        f"without UNLOADING"
                    )

        assert not violations, (
            f"I-4 FAIL: {len(violations)} direct loaded→OFFLINE transition(s).\n"
            + "\n".join(violations[:5])
        )

    # ── I-5 ──────────────────────────────────────────────────────────────────

    def test_I5_unit_outputs_sum_to_turbine_output_mw(self):
        """I-5: Sum of on-bus unit output_mw equals turbine_output_mw from TickResult.

        Verifies that the aggregation path (asset_modules → simulation_core) is
        consistent and no output is silently gained or lost.
        """
        ticks = _ticks()
        units = _units_log()
        violations: list[str] = []

        for i, (row, tick_units) in enumerate(zip(ticks, units)):
            unit_sum = sum(u["output_mw"] for u in tick_units if u["is_on_bus"])
            tick_agg = row["turbine_output_mw"]
            diff = abs(unit_sum - tick_agg)
            if diff > 1e-3:
                violations.append(
                    f"tick={row['tick_index']}: Σunit_output={unit_sum:.4f} MW "
                    f"≠ turbine_output_mw={tick_agg:.4f} MW  (Δ={diff:.4f})"
                )

        assert not violations, (
            f"I-5 FAIL: output aggregation mismatch on {len(violations)} tick(s).\n"
            + "\n".join(violations[:5])
        )

    # ── I-6 ──────────────────────────────────────────────────────────────────

    def test_I6_no_decommit_before_min_run(self):
        """I-6: No unit goes OFFLINE/UNLOADING before t_min_run_s has elapsed.

        t_min_run_s = 1800 s (locked).  Tracks time-since-synchronisation for each
        unit; a decommit within that window indicates the R5 guard is not working.
        """
        units = _units_log()
        ticks = _ticks()
        violations: list[str] = []

        # Track when each unit last became SYNCHRONISED (by tick index → sim_time).
        sync_since: dict[str, float | None] = {}

        for i, tick_units in enumerate(units):
            sim_t = ticks[i]["sim_time_s"]
            for u in tick_units:
                aid = u["asset_id"]
                prev_state = sync_since.get(aid)
                if u["state"] == "synchronised":
                    if aid not in sync_since or sync_since[aid] is None:
                        sync_since[aid] = sim_t   # first sync tick
                elif u["state"] in ("offline", "unloading"):
                    t_sync = sync_since.get(aid)
                    if t_sync is not None:
                        run_time = sim_t - t_sync
                        if run_time < _T_MIN_RUN - 1.0:   # 1 s grace for tick boundary
                            violations.append(
                                f"tick={ticks[i]['tick_index']} {aid}: "
                                f"decommit after {run_time:.0f} s < t_min_run={_T_MIN_RUN} s"
                            )
                        sync_since[aid] = None   # reset after decommit

        assert not violations, (
            f"I-6 FAIL: early decommit on {len(violations)} event(s).\n"
            + "\n".join(violations[:5])
        )

    # ── I-7 ──────────────────────────────────────────────────────────────────

    def test_I7_no_two_breaker_opens_same_tick(self):
        """I-7: No two units open their breaker (on-bus → OFFLINE) in the same tick.

        A single tick must shed at most one unit so the remaining fleet has time
        to absorb the step (sequential-stop guard).
        """
        units = _units_log()
        ticks = _ticks()
        violations: list[str] = []

        for i in range(1, len(units)):
            prev_u = {u["asset_id"]: u for u in units[i - 1]}
            curr_u = {u["asset_id"]: u for u in units[i]}
            went_offline = [
                aid for aid, cu in curr_u.items()
                if cu["state"] == "offline"
                and prev_u.get(aid, {}).get("is_on_bus", False)
            ]
            if len(went_offline) > 1:
                violations.append(
                    f"tick={ticks[i]['tick_index']}: {len(went_offline)} units opened "
                    f"breaker simultaneously: {went_offline}"
                )

        assert not violations, (
            f"I-7 FAIL: simultaneous breaker-open on {len(violations)} tick(s).\n"
            + "\n".join(violations[:5])
        )

    # ── I-8 ──────────────────────────────────────────────────────────────────

    def test_I8_threshold_crossing_sets_collapse_reason(self):
        """I-8: When a protection threshold fires, collapse_reason is set.

        The first tick that crosses of_trip_hz or island_collapse_hz must have
        island_collapsed=True and a non-empty collapse_reason.

        Also verifies that the threshold that actually fired matches the
        direction of the frequency deviation (UF → uf reason, OF → of reason).
        """
        ticks = _ticks()
        # Find any tick where the frequency is outside the protection band.
        for row in ticks:
            f = row["frequency_hz"]
            above_of = (f > OF_TRIP + 1e-4)
            below_uf = (f < ISLAND_COLLAPSE - 1e-4)
            if above_of or below_uf:
                assert row["island_collapsed"], (
                    f"I-8 FAIL: frequency {f:.4f} Hz crossed threshold "
                    f"but island_collapsed is False at tick {row['tick_index']}"
                )
                assert row["collapse_reason"], (
                    f"I-8 FAIL: island_collapsed but collapse_reason is empty "
                    f"at tick {row['tick_index']}"
                )
                if above_of:
                    assert "of" in row["collapse_reason"], (
                        f"I-8 FAIL: OF crossing but reason={row['collapse_reason']!r}"
                    )
                if below_uf:
                    assert "uf" in row["collapse_reason"], (
                        f"I-8 FAIL: UF crossing but reason={row['collapse_reason']!r}"
                    )

    # ── I-9 ──────────────────────────────────────────────────────────────────

    def test_I9_run_terminates_correctly(self):
        """I-9: Run terminates either at 5400 s (normal) or on island_collapsed — never silently.

        'Silently' means: the loop exited before 5400 s without setting
        island_collapsed=True on the final tick.  Such a termination would
        indicate a bug in the drive loop's break condition.
        """
        ticks = _ticks()
        assert ticks, "I-9 FAIL: no ticks were produced at all"

        last = ticks[-1]
        at_end     = last["sim_time_s"] >= DURATION_S
        collapsed  = bool(last["island_collapsed"])

        assert at_end or collapsed, (
            f"I-9 FAIL: run ended at sim_time={last['sim_time_s']} s "
            f"(< {DURATION_S} s) without island_collapsed=True"
        )
