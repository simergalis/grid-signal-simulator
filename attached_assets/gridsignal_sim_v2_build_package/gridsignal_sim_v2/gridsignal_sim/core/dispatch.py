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
    IN_VALLEY = "in_valley"          # drop detected, within the 45s recovery window
    CHECKPOINT = "checkpoint"         # recovered >= 90% within 45s -> confirmed checkpoint
    JOB_END = "job_end"               # did not recover -> job completion
    UNCERTAIN = "uncertain"           # 45s elapsed, no recovery, no job_end event yet


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
    """Per-job state machine. Explicit checkpoint_start/checkpoint_end
    scheduler events are authoritative when present (source spec
    Section 6.2 primary signal); this skeleton implements the fallback
    shape heuristic, which is the harder/interesting part to get right,
    and exposes `apply_explicit_event` for the primary-signal path.
    """

    DROP_THRESHOLD_FRACTION = 0.15
    MIN_DROP_DURATION_S = 5.0
    MAX_DROP_DURATION_S = 30.0
    RECOVERY_WINDOW_S = 45.0
    RECOVERY_THRESHOLD_FRACTION = 0.90
    UNCERTAIN_GRACE_PERIOD_S = 30.0

    def __init__(self) -> None:
        self._jobs: dict[str, _JobDrawHistory] = {}

    def _history_for(self, job_id: str) -> _JobDrawHistory:
        return self._jobs.setdefault(job_id, _JobDrawHistory())

    def apply_explicit_event(self, job_id: str, is_checkpoint_start: bool, sim_time: float) -> None:
        hist = self._history_for(job_id)
        hist.state = CheckpointState.IN_VALLEY if is_checkpoint_start else CheckpointState.CHECKPOINT

    def record_and_classify(self, job_id: str, sim_time: float, draw_mw: float) -> CheckpointState:
        hist = self._history_for(job_id)
        hist.samples.append((sim_time, draw_mw))
        cutoff = sim_time - 600  # keep a bit more than the 5-minute window
        hist.samples = [(t, v) for t, v in hist.samples if t >= cutoff]

        if hist.state in (CheckpointState.NORMAL, CheckpointState.CHECKPOINT, CheckpointState.JOB_END):
            median = hist.trailing_median(sim_time)
            if median and median > 0 and draw_mw <= median * (1 - self.DROP_THRESHOLD_FRACTION):
                hist.state = CheckpointState.IN_VALLEY
                hist.drop_onset_time = sim_time
                hist.pre_drop_draw_mw = median
            else:
                hist.state = CheckpointState.NORMAL
            return hist.state

        if hist.state == CheckpointState.IN_VALLEY:
            assert hist.drop_onset_time is not None and hist.pre_drop_draw_mw is not None
            elapsed = sim_time - hist.drop_onset_time
            recovered_fraction = draw_mw / hist.pre_drop_draw_mw if hist.pre_drop_draw_mw else 0.0

            if elapsed <= self.RECOVERY_WINDOW_S and recovered_fraction >= self.RECOVERY_THRESHOLD_FRACTION:
                hist.state = CheckpointState.CHECKPOINT
            elif elapsed > self.RECOVERY_WINDOW_S:
                hist.state = CheckpointState.JOB_END if recovered_fraction < self.RECOVERY_THRESHOLD_FRACTION else CheckpointState.NORMAL
                if hist.state == CheckpointState.JOB_END and self.MIN_DROP_DURATION_S <= elapsed:
                    pass  # classified job_end
                elif recovered_fraction < self.RECOVERY_THRESHOLD_FRACTION:
                    hist.state = CheckpointState.UNCERTAIN
                    hist.uncertain_since = sim_time
            # else: still within recovery window, not yet recovered -> stays IN_VALLEY
            return hist.state

        if hist.state == CheckpointState.UNCERTAIN:
            assert hist.uncertain_since is not None
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
    band. Base band width is a simple placeholder here -- real MAPE-
    based narrowing (source spec Section 12, per parent FR-1.5) is out
    of scope for this skeleton and is called out as such."""

    BASE_BAND_FRACTION = 0.05
    WIDENING_PER_TAG = {
        DataQualityTag.UNMAPPED_HARDWARE: 0.10,
        DataQualityTag.UNCALIBRATED_SITE: 0.08,
        DataQualityTag.INVALID_PAYLOAD: 0.15,
    }

    def band_for(self, point_estimate_mw: float, tags: set[DataQualityTag]) -> ConfidenceBand:
        fraction = self.BASE_BAND_FRACTION + sum(self.WIDENING_PER_TAG[t] for t in tags)
        return ConfidenceBand(
            point_estimate_mw=point_estimate_mw,
            plus_minus_fraction=fraction,
            tags=frozenset(tags),
        )
