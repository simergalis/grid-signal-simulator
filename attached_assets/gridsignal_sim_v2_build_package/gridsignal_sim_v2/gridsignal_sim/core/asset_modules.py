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
from typing import Any, Optional

import numpy as np

from .models import (
    BessConfig,
    GENERIC_FALLBACK_PROFILE,
    HardwareProfile,
    IslandMode,
    SiteConfig,
    SolarConfig,
    ThermalState,
    TurbineConfig,
    TurbineState,
    UnitAvailability,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from .step_config import LoadProfileConfig


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
    # 120 s chosen so the ramp spans multiple UI frames even at high sim speeds
    # (process launch → NCCL/collective init → dataloader spin-up → first steps).
    ramp_seconds: float = 120.0
    _ramp_progress: dict[str, float] = field(default_factory=dict)  # job_id -> [0.0, 1.0]

    # ── Within-step power profile (stochastic-step spec Part 2) ─────────────
    # load_config — when set, per_job_compute_mw() applies a within-step power
    #   profile (compute vs allreduce phases) with first-order GPU lag.
    #   None (default) = pure ramp formula, preserving all existing test
    #   behaviour.  Set by scenario_factory when kube_config.load_config is set.
    load_config: Optional[LoadProfileConfig] = None

    # step_phase — fractional position within the current ML step, ∈ [0, 1).
    #   Set each tick by simulation_core from kube_agent.current_step_phase
    #   BEFORE advance() is called so the lag update uses the correct phase.
    #   Defaults to 0.0 (compute phase) so the formula is identical to the
    #   existing formula when load_config is None.
    step_phase: float = 0.0

    # _lag_raw_profile — first-order lag state for the within-step power profile.
    #   Smooths the sharp compute↔allreduce transition with tau_gpu_s.
    #   Initialised to 1.0 (compute phase at power 1.0).
    _lag_raw_profile: float = field(default=1.0, repr=False)

    # _auto_step_period_s — when > 0, advance() self-computes step_phase from
    #   sim_time % period / period each tick.  This is the non-kube path: for
    #   scenarios using scripted workload_events (no KubeAgent), setting this
    #   enables compute vs allreduce phase variation without needing a kube
    #   scheduler.  Period = StepTimingConfig.median_step_s default (0.70 s).
    #
    #   0.0 = disabled (kube path — simulation_core sets step_phase externally
    #   BEFORE advance() so we must NOT overwrite it here).
    _auto_step_period_s: float = field(default=0.0, repr=False)

    # rng_load — numpy Generator for per-tick load noise.
    #   None (default) = no noise, preserving all existing test determinism.
    #   Injected by scenario_factory from kube_agent.rng_load after the agent
    #   is created (so all modules share the same noise stream as the agent).
    rng_load: Any = field(default=None, repr=False)

    # Scale-up cohort tracking.
    # When a SCALE-UP event arrives, added nodes are cold — they undergo the
    # same container-init / weight-load ramp as a fresh STARTING event.  We
    # split the job into the original cohort (existing key, unchanged ramp
    # progress) and a new delta cohort (key = job_id + "-cohort-N", progress=0).
    #
    # _desired_node_counts — authoritative total per job (updated on every SCALE).
    #     Delta for any SCALE is always computed against this, NOT against
    #     _node_counts[job_id] (which only holds the base cohort's count and
    #     is stale after scale-ups).  Without this guard, two consecutive
    #     SCALEs would compute deltas against the original base each time,
    #     inflating effective nodes beyond the requested total.
    # _cohort_counters  — monotonic counter per job; ensures cohort keys are unique.
    # _job_cohorts      — maps base job_id → ordered list of live cohort keys.
    #     Ordered newest-last so scale-down can reduce from the newest first.
    # _last_scale_cohort_key — set by apply_signal(SCALE-UP) so simulation_core
    #     can register a CoolingModule envelope for the new cohort; None otherwise.
    # _last_scale_removed_cohort_keys — set by apply_signal(SCALE-DOWN) to the
    #     list of cohort keys whose node count was reduced to zero and therefore
    #     removed from _node_counts.  simulation_core reads this to call
    #     cooling.register_job_end() for each, so the cooling envelopes start
    #     their drain countdown rather than staying elevated indefinitely.
    #     Empty list when no cohorts were fully removed (partial reductions or
    #     scale-down against the base only).
    _desired_node_counts: dict[str, int] = field(default_factory=dict)
    _cohort_counters: dict[str, int] = field(default_factory=dict)
    _job_cohorts: dict[str, list] = field(default_factory=dict)
    _last_scale_cohort_key: Optional[str] = field(default=None)
    _last_scale_removed_cohort_keys: list = field(default_factory=list)

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

        self._last_scale_cohort_key = None      # reset each call
        self._last_scale_removed_cohort_keys = []  # reset each call

        if signal.event_type == WorkloadEventType.STARTING:
            self._node_counts[signal.job_id] = signal.node_count
            self._job_profiles[signal.job_id] = signal.hardware_profile_id
            self._ramp_progress[signal.job_id] = 0.0          # begin Δt_lead ramp
            # Seed the authoritative desired count so SCALE deltas compute correctly.
            self._desired_node_counts[signal.job_id] = signal.node_count
        elif signal.event_type == WorkloadEventType.SCALE:
            # Always compute the delta against _desired_node_counts, NOT against
            # _node_counts[job_id].  After a scale-up, _node_counts[job_id] still
            # holds the original base count; using it as the baseline would double-
            # count the delta on every subsequent SCALE.
            old_desired = self._desired_node_counts.get(signal.job_id, 0)
            new_desired = signal.node_count

            if old_desired == 0:
                # No prior STARTING: snap to full (Kubernetes "already-running"
                # injection pattern — nodes were live before monitoring began).
                self._node_counts[signal.job_id] = new_desired
                self._job_profiles[signal.job_id] = signal.hardware_profile_id
                self._ramp_progress[signal.job_id] = 1.0
                self._desired_node_counts[signal.job_id] = new_desired
            elif new_desired > old_desired:
                # Scale-UP on a live job: added nodes are cold.
                # Base cohort retains its current ramp progress unchanged.
                delta_nodes = new_desired - old_desired
                cohort_n = self._cohort_counters.get(signal.job_id, 0) + 1
                self._cohort_counters[signal.job_id] = cohort_n
                cohort_key = f"{signal.job_id}-cohort-{cohort_n}"
                self._node_counts[cohort_key] = delta_nodes
                self._job_profiles[cohort_key] = signal.hardware_profile_id
                self._ramp_progress[cohort_key] = 0.0         # cold-start ramp
                self._job_cohorts.setdefault(signal.job_id, []).append(cohort_key)
                self._desired_node_counts[signal.job_id] = new_desired
                self._last_scale_cohort_key = cohort_key
            elif new_desired < old_desired:
                # Scale-DOWN: shed nodes from newest cohorts first (no ramp reset),
                # then reduce the base entry if cohorts are exhausted.
                # Track fully-removed cohorts so simulation_core can end their
                # CoolingModule envelopes; without this, the envelope has no
                # end_t and retains its last historical power level indefinitely.
                reduction = old_desired - new_desired
                for cohort_key in list(reversed(self._job_cohorts.get(signal.job_id, []))):
                    if reduction <= 0:
                        break
                    cohort_nodes = self._node_counts.get(cohort_key, 0)
                    if reduction >= cohort_nodes:
                        # Remove this cohort entirely — record it for cooling cleanup.
                        self._node_counts.pop(cohort_key, None)
                        self._job_profiles.pop(cohort_key, None)
                        self._ramp_progress.pop(cohort_key, None)
                        self._job_cohorts[signal.job_id].remove(cohort_key)
                        self._last_scale_removed_cohort_keys.append(cohort_key)
                        reduction -= cohort_nodes
                    else:
                        # Partially reduce — ramp progress of surviving nodes unchanged.
                        # Cooling for the reduced cohort will self-correct as the
                        # lower-power samples fill in via record_job_compute().
                        self._node_counts[cohort_key] -= reduction
                        reduction = 0
                # Any remaining reduction falls on the base entry.
                if reduction > 0:
                    base = self._node_counts.get(signal.job_id, 0)
                    self._node_counts[signal.job_id] = max(0, base - reduction)
                self._desired_node_counts[signal.job_id] = new_desired
            # new_desired == old_desired: desired count already correct, no-op.
        elif signal.event_type in (WorkloadEventType.JOB_END, WorkloadEventType.CANCELLED):
            self._node_counts.pop(signal.job_id, None)
            self._job_profiles.pop(signal.job_id, None)
            self._ramp_progress.pop(signal.job_id, None)
            # Clean up all scale-up cohorts spawned from this job.
            for cohort_key in self._job_cohorts.pop(signal.job_id, []):
                self._node_counts.pop(cohort_key, None)
                self._job_profiles.pop(cohort_key, None)
                self._ramp_progress.pop(cohort_key, None)
            self._cohort_counters.pop(signal.job_id, None)
            self._desired_node_counts.pop(signal.job_id, None)
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

        Stochastic-step Part 2: when load_config is set, update the
        first-order lag on the raw power profile.  step_phase is set by
        simulation_core from kube_agent.current_step_phase BEFORE this
        call so the lag always tracks the current step position.
        """
        for job_id in list(self._ramp_progress):
            p = self._ramp_progress[job_id]
            if p < 1.0:
                self._ramp_progress[job_id] = min(1.0, p + dt_seconds / self.ramp_seconds)

        # Within-step power profile lag (Part 2.2 — transition smoothing).
        # raw_profile switches between 1.0 (compute phase) and p_comm_ratio
        # (allreduce phase) based on step_phase.  The first-order lag with
        # tau_gpu_s smooths the sharp edge so the power signal is band-limited.
        if self.load_config is not None:
            # Non-kube path: self-manage step_phase from sim_time.
            # Kube path: step_phase is set externally by simulation_core BEFORE
            # advance() so _auto_step_period_s is 0.0 there and this branch
            # is skipped — the externally-set value is used as-is.
            if self._auto_step_period_s > 0.0:
                if dt_seconds >= self._auto_step_period_s:
                    # Tick spans multiple complete steps (dt >> period).
                    # Point-sampling step_phase aliases harshly against the tick
                    # grid and produces large artificial jumps on the display
                    # (e.g. 6.3 → 2.91 MW every few ticks at dt=5 s, period=0.7 s).
                    # Use the duty-cycle average instead: every full-step tick
                    # sees the same weighted mix of compute and allreduce power,
                    # which is the physically correct coarse-grained value.
                    raw_profile = (
                        self.load_config.f_compute * 1.0
                        + (1.0 - self.load_config.f_compute)
                        * self.load_config.p_comm_ratio
                    )
                else:
                    self.step_phase = (
                        math.fmod(sim_time, self._auto_step_period_s)
                        / self._auto_step_period_s
                    )
                    raw_profile = (
                        1.0 if self.step_phase < self.load_config.f_compute
                        else self.load_config.p_comm_ratio
                    )
            else:
                raw_profile = (
                    1.0 if self.step_phase < self.load_config.f_compute
                    else self.load_config.p_comm_ratio
                )
            # Discrete first-order lag: alpha = 1 - exp(-dt/tau).
            # At tau_gpu_s=0.06 s, dt=0.1 s (10 Hz): alpha ≈ 0.811 (fast).
            alpha = 1.0 - math.exp(
                -dt_seconds / max(self.load_config.tau_gpu_s, 1e-9)
            )
            self._lag_raw_profile += alpha * (raw_profile - self._lag_raw_profile)

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
        base_draw = full_kw * self._ramp_multiplier(progress)

        # ── Stochastic-step Part 2: within-step power profile ─────────────────
        # Only applied when load_config is set (kube path with step scheduler).
        # When load_config is None the formula reduces to the existing pure-ramp
        # return, preserving ALL existing test behaviour with zero code change.
        if self.load_config is not None:
            # effective_profile = 1 + phase_coherence * (lag_state - 1)
            #   lag_state tracks the smoothed raw_profile (compute vs allreduce).
            #   phase_coherence = 0 → flat (fleet incoherent) → L2 criterion.
            #   phase_coherence = 1 → full oscillation depth.
            effective_mult = (
                1.0
                + self.load_config.phase_coherence * (self._lag_raw_profile - 1.0)
            )
            result = base_draw * effective_mult
            # Gaussian noise: small fractional sigma so the checkpoint classifier's
            # 15% threshold is unaffected (0.5% << 15%).
            if self.rng_load is not None:
                noise = self.rng_load.normal(
                    0.0, base_draw * self.load_config.noise_sigma_fraction
                )
                result = max(0.0, result + noise)
            return result

        return base_draw

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

    def effective_node_count(self) -> int:
        """Node count weighted by current ramp progress, matching the power curve.

        During the Δt_lead ramp window, newly admitted jobs haven't reached full
        TDP.  For UI consistency the reported node count is scaled by the same
        _ramp_multiplier used for power so the COMPUTE RACKS tile rises in
        lock-step with P_compute rather than snapping to the admitted count the
        moment a STARTING signal is processed.

        PROTO-1 note: _ramp_multiplier is a chosen piecewise curve (no measured
        basis).  Effective node count therefore inherits the same prototype
        caveat — it is a display-only metric, not used for dispatch sizing.

        Fully-ramped jobs (progress == 1.0) always contribute their full
        node_count so that steady-state runs produce no rounding artefacts.
        """
        total = 0
        for job_id, nodes in self._node_counts.items():
            progress = self._ramp_progress.get(job_id, 1.0)
            if progress >= 1.0:
                total += nodes
            else:
                total += round(nodes * self._ramp_multiplier(progress))
        return total

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

    def record_compute_sample(self, sim_time: float, p_compute_demand_mw: float) -> None:
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
        delta = p_compute_demand_mw - self._prev_agg_mw
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
        self._prev_agg_mw = p_compute_demand_mw

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

# TurbineState is defined in models.py (Phase 2 refactor) and re-exported here
# for backward compatibility with any code that imports from asset_modules.
# Do not redefine it here — models.py is the single source of truth.


@dataclass
class TurbineModule(AssetModule):
    config: TurbineConfig
    state: TurbineState = TurbineState.OFFLINE
    _current_output_mw: float = 0.0
    # R4–R6 run-time tracking (Phase 13.5)
    # _run_start_s: sim_time when the current run started.  math.nan = never
    #   started (or stopped and time already recorded in _stop_time_s).
    _run_start_s: float = math.nan
    # _stop_time_s: sim_time of the last controlled stop.  math.nan = never
    #   stopped.  Guards t_min_down_s enforcement on the next restart.
    _stop_time_s: float = math.nan
    # Phase 2: thermal state and start sequence tracking
    # _thermal_state: seeded from config.initial_thermal_state in __post_init__;
    # then updated at each command_start() from time-offline heuristic.
    _thermal_state: ThermalState = ThermalState.COLD
    # _time_to_online_s: countdown timer while STARTING; 0 when SYNCHRONISED.
    _time_to_online_s: float = 0.0
    # _last_sync_stop_s: sim_time when last SYNCHRONISED → OFFLINE transition
    #   completed.  Used to classify the next start as HOT/WARM/COLD.
    _last_sync_stop_s: float = math.nan
    # _out_of_service_reason: non-None only when state == OUT_OF_SERVICE.
    _out_of_service_reason: Optional[str] = None
    # _start_phase: human-readable label for the STARTING sub-phase (display only).
    _start_phase: str = "purge"
    # Phase E Item 5: levelled-off dwell tracker.
    # When the UNLOADING unit's output first reaches its MSL setpoint within
    # levelled_off_tol_mw, this is set to the current sim_time.  The breaker opens
    # once (sim_time − _levelled_off_since_s) ≥ config.unload_tail_s.
    # Reset to math.nan whenever the predicate is False or the breaker opens.
    _levelled_off_since_s: float = math.nan
    # Phase E+ Item 4: sustained levelled-off predicate broadcast on the wire.
    # True only once the dwell has exceeded levelled_off_window_s — the same
    # threshold the commitment engine uses, not just "started holding".
    # The panel and the breaker-open gate therefore agree.
    _levelled_off_sustained: bool = False
    # Phase E+: last setpoint commanded by the loading layer (before rate-clip).
    # Stored in set_output() so the commitment modal can render a per-unit
    # setpoint marker without a separate field on TickResult.  0.0 until the
    # first set_output() call (STARTING units never receive a setpoint call).
    _last_setpoint_mw: float = 0.0
    # Phase 4 (DR-2026-08-08-FREQ): governor cascade state (per-unit, MW domain).
    # _gov_valve_mw: current valve gate position (output of valve-lag first-order lag).
    # _gov_power_mw: current governor mechanical power output (output of fuel-lag).
    # Both are initialised to 0.0 (no governor correction at start of run).
    # Updated each sub-step in the swing-equation loop; persist across outer ticks.
    _gov_valve_mw: float = 0.0
    _gov_power_mw: float = 0.0
    # Phase B Item 2: per-interval write counter for set_output().
    # Reset to 0 by begin_interval() at the start of each evaluation interval.
    # Incremented by set_output(); if it reaches 2 a RuntimeError is raised,
    # catching any code path that calls set_output() twice in one interval.
    _output_writes: int = 0

    def __post_init__(self) -> None:
        # Seed thermal state from the scenario spec so the first command_start()
        # uses the operator-configured tier (hot/warm/cold) rather than always COLD.
        self._thermal_state = self.config.initial_thermal_state

    @property
    def asset_id(self) -> str:  # noqa: D401 -- property mirrors dataclass field name
        return self.config.asset_id

    @property
    def is_on_bus(self) -> bool:
        """True when the unit is electrically connected to the AC bus.

        Phase C: A = {SYNCHRONISED, UNLOADING} — both states produce output and
        count toward N-1 contingency.  UNLOADING units are tracking down through
        the loading layer but their breaker is still closed.
        Hot-standby units are never on bus regardless of state.

        Item 4 rationale: the old is_synchronised returned True for RAMPING and
        AT_TARGET (legacy states that no longer exist), producing misleading
        diagnostics.  The explicit name is_on_bus makes breaker-state semantics
        unambiguous.
        """
        return self.state in (
            TurbineState.SYNCHRONISED,
            TurbineState.UNLOADING,
        ) and not self.config.hot_standby

    @property
    def contributes_to_reserve(self) -> bool:
        """True when the unit holds upward headroom and should be credited toward reserve.

        Phase C: only SYNCHRONISED units have upward ramp headroom.  UNLOADING
        units are tracking down toward MSL and cannot respond upward.
        Hot-standby units are never counted regardless of state.
        """
        return self.state == TurbineState.SYNCHRONISED and not self.config.hot_standby

    def begin_interval(self) -> None:
        """Reset the per-interval write counter at the start of each evaluation interval.

        Called by simulation_core.evaluate_tick() before advance() so that
        set_output()'s double-write guard (Item 2, Phase B) is fresh for the
        new interval.  Tests that call advance() or set_output() directly and
        do not go through evaluate_tick() do not need to call this.
        """
        self._output_writes = 0

    def set_output(self, new_output_mw: float) -> None:
        """Set per-unit output MW.  Called by the loading layer for SYNCHRONISED units.

        Clamps to [0, rated_mw].  Does not change state.

        Phase B Item 2 — write counter guard:
          Increments _output_writes each time this method is called within an
          interval (i.e. between two begin_interval() calls).  If the counter
          reaches 2 a RuntimeError is raised immediately.  This catches any code
          path that writes to a unit's output twice in the same interval — for
          example, if a promoted unit were included in the loading set twice or if
          a second caller duplicated apply_loading().
        """
        self._output_writes += 1
        if self._output_writes > 1:
            raise RuntimeError(
                f"TurbineModule '{self.config.asset_id}': set_output() called "
                f"{self._output_writes} times in one interval (limit: 1).  "
                f"This is the Phase B double-write guard.  "
                f"Likely cause: the unit appears in _synchronised_units more than "
                f"once, or apply_loading() was called twice for the same unit.  "
                f"Fix: ensure _synchronised_units contains each unit at most once "
                f"and that begin_interval() is called at the start of each tick."
            )
        self._last_setpoint_mw = float(new_output_mw)   # store before rate-clip
        self._current_output_mw = max(0.0, min(new_output_mw, self.config.rated_mw))

    def command_start(self, sim_time: float) -> None:
        """Transition OFFLINE → STARTING.  Phase 2 commitment-logic entry point.

        Determines thermal state from time since last synchronisation, selects
        the appropriate start duration from config, and begins the countdown.
        No literals in state machine — all durations read from TurbineConfig.

        R6: minimum down-time (t_min_down_s) still enforced.  A start command
        during the cooling window is silently dropped (same as stage_target()).

        No output is produced while STARTING (_current_output_mw stays 0.0).
        """
        if self.config.hot_standby:
            return
        if self.state != TurbineState.OFFLINE:
            return

        # R6: enforce minimum down-time when the constraint is enabled.
        # Phase E closeout Item 1 / D-03: gated on min_down_enabled so tests
        # that create TurbineConfig() directly (min_down_enabled=False default)
        # are unaffected.
        if self.config.min_down_enabled and not math.isnan(self._stop_time_s):
            elapsed = sim_time - self._stop_time_s
            if elapsed < self.config.t_min_down_s:
                return  # cooling window not yet satisfied

        # Determine thermal state from time offline since last synchronisation.
        # First start (never stopped): use config.initial_thermal_state so the
        # scenario-specified tier (hot/warm/cold) is honoured rather than always
        # defaulting to the conservative cold path.  Subsequent restarts continue
        # to use the elapsed-time classifier (time since last sync stop).
        if math.isnan(self._last_sync_stop_s):
            self._thermal_state = self.config.initial_thermal_state
        else:
            elapsed_offline = sim_time - self._last_sync_stop_s
            if elapsed_offline < self.config.hot_threshold_s:
                self._thermal_state = ThermalState.HOT
            elif elapsed_offline < self.config.warm_threshold_s:
                self._thermal_state = ThermalState.WARM
            else:
                self._thermal_state = ThermalState.COLD

        # Start duration from config — no literals in state machine
        if self._thermal_state == ThermalState.HOT:
            self._time_to_online_s = self.config.hot_start_s
        elif self._thermal_state == ThermalState.WARM:
            self._time_to_online_s = self.config.warm_start_s
        else:
            self._time_to_online_s = self.config.cold_start_s

        self._start_phase = "purge"
        self.state = TurbineState.STARTING

    def unit_availability(self) -> "UnitAvailability":
        """Build a UnitAvailability boundary object from current state.

        Called by simulation_core.py each tick to build the availability list
        for reserve check and N-1 computation without exposing TurbineModule
        internals to consumers.
        """
        if self.state == TurbineState.OUT_OF_SERVICE:
            time_to_online: Optional[float] = None
        elif self.state == TurbineState.STARTING:
            time_to_online = self._time_to_online_s
        elif self.is_on_bus:
            # Item 4: is_on_bus = {SYNCHRONISED, UNLOADING} — availability is a
            # breaker-state question, not a reserve question.
            time_to_online = 0.0
        else:
            time_to_online = None

        return UnitAvailability(
            unit_id=self.config.asset_id,
            state=self.state,
            output_mw=self._current_output_mw,
            rated_mw=self.config.rated_mw,
            msl_mw=self.config.p_min_stable_frac * self.config.rated_mw,
            r_asset_effective_mw_per_s=self.config.r_asset_mw_per_s,
            time_to_online_s=time_to_online,
            out_of_service_reason=self._out_of_service_reason,
            hot_standby=self.config.hot_standby,
        )

    def command_stop(self, sim_time: float) -> Optional[str]:
        """Transition SYNCHRONISED → UNLOADING.  Phase E controlled-stop path.

        Phase E closeout Item 3: returns a block-reason string when the stop
        is deferred, and None when it is accepted.  The caller (simulation_core.py
        decommit path) propagates the reason into CommitmentDecision.blocked_by
        so it is visible in the fleet modal and run log.

        R5 enforcement (Phase E Item 8 / closeout Item 1): when min_run_enabled
        is True and the unit has not yet run for at least t_min_run_s seconds
        since it last reached SYNCHRONISED, the stop is deferred.  The caller
        may retry on the next decommit check.

        Raises RuntimeError for any state other than SYNCHRONISED — a loaded unit
        must not be transitioned directly to OFFLINE through any normal dispatch
        path.  Operator trips (emergency) go through the run_manager.py A-1
        drain loop.

        Returns
        -------
        None     — stop accepted; unit has transitioned to UNLOADING.
        str      — stop deferred; value is the block reason for blocked_by.
        """
        if self.state != TurbineState.SYNCHRONISED:
            raise RuntimeError(
                f"TurbineModule '{self.config.asset_id}': command_stop() called in "
                f"state {self.state.value!r}. Only SYNCHRONISED → UNLOADING is valid "
                f"here; operator trips use the run_manager trip path."
            )
        # R5: enforce minimum run time when the constraint is enabled.
        if (
            self.config.min_run_enabled
            and not math.isnan(self._run_start_s)
            and (sim_time - self._run_start_s) < self.config.t_min_run_s
        ):
            remaining = self.config.t_min_run_s - (sim_time - self._run_start_s)
            return (
                f"r5_min_run_not_elapsed:"
                f"elapsed={sim_time - self._run_start_s:.0f}s"
                f"<required={self.config.t_min_run_s:.0f}s"
                f"(remaining={remaining:.0f}s)"
            )
        self.state = TurbineState.UNLOADING
        self._levelled_off_since_s = math.nan   # Phase E: reset dwell clock on entry
        return None

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        """Tick this unit's internal state forward by one interval.

        Phase C state routing:
          STARTING     → tick countdown; on expiry → SYNCHRONISED.
          SYNCHRONISED → no-op; loading layer drives output via set_output().
          UNLOADING    → no-op; loading layer drives output down via set_output().
          all others   → no-op.

        The RAMPING branch (legacy ramp-to-target) is deleted in Phase C.
        Output for on-bus units (SYNCHRONISED and UNLOADING) is written
        exclusively by the loading layer via set_output().
        """
        if self.state == TurbineState.STARTING:
            # Tick the STARTING countdown timer.
            self._time_to_online_s = max(0.0, self._time_to_online_s - dt_seconds)
            if self._time_to_online_s <= 0.0:
                # Timer expired — unit is now synchronised to the bus.
                self._time_to_online_s = 0.0
                self.state = TurbineState.SYNCHRONISED
                self._run_start_s = sim_time   # record for R5 enforcement
        # SYNCHRONISED / UNLOADING: loading layer writes output via set_output().
        # OFFLINE / OUT_OF_SERVICE: no output; no transition needed.

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
    # _prev_output_mw: lag filter state — last-tick actual output.
    # Tracks the first-order response toward the current setpoint using the
    # inverter control-loop time constant bess_response_tau_s (Phase 13.3).
    _prev_output_mw: float = 0.0

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
        discharge_target_mw = min(allocated_mw, max_by_power, max_by_energy)

        # Phase 13.3 — first-order inverter response lag.
        # Discrete: actual = prev + alpha × (target − prev), alpha = 1 − exp(−dt/τ).
        # At τ=0.05 s (grid-forming inverter) and dt=0.1 s: alpha≈0.865 (fast).
        # At τ=0.05 s and dt=5 s (live dispatch tick):     alpha≈1.000 (instant).
        # Clamp actual output to [0, discharge_target_mw] so the lag never
        # over-shoots (inverter cannot deliver more than the physics allows).
        tau = self.config.bess_response_tau_s
        if tau > 0.0 and dt_seconds > 0.0:
            alpha = 1.0 - math.exp(-dt_seconds / tau)
            discharge_mw = self._prev_output_mw + alpha * (discharge_target_mw - self._prev_output_mw)
            discharge_mw = max(0.0, min(discharge_mw, discharge_target_mw))
        else:
            discharge_mw = discharge_target_mw

        self.soc_mwh = max(0.0, self.soc_mwh - discharge_mw * (dt_seconds / 3600.0))
        self._prev_output_mw = discharge_mw
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
    _override_active: bool = False  # True once RunManager has called override_output_mw()

    @property
    def asset_id(self) -> str:
        return self.config.asset_id

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        if self._override_active:
            # RunManager._drive() called override_output_mw() before ctx.step(),
            # so _current_output_mw already holds the three-tier bank-aggregated
            # value.  Do not overwrite it with rated_mw * fraction (AT-9/AT-10).
            return
        # Fallback: used by test paths that call evaluate_tick() directly without
        # going through RunManager._drive().  In a live run this branch never
        # executes because _override_active is set pre-step in A0.
        fraction = self.irradiance_profile.fraction_at(sim_time)
        self._current_output_mw = self.config.rated_mw * fraction

    def override_output_mw(self, mw: float) -> None:
        """Inject the three-tier bank-aggregated MW from RunManager (pre-step).

        Sets _override_active so advance() skips the rated_mw * fraction
        shortcut.  Never call from inside core/ — only RunManager._drive()
        (section A0) may call this to preserve plane-separation.
        """
        self._override_active = True
        self._current_output_mw = max(0.0, float(mw))

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
