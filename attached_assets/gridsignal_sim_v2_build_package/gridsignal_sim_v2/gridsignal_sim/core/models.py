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
    # Step 8 scaffolding (§7.1.1) — keeps SOLAR_STEP in the workload enum so the
    # arbitrator's stage_for_predicted_step path is exercised with dt_lead=0,
    # proving TC-33 symmetry (identical delta_p_mw → identical staging arithmetic
    # regardless of whether ΔP came from a compute step or a renewable drop).
    #
    # IMPORTANT — this is NOT the correct permanent home for renewable telemetry.
    # Solar irradiance is SCADA/EMS data, not scheduler intent.  Step 11 (§28)
    # will introduce a dedicated SCADA telemetry path; at that point SOLAR_STEP
    # should be retired from WorkloadEventType and replaced by a SCADA event that
    # flows through its own signal handler.  Do not use SOLAR_STEP as a precedent
    # for routing non-workload signals through this enum.
    SOLAR_STEP = "solar_step"


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
    # §7.1.1 SOLAR_STEP: magnitude of the renewable-output drop that triggers
    # staging.  Zero for all other event types.  Named _mw (megawatts) not
    # _fraction because staging arithmetic works in absolute power, not ratios.
    renewable_shortfall_mw: float = 0.0


# ---------------------------------------------------------------------------
# Operating mode (Step 3 Item 4 / v2.5 §7.1.2)
# ---------------------------------------------------------------------------

class IslandMode(str, Enum):
    """Site-level operating mode — read each tick by the dispatch arbitrator,
    not from static config, because the anchor role changes with mode.

    Default: ISLANDED.  Rationale (TC-63): defaulting to GRID_TIE makes
    P_anchor_reserve zero for every unit (grid_forming has no effect unless
    islanded), which silently reproduces the unadjusted arithmetic this
    constraint exists to correct.  The representative market for this product
    is islanded data centres; ISLANDED is therefore both conservative and
    realistic.

    Mode transition machinery is out of scope until Step 11 (§28).  The
    field is mutable on SiteConfig so Step 11 can flip it without changing
    BessConfig or the dispatch interface.
    """
    GRID_TIE = "grid_tie"
    ISLANDED  = "islanded"


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
    # Step 3 Item 4 — §7.1.2: anchor constraint is mode-dependent.
    # Default ISLANDED: conservative (TC-63) and representative market.
    # Step 11 (§28) will add the transition machinery; for now we expose the
    # field so the arbitrator can read it each tick.
    island_mode: IslandMode = IslandMode.ISLANDED


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
    # Step 3 Item 4 — v2.5 §7.1.2: anchor reserve.
    # p_anchor_reserve_mw: power withheld from bridging when this unit is the
    #   island's grid-forming anchor (grid_forming=True, island_mode=ISLANDED).
    #   An anchor must retain headroom in BOTH directions to regulate against
    #   disturbance; its full rating is therefore not available for bridging.
    # TC-63: default must be non-zero — defaulting to 0 silently reproduces the
    #   unadjusted arithmetic this constraint exists to correct.  1.0 MW is a
    #   CHOSEN value (no measured basis, PROTO-9); calibrate against design partner
    #   frequency-regulation specs.
    p_anchor_reserve_mw: float = 1.0  # CHOSEN — non-zero per TC-63, no measured basis (PROTO-9)
    # grid_forming: True when this unit is the designated grid-forming anchor
    #   for the islanded bus.  False = grid-following; P_anchor_reserve = 0.
    #   Default False: most units in a fleet are grid-following; the anchor role
    #   is an explicit designation, not a default assumption.
    grid_forming: bool = False

    def __post_init__(self) -> None:
        """D12 / PROTO-9: warn when C-rate is outside the 0.25–4.0 C physical
        range (chosen, no measured basis).  Deployed grid storage runs ~0.5 C;
        the guard exists to catch typos, not to block non-standard configs.
        Emitted as a warning so operators modelling real systems outside this
        range are not blocked.
        """
        import warnings
        _c_rate = self.rated_mw / self.usable_mwh
        if not (0.25 <= _c_rate <= 4.0):
            warnings.warn(
                f"BessConfig {self.asset_id!r}: C-rate {_c_rate:.2f} C is "
                f"outside the 0.25–4.0 C physical range "
                f"(PROTO-9 — chosen, no measured basis). "
                f"rated_mw={self.rated_mw}, usable_mwh={self.usable_mwh}",
                UserWarning,
                stacklevel=2,
            )


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
    # F5: interval-END timestamp — the simulated instant this TickResult describes.
    # Equals clock.sim_time + clock.dt_seconds.  All internal elapsed-time checks
    # inside evaluate_tick() use clock.sim_time (interval-start); this persisted
    # and wire field carries the interval-end value so stored rows are aligned with
    # the physical state they represent and FR-1.5 MAPE attribution is unbiased.
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
    # D7 fix: §5.1 onboarding alerts — frozenset of hardware_profile_id strings
    # for which the one-time alert fired on this tick.  Empty frozenset = no new
    # alerts.  Deduplicated per (site_id, hardware_profile_id) in SimulationState
    # so the set is non-empty on at most one tick per unique profile_id per run.
    unrecognised_profile_alerts: frozenset[str] = field(default_factory=frozenset)
    checkpoint_states: dict[str, str] = field(default_factory=dict)  # job_id -> state
    # Step 5: wall-clock stamp at the tick start, as a UTC Unix timestamp.
    # Supplied by RunContext.step() via SimClock; 0.0 is the safe sentinel for
    # tests that do not inject a real wall stamp.  Needed alongside sim_time so
    # forecast-error attribution can compare simulated latency to real latency.
    wall_stamp_utc: float = 0.0
    # Step 7: three fields required by the live dashboard that are computed in
    # core but were absent from TickResult (and therefore the WS payload).
    #
    # p_renewable_mw: cannot be back-computed from net_demand_mw after the fact
    #   because the clamp max(0, p_total − p_renewable) is lossy: when renewable
    #   output exceeds total load, net_demand_mw is 0 and p_renewable is invisible.
    p_renewable_mw: float = 0.0
    # bess_bridging_seconds: how long the BESS fleet can sustain net_demand_mw
    #   from current state of charge, using the same proportional-allocation +
    #   min() logic as stage_for_predicted_step (D13).  Using the SAME function
    #   (BessModule.max_sustainable_seconds) ensures the AssetReservePanel and
    #   the insufficient-reserve alert arithmetic are identical; they cannot
    #   disagree if they call the same code.
    #   C1 correction: a MW/MW × 3600 ratio computed in the serializer would be
    #   dimensionally wrong (§7.2.4 names this exact error).  The duration must
    #   come from max_sustainable_seconds(), not from the serializer.
    #   math.inf when net_demand_mw == 0 (no load, no bridging required);
    #   serializer caps to 86 400.0 (24 h) for JSON safety.
    bess_bridging_seconds: float = 0.0
    # dt_lead_next_s: seconds until the next in-flight GPU job reaches full TDP.
    #   C2 correction: min() across in-flight ramp remaining times, not sum().
    #   Two jobs with 10 s and 30 s remaining → next TDP event in 10 s.
    #   sum() = 40 s corresponds to no physical event.
    #   Named dt_lead_next_s (not dt_lead_s) so the semantics are on the field.
    #   0.0 when no job is currently ramping.
    dt_lead_next_s: float = 0.0
    # bridging_basis: which demand figure is binding for bess_bridging_seconds.
    # F2 fix: when a staged prediction's predicted peak shortfall exceeds current
    # net demand, the panel must answer the same question as the alert banner
    # ("can the BESS sustain the predicted peak?"), not the easier question
    # ("can it sustain the near-zero current demand?").
    #   "predicted_peak" — staged prediction's peak shortfall is the binding figure.
    #   "current_demand" — current net_demand_mw is the binding figure.
    #   "no_load"        — net demand is zero; bridging is not required.
    bridging_basis: str = "current_demand"
