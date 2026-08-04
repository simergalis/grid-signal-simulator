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
import dataclasses
from dataclasses import dataclass, field
from typing import Optional

from .asset_modules import BessModule, CoolingModule, GPUModule, SolarModule, TurbineModule, TurbineState
from .loading import apply_loading, ramp_capability, LEAD_WINDOW_S
from .contingency import BessSnapshot, PlantState, TurbineSnapshot, evaluate_contingency
from .kube_demand import KubeDemandAgent, KubeGridState

_log = logging.getLogger(__name__)
from .dispatch import (
    CandidateResponse, CheckpointClassifier, ConfidenceEngine, CurtailmentLadder,
    CurtailmentProposal, CurtailmentTier, DispatchArbitrator, InsufficientReserveAlert,
    LadderPosition, PreStagingEngine, select_candidates,
)
from .scada_layer import CommandType, SimulatedPMS, SimulatedScadaLayer
from .models import DataQualityTag, GENERIC_FALLBACK_PROFILE, IslandMode, KubeMetrics, SiteConfig, TickResult, WorkloadEventType, WorkloadSignal
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
    # Kubernetes demand agent — present when kube_config is set in ScenarioSpec.
    # None = standard scripted workload path (all existing tests unaffected).
    kube_agent: KubeDemandAgent | None = field(default=None)
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
    # Turbine ramp credit and peak shortfall from the most recent staging event.
    # Carried while a STARTING event is in-flight (dt_lead_next_s > 0) so the
    # AssetReservePanel can explain why the reserve check passed or fired.
    # Both reset to 0.0 when no staging is pending.
    _pending_ramp_credit_mw:   float = 0.0
    _pending_peak_shortfall_mw: float = 0.0
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
    # Step 10: §23.2 curtailment ladder (stateful; created in __post_init__).
    curtailment_ladder: CurtailmentLadder = field(init=False)
    # Step 10: §8.1 pre-staging engine (None when site has no shiftable load).
    pre_staging_engine: PreStagingEngine | None = field(default=None, init=False)
    # Step 11: §4.6 SCADA layer (always created; protocol map can be empty).
    scada_layer: SimulatedScadaLayer = field(init=False)
    # Step 11: §28.4 PMS (None when site has no pms_config).
    pms: SimulatedPMS | None = field(default=None, init=False)
    # Grid state snapshot for the Kubernetes demand agent.
    # Carries the previous tick's grid metrics so the agent can read headroom
    # without accessing the current tick's in-progress values.
    _kube_grid_state: KubeGridState | None = field(default=None, init=False)

    # Phase 11.2 — workload signal staleness / absence tracking.
    # _last_workload_signal_sim_time: sim_time of the most recent WorkloadSignal
    #   (STARTING, RUNNING, SCALE, JOB_END, CANCELLED, CHECKPOINT_*).
    #   SOLAR_STEP and UNIT_TRIP are EXCLUDED — they are not workload signals.
    #   Default -1.0 (before any signal); compared against sim_time each tick.
    # _ever_received_workload_signal: True once the first qualifying signal
    #   arrives; used to distinguish "never received" (absent) from "received
    #   but gone stale" (stale).  Separate bool prevents -1.0 from being
    #   confused with a legitimate t=0 signal.
    _last_workload_signal_sim_time:  float = field(default=-1.0, init=False)
    _ever_received_workload_signal:  bool  = field(default=False, init=False)

    # Phase 11.3 — frequency state for the swing equation (islanded mode only).
    # Persisted on SimulationState so df/dt integration accumulates correctly
    # across ticks.  Starts at the nominal frequency; deviates when
    # balance_residual_mw is non-zero in islanded mode.
    # In grid-connected mode this field is reset to frequency_nominal_hz each
    # tick (the grid holds the frequency reference and acts as infinite slack).
    _frequency_hz: float = field(default=50.0, init=False)

    # Phase 11.3/11.5 — running forecast MAE accumulators.
    # Used by Phase 11.5 Forecast Quality panel to report empirical accuracy.
    # _forecast_error_sum_mw: running sum of |forecast_mw - p_actual_mw| over
    #   ticks where p_actual > 1e-4 (meaningful load present).
    # _forecast_ticks: number of ticks included in the MAE sum.
    # Both are intentionally not reset mid-run (full-run statistic).
    _forecast_error_sum_mw: float = field(default=0.0, init=False)
    _forecast_ticks:        int   = field(default=0,   init=False)

    def __post_init__(self) -> None:
        # Step 3 Item 4: arbitrator now holds a reference to site so it can
        # read island_mode each tick (mode changes with operating state —
        # Step 11 will flip it; holding the reference keeps the tick path O(1)).
        self.arbitrator = DispatchArbitrator(self.turbines, self.bess_units, self.site)
        # Step 10: curtailment ladder and pre-staging engine.
        self.curtailment_ladder = CurtailmentLadder()
        if self.site.pre_staging_config is not None:
            self.pre_staging_engine = PreStagingEngine(self.site.pre_staging_config)
        # Step 11: SCADA layer (seeded, deterministic) and optional PMS.
        self.scada_layer = SimulatedScadaLayer(seed=42)
        if self.site.pms_config is not None:
            self.pms = SimulatedPMS(self.site.pms_config)

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
            (
                self._pending_alert,
                self._pending_ramp_credit_mw,
                self._pending_peak_shortfall_mw,
            ) = self.arbitrator.stage_for_predicted_step(
                delta_p_mw=signal.renewable_shortfall_mw,
                dt_lead_seconds=0.0,   # §7.1.1: no advance signal for renewables
                sim_time=signal.timestamp,
            )
            return

        if signal.event_type == WorkloadEventType.UNIT_TRIP:
            # TC-84: force the named generating unit offline immediately.
            # asset_id is carried in signal.job_id (non-job event, no GPU state
            # is touched).  Unknown asset_ids are logged and silently ignored so
            # a misconfigured scenario does not crash a live run.
            _tripped_asset_id = signal.job_id
            _matched = False
            for _t in self.turbines:
                if _t.config.asset_id == _tripped_asset_id:
                    _t.state = TurbineState.OFFLINE
                    _t._current_output_mw = 0.0
                    _t._target_mw = 0.0
                    _matched = True
                    _log.info(
                        "UNIT_TRIP: turbine %r forced OFFLINE at sim_time=%.1f (TC-84).",
                        _tripped_asset_id,
                        signal.timestamp,
                    )
                    break
            if not _matched:
                _log.warning(
                    "UNIT_TRIP: asset_id %r not found in turbine fleet "
                    "(known: %s); event ignored.",
                    _tripped_asset_id,
                    [_t.config.asset_id for _t in self.turbines],
                )
            return

        gpu = self._owning_gpu_module(signal)
        # Capture cohort keys before apply_signal() clears _job_cohorts on JOB_END.
        _cohort_keys_before_end: list[str] = []
        if signal.event_type in (WorkloadEventType.JOB_END, WorkloadEventType.CANCELLED):
            _cohort_keys_before_end = list(gpu._job_cohorts.get(signal.job_id, []))
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
            (
                self._pending_alert,
                self._pending_ramp_credit_mw,
                self._pending_peak_shortfall_mw,
            ) = self.arbitrator.stage_for_predicted_step(
                delta_p_mw=delta_p_mw,
                dt_lead_seconds=dt_lead_seconds,
                sim_time=signal.timestamp,
            )
        elif signal.event_type == WorkloadEventType.SCALE:
            # Scale-UP: the delta cohort is cold — register its own cooling
            # envelope seeded at the SCALE event timestamp so its cooling rises
            # from the SCALE moment, not from job start (§8 per-job superposition).
            # gpu._last_scale_cohort_key is None for scale-downs (no new envelope needed).
            _cohort_key = gpu._last_scale_cohort_key
            if _cohort_key is not None:
                self.cooling.register_job_start(_cohort_key, signal.timestamp)
            # Scale-DOWN: end the CoolingModule envelope for each cohort that was
            # fully removed (node count reached zero).  Without this, the envelope
            # has no end_t and retains its last historical compute power level
            # indefinitely — no new samples are written once the cohort is gone, so
            # the lagged cursor stays stuck at the last pre-scale value forever.
            # Partially-reduced cohorts (node count > 0) self-correct as lower-power
            # samples fill in via record_job_compute(); no intervention needed there.
            for _removed_key in gpu._last_scale_removed_cohort_keys:
                self.cooling.register_job_end(_removed_key, signal.timestamp)
        elif signal.event_type in (WorkloadEventType.JOB_END, WorkloadEventType.CANCELLED):
            # Step 3 Item 3: mark the envelope ended so the retention window
            # starts.  Heat is already in the room; the buffer drains over
            # dt_thermal + 5·τ — it must not drop in one tick.
            self.cooling.register_job_end(signal.job_id, signal.timestamp)
            # Also end cooling envelopes for any scale-up cohorts that were
            # spawned from this job (captured before apply_signal cleared them).
            for _ck in _cohort_keys_before_end:
                self.cooling.register_job_end(_ck, signal.timestamp)

        if signal.event_type == WorkloadEventType.CHECKPOINT_START:
            self.classifier.apply_explicit_event(signal.job_id, is_checkpoint_start=True, sim_time=signal.timestamp)
        elif signal.event_type == WorkloadEventType.CHECKPOINT_END:
            self.classifier.apply_explicit_event(signal.job_id, is_checkpoint_start=False, sim_time=signal.timestamp)

        # Phase 11.2 — workload signal staleness / absence tracking.
        # Record the timestamp of this qualifying signal.  SOLAR_STEP and
        # UNIT_TRIP are excluded (early-return above ensures we never reach here
        # for those event types).
        self._last_workload_signal_sim_time = signal.timestamp
        self._ever_received_workload_signal = True


def evaluate_tick(state: SimulationState, clock: SimClock) -> TickResult:
    """The fixed-order tick evaluation (Design Spec Section 5 / 10.1):

        GPU -> Cooling -> Solar (renewable offset)
        -> [Phase 0: pre-staging §8.1]          ← Step 10 insertion point
        -> Turbine/BESS (arbitration)
        -> Curtailment ladder (§23.2 observation)← Step 10 insertion point
        -> Checkpoint classifier -> Confidence engine

    Solar moves before arbitration (Step 3 Item 0): P_dispatch_required(t) =
    P_total(t) − P_renewable(t) per §7.1.1.  The arbitrator sizes against
    P_dispatch_required, not P_total.  Renewables have no lead-time signal and
    are structurally absent from the ramp-capability calculation inside
    DispatchArbitrator (§7.1.1 asymmetry 1 & 2).

    Step 10 — Phase 0 insertion (§8.1 pre-staging):
        Inserted AFTER P_dispatch_required is computed (step 3) and BEFORE
        arbitrator.tick() (step 4).  Pre-staging reduces the SIZE of the gap
        rather than closing an existing one, so it sits ahead of the ladder —
        it is a gap-reduction phase, not a gap-closure rung.  Existing stages
        are preserved in their original order; this is a new stage at a defined
        point, not a reordering of existing stages.

    Step 10 — Curtailment ladder observation:
        Inserted after arbitrator.tick() (step 4) has done its best.  The
        remaining gap (if any) is passed to CurtailmentLadder.tick(), which
        applies the 120 s dwell, TC-43 low-confidence interlock, dead-man
        expiry, and mandatory tier ordering before returning proposals.

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

    # 0. Kubernetes demand agent — must run BEFORE gpu.advance() so demand
    #    changes driven by the scheduler take effect in the current tick's power
    #    calculation.  Uses _kube_grid_state from the previous tick (None at t=0)
    #    so the agent reads last-known headroom rather than in-progress values.
    _kube_metrics: KubeMetrics | None = None
    if state.kube_agent is not None:
        _kube_signals, _kube_metrics = state.kube_agent.tick(
            sim_time, dt_seconds, state._kube_grid_state
        )
        for _ks in _kube_signals:
            # §9 / resolution-log item 5: dt_lead_seconds for a Kubernetes signal
            # equals GPUModule.ramp_seconds (default 45 s) — the physical window
            # from scheduler allocation to GPUs reaching full TDP.
            #
            # Previously this was hard-coded to 0.0, which told the arbitrator
            # the turbine had no ramp window, so already_ramped_mw = r_asset × 0
            # = 0 MW (no turbine credit) and the BESS bridging requirement was
            # sized against the full ΔP rather than the residual after turbine
            # ramping.  That caused systematic over-alerts on the Kubernetes path
            # and broke the v0.1 worked-example fixture.
            #
            # A zero-lead stressor scenario (Kubernetes with truly instantaneous
            # load) must be constructed as an explicit scripted WorkloadSignal
            # with dt_lead_seconds=0 — it is not the default.
            _kube_ramp_s = (
                state.gpu_modules[0].ramp_seconds
                if state.gpu_modules else 45.0
            )
            state.apply_workload_signal(_ks, dt_lead_seconds=_kube_ramp_s)

        # ── Propagate step_phase to GPUModules BEFORE advance() ──────────────
        # The within-step power profile lag (GPUModule.advance()) needs the
        # updated step_phase from the step scheduler.  Setting it here ensures
        # the lag state update in advance() uses the current tick's phase, not
        # the previous tick's.  This must happen between kube_agent.tick() and
        # gpu.advance().
        _fleet_phase = state.kube_agent.current_step_phase
        for _g in state.gpu_modules:
            _g.step_phase = _fleet_phase

    # 1. Compute term — advance GPU ramps first (Step 3 Item 2: Δt_lead ramp).
    # GPU advance() is no longer a no-op: it advances the per-job ramp_progress
    # by dt_seconds/ramp_seconds so that P_compute grows realistically from near-0
    # at STARTING toward full TDP over the Δt_lead window, rather than stepping
    # to full TDP in a single tick.
    for gpu in state.gpu_modules:
        gpu.advance(sim_time, dt_seconds)

    # Node-count ramp patch (§9 cosmetic fix, Task #39):
    # kube_agent.tick() computes node_count = max(min_nodes, admitted_nodes)
    # using the raw scheduler admission count — it fires before gpu.advance()
    # so it has no visibility into the per-job ramp_progress values.  After
    # gpu.advance() has updated ramp_progress we recompute node_count using
    # GPUModule.effective_node_count() which applies the same _ramp_multiplier
    # curve as the power path.  This makes the COMPUTE RACKS tile rise
    # gradually alongside P_compute instead of snapping to admitted_nodes the
    # moment a STARTING signal is received.
    #
    # admitted_nodes is intentionally left unchanged — it reflects the
    # scheduler's raw allocation and is used for capacity planning / eviction
    # decisions that must see the full committed count, not the ramped view.
    if _kube_metrics is not None and state.gpu_modules and state.kube_agent is not None:
        _effective_admitted = sum(g.effective_node_count() for g in state.gpu_modules)
        _effective_total = max(state.kube_agent.config.min_nodes, _effective_admitted)
        _kube_metrics = dataclasses.replace(
            _kube_metrics,
            node_count=_effective_total,
            utilization=_effective_total / state.kube_agent.config.max_nodes,
        )

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
    # Phase 13.4 B1: track load-model bias as a separately observable channel.
    # Does NOT flow into p_dispatch_required, BESS setpoint, or frequency_forcing.
    _model_error_mw = state.site.load_model_bias_mw

    # 3a. Phase 0 — GAP REDUCTION: §8.1 pre-staging (shiftable thermal load).
    #
    # INSERTION POINT (Step 10): placed here — after P_dispatch_required is
    # computed (step 3) and before turbine/BESS arbitration (step 4).
    # Pre-staging reduces the SIZE of the gap before the §26.4 ladder tries
    # to close it; it is not a rung in the ladder.  The BMS retains
    # unconditional override (TC-56).  Bounded by inlet temperature band (TC-55).
    #
    # net_demand_mw is kept as a synonym so downstream fields that reference
    # the pre-staging-adjusted demand are consistent.
    pre_staging_shift_mw = 0.0
    pre_staging_precool_mw = 0.0
    if state.pre_staging_engine is not None:
        _bms_override = (
            state.site.pre_staging_config.bms_override
            if state.site.pre_staging_config is not None
            else False
        )
        pre_staging_shift_mw, pre_staging_precool_mw = (
            state.pre_staging_engine.compute_tick(
                gap_mw=p_dispatch_required_mw,
                bms_override=_bms_override,
                sim_time=sim_time,
                dt_seconds=dt_seconds,
            )
        )
        # Discharge phase reduces the gap; charge phase draws extra load NOW.
        # The two are mutually exclusive each tick (compute_tick guarantee).
        p_dispatch_required_mw = (
            max(0.0, p_dispatch_required_mw - pre_staging_shift_mw)
            + pre_staging_precool_mw
        )
        net_demand_mw = p_dispatch_required_mw

    # 3b. Step 11 — §28 PMS tick (before arbitration).
    # fast_shed: TC-64 interlock gates the curtailment ladder; TC-66 records it.
    # transition_gap: TC-67 open-transition adds a temporary coverage discontinuity
    # to P_dispatch_required so dispatchable assets must bridge the gap.
    _pms_shed_active = False
    _transition_gap_mw = 0.0
    if state.pms is not None:
        _pms_fast_shed_mw, _transition_gap_mw = state.pms.tick(sim_time, dt_seconds)
        _pms_shed_active = state.pms.is_fast_shed_active
        if _transition_gap_mw > 0.0:
            # TC-67: open-transition coverage gap is a discontinuity to ride through.
            p_dispatch_required_mw = p_dispatch_required_mw + _transition_gap_mw
            net_demand_mw = p_dispatch_required_mw
            _log.info(
                "PMS open-transition gap at sim_time=%.1f — "
                "+%.2f MW to P_dispatch_required (TC-67).", sim_time, _transition_gap_mw,
            )

    # ── Phase 13.3: governor droop pre-correction ─────────────────────────────
    # S_base = total synchronous generator rating (MVA), used for both droop and
    # the swing equation.  Computed here so it is available to both blocks.
    _s_base_mw = max(1.0, sum(t.config.rated_mw for t in state.turbines))

    # _islanded: topology flag, used in droop, decomposition, and swing equation.
    _islanded = (state.site.island_mode == IslandMode.ISLANDED)

    # Governor droop adjusts the turbine dispatch setpoint proportionally to the
    # current frequency error, providing primary frequency response.  Active in
    # islanded mode only — in grid-tie the infinite bus holds frequency and the
    # forcing term is zero (D2).
    #
    # Formula: ΔP = −Δf / (droop × f_nominal) × P_rated
    #   Δf > 0 (f above nominal) → ΔP < 0 → reduce turbine command.
    #   Δf < 0 (f below nominal) → ΔP > 0 → increase turbine command.
    #
    # Deadband: no response within ±0.02 Hz of nominal to avoid hunting.
    # Ramp limits: TurbineModule.advance() naturally limits how far the turbine
    #   can actually move in one tick, so no explicit per-tick clamping here.
    # Lower bound: clamped to 0 — turbines cannot be commanded below zero output.
    _GOVERNOR_DEADBAND_HZ: float = 0.02
    _f_error_hz = state._frequency_hz - state.site.frequency_nominal_hz

    if (
        _islanded
        and abs(_f_error_hz) > _GOVERNOR_DEADBAND_HZ
        and state.site.governor_droop > 0.0
    ):
        _droop_correction_mw = (
            -_f_error_hz
            / (state.site.governor_droop * state.site.frequency_nominal_hz)
            * _s_base_mw
        )
    else:
        # governor_droop == 0: droop response disabled (no correction).
        # _f_error within deadband: small dead-zone to avoid hunting.
        # grid-connected: droop inactive (infinite bus holds frequency).
        _droop_correction_mw = 0.0

    # Effective turbine dispatch setpoint includes the droop correction.
    # Used by the arbitrator, the balance decomposition, and the TickResult.
    _p_dispatch_droop_mw = max(0.0, p_dispatch_required_mw + _droop_correction_mw)

    # 4. Turbine advance + Phase 1b loading layer + BESS shortfall coverage
    #
    # advance() ticks STARTING countdown timers and the legacy RAMPING ramp.
    # SYNCHRONISED units are no-ops in advance() — loading layer drives them.
    for turbine in state.turbines:
        turbine.advance(sim_time, dt_seconds)

    # Phase 1b: loading layer — drive SYNCHRONISED units toward their share of
    # the droop-adjusted fleet setpoint.  Returns sub_msl_surplus_mw (> 0 only
    # when P_allocated < Σ msl_i, which holds the floor and reports the gap).
    # Allocated set A = SYNCHRONISED state ONLY.
    # RAMPING and AT_TARGET (legacy pre-Phase-2 aliases) continue using
    # advance() and the old stage_target() mechanism for backward compatibility.
    _synchronised_units = [
        t for t in state.turbines
        if t.state == TurbineState.SYNCHRONISED and not t.config.hot_standby
    ]
    _sub_msl_surplus_mw: float = apply_loading(
        _synchronised_units, _p_dispatch_droop_mw, dt_seconds
    )

    # Phase 11.3: dispatch.tick() now returns a 4-tuple.
    # _bess_setpoint_mw: commanded BESS output before SOC/power clipping.
    # Unpack position 2 (before candidates) — see dispatch.DispatchArbitrator.tick().
    # Phase 13.3: pass the droop-adjusted setpoint so the turbine is staged toward
    # the frequency-corrected target and the BESS covers only the residual shortfall.
    turbine_output_mw, bess_output_mw, _bess_setpoint_mw, _arb_candidates = state.arbitrator.tick(_p_dispatch_droop_mw, dt_seconds)
    # Phase 13.4 B3: detect when the commanded BESS output exceeds the fleet's
    # total rated power ceiling.  Surfaced in TickResult for dashboard / alerts.
    _binding_constraint: Optional[str] = (
        "bess_power_saturated"
        if _bess_setpoint_mw > sum(b.config.rated_mw for b in state.bess_units)
        else None
    )

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

    # 4d. §26.4 unified selection + §23.2 curtailment ladder (Step 10/11).
    #
    # Step 11 K1/K3: build one pool from all candidate sources and pass to
    # select_candidates() — the TC-49 live path.  Pool members:
    #   _arb_candidates: BESS (pos=0) + turbine (pos=1) from arbitrator.tick()
    #   _curtailment_candidates: tiers A-D (pos=4,5) from generate_candidates()
    #
    # is_low_confidence: pre-computed from GPU state and site.uncalibrated so
    # TC-43's low_confidence interlock can block the ladder before ConfidenceEngine
    # runs (step 6).  Same tags as step 6 — they cannot disagree.
    #
    # Phase 11.2 — workload signal absence/staleness flags.
    # Computed here (before curtailment gating) so _workload_signal_absent can
    # be folded into _is_low_confidence and block autonomous curtailment
    # (never-silent rule — mirrors TC-43's unmapped-hardware interlock).
    # SOLAR_STEP and UNIT_TRIP events never update the timestamp (early-return
    # in apply_workload_signal ensures it), so they do not reset staleness.
    _workload_signal_absent = (
        bool(state.gpu_modules) and not state._ever_received_workload_signal
    )
    _workload_signal_stale = (
        bool(state.gpu_modules)
        and state._ever_received_workload_signal
        and (sim_time - state._last_workload_signal_sim_time) >= state.site.workload_signal_stale_s
    )

    _is_low_confidence = (
        any(g.has_active_unmapped_jobs() for g in state.gpu_modules)
        or state.site.uncalibrated
        # Phase 11.2: absent feed is structurally equivalent to unmapped hardware
        # for the purposes of the curtailment interlock (TC-43 pattern).
        or _workload_signal_absent
    )
    _remaining_gap_mw = max(
        0.0, p_dispatch_required_mw - turbine_output_mw - bess_output_mw
    )

    # TC-64: if PMS fast shed is active, curtailment is bypassed entirely.
    # GridSignal must not curtail in response to a PMS-driven load reduction.
    # TC-66: the event is already in pms.fast_shed_log for forecast-error attribution.
    if _pms_shed_active:
        _log.info(
            "PMS fast shed active at sim_time=%.1f — "
            "curtailment ladder bypassed (TC-64). "
            "Event recorded for forecast-error attribution (TC-66).",
            sim_time,
        )
        _curtailment_candidates: list[CandidateResponse] = []
    else:
        _curtailment_candidates = state.curtailment_ladder.generate_candidates(
            gap_mw=_remaining_gap_mw,
            is_low_confidence=_is_low_confidence,
            operating_tier=state.site.operating_tier,
            sim_time=sim_time,
        )

    # K1 unified pool: storage + turbine (dispatched) + curtailment (proposed).
    # select_candidates() sorts by total order (position ASC, impact DESC, id ASC)
    # and greedily selects until the gap is covered — TC-49 live path.
    _unified_pool: list[CandidateResponse] = _arb_candidates + _curtailment_candidates
    _selected_unified: list[CandidateResponse] = select_candidates(
        _unified_pool, p_dispatch_required_mw
    )

    # Convert selected curtailment entries to CurtailmentProposal for TickResult.
    _curtailment_ladder_positions = frozenset({
        LadderPosition.CURTAILMENT_A_B, LadderPosition.CURTAILMENT_C_D
    })
    _curtailment_proposals: list[CurtailmentProposal] = [
        CurtailmentProposal(
            tier=CurtailmentTier(c.response_kind),
            estimated_impact_mw=c.estimated_impact_mw,
            requires_confirmation=c.requires_confirmation,
            expires_at_sim_time=sim_time + state.curtailment_ladder.MAX_HOLD_S,
            bounded_by_gap=True,
        )
        for c in _selected_unified
        if c.ladder_position in _curtailment_ladder_positions
    ]
    _curtailment_proposal_tiers: tuple[str, ...] = tuple(
        p.tier.value for p in _curtailment_proposals
    )

    # TC-65: detect PMS/GridSignal shed order conflict (commissioning defect).
    _pms_order_conflict: str | None = None
    if state.pms is not None and _curtailment_proposals:
        _gs_shed_order = [
            c.response_kind for c in _selected_unified
            if c.ladder_position in _curtailment_ladder_positions
        ]
        _pms_order_conflict = state.pms.check_order_conflict(_gs_shed_order)
        if _pms_order_conflict:
            _log.warning("SCADA %s", _pms_order_conflict)

    # Step 11 — SCADA command recording (TC-68 egress boundary).
    # Only TURBINE_SETPOINT, BESS_DISPATCH, LOAD_CURTAILMENT may appear.
    # Protection commands (islanding, droop, etc.) must never be issued by GridSignal.
    _scada_commands_issued = 0
    if turbine_output_mw > 1e-9:
        state.scada_layer.issue_command(
            CommandType.TURBINE_SETPOINT, "turbine-fleet", 64, sim_time, dt_seconds,
        )
        _scada_commands_issued += 1
    if bess_output_mw > 1e-9:
        state.scada_layer.issue_command(
            CommandType.BESS_DISPATCH, "bess-fleet", 64, sim_time, dt_seconds,
        )
        _scada_commands_issued += 1
    for _cp in _curtailment_proposals:
        if not _cp.requires_confirmation:
            state.scada_layer.issue_command(
                CommandType.LOAD_CURTAILMENT, f"curtail-{_cp.tier.value}",
                64, sim_time, dt_seconds,
            )
            _scada_commands_issued += 1
    state.scada_layer.deliver_pending(sim_time)

    # GT-1: §7.4 contingency coverage — pure function, no I/O, no mutation.
    # Build a frozen PlantState snapshot from the current simulation state
    # (after dispatch arbitration and SCADA recording are complete) and call
    # evaluate_contingency().  The result is stamped onto TickResult so the
    # WS payload carries quantitative gen-trip figures to the dashboard every tick.
    _plant_state = PlantState(
        turbine_snapshots=tuple(
            TurbineSnapshot(
                asset_id=t.config.asset_id,
                current_output_mw=t.output_mw(),
                rated_mw=t.config.rated_mw,
                r_asset_mw_per_s=t.config.r_asset_mw_per_s,
                # Synchronized = RAMPING or AT_TARGET; OFFLINE = hot standby or uncommissioned.
                # Phase 2: use is_synchronised property to exclude STARTING/
                # OUT_OF_SERVICE/TRANSITIONAL units from N-1 computation.
                is_synchronized=t.is_synchronised,
            )
            for t in state.turbines
        ),
        bess_snapshots=tuple(
            BessSnapshot(
                asset_id=b.config.asset_id,
                rated_mw=b.config.rated_mw,
                soc_mwh=b.soc_mwh,
                usable_mwh=b.config.usable_mwh,
                p_anchor_reserve_mw=b.config.p_anchor_reserve_mw,
                grid_forming=b.config.grid_forming,
            )
            for b in state.bess_units
        ),
        island_mode=state.site.island_mode,
        curtailable_capacity_mw=state.curtailment_ladder.total_capacity_mw(),
        renewable_mw=p_renewable_mw,
    )
    _contingency_coverage = evaluate_contingency(_plant_state)

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
    # Phase 11.2: workload signal quality tags (flags were computed at 4d,
    # before the curtailment interlock that uses them).
    if _workload_signal_absent:
        tags.add(DataQualityTag.WORKLOAD_SIGNAL_ABSENT)
    if _workload_signal_stale:
        tags.add(DataQualityTag.WORKLOAD_SIGNAL_STALE)

    # Phase 11.1: queue-derived forecast — Section 4 formula.
    # P_compute_forecast(t) = Σ_i Nodes_i(t) × kW_i × PUE_base / 1000
    # No ramp multiplier: this is the full-TDP draw for all currently admitted
    # jobs.  Sourced exclusively from WorkloadSignal; invariant to measured-draw
    # fluctuations (F3 criterion: step change in measured draw with no new
    # WorkloadSignal → forecast changes by exactly 0.0 MW).
    #
    # target_output_mw() is the existing method used by stage_for_predicted_step()
    # to size the turbine pre-stage — we reuse it here for consistency so the
    # confidence band and the staging computation are always aligned (F4 criterion).
    forecast_mw = sum(g.target_output_mw() for g in state.gpu_modules)

    # Never-silent rule (Phase 11.2 §12 / TC-43 pattern):
    # When WORKLOAD_SIGNAL_ABSENT is active, the forecaster must not present a
    # confident 0 MW.  Fall back to max(queue-forecast, measured-draw) to ensure
    # the band never goes below what the site is visibly drawing.
    _confidence_point_mw = (
        max(forecast_mw, p_total_mw)
        if _workload_signal_absent
        else forecast_mw
    )
    confidence = state.confidence_engine.band_for(_confidence_point_mw, tags)

    alert_fired = state._pending_alert is not None and state._pending_alert.fires_at_sim_time <= sim_time
    if alert_fired:
        state._pending_alert = None

    # Turbine ramp credit is visible while a STARTING ramp is in-flight (dt_lead_next_s > 0).
    # Once the ramp completes (dt_lead_next_s reaches 0) reset the staging info.
    if dt_lead_next_s <= 0.0:
        state._pending_ramp_credit_mw   = 0.0
        state._pending_peak_shortfall_mw = 0.0

    # D7 fix: §5.1 onboarding alerts — drain the pending set and clear it so
    # the frozenset is non-empty on at most one tick per unique profile_id.
    unrecognised_alerts = frozenset(state._pending_unrecognised_alerts)
    state._pending_unrecognised_alerts = set()

    # Store grid state for the Kubernetes demand agent on the NEXT tick.
    # Carries the generation-side view (headroom, BESS SoC) computed this tick
    # so the agent can enforce power-caps based on the last committed values.
    if state.kube_agent is not None:
        _k_turbine_rated = sum(t.config.rated_mw for t in state.turbines)
        _k_bess_rated    = sum(b.config.rated_mw for b in state.bess_units)
        state._kube_grid_state = KubeGridState(
            p_dispatch_required_mw=net_demand_mw,
            bess_soc_fraction=(
                state.bess_units[0].soc_fraction if state.bess_units else 1.0
            ),
            turbine_headroom_mw=max(0.0, _k_turbine_rated - turbine_output_mw),
            bess_headroom_mw=max(0.0, _k_bess_rated - bess_output_mw),
        )

    # ── Collect stochastic-step fields for TickResult ─────────────────────────
    _step_phase = 0.0
    _step_kind = "training"
    if state.kube_agent is not None:
        _step_phase = state.kube_agent.current_step_phase
        _step_kind = state.kube_agent.current_step_kind

    # ── Phase 11.3: balance residual and frequency tracking ───────────────────
    # P_gen(t) = turbines + BESS (actual measured) + renewables.
    # _balance_residual_mw = P_gen − P_load  (local scratch — not broadcast).
    #
    # In grid-connected steady state, BESS is the balance slack and
    # _balance_residual_mw ≈ 0 by construction.  Non-zero when:
    #   (a) BESS is SOC-limited or power-saturated (bess_output < bess_setpoint), OR
    #   (b) there is a true load-model error (e.g. load_error injection for B1).
    # In islanded mode, a non-zero residual drives the swing equation below;
    # in grid-connected mode, the grid absorbs / provides the mismatch.
    # Branch B: _balance_residual_mw is a local scratch variable; it is NOT on
    # TickResult.  D4 is asserted inline below before any use in the swing eq.
    _p_gen_mw = turbine_output_mw + bess_output_mw + p_renewable_mw
    _balance_residual_mw = _p_gen_mw - p_total_mw

    # ── Phase 13.2: balance decomposition — three independent channels ────────
    #
    # _p_commanded_mw: what the dispatch logic ASKED all dispatchable + renewable
    # assets to produce this tick — three independently modelled sources:
    #   gt_setpoint = _p_dispatch_droop_mw  (turbine fleet, droop-adjusted)
    #   bess_setpoint = _bess_setpoint_mw   (BESS fleet, from arbitrator)
    #   renewable = p_renewable_mw          (solar + wind, from solar arrays)
    # Phase 13.3: gt_setpoint is now the droop-adjusted demand, not the raw
    # demand requirement.  This ensures frequency_forcing_mw reflects the
    # governor's correction and can become negative (restoring force) when
    # frequency is above nominal and the droop pulls the setpoint below demand.
    _p_commanded_mw = _p_dispatch_droop_mw + _bess_setpoint_mw + p_renewable_mw

    # asset_delivery_error_mw: actual dispatchable delivery minus commanded dispatch.
    #   = (turbine_output − gt_setpoint) + (bess_output − bess_setpoint)
    # Measures how closely the turbine and BESS fleets tracked their setpoints
    # (the droop-adjusted setpoint for the turbine fleet).
    # Positive = over-delivered; negative = under-delivered (e.g. BESS depleted,
    # turbine curtailed).  ~0 in steady state without injected faults (D3).
    #
    # Phase 13.3: this channel does NOT participate in the swing equation.
    # Frequency is driven by frequency_forcing_mw only — the dispatch-plan
    # mismatch — so that a physical delivery fault (e.g. BESS under-delivery)
    # does not spontaneously move frequency.  Only the dispatch plan drives
    # the inertial response.  "Model error must not move frequency."
    #
    # Renamed from model_error_mw (Phase 13.2 addendum): "asset delivery error"
    # correctly describes what the channel measures; "model error" implied it was
    # a modelling residual (which would be the slack variable that D5 was written
    # to prevent).  A genuine model_error_mw would require independent energy
    # accounting and is left for a future phase.
    # Renewable is excluded: it has no setpoint in this model (not dispatchable).
    # D5: computed exclusively from setpoints and actual outputs — NOT derived as
    #     "balance_residual − grid_exchange − frequency_forcing", which would make
    #     it the new slack variable.
    # channel_source: derived.
    _asset_delivery_error_mw = (
        (turbine_output_mw - _p_dispatch_droop_mw)
        + (bess_output_mw  - _bess_setpoint_mw)
    )

    # grid_exchange_mw / frequency_forcing_mw: both compute (_p_commanded − p_total)
    # but only one is non-zero — selected by mode topology:
    #   Grid-connected: infinite bus absorbs the dispatch surplus/deficit as PCC flow.
    #     grid_exchange_mw = _p_commanded − p_total  (positive = site exports to grid)
    #     frequency_forcing_mw = 0.0 exactly                                      (D2)
    #   Islanded: PCC open; dispatch plan presses/relieves rotating inertia instead.
    #     grid_exchange_mw = 0.0 exactly                                           (D1)
    #     frequency_forcing_mw = _p_commanded − p_total  (positive = frequency rises)
    # channel_source: derived (both channels use _p_commanded and p_total — two
    #   independently modelled quantities, neither defined to "close the equation").
    # _islanded was already computed in the droop block above (Phase 13.3).
    if _islanded:
        _grid_exchange_mw     = 0.0                           # topology — PCC open (D1)
        _frequency_forcing_mw = _p_commanded_mw - p_total_mw
    else:
        _grid_exchange_mw     = _p_commanded_mw - p_total_mw
        _frequency_forcing_mw = 0.0                           # grid holds frequency (D2)

    # D4 inline assertion (Branch B) — three channels must sum to the scratch
    # residual.  _balance_residual_mw is a local variable only; it is NOT on
    # TickResult.  Asserting here validates the decomposition without exposing
    # the scratch value in the public API.
    _d4_sum = _grid_exchange_mw + _frequency_forcing_mw + _asset_delivery_error_mw
    assert abs(_d4_sum - _balance_residual_mw) < 1e-6, (
        f"D4 invariant violated: sum of channels {_d4_sum:.9f} "
        f"!= scratch residual {_balance_residual_mw:.9f}"
    )

    # Phase 1b: ramp capability over LEAD_WINDOW_S horizon — broadcast so the
    # frontend drawer reads this typed field instead of applying its own cap.
    _ramp_capability_mw = ramp_capability(LEAD_WINDOW_S, state.turbines)

    # Swing equation — islanded mode only.
    # Phase 13.3: forcing input = frequency_forcing_mw ONLY.
    #   df/dt = frequency_forcing_mw / (2 × H × S_base) × f₀
    # where H = inertia_constant_s, S_base = total turbine fleet rating (MVA),
    #       f₀ = frequency_nominal_hz.
    #
    # frequency_forcing_mw is the dispatch-plan mismatch: (p_commanded − p_total).
    # This is the ONLY term that drives frequency.  Physical delivery faults
    # (asset_delivery_error_mw ≠ 0) do NOT directly alter the swing equation —
    # they appear in the delivery channel for diagnostics but model error must
    # not move frequency (Phase 13.3 design principle).
    #
    # Governor droop provides the restoring force: by adjusting _p_dispatch_droop_mw
    # before arbitration, the droop correction changes _p_commanded_mw each tick,
    # which changes frequency_forcing_mw, which drives df/dt back toward zero.
    # The feedback loop is:
    #   Δf > 0 → droop reduces setpoint → _p_commanded falls → frequency_forcing < 0
    #          → df/dt < 0 → frequency falls back toward nominal.
    #
    # _s_base_mw and _islanded are computed early in the droop block (Phase 13.3).
    # Grid-connected: frequency is held at nominal by the grid; reset each tick.
    if _islanded:
        _df_dt = (
            _frequency_forcing_mw
            / (2.0 * state.site.inertia_constant_s * _s_base_mw)
            * state.site.frequency_nominal_hz
        )
        state._frequency_hz += _df_dt * dt_seconds
    else:
        # Grid-connected: frequency is the grid's reference; not integrated.
        state._frequency_hz = state.site.frequency_nominal_hz

    # ── Phase 11.6: compute inlet temperature (Section 8 thermal model) ───────
    # T_inlet = T_ambient_base + cooling_fraction × T_rise_max_c
    # where cooling_fraction = p_cooling_mw / max_cooling_mw (0–1).
    # max_cooling_mw = alpha_max × max(p_compute_mw, ε) — the peak steady-state
    # cooling capacity at the current compute level.
    # Because p_cooling_mw already carries the dt_thermal thermal lag (via
    # CoolingModule.advance()), T_inlet inherits the same lag and automatically
    # satisfies the C3 lag-1 autocorrelation requirement (≥ 0.99 at 10 Hz when
    # tau_seconds=20s, since exp(−0.1/20) ≈ 0.9950).
    _T_AMBIENT_BASE_C = 20.0  # °C — chosen; representative air-cooled ambient
    _T_RISE_MAX_C     = 15.0  # °C — chosen; typical hot-aisle delta (PROTO-11-COOL)
    _max_cooling_mw = state.site.alpha_max * max(p_compute_mw, 1e-6)
    _cooling_fraction = (
        min(1.0, p_cooling_mw / _max_cooling_mw)
        if _max_cooling_mw > 1e-9
        else 0.0
    )
    _compute_inlet_temp_c = _T_AMBIENT_BASE_C + _cooling_fraction * _T_RISE_MAX_C

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
        # §7.4 SLD tile sub-fields.  p_expected_mw and banks_reporting are None
        # on the run path: the run engine has no independent expectation model,
        # and routing p_renewable_mw here creates a tautology that makes the
        # four-state classifier's ratio thresholds structurally unreachable.
        # The honest figures come from SolarSim.snapshot()["power"] (1 Hz console).
        # p_expected_mw=None  ← default from TickResult
        # banks_reporting=None  ← default from TickResult
        bess_bridging_seconds=bess_bridging_seconds,
        turbine_ramp_credit_mw=state._pending_ramp_credit_mw,
        peak_shortfall_mw=state._pending_peak_shortfall_mw,
        dt_lead_next_s=dt_lead_next_s,
        bridging_basis=bridging_basis,
        pre_staging_shift_mw=pre_staging_shift_mw,
        pre_staging_precool_mw=pre_staging_precool_mw,
        curtailment_proposal_tiers=_curtailment_proposal_tiers,
        pms_fast_shed_active=_pms_shed_active,
        pms_order_conflict=_pms_order_conflict,
        scada_commands_issued=_scada_commands_issued,
        kube_metrics=_kube_metrics,
        contingency_coverage=_contingency_coverage,
        step_phase=_step_phase,
        step_kind=_step_kind,
        # Phase 11.1: queue-derived forecast (single source of truth).
        forecast_mw=forecast_mw,
        # Phase 11.3: dispatch truthfulness.
        bess_setpoint_mw=_bess_setpoint_mw,
        # Phase 13.3: gt_setpoint_mw is the droop-adjusted turbine command
        # (_p_dispatch_droop_mw), not the raw demand requirement.  The droop
        # correction is zero at nominal frequency (deadband), so this field
        # equals p_dispatch_required_mw in steady state — B5b and similar
        # tests run at initial frequency (50 Hz) and are unaffected.
        gt_setpoint_mw=_p_dispatch_droop_mw,
        # balance_residual_mw REMOVED (Branch B) — local scratch only; D4 asserted above.
        frequency_hz=state._frequency_hz,
        # Phase 13.2: balance decomposition — three independent channels.
        # D4 (sum == scratch residual) is asserted inline above, not via a broadcast field.
        grid_exchange_mw=_grid_exchange_mw,
        frequency_forcing_mw=_frequency_forcing_mw,
        asset_delivery_error_mw=_asset_delivery_error_mw,
        # Phase 13.4: setpoint/actual split.
        model_error_mw=_model_error_mw,
        binding_constraint=_binding_constraint,
        # Phase 11.6: cooling thermal lag — compute inlet temperature.
        compute_inlet_temp_c=_compute_inlet_temp_c,
        # Phase 1b: loading-layer outputs.
        sub_msl_surplus_mw=_sub_msl_surplus_mw,
        ramp_capability_mw=_ramp_capability_mw,
    )
