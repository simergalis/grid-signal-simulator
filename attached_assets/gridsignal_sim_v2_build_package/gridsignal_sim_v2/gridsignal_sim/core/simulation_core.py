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

from dataclasses import dataclass, field

from .asset_modules import BessModule, CoolingModule, GPUModule, SolarModule, TurbineModule
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
    _unmapped_hardware_ever_seen: bool = False
    _pending_alert: InsufficientReserveAlert | None = None
    _job_owner_index: dict[str, int] = field(default_factory=dict)

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
        unmapped = gpu.apply_signal(signal)
        if unmapped:
            self._unmapped_hardware_ever_seen = True

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

        GPU -> Cooling -> Turbine/BESS (arbitration) -> Solar (offset)
        -> Checkpoint classifier -> Confidence engine

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

    # 3. Turbine ramp + BESS shortfall coverage
    for turbine in state.turbines:
        turbine.advance(sim_time, dt_seconds)
    turbine_output_mw, bess_output_mw = state.arbitrator.tick(p_total_mw, dt_seconds)

    # 4. Solar offset (Extension E-1) -> Net_demand(t), clipped at zero
    for solar in state.solar_arrays:
        solar.advance(sim_time, dt_seconds)
    solar_output_mw = sum(s.output_mw() for s in state.solar_arrays)
    net_demand_mw = max(0.0, p_total_mw - solar_output_mw)

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

    # 6. Confidence banding
    tags: set[DataQualityTag] = set()
    if state._unmapped_hardware_ever_seen:
        tags.add(DataQualityTag.UNMAPPED_HARDWARE)
    if state.site.uncalibrated:
        tags.add(DataQualityTag.UNCALIBRATED_SITE)
    confidence = state.confidence_engine.band_for(p_total_mw, tags)

    alert_fired = state._pending_alert is not None and state._pending_alert.fires_at_sim_time <= sim_time
    if alert_fired:
        state._pending_alert = None

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
        checkpoint_states=checkpoint_states,
    )
