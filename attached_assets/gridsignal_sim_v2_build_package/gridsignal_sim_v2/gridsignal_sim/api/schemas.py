"""
api/schemas.py — Pydantic request / response models for the HTTP API.

Step 6 / v2.5 §8.1.

No imports from core/ — the wire format is owned here; core/models.py
is the authoritative in-process representation and is not exposed
directly to callers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StartRunRequest(BaseModel):
    job_id: str
    node_count: int = Field(ge=1, description="Number of GPU nodes")
    hardware_profile_id: str = "enterprise_8gpu_air"
    end_sim_time: float = Field(default=300.0, gt=0, description="Simulated seconds to run")
    playback_speed: float = Field(
        default=0.0,
        ge=0,
        description="Simulated seconds per real second (0 = max speed)",
    )


class StartRunResponse(BaseModel):
    run_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    active: bool


class RunListResponse(BaseModel):
    run_ids: list[str]
