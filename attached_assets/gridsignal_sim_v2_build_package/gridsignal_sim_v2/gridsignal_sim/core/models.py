"""
Shared data models for the GridSignal Simulator.

These are plain dataclasses -- no ORM, no async -- so the simulation
core (asset_modules.py, dispatch.py, simulation_core.py) stays a pure,
synchronous, independently-testable library, per Design Spec Section 2
("fidelity over cleverness") and Section 5.

Persistence (SQLAlchemy models) is intentionally a separate concern and
is not defined here -- see runtime/persistence.py for the mapping from
these dataclasses to stored rows (Design Spec Section 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Hardware / workload
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HardwareProfile:
    """Source spec Section 5: kW_i lookup, keyed by hardware_profile_id.

    v2.5 §5.2: counting_unit declares what node_count is expressed in
    (chassis / cabinet / package / die / accelerator).  A site reporting
    dies against a profile assuming packages produces a forecast off by
    exactly 2x with no visible symptom other than persistent forecast error
    (TC-53).  Validation logic deferred to Step 10.

    v2.5 §5.3: vintage_generation + vintage_established let the confidence
    engine flag stale profiles.  Forecasting against a two-generation-old
    profile under-predicts by 60-90 kW/cabinet (TC-54).  No validation yet.
    """
    profile_id: str
    rated_kw: float
    description: str = ""
    # v2.5 §5.2 — counting unit; must be one of the five canonical values but
    # validation is deferred to Step 10.  Optional so existing call-sites that
    # omit it are not broken.
    counting_unit: Optional[str] = None    # chassis|cabinet|package|die|accelerator
    # v2.5 §5.3 — profile vintage.  Optional for the same reason.
    vintage_generation: Optional[str] = None   # e.g. "gen4", "h100", "grace-hopper"
    vintage_established: Optional[str] = None  # ISO-8601 date string, e.g. "2024-Q1"


GENERIC_FALLBACK_PROFILE = HardwareProfile(
    profile_id="generic_fallback",
    rated_kw=12.0,  # MVP default per source spec Section 5.1
    description="Unmapped/unrecognized hardware profile",
)


class WorkloadEventType(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    SCALE = "scale"
    CHECKPOINT_START = "checkpoint_start"
    CHECKPOINT_END = "checkpoint_end"
    JOB_END = "job_end"
    CANCELLED = "cancelled"


class WorkloadClass(str, Enum):
    TRAINING = "training"
    INFERENCE = "inference"
    OTHER = "other"


@dataclass
class WorkloadSignal:
    """Source spec Section 10 payload contract, as scripted by the
    simulator's Scenario Builder (functional spec Section 6/7.2) instead
    of arriving from a real Slurm/K8s/Ray integration."""
    event_id: str
    job_id: str
    event_type: WorkloadEventType
    timestamp: float  # simulated seconds since run start
    hardware_profile_id: str
    node_count: int
    workload_class: WorkloadClass
    site_id: str
    queue_depth: Optional[float] = None  # required for inference class


# ---------------------------------------------------------------------------
# Asset configuration (Design Spec Section 6 / functional spec Section 8.1)
# ---------------------------------------------------------------------------

@dataclass
class SiteConfig:
    site_id: str
    pue_base: float = 1.03            # source spec Section 4, 1.02-1.05
    alpha_max: float = 0.20           # source spec Section 8, 0.10-0.30
    tau_seconds: float = 20.0         # source spec Section 8
    dt_thermal_seconds: float = 90.0  # source spec Section 8-9, 60-120s
    uncalibrated: bool = True         # source spec Section 17.3


@dataclass
class TurbineConfig:
    asset_id: str
    r_asset_mw_per_s: float = 0.2     # source spec Section 7.1 MVP default
    rated_mw: float = 10.0


@dataclass
class BessConfig:
    asset_id: str
    rated_mw: float = 5.0
    usable_mwh: float = 2.0
    initial_soc_fraction: float = 1.0


@dataclass
class SolarConfig:
    """Extension E-1 -- not in the source spec; simulator-only."""
    asset_id: str
    rated_mw: float = 4.0


# ---------------------------------------------------------------------------
# Data quality / confidence tagging (source spec Section 5.1, 12, 17.2-17.3)
# ---------------------------------------------------------------------------

class DataQualityTag(str, Enum):
    UNMAPPED_HARDWARE = "unmapped_hardware"
    UNCALIBRATED_SITE = "uncalibrated_site"
    INVALID_PAYLOAD = "invalid_payload"
    STALE_PROFILE = "stale_profile"   # v2.5 §5.3: profile vintage is outdated


@dataclass
class ConfidenceBand:
    point_estimate_mw: float
    plus_minus_fraction: float
    tags: frozenset[DataQualityTag] = field(default_factory=frozenset)

    @property
    def lower_bound_mw(self) -> float:
        return self.point_estimate_mw * (1 - self.plus_minus_fraction)

    @property
    def upper_bound_mw(self) -> float:
        return self.point_estimate_mw * (1 + self.plus_minus_fraction)


# ---------------------------------------------------------------------------
# Tick output
# ---------------------------------------------------------------------------

@dataclass
class TickResult:
    """One row of RunTimeseries (functional spec Section 6.5). This is
    the object that flows: evaluate_tick() -> persistence -> WebSocket
    broadcast, per Design Spec Section 4.2/4.4."""
    run_id: str
    tick_index: int
    sim_time_seconds: float
    p_compute_mw: float
    p_cooling_mw: float
    p_total_mw: float
    net_demand_mw: float               # p_total - solar output, Section 4.4.2
    turbine_output_mw: float
    bess_output_mw: float
    bess_soc_fraction: float
    confidence: ConfidenceBand
    insufficient_reserve_alert: bool = False
    checkpoint_states: dict[str, str] = field(default_factory=dict)  # job_id -> state
