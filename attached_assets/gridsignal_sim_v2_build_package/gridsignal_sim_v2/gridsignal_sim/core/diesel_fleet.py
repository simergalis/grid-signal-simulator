"""Addendum H diesel fleet coordination.

The coordinator owns diesel fleet state and consumes a caller-supplied gap.
The live simulation supplies that gap from evaluate_tick(), while dispatch
arbitration remains responsible for turbines and BESS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping, Optional

from .asset_modules import DieselModule
from .models import DieselState


@dataclass(frozen=True)
class DieselInsufficientStartAlert:
    """One advisory event emitted when the active target cannot be met."""

    episode_id: str
    sim_time: float
    shortfall_mw: float


@dataclass(frozen=True)
class DieselFleetSnapshot:
    """Observable standalone diesel fleet state after one coordinator step."""

    state: str
    episode_id: Optional[str]
    synchronised_count: int
    n_active: int
    n_standby_available: int
    n_out_of_service: int
    output_mw: float
    shortfall_mw: float
    fuel_remaining_gal: float
    fuel_runtime_hours_remaining: Optional[float]
    time_in_state_s: float
    insufficient_start_alert_fired: bool


@dataclass
class DieselFleetCoordinator:
    """Coordinate a diesel unit list without touching live dispatch arithmetic."""

    diesel_units: list[DieselModule]
    n_active: Optional[int] = None
    unit_rating_mw: Optional[float] = None
    debounce_s: float = 1.0
    restore_hold_s: float = 300.0
    fuel_burn_gal_per_hr_per_unit_at_full_load: float = 230.0
    min_fuel_runtime_hours: float = 48.0

    fleet_state: str = field(default="idle", init=False)
    episode_id: Optional[str] = field(default=None, init=False)
    fuel_remaining_gal: float = field(init=False)
    v_fuel_required_gal: float = field(init=False)
    insufficient_start_alert_fired: bool = field(default=False, init=False)
    insufficient_start_alerts: list[DieselInsufficientStartAlert] = field(
        default_factory=list,
        init=False,
    )
    _episode_sequence: int = field(default=0, init=False)
    _activation_sim_time: float = field(default=0.0, init=False)
    _positive_gap_s: float = field(default=0.0, init=False)
    _restore_elapsed_s: float = field(default=0.0, init=False)
    _handled_failed_starts: set[str] = field(default_factory=set, init=False)
    _cooldown_until_s: float = field(default=math.nan, init=False)
    _last_sim_time: float = field(default=0.0, init=False)
    _state_since_sim_time: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        if self.debounce_s < 0.0 or self.restore_hold_s < 0.0:
            raise ValueError("diesel debounce and restore hold must not be negative")
        if self.fuel_burn_gal_per_hr_per_unit_at_full_load < 0.0:
            raise ValueError("diesel fuel burn must not be negative")
        if self.min_fuel_runtime_hours < 0.0:
            raise ValueError("diesel minimum fuel runtime must not be negative")

        primary_count = sum(unit.role == "primary" for unit in self.diesel_units)
        self.n_active = primary_count if self.n_active is None else self.n_active
        if self.n_active < 0:
            raise ValueError("diesel n_active must not be negative")
        if self.n_active > len(self.diesel_units):
            raise ValueError("diesel n_active cannot exceed diesel unit count")

        if self.unit_rating_mw is None:
            self.unit_rating_mw = (
                self.diesel_units[0].config.rated_mw
                if self.diesel_units
                else 0.0
            )
        if self.unit_rating_mw < 0.0:
            raise ValueError("diesel unit rating must not be negative")

        self.v_fuel_required_gal = (
            self.n_active
            * self.fuel_burn_gal_per_hr_per_unit_at_full_load
            * self.min_fuel_runtime_hours
        )
        self.fuel_remaining_gal = self.v_fuel_required_gal

    @property
    def synchronised_count(self) -> int:
        return sum(
            unit.state == DieselState.SYNCHRONISED
            for unit in self.diesel_units
        )

    @property
    def output_mw(self) -> float:
        """Aggregate measured output from synchronised diesel units."""
        return sum(
            (
                unit.output_mw()
                for unit in self.diesel_units
                if unit.state == DieselState.SYNCHRONISED
            ),
            0.0,
        )

    @property
    def standby_available_count(self) -> int:
        """Count standby units that can accept a start at the current time."""
        return sum(
            unit.role == "standby" and unit.can_start(self._last_sim_time)
            for unit in self.diesel_units
        )

    @property
    def out_of_service_count(self) -> int:
        return sum(
            unit.state == DieselState.OUT_OF_SERVICE
            for unit in self.diesel_units
        )

    @property
    def fuel_runtime_hours_remaining(self) -> Optional[float]:
        """Full-load hours remaining for the configured active target."""
        burn_rate = (
            (self.n_active or 0)
            * self.fuel_burn_gal_per_hr_per_unit_at_full_load
        )
        if burn_rate <= 0.0 or not self.diesel_units:
            return None
        return self.fuel_remaining_gal / burn_rate

    @property
    def shortfall_mw(self) -> float:
        return max(
            0.0,
            (self.n_active - self.synchronised_count)
            * (self.unit_rating_mw or 0.0),
        )

    def snapshot(self) -> DieselFleetSnapshot:
        return DieselFleetSnapshot(
            state=self.fleet_state,
            episode_id=self.episode_id,
            synchronised_count=self.synchronised_count,
            n_active=self.n_active or 0,
            n_standby_available=self.standby_available_count,
            n_out_of_service=self.out_of_service_count,
            output_mw=self.output_mw,
            shortfall_mw=self.shortfall_mw
            if self.fleet_state == "insufficient_start"
            else 0.0,
            fuel_remaining_gal=self.fuel_remaining_gal,
            fuel_runtime_hours_remaining=self.fuel_runtime_hours_remaining,
            time_in_state_s=max(
                0.0,
                self._last_sim_time - self._state_since_sim_time,
            ),
            insufficient_start_alert_fired=self.insufficient_start_alert_fired,
        )

    def step(
        self,
        gap_mw: float,
        sim_time: float,
        dt_seconds: float,
        *,
        success_overrides: Optional[Mapping[str, bool]] = None,
    ) -> DieselFleetSnapshot:
        """Advance units and coordinate one synthetic-gap fleet tick.

        ``gap_mw`` is intentionally caller-supplied.  The live simulation
        provides the pre-diesel remaining gap without making this coordinator
        read dispatch arithmetic.
        """
        if dt_seconds < 0.0:
            raise ValueError("diesel fleet dt_seconds must not be negative")
        self._last_sim_time = sim_time

        for unit in self.diesel_units:
            unit.advance(sim_time, dt_seconds)
        self._consume_fuel(dt_seconds)
        self._complete_cooldown_if_ready(sim_time)

        if gap_mw > 0.0:
            self._positive_gap_s += dt_seconds
        else:
            self._positive_gap_s = 0.0

        if self.episode_id is None:
            if (
                gap_mw > 0.0
                and self._positive_gap_s >= self.debounce_s
                and math.isnan(self._cooldown_until_s)
            ):
                self._begin_episode(sim_time)
            else:
                self._update_rollup()
                return self.snapshot()

        if gap_mw > 0.0:
            self._restore_elapsed_s = 0.0
            if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
                for unit in self.diesel_units:
                    unit.resume_from_unloading()
            if self.fleet_state != "insufficient_start":
                self._start_due_primary_units(
                    sim_time,
                    success_overrides or {},
                )
        else:
            if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
                self._restore_elapsed_s += dt_seconds
            elif any(unit.state == DieselState.SYNCHRONISED for unit in self.diesel_units):
                self._begin_unloading(sim_time)
                self._restore_elapsed_s += dt_seconds

            if (
                self._restore_elapsed_s >= self.restore_hold_s
                and any(unit.state == DieselState.UNLOADING for unit in self.diesel_units)
            ):
                self._finish_unloading(sim_time)

        self._handle_failed_starts(sim_time, success_overrides or {})
        self._update_insufficient_start(sim_time)
        self._update_rollup()
        return self.snapshot()

    def _begin_episode(self, sim_time: float) -> None:
        self._episode_sequence += 1
        self.episode_id = f"diesel-episode-{self._episode_sequence}"
        self._activation_sim_time = sim_time
        self._restore_elapsed_s = 0.0
        self._handled_failed_starts.clear()
        self.insufficient_start_alert_fired = False
        self.insufficient_start_alerts.clear()
        self.fleet_state = "starting"
        self._state_since_sim_time = sim_time

    def _start_due_primary_units(
        self,
        sim_time: float,
        success_overrides: Mapping[str, bool],
    ) -> None:
        for unit in self.diesel_units:
            if unit.role != "primary" or unit.start_attempted:
                continue
            offset = max(0.0, unit.start_offset_s or 0.0)
            if sim_time - self._activation_sim_time < offset:
                continue
            unit.command_start(
                sim_time,
                success_override=success_overrides.get(unit.asset_id),
            )

    def _handle_failed_starts(
        self,
        sim_time: float,
        success_overrides: Mapping[str, bool],
    ) -> None:
        for failed in self.diesel_units:
            if (
                failed.state != DieselState.FAILED_START
                or failed.asset_id in self._handled_failed_starts
            ):
                continue
            self._handled_failed_starts.add(failed.asset_id)

            if self.synchronised_count >= (self.n_active or 0):
                continue

            replacement = next(
                (
                    unit
                    for unit in self.diesel_units
                    if unit.role == "standby"
                    and unit.can_start(sim_time)
                ),
                None,
            )
            if replacement is not None:
                replacement.command_start(
                    sim_time,
                    success_override=success_overrides.get(replacement.asset_id),
                )

    def _update_insufficient_start(self, sim_time: float) -> None:
        if self.episode_id is None or self.synchronised_count >= (self.n_active or 0):
            return
        if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
            return
        if any(unit.state == DieselState.STARTING for unit in self.diesel_units):
            return
        standby_available = any(
            unit.role == "standby" and unit.can_start(sim_time)
            for unit in self.diesel_units
        )
        if standby_available or self.insufficient_start_alert_fired:
            return

        self.insufficient_start_alert_fired = True
        self.insufficient_start_alerts.append(
            DieselInsufficientStartAlert(
                episode_id=self.episode_id,
                sim_time=sim_time,
                shortfall_mw=self.shortfall_mw,
            )
        )

    def _begin_unloading(self, sim_time: float) -> None:
        for unit in self.diesel_units:
            if unit.state == DieselState.SYNCHRONISED:
                unit.command_stop(sim_time)

    def _finish_unloading(self, sim_time: float) -> None:
        for unit in self.diesel_units:
            unit.complete_unloading(sim_time)
        cooldowns = [
            unit.config.min_down_s
            for unit in self.diesel_units
            if unit.state == DieselState.OFFLINE
        ]
        self._cooldown_until_s = (
            sim_time + max(cooldowns, default=0.0)
            if cooldowns
            else math.nan
        )

    def _complete_cooldown_if_ready(self, sim_time: float) -> None:
        if math.isnan(self._cooldown_until_s) or sim_time < self._cooldown_until_s:
            return
        if not all(unit.state == DieselState.OFFLINE for unit in self.diesel_units):
            return

        for unit in self.diesel_units:
            unit.reset_for_new_episode()
        self.episode_id = None
        self._cooldown_until_s = math.nan
        self._positive_gap_s = 0.0
        self._restore_elapsed_s = 0.0
        self._handled_failed_starts.clear()
        self.insufficient_start_alert_fired = False
        self.insufficient_start_alerts.clear()

    def _consume_fuel(self, dt_seconds: float) -> None:
        dt_hours = dt_seconds / 3600.0
        if dt_hours <= 0.0:
            return
        consumed_gal = 0.0
        for unit in self.diesel_units:
            if unit.state != DieselState.SYNCHRONISED:
                continue
            if unit.config.rated_mw <= 0.0:
                continue
            load_fraction = max(
                0.0,
                min(1.0, unit.output_mw() / unit.config.rated_mw),
            )
            consumed_gal += (
                load_fraction
                * self.fuel_burn_gal_per_hr_per_unit_at_full_load
                * dt_hours
            )
        self.fuel_remaining_gal = max(
            0.0,
            self.fuel_remaining_gal - consumed_gal,
        )

    def _update_rollup(self) -> None:
        previous_state = self.fleet_state
        if any(unit.state == DieselState.UNLOADING for unit in self.diesel_units):
            next_state = "unloading"
        elif not math.isnan(self._cooldown_until_s):
            next_state = "cooldown"
        elif self.insufficient_start_alert_fired and self.shortfall_mw > 0.0:
            next_state = "insufficient_start"
        elif any(unit.state == DieselState.STARTING for unit in self.diesel_units):
            next_state = "starting"
        elif self.synchronised_count >= (self.n_active or 0) and (self.n_active or 0) > 0:
            next_state = "sustaining"
        elif self.episode_id is not None:
            next_state = "starting"
        else:
            next_state = "idle"

        self.fleet_state = next_state
        if next_state != previous_state:
            self._state_since_sim_time = self._last_sim_time