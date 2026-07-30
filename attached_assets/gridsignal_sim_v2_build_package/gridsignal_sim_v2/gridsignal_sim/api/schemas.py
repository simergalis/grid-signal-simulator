"""
api/schemas.py — Pydantic request / response models for the HTTP API.

Step 6 / v2.5 §8.1.

No imports from core/ — the wire format is owned here; core/models.py
is the authoritative in-process representation and is not exposed
directly to callers.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Accepted values for scenario_preset (F1 scaffolding — Step 8 replaces
# with real scenario CRUD).
ScenarioPreset = Literal["demo-20mw", "demo-alert", "demo-5mw", "demo-baseline"]


class StartRunRequest(BaseModel):
    # F1 fix: scenario_preset bypasses the per-field job_id / node_count
    # requirement, instead expanding to the build_run_context kwargs defined
    # in _SCENARIO_PRESETS (api/routes/runs.py).  This is scaffolding so
    # Page 1 is demonstrable without Step 8's real scenario CRUD.
    scenario_preset: Optional[ScenarioPreset] = Field(
        default=None,
        description=(
            "Named demo preset.  Sets all BESS / turbine parameters to the values "
            "used by example_usage.py, including bess_rated_mw and bess_usable_mwh "
            "which the individual fields cannot currently express.  When present, "
            "job_id and node_count are optional.  Step 8 replaces this with real "
            "scenario CRUD."
        ),
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Job identifier; required when scenario_preset is not set.",
    )
    node_count: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of GPU nodes; required when scenario_preset is not set.",
    )
    hardware_profile_id: str = "enterprise_8gpu_air"
    end_sim_time: float = Field(default=300.0, gt=0, description="Simulated seconds to run")
    playback_speed: float = Field(
        default=0.0,
        ge=0,
        description="Simulated seconds per real second (0 = max speed)",
    )

    @model_validator(mode="after")
    def _require_job_fields_without_preset(self) -> "StartRunRequest":
        """job_id and node_count are required exactly when scenario_preset is absent."""
        if self.scenario_preset is None:
            missing = [
                name
                for name, val in [("job_id", self.job_id), ("node_count", self.node_count)]
                if val is None
            ]
            if missing:
                raise ValueError(
                    f"Fields {missing} are required when scenario_preset is not provided."
                )
        return self


class StartRunResponse(BaseModel):
    run_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    active: bool


class RunListResponse(BaseModel):
    run_ids: list[str]
