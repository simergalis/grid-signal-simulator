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
    # Two-phase thermal SoC fields (§8.1 load-shifting, not curtailment).
    # thermal_soc_initial_mwh: pre-charged thermal energy at run start (MWh).
    #   0.0 = no stored energy; engine must charge before it can discharge.
    # eta: charge-phase efficiency (dimensionless, 0 < η ≤ 1).
    thermal_soc_initial_mwh: float = Field(default=0.0, ge=0.0)
    eta: float = Field(default=0.9, gt=0.0, le=1.0)


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
      "unit_trip"  — Force a generating unit offline immediately (TC-84).
                     job_id carries the turbine asset_id; node_count and
                     hardware_profile_id are ignored.
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
    # PW-3 / §15: explicit per-unit anchor-reserve override (MW).
    # When present, build_run_context_from_spec uses this value directly instead
    # of deriving from anchor_reserve_pct.  1.0 MW is the BessConfig default
    # (PROTO-9 / CHOSEN).  San Diego demo scenario uses 2.0 MW explicitly.
    p_anchor_reserve_mw: float = Field(default=1.0, ge=0.0)

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
    # Optional operating-hours counter for narrative / re-rating context.
    # None = not tracked (most scenarios).  When set, the fleet modal shows
    # the value in the RUN h column and names the unit in the degraded footnote.
    run_hours_h: Optional[float] = Field(default=None, ge=0)
    # hot_standby: True when this unit is commissioned but not synchronized.
    # Hot-standby units are excluded from dispatch staging and contribute zero
    # to contingency ramp capability (§7.4 / TC-83).  Default False.
    hot_standby: bool = False
    # PW-1 / §15: minimum stable load as a fraction of rated_mw.
    # 0.0 = disabled (default — backward-compat with existing scenarios).
    # Set to 0.40 on demo-20mw turbine units (2.8 MW floor on 7 MW units).
    # CHOSEN — OEM combustion-stability data required for calibration.
    p_min_stable_frac: float = Field(default=0.0, ge=0.0, le=1.0)


class StepTimingConfigSpec(BaseModel):
    """Wire-format mirror of core.step_config.StepTimingConfig.

    All defaults match the spec document (SPEC_DEFAULT).  Only override fields
    whose values differ from the default; the engine fills in the rest.
    """
    median_step_s: float = Field(default=0.70, gt=0.0, description="Median inter-step gap (s). SPEC_DEFAULT.")
    step_cv: float = Field(default=0.08, ge=0.0, le=1.0, description="Lognormal CV. SPEC_DEFAULT.")
    tau_drift_s: float = Field(default=300.0, gt=0.0, description="OU mean-reversion time (s). SPEC_DEFAULT.")
    sigma_drift: float = Field(default=0.03, ge=0.0, description="OU diffusion (dimensionless). SPEC_DEFAULT.")
    p_straggler: float = Field(default=0.02, ge=0.0, le=1.0, description="Straggler injection probability. SPEC_DEFAULT.")
    straggler_scale: float = Field(default=1.5, gt=0.0, description="Exponential straggler scale. SPEC_DEFAULT.")
    straggler_max: float = Field(default=10.0, gt=1.0, description="Hard cap on straggler multiplier. SPEC_DEFAULT.")
    ckpt_interval_steps: int = Field(default=400, ge=1, description="Steps between checkpoint long-steps. SPEC_DEFAULT.")
    ckpt_jitter_steps: int = Field(default=40, ge=0, description="±Uniform jitter on checkpoint interval. SPEC_DEFAULT.")
    ckpt_min_s: float = Field(default=5.0, gt=0.0, description="Checkpoint step minimum duration (s). SPEC_DEFAULT.")
    ckpt_max_s: float = Field(default=30.0, gt=0.0, description="Checkpoint step maximum duration (s). SPEC_DEFAULT.")


class LoadProfileConfigSpec(BaseModel):
    """Wire-format mirror of core.step_config.LoadProfileConfig.

    Controls the within-step compute load profile that makes step events
    physically present in compute_load_mw.  All defaults are SPEC_DEFAULT.
    """
    f_compute: float = Field(default=0.72, ge=0.0, le=1.0, description="Compute-phase fraction. SPEC_DEFAULT.")
    p_comm_ratio: float = Field(default=0.55, ge=0.0, le=1.0, description="Relative power during allreduce. SPEC_DEFAULT.")
    tau_gpu_s: float = Field(default=0.06, gt=0.0, description="GPU power transition lag (s). SPEC_DEFAULT.")
    phase_coherence: float = Field(default=0.85, ge=0.0, le=1.0, description="Fleet phase coherence. SPEC_DEFAULT.")
    noise_sigma_fraction: float = Field(default=0.005, ge=0.0, le=0.1, description="Noise sigma as fraction of base draw. CHOSEN.")


class KubeConfigSpec(BaseModel):
    """Kubernetes gang-admission demand simulator configuration.

    When present on a ScenarioSpec, the simulator replaces the scripted
    workload-event path with a discrete gang-admission simulator that models
    steps 1–2 of the Kubernetes-to-turbine path:

      1. OBSERVE:  Poisson-arrival jobs enter a 10-second reorder buffer,
         simulating an in-cluster informer watching Kueue/Volcano objects.
      2. MAP TO CONTRACT: Each admitted gang emits a WorkloadSignal with
         node_count and hardware_profile_id.  Steps 3–8 (P_compute formula,
         thermal lag, BESS arbitration, turbine ramp) run unchanged in the
         scheduler-agnostic core pipeline.

    dt_lead = 0 throughout — Kubernetes gives no advance notice to the grid.

    Use rng_seed for deterministic replay; rng_seed=None gives time-seeded variety.
    Activate stochastic step timing by supplying step_config; activate the
    within-step load profile by supplying load_config.
    """
    hardware_profile_id: str = "enterprise_8gpu_air"

    # Fleet sizing
    max_nodes: int = Field(default=1900, ge=1)
    min_nodes: int = Field(default=200, ge=1,
                           description="Idle-baseline nodes — cluster never fully drains")

    # Gang-admission arrival pattern (Poisson process)
    mean_interarrival_s: float = Field(
        default=60.0, ge=5.0, le=3600.0,
        description="Mean simulated seconds between successive gang admissions",
    )

    # Job size distribution (Gaussian, clipped)
    mean_job_nodes: int = Field(default=200, ge=1,
                                description="Mean gang size in nodes")
    job_node_std: float = Field(default=80.0, ge=0.0,
                                description="Std deviation of gang size")
    min_job_nodes: int = Field(default=50, ge=1,
                               description="Minimum nodes per admission")

    # Job duration distribution (exponential, clipped)
    mean_job_duration_s: float = Field(default=300.0, ge=10.0,
                                       description="Mean job duration in sim-seconds")
    min_job_duration_s: float = Field(default=30.0, ge=5.0,
                                      description="Minimum job duration in sim-seconds")

    # Reorder buffer and NTP jitter
    reorder_window_s: float = Field(
        default=10.0, ge=0.0, le=60.0,
        description="Events drain from buffer after this many sim-seconds",
    )
    ntp_jitter_s: float = Field(
        default=2.0, ge=0.0, le=10.0,
        description="±seconds of NTP jitter added to event timestamps",
    )

    # Power-cap threshold
    headroom_threshold_mw: float = Field(
        default=2.5, ge=0.0,
        description="Grid headroom below which new admissions are held",
    )

    rng_seed: Optional[int] = None

    # ── Stochastic step timing (spec Part 1) ──────────────────────────────────
    # None (default) = step scheduler off; period falls back to no step events.
    step_config: Optional[StepTimingConfigSpec] = None

    # ── Within-step load profile (spec Part 2) ───────────────────────────────
    # None (default) = no profile modulation; compute_load_mw is a pure ramp.
    load_config: Optional[LoadProfileConfigSpec] = None


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
    # A1 / Task #200: site nominal grid frequency.
    # San Diego (SDG&E territory) = 60 Hz; EU/APAC grids = 50 Hz.
    # Default 60.0 — primary deployment site is WECC.  Override explicitly for
    # non-WECC scenarios.  Carried through scenario_factory → SiteConfig;
    # SiteConfig has no default so omitting this from the spec fails at startup.
    frequency_nominal_hz: float = Field(
        default=60.0,
        ge=45.0, le=65.0,
        description=(
            "Nominal grid frequency for the site (Hz).  "
            "60 Hz for WECC/ERCOT (North America); 50 Hz for EU/APAC. "
            "Drives the swing-equation denominator and all frequency-response criteria."
        ),
    )
    power_factor: float = Field(
        default=0.85,
        gt=0.0, le=1.0,
        description=(
            "Rated power factor of the synchronous generator fleet (dimensionless).  "
            "Converts rated_mw to MVA base: S_base = Σ rated_mw / power_factor.  "
            "Typical gas turbine: 0.85 (CHOSEN — calibrate against nameplate or vendor data).  "
            "Raising pf toward 1.0 lowers S_base and increases df/dt; lowering it slows frequency response."
        ),
    )
    pue_base: float = Field(default=1.03, ge=1.0, le=2.0)
    end_sim_time: float = Field(default=300.0, ge=60.0, le=86400.0)
    # Default playback speed stored with the scenario so operators don't have to
    # re-select it every run.  0 = max-speed sentinel; >0 = simulated-s per real-s.
    # Honoured by the "Run" button in the Scenarios modal and the DemoBar auto-fill.
    default_playback_speed: float = Field(
        default=1.0,
        ge=0.0,
        description=(
            "Default simulation playback speed for this scenario.  "
            "0 = run as fast as possible; >0 = simulated-seconds per real-second.  "
            "Stored in the spec so the operator's choice persists across sessions."
        ),
    )

    # ── Physics parameters (gridsignal_parameters.json §2) ─────────────────
    # Generated from gridsignal_parameters.json at runtime; never hand-coded.
    # Split parameters (split=true in JSON) have optional plant_ variants.
    # When plant_* is None the simulation uses the engine value (linked default).
    #
    # §2.1 / §2.2 — Thermal response (PARAM-02/03/04)
    dt_thermal_seconds: float = Field(
        default=90.0, ge=0.0, le=300.0,
        description=(
            "Engine value: thermal-delay before cooling ramp (Δt_thermal, s). "
            "Source: §8–9, SPEC_DEFAULT."
        ),
    )
    plant_dt_thermal_seconds: Optional[float] = Field(
        default=None, ge=0.0, le=300.0,
        description=(
            "Plant value for Δt_thermal. None = linked to dt_thermal_seconds. "
            "Set explicitly to simulate a plant/engine thermal-model divergence."
        ),
    )
    alpha_max: float = Field(
        default=0.20, ge=0.0, le=1.0,
        description=(
            "Engine value: maximum cooling fraction (α_max). "
            "Source: §8, SPEC_DEFAULT."
        ),
    )
    plant_alpha_max: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Plant value for α_max. None = linked to alpha_max.",
    )
    tau_seconds: float = Field(
        default=20.0, ge=1.0, le=120.0,
        description=(
            "Engine value: cooling time-constant (τ, s). "
            "Source: §8, PROPOSED_HERE."
        ),
    )
    plant_tau_seconds: Optional[float] = Field(
        default=None, ge=1.0, le=120.0,
        description="Plant value for τ. None = linked to tau_seconds.",
    )

    # §2.5 — Reserve-check parameters (PARAM-09/13/14/15)
    # anchor_reserve_pct: % of each grid-forming BESS's rated MW withheld as
    #   anchor reserve.  0.0 = use BessConfig.p_anchor_reserve_mw default (1.0 MW).
    #   PROPOSED_HERE — 8% is the placeholder; calibrate against commissioning specs.
    anchor_reserve_pct: float = Field(
        default=0.0, ge=0.0, le=20.0,
        description=(
            "Anchor reserve as % of BESS rated MW (grid-forming unit only). "
            "0 = use BessConfig default (1.0 MW). PROPOSED_HERE — pending commissioning."
        ),
    )
    # Confidence band (§2.5, INV-2) — PROPOSED_HERE decisions:
    #   band_pct_calibrated = 4%  →  uncalibrated = 4% × 2.0 = 8% = fixture
    #   band_mult_uncalibrated = 2.0×
    #   band_mult_unmapped_hw  = 1.5×
    # Default 0.0 in ScenarioSpec preserves backward-compat for all seeded
    # scenarios (which pre-date this parameter and should behave as before).
    # Set to 4.0 in the ParameterModal default to activate INV-2 compliance.
    band_pct_calibrated: float = Field(
        default=0.0, ge=0.0, le=15.0,
        description=(
            "Confidence band ±% of peak_shortfall for reserve check (INV-2). "
            "0 = disabled (point-estimate check only, backward-compat). "
            "PROPOSED_HERE default: 4.0%. "
            "Effective band = band_pct × mult_uncalib × mult_unmapped_hw."
        ),
    )
    band_mult_uncalibrated: float = Field(
        default=2.0, ge=1.0, le=4.0,
        description=(
            "Reserve-band multiplier for uncalibrated sites (§17.3). "
            "PROPOSED_HERE decision: 2.0× (calibrated × 2.0 = fixture 8%)."
        ),
    )
    band_mult_unmapped_hw: float = Field(
        default=1.5, ge=1.0, le=4.0,
        description=(
            "Reserve-band multiplier for unmapped hardware profiles (§5.1). "
            "PROPOSED_HERE decision: 1.5× (independent of uncalibrated mult)."
        ),
    )

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

    # Kubernetes demand agent — autonomous stochastic GPU cluster demand.
    # None = standard scripted workload path (default; existing tests unaffected).
    # When set, the agent emits STARTING then SCALE signals each tick, driven by
    # an OU process + EMA.  Power-cap fires when grid headroom < headroom_threshold_mw.
    kube_config: Optional[KubeConfigSpec] = None

    # ── Within-step compute load profile (scripted-event / non-kube path) ────
    # Activates compute-phase vs allreduce-phase power variation for scenarios
    # that use workload_events rather than kube_config.  The step phase is
    # self-managed by GPUModule.advance() using a fixed 0.70 s step period
    # (StepTimingConfig.median_step_s default) so tick-to-tick p_compute_mw
    # varies realistically between ~100% TDP (compute) and ~55% TDP (allreduce).
    #
    # Ignored when kube_config is set — kube_config.load_config takes priority.
    # None (default) = flat profile, preserving all existing test behaviour.
    load_config: Optional[LoadProfileConfigSpec] = None

    # ── Pre-run generation architecture ────────────────────────────────────────
    # All generators run concurrently BEFORE t=0, materialising timelines that
    # the tick loop replays deterministically.  No generator runs during ticks.

    # Correlated ambient weather: when solar_rated_mw > 0 and irradiance_steps
    # is the bare default, generate_solar_forecast() already emits ambient_steps.
    # This field carries those steps (injected by runs.py, not user-settable).
    ambient_steps: list[tuple[float, float, float]] = Field(
        default_factory=list,
        description="Pre-generated (sim_time_s, drybulb_c, wetbulb_c) timeline. "
                    "Populated automatically by generate_solar_forecast(); not user-settable.",
    )

    # LLM cluster arrival generator — replaces (or supplements) scripted workload events
    # with a Mistral-generated bursty, correlated cluster traffic timeline.
    # None = use existing workload_events and/or kube_config as-is.
    cluster_gen_config: Optional[ClusterGenConfigSpec] = None

    # LLM fault/stressor timeline generator — adds compound fault scenarios
    # (cloud fronts, inverter trips) as SOLAR_STEP events.
    # None = no stressor injection.
    stressor_gen_config: Optional[StressorGenConfigSpec] = None

    # Per-run seeded RNG parameter sampling — draws physics params from their
    # documented ranges once, producing a distinct sensitivity point per run.
    # None = no parameter sampling.
    param_sampling_config: Optional[ParamSamplingConfigSpec] = None

    # Pre-generated telemetry corruption schedule — stresses §17.2 quarantine.
    # None = clean telemetry (default; existing tests unaffected).
    telemetry_corruption_config: Optional[TelemetryCorruptionConfigSpec] = None

    # Generation block — populated by runs.py after all generators complete.
    # Distinguishes a scenario definition from a materialised spec and makes
    # any failing run replayable.
    generation_block: Optional[GenerationBlock] = None

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

    # Solar origin UTC hour override — demo-solar-peak uses this to anchor
    # generate_solar_forecast() at a fixed midday UTC time (UTC 20 = 12:00 PST)
    # regardless of when the demo is actually run.  None = use real UTC now.
    # Valid range [0, 23]; runs.py converts to a datetime before calling
    # generate_solar_forecast() so the Mistral prompt and physics curve both
    # see the anchored local San Diego time.
    solar_origin_utc_hour: Optional[int] = Field(
        default=None, ge=0, le=23,
        description=(
            "Fix the UTC hour passed to generate_solar_forecast(). "
            "Use 20 for UTC 20:00 = 12:00 PST San Diego solar noon. "
            "None = real wall-clock UTC (default for all other scenarios)."
        ),
    )

    # Step 9: optional pass/fail assertions evaluated at run completion.
    # Each element is one of the AssertionSpec union members (discriminated
    # on 'check').  Empty list → verdict is INCONCLUSIVE.
    assertions: list[AssertionSpec] = Field(default_factory=list)

    # Phase 10: fabric stress scenario reference.
    # When set, the FabricEngine loads the named S1–S8 scenario JSON from
    # config/scenarios/, using its jobs/stressors/capability_tier, and
    # evaluates the scenario's fabric-specific assertions at run completion.
    # The value is the scenario_id field from the JSON file (e.g. "S2_checkpoint_hotspot").
    fabric_scenario_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of a fabric stress scenario JSON file to drive the FabricEngine. "
            "Set to the scenario_id value from one of the config/scenarios/S*.json files."
        ),
    )

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


# ---------------------------------------------------------------------------
# Generation architecture — pre-run generators (materialized before t=0)
# ---------------------------------------------------------------------------

class GenerationBlock(BaseModel):
    """Metadata record for all pre-run generators that ran for a scenario.

    Stored on RunContext and emitted in run metadata so that a scenario
    definition and a materialised spec are distinguishable artifacts.
    A run ID + generation_block is sufficient to replay any run exactly:
    - physics/RNG paths replay from seed alone.
    - LLM paths replay by re-running the generators (Mistral may vary) or by
      reading the stored event lists from the scenario spec.

    Fields
    ------
    seed              : master RNG seed for this run (None = time-seeded).
    generated_at      : ISO-8601 UTC timestamp when generation ran.
    generators_used   : list of generator names that actually ran.
    solar_source      : "mistral" | "physics" | "none".
    cluster_source    : "mistral" | "rng" | "none".
    stressor_source   : "mistral" | "rng" | "none".
    param_sampler_note: human-readable summary from param_sampler.
    corruption_note   : human-readable summary from telemetry_corruption.
    """
    seed:               Optional[int]   = None
    generated_at:       str             = ""
    generators_used:    list[str]       = Field(default_factory=list)
    solar_source:       str             = "none"
    cluster_source:     str             = "none"
    stressor_source:    str             = "none"
    param_sampler_note: str             = ""
    corruption_note:    str             = ""


class ClusterGenConfigSpec(BaseModel):
    """Configuration for the LLM-driven cluster arrival process generator.

    When present on a ScenarioSpec, the generator is called ONCE at run start
    (before the tick loop).  The resulting STARTING/JOB_END/SCALE events are
    merged into spec_data["workload_events"] before the RunContext is built.

    use_llm=True (default) calls Mistral for temporal structure — bursts,
    business-hours patterns — that a Poisson process cannot reproduce.
    Falls back to seeded RNG when MISTRAL_API_KEY is absent or the call fails.

    use_llm=False forces the seeded RNG path.  Prefer this when the arrival
    statistics are fully specified by the other fields (the Poisson case).
    """
    description:        str   = "plausible weekday on a 1900-node ML cluster"
    hardware_profile_id: str  = "enterprise_8gpu_air"
    max_nodes:          int   = Field(default=1900, ge=1)
    min_nodes:          int   = Field(default=200,  ge=1)
    mean_interarrival_s: float = Field(default=60.0, ge=5.0, le=3600.0)
    mean_job_nodes:     int   = Field(default=200, ge=1)
    job_node_std:       float = Field(default=80.0, ge=0.0)
    min_job_nodes:      int   = Field(default=50, ge=1)
    mean_job_duration_s: float = Field(default=300.0, ge=10.0)
    min_job_duration_s: float = Field(default=30.0,  ge=5.0)
    rng_seed:           Optional[int] = None
    use_llm:            bool  = True


class StressorGenConfigSpec(BaseModel):
    """Configuration for the LLM-driven fault and stressor timeline generator.

    When present on a ScenarioSpec, the generator is called ONCE at run start
    and its output (SOLAR_STEP events) is merged into spec_data["workload_events"].

    The LLM composes plausible compound fault sequences: cloud front arrives,
    inverter trips 90 seconds later, partial recovery — the correlated-failure
    case that a hand-written scenario library under-represents.

    use_llm=False forces the seeded RNG fallback (random cloud fronts).
    """
    description:    str   = "compound cloud-front and inverter-trip scenario"
    n_rng_events:   int   = Field(default=3, ge=1, le=20)
    rng_seed:       Optional[int] = None
    use_llm:        bool  = True


class ParamSamplingConfigSpec(BaseModel):
    """Configuration for per-run seeded RNG parameter sampling (§6.1 sensitivity).

    When present, draws the listed physics parameters from their documented
    [min, max] ranges once at run start and merges them into spec_data.

    The seeded RNG path is always used — there is no LLM call here.  Seeded RNG
    is the correct tool: the sampling distribution is fully specified by the
    parameter ranges and there is no temporal structure an LLM adds value to.

    keys  — parameter keys as in gridsignal_parameters.json (e.g. "alpha_max").
            Keys not in the adjustable list or in the _NEVER_SAMPLE exclusion set
            are silently skipped.
    seed  — RNG seed; None = time-seeded (non-reproducible).
    sample_plant_split — if True, split parameters draw independent plant and
            engine values, producing natural plant/engine divergence.
    """
    keys:               list[str] = Field(
        default_factory=lambda: ["dt_thermal", "alpha_max", "tau"],
        description="Parameter keys to sample from gridsignal_parameters.json",
    )
    seed:               Optional[int] = None
    sample_plant_split: bool = True


class TelemetryCorruptionConfigSpec(BaseModel):
    """Configuration for the pre-generated telemetry corruption schedule.

    When present, a per-tick corruption manifest is generated ONCE at run start
    from a seeded RNG.  The manifest specifies which ticks receive Gaussian noise,
    dropout (record suppressed), or staleness (old reading substituted).

    This exercises the §17.2 quarantine path, NTP-skew handling, and out-of-order
    delivery logic.  All values default to 0.0 / 0 (no corruption) so that adding
    the block without setting values is a safe no-op.
    """
    noise_sigma:  float = Field(
        default=0.0, ge=0.0, le=0.5,
        description="1-sigma of multiplicative Gaussian noise on readings (e.g. 0.05 = ±5%)",
    )
    dropout_prob: float = Field(
        default=0.0, ge=0.0, lt=1.0,
        description="Per-tick probability of record suppression (packet loss)",
    )
    max_stale:    int   = Field(
        default=0, ge=0, le=30,
        description="Maximum staleness in ticks (0 = no staleness injection)",
    )
    seed:         Optional[int] = None


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
    end_sim_time: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Simulated seconds to run.  None (default) means use the scenario's own "
            "end_sim_time.  Pass 1e15 for an effectively unlimited run."
        ),
    )
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
    soc_floor_pct: float = 10.0   # operator-set BESS lower display bound
    soc_ceil_pct: float  = 95.0   # operator-set BESS upper display bound


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


# ---------------------------------------------------------------------------
# Operator unit command (Task #203)
# ---------------------------------------------------------------------------

class UnitCommandRequest(BaseModel):
    """Body for POST /runs/{run_id}/units/{unit_id}/command.

    action:
      "trip"  — force the named unit to OFFLINE immediately; output zeroed.
                Only valid when the unit is on-bus (synchronised / ramping /
                at_target).
      "start" — enter the start sequence from OFFLINE; unit ramps to
                SYNCHRONISED naturally.  Only valid when state is OFFLINE.
    """
    action: Literal["trip", "start"]
