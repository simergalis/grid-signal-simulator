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
from dataclasses import dataclass, field

from .asset_modules import BessModule, CoolingModule, GPUModule, SolarModule, TurbineModule

_log = logging.getLogger(__name__)
from .dispatch import CheckpointClassifier, ConfidenceEngine, DispatchArbitrator, InsufficientReserveAlert
from .models import DataQualityTag, SiteConfig, TickResult, WorkloadEventType, WorkloadSignal


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
        self.arbitrator = DispatchArbitrator(self.turbines, self.bess_units)

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
        """
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
            delta_p_mw = sum(g.output_mw() for g in self.gpu_modules)
            self._pending_alert = self.arbitrator.stage_for_predicted_step(
                delta_p_mw=delta_p_mw,
                dt_lead_seconds=dt_lead_seconds,
                sim_time=signal.timestamp,
            )

        if signal.event_type == WorkloadEventType.CHECKPOINT_START:
            self.classifier.apply_explicit_event(signal.job_id, is_checkpoint_start=True, sim_time=signal.timestamp)
        elif signal.event_type == WorkloadEventType.CHECKPOINT_END:
            self.classifier.apply_explicit_event(signal.job_id, is_checkpoint_start=False, sim_time=signal.timestamp)


def evaluate_tick(state: SimulationState, sim_time: float, dt_seconds: float) -> TickResult:
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
    """
    # 1. Compute term
    p_compute_mw = sum(g.output_mw() for g in state.gpu_modules)
    state.cooling.record_compute_sample(sim_time, p_compute_mw)

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
    p_dispatch_required_mw = max(0.0, p_total_mw - p_renewable_mw)
    net_demand_mw = p_dispatch_required_mw

    # 4. Turbine ramp + BESS shortfall coverage, sized against P_dispatch_required
    for turbine in state.turbines:
        turbine.advance(sim_time, dt_seconds)
    turbine_output_mw, bess_output_mw = state.arbitrator.tick(p_dispatch_required_mw, dt_seconds)

    # 5. Checkpoint classification, per active training job
    checkpoint_states: dict[str, str] = {}
    for gpu in state.gpu_modules:
        for job_id in gpu.active_training_jobs():
            job_draw_mw = p_compute_mw  # simplified: per-job draw attribution is a
            # documented refinement -- this skeleton classifies against the
            # module's aggregate draw, which is correct for the single-job-
            # per-module case exercised by the starter scenarios (functional
            # spec Section 6.4) and should be extended for multi-job modules.
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
        sim_time_seconds=sim_time,
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
    )
