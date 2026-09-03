"""Phase 1 H.4 scenario construction.

Baseline workload samples are driven by the existing seeded
``KubeDemandAgent``.  This module only assembles the four Addendum H scenario
types; it does not add a second contingency family or perform sizing math.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

from core.kube_demand import KubeConfig, KubeDemandAgent
from core.models import (
    BessConfig,
    SiteConfig,
    TurbineConfig,
    TurbineState,
)

from .models import (
    AnchorMode,
    BessSizingScenario,
    DispatchStep,
    RenewableSample,
    ScenarioType,
    SocCyclingPolicy,
    ThermalParameters,
    WorkloadEnvelope,
)


def generate_seeded_workload_envelope(
    kube_config: KubeConfig,
    *,
    site_id: str,
    horizon_s: float,
    tick_seconds: float,
) -> WorkloadEnvelope:
    """Run the existing seeded KubeDemandAgent and retain its raw signals."""

    if horizon_s < 0.0:
        raise ValueError("horizon_s must not be negative")
    if tick_seconds <= 0.0:
        raise ValueError("tick_seconds must be greater than zero")

    agent = KubeDemandAgent(kube_config, site_id=site_id)
    signals = []
    sim_time = 0.0
    while sim_time <= horizon_s:
        batch, _metrics = agent.tick(
            sim_time=sim_time,
            dt_seconds=tick_seconds,
        )
        signals.extend(batch)
        sim_time += tick_seconds
    return WorkloadEnvelope(
        kube_config=kube_config,
        horizon_s=horizon_s,
        tick_seconds=tick_seconds,
        seeded_signals=tuple(signals),
    )


def _sampled_kube_configs(
    base_config: KubeConfig,
    arrival_rate_samples_s: Sequence[float],
    job_size_samples_nodes: Sequence[int],
) -> Iterable[tuple[int, float, int, KubeConfig]]:
    sample_index = 0
    for mean_interarrival_s in arrival_rate_samples_s:
        if mean_interarrival_s < 5.0:
            raise ValueError("arrival-rate samples must be at least 5 seconds")
        for mean_job_nodes in job_size_samples_nodes:
            if mean_job_nodes < 1:
                raise ValueError("job-size samples must be positive")
            seed = (
                None
                if base_config.rng_seed is None
                else int(base_config.rng_seed) + sample_index
            )
            yield (
                sample_index,
                mean_interarrival_s,
                mean_job_nodes,
                replace(
                    base_config,
                    mean_interarrival_s=mean_interarrival_s,
                    mean_job_nodes=mean_job_nodes,
                    rng_seed=seed,
                ),
            )
            sample_index += 1


def _scenario_common(
    *,
    scenario_id: str,
    scenario_type: ScenarioType,
    turbine_fleet: tuple[TurbineConfig, ...],
    bess_fleet: tuple[BessConfig, ...],
    site: SiteConfig,
    workload_envelope: WorkloadEnvelope,
    dispatch_steps: tuple[DispatchStep, ...],
    dt_lead_distribution_s: tuple[float, ...],
    renewable_profile: tuple[RenewableSample, ...] = (),
    anchor_mode: AnchorMode = AnchorMode.GRID_FOLLOWING,
    p_anchor_reserve_mw: float = 0.0,
    anchor_bess_asset_id: str | None = None,
    initial_dispatch_required_mw: float = 0.0,
    tick_seconds: float = 5.0,
    horizon_s: float = 0.0,
    initial_turbine_states: tuple[TurbineState, ...] = (),
    unavailable_turbine_ids: tuple[str, ...] = (),
) -> BessSizingScenario:
    return BessSizingScenario(
        scenario_id=scenario_id,
        scenario_type=scenario_type,
        turbine_fleet=turbine_fleet,
        bess_fleet=bess_fleet,
        site_config=site,
        workload_envelope=workload_envelope,
        renewable_profile=renewable_profile,
        dispatch_steps=dispatch_steps,
        dt_lead_distribution_s=tuple(dt_lead_distribution_s),
        thermal_parameters=ThermalParameters.from_site(site),
        soc_cycling_policy=SocCyclingPolicy(),
        anchor_mode=anchor_mode,
        p_anchor_reserve_mw=p_anchor_reserve_mw,
        anchor_bess_asset_id=anchor_bess_asset_id,
        initial_dispatch_required_mw=initial_dispatch_required_mw,
        tick_seconds=tick_seconds,
        horizon_s=horizon_s,
        initial_turbine_states=initial_turbine_states,
        unavailable_turbine_ids=unavailable_turbine_ids,
    )


def generate_bess_sizing_scenarios(
    *,
    site: SiteConfig,
    turbine_fleet: Sequence[TurbineConfig],
    bess_fleet: Sequence[BessConfig],
    base_kube_config: KubeConfig | None = None,
    arrival_rate_samples_s: Sequence[float] = (60.0, 30.0),
    job_size_samples_nodes: Sequence[int] = (200, 400),
    dt_lead_distribution_s: Sequence[float] = (30.0,),
    horizon_s: float = 600.0,
    tick_seconds: float = 5.0,
    coincidence_step_mw: float = 20.0,
    contingency_step_mw: float = 20.0,
    renewable_loss_step_mw: float = 5.0,
) -> tuple[BessSizingScenario, ...]:
    """Build exactly the four H.4 scenario types.

    Baseline scenarios are the Cartesian product of the supplied arrival-rate
    and job-size samples.  Their workload envelopes are produced by the
    existing KubeDemandAgent.  The other three scenario types each add exactly
    one specified event:

    * a thermal-ramp coincidence step,
    * one unavailable online turbine at a step-load,
    * one renewable step loss at a step-load.

    ``dt_lead_distribution_s`` is PROPOSED_HERE until the Addendum H timing
    distribution is finalized.  No Phase 2 aggregation is performed.
    """

    if not dt_lead_distribution_s:
        raise ValueError("dt_lead_distribution_s must contain at least one value")
    if any(value < 0.0 for value in dt_lead_distribution_s):
        raise ValueError("dt_lead_distribution_s values must not be negative")
    if horizon_s < 0.0:
        raise ValueError("horizon_s must not be negative")
    if tick_seconds <= 0.0:
        raise ValueError("tick_seconds must be greater than zero")
    turbines = tuple(turbine_fleet)
    bess_units = tuple(bess_fleet)
    if not turbines:
        raise ValueError("turbine_fleet must contain at least one turbine")

    kube_base = base_kube_config if base_kube_config is not None else KubeConfig()
    scenarios: list[BessSizingScenario] = []
    for index, arrival_s, job_nodes, kube_config in _sampled_kube_configs(
        kube_base,
        arrival_rate_samples_s,
        job_size_samples_nodes,
    ):
        envelope = generate_seeded_workload_envelope(
            kube_config,
            site_id=site.site_id,
            horizon_s=horizon_s,
            tick_seconds=tick_seconds,
        )
        lead_s = dt_lead_distribution_s[index % len(dt_lead_distribution_s)]
        scenarios.append(
            _scenario_common(
                scenario_id=f"baseline-ramp-{index}",
                scenario_type=ScenarioType.BASELINE_RAMP,
                turbine_fleet=turbines,
                bess_fleet=bess_units,
                site=site,
                workload_envelope=envelope,
                dispatch_steps=(),
                dt_lead_distribution_s=tuple(dt_lead_distribution_s),
                tick_seconds=tick_seconds,
                horizon_s=horizon_s,
            )
        )

    coincidence_envelope = generate_seeded_workload_envelope(
        kube_base,
        site_id=site.site_id,
        horizon_s=horizon_s,
        tick_seconds=tick_seconds,
    )
    coincidence_time_s = site.dt_thermal_seconds
    scenarios.append(
        _scenario_common(
            scenario_id="coincidence-thermal-ramp",
            scenario_type=ScenarioType.COINCIDENCE,
            turbine_fleet=turbines,
            bess_fleet=bess_units,
            site=site,
            workload_envelope=coincidence_envelope,
            dispatch_steps=(
                DispatchStep(
                    time_s=coincidence_time_s,
                    delta_p_mw=coincidence_step_mw,
                    dt_lead_seconds=dt_lead_distribution_s[0],
                    label="compute-step-at-thermal-ramp-beginning",
                ),
            ),
            dt_lead_distribution_s=tuple(dt_lead_distribution_s),
            tick_seconds=tick_seconds,
            horizon_s=(
                horizon_s
                if horizon_s >= coincidence_time_s
                else coincidence_time_s
            ),
        )
    )

    contingency_envelope = generate_seeded_workload_envelope(
        kube_base,
        site_id=site.site_id,
        horizon_s=horizon_s,
        tick_seconds=tick_seconds,
    )
    online_ids = tuple(turbine.asset_id for turbine in turbines)
    unavailable_id = online_ids[0]
    contingency_time_s = 0.0
    scenarios.append(
        _scenario_common(
            scenario_id="contingency-n-minus-1-step-load",
            scenario_type=ScenarioType.CONTINGENCY_N_MINUS_1,
            turbine_fleet=turbines,
            bess_fleet=bess_units,
            site=site,
            workload_envelope=contingency_envelope,
            dispatch_steps=(
                DispatchStep(
                    time_s=contingency_time_s,
                    delta_p_mw=contingency_step_mw,
                    dt_lead_seconds=dt_lead_distribution_s[0],
                    label="n-minus-1-at-step-load",
                ),
            ),
            dt_lead_distribution_s=tuple(dt_lead_distribution_s),
            tick_seconds=tick_seconds,
            horizon_s=horizon_s,
            initial_turbine_states=tuple(
                TurbineState.SYNCHRONISED for _ in turbines
            ),
            unavailable_turbine_ids=(unavailable_id,),
        )
    )

    renewable_envelope = generate_seeded_workload_envelope(
        kube_base,
        site_id=site.site_id,
        horizon_s=horizon_s,
        tick_seconds=tick_seconds,
    )
    scenarios.append(
        _scenario_common(
            scenario_id="renewable-step-loss-at-step-load",
            scenario_type=ScenarioType.RENEWABLE_STEP_LOSS,
            turbine_fleet=turbines,
            bess_fleet=bess_units,
            site=site,
            workload_envelope=renewable_envelope,
            renewable_profile=(
                RenewableSample(time_s=0.0, output_mw=renewable_loss_step_mw),
                RenewableSample(time_s=tick_seconds, output_mw=0.0),
            ),
            dispatch_steps=(
                DispatchStep(
                    time_s=0.0,
                    delta_p_mw=renewable_loss_step_mw,
                    dt_lead_seconds=0.0,
                    label="renewable-step-loss-coincident-with-step-load",
                    renewable_loss_mw=renewable_loss_step_mw,
                ),
            ),
            dt_lead_distribution_s=tuple(dt_lead_distribution_s),
            tick_seconds=tick_seconds,
            horizon_s=horizon_s,
        )
    )
    return tuple(scenarios)


def make_tc_h1_worked_example() -> BessSizingScenario:
    """Create the Section 7.3 / TC-H1 20 MW, 30 s lead fixture."""

    site = SiteConfig(site_id="tc-h1")
    turbine = TurbineConfig(
        asset_id="t0",
        r_asset_mw_per_s=0.2,
        rated_mw=25.0,
    )
    bess = BessConfig(
        asset_id="bess-h1",
        rated_mw=5.0,
        usable_mwh=2.0,
    )
    kube_config = KubeConfig(
        max_nodes=1,
        min_nodes=1,
        mean_interarrival_s=3600.0,
        mean_job_nodes=1,
        min_job_nodes=1,
        max_job_nodes=1,
        rng_seed=0,
    )
    envelope = generate_seeded_workload_envelope(
        kube_config,
        site_id=site.site_id,
        horizon_s=0.0,
        tick_seconds=5.0,
    )
    return _scenario_common(
        scenario_id="tc-h1-section-7-3-worked-example",
        scenario_type=ScenarioType.BASELINE_RAMP,
        turbine_fleet=(turbine,),
        bess_fleet=(bess,),
        site=site,
        workload_envelope=envelope,
        dispatch_steps=(
            DispatchStep(
                time_s=0.0,
                delta_p_mw=20.0,
                dt_lead_seconds=30.0,
                label="20-mw-job",
            ),
        ),
        dt_lead_distribution_s=(30.0,),
        tick_seconds=5.0,
        horizon_s=30.0,
    )