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

from fastapi import APIRouter, HTTPException, Request, status

from api.schemas import (
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

_ENT_KW   = 10.2   # kW per node — enterprise_8gpu_air HardwareProfile
_PUE      = 1.03   # SiteConfig.pue_base default


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


def _bess(
    asset_id: str,
    rated_mw: float,
    usable_mwh: float,
    grid_forming: bool = False,
) -> BessUnitSpec:
    return BessUnitSpec(
        asset_id=asset_id,
        rated_mw=rated_mw,
        usable_mwh=usable_mwh,
        grid_forming=grid_forming,
    )


def _turbine(
    asset_id: str = "turbine-0",
    rated_mw: float = 10.0,
    r_mw_per_s: float = 0.2,
) -> TurbineUnitSpec:
    return TurbineUnitSpec(
        asset_id=asset_id,
        rated_mw=rated_mw,
        r_asset_mw_per_s=r_mw_per_s,
    )


# ---------------------------------------------------------------------------
# Built-in scenario specs
# ---------------------------------------------------------------------------

# 1900-node peak compute (enterprise_8gpu_air, PUE 1.03) → 19.9614 MW.
# PROTO-7 solar → 4.99035 MW.
_SOLAR_20MW = _proto7_solar(1900)    # 4.99035 MW
_SOLAR_5MW  = _proto7_solar(476)     # 1.250214 MW
_SOLAR_BASE = _proto7_solar(1)       # 0.0026265 MW

# TC-33: 600 nodes × 10.2 kW × 1.03 PUE = 6.3036 MW (exact, no PROTO-7 fraction).
_TC33_MW = 600 * _ENT_KW * _PUE / 1000.0   # 6.3036 MW

# TC-33 compute dt_lead: required_ramp = 6.3036 / 0.2 = 31.518 s.
# dt_lead=15 s → gap = 16.518 s > 0 → alert fires.
_TC33_DT_LEAD = 15.0

_SEEDED: list[tuple[str, ScenarioSpec]] = [
    # ── AD1: procurement (TC-47, TC-52) ─────────────────────────────────
    (
        "demo-procurement",
        ScenarioSpec(
            name="demo-procurement",
            description=(
                "demo-20mw + §24 ProcurementLayer active (AD1).  "
                "ProcurementLayer calls NonFirmImportEffect.apply() (TC-47: reserve gap "
                "unchanged despite non-firm import) and creates ReservationProposal "
                "(TC-52: requires_confirmation always True) each tick.  "
                "non_firm_available_mw=3.0 MW; firm=20.0 MW; reserved=10.0 MW.  "
                "Observe-only: no effect on dispatch trace."
            ),
            workload_events=[_evt_start("job-big", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
            procurement_config=ProcurementConfigSpec(
                firm_available_mw=20.0,
                reserved_available_mw=10.0,
                non_firm_available_mw=3.0,
                price_curve_seed=7,
            ),
        ),
    ),
    # ── AD1: maintenance (TC-58, TC-59, TC-60) ──────────────────────────
    (
        "demo-maintenance",
        ScenarioSpec(
            name="demo-maintenance",
            description=(
                "demo-20mw + §27 MaintenanceLayer active (AD1).  "
                "Asset starts DEGRADED (effective_ramp=0.15 < nameplate=0.20 MW/s). "
                "Each tick: reserve_contribution_mw_per_s() returns effective rate (TC-58). "
                "At sim_time≥30 s: validate_window() checks synthetic window [60,120) "
                "across full forecast duration (TC-59). "
                "After 20 favorable ticks: propose_rating_change() returns RAISE with "
                "requires_confirmation=True (TC-60). "
                "Observe-only: no effect on dispatch trace."
            ),
            workload_events=[_evt_start("job-big", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
            maintenance_config=MaintenanceConfigSpec(
                asset_id="turbine-0",
                nameplate_ramp_mw_per_s=0.2,
                effective_ramp_mw_per_s=0.15,   # DEGRADED — below nameplate
                reserve_threshold_mw=1.0,
            ),
        ),
    ),
    # ── AD1: ramp relaxation (TC-75, TC-76) ─────────────────────────────
    (
        "demo-ramp-relax",
        ScenarioSpec(
            name="demo-ramp-relax",
            description=(
                "demo-20mw + §23.7.2 RampRelaxationEngine active (AD1).  "
                "evaluate() called each tick with ReservePosition built from "
                "turbine_rated_mw=25 MW and forecast_upper_bound = demand × 1.10. "
                "headroom_at_upper_bound check (TC-75) fires every tick; "
                "gridSignal_connected=True so adaptive_active reflects reserve headroom. "
                "TC-76 (gridSignal_connected=False → baseline) is exercised by the unit "
                "test; this scenario exercises the evaluate() code path live. "
                "Observe-only: returned SiteRampPolicy is advisory only."
            ),
            workload_events=[_evt_start("job-big", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
            ramp_relaxation_config=RampRelaxationConfigSpec(
                reserve_threshold_mw=2.0,
                baseline_ramp_cap_mw=5.0,
                baseline_ramp_duration_s=75.0,
                adaptive_ramp_duration_s=30.0,
            ),
        ),
    ),
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
            workload_events=[_evt_start("job-big", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
            pms_config=PmsConfigSpec(),   # all defaults: open_transition, fast_shed_duration_s=30
        ),
    ),
    (
        "demo-prestage",
        ScenarioSpec(
            name="demo-prestage",
            description=(
                "demo-20mw + §8.1 pre-staging (Step 10).  "
                "PreStagingConfig defaults: max_shift=1.0 MW, initial_temp=21.0 °C, "
                "band [18–24 °C], gain=0.05 °C/MW/s, warmup=0.002 °C/s.  "
                "Pre-staging fires from tick 1; temperature headroom exhausts at "
                "≈t=62 s (12–13 ticks); engine then idles until warmup recovers.  "
                "Separate from demo-20mw because pre-staging shifts p_dispatch_required "
                "and changes turbine/BESS allocation numbers."
            ),
            workload_events=[_evt_start("job-big", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
            pre_staging_config=PreStagingConfigSpec(),   # all defaults
        ),
    ),
    (
        "demo-20mw",
        ScenarioSpec(
            name="demo-20mw",
            description="1900-node 20 MW GPU ramp — single BESS (grid-forming), "
                        "large turbine.  Turbine covers full load; BESS provides "
                        "bridging only during the ramp.  alerts_seen=False.",
            workload_events=[_evt_start("job-big", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=18.0, usable_mwh=8.0, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
        ),
    ),
    (
        "demo-alert",
        ScenarioSpec(
            name="demo-alert",
            description="1900-node scenario where BESS cannot bridge the predicted "
                        "peak — insufficient_reserve_alert fires at tick 1.  "
                        "exercises the alert latch (F4) and basis label (F2).",
            workload_events=[_evt_start("job-alert", 1900)],
            dt_lead_seconds=30.0,
            bess_units=[_bess("bess-0", rated_mw=5.0, usable_mwh=2.5, grid_forming=True)],
            turbine_units=[_turbine("turbine-0", rated_mw=25.0, r_mw_per_s=0.2)],
            solar_rated_mw=_SOLAR_20MW,
            end_sim_time=300.0,
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
                _turbine("turbine-01", rated_mw=15.0, r_mw_per_s=0.2),
                _turbine("turbine-02", rated_mw=15.0, r_mw_per_s=0.2),
                _turbine("turbine-03", rated_mw=15.0, r_mw_per_s=0.16),
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
]


def build_seeded_store() -> ScenarioStore:
    """Return a ScenarioStore pre-loaded with all built-in demo scenarios."""
    store = ScenarioStore()
    for sid, spec in _SEEDED:
        store._seed(sid, spec)
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
