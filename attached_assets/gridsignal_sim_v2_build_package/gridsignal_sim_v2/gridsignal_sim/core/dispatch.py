"""
Checkpoint-valley classification, dispatch arbitration, and confidence
banding -- source spec Sections 6.2, 7.2, 12; functional spec Sections
5.3, 5.4.

Kept synchronous and side-effect-free at the arithmetic level for the
same reason as asset_modules.py (Design Spec Section 4.3): this is the
deterministic core, tested independently of the async run-management
layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .asset_modules import BessModule, GPUModule, TurbineModule
from .models import ConfidenceBand, DataQualityTag, IslandMode, SiteConfig

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Checkpoint-valley classifier -- source spec Section 6.2
# ---------------------------------------------------------------------------

class CheckpointState(str, Enum):
    NORMAL = "normal"
    IN_VALLEY = "in_valley"      # drop detected, within the 45s recovery window
    CHECKPOINT = "checkpoint"    # recovered >= 90% within 45s -> confirmed checkpoint
    JOB_END = "job_end"          # grace period expired without recovery -> job completion
    UNCERTAIN = "uncertain"      # 45s elapsed, no recovery, no job_end event yet


@dataclass
class _JobDrawHistory:
    """Trailing draw samples for one job, used to compute the 5-minute
    median and detect the shape-heuristic drop/recovery per source
    spec Section 6.2."""
    samples: list[tuple[float, float]] = field(default_factory=list)  # (t, draw_mw)
    drop_onset_time: Optional[float] = None
    pre_drop_draw_mw: Optional[float] = None
    state: CheckpointState = CheckpointState.NORMAL
    uncertain_since: Optional[float] = None

    # D1 fix (explicit_hold): set by apply_explicit_event(checkpoint_start=True),
    # cleared by apply_explicit_event(checkpoint_start=False).  While True, the
    # IN_VALLEY branch skips the RECOVERY_WINDOW_S timeout entirely — the
    # scheduler event is authoritative and the heuristic timer must not override
    # it regardless of how long the checkpoint write takes.
    explicit_hold: bool = False

    # D1/B-1 (explicit_active): set alongside explicit_hold on checkpoint_start,
    # consumed on exactly the next record_and_classify call.  Prevents the NORMAL/
    # CHECKPOINT re-entry branch from immediately re-detecting a drop and
    # overwriting the IN_VALLEY state the explicit event just established.
    # Does a different job from explicit_hold and must be kept separately.
    explicit_active: bool = False

    def trailing_median(self, sim_time: float, window_s: float = 300.0) -> Optional[float]:
        window = [v for t, v in self.samples if sim_time - window_s <= t <= sim_time]
        if not window:
            return None
        window_sorted = sorted(window)
        mid = len(window_sorted) // 2
        if len(window_sorted) % 2 == 0:
            return (window_sorted[mid - 1] + window_sorted[mid]) / 2
        return window_sorted[mid]


class CheckpointClassifier:
    """Per-job state machine implementing §6.2's two-tier classification:
    1. Explicit scheduler events are the authoritative (primary) signal.
    2. Shape heuristic (drop/recovery detection) is the fallback path.

    JOB_END is terminal for a given job_id.  Once set it does not flip
    back to in_valley, which would otherwise oscillate a controller's
    turbine ramp-down decision (B-3 fix).
    """

    DROP_THRESHOLD_FRACTION = 0.15      # §6.2: drop >= 15% triggers IN_VALLEY
    MIN_DROP_DURATION_S = 5.0
    MAX_DROP_DURATION_S = 30.0
    RECOVERY_WINDOW_S = 45.0            # §6.2: recovery window (heuristic only)
    RECOVERY_THRESHOLD_FRACTION = 0.90  # §6.2: >= 90% recovery -> CHECKPOINT
    UNCERTAIN_GRACE_PERIOD_S = 30.0     # §6.2: hold staging after 45s expiry
    # D4 fix: safety ceiling on explicit_hold.  If checkpoint_end never arrives
    # (scheduler crash, dropped event, or §17.2 quarantine) the hold must release
    # so turbine ramp-down is not blocked indefinitely — same failure class as
    # §23.6 curtailment: "a partitioned controller must not be able to hold a
    # customer's fleet down indefinitely."
    # 900.0 s is a CHOSEN value with no measured basis; the plausible upper bound
    # on a large model checkpoint write is unmeasured (PROTO-3).
    MAX_EXPLICIT_HOLD_S = 900.0         # CHOSEN value — no measured basis (PROTO-3)

    def __init__(self) -> None:
        self._jobs: dict[str, _JobDrawHistory] = {}

    def _history_for(self, job_id: str) -> _JobDrawHistory:
        return self._jobs.setdefault(job_id, _JobDrawHistory())

    def apply_explicit_event(
        self, job_id: str, is_checkpoint_start: bool, sim_time: float
    ) -> None:
        """Apply an authoritative scheduler checkpoint_start or checkpoint_end.

        Per §6.2, an explicit scheduler event is the primary signal and
        short-circuits the shape heuristic entirely.

        D2 fix: JOB_END is terminal.  apply_explicit_event previously wrote
        hist.state directly with no terminal check, so a late or duplicate
        checkpoint_end (expected under §11.3's reordering buffer) would resurrect
        a finished job to CHECKPOINT.  Events arriving after JOB_END are now
        discarded and logged.

        D1 fix: explicit_hold (set here on checkpoint_start, cleared on
        checkpoint_end) causes the IN_VALLEY branch in record_and_classify to
        skip the RECOVERY_WINDOW_S timeout for as long as the authoritative hold
        is active.  This is separate from explicit_active, which only bypasses
        the re-entry drop-detection on exactly the next tick.
        """
        hist = self._history_for(job_id)

        # D2 fix: terminal guard.  §11.3 reordering buffer means late events are
        # expected in production; discard silently-but-visibly rather than letting
        # a stale event change control state.
        if hist.state == CheckpointState.JOB_END:
            _log.debug(
                "apply_explicit_event discarded for job %r: state is JOB_END "
                "(terminal).  is_checkpoint_start=%r sim_time=%s",
                job_id, is_checkpoint_start, sim_time,
            )
            return

        if is_checkpoint_start:
            hist.state = CheckpointState.IN_VALLEY
            hist.drop_onset_time = sim_time
            # Initialise pre_drop_draw_mw from the trailing median so the
            # IN_VALLEY guard below does not see None.  Fall back to the last
            # recorded sample, or to a sentinel when there is no history yet
            # (sentinel is safe because explicit_active bypasses the heuristic
            # on tick 1, and explicit_hold bypasses the timeout thereafter).
            median = hist.trailing_median(sim_time)
            if median is not None and median > 0:
                hist.pre_drop_draw_mw = median
            elif hist.samples:
                hist.pre_drop_draw_mw = hist.samples[-1][1]
            else:
                hist.pre_drop_draw_mw = 1.0  # sentinel
            # D1 fix: hold the explicit state until checkpoint_end arrives.
            hist.explicit_hold = True
        else:
            hist.state = CheckpointState.CHECKPOINT
            # D1 fix: checkpoint_end closes the authoritative hold.
            hist.explicit_hold = False

        # B-1/D1 fix: bypass the re-entry drop-detection branch for exactly one
        # tick so that the explicit event is not immediately overwritten.
        hist.explicit_active = True

    def record_and_classify(
        self, job_id: str, sim_time: float, draw_mw: float
    ) -> CheckpointState:
        hist = self._history_for(job_id)
        hist.samples.append((sim_time, draw_mw))
        cutoff = sim_time - 600  # keep slightly more than the 5-minute window
        hist.samples = [(t, v) for t, v in hist.samples if t >= cutoff]

        # B-3 fix: JOB_END is terminal.  A classification that oscillates
        # job_end -> in_valley on alternating ticks would cause a controller to
        # start and abort turbine ramp-down repeatedly with no input change.
        if hist.state == CheckpointState.JOB_END:
            return hist.state

        # B-1/D1 fix (explicit_active): the explicit scheduler event is the
        # authoritative signal; bypass re-entry drop-detection for one tick.
        if hist.explicit_active:
            hist.explicit_active = False
            return hist.state

        if hist.state in (CheckpointState.NORMAL, CheckpointState.CHECKPOINT):
            median = hist.trailing_median(sim_time)
            if median and median > 0 and draw_mw <= median * (1 - self.DROP_THRESHOLD_FRACTION):
                hist.state = CheckpointState.IN_VALLEY
                hist.drop_onset_time = sim_time
                hist.pre_drop_draw_mw = median
            else:
                hist.state = CheckpointState.NORMAL
            return hist.state

        if hist.state == CheckpointState.IN_VALLEY:
            # B-1 fix: raise rather than assert — asserts are stripped under
            # python -O, silently converting a visible crash into None arithmetic.
            if hist.drop_onset_time is None or hist.pre_drop_draw_mw is None:
                raise ValueError(
                    f"IN_VALLEY for job {job_id!r} is missing drop_onset_time or "
                    "pre_drop_draw_mw.  IN_VALLEY must only be entered via drop "
                    "detection (which sets both) or apply_explicit_event("
                    "is_checkpoint_start=True) (which also sets both explicitly)."
                )
            elapsed = sim_time - hist.drop_onset_time
            recovered_fraction = (
                draw_mw / hist.pre_drop_draw_mw if hist.pre_drop_draw_mw else 0.0
            )

            # D4 fix: safety release.  If checkpoint_end never arrives (scheduler
            # crash, dropped event, §17.2 quarantine) the hold must expire rather
            # than keeping the job IN_VALLEY forever and blocking turbine ramp-down.
            # After release, execution falls through to the elif below, which fires
            # immediately (elapsed >> RECOVERY_WINDOW_S) and sets UNCERTAIN.
            # The explicit event pair remains authoritative when present; this only
            # fires when checkpoint_end has been absent for MAX_EXPLICIT_HOLD_S.
            if hist.explicit_hold and elapsed > self.MAX_EXPLICIT_HOLD_S:
                _log.warning(
                    "explicit_hold safety-released for job %r: checkpoint_end not "
                    "received after %.0fs (MAX_EXPLICIT_HOLD_S=%.0f — CHOSEN value, "
                    "no measured basis, PROTO-3).  Heuristic resumes.",
                    job_id, elapsed, self.MAX_EXPLICIT_HOLD_S,
                )
                hist.explicit_hold = False
                # Fall through — do NOT jump to a classification here.

            if (
                elapsed <= self.RECOVERY_WINDOW_S
                and recovered_fraction >= self.RECOVERY_THRESHOLD_FRACTION
            ):
                hist.state = CheckpointState.CHECKPOINT
            elif elapsed > self.RECOVERY_WINDOW_S and not hist.explicit_hold:
                # D1 fix: only apply the heuristic timeout when there is no
                # authoritative scheduler hold in force.  If explicit_hold is True
                # the checkpoint_start event has asserted that this IS a checkpoint
                # write; we wait for the matching checkpoint_end regardless of
                # elapsed time (up to MAX_EXPLICIT_HOLD_S, per D4).
                if recovered_fraction >= self.RECOVERY_THRESHOLD_FRACTION:
                    # Recovered after the window — job is running normally again.
                    hist.state = CheckpointState.NORMAL
                else:
                    # B-2 fix: 45s elapsed without recovery and without an
                    # explicit job_end event → UNCERTAIN; hold staging for the
                    # 30s grace period.  JOB_END follows only from an explicit
                    # event or grace-period expiry in the UNCERTAIN handler below.
                    hist.state = CheckpointState.UNCERTAIN
                    if hist.uncertain_since is None:
                        hist.uncertain_since = sim_time
            # else: within recovery window, OR explicit hold still active
            #       → stay IN_VALLEY
            return hist.state

        if hist.state == CheckpointState.UNCERTAIN:
            if hist.uncertain_since is None:
                raise ValueError(
                    f"UNCERTAIN for job {job_id!r} is missing uncertain_since.  "
                    "UNCERTAIN must only be entered when the IN_VALLEY recovery "
                    "window expires without recovery, setting uncertain_since at "
                    "that moment."
                )
            if sim_time - hist.uncertain_since > self.UNCERTAIN_GRACE_PERIOD_S:
                hist.state = CheckpointState.JOB_END
            return hist.state

        return hist.state

    def state_of(self, job_id: str) -> CheckpointState:
        return self._history_for(job_id).state


# ---------------------------------------------------------------------------
# Dispatch arbitrator -- source spec Section 7.2, 7.3
# ---------------------------------------------------------------------------

@dataclass
class InsufficientReserveAlert:
    shortfall_mw: float
    gap_duration_s: float
    fires_at_sim_time: float


class DispatchArbitrator:
    """Stages turbines and BESS against P_dispatch_required(t) per §7.1.1.

    P_dispatch_required(t) = P_total(t) − P_renewable(t).

    Two asymmetries are structural here, not branch-guarded:

    1. No lead time for renewable shortfalls.  An inverter trip is a step
       change with Δt_lead = 0; stage_for_predicted_step() is only called for
       compute job starts (which do have lead time).  Renewable availability is
       subtracted by the caller before tick() is entered, so the fleet sizes
       against the net load it must serve from dispatchable sources alone.

    2. Renewables are availability, not dispatchability.  P_renewable is never
       counted toward ramp capability in the step-4 shortfall calculation.
       stage_for_predicted_step() uses only turbine r_asset values — there is
       no renewable term to forget, because there is no renewable term at all.
    """

    def __init__(
        self,
        turbines: list[TurbineModule],
        bess_units: list[BessModule],
        site: "SiteConfig",
    ) -> None:
        self.turbines = turbines
        self.bess_units = bess_units
        self.site = site   # read each tick for island_mode (Step 3 Item 4 / §7.1.2)

    # ------------------------------------------------------------------
    # Fleet allocation helper (Step 3 Item 4)
    # ------------------------------------------------------------------

    def _proportional_allocations(self, demand_mw: float) -> list[float]:
        """Split demand_mw across BESS units proportional to each unit's
        bridging_available_mw (anchor-adjusted power ceiling).

        When all units are identical this reduces to equal sharing.  For a
        heterogeneous fleet it prevents equal-share over-allocation to weak
        units, which would cause D11's power-ceiling guard to return 0.0 for
        those units and understate total fleet capability.

        If total bridging capacity is zero (all units depleted or anchored
        to zero), each unit gets a proportional share of demand_mw based on
        rated_mw so the taper/SoC logic still sees the correct demand signal
        and drains gracefully — none of them can deliver, but the call path
        stays well-defined.

        Returns a list aligned with self.bess_units.
        """
        island_mode = self.site.island_mode
        weights = [b.bridging_available_mw(island_mode) for b in self.bess_units]
        total_w = sum(weights)
        if total_w <= 0:
            # Fallback to rated_mw weights so the call path is always defined.
            weights = [b.config.rated_mw for b in self.bess_units]
            total_w = sum(weights) or 1.0
        return [demand_mw * w / total_w for w in weights]

    def stage_for_predicted_step(
        self, delta_p_mw: float, dt_lead_seconds: float, sim_time: float
    ) -> Optional[InsufficientReserveAlert]:
        """Called once at a job's STARTING event (§7.2 step 1) — NOT every tick.

        delta_p_mw is the step increase in P_dispatch_required caused by the
        new job.  For a compute job start this equals the step in P_total (solar
        output is unaffected by a new job landing); it must NOT include any
        renewable contribution because renewables can vanish without notice
        (Δt_lead = 0 for renewable shortfalls).

        Ramp capability is turbine-only — renewables are structurally absent
        from this function (no term to add, no branch to forget).  BESS bridges
        any gap between turbine ramp rate and required delta delivery time.

        Step 3 Item 4 — reserve aggregation:
          1. Allocate peak_shortfall_mw proportional to bridging_available_mw.
          2. Sum each unit's max_sustainable_seconds at ITS OWN allocated share.
          3. Compare sum against gap_s.

        The sum works because:
          - When fleet CAN cover: all allocations ≤ bridging_available_mw; each
            unit returns a positive duration; sum >> gap_s.
          - When fleet CANNOT cover: at least one unit's allocation exceeds its
            bridging_available_mw (because total_available < demand); that unit
            returns 0.0, collapsing the sum below gap_s → alert fires.

        D11 interaction: bridging_available_mw is the power ceiling (not rated_mw),
        so an anchor unit with reserve withheld and a unit allocated above its
        ceiling both correctly return 0.0.  A plain min() over equal-share
        fractions would average 0.0 away for a heterogeneous fleet; summing
        preserves the D11 signal.
        """
        if not self.turbines:
            required_ramp_s = float("inf")
        else:
            per_turbine_target = delta_p_mw / len(self.turbines)
            for turbine in self.turbines:
                turbine.stage_target(turbine.output_mw() + per_turbine_target)
            total_r_asset = sum(t.config.r_asset_mw_per_s for t in self.turbines)
            required_ramp_s = delta_p_mw / total_r_asset if total_r_asset else float("inf")

        gap_s = required_ramp_s - dt_lead_seconds
        if gap_s <= 0:
            return None  # sufficient lead time, no alert -- TC-11

        # Peak shortfall the BESS fleet must cover, per the §7.3 worked example.
        already_ramped_mw = sum(t.config.r_asset_mw_per_s for t in self.turbines) * dt_lead_seconds
        peak_shortfall_mw = max(0.0, delta_p_mw - already_ramped_mw)

        # Step 3 Item 4: proportional allocation + sum of sustainable durations.
        island_mode = self.site.island_mode
        allocations = self._proportional_allocations(peak_shortfall_mw)
        total_sustainable_s = sum(
            b.max_sustainable_seconds(alloc, island_mode)
            for b, alloc in zip(self.bess_units, allocations)
        )
        if total_sustainable_s >= gap_s:
            return None  # fleet can bridge the gap -- no alert

        return InsufficientReserveAlert(
            shortfall_mw=peak_shortfall_mw,
            gap_duration_s=gap_s,
            fires_at_sim_time=sim_time,
        )

    def tick(self, p_dispatch_required_mw: float, dt_seconds: float) -> tuple[float, float]:
        """Called every tick.  Returns (turbine_output_mw, bess_output_mw).

        p_dispatch_required_mw = P_total(t) − P_renewable(t) per §7.1.1.
        The renewable offset is applied by the caller (evaluate_tick) before
        this method is entered — renewables are structurally absent from all
        ramp and reserve arithmetic here (§7.1.1 asymmetry 2).

        A renewable shortfall (inverter trip, cloud shadow) has Δt_lead = 0;
        the fleet must cover P_dispatch_required from dispatchable sources alone
        with no warning (§7.1.1 asymmetry 1).

        Step 3 Item 4 — fleet split:
          Distribute the fleet shortfall proportional to each unit's
          bridging_available_mw (anchor-adjusted).  For a homogeneous fleet this
          equals equal sharing.  For a heterogeneous fleet it prevents equal-share
          over-allocation to weak units (spec test case b) and respects anchor
          reserve deductions (spec test case c).

          fleet_covered flag: True when turbines already cover demand at fleet
          level — passed to cover_shortfall for taper logic.  A unit with zero
          allocation (depleted or anchored) must not advance its own taper timer
          while the fleet still has a shortfall.
        """
        turbine_output_mw = sum(t.output_mw() for t in self.turbines)
        fleet_shortfall = max(0.0, p_dispatch_required_mw - turbine_output_mw)
        fleet_covered = fleet_shortfall <= 0.0

        island_mode = self.site.island_mode
        allocations = self._proportional_allocations(fleet_shortfall)

        bess_output_mw = 0.0
        for bess, alloc in zip(self.bess_units, allocations):
            bess_output_mw += bess.cover_shortfall(alloc, fleet_covered, dt_seconds, island_mode)
        return turbine_output_mw, bess_output_mw


# ---------------------------------------------------------------------------
# Confidence engine -- source spec Section 12, 17.2, 17.3
# ---------------------------------------------------------------------------

class ConfidenceEngine:
    """Composes independent data-quality tags into a widened confidence
    band.  Base band width and per-tag widening factors are chosen values,
    not derived from measured data -- they are placeholders pending
    design-partner calibration (source spec Section 12, FR-1.5).

    The additive composition is intentional: tags are independent
    provenance signals and their penalties must not cancel each other out.
    """

    BASE_BAND_FRACTION = 0.05

    # D6 fix: DEFAULT_WIDENING is used when a DataQualityTag has no
    # calibrated entry in WIDENING_PER_TAG.  Before this fix, .get(t, 0.0)
    # returned 0.0 for unknown tags — making an unknown tag produce the
    # same band as having no tag at all, silently reproducing the unadjusted
    # arithmetic the mechanism exists to correct (TC-63 argument).
    # An unknown data-quality problem is at least as bad as the worst known
    # one; 0.15 is a CHOSEN value with no measured basis (PROTO-4).
    DEFAULT_WIDENING: float = 0.15   # CHOSEN — no measured basis (PROTO-4)

    WIDENING_PER_TAG = {
        DataQualityTag.UNMAPPED_HARDWARE: 0.10,   # chosen value — no measured basis
        DataQualityTag.UNCALIBRATED_SITE: 0.08,   # chosen value — no measured basis
        DataQualityTag.INVALID_PAYLOAD: 0.15,     # chosen value — no measured basis
        DataQualityTag.STALE_PROFILE: 0.12,       # chosen value — no measured basis (v2.5 §5.3)
    }

    def __init__(self) -> None:
        # D6 fix: track which unknown tags have already been warned about so
        # the log fires at most once per unrecognised tag per engine instance
        # (one-time alert per session, not per tick — same pattern as §5.1's
        # one-time onboarding alert for unmapped hardware profiles).
        self._warned_unknown_tags: set[DataQualityTag] = set()

    def band_for(self, point_estimate_mw: float, tags: set[DataQualityTag]) -> ConfidenceBand:
        # D6 fix: unknown tags use DEFAULT_WIDENING, not 0.0.
        # Log once per unrecognised tag so the operator knows calibration is
        # missing; subsequent ticks are silent to avoid per-tick log spam.
        fraction = self.BASE_BAND_FRACTION
        for t in tags:
            w = self.WIDENING_PER_TAG.get(t)
            if w is None:
                if t not in self._warned_unknown_tags:
                    _log.warning(
                        "ConfidenceEngine: DataQualityTag %r has no calibrated "
                        "widening factor — applying DEFAULT_WIDENING=%.2f "
                        "(CHOSEN, no measured basis, PROTO-4).  Add a "
                        "WIDENING_PER_TAG entry when calibrated data is available.",
                        t, self.DEFAULT_WIDENING,
                    )
                    self._warned_unknown_tags.add(t)
                w = self.DEFAULT_WIDENING
            fraction += w
        return ConfidenceBand(
            point_estimate_mw=point_estimate_mw,
            plus_minus_fraction=fraction,
            tags=frozenset(tags),
        )
