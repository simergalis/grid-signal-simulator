"""
api/schemas.py — Pydantic request / response models for the HTTP API.

Step 6 / v2.5 §8.1.
Step 8: adds ScenarioSpec + related models; removes F1 scenario_preset scaffolding.
Step 9: adds AssertionSpec (imported from runtime.verdict) + ScenarioSpec.assertions;
        adds RunResultResponse and TimeseriesResponse for the results screen.

No imports from core/ — the wire format is owned here; core/models.py
is the authoritative in-process representation and is not exposed
directly to callers.

The import of AssertionSpec from runtime.verdict (api/ → runtime/) is an allowed
direction per §21.1; runtime/ → api/ is the forbidden direction.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Step 9: AssertionSpec lives in runtime/verdict.py so that runtime/ code can
# import it without creating a runtime/ → api/ circular dependency.
from runtime.verdict import AssertionSpec  # noqa: F401 (re-exported for callers)


# ---------------------------------------------------------------------------
# Step 11: PMS config schema (AB1)
# ---------------------------------------------------------------------------

class PmsConfigSpec(BaseModel):
    """Wire-format mirror of core.models.PmsConfig.

    All fields match the dataclass fields exactly so that
    ``PmsConfig(...)`` wiring in build_run_context_from_spec is safe
    without any field-name translation.

    transition_mode must be one of the TransitionMode string values:
      "open_transition"   — default; brief coverage gap during reconnect
                            (open_transition_gap_mw for open_transition_duration_s).
      "closed_transition" — instantaneous; no coverage gap.

    shed_priority_order: list of workload job_ids to shed first (highest
    priority first).  Empty list → PMS sheds in arbitrary order.

    All bounds are CHOSEN (PROTO-11).
    """
    shed_priority_order: list[str] = Field(default_factory=list)
    transition_mode: Literal["open_transition", "closed_transition"] = "open_transition"
    open_transition_gap_mw: float = Field(default=2.0, ge=0.0)
    open_transition_duration_s: float = Field(default=5.0, gt=0.0)
    fast_shed_duration_s: float = Field(default=30.0, gt=0.0)


# ---------------------------------------------------------------------------
# Step 10: Pre-staging config schema (AA1)
# ---------------------------------------------------------------------------

class PreStagingConfigSpec(BaseModel):
    """Wire-format mirror of core.models.PreStagingConfig.

    All fields match the dataclass fields exactly so that
    ``PreStagingConfig(**spec_data["pre_staging_config"])`` is safe in
    build_run_context_from_spec without any field-name translation.

    All values are CHOSEN (PROTO-10).  See core/models.py PreStagingConfig
    for the hold-analysis and design rationale.
    """
    max_shift_mw: float = Field(default=1.0, ge=0.0, le=50.0)
    inlet_temp_low_c: float = Field(default=18.0, ge=10.0, le=30.0)
    inlet_temp_high_c: float = Field(default=24.0, ge=15.0, le=35.0)
    cooling_gain_c_per_mw_s: float = Field(default=0.05, gt=0.0)
    warmup_rate_c_per_s: float = Field(default=0.002, ge=0.0)
    initial_temp_c: float = Field(default=21.0, ge=10.0, le=35.0)
    bms_override: bool = False


# ---------------------------------------------------------------------------
# AD1: Procurement config schema (TC-47, TC-52)
# ---------------------------------------------------------------------------

class ProcurementConfigSpec(BaseModel):
    """Wire-format config for §24 grid procurement (ProcurementLayer).

    Gates whether a ProcurementLayer is instantiated in the run context.
    The layer calls NonFirmImportEffect.apply() (TC-47) and creates
    ReservationProposal objects (TC-52) each tick when reserve_gap > 0.

    All capacity values are CHOSEN (PROTO-AD1).
    """
    firm_available_mw: float = Field(default=20.0, ge=0.0)
    reserved_available_mw: float = Field(default=10.0, ge=0.0)
    non_firm_available_mw: float = Field(default=3.0, ge=0.0)
    price_curve_seed: int = Field(default=42, ge=0)


# ---------------------------------------------------------------------------
# AD1: Maintenance config schema (TC-58, TC-59, TC-60)
# ---------------------------------------------------------------------------

class MaintenanceConfigSpec(BaseModel):
    """Wire-format config for §27 prescriptive maintenance (MaintenanceLayer).

    Gates whether a MaintenanceLayer is instantiated in the run context.
    The layer calls reserve_contribution_mw_per_s() (TC-58), validate_window()
    (TC-59), and propose_rating_change() (TC-60) during live runs.

    effective_ramp_mw_per_s < nameplate_ramp_mw_per_s → asset starts DEGRADED,
    so the first propose_rating_change() call is a RAISE (TC-60 requires
    confirmation; reduction is immediate).

    All values are CHOSEN (PROTO-AD1).
    """
    asset_id: str = "turbine-0"
    nameplate_ramp_mw_per_s: float = Field(default=0.2, gt=0.0)
    effective_ramp_mw_per_s: float = Field(default=0.15, gt=0.0)
    reserve_threshold_mw: float = Field(default=1.0, ge=0.0)


# ---------------------------------------------------------------------------
# AD1: Ramp relaxation config schema (TC-75, TC-76)
# ---------------------------------------------------------------------------

class RampRelaxationConfigSpec(BaseModel):
    """Wire-format config for §23.7.2 adaptive ramp relaxation (RampRelaxationEngine).

    Gates whether a RampRelaxationEngine is instantiated in the run context.
    The engine's evaluate() runs each tick (TC-75: upper-bound reserve check;
    TC-76: gridSignal_connected=False reverts to baseline — tested via unit test,
    but the evaluate() path is exercised every demo tick).

    All values are CHOSEN (PROTO-AD1).
    """
    reserve_threshold_mw: float = Field(default=2.0, ge=0.0)
    baseline_ramp_cap_mw: float = Field(default=5.0, gt=0.0)
    baseline_ramp_duration_s: float = Field(default=75.0, gt=0.0)
    adaptive_ramp_duration_s: float = Field(default=30.0, gt=0.0)


# ---------------------------------------------------------------------------
# Step 8: Scenario schemas
# ---------------------------------------------------------------------------

class WorkloadEventSpec(BaseModel):
    """One scripted workload event (GPU job or renewable step) within a scenario.

    event_type must be a WorkloadEventType string value:
      "starting"   — GPU job ramp begins; staging fires with dt_lead_seconds.
      "job_end"    — GPU job finishes.
      "solar_step" — Renewable curtailment; staging fires with dt_lead=0 (§7.1.1).
      Any other WorkloadEventType value is forwarded as-is.

    For solar_step events job_id, node_count, and hardware_profile_id are
    ignored by the runtime; renewable_shortfall_mw carries the staging delta.
    """
    event_id: str = Field(default_factory=lambda: f"evt-{_uuid.uuid4().hex[:8]}")
    job_id: str = ""
    event_type: str  # WorkloadEventType string value
    timestamp: float = Field(ge=0.0)
    node_count: int = Field(default=0, ge=0)
    hardware_profile_id: str = "enterprise_8gpu_air"
    # §7.1.1 SOLAR_STEP: magnitude of the renewable drop that triggers staging.
    # Zero for all other event types.
    renewable_shortfall_mw: float = Field(default=0.0, ge=0.0)


class BessUnitSpec(BaseModel):
    """One BESS unit within a scenario's fleet."""
    asset_id: str
    rated_mw: float = Field(gt=0)
    usable_mwh: float = Field(gt=0)
    initial_soc_fraction: float = Field(default=0.95, ge=0.1, le=1.0)
    # §7.1.2: at most one unit per scenario may be the grid-forming anchor.
    # Validated at the ScenarioSpec level.
    grid_forming: bool = False

    def c_rate(self) -> float:
        return self.rated_mw / self.usable_mwh

    def c_rate_warning(self) -> Optional[str]:
        """D12 / PROTO-9: warn if C-rate is outside 0.25–4.0 C.
        Returns None when within bounds.  Callers include the warning as a
        response field; it never causes a 400 (the bound is chosen, not
        measured)."""
        c = self.c_rate()
        if not (0.25 <= c <= 4.0):
            return (
                f"{self.asset_id}: C-rate {c:.2f} C outside 0.25–4.0 C "
                f"(PROTO-9 — chosen, no measured basis; "
                f"rated_mw={self.rated_mw}, usable_mwh={self.usable_mwh})"
            )
        return None


class TurbineUnitSpec(BaseModel):
    """One turbine unit within a scenario's fleet."""
    asset_id: str
    rated_mw: float = Field(default=10.0, gt=0)
    r_asset_mw_per_s: float = Field(default=0.2, gt=0)


class ScenarioSpec(BaseModel):
    """Full scenario configuration.  Stored as spec_json in ScenarioRecord.
    Posted to POST /scenarios or PUT /scenarios/{id}.

    irradiance_steps convention — zero-order hold ("value applies from t
    onward"): [(0.0, 1.0), (30.0, 0.0)] gives 1.0 for t<30 and 0.0 for
    t≥30.  The last sample's value applies for all time beyond it.
    """
    name: str = Field(min_length=1)
    description: str = ""

    # Workload events ordered by timestamp.  Empty list = no scripted events
    # (idle run or run with pre-existing state from t<0, which is not yet
    # supported — see TC-33 compute scenario for the deferred-start pattern).
    workload_events: list[WorkloadEventSpec] = Field(default_factory=list)
    hardware_profile_id: str = "enterprise_8gpu_air"
    dt_lead_seconds: float = Field(
        default=30.0, ge=0.0, le=300.0,
        description=(
            "Advance warning time for GPU job starts (seconds).  "
            "SOLAR_STEP events always use dt_lead=0 regardless of this value (§7.1.1)."
        ),
    )

    bess_units: list[BessUnitSpec] = Field(min_length=1)
    turbine_units: list[TurbineUnitSpec] = Field(min_length=1)

    solar_rated_mw: float = Field(default=0.0, ge=0.0)
    irradiance_steps: list[tuple[float, float]] = Field(
        default_factory=lambda: [(0.0, 1.0)],
        description="Zero-order-hold irradiance profile. Duplicate timestamps unnecessary.",
    )

    island_mode: bool = True
    pue_base: float = Field(default=1.03, ge=1.0, le=2.0)
    end_sim_time: float = Field(default=300.0, ge=60.0, le=86400.0)

    # Step 10: optional §8.1 pre-staging configuration.
    # None = PreStagingEngine not instantiated (SiteConfig.pre_staging_config = None).
    pre_staging_config: Optional[PreStagingConfigSpec] = None

    # Step 11: optional §28.4 PMS configuration.
    # None = SimulatedPMS not instantiated (SiteConfig.pms_config = None).
    # fast_shed and open_transition are injected at runtime via
    # SimulatedPMS.inject_fast_shed() / inject_transition(); the scenario only
    # gates whether the PMS code path is active.
    pms_config: Optional[PmsConfigSpec] = None

    # AD1: optional §24 procurement configuration.
    # None = ProcurementLayer not instantiated.
    # When set, NonFirmImportEffect.apply() (TC-47) and ReservationProposal
    # (TC-52) are exercised each tick during the live run.
    procurement_config: Optional[ProcurementConfigSpec] = None

    # AD1: optional §27 maintenance configuration.
    # None = MaintenanceLayer not instantiated.
    # When set, reserve_contribution_mw_per_s (TC-58), validate_window (TC-59),
    # and propose_rating_change (TC-60) are exercised during the live run.
    maintenance_config: Optional[MaintenanceConfigSpec] = None

    # AD1: optional §23.7.2 ramp relaxation configuration.
    # None = RampRelaxationEngine not instantiated.
    # When set, evaluate() is called each tick (TC-75 upper-bound reserve check;
    # TC-76 gridSignal_connected=False revert is covered by unit test).
    ramp_relaxation_config: Optional[RampRelaxationConfigSpec] = None

    # AD2: site calibration flag.
    # False (default) = SiteConfig.uncalibrated=True (§17.3 default: uncalibrated
    # until explicit calibration run).  The TC-43 low-confidence interlock
    # resets the curtailment dwell every tick while uncalibrated is True, so
    # curtailment proposals never fire in the default state.
    # True = SiteConfig.uncalibrated=False — site is treated as calibrated,
    # curtailment ladder fires normally once the dwell elapses.
    # Only set True for scenarios where the curtailment path must engage
    # (e.g. demo-pms-shortfall for TC-65 conflict detection).
    calibrated: bool = False

    # Step 9: optional pass/fail assertions evaluated at run completion.
    # Each element is one of the AssertionSpec union members (discriminated
    # on 'check').  Empty list → verdict is INCONCLUSIVE.
    assertions: list[AssertionSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _single_grid_forming_anchor(self) -> "ScenarioSpec":
        """§7.1.2: only one BESS unit may be the grid-forming anchor."""
        forming = [u for u in self.bess_units if u.grid_forming]
        if len(forming) > 1:
            ids = [u.asset_id for u in forming]
            raise ValueError(
                f"§7.1.2: at most one BESS unit may have grid_forming=True "
                f"(found {len(forming)}: {ids}). "
                f"Only the designated island-frequency anchor holds the anchor reserve."
            )
        return self

    def collect_c_rate_warnings(self) -> list[str]:
        """Return all non-None C-rate warnings across the BESS fleet."""
        return [w for u in self.bess_units if (w := u.c_rate_warning()) is not None]


class ScenarioSummary(BaseModel):
    """Lightweight row returned by GET /scenarios (list)."""
    scenario_id: str
    name: str
    description: str
    created_at: str   # ISO-8601 UTC


class ScenarioDetailResponse(BaseModel):
    """Full detail returned by GET /scenarios/{id}."""
    scenario_id: str
    name: str
    description: str
    created_at: str
    spec: ScenarioSpec
    c_rate_warnings: list[str]


class CreateScenarioResponse(BaseModel):
    """Returned by POST /scenarios and PUT /scenarios/{id}."""
    scenario_id: str
    name: str
    c_rate_warnings: list[str]


# ---------------------------------------------------------------------------
# Run lifecycle schemas
# ---------------------------------------------------------------------------

class StartRunRequest(BaseModel):
    """Start a new simulation run.

    Two accepted paths:
      (a) scenario_id  — reference a stored ScenarioSpec; fleet and workload
          parameters come from the stored spec.
      (b) job_id + node_count  — direct programmatic path; used by tests and
          load-test scripts.

    Step 8 removes the F1 scenario_preset scaffolding.  Callers that used
    scenario_preset must switch to scenario_id (POST /scenarios first to
    obtain one).
    """
    scenario_id: Optional[str] = Field(
        default=None,
        description="Stored scenario ID from GET /scenarios. "
                    "When set, all fleet/workload parameters come from the spec.",
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Job identifier; required when scenario_id is not set.",
    )
    node_count: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of GPU nodes; required when scenario_id is not set.",
    )
    hardware_profile_id: str = "enterprise_8gpu_air"
    end_sim_time: float = Field(default=300.0, gt=0, description="Simulated seconds to run")
    playback_speed: float = Field(
        default=0.0,
        ge=0,
        description="Simulated seconds per real second (0 = max speed)",
    )

    @model_validator(mode="after")
    def _require_scenario_or_job_fields(self) -> "StartRunRequest":
        """scenario_id OR (job_id + node_count) must be present."""
        if self.scenario_id is None:
            missing = [
                name
                for name, val in [("job_id", self.job_id), ("node_count", self.node_count)]
                if val is None
            ]
            if missing:
                raise ValueError(
                    f"Fields {missing} are required when scenario_id is not provided."
                )
        return self


class StartRunResponse(BaseModel):
    run_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    active: bool


class RunListResponse(BaseModel):
    run_ids: list[str]


# ---------------------------------------------------------------------------
# Step 9: Results / playback response schemas
# ---------------------------------------------------------------------------

class AssertionResultResponse(BaseModel):
    """One assertion's evaluation outcome, as returned by GET /runs/{id}/result."""
    check: str
    status: str   # "PASS" | "FAIL" | "INCONCLUSIVE"
    detail: str


class RunResultResponse(BaseModel):
    """Full verdict returned by GET /runs/{run_id}/result."""
    run_id: str
    scenario_id: Optional[str] = None
    scenario_name: str
    completed_at: str              # ISO-8601 UTC
    overall: str                   # "PASS" | "FAIL" | "INCONCLUSIVE"
    tick_count: int
    dropped_ticks: int
    gap_count: int
    assertions: list[AssertionResultResponse]


class TimeseriesRowResponse(BaseModel):
    """One tick row returned by GET /runs/{run_id}/timeseries.

    sim_time_seconds is stored from the serialisation layer (F5 convention:
    interval-END time) and is never re-derived here.
    """
    tick_index: int
    sim_time_seconds: float
    p_compute_mw: float
    p_cooling_mw: float
    p_total_mw: float
    net_demand_mw: float
    turbine_output_mw: float
    bess_output_mw: float
    bess_soc_fraction: float
    confidence_lower_mw: float
    confidence_upper_mw: float
    insufficient_reserve_alert: bool
    p_renewable_mw: float
    bess_bridging_seconds: float
    dt_lead_next_s: float
    bridging_basis: str
    gap_before: bool               # True when tick_index jumps > 1 from the previous row


class TimeseriesResponse(BaseModel):
    """Full timeseries returned by GET /runs/{run_id}/timeseries."""
    run_id: str
    gap_count: int
    rows: list[TimeseriesRowResponse]
