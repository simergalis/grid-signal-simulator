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

import logging as _logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# site_parameters: runtime catalogue loader (GS-DES-CFG-001 v1.0).
# Imported here so SiteConfig field defaults read from gridsignal_parameters.json
# rather than being hardcoded literals.  The import is safe: site_parameters.py
# only imports stdlib modules and has no core/ dependencies.
from core import site_parameters as _sp


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
    # TC-84: Turbine trip event — forces the named generating unit offline
    # immediately so the gen-trip indicator on the operator dashboard transitions
    # state (COVERED → COVERED_WITH_SHED → CANNOT_CARRY) during a live run.
    # The tripped asset_id is carried in WorkloadSignal.job_id (no GPU or job
    # state is touched; apply_workload_signal() early-returns after the trip).
    UNIT_TRIP = "unit_trip"


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
    # Two-phase thermal SoC model (§8.1 load-shifting, not curtailment).
    # thermal_soc_initial_mwh: pre-charged thermal energy at run start (MWh).
    #   0.0 = no stored energy; engine must charge before it can discharge.
    # eta: charge-phase efficiency (dimensionless, 0 < η ≤ 1).
    #   Energy stored = P_precool × dt/3600 × eta.
    # CHOSEN values — no measured basis (PROTO-10).
    thermal_soc_initial_mwh: float = 0.0   # CHOSEN (PROTO-10)
    eta: float = 0.9                        # CHOSEN (PROTO-10)


# ---------------------------------------------------------------------------
# Asset configuration (Design Spec Section 6 / functional spec Section 8.1)
# ---------------------------------------------------------------------------

@dataclass
class SiteConfig:
    site_id: str
    # A2 / Task #200: site nominal grid frequency.
    # Default 60.0 — primary deployment site is WECC/SDG&E territory (San Diego).
    # Override explicitly for non-WECC sites: 50 Hz = EU / APAC / NZ grids.
    #
    # Provenance: CHOSEN at 60.0 for the demo site; physically constrained by
    # the North American Eastern and Western Interconnections.  EU/APAC sites
    # must set this field to 50.0 at construction — the default does not apply.
    #
    # The API schema (api/schemas.py) and scenario factory (runtime/scenario_factory.py)
    # both carry the same 60.0 default independently.  All three default sites must
    # stay in sync; change here and at the other two if the primary site moves.
    #
    # Impact: df/dt = f₀ × ΔP / (2H × S_base) scales linearly with this value.
    # A 20% change (50 → 60 Hz) makes every frequency excursion 20% faster.
    frequency_nominal_hz: float = 60.0   # WECC/SDG&E default — see A2 above
    # power_factor: rated pf of the synchronous generator fleet (dimensionless).
    # MW ≠ MVA; pf=1 silently underestimates S_base and overestimates df/dt.
    # Typical gas turbine: 0.85 (CHOSEN — calibrate against nameplate or vendor data).
    # Default 0.85 required here for Python dataclass field-ordering: once
    # frequency_nominal_hz above carries a default, every subsequent field must also
    # have one.  The API schema (api/schemas.py) and scenario factory already default
    # to 0.85; this makes SiteConfig consistent.  Operator-visible via ParameterModal.
    power_factor: float = 0.85        # CHOSEN — typical gas turbine; see comment above
    pue_base: float = _sp.value("pue_base")
    # IT-side overhead: power conversion, distribution, UPS losses, lighting.
    # Excludes cooling (§4.1).  PROPOSED_HERE; range [1.01, 1.10].
    # Source: gridsignal_parameters.json PARAM-06.
    alpha_max: float = _sp.value("alpha_max")             # PROPOSED_HERE §8, 0.10-0.30
    tau_seconds: float = _sp.value("tau")                 # PROPOSED_HERE §8; key "tau" in catalogue
    dt_thermal_seconds: float = _sp.value("dt_thermal")   # PROPOSED_HERE §8-9; key "dt_thermal"
    uncalibrated: bool = True                              # source spec Section 17.3
    # Scenario-scripted DQ tag injection windows.  Each tuple is
    # (start_s, end_s, tag_str) where tag_str is a DataQualityTag value.
    # At every tick where start_s <= sim_time < end_s the named tag is added
    # to the confidence band computation and the low-confidence interlock.
    # Default empty — no injected flags in production scenarios.
    dq_inject_events: list[tuple[float, float, str]] = field(default_factory=list)

    # ── Confidence band for reserve check (gridsignal_parameters.json §2.5) ──
    # INV-2: reserve check evaluates the band, never the point estimate.
    # band_enabled=False preserves backward-compat for all existing tests and
    # seeded scenarios.  ScenarioSpec sets band_enabled=True when
    # band_pct_calibrated > 0 (backward-compat inference in scenario_factory).
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
    band_enabled: bool = False
    # False = point-estimate check (backward-compat).
    band_pct_calibrated: float = _sp.value("band_pct_calibrated")
    # ±% of peak_shortfall; only used when band_enabled=True.
    band_mult_uncalibrated: float = _sp.value("band_mult_uncalibrated")
    # multiplier for uncalibrated site.
    band_mult_unmapped_hw: float = _sp.value("band_mult_unmapped_hw")
    # multiplier for unmapped hardware.

    def reserve_band_upper(self, is_unmapped_hw: bool = False) -> float:
        """Band fraction for the reserve check (§2.5, INV-2).

        alert ⟺  peak_shortfall × (1 + reserve_band_upper()) > P_bridge_avail

        Returns 0.0 when band_enabled is False (backward-compatible default).
        Calibrated site: base = band_pct_calibrated / 100.
        Uncalibrated:    base × band_mult_uncalibrated.
        Unmapped HW:     multiply further by band_mult_unmapped_hw.
        """
        if not self.band_enabled:
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

    # Phase 11.2 — workload signal staleness threshold.
    # A WorkloadSignal is considered stale when none has arrived within this many
    # seconds for an active job.  Default 30 s (CHOSEN, no measured basis).
    workload_signal_stale_s: float = _sp.value("workload_signal_stale_s")

    # Phase 11.3 — swing-equation parameters for islanded frequency tracking.
    # These are used to compute df/dt from balance_residual_mw each tick.
    #
    # inertia_constant_s (H): combined inertia of all synchronous generators,
    #   in seconds.  Default 4.0 s (typical medium diesel/gas island plant).
    #   CHOSEN — no measured basis; calibrate against design partner specs.
    #
    #   OPEN PARAMETER (Phase 13.2 addendum):
    #   H sets the entire frequency-response timescale: the electromechanical
    #   time constant is ~2H/droop, so every derived frequency criterion —
    #   trip threshold crossing time, droop settle time, stability margin —
    #   scales directly with this value.  It belongs on the open-parameters
    #   list alongside r_asset_mw_per_s (TurbineConfig, no measured basis,
    #   Section 7.1 MVP default) and bess_tau_s (not yet a first-class field
    #   but implied by charge/discharge dynamics).  All three require vendor
    #   or measured data before any derived frequency number is quoted externally.
    #
    # frequency_nominal_hz: see field declaration at top of dataclass (required).
    # governor_droop: per-unit frequency deviation that produces 100% governor
    #   response.  Default 4% (0.04) — typical gas turbine governor setting.
    #   CHOSEN — no measured basis; read but not yet wired to control path
    #   (Phase 13.3b will close this).
    inertia_constant_s:    float = _sp.value("inertia_constant_s")  # CHOSEN — read from catalogue
    governor_droop:        float = _sp.value("governor_droop")       # CHOSEN — read from catalogue

    # ── Phase 2A–5: Frequency-dynamics catalogue fields (DR-2026-08-08-FREQ) ───
    # anchor_mode: "vsm" (virtual synchronous machine) — when zero synchronous machines
    #   are on-bus, grid-forming BESS provides virtual inertia via vsm_inertia_constant_s.
    #   DR-2026-08-08-FREQ; replaces the old frozen-frequency (df/dt=0) branch.
    anchor_mode: str = _sp.value("anchor_mode")  # DR-2026-08-08-FREQ — "vsm"
    # vsm_inertia_constant_s: virtual H for the GF-BESS in zero-machine phase.
    #   PROVISIONAL-UNMEASURED — 2.0 s. Blocks demo export when used.
    vsm_inertia_constant_s: float = _sp.value("vsm_inertia_constant_s")  # PROVISIONAL-UNMEASURED
    # dynamic_step_s: swing-equation sub-step (0.01 s). DR-2026-08-08-FREQ.
    #   Must satisfy: dynamic_step_s ≤ min(protection_delay) / 10 = 0.015 s.
    dynamic_step_s: float = _sp.value("dynamic_step_s")  # DR-2026-08-08-FREQ — 0.01 s
    # fixed_speed_cooling_fraction: fraction of cooling load on fixed-speed motors.
    #   PROVISIONAL-UNMEASURED — 0.30. Used by D_eff damping term.
    fixed_speed_cooling_fraction: float = _sp.value("fixed_speed_cooling_fraction")  # PROVISIONAL-UNMEASURED
    # d_motor: motor damping coefficient (pu/pu). Affinity-law basis.
    #   PROVISIONAL-UNMEASURED — 2.5. D_eff = cooling_frac × fixed_speed_frac × d_motor.
    d_motor: float = _sp.value("d_motor")  # PROVISIONAL-UNMEASURED — 2.5 pu/pu
    # valve_actuation_tc_s / fuel_to_power_tc_s: governor cascade time constants.
    #   PROVISIONAL-UNMEASURED. Fleet-level defaults; per-unit overrides on TurbineConfig.
    valve_actuation_tc_s: float = _sp.value("valve_actuation_tc_s")      # PROVISIONAL-UNMEASURED — 0.2 s
    fuel_to_power_tc_s:   float = _sp.value("fuel_to_power_tc_s")        # PROVISIONAL-UNMEASURED — 1.0 s
    # max_instantaneous_load_step_mw: governor output rate limit per sub-step.
    #   PROVISIONAL-UNMEASURED — 2.25 MW. Fleet-level default.
    max_instantaneous_load_step_mw: float = _sp.value("max_instantaneous_load_step_mw")  # PROVISIONAL-UNMEASURED
    # ufls_stages: 3-stage UFLS relay definitions (threshold_hz, delay_s, block_fraction).
    #   PROVISIONAL-UNMEASURED. OPT-IN: defaults to [] (disabled). Must be explicitly
    #   populated per-scenario via ScenarioSpec.ufls_stages to enable protection.
    #   Rationale: the 59.3/58.9/58.5 Hz thresholds (only 0.7–1.5 Hz below 60 Hz nominal)
    #   are too aggressive for general-purpose runs; they cause spurious UFLS trips in
    #   scenarios not designed for protection testing. Enable explicitly when needed.
    ufls_stages: list = field(default_factory=list)  # PROVISIONAL-UNMEASURED — opt-in
    # relay_81u_threshold_hz / relay_81u_delay_s: islanded 81U under-frequency protection.
    #   PROVISIONAL-UNMEASURED. OPT-IN: threshold defaults to None (disabled).
    #   Set explicitly in ScenarioSpec to enable islanded 81U protection.
    relay_81u_threshold_hz: float | None = None     # PROVISIONAL-UNMEASURED — opt-in; 57.5 Hz when enabled
    relay_81u_delay_s:      float = _sp.value("relay_81u_delay_s")  # PROVISIONAL-UNMEASURED — 0.10 s

    # §FP: Frequency protection thresholds (islanded mode only; read each tick, no literals).
    #
    # Five thresholds form two asymmetric barriers around f_nominal.  At 60 Hz (SDG&E/WECC):
    #
    # Standard reference: IEEE 1547-2018 §6.5.1, "Frequency trip settings for 60 Hz EPS".
    # That section covers DER interconnection; for islanded operation IEEE 1547.4 / site
    # relay coordination may apply different (tighter) values.  Flag all five for operator
    # confirmation against the SDG&E Rule 21 interconnection agreement and plant relay settings.
    #
    # Trip times from IEEE 1547-2018 §6.5.1 Category I (default settings):
    #   UF mandatory (< island_collapse_hz): ≤ 0.16 s clearing — hard trip.
    #   UF adjustable (ufls_stage1_hz):      ≤ 2.0 s clearing  — CHOSEN within adjustable range.
    #   OF mandatory (> of_trip_hz):         ≤ 0.16 s clearing — hard trip.
    # The simulator freezes frequency at the trip threshold and sets island_collapsed=True.
    # ufls_stage1_hz triggers a warning only (not yet wired to curtailment ladder — see §FP report).
    #
    # None = protection DISABLED for that threshold.  The protection layer only
    # fires when the operator explicitly provides a value in the scenario spec.
    # This ensures all pre-existing frequency tests (which exercise large swings
    # for physics verification) are unaffected by the protection layer.
    #
    # RECOMMENDED values for a 60 Hz (SDG&E/WECC) site (IEEE 1547-2018 §6.5.1):
    #   uf_warning_hz      = 59.5    # lower boundary of normal operation band
    #   ufls_stage1_hz     = 58.5    # CHOSEN within adjustable range 57.0–59.5 Hz
    #   island_collapse_hz = 57.0    # Cat I mandatory UF trip (≤ 0.16 s clearing)
    #   of_warning_hz      = 60.5    # upper boundary of normal operation band
    #   of_trip_hz         = 62.0    # Cat I mandatory OF trip (≤ 0.16 s clearing)
    # Set all five explicitly in the scenario spec; do not rely on defaults.
    uf_warning_hz:      Optional[float] = None  # None = disabled; set explicitly (see above)
    ufls_stage1_hz:     Optional[float] = None  # None = disabled; set explicitly (see above)
    island_collapse_hz: Optional[float] = None  # None = disabled; set explicitly (see above)
    of_warning_hz:      Optional[float] = None  # None = disabled; set explicitly (see above)
    of_trip_hz:         Optional[float] = None  # None = disabled; set explicitly (see above)

    # load_model_bias_mw: deliberate load-estimation offset for test injection (B1).
    #   Default 0.0 — the dispatch engine's load estimate matches the metered load.
    #   When non-zero, the difference is reported as model_error_mw in TickResult
    #   WITHOUT flowing into p_dispatch_required, bess_setpoint, or frequency_forcing.
    #   Represents injected PUE miscalibration or load-accounting drift; test-only.
    load_model_bias_mw:    float = 0.0


class TurbineState(str, Enum):
    """Phase C canonical turbine unit states (five states).

    UNLOADING is the Phase C controlled-stop state: on-bus, producing, tracking
    down through the loading layer.  The full unload sequence (R5 enforcement,
    MSL dwell, breaker open) is Phase E.

    RAMPING, AT_TARGET, and TRANSITIONAL have been removed in Phase C.
    Use from_persisted() to load states from storage — it applies the Phase C
    migration map and fails fast on unrecognised values.
    """
    OFFLINE        = "offline"        # not producing; no fault; ready to start
    OUT_OF_SERVICE = "out_of_service" # excluded: operator | fault | maintenance
    STARTING       = "starting"       # start sequence running; output_mw = 0
    UNLOADING      = "unloading"      # on-bus; tracking down to MSL; Phase C+
    SYNCHRONISED   = "synchronised"   # on-bus; continuous output; loading-layer-managed

    @classmethod
    def from_persisted(cls, value: str) -> "TurbineState":
        """Deserialise a persisted state string, applying the Phase C migration map.

        Migration (Phase C):
            ramping      → synchronised  (legacy ramp-to-target alias)
            at_target    → synchronised  (legacy at-setpoint alias)
            transitional → offline       (transient state; never produced real output)

        Raises ValueError for any unrecognised value — a silently defaulted state
        would credit a unit toward reserve on grounds nobody chose.
        """
        _MIGRATION: dict[str, "TurbineState"] = {
            "ramping":      cls.SYNCHRONISED,
            "at_target":    cls.SYNCHRONISED,
            "transitional": cls.OFFLINE,
        }
        if value in _MIGRATION:
            return _MIGRATION[value]
        try:
            return cls(value)
        except ValueError:
            raise ValueError(
                f"TurbineState.from_persisted: unrecognised persisted state "
                f"{value!r}. No default applied — fix the persisted data or "
                f"add an explicit migration mapping."
            ) from None


class ThermalState(str, Enum):
    """Thermal classification that determines start duration (§ Phase 2).

    Inferred from time offline since last synchronisation.  All thresholds
    from TurbineConfig — no literals in the state machine.
    """
    COLD = "cold"
    WARM = "warm"
    HOT  = "hot"


@dataclass(frozen=True)
class UnitAvailability:
    """Phase 2 boundary object — the interface a PMS would populate at a real site.

    Provides an import-free seam between the turbine asset model and consumers
    (reserve check, N-1 tile, commitment logic).  Build via
    TurbineModule.unit_availability(); do not read TurbineModule fields directly
    outside asset_modules.py.

    r_asset_effective_mw_per_s: re-rated if applicable (TC-58); equal to
        TurbineConfig.r_asset_mw_per_s in the current build.
    time_to_online_s: 0.0 when SYNCHRONISED (including RAMPING/AT_TARGET aliases);
        None when OUT_OF_SERVICE (no planned return to service).
    out_of_service_reason: None unless OUT_OF_SERVICE.
    """
    unit_id: str
    state: TurbineState
    output_mw: float
    rated_mw: float
    msl_mw: float
    r_asset_effective_mw_per_s: float
    time_to_online_s: Optional[float]    # 0.0 = SYNCHRONISED; None = OUT_OF_SERVICE
    out_of_service_reason: Optional[str] # None unless OUT_OF_SERVICE
    hot_standby: bool = False            # True → excluded from ramp credit and dispatch

    @property
    def is_starting(self) -> bool:
        """True when the unit is in the STARTING state (non-zero startup countdown)."""
        return self.state == TurbineState.STARTING


@dataclass
class TurbineConfig:
    asset_id: str
    r_asset_mw_per_s: float = _sp.value("r_asset_mw_per_s")  # CHOSEN — read from catalogue
    rated_mw: float = 10.0
    # hot_standby: True when this unit is commissioned but not synchronized to the
    # bus.  A hot-standby unit is ready to start but contributes zero to the
    # dispatch fleet and zero to contingency ramp capability (§7.4 / TC-83).
    # Its start time is a separate quantity and must never be folded into a ramp
    # rate.  False = default (synchronized online).
    hot_standby: bool = False
    # initial_thermal_state: thermal classification at t=0 of the run.
    # Determines which start-duration path (hot/warm/cold) is used on the FIRST
    # command_start() call.  Subsequent starts use the elapsed-time classifier.
    # CHOSEN default COLD — conservative; scenarios that want a pre-warmed fleet
    # set this explicitly per unit in TurbineUnitSpec.thermal_state.
    initial_thermal_state: ThermalState = ThermalState.COLD
    # R4–R6 operational constraints (Phase 13.5).  All CHOSEN (PROTO-R4); no
    # measured basis.  A production deployment should replace these with
    # OEM-specified values for the installed frame class.
    #
    # p_min_stable_frac — minimum stable load as a fraction of rated_mw.
    #   Dispatch commands below p_min_stable_frac × rated_mw are clamped up
    #   to this floor while the turbine is running.  Prevents operation in the
    #   lean-extinction regime that causes combustion instability.
    #   0.0 = constraint disabled (default — backward-compatible with scenarios
    #   that do not model combustion stability limits).  Set to 0.40 in
    #   demo-20mw (PW-1 / §15: 2.8 MW floor on 7 MW units, CHOSEN).
    # Phase E closeout Item 2 / §7.1.3.6: read p_min_stable_frac from catalogue
    #   so the field carries the CHOSEN production default (0.40) without a
    #   code literal that Guard D1 would flag as a drift.  The catalogue key
    #   is "p_min_stable_frac" (unified after closeout Item 2 rename).
    #   0.0 disables the MSL floor (pass explicitly for tests that do not model
    #   combustion stability limits).
    p_min_stable_frac: float = _sp.value("p_min_stable_frac")
    # t_min_run_s — minimum continuous run time (seconds) before a controlled
    #   stop is permitted.  When min_run_enabled=True, a stop command issued
    #   before this time elapses is deferred via R5 in command_stop().
    #   Read from catalogue so the field carries the CHOSEN production default
    #   (1800 s) without a code literal that Guard D1 would flag as a drift.
    t_min_run_s: float = _sp.value("t_min_run_s")
    # min_run_enabled — Phase E closeout Item 1 / D-03 pattern.
    #   True  = R5 guard active; command_stop() defers until t_min_run_s elapses.
    #   False = R5 guard disabled (backward-compat default for unit tests that
    #           create TurbineConfig() directly without going through the factory).
    #   Scenario factory always sets True for production seeded scenarios.
    # min_run_enabled — Phase E closeout Item 1 / D-03 pattern.
    #   True  = R5 guard active; command_stop() defers until t_min_run_s elapses.
    #   False = R5 guard disabled.
    #   DEFAULT True (§GS_prompt_modal_with_closeout): every config carries the
    #   physical constraint by default.  A test needing the constraint off must
    #   say so explicitly — that is the point of an explicit flag.
    min_run_enabled: bool = True
    # t_min_down_s — minimum cooling/rest period (seconds) between a controlled
    #   stop and the next permitted restart.  When min_down_enabled=True, a start
    #   command during the cooling window is silently dropped via R6.
    #   Read from catalogue so the field carries the CHOSEN production default
    #   (900 s) without a code literal that Guard D1 would flag as a drift.
    t_min_down_s: float = _sp.value("t_min_down_s")
    # min_down_enabled — Phase E closeout Item 1 / D-03 pattern.
    #   True  = R6 guard active; command_start() defers until t_min_down_s elapses.
    #   False = R6 guard disabled.
    #   DEFAULT True: same reasoning as min_run_enabled above.
    min_down_enabled: bool = True
    # gt_mode — per-unit gas turbine frame class.
    #   "frame" = large heavy-duty frame (slow ramp, high inertia).
    #   "aero"  = aeroderivative unit (fast ramp, lower inertia).
    gt_mode: str = "frame"
    # ── Phase 2: start durations — from config, no literals in state machine ─
    # cold_start_s: time for a COLD-start unit to reach SYNCHRONISED.
    #   TC-80 implies 900 s.  CHOSEN — no measured OEM basis.
    cold_start_s: float = _sp.value("cold_start_s")
    # warm_start_s: time for a WARM-start unit to reach SYNCHRONISED.
    #   CHOSEN — engineering placeholder; OEM data required.
    warm_start_s: float = _sp.value("warm_start_s")
    # hot_start_s: time for a HOT-start unit to reach SYNCHRONISED.
    #   CHOSEN — 300 s (5 min); OEM data required.
    #   Phase D (D-08): raised from 60 s to 300 s — a frame machine cannot
    #   synchronise in a minute; 60 s was an unrealistic bypass.
    hot_start_s: float = _sp.value("hot_start_s")
    # Thermal classification thresholds (time offline since last synchronisation).
    # hot_threshold_s: elapsed ≤ this → HOT start.
    #   CHOSEN — 1 h; OEM calibration required.
    hot_threshold_s: float = _sp.value("hot_threshold_s")
    # warm_threshold_s: hot_threshold_s < elapsed ≤ this → WARM; above → COLD.
    #   CHOSEN — 4 h; OEM calibration required.
    warm_threshold_s: float = _sp.value("warm_threshold_s")
    # unload_tail_s: settling dwell (seconds) from levelled_off True to breaker open,
    #   and also the minimum settling interval after each breaker open before the next
    #   unit may enter UNLOADING (sequential-stop guard, Item 6).
    #   CHOSEN — 60 s.  Calibrate against OEM breaker and droop-response data.
    unload_tail_s: float = _sp.value("unload_tail_s")
    # levelled_off_tol_mw: absolute output tolerance (MW) used to detect that an
    #   UNLOADING unit has reached its MSL setpoint.  When |output − msl| < tol the
    #   levelled_off predicate is True and the unload_tail_s dwell clock starts.
    #   Must be < r_asset_mw_per_s × dt_seconds (1.0 MW at r=0.2, dt=5) so the
    #   predicate does not fire prematurely mid-descent.
    #   CHOSEN — 0.05 MW (50 kW).  PROTO-23.
    levelled_off_tol_mw: float = _sp.value("levelled_off_tol_mw")

    # ── Phase 2B: Per-unit turbine physics fields (DR-2026-08-08-FREQ) ────────
    # These default to the fleet-level catalogue values and can be overridden
    # per-unit in the scenario spec (TurbineUnitSpec) for heterogeneous fleets.
    #
    # power_factor: per-unit pf for MVA base computation: S_i = rated_mw_i / pf_i.
    #   Default matches SiteConfig.power_factor (0.85). CHOSEN.
    power_factor: float = _sp.value("power_factor_turbine")  # CHOSEN — 0.85
    # inertia_constant_s: per-unit H for H_aggregate computation.
    #   Default from catalogue inertia_constant_s (same as SiteConfig fleet H).
    inertia_constant_s: float = _sp.value("inertia_constant_s")  # CHOSEN
    # droop_r: per-unit governor droop (pu/pu). Default 0.04 (= governor_droop).
    droop_r: float = _sp.value("droop_r")  # CHOSEN — 0.04 pu/pu
    # valve_actuation_tc_s / fuel_to_power_tc_s: governor cascade time constants.
    #   PROVISIONAL-UNMEASURED per unit; default matches SiteConfig fleet value.
    valve_actuation_tc_s: float = _sp.value("valve_actuation_tc_s")  # PROVISIONAL-UNMEASURED — 0.2 s
    fuel_to_power_tc_s:   float = _sp.value("fuel_to_power_tc_s")    # PROVISIONAL-UNMEASURED — 1.0 s
    # max_instantaneous_load_step_mw: governor output rate limit per sub-step.
    #   PROVISIONAL-UNMEASURED per unit; default matches SiteConfig fleet value.
    max_instantaneous_load_step_mw: float = _sp.value("max_instantaneous_load_step_mw")  # PROVISIONAL-UNMEASURED


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
    # GS-DES-CFG-001 §Phase-6 / Item-2: sourced from catalogue (locked bess_anchor_reserve_mw).
    p_anchor_reserve_mw: float = _sp.value("bess_anchor_reserve_mw")  # §7.1.2 / PROTO-9; CHOSEN
    # grid_forming: True when this unit is the designated grid-forming anchor
    #   for the islanded bus.  False = grid-following; P_anchor_reserve = 0.
    #   Default False: most units in a fleet are grid-following; the anchor role
    #   is an explicit designation, not a default assumption.
    grid_forming: bool = False

    # bess_response_tau_s: first-order lag time constant for BESS power output
    #   (seconds).  Models the inverter control-loop settling time between a
    #   new setpoint and the achieved output.
    #
    #   ASSET CLASS REFERENCE (Phase 13.3 BESS tau investigation):
    #   gridsignal_logger.py uses tau=0.3 s.  That figure is closer to a slow
    #   droop controller (~200–500 ms) than to the grid-forming or grid-following
    #   inverters this simulator targets (~10–100 ms).
    #
    #   Representative values by asset class:
    #     Grid-forming inverter (VSM / virtual inertia): ~20–50 ms → 0.02–0.05 s
    #     Grid-following inverter (PLL-based):           ~50–150 ms → 0.05–0.15 s
    #     Slow droop / legacy UPS BESS:                  ~200–500 ms → 0.2–0.5 s
    #
    #   Default 0.05 s (50 ms) — grid-forming inverter class.  This is an
    #   OPEN PARAMETER (no measured basis for this site); calibrate against
    #   design partner inverter specs.
    #
    #   Effect on coverage: shorter tau → faster delivery → higher coverage ratio
    #   for a given tick interval.  At dt=0.1 s, alpha = 1−exp(−0.1/tau):
    #     tau=0.05 s → alpha≈0.865 (87% of setpoint delivered per tick)
    #     tau=0.30 s → alpha≈0.283 (28% of setpoint delivered per tick)
    bess_response_tau_s: float = _sp.value("bess_response_tau_s")   # CHOSEN — read from catalogue

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
    # Approximate GPU node count that maps to shed_required_mw at current load density.
    # None when compute load is zero (no active jobs) or shed_required_mw is 0.
    # Computed in simulation_core.py after evaluate_contingency().
    shed_equivalent_nodes: Optional[int] = None


# ---------------------------------------------------------------------------
# Data quality / confidence tagging (source spec Section 5.1, 12, 17.2-17.3)
# ---------------------------------------------------------------------------

class DataQualityTag(str, Enum):
    UNMAPPED_HARDWARE = "unmapped_hardware"
    UNCALIBRATED_SITE = "uncalibrated_site"
    INVALID_PAYLOAD = "invalid_payload"
    STALE_PROFILE = "stale_profile"   # v2.5 §5.3: profile vintage is outdated
    # Phase 11.2 — workload signal feed quality flags.
    # Spec §12: no tag should express "normal quality" — flags must be silent
    # when the feed is healthy and loud when it is not.
    #
    # workload_signal_stale: No WorkloadSignal received within
    #   SiteConfig.workload_signal_stale_s (default 30 s) for an active job.
    #   Widening: +20% (CHOSEN, no measured basis — mirrors uncalibrated_site order
    #   of magnitude; stale data degrades forecast similarly to an uncalibrated site).
    #
    # workload_signal_absent: No WorkloadSignal ever received since run start, or
    #   the ingest connection is confirmed down.
    #   Widening: +50% (CHOSEN, no measured basis — absence is structurally worse
    #   than staleness; 50% chosen to force visible band even on small forecasts).
    #   Never-silent rule: when this flag is set, the engine must not present a
    #   confident point forecast; it falls back to the conservative measured-draw
    #   estimate and blocks autonomous curtailment (TC-43 pattern).
    WORKLOAD_SIGNAL_STALE  = "workload_signal_stale"
    WORKLOAD_SIGNAL_ABSENT = "workload_signal_absent"


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

    utilization       — admitted_nodes / max_nodes (or min_nodes/max_nodes when idle).
    node_count        — max(min_nodes, admitted_nodes): total nodes powering compute.
    power_cap_active  — True when grid headroom < headroom_threshold_mw.
    headroom_mw       — turbine_headroom + bess_headroom from the previous tick.
    active_jobs       — number of gang-admitted workloads currently running.
    admitted_nodes    — sum of node_count across active jobs (before min_nodes floor).
    arrivals_this_tick — new Poisson arrivals observed by the informer this tick.
    requeued_this_tick — admissions held by the power-cap and re-queued this tick.
                         A non-zero value every tick signals the §6.2 oscillation
                         pathology: the 5 s re-queue delay equals TICK_INTERVAL_SIM_SECONDS,
                         locking the cap toggle to the tick rate.
    """
    utilization: float       # [0, 1] — total_nodes / max_nodes
    node_count: int          # max(min_nodes, admitted_nodes)
    power_cap_active: bool   # True when headroom < headroom_threshold_mw
    headroom_mw: float       # MW headroom at last grid reading
    active_jobs: int         # count of running gang-admitted workloads
    admitted_nodes: int      # sum of node_count across active jobs (pre-floor)
    arrivals_this_tick: int  # new Poisson arrivals observed this tick
    requeued_this_tick: int  # admissions held by power-cap and re-queued this tick
    queued_jobs: int         # jobs currently sitting in the reorder buffer (observed, not yet admitted)
    queued_nodes: int        # sum of node_count across all jobs in the reorder buffer


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
    p_compute_demand_mw: float
    p_cooling_demand_mw: float
    p_demand_mw: float
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
    # GS-CHG-2026-08-08 successor Phase 1 — P_generation aggregate producer.
    # ONE producer in simulation_core; summing in the serialiser is prohibited (Spec 19).
    # Sign convention: BESS discharging → positive generation.
    #                  BESS charging    → negative generation (not load).
    #                  Grid import (PCC supplying the site) → positive.
    # In islanded mode grid_exchange_mw = 0, so p_generation_mw = local generation only.
    # Default 0.0 allows pre-existing test TickResult constructors that omit this kwarg
    # to remain valid; evaluate_tick() always sets it explicitly.
    p_generation_mw: float = 0.0

    # ── Phase 2A: Protection-provisional flag ─────────────────────────────────
    # True when this tick consulted any PROVISIONAL-UNMEASURED catalogue parameter
    # in the frequency-dynamics path.  Set True for all islanded ticks (D_eff uses
    # d_motor + fixed_speed_cooling_fraction, both PROVISIONAL-UNMEASURED).
    # Propagated run-wide via run_manager.set_run_provisional().
    # Blocks demo export when True (HTTP 403 via is_export_blocked()).
    protection_provisional: bool = False

    # ── Phase 6: Supply/served producers ──────────────────────────────────────
    # p_served_mw:   demand actually served = p_demand - cumulative_shed_mw.
    #   NOT a clamp min(p_demand, p_generation). Shed is discrete UFLS blocks.
    # p_unserved_mw: load shed so far = p_demand - p_served_mw = cumulative_shed_mw.
    # p_imbalance_mw: generation vs served = p_generation - p_served_mw.
    #   Positive: surplus (frequency rises); Negative: deficit (frequency falls).
    # Per-subsystem shares allocated proportional to demand fraction.
    # All None until Phase 6 wires producers; TC-87/TC-91 move xfail→pass.
    p_served_mw:           Optional[float] = None
    p_unserved_mw:         Optional[float] = None
    p_imbalance_mw:        Optional[float] = None
    p_compute_served_mw:   Optional[float] = None
    p_compute_unserved_mw: Optional[float] = None
    p_cooling_served_mw:   Optional[float] = None
    p_cooling_unserved_mw: Optional[float] = None

    # §INV-CURT: MW of solar output curtailed this tick by the frequency-response
    # inverter logic (islanded mode only).  Proportional curtailment between
    # of_warning_hz (0 %) and of_trip_hz (100 %).  0.0 in grid-connected mode,
    # when either threshold is None, or when frequency ≤ of_warning_hz.
    # p_renewable_mw is the POST-curtailment figure; this field carries the delta
    # so callers can reconstruct the pre-curtailment output when needed.
    p_renewable_curtailed_mw: float = 0.0
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
    # turbine_ramp_credit_mw: MW already covered by turbine ramp rate × dt_lead
    #   at the most recent STARTING or SOLAR_STEP staging event.
    #   0.0 when no staging event is in-flight (dt_lead_next_s == 0).
    #   When this equals delta_p_mw, peak_shortfall_mw is 0 and the reserve check
    #   passed without any BESS bridging ("Covered by turbine ramp").
    turbine_ramp_credit_mw: float = 0.0
    # peak_shortfall_mw: MW of the step that turbine ramp could NOT cover in time.
    #   max(0, delta_p_mw − turbine_ramp_credit_mw).
    #   0.0 when ramp credit fully covers the step or no staging is in-flight.
    #   The BESS must sustain this amount for gap_s to avoid an alert.
    peak_shortfall_mw: float = 0.0
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
    # Step 10: §8.1 pre-staging — two-phase load-shifting fields.
    # pre_staging_shift_mw: MW of gap REDUCED this tick (discharge phase).
    #   0.0 when no pre-staging engine is configured, gap is 0, or thermal_soc
    #   is exhausted.
    pre_staging_shift_mw: float = 0.0
    # pre_staging_precool_mw: MW of EXTRA load drawn this tick to charge the
    #   thermal store (charge phase).  0.0 during discharge or when BMS overrides.
    pre_staging_precool_mw: float = 0.0
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
    #   {"asset_id": str, "rated_mw": float, "r_asset_mw_per_s": float,
    #    "run_hours_h": float|None, "gt_mode": str, "hot_standby": bool,
    #    "breaker_closed": bool, "no_load_mw": float, "msl_mw": float}
    # tuple (not list) because TickResult is frozen=True; tuple is immutable.
    # Phase 0 adds breaker_closed, gt_mode, no_load_mw, msl_mw (§0.1/0.2/0.6).
    # Old dicts without these keys are backward-compatible via .get() with defaults.
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
    # PROTO-32-AMB: ambient temperature metadata — constant per run, stamped so the
    # Solar PV modal can surface the weather-to-cooling link without a separate endpoint.
    # 0.0 / 1.0 on runs without a solar forecast or direct job-id path.
    ambient_avg_c:       float = 0.0  # average dry-bulb °C across the run window
    ambient_alpha_scale: float = 1.0  # scale applied to site.alpha_max (>1 = hotter)
    # GT-1: §7.4 contingency coverage — computed each tick after dispatch
    # arbitration.  None only when the tick is produced by a code path that
    # predates the contingency engine (should not occur in normal operation).
    contingency_coverage: Optional[ContingencyCoverage] = None

    # W2a: advisory telemetry — stamped before broadcast from AgentRegistry.telemetry_snapshot().
    # None when no registry is active (LP-1 / tests that build TickResult without a registry).
    # Keys: backend, agents_armed, proposals_total, proposals_pending,
    #        last_proposal_sim_time, per_agent (dict[str, float]).
    advisory_telemetry: Optional[dict] = None

    # Phase 10: fabric model modal-view — six plant-plane fields derived from
    # the Network Fabric model.  None when FabricEngine is not wired (headless
    # tests, direct job-id path without a spec).
    # Keys mirror FabricModel.TickResult.modal_view():
    #   topology_nodes, congested_links, bandwidth_headroom_frac,
    #   packet_loss, retransmit_rate, control_latency_ms
    # Plus per-link utilisation vector (link_id → u) for the heat strip.
    fabric_modal: Optional[dict] = None

    # §7.4 solar bank telemetry — wired to the SLD tile sub-field.
    # p_expected_mw: what the array should produce at current measured POA
    #   (rated × cloud_factor — soiling excluded so faults surface as shortfall).
    #   None on the run-loop path — the run engine has no independent expectation
    #   model and routing p_renewable_mw here would create a tautology that makes
    #   fault detection (ratio >= 0.92 / >= 0.05 classifier) structurally unreachable.
    #   Use SolarSim.snapshot()["power"]["p_expected_mw"] for the honest figure.
    # banks_reporting: banks with live telemetry.
    #   None on the run-loop path — the run engine has no per-bank telemetry.
    #   Use SolarSim.snapshot()["power"]["banks_reporting"] for the honest figure.
    p_expected_mw:   Optional[float] = None
    banks_reporting: Optional[int]   = None

    # SD-1: site identity stamped on every tick so the WS header cannot diverge
    # from the physics when the server restarts under an open browser tab.
    # Defaults are 0.0 / "" — scenario_factory always stamps real values before t=0.
    # Geographic literals are prohibited here; they live only in site_config.py.
    site_lat:          float = 0.0
    site_lon:          float = 0.0
    site_utc_offset_h: float = 0.0
    site_name:         str   = ""

    # Stochastic step timing fields — wired when kube_config is active (Part 1/2 spec).
    # Defaults produce innocuous values for the scripted workload path; no existing
    # code paths or tests need to change.
    #
    # step_phase: fractional position within the current ML training step, ∈ [0, 1).
    #   0.0 at the instant a step fires; approaches 1.0 just before the next step.
    #   Used by the within-step power profile in GPUModule.per_job_compute_mw().
    # step_kind: "training" for normal steps; "checkpoint" for long-steps.
    #   "checkpoint" aligns with the existing CheckpointClassifier's vocabulary.
    step_phase: float = 0.0
    step_kind: str = "training"

    # ── Phase 11.1 — Forecast path correctness ───────────────────────────────
    # forecast_mw: queue-derived compute forecast using the Section 4 formula
    #   P_compute_forecast(t) = Σ_i Nodes_i(t) × kW_i × PUE_base / 1000
    # where the sum is over all ACTIVE jobs in all GPU modules and no ramp
    # multiplier is applied.  This is what the site WILL draw at full TDP;
    # it is sourced exclusively from WorkloadSignal data and is therefore
    # invariant to instantaneous measured draw fluctuations (F3 criterion).
    #
    # Single-source-of-truth guarantee: confidence.point_estimate_mw is set
    # to forecast_mw (or the conservative fallback when
    # WORKLOAD_SIGNAL_ABSENT is active).  The dashboard header and the
    # Forecast Quality panel MUST read the same field (F4 criterion).
    #
    # 0.0 at run start before any STARTING signal; grows as jobs are admitted.
    forecast_mw: float = 0.0

    # ── Phase 11.3 — Dispatch truthfulness ───────────────────────────────────
    # bess_setpoint_mw: what the dispatch arbitrator commanded the BESS fleet
    #   to produce this tick (the fleet_shortfall before SOC / power clipping).
    #   Differs from bess_output_mw when the fleet is SOC-limited or
    #   power-saturated.  That difference IS the balance residual from the
    #   BESS side.
    # gt_setpoint_mw: effective turbine dispatch setpoint this tick.
    #   Phase 13.3: equals the droop-adjusted demand (_p_dispatch_droop_mw),
    #   not the raw p_dispatch_required_mw.  The droop correction is zero at
    #   nominal frequency (within deadband ±0.02 Hz), so this field equals
    #   p_dispatch_required_mw in steady state.
    #   Differs from turbine_output_mw while turbines are still ramping.
    # balance_residual_mw: (turbine_output + bess_output + p_renewable) − p_total.
    #   DEPRECATED (Phase 13.2): read grid_exchange_mw + frequency_forcing_mw +
    #   asset_delivery_error_mw instead.  Retained for backward compatibility only.
    #   sum(grid_exchange_mw, frequency_forcing_mw, asset_delivery_error_mw) == balance_residual_mw.
    # frequency_hz: nominal system frequency (50 Hz) plus the deviation
    #   accumulated by the swing equation in islanded mode.
    #   In grid-connected mode: fixed at site.frequency_nominal_hz (grid is
    #   the frequency reference and the slack variable).
    # compute_inlet_temp_c: inlet air temperature at the compute racks, derived
    #   from the lagged cooling output (Phase 11.6 / Section 8 thermal model).
    #   Because the underlying cooling load already carries the dt_thermal lag,
    #   this field exhibits the high lag-1 autocorrelation (≥ 0.99 at 10 Hz)
    #   required by C3.  Default 20 °C (ambient baseline; rises with cooling load).
    bess_setpoint_mw:     float = 0.0
    gt_setpoint_mw:       float = 0.0
    # balance_residual_mw REMOVED — Branch B (Phase pre-work).
    # Was (turbine_output + bess_output + p_renewable) − p_total.
    # Deprecated since Phase 13.2; now deleted from the public API.
    # D4: sum(grid_exchange_mw + frequency_forcing_mw + asset_delivery_error_mw)
    #     == (_p_gen_mw − p_total_mw) is asserted inline in evaluate_tick().
    frequency_hz:         float = 0.0   # always overwritten by evaluate_tick; 0 = sentinel
    compute_inlet_temp_c: float = 20.0
    # ── Phase 13.2 — Balance decomposition ───────────────────────────────────
    # Three independently computed channels that sum to balance_residual_mw (D4).
    # balance_residual_mw is retained for backward compatibility; prefer these.
    #
    # grid_exchange_mw: power crossing the PCC.
    #   Grid-connected: _p_commanded − p_total (positive = site exports to grid).
    #   Islanded:       exactly 0.0 — PCC is open (D1).
    #   channel_source: derived (from commanded dispatch and total load; independent models).
    #
    # frequency_forcing_mw: dispatch-plan residual that presses rotating inertia.
    #   Islanded:       _p_commanded − p_total (positive = frequency rises).
    #   Grid-connected: exactly 0.0 — grid holds frequency (D2).
    #   channel_source: derived.
    #
    # asset_delivery_error_mw: physical shortfall — actual dispatchable delivery
    #   minus commanded dispatch (the droop-adjusted setpoint, Phase 13.3).
    #   = (turbine_output − gt_setpoint) + (bess_output − bess_setpoint).
    #   Positive = assets over-delivered; negative = under-delivered (e.g. BESS depleted).
    #   ~0 in steady state without injected faults in BOTH modes (D3).
    #
    #   Phase 13.3: this channel does NOT participate in the swing equation.
    #   Frequency is driven by frequency_forcing_mw only (the dispatch-plan
    #   mismatch).  A physical delivery fault (turbine or BESS under-delivery)
    #   appears here for diagnostics but does not directly alter df/dt.
    #   "Model error must not move frequency" — Phase 13.3 design principle.
    #
    #   Renamed from model_error_mw (Phase 13.2 addendum): the channel measures
    #   a physical shortfall; "model error" implied a residual/slack, which D5
    #   was written to prevent.
    #
    #   MODEL-ERROR LIMITATION (Phase 13.0 finding — documented, not eliminated):
    #   Genuine model error (e.g. PUE miscalibration, double-counted cooling load,
    #   unit-conversion bugs) is NOT separately observable in the current
    #   architecture: it would require an independent energy-accounting path.
    #   The rename was correct and necessary; it does not imply that the Phase 13.0
    #   overloading finding has been resolved.
    #
    #   D5: NOT computed as "balance_residual − grid_exchange − frequency_forcing"
    #   (that would make it the new slack variable). Uses setpoints + actual outputs
    #   exclusively — two independently modelled sources.
    #   channel_source: derived.
    grid_exchange_mw:          float = 0.0
    frequency_forcing_mw:      float = 0.0
    asset_delivery_error_mw:   float = 0.0
    # ── Phase 1b — Loading layer outputs ─────────────────────────────────────
    # sub_msl_surplus_mw: non-zero when P_allocated < Σ msl_i for SYNCHRONISED
    #   units.  Fleet holds at the floor; surplus enters frequency_forcing_mw
    #   (islanded → overfrequency) or is absorbed by grid (grid-connected).
    #   sub_msl_surplus_mw is a REPORTING field only — not a balance channel.
    #   0.0 in normal operation (feasible band: Σ msl ≤ P_allocated ≤ Σ rated).
    # ramp_capability_mw: fleet ramp capability over the runtime lead horizon
    #   (dt_lead_next_s from the dispatch arbitrator).
    #   Σ_{i∈A} min(r_i × H, rated_i − output_i) for SYNCHRONISED/RAMPING/AT_TARGET.
    #   STARTING units contribute zero (not on bus; starts fail — Task #198 item 2).
    #   Replaces the Phase 0.5 display-level cap in turbineFleet.ts (spec §1b).
    sub_msl_surplus_mw:        float = 0.0
    ramp_capability_mw:        float = 0.0
    # d4_balance_defect_mw: |Σ channels − balance_residual|.
    #   Zero in normal operation.  Non-zero signals a power-balance accounting
    #   error; the run continues and the field is logged (Task #198 item 5).
    #   Tests assert abs(d4_balance_defect_mw) < 1e-3.
    d4_balance_defect_mw:      float = 0.0

    # ── §FP: Frequency protection outcome ────────────────────────────────────
    # island_collapsed: True on the one tick where a protection threshold fires.
    #   The run manager broadcasts this tick and then halts the loop.  Every tick
    #   before the collapse carries island_collapsed=False; the tick after a collapse
    #   should never be evaluated (the loop stops), but evaluate_tick() guards
    #   against a second call by returning a frozen collapsed result.
    # collapse_reason: which threshold fired.
    #   "island_collapse_uf" — frequency fell through island_collapse_hz.
    #   "island_collapse_of" — frequency rose through of_trip_hz.
    #   "ufls_stage1"        — frequency fell through ufls_stage1_hz (warning tick only;
    #                          island_collapsed is False on a warning tick).
    #   "uf_warning" / "of_warning" — frequency crossed the normal-band edge (advisory).
    #   None when island_collapsed is False and no warning fired.
    # collapse_tick_index: tick_index at which the collapse was detected.
    #   None when island_collapsed is False.
    # collapse_frequency_hz: frequency frozen at the trip threshold.
    #   None when island_collapsed is False.
    island_collapsed:      bool          = False
    collapse_reason:       Optional[str] = None
    collapse_tick_index:   Optional[int] = None
    collapse_frequency_hz: Optional[float] = None

    # ── Phase 13.4 — Setpoint/actual split ────────────────────────────────────
    # model_error_mw: injected load-model bias (site.load_model_bias_mw).
    #   Default 0.0.  Observable as its own channel — does NOT flow into dispatch
    #   or frequency_forcing (B1: inject 1 MW → model_error_mw ≥ 0.9; BESS and
    #   frequency remain at their unperturbed values).
    model_error_mw:            float = 0.0
    # binding_constraint: "bess_power_saturated" when bess_setpoint_mw exceeds
    #   the BESS fleet's total rated_mw ceiling.  None in normal operation (B3).
    binding_constraint:        Optional[str] = None
    # ── Phase 4 (GS-DES-CFG-001): BESS fleet aggregates + thermal site params ─
    # Broadcast per tick so panels can display config nameplate figures without
    # reading ScenarioSpec (which is not on the wire).
    #
    # bess_rated_mw:   Σ config.rated_mw across all BESS units — fleet nameplate.
    #   NOT SOC-corrected.  The output BulletBar max must come from this field.
    #   Source: sim_state.bess_units[i].config.rated_mw for each i.
    # bess_usable_mwh: Σ config.usable_mwh across all BESS units — fleet nameplate
    #   usable energy from config.  Do NOT source from
    #   contingency_coverage.bess_usable_energy_mwh — that figure is altered by
    #   SOC-corruption injection (run_manager.py:787–788) and would put a fault
    #   value into a static spec row.
    # bess_unit_count: len(sim_state.bess_units) — lets a panel state whether an
    #   aggregate covers one unit or several, without broadcasting bess_units[].
    # dt_thermal_seconds: SiteConfig.dt_thermal_seconds — base thermal lag (s).
    #   The panel docstring must NOT derive this from a module-scope constant.
    # alpha_max:    SiteConfig.alpha_max — base cooling fraction; NOT multiplied
    #   by ambient_alpha_scale (already on wire).  Broadcast both so a panel can
    #   show base AND scaled value.  Labelling a × ambient_alpha_scale result as
    #   "α_max" would mislead during ambient stress scenarios.
    bess_rated_mw:      float = 0.0                   # FLEET: Σ config.rated_mw — config nameplate
    bess_usable_mwh:    float = 0.0                   # FLEET: Σ config.usable_mwh — config nameplate
    bess_unit_count:    int   = 0                     # count of BESS units in fleet
    dt_thermal_seconds: float = _sp.value("dt_thermal")  # base thermal lag; enriched from ctx.sim_state.site per tick
    alpha_max:          float = _sp.value("alpha_max")   # base α_max; enriched from ctx.sim_state.site per tick
    # GS-DES-CFG-001 §Phase-6: two new wire fields.
    # bess_anchor_reserve_mw: anchor reserve on the grid-forming BESS unit (MW).
    #   LAYERING: the broadcast value is the CONFIGURED value on the grid-forming unit
    #   (BessConfig.p_anchor_reserve_mw), NOT the catalogue default.  These legitimately
    #   differ when a scenario overrides p_anchor_reserve_mw — e.g. the San Diego demo
    #   broadcasts 2.0 MW while the catalogue locked value is 1.0 MW.  This is by design:
    #   the broadcast reports what the plant is actually configured with.
    #   Guard D cannot detect catalogue-vs-configured divergence — this is intended;
    #   the override is explicit and scenario-level.  Default (no grid-forming unit present):
    #   falls back to the catalogue default (bess_anchor_reserve_mw).
    # design_peak_load_mw: declared design peak site load (MW) — NOT observed run peak.
    #   = peak_it_load_mw + rated_cooling_mw; set by factory; 0.0 when uncomputable
    #   (spec-path with no workload_events) — frontend falls back to observed peak.
    bess_anchor_reserve_mw: float = _sp.value("bess_anchor_reserve_mw")  # anchor reserve (MW)
    design_peak_load_mw:    float = 0.0  # declared design peak; enriched from ctx._design_peak_load_mw

    # Phase E+: commitment engine last-decision summary — serialised for fleet modal.
    # Populated by simulation_core.evaluate_tick() each tick from _commit_decision.
    # Defaults produce innocuous values for tests that build TickResult directly.
    commitment_action: str = "hold"
    commitment_target_unit_id: Optional[str] = None
    commitment_reason: str = ""
    commitment_blocked_by: str = ""
    # committed_rated_mw: Σ rated_mw for SYNCHRONISED units this tick — SYNCHRONISED only.
    #   UNLOADING units are excluded: they are pinned at MSL with no upward headroom, so
    #   counting their nameplate overstates reserve precisely when the fleet is shrinking.
    #   Distinct from on_bus_output_mw (run_manager) which INCLUDES UNLOADING because
    #   UNLOADING units are breaker-closed and producing; the two fields answer different
    #   questions — reserve capacity vs produced output.
    # reserve_floor_mw:   p_demand + largest committed unit (N-1 floor from CommitmentDecision).
    #   NOT the decommit threshold; reads directly from CommitmentDecision.floor_mw.
    # fleet_utilisation:  p_demand / committed_rated_mw (0.0 when no committed units).
    committed_rated_mw:   float = 0.0
    reserve_floor_mw:     float = 0.0
    reserve_satisfied:    bool  = True
    fleet_utilisation:    float = 0.0
    # pending_start_unit_id: asset_id of the unit currently in STARTING; None when empty.
    pending_start_unit_id: Optional[str] = None
