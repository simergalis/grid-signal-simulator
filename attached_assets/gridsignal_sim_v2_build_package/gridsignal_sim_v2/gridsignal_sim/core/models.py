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


class OperatingTier(str, Enum):
    """§26.2 authority tier — minimum machinery for Step 10.

    Same pattern as IslandMode (Step 3 Item 4): a field on SiteConfig, read
    each tick by the curtailment ladder.  Full authority-role machinery
    (operator vs. approver vs. admin) is deferred to a later step.

    AUTONOMOUS: A/B curtailment may execute without human confirmation.
               C/D are STILL blocked (TC-42 — requires_confirmation is set
               at tier construction, independent of operating_tier).
    SUPERVISED: conservative default.  A/B autonomous within bounds; C/D
               require explicit human confirmation.  Low-confidence segments
               block all autonomous curtailment (TC-43).
    OPERATOR:   explicit human confirmation required for every tier above A.

    Default: SUPERVISED — conservative, same rationale as ISLANDED.
    """
    AUTONOMOUS = "autonomous"
    SUPERVISED = "supervised"
    OPERATOR   = "operator"


class TransitionMode(str, Enum):
    """§28.3 mode used when utility supply fails.

    OPEN_TRANSITION (default): a brief coverage gap exists between utility loss
    and island stabilisation.  The gap is a discontinuity to be ridden through
    by dispatchable assets, not a smooth capacity reduction (TC-67).

    CLOSED_TRANSITION: supply handoff is seamless (requires a make-before-break
    transfer switch).  Not modelled in detail; placeholder for a future step.

    Default OPEN_TRANSITION: conservative and representative of most sites that
    do not have synchronised transfer gear.
    """
    OPEN_TRANSITION   = "open_transition"
    CLOSED_TRANSITION = "closed_transition"


@dataclass
class PmsConfig:
    """§28.4 simulated Power Management System configuration.

    The PMS holds its own shed priority order, independent of GridSignal's
    curtailment priority (TC-65).  Where the two disagree a commissioning defect
    is reported — the PMS order is authoritative and GridSignal does not override
    it.

    Hold analysis (D1/D2/D4 pattern):
      Fast shed bound:    fast_shed_duration_s — CHOSEN (PROTO-11).
      Fast shed terminal: duration elapses; no external release needed.
      Fast shed no-release: auto-clears; PMS retains physical authority
          regardless of GridSignal connectivity.
      Transition bound:   open_transition_duration_s — CHOSEN (PROTO-11).
      Transition terminal: duration elapses.
      Transition no-release: auto-clears; conservative simplification (PROTO-11).

    All numeric values are CHOSEN (no measured basis, PROTO-11).
    """
    # Ordered list of asset / load IDs the PMS would shed first (index 0 first).
    shed_priority_order: list = field(default_factory=list)
    transition_mode: TransitionMode = TransitionMode.OPEN_TRANSITION
    # MW increase in P_dispatch_required during open-transition coverage gap (TC-67).
    open_transition_gap_mw: float = 2.0     # CHOSEN (PROTO-11)
    # Duration of the open-transition coverage gap.
    open_transition_duration_s: float = 5.0  # CHOSEN (PROTO-11)
    # How long a fast shed event persists before auto-clearing.
    fast_shed_duration_s: float = 30.0       # CHOSEN (PROTO-11)


@dataclass
class PreStagingConfig:
    """§8.1 shiftable thermal load parameters (Step 10).

    Pre-staging pre-cools the data hall within the inlet-temperature band
    (TC-55), reducing P_dispatch_required ahead of a dispatchable demand peak.
    The BMS retains unconditional override (TC-56): when bms_override is True
    on any tick the engine returns 0.0 MW shifted.

    Hold analysis (D1/D2/D4 pattern):
      Bound:    inlet_temp_low_c — cannot cool below the lower comfort bound.
      Terminal: temperature reaches lower bound; BMS override; gap closes.
      No-release: if gap never closes, temperature-bound acts as the hard cap —
                  shift naturally drops to 0.0 as temp approaches low_c.  The
                  physics provides the bound; no separate dead-man is needed.

    All numeric values are CHOSEN (no measured basis, PROTO-10).
    """
    max_shift_mw: float = 1.0              # CHOSEN (PROTO-10)

    inlet_temp_low_c: float = 18.0         # CHOSEN (PROTO-10)
    inlet_temp_high_c: float = 24.0        # CHOSEN (PROTO-10)
    # °C drop per MW of additional cooling per second of dt.
    cooling_gain_c_per_mw_s: float = 0.05  # CHOSEN (PROTO-10)
    # Ambient warming rate per second when not actively cooling.
    warmup_rate_c_per_s: float = 0.002     # CHOSEN (PROTO-10)
    # Starting inlet temperature; default is midpoint of the comfort band.
    initial_temp_c: float = 21.0           # midpoint of [18.0, 24.0]
    # BMS override flag.  In the real system this arrives as a per-tick
    # telemetry signal; here it is on the config so tests can set it.
    bms_override: bool = False


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

    # ── Confidence band for reserve check (gridsignal_parameters.json §2.5) ──
    # INV-2: reserve check evaluates the band, never the point estimate.
    # Default 0.0 preserves backward-compatibility for all existing tests and
    # seeded scenarios; ScenarioSpec defaults to 4.0% per PROPOSED_HERE decision.
    #
    # Decision: band_pct_calibrated = 4%  (PROPOSED_HERE, this document)
    #   Rationale: at 4% calibrated × 2.0 uncalibrated multiplier = 8%,
    #   which exactly matches the worked-example fixture.  The fixture then
    #   becomes a live regression rather than a historical illustration.
    #
    # Decision: band_mult_uncalibrated = 2.0× (PROPOSED_HERE, this document)
    #   §17.3 requires widening for uncalibrated sites; 2.0× is the minimum
    #   meaningful doubling and matches the worked-example fixture exactly.
    #
    # Decision: band_mult_unmapped_hw = 1.5× (PROPOSED_HERE, this document)
    #   §5.1 requires widening for unmapped hardware; 1.5× is conservative but
    #   avoids excessive alert fatigue when a new profile is first registered.
    band_pct_calibrated:   float = 0.0   # ±% of peak_shortfall; 0=disabled
    band_mult_uncalibrated: float = 2.0  # multiplier for uncalibrated site
    band_mult_unmapped_hw:  float = 1.5  # multiplier for unmapped hardware

    def reserve_band_upper(self, is_unmapped_hw: bool = False) -> float:
        """Band fraction for the reserve check (§2.5, INV-2).

        alert ⟺  peak_shortfall × (1 + reserve_band_upper()) > P_bridge_avail

        Returns 0.0 when band_pct_calibrated is 0 (backward-compatible default).
        Calibrated site: base = band_pct_calibrated / 100.
        Uncalibrated:    base × band_mult_uncalibrated.
        Unmapped HW:     multiply further by band_mult_unmapped_hw.
        """
        if self.band_pct_calibrated <= 0.0:
            return 0.0
        base = self.band_pct_calibrated / 100.0
        mult = self.band_mult_uncalibrated if self.uncalibrated else 1.0
        if is_unmapped_hw:
            mult *= self.band_mult_unmapped_hw
        return base * mult
    # Step 3 Item 4 — §7.1.2: anchor constraint is mode-dependent.
    # Default ISLANDED: conservative (TC-63) and representative market.
    # Step 11 (§28) will add the transition machinery; for now we expose the
    # field so the arbitrator can read it each tick.
    island_mode: IslandMode = IslandMode.ISLANDED
    # Step 10 — §26.2: authority tier, read each tick by the curtailment ladder.
    # Default SUPERVISED: conservative, same rationale as ISLANDED.
    # Full tier machinery deferred to a later step.
    operating_tier: OperatingTier = OperatingTier.SUPERVISED
    # Step 10 — §8.1: optional shiftable thermal load parameters.
    # None = no pre-staging capability on this site.
    pre_staging_config: Optional[PreStagingConfig] = None
    # Step 11 — §28.4: optional simulated PMS configuration.
    # None = no PMS integration on this site (SCADA layer still active;
    # PMS-specific features — fast shed, order conflict, transition — are skipped).
    pms_config: Optional[PmsConfig] = None


@dataclass
class TurbineConfig:
    asset_id: str
    r_asset_mw_per_s: float = 0.2     # source spec Section 7.1 MVP default
    rated_mw: float = 10.0
    # hot_standby: True when this unit is commissioned but not synchronized to the
    # bus.  A hot-standby unit is ready to start but contributes zero to the
    # dispatch fleet and zero to contingency ramp capability (§7.4 / TC-83).
    # Its start time is a separate quantity and must never be folded into a ramp
    # rate.  False = default (synchronized online).
    hot_standby: bool = False


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
# Contingency coverage (§7.4, §7.5)
# ---------------------------------------------------------------------------

class ContingencyState(str, Enum):
    """Three-state N−1 gen-trip coverage readout per §7.4.

    COVERED          — power test ∧ energy test ∧ closable.
    COVERED_WITH_SHED — ¬closable but shed_required ≤ curtailable capacity.
    CANNOT_CARRY     — shed_required exceeds curtailable capacity.
    """
    COVERED           = "COVERED"
    COVERED_WITH_SHED = "COVERED_WITH_SHED"
    CANNOT_CARRY      = "CANNOT_CARRY"


@dataclass(frozen=True)
class ContingencyCoverage:
    """Per-tick output of evaluate_contingency() (core/contingency.py).

    All intermediate results are preserved so display layers and tests can
    inspect them independently.  The two BESS tests (power and energy) are
    kept separate per TC-78 — do not collapse them before returning.
    """
    # Contingency selection
    tripped_unit_id: Optional[str]      # None when fleet has no online units
    deficit_mw: float                    # current output of the tripped unit (TC-77)
    headroom_surviving_mw: float         # Σ(rated_i − output_i) for surviving units
    r_surviving_mw_per_s: float          # Σ r_asset_i for synchronized online survivors
    # BESS fleet (anchor-adjusted per §7.1.2)
    bess_bridging_available_mw: float    # total anchor-adj power ceiling across BESS fleet
    bess_usable_energy_mwh: float        # Σ soc_mwh across BESS fleet
    # Independent tests (TC-78)
    power_test_passes: bool              # bess_bridging_available ≥ deficit
    energy_test_passes: bool             # E_usable ≥ 0.5 × deficit × t_close / 3600
    # Closability
    closable: bool                       # headroom_surviving ≥ deficit
    time_to_close_s: float               # deficit / r_surviving; math.inf when not closable
    # Shed + ride-through
    shed_required_mw: float              # max(0, deficit − headroom_surviving)
    ride_through_s: float                # soc_mwh × 3600 / deficit; math.inf when no deficit
    # Three-state verdict
    state: ContingencyState
    # §7.5 header-strip figures
    dispatchable_mw: float               # online turbine rated + anchor-adj BESS bridging
    renewable_mw: float                  # solar output — displayed separately, never in coverage arithmetic


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
# Kubernetes demand metrics (per-tick snapshot from KubeDemandAgent)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KubeMetrics:
    """Per-tick snapshot of the Kubernetes gang-admission simulator state.

    Carried on TickResult.kube_metrics when kube_config is active for the run.
    None on TickResult when the standard scripted workload path is used.

    utilization    — admitted_nodes / max_nodes (or min_nodes/max_nodes when idle).
    node_count     — max(min_nodes, admitted_nodes): total nodes powering compute.
    power_cap_active — True when grid headroom < headroom_threshold_mw.
    headroom_mw    — turbine_headroom + bess_headroom from the previous tick.
    active_jobs    — number of gang-admitted workloads currently running.
    admitted_nodes — sum of node_count across all active jobs (before min_nodes floor).
    """
    utilization: float       # [0, 1] — total_nodes / max_nodes
    node_count: int          # max(min_nodes, admitted_nodes)
    power_cap_active: bool   # True when headroom < headroom_threshold_mw
    headroom_mw: float       # MW headroom at last grid reading
    active_jobs: int         # count of running gang-admitted workloads
    admitted_nodes: int      # sum of node_count across active jobs (pre-floor)


# ---------------------------------------------------------------------------
# Tick output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TickResult:
    """One row of RunTimeseries (functional spec Section 6.5). This is
    the object that flows: evaluate_tick() -> persistence -> WebSocket
    broadcast, per Design Spec Section 4.2/4.4.

    frozen=True: TickResult is a value object — once emitted by evaluate_tick()
    it must never be mutated in place.  The control plane (run_manager._drive)
    may enrich a fresh instance with thermal fields via dataclasses.replace()
    BEFORE appending it to tick_history; after that the object is shared between
    the main coroutine and advisory worker threads and must not change.
    This makes the invariant structural rather than reasoning-based."""
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
    # Step 10: §8.1 pre-staging — MW of gap reduced by Phase 0 shiftable load.
    # 0.0 when no pre-staging engine is configured or gap is 0.
    pre_staging_shift_mw: float = 0.0
    # Step 10: §23.2 curtailment proposals — tuple of tier name strings for
    # every tier the curtailment ladder proposed this tick (empty = no proposal).
    # Proposals do not guarantee execution: C/D require human confirmation (TC-42).
    curtailment_proposal_tiers: tuple[str, ...] = field(default_factory=tuple)
    # Step 11: §28 PMS / SCADA state for this tick.
    # pms_fast_shed_active: True when PMS fast shed is in effect this tick.
    #   GridSignal must not curtail while this is True (TC-64).
    pms_fast_shed_active: bool = False
    # pms_order_conflict: non-None when GridSignal's curtailment order disagrees
    #   with the PMS shed priority order (TC-65 commissioning defect).
    pms_order_conflict: Optional[str] = None
    # scada_commands_issued: count of commands issued to the egress boundary
    #   this tick (informational; TC-68 inspects the egress log directly).
    scada_commands_issued: int = 0
    # W1c — thermal headroom fields.
    # Stamped by the run loop immediately after _update_thermal_state() and
    # BEFORE sink.append() / broadcast() so the live WebSocket payload and
    # the stored timeseries carry live thermal data (Cell 3).
    # Mirrors the computation in GET /thermal; guaranteed to agree because
    # both use the same _approach_rate_mw_s / _rated_cooling_mw ctx fields.
    rated_cooling_mw:   float = 0.0      # rated cooling capacity (factory config)
    absorbable_mw:      float = 0.0      # max(0, rated − current) MW of headroom
    time_to_limit_s:    float = 86400.0  # s until headroom reaches 0 (86400 = ∞)
    approach_rate_mw_s: float = 0.0      # MW/s approach rate (+ = rising load)
    # AE2 — per-unit turbine config stamped from RunContext.turbine_unit_specs.
    # Constant across ticks for a given run; carried on every TickResult so the
    # fleet modal can read unit count, rated MW, and effective ramp per unit
    # without a separate API call.  Each element is a plain dict:
    #   {"asset_id": str, "rated_mw": float, "r_asset_mw_per_s": float}
    # tuple (not list) because TickResult is frozen=True; tuple is immutable.
    turbine_units: tuple = field(default_factory=tuple)
    # Kubernetes demand agent metrics — non-None when kube_config is active.
    # None on every tick when the standard scripted workload path is used,
    # so existing tests and displays that don't reference this field are unaffected.
    kube_metrics: Optional[KubeMetrics] = None
    # Solar weather metadata — stamped from RunContext.solar_weather / solar_conditions
    # at every tick (same pattern as turbine_units).  Empty strings when solar is not
    # present in the scenario or the run was started via the direct job-id path.
    solar_weather:    str = ""
    solar_conditions: str = ""
    # GT-1: §7.4 contingency coverage — computed each tick after dispatch
    # arbitration.  None only when the tick is produced by a code path that
    # predates the contingency engine (should not occur in normal operation).
    contingency_coverage: Optional[ContingencyCoverage] = None
