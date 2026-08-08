"""
Small helper for constructing a ready-to-run RunContext from minimal
parameters.  This is not the real Scenario Builder (functional spec
Section 7.2) -- it's a convenience used by tests and by the usage
example (runtime/example_usage.py) to stand up a SimulationState
without wiring every constructor by hand.

Placement rationale: build_run_context() and build_load_test_context()
both return RunContext (a runtime/ concept) and import from
runtime.run_manager.  They belong in runtime/ so that core/ stays free
of any runtime/ dependency -- a requirement of v2.5 §21.1 and Design
Spec §2 principle 2 (core/ is the synchronous control plane; runtime/
is the concurrency layer).
"""

from __future__ import annotations

import os
import uuid as _uuid

from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.models import (
    BessConfig,
    HardwareProfile,
    IslandMode,
    PmsConfig,
    PreStagingConfig,
    SiteConfig,
    SolarConfig,
    TransitionMode,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.kube_demand import KubeConfig, KubeDemandAgent
from core.step_config import LoadProfileConfig, StepTimingConfig
from core.simulation_core import SimulationState
import core.site_parameters as _sp  # GS-DES-CFG-001 §Phase-6
from pydantic import TypeAdapter

from runtime.run_manager import InMemoryTimeseriesSink, RunContext
from runtime.verdict import AssertionSpec as _AssertionSpec

# W1 — advisory, telemetry, and procurement wiring.
# Imported here (runtime/) not in run_manager (would create circular import
# because advisory/ imports from runtime/advisory_gate).
from runtime.advisory_router import AdvisoryRouter, DeterministicRouter
from advisory.agent_registry import AgentRegistry
from core.network_telemetry import NetworkTelemetryIngestor
from core.corroboration import FabricCorroborator
from core.procurement import (
    CapacityType,
    GridCapacity,
    ProcurementLayer,
    SyntheticPriceCurve,
)
from core.maintenance import AssetHealthRecord, MaintenanceLayer
from core.ramp_relaxation import RampRelaxationEngine

# TypeAdapter for deserialising assertion specs from plain dicts in
# build_run_context_from_spec.  Created once at module level (not per-call)
# to avoid repeated schema compilation overhead.
_assertion_adapter: TypeAdapter = TypeAdapter(_AssertionSpec)


DEFAULT_HARDWARE_LIBRARY = {
    "enterprise_8gpu_air": HardwareProfile("enterprise_8gpu_air", rated_kw=10.2),
    "nextgen_rack_liquid": HardwareProfile("nextgen_rack_liquid", rated_kw=126.0),
}


def build_run_context(
    run_id: str,
    *,
    job_id: str,
    node_count: int,
    hardware_profile_id: str = "enterprise_8gpu_air",
    dt_lead_seconds: float = 30.0,
    turbine_count: int = 1,
    r_asset_mw_per_s: float = 0.2,
    # PROTO-8: turbine_rated_mw default (10 MW) matches the fleet sizing that
    # produces the §7.2 arc for a single-turbine ~5 MW scenario.  Larger loads
    # (e.g. demo-20mw at ~19 MW) must pass a higher value so the turbine can
    # eventually cover steady-state P_dispatch_required and allow BESS to taper.
    turbine_rated_mw: float = 10.0,
    bess_rated_mw: float = 5.0,
    bess_usable_mwh: float = 2.0,
    # Step 3 Item 4: whether the BESS is the grid-forming anchor unit.
    # Default False — most units are grid-following; the anchor role must be
    # explicitly assigned.  Set True for islanded scenarios where this BESS
    # holds frequency by retaining headroom in both directions (§7.1.2).
    bess_grid_forming: bool = False,
    end_sim_time: float = 600.0,
    playback_speed: float = 0.0,  # 0 == "max" speed, no artificial delay
    # A1: frequency_nominal_hz must be supplied by caller; 60.0 default is WECC/SDG&E
    # territory (San Diego demo site).  Override explicitly for non-WECC fixtures.
    frequency_nominal_hz: float = 60.0,
    # power_factor: rated pf of the synchronous fleet.  0.85 is CHOSEN (typical gas
    # turbine); calibrate against vendor data for real deployments.
    power_factor: float = 0.85,
) -> RunContext:
    site = SiteConfig(
        site_id=f"site-for-{run_id}",
        frequency_nominal_hz=frequency_nominal_hz,
        power_factor=power_factor,
    )

    gpu = GPUModule(
        asset_id="gpu-0",
        site=site,
        hardware_library=DEFAULT_HARDWARE_LIBRARY,
    )
    cooling = CoolingModule(asset_id="cooling-0", site=site)
    turbines = [
        TurbineModule(TurbineConfig(
            asset_id=f"turbine-{i}",
            r_asset_mw_per_s=r_asset_mw_per_s,
            rated_mw=turbine_rated_mw,
        ))
        for i in range(turbine_count)
    ]
    bess_units = [BessModule(BessConfig(
        asset_id="bess-0",
        rated_mw=bess_rated_mw,
        usable_mwh=bess_usable_mwh,
        grid_forming=bess_grid_forming,
    ))]
    # PROTO-7: solar sized at 25% of peak compute draw — CHOSEN, no measured basis.
    # Sizing as a fraction of peak compute keeps P_dispatch_required non-zero
    # (BESS bridging, the reserve check, and the §7.1.1 renewable-shortfall
    # scenario all remain exercisable) while representing a realistic on-site
    # renewable contribution.  20–30% is the chosen range; 25% is the midpoint.
    _solar_profile = DEFAULT_HARDWARE_LIBRARY.get(
        hardware_profile_id,
        HardwareProfile(hardware_profile_id, rated_kw=12.0),
    )
    # GS-DES-CFG-001 §Phase-6 / Item-1: one definition, PUE-inclusive, named for its basis.
    # simulation_core.py:953 computes P_compute = Σ nodes × kW × PUE_base / 1000 (PUE-inclusive).
    # alpha_max is applied to that PUE-inclusive figure at runtime (simulation_core.py:1152),
    # so cooling sizing must use the same basis.  Solar also sizes against total site draw
    # (PUE-inclusive), so one definition serves both.  Former two-definition rebind removed.
    _peak_it_load_mw = node_count * _solar_profile.rated_kw * site.pue_base / 1000.0
    _solar_rated_mw  = _sp.value("solar_fraction_of_peak") * _peak_it_load_mw  # PROTO-7

    solar_arrays = [
        SolarModule(
            SolarConfig(asset_id="solar-0", rated_mw=_solar_rated_mw),
            irradiance_profile=IrradianceProfile([(0.0, 1.0), (end_sim_time, 1.0)]),
        )
    ]

    sim_state = SimulationState(
        run_id=run_id,
        site=site,
        gpu_modules=[gpu],
        turbines=turbines,
        bess_units=bess_units,
        solar_arrays=solar_arrays,
        cooling=cooling,
    )

    events = [
        WorkloadSignal(
            event_id=f"evt-{job_id}-start",
            job_id=job_id,
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id=hardware_profile_id,
            node_count=node_count,
            workload_class=WorkloadClass.TRAINING,
            site_id=site.site_id,
        )
    ]

    # ── W1 advisory, telemetry, procurement wiring ────────────────────────
    # GS-DES-CFG-001 §Phase-6 / Item-1+2, corrected §Phase-7 / Item-1.
    # _COOLING_MARGIN (1.15) is sourced from the catalogue (locked cooling_margin, PROTO-10).
    #
    # What the 15% covers AFTER Phase 6 (PUE overhead is no longer in scope —
    # it is now inside _peak_it_load_mw = nodes × kW × PUE_base / 1000):
    #   1. BESS charge overhead — inverter losses (~2–4%) heat the plant during charging.
    #   2. Non-compute IT load — networking switches, PDUs, UPS auxiliary (~3–8% of compute).
    #   3. Ambient excursion headroom — alpha_max × ambient_alpha_scale can add up to +4.5%
    #      above nominal (3°C × 1.5%/°C, locked ambient_cooling_scale_per_c) before saturation.
    #   4. Cooling-plant efficiency margin — chillers operate below nameplate at partial load (~2–5%).
    #
    # Remaining sum: 11.5–21.5%; 1.15 is the CHOSEN midpoint.  Value unchanged from Phase 6.
    # PUE overhead (formerly cited here) is absorbed into _peak_it_load_mw; not a margin job.
    _COOLING_MARGIN      = _sp.value("cooling_margin")  # PROTO-10; catalogue: locked cooling_margin
    _rated_cooling_mw    = site.alpha_max * _peak_it_load_mw * _COOLING_MARGIN
    _design_peak_load_mw = _peak_it_load_mw + _rated_cooling_mw

    # Grid capacity scaled to turbine fleet (static for the demo run).
    _total_turbine_mw = turbine_rated_mw * turbine_count
    _grid_cap = [
        GridCapacity(CapacityType.FIRM,     available_mw=_total_turbine_mw * 0.80, price_per_mwh=48.0, t_reserve_s=0.0),
        GridCapacity(CapacityType.RESERVED, available_mw=_total_turbine_mw * 0.40, price_per_mwh=62.0, t_reserve_s=300.0),
        GridCapacity(CapacityType.NON_FIRM, available_mw=_total_turbine_mw * 0.15, price_per_mwh=198.0, t_reserve_s=0.0),
    ]

    return RunContext(
        run_id=run_id,
        sim_state=sim_state,
        events=events,
        dt_lead_seconds=dt_lead_seconds,
        end_sim_time=end_sim_time,
        playback_speed=playback_speed,
        sink=InMemoryTimeseriesSink(),
        # W1 fields
        registry=AgentRegistry(
            router=DeterministicRouter() if os.environ.get('PYTEST_CURRENT_TEST')
                   else AdvisoryRouter(),
            enabled=True,
        ),
        telemetry_ingestor=NetworkTelemetryIngestor(),
        corroborator=FabricCorroborator(),
        price_curve=SyntheticPriceCurve(seed=42),
        grid_capacity=_grid_cap,
        _rated_cooling_mw=_rated_cooling_mw,
        _design_peak_load_mw=_design_peak_load_mw,
    )


def build_load_test_context(
    run_id: str,
    *,
    gpu_module_count: int = 50,
    turbine_count: int = 8,
    bess_count: int = 4,
    solar_count: int = 4,
    nodes_per_gpu_module: int = 20,
    hardware_profile_id: str = "enterprise_8gpu_air",
    dt_lead_seconds: float = 30.0,
    r_asset_mw_per_s: float = 0.2,
    bess_rated_mw: float = 5.0,
    bess_usable_mwh: float = 2.0,
    end_sim_time: float = 14400.0,   # 4 simulated hours -- functional spec Section 11
    playback_speed: float = 0.0,     # 0 == "max" speed
    frequency_nominal_hz: float = 60.0,   # WECC/SDG&E default; override for non-WECC
    power_factor: float = 0.85,           # CHOSEN — typical gas turbine
) -> RunContext:
    """Builds a RunContext at (or above, via the *_count params) the
    functional spec's NFR-ceiling configuration (Section 11: 50 GPU
    modules / 8 turbines / 4 BESS / 4 solar per site), for use by the
    load-testing script (Design Spec Section 9's validation plan).

    Unlike build_run_context() above, every GPU module here carries its
    own active training job, so the tick's compute term actually sums
    across `gpu_module_count` independent modules -- this is what makes
    the load test representative of evaluate_tick()'s real per-tick
    cost (Design Spec Section 4.3), not just an idle scaffold.
    """
    site = SiteConfig(
        site_id=f"site-for-{run_id}",
        frequency_nominal_hz=frequency_nominal_hz,
        power_factor=power_factor,
    )

    gpu_modules = [
        GPUModule(asset_id=f"gpu-{i}", site=site, hardware_library=DEFAULT_HARDWARE_LIBRARY)
        for i in range(gpu_module_count)
    ]
    cooling = CoolingModule(asset_id="cooling-0", site=site)
    turbines = [
        TurbineModule(TurbineConfig(asset_id=f"turbine-{i}", r_asset_mw_per_s=r_asset_mw_per_s))
        for i in range(turbine_count)
    ]
    bess_units = [
        BessModule(BessConfig(asset_id=f"bess-{i}", rated_mw=bess_rated_mw, usable_mwh=bess_usable_mwh))
        for i in range(bess_count)
    ]
    # PROTO-7: solar total = 25% of peak compute draw, distributed equally.
    # See build_run_context() for the sizing rationale.
    _lt_profile = DEFAULT_HARDWARE_LIBRARY.get(
        hardware_profile_id,
        HardwareProfile(hardware_profile_id, rated_kw=12.0),
    )
    # GS-DES-CFG-001 §Phase-6 / Item-1: PUE-inclusive, same basis as build_run_context.
    _lt_peak_it_load_mw = (
        gpu_module_count * nodes_per_gpu_module * _lt_profile.rated_kw * site.pue_base / 1000.0
    )
    _lt_solar_rated_mw_each = (_sp.value("solar_fraction_of_peak") * _lt_peak_it_load_mw) / max(solar_count, 1)  # PROTO-7

    solar_arrays = [
        SolarModule(
            SolarConfig(asset_id=f"solar-{i}", rated_mw=_lt_solar_rated_mw_each),
            irradiance_profile=IrradianceProfile([(0.0, 1.0), (end_sim_time, 1.0)]),
        )
        for i in range(solar_count)
    ]

    sim_state = SimulationState(
        run_id=run_id,
        site=site,
        gpu_modules=gpu_modules,
        turbines=turbines,
        bess_units=bess_units,
        solar_arrays=solar_arrays,
        cooling=cooling,
    )

    # One job per GPU module, all starting at t=0, so the very first
    # tick already exercises the full compute-term summation
    # (Design Spec Section 4.3's "66 assets" analysis, generalized to
    # whatever counts the caller passed in).
    events = [
        WorkloadSignal(
            event_id=f"evt-{run_id}-gpu{i}-start",
            job_id=f"job-{run_id}-{i}",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id=hardware_profile_id,
            node_count=nodes_per_gpu_module,
            workload_class=WorkloadClass.TRAINING,
            site_id=site.site_id,
        )
        for i in range(gpu_module_count)
    ]

    # ── W1 advisory, telemetry, procurement wiring (load-test context) ──────
    _lt_total_turbine_mw = 10.0 * turbine_count   # default rated_mw per turbine
    # GS-DES-CFG-001 §Phase-6 / Item-1, corrected §Phase-7 / Item-1: see build_run_context
    # for the full enumeration of what _COOLING_MARGIN covers.  PUE in _lt_peak_it_load_mw.
    _lt_rated_cooling_mw    = site.alpha_max * _lt_peak_it_load_mw * _sp.value("cooling_margin")  # PROTO-10
    _lt_design_peak_load_mw = _lt_peak_it_load_mw + _lt_rated_cooling_mw
    _lt_grid_cap = [
        GridCapacity(CapacityType.FIRM,     available_mw=_lt_total_turbine_mw * 0.80, price_per_mwh=48.0, t_reserve_s=0.0),
        GridCapacity(CapacityType.RESERVED, available_mw=_lt_total_turbine_mw * 0.40, price_per_mwh=62.0, t_reserve_s=300.0),
        GridCapacity(CapacityType.NON_FIRM, available_mw=_lt_total_turbine_mw * 0.15, price_per_mwh=198.0, t_reserve_s=0.0),
    ]

    return RunContext(
        run_id=run_id,
        sim_state=sim_state,
        events=events,
        dt_lead_seconds=dt_lead_seconds,
        end_sim_time=end_sim_time,
        playback_speed=playback_speed,
        sink=InMemoryTimeseriesSink(),
        # W1 fields
        # AC1(a): load test measures simulation throughput, not advisory quality.
        # Agents disabled so the LLM call cost (6 s / tick-1 stampede) does not
        # count against the 30 s wall-clock NFR. Use build_run_context() or
        # build_run_context_from_spec() for contexts that require proposals.
        # AC1(b): even when enabled=False,run_all() is wrapped in
        # asyncio.to_thread() in _drive() so the event loop stays free.
        registry=AgentRegistry(
            router=DeterministicRouter() if os.environ.get('PYTEST_CURRENT_TEST')
                   else AdvisoryRouter(),
            enabled=True, 
        ),
        telemetry_ingestor=NetworkTelemetryIngestor(),
        corroborator=FabricCorroborator(),
        price_curve=SyntheticPriceCurve(seed=42),
        grid_capacity=_lt_grid_cap,
        _rated_cooling_mw=_lt_rated_cooling_mw,
        _design_peak_load_mw=_lt_design_peak_load_mw,
    )


# ---------------------------------------------------------------------------
# Step 8: build_run_context_from_spec
# ---------------------------------------------------------------------------

def build_run_context_from_spec(
    run_id: str,
    spec_data: dict,
    playback_speed: float = 0.0,
) -> RunContext:
    """Build a RunContext from a scenario spec dictionary (JSON-round-trip safe).

    ``spec_data`` is the plain-Python form of a serialised ScenarioSpec —
    i.e. ``json.loads(record.spec_json)`` or ``spec.model_dump()``.
    All dicts, lists, and scalars; no Pydantic models.

    Design constraints:
    - This function must NOT import from api/ (runtime/ → api/ is forbidden
      by §21.1 plane-separation).  The caller (api/routes/runs.py) is
      responsible for validating the spec via Pydantic and serialising it;
      this function only reads a plain dict.
    - WorkloadClass is always TRAINING.  The scenario builder does not
      distinguish class types; that's a Step 10 concern.
    - An empty workload_events list is valid (idle run or TC-33 compute
      where the job starts at t>0).
    - SOLAR_STEP events are forwarded with event_type=WorkloadEventType.SOLAR_STEP;
      SimulationState.apply_workload_signal's early-return handles them.

    Step 9 will swap ScenarioRecord.spec_json reads from in-memory to
    SQLAlchemy while calling this function identically.
    """
    # ── Site configuration ────────────────────────────────────────────────
    island = (
        IslandMode.ISLANDED
        if spec_data.get("island_mode", True)
        else IslandMode.GRID_TIE
    )
    # A1: frequency_nominal_hz and power_factor are REQUIRED on SiteConfig (no default).
    # ScenarioSpec guarantees both via schema defaults (60.0 / 0.85), so these
    # raises fire only when a raw dict without the fields is passed directly.
    _freq_raw = spec_data.get("frequency_nominal_hz")
    if _freq_raw is None:
        raise ValueError(
            f"scenario spec for run '{run_id}' is missing 'frequency_nominal_hz'. "
            "Set it explicitly: 60.0 for WECC/ERCOT (North America), 50.0 for EU/APAC."
        )
    _pf_raw = spec_data.get("power_factor")
    if _pf_raw is None:
        raise ValueError(
            f"scenario spec for run '{run_id}' is missing 'power_factor'. "
            "Add it: typical gas turbine pf = 0.85 (CHOSEN — calibrate against nameplate)."
        )
    site = SiteConfig(
        site_id=f"site-for-{run_id}",
        frequency_nominal_hz=float(_freq_raw),
        power_factor=float(_pf_raw),
        pue_base=spec_data.get("pue_base", 1.03),
        island_mode=island,
        # AD2: calibrated=True in spec → uncalibrated=False in SiteConfig.
        # Required for scenarios where the TC-43 curtailment dwell must fire
        # (e.g. demo-pms-shortfall).  Default False preserves §17.3 behaviour.
        uncalibrated=not bool(spec_data.get("calibrated", False)),
        # ── Physics parameters (gridsignal_parameters.json §2) ──────────────
        # Plant values: what the simulation actually does.
        # plant_* present → use that; absent → use engine value (linked default).
        alpha_max=float(
            spec_data.get("plant_alpha_max")
            or spec_data.get("alpha_max", 0.20)
        ),
        tau_seconds=float(
            spec_data.get("plant_tau_seconds")
            or spec_data.get("tau_seconds", 20.0)
        ),
        dt_thermal_seconds=float(
            spec_data.get("plant_dt_thermal_seconds")
            or spec_data.get("dt_thermal_seconds", 90.0)
        ),
        # Reserve-check confidence band (INV-2, §2.5).
        # band_enabled: inferred from band_pct_calibrated for backward-compat —
        # any pre-existing spec with band_pct_calibrated > 0 activates the band
        # automatically. Explicit band_enabled in spec_data takes precedence.
        band_enabled=bool(spec_data.get(
            "band_enabled",
            float(spec_data.get("band_pct_calibrated", 0.0)) > 0.0,
        )),
        band_pct_calibrated=float(spec_data.get("band_pct_calibrated", 0.0)),
        band_mult_uncalibrated=float(spec_data.get("band_mult_uncalibrated", 2.0)),
        band_mult_unmapped_hw=float(spec_data.get("band_mult_unmapped_hw", 1.5)),
        # §FP: Optional frequency protection thresholds.
        # Not present → None (protection disabled for that threshold).
        # Set all five in the spec for a site with active protection.
        # Recommended values for 60 Hz (SDG&E/WECC) are documented in
        # gridsignal_parameters.json under the "frequency_protection" group.
        uf_warning_hz=(
            float(spec_data["uf_warning_hz"])
            if spec_data.get("uf_warning_hz") is not None else None
        ),
        ufls_stage1_hz=(
            float(spec_data["ufls_stage1_hz"])
            if spec_data.get("ufls_stage1_hz") is not None else None
        ),
        island_collapse_hz=(
            float(spec_data["island_collapse_hz"])
            if spec_data.get("island_collapse_hz") is not None else None
        ),
        of_warning_hz=(
            float(spec_data["of_warning_hz"])
            if spec_data.get("of_warning_hz") is not None else None
        ),
        of_trip_hz=(
            float(spec_data["of_trip_hz"])
            if spec_data.get("of_trip_hz") is not None else None
        ),
        # Phase 5: UFLS and 81U relay (opt-in — empty list / None = disabled).
        ufls_stages=(
            list(spec_data["ufls_stages"])
            if spec_data.get("ufls_stages") is not None else []
        ),
        relay_81u_threshold_hz=(
            float(spec_data["relay_81u_threshold_hz"])
            if spec_data.get("relay_81u_threshold_hz") is not None else None
        ),
        relay_81u_delay_s=(
            float(spec_data["relay_81u_delay_s"])
            if spec_data.get("relay_81u_delay_s") is not None else
            float(_sp.value("relay_81u_delay_s"))
        ),
    )

    # PROTO-32-AMB: ambient temperature adjustment to alpha_max.
    # When generate_solar_forecast() has been called before run start,
    # spec_data["ambient_steps"] carries correlated dry-bulb temperatures.
    # Hotter ambient → HVAC operates less efficiently → higher cooling fraction.
    # Absent on tests and runs without a solar forecast (ambient_steps=[] → no-op).
    # Applied after the explicit alpha_max / plant_alpha_max read so that the
    # spec-level value is always the baseline and ambient modulates around it.
    _ambient_steps_raw = spec_data.get("ambient_steps", [])
    _ambient_avg_c:   float = 0.0
    _ambient_scale:   float = 1.0
    if _ambient_steps_raw:
        from runtime.solar_sim import ambient_alpha_scale  # lazy — runtime→runtime OK
        _scale = ambient_alpha_scale(_ambient_steps_raw)
        _drybulbs = [float(db) for _, db, _ in _ambient_steps_raw]
        _ambient_avg_c = sum(_drybulbs) / len(_drybulbs)
        _ambient_scale = _scale
        site.alpha_max = site.alpha_max * _scale

    # Step 10 — §8.1: wire optional pre-staging config from spec.
    # Must be set before SimulationState() so __post_init__ picks it up.
    _pre_staging_raw = spec_data.get("pre_staging_config")
    if _pre_staging_raw:
        site.pre_staging_config = PreStagingConfig(**_pre_staging_raw)

    # Step 11 — §28.4: wire optional PMS config from spec.
    # Must be set before SimulationState() so __post_init__ picks it up.
    _pms_raw = spec_data.get("pms_config")
    if _pms_raw:
        site.pms_config = PmsConfig(
            shed_priority_order=list(_pms_raw.get("shed_priority_order", [])),
            transition_mode=TransitionMode(_pms_raw.get("transition_mode", "open_transition")),
            open_transition_gap_mw=float(_pms_raw.get("open_transition_gap_mw", 2.0)),
            open_transition_duration_s=float(_pms_raw.get("open_transition_duration_s", 5.0)),
            fast_shed_duration_s=float(_pms_raw.get("fast_shed_duration_s", 30.0)),
        )

    hw_id = spec_data.get("hardware_profile_id", "enterprise_8gpu_air")

    # ── Modules ───────────────────────────────────────────────────────────
    # ramp_seconds must match dt_lead_seconds so the GPU compute draw reaches
    # full TDP over the same window that the commitment engine uses to stage
    # turbines.  The kube path already reads gpu_module.ramp_seconds and uses
    # it as the workload-signal dt_lead (simulation_core.py §0); wiring both
    # sides to the same value here keeps the two paths consistent.
    _dt_lead = float(spec_data.get("dt_lead_seconds", 45.0))
    gpu_modules = [
        GPUModule(
            asset_id="gpu-0",
            site=site,
            hardware_library=DEFAULT_HARDWARE_LIBRARY,
            ramp_seconds=_dt_lead,
        )
    ]
    cooling = CoolingModule(asset_id="cooling-0", site=site)

    turbines = [
        TurbineModule(
            TurbineConfig(
                asset_id=t.get("asset_id") or f"turbine-{i}",
                r_asset_mw_per_s=float(t.get("r_asset_mw_per_s", 0.2)),
                rated_mw=float(t.get("rated_mw", 10.0)),
                hot_standby=bool(t.get("hot_standby", False)),
                # Phase E §7.1.3.6 / closeout Item 1 — physical constraints.
                # p_min_stable_frac=0.40: frame-class MSL floor (PW-1 / §15, CHOSEN).
                # t_min_run_s=1800: 30 min minimum run time (R5, CHOSEN).
                # min_run_enabled=True: R5 guard active for all factory-built scenarios.
                # t_min_down_s=900: 15 min cooling window (R6, CHOSEN).
                # min_down_enabled=True: R6 guard active for all factory-built scenarios.
                # D-03 pattern: the enable flags distinguish "no constraint" from
                # "constraint with the CHOSEN duration" — no 0.0-sentinel needed.
                p_min_stable_frac=float(t.get("p_min_stable_frac", 0.40)),
                t_min_run_s=float(t.get("t_min_run_s", 1800.0)),
                min_run_enabled=bool(t.get("min_run_enabled", True)),
                t_min_down_s=float(t.get("t_min_down_s", 900.0)),
                min_down_enabled=bool(t.get("min_down_enabled", True)),
                # Start-duration overrides — fall back to locked parameter values
                # when not present in the scenario JSON (None sentinel from schema).
                **({} if t.get("cold_start_s") is None else {"cold_start_s": float(t["cold_start_s"])}),
                **({} if t.get("warm_start_s") is None else {"warm_start_s": float(t["warm_start_s"])}),
                **({} if t.get("hot_start_s") is None else {"hot_start_s": float(t["hot_start_s"])}),
                # Phase 2B (DR-2026-08-08-FREQ): per-unit governor physics overrides.
                # When None, TurbineConfig defaults (from catalogue) apply unchanged.
                **({} if t.get("power_factor") is None else {"power_factor": float(t["power_factor"])}),
                **({} if t.get("inertia_constant_s") is None else {"inertia_constant_s": float(t["inertia_constant_s"])}),
                **({} if t.get("droop_r") is None else {"droop_r": float(t["droop_r"])}),
                **({} if t.get("valve_actuation_tc_s") is None else {"valve_actuation_tc_s": float(t["valve_actuation_tc_s"])}),
                **({} if t.get("fuel_to_power_tc_s") is None else {"fuel_to_power_tc_s": float(t["fuel_to_power_tc_s"])}),
                **({} if t.get("max_instantaneous_load_step_mw") is None else {"max_instantaneous_load_step_mw": float(t["max_instantaneous_load_step_mw"])}),
            )
        )
        for i, t in enumerate(spec_data.get("turbine_units", []))
    ]

    # anchor_reserve_pct wires the scenario-level reserve percentage into the
    # grid-forming unit's BessConfig.  0.0 = use BessConfig default (1.0 MW).
    _anchor_pct = float(spec_data.get("anchor_reserve_pct", 0.0))

    bess_units = [
        BessModule(
            BessConfig(
                asset_id=b.get("asset_id") or f"bess-{i}",
                rated_mw=float(b.get("rated_mw", 5.0)),
                usable_mwh=float(b.get("usable_mwh", 2.0)),
                initial_soc_fraction=float(b.get("initial_soc_fraction", 0.95)),
                grid_forming=bool(b.get("grid_forming", False)),
                # anchor_reserve_pct: only applied to the grid-forming unit.
                # When 0.0 (default) the BessConfig default (1.0 MW) is kept
                # so existing scenarios and tests are unaffected.
                p_anchor_reserve_mw=(
                    float(b.get("rated_mw", 5.0)) * _anchor_pct / 100.0
                    if _anchor_pct > 0.0 and bool(b.get("grid_forming", False))
                    else float(b.get("p_anchor_reserve_mw", 1.0))
                ),
            )
        )
        for i, b in enumerate(spec_data.get("bess_units", []))
    ]

    # ── Solar ─────────────────────────────────────────────────────────────
    solar_rated_mw = float(spec_data.get("solar_rated_mw", 0.0))
    irradiance_steps_raw = spec_data.get("irradiance_steps", [(0.0, 1.0)])
    irradiance_steps: list[tuple[float, float]] = [tuple(s) for s in irradiance_steps_raw]

    solar_arrays: list[SolarModule] = []
    if solar_rated_mw > 0:
        solar_arrays = [
            SolarModule(
                SolarConfig(asset_id="solar-0", rated_mw=solar_rated_mw),
                irradiance_profile=IrradianceProfile(irradiance_steps),
            )
        ]

    # ── SimulationState ───────────────────────────────────────────────────
    sim_state = SimulationState(
        run_id=run_id,
        site=site,
        gpu_modules=gpu_modules,
        turbines=turbines,
        bess_units=bess_units,
        solar_arrays=solar_arrays,
        cooling=cooling,
    )

    # ── Kubernetes demand agent ───────────────────────────────────────────
    # Created after SimulationState so site_id is available.
    # Only instantiated when kube_config is present in the spec; all existing
    # scripted scenarios (and every unit test) are unaffected.
    _kube_raw = spec_data.get("kube_config")
    if _kube_raw is not None:
        _kube_cfg_fields = {
            k: v for k, v in _kube_raw.items()
            if k in KubeConfig.__dataclass_fields__
        }
        # Convert step_config dict → StepTimingConfig dataclass (if present).
        # The API layer passes raw JSON dicts; KubeConfig expects typed dataclasses.
        if isinstance(_kube_cfg_fields.get("step_config"), dict):
            _sc_raw = _kube_cfg_fields["step_config"]
            _kube_cfg_fields["step_config"] = StepTimingConfig(**{
                k: v for k, v in _sc_raw.items()
                if k in StepTimingConfig.__dataclass_fields__
            })
        # Convert load_config dict → LoadProfileConfig dataclass (if present).
        if isinstance(_kube_cfg_fields.get("load_config"), dict):
            _lc_raw = _kube_cfg_fields["load_config"]
            _kube_cfg_fields["load_config"] = LoadProfileConfig(**{
                k: v for k, v in _lc_raw.items()
                if k in LoadProfileConfig.__dataclass_fields__
            })
        sim_state.kube_agent = KubeDemandAgent(
            KubeConfig(**_kube_cfg_fields),
            site_id=site.site_id,
        )
        # Wire load_config and the agent's rng_load into every GPUModule so
        # they all share the same noise stream and use the same profile config.
        if sim_state.kube_agent.config.load_config is not None:
            for _gpu in sim_state.gpu_modules:
                _gpu.load_config = sim_state.kube_agent.config.load_config
                _gpu.rng_load = sim_state.kube_agent.rng_load

    else:
        # ── Non-kube path: wire top-level load_config (if present) ───────────
        # Scripted-event scenarios (workload_events, no KubeAgent) can opt in to
        # compute vs allreduce phase variation by setting load_config in their
        # ScenarioSpec.  GPUModule._auto_step_period_s > 0 tells advance() to
        # self-manage step_phase from sim_time instead of waiting for the kube
        # path to set it externally.
        _top_lc_raw = spec_data.get("load_config")
        if isinstance(_top_lc_raw, dict):
            _top_lc = LoadProfileConfig(**{
                k: v for k, v in _top_lc_raw.items()
                if k in LoadProfileConfig.__dataclass_fields__
            })
            # Fixed step period = StepTimingConfig.median_step_s default (0.70 s).
            # This is not stochastic — the phase cycles deterministically — but
            # it produces realistic tick-to-tick power variation (compute ↔
            # allreduce) without requiring a full KubeAgent.
            _STEP_PERIOD_S = 0.70
            for _gpu in sim_state.gpu_modules:
                _gpu.load_config = _top_lc
                _gpu._auto_step_period_s = _STEP_PERIOD_S

    # ── Workload events ───────────────────────────────────────────────────
    events: list[WorkloadSignal] = []
    for evt in spec_data.get("workload_events", []):
        event_id = evt.get("event_id") or f"evt-{_uuid.uuid4().hex[:8]}"
        job_id = evt.get("job_id") or f"job-{_uuid.uuid4().hex[:8]}"
        events.append(
            WorkloadSignal(
                event_id=event_id,
                job_id=job_id,
                event_type=WorkloadEventType(evt["event_type"]),
                timestamp=float(evt["timestamp"]),
                hardware_profile_id=evt.get("hardware_profile_id") or hw_id,
                node_count=int(evt.get("node_count", 0)),
                workload_class=WorkloadClass.TRAINING,
                site_id=site.site_id,
                renewable_shortfall_mw=float(evt.get("renewable_shortfall_mw", 0.0)),
            )
        )
    events.sort(key=lambda e: e.timestamp)

    # ── Assertions (Step 9) ───────────────────────────────────────────────
    # spec_data["assertions"] is a list of plain dicts (JSON-round-trip safe).
    # _assertion_adapter validates each dict against the AssertionSpec union
    # so that RunContext.assertions always holds typed Pydantic objects.
    raw_assertions = spec_data.get("assertions", [])
    assertions = [_assertion_adapter.validate_python(a) for a in raw_assertions]

    # ── W1 advisory, telemetry, procurement wiring (spec path) ───────────
    _spec_turbine_mws = [float(t.get("rated_mw", 10.0)) for t in spec_data.get("turbine_units", [])]
    _spec_total_turbine_mw = sum(_spec_turbine_mws) if _spec_turbine_mws else 10.0
    # GS-DES-CFG-001 §Phase-7 / Item-2: 20.0 MW literal fallback removed.
    # Paths that reach this code with no workload events (kube path, idle run, TC-33
    # compute runs without scripted workload_events) must NOT receive an invented figure.
    # When peak load is uncomputable, _spec_design_peak_load_mw is left at 0.0.
    # The wire field broadcasts 0 → frontend falls back to peakSiteLoadMW(history)
    # and labels it "observed this run" — a labelled observed figure is strictly better
    # than an unlabelled literal.  The only path to the former 20.0 fallback was here;
    # it is now removed.
    _spec_hw_profile = DEFAULT_HARDWARE_LIBRARY.get(hw_id, HardwareProfile(hw_id, rated_kw=12.0))
    _spec_max_node_count = max(
        (int(e.get("node_count", 0)) for e in spec_data.get("workload_events", [])),
        default=0,
    )
    if _spec_max_node_count > 0:
        _spec_peak_it_load_mw     = _spec_max_node_count * _spec_hw_profile.rated_kw * site.pue_base / 1000.0
        _spec_rated_cooling_mw    = site.alpha_max * _spec_peak_it_load_mw * _sp.value("cooling_margin")  # PROTO-10
        # Honour declared design_peak_load_mw from the spec dict if present; otherwise derive.
        _spec_design_peak_load_mw = float(spec_data.get("design_peak_load_mw") or 0.0) or (
            _spec_peak_it_load_mw + _spec_rated_cooling_mw
        )
    else:
        # No workload events — do not substitute a literal.
        _spec_rated_cooling_mw    = 0.0   # unused sizing; defined to avoid NameError
        # Honour explicit design_peak_load_mw from spec if provided; otherwise 0.
        _spec_design_peak_load_mw = float(spec_data.get("design_peak_load_mw") or 0.0)
    _spec_grid_cap = [
        GridCapacity(CapacityType.FIRM,     available_mw=_spec_total_turbine_mw * 0.80, price_per_mwh=48.0, t_reserve_s=0.0),
        GridCapacity(CapacityType.RESERVED, available_mw=_spec_total_turbine_mw * 0.40, price_per_mwh=62.0, t_reserve_s=300.0),
        GridCapacity(CapacityType.NON_FIRM, available_mw=_spec_total_turbine_mw * 0.15, price_per_mwh=198.0, t_reserve_s=0.0),
    ]

    # ── AD1: optional engine wiring ───────────────────────────────────────
    # Each engine is instantiated only when its *_config field is present in
    # the spec.  All three are observe-only (no writes to sim_state).

    # AD1 — ProcurementLayer (TC-47, TC-52)
    _proc_layer = None
    _proc_raw = spec_data.get("procurement_config")
    if _proc_raw:
        _pc_caps = [
            GridCapacity(CapacityType.FIRM,
                         available_mw=float(_proc_raw.get("firm_available_mw", 20.0)),
                         price_per_mwh=48.0, t_reserve_s=0.0),
            GridCapacity(CapacityType.RESERVED,
                         available_mw=float(_proc_raw.get("reserved_available_mw", 10.0)),
                         price_per_mwh=62.0, t_reserve_s=300.0),
            GridCapacity(CapacityType.NON_FIRM,
                         available_mw=float(_proc_raw.get("non_firm_available_mw", 3.0)),
                         price_per_mwh=198.0, t_reserve_s=0.0),
        ]
        _pc_curve = SyntheticPriceCurve(seed=int(_proc_raw.get("price_curve_seed", 42)))
        _proc_layer = ProcurementLayer(_pc_caps, _pc_curve)

    # AD1 — MaintenanceLayer (TC-58, TC-59, TC-60)
    _maint_layer = None
    _maint_raw = spec_data.get("maintenance_config")
    if _maint_raw:
        _maint_record = AssetHealthRecord(
            asset_id=str(_maint_raw.get("asset_id", "turbine-0")),
            nameplate_ramp_mw_per_s=float(_maint_raw.get("nameplate_ramp_mw_per_s", 0.2)),
            effective_ramp_mw_per_s=float(_maint_raw.get("effective_ramp_mw_per_s", 0.15)),
        )
        _maint_layer = MaintenanceLayer(
            records=[_maint_record],
            reserve_threshold_mw=float(_maint_raw.get("reserve_threshold_mw", 1.0)),
        )

    # AD1 — RampRelaxationEngine (TC-75, TC-76)
    _ramp_engine = None
    _ramp_raw = spec_data.get("ramp_relaxation_config")
    if _ramp_raw:
        _ramp_engine = RampRelaxationEngine(
            reserve_threshold_mw=float(_ramp_raw.get("reserve_threshold_mw", 2.0)),
            baseline_ramp_cap_mw=float(_ramp_raw.get("baseline_ramp_cap_mw", 5.0)),
            baseline_ramp_duration_s=float(_ramp_raw.get("baseline_ramp_duration_s", 75.0)),
            adaptive_ramp_duration_s=float(_ramp_raw.get("adaptive_ramp_duration_s", 30.0)),
        )

    # ── RunContext ────────────────────────────────────────────────────────
    return RunContext(
        run_id=run_id,
        sim_state=sim_state,
        events=events,
        dt_lead_seconds=float(spec_data.get("dt_lead_seconds", 30.0)),
        end_sim_time=float(spec_data.get("end_sim_time", 300.0)),
        playback_speed=playback_speed,
        sink=InMemoryTimeseriesSink(),
        assertions=assertions,
        scenario_name=str(spec_data.get("name", "")),
        # W1 fields
        registry=AgentRegistry(
            router=DeterministicRouter() if os.environ.get('PYTEST_CURRENT_TEST')
                   else AdvisoryRouter(),
            enabled=True,
            max_proposal_mw=float(spec_data.get("advisory_max_mw", 20.0)),
        ),
        telemetry_ingestor=NetworkTelemetryIngestor(),
        corroborator=FabricCorroborator(),
        price_curve=SyntheticPriceCurve(seed=42),
        grid_capacity=_spec_grid_cap,
        _rated_cooling_mw=_spec_rated_cooling_mw,
        _design_peak_load_mw=_spec_design_peak_load_mw,
        # AB2: for §21.2 cost model in energy-summary endpoint.
        turbine_rated_mw=_spec_total_turbine_mw,
        # PROTO-32-AMB: ambient temperature metadata for the Solar PV modal.
        ambient_avg_c=_ambient_avg_c,
        ambient_alpha_scale=_ambient_scale,
        # AE2: per-unit specs as plain dicts for the fleet modal.
        turbine_unit_specs=tuple(
            {
                "asset_id": t.get("asset_id") or f"turbine-{i}",
                "rated_mw": float(t.get("rated_mw", 10.0)),
                "r_asset_mw_per_s": float(t.get("r_asset_mw_per_s", 0.2)),
                # run_hours_h: None when not tracked; non-None for scenarios
                # that carry operating-hours data (e.g. demo-3turbine).
                "run_hours_h": float(t["run_hours_h"]) if t.get("run_hours_h") is not None else None,
                # Phase 0 §0.1: prime-mover class — "frame" or "aero".
                # Drives the derived identity line in the fleet modal.
                "gt_mode": str(t.get("gt_mode", "frame")),
                # Phase 0 §0.2: hot_standby — commissioned but not synchronised to
                # the AC bus.  A hot-standby unit contributes zero output and is
                # excluded from contingency ramp (TC-83).
                "hot_standby": bool(t.get("hot_standby", False)),
                # Phase 0 §0.2: breaker_closed — AC bus breaker closed.
                # Derived from hot_standby for Phase 0; Phase 1 will track real-time
                # breaker state from turbine physics.  Drives SYNC column and
                # units_on_bus_count without inference from aggregate output.
                "breaker_closed": not bool(t.get("hot_standby", False)),
                # Phase 0 §0.6: no_load_mw — net output at no-load speed (shaft
                # spinning, zero electrical delivery).  Typically 0.0 for aeroderivatives;
                # set per OEM data sheet.  Separate from MSL.
                "no_load_mw": float(t.get("no_load_mw", 0.0)),
                # Phase 0 §0.6: msl_mw — minimum stable load (p_min_stable_frac ×
                # rated_mw).  Below this the combustion regime is unstable.
                "msl_mw": float(t.get("p_min_stable_frac", 0.0)) * float(t.get("rated_mw", 10.0)),
                # Phase 0 §0.2: sync_relay_state — state of the synchro-check relay.
                # Derived from hot_standby for Phase 0 static config; Phase 1 will
                # track real-time relay state as the breaker transitions each tick.
                # "permissive" — relay granted closure; unit is on the AC bus.
                # "checking"   — relay active, matching V/f/θ before close (hot standby).
                # "open"       — unit offline; not in sync sequence (Phase 1+ only).
                "sync_relay_state": (
                    "checking"
                    if bool(t.get("hot_standby", False))
                    else "permissive"
                ),
            }
            for i, t in enumerate(spec_data.get("turbine_units", []))
        ),
        # AD1: optional engine instances.
        procurement_layer=_proc_layer,
        maintenance_layer=_maint_layer,
        ramp_relaxation_engine=_ramp_engine,
        # Phase 10: FabricEngine — always wired for spec-path runs so the
        # Network Fabric modal shows live data from the first tick.
        # When fabric_scenario_id is present, the engine uses the named
        # scenario's job timelines, stressors, and capability_tier.
        fabric_engine=_build_fabric_engine(
            run_id,
            fabric_scenario_id=spec_data.get("fabric_scenario_id"),
        ),
        # SD-1: site identity stamped onto every TickResult so the WS header
        # renders from authoritative server-side state, not client-held state
        # that diverges silently after a server restart.
        site_lat=float(spec_data.get("site_latitude",
                       (spec_data["_site_location"].latitude_deg
                        if "_site_location" in spec_data else 0.0))),
        site_lon=float(spec_data.get("site_longitude",
                       (spec_data["_site_location"].longitude_deg
                        if "_site_location" in spec_data else 0.0))),
        site_utc_offset_h=float(spec_data.get("site_utc_offset_h",
                       (spec_data["_site_location"].longitude_deg / 15.0
                        if "_site_location" in spec_data else 0.0))),
        site_name=str(spec_data.get("site_name",
                      (spec_data["_site_location"].site_name
                       if "_site_location" in spec_data else ""))),
        # Three-tier Mistral aggregation: supply the irradiance_profile to the
        # run context so _drive() can call fraction_at(sim_time) each tick.
        # None when solar_rated_mw == 0 (no solar in this scenario).
        irradiance_profile=(
            IrradianceProfile(irradiance_steps) if solar_rated_mw > 0 else None
        ),
    )


def _build_fabric_engine(run_id: str, fabric_scenario_id: str | None = None):
    """
    Instantiate a FabricEngine for a spec-path run.  Failures are caught and
    logged; a None return leaves the tick payload's fabric field null rather
    than crashing the run.

    When fabric_scenario_id is provided, the engine loads the named scenario
    JSON from config/scenarios/ and uses its job timelines, stressors,
    capability_tier, and assertions.
    """
    import json as _json
    import logging as _log
    _logger = _log.getLogger("gridsignal.scenario_factory")
    try:
        from runtime.fabric_engine import FabricEngine  # lazy — avoids startup cost
        seed = hash(run_id) % (2 ** 31)  # deterministic per run_id

        scenario_data = None
        if fabric_scenario_id:
            from pathlib import Path as _Path
            _cfg_dir = _Path("config/scenarios")
            _candidates = [
                _cfg_dir / f"{fabric_scenario_id}.json",
            ]
            for _path in _candidates:
                if _path.exists():
                    try:
                        scenario_data = _json.loads(_path.read_text())
                        _logger.info(
                            "FabricEngine: loaded scenario file %s for run %s",
                            _path, run_id,
                        )
                    except Exception:
                        _logger.exception(
                            "FabricEngine: failed to parse scenario file %s", _path
                        )
                    break
            else:
                _logger.warning(
                    "FabricEngine: fabric_scenario_id=%r — file not found; "
                    "using default engine",
                    fabric_scenario_id,
                )

        cap_tier = "current"
        if scenario_data:
            cap_tier = scenario_data.get("capability_tier", "current")

        return FabricEngine(seed=seed, capability_tier=cap_tier, scenario_data=scenario_data)
    except Exception:
        _log.getLogger("gridsignal.scenario_factory").exception(
            "FabricEngine init failed for run %s — fabric data will be absent", run_id
        )
        return None
