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
    SiteConfig,
    SolarConfig,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.simulation_core import SimulationState
from runtime.run_manager import InMemoryTimeseriesSink, RunContext

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
    bess_rated_mw: float = 5.0,
    bess_usable_mwh: float = 2.0,
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
        TurbineModule(TurbineConfig(asset_id=f"turbine-{i}", r_asset_mw_per_s=r_asset_mw_per_s))
        for i in range(turbine_count)
    ]
    bess_units = [BessModule(BessConfig(asset_id="bess-0", rated_mw=bess_rated_mw, usable_mwh=bess_usable_mwh))]
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

    return RunContext(
        run_id=run_id,
        sim_state=sim_state,
        events=events,
        dt_lead_seconds=dt_lead_seconds,
        end_sim_time=end_sim_time,
        playback_speed=playback_speed,
        sink=InMemoryTimeseriesSink(),
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

    return RunContext(
        run_id=run_id,
        sim_state=sim_state,
        events=events,
        dt_lead_seconds=dt_lead_seconds,
        end_sim_time=end_sim_time,
        playback_speed=playback_speed,
        sink=InMemoryTimeseriesSink(),
    )
