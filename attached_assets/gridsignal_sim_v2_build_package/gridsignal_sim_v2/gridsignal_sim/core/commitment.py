"""core/commitment.py — Phase A: commitment decision structures (no wiring).

Phase A deliverables (DR-2026-08-06 §7.1.3, Phase A spec):
  CommitmentConfig      — operational thresholds, all read from the catalogue.
  SustainedCondition    — durable hysteresis timer for commit/decommit conditions.
  PendingStartRegister  — tracks the one unit currently in its start sequence.
  CommitmentDecision    — immutable output from evaluate_commitment().
  evaluate_commitment() — pure function; mutates only the two SustainedCondition
                          arguments; no I/O, no wall clock, no RNG.

NOT wired to any call site in Phase A.  Phase D wires evaluate_commitment()
into simulation_core.py and replaces the headroom block entirely.

Provenance notes (UC-1…UC-4)
-----------------------------
All eight thresholds carry CHOSEN provenance: none is validated against real
load data from the design partner.  UC-1 covers commit thresholds and timing;
UC-2 covers the decommit gap; UC-3 covers post-removal utilisation; UC-4
covers the 300 s decommit window and its 10× asymmetry.  Production deployments
should calibrate against commissioning data.

PROHIBITED (Phase A)
--------------------
  ─ Calling evaluate_commitment() from any production code path.
  ─ Writing any threshold as a code literal (all values read from catalogue).
  ─ Crediting PendingStartRegister contents toward capacity, reserve, headroom,
    or ramp figures — the pending unit is not yet on the bus.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from core.models import UnitAvailability


# ── CommitmentConfig ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommitmentConfig:
    """Operational thresholds for the commitment engine.

    ALL fields are read from the catalogue at construction time via
    CommitmentConfig.from_catalogue().  Writing any threshold as a code
    literal violates Guard D1 the moment the entry is catalogued.

    Spec ref: §7.1.3.3.  All thresholds are CHOSEN (UC-1…UC-4); no measured
    basis against this fleet class.

    Fields
    ------
    commit_utilisation        (0.80) Fleet U ≥ this → start next unit.
    decommit_utilisation      (0.50) Fleet U ≤ this → consider stopping last unit.
    decommit_post_removal_max (0.70) U_without_candidate must not exceed this.
    commit_confirm_s          (30)   Commit condition must hold this long.
    decommit_confirm_s        (300)  Decommit condition must hold this long.
    inter_start_settle_s      (60)   Gap between consecutive start commands.
    levelled_off_epsilon_mw   (0.05) |output − setpoint| deadband for levelled-off.
    levelled_off_window_s     (10)   levelled_off must be sustained this long.
    """
    commit_utilisation: float           # UC-1
    decommit_utilisation: float         # UC-2
    decommit_post_removal_max: float    # UC-3
    commit_confirm_s: float             # UC-1
    decommit_confirm_s: float           # UC-4
    inter_start_settle_s: float         # UC-1
    levelled_off_epsilon_mw: float      # MW
    levelled_off_window_s: float        # s

    @classmethod
    def from_catalogue(cls) -> "CommitmentConfig":
        """Construct from the site_parameters catalogue.

        Raises core.site_parameters.ParameterNotCatalogued if any key is
        absent from gridsignal_parameters.json.  Fail fast — a missing key
        means a threshold was removed from the catalogue without updating this
        class, which is a programming error.
        """
        from core.site_parameters import value as _sp_value  # local import breaks circular
        return cls(
            commit_utilisation=_sp_value("commit_utilisation"),
            decommit_utilisation=_sp_value("decommit_utilisation"),
            decommit_post_removal_max=_sp_value("decommit_post_removal_max"),
            commit_confirm_s=float(_sp_value("commit_confirm_s")),
            decommit_confirm_s=float(_sp_value("decommit_confirm_s")),
            inter_start_settle_s=float(_sp_value("inter_start_settle_s")),
            levelled_off_epsilon_mw=_sp_value("levelled_off_epsilon_mw"),
            levelled_off_window_s=float(_sp_value("levelled_off_window_s")),
        )


# ── SustainedCondition ────────────────────────────────────────────────────────

@dataclass
class SustainedCondition:
    """Durable hysteresis timer for commit and decommit conditions.

    Tracks how long a condition has been continuously true.  Resets to 0.0
    on the first tick the condition is false.

    Design
    ------
    sustained_s  : accumulated seconds the condition has been continuously true.
    threshold_s  : minimum duration required before met is True.

    Not frozen — evaluate_commitment() mutates sustained_s per tick.
    No I/O, no wall clock; the caller passes dt_s and the boolean predicate.
    """
    sustained_s: float = 0.0
    threshold_s: float = 0.0

    def update(self, condition_true: bool, dt_s: float) -> None:
        """Advance by dt_s when the condition holds; reset to 0.0 otherwise."""
        if condition_true:
            self.sustained_s = self.sustained_s + dt_s
        else:
            self.sustained_s = 0.0

    @property
    def met(self) -> bool:
        """True when the condition has been sustained ≥ threshold_s seconds."""
        return self.sustained_s >= self.threshold_s


# ── PendingStartRegister ──────────────────────────────────────────────────────

@dataclass
class PendingStartRegister:
    """Tracks the unit currently in its start sequence.

    At most one unit may be in STARTING at any time (§7.1.3 sequential-start
    contract, D-05).  PendingStartRegister prevents the headroom check and
    evaluate_commitment() from issuing a second command_start() while a unit
    is still counting down to SYNCHRONISED.

    Design
    ------
    pending_unit_id      : asset_id of the unit in STARTING; None when empty.
    start_commanded_at_s : sim_time when command_start() was last issued.
                           math.nan when pending_unit_id is None.

    PROHIBITED: crediting the pending unit toward capacity, reserve, headroom,
    or ramp figures.  The unit is not yet on the bus and must not be counted.
    """
    pending_unit_id: Optional[str] = None
    start_commanded_at_s: float = field(default_factory=lambda: math.nan)

    def record_start(self, unit_id: str, sim_time: float) -> None:
        """Record that unit_id received command_start() at sim_time."""
        self.pending_unit_id = unit_id
        self.start_commanded_at_s = sim_time

    def clear_on_synchronised(self, unit_id: str) -> None:
        """Clear the register once the tracked unit reaches SYNCHRONISED.

        No-op if unit_id does not match pending_unit_id — tolerates out-of-order
        notifications without corrupting the register.
        """
        if self.pending_unit_id == unit_id:
            self.pending_unit_id = None
            self.start_commanded_at_s = math.nan

    @property
    def is_empty(self) -> bool:
        """True when no unit is currently in its start sequence."""
        return self.pending_unit_id is None

    def settled_at(self, sim_time: float, inter_start_settle_s: float) -> bool:
        """True once inter_start_settle_s has elapsed since the last start.

        Guards the next start command from issuing too soon after the previous
        unit was commanded to start.  Returns True when the register is empty,
        because no pending start means the settle interval is trivially satisfied.

        Note: the settle interval is measured from command issuance, not from
        the moment the unit reaches SYNCHRONISED.  Phase D will adjust if
        SYNCHRONISED-anchored timing is preferred after commissioning data is
        available.
        """
        if self.is_empty:
            return True
        return (sim_time - self.start_commanded_at_s) >= inter_start_settle_s


# ── CommitmentDecision ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommitmentDecision:
    """Immutable output from evaluate_commitment().

    action
    ------
    "commit"   Issue command_start() to target_unit_id.
    "decommit" Issue command_stop() to target_unit_id (Phase C adds command_stop).
    "hold"     No unit state change this tick.

    Fields
    ------
    action         : "commit" | "decommit" | "hold"
    target_unit_id : unit to start or stop; None when action == "hold".
    reason         : human-readable diagnostic for dashboard / run log.
    blocked_by     : non-empty when action == "hold" due to a blocking condition;
                     empty string otherwise.
    """
    action: str                    # "commit" | "decommit" | "hold"
    target_unit_id: Optional[str]  # None when action == "hold"
    reason: str                    # diagnostic string
    blocked_by: str = ""           # empty unless action == "hold" with a guard active


# ── evaluate_commitment ───────────────────────────────────────────────────────

def evaluate_commitment(
    on_bus: list[UnitAvailability],
    offline: list[UnitAvailability],
    p_demand_mw: float,
    pending: PendingStartRegister,
    commit_cond: SustainedCondition,
    decommit_cond: SustainedCondition,
    cfg: CommitmentConfig,
    dt_s: float,
    sim_time: float,
) -> CommitmentDecision:
    """Evaluate commitment state and return an action for this interval.

    Pure function — the ONLY side effects are mutating commit_cond.sustained_s
    and decommit_cond.sustained_s.  No I/O, no wall clock, no RNG.

    Parameters
    ----------
    on_bus        UnitAvailability snapshots for SYNCHRONISED units.
                  MUST be snapshots, never live TurbineModule references.
    offline       UnitAvailability snapshots for OFFLINE (startable) units.
    p_demand_mw   Current P_dispatch_required (turbine-side demand only).
    pending       PendingStartRegister — governs sequential-start guard.
                  Caller is responsible for calling pending.record_start() when
                  a "commit" decision is acted upon (Phase D wiring).
    commit_cond   Commit hysteresis timer — mutated by this call.
    decommit_cond Decommit hysteresis timer — mutated by this call.
    cfg           CommitmentConfig built from catalogue (no literals).
    dt_s          Interval duration in seconds (used to advance timers).
    sim_time      Interval start time in seconds (used for settled_at()).

    Algorithm
    ---------
    1. Reserve floor: Σ rated_on_bus ≥ p_demand_mw + max(rated_on_bus).
       Violation is always a commit trigger regardless of hysteresis.
    2. Utilisation U = p_demand_mw / Σ rated_on_bus.
    3. Commit trigger = floor_violated OR U ≥ cfg.commit_utilisation.
       Commit condition must be sustained cfg.commit_confirm_s.
       PendingStartRegister and settled_at() guard the actual commit action.
    4. Decommit trigger = all of: floor OK without candidate; U ≤ decommit_utilisation;
       U_without ≤ decommit_post_removal_max.  Decommit condition must be sustained
       cfg.decommit_confirm_s.  Applies to the last on_bus unit only.
    5. Where commit and decommit both trigger (not possible in the normal
       monotone case, but reachable with step changes), commit governs.
    """
    # ── Step 1 & 2: Reserve floor and utilisation ──────────────────────────
    on_bus_rated = [u.rated_mw for u in on_bus if not u.hot_standby]
    total_rated_mw = sum(on_bus_rated)
    largest_mw = max(on_bus_rated, default=0.0)
    floor_mw = p_demand_mw + largest_mw
    floor_violated = total_rated_mw < floor_mw

    # U = 0 when no units are on bus (avoids ZeroDivisionError; force commit below).
    utilisation = p_demand_mw / total_rated_mw if total_rated_mw > 0.0 else 0.0

    # ── Step 3: Commit path ────────────────────────────────────────────────
    commit_trigger = floor_violated or utilisation >= cfg.commit_utilisation
    commit_cond.update(commit_trigger, dt_s)

    if commit_cond.met and offline:
        # Guard A: at most one start sequence at a time.
        if not pending.is_empty:
            return CommitmentDecision(
                action="hold",
                target_unit_id=None,
                reason=f"commit condition met (U={utilisation:.3f}, floor_violated={floor_violated})",
                blocked_by=f"start pending for {pending.pending_unit_id!r}",
            )
        # Guard B: inter-start settle interval.
        if not pending.settled_at(sim_time, cfg.inter_start_settle_s):
            elapsed = sim_time - pending.start_commanded_at_s
            return CommitmentDecision(
                action="hold",
                target_unit_id=None,
                reason=f"commit condition met (U={utilisation:.3f}, floor_violated={floor_violated})",
                blocked_by=(
                    f"inter-start settle: {elapsed:.0f}/{cfg.inter_start_settle_s:.0f} s elapsed"
                ),
            )
        return CommitmentDecision(
            action="commit",
            target_unit_id=offline[0].unit_id,
            reason=(
                f"floor_violated={floor_violated}, U={utilisation:.3f}"
                f" ≥ {cfg.commit_utilisation}" if not floor_violated else
                f"reserve floor violated: {total_rated_mw:.1f} MW < {floor_mw:.1f} MW"
            ),
        )

    # ── Step 4: Decommit path ──────────────────────────────────────────────
    # Candidate: the last unit in on_bus (last-committed by convention).
    # Only attempt decommit when ≥1 unit is on bus and commit condition is not met.
    decommit_trigger = False
    decommit_candidate: Optional[UnitAvailability] = None

    if on_bus and not commit_cond.met:
        decommit_candidate = on_bus[-1]
        remaining_rated = [
            u.rated_mw for u in on_bus
            if u.unit_id != decommit_candidate.unit_id and not u.hot_standby
        ]
        remaining_total = sum(remaining_rated)
        remaining_largest = max(remaining_rated, default=0.0)
        floor_without = p_demand_mw + remaining_largest
        floor_ok_without = remaining_total >= floor_without
        u_without = (
            p_demand_mw / remaining_total if remaining_total > 0.0 else float("inf")
        )
        decommit_trigger = (
            not floor_violated
            and floor_ok_without
            and utilisation <= cfg.decommit_utilisation
            and u_without <= cfg.decommit_post_removal_max
        )

    decommit_cond.update(decommit_trigger, dt_s)

    if decommit_cond.met and decommit_candidate is not None:
        return CommitmentDecision(
            action="decommit",
            target_unit_id=decommit_candidate.unit_id,
            reason=(
                f"U={utilisation:.3f} ≤ {cfg.decommit_utilisation}, "
                f"U_without={u_without:.3f} ≤ {cfg.decommit_post_removal_max}"
            ),
        )

    # ── Step 5: Hold ───────────────────────────────────────────────────────
    return CommitmentDecision(
        action="hold",
        target_unit_id=None,
        reason=(
            f"U={utilisation:.3f}, floor_mw={floor_mw:.1f}, "
            f"total_rated={total_rated_mw:.1f}, "
            f"commit_sustained={commit_cond.sustained_s:.0f}/{cfg.commit_confirm_s:.0f} s, "
            f"decommit_sustained={decommit_cond.sustained_s:.0f}/{cfg.decommit_confirm_s:.0f} s"
        ),
    )
