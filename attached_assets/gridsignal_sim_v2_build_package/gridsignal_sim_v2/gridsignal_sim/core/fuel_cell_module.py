"""
Fuel-cell array asset module.

This module owns the SOFC array's thermal state and rate-limited output.  The
simulation loop reads its measured output but does not pass demand or dispatch
state into it.

The state machine models the thermal/chemical constraints that distinguish an
SOFC array from a mechanical turbine:

    COLD -> WARMING -> HOT_STANDBY -> RUNNING
                              ^           |
                              |           v
                         CONTROLLED_COOLING
                              |
                              v
                             COLD

Warming and controlled cooling are non-interruptible.  A running array never
operates below its minimum stable output; a request below that floor starts
controlled cooling instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from .asset_modules import AssetModule


class FuelCellState(str, Enum):
    """Thermal/operational states for a fuel-cell array."""

    COLD = "cold"
    WARMING = "warming"
    HOT_STANDBY = "hot_standby"
    RUNNING = "running"
    CONTROLLED_COOLING = "controlled_cooling"


@dataclass
class FuelCellConfig:
    """Configuration for one aggregate SOFC array asset.

    ``ramp_rate_mw_per_s`` is intentionally a fuel-cell-specific parameter.
    It is not named or sourced as the turbine ``r_asset_mw_per_s`` value.
    The default is 0.02 MW/s, roughly one order of magnitude slower than the
    simulator's 0.2 MW/s turbine default.

    ``baseload_target_mw`` is fixed when the scenario is built.  It is not a
    runtime dispatch setpoint; the module only moves its measured output toward
    this target at the configured fuel-cell ramp rate.

    ``monitoring_only`` is stored here as contractual metadata.  Control-plane
    enforcement is deliberately deferred to a later phase.
    """

    asset_id: str
    rated_mw: float = 10.0
    ramp_rate_mw_per_s: float = 0.02
    ramp_down_rate_mw_per_s: float | None = None
    min_stable_frac: float = 0.50
    cold_start_s: float = 8.0 * 60.0 * 60.0
    controlled_cooling_s: float = 60.0 * 60.0
    min_setpoint_interval_s: float = 60.0 * 60.0
    monitoring_only: bool = False
    load_following: bool = False
    # Kept after the Phase 1 fields so existing positional construction remains
    # compatible while the target becomes fixed scenario configuration.
    baseload_target_mw: float | None = None

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("FuelCellConfig.asset_id must not be empty")
        if self.rated_mw <= 0.0:
            raise ValueError("FuelCellConfig.rated_mw must be greater than zero")
        if self.baseload_target_mw is None:
            self.baseload_target_mw = self.rated_mw
        if not math.isfinite(self.baseload_target_mw):
            raise ValueError(
                "FuelCellConfig.baseload_target_mw must be finite"
            )
        if not 0.0 <= self.baseload_target_mw <= self.rated_mw:
            raise ValueError(
                "FuelCellConfig.baseload_target_mw must be between zero and rated_mw"
            )
        if self.ramp_rate_mw_per_s <= 0.0:
            raise ValueError(
                "FuelCellConfig.ramp_rate_mw_per_s must be greater than zero"
            )
        if self.ramp_down_rate_mw_per_s is None:
            self.ramp_down_rate_mw_per_s = self.ramp_rate_mw_per_s
        if self.ramp_down_rate_mw_per_s <= 0.0:
            raise ValueError(
                "FuelCellConfig.ramp_down_rate_mw_per_s must be greater than zero"
            )
        if not 0.0 <= self.min_stable_frac <= 1.0:
            raise ValueError(
                "FuelCellConfig.min_stable_frac must be between zero and one"
            )
        if self.cold_start_s <= 0.0:
            raise ValueError(
                "FuelCellConfig.cold_start_s must be greater than zero"
            )
        if self.controlled_cooling_s <= 0.0:
            raise ValueError(
                "FuelCellConfig.controlled_cooling_s must be greater than zero"
            )
        if self.min_setpoint_interval_s < 0.0:
            raise ValueError(
                "FuelCellConfig.min_setpoint_interval_s must not be negative"
            )


@dataclass
class FuelCellModule(AssetModule):
    """Self-contained SOFC array state machine.

    The module has no connection to the existing scalar fuel-cell fields.  Its
    fixed baseload target is configuration; its output is local runtime state.
    """

    config: FuelCellConfig
    state: FuelCellState = FuelCellState.COLD
    _current_output_mw: float = 0.0
    _time_remaining_s: float = 0.0
    _load_following_target_mw: float | None = None

    def __post_init__(self) -> None:
        # A scenario may restore a thermal state without carrying transient
        # timer/output fields.  Establish the physically meaningful entry
        # point for that state rather than allowing the first tick to create
        # an unbounded jump to the stable floor.
        if self.state == FuelCellState.RUNNING and self._current_output_mw == 0.0:
            self._current_output_mw = self.min_stable_mw
        elif self.state == FuelCellState.WARMING and self._time_remaining_s == 0.0:
            self._time_remaining_s = self.config.cold_start_s
        elif (
            self.state == FuelCellState.CONTROLLED_COOLING
            and self._time_remaining_s == 0.0
        ):
            self._time_remaining_s = self.config.controlled_cooling_s

    @property
    def asset_id(self) -> str:
        return self.config.asset_id

    @property
    def min_stable_mw(self) -> float:
        return self.config.min_stable_frac * self.config.rated_mw

    @property
    def target_output_mw(self) -> float:
        if self.config.load_following and self._load_following_target_mw is not None:
            return self._load_following_target_mw
        return float(self.config.baseload_target_mw)

    def set_load_following_target_mw(self, target_mw: float) -> None:
        """Update the runtime demand target for a load-following array."""
        if not self.config.load_following:
            return
        if not math.isfinite(target_mw):
            raise ValueError("fuel-cell load-following target must be finite")
        self._load_following_target_mw = max(
            0.0,
            min(self.config.rated_mw, target_mw),
        )

    @property
    def time_remaining_s(self) -> float:
        """Remaining warming or controlled-cooling time."""
        return self._time_remaining_s

    @property
    def time_to_ready_s(self) -> float | None:
        """Remaining time until the array is hot enough to run."""
        if self.state == FuelCellState.WARMING:
            return self._time_remaining_s
        if self.state == FuelCellState.HOT_STANDBY:
            return 0.0
        return None

    def command_start(self, sim_time: float) -> bool:
        """Begin the non-interruptible cold-start sequence.

        Only a cold array can be started.  A warming or cooling array cannot be
        interrupted, and a hot-standby array is already ready.
        """
        del sim_time  # Reserved for the later event/audit integration.
        if self.state != FuelCellState.COLD:
            return False

        self._current_output_mw = 0.0
        self._time_remaining_s = self.config.cold_start_s
        self.state = FuelCellState.WARMING
        return True

    def command_run(self, sim_time: float) -> bool:
        """Move hot standby into running operation at the stable-load floor."""
        del sim_time  # Reserved for the later event/audit integration.
        if self.state != FuelCellState.HOT_STANDBY:
            return False

        if self.target_output_mw < self.min_stable_mw:
            return False

        # The transition out of hot standby establishes the stable operating
        # floor.  All subsequent RUNNING output changes are rate-limited.
        self._current_output_mw = self.min_stable_mw
        self.state = FuelCellState.RUNNING
        return True

    def command_stop(self, sim_time: float) -> bool:
        """Begin non-interruptible controlled cooling from a hot state."""
        del sim_time  # Reserved for the later event/audit integration.
        if self.state not in (
            FuelCellState.HOT_STANDBY,
            FuelCellState.RUNNING,
        ):
            return False

        self._current_output_mw = 0.0
        self._time_remaining_s = self.config.controlled_cooling_s
        self.state = FuelCellState.CONTROLLED_COOLING
        return True

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        """Advance warming, cooling, or chemically rate-limited output."""
        del sim_time  # Reserved for later event/audit integration.
        if dt_seconds < 0.0:
            raise ValueError("FuelCellModule.advance() requires non-negative dt")

        if self.state == FuelCellState.WARMING:
            self._time_remaining_s = max(
                0.0,
                self._time_remaining_s - dt_seconds,
            )
            if self._time_remaining_s <= 0.0:
                self.state = FuelCellState.HOT_STANDBY
                self._current_output_mw = 0.0
            return

        if self.state == FuelCellState.CONTROLLED_COOLING:
            self._time_remaining_s = max(
                0.0,
                self._time_remaining_s - dt_seconds,
            )
            self._current_output_mw = 0.0
            if self._time_remaining_s <= 0.0:
                self.state = FuelCellState.COLD
            return

        if self.state != FuelCellState.RUNNING:
            self._current_output_mw = 0.0
            return

        if self.target_output_mw < self.min_stable_mw:
            self.command_stop(0.0)
            return

        delta_mw = self.target_output_mw - self._current_output_mw
        ramp_rate_mw_per_s = (
            self.config.ramp_rate_mw_per_s
            if delta_mw >= 0.0
            else float(self.config.ramp_down_rate_mw_per_s)
        )
        max_step_mw = ramp_rate_mw_per_s * dt_seconds
        step_mw = max(-max_step_mw, min(max_step_mw, delta_mw))
        self._current_output_mw = max(
            self.min_stable_mw,
            min(self.config.rated_mw, self._current_output_mw + step_mw),
        )

    def output_mw(self) -> float:
        return self._current_output_mw