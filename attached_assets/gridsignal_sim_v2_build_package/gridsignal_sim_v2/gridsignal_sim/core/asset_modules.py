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
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import (
    BessConfig,
    GENERIC_FALLBACK_PROFILE,
    HardwareProfile,
    IslandMode,
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

    def min_ramp_remaining_seconds(self) -> float:
        """Minimum remaining ramp time across in-flight jobs (ramp_progress < 1.0).

        Used by evaluate_tick() to compute dt_lead_next_s (hero panel countdown).
        Returns math.inf when no jobs are currently ramping (all at full TDP or
        no active jobs).  The caller converts math.inf to 0.0 ("no active ramp").

        C2 correction: the hero countdown shows when the NEXT job reaches full TDP.
        Only min() has that semantics; sum() across two jobs' remaining times does
        not correspond to any physical event.
        """
        remaining = (
            (1.0 - p) * self.ramp_seconds
            for p in self._ramp_progress.values()
            if p < 1.0
        )
        return min(remaining, default=math.inf)

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
# Cooling module -- source spec Section 8 / Build Plan v2.2 Step 3 Item 3
# ---------------------------------------------------------------------------

@dataclass
class _LoadEnvelope:
    """One job's (or synthetic step-load's) lagged cooling contribution.

    onset_t    — t₀ₖ: the STARTING event timestamp (simulation path) or the
                 sim_time at which a step-up was detected (scalar path).
    load_mw    — scalar-path only: constant step-load size; preserved on
                 close (do NOT zero on JOB_END) so _lagged_mw can return the
                 historical load for target_time in [onset_t, end_t].
    history    — simulation path: deque of (sim_t, mw) per-tick samples from
                 GPUModule.per_job_compute_mw(), enabling ramp-varying loads.
    end_t      — set on JOB_END/CANCELLED; envelope is retained for
                 dt_thermal + 5·τ seconds after this time, then pruned.
                 Retention rule (P3): "the heat is already in the room" —
                 P_cooling stays elevated for ~dt_thermal seconds after job
                 end, then decays as the lagged compute term crosses end_t.
                 Pruning earlier causes a discontinuous P_cooling drop; never
                 pruning leaks memory.  Pruning happens in advance().

    Cursor fields (P1 — O(1) amortised lagged-sample lookup):
    _cursor_abs    — absolute index into the conceptual "all samples ever
                     appended" sequence.  Deque-relative index is
                     cursor_rel = _cursor_abs - _pruned_count.
    _pruned_count  — samples popped from the left of the deque via popleft().
                     Invariant: _cursor_abs >= _pruned_count always.
    THE TRAP: if you hold a plain integer index into the deque and call
    popleft(), the index silently refers to the wrong element.  The absolute
    counter + pruned_count pair avoids this: cursor_rel stays valid after
    each popleft() because _pruned_count is incremented in lockstep.
    """
    onset_t: float
    load_mw: float = 0.0
    history: deque = field(default_factory=deque)   # deque of (sim_t, mw)
    end_t: Optional[float] = None
    _pruned_count: int = field(default=0, init=False)
    _cursor_abs: int = field(default=0, init=False)


@dataclass
class CoolingModule(AssetModule):
    """Per-job cooling superposition (Step 3 Item 3 — v2.5 §8, §11.1).

    P_cooling(t) = Σₖ αₖ(t) × P_compute_k(t − Δt_thermal)
    αₖ(t) = α_max × (1 − e^−(t − t₀ₖ − Δt_thermal)/τ)   for t ≥ t₀ₖ + Δt_thermal
           = 0                                             otherwise

    k indexes JOBS, not detected aggregate step-loads.  Each job has its own
    envelope so that:
      (a) a second job's cooling rises smoothly from zero after its own
          dt_thermal lag — not as a step discontinuity into an already-settled
          alpha (the aliasing §8 warns against);
      (b) ending a job does NOT collapse its cooling contribution; heat
          already in the room drains over dt_thermal + 5·τ seconds.

    Two interfaces feed this module:

    Scalar path — record_compute_sample(t, float):
        Backward-compatible interface used by direct-unit tests (e.g. audit
        tests, test_tc02, test_tc03) that work with aggregate P_compute.
        Step-up changes (delta > 0) create a synthetic envelope at that
        sim_time; step-downs mark the youngest live envelope ended.

    Simulation path — register_job_start / register_job_end / record_job_compute:
        Called by simulation_core.py using the STARTING event timestamp as
        t₀ₖ and per_job_compute_mw() as the varying load trace.  This is the
        canonical path; the engine must not infer onset from aggregate draw
        shape — it reads the STARTING signal directly.

    §12 identity: at steady state Σₖ αₖ × P_k = α_max × P_compute, so
    effective PUE = PUE_base × (1 + α_max), same as the pre-Item-3 formula.
    """

    asset_id: str
    site: SiteConfig
    _envelopes: dict[str, _LoadEnvelope] = field(default_factory=dict)
    _last_output_mw: float = 0.0
    # Scalar-path state
    _prev_agg_mw: float = 0.0
    _synth_counter: int = 0

    # ------------------------------------------------------------------
    # Simulation path
    # ------------------------------------------------------------------

    def register_job_start(self, job_id: str, onset_t: float) -> None:
        """Record t₀ₖ from the STARTING event.  Called by apply_workload_signal().

        Creates a fresh envelope; existing history for the same job_id (from a
        previous run reusing an id) is discarded so the onset is correct.
        """
        self._envelopes[job_id] = _LoadEnvelope(onset_t=onset_t)

    def register_job_end(self, job_id: str, end_t: float) -> None:
        """Mark envelope ended.  Retained for dt_thermal + 5·τ, then pruned.

        Pruning location: advance() checks end_t against the retention window
        each tick.  Pruning in advance() rather than here prevents an early
        caller from inadvertently dropping history mid-drain.
        """
        if job_id in self._envelopes:
            self._envelopes[job_id].end_t = end_t

    def record_job_compute(self, sim_time: float,
                            per_job_mw: dict[str, float]) -> None:
        """Per-tick simulation-path sample.  Called from evaluate_tick() after
        GPU advance() so the draw already reflects the Item 2 ramp.

        Job IDs absent from _envelopes (started before this module was
        initialised, or using the scalar path) are silently skipped.

        P1 pruning: popleft() is O(1) on deque.  _pruned_count is incremented
        in lockstep so cursor_rel = _cursor_abs - _pruned_count stays valid
        after each removal.  THE TRAP: a bare integer index into the deque
        would silently point at the wrong sample after the first popleft().
        """
        retention_buf = self.site.dt_thermal_seconds * 2 + 10
        cutoff = sim_time - retention_buf
        for job_id, mw in per_job_mw.items():
            env = self._envelopes.get(job_id)
            if env is None:
                continue
            env.history.append((sim_time, mw))
            # Keep at least one sample; popleft() shifts deque positions, so
            # _pruned_count must be incremented in lockstep with each removal.
            while len(env.history) > 1 and env.history[0][0] < cutoff:
                env.history.popleft()
                env._pruned_count += 1
            # Pin cursor to new head if pruning advanced past it (safety guard).
            if env._cursor_abs < env._pruned_count:
                env._cursor_abs = env._pruned_count

    # ------------------------------------------------------------------
    # Scalar path (backward compat)
    # ------------------------------------------------------------------

    def record_compute_sample(self, sim_time: float, p_compute_mw: float) -> None:
        """Scalar aggregate interface — backward compat for unit tests.

        Each step-up creates a synthetic envelope (onset_t=sim_time, load_mw=delta).
        Step-downs close the youngest live envelope(s) WITHOUT zeroing load_mw,
        so _lagged_mw still returns the historical load for target_time in
        [onset_t, end_t] and P_cooling drains over ~dt_thermal after the job ends.

        Partial reduction: the closed envelope keeps its original load_mw; a
        continuation envelope is spawned at the same onset_t with the reduced load.

        IMPORTANT: simulation_core.py calls register_job_start() +
        record_job_compute() instead, so onset timestamps come from STARTING
        events — the engine must never infer t₀ from aggregate draw shape.
        """
        _EPS = 1e-9
        delta = p_compute_mw - self._prev_agg_mw
        if delta > _EPS:
            key = f"_syn_{self._synth_counter}"
            self._synth_counter += 1
            self._envelopes[key] = _LoadEnvelope(onset_t=sim_time, load_mw=delta)
        elif delta < -_EPS:
            # Close youngest live envelope(s) to account for the load drop.
            # DO NOT zero load_mw: _lagged_mw uses it for target_time < end_t,
            # keeping P_cooling elevated for ~dt_thermal after the job ends.
            remaining = -delta
            for key in reversed(list(self._envelopes)):
                env = self._envelopes[key]
                if env.end_t is not None:
                    continue
                if env.load_mw <= remaining + _EPS:
                    # Close whole envelope; preserve load_mw for lagged history.
                    env.end_t = sim_time
                    remaining -= env.load_mw
                else:
                    # Partial reduction: close old envelope (load_mw unchanged),
                    # spawn continuation at same onset_t with reduced load.
                    env.end_t = sim_time
                    reduced = env.load_mw - remaining
                    remaining = 0.0
                    new_key = f"_syn_{self._synth_counter}"
                    self._synth_counter += 1
                    self._envelopes[new_key] = _LoadEnvelope(
                        onset_t=env.onset_t, load_mw=reduced
                    )
                if remaining <= _EPS:
                    break
        self._prev_agg_mw = p_compute_mw

    # ------------------------------------------------------------------
    # Shared internals
    # ------------------------------------------------------------------

    def _lagged_mw(self, env: _LoadEnvelope, target_time: float) -> float:
        """Lagged compute for one envelope at t − dt_thermal.

        Simulation path (history populated): cursor-based forward scan.
          lag_time advances monotonically each tick, so _cursor_abs only moves
          forward — amortised O(1).  SIDE EFFECT: advances _cursor_abs in-place.
          cursor_rel = _cursor_abs - _pruned_count is the deque-relative index;
          _pruned_count compensates for popleft() calls so the index stays valid.

        Scalar path (history empty): step load active for target_time in
          [onset_t, end_t].  load_mw is NEVER zeroed on close (see
          record_compute_sample step-down handler) so the historical load is
          available for the full dt_thermal drain window after job end.

        Returns 0.0 if the envelope had not yet started at target_time.
        """
        if env.history:
            # Simulation path — cursor-based forward scan.
            if target_time < env.onset_t:
                return 0.0
            cursor_rel = env._cursor_abs - env._pruned_count
            while (cursor_rel + 1 < len(env.history)
                   and env.history[cursor_rel + 1][0] <= target_time):
                env._cursor_abs += 1
                cursor_rel += 1
            return env.history[cursor_rel][1]
        else:
            # Scalar path — step load from onset_t to end_t (inclusive).
            if target_time < env.onset_t:
                return 0.0
            if env.end_t is not None and target_time > env.end_t:
                return 0.0
            return env.load_mw

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        """Sum per-envelope αₖ × P_k_lagged and prune expired envelopes.

        Retention rule (P3): an ended envelope is removed when
          sim_time > end_t + dt_thermal + 5·τ
        That is dt_thermal + 5·τ = 90 + 100 = 190 s after end_t with SITE
        defaults.  Pruning earlier drops P_cooling discontinuously because the
        lagged compute term still references history inside that window.  Never
        pruning leaks one envelope per job per run.  Pruning happens here, once
        per tick, so the hot path is a single dict iteration.
        """
        retention = self.site.dt_thermal_seconds + 5.0 * self.site.tau_seconds
        lag_time = sim_time - self.site.dt_thermal_seconds
        total = 0.0

        for key in list(self._envelopes):
            env = self._envelopes[key]

            # Prune envelopes whose heat has fully dissipated.
            if env.end_t is not None and sim_time > env.end_t + retention:
                del self._envelopes[key]
                continue

            # αₖ(t): zero until dt_thermal has elapsed since onset.
            threshold = env.onset_t + self.site.dt_thermal_seconds
            if sim_time < threshold:
                continue  # α_k = 0 before thermal delay expires
            elapsed = sim_time - threshold
            alpha_k = self.site.alpha_max * (
                1.0 - math.exp(-elapsed / self.site.tau_seconds)
            )

            total += alpha_k * self._lagged_mw(env, lag_time)

        self._last_output_mw = total

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
        using the full available lead time.

        Hot-standby units are excluded: they are not synchronized to the bus
        and must not receive automatic dispatch orders.  Their start time is
        a separate, operator-initiated action.
        """
        if self.config.hot_standby:
            return
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

    def bridging_available_mw(self, island_mode: IslandMode) -> float:
        """Anchor-adjusted bridging power ceiling (v2.5 §7.1.2).

            BESS_bridging_available(t) = min(rated, usable SoC) − P_anchor_reserve

        P_anchor_reserve is non-zero only when BOTH conditions hold:
          1. This unit is the designated grid-forming anchor (grid_forming=True).
          2. The site is in ISLANDED mode (island_mode=IslandMode.ISLANDED).
        In any other combination (grid-following unit, or grid-tie mode),
        P_anchor_reserve = 0 and the full rated power is available for bridging.

        Conservative default: grid_forming=False → most units have no deduction.
        The anchor role must be explicitly assigned; it must not be assumed.
        """
        anchor_deduction = (
            self.config.p_anchor_reserve_mw
            if self.config.grid_forming and island_mode == IslandMode.ISLANDED
            else 0.0
        )
        return max(0.0, self.config.rated_mw - anchor_deduction)

    def cover_shortfall(
        self,
        allocated_mw: float,
        fleet_covered: bool,
        dt_seconds: float,
        power_ceiling_mw: float,
    ) -> float:
        """Discharge this unit's proportionally allocated share of the fleet shortfall.

        Step 3 Item 4 — this unit no longer receives the full fleet shortfall.
        The DispatchArbitrator splits peak_shortfall proportional to each unit's
        bridging_available_mw before calling cover_shortfall, so allocated_mw
        is at most this unit's bridging_available_mw.

        fleet_covered — True when turbine_output >= p_dispatch_required at the
          fleet level.  Controls the taper timer: once turbines have covered the
          fleet shortfall for 10 continuous seconds, this unit tapers to standby.
          Using the fleet-level flag (not per-unit allocation) ensures a unit
          with zero allocation (e.g. depleted) does NOT falsely advance its taper
          timer while the fleet still has a shortfall.

        power_ceiling_mw — pre-computed bridging_available_mw for this unit,
          passed in by DispatchArbitrator.tick() which hoists the computation
          once per tick (P4 fix).  This avoids a redundant self.site.island_mode
          read and a bridging_available_mw() call inside the hot per-tick loop.
          The anchor reserve is still enforced; the caller computed the ceiling
          with the correct island_mode before entering the loop.
        """
        if fleet_covered:
            self._sustained_catchup_seconds += dt_seconds
        else:
            self._sustained_catchup_seconds = 0.0

        if self._sustained_catchup_seconds >= 10.0:
            self._current_output_mw = 0.0
            return 0.0

        if allocated_mw <= 0:
            return 0.0

        max_by_power = power_ceiling_mw
        max_by_energy = self.soc_mwh / (dt_seconds / 3600.0) if dt_seconds > 0 else max_by_power
        discharge_mw = min(allocated_mw, max_by_power, max_by_energy)

        self.soc_mwh = max(0.0, self.soc_mwh - discharge_mw * (dt_seconds / 3600.0))
        self._current_output_mw = discharge_mw
        return discharge_mw

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        return  # state is updated via cover_shortfall(), called by the arbitrator each tick

    def output_mw(self) -> float:
        return self._current_output_mw

    def max_sustainable_seconds(self, discharge_mw: float, island_mode: IslandMode) -> float:
        """Used by the insufficient-reserve check (dispatch.py):
        how long, in seconds, this BESS can sustain `discharge_mw` given
        current state of charge and anchor-adjusted power ceiling.

        §7.2 step 4: "the BESS's max sustainable discharge duration AT THE
        REQUIRED POWER LEVEL."  A unit cannot sustain any power level above
        its bridging_available_mw — for any duration — so the answer is 0.0.

        D11 fix (extended to anchor reserve): the power ceiling is now
        bridging_available_mw(island_mode), not raw rated_mw.  An anchor unit
        can only deliver up to (rated_mw − p_anchor_reserve_mw), so a discharge
        request above that returns 0.0.  Omitting the anchor deduction would
        allow an anchor to appear capable when it is not — exactly the TC-61/
        TC-63 failure mode the constraint exists to prevent.
        """
        if discharge_mw <= 0:
            return math.inf
        effective_ceiling = self.bridging_available_mw(island_mode)
        if discharge_mw > effective_ceiling:
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
        """Return the irradiance fraction for sim_time.

        Convention — zero-order hold ("value applies from t onward"):
        Each sample specifies the value that holds from its timestamp
        forward until the next sample.  The last sample's value applies
        for all time beyond it.

        Examples:
          [(0.0, 1.0)]                  → always 1.0
          [(0.0, 1.0), (30.0, 0.0)]     → 1.0 for t < 30, 0.0 for t ≥ 30
          [(0.0, 1.0), (end, 1.0)]      → always 1.0 (degenerate constant)

        Consequence: duplicate timestamps are unnecessary.  The old style
        [(0, 1.0), (30, 1.0), (30, 0.0)] was used to model a step-drop;
        simply [(0, 1.0), (30, 0.0)] expresses the same thing with fewer
        samples.  If two samples share a timestamp the last one (by sort
        order) wins, which matches the intuitive "override" reading.
        """
        if not self._samples:
            return 1.0
        result = self._samples[0][1]   # value before the first anchor
        for t, f in self._samples:
            if t <= sim_time:
                result = f
            else:
                break
        return result
