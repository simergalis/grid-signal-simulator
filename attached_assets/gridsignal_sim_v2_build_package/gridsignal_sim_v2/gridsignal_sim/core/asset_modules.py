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
    # Step 3 Item 2: Δt_lead ramp state.
    # ramp_seconds — the window over which a newly-allocated job ramps from
    # 0 → full TDP.  §6.1 specifies "30–60 s" as the interval; the exact
    # curve inside it is PROTO-1 (CHOSEN, no measured basis — see _ramp_multiplier).
    ramp_seconds: float = 45.0
    _ramp_progress: dict[str, float] = field(default_factory=dict)  # job_id -> [0.0, 1.0]

    # ------------------------------------------------------------------
    # Δt_lead ramp shape  (Step 3 Item 2 — PROTO-1)
    # ------------------------------------------------------------------

    @staticmethod
    def _ramp_multiplier(progress: float) -> float:
        """Piecewise ramp shape matching §6.1's physical narrative.

        PROTO-1: CHOSEN shape, no measured basis.  §6.1 specifies the
        interval (Δt_lead = 30–60 s), not the curve inside it.

        Three phases defined by progress ∈ [0, 1]:
          Phase 1 [0.00, 0.20): near-idle container init        0.00 → 0.05
          Phase 2 [0.20, 0.70): steep linear rise, weight load  0.05 → 0.95
          Phase 3 [0.70, 1.00]: plateau, collective warmup       0.95 → 1.00
        """
        if progress <= 0.0:
            return 0.0
        if progress >= 1.0:
            return 1.0
        if progress < 0.20:
            return 0.05 * (progress / 0.20)
        if progress < 0.70:
            return 0.05 + 0.90 * ((progress - 0.20) / 0.50)
        # Phase 3: 0.70 ≤ progress < 1.0
        return 0.95 + 0.05 * ((progress - 0.70) / 0.30)

    def apply_signal(self, signal: WorkloadSignal) -> bool:
        """Returns True if this signal introduced an unmapped hardware
        profile (source spec Section 5.1), so the caller can raise the
        one-time onboarding alert and confidence-widening tag.

        Step 3 Item 2: STARTING initialises the ramp at 0 (nothing yet
        running); SCALE snaps to 1.0 (the job is already live — the node
        count changes but no cold-start delay applies); JOB_END/CANCELLED
        removes the ramp entry alongside the node count.
        """
        unmapped = signal.hardware_profile_id not in self.hardware_library

        if signal.event_type == WorkloadEventType.STARTING:
            self._node_counts[signal.job_id] = signal.node_count
            self._job_profiles[signal.job_id] = signal.hardware_profile_id
            self._ramp_progress[signal.job_id] = 0.0          # begin Δt_lead ramp
        elif signal.event_type == WorkloadEventType.SCALE:
            self._node_counts[signal.job_id] = signal.node_count
            self._job_profiles[signal.job_id] = signal.hardware_profile_id
            self._ramp_progress[signal.job_id] = 1.0          # already live, no ramp
        elif signal.event_type in (WorkloadEventType.JOB_END, WorkloadEventType.CANCELLED):
            self._node_counts.pop(signal.job_id, None)
            self._job_profiles.pop(signal.job_id, None)
            self._ramp_progress.pop(signal.job_id, None)
        # checkpoint_start/checkpoint_end intentionally leave node_count
        # untouched -- the classifier (dispatch.py) reads the resulting
        # draw shape, it doesn't get a node-count signal of its own.

        if unmapped:
            self.unmapped_profile_seen.add(signal.hardware_profile_id)
        return unmapped

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        """Advance the Δt_lead ramp for every job currently in mid-ramp.

        Step 3 Item 2: advance() is no longer a no-op.  Each tick the
        progress fraction for ramping jobs increases by dt_seconds /
        ramp_seconds, clamped at 1.0 (full TDP).  Jobs with progress
        already at 1.0 skip the update so steady-state runs are free.
        """
        for job_id in list(self._ramp_progress):
            p = self._ramp_progress[job_id]
            if p < 1.0:
                self._ramp_progress[job_id] = min(1.0, p + dt_seconds / self.ramp_seconds)

    def output_mw(self) -> float:
        """Sum of current (ramped) per-job draws across all active jobs."""
        return sum(self.per_job_compute_mw(job_id) for job_id in self._node_counts)

    def per_job_compute_mw(self, job_id: str) -> float:
        """Current (ramped) draw for job_id: Nodes_i × kW_i × PUE_base / 1000
        × _ramp_multiplier(progress).

        CURRENT draw — partial during the Δt_lead window.  All three items
        in Step 3 consume this:
          Item 1 — checkpoint classifier: sees actual draw shape (dips detectable)
          Item 2 — P_compute(t) / cooling input: sees the ramping load
          Item 3 — per-job cooling superposition: each job's own lagged trace

        Returns 0.0 if job_id is not active on this module.
        Use per_job_target_mw() when you need full-TDP regardless of ramp.
        """
        nodes = self._node_counts.get(job_id, 0)
        if nodes == 0:
            return 0.0
        profile_id = self._job_profiles.get(job_id, "")
        profile = self.hardware_library.get(profile_id, GENERIC_FALLBACK_PROFILE)
        full_kw = nodes * profile.rated_kw * self.site.pue_base / 1000.0
        progress = self._ramp_progress.get(job_id, 1.0)  # 1.0 = fully ramped
        return full_kw * self._ramp_multiplier(progress)

    def per_job_target_mw(self, job_id: str) -> float:
        """Full-TDP draw for job_id, regardless of ramp progress.

        TARGET draw — used by apply_workload_signal() for staging:
        stage_for_predicted_step() must plan for the load the job will
        eventually place, not the near-zero draw at the STARTING tick.
        Staging with current draw (ramp=0) would produce delta_p≈0 and
        the turbine would stage for nothing — exactly the trap §6.1 warns
        about.

        Returns 0.0 if job_id is not active on this module.
        """
        nodes = self._node_counts.get(job_id, 0)
        if nodes == 0:
            return 0.0
        profile_id = self._job_profiles.get(job_id, "")
        profile = self.hardware_library.get(profile_id, GENERIC_FALLBACK_PROFILE)
        return nodes * profile.rated_kw * self.site.pue_base / 1000.0

    def target_output_mw(self) -> float:
        """Sum of full-TDP draws across all active jobs (no ramp adjustment).

        Used in apply_workload_signal() staging: computing delta_p_mw as
        (target_after − target_before) gives the anticipated load increment
        the dispatch fleet must pre-stage for, irrespective of how far
        through their individual ramps the current jobs are.
        """
        return sum(self.per_job_target_mw(job_id) for job_id in self._node_counts)

    def active_training_jobs(self) -> list[str]:
        return [
            job_id
            for job_id in self._node_counts
            if self._job_profiles.get(job_id)  # profile known -> job is active
        ]

    def has_active_unmapped_jobs(self) -> bool:
        """True if any currently active job on this module uses a hardware
        profile that is not present in the library.

        Called per-tick by evaluate_tick() to tag the *segment* rather than
        the run.  §5.1 and §12 require the affected segment to be tagged;
        a sticky run-global flag (the previous approach) tagged every
        subsequent segment even after the unmapped job ended.
        """
        return any(
            self._job_profiles.get(job_id) not in self.hardware_library
            for job_id in self._node_counts
        )


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
        given current state of charge and power rating.

        §7.2 step 4 specifies "the BESS's max sustainable discharge duration
        AT THE REQUIRED POWER LEVEL."  A unit cannot sustain any power level
        above its rated_mw — for any duration — so the answer is 0.0 in that
        case.  The pre-D11 code omitted this check and computed energy /
        discharge_mw, producing a finite (but physically impossible) duration
        when discharge_mw > rated_mw.  That is the energy-vs-time confusion
        §7.2 step 4's parenthetical warns against: 516 s sustainable on a
        14 MW draw from a 5 MW battery is a false negative.

        D11 fix: return 0.0 whenever discharge_mw exceeds rated_mw.
        """
        if discharge_mw <= 0:
            return math.inf
        # D11 fix: power ceiling.  Above rating the unit cannot deliver at all.
        if discharge_mw > self.config.rated_mw:
            return 0.0
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
