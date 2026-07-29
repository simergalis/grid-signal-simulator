"""
Asset modules: the simulated domain model (functional spec Section 4).

Every module implements the same small interface (AssetModule) so that
new asset types can be added without touching the dispatch arbitrator
or the simulation loop, per functional spec Section 16 (Extensibility
Guide) and Design Spec Section 5.

All of this is deliberately synchronous, pure-Python, side-effect-free
arithmetic -- see Design Spec Section 4.3 for why no concurrency is
introduced at this layer.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import (
    BessConfig,
    GENERIC_FALLBACK_PROFILE,
    HardwareProfile,
    SiteConfig,
    SolarConfig,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)


class AssetModule(ABC):
    """Common interface every simulated asset implements.

    Design Spec Section 5. `advance(dt)` mutates the module's own state
    forward by one tick; `output_mw(t)` (or `output_mw()` for modules
    that only need their own current state) reports the asset's current
    contribution. Kept intentionally minimal -- richer modules add
    methods, they don't need to widen this interface.
    """

    asset_id: str

    @abstractmethod
    def advance(self, sim_time: float, dt_seconds: float) -> None:
        """Move this asset's internal state forward by one tick."""

    @abstractmethod
    def output_mw(self) -> float:
        """This asset's current power contribution (draw, positive;
        supply/offset, also positive -- sign convention is applied by
        the caller, e.g. Net_demand(t) subtracts solar's output_mw())."""


# ---------------------------------------------------------------------------
# GPU compute module -- source spec Section 4.1, 5, 6
# ---------------------------------------------------------------------------

@dataclass
class GPUModule(AssetModule):
    """Tracks node_count per active job on this module and reports the
    instantaneous compute draw, P_compute(t)'s per-module term:

        Nodes_i(t) * kW_i * PUE_base / 1000

    Node counts are updated by WorkloadSignal events (job start/scale/
    end), not by `advance()` -- `advance()` here is a no-op placeholder
    for modules whose state doesn't decay/ramp on its own, kept for
    interface symmetry with TurbineModule/BessModule.
    """

    asset_id: str
    site: SiteConfig
    hardware_library: dict[str, HardwareProfile]
    _node_counts: dict[str, int] = field(default_factory=dict)  # job_id -> nodes
    _job_profiles: dict[str, str] = field(default_factory=dict)  # job_id -> profile_id
    unmapped_profile_seen: set[str] = field(default_factory=set)

    def apply_signal(self, signal: WorkloadSignal) -> bool:
        """Returns True if this signal introduced an unmapped hardware
        profile (source spec Section 5.1), so the caller can raise the
        one-time onboarding alert and confidence-widening tag."""
        unmapped = signal.hardware_profile_id not in self.hardware_library

        if signal.event_type in (WorkloadEventType.STARTING, WorkloadEventType.SCALE):
            self._node_counts[signal.job_id] = signal.node_count
            self._job_profiles[signal.job_id] = signal.hardware_profile_id
        elif signal.event_type in (WorkloadEventType.JOB_END, WorkloadEventType.CANCELLED):
            self._node_counts.pop(signal.job_id, None)
            self._job_profiles.pop(signal.job_id, None)
        # checkpoint_start/checkpoint_end intentionally leave node_count
        # untouched -- the classifier (dispatch.py) reads the resulting
        # draw shape, it doesn't get a node-count signal of its own.

        if unmapped:
            self.unmapped_profile_seen.add(signal.hardware_profile_id)
        return unmapped

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        return  # no autonomous dynamics; state changes only via apply_signal

    def output_mw(self) -> float:
        total_kw = 0.0
        for job_id, nodes in self._node_counts.items():
            profile_id = self._job_profiles[job_id]
            profile = self.hardware_library.get(profile_id, GENERIC_FALLBACK_PROFILE)
            total_kw += nodes * profile.rated_kw
        return total_kw * self.site.pue_base / 1000.0

    def active_training_jobs(self) -> list[str]:
        return [
            job_id
            for job_id in self._node_counts
            if self._job_profiles.get(job_id)  # profile known -> job is active
        ]


# ---------------------------------------------------------------------------
# Cooling module -- source spec Section 8
# ---------------------------------------------------------------------------

@dataclass
class CoolingModule(AssetModule):
    """P_cooling(t) = alpha(t) * P_compute(t - dt_thermal)

    alpha(t) = alpha_max * (1 - e^-((t - t0 - dt_thermal) / tau))  for t >= t0 + dt_thermal
             = 0                                                   otherwise

    Requires a short history of P_compute samples to look back
    dt_thermal seconds -- maintained by the caller (simulation_core.py)
    and passed in each tick via `record_compute_sample`.
    """

    asset_id: str
    site: SiteConfig
    step_onset_time: Optional[float] = None  # t0: first tick a step-load appears
    _compute_history: list[tuple[float, float]] = field(default_factory=list)  # (t, P_compute)
    _last_output_mw: float = 0.0

    def record_compute_sample(self, sim_time: float, p_compute_mw: float) -> None:
        self._compute_history.append((sim_time, p_compute_mw))
        # Bound history growth: only need slightly more than dt_thermal seconds of lookback.
        cutoff = sim_time - (self.site.dt_thermal_seconds * 2 + 10)
        while self._compute_history and self._compute_history[0][0] < cutoff:
            self._compute_history.pop(0)

        if self.step_onset_time is None and p_compute_mw > 0:
            self.step_onset_time = sim_time

    def _lagged_compute_mw(self, target_time: float) -> float:
        """Nearest-sample lookup of P_compute at (t - dt_thermal). A
        production build may want linear interpolation between
        samples; nearest-sample is sufficient at the 5s tick cadence
        (source spec Section 3.1) and keeps this deterministic and
        simple for the skeleton."""
        if not self._compute_history:
            return 0.0
        best = min(self._compute_history, key=lambda sample: abs(sample[0] - target_time))
        return best[1]

    def _alpha(self, sim_time: float) -> float:
        if self.step_onset_time is None:
            return 0.0
        threshold = self.step_onset_time + self.site.dt_thermal_seconds
        if sim_time < threshold:
            return 0.0
        elapsed_past_threshold = sim_time - threshold
        return self.site.alpha_max * (1 - math.exp(-elapsed_past_threshold / self.site.tau_seconds))

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        lag_time = sim_time - self.site.dt_thermal_seconds
        lagged_compute = self._lagged_compute_mw(lag_time)
        self._last_output_mw = self._alpha(sim_time) * lagged_compute

    def output_mw(self) -> float:
        return self._last_output_mw


# ---------------------------------------------------------------------------
# Turbine module -- source spec Section 7.1, 7.2
# ---------------------------------------------------------------------------

class TurbineState(str, Enum):
    OFFLINE = "offline"
    RAMPING = "ramping"
    AT_TARGET = "at_target"


@dataclass
class TurbineModule(AssetModule):
    config: TurbineConfig
    state: TurbineState = TurbineState.OFFLINE
    _current_output_mw: float = 0.0
    _target_mw: float = 0.0

    @property
    def asset_id(self) -> str:  # noqa: D401 -- property mirrors dataclass field name
        return self.config.asset_id

    def stage_target(self, target_mw: float) -> None:
        """Dispatch arbitrator calls this at a job's `starting` event
        (source spec Section 7.2 step 1) to begin ramping immediately,
        using the full available lead time."""
        self._target_mw = min(target_mw, self.config.rated_mw)
        if self.state == TurbineState.OFFLINE:
            self.state = TurbineState.RAMPING

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        if self.state != TurbineState.RAMPING:
            return
        max_delta = self.config.r_asset_mw_per_s * dt_seconds
        if self._current_output_mw < self._target_mw:
            self._current_output_mw = min(self._target_mw, self._current_output_mw + max_delta)
        elif self._current_output_mw > self._target_mw:
            self._current_output_mw = max(self._target_mw, self._current_output_mw - max_delta)
        if math.isclose(self._current_output_mw, self._target_mw, abs_tol=1e-6):
            self.state = TurbineState.AT_TARGET

    def output_mw(self) -> float:
        return self._current_output_mw


# ---------------------------------------------------------------------------
# BESS module -- source spec Section 7.1, 7.2
# ---------------------------------------------------------------------------

@dataclass
class BessModule(AssetModule):
    config: BessConfig
    soc_mwh: float = field(init=False)
    _current_output_mw: float = 0.0
    _sustained_catchup_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.soc_mwh = self.config.usable_mwh * self.config.initial_soc_fraction

    @property
    def asset_id(self) -> str:
        return self.config.asset_id

    @property
    def soc_fraction(self) -> float:
        return self.soc_mwh / self.config.usable_mwh if self.config.usable_mwh else 0.0

    def cover_shortfall(self, p_total_mw: float, turbine_output_mw: float, dt_seconds: float) -> float:
        """Source spec Section 7.2 step 2-3:

            BESS_output(t) = max(0, P_total(t) - turbine_output(t))

        bounded by rated capacity and state of charge, tapering to
        standby once turbines have sustained coverage for 10s.
        """
        shortfall = max(0.0, p_total_mw - turbine_output_mw)

        if turbine_output_mw >= p_total_mw:
            self._sustained_catchup_seconds += dt_seconds
        else:
            self._sustained_catchup_seconds = 0.0

        if self._sustained_catchup_seconds >= 10.0:
            self._current_output_mw = 0.0
            return self._current_output_mw

        max_by_power = self.config.rated_mw
        max_by_energy = self.soc_mwh / (dt_seconds / 3600.0) if dt_seconds > 0 else max_by_power
        discharge_mw = min(shortfall, max_by_power, max_by_energy)

        self.soc_mwh = max(0.0, self.soc_mwh - discharge_mw * (dt_seconds / 3600.0))
        self._current_output_mw = discharge_mw
        return discharge_mw

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        return  # state is updated via cover_shortfall(), called by the arbitrator each tick

    def output_mw(self) -> float:
        return self._current_output_mw

    def max_sustainable_seconds(self, discharge_mw: float) -> float:
        """Used by the insufficient-reserve check (dispatch.py):
        how long, in seconds, this BESS can sustain `discharge_mw`
        given current state of charge."""
        if discharge_mw <= 0:
            return math.inf
        hours = self.soc_mwh / discharge_mw
        return hours * 3600.0


# ---------------------------------------------------------------------------
# Solar module -- Extension E-1, simulator-only (not in source spec)
# ---------------------------------------------------------------------------

@dataclass
class SolarModule(AssetModule):
    """Non-dispatchable supply term. Contributes to Net_demand(t) =
    P_total(t) - Solar_output(t), clipped at zero (functional spec
    Section 4.4.2 / Section 16.3 validation checklist)."""

    config: SolarConfig
    irradiance_profile: "IrradianceProfile"
    _current_output_mw: float = 0.0

    @property
    def asset_id(self) -> str:
        return self.config.asset_id

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        fraction = self.irradiance_profile.fraction_at(sim_time)
        self._current_output_mw = self.config.rated_mw * fraction

    def output_mw(self) -> float:
        return self._current_output_mw


class IrradianceProfile:
    """Minimal sim-time -> [0, 1] output-fraction lookup. Scenario
    Builder-configured (functional spec Section 7.2); a flat/constant
    profile is a valid degenerate case for scripted "cloudy period"
    stressors."""

    def __init__(self, samples: list[tuple[float, float]]):
        self._samples = sorted(samples)

    def fraction_at(self, sim_time: float) -> float:
        if not self._samples:
            return 1.0
        if sim_time <= self._samples[0][0]:
            return self._samples[0][1]
        if sim_time >= self._samples[-1][0]:
            return self._samples[-1][1]
        for (t0, f0), (t1, f1) in zip(self._samples, self._samples[1:]):
            if t0 <= sim_time <= t1:
                span = t1 - t0
                if span == 0:
                    return f0
                weight = (sim_time - t0) / span
                return f0 + (f1 - f0) * weight
        return self._samples[-1][1]
