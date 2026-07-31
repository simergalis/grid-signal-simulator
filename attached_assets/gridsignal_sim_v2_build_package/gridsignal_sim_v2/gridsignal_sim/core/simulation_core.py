"""
evaluate_tick(): the single orchestration function for one simulation
tick, called by RunContext (runtime/run_manager.py) once per tick.

Design Spec Section 5: "evaluate_tick(ctx) is the single orchestration
function that calls each module in the fixed order above ... this
ordering is itself part of what 'deterministic' means for this system."

This function is synchronous and has no I/O -- see Design Spec Section
4.3 for the timing analysis showing this is safely inside budget
without any parallelism.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .asset_modules import BessModule, CoolingModule, GPUModule, SolarModule, TurbineModule

_log = logging.getLogger(__name__)
from .dispatch import CheckpointClassifier, ConfidenceEngine, DispatchArbitrator, InsufficientReserveAlert
from .models import DataQualityTag, GENERIC_FALLBACK_PROFILE, SiteConfig, TickResult, WorkloadEventType, WorkloadSignal
from ._plane_guard import _EVALUATE_TICK_PERMITTED
from .sim_clock import SimClock


@dataclass
class SimulationState:
    """The full set of asset modules + engines for one run. This is the
    part of RunContext (runtime/run_manager.py) that evaluate_tick()
    actually touches -- kept separate from run-management concerns
    (playback speed, WebSocket subscribers, persistence) so this module
    has zero knowledge of asyncio."""

    run_id: str
    site: SiteConfig
    gpu_modules: list[GPUModule]
    turbines: list[TurbineModule]
    bess_units: list[BessModule]
    solar_arrays: list[SolarModule]
    cooling: CoolingModule
    classifier: CheckpointClassifier = field(default_factory=CheckpointClassifier)
    confidence_engine: ConfidenceEngine = field(default_factory=ConfidenceEngine)
    arbitrator: DispatchArbitrator = field(init=False)
    tick_index: int = 0
    # _unmapped_hardware_ever_seen removed (Step 2 per-segment tagging fix):
    # that flag was sticky — once set it tagged every subsequent tick even
    # after the unmapped job ended.  §5.1 and §12 require tagging the
    # affected segment.  evaluate_tick() now checks per-tick via
    # GPUModule.has_active_unmapped_jobs().
    _pending_alert: InsufficientReserveAlert | None = None
    _job_owner_index: dict[str, int] = field(default_factory=dict)
    # D7 fix: §5.1 onboarding alert deduplication.
    # _unmapped_profile_alerted: profile_ids for which the one-time alert has
    #   already been queued this run.  site_id is implicit (one SimulationState
    #   = one site), so this set deduplicates on (site_id, hardware_profile_id).
    # _pending_unrecognised_alerts: profile_ids whose first-seen alert will fire
    #   on the next TickResult.  Set by apply_workload_signal(); drained and
    #   cleared by evaluate_tick() before returning TickResult.
    _unmapped_profile_alerted: set[str] = field(default_factory=set)
    _pending_unrecognised_alerts: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # Step 3 Item 4: arbitrator now holds a reference to site so it can
        # read island_mode each tick (mode changes with operating state —
        # Step 11 will flip it; holding the reference keeps the tick path O(1)).
        self.arbitrator = DispatchArbitrator(self.turbines, self.bess_units, self.site)

    def _owning_gpu_module(self, signal: WorkloadSignal) -> GPUModule:
        """A WorkloadSignal targets exactly one GPU module -- the real
        system's Section 4.1 sum is per-job-instance, not "broadcast
        this event to every module." A job's owning module is assigned
        once, on its first (STARTING) event, and reused for every
        subsequent event on that job_id (scale/checkpoint/end), so a
        job's node-count contribution lives in exactly one place.

        Assignment is a simple round-robin over the configured modules
        rather than anything hardware-aware -- a real Connector Fabric
        integration would report which physical module/rack a job
        landed on; this skeleton doesn't model rack placement.
        """
        if signal.job_id not in self._job_owner_index:
            self._job_owner_index[signal.job_id] = len(self._job_owner_index) % len(self.gpu_modules)
        return self.gpu_modules[self._job_owner_index[signal.job_id]]

    def apply_workload_signal(self, signal: WorkloadSignal, dt_lead_seconds: float) -> None:
        """Called by the Run Manager when a scripted WorkloadSignal's
        timestamp is reached. Fixed order per module design (Section
        5 of the design spec): GPU modules first (they own node
        counts), then the arbitrator is staged if this is a job start.

        Step 8 — SOLAR_STEP: §7.1.1 renewable curtailment carries no advance
        signal.  The staging path is identical to a compute STARTING event, but
        dt_lead is always 0.  This is the TC-33 invariant made executable:
        stage_for_predicted_step sees the same delta_p_mw regardless of whether
        the step came from a compute ramp or a renewable drop.  Only dt_lead
        differs, which correctly makes the renewable gap (and therefore the BESS
        bridging requirement) larger.  Early-return so the GPU plane is untouched.
        """
        if signal.event_type == WorkloadEventType.SOLAR_STEP:
            self._pending_alert = self.arbitrator.stage_for_predicted_step(
                delta_p_mw=signal.renewable_shortfall_mw,
                dt_lead_seconds=0.0,   # §7.1.1: no advance signal for renewables
                sim_time=signal.timestamp,
            )
            return

        gpu = self._owning_gpu_module(signal)
        new_unmapped = gpu.apply_signal(signal)
        # Unmapped-hardware confidence tagging is per-tick via evaluate_tick step 6.
        # D7 fix: §5.1 onboarding alert — fire once per unique unmapped
        # hardware_profile_id per site.  Deduplicated by _unmapped_profile_alerted;
        # queued in _pending_unrecognised_alerts so it surfaces on the next
        # TickResult (reaching operator subscribers, not only the log).
        if new_unmapped and signal.hardware_profile_id not in self._unmapped_profile_alerted:
            self._unmapped_profile_alerted.add(signal.hardware_profile_id)
            self._pending_unrecognised_alerts.add(signal.hardware_profile_id)
            _log.warning(
                "§5.1 onboarding alert (site=%r): hardware profile %r is not in "
                "the library.  Map it in the hardware profile library to enable "
                "per-profile draw attribution and confidence calibration.  "
                "(First seen on job_id=%r)",
                self.site.site_id,
                signal.hardware_profile_id,
                signal.job_id,
            )

        if signal.event_type == WorkloadEventType.STARTING:
            # Step 3 Item 3: register t₀ₖ with the cooling module directly from
            # the STARTING event timestamp.  The engine must never infer onset
            # from aggregate draw shape (§8).
            self.cooling.register_job_start(signal.job_id, signal.timestamp)
            # D8 fix: delta_p_mw must be the increment this job adds to
            # P_dispatch_required, net of renewable output at staging time.
            # The old code had two errors on the same line:
            #   (1) sum(g.output_mw()) = total site compute, not this job's increment.
            #   (2) no renewable offset — staging sized against P_total, not P_dispatch_required.
            #
            # Step 3 Item 2 — TARGET draw for staging.
            # After the Δt_lead ramp fix, apply_signal(STARTING) sets ramp_progress=0,
            # so output_mw() returns ≈0 for the new job.  Computing delta_p_mw from
            # output_mw() would give delta_p ≈ 0 — the turbine stages for nothing.
            # Staging must use TARGET draw (full TDP), because that is the load the
            # turbine needs to be ready for when Δt_lead expires.
            #
            # target_output_mw() sums per_job_target_mw() for all active jobs,
            # ignoring ramp progress.  per_job_target_mw() is the complementary
            # accessor to per_job_compute_mw(): same formula, no ramp multiplier.
            _job_target_mw = gpu.per_job_target_mw(signal.job_id)
            _p_target_after = sum(g.target_output_mw() for g in self.gpu_modules)
            _p_target_before = _p_target_after - _job_target_mw
            # Current renewable output at the moment staging occurs.  When
            # solar has not yet been advanced (first tick, t=0) this is 0,
            # and delta_p_mw collapses to _job_target_mw — correct behaviour,
            # since no renewable offset is available yet.
            _p_renewable_mw = sum(s.output_mw() for s in self.solar_arrays)
            # Delta in P_dispatch_required.  Strictly <= _job_target_mw:
            # renewables already covering part of the pre-job load absorb some
            # of the step, reducing what dispatchable sources must pre-stage for.
            delta_p_mw = (
                max(0.0, _p_target_after - _p_renewable_mw)
                - max(0.0, _p_target_before - _p_renewable_mw)
            )
            self._pending_alert = self.arbitrator.stage_for_predicted_step(
                delta_p_mw=delta_p_mw,
                dt_lead_seconds=dt_lead_seconds,
                sim_time=signal.timestamp,
            )
        elif signal.event_type in (WorkloadEventType.JOB_END, WorkloadEventType.CANCELLED):
            # Step 3 Item 3: mark the envelope ended so the retention window
            # starts.  Heat is already in the room; the buffer drains over
            # dt_thermal + 5·τ — it must not drop in one tick.
            self.cooling.register_job_end(signal.job_id, signal.timestamp)

        if signal.event_type == WorkloadEventType.CHECKPOINT_START:
            self.classifier.apply_explicit_event(signal.job_id, is_checkpoint_start=True, sim_time=signal.timestamp)
        elif signal.event_type == WorkloadEventType.CHECKPOINT_END:
            self.classifier.apply_explicit_event(signal.job_id, is_checkpoint_start=False, sim_time=signal.timestamp)


def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
    """The fixed-order tick evaluation (Design Spec Section 5 / 10.1):

        GPU -> Cooling -> Solar (renewable offset) -> Turbine/BESS (arbitration)
        -> Checkpoint classifier -> Confidence engine

    Solar moves before arbitration (Step 3 Item 0): P_dispatch_required(t) =
    P_total(t) − P_renewable(t) per §7.1.1.  The arbitrator sizes against
    P_dispatch_required, not P_total.  Renewables have no lead-time signal and
    are structurally absent from the ramp-capability calculation inside
    DispatchArbitrator (§7.1.1 asymmetry 1 & 2).

    Deterministic: same inputs, same order, every time -- no dict/set
    iteration order dependency (all module lists are plain lists).

    Step 4 — runtime purity guard: the ContextVar sentinel
    _EVALUATE_TICK_PERMITTED must be True when this function is entered.
    The sentinel is SET BY THE CALLER (runtime/run_manager.py:RunContext.step),
    not here — setting it here would self-sign and defeat the guard.  Direct
    callers (scripts, tests) must use core._plane_guard or the test helper
    _plane_guard_active() in tests/test_plane_separation.py.
    """
    # Step 4: runtime purity guard — reject calls that bypass the runtime harness.
    if not _EVALUATE_TICK_PERMITTED.get():
        raise RuntimeError(
            "evaluate_tick() called without the runtime guard active.  "
            "The ContextVar core._plane_guard._EVALUATE_TICK_PERMITTED must be "
            "True before entering evaluate_tick().  In production this is set by "
            "RunContext.step() in runtime/run_manager.py.  In tests, use the "
            "_plane_guard_active() context manager from "
            "tests/test_plane_separation.py."
        )

    # Step 5: unpack SimClock into local names so the function body is unchanged.
    # sim_time and dt_seconds are simulated seconds (Rule 1: all spec intervals
    # are measured in simulated time).  wall_stamp_utc is carried through to
    # TickResult so the persistence layer can record both clocks per tick.
    sim_time = clock.sim_time
    dt_seconds = clock.dt_seconds

    # 1. Compute term — advance GPU ramps first (Step 3 Item 2: Δt_lead ramp).
    # GPU advance() is no longer a no-op: it advances the per-job ramp_progress
    # by dt_seconds/ramp_seconds so that P_compute grows realistically from near-0
    # at STARTING toward full TDP over the Δt_lead window, rather than stepping
    # to full TDP in a single tick.
    for gpu in state.gpu_modules:
        gpu.advance(sim_time, dt_seconds)
    # Step 3 Item 3: per-job cooling superposition.
    # Build the per-job draw dict from all GPU modules (each job lives in exactly
    # one module via _job_owner_index, so no double-counting).  Pass this to
    # CoolingModule's simulation path instead of the old aggregate scalar.
    # The engine reads per_job_compute_mw() directly — it does NOT infer job
    # boundaries from aggregate draw shape (§8 / Build Plan v2.2 Step 3 Item 3).
    _per_job_draws: dict[str, float] = {}
    for _g in state.gpu_modules:
        for _job_id in _g._node_counts:
            _per_job_draws[_job_id] = _g.per_job_compute_mw(_job_id)
    p_compute_mw = sum(_per_job_draws.values())
    state.cooling.record_job_compute(sim_time, _per_job_draws)

    # 2. Cooling term (lagged)
    state.cooling.advance(sim_time, dt_seconds)
    p_cooling_mw = state.cooling.output_mw()

    p_total_mw = p_compute_mw + p_cooling_mw

    # 3. Solar offset (Extension E-1 / §7.1.1) — evaluated BEFORE arbitration
    #    so the fleet sizes against P_dispatch_required, not P_total.
    #    P_renewable can vanish without notice (Δt_lead = 0 for inverter trips);
    #    the arbitrator must never count it as ramp capability.
    for solar in state.solar_arrays:
        solar.advance(sim_time, dt_seconds)
    p_renewable_mw = sum(s.output_mw() for s in state.solar_arrays)
    # P_dispatch_required(t) = P_total(t) − P_renewable(t), clipped at zero.
    # net_demand_mw is a synonym kept for TickResult reporting compatibility.
    #
    # EXPORT SCOPE NOTE: the unclamped value (p_total_mw - p_renewable_mw) can
    # be negative when renewable output exceeds load — that is the grid-export
    # condition and is relevant for the §7.1 grid-tie boundary.  It is NOT
    # stored here; only the clamped value is used.  Grid-export modelling is
    # out of scope for this simulator release.
    p_dispatch_required_mw = max(0.0, p_total_mw - p_renewable_mw)
    net_demand_mw = p_dispatch_required_mw

    # 4. Turbine ramp + BESS shortfall coverage, sized against P_dispatch_required
    for turbine in state.turbines:
        turbine.advance(sim_time, dt_seconds)
    turbine_output_mw, bess_output_mw = state.arbitrator.tick(p_dispatch_required_mw, dt_seconds)

    # 4b. dt_lead_next_s: minimum remaining ramp time across all in-flight GPU jobs.
    # C2 correction: min(), not sum().  Two jobs with 10 s and 30 s remaining →
    # the next GPU-full-TDP event fires in 10 s, not 40 s.  sum() does not
    # correspond to any physical event.  Named dt_lead_next_s (not dt_lead_s) so
    # the semantics are encoded in the field, not hidden in a comment.
    # math.inf is returned by min_ramp_remaining_seconds when no job is ramping;
    # convert to 0.0 for the TickResult ("no active ramp").
    _dt_lead_raw = min(
        (g.min_ramp_remaining_seconds() for g in state.gpu_modules),
        default=math.inf,
    )
    dt_lead_next_s = _dt_lead_raw if _dt_lead_raw < math.inf else 0.0

    # 4c. bess_bridging_seconds + bridging_basis: fleet bridging duration at the
    # BINDING demand — max(net_demand_mw, pending predicted peak shortfall).
    #
    # F2 fix: when a step has been staged and its predicted peak shortfall exceeds
    # current net demand (typical at t=0: GPU hasn't ramped yet but the alert is
    # live), the panel must answer the same question as the alert banner ("can the
    # BESS sustain the predicted peak?"), not the easier question ("can it sustain
    # the near-zero current demand?").  Using net_demand_mw at t=0 produces
    # "full reserve" alongside "Insufficient reserve" — contradictory to the
    # operator.  The binding constraint is whatever is larger.
    #
    # bridging_basis names which denominator was used so AssetReservePanel can
    # label it and the operator knows the panel is answering the same question
    # the banner asked.
    #
    # C1 correction still applies: use BessModule.max_sustainable_seconds()
    # (the same function stage_for_predicted_step uses) rather than a MW/MW × 3600
    # ratio.  Fleet aggregation: D13 min() across proportional shares, not sum().
    # math.inf when binding demand ≤ 0 (no_load); serializer caps to 86 400 s.
    _pending_peak_mw = (
        state._pending_alert.shortfall_mw
        if state._pending_alert is not None
        else 0.0
    )
    _binding_demand_mw = max(net_demand_mw, _pending_peak_mw)

    if _binding_demand_mw <= 0.0:
        bridging_basis = "no_load"
        bess_bridging_seconds = math.inf
    else:
        bridging_basis = (
            "predicted_peak" if _pending_peak_mw > net_demand_mw else "current_demand"
        )
        if state.bess_units:
            _bbs_island_mode = state.site.island_mode
            _bbs_ceilings = [b.bridging_available_mw(_bbs_island_mode) for b in state.bess_units]
            # D14: if binding demand exceeds total fleet ceiling the fleet is
            # power-limited — it cannot sustain the demand regardless of stored
            # energy.  Report 0.0 immediately; do not compute an endurance for
            # a sub-ceiling allocation (the allocation is capped but that does
            # not mean the fleet CAN cover the demand).
            if _binding_demand_mw > sum(_bbs_ceilings):
                bess_bridging_seconds = 0.0
            else:
                _bbs_allocs = state.arbitrator._capped_equal_share_allocations(
                    _binding_demand_mw, _bbs_ceilings
                )
                bess_bridging_seconds = min(
                    b.max_sustainable_seconds(alloc, _bbs_island_mode)
                    for b, alloc in zip(state.bess_units, _bbs_allocs)
                )
        else:
            bess_bridging_seconds = 0.0

    # 5. Checkpoint classification, per active training job.
    # Step 3 Item 1: use gpu.per_job_compute_mw(job_id) — the draw for THIS job
    # on THIS module — not the site-wide p_compute_mw sum.  A 20% checkpoint dip
    # in a 1 MW job is a 0.4% dip in a 50 MW site and never crosses §6.2's 15%
    # threshold when the classifier sees the aggregate.
    # per_job_compute_mw() is the shared substrate: Items 2 and 3 will consume
    # the same accessor rather than each deriving their own job-level draw.
    checkpoint_states: dict[str, str] = {}
    for gpu in state.gpu_modules:
        for job_id in gpu.active_training_jobs():
            job_draw_mw = gpu.per_job_compute_mw(job_id)
            new_state = state.classifier.record_and_classify(job_id, sim_time, job_draw_mw)
            checkpoint_states[job_id] = new_state.value

    # 6. Confidence banding — tags belong to this segment, not the run.
    # Per-segment tagging fix (Step 2): check live state of each module
    # this tick instead of a sticky run-global flag.  An unmapped job that
    # ended two hours ago must not tag the current segment (§5.1, §12).
    tags: set[DataQualityTag] = set()
    if any(g.has_active_unmapped_jobs() for g in state.gpu_modules):
        tags.add(DataQualityTag.UNMAPPED_HARDWARE)
    if state.site.uncalibrated:
        tags.add(DataQualityTag.UNCALIBRATED_SITE)
    confidence = state.confidence_engine.band_for(p_total_mw, tags)

    alert_fired = state._pending_alert is not None and state._pending_alert.fires_at_sim_time <= sim_time
    if alert_fired:
        state._pending_alert = None

    # D7 fix: §5.1 onboarding alerts — drain the pending set and clear it so
    # the frozenset is non-empty on at most one tick per unique profile_id.
    unrecognised_alerts = frozenset(state._pending_unrecognised_alerts)
    state._pending_unrecognised_alerts = set()

    state.tick_index += 1
    return TickResult(
        run_id=state.run_id,
        tick_index=state.tick_index,
        # F5: TickResult carries the INTERVAL-END timestamp — the instant the
        # state was measured (after asset advance() calls).  SimClock.sim_time
        # is the interval START; all internal elapsed calculations above use
        # clock.sim_time directly.  Only the persisted / wire field changes.
        sim_time_seconds=sim_time + clock.dt_seconds,
        p_compute_mw=p_compute_mw,
        p_cooling_mw=p_cooling_mw,
        p_total_mw=p_total_mw,
        net_demand_mw=net_demand_mw,
        turbine_output_mw=turbine_output_mw,
        bess_output_mw=bess_output_mw,
        bess_soc_fraction=(state.bess_units[0].soc_fraction if state.bess_units else 1.0),
        confidence=confidence,
        insufficient_reserve_alert=alert_fired,
        unrecognised_profile_alerts=unrecognised_alerts,
        checkpoint_states=checkpoint_states,
        wall_stamp_utc=clock.wall_stamp_utc,
        p_renewable_mw=p_renewable_mw,
        bess_bridging_seconds=bess_bridging_seconds,
        dt_lead_next_s=dt_lead_next_s,
        bridging_basis=bridging_basis,
    )
