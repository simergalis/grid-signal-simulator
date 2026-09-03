"""Phase 1 data contracts for the Addendum H BESS sizing sweep.

The contracts in this module describe inputs and raw outputs only.  In
particular, a ``DispatchStep`` is an already-specified change in net
dispatch-required MW.  The existing ``DispatchArbitrator`` remains the sole
owner of ramp, shortfall, BESS, and bridging behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.kube_demand import KubeConfig
from core.models import (
    BessConfig,
    SiteConfig,
    ThermalState,
    TurbineConfig,
    TurbineState,
    WorkloadSignal,
)


class ScenarioType(str, Enum):
    """The four Phase 1 H.4 scenario classes, and no others."""

    BASELINE_RAMP = "baseline_ramp"
    COINCIDENCE = "coincidence"
    CONTINGENCY_N_MINUS_1 = "contingency_n_minus_1"
    RENEWABLE_STEP_LOSS = "renewable_step_loss"


class AnchorMode(str, Enum):
    """BESS anchor role carried by a sizing scenario."""

    GRID_FOLLOWING = "grid_following"
    GRID_FORMING = "grid_forming"


@dataclass(frozen=True)
class ThermalParameters:
    """Thermal inputs carried with one scenario.

    The defaults are intentionally not duplicated here.  Use
    ``ThermalParameters.from_site(site)`` so the catalogue-backed SiteConfig
    remains the source of truth.
    """

    dt_thermal_seconds: float
    tau_seconds: float
    alpha_max: float

    @classmethod
    def from_site(cls, site: SiteConfig) -> "ThermalParameters":
        return cls(
            dt_thermal_seconds=site.dt_thermal_seconds,
            tau_seconds=site.tau_seconds,
            alpha_max=site.alpha_max,
        )


@dataclass(frozen=True)
class SocCyclingPolicy:
    """Phase 1 placeholder for the Phase 3 SoC cycling policy."""

    # PROPOSED_HERE: policy semantics are intentionally deferred to Phase 3.
    normal_dispatch_depth_pct: float = 0.0
    emergency_reserve_floor_pct: float = 0.0


@dataclass(frozen=True)
class RenewableSample:
    """One point in the scenario's renewable availability profile."""

    time_s: float
    output_mw: float


@dataclass(frozen=True)
class DispatchStep:
    """A scheduled net dispatch-required step passed to the real arbitrator."""

    time_s: float
    delta_p_mw: float
    dt_lead_seconds: float
    label: str = ""
    renewable_loss_mw: float = 0.0


@dataclass(frozen=True)
class WorkloadEnvelope:
    """The existing seeded Kubernetes workload generator and its raw signals."""

    # This is the existing core generator configuration, not a replacement.
    kube_config: KubeConfig
    horizon_s: float
    tick_seconds: float
    seeded_signals: tuple[WorkloadSignal, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BessSizingFleetConfig:
    """Site and dispatchable fleet configuration used by a sizing scenario."""

    site_config: SiteConfig
    turbine_configs: tuple[TurbineConfig, ...]
    bess_configs: tuple[BessConfig, ...]


@dataclass(frozen=True)
class BessSizingScenario:
    """One raw H.3 sizing-sweep scenario."""

    scenario_id: str
    scenario_type: ScenarioType
    turbine_fleet: tuple[TurbineConfig, ...]
    bess_fleet: tuple[BessConfig, ...]
    site_config: SiteConfig
    workload_envelope: WorkloadEnvelope
    renewable_profile: tuple[RenewableSample, ...]
    dispatch_steps: tuple[DispatchStep, ...]
    # PROPOSED_HERE: distribution is retained as input metadata in Phase 1;
    # sampling/aggregation policy is deferred to later Addendum H phases.
    dt_lead_distribution_s: tuple[float, ...]
    thermal_parameters: ThermalParameters
    soc_cycling_policy: SocCyclingPolicy
    anchor_mode: AnchorMode = AnchorMode.GRID_FOLLOWING
    p_anchor_reserve_mw: float = 0.0
    anchor_bess_asset_id: Optional[str] = None
    initial_dispatch_required_mw: float = 0.0
    tick_seconds: float = 5.0
    horizon_s: float = 0.0
    initial_turbine_states: tuple[TurbineState, ...] = field(default_factory=tuple)
    initial_turbine_outputs_mw: tuple[float, ...] = field(default_factory=tuple)
    unavailable_turbine_ids: tuple[str, ...] = field(default_factory=tuple)
    turbine_initial_thermal_state: ThermalState = ThermalState.COLD

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ValueError("scenario_id must not be empty")
        if self.tick_seconds <= 0.0:
            raise ValueError("tick_seconds must be greater than zero")
        if self.horizon_s < 0.0:
            raise ValueError("horizon_s must not be negative")
        if self.p_anchor_reserve_mw < 0.0:
            raise ValueError("p_anchor_reserve_mw must not be negative")
        if self.initial_turbine_states and len(self.initial_turbine_states) != len(self.turbine_fleet):
            raise ValueError("initial_turbine_states must match turbine_fleet size")
        if self.initial_turbine_outputs_mw and len(self.initial_turbine_outputs_mw) != len(self.turbine_fleet):
            raise ValueError("initial_turbine_outputs_mw must match turbine_fleet size")
        turbine_ids = {config.asset_id for config in self.turbine_fleet}
        if len(turbine_ids) != len(self.turbine_fleet):
            raise ValueError("turbine_fleet asset IDs must be unique")
        bess_ids = {config.asset_id for config in self.bess_fleet}
        if len(bess_ids) != len(self.bess_fleet):
            raise ValueError("bess_fleet asset IDs must be unique")
        if not set(self.unavailable_turbine_ids).issubset(turbine_ids):
            raise ValueError("unavailable_turbine_ids must name turbine fleet members")
        if len(set(self.unavailable_turbine_ids)) != len(self.unavailable_turbine_ids):
            raise ValueError("unavailable_turbine_ids must be unique")
        if self.anchor_bess_asset_id is not None and self.anchor_bess_asset_id not in bess_ids:
            raise ValueError("anchor_bess_asset_id must name a BESS fleet member")


@dataclass(frozen=True)
class StageTrace:
    """Raw result returned by one call to stage_for_predicted_step()."""

    time_s: float
    step_label: str
    alert_shortfall_mw: Optional[float]
    alert_gap_duration_s: Optional[float]
    already_ramped_mw: float
    peak_shortfall_mw: float


@dataclass(frozen=True)
class TickTrace:
    """Raw result from one DispatchArbitrator.tick() call."""

    time_s: float
    p_dispatch_required_mw: float
    turbine_output_mw: float
    bess_output_mw: float
    bridging_capacity_mw: float
    bridging_capacity_by_unit_mw: tuple[float, ...]


@dataclass(frozen=True)
class ScenarioTrace:
    """Raw per-tick series for one scenario; no aggregate statistics."""

    scenario_id: str
    scenario_type: ScenarioType
    stage_traces: tuple[StageTrace, ...]
    tick_traces: tuple[TickTrace, ...]

    @property
    def bess_output_series_mw(self) -> tuple[float, ...]:
        return tuple(trace.bess_output_mw for trace in self.tick_traces)

    @property
    def bridging_capacity_series_mw(self) -> tuple[float, ...]:
        return tuple(trace.bridging_capacity_mw for trace in self.tick_traces)


@dataclass(frozen=True)
class BessSizingSweepResult:
    """Raw traces keyed by scenario ID."""

    traces: tuple[ScenarioTrace, ...]

    def by_scenario_id(self, scenario_id: str) -> ScenarioTrace:
        for trace in self.traces:
            if trace.scenario_id == scenario_id:
                return trace
        raise KeyError(scenario_id)