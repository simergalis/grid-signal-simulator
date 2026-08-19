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
from .loading import apply_loading, ramp_capability
from .contingency import BessSnapshot, FuelCellSnapshot, PlantState, TurbineSnapshot, evaluate_contingency
from .kube_demand import KubeDemandAgent, KubeGridState

_log = logging.getLogger(__name__)


from .dispatch import (
    CandidateResponse, CheckpointClassifier, ConfidenceEngine, CurtailmentLadder,
    CurtailmentProposal, CurtailmentTier, DispatchArbitrator, InsufficientReserveAlert,
    LadderPosition, PreStagingEngine, select_candidates,
)
from .commitment import (
    CommitmentConfig, CommitmentDecision, PendingStartRegister,
    SustainedCondition, evaluate_commitment,
)
from .scada_layer import CommandType, SimulatedPMS, SimulatedScadaLayer
from .models import DataQualityTag, GENERIC_FALLBACK_PROFILE, IslandMode, KubeClusterMetrics, KubeMetrics, SiteConfig, ThermalState, TickResult, WorkloadEventType, WorkloadSignal
from ._plane_guard import _EVALUATE_TICK_PERMITTED
from .sim_clock import SimClock
from . import site_parameters as _sp
from .power_balance import (
    BalanceTerms as _BalanceTerms,
    balance_defect_mw as _balance_defect_mw,
    ISLANDED as _BAL_ISLANDED,
    GRID_TIE as _BAL_GRID_TIE,
)
from .power_source_priority import (
    AuthorityTier as _AuthorityTier,
    PowerRanker as _PowerRanker,
    PowerSource as _PowerSource,
    PowerSourceType as _PowerSourceType,
    ResponseLatencyClass as _ResponseLatencyClass,
)
from .droop import (
    DroopUnit as _DroopUnit,
    droop_correction as _droop_correction_fn,
    dispatch_requirement_mw as _droop_dispatch_mw,
    max_frequency_error_from_thresholds as _droop_max_freq_error,
)


@dataclass
class TenantBurstEvent:
    """Lightweight runtime representation of a scripted tenant workload event.

    Translated from TenantWorkloadEvent (api/schemas.py) at run-start by
    scenario_factory.py.  Stored on SimulationState.tenant_events and consumed
    each tick in evaluate_tick() — contributes gpus × 0.0007 MW to
    p_compute_demand_mw during [t_start, t_start + duration_s).
    """
    tenant_id: str
    gpus: int
    t_start: float
    duration_s: float

    @property
    def tdp_mw(self) -> float:
        return self.gpus * 0.0007


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
    # Kubernetes demand agents — one per tenant in multi-tenant mode, one in
    # single-agent mode, or empty for the standard scripted workload path.
    # Fixed iteration order A→B→C enforced by the factory (AT-7 determinism).
    # Use the kube_agent property for backward-compatible single-agent reads.
    kube_agents: list[KubeDemandAgent] = field(default_factory=list)

    @property
    def kube_agent(self) -> KubeDemandAgent | None:
        """Backward-compat: primary (first) agent, or None when no agents."""
        return self.kube_agents[0] if self.kube_agents else None

    @kube_agent.setter
    def kube_agent(self, value: KubeDemandAgent | None) -> None:
        """Backward-compat setter: replaces kube_agents[0] or clears the list.
        Used by tests that set a single agent directly on SimulationState.
        """
        if value is None:
            self.kube_agents.clear()
        elif self.kube_agents:
            self.kube_agents[0] = value
        else:
            self.kube_agents.append(value)
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

    # Operator GPU load profile — zero-order-hold list of (sim_time_s, fraction)
    # tuples sorted ascending by time.  Empty = constant 1.0 (full load).
    # Populated from ScenarioSpec.gpu_load_profile at run start; all existing
    # scripted scenarios and tests omit it (empty = no-op, fully backward-compat).
    gpu_load_profile: list[tuple[float, float]] = field(default_factory=list)

    # Phase 11.4 — Workload floor (MW).
    # Computed from ScenarioSpec.workload_floor_fraction × peak_compute_mw
    # by core.generation_factory.compute_floor_mw() at run start.
    # evaluate_tick() clamps p_compute_demand_mw to at least this value every tick.
    # 0.0 (default) = no floor enforced; fully backward-compatible.
    compute_floor_mw: float = 0.0

    # Scripted tenant workload events — each adds GPU TDP to p_compute_demand_mw
    # during [t_start, t_start + duration_s).  Populated from
    # ScenarioSpec.tenant_events at run start via scenario_factory.py.
    # Empty list = no extra tenant load (default; fully backward-compat).
    tenant_events: list = field(default_factory=list)  # list[TenantBurstEvent]

    # Contracted power ceilings (MW) per tenant ID — populated by scenario_factory
    # alongside tenant_events.  Empty dict when no tenant events are configured.
    # Used by evaluate_tick() to compute overage MWh when a tenant draws above
    # 100 % of their contracted ceiling (allowed up to 150 %; billed at +50 %).
    tenant_contracted_mw: dict = field(default_factory=dict)  # {tenant_id: float}

    # Per-tenant overage energy accumulator (MWh) — incremented each tick for
    # any tenant drawing above their contracted ceiling.  Zero-initialised;
    # read by run_manager at end of run to emit the billing summary.
    tenant_overage_mwh: dict = field(default_factory=dict)    # {tenant_id: float}

    # Fuel cell array rated capacity (MW).  0.0 when fuel_cell_enabled is False.
    # Set by scenario_factory after SimulationState construction so the dispatch
    # logic in evaluate_tick() can dispatch the fuel cell in marginal-cost order
    # after cheaper BESS and turbine capacity.  Fully backward-compatible:
    # default 0.0 means no fuel cell dispatch in any existing scenario or test.
    fuel_cell_rated_mw: float = 0.0

    # Phase 11.3 — frequency state for the swing equation (islanded mode only).
    # Persisted on SimulationState so df/dt integration accumulates correctly
    # across ticks.  Initialized to site.frequency_nominal_hz in __post_init__
    # (A2 / Task #200 — no literal default); deviates in islanded mode when
    # balance_residual_mw is non-zero.  Reset to frequency_nominal_hz each tick
    # in grid-connected mode (the grid is the infinite-bus frequency reference).
    _frequency_hz: float = field(default=0.0, init=False)  # set in __post_init__

    # Phase 11.3/11.5 — running forecast MAE accumulators.
    # Used by Phase 11.5 Forecast Quality panel to report empirical accuracy.
    # _forecast_error_sum_mw: running sum of |forecast_mw - p_actual_mw| over
    #   ticks where p_actual > 1e-4 (meaningful load present).
    # _forecast_ticks: number of ticks included in the MAE sum.
    # Both are intentionally not reset mid-run (full-run statistic).
    _forecast_error_sum_mw: float = field(default=0.0, init=False)
    _forecast_ticks:        int   = field(default=0,   init=False)

    # Phase D Item 5: commitment engine state.
    # All four fields are init=False; initialized in __post_init__ from the
    # catalogue so no threshold appears as a code literal (Guard D1).
    # PROHIBITED: crediting _pending_start contents toward capacity, reserve,
    # ramp, or headroom — the pending unit is not yet on the bus.
    _commit_cfg:    CommitmentConfig    = field(init=False)
    _pending_start: PendingStartRegister = field(init=False)
    _commit_cond:   SustainedCondition  = field(init=False)
    _decommit_cond: SustainedCondition  = field(init=False)
    # Fuel-cell saturation turbine-commit latch.  _threshold_above records the
    # previous tick's level for rising-edge detection; _signal_pending holds one
    # crossing until the sequential-start guard can accept it.
    _fuel_cell_commit_threshold_above: bool = field(default=False, init=False)
    _fuel_cell_commit_signal_pending: bool = field(default=False, init=False)
    # Phase E Item 6: sim_time of the most recent breaker-open event.
    # Guards sequential-stop settling: a new decommit is blocked until
    # (sim_time − _last_breaker_open_s) ≥ max(unload_tail_s) across the fleet.
    _last_breaker_open_s: float = field(default=math.nan, init=False)

    # ── Phase 5 (DR-2026-08-08-FREQ): UFLS relay state ────────────────────────
    # _ufls_timer_s: elapsed time (s) each stage has been below its threshold.
    #   Resets to 0 when frequency recovers above the threshold (stage not fired).
    # _ufls_fired: True once a stage has shed load; stays True (no re-engagement).
    # _cumulative_shed_mw: total load shed so far this run by all UFLS stages.
    #   Monotonically increasing; used by Phase 6 P_served computation.
    # _relay_81u_timer_s: elapsed time (s) frequency has been ≤ relay_81u_threshold_hz.
    # _relay_81u_fired: True once the 81U islanded UF protection trips.
    # Initialized in __post_init__ (UFLS lists sized to catalogue stage count).
    _ufls_timer_s:      list  = field(default_factory=list, init=False)
    _ufls_fired:        list  = field(default_factory=list, init=False)
    _cumulative_shed_mw: float = field(default=0.0, init=False)
    _relay_81u_timer_s: float = field(default=0.0, init=False)
    _relay_81u_fired:   bool  = field(default=False, init=False)

    def __post_init__(self) -> None:
        # Step 3 Item 4: arbitrator now holds a reference to site so it can
        # read island_mode each tick (mode changes with operating state —
        # Step 11 will flip it; holding the reference keeps the tick path O(1)).
        self.arbitrator = DispatchArbitrator(self.turbines, self.bess_units, self.site)
        # Phase D Item 5: commitment engine — build config from catalogue, wire
        # PendingStartRegister to the arbitrator so stage_for_predicted_step()
        # respects the sequential-start contract (D-05).
        self._commit_cfg    = CommitmentConfig.from_catalogue()
        self._pending_start = PendingStartRegister()
        self._commit_cond   = SustainedCondition(threshold_s=self._commit_cfg.commit_confirm_s)
        self._decommit_cond = SustainedCondition(threshold_s=self._commit_cfg.decommit_confirm_s)
        self.arbitrator.pending_start = self._pending_start
        # Step 10: curtailment ladder and pre-staging engine.
        self.curtailment_ladder = CurtailmentLadder()
        if self.site.pre_staging_config is not None:
            self.pre_staging_engine = PreStagingEngine(self.site.pre_staging_config)
        # Step 11: SCADA layer (seeded, deterministic) and optional PMS.
        self.scada_layer = SimulatedScadaLayer(seed=42)
        if self.site.pms_config is not None:
            self.pms = SimulatedPMS(self.site.pms_config)
        # A2 / Task #200: initialise frequency from site nominal (no literal default).
        # SiteConfig.frequency_nominal_hz is required (no default) so this always
        # sources from a conscious per-site choice (60 Hz WECC/SDG&E; 50 Hz EU/APAC).
        self._frequency_hz = self.site.frequency_nominal_hz
        # Phase 5: UFLS timer/fired lists — sized to catalogue stage count.
        # Always 3 stages in the current catalogue; sized dynamically for robustness.
        _n_ufls = len(self.site.ufls_stages)
        self._ufls_timer_s = [0.0] * _n_ufls
        self._ufls_fired   = [False] * _n_ufls

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


_STANDBY_THERMAL_PRIORITY = {
    ThermalState.HOT: 0,
    ThermalState.WARM: 1,
    ThermalState.COLD: 2,
}


def _offline_turbines_by_thermal_priority(
    turbines: list[TurbineModule],
) -> list[TurbineModule]:
    """Return offline turbines in hot → warm → cold, then roster order."""
    roster_index = {id(turbine): index for index, turbine in enumerate(turbines)}
    candidates = [
        turbine
        for turbine in turbines
        if turbine.state == TurbineState.OFFLINE
    ]
    return sorted(
        candidates,
        key=lambda turbine: (
            _STANDBY_THERMAL_PRIORITY[turbine.thermal_state],
            roster_index[id(turbine)],
        ),
    )


def _promote_reserve_standby_labels(
    turbines: list[TurbineModule],
) -> tuple[str, ...]:
    """Maintain one HOT and one WARM label among remaining standby units.

    Any additional reserve units are labelled COLD.  With only one remaining
    standby unit, HOT is retained as the highest-readiness reserve.
    """
    remaining = [
        turbine
        for turbine in _offline_turbines_by_thermal_priority(turbines)
        if turbine.config.hot_standby
    ]
    desired = [ThermalState.HOT, ThermalState.WARM]
    changes: list[str] = []
    for index, turbine in enumerate(remaining):
        target_state = desired[index] if index < len(desired) else ThermalState.COLD
        previous_state = turbine.thermal_state
        if previous_state != target_state:
            turbine.assign_standby_thermal_state(target_state)
            changes.append(
                f"{turbine.config.asset_id}:{previous_state.value}->{target_state.value}"
            )
    return tuple(changes)


def _gpu_load_fraction_at(profile: list[tuple[float, float]], t: float) -> float:
    """Zero-order-hold lookup for gpu_load_profile.

    Returns the non-negative load multiplier that applies at sim-time t.
    The last entry whose time_s <= t wins; if t precedes all entries the first
    entry's value is used.  Returns 1.0 for an empty profile (full load, no-op).
    Negative authored values are clamped to zero; values above 1.0 intentionally
    model planned GPU over-peak demand.
    """
    if not profile:
        return 1.0
    frac = profile[0][1]          # use first point even before its timestamp
    for time_s, value in profile:
        if time_s <= t:
            frac = value
        else:
            break
    return max(0.0, frac)


def _cost_ranked_dispatch_allocations(
    demand_mw: float,
    *,
    bess_available_mw: float,
    turbine_available_mw: float,
    fuel_cell_available_mw: float,
) -> dict[str, float]:
    """Allocate discretionary demand using the shared marginal-cost ranking.

    Renewable output and physically unavoidable turbine minimum-stable output
    are removed before this helper is called.  The remaining dispatchable MW is
    allocated greedily from :class:`PowerRanker`, so the physics path and the
    operator advisory use one catalogue-backed source of truth.
    """
    sources = [
        _PowerSource(
            source_id="bess-fleet",
            source_type=_PowerSourceType.BESS,
            dispatchable=True,
            counts_toward_reserve=True,
            marginal_cost_mwh=float(_sp.value("bess_marginal_cost_mwh")),
            response_latency_class=_ResponseLatencyClass.INSTANT,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            available_mw=max(0.0, bess_available_mw),
            cost_basis_note="catalogue: bess_marginal_cost_mwh",
        ),
        _PowerSource(
            source_id="turbine-fleet",
            source_type=_PowerSourceType.TURBINE,
            dispatchable=True,
            counts_toward_reserve=True,
            marginal_cost_mwh=float(_sp.value("turbine_variable_per_mwh")),
            response_latency_class=_ResponseLatencyClass.THERMAL_LAG,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            available_mw=max(0.0, turbine_available_mw),
            cost_basis_note="catalogue: turbine_variable_per_mwh",
        ),
        _PowerSource(
            source_id="fuel-cell-fleet",
            source_type=_PowerSourceType.FUEL_CELL,
            dispatchable=True,
            counts_toward_reserve=False,
            marginal_cost_mwh=float(_sp.value("fuel_cell_ppa_rate_mwh")),
            response_latency_class=_ResponseLatencyClass.RAMP_LIMITED,
            authority_tier=_AuthorityTier.AUTONOMOUS,
            available_mw=max(0.0, fuel_cell_available_mw),
            cost_basis_note="catalogue: fuel_cell_ppa_rate_mwh",
        ),
    ]
    ranked = _PowerRanker().rank(sources).ranked_sources
    remaining_mw = max(0.0, demand_mw)
    allocations = {
        "bess-fleet": 0.0,
        "turbine-fleet": 0.0,
        "fuel-cell-fleet": 0.0,
    }
    for source in ranked:
        if remaining_mw <= 1e-9:
            break
        allocated_mw = min(source.available_mw, remaining_mw)
        allocations[source.source_id] = allocated_mw
        remaining_mw -= allocated_mw
    return allocations


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
    if state.kube_agents:
        # Fixed declaration order (AT-7 determinism: list iteration, never
        # dict/set iteration).  Admission totals are isolated by cluster_id:
        # legacy A/B/C agents intentionally share one ID and one fleet ceiling;
        # heterogeneous multi-cluster scenarios use distinct IDs and ceilings.
        _admitted_by_cluster: dict[str, int] = {}
        _merged_signals: list[WorkloadSignal] = []
        _merged_metrics: list[KubeMetrics] = []
        for _agent in state.kube_agents:
            _cluster_key = _agent.config.cluster_id or "legacy-shared-fleet"
            _already_admitted = _admitted_by_cluster.get(_cluster_key, 0)
            _ks_list, _km = _agent.tick(
                sim_time, dt_seconds, state._kube_grid_state,
                already_admitted_nodes=_already_admitted,
            )
            _admitted_by_cluster[_cluster_key] = (
                _already_admitted + _km.admitted_nodes
            )
            _merged_signals.extend(_ks_list)
            _merged_metrics.append(_km)

        # Merge per-agent metrics into independently capacity-constrained
        # cluster summaries.  Legacy shared-cluster agents collapse into one
        # summary; new scheduler clusters stay separate.
        _cluster_rollup: dict[str, dict[str, object]] = {}
        for _agent, _metric in zip(state.kube_agents, _merged_metrics):
            _cluster_key = _agent.config.cluster_id or "legacy-shared-fleet"
            _entry = _cluster_rollup.setdefault(
                _cluster_key,
                {
                    "agent": _agent,
                    "scheduled_units": 0,
                    "admitted_units": 0,
                },
            )
            _entry["scheduled_units"] = int(_entry["scheduled_units"]) + _metric.node_count
            _entry["admitted_units"] = int(_entry["admitted_units"]) + _metric.admitted_nodes

        _cluster_metrics = []
        for _cluster_key, _entry in _cluster_rollup.items():
            _agent = _entry["agent"]
            _scheduled_units = int(_entry["scheduled_units"])
            _admitted_units = int(_entry["admitted_units"])
            _max_units = _agent.config.max_nodes
            _capacity_mw = _max_units * _agent.config.rated_kw_per_node / 1000.0
            _cluster_metrics.append(KubeClusterMetrics(
                cluster_id=_cluster_key,
                tenant_id=_agent.config.tenant_id,
                scheduler_type=_agent.config.scheduler_type,
                hardware_profile_id=_agent.config.hardware_profile_id,
                capacity_unit=_agent.config.capacity_unit,
                gpus_per_unit=_agent.config.gpus_per_unit,
                max_units=_max_units,
                scheduled_units=_scheduled_units,
                admitted_units=_admitted_units,
                gpu_capacity=_max_units * _agent.config.gpus_per_unit,
                rated_capacity_mw=round(_capacity_mw, 4),
                utilization=_scheduled_units / _max_units,
            ))

        _total_capacity_mw = sum(m.rated_capacity_mw for m in _cluster_metrics)
        _total_capacity_units = sum(m.max_units for m in _cluster_metrics)
        _scheduled_units = sum(m.scheduled_units for m in _cluster_metrics)
        _scheduled_mw = sum(
            m.scheduled_units
            * next(
                a.config.rated_kw_per_node
                for a in state.kube_agents
                if (a.config.cluster_id or "legacy-shared-fleet") == m.cluster_id
            )
            / 1000.0
            for m in _cluster_metrics
        )
        _kube_metrics = KubeMetrics(
            utilization=(
                _scheduled_mw / _total_capacity_mw
                if _total_capacity_mw > 0.0
                else (
                    _scheduled_units / _total_capacity_units
                    if _total_capacity_units > 0 else 0.0
                )
            ),
            node_count=sum(m.node_count for m in _merged_metrics),
            power_cap_active=any(m.power_cap_active for m in _merged_metrics),
            headroom_mw=_merged_metrics[0].headroom_mw,
            active_jobs=sum(m.active_jobs for m in _merged_metrics),
            admitted_nodes=sum(m.admitted_nodes for m in _merged_metrics),
            arrivals_this_tick=sum(m.arrivals_this_tick for m in _merged_metrics),
            requeued_this_tick=sum(m.requeued_this_tick for m in _merged_metrics),
            cap_gate_deferred_count=sum(m.cap_gate_deferred_count for m in _merged_metrics),
            queued_jobs=sum(m.queued_jobs for m in _merged_metrics),
            queued_nodes=sum(m.queued_nodes for m in _merged_metrics),
            pending_jobs=tuple(j for m in _merged_metrics for j in m.pending_jobs),
            active_jobs_detail=tuple(
                j for m in _merged_metrics for j in m.active_jobs_detail
            ),
            cluster_metrics=tuple(_cluster_metrics),
            total_gpu_capacity=sum(m.gpu_capacity for m in _cluster_metrics),
            total_capacity_mw=round(_total_capacity_mw, 4),
        )

        # §9 / resolution-log item 5: dt_lead_seconds for a Kubernetes signal
        # equals GPUModule.ramp_seconds — the physical window from scheduler
        # allocation to GPUs reaching full TDP.  For spec-built runs this is
        # wired from dt_lead_seconds in scenario_factory.build_run_context_from_spec.
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
        for _ks in _merged_signals:
            state.apply_workload_signal(_ks, dt_lead_seconds=_kube_ramp_s)

        # ── Propagate step_phase from primary agent (A) to GPUModules ────────
        # The within-step power profile lag (GPUModule.advance()) needs the
        # updated step_phase from the step scheduler.  Setting it here ensures
        # the lag state update in advance() uses the current tick's phase, not
        # the previous tick's.  This must happen between kube_agent.tick() and
        # gpu.advance().
        # Primary agent (kube_agents[0]) drives the fleet-level step scheduler.
        # Per-tenant step phases are deferred to CL-4; not in scope here.
        _fleet_phase = state.kube_agents[0].current_step_phase
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
    if _kube_metrics is not None and state.gpu_modules and state.kube_agents:
        _effective_admitted = sum(g.effective_node_count() for g in state.gpu_modules)
        _fleet_min = sum(a.config.min_nodes for a in state.kube_agents)
        _effective_total = max(_fleet_min, _effective_admitted)
        _raw_total = max(1, _kube_metrics.node_count)
        _kube_metrics = dataclasses.replace(
            _kube_metrics,
            node_count=_effective_total,
            utilization=min(
                1.0,
                _kube_metrics.utilization * (_effective_total / _raw_total),
            ),
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
    p_compute_demand_mw = sum(_per_job_draws.values())

    # ── GPU load profile scaling (operator-authored zero-order-hold) ──────────
    # Multiplies p_compute_demand_mw AND the per-job draws passed to the cooling
    # model by the active fraction so that cooling tracks the same throttled load.
    # No-op when the profile is empty (the default), so all existing tests and
    # seeded scenarios are unaffected.
    _gpu_load_fraction = _gpu_load_fraction_at(state.gpu_load_profile, sim_time)
    if _gpu_load_fraction != 1.0:
        p_compute_demand_mw *= _gpu_load_fraction
        # Scale per-job draws so the cooling model sees the same throttled GPU heat
        # output — not the full-TDP value before the profile was applied.
        _per_job_draws = {k: v * _gpu_load_fraction for k, v in _per_job_draws.items()}

    # ── Scripted tenant workload events ────────────────────────────────────────
    # Each TenantBurstEvent contributes gpus × 0.0007 MW during its active window.
    # Added AFTER gpu_load_fraction scaling so the profile throttles only the base
    # cluster load; tenant burst jobs are not throttled by the operator load profile.
    # No-op when tenant_events is empty (all existing tests and scenarios unaffected).
    #
    # Overage tracking: tenants may draw up to 150 % of their contracted ceiling.
    # Draw above 100 % is billed at +50 % per MWh; overage_mwh is accumulated here
    # per tenant and read by run_manager at end of run to emit the billing summary.
    if state.tenant_events:
        # Group active-window events by tenant so simultaneous jobs are combined.
        _tenant_draw: dict[str, float] = {}
        for _tev in state.tenant_events:
            if _tev.t_start <= sim_time < _tev.t_start + _tev.duration_s:
                _tenant_draw[_tev.tenant_id] = (
                    _tenant_draw.get(_tev.tenant_id, 0.0) + _tev.tdp_mw
                )
        if _tenant_draw:
            _tenant_extra_mw = sum(_tenant_draw.values())
            p_compute_demand_mw += _tenant_extra_mw
            # Accumulate overage MWh for any tenant drawing above their ceiling.
            if state.tenant_contracted_mw:
                _dt_h = dt_seconds / 3600.0
                for _tid, _draw_mw in _tenant_draw.items():
                    _ceil = state.tenant_contracted_mw.get(_tid, 0.0)
                    if _ceil > 0.0 and _draw_mw > _ceil + 1e-6:
                        state.tenant_overage_mwh[_tid] = (
                            state.tenant_overage_mwh.get(_tid, 0.0)
                            + (_draw_mw - _ceil) * _dt_h
                        )

    # Phase 11.4 — Apply workload floor (compute_floor_mw).
    # Clamps p_compute_demand_mw to at least compute_floor_mw so the Forecast
    # Quality panel always shows a visible actual-vs-forecast gap.  Only active
    # when the scenario sets workload_floor_fraction (compute_floor_mw > 0.0).
    # No-op when compute_floor_mw == 0.0 (default; all existing tests unaffected).
    #
    # Cooling-envelope contract: scenario_factory registers a "__floor__" envelope
    # at run start whenever compute_floor_mw > 0.0.  This block must maintain a
    # sample for that envelope on every tick to keep the lagged cooling correct:
    #
    #   • No active jobs (all load from floor): "__floor__" gets compute_floor_mw;
    #     job envelopes get nothing (they have no active draw this tick).
    #   • Jobs active but total < floor: job draws are scaled up to floor_mw;
    #     "__floor__": 0.0 is recorded so the floor envelope drains to zero and
    #     does not double-count with the scaled-up job heat.
    #   • Jobs active and total ≥ floor (floor not binding): job draws are passed
    #     unchanged; "__floor__": 0.0 is recorded so the floor envelope drains.
    if state.compute_floor_mw > 0.0:
        if p_compute_demand_mw < state.compute_floor_mw:
            p_compute_demand_mw = state.compute_floor_mw
            _draw_total = sum(_per_job_draws.values()) if _per_job_draws else 0.0
            if _draw_total > 0.0:
                # Jobs partially cover demand — scale them up to meet floor.
                # Record __floor__: 0.0 so its envelope drains and does not
                # double-count heat with the scaled job envelopes.
                _scale = state.compute_floor_mw / _draw_total
                _per_job_draws = {k: v * _scale for k, v in _per_job_draws.items()}
                _per_job_draws["__floor__"] = 0.0
            else:
                # No active jobs: floor carries all the compute load.
                _per_job_draws = {"__floor__": state.compute_floor_mw}
        else:
            # Floor not binding: jobs carry the load.  Zero the floor envelope so
            # its history drains to zero and does not inflate cooling demand.
            _per_job_draws = dict(_per_job_draws)
            _per_job_draws["__floor__"] = 0.0

    state.cooling.record_job_compute(sim_time, _per_job_draws)

    # 2. Cooling term (lagged)
    state.cooling.advance(sim_time, dt_seconds)
    p_cooling_demand_mw = state.cooling.output_mw()

    p_demand_mw = p_compute_demand_mw + p_cooling_demand_mw

    # _islanded: hoisted here (before section 3) so the §INV-CURT inverter
    # curtailment block can reference it before the Phase 13.3 droop block.
    # A single assignment; the same object is referenced throughout evaluate_tick().
    _islanded = (state.site.island_mode == IslandMode.ISLANDED)

    # 3. Solar offset (Extension E-1 / §7.1.1) — evaluated BEFORE arbitration
    #    so the fleet sizes against P_dispatch_required, not P_total.
    #    P_renewable can vanish without notice (Δt_lead = 0 for inverter trips);
    #    the arbitrator must never count it as ramp capability.
    for solar in state.solar_arrays:
        solar.advance(sim_time, dt_seconds)
    p_renewable_mw = sum(s.output_mw() for s in state.solar_arrays)

    # §INV-CURT: Inverter frequency-response curtailment (islanded mode only).
    #
    # IEEE 1547-2018 §6.5.2: a grid-forming inverter reduces renewable output
    # proportionally as frequency rises above of_warning_hz, saturating at full
    # curtailment when f reaches of_trip_hz.
    #
    # Curtailment fraction = clamp((f − of_warning) / (of_trip − of_warning), 0, 1).
    # Proportional (not a step-to-load clamp) — an abrupt step is itself a
    # disturbance; the linear ramp is the physically correct model.
    #
    # Gain K = 1 / (of_trip_hz − of_warning_hz) [Hz⁻¹] — derived entirely from
    # the existing catalogue threshold fields; no additional free parameter.
    # Provenance of the thresholds: CHOSEN (IEEE 1547-2018 Cat I, SDG&E defaults).
    #
    # Active when:
    #   • island_mode == ISLANDED
    #   • both of_warning_hz and of_trip_hz are non-None (threshold pair enabled)
    #   • of_trip_hz > of_warning_hz (well-ordered; guards against zero-divide)
    #   • state._frequency_hz > of_warning_hz (above the curtailment deadband)
    #
    # Uses state._frequency_hz (previous-tick frequency) — causal: the inverter
    # responds to the last measured frequency, not to a next-tick projection.
    _p_renewable_curtailed_mw = 0.0
    _of_warn_curt = state.site.of_warning_hz
    _of_trip_curt = state.site.of_trip_hz
    if (
        _islanded
        and _of_warn_curt is not None
        and _of_trip_curt is not None
        and _of_trip_curt > _of_warn_curt
        and state._frequency_hz > _of_warn_curt
    ):
        _curt_fraction = min(
            1.0,
            (state._frequency_hz - _of_warn_curt) / (_of_trip_curt - _of_warn_curt),
        )
        _p_renewable_curtailed_mw = _curt_fraction * p_renewable_mw
        p_renewable_mw = p_renewable_mw - _p_renewable_curtailed_mw
        _log.info(
            "§INV-CURT tick %d: f=%.3f Hz → curtail %.3f MW (%.1f %%) of solar "
            "(of_warn=%.1f Hz, of_trip=%.1f Hz).",
            state.tick_index, state._frequency_hz,
            _p_renewable_curtailed_mw, _curt_fraction * 100.0,
            _of_warn_curt, _of_trip_curt,
        )

    # P_dispatch_required(t) = P_total(t) − P_renewable(t), clipped at zero.
    # net_demand_mw is a synonym kept for TickResult reporting compatibility.
    #
    # EXPORT SCOPE NOTE: the unclamped value (p_total_mw - p_renewable_mw) can
    # be negative when renewable output exceeds load — that is the grid-export
    # condition and is relevant for the §7.1 grid-tie boundary.  It is NOT
    # stored here; only the clamped value is used.  Grid-export modelling is
    # out of scope for this simulator release.
    p_dispatch_required_mw = max(0.0, p_demand_mw - p_renewable_mw)
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

    # ── Phase 2C+4: Per-unit H_aggregate, S_base_mva, and bounded governor droop ─
    # Replaces the old _s_base_mw = Σ on-bus rated_MW / pf fleet formula.
    #
    # Per-unit inertia: S_i = rated_mw_i / pf_i (MVA per unit).
    #   H_agg = Σ(H_i × S_i) / Σ(S_i)  — capacity-weighted H.
    # On-bus turbines only: OFFLINE/STARTING contribute zero rotational inertia.
    #
    # Phase 4: Governor outer droop uses the per-turbine governor terminal state
    # (_gov_power_mw) from the previous tick's sub-step loop, not an instantaneous
    # droop formula. This correctly models the cascade dynamics (valve_tc → fuel_tc)
    # with the max_load_step bound, and persists across outer ticks.
    #
    # §REPORT-2A (island_collapse_hz defect): The existing island_collapse_hz
    # (IEEE 1547 Cat I = 57.0 Hz) is a grid-connected DER interconnection threshold.
    # It is currently applied in islanded mode — a defect. Phase 5 adds the
    # correct islanded 81U relay at relay_81u_threshold_hz (57.5 Hz PROVISIONAL).
    # island_collapse_hz is retained for backward compat with tests that set it
    # explicitly. See swing equation below.
    _GOVERNOR_DEADBAND_HZ: float = 0.02

    _on_bus_turbines = [t for t in state.turbines if t.is_on_bus]
    if _on_bus_turbines:
        _per_unit_s_i = [t.config.rated_mw / t.config.power_factor for t in _on_bus_turbines]
        _per_unit_h_s = [t.config.inertia_constant_s * s for t, s in zip(_on_bus_turbines, _per_unit_s_i)]
        _s_base_mva = sum(_per_unit_s_i)
        _h_aggregate = sum(_per_unit_h_s) / _s_base_mva
    else:
        # Phase 2C: zero synchronous machines on bus.
        # DELETED BRANCH: The old frozen-frequency path was:
        #   "if GF-BESS present: _df_dt=0, freeze frequency (no virtual inertia).
        #    else: virtual S_base = 1.0/pf, use SiteConfig.inertia_constant_s."
        # Phase 2C replaces this with the VSM inertia model (anchor_mode='vsm'):
        #   GF-BESS provides virtual inertia H_vsm; sub-step swing equation applies.
        # This enables realistic frequency dynamics during the zero-machine phase
        # (e.g., S9 zero-machine phase where GF-BESS held f at 60 Hz).
        _gf_bess_units = [b for b in state.bess_units if b.config.grid_forming]
        if _gf_bess_units and state.site.anchor_mode == "vsm":
            # VSM: GF-BESS contributes virtual inertia on its own MVA base.
            _vsm_s = sum(b.config.rated_mw / state.site.power_factor for b in _gf_bess_units)
            _s_base_mva = _vsm_s if _vsm_s > 0.0 else 1.0 / state.site.power_factor
            _h_aggregate = state.site.vsm_inertia_constant_s  # PROVISIONAL-UNMEASURED
        else:
            # No GF-BESS or non-vsm mode: minimum inertia sentinel.
            _s_base_mva = 1.0 / state.site.power_factor
            _h_aggregate = state.site.inertia_constant_s  # site-level H fallback

    # Phase 4 / Phase 1 — Dispatch droop correction.
    #
    # Phase 1 (DR-2026-08-09-BALANCE): bounded per-unit droop with Δf clamp
    # derived from the site's first-stage protective settings (DR-BAL-1 closed,
    # C-4). The unbounded fallback is removed; two paths for one behaviour must
    # not survive.
    #
    # Δf clamp derivation (C-4): the tightest margin from nominal to a first-stage
    # threshold. Beyond that point a machine is on a protection timer, not
    # governing. First-stage UF = site.ufls_stage1_hz; first-stage OF = site.of_trip_hz.
    # If no protective settings are configured, the clamp cannot be derived and
    # droop correction is skipped (no fallback to an unbounded formula).
    #
    # Attribute name differences from the integration guide (confirmed against codebase):
    #   t.unit_id         → t.config.asset_id
    #   t.current_output_mw → t.output_mw()      (method, not attribute)
    #   t.config.msl_mw   → t.config.p_min_stable_frac * t.config.rated_mw
    #
    # WHY INSTANTANEOUS FOR DISPATCH: same as before — see original comment above.
    # The sub-step governor cascade in Phase 3+4+5 still uses _GOVERNOR_DEADBAND_HZ
    # at line ~1525; that usage is unchanged here.
    _f_error_hz = state._frequency_hz - state.site.frequency_nominal_hz
    _governor_deadband_hz = _sp.value("governor_deadband_hz")
    # Dispatch ceiling = total installed fleet (not just on-bus) — dispatch intent,
    # not inertia basis. Decoupled from _s_base_mva per §INV-INERTIA.
    #
    # BUG-FIX: include BESS rated MW so that no-turbine configurations (e.g.
    # grid + fuel-cell + BESS with no gas turbines) do not produce a ceiling
    # of 0 MW.  With _sync_ceiling_mw = 0, the else-branch clamp
    # min(demand, 0) = 0 → _p_dispatch_droop_mw = 0 → arbitrator sees zero
    # fleet shortfall → BESS setpoint = 0 on every tick despite live demand.
    # Including BESS here aligns the code with the comment ("total installed
    # fleet") and allows the arbitrator to dispatch BESS against real demand.
    _sync_ceiling_mw = (
        sum(t.config.rated_mw for t in state.turbines) +
        sum(b.config.rated_mw for b in state.bess_units) +
        state.fuel_cell_rated_mw   # FC capacity raises the ceiling so dispatch reaches it
    )
    # Derive the Δf clamp from first-stage protective settings (C-4, DR-BAL-1).
    _first_stage_thresholds_hz = [
        hz for hz in [state.site.ufls_stage1_hz, state.site.of_trip_hz]
        if hz is not None
    ]
    try:
        _droop_max_f_err_hz: float | None = _droop_max_freq_error(
            state.site.frequency_nominal_hz, _first_stage_thresholds_hz
        )
    except ValueError:
        # No first-stage protective settings configured for this run — skip droop.
        _droop_max_f_err_hz = None
    if (
        _islanded
        and _on_bus_turbines
        and abs(_f_error_hz) > _governor_deadband_hz
        and _droop_max_f_err_hz is not None
    ):
        # Phase 1 active — bounded per-unit droop with headroom limits and Δf clamp.
        # Prevents the fleet ceiling from becoming the operating point (the pathology
        # that drove 21.2 MW of generation into a 6.86 MW load on demo-20mw).
        _droop_units = [
            _DroopUnit(
                unit_id=t.config.asset_id,
                rated_mw=t.config.rated_mw,
                output_mw=t.output_mw(),
                droop_r=t.config.droop_r,
                power_factor=t.config.power_factor,
                msl_mw=t.config.p_min_stable_frac * t.config.rated_mw,
            )
            for t in _on_bus_turbines
        ]
        _droop_phase1 = _droop_correction_fn(
            _droop_units,
            frequency_hz=state._frequency_hz,
            frequency_nominal_hz=state.site.frequency_nominal_hz,
            governor_deadband_hz=_governor_deadband_hz,
            max_frequency_error_hz=_droop_max_f_err_hz,
        )
        _p_dispatch_droop_mw, _droop_phase1 = _droop_dispatch_mw(
            p_dispatch_required_mw, _droop_phase1, _sync_ceiling_mw)
        _droop_correction_mw = _droop_phase1.correction_mw
        if _droop_phase1.fleet_ceiling_binding:
            _log.debug(
                "droop fleet ceiling binding: sync_ceiling=%.2f MW, "
                "bounded_correction=%.4f MW; verify frequency model is stable",
                _sync_ceiling_mw, _droop_correction_mw,
            )
    else:
        # Deadband / no turbines / no protective settings — zero correction.
        _droop_correction_mw = 0.0
        _p_dispatch_droop_mw = max(
            0.0,
            min(p_dispatch_required_mw + _droop_correction_mw, _sync_ceiling_mw),
        )

    # 4. Turbine advance + Phase 1b loading layer + BESS shortfall coverage
    #
    # Phase B Item 1 — interval-entry state snapshot:
    # Capture each unit's state BEFORE advance() runs.  A unit that promotes
    # RAMPING → SYNCHRONISED inside advance() has entry state RAMPING and is
    # excluded from the loaded set for this interval; its first loaded interval
    # is the next tick.  Building the set from live state (post-advance) would
    # include the promoted unit, causing apply_loading() to overwrite the ramp
    # endpoint that advance() just computed — an unbounded step (TC-88 defect).
    _entry_states: dict[str, "TurbineState"] = {
        t.config.asset_id: t.state for t in state.turbines
    }

    # Phase B Item 2 — reset per-interval write counters before advance().
    # begin_interval() zeros _output_writes on each TurbineModule so that
    # set_output()'s double-write guard starts fresh for this interval.
    for turbine in state.turbines:
        turbine.begin_interval()

    # advance() ticks STARTING countdown timers and the legacy RAMPING ramp.
    # SYNCHRONISED units are no-ops in advance() — loading layer drives them.
    for turbine in state.turbines:
        turbine.advance(sim_time, dt_seconds)

    # Phase D Item 5: clear pending start when tracked unit reaches SYNCHRONISED.
    # advance() may have just transitioned a STARTING unit to SYNCHRONISED; if
    # it matches the pending register, clear it so evaluate_commitment() can
    # issue the next start command on a future tick.
    for _ta in state.turbines:
        if _ta.state == TurbineState.SYNCHRONISED:
            state._pending_start.clear_on_synchronised(_ta.config.asset_id)

    # Phase 1b: loading layer — drive SYNCHRONISED units toward their share of
    # the droop-adjusted fleet setpoint.  Returns sub_msl_surplus_mw (> 0 only
    # when P_allocated < Σ msl_i, which holds the floor and reports the gap).
    #
    # Allocated set A = SYNCHRONISED at INTERVAL ENTRY (not live state).
    # Units that promoted to SYNCHRONISED during advance() (entry state RAMPING)
    # are excluded; their ramp endpoint is preserved for this interval.
    # Phase C Item 1: filter widened to {SYNCHRONISED, UNLOADING} before UNLOADING
    # was added (committed first so there is never a state where UNLOADING exists but
    # the filter does not include it).  An unloading unit is on-bus and producing;
    # if excluded, set_output() is never called and its output freezes — a silent
    # stall that the write-guard counter cannot catch (missing write ≠ double write).
    _synchronised_units = [
        t for t in state.turbines
        if _entry_states[t.config.asset_id] in (TurbineState.SYNCHRONISED, TurbineState.UNLOADING)
        and not t.config.hot_standby
    ]
    # _check_loading_exclusion deleted (Phase C): the legacy states (RAMPING, AT_TARGET)
    # it guarded against no longer exist.  The Phase B write guard (begin_interval +
    # set_output counter) provides the remaining double-write protection.

    # Phase E Item 5: split loading between UNLOADING and SYNCHRONISED units.
    # UNLOADING units receive exactly their MSL setpoint — not the proportional
    # fleet share — so output tracks continuously down to MSL rather than being
    # pulled by fleet-level redistribution.  Residual after MSL allocation goes
    # exclusively to SYNCHRONISED units.
    _unloading_units  = [t for t in _synchronised_units if t.state == TurbineState.UNLOADING]
    _truly_sync_units = [t for t in _synchronised_units if t.state == TurbineState.SYNCHRONISED]
    _msl_held_mw: float = sum(
        t.config.p_min_stable_frac * t.config.rated_mw for t in _unloading_units
    )

    # Live economic dispatch: allocate all discretionary MW from the same
    # catalogue-backed PowerRanker used by the advisory path.  Renewable output
    # has already been removed from _p_dispatch_droop_mw.  A turbine's
    # minimum-stable output remains a physical must-run floor; only capacity
    # above that floor competes with BESS and fuel-cell capacity on $/MWh.
    #
    # Units that synchronised during this interval are excluded from the loading
    # set until the next tick.  Their current output is therefore unavoidable
    # this interval and is removed before ranking, preventing a second source
    # from being allocated against the same demand.
    _controllable_turbine_ids = {
        t.config.asset_id for t in _synchronised_units
    }
    _uncontrolled_on_bus_mw = sum(
        t.output_mw()
        for t in state.turbines
        if t.is_on_bus and t.config.asset_id not in _controllable_turbine_ids
    )
    _sync_msl_mw = sum(
        t.config.p_min_stable_frac * t.config.rated_mw
        for t in _truly_sync_units
    )
    _turbine_must_run_mw = (
        _uncontrolled_on_bus_mw + _msl_held_mw + _sync_msl_mw
    )
    _turbine_incremental_available_mw = sum(
        max(
            0.0,
            t.config.rated_mw
            - t.config.p_min_stable_frac * t.config.rated_mw,
        )
        for t in _truly_sync_units
    )
    # Economic BESS availability must account for both the instantaneous power
    # ceiling and energy that can actually be delivered during this tick.  If
    # only the power ceiling is ranked, an empty/near-empty BESS reserves cheap
    # MW it cannot deliver and the fuel cell can incorrectly fill that gap while
    # cheaper turbine headroom remains unused.
    #
    # A scenario may additionally reserve the BESS after a configured normal
    # depth of discharge. The held charge stays out of the normal merit order,
    # but is released below when fuel-cell capacity and available grid import
    # cannot cover the demand.
    _bess_physical_ceilings_mw: list[float] = []
    _bess_normal_dispatch_ceilings_mw: list[float] = []
    _normal_bess_depth_fraction = state.site.bess_normal_dispatch_depth_fraction
    for _bess in state.bess_units:
        _bess_power_ceiling_mw = _bess.bridging_available_mw(
            state.site.island_mode
        )
        _bess_energy_ceiling_mw = (
            _bess.soc_mwh / (dt_seconds / 3600.0)
            if dt_seconds > 0.0
            else _bess_power_ceiling_mw
        )
        _physical_ceiling_mw = min(
            _bess_power_ceiling_mw,
            _bess_energy_ceiling_mw,
        )
        _bess_physical_ceilings_mw.append(_physical_ceiling_mw)
        if _normal_bess_depth_fraction <= 0.0:
            _bess_normal_dispatch_ceilings_mw.append(_physical_ceiling_mw)
            continue

        _reserve_soc_fraction = max(
            0.0,
            _bess.config.initial_soc_fraction - _normal_bess_depth_fraction,
        )
        _normal_energy_mwh = max(
            0.0,
            _bess.soc_mwh
            - _bess.config.usable_mwh * _reserve_soc_fraction,
        )
        _normal_energy_ceiling_mw = (
            _normal_energy_mwh / (dt_seconds / 3600.0)
            if dt_seconds > 0.0
            else _physical_ceiling_mw
        )
        _bess_normal_dispatch_ceilings_mw.append(
            min(_physical_ceiling_mw, _normal_energy_ceiling_mw)
        )
    _bess_available_mw = sum(_bess_normal_dispatch_ceilings_mw)
    _economic_demand_mw = max(
        0.0,
        _p_dispatch_droop_mw - _turbine_must_run_mw,
    )
    _economic_allocations = _cost_ranked_dispatch_allocations(
        _economic_demand_mw,
        bess_available_mw=_bess_available_mw,
        turbine_available_mw=_turbine_incremental_available_mw,
        fuel_cell_available_mw=state.fuel_cell_rated_mw,
    )
    _planned_bess_setpoint_mw = _economic_allocations["bess-fleet"]
    _thermal_dispatch_target_mw = (
        _turbine_must_run_mw + _economic_allocations["turbine-fleet"]
    )

    for _ut in _unloading_units:
        _ut_msl_mw = _ut.config.p_min_stable_frac * _ut.config.rated_mw
        apply_loading([_ut], _ut_msl_mw, dt_seconds)
    _p_sync_fleet_mw = max(
        0.0,
        _thermal_dispatch_target_mw
        - _uncontrolled_on_bus_mw
        - _msl_held_mw,
    )
    _sub_msl_surplus_mw: float = apply_loading(
        _truly_sync_units, _p_sync_fleet_mw, dt_seconds
    )

    # Phase E Item 5 — levelled-off predicate and breaker open.
    # `levelled_off` = |output − msl| < levelled_off_tol_mw — a derived predicate,
    # NOT a TurbineState (spec §E.5 prohibition: a state needs an owner, and a second
    # owner of unit output reproduces the dual-writer defect this sequence removed).
    # Output falls continuously to MSL through the loading layer, then steps
    # discontinuously to 0 when the dwell (unload_tail_s) has been sustained.  Do not
    # smooth the discontinuous step — spec §E.5 explicit prohibition.
    #
    # Phase E+ Item 4: sustained predicate — levelled_off_window_s is the threshold
    # after which the panel and the commitment engine agree the unit is settled.
    # Shorter than unload_tail_s (the physical breaker gate).
    _commit_cfg_lo  = getattr(state, '_commit_cfg', None)
    _loff_window_s  = (
        getattr(_commit_cfg_lo, 'levelled_off_window_s', 0.0)
        if _commit_cfg_lo is not None else 0.0
    )
    for _ut in _unloading_units:
        _ut_msl_mw = _ut.config.p_min_stable_frac * _ut.config.rated_mw
        _levelled  = abs(_ut.output_mw() - _ut_msl_mw) < _ut.config.levelled_off_tol_mw
        if _levelled:
            if math.isnan(_ut._levelled_off_since_s):
                _ut._levelled_off_since_s = sim_time   # start dwell clock
            _dwell_elapsed = sim_time - _ut._levelled_off_since_s
            # Sustained predicate: True once dwell ≥ levelled_off_window_s.
            _ut._levelled_off_sustained = _dwell_elapsed >= _loff_window_s
            if _dwell_elapsed >= _ut.config.unload_tail_s:
                # Breaker opens: output steps discontinuously from MSL to 0.
                _ut._levelled_off_sustained = False  # reset before state change
                _ut.state                  = TurbineState.OFFLINE
                _ut._current_output_mw     = 0.0
                _ut._stop_time_s           = sim_time
                _ut._last_sync_stop_s      = sim_time
                _ut._levelled_off_since_s  = math.nan
                state._last_breaker_open_s = sim_time
                _log.info(
                    "Stop sequencing: breaker open for %r at sim_time=%.1f "
                    "(msl_mw=%.3f, dwell=%.1f s)",
                    _ut.config.asset_id, sim_time, _ut_msl_mw, _dwell_elapsed,
                )
        else:
            _ut._levelled_off_since_s   = math.nan  # reset dwell clock while descending
            _ut._levelled_off_sustained = False

    # Phase 11.3: dispatch.tick() now returns a 4-tuple.
    # _bess_setpoint_mw: commanded BESS output before SOC/power clipping.
    # Unpack position 2 (before candidates) — see dispatch.DispatchArbitrator.tick().
    # Phase 13.3: pass the droop-adjusted setpoint so the turbine is staged toward
    # the frequency-corrected target and the BESS covers only the residual shortfall.
    _post_loading_turbine_output_mw = sum(
        t.output_mw() for t in state.turbines if t.is_on_bus
    )
    _reserve_bess_ceilings_mw = [
        max(0.0, physical - normal)
        for physical, normal in zip(
            _bess_physical_ceilings_mw,
            _bess_normal_dispatch_ceilings_mw,
        )
    ]
    # Do not release the retained reserve until normal BESS energy is fully
    # consumed. This is intentionally stricter than a power-based test: in the
    # final normal-dispatch tick, the available normal energy may be less than
    # the BESS MW rating but must be exhausted before any held charge is used.
    _normal_bess_energy_exhausted = _bess_available_mw <= 1e-9
    if _normal_bess_energy_exhausted:
        _grid_emergency_support_mw = (
            0.0
            if _islanded
            else (
                float("inf")
                if state.site.grid_import_limit_mw is None
                else max(0.0, state.site.grid_import_limit_mw)
            )
        )
        # An emergency is an actual residual after every non-BESS source
        # available to this model: online turbine output, fuel-cell nameplate,
        # and PCC import. Only the retained BESS reserve is released for it.
        _emergency_gap_mw = max(
            0.0,
            _p_dispatch_droop_mw
            - _post_loading_turbine_output_mw
            - state.fuel_cell_rated_mw
            - _grid_emergency_support_mw,
        )
        _emergency_bess_target_mw = min(
            _emergency_gap_mw,
            sum(_reserve_bess_ceilings_mw),
        )
    else:
        _emergency_bess_target_mw = 0.0
    if _emergency_bess_target_mw > 0.0:
        _reserve_total_mw = sum(_reserve_bess_ceilings_mw)
        _bess_dispatch_ceilings_mw = [
            normal + _emergency_bess_target_mw * reserve / _reserve_total_mw
            for normal, reserve in zip(
                _bess_normal_dispatch_ceilings_mw,
                _reserve_bess_ceilings_mw,
            )
        ]
    else:
        _bess_dispatch_ceilings_mw = _bess_normal_dispatch_ceilings_mw
    _effective_bess_setpoint_mw = min(
        _planned_bess_setpoint_mw + _emergency_bess_target_mw,
        max(0.0, _p_dispatch_droop_mw - _post_loading_turbine_output_mw),
    )
    turbine_output_mw, bess_output_mw, _bess_setpoint_mw, _arb_candidates = state.arbitrator.tick(
        _p_dispatch_droop_mw,
        dt_seconds,
        bess_dispatch_target_mw=_effective_bess_setpoint_mw,
        bess_dispatch_ceilings_mw=_bess_dispatch_ceilings_mw,
    )

    # Fuel cell is the highest-cost local source in the catalogue.  It therefore
    # fills only the residual left by actual BESS and turbine delivery.  Using
    # measured outputs here also prevents ramp/SoC clipping from breaking the
    # production-consumption identity.
    _fuel_cell_setpoint_mw = min(
        state.fuel_cell_rated_mw,
        max(
            0.0,
            _p_dispatch_droop_mw - turbine_output_mw - bess_output_mw,
        ),
    )
    fuel_cell_output_mw: float = _fuel_cell_setpoint_mw

    # FC CandidateResponse for the §26.4 unified pool (attribution + Step-12 ordering).
    # Position FUEL_CELL_DISPATCH ranks after BESS and turbine, matching the
    # catalogue cost order.  Emitted only when FC dispatches.
    _fc_candidates: list[CandidateResponse] = []
    if fuel_cell_output_mw > 1e-9:
        _fc_candidates.append(CandidateResponse(
            ladder_position=LadderPosition.FUEL_CELL_DISPATCH,
            estimated_impact_mw=fuel_cell_output_mw,
            candidate_id="fuel-cell-fleet",
            response_kind="fuel_cell_dispatch",
            requires_confirmation=False,
        ))

    # ── Phase D Item 5: evaluate_commitment() replaces headroom block ────────
    # Called every tick so commit/decommit hysteresis timers accumulate.
    # Reserve floor (always binding):
    #   Σ rated(on_bus) ≥ P_dispatch_required + max(rated(on_bus))
    # Violation is an immediate commit trigger regardless of utilisation.
    #
    # PROHIBITED: the pending unit (STARTING) must NOT be included in on_bus
    # or offline — it is not on the bus and must not be counted toward capacity,
    # reserve, ramp, or headroom figures.

    # ── Stale-register recovery ───────────────────────────────────────────
    # command_start() can silently drop a start command (hot_standby guard,
    # wrong state, min-down-time not elapsed) while leaving no external signal.
    # If that happens, record_start() was already called → pending_unit_id is
    # set, but the unit never reaches STARTING → clear_on_synchronised() never
    # fires → the register is stuck for the rest of the run, blocking all
    # future turbine commits permanently.
    #
    # Recovery: if the pending unit is back in OFFLINE (not STARTING and not
    # on bus), the start did not take — clear the register so the engine can
    # retry on the next commit tick.
    if not state._pending_start.is_empty:
        for _stale_t in state.turbines:
            if _stale_t.config.asset_id == state._pending_start.pending_unit_id:
                if _stale_t.state == TurbineState.OFFLINE:
                    _log.warning(
                        "Commitment engine: clearing stale pending-start register "
                        "for %r at sim_time=%.1f — unit is OFFLINE, start did not take",
                        state._pending_start.pending_unit_id, sim_time,
                    )
                    state._pending_start.pending_unit_id = None
                    state._pending_start.start_commanded_at_s = math.nan
                break

    _avail_on_bus = [t.unit_availability() for t in state.turbines if t.is_on_bus]
    _avail_offline = [
        t.unit_availability()
        for t in _offline_turbines_by_thermal_priority(state.turbines)
        if not t.config.hot_standby
    ]

    # ── Fuel-cell saturation turbine commit ───────────────────────────────
    # A rising crossing of the configured fraction emits one signal.  The
    # signal remains pending while another unit is STARTING, then is consumed
    # only after exactly one turbine accepts command_start().  Remaining high
    # output cannot start further turbines until output first falls below the
    # threshold and crosses upward again.
    _fc_commit_override: Optional[CommitmentDecision] = None
    _fc_commit_started = False
    _fc_commit_fraction = state.site.fuel_cell_turbine_commit_fraction
    if (
        _fc_commit_fraction is not None
        and state.fuel_cell_rated_mw > 0.0
        and state.turbines
    ):
        _fc_commit_threshold_mw = _fc_commit_fraction * state.fuel_cell_rated_mw
        _fc_commit_above = (
            fuel_cell_output_mw + 1e-9 >= _fc_commit_threshold_mw
        )
        _fc_commit_crossing = (
            _fc_commit_above
            and not state._fuel_cell_commit_threshold_above
        )
        state._fuel_cell_commit_threshold_above = _fc_commit_above

        if (
            _fc_commit_crossing
            and _offline_turbines_by_thermal_priority(state.turbines)
        ):
            state._fuel_cell_commit_signal_pending = True
            _log.info(
                "Fuel-cell turbine commit signal: %.2f MW >= %.2f MW "
                "(%.0f%% of %.2f MW) at sim_time=%.1f",
                fuel_cell_output_mw,
                _fc_commit_threshold_mw,
                _fc_commit_fraction * 100.0,
                state.fuel_cell_rated_mw,
                sim_time,
            )

        if state._fuel_cell_commit_signal_pending:
            _fc_turbine_candidates = _offline_turbines_by_thermal_priority(
                state.turbines
            )
            if not state._pending_start.is_empty:
                _fc_commit_override = CommitmentDecision(
                    action="hold",
                    target_unit_id=None,
                    reason=(
                        "fuel-cell output crossed "
                        f"{_fc_commit_fraction:.0%} capacity; turbine commit pending"
                    ),
                    blocked_by=(
                        f"start pending for {state._pending_start.pending_unit_id!r}"
                    ),
                )
            elif _fc_turbine_candidates:
                _fc_target = _fc_turbine_candidates[0]
                _was_hot_standby = _fc_target.config.hot_standby
                if _was_hot_standby:
                    # OFFLINE standby units reject command_start() while this
                    # flag is set.  Release the selected unit before starting.
                    _fc_target.config.hot_standby = False
                _fc_target.command_start(sim_time)
                if _fc_target.state == TurbineState.STARTING:
                    state._pending_start.record_start(
                        _fc_target.config.asset_id,
                        sim_time,
                    )
                    state._fuel_cell_commit_signal_pending = False
                    _promotion_changes = _promote_reserve_standby_labels(
                        state.turbines
                    )
                    _promotion_text = (
                        "; reserve promotions=" + ", ".join(_promotion_changes)
                        if _promotion_changes
                        else "; reserve promotions=none"
                    )
                    _fc_commit_override = CommitmentDecision(
                        action="commit",
                        target_unit_id=_fc_target.config.asset_id,
                        reason=(
                            f"fuel-cell output {fuel_cell_output_mw:.2f} MW reached "
                            f"{_fc_commit_fraction:.0%} of "
                            f"{state.fuel_cell_rated_mw:.2f} MW; selected "
                            f"{_fc_target.thermal_state.value} standby"
                            f"{_promotion_text}"
                        ),
                    )
                    _fc_commit_started = True
                    _log.info(
                        "Fuel-cell turbine commit: start %r (%s) at sim_time=%.1f%s",
                        _fc_target.config.asset_id,
                        _fc_target.thermal_state.value,
                        sim_time,
                        _promotion_text,
                    )
                else:
                    if _was_hot_standby:
                        _fc_target.config.hot_standby = True
                    _fc_commit_override = CommitmentDecision(
                        action="hold",
                        target_unit_id=_fc_target.config.asset_id,
                        reason=(
                            "fuel-cell output crossed "
                            f"{_fc_commit_fraction:.0%} capacity"
                        ),
                        blocked_by="selected turbine start was deferred by unit guards",
                    )
            else:
                # No remaining offline unit can consume this crossing.
                state._fuel_cell_commit_signal_pending = False
    else:
        state._fuel_cell_commit_threshold_above = False
        state._fuel_cell_commit_signal_pending = False

    if _fc_commit_started:
        _avail_offline = [
            t.unit_availability()
            for t in _offline_turbines_by_thermal_priority(state.turbines)
            if not t.config.hot_standby
        ]

    # ── Cascade commit trigger (site.cascade_commit_fraction) ─────────────
    # When set, the commitment engine triggers the next standby turbine when
    # the LAST on-bus active (non-hot-standby) turbine's output reaches
    # cascade_commit_fraction × its own rated MW.
    #
    # Hot-standby turbines are a special case: they are already SYNCHRONISED
    # (not OFFLINE), so they CANNOT go through command_start() or appear in
    # _avail_offline.  Instead, clearing config.hot_standby = False on the
    # next unit immediately makes it is_on_bus=True and dispatchable.
    # After release its output is 0 MW → cascade threshold won't refire until
    # it ramps to cascade_commit_fraction × its rated MW, giving a natural
    # step-through: turbine-1 commits turbine-2, turbine-2 commits turbine-3.
    #
    # OFFLINE standby units still flow through force_commit_trigger → evaluate_commitment.
    _cascade_trigger = False
    _cascade_frac = getattr(state.site, "cascade_commit_fraction", None)
    if _cascade_frac is not None:
        _active_on_bus = [t for t in state.turbines if t.is_on_bus and not t.config.hot_standby]
        if _active_on_bus:
            _lead_turbine = _active_on_bus[-1]  # last committed active unit
            _threshold_mw = _cascade_frac * _lead_turbine.config.rated_mw
            if _lead_turbine.output_mw() >= _threshold_mw:
                # ── Hot-standby path ────────────────────────────────────────────
                # Hot-standby turbines sit in OFFLINE state (not SYNCHRONISED) —
                # the hot_standby flag is what suppresses is_on_bus and blocks
                # command_start().  Fix: clear the flag, THEN call command_start()
                # (the guard is gone so it transitions OFFLINE → STARTING normally,
                # using initial_thermal_state="hot" → hot_start_s duration).
                _hs_units = [
                    t
                    for t in _offline_turbines_by_thermal_priority(state.turbines)
                    if t.config.hot_standby
                ]
                if _hs_units and state._pending_start.is_empty:
                    _next_hs = _hs_units[0]
                    _next_hs.config.hot_standby = False  # TurbineConfig is non-frozen
                    _next_hs.command_start(sim_time)      # now accepted — guard cleared
                    if _next_hs.state == TurbineState.STARTING:
                        state._pending_start.record_start(_next_hs.config.asset_id, sim_time)
                        _cascade_promotions = _promote_reserve_standby_labels(
                            state.turbines
                        )
                        _cascade_promotion_text = (
                            "; reserve promotions=" + ", ".join(_cascade_promotions)
                            if _cascade_promotions
                            else "; reserve promotions=none"
                        )
                        _log.info(
                            "Cascade commit: released hot-standby %r → STARTING at "
                            "sim_time=%.1f (lead %r %.2f MW ≥ %.2f MW threshold)%s",
                            _next_hs.config.asset_id, sim_time,
                            _lead_turbine.config.asset_id,
                            _lead_turbine.output_mw(),
                            _threshold_mw,
                            _cascade_promotion_text,
                        )
                    else:
                        _next_hs.config.hot_standby = True
                else:
                    # ── OFFLINE (non-hot-standby) units: via evaluate_commitment ──
                    _cascade_trigger = bool(_avail_offline)

    _commit_decision: CommitmentDecision = evaluate_commitment(
        on_bus               = _avail_on_bus,
        offline              = _avail_offline,
        p_demand_mw          = _thermal_dispatch_target_mw,
        pending              = state._pending_start,
        commit_cond          = state._commit_cond,
        decommit_cond        = state._decommit_cond,
        cfg                  = state._commit_cfg,
        dt_s                 = dt_seconds,
        sim_time             = sim_time,
        force_commit_trigger = _cascade_trigger,
    )
    if (
        not _fc_commit_started
        and _commit_decision.action == "commit"
        and _commit_decision.target_unit_id is not None
    ):
        for _cht in state.turbines:
            if _cht.config.asset_id == _commit_decision.target_unit_id:
                _cht.command_start(sim_time)
                # Only record the pending start when command_start() actually
                # transitioned the unit to STARTING.  command_start() can
                # silently drop (hot_standby guard, min-down-time, wrong state)
                # without changing state.  Calling record_start() when the
                # unit stayed OFFLINE would set pending_unit_id permanently —
                # clear_on_synchronised() never fires → all future commits
                # blocked for the rest of the run.
                if _cht.state == TurbineState.STARTING:
                    state._pending_start.record_start(_cht.config.asset_id, sim_time)
                    _log.info(
                        "Commitment engine: start %r at sim_time=%.1f (%s)",
                        _cht.config.asset_id,
                        sim_time,
                        _commit_decision.reason,
                    )
                else:
                    _log.warning(
                        "Commitment engine: start %r silently dropped by "
                        "command_start() at sim_time=%.1f (state=%s) — "
                        "pending register NOT set; engine will retry next tick",
                        _cht.config.asset_id, sim_time, _cht.state.name,
                    )
                break
    elif (
        not _fc_commit_started
        and _commit_decision.action == "decommit"
        and _commit_decision.target_unit_id is not None
    ):
        # Phase E Item 6: sequential-stop guard — at most one UNLOADING at a time,
        # plus settling interval after last breaker open (symmetric to Phase D D-05).
        # A new decommit is blocked when:
        #   (a) any unit is already in UNLOADING, OR
        #   (b) the last breaker opened less than unload_tail_s seconds ago.
        _n_unloading = sum(1 for _tu in state.turbines if _tu.state == TurbineState.UNLOADING)
        _settle_s = max(
            (_tu.config.unload_tail_s for _tu in state.turbines), default=60.0
        )
        _settle_ok = (
            math.isnan(state._last_breaker_open_s)
            or (sim_time - state._last_breaker_open_s) >= _settle_s
        )
        if _n_unloading == 0 and _settle_ok:
            for _cht in state.turbines:
                if _cht.config.asset_id == _commit_decision.target_unit_id:
                    try:
                        # Phase E closeout Item 3: command_stop() now returns
                        # Optional[str] — None = accepted, str = block reason.
                        _stop_block: Optional[str] = _cht.command_stop(sim_time)
                    except (RuntimeError, AttributeError):
                        _stop_block = None  # state changed between snapshot and call
                    if _stop_block is None:
                        _log.info(
                            "Commitment engine: stop %r at sim_time=%.1f (%s)",
                            _cht.config.asset_id, sim_time, _commit_decision.reason,
                        )
                    else:
                        # R5 guard deferred the stop — thread the reason into
                        # blocked_by so the fleet modal and run log surface it.
                        _commit_decision = CommitmentDecision(
                            action="hold",
                            target_unit_id=_commit_decision.target_unit_id,
                            reason=_commit_decision.reason,
                            blocked_by=_stop_block,
                            floor_mw=_commit_decision.floor_mw,
                            floor_violated=_commit_decision.floor_violated,
                        )
                        _log.debug(
                            "R5 guard: decommit of %r deferred at sim_time=%.1f: %s",
                            _cht.config.asset_id, sim_time, _stop_block,
                        )
                    break
        else:
            _log.debug(
                "Decommit of %r deferred: n_unloading=%d settle_ok=%s (sim_time=%.1f)",
                _commit_decision.target_unit_id, _n_unloading, _settle_ok, sim_time,
            )

    if _fc_commit_override is not None:
        # Preserve reserve-floor diagnostics computed by evaluate_commitment()
        # while replacing only the operator-facing action/selection evidence.
        _commit_decision = CommitmentDecision(
            action=_fc_commit_override.action,
            target_unit_id=_fc_commit_override.target_unit_id,
            reason=_fc_commit_override.reason,
            blocked_by=_fc_commit_override.blocked_by,
            floor_mw=_commit_decision.floor_mw,
            floor_violated=_commit_decision.floor_violated,
        )

    # ── GS-DEF-CMT-001 Phase A diagnostic — logging only, no behavior change ─
    # Writes every tick from t=0 to t=1400 s to /tmp/cmt001_diag.log.
    # Remove after Phase A review.
    if sim_time <= 1400.0:
        _cmt_on_bus_rated = [u.rated_mw for u in _avail_on_bus if not u.hot_standby]
        _cmt_total_rated  = sum(_cmt_on_bus_rated)
        _cmt_largest      = max(_cmt_on_bus_rated, default=0.0)
        _cmt_U            = (_thermal_dispatch_target_mw / _cmt_total_rated
                             if _cmt_total_rated > 0.0 else 0.0)
        _cmt_floor_deficit = _commit_decision.floor_mw - _cmt_total_rated
        _cmt_bess_soc_pct  = (state.bess_units[0].soc_fraction * 100.0
                               if state.bess_units else float("nan"))
        _cmt_bess_anchor   = (state.bess_units[0].config.p_anchor_reserve_mw
                               if state.bess_units else 0.0)
        _cmt_t_states = {t.config.asset_id: t.state.name for t in state.turbines}
        _cmt_line = (
            f"CMT001 "
            f"t={sim_time:.1f} commit_raised={_commit_decision.action == 'commit'} action={_commit_decision.action!r} "
            f"U={_cmt_U:.4f} p_demand_mw={_thermal_dispatch_target_mw:.3f} total_rated_mw={_cmt_total_rated:.3f} largest_mw={_cmt_largest:.3f} "
            f"floor_mw={_commit_decision.floor_mw:.3f} floor_violated={_commit_decision.floor_violated} floor_deficit={_cmt_floor_deficit:.3f} "
            f"commit_sustained_s={state._commit_cond.sustained_s:.1f} commit_confirm_s={state._commit_cfg.commit_confirm_s} "
            f"pending_id={state._pending_start.pending_unit_id!r} pending_since={state._pending_start.start_commanded_at_s:.1f} "
            f"turbine_states={_cmt_t_states} "
            f"p_total={p_demand_mw:.3f} p_renewable={p_renewable_mw:.3f} p_dispatch_req={p_dispatch_required_mw:.3f} "
            f"bess_soc_pct={_cmt_bess_soc_pct:.2f} bess_output_mw={bess_output_mw:.3f} bess_anchor_mw={_cmt_bess_anchor:.3f} "
            f"turbine_output_mw={turbine_output_mw:.3f} blocked_by={_commit_decision.blocked_by!r}\n"
        )
        with open("/tmp/cmt001_diag.log", "a") as _cmt_f:
            _cmt_f.write(_cmt_line)

    # Phase E+: commitment engine summary — serialised for the fleet modal.
    # Computed AFTER _commit_decision is finalised so that an R5-guard hold
    # override is reflected correctly in the action field.
    #
    # Item 2: committed_rated_mw counts SYNCHRONISED only (contributes_to_reserve).
    # UNLOADING units are pinned at MSL with no upward headroom — counting their
    # nameplate overstates reserve precisely when the fleet is shrinking.
    # Distinct from on_bus_output_mw which INCLUDES UNLOADING (they do produce).
    _avail_reserve        = [t.unit_availability() for t in state.turbines if t.contributes_to_reserve]
    _committed_rated_mw_cs = sum(u.rated_mw for u in _avail_reserve)
    _fleet_utilisation_cs = (
        _thermal_dispatch_target_mw / _committed_rated_mw_cs
        if _committed_rated_mw_cs > 0.0 else 0.0
    )
    # Item 1: reserve_floor_mw and reserve_satisfied from CommitmentDecision — one source.
    # CommitmentDecision.floor_mw = p_demand + max(rated_on_bus) — the correct N-1 quantity.
    # The previous code recomputed decommit_utilisation × total_rated, which is the
    # decommit threshold under a different name and inverts the satisfied predicate.
    _reserve_floor_mw_cs   = _commit_decision.floor_mw
    _reserve_satisfied_cs  = not _commit_decision.floor_violated
    _pending_start_id_cs   = getattr(getattr(state, '_pending_start', None), 'pending_unit_id', None)

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

    # Scenario-scripted DQ inject events: any active window makes this tick
    # low-confidence regardless of real hardware/calibration state.
    _dq_injected = any(
        s <= sim_time < e
        for s, e, _ in state.site.dq_inject_events
    )
    _is_low_confidence = (
        any(g.has_active_unmapped_jobs() for g in state.gpu_modules)
        or state.site.uncalibrated
        # Phase 11.2: absent feed is structurally equivalent to unmapped hardware
        # for the purposes of the curtailment interlock (TC-43 pattern).
        or _workload_signal_absent
        # Scripted inject windows (demo / scenario testing).
        or _dq_injected
    )
    # Remaining gap passed to the curtailment ladder must account for ALL
    # dispatched sources — including the fuel cell.  Omitting fuel_cell_output_mw
    # here caused the ladder to see a false gap equal to the FC's contribution,
    # potentially triggering curtailment of GPU nodes that FC was already serving.
    _remaining_gap_mw = max(
        0.0, p_dispatch_required_mw - turbine_output_mw - bess_output_mw - fuel_cell_output_mw
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

    # K1 unified pool: storage + fuel cell + turbine (dispatched) + curtailment (proposed).
    # FC candidates sit at FUEL_CELL_DISPATCH (position 2), after storage (0) and
    # turbine ramp (1), so select_candidates() reflects the operating source order
    # before ever reaching curtailment.
    # select_candidates() sorts by total order (position ASC, impact DESC, id ASC)
    # and greedily selects until the gap is covered — TC-49 live path.
    _unified_pool: list[CandidateResponse] = _arb_candidates + _fc_candidates + _curtailment_candidates
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

    # §6.2 / kube_demand power-cap tier: when the Kube admission gate is
    # holding new jobs due to low grid headroom, surface "b_power_cap" in the
    # curtailment_proposal_tiers tuple so the operator UI can show the active
    # curtailment tier without duplicating the logic from kube_demand.py.
    # This is tier B in the A→B→C→D ladder (defer→power-cap→suspend→shed).
    # Only injected when power_cap_active=True to avoid polluting the tiers
    # list on normal ticks where the Kube gate is not engaged.
    if (
        _kube_metrics is not None
        and _kube_metrics.power_cap_active
        and "b_power_cap" not in _curtailment_proposal_tiers
    ):
        _curtailment_proposal_tiers = _curtailment_proposal_tiers + ("b_power_cap",)

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
                # Phase C Item 4 (simulation_core contingency snapshot): is_on_bus —
                # an unloading unit is still breaker-closed and can trip; it must
                # be included in the N-1 computation.
                is_synchronized=t.is_on_bus,
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
        fuel_cell_snapshots=(
            (FuelCellSnapshot(rated_mw=state.fuel_cell_rated_mw),)
            if state.fuel_cell_rated_mw > 0.0 else ()
        ),
        island_mode=state.site.island_mode,
        curtailable_capacity_mw=state.curtailment_ladder.total_capacity_mw(),
        renewable_mw=p_renewable_mw,
    )
    _contingency_coverage = evaluate_contingency(_plant_state)

    # 4b. Annotate contingency coverage with an approximate node count for shed_required_mw.
    # Converts the MW figure into "≈ N nodes" so the UI can show both without the frontend
    # needing to know the per-node power density.
    _shed_equiv_nodes: Optional[int] = None
    if _contingency_coverage.shed_required_mw > 0 and state.gpu_modules:
        _total_active_nodes = sum(g.effective_node_count() for g in state.gpu_modules)
        _p_compute_total = sum(
            g.per_job_compute_mw(j)
            for g in state.gpu_modules
            for j in g.active_training_jobs()
        )
        if _total_active_nodes > 0 and _p_compute_total > 0.01:
            _shed_equiv_nodes = max(1, round(
                _contingency_coverage.shed_required_mw / _p_compute_total * _total_active_nodes
            ))
    _contingency_coverage = dataclasses.replace(
        _contingency_coverage, shed_equivalent_nodes=_shed_equiv_nodes
    )

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
    # Scenario-scripted DQ inject windows — add named tags for any active window.
    for _inj_start, _inj_end, _inj_tag_str in state.site.dq_inject_events:
        if _inj_start <= sim_time < _inj_end:
            try:
                tags.add(DataQualityTag(_inj_tag_str))
            except ValueError:
                _log.warning(
                    "dq_inject_events: unknown tag %r at sim_time=%.1f — skipped.",
                    _inj_tag_str, sim_time,
                )

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
        max(forecast_mw, p_demand_mw)
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
        # BUG FIX: only count turbines that are currently on-bus (SYNCHRONISED or
        # UNLOADING).  The previous formula summed ALL turbines' rated_mw, including
        # units that are OFFLINE, STARTING, or HOT_STANDBY — none of which can
        # deliver power right now.  That inflated headroom let the kube scheduler
        # admit workloads far beyond available generation (e.g. 5 × 12 MW = 60 MW
        # rated when only 1 turbine at 15 MW is on bus → reported headroom 45 MW
        # while actual spare capacity was 0 MW).  Units that are staging but not yet
        # synchronised are accounted for via _pending_ramp_credit_mw in the staging
        # path, so they must not also appear here.
        _k_turbine_rated = sum(
            t.config.rated_mw for t in state.turbines if t.is_on_bus
        )
        _k_bess_rated    = sum(b.config.rated_mw for b in state.bess_units)
        state._kube_grid_state = KubeGridState(
            p_dispatch_required_mw=net_demand_mw,
            bess_soc_fraction=(
                state.bess_units[0].soc_fraction if state.bess_units else 1.0
            ),
            turbine_headroom_mw=max(0.0, _k_turbine_rated - turbine_output_mw),
            bess_headroom_mw=max(0.0, _k_bess_rated - bess_output_mw),
            # IMPL-FC-HEADROOM-001: include idle FC capacity in the headroom
            # signal so the kube admission gate is not blind to available FC MW.
            # Mirrors BESS treatment exactly: rated − current_output, floored at 0.
            # fuel_cell_rated_mw is 0.0 when no FC is configured — safe unconditionally.
            fuel_cell_headroom_mw=max(
                0.0, state.fuel_cell_rated_mw - fuel_cell_output_mw
            ),
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
    _p_gen_mw = turbine_output_mw + bess_output_mw + fuel_cell_output_mw + p_renewable_mw
    _balance_residual_mw = _p_gen_mw - p_demand_mw

    # ── Phase 13.2: balance decomposition — three independent channels ────────
    #
    # _p_commanded_mw: what the dispatch logic ASKED all dispatchable + renewable
    # assets to produce this tick — three independently modelled sources:
    #   gt_setpoint = _thermal_dispatch_target_mw  (turbine fleet residual)
    #   bess_setpoint = _bess_setpoint_mw   (BESS fleet, from arbitrator)
    #   renewable = p_renewable_mw          (solar + wind, from solar arrays)
    # The FC receives the preferred portion of the droop-adjusted demand and the
    # thermal fleet receives only the remainder.  Together they preserve the
    # previous total-command identity.
    _p_commanded_mw = (
        _thermal_dispatch_target_mw
        + _bess_setpoint_mw
        + _fuel_cell_setpoint_mw
        + p_renewable_mw
    )

    # Phase 13.2 + Task #200 B1/B2 — two-channel energy identity, one reporting field.
    #
    # D1: islanded → grid_exchange_mw = 0.0 exactly (PCC open).
    # D2: grid-connected with an unconstrained PCC → frequency_forcing_mw = 0.0
    #     exactly (grid holds f).  When grid_import_limit_mw is configured and
    #     saturated, the excess deficit remains on frequency_forcing_mw so D4
    #     continues to expose the unserved power rather than inventing grid import.
    # D4: grid_exchange + frequency_forcing = balance_residual.
    #     Two channels only; holds in BOTH modes without any conditional or RHS term.
    # D5: asset_delivery_error_mw is NOT a term in D4.  Computed independently
    #     from setpoints + actuals; same formula in both modes.
    #
    # Energy routing (B1):
    #   Islanded:       balance_residual = p_gen − p_load routes to rotors → frequency.
    #                   frequency_forcing_mw = balance_residual (actual supply-demand,
    #                   not the commanded approximation).  Sub-MSL surplus is implicit:
    #                   turb_out > droop means p_gen is higher → balance_residual is
    #                   higher → stronger overfrequency.  No separate sub_msl term needed.
    #   Grid-connected: balance_residual routes to PCC (import/export).
    #                   grid_exchange_mw = balance_residual.
    #
    # Reporting (B2):
    #   asset_delivery_error_mw = (turb_out − droop) + (bess_out − bess_sp).
    #   Mode-independent: reports commanded ≠ delivered regardless of cause —
    #   floor constraint, actuator lag, hardware fault.  Not in D4.
    #   A unit at its MSL floor (turb_out = 2.8 MW, droop = 2.0 MW) reports
    #   +0.8 MW in BOTH islanded and grid-connected modes.
    #
    # D4 algebra:
    #   Islanded:       0 + balance_residual = balance_residual  ✓ (trivially)
    #   Grid-connected: balance_residual + 0 = balance_residual  ✓ (trivially)
    #
    # §13.2 spec note (B3):
    #   asset_delivery_error_mw was originally defined as an energy channel in D4
    #   (three-channel identity: grid + forcing + delivery_error = balance_residual).
    #   This is a deliberate re-scope: it is now a reporting field outside D4.
    #   The §13.2 spec document needs an edit to reflect two-channel D4 and the
    #   mode-independent delivery_error definition — reported, not edited here.
    # Gate the turbine setpoint used in delivery-error on SYNCHRONISED.
    # _thermal_dispatch_target_mw is the turbine fleet's residual demand.  When no SYNCHRONISED
    # turbines exist (e.g. all units OFFLINE or STARTING), the demand is
    # fully absorbed by the BESS shortfall path: bess_setpoint ≈ residual and
    # bess_output ≈ bess_setpoint.  Attributing _p_dispatch_droop_mw as the
    # turbine setpoint would inject a spurious delivery error equal to −demand
    # even when the BESS has covered load perfectly.
    #
    # The gating criterion: _committed_rated_mw_cs > 0 ↔ at least one
    # SYNCHRONISED turbine has headroom and can act on the setpoint.
    _turb_setpoint_for_error_mw = (
        _thermal_dispatch_target_mw if _committed_rated_mw_cs > 0.0 else 0.0
    )
    _asset_delivery_error_mw = (           # reporting only — NOT a D4 term
        (turbine_output_mw - _turb_setpoint_for_error_mw)
        + (bess_output_mw  - _bess_setpoint_mw)
    )
    if _islanded:
        _grid_exchange_mw     = 0.0                    # PCC open (D1)
        _frequency_forcing_mw = _balance_residual_mw   # actual supply-demand → rotors
    else:
        _grid_import_limit_mw = state.site.grid_import_limit_mw
        if _grid_import_limit_mw is None:
            _grid_exchange_mw     = _balance_residual_mw
            _frequency_forcing_mw = 0.0                # unlimited grid holds frequency (D2)
        else:
            # Negative grid_exchange_mw means import.  Clamp only that direction;
            # positive export remains unconstrained.  Any deficit beyond the PCC
            # ceiling stays visible in the second D4 energy channel.
            _grid_exchange_mw = max(
                _balance_residual_mw,
                -max(0.0, _grid_import_limit_mw),
            )
            _frequency_forcing_mw = _balance_residual_mw - _grid_exchange_mw

    # GS-CHG-2026-08-08 successor Phase 1 — P_generation aggregate producer.
    # ONE computation site; the serialiser must NOT sum these components again (Spec 19 / TC-92).
    # _p_gen_mw = turbine + BESS + solar (already computed at line ~1291).
    # Grid import: _grid_exchange_mw < 0 in grid-connected when local gen < demand;
    #   -_grid_exchange_mw > 0 gives the MW drawn from the PCC.  In islanded mode
    #   _grid_exchange_mw = 0 always (D1), so max(0, -0) = 0 and this is a no-op.
    _p_generation_mw = _p_gen_mw + max(0.0, -_grid_exchange_mw)

    # Phase 1b (Task #198 item 3): ramp capability over the dispatch arbitrator's
    # runtime lead time — same horizon used for staging and BESS bridging.
    # No separate LEAD_WINDOW_S constant; one source of truth.
    _ramp_capability_mw = ramp_capability(dt_lead_next_s, state.turbines)

    # ── Phase 3+4+5: Sub-stepped swing equation, bounded governor, UFLS/81U ────
    # Replaces the single-step swing equation from Phase 13.3.
    #
    # Sub-step dt = site.dynamic_step_s (0.01 s, DR-2026-08-08-FREQ).
    # n_sub = round(dt_seconds / dynamic_step_s) = 500 sub-steps per 5 s outer tick.
    # Assertion: dynamic_step_s ≤ min(relay_81u_delay_s, ufls_delay_s) / 10 = 0.01 s.
    #
    # §REPORT-2C (deleted branch): The old frozen-frequency branch
    # "if GF-BESS and zero machines: df/dt=0, freeze frequency" has been removed
    # (Phase 2C). The frozen-frequency model treated GF-BESS as an infinite bus
    # with no virtual inertia, preventing any frequency dynamics during the zero-
    # machine phase. Phase 2C replaces it with VSM physics (H_vsm=2.0 s PROVISIONAL).
    #
    # §REPORT-5A (defect retained): island_collapse_hz (IEEE 1547 Cat I, 57.0 Hz)
    # is a grid-connected DER interconnection threshold. It is currently applied
    # inside the islanded block — a defect. Phase 5 adds the correct islanded 81U
    # relay at relay_81u_threshold_hz (57.5 Hz, PROVISIONAL-UNMEASURED). The 81U
    # fires at a less-conservative threshold with a delay; for rapidly falling
    # frequency, island_collapse_hz fires first. Backward compat: retained.
    _island_collapsed_this_tick: bool = False
    _fp_collapse_reason: Optional[str] = None
    _fp_collapse_frequency_hz: Optional[float] = None
    # Phase 2A: protection_provisional — True for every islanded tick.
    # D_eff uses d_motor + fixed_speed_cooling_fraction (both PROVISIONAL-UNMEASURED).
    _protection_provisional: bool = _islanded

    if _islanded:
        _f0 = state.site.frequency_nominal_hz

        # Phase 3 assertion: sub-step ≤ shortest_protection_delay / 10.
        # Shortest delay = min(relay_81u_delay_s, min UFLS stage delay_s).
        _shortest_delay_s = min(
            state.site.relay_81u_delay_s,
            min((s["delay_s"] for s in state.site.ufls_stages), default=float("inf")),
        )
        assert state.site.dynamic_step_s <= _shortest_delay_s / 10.0, (
            f"dynamic_step_s={state.site.dynamic_step_s} s violates "
            f"dynamic_step_s ≤ shortest_protection_delay/10 = "
            f"{_shortest_delay_s / 10.0} s (§DR-2026-08-08-FREQ Phase 3)"
        )

        _dt_sub = state.site.dynamic_step_s
        _n_sub  = max(1, round(dt_seconds / _dt_sub))
        _dt_sub = dt_seconds / _n_sub  # actual sub-step (may differ by float rounding)

        # Phase 3: Load damping D_eff (dimensionless, pu/pu).
        # Only fixed-speed motors damp frequency; VFD loads and IT loads do NOT.
        # D_eff ≈ 0.13 at typical 0.45 × 0.30 × 2.5 = 0.3375 MW/MW cooling fraction.
        _d_eff: float = 0.0
        if p_demand_mw > 1e-9:
            _d_eff = (
                (p_cooling_demand_mw / p_demand_mw)
                * state.site.fixed_speed_cooling_fraction
                * state.site.d_motor
            )

        # Shed accumulated within this outer tick's sub-steps (affects swing eq).
        _shed_this_tick_mw: float = 0.0

        _f = state._frequency_hz  # working frequency across sub-steps

        for _k in range(_n_sub):
            _f_dev = _f - _f0

            # Phase 3: Swing equation sub-step.
            # 2·H_agg/f0 · df/dt = P_net/S_base − D_eff·(f−f0)/f0
            # => df/dt = [P_net_pu·f0 − D_eff·f_dev] / (2·H_agg)
            #
            # Forcing: _frequency_forcing_mw is the outer-tick balance residual
            # (constant within the sub-step loop). This is the dispatch-plan
            # imbalance that drives rotating inertia.
            #
            # Governor feedback (Phase 4) runs SEPARATELY below and advances the
            # governor state using the instantaneous frequency deviation. The
            # governor terminal state (_gov_power_mw) is used as the NEXT outer
            # tick's dispatch correction (outer droop), NOT as a within-tick
            # feedback to the swing equation. This one-outer-tick delay correctly
            # models the governor's role: it adjusts the NEXT dispatch setpoint,
            # not the current tick's balance residual.
            #
            # Within-tick shed from UFLS is added to the forcing since shed
            # reduces the effective load immediately (sub-step granularity).
            if _s_base_mva > 0.0 and _h_aggregate > 0.0:
                _p_net_pu = (
                    (_frequency_forcing_mw + _shed_this_tick_mw)
                    / _s_base_mva
                )
                _df_dt_sub = (
                    _p_net_pu * _f0 - _d_eff * _f_dev
                ) / (2.0 * _h_aggregate)
                _f += _df_dt_sub * _dt_sub
            # If _s_base_mva==0 or _h_aggregate==0: degenerate; f unchanged.

            # Phase 4: Advance per-unit bounded governor cascade (valve lag → fuel lag).
            # Governor reads the instantaneous frequency deviation and advances its
            # cascade state. The terminal _gov_power_mw is used by the NEXT outer
            # tick's dispatch correction (outer droop formula). This is a one-outer-tick
            # delay, which is the correct model for governor response to frequency events.
            # Not added to the swing equation forcing within this tick.
            for _t in _on_bus_turbines:
                _s_i = _t.config.rated_mw / _t.config.power_factor  # MVA base for this unit
                # Governor demand: droop signal in MW (positive = more output needed).
                _gov_target = (
                    (-_f_dev / (_t.config.droop_r * _f0)) * _s_i
                    if abs(_f_dev) > _GOVERNOR_DEADBAND_HZ and _t.config.droop_r > 0.0
                    else 0.0
                )
                # Valve first-order lag.
                _alpha_v = 1.0 - math.exp(-_dt_sub / _t.config.valve_actuation_tc_s)
                _new_valve = _t._gov_valve_mw + (_gov_target - _t._gov_valve_mw) * _alpha_v
                # Fuel/power first-order lag.
                _alpha_f = 1.0 - math.exp(-_dt_sub / _t.config.fuel_to_power_tc_s)
                _new_power = _t._gov_power_mw + (_new_valve - _t._gov_power_mw) * _alpha_f
                # Rate limiter: max_instantaneous_load_step_mw per sub-step.
                _step = _new_power - _t._gov_power_mw
                if abs(_step) > _t.config.max_instantaneous_load_step_mw:
                    _new_power = _t._gov_power_mw + math.copysign(
                        _t.config.max_instantaneous_load_step_mw, _step
                    )
                _t._gov_valve_mw = _new_valve
                _t._gov_power_mw = _new_power

            # Phase 5: UFLS staged protection (PROVISIONAL-UNMEASURED thresholds).
            # Guard: like the 81U relay, UFLS thresholds are calibrated for 60 Hz
            # systems. A 59.3 Hz threshold is meaningless for a 50 Hz system (50 Hz
            # nominal is already below 59.3 Hz — the relay would fire immediately).
            # Only fire when threshold_hz < frequency_nominal_hz.
            # Timer resets if f recovers above threshold before stage fires.
            for _j, _stage in enumerate(state.site.ufls_stages):
                if state._ufls_fired[_j]:
                    continue  # already shed; skip
                if _stage["threshold_hz"] >= _f0:
                    continue  # threshold above nominal: not calibrated for this system
                if _f <= _stage["threshold_hz"]:
                    state._ufls_timer_s[_j] += _dt_sub
                    if state._ufls_timer_s[_j] >= _stage["delay_s"]:
                        _shed_block = _stage["block_fraction"] * p_demand_mw
                        state._cumulative_shed_mw += _shed_block
                        _shed_this_tick_mw += _shed_block
                        state._ufls_fired[_j] = True
                        _log.warning(
                            "§UFLS Stage %d fired: f=%.3f Hz ≤ %.3f Hz, tick %d, "
                            "shed=%.2f MW (%.0f%% of %.2f MW demand). PROVISIONAL thresholds.",
                            _j, _f, _stage["threshold_hz"], state.tick_index,
                            _shed_block, _stage["block_fraction"] * 100, p_demand_mw,
                        )
                else:
                    state._ufls_timer_s[_j] = 0.0  # recovered; reset timer

            # Phase 5: 81U islanded UF relay (PROVISIONAL-UNMEASURED, 57.5 Hz / 0.10 s).
            # Guard: relay_81u_threshold_hz must be below the system nominal frequency.
            # A 57.5 Hz threshold makes no sense for a 50 Hz system — 50 Hz nominal is
            # already below 57.5 Hz, so the relay would fire immediately on every sub-step.
            # Physical interpretation: the threshold is calibrated for the site frequency;
            # for a 60 Hz (WECC/SDG&E) site 57.5 Hz < 60 Hz → relay active.
            # For a 50 Hz (EU/APAC) site 57.5 Hz > 50 Hz → relay disabled (not calibrated).
            if not state._relay_81u_fired and not _island_collapsed_this_tick:
                _r81u_thresh = state.site.relay_81u_threshold_hz
                # relay_81u_threshold_hz is opt-in (None = disabled).
                # Also guard: threshold must be below the system nominal frequency.
                if _r81u_thresh is not None and _r81u_thresh < _f0 and _f <= _r81u_thresh:
                    state._relay_81u_timer_s += _dt_sub
                    if state._relay_81u_timer_s >= state.site.relay_81u_delay_s:
                        state._relay_81u_fired = True
                        _island_collapsed_this_tick = True
                        _fp_collapse_reason = "island_collapse_uf"
                        _fp_collapse_frequency_hz = _f
                        state._frequency_hz = _f
                        _log.warning(
                            "§81U ISLANDED TRIP: f=%.3f Hz ≤ %.3f Hz for %.3f s "
                            "≥ %.3f s delay, tick %d. PROVISIONAL-UNMEASURED threshold.",
                            _f, _r81u_thresh, state._relay_81u_timer_s,
                            state.site.relay_81u_delay_s, state.tick_index,
                        )
                        break
                else:
                    state._relay_81u_timer_s = 0.0

            # §REPORT-5A: island_collapse_hz — retained for backward compat.
            # NOTE: This is the IEEE 1547-2018 Cat I grid-connected DER threshold
            # (57.0 Hz). Using it as the islanded UF trip is a defect (reported).
            # The 81U relay (57.5 Hz, delayed) fires at a less-conservative level;
            # for rapidly falling f, island_collapse_hz fires first (57.0 < 57.5 Hz).
            if not _island_collapsed_this_tick:
                _fp_collapse = state.site.island_collapse_hz
                _fp_of_trip  = state.site.of_trip_hz
                if _fp_collapse is not None and _f <= _fp_collapse:
                    state._frequency_hz = _fp_collapse
                    _island_collapsed_this_tick = True
                    _fp_collapse_reason = "island_collapse_uf"
                    _fp_collapse_frequency_hz = _fp_collapse
                    _log.warning(
                        "§FP UF-2 ISLAND COLLAPSE: f=%.3f Hz ≤ %.3f Hz at tick %d "
                        "(sim_time=%.1f s).  Frequency frozen; run will halt after this tick.",
                        _f, _fp_collapse, state.tick_index, clock.sim_time,
                    )
                    break
                elif _fp_of_trip is not None and _f >= _fp_of_trip:
                    state._frequency_hz = _fp_of_trip
                    _island_collapsed_this_tick = True
                    _fp_collapse_reason = "island_collapse_of"
                    _fp_collapse_frequency_hz = _fp_of_trip
                    _log.warning(
                        "§FP OF-2 ISLAND COLLAPSE: f=%.3f Hz ≥ %.3f Hz at tick %d "
                        "(sim_time=%.1f s).  Frequency frozen; run will halt after this tick.",
                        _f, _fp_of_trip, state.tick_index, clock.sim_time,
                    )
                    break

        if not _island_collapsed_this_tick:
            state._frequency_hz = _f

        # Advisory threshold checks (non-tripping; island_collapsed stays False).
        if not _island_collapsed_this_tick:
            _fp_ufls1   = state.site.ufls_stage1_hz
            _fp_uf_warn = state.site.uf_warning_hz
            _fp_of_warn = state.site.of_warning_hz
            if _fp_ufls1 is not None and state._frequency_hz <= _fp_ufls1:
                _fp_collapse_reason = "ufls_stage1"
            elif _fp_uf_warn is not None and state._frequency_hz <= _fp_uf_warn:
                _fp_collapse_reason = "uf_warning"
            elif _fp_of_warn is not None and state._frequency_hz >= _fp_of_warn:
                _fp_collapse_reason = "of_warning"
    else:
        # Grid-connected: frequency is the grid's reference; not integrated.
        state._frequency_hz = state.site.frequency_nominal_hz
        _protection_provisional = False  # No PROVISIONAL physics in grid-connected mode

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
    _max_cooling_mw = state.site.alpha_max * max(p_compute_demand_mw, 1e-6)
    _cooling_fraction = (
        min(1.0, p_cooling_demand_mw / _max_cooling_mw)
        if _max_cooling_mw > 1e-9
        else 0.0
    )
    _compute_inlet_temp_c = _T_AMBIENT_BASE_C + _cooling_fraction * _T_RISE_MAX_C

    # ── Phase 6: Supply/served producers ──────────────────────────────────────
    # P_served = min(P_demand − cumulative_shed, P_generation).
    #
    # The cap at P_generation is essential: when the BESS is power-saturated or
    # turbines are still starting, generation can be less than admitted demand.
    # Without the cap, served = full demand and the display shows physically
    # impossible values (e.g. 21.09 MW served from 20.40 MW generation).
    #
    # The cap is display-only: frequency physics uses _balance_residual_mw
    # (= P_gen − P_demand, line ~1381) directly and is NOT derived from
    # _p_served_mw, so the swing-equation dynamics are unaffected.
    #
    # P_unserved now captures both UFLS-shed load AND generation-deficit load in
    # one field, which closes the D4 identity:
    #   defect = generation + exchange − (demand − unserved)
    #          = generation + exchange − served  →  0 when served = generation.
    #
    # Per-subsystem shed: proportional to demand fraction (same judgement call as
    # before — stage definitions specify block_fraction of total demand only).
    _cumulative_shed_mw = state._cumulative_shed_mw  # monotonic run total
    # GS-FIX-SERVED: cap on _p_generation_mw (local gen + grid import) rather than
    # _p_gen_mw (local gen only).  In grid-connected mode the grid is the slack bus
    # and covers whatever local generation cannot supply; capping on _p_gen_mw alone
    # set _p_served_mw = 0 whenever all turbines/BESS were absent or at standby,
    # reporting SERVED = 0.00 MW even though the grid was actively importing to meet
    # demand.  In islanded mode _grid_exchange_mw = 0 (D1), so
    # _p_generation_mw == _p_gen_mw and the fix is a no-op there.
    _p_served_mw   = min(p_demand_mw - _cumulative_shed_mw, _p_generation_mw)
    _p_unserved_mw = p_demand_mw - _p_served_mw   # shed + generation deficit
    _p_imbalance_mw = _p_generation_mw - _p_served_mw

    # D4 — power balance identity (Phase 0 + DR-BAL-5, DR-2026-08-09-BALANCE).
    #
    # FINDING (Phase 0): the previous expression
    #   _d4_sum = _grid_exchange_mw + _frequency_forcing_mw
    #   _d4_balance_defect_mw = _d4_sum - _balance_residual_mw
    # was a routing consistency check, identically zero by algebraic construction
    # when islanded: _grid_exchange_mw=0, _frequency_forcing_mw=_balance_residual_mw
    # → defect = _balance_residual_mw - _balance_residual_mw = 0. Defect #273.
    #
    # Replacement: supply-demand residual (local_gen + import − served − losses).
    # Sign convention: positive = surplus generation (per core/power_balance.py).
    #
    # Convention note: power_balance.py uses GRID_EXCHANGE_POSITIVE_IS_IMPORT=True,
    # meaning it expects a positive value for grid import.  simulation_core's
    # _grid_exchange_mw is negative on import (balance_residual < 0 when local gen
    # < demand), so we pass −_grid_exchange_mw here to match the convention.
    #
    # DR-BAL-5 (C-3): p_unserved_mw = _cumulative_shed_mw (UFLS-shed load only).
    # Generation deficit is NOT a "shed" for D4 purposes — it shows up as a non-zero
    # defect (generation + import < served) rather than reducing the served load term.
    # p_losses_mw defaults to 0.0 — the model does not represent losses.
    _d4_balance_defect_mw = _balance_defect_mw(_BalanceTerms(
        p_generation_mw=_p_gen_mw,            # local gen only (turbine+BESS+solar)
        p_demand_mw=p_demand_mw,
        p_unserved_mw=_cumulative_shed_mw,     # UFLS-shed only; gen deficit ≠ shed
        grid_exchange_mw=-_grid_exchange_mw,   # negate: positive = import (POSITIVE_IS_IMPORT=True)
        island_mode=_BAL_ISLANDED if _islanded else _BAL_GRID_TIE,
    ))
    if abs(_d4_balance_defect_mw) >= 1e-3:
        _log.warning(
            "D4 balance identity does not close: %+.4g MW "
            "(gen=%.4f, demand=%.4f, exchange=%.4f islanded=%s; "
            "routing check — balance_residual=%.6f)",
            _d4_balance_defect_mw,
            _p_generation_mw, p_demand_mw, _grid_exchange_mw, _islanded,
            _balance_residual_mw,
        )

    if p_demand_mw > 1e-9:
        _compute_demand_frac = p_compute_demand_mw / p_demand_mw
        _cooling_demand_frac = p_cooling_demand_mw / p_demand_mw
    else:
        _compute_demand_frac = 0.5
        _cooling_demand_frac = 0.5
    _p_compute_served_mw   = p_compute_demand_mw - _p_unserved_mw * _compute_demand_frac
    _p_compute_unserved_mw = _p_unserved_mw * _compute_demand_frac
    _p_cooling_served_mw   = p_cooling_demand_mw - _p_unserved_mw * _cooling_demand_frac
    _p_cooling_unserved_mw = _p_unserved_mw * _cooling_demand_frac

    state.tick_index += 1
    return TickResult(
        run_id=state.run_id,
        tick_index=state.tick_index,
        # F5: TickResult carries the INTERVAL-END timestamp — the instant the
        # state was measured (after asset advance() calls).  SimClock.sim_time
        # is the interval START; all internal elapsed calculations above use
        # clock.sim_time directly.  Only the persisted / wire field changes.
        sim_time_seconds=sim_time + clock.dt_seconds,
        p_compute_demand_mw=p_compute_demand_mw,
        p_cooling_demand_mw=p_cooling_demand_mw,
        p_demand_mw=p_demand_mw,
        net_demand_mw=net_demand_mw,
        turbine_output_mw=turbine_output_mw,
        bess_output_mw=bess_output_mw,
        fuel_cell_output_mw=fuel_cell_output_mw,
        bess_soc_fraction=(state.bess_units[0].soc_fraction if state.bess_units else 1.0),
        confidence=confidence,
        insufficient_reserve_alert=alert_fired,
        unrecognised_profile_alerts=unrecognised_alerts,
        checkpoint_states=checkpoint_states,
        wall_stamp_utc=clock.wall_stamp_utc,
        p_renewable_mw=p_renewable_mw,
        p_renewable_curtailed_mw=_p_renewable_curtailed_mw,
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
        # Phase 13.3: gt_setpoint_mw is the droop-adjusted turbine command.
        # Gate on SYNCHRONISED (same variable as the delivery-error formula):
        # when no SYNCHRONISED turbine exists, the turbine fleet has no actionable
        # setpoint — demand is fully absorbed by the BESS shortfall path.
        # Using _p_dispatch_droop_mw here while asset_delivery_error_mw uses
        # _turb_setpoint_for_error_mw would make the D5 formula check inconsistent.
        gt_setpoint_mw=_turb_setpoint_for_error_mw,
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
        # Task #198 item 5: D4 defect field — 0.0 in normal operation.
        d4_balance_defect_mw=_d4_balance_defect_mw,
        # Phase E+: commitment engine last-decision summary.
        commitment_action=_commit_decision.action,
        commitment_target_unit_id=_commit_decision.target_unit_id,
        commitment_reason=_commit_decision.reason,
        commitment_blocked_by=_commit_decision.blocked_by,
        committed_rated_mw=_committed_rated_mw_cs,
        reserve_floor_mw=_reserve_floor_mw_cs,
        reserve_satisfied=_reserve_satisfied_cs,
        fleet_utilisation=_fleet_utilisation_cs,
        pending_start_unit_id=_pending_start_id_cs,
        # §FP: Frequency protection outcome — derived from protection logic above.
        island_collapsed=_island_collapsed_this_tick,
        collapse_reason=_fp_collapse_reason,
        collapse_tick_index=(state.tick_index if _island_collapsed_this_tick else None),
        collapse_frequency_hz=_fp_collapse_frequency_hz,
        # GS-CHG-2026-08-08 successor Phase 1
        p_generation_mw=_p_generation_mw,
        # Phase 2A: protection_provisional — True for all islanded ticks.
        protection_provisional=_protection_provisional,
        # Phase 6: supply/served producers.
        p_served_mw=_p_served_mw,
        p_unserved_mw=_p_unserved_mw,
        p_imbalance_mw=_p_imbalance_mw,
        p_compute_served_mw=_p_compute_served_mw,
        p_compute_unserved_mw=_p_compute_unserved_mw,
        p_cooling_served_mw=_p_cooling_served_mw,
        p_cooling_unserved_mw=_p_cooling_unserved_mw,
        # GPU load profile — active fraction this tick (1.0 = no scaling).
        gpu_load_fraction=_gpu_load_fraction,
    )
