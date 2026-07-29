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

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .asset_modules import BessModule, GPUModule, TurbineModule
from .models import ConfidenceBand, DataQualityTag


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
    # Set by apply_explicit_event(); causes record_and_classify() to short-circuit
    # the shape heuristic for exactly one tick.  This ensures the explicit
    # scheduler event is the authoritative classification, not immediately
    # overwritten by heuristic re-evaluation.
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
    RECOVERY_WINDOW_S = 45.0            # §6.2: recovery window
    RECOVERY_THRESHOLD_FRACTION = 0.90  # §6.2: >= 90% recovery -> CHECKPOINT
    UNCERTAIN_GRACE_PERIOD_S = 30.0     # §6.2: hold staging after 45s expiry

    def __init__(self) -> None:
        self._jobs: dict[str, _JobDrawHistory] = {}

    def _history_for(self, job_id: str) -> _JobDrawHistory:
        return self._jobs.setdefault(job_id, _JobDrawHistory())

    def apply_explicit_event(
        self, job_id: str, is_checkpoint_start: bool, sim_time: float
    ) -> None:
        """Apply an authoritative scheduler checkpoint_start or checkpoint_end.

        Per §6.2, an explicit scheduler event is the primary signal and
        short-circuits the shape heuristic entirely.  This method initialises
        all state that the heuristic would normally set -- specifically
        drop_onset_time and pre_drop_draw_mw -- so that the next call to
        record_and_classify() does not enter a half-initialised IN_VALLEY
        branch.  The explicit_active flag tells record_and_classify() to skip
        the heuristic for exactly one tick after this call.
        """
        hist = self._history_for(job_id)
        if is_checkpoint_start:
            hist.state = CheckpointState.IN_VALLEY
            hist.drop_onset_time = sim_time
            # Initialise pre_drop_draw_mw from the trailing median so the
            # IN_VALLEY guard below does not see None.  Fall back to the last
            # recorded sample, or to a sentinel when there is no history yet
            # (sentinel is safe because explicit events bypass shape heuristic).
            median = hist.trailing_median(sim_time)
            if median is not None and median > 0:
                hist.pre_drop_draw_mw = median
            elif hist.samples:
                hist.pre_drop_draw_mw = hist.samples[-1][1]
            else:
                hist.pre_drop_draw_mw = 1.0  # sentinel; bypassed by explicit_active
        else:
            hist.state = CheckpointState.CHECKPOINT
        # Short-circuit the heuristic on the very next record_and_classify call.
        hist.explicit_active = True

    def record_and_classify(
        self, job_id: str, sim_time: float, draw_mw: float
    ) -> CheckpointState:
        hist = self._history_for(job_id)
        hist.samples.append((sim_time, draw_mw))
        cutoff = sim_time - 600  # keep a bit more than the 5-minute window
        hist.samples = [(t, v) for t, v in hist.samples if t >= cutoff]

        # B-3 fix: JOB_END is terminal.  A classification that oscillates
        # job_end -> in_valley on alternating ticks would cause a controller to
        # start and abort turbine ramp-down repeatedly with no input change.
        if hist.state == CheckpointState.JOB_END:
            return hist.state

        # B-1 fix (explicit-event path): the explicit scheduler event is the
        # authoritative signal; short-circuit the heuristic for one tick.
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
            # B-1 fix: replace assert with a real guard.  Asserts are stripped
            # under python -O, which would convert this crash into silent None
            # arithmetic on a control path.
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

            if (
                elapsed <= self.RECOVERY_WINDOW_S
                and recovered_fraction >= self.RECOVERY_THRESHOLD_FRACTION
            ):
                hist.state = CheckpointState.CHECKPOINT
            elif elapsed > self.RECOVERY_WINDOW_S:
                if recovered_fraction >= self.RECOVERY_THRESHOLD_FRACTION:
                    # Recovered after the window -- not a clean checkpoint by the
                    # heuristic, but the job is running normally again.
                    hist.state = CheckpointState.NORMAL
                else:
                    # B-2 fix: 45s elapsed without recovery and without an
                    # explicit job_end event.  §6.2 routes this to UNCERTAIN:
                    # hold staging for a further 30s grace period and flag the
                    # job.  JOB_END follows only from an explicit event OR from
                    # the grace period expiring in the UNCERTAIN handler below.
                    # (Previously the code set JOB_END here, then tested
                    # `elif recovered < 0.90` -- an unreachable branch because
                    # that condition was already consumed by the preceding line.)
                    hist.state = CheckpointState.UNCERTAIN
                    if hist.uncertain_since is None:
                        hist.uncertain_since = sim_time
            # else: still within recovery window, not yet recovered -> stays IN_VALLEY
            return hist.state

        if hist.state == CheckpointState.UNCERTAIN:
            if hist.uncertain_since is None:
                raise ValueError(
                    f"UNCERTAIN for job {job_id!r} is missing uncertain_since.  "
                    "UNCERTAIN must only be entered when the IN_VALLEY recovery "
                    "window expires without recovery, at which point uncertain_since "
                    "is set to the current sim_time."
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
    """Stages turbines and BESS against a predicted step-load per
    source spec Section 7.2's four-step rule. This skeleton exposes
    one entry point per tick; the Run Manager (runtime/run_manager.py)
    calls it after computing this tick's P_total(t)."""

    def __init__(self, turbines: list[TurbineModule], bess_units: list[BessModule]) -> None:
        self.turbines = turbines
        self.bess_units = bess_units

    def stage_for_predicted_step(
        self, delta_p_mw: float, dt_lead_seconds: float, sim_time: float
    ) -> Optional[InsufficientReserveAlert]:
        """Called once, at a job's `starting` event (source spec
        Section 7.2 step 1) -- NOT every tick. Splits delta_p across
        online turbines and checks reserve sufficiency (step 4)."""
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

        # Peak shortfall the BESS must cover, per the Section 7.3 worked
        # example: turbines have already ramped `dt_lead_seconds` worth
        # by the time the full load lands.
        already_ramped_mw = sum(t.config.r_asset_mw_per_s for t in self.turbines) * dt_lead_seconds
        peak_shortfall_mw = max(0.0, delta_p_mw - already_ramped_mw)

        total_sustainable_s = min(
            (b.max_sustainable_seconds(peak_shortfall_mw / max(len(self.bess_units), 1)) for b in self.bess_units),
            default=0.0,
        )
        if total_sustainable_s >= gap_s:
            return None  # BESS can bridge the gap -- no alert

        return InsufficientReserveAlert(
            shortfall_mw=peak_shortfall_mw,
            gap_duration_s=gap_s,
            fires_at_sim_time=sim_time,
        )

    def tick(self, p_total_mw: float, dt_seconds: float) -> tuple[float, float]:
        """Called every tick. Returns (turbine_output_mw, bess_output_mw)."""
        turbine_output_mw = sum(t.output_mw() for t in self.turbines)
        bess_output_mw = 0.0
        remaining_total = p_total_mw
        for bess in self.bess_units:
            bess_output_mw += bess.cover_shortfall(remaining_total, turbine_output_mw, dt_seconds)
            # Each BESS unit sees the same (p_total, turbine_output) pair in
            # this skeleton -- a fleet-aware split is a documented refinement,
            # not required to demonstrate the arbitration rule itself.
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
    # Chosen values, not derived -- label makes the intent explicit so
    # future work does not mistake them for measured constants.
    WIDENING_PER_TAG = {
        DataQualityTag.UNMAPPED_HARDWARE: 0.10,   # chosen value
        DataQualityTag.UNCALIBRATED_SITE: 0.08,   # chosen value
        DataQualityTag.INVALID_PAYLOAD: 0.15,     # chosen value
    }

    def band_for(self, point_estimate_mw: float, tags: set[DataQualityTag]) -> ConfidenceBand:
        fraction = self.BASE_BAND_FRACTION + sum(self.WIDENING_PER_TAG[t] for t in tags)
        return ConfidenceBand(
            point_estimate_mw=point_estimate_mw,
            plus_minus_fraction=fraction,
            tags=frozenset(tags),
        )
