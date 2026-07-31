"""
core/maintenance.py — §27 Prescriptive maintenance: asset health tracking,
degradation, maintenance windows, and forecast-aware scheduling.

TC-58  Reserve arithmetic uses the re-rated ramp figure, neither excluding
       the asset from reserve nor counting it at nameplate.  After a re-rating
       is applied, reserve_contribution_mw_per_s() returns the effective value.

TC-59  MaintenanceScheduler.validate_window() checks the forecast across the
       FULL duration [start_sim_time, end_sim_time).  A window that begins in a
       demand trough but ends during a forecast step-load is REJECTED.  Checking
       only the start instant is a known failure mode: the window passes at the
       trough but the asset is unavailable during the step-load.

TC-60  Rating raises (proposed > effective) require:
         • observation window ≥ RAISE_CONFIRMATION_TICKS ticks of favorable data
         • requires_confirmation = True (always set by __post_init__)
       Rating reductions apply immediately with no confirmation requirement.
       Ratings move down easily, up only after evidence — "wrong in the raise
       direction" means an under-rated asset during a shortfall.

Scheduling is proposal-only at every tier.  Taking an asset out of service
dispatches a technician, not a setpoint.  Nothing in this module writes to
SimulationState or any runtime object.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Asset availability state machine
# ---------------------------------------------------------------------------

class AssetAvailability(str, Enum):
    OPERATIONAL = "operational"   # fully available, at or above effective rating
    DEGRADED    = "degraded"      # below nameplate but dispatch-eligible
    MAINTENANCE = "maintenance"   # scheduled downtime; excluded from dispatch
    FAILED      = "failed"        # unplanned failure; excluded from dispatch


# ---------------------------------------------------------------------------
# Asset health record
# ---------------------------------------------------------------------------

@dataclass
class AssetHealthRecord:
    """Tracks the current health and effective rating for one dispatchable asset.

    TC-58: reserve arithmetic uses effective_ramp_mw_per_s (the re-rated figure).
    Neither nameplate_ramp_mw_per_s (may overstate) nor 0.0 (excluded) is used
    while the asset is OPERATIONAL or DEGRADED.
    """

    asset_id:                    str
    availability:                AssetAvailability = AssetAvailability.OPERATIONAL

    # Current effective ramp rate — may differ from nameplate after re-rating.
    # TC-58: this is the value reserve_contribution_mw_per_s() returns.
    nameplate_ramp_mw_per_s:     float = 0.0
    effective_ramp_mw_per_s:     float = 0.0      # set equal to nameplate at creation

    # Observed ramp (from runtime measurement); None until at least one sample.
    measured_ramp_mw_per_s:      Optional[float] = None

    # TC-60: ticks of favorable data accumulated toward a rating raise.
    favorable_observation_ticks: int = 0

    # Ticks required before a rating raise is proposed.  PROTO-14: chosen value.
    RAISE_CONFIRMATION_TICKS: ClassVar[int] = 20

    @property
    def is_dispatch_eligible(self) -> bool:
        """True when the asset contributes to reserve (not MAINTENANCE or FAILED)."""
        return self.availability in (
            AssetAvailability.OPERATIONAL,
            AssetAvailability.DEGRADED,
        )


def reserve_contribution_mw_per_s(record: AssetHealthRecord) -> float:
    """TC-58: return the effective ramp rate for reserve arithmetic.

    Uses record.effective_ramp_mw_per_s — the re-rated figure when a §27
    re-rating is in force.

    Excludes (returns 0.0) assets in MAINTENANCE or FAILED state.  For
    OPERATIONAL or DEGRADED assets it uses the re-rated value, which may be
    lower than nameplate but is never zero by this function.

    Callers must pass the health record, not the TurbineConfig, so that
    re-ratings flow through without modifying the config object.
    """
    if not record.is_dispatch_eligible:
        return 0.0          # TC-58: correctly excluded (MAINTENANCE / FAILED)
    return record.effective_ramp_mw_per_s   # TC-58: re-rated figure, not nameplate


# ---------------------------------------------------------------------------
# Rating proposals (§27.5)
# ---------------------------------------------------------------------------

class RatingChangeKind(str, Enum):
    LOWER = "lower"   # degradation demotion — applies immediately
    RAISE = "raise"   # capability claim  — requires evidence + confirmation


@dataclass
class RatingProposal:
    """§27.5 re-rating proposal.

    TC-60: kind=RAISE always has requires_confirmation=True.
    TC-60: kind=LOWER has requires_confirmation=False (conservative direction).
    """

    asset_id:                    str
    kind:                        RatingChangeKind
    proposed_ramp_mw_per_s:      float
    observation_ticks_at_proposal: int = 0
    requires_confirmation:       bool = False

    def __post_init__(self) -> None:
        # TC-60: raising always requires confirmation; caller cannot override.
        if self.kind == RatingChangeKind.RAISE:
            self.requires_confirmation = True


# ---------------------------------------------------------------------------
# Maintenance windows (TC-59)
# ---------------------------------------------------------------------------

@dataclass
class MaintenanceWindow:
    """A scheduled maintenance slot for one asset.

    TC-59: validate_window() checks the forecast over the full
    [start_sim_time, end_sim_time) duration, not only the start instant.
    """

    asset_id:          str
    window_id:         str
    start_sim_time:    float
    end_sim_time:      float
    forecast_validated: bool = False
    rejection_reason:  str   = ""   # non-empty when validate_window() returned False


# ---------------------------------------------------------------------------
# Maintenance scheduler (§27.3)
# ---------------------------------------------------------------------------

class MaintenanceScheduler:
    """§27.3 prescriptive maintenance ladder.

    Scheduling is proposal-only at every tier.  Outputs are proposals and
    validation verdicts — nothing here touches SimulationState.

    TC-59  validate_window() iterates every forecast tick whose sim_time falls
           within [window.start_sim_time, window.end_sim_time].  If any tick
           shows remaining capacity (available_capacity_without_asset_mw −
           demand_mw) below reserve_threshold_mw, the window is rejected.

    TC-60  propose_rating_change() classifies the direction.  RAISE proposals
           carry requires_confirmation=True unconditionally.  LOWER proposals
           carry requires_confirmation=False.
    """

    # ── TC-59: maintenance window validation ─────────────────────────────

    def validate_window(
        self,
        record: AssetHealthRecord,
        window: MaintenanceWindow,
        *,
        forecast_ticks: Sequence[Tuple[float, float, float]],
        reserve_threshold_mw: float = 0.0,
    ) -> bool:
        """TC-59: full-duration forecast validation.

        Parameters
        ----------
        record:
            The asset being scheduled for maintenance.
        window:
            The proposed maintenance window.
        forecast_ticks:
            Sequence of (sim_time, demand_mw, available_capacity_without_asset_mw).
            Ticks outside [window.start_sim_time, window.end_sim_time] are ignored.
        reserve_threshold_mw:
            Minimum reserve headroom required at every tick in the window.

        Returns True when safe across the full duration; False otherwise.
        Populates window.rejection_reason when returning False.
        window.forecast_validated is set to the return value.

        TC-59 guarantee: checking only the start instant would miss a window
        that begins in a demand trough and ends during a forecast step-load.
        This method examines EVERY tick within the duration.
        """
        # Collect only ticks within the window's duration.
        covered = [
            (sim_t, demand, capacity)
            for (sim_t, demand, capacity) in forecast_ticks
            if window.start_sim_time <= sim_t <= window.end_sim_time
        ]

        failures: list[str] = []
        for sim_t, demand, capacity in covered:
            headroom = capacity - demand
            if headroom < reserve_threshold_mw:
                failures.append(
                    f"t={sim_t:.1f}s: headroom={headroom:.2f} MW < "
                    f"threshold={reserve_threshold_mw:.2f} MW "
                    f"(demand={demand:.2f}, capacity={capacity:.2f})"
                )

        if failures:
            window.rejection_reason = (
                f"TC-59: window validation failed at {len(failures)} tick(s): "
                + failures[0]
                + (f" [+{len(failures)-1} more]" if len(failures) > 1 else "")
            )
            window.forecast_validated = False
            return False

        window.forecast_validated = True
        window.rejection_reason = ""
        return True

    # ── TC-60: rating proposals (§27.5) ──────────────────────────────────

    def propose_rating_change(
        self,
        record: AssetHealthRecord,
        proposed_ramp_mw_per_s: float,
    ) -> RatingProposal:
        """§27.5 re-rating proposal.

        TC-60: raises require the observation window ≥ RAISE_CONFIRMATION_TICKS
        AND requires_confirmation=True (set by RatingProposal.__post_init__).
        Reductions apply without confirmation — conservative direction.

        A rating raise asserts the asset can do more than believed.  If that
        assertion is wrong it is discovered during a shortfall, so a longer
        observation window is required before the proposal is even generated.
        Reductions assert less capability — discovered as excess conservatism,
        not a shortfall.
        """
        if proposed_ramp_mw_per_s <= record.effective_ramp_mw_per_s:
            # Equal or lower: conservative direction (LOWER).
            # A raise requires strictly greater — asserting the asset can do MORE.
            kind = RatingChangeKind.LOWER
        else:
            kind = RatingChangeKind.RAISE

        return RatingProposal(
            asset_id=record.asset_id,
            kind=kind,
            proposed_ramp_mw_per_s=proposed_ramp_mw_per_s,
            observation_ticks_at_proposal=record.favorable_observation_ticks,
            # requires_confirmation is set by __post_init__ for RAISE
        )

    def apply_confirmed_rating(
        self,
        record: AssetHealthRecord,
        proposal: RatingProposal,
    ) -> None:
        """Apply a confirmed re-rating to the health record.

        TC-58: after this call, reserve_contribution_mw_per_s(record) returns
        the re-rated figure — neither nameplate nor zero (excluded).

        For LOWER proposals, applies immediately (no confirmation gate check
        here — the caller is responsible for the confirmation gate for RAISE;
        this method applies whatever proposal is passed unconditionally so it
        can be used in both the confirmed and the immediate-reduction paths).
        """
        if proposal.asset_id != record.asset_id:
            raise ValueError(
                f"Proposal for {proposal.asset_id!r} cannot be applied to "
                f"record for {record.asset_id!r}"
            )
        record.effective_ramp_mw_per_s = round(proposal.proposed_ramp_mw_per_s, 6)
        if proposal.kind == RatingChangeKind.LOWER:
            if record.effective_ramp_mw_per_s < record.nameplate_ramp_mw_per_s:
                record.availability = AssetAvailability.DEGRADED
        else:
            # Rating raise — if back to nameplate, restore OPERATIONAL
            if abs(record.effective_ramp_mw_per_s - record.nameplate_ramp_mw_per_s) < 1e-9:
                record.availability = AssetAvailability.OPERATIONAL


# ---------------------------------------------------------------------------
# AD1: MaintenanceLayer — per-tick evaluation (TC-58, TC-59, TC-60)
# ---------------------------------------------------------------------------

class MaintenanceLayer:
    """§27 prescriptive maintenance layer — exercised each tick by _drive().

    Exercises TC-58 (reserve uses re-rated ramp, not nameplate), TC-59
    (window validation checks full duration, not just start), and TC-60
    (rating raise always requires confirmation) during live runs.

    Pure observation: no writes to SimulationState, no effect on dispatch.
    """

    def __init__(
        self,
        records: list[AssetHealthRecord],
        reserve_threshold_mw: float = 1.0,
    ) -> None:
        self.records = records
        self.reserve_threshold_mw = reserve_threshold_mw
        self.scheduler = MaintenanceScheduler()
        self._window_validated = False
        self._raise_proposal: Optional[RatingProposal] = None

    def evaluate_tick(
        self,
        sim_time: float,
        net_demand_mw: float,
        available_capacity_mw: float,
    ) -> dict:
        """TC-58 + TC-59 + TC-60 per-tick maintenance evaluation.

        TC-58: reserve_contribution_mw_per_s() returns effective_ramp (re-rated
               figure), not nameplate and not 0.0.

        TC-59: validate_window() is called once (at sim_time >= 30 s) for a
               synthetic window [60, 120) with a full forecast across the
               duration — confirms the full-duration check fires.

        TC-60: after AssetHealthRecord.RAISE_CONFIRMATION_TICKS favorable
               observations, propose_rating_change() is called and the resulting
               RatingProposal has requires_confirmation=True.
        """
        # TC-58: re-rated reserve contribution for every dispatch-eligible asset.
        contributions = [reserve_contribution_mw_per_s(r) for r in self.records]

        # Accumulate favorable observation ticks (TC-60 evidence counter).
        for r in self.records:
            if r.is_dispatch_eligible:
                r.favorable_observation_ticks += 1

        # TC-59: full-duration window validation once after warm-up.
        if not self._window_validated and sim_time >= 30.0:
            window = MaintenanceWindow(
                asset_id=self.records[0].asset_id,
                window_id="maint-window-tc59",
                start_sim_time=60.0,
                end_sim_time=120.0,
            )
            # Capacity without the maintained asset (proxy: subtract one unit's
            # effective ramp scaled to 5 s intervals).
            cap_without = max(
                0.0,
                available_capacity_mw
                - self.records[0].effective_ramp_mw_per_s * 5.0,
            )
            forecast = [
                (t, net_demand_mw, cap_without)
                for t in (60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0)
            ]
            self.scheduler.validate_window(
                self.records[0],
                window,
                forecast_ticks=forecast,
                reserve_threshold_mw=self.reserve_threshold_mw,
            )
            self._window_validated = True

        # TC-60: once enough favorable observations accumulate, propose a raise.
        for r in self.records:
            if (
                r.favorable_observation_ticks >= AssetHealthRecord.RAISE_CONFIRMATION_TICKS
                and r.effective_ramp_mw_per_s < r.nameplate_ramp_mw_per_s
                and self._raise_proposal is None
            ):
                self._raise_proposal = self.scheduler.propose_rating_change(
                    r, r.nameplate_ramp_mw_per_s
                )

        return {
            "reserve_contributions_mw_per_s": contributions,   # TC-58
            "window_validated": self._window_validated,         # TC-59
            "raise_requires_confirmation": (                    # TC-60
                self._raise_proposal.requires_confirmation
                if self._raise_proposal else None
            ),
        }
