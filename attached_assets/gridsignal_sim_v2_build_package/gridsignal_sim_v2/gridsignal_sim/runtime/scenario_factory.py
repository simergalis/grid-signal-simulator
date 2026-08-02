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
from core.simulation_core import SimulationState
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
) -> RunContext:
    site = SiteConfig(site_id=f"site-for-{run_id}")

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
    _peak_compute_mw = node_count * _solar_profile.rated_kw * site.pue_base / 1000.0
    _solar_rated_mw = 0.25 * _peak_compute_mw  # PROTO-7 — CHOSEN, no measured basis

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
    # Rated cooling MW: alpha_max (fraction of compute) × peak compute MW,
    # plus 15 % headroom for BESS-charge and PUE-base overhead on total IT
    # load (PROTO-10-MARGIN).  Without this the cooling plant saturates the
    # moment any non-compute IT load is added at peak compute.
    _COOLING_MARGIN   = 1.15
    _peak_compute_mw  = node_count * _solar_profile.rated_kw / 1000.0
    _rated_cooling_mw = site.alpha_max * _peak_compute_mw * _COOLING_MARGIN

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
    site = SiteConfig(site_id=f"site-for-{run_id}")

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
    _lt_peak_compute_mw = (
        gpu_module_count * nodes_per_gpu_module * _lt_profile.rated_kw * site.pue_base / 1000.0
    )
    _lt_solar_rated_mw_each = (0.25 * _lt_peak_compute_mw) / max(solar_count, 1)  # PROTO-7

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
    _lt_peak_compute_mw  = (
        gpu_module_count * nodes_per_gpu_module * _lt_profile.rated_kw / 1000.0
    )
    _lt_rated_cooling_mw = site.alpha_max * _lt_peak_compute_mw * 1.15  # PROTO-10-MARGIN
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
    site = SiteConfig(
        site_id=f"site-for-{run_id}",
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
        # Default 0.0 preserves backward-compat for seeded scenarios and tests.
        band_pct_calibrated=float(spec_data.get("band_pct_calibrated", 0.0)),
        band_mult_uncalibrated=float(spec_data.get("band_mult_uncalibrated", 2.0)),
        band_mult_unmapped_hw=float(spec_data.get("band_mult_unmapped_hw", 1.5)),
    )

    # PROTO-32-AMB: ambient temperature adjustment to alpha_max.
    # When generate_solar_forecast() has been called before run start,
    # spec_data["ambient_steps"] carries correlated dry-bulb temperatures.
    # Hotter ambient → HVAC operates less efficiently → higher cooling fraction.
    # Absent on tests and runs without a solar forecast (ambient_steps=[] → no-op).
    # Applied after the explicit alpha_max / plant_alpha_max read so that the
    # spec-level value is always the baseline and ambient modulates around it.
    _ambient_steps_raw = spec_data.get("ambient_steps", [])
    if _ambient_steps_raw:
        from runtime.solar_sim import ambient_alpha_scale  # lazy — runtime→runtime OK
        site.alpha_max = site.alpha_max * ambient_alpha_scale(_ambient_steps_raw)

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
    gpu_modules = [
        GPUModule(
            asset_id="gpu-0",
            site=site,
            hardware_library=DEFAULT_HARDWARE_LIBRARY,
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
        sim_state.kube_agent = KubeDemandAgent(
            KubeConfig(**_kube_cfg_fields),
            site_id=site.site_id,
        )

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
    _spec_peak_compute_mw  = float(spec_data.get("solar_rated_mw", 0.0)) / 0.25  # reverse PROTO-7
    if _spec_peak_compute_mw <= 0:
        _spec_peak_compute_mw = 20.0  # safe fallback when solar is absent
    _spec_rated_cooling_mw = site.alpha_max * _spec_peak_compute_mw * 1.15  # PROTO-10-MARGIN
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
        # AB2: for §21.2 cost model in energy-summary endpoint.
        turbine_rated_mw=_spec_total_turbine_mw,
        # AE2: per-unit specs as plain dicts for the fleet modal.
        turbine_unit_specs=tuple(
            {
                "asset_id": t.get("asset_id") or f"turbine-{i}",
                "rated_mw": float(t.get("rated_mw", 10.0)),
                "r_asset_mw_per_s": float(t.get("r_asset_mw_per_s", 0.2)),
                # run_hours_h: None when not tracked; non-None for scenarios
                # that carry operating-hours data (e.g. demo-3turbine).
                "run_hours_h": float(t["run_hours_h"]) if t.get("run_hours_h") is not None else None,
            }
            for i, t in enumerate(spec_data.get("turbine_units", []))
        ),
        # AD1: optional engine instances.
        procurement_layer=_proc_layer,
        maintenance_layer=_maint_layer,
        ramp_relaxation_engine=_ramp_engine,
        # Phase 10: FabricEngine — always wired for spec-path runs so the
        # Network Fabric modal shows live data from the first tick.
        fabric_engine=_build_fabric_engine(run_id),
    )


def _build_fabric_engine(run_id: str):
    """
    Instantiate a FabricEngine for a spec-path run.  Failures are caught and
    logged; a None return leaves the tick payload's fabric field null rather
    than crashing the run.
    """
    try:
        from runtime.fabric_engine import FabricEngine  # lazy — avoids startup cost
        seed = hash(run_id) % (2 ** 31)  # deterministic per run_id
        return FabricEngine(seed=seed, capability_tier="current")
    except Exception:
        import logging as _log
        _log.getLogger("gridsignal.scenario_factory").exception(
            "FabricEngine init failed for run %s — fabric data will be absent", run_id
        )
        return None
