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
from typing import Optional

from pydantic import BaseModel, Field, model_validator

# Step 9: AssertionSpec lives in runtime/verdict.py so that runtime/ code can
# import it without creating a runtime/ → api/ circular dependency.
from runtime.verdict import AssertionSpec  # noqa: F401 (re-exported for callers)


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
