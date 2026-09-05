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
    DieselModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.fuel_cell_module import (
    BlockFuelCellArray,
    BlockFuelCellConfig,
    BlockFuelCellFleet,
    FuelSystemConfig,
    FuelCellConfig,
    FuelCellModule,
    FuelCellState,
)
from core.models import (
    BessConfig,
    DieselConfig,
    HardwareProfile,
    IslandMode,
    PmsConfig,
    PreStagingConfig,
    SiteConfig,
    SolarConfig,
    ThermalState,
    TransitionMode,
    TurbineConfig,
    TurbineState,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.kube_demand import KubeConfig, KubeDemandAgent
from core.step_config import LoadProfileConfig, StepTimingConfig
from core.simulation_core import SimulationState, TenantBurstEvent
from core.generation_factory import compute_floor_mw as _compute_floor_mw
from api.schemas import (
    TENANT_CONTRACTED_MW as _TENANT_CONTRACTED_MW,
    _DEFAULT_TENANT_CONTRACTED_MW as _DEFAULT_TENANT_MW,
)
import core.site_parameters as _sp  # GS-DES-CFG-001 §Phase-6
from pydantic import TypeAdapter

from runtime.run_manager import InMemoryTimeseriesSink, RunContext
from runtime.pms_test_double import OperatorResponseProfile as _OperatorResponseProfile
from runtime.verdict import AssertionSpec as _AssertionSpec

# W1 — advisory, telemetry, and procurement wiring.
# Imported here (runtime/) not in run_manager (would create circular import
# because advisory/ imports from runtime/advisory_gate).
from runtime.advisory_router import AdvisoryRouter, DeterministicRouter
from advisory.agent_registry import AgentRegistry
from runtime.fuel_cell_readiness import BlockFuelCellReadinessController
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
from core.power_source_priority import (
    AuthorityTier as _AuthorityTier,
    PowerSource as _PowerSource,
    PowerSourceType as _PowerSourceType,
    ResponseLatencyClass as _ResponseLatencyClass,
)

# TypeAdapter for deserialising assertion specs from plain dicts in
# build_run_context_from_spec.  Created once at module level (not per-call)
# to avoid repeated schema compilation overhead.
_assertion_adapter: TypeAdapter = TypeAdapter(_AssertionSpec)

# A simulation calendar must be part of its inputs.  Direct factory paths do
# not accept a calendar override, so use this stable baseline rather than the
# machine's wall clock.
_DEFAULT_EDL_CALENDAR_MONTH = 1


DEFAULT_HARDWARE_LIBRARY = {
    "enterprise_8gpu_air": HardwareProfile(
        "enterprise_8gpu_air",
        rated_kw=10.2,
        description="H100-class 8-GPU air-cooled node",
        counting_unit="chassis",
        gpus_per_unit=8,
        vintage_generation="h100",
    ),
    # Canonical profile emitted by the Slurm adapter for
    # gres/gpu:h100 allocations.  Keep it physically equivalent to the
    # existing H100-class node profile while preserving the external profile
    # identity required by the WorkloadSignal contract.
    "h100-sxm5-8way-nvl4": HardwareProfile(
        "h100-sxm5-8way-nvl4",
        rated_kw=10.2,
        description="H100 SXM5 8-GPU NVLink node",
        counting_unit="chassis",
        gpus_per_unit=8,
        vintage_generation="h100",
    ),
    "nextgen_rack_liquid": HardwareProfile(
        "nextgen_rack_liquid",
        rated_kw=120.0,
        description="GB200 NVL72-class 120 kW liquid-cooled rack",
        counting_unit="cabinet",
        gpus_per_unit=72,
        vintage_generation="gb200-nvl72",
    ),
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
    # The convenience factory represents an already operating facility.  The
    # scenario-spec factory below deliberately does not do this: its authored
    # fleet starts OFFLINE and exercises the sequential commitment path.
    for turbine in turbines:
        turbine.state = TurbineState.SYNCHRONISED
        turbine._current_output_mw = 0.0
        turbine._run_start_s = 0.0

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

    # ── EDL sources (PSP-002 §3.2 / Task #371) ───────────────────────────
    # Wire the single BESS unit + grid so EconomicDispatchLoop.step() runs
    # every tick for direct-path runs (tests and the legacy API path).
    # build_run_context_from_spec handles spec-path runs independently.
    _brc_edl_sources = [
        _PowerSource(
            source_id="bess-0",
            source_type=_PowerSourceType.BESS,
            dispatchable=True,
            counts_toward_reserve=True,
            marginal_cost_mwh=float(_sp.value("bess_marginal_cost_mwh")),
            response_latency_class=_ResponseLatencyClass.INSTANT,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            available_mw=float(bess_rated_mw),
            cost_basis_note="cycle amortisation (PSP-6)",
        ),
        _PowerSource(
            source_id="grid-firm",
            source_type=_PowerSourceType.GRID_FIRM,
            dispatchable=True,
            counts_toward_reserve=False,
            marginal_cost_mwh=float(_sp.value("pge_tou_summer_off_peak_mwh")),
            response_latency_class=_ResponseLatencyClass.INSTANT,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            available_mw=999.0,
            cost_basis_note="PG&E B-20 TOU placeholder — repriced per tick by EDL.step()",
        ),
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
        # PSP-002 §3.2 / Task #371 — activate per-tick EDL for direct-path runs.
        edl_sources=_brc_edl_sources,
        edl_calendar_month=_DEFAULT_EDL_CALENDAR_MONTH,
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

    # ── EDL sources (PSP-002 §3.2 / Task #371) ───────────────────────────
    # Wire all BESS units + grid so EconomicDispatchLoop.step() runs every
    # tick in load-test runs.  BESS units match the bess_count / bess_rated_mw
    # parameters supplied by the caller.
    _lt_edl_sources = [
        _PowerSource(
            source_id=f"bess-{_i}",
            source_type=_PowerSourceType.BESS,
            dispatchable=True,
            counts_toward_reserve=True,
            marginal_cost_mwh=float(_sp.value("bess_marginal_cost_mwh")),
            response_latency_class=_ResponseLatencyClass.INSTANT,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            available_mw=float(bess_rated_mw),
            cost_basis_note="cycle amortisation (PSP-6)",
        )
        for _i in range(bess_count)
    ] + [
        _PowerSource(
            source_id="grid-firm",
            source_type=_PowerSourceType.GRID_FIRM,
            dispatchable=True,
            counts_toward_reserve=False,
            marginal_cost_mwh=float(_sp.value("pge_tou_summer_off_peak_mwh")),
            response_latency_class=_ResponseLatencyClass.INSTANT,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            available_mw=999.0,
            cost_basis_note="PG&E B-20 TOU placeholder — repriced per tick by EDL.step()",
        ),
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
            # LP-1 / GS-IMPL-LOADPERF-001: load test always uses the
            # deterministic router — no network calls, no Mistral/Anthropic
            # I/O — so the 30 s wall-clock NFR is not inflated by LLM
            # round-trips.  DeterministicRouter is a subclass of
            # AdvisoryRouter with has_agent==True and no outbound HTTP.
            # Other callers (build_run_context, build_run_context_from_spec)
            # are unchanged and continue to honour LP-1 key presence.
            router=DeterministicRouter(),
            # GS-IMPL-LOADPERF-001: load test measures simulation throughput,
            # not advisory quality.  Agents must be disabled so the advisory
            # pipeline CPU cost (deidentify → _make_bin → statistics.mean,
            # GIL-serialized across concurrent runs in the shared
            # _ADVISORY_EXECUTOR thread pool) does not inflate the 30 s
            # wall-clock NFR.  DeterministicRouter already removes network I/O
            # (prior commit); this flag removes the remaining binning/stats
            # work by short-circuiting run_all() before it touches self._agents.
            # Use build_run_context() or build_run_context_from_spec() for
            # contexts that require live advisory proposals.
            enabled=False,
        ),
        telemetry_ingestor=NetworkTelemetryIngestor(),
        corroborator=FabricCorroborator(),
        price_curve=SyntheticPriceCurve(seed=42),
        grid_capacity=_lt_grid_cap,
        _rated_cooling_mw=_lt_rated_cooling_mw,
        _design_peak_load_mw=_lt_design_peak_load_mw,
        # PSP-002 §3.2 / Task #371 — activate per-tick EDL for load-test runs.
        edl_sources=_lt_edl_sources,
        edl_calendar_month=_DEFAULT_EDL_CALENDAR_MONTH,
    )


# ---------------------------------------------------------------------------
# Step 8: build_run_context_from_spec
# ---------------------------------------------------------------------------

def validate_fuel_cell_source_consistency(spec_data: dict) -> None:
    """Reject a disabled Fuel Cell Module Array before a run can start.

    ``fuel_cell_units`` is the authoritative declaration of the
    block-addressable array.  Keeping a legacy ``fuel_cell_enabled=false``
    beside it previously let an author describe an array as disabled while
    the block path still built it.  That ambiguity is unsafe for every caller
    of the spec factory, including future run-start endpoints.
    """
    if not spec_data.get("fuel_cell_units"):
        return
    if "fuel_cell_enabled" not in spec_data:
        # Direct factory callers may supply pre-schema legacy dictionaries.
        # Preserve the same effective-enable rule that ScenarioSpec applies.
        spec_data["fuel_cell_enabled"] = True
        return
    if not spec_data["fuel_cell_enabled"]:
        raise ValueError(
            "Fuel Cell Module Array is declared by fuel_cell_units but "
            "fuel_cell_enabled is false. Set fuel_cell_enabled=true. For a "
            "legitimate absent-array experiment, use a named scenario variant "
            "or a named UNIT_TRIP event; do not disable the array with this toggle."
        )


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
    validate_fuel_cell_source_consistency(spec_data)

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
        grid_import_limit_mw=(
            float(spec_data["grid_import_limit_mw"])
            if spec_data.get("grid_import_limit_mw") is not None
            else None
        ),
        bess_normal_dispatch_depth_fraction=float(
            spec_data.get("bess_normal_dispatch_depth_fraction", 0.0)
        ),
        bess_bridging_floor_fraction=float(spec_data.get("bess_bridging_floor_fraction", _sp.value("bess_bridging_floor_fraction"))),
        bess_bridging_floor_anchor_multiple=float(spec_data.get("bess_bridging_floor_anchor_multiple", _sp.value("bess_bridging_floor_anchor_multiple"))),
        bess_material_discharge_fraction=float(spec_data.get("bess_material_discharge_fraction", _sp.value("bess_material_discharge_fraction"))),
        bess_material_discharge_min_mw=float(spec_data.get("bess_material_discharge_min_mw", _sp.value("bess_material_discharge_min_mw"))),
        bess_catchup_sustain_s=float(spec_data.get("bess_catchup_sustain_s", _sp.value("bess_catchup_sustain_s"))),
        bess_catchup_slope_window_s=float(spec_data.get("bess_catchup_slope_window_s", _sp.value("bess_catchup_slope_window_s"))),
        bess_catchup_bridge_margin=float(spec_data.get("bess_catchup_bridge_margin", _sp.value("bess_catchup_bridge_margin"))),
        # AD2: calibrated=True in spec → uncalibrated=False in SiteConfig.
        # Required for scenarios where the TC-43 curtailment dwell must fire
        # (e.g. demo-pms-shortfall).  Default False preserves §17.3 behaviour.
        uncalibrated=not bool(spec_data.get("calibrated", False)),
        # Scripted DQ inject windows — convert list[dict] from JSON to list[tuple].
        dq_inject_events=[
            (float(e["start_s"]), float(e["end_s"]), str(e["tag"]))
            for e in spec_data.get("dq_inject_events", [])
        ],
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

    # Cascade commit fraction — optional per-scenario override.
    # When present, the commitment engine triggers the next standby-turbine start
    # when the last on-bus active turbine's output reaches this fraction of rated.
    _cascade_raw = spec_data.get("cascade_commit_fraction")
    if _cascade_raw is not None:
        site.cascade_commit_fraction = float(_cascade_raw)

    # Deprecated fuel-cell saturation pre-commit compatibility field.
    # Retain legacy scenario JSON compatibility; the former runtime trigger
    # has been removed and this value has no effect.
    _fc_commit_raw = spec_data.get("fuel_cell_turbine_commit_fraction")
    if _fc_commit_raw is not None:
        site.fuel_cell_turbine_commit_fraction = float(_fc_commit_raw)

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
                # thermal_state: initial thermal classification (hot/warm/cold).
                # Defaults to COLD when absent or explicitly null.
                initial_thermal_state=ThermalState(t["thermal_state"])
                    if t.get("thermal_state") else ThermalState.COLD,
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

    # A fleet with one designated non-standby lead and standby followers models
    # an already-operating bus anchor: place only that lead on-bus at run start.
    # Multi-active fleets remain OFFLINE so the shared pending-start register can
    # enforce the sequential-start contract on their first and later ticks.
    _active_turbines = [t for t in turbines if not t.config.hot_standby]
    if len(_active_turbines) == 1:
        _lead_turbine = _active_turbines[0]
        _lead_turbine.state = TurbineState.SYNCHRONISED
        _lead_turbine._current_output_mw = 0.0
        _lead_turbine._run_start_s = 0.0

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

    # ── Diesel runtime modules ───────────────────────────────────────────
    # The modules are coordinated by SimulationState's fleet coordinator;
    # dispatch arbitration remains responsible for turbines and BESS.
    _diesel_block = spec_data.get("diesel_power_block") or {}
    diesel_units = [
        DieselModule(
            DieselConfig(
                asset_id=d.get("asset_id") or f"diesel-{i:03d}",
                rated_mw=float(d.get("rated_mw", _diesel_block.get("unit_rating_mw", 3.0))),
                role=str(d.get("role", "primary")),
                p_start=float(_diesel_block.get("p_start", 0.985)),
                start_offset_s=(
                    None
                    if d.get("start_offset_s") is None
                    else float(d["start_offset_s"])
                ),
                delta_t_start_s=float(d.get("delta_t_start_s", _diesel_block.get("delta_t_start_s", 10.0))),
                f_block=float(d.get("f_block", _diesel_block.get("f_block", 0.80))),
                residual_ramp_s=float(d.get("residual_ramp_s", _diesel_block.get("residual_ramp_s", 8.0))),
                min_stable_load_mw=float(d.get("min_stable_load_mw", 0.0)),
                min_run_s=float(d.get("min_run_s", _diesel_block.get("min_run_s", 900.0))),
                min_down_s=float(d.get("min_down_s", _diesel_block.get("min_down_s", 300.0))),
                cooldown_s=float(d.get("cooldown_s", _diesel_block.get("cooldown_s", 300.0))),
            )
        )
        for i, d in enumerate(spec_data.get("diesel_units", []))
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
        diesel_units=diesel_units,
        diesel_debounce_s=float(_diesel_block.get("debounce_s", 1.0)),
        diesel_restore_hold_s=float(_diesel_block.get("restore_hold_s", 300.0)),
        diesel_fuel_burn_gal_per_hr_per_unit_at_full_load=float(
            _diesel_block.get(
                "fuel_burn_gal_per_hr_per_unit_at_full_load",
                230.0,
            )
        ),
        diesel_min_fuel_runtime_hours=float(
            _diesel_block.get("min_fuel_runtime_hours", 48.0)
        ),
    )

    # ── Fuel cell rated capacity ──────────────────────────────────────────
    # G-1 units take precedence over the legacy aggregate wire fields.  The
    # aggregate path below is intentionally unchanged for existing scenarios.
    _fc_units_raw = spec_data.get("fuel_cell_units", [])
    if _fc_units_raw:
        _fc_arrays = [
            BlockFuelCellArray(
                BlockFuelCellConfig(
                    asset_id=str(unit["asset_id"]),
                    block_rated_mw=float(unit["block_rated_mw"]),
                    block_count=int(unit["block_count"]),
                    apparent_power_rating_mva_per_block=(
                        float(unit["apparent_power_rating_mva_per_block"])
                        if unit.get("apparent_power_rating_mva_per_block") is not None
                        else None
                    ),
                    initial_running_blocks=int(unit.get("initial_running_blocks", 0)),
                    initial_hot_standby_blocks=int(unit.get("initial_hot_standby_blocks", 0)),
                    requested_commit_rate_blocks_per_s=float(unit.get(
                        "requested_commit_rate_blocks_per_s",
                        unit.get("commit_rate_blocks_per_s", 1.0))),
                    decommit_rate_blocks_per_s=float(unit.get("decommit_rate_blocks_per_s", 1.0)),
                    cold_start_s=float(unit.get("cold_start_s", 8.0 * 60.0 * 60.0)),
                    warm_start_s=float(unit.get("warm_start_s", 4.0 * 60.0 * 60.0)),
                    **(
                        {}
                        if unit.get("hot_start_s") is None
                        else {"hot_start_s": float(unit["hot_start_s"])}
                    ),
                    controlled_cooling_s=(
                        float(unit["controlled_cooling_s"])
                        if unit.get("controlled_cooling_s") is not None
                        else None
                    ),
                    hot_standby=bool(unit.get("hot_standby", True)),
                    min_stable_frac=float(unit.get("min_stable_frac", 0.5)),
                    intrinsic_output_ramp_rate_mw_per_s=(
                        float(unit["intrinsic_output_ramp_rate_mw_per_s"])
                        if unit.get("intrinsic_output_ramp_rate_mw_per_s") is not None
                        else None
                    ),
                    hot_standby_floor_blocks=int(unit.get("hot_standby_floor_blocks", 0)),
                    dispatch_mechanism=str(unit.get("dispatch_mechanism", "hybrid")),
                    readiness_dwell_s=float(unit.get("readiness_dwell_s", 0.0)),
                    grid_forming=bool(unit.get("grid_forming", False)),
                    power_factor=float(unit.get("power_factor", 1.0)),
                    reactive_capability_mvar=(
                        float(unit["reactive_capability_mvar"])
                        if unit.get("reactive_capability_mvar") is not None else None),
                    ieee_1547_category=int(unit.get("ieee_1547_category", 3)),
                    provenance=dict(unit.get("provenance", {})),
                    electrical_groups=[(str(g["electrical_group_id"]), int(g["block_count"])) for g in unit.get("electrical_groups", [])],
                    beginning_of_life_heat_rate_btu_per_kwh=float(unit.get("beginning_of_life_heat_rate_btu_per_kwh", 5811.0)),
                    end_of_life_heat_rate_btu_per_kwh=float(unit.get("end_of_life_heat_rate_btu_per_kwh", 7127.0)),
                    degradation_fraction=float(unit.get("degradation_fraction", 0.5)),
                    part_load_heat_rate_multiplier=float(unit.get("part_load_heat_rate_multiplier", 1.0)),
                    gas_heating_value_btu_per_scf=float(unit.get("gas_heating_value_btu_per_scf", 1030.0)),
                    hot_standby_fuel_fraction=float(unit.get("hot_standby_fuel_fraction", 0.10)),
                    gas_price_usd_per_mmbtu=unit.get("gas_price_usd_per_mmbtu", 5.0),
                    fuel_system=(
                        FuelSystemConfig(**unit["fuel_system"])
                        if unit.get("fuel_system") is not None else None
                    ),
                )
            )
            for unit in _fc_units_raw
        ]
        _fc_fleet = BlockFuelCellFleet(_fc_arrays)
        sim_state.fuel_cell_rated_mw = _fc_fleet.rated_mw
        sim_state.fuel_cell_module = _fc_fleet

    # fuel_cell_rated_mw is the nameplate rating of ONE stack.  Multiply by
    # fuel_cell_stack_count to get the fleet-total capacity that the physics
    # engine and EDL should see.  Default stack_count=1 is backward-compatible.
    # Set on SimulationState so evaluate_tick() can dispatch the fuel cell in
    # merit order (after BESS, before grid import).  0.0 when not enabled.
    _fc_stack_count: int = int(spec_data.get("fuel_cell_stack_count", 1))
    _fc_rated_mw_fleet: float = (
        float(spec_data.get("fuel_cell_rated_mw", 0.0)) * _fc_stack_count
        if spec_data.get("fuel_cell_enabled", False)
        else 0.0
    )
    if not _fc_units_raw and spec_data.get("fuel_cell_enabled", False):
        sim_state.fuel_cell_rated_mw = _fc_rated_mw_fleet
        _fc_state_raw = spec_data.get("fuel_cell_initial_state")
        if _fc_state_raw is None:
            _fc_state_raw = spec_data.get("fuel_cell_state")
        if _fc_state_raw is None:
            _fc_state_raw = FuelCellState.RUNNING.value
        try:
            _fc_initial_state = FuelCellState(str(_fc_state_raw))
        except ValueError as exc:
            raise ValueError(
                f"unknown fuel-cell initial state: {_fc_state_raw!r}"
            ) from exc
        _fc_target_raw = spec_data.get("fuel_cell_baseload_target_mw")
        if _fc_target_raw is None:
            _fc_target_raw = _fc_rated_mw_fleet
        _fc_target_mw = float(_fc_target_raw)
        if _fc_target_mw > _fc_rated_mw_fleet:
            raise ValueError(
                "fuel_cell_baseload_target_mw cannot exceed the aggregate "
                "fuel-cell fleet nameplate"
            )
        sim_state.fuel_cell_module = FuelCellModule(
            config=FuelCellConfig(
                asset_id="fuel-cell-fleet",
                rated_mw=_fc_rated_mw_fleet,
                baseload_target_mw=_fc_target_mw,
                load_following=bool(spec_data.get("fuel_cell_load_following", False)),
                ramp_rate_mw_per_s=float(
                    spec_data.get("fuel_cell_ramp_rate_mw_per_s", 0.02)
                ),
                ramp_down_rate_mw_per_s=(
                    float(spec_data["fuel_cell_ramp_down_rate_mw_per_s"])
                    if spec_data.get("fuel_cell_ramp_down_rate_mw_per_s") is not None
                    else None
                ),
                min_stable_frac=float(
                    spec_data.get("fuel_cell_min_stable_fraction", 0.5)
                ),
            ),
            state=_fc_initial_state,
        )

    # ── GPU load profile ──────────────────────────────────────────────────
    _gpu_load_raw = spec_data.get("gpu_load_profile", [])
    if _gpu_load_raw:
        sim_state.gpu_load_profile = sorted(
            (float(t), float(f)) for t, f in _gpu_load_raw
        )

    # ── Phase 11.4: Workload floor ────────────────────────────────────────
    # Compute the absolute floor MW from workload_floor_fraction × peak and
    # store on sim_state so evaluate_tick() can enforce it each tick.
    # No-op when workload_floor_fraction is absent/None (returns 0.0).
    _floor_mw = _compute_floor_mw(spec_data)
    if _floor_mw > 0.0:
        sim_state.compute_floor_mw = _floor_mw
        # Pre-register the "__floor__" cooling envelope so evaluate_tick()'s
        # record_job_compute() can record idle-floor heat each tick.
        # Without this, record_job_compute() silently skips unknown job IDs and
        # the floor produces no cooling demand during idle periods.
        sim_state.cooling.register_job_start("__floor__", 0.0)

    # ── Tenant workload events ────────────────────────────────────────────
    # Translate ScenarioSpec.tenant_events dicts into TenantBurstEvent instances
    # and store on sim_state so evaluate_tick() can add their MW each tick.
    # Also populate tenant_contracted_mw so evaluate_tick() can compute per-tenant
    # overage MWh for billing (draw above 100 % of ceiling, up to 150 %, billed at +50 %).
    _tenant_events_raw = spec_data.get("tenant_events", [])
    if _tenant_events_raw:
        sim_state.tenant_events = [
            TenantBurstEvent(
                tenant_id=str(ev.get("tenant_id", "")),
                gpus=int(ev.get("gpus", 0)),
                t_start=float(ev.get("t_start", 0.0)),
                duration_s=float(ev.get("duration_s", 60.0)),
            )
            for ev in _tenant_events_raw
            if int(ev.get("gpus", 0)) > 0
        ]
        # Build contracted-ceiling lookup from the unique tenant IDs present in the
        # scenario.  Uses the global catalogue first; falls back to the per-scenario
        # tenant_budgets list (if provided); then to the default 0.20 MW fallback.
        _inline_budgets: dict[str, float] = {}
        for _tb in spec_data.get("tenant_budgets") or []:
            _tb_id = str(_tb.get("tenant_id", "")).lower()
            _tb_ceil = float(_tb.get("ceiling_mw", 0.0))
            if _tb_id and _tb_ceil > 0.0:
                _inline_budgets[_tb_id] = _tb_ceil
        _unique_tids = {
            str(ev.get("tenant_id", "")).lower()
            for ev in _tenant_events_raw
            if int(ev.get("gpus", 0)) > 0
        }
        sim_state.tenant_contracted_mw = {
            tid: _inline_budgets.get(
                tid, _TENANT_CONTRACTED_MW.get(tid, _DEFAULT_TENANT_MW)
            )
            for tid in _unique_tids
        }

    # ── Kubernetes demand agent ───────────────────────────────────────────
    # Created after SimulationState so site_id is available.
    # Only instantiated when kube_config is present in the spec; all existing
    # scripted scenarios (and every unit test) are unaffected.
    _kube_raw = spec_data.get("kube_config")
    _kube_cluster_raws = spec_data.get("kube_clusters") or []
    if _kube_raw is not None or _kube_cluster_raws:
        if _kube_cluster_raws:
            _agent_defs = list(_kube_cluster_raws)
        else:
            # Legacy shared-fleet path: preserve A/B/C scheduler mix, arrival
            # scaling, event IDs, and deterministic seed partitioning.
            _agent_defs = []
            _base_seed = _kube_raw.get("rng_seed", KubeConfig().rng_seed)
            for _tid, _stype, _weight, _seed_off in (
                ("A", "SLURM", 0.40, 0),
                ("B", "K8S",   0.35, 1),
                ("C", "RAY",   0.25, 2),
            ):
                _definition = dict(_kube_raw)
                _definition.update(
                    cluster_id="legacy-shared-fleet",
                    tenant_id=_tid,
                    scheduler_type=_stype,
                    capacity_unit="node",
                    workload_share=_weight,
                    rng_seed=(
                        None if _base_seed is None
                        else int(_base_seed) + _seed_off
                    ),
                )
                _agent_defs.append(_definition)

        for _definition in _agent_defs:
            _share = float(_definition.get("workload_share", 1.0))
            _cfg = {
                k: v for k, v in _definition.items()
                if k in KubeConfig.__dataclass_fields__
            }
            _cfg["mean_interarrival_s"] = max(
                5.0,
                float(_definition.get(
                    "mean_interarrival_s", KubeConfig().mean_interarrival_s
                )) / _share,
            )
            if isinstance(_cfg.get("step_config"), dict):
                _cfg["step_config"] = StepTimingConfig(**{
                    k: v for k, v in _cfg["step_config"].items()
                    if k in StepTimingConfig.__dataclass_fields__
                })
            if isinstance(_cfg.get("load_config"), dict):
                _cfg["load_config"] = LoadProfileConfig(**{
                    k: v for k, v in _cfg["load_config"].items()
                    if k in LoadProfileConfig.__dataclass_fields__
                })

            _hw_id = _cfg.get(
                "hardware_profile_id", KubeConfig().hardware_profile_id
            )
            if _hw_id not in DEFAULT_HARDWARE_LIBRARY:
                raise ValueError(
                    f"Kubernetes hardware profile {_hw_id!r} is not in "
                    "DEFAULT_HARDWARE_LIBRARY"
                )
            _profile = DEFAULT_HARDWARE_LIBRARY[_hw_id]
            if _profile.rated_kw <= 0.0:
                raise ValueError(
                    f"Hardware profile {_hw_id!r} resolved to rated_kw=0.0 "
                    "from DEFAULT_HARDWARE_LIBRARY"
                )
            _cfg["rated_kw_per_node"] = _profile.rated_kw
            _cfg["gpus_per_unit"] = _profile.gpus_per_unit
            if _kube_cluster_raws:
                _cfg["event_id_prefix"] = str(_cfg["cluster_id"])
                # The old MW gate is node-based and cannot safely combine mixed
                # scheduling-unit powers. Site headroom remains the global gate.
                _cfg["capacity_ceiling_mw"] = None
            else:
                _cap_ceiling = float(spec_data.get("design_peak_load_mw") or 0.0)
                if _cap_ceiling > 0.0:
                    _cfg["capacity_ceiling_mw"] = _cap_ceiling

            sim_state.kube_agents.append(
                KubeDemandAgent(KubeConfig(**_cfg), site_id=site.site_id)
            )

        # Agents sharing one cluster_id must agree on that cluster's ceiling.
        _max_by_cluster: dict[str, int] = {}
        for _agent in sim_state.kube_agents:
            _key = _agent.config.cluster_id or "legacy-shared-fleet"
            _prior = _max_by_cluster.setdefault(_key, _agent.config.max_nodes)
            if _prior != _agent.config.max_nodes:
                _offenders = [
                    (a.config.tenant_id, a.config.max_nodes)
                    for a in sim_state.kube_agents
                    if (a.config.cluster_id or "legacy-shared-fleet") == _key
                ]
                raise ValueError(
                    "Fleet max_nodes invariant violated for cluster "
                    f"{_key!r}: agents sharing a cluster_id must agree, "
                    f"but found {_offenders!r}"
                )

        # Wire load_config / rng_load from the primary agent (A) into GPUModules.
        if sim_state.kube_agents[0].config.load_config is not None:
            for _gpu in sim_state.gpu_modules:
                _gpu.load_config = sim_state.kube_agents[0].config.load_config
                _gpu.rng_load = sim_state.kube_agents[0].rng_load

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

    def _scripted_signal(
        evt: dict,
        *,
        event_type: WorkloadEventType | None = None,
        event_id: str | None = None,
        job_id: str | None = None,
        node_count: int | None = None,
    ) -> WorkloadSignal:
        resolved_event_id = (
            event_id or evt.get("event_id") or f"evt-{_uuid.uuid4().hex[:8]}"
        )
        resolved_job_id = job_id or evt.get("job_id") or f"job-{_uuid.uuid4().hex[:8]}"
        return WorkloadSignal(
            event_id=resolved_event_id,
            job_id=resolved_job_id,
            event_type=event_type or WorkloadEventType(evt["event_type"]),
            timestamp=float(evt["timestamp"]),
            hardware_profile_id=evt.get("hardware_profile_id") or hw_id,
            node_count=(
                int(evt.get("node_count", 0))
                if node_count is None else node_count
            ),
            workload_class=WorkloadClass(evt.get("workload_class", "training")),
            site_id=site.site_id,
            request_rate=(
                float(evt["request_rate"])
                if evt.get("request_rate") is not None else None
            ),
            scheduler_domain=evt.get("scheduler_domain"),
            renewable_shortfall_mw=float(evt.get("renewable_shortfall_mw", 0.0)),
            tenant_id=evt.get("tenant_id"),
            cluster_id=evt.get("cluster_id"),
            scheduler_type=evt.get("scheduler_type"),
            capacity_unit=evt.get("capacity_unit"),
            gpus_per_unit=int(evt.get("gpus_per_unit", 1)),
            electrical_group_id=evt.get("electrical_group_id"),
        )

    # Scheduler-authored job cohorts at one timestamp are applied atomically per
    # cluster, then emitted as one persistent cluster allocation.  This mirrors
    # the aggregate STARTING/SCALE signals produced by KubeDemandAgent and avoids
    # resetting GPU ramp state when one set of jobs hands off to the next level.
    _raw_events = list(spec_data.get("workload_events", []))
    _clustered_by_time: dict[float, list[dict]] = {}
    for evt in _raw_events:
        _event_type = str(evt.get("event_type", ""))
        if (
            evt.get("cluster_id")
            and evt.get("scheduler_type")
            and _event_type in {"starting", "scale", "job_end", "cancelled"}
        ):
            _clustered_by_time.setdefault(float(evt["timestamp"]), []).append(evt)
        else:
            events.append(_scripted_signal(evt))

    _active_cluster_jobs: dict[str, dict[str, int]] = {}
    _last_cluster_total: dict[str, int] = {}
    _started_clusters: set[str] = set()
    for _timestamp in sorted(_clustered_by_time):
        _changed_clusters: list[str] = []
        _cluster_metadata: dict[str, dict] = {}
        for evt in _clustered_by_time[_timestamp]:
            _cluster_id = str(evt["cluster_id"])
            if _cluster_id not in _changed_clusters:
                _changed_clusters.append(_cluster_id)
            _cluster_metadata[_cluster_id] = evt
            _jobs = _active_cluster_jobs.setdefault(_cluster_id, {})
            _event_type = WorkloadEventType(evt["event_type"])
            _job_id = str(evt.get("job_id") or "")
            if _event_type in {WorkloadEventType.STARTING, WorkloadEventType.SCALE}:
                _jobs[_job_id] = int(evt.get("node_count", 0))
            elif _event_type in {WorkloadEventType.JOB_END, WorkloadEventType.CANCELLED}:
                _jobs.pop(_job_id, None)

        for _cluster_id in _changed_clusters:
            _total_nodes = sum(_active_cluster_jobs[_cluster_id].values())
            _prior_nodes = _last_cluster_total.get(_cluster_id)
            if _prior_nodes == _total_nodes:
                continue
            if _cluster_id not in _started_clusters:
                if _total_nodes <= 0:
                    continue
                _aggregate_type = WorkloadEventType.STARTING
                _started_clusters.add(_cluster_id)
            elif _total_nodes > 0:
                _aggregate_type = WorkloadEventType.SCALE
            else:
                _aggregate_type = WorkloadEventType.JOB_END

            _metadata = _cluster_metadata[_cluster_id]
            events.append(_scripted_signal(
                _metadata,
                event_type=_aggregate_type,
                event_id=f"{_cluster_id}-scripted-t{int(_timestamp * 10)}",
                job_id=f"scripted-admission-{_cluster_id}",
                node_count=_total_nodes,
            ))
            _last_cluster_total[_cluster_id] = _total_nodes
    events.sort(key=lambda e: e.timestamp)

    # ── Assertions (Step 9) ───────────────────────────────────────────────
    # spec_data["assertions"] is a list of plain dicts (JSON-round-trip safe).
    # _assertion_adapter validates each dict against the AssertionSpec union
    # so that RunContext.assertions always holds typed Pydantic objects.
    raw_assertions = spec_data.get("assertions", [])
    assertions = [_assertion_adapter.validate_python(a) for a in raw_assertions]
    # This guard is intentionally injected by the factory rather than authored
    # in individual JSON files: every declared block array must prove that it
    # produced nonzero achieved output at least once during a completed run.
    # It cannot be omitted by a scenario author.
    if spec_data.get("fuel_cell_units"):
        assertions.append(
            _assertion_adapter.validate_python({"check": "fuel_cell_output_nonzero"})
        )

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
        # No workload_events: peak IT load is uncomputable from scripted node counts
        # (kube path, idle run, or GPU-load-step scenarios).  Do NOT set
        # _spec_rated_cooling_mw = 0.0 — that value propagates to RunContext and gets
        # broadcast every tick as rated_cooling_mw=0.00, which the UI renders as a
        # config defect (a 6+ MW facility with zero rated cooling capacity is impossible).
        #
        # Proxy: turbine fleet MW × alpha_max × cooling_margin.  The turbine fleet is
        # sized to power the full site; alpha_max is the fraction that goes to cooling.
        # This matches how the two event-driven factory paths compute rated cooling MW
        # (see lines above) and produces a physically coherent rated value even when
        # no scripted node count is available.
        _spec_rated_cooling_mw    = site.alpha_max * _spec_total_turbine_mw * _sp.value("cooling_margin")
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

    # ── EDL sources (PSP-002 §3.2 / Task #371) ───────────────────────────
    # Build the PowerSource list that EconomicDispatchLoop.step() uses for
    # merit-order dispatch.  RunContext.edl_sources = None causes the EDL to
    # be skipped entirely each tick; populating it here activates per-tick
    # economic dispatch.
    #
    # Authority tier: honour per-unit spec field written by the Scenario
    # Builder UI (autonomous / confirm / human_only).  Defaults to AUTONOMOUS
    # so the EDL can dispatch without operator confirmation in headless runs.
    #
    # Grid source: uncapped (available_mw=999.0 — no hard physics limit).
    # EDL.step() reprices grid sources per TOU each tick, so the initial
    # marginal_cost_mwh here is a catalogue-read placeholder only.
    _edl_sources: list[_PowerSource] = []

    for _i, _b in enumerate(spec_data.get("bess_units", [])):
        _tier_raw = _b.get("authority_tier", "autonomous")
        try:
            _bess_tier = _AuthorityTier(_tier_raw)
        except ValueError:
            _bess_tier = _AuthorityTier.AUTONOMOUS
        _edl_sources.append(_PowerSource(
            source_id=_b.get("asset_id") or f"bess-{_i}",
            source_type=_PowerSourceType.BESS,
            dispatchable=True,
            counts_toward_reserve=True,
            marginal_cost_mwh=float(_sp.value("bess_marginal_cost_mwh")),
            response_latency_class=_ResponseLatencyClass.INSTANT,
            authority_tier=_bess_tier,
            available_mw=float(_b.get("rated_mw", 5.0)),
            cost_basis_note="cycle amortisation (PSP-6)",
        ))

    # Turbine fleet: add to EDL for merit-order advisory and cost accounting.
    # available_mw is initialised to the rated fleet total here; run_manager._drive()
    # updates it each tick to tick_result.turbine_output_mw so cost attribution
    # reflects actual physics dispatch rather than nameplate capacity.
    _spec_turbine_units = spec_data.get("turbine_units", [])
    if _spec_turbine_units:
        _turbine_fleet_rated_mw = sum(
            float(t.get("rated_mw", 10.0)) for t in _spec_turbine_units
        )
        if _turbine_fleet_rated_mw > 0.0:
            _edl_sources.append(_PowerSource(
                source_id="turbine-fleet",
                source_type=_PowerSourceType.TURBINE,
                dispatchable=True,
                counts_toward_reserve=True,
                marginal_cost_mwh=float(_sp.value("turbine_variable_per_mwh")),
                response_latency_class=_ResponseLatencyClass.THERMAL_LAG,
                authority_tier=_AuthorityTier.AUTONOMOUS,
                available_mw=_turbine_fleet_rated_mw,
                cost_basis_note="fuel + variable O&M (turbine_variable_per_mwh catalogue)",
            ))

    if spec_data.get("fuel_cell_enabled", False):
        _edl_sources.append(_PowerSource(
            source_id="fuel-cell-0",
            source_type=_PowerSourceType.FUEL_CELL,
            dispatchable=True,
            counts_toward_reserve=False,
            marginal_cost_mwh=float(_sp.value("fuel_cell_ppa_rate_mwh")),
            response_latency_class=_ResponseLatencyClass.RAMP_LIMITED,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            # fleet-total MW: per-stack rated_mw × stack_count (same as sim_state)
            available_mw=_fc_rated_mw_fleet,
            cost_basis_note="fuel cell PPA rate (PSP-002 §7)",
        ))

    # Grid is always present as the last-resort source.
    # Task #372: authority tier is configurable from the spec so the Scenario
    # Builder UI can promote grid to CONFIRM/HUMAN_ONLY and force §4.3 EDL
    # shortfall events, enabling PMSTestDouble replay (grid_authority_tier field).
    # Default "autonomous" preserves all existing behaviour.
    _grid_tier_raw = spec_data.get("grid_authority_tier", "autonomous")
    try:
        _grid_tier = _AuthorityTier(_grid_tier_raw)
    except ValueError:
        _grid_tier = _AuthorityTier.AUTONOMOUS
    _edl_sources.append(_PowerSource(
        source_id="grid-firm",
        source_type=_PowerSourceType.GRID_FIRM,
        dispatchable=True,
        counts_toward_reserve=False,
        marginal_cost_mwh=float(_sp.value("pge_tou_summer_off_peak_mwh")),
        response_latency_class=_ResponseLatencyClass.INSTANT,
        authority_tier=_grid_tier,
        available_mw=999.0,
        cost_basis_note="PG&E B-20 TOU placeholder — repriced per tick by EDL.step()",
    ))

    # Calendar month for TOU classification (Task #370).
    # Honour spec field when the Scenario Builder has overridden it;
    # fall back to a stable simulation baseline.  Using the host wall clock
    # would make otherwise identical scenario inputs produce different physics.
    _edl_calendar_month: int = int(
        spec_data.get("edl_calendar_month")
        if spec_data.get("edl_calendar_month") is not None
        else _DEFAULT_EDL_CALENDAR_MONTH
    )

    # ── Operator response profile (PSP-002 §3.4 / §4.3) ─────────────────
    # ScenarioSpec.operator_response_profile is an untyped dict stored in
    # JSON, so dict keys are always strings.  OperatorResponseProfile expects
    # Dict[int, ...] keys (rank is 1-indexed int), so coerce on the way in.
    _raw_pms = spec_data.get("operator_response_profile")
    _pms_profile: "_OperatorResponseProfile | None" = None
    if isinstance(_raw_pms, dict):
        _pms_profile = _OperatorResponseProfile(
            response_latency_s={
                int(k): float(v)
                for k, v in _raw_pms.get("response_latency_s", {}).items()
            },
            approve={
                int(k): bool(v)
                for k, v in _raw_pms.get("approve", {}).items()
            },
            default_latency_s=float(_raw_pms.get("default_latency_s", 30.0)),
            default_approve=bool(_raw_pms.get("default_approve", True)),
        )

    # ── RunContext ────────────────────────────────────────────────────────
    _registry = AgentRegistry(
        router=DeterministicRouter() if os.environ.get('PYTEST_CURRENT_TEST')
               else AdvisoryRouter(),
        enabled=True,
        max_proposal_mw=float(spec_data.get("advisory_max_mw", 20.0)),
    )
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
        registry=_registry,
        fuel_cell_readiness_controller=(
            BlockFuelCellReadinessController(_registry.get_gate())
            if _fc_units_raw else None
        ),
        telemetry_ingestor=NetworkTelemetryIngestor(),
        corroborator=FabricCorroborator(),
        price_curve=SyntheticPriceCurve(seed=42),
        grid_capacity=_spec_grid_cap,
        _rated_cooling_mw=_spec_rated_cooling_mw,
        _design_peak_load_mw=_spec_design_peak_load_mw,
        # AB2: for §21.2 cost model in energy-summary endpoint.
        turbine_rated_mw=_spec_total_turbine_mw,
        # DIAG-1 / DIAG-2: per-scenario cost price overrides.
        # None when the operator did not set them; cost engine uses
        # _COST_CFG_DEFAULTS fallback in that case.  `is not None` checks
        # are used throughout — never `or` — so $0.0 overrides are honoured.
        grid_import_price_per_mwh=spec_data.get("grid_import_price_per_mwh"),
        bess_charge_price_override_per_mwh=spec_data.get("bess_charge_price_override_per_mwh"),
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
        site_lat=float(spec_data["site_latitude"])
            if spec_data.get("site_latitude") is not None
            else float(
                spec_data["_site_location"].latitude_deg
                if "_site_location" in spec_data else 0.0
            ),
        site_lon=float(spec_data["site_longitude"])
            if spec_data.get("site_longitude") is not None
            else float(
                spec_data["_site_location"].longitude_deg
                if "_site_location" in spec_data else 0.0
            ),
        site_utc_offset_h=float(spec_data["site_utc_offset_h"])
            if spec_data.get("site_utc_offset_h") is not None
            else float(
                spec_data["_site_location"].longitude_deg / 15.0
                if "_site_location" in spec_data else 0.0
            ),
        site_name=str(spec_data["site_name"])
            if spec_data.get("site_name") is not None
            else str(
                spec_data["_site_location"].site_name
                if "_site_location" in spec_data else ""
            ),
        # Three-tier Mistral aggregation: supply the irradiance_profile to the
        # run context so _drive() can call fraction_at(sim_time) each tick.
        # None when solar_rated_mw == 0 (no solar in this scenario).
        irradiance_profile=(
            IrradianceProfile(irradiance_steps) if solar_rated_mw > 0 else None
        ),
        # PSP-002 §3.2 / Task #371 — activate per-tick EDL merit-order dispatch.
        edl_sources=_edl_sources,
        # PSP-002 §7 / Task #370 — TOU month for grid repricing.
        edl_calendar_month=_edl_calendar_month,
        # PSP-002 §4.3 / Task #372 — PMSTestDouble operator response profile.
        # None when the scenario spec omits operator_response_profile (most runs).
        pms_response_profile=_pms_profile,
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
            _cfg_dir = (
                _Path(__file__).resolve().parents[1] / "config" / "scenarios"
            )
            # The regression scenarios use descriptive public IDs.  Their
            # historical filenames remain stable so existing source links and
            # archived artifacts do not break.  Older saved IDs still resolve
            # directly through the fallback below.
            _legacy_filenames = {
                "regression-test-healthy-training-baseline": "S1_baseline_training",
                "regression-test-checkpoint-storage-hotspot": "S2_checkpoint_hotspot",
                "regression-test-clean-job-termination": "S3_job_end_withholds",
                "regression-test-control-path-latency-isolation": "S4_control_path_nfr2_breach",
                "regression-test-gray-link-failure": "S5_gray_failure",
                "regression-test-degraded-fabric-observability": "S6_baseline_tier_degradation",
                "regression-test-slow-checkpoint": "S7_slow_checkpoint",
                "regression-test-transceiver-degradation": "S8_transceiver_degrade",
                "regression-test-islanded-ramp-protection": "S9_islanded_ramp_protection",
            }
            _filename = _legacy_filenames.get(fabric_scenario_id, fabric_scenario_id)
            _candidates = [
                _cfg_dir / f"{_filename}.json",
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
