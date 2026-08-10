"""
api/routes/scenarios.py — Scenario CRUD endpoints (Step 8).

POST   /scenarios            create a scenario
GET    /scenarios            list all scenarios (summary)
GET    /scenarios/{id}       full scenario detail + spec
PUT    /scenarios/{id}       update a scenario
DELETE /scenarios/{id}       delete a scenario

ScenarioStore is an in-memory dict aligned with the Step 2 Scenario ORM
entity (runtime/persistence.py Scenario class + spec_json column).
Step 9 replaces _data with SQLAlchemy session calls using the same entity.

§7.1.2 single-anchor invariant is validated by ScenarioSpec's model_validator,
so it fires on both create and update without any additional logic here.

D12 / PROTO-9 C-rate guard: out-of-range C-rates are returned as a warning
list field, never as a 400.  The bound is chosen without measured basis.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status

from api.schemas import (
    DqInjectEvent,
    KubeConfigSpec,
    LoadProfileConfigSpec,
    MaintenanceConfigSpec,
    ProcurementConfigSpec,
    RampRelaxationConfigSpec,
    CreateScenarioResponse,
    PmsConfigSpec,
    PreStagingConfigSpec,
    ScenarioDetailResponse,
    ScenarioSpec,
    ScenarioSummary,
    WorkloadEventSpec,
    BessUnitSpec,
    TurbineUnitSpec,
)

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

@dataclass
class ScenarioRecord:
    """In-memory mirror of the Scenario ORM entity + spec_json.

    Fields align with runtime/persistence.py Scenario so Step 9 can swap
    this dataclass for SQLAlchemy Session writes to the same table without
    changing the callers (api/routes/runs.py, api/app.py).

    spec_json holds a JSON-serialised ScenarioSpec (model_dump_json()).
    Callers deserialise with ScenarioSpec.model_validate_json(record.spec_json)
    for full validation, or json.loads(record.spec_json) for the runtime dict
    path in build_run_context_from_spec.
    """
    scenario_id: str
    name: str
    spec_json: str
    created_at: datetime
    last_run_id: Optional[str] = None


class ScenarioStore:
    """Process-lifetime in-memory scenario library.

    Created once in api/app.py lifespan and seeded with built-in demos.
    Attached to app.state.scenario_store and retrieved via _scenario_store()
    in each request handler.
    """

    def __init__(self) -> None:
        self._data: dict[str, ScenarioRecord] = {}

    # ── Write operations ──────────────────────────────────────────────────

    def create(self, spec: ScenarioSpec) -> ScenarioRecord:
        sid = str(uuid.uuid4())
        rec = ScenarioRecord(
            scenario_id=sid,
            name=spec.name,
            spec_json=spec.model_dump_json(),
            created_at=datetime.now(timezone.utc),
        )
        self._data[sid] = rec
        return rec

    def update(self, scenario_id: str, spec: ScenarioSpec) -> Optional[ScenarioRecord]:
        rec = self._data.get(scenario_id)
        if rec is None:
            return None
        rec.name = spec.name
        rec.spec_json = spec.model_dump_json()
        return rec

    def delete(self, scenario_id: str) -> bool:
        if scenario_id in self._data:
            del self._data[scenario_id]
            return True
        return False

    def link_run(self, scenario_id: str, run_id: str) -> None:
        """Record the most recent run_id for a scenario (informational)."""
        rec = self._data.get(scenario_id)
        if rec is not None:
            rec.last_run_id = run_id

    # ── Read operations ───────────────────────────────────────────────────

    def get(self, scenario_id: str) -> Optional[ScenarioRecord]:
        return self._data.get(scenario_id)

    def list_all(self) -> list[ScenarioRecord]:
        return list(self._data.values())

    # ── Seeding ───────────────────────────────────────────────────────────

    def _seed(self, scenario_id: str, spec: ScenarioSpec) -> None:
        """Insert a seeded scenario with a fixed, stable ID."""
        self._data[scenario_id] = ScenarioRecord(
            scenario_id=scenario_id,
            name=spec.name,
            spec_json=spec.model_dump_json(),
            created_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Seeded scenario helpers
# ---------------------------------------------------------------------------

_ENT_KW      = 10.2   # kW per node — enterprise_8gpu_air HardwareProfile
_PUE         = 1.03   # SiteConfig.pue_base default
# Demo job size: 600 nodes → ~6.3 MW (~30% of total site load).
# Reduced from 1900 nodes (19.96 MW) which was 11× the pre-step baseline and
# equal to the full N-1 figure — unfollowable by any generator and indistinguishable
# from no-forecast.  600 nodes keeps the step in the 20–40% range where
# pre-staging visibly converts lead time into covered capacity.
_DEMO_NODES  = 600


def _proto7_solar(nodes: int) -> float:
    """PROTO-7: solar rated at 25% of peak compute (PUE-adjusted).
    Chosen, no measured basis.  See scenario_factory.py for the rationale.
    """
    return 0.25 * nodes * _ENT_KW * _PUE / 1000.0


def _evt_start(
    job_id: str,
    node_count: int,
    t: float = 0.0,
    hw: str = "enterprise_8gpu_air",
) -> WorkloadEventSpec:
    return WorkloadEventSpec(
        event_id=f"evt-{job_id}-start",
        job_id=job_id,
        event_type="starting",
        timestamp=t,
        node_count=node_count,
        hardware_profile_id=hw,
    )


def _evt_solar_step(t: float, shortfall_mw: float) -> WorkloadEventSpec:
    """§7.1.1 renewable curtailment event (dt_lead=0 at runtime)."""
    return WorkloadEventSpec(
        event_id=f"evt-solar-step-{int(t)}s",
        job_id="",
        event_type="solar_step",
        timestamp=t,
        node_count=0,
        renewable_shortfall_mw=shortfall_mw,
    )


def _evt_unit_trip(t: float, asset_id: str) -> WorkloadEventSpec:
    """TC-84: turbine trip event — forces the named unit offline immediately.

    asset_id is carried in job_id (non-job event); node_count and
    hardware_profile_id are ignored by apply_workload_signal().
    """
    return WorkloadEventSpec(
        event_id=f"evt-unit-trip-{asset_id}-{int(t)}s",
        job_id=asset_id,          # carries the turbine asset_id to the runtime
        event_type="unit_trip",
        timestamp=t,
        node_count=0,
    )


def _bess(
    asset_id: str,
    rated_mw: float,
    usable_mwh: float,
    grid_forming: bool = False,
    p_anchor_reserve_mw: float = 1.0,
) -> BessUnitSpec:
    """Build a BessUnitSpec.

    p_anchor_reserve_mw: explicit anchor-reserve override (MW).  Default 1.0
    matches BessConfig.p_anchor_reserve_mw default (PROTO-9 / CHOSEN).
    San Diego demo site uses 2.0 MW (PW-3 / §15).
    """
    return BessUnitSpec(
        asset_id=asset_id,
        rated_mw=rated_mw,
        usable_mwh=usable_mwh,
        grid_forming=grid_forming,
        p_anchor_reserve_mw=p_anchor_reserve_mw,
    )


def _turbine(
    asset_id: str = "turbine-0",
    rated_mw: float = 10.0,
    r_mw_per_s: float = 0.2,
    run_hours_h: Optional[float] = None,
    hot_standby: bool = False,
    p_min_stable_frac: float = 0.40,
    t_min_run_s: float = 1800.0,
    min_run_enabled: bool = True,
    t_min_down_s: float = 900.0,
    min_down_enabled: bool = True,
) -> TurbineUnitSpec:
    """Build a TurbineUnitSpec.

    Phase E §7.1.3.6 / closeout Item 1: physical constraints with D-03 flags.
    p_min_stable_frac=0.40  — frame-class MSL floor (PW-1 / §15, CHOSEN).
    t_min_run_s=1800        — 30 min minimum run time before a stop (R5, CHOSEN).
    min_run_enabled=True    — R5 guard active for all seeded scenarios.
    t_min_down_s=900        — 15 min cooling window before a restart (R6, CHOSEN).
    min_down_enabled=True   — R6 guard active for all seeded scenarios.
    """
    return TurbineUnitSpec(
        asset_id=asset_id,
        rated_mw=rated_mw,
        r_asset_mw_per_s=r_mw_per_s,
        run_hours_h=run_hours_h,
        hot_standby=hot_standby,
        p_min_stable_frac=p_min_stable_frac,
        t_min_run_s=t_min_run_s,
        min_run_enabled=min_run_enabled,
        t_min_down_s=t_min_down_s,
        min_down_enabled=min_down_enabled,
    )


# ---------------------------------------------------------------------------
# Built-in scenario specs
# ---------------------------------------------------------------------------

# 1900-node peak compute (enterprise_8gpu_air, PUE 1.03) → 19.9614 MW.
# Kept for fleet / 3-turbine scenarios that are sized around a 20 MW load.
# PROTO-7 solar → 4.99035 MW.
_SOLAR_20MW = _proto7_solar(1900)    # 4.99035 MW  (fleet scenarios only)
_SOLAR_DEMO = _proto7_solar(_DEMO_NODES)  # 1.5759 MW  (demo scenarios, 600-node job)
_SOLAR_5MW  = _proto7_solar(476)     # 1.250214 MW
_SOLAR_BASE = _proto7_solar(1)       # 0.0026265 MW

# TC-33: 600 nodes × 10.2 kW × 1.03 PUE = 6.3036 MW (exact, no PROTO-7 fraction).
_TC33_MW = 600 * _ENT_KW * _PUE / 1000.0   # 6.3036 MW

# TC-33 compute dt_lead: required_ramp = 6.3036 / 0.2 = 31.518 s.
# dt_lead=15 s → gap = 16.518 s > 0 → alert fires.
_TC33_DT_LEAD = 15.0

_SEEDED: list[tuple[str, ScenarioSpec]] = [
    # ── AD2: PMS shortfall — TC-65 live conflict detection ───────────────
    (
        "demo-pms-shortfall",
        ScenarioSpec(
            name="demo-pms-shortfall",
            description=(
                "§28.4 PMS with undersized turbine so the curtailment ladder engages "
                "(AD2 / TC-65).  "
                "Turbine=5 MW, BESS=3 MW, demand≈15 MW → shortfall≈7 MW after ramp. "
                "CurtailmentTier order: GridSignal issues a_defer (2 MW) then "
                "b_power_cap (5 MW) to cover the gap (mandatory tier ordering §23.2). "
                "PMS shed_priority_order=['b_power_cap', 'a_defer'] — reversed. "
                "After curtailment dwell (§23.2 120 s), _curtailment_proposals is "
                "non-empty, triggering check_order_conflict() each tick. "
                "Conflict: PMS order [b,a] ≠ GridSignal order [a,b]. "
                "Per §28.4, PMS order is authoritative; GridSignal must not override "
                "it — the mismatch is a commissioning defect logged to pms_order_conflict."
            ),
            workload_events=[_evt_start("job-big", 1900)],
            dt_lead_seconds=30.0,
            # Undersized fleet: turbine 5 MW + BESS 3 MW < demand ~15 MW
            bess_units=[_bess("bess-0", rated_mw=3.0, usable_mwh=2.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=5.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
            pms_config=PmsConfigSpec(
                # PMS insists: a_defer FIRST, then b_power_cap (A→B tier-letter
                # order, i.e. smallest tier first).
                # GridSignal's select_candidates() sorts by impact DESC within
                # the same LadderPosition, so it naturally picks b_power_cap
                # (5 MW) before a_defer (2 MW).
                # PMS order [a, b] ≠ GS order [b, a] → conflict detected (TC-65).
                shed_priority_order=["a_defer", "b_power_cap"],
                transition_mode="open_transition",
                open_transition_gap_mw=2.0,
                open_transition_duration_s=5.0,
                fast_shed_duration_s=30.0,
            ),
            # AD2: set calibrated=True so TC-43 low-confidence interlock does NOT
            # reset the curtailment dwell.  Without this, site.uncalibrated=True
            # (default §17.3) causes TC-43 to reset the dwell every tick, and
            # curtailment proposals never fire — making check_order_conflict()
            # unreachable.  Calibrated state is a precondition for TC-65 to be
            # observable in a live run.
            calibrated=True,
        ),
    ),
    (
        "demo-pms",
        ScenarioSpec(
            name="demo-pms",
            description=(
                "demo-20mw + §28.4 PMS active (Step 11 / AB1).  "
                "PmsConfig defaults: fast_shed=30 s, open_transition mode, "
                "transition_gap=2.0 MW for 5 s, shed_priority_order=[].  "
                "The scenario activates SimulatedPMS; fast shed and open transition "
                "are injected externally via inject_fast_shed() / inject_transition() "
                "in the TC-68 egress audit script.  "
                "Separate from demo-20mw because PMS modifies p_dispatch_required_mw "
                "during the shed/transition windows, changing allocation numbers."
            ),
            workload_events=[_evt_start("job-big", _DEMO_NODES)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_DEMO,
            end_sim_time=300.0,
            pms_config=PmsConfigSpec(),   # all defaults: open_transition, fast_shed_duration_s=30
        ),
    ),
    (
        "demo-prestage",
        ScenarioSpec(
            name="demo-prestage",
            description=(
                "demo-20mw + §8.1 pre-staging (Step 10) — two-phase load-shifting model.  "
                "Charge phase (early ticks, gap ≤ 0): engine draws up to 1.0 MW of extra "
                "cooling load, lowering inlet temp and banking thermal energy (η=0.9).  "
                "Discharge phase (gap > 0): stored thermal energy offsets up to 1.0 MW "
                "of p_dispatch_required; shift tapers to 0 once thermal_soc is exhausted.  "
                "Energy shifted ≤ energy pre-cooled × η (observable energy balance).  "
                "BMS override (TC-56) blocks both phases; inlet band [18–24 °C] bounds "
                "the charge rate (TC-55).  "
                "Separate from demo-20mw because pre-staging changes dispatch numbers."
            ),
            workload_events=[_evt_start("job-big", _DEMO_NODES)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_DEMO,
            end_sim_time=300.0,
            pre_staging_config=PreStagingConfigSpec(),   # defaults: max_shift=1.0 MW, eta=0.9
        ),
    ),
    (
        "demo-20mw",
        ScenarioSpec(
            name="demo-20mw",
            description=(
                "600-node ~6.3 MW GPU ramp — 5 × 7 MW gas turbine fleet "
                "(4 synchronized online + 1 hot standby), single grid-forming BESS "
                "(18 MW / 8 MWh).  "
                "Job ramps over 120 s (process launch → NCCL init → first steps), "
                "giving the pre-staged turbines time to convert lead-time into MW. "
                "Staging distributes demand across the 4 active (non-standby) units: "
                "each stages to ≈ 1.58 MW.  "
                "Ramp credit per turbine = dt_lead × r = 30 s × 0.2 MW/s = 6.0 MW "
                ">> 1.58 MW → COVERED before and after the live trip. "
                "TC-84 live trip: turbine-1 trips at t=120 s → 3 online remain; "
                "each now stages to 2.10 MW, still well within 6.0 MW ramp credit "
                "→ COVERED.  Dashboard gen-trip indicator changes state on screen. "
                "BESS power test: 18 − 1 = 17 MW bridging ≥ any single-turbine "
                "deficit throughout the run. "
                "The hot-standby unit (turbine-4) contributes zero to dispatch "
                "and zero to r_surviving (§7.4 / TC-83)."
            ),
            workload_events=[
                _evt_start("job-big", _DEMO_NODES),
                # TC-84: trip turbine-1 at t=120 s — mid-run, after the GPU
                # ramp has completed (ramp_seconds=120 s) and all turbines are
                # at or near full output.  Removing one of the four online units
                # shrinks surviving capacity from 4 × ~6 MW to 3 × ~6 MW,
                # changing the contingency readout visible on the dashboard.
                _evt_unit_trip(t=120.0, asset_id="turbine-1"),
            ],
            dt_lead_seconds=30.0,
            # PW-3 / §15: San Diego anchor reserve = 2.0 MW (CHOSEN; PROTO-9
            # default is 1.0 MW — this is a deliberate site-level override for
            # the San Diego demo plant).  BessConfig default (1.0 MW) unchanged.
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0,
                               grid_forming=True, p_anchor_reserve_mw=2.0)],
            # PW-1 / §15: p_min_stable_frac = 0.40 on all demo plant turbines.
            # MSL = 0.40 × 7.0 = 2.8 MW per unit; Σ msl = 14.0 MW for 5 units
            # (4 online + 1 hot-standby).  Loading layer enforces the floor;
            # sub_msl_surplus_mw > 0 when P_fleet < 14.0 MW.  CHOSEN (PROTO-R4).
            turbine_units=[
                _turbine("turbine-0", rated_mw=7.0, r_mw_per_s=0.2, p_min_stable_frac=0.40),
                _turbine("turbine-1", rated_mw=7.0, r_mw_per_s=0.2, p_min_stable_frac=0.40),
                _turbine("turbine-2", rated_mw=7.0, r_mw_per_s=0.2, p_min_stable_frac=0.40),
                _turbine("turbine-3", rated_mw=7.0, r_mw_per_s=0.2, p_min_stable_frac=0.40),
                _turbine("turbine-4", rated_mw=7.0, r_mw_per_s=0.2, hot_standby=True,
                          p_min_stable_frac=0.40),
            ],
            solar_rated_mw=_SOLAR_DEMO,
            end_sim_time=300.0,
            # Enables compute vs allreduce phase variation on the COMPUTE RACKS
            # tile.  Uses all LoadProfileConfig defaults: phase_coherence=0.85,
            # f_compute=0.72, p_comm_ratio=0.55.  Step phase is self-managed by
            # GPUModule.advance() at a 0.70 s period (StepTimingConfig default).
            load_config=LoadProfileConfigSpec(),
            # A1 / Task #200: San Diego — SDG&E territory, 60 Hz (WECC).
            frequency_nominal_hz=60.0,
            # power_factor: CHOSEN — typical gas turbine (0.85).  Calibrate against
            # vendor nameplate for real deployments.  Raises S_base vs pf=1 by ~18%.
            power_factor=0.85,
            # Demo DQ inject: trip FORECAST QUALITY to ATTENTION at t=90 s so the
            # operator sees the tile change colour mid-run.  Clears at t=180 s.
            # During the window the confidence band widens (+15%) and autonomous
            # curtailment is blocked (TC-43).  The turbine-1 trip at t=120 s fires
            # inside this window — showing what happens when quality degrades mid-event.
            dq_inject_events=[
                DqInjectEvent(start_s=90.0, end_s=180.0, tag="invalid_payload"),
            ],
        ),
    ),
    (
        "demo-alert",
        ScenarioSpec(
            name="demo-alert",
            description="600-node ~6.3 MW scenario where BESS cannot bridge the "
                        "predicted peak — insufficient_reserve_alert fires at tick 1.  "
                        "Exercises the alert latch (F4) and basis label (F2).",
            workload_events=[_evt_start("job-alert", _DEMO_NODES)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=5.0, usable_mwh=2.5, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_DEMO,
            end_sim_time=300.0,
            load_config=LoadProfileConfigSpec(),
        ),
    ),
    (
        "demo-5mw",
        ScenarioSpec(
            name="demo-5mw",
            description="476-node 5 MW scenario — longer dt_lead (60 s).  "
                        "Turbine covers steadily; no alert expected.",
            workload_events=[_evt_start("job-small", 476)],
            dt_lead_seconds=60.0,
            bess_units=[_bess("bess-0", rated_mw=5.0, usable_mwh=2.0)],
            turbine_units=[_turbine("turbine-0", rated_mw=10.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_5MW,
            end_sim_time=300.0,
        ),
    ),
    (
        "demo-baseline",
        ScenarioSpec(
            name="demo-baseline",
            description="1-node idle baseline — minimal compute, full renewable offset.  "
                        "Validates zero-load path through evaluate_tick.",
            workload_events=[_evt_start("job-idle", 1)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=5.0, usable_mwh=2.0)],
            turbine_units=[_turbine("turbine-0", rated_mw=10.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_BASE,
            end_sim_time=300.0,
        ),
    ),
    (
        "demo-3turbine",
        ScenarioSpec(
            name="demo-3turbine",
            description=(
                "3 × 15 MW aeroderivative fleet — islanded primary generation. "
                "turbine-03 re-rated to 0.160 MW/s after 2,041 h (§27, TC-58). "
                "N−1 firm capacity 30.0 MW vs 23.95 MW peak (+25% margin). "
                "Aggregate ramp 0.600 MW/s covers a 23.95 MW step in 45 s. "
                "Demonstrates fleet view in the Gas Turbine Fleet modal."
            ),
            workload_events=[_evt_start("job-fleet3", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[
                _turbine("turbine-01", rated_mw=15.0, r_mw_per_s=0.2,  run_hours_h=1284.0),
                _turbine("turbine-02", rated_mw=15.0, r_mw_per_s=0.2,  run_hours_h=1197.0),
                _turbine("turbine-03", rated_mw=15.0, r_mw_per_s=0.16, run_hours_h=2041.0),
            ],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
        ),
    ),
    (
        "demo-fleet",
        ScenarioSpec(
            name="demo-fleet",
            description="Heterogeneous 2-BESS fleet — bess-0 (18 MW / 8 MWh, "
                        "grid-forming anchor) + bess-1 (5 MW / 2.5 MWh, follower).  "
                        "Exercises Step 3 proportional fleet allocation (78%/22% at "
                        "peak) and D13 min() endurance across units.  Both are visible "
                        "in AssetReservePanel's bridging readout.",
            workload_events=[_evt_start("job-fleet", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[
                _bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True),   # 2.25 C ✓
                _bess("bess-1", rated_mw=5.0,  usable_mwh=2.5, grid_forming=False),  # 2.0 C ✓
            ],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
        ),
    ),
    (
        "demo-tc33-compute",
        ScenarioSpec(
            name="demo-tc33-compute",
            description="TC-33 compute path — no workload at t=0; 600-node job "
                        "starts at t=30 s with dt_lead=15 s.  Staging fires via "
                        "STARTING event (gap ≈ 16.5 s > 0 → alert).  Compare with "
                        "demo-tc33-renewable: same delta_p, larger gap because "
                        "renewable has no advance warning.",
            workload_events=[
                # No event at t=0 — idle start.  Job STARTING at t=30 is the step.
                _evt_start("job-tc33c", 600, t=30.0),
            ],
            dt_lead_seconds=_TC33_DT_LEAD,  # 15 s: required_ramp=31.5 s → gap=16.5 s
            bess_units=[_bess("bess-0", rated_mw=5.0, usable_mwh=2.5)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=0.0,   # no solar — net_demand = full compute draw
            end_sim_time=120.0,
        ),
    ),
    (
        "demo-tc33-renewable",
        ScenarioSpec(
            name="demo-tc33-renewable",
            description="TC-33 renewable path — 600-node job from t=0 fully offset by "
                        f"{_TC33_MW:.4f} MW solar.  Irradiance drops to 0 at t=30 s; "
                        "SOLAR_STEP event triggers staging with dt_lead=0 (§7.1.1).  "
                        "Gap = 31.5 s (larger than compute case) → BESS bridges longer.  "
                        "This is the demo's most counterintuitive result: a renewable "
                        "curtailment is MORE dangerous than a compute ramp of equal "
                        "magnitude because there is no advance warning.",
            workload_events=[
                _evt_start("job-tc33r", 600, t=0.0),
                # SOLAR_STEP at t=30 triggers stage_for_predicted_step(dt_lead=0).
                _evt_solar_step(t=30.0, shortfall_mw=_TC33_MW),
            ],
            dt_lead_seconds=30.0,  # applies to GPU events only; SOLAR_STEP ignores it
            bess_units=[_bess("bess-0", rated_mw=5.0, usable_mwh=2.5)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_TC33_MW,  # exactly matches 600-node compute draw (A-fix)
            irradiance_steps=[(0.0, 1.0), (30.0, 0.0)],  # zero-order hold step
            end_sim_time=120.0,
        ),
    ),
    # ── Solar-peak demo — midday anchor for daytime solar variability ────
    (
        "demo-solar-peak",
        ScenarioSpec(
            name="demo-solar-peak",
            description=(
                "demo-20mw anchored at San Diego solar noon (UTC 20:00 = 12:00 PST). "
                "solar_origin_utc_hour=20 overrides real wall-clock UTC so the Mistral "
                "weather query and physics fallback both see midday regardless of when "
                "the demo runs.  Solar output varies 0.65–0.98 across the 300-second "
                "run, making marine-layer behaviour and Fleet-must-cover changes visible "
                "in the Solar PV modal.  Identical fleet to demo-20mw; only the solar "
                "origin time differs."
            ),
            workload_events=[_evt_start("job-big", _DEMO_NODES)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_DEMO,
            end_sim_time=300.0,
            solar_origin_utc_hour=20,   # UTC 20:00 = 12:00 PST San Diego solar noon
        ),
    ),
    # ── Kubernetes demand layer ───────────────────────────────────────────
    (
        "demo-kube",
        ScenarioSpec(
            name="demo-kube",
            description=(
                "Kubernetes gang-admission demand simulator (steps 1–2 of the "
                "Kube-to-turbine path).  An in-cluster informer watches Kueue / "
                "Volcano PodGroup objects; gang admission is the trigger.  Each "
                "admitted pod group maps to a WorkloadSignal (node_count from the "
                "spec, hardware_profile_id from node labels).  A 10-second reorder "
                "buffer honours the NTP ordering guarantee; event_ids are deduped.  "
                "Steps 3–8 (P_compute = Σ[nodes × kW] × PUE / 1000, thermal lag, "
                "BESS arbitration, turbine ramp) run unchanged in the core pipeline.  "
                "dt_lead=0 throughout: Kubernetes gives no advance notice to the grid "
                "— the scheduler decides, the microgrid finds out when current flows.  "
                "Power-cap holds new admissions when headroom < 2.5 MW; critical "
                "headroom evicts the largest running job.  rng_seed=42 for replay."
            ),
            workload_events=[],      # gang-admission simulator handles all signals
            dt_lead_seconds=0.0,     # no advance notice — dt_lead=0 per spec
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=600.0,      # 10 min — covers several admission / retirement cycles
            kube_config=KubeConfigSpec(
                hardware_profile_id="enterprise_8gpu_air",
                max_nodes=1900,
                min_nodes=200,
                mean_interarrival_s=60.0,    # ~1 gang admission per minute
                mean_job_nodes=200,
                job_node_std=80.0,
                min_job_nodes=50,
                mean_job_duration_s=300.0,   # 5-min mean job length
                min_job_duration_s=30.0,
                reorder_window_s=10.0,
                ntp_jitter_s=2.0,
                headroom_threshold_mw=2.5,
                rng_seed=42,
            ),
        ),
    ),
]


def _seed_fabric_scenarios(store: ScenarioStore) -> None:
    """Seed the eight fabric stress scenarios (S1–S8) into the store.

    Each scenario is backed by a JSON file in config/scenarios/.  The
    ScenarioSpec here is a minimal carrier (1 node, 1 turbine, 1 BESS) —
    just enough to pass the run-loop preconditions.  The actual fabric
    behaviour (jobs, stressors, capability_tier, assertions) is driven by
    the FabricEngine once it sees the fabric_scenario_id field.

    Descriptive names and durations come from the scenario JSON headers.
    """
    import json as _json
    from pathlib import Path as _Path

    # Map from stable store key → (display_name, end_sim_time, fabric_scenario_id,
    #                               capability_tier).
    # capability_tier is "degraded" for S6 only.
    FABRIC_ENTRIES: list[tuple[str, str, float, str, str]] = [
        ("fabric-s1", "S1: Baseline Training",         60.0,  "S1_baseline_training",          "current"),
        ("fabric-s2", "S2: Checkpoint ECMP Hotspot",   80.0,  "S2_checkpoint_hotspot",         "current"),
        ("fabric-s3", "S3: Job-End Withholds",         60.0,  "S3_job_end_withholds",          "current"),
        ("fabric-s4", "S4: NFR-2 Control-Path Breach", 20.0,  "S4_control_path_nfr2_breach",   "current"),
        ("fabric-s5", "S5: Gray Failure",              30.0,  "S5_gray_failure",               "current"),
        ("fabric-s6", "S6: Baseline Tier Degradation", 30.0,  "S6_baseline_tier_degradation",  "degraded"),
        ("fabric-s7", "S7: Slow Checkpoint",          100.0,  "S7_slow_checkpoint",            "current"),
        ("fabric-s8", "S8: Transceiver Degradation",   30.0,  "S8_transceiver_degrade",        "current"),
    ]

    _cfg_dir = _Path("config/scenarios")

    for store_id, display_name, duration, fab_id, _cap_tier in FABRIC_ENTRIES:
        # Load the fabric scenario JSON to extract the description.
        _desc = ""
        _jpath = _cfg_dir / f"{fab_id}.json"
        try:
            _raw = _json.loads(_jpath.read_text())
            # Use the first assertion description as a summary when available.
            if _raw.get("assertions"):
                _descs = [a.get("description", "") for a in _raw["assertions"]]
                _desc = "; ".join(d for d in _descs if d)
        except Exception:
            pass  # missing file handled gracefully; run will get 503 later

        _spec = ScenarioSpec(
            name=display_name,
            description=_desc,
            workload_events=[_evt_start("job-fabric", 1)],   # minimal 1-node job
            dt_lead_seconds=0.0,
            bess_units=[_bess("bess-0", rated_mw=5.0, usable_mwh=2.5, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=10.0, r_mw_per_s=0.2)],
            solar_rated_mw=0.0,
            # Run duration matches the fabric scenario; minimum is the fabric duration.
            # We pad to at least 60 s so the run clock has enough room.
            end_sim_time=max(duration, 60.0),
            fabric_scenario_id=fab_id,
        )
        store._seed(store_id, _spec)


def _seed_json_scenarios(store: ScenarioStore) -> None:
    """Seed scenarios stored as full ScenarioSpec JSON files in config/scenarios/.

    Each entry maps a stable store key to a filename under config/scenarios/.
    The JSON must be a valid ScenarioSpec (model_dump_json output).
    """
    import json as _json
    from pathlib import Path as _Path

    _JSON_ENTRIES: list[tuple[str, str]] = [
        # (store_id, filename)
        ("demo-islanded-ramp", "demo-islanded-ramp.json"),
    ]

    _cfg_dir = _Path("config/scenarios")
    for store_id, filename in _JSON_ENTRIES:
        _jpath = _cfg_dir / filename
        try:
            _raw = _jpath.read_text()
            _spec = ScenarioSpec.model_validate_json(_raw)
            store._seed(store_id, _spec)
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Failed to seed %s from %s: %s", store_id, filename, exc
            )


def build_seeded_store() -> ScenarioStore:
    """Return a ScenarioStore pre-loaded with all built-in demo scenarios."""
    store = ScenarioStore()
    for sid, spec in _SEEDED:
        store._seed(sid, spec)
    _seed_fabric_scenarios(store)
    _seed_json_scenarios(store)
    return store


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def _scenario_store(request: Request) -> ScenarioStore:
    return request.app.state.scenario_store


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateScenarioResponse,
    summary="Create a new scenario",
)
async def create_scenario(
    body: ScenarioSpec,
    request: Request,
) -> CreateScenarioResponse:
    """Persist a new scenario spec and return its ID.

    C-rate warnings are returned as a list field, never as 400.  Out-of-range
    C-rate values may represent real systems outside PROTO-9's chosen bounds.
    """
    store = _scenario_store(request)
    warnings = body.collect_c_rate_warnings()
    rec = store.create(body)
    return CreateScenarioResponse(
        scenario_id=rec.scenario_id,
        name=rec.name,
        c_rate_warnings=warnings,
    )


@router.get(
    "",
    response_model=list[ScenarioSummary],
    summary="List all scenarios",
)
async def list_scenarios(request: Request) -> list[ScenarioSummary]:
    """Return a summary list of all stored scenarios (seeded + user-created)."""
    store = _scenario_store(request)
    return [
        ScenarioSummary(
            scenario_id=rec.scenario_id,
            name=rec.name,
            description=json.loads(rec.spec_json).get("description", ""),
            created_at=rec.created_at.isoformat(),
        )
        for rec in store.list_all()
    ]


@router.get(
    "/{scenario_id}",
    response_model=ScenarioDetailResponse,
    summary="Get scenario detail",
    responses={404: {"description": "Scenario not found"}},
)
async def get_scenario(
    scenario_id: str,
    request: Request,
) -> ScenarioDetailResponse:
    store = _scenario_store(request)
    rec = store.get(scenario_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id!r} not found",
        )
    spec = ScenarioSpec.model_validate_json(rec.spec_json)
    return ScenarioDetailResponse(
        scenario_id=rec.scenario_id,
        name=rec.name,
        description=spec.description,
        created_at=rec.created_at.isoformat(),
        spec=spec,
        c_rate_warnings=spec.collect_c_rate_warnings(),
    )


@router.get(
    "/{scenario_id}/download",
    summary="Download scenario spec as a JSON file",
    responses={404: {"description": "Scenario not found"}},
)
async def download_scenario(
    scenario_id: str,
    request: Request,
) -> Response:
    store = _scenario_store(request)
    rec = store.get(scenario_id)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id!r} not found",
        )
    spec = ScenarioSpec.model_validate_json(rec.spec_json)
    filename = f"{scenario_id.replace('/', '_')}.json"
    return Response(
        content=spec.model_dump_json(indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put(
    "/{scenario_id}",
    response_model=CreateScenarioResponse,
    summary="Update a scenario",
    responses={404: {"description": "Scenario not found"}},
)
async def update_scenario(
    scenario_id: str,
    body: ScenarioSpec,
    request: Request,
) -> CreateScenarioResponse:
    store = _scenario_store(request)
    rec = store.update(scenario_id, body)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id!r} not found",
        )
    return CreateScenarioResponse(
        scenario_id=rec.scenario_id,
        name=rec.name,
        c_rate_warnings=body.collect_c_rate_warnings(),
    )


@router.delete(
    "/{scenario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scenario",
    responses={404: {"description": "Scenario not found"}},
)
async def delete_scenario(
    scenario_id: str,
    request: Request,
) -> None:
    store = _scenario_store(request)
    if not store.delete(scenario_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_id!r} not found",
        )
