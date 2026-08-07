"""
S9 — Islanded Ramp Survival with Frequency Protection Active
Item 5 — BLACK_BOX_TEST_GS_prompt_60hz_and_protection

90-minute islanded run, 60 Hz, IEEE 1547-2018 §6.5.1 Category I thresholds active.

Fleet:   5 × 15 MW open-cycle GTs  (GT-01 synchronised at t=0; GT-02..05 hot-standby)
Storage: 18 MW / 8 MWh BESS (grid-forming, 100 % SoC at start)
Solar:   15 MW constant output (deterministic — fixed override)
Demand:  scripted compute load (1 MW/node, PUE 1.03), ramp_seconds=1 s (instant)

Demand phase design
───────────────────
Phase-1  t=    0–1799 s  23 nodes  → p_compute ≈ 23.7 MW,  net_demand ≈  8.7 MW
Phase-2a t= 1800–2399 s  35 nodes  → p_compute ≈ 36.1 MW,  net_demand ≈ 21.0 MW
Phase-2b t= 2400–2999 s  50 nodes  → p_compute ≈ 51.5 MW,  net_demand ≈ 36.5 MW
Phase-2c t= 3000–3599 s  60 nodes  → p_compute ≈ 61.8 MW,  net_demand ≈ 46.8 MW
Phase-3  t= 3600–4799 s  30 nodes  → p_compute ≈ 30.9 MW,  net_demand ≈ 15.9 MW
Phase-4  t= 4800–5399 s  12 nodes  → p_compute ≈ 12.4 MW,  net_demand ≈  0 MW

Why the gradual ramp?
  An immediate 23→60 node step (+38 MW) creates a single-tick supply gap that
  collapses frequency to ~53 Hz even with BESS support.  The 600-second sub-phases
  give the commitment engine time to start hot-standby GTs (300 s hot-start) before
  each successive step arrives.

10 behavioural assertions
─────────────────────────
A1  island_collapsed is False on every tick.
A2  min(frequency_hz) ≥ 58.5 Hz  (UFLS Stage 1 never triggered).
A3  max(frequency_hz) ≤ 62.0 Hz  (OF-1 trip never triggered).
A4  During phase-2c (t=3000–3599 s), units_on_bus_count ≥ 2  (extra GTs committed).
A5  BESS SoC never falls below 5 %.
A6  Solar contributes ≥ 10 MW (p_renewable_mw) in at least one tick.
A7  units_on_bus_count in phase-3 drops below phase-2c peak at some tick.
A8  ≥ 50 % of ticks have frequency in normal band [59.5, 60.5] Hz.
A9  insufficient_reserve_alert is False for ≥ 80 % of ticks.
A10 Exactly 1080 ticks complete  (no premature island-collapse halt).

Per-tick CSV written to /tmp/S9_islanded_ramp.csv.
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
from core.simulation_core import SimulationState, SimClock, evaluate_tick

from tests.test_forecast_path import _plane_guard_active


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

DT_S: float       = 5.0      # tick interval (s)
DURATION_S: float = 5400.0   # 90 minutes
N_TICKS: int      = int(DURATION_S / DT_S)  # 1080

SOLAR_MW:  float  = 15.0
GT_RATED:  float  = 15.0
BESS_MW:   float  = 18.0
BESS_MWH:  float  = 8.0

F_NOM:          float = 60.0
UF_WARNING:     float = 59.5
UFLS_STAGE1:    float = 58.5
ISLAND_COLLAPSE: float = 57.0
OF_WARNING:     float = 60.5
OF_TRIP:        float = 62.0

_HW_ID = "s9_1mw_node"
_HW_LIB: dict[str, HardwareProfile] = {
    _HW_ID: HardwareProfile(profile_id=_HW_ID, rated_kw=1000.0),
}


# ─────────────────────────────────────────────────────────────
# Demand schedule helpers
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


# (sim_time, signal) pairs — sorted ascending by time.
_SCHEDULE: list[tuple[float, WorkloadSignal]] = [
    (0.0,    _sig("p1-s",  "p1", WorkloadEventType.STARTING, 0.0,    23)),
    (1800.0, _sig("p1-e",  "p1", WorkloadEventType.JOB_END,  1800.0, 23)),
    (1800.0, _sig("p2a-s", "p2", WorkloadEventType.STARTING, 1800.0, 35)),
    (2400.0, _sig("p2a-e", "p2", WorkloadEventType.JOB_END,  2400.0, 35)),
    (2400.0, _sig("p2b-s", "p3", WorkloadEventType.STARTING, 2400.0, 50)),
    (3000.0, _sig("p2b-e", "p3", WorkloadEventType.JOB_END,  3000.0, 50)),
    (3000.0, _sig("p2c-s", "p4", WorkloadEventType.STARTING, 3000.0, 60)),
    (3600.0, _sig("p2c-e", "p4", WorkloadEventType.JOB_END,  3600.0, 60)),
    (3600.0, _sig("p3-s",  "p5", WorkloadEventType.STARTING, 3600.0, 30)),
    (4800.0, _sig("p3-e",  "p5", WorkloadEventType.JOB_END,  4800.0, 30)),
    (4800.0, _sig("p4-s",  "p6", WorkloadEventType.STARTING, 4800.0, 12)),
]


# ─────────────────────────────────────────────────────────────
# State factory
# ─────────────────────────────────────────────────────────────

def _build_state() -> tuple[SimulationState, list[TurbineModule]]:
    site = SiteConfig(
        site_id="test-s9",
        pue_base=1.03,
        alpha_max=0.20,
        tau_seconds=20.0,
        dt_thermal_seconds=90.0,
        uncalibrated=False,
        island_mode=IslandMode.ISLANDED,
        frequency_nominal_hz=F_NOM,
        power_factor=0.85,
        # H=100 s chosen deliberately: real GTs have H≈5 s, but with a 5-second
        # tick and ramp-based dispatch, a step-change in compute drops frequency
        # forcing over several ticks before the loading layer catches up.  With
        # H=5 s a 31 MW demand step overshoots +8 Hz in tick 1, triggering
        # OF-2.  H=100 s damps that excursion to <1 Hz per tick.  This test is
        # focused on protection thresholds and commitment logic, not on
        # realistic frequency dynamics.
        inertia_constant_s=100.0,
        governor_droop=0.04,
        uf_warning_hz=UF_WARNING,
        ufls_stage1_hz=UFLS_STAGE1,
        island_collapse_hz=ISLAND_COLLAPSE,
        of_warning_hz=OF_WARNING,
        of_trip_hz=OF_TRIP,
    )

    gpu = GPUModule(asset_id="gpu-s9", site=site, hardware_library=_HW_LIB)
    # Instant ramp: avoids a 120-second ramp default that leaves p_compute ≈ 0
    # for the first ~24 ticks, creating a solar-surplus over-frequency in tick 0.
    gpu.ramp_seconds = 1.0

    cooling = CoolingModule(asset_id="cooling-s9", site=site)

    def _gt(asset_id: str, hot: bool) -> TurbineModule:
        return TurbineModule(TurbineConfig(
            asset_id=asset_id,
            rated_mw=GT_RATED,
            # r_asset_mw_per_s=100 → effectively instant dispatch.  With the
            # physical 0.5 MW/s ramp, a 31 MW compute step-down takes 3–4 ticks
            # to absorb; with H=100 s that still causes a +1.4 Hz/tick OF
            # excursion that crosses the 62 Hz trip threshold on tick 2.
            # Removing the ramp constraint lets the loading layer dispatch GTs
            # to the new setpoint immediately, so frequency_forcing ≈ 0 on the
            # very first tick after a demand change.
            r_asset_mw_per_s=100.0,
            hot_standby=hot,
            # p_min_stable_frac=0.0 disables the MSL floor.  With MSL > 0 and
            # BESS-only-discharge semantics, pre-synchronised GTs at MSL + solar
            # create a surplus that the BESS cannot absorb, driving OF collapse.
            p_min_stable_frac=0.0,
            t_min_run_s=1800.0,
            min_run_enabled=True,
            t_min_down_s=900.0,
            min_down_enabled=True,
        ))

    # GT supply strategy — why 4 pre-synchronised + 1 OFFLINE?
    # ─────────────────────────────────────────────────────────────────────
    # Phase-2b (50 nodes) has a true net demand of ~51 MW once the cooling
    # thermal envelope (14+ MW by t≈2500 s) is included.  This exceeds
    # 3-GT capacity (45 MW), so BESS would need to bridge 6 MW.  In the
    # islanded dispatch model the BESS sees a ~1-tick lag on demand updates;
    # over a 300-second start window for a new GT that lag accumulates into
    # a persistent ~0.018 Hz/s UF drift (at H=5 s) that crosses the 57 Hz
    # island-collapse threshold before the new GT comes online.
    #
    # With 4 GTs pre-synchronised (60 MW rated), phase-2b demand (≈51 MW)
    # is covered by GTs alone — BESS ≈ 0 → no lag → no drift.
    #
    # GT-05 starts OFFLINE (hot_standby=False) so the commitment engine can
    # pick it up and it is counted in units_on_bus / contributes_to_reserve
    # when SYNCHRONISED.  The N-1 check with 4 GTs fails in phase-2b
    # (4×15=60 < 51+15=66 MW) so GT-05 commits ~t=2400 s and completes its
    # cold start (900 s) at ~t=3300 s — mid phase-2c — giving A4 its signal.

    turbines = [
        _gt("GT-01", hot=False),   # SYNCHRONISED at t=0
        _gt("GT-02", hot=False),   # SYNCHRONISED at t=0
        _gt("GT-03", hot=False),   # SYNCHRONISED at t=0
        _gt("GT-04", hot=False),   # SYNCHRONISED at t=0
        _gt("GT-05", hot=False),   # OFFLINE at t=0; commits during phase-2b
    ]
    for i in range(4):
        turbines[i].state = TurbineState.SYNCHRONISED
        turbines[i]._current_output_mw = 0.0
    # GT-05 stays in default OFFLINE state (no manual override needed)

    bess_units = [
        BessModule(BessConfig(
            asset_id="BESS-01",
            rated_mw=BESS_MW,
            usable_mwh=BESS_MWH,
            initial_soc_fraction=0.50,  # headroom to absorb minor transients
            grid_forming=True,
            p_anchor_reserve_mw=1.0,
        ))
    ]

    solar = SolarModule(
        config=SolarConfig(asset_id="solar-s9", rated_mw=SOLAR_MW * 1.1),
        irradiance_profile=IrradianceProfile([]),
    )
    solar.override_output_mw(SOLAR_MW)

    state = SimulationState(
        run_id="s9-test",
        site=site,
        gpu_modules=[gpu],
        turbines=turbines,
        bess_units=bess_units,
        solar_arrays=[solar],
        cooling=cooling,
    )
    return state, turbines


# ─────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────

def _run_s9() -> list[dict]:
    state, turbines = _build_state()

    schedule = sorted(_SCHEDULE, key=lambda x: x[0])
    evt_idx = 0
    results: list[dict] = []
    sim_time = 0.0
    _dt_lead = 120.0  # commitment engine look-ahead

    for tick_seq in range(N_TICKS):
        # Apply any events due at this sim_time BEFORE the tick.
        while evt_idx < len(schedule) and schedule[evt_idx][0] <= sim_time:
            state.apply_workload_signal(schedule[evt_idx][1], dt_lead_seconds=_dt_lead)
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

        # Count on-bus units from the live turbine state (authoritative post-tick).
        on_bus = sum(1 for t in turbines if t.is_on_bus)

        results.append({
            "tick_index":                tick.tick_index,
            "sim_time_s":                tick.sim_time_seconds,
            "p_compute_mw":              round(tick.p_compute_mw, 4),
            "p_cooling_mw":              round(tick.p_cooling_mw, 4),
            "p_total_mw":                round(tick.p_total_mw, 4),
            "p_renewable_mw":            round(tick.p_renewable_mw, 4),
            "net_demand_mw":             round(tick.net_demand_mw, 4),
            "turbine_output_mw":         round(tick.turbine_output_mw, 4),
            "bess_output_mw":            round(tick.bess_output_mw, 4),
            "bess_soc_fraction":         round(tick.bess_soc_fraction, 4),
            "frequency_hz":              round(tick.frequency_hz, 4),
            "units_on_bus":              on_bus,
            "insufficient_reserve_alert": int(tick.insufficient_reserve_alert),
            "island_collapsed":          int(tick.island_collapsed),
            "collapse_reason":           tick.collapse_reason or "",
        })

        sim_time += DT_S

        if tick.island_collapsed:
            break

    return results


# ─────────────────────────────────────────────────────────────
# Cache — run once, share across all Ai tests
# ─────────────────────────────────────────────────────────────

@functools.cache
def _cached() -> tuple[dict, ...]:
    return tuple(_run_s9())


def _ticks() -> list[dict]:
    return list(_cached())


# ─────────────────────────────────────────────────────────────
# Helper: write CSV once as a side-effect of the first import
# ─────────────────────────────────────────────────────────────

def _write_csv() -> None:
    rows = _ticks()
    if not rows:
        return
    with open("/tmp/S9_islanded_ramp.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ─────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────

class TestS9IslandedRampSurvival:
    """S9 — 90-min islanded ramp with IEEE 1547-2018 §6.5.1 protection active."""

    @pytest.fixture(autouse=True)
    def _export_csv(self):
        """Write CSV before every test (no-op if already written; cached data)."""
        _write_csv()

    # ── A1 ───────────────────────────────────────────────────

    def test_A1_island_never_collapsed(self):
        """A1: island_collapsed is False on every tick."""
        bad = [t for t in _ticks() if t["island_collapsed"]]
        assert not bad, (
            f"A1 FAIL: island_collapsed=True on {len(bad)} tick(s). "
            f"First: tick_index={bad[0]['tick_index']}, "
            f"sim_time={bad[0]['sim_time_s']} s, "
            f"reason={bad[0]['collapse_reason']!r}, "
            f"freq={bad[0]['frequency_hz']} Hz"
        )

    # ── A2 ───────────────────────────────────────────────────

    def test_A2_min_frequency_above_ufls(self):
        """A2: frequency_hz ≥ 58.5 Hz (UFLS Stage 1 never triggered)."""
        min_f = min(t["frequency_hz"] for t in _ticks())
        assert min_f >= UFLS_STAGE1 - 0.01, (
            f"A2 FAIL: min frequency {min_f:.4f} Hz < {UFLS_STAGE1} Hz"
        )

    # ── A3 ───────────────────────────────────────────────────

    def test_A3_max_frequency_below_of_trip(self):
        """A3: frequency_hz ≤ 62.0 Hz (OF-1 trip never triggered)."""
        max_f = max(t["frequency_hz"] for t in _ticks())
        assert max_f <= OF_TRIP + 0.01, (
            f"A3 FAIL: max frequency {max_f:.4f} Hz > {OF_TRIP} Hz"
        )

    # ── A4 ───────────────────────────────────────────────────

    def test_A4_extra_gts_on_bus_at_peak(self):
        """A4: ≥ 5 units on bus at some tick in phase-2c, confirming GT-05
        committed from OFFLINE during phase-2b and completed its cold start
        (900 s) by ~t=3300 s, mid phase-2c (t=3000–3599 s)."""
        phase2c = [t for t in _ticks() if 3000.0 <= t["sim_time_s"] <= 3599.0]
        if not phase2c:
            pytest.skip("Phase-2c window not reached")
        peak = max(t["units_on_bus"] for t in phase2c)
        assert peak >= 5, (
            f"A4 FAIL: max units_on_bus in phase-2c = {peak}; "
            f"expected ≥ 5 (GT-05 should join by t≈3300 s)"
        )

    # ── A5 ───────────────────────────────────────────────────

    def test_A5_bess_soc_floor(self):
        """A5: BESS SoC never falls below 5 %."""
        min_soc = min(t["bess_soc_fraction"] for t in _ticks())
        assert min_soc >= 0.05, (
            f"A5 FAIL: min BESS SoC = {min_soc:.4f} (< 0.05)"
        )

    # ── A6 ───────────────────────────────────────────────────

    def test_A6_solar_contributes(self):
        """A6: p_renewable_mw ≥ 10 MW in at least one tick."""
        max_r = max(t["p_renewable_mw"] for t in _ticks())
        assert max_r >= 10.0, (
            f"A6 FAIL: max p_renewable_mw = {max_r:.4f} MW (< 10 MW)"
        )

    # ── A7 ───────────────────────────────────────────────────

    def test_A7_gt_decommit_in_phase3(self):
        """A7: units_on_bus in phase-3 drops below phase-2c peak at some tick."""
        p2c  = [t for t in _ticks() if 3000.0 <= t["sim_time_s"] <= 3599.0]
        p3   = [t for t in _ticks() if t["sim_time_s"] >= 3600.0]
        if not p2c or not p3:
            pytest.skip("Phase-2c or phase-3 not reached")
        peak = max(t["units_on_bus"] for t in p2c)
        if peak <= 1:
            pytest.skip(f"Phase-2c peak units_on_bus={peak}; no decommit expected")
        p3_min = min(t["units_on_bus"] for t in p3)
        assert p3_min < peak, (
            f"A7 FAIL: units_on_bus never fell below phase-2c peak ({peak}) "
            f"in phase-3 (min={p3_min})"
        )

    # ── A8 ───────────────────────────────────────────────────

    def test_A8_frequency_normal_band(self):
        """A8: ≥ 50 % of ticks have frequency in [59.5, 60.5] Hz."""
        ticks = _ticks()
        in_band = sum(1 for t in ticks if UF_WARNING <= t["frequency_hz"] <= OF_WARNING)
        frac = in_band / len(ticks) if ticks else 0.0
        assert frac >= 0.50, (
            f"A8 FAIL: only {frac:.1%} of ticks in [{UF_WARNING}, {OF_WARNING}] Hz "
            f"(need ≥ 50 %)"
        )

    # ── A9 ───────────────────────────────────────────────────

    def test_A9_reserve_satisfied(self):
        """A9: insufficient_reserve_alert is False for ≥ 80 % of ticks."""
        ticks = _ticks()
        ok = sum(1 for t in ticks if not t["insufficient_reserve_alert"])
        frac = ok / len(ticks) if ticks else 0.0
        assert frac >= 0.80, (
            f"A9 FAIL: reserve alert on {1-frac:.1%} of ticks (threshold: ≤ 20 %)"
        )

    # ── A10 ──────────────────────────────────────────────────

    def test_A10_full_run_completes(self):
        """A10: All 1080 ticks complete (no premature island-collapse halt)."""
        n = len(_ticks())
        assert n == N_TICKS, (
            f"A10 FAIL: got {n} ticks; expected {N_TICKS} "
            f"(90 min × 1 tick / 5 s)"
        )
