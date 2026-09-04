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
from dataclasses import dataclass, field
from enum import Enum

from .asset_modules import AssetModule
from .site_parameters import value as catalogue_value


# This is deliberately resolved from the package's authoritative catalogue,
# rather than duplicated as a numeric literal in the block-array model.
DEFAULT_BLOCK_FUEL_CELL_HOT_START_S = float(
    catalogue_value("fuel_cell_hot_start_s")
)


@dataclass
class FuelSystemConfig:
    """Optional, deliberately simple common-manifold fuel model (G-2).

    Omission is significant: callers which do not author this object retain
    the G-1 ideal, infinite-volume, instantaneous-regulator behaviour.
    """
    supply_pressure_psig: float = 15.0
    minimum_block_inlet_pressure_psig: float = 12.0
    block_trip_pressure_psig: float = 9.5
    manifold_volume_ft3: float = 920.0
    regulator_time_constant_s: float = 2.0
    regulator_droop_fraction: float = 0.05
    distribution_loss_psi: float = 0.5
    maximum_supply_flow_scfm: float | None = None
    delivered_to_cell_time_constant_s: float = 3.0
    max_fuel_utilisation: float = 0.85
    provenance: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.supply_pressure_psig <= self.minimum_block_inlet_pressure_psig
                or self.minimum_block_inlet_pressure_psig <= self.block_trip_pressure_psig):
            raise ValueError("fuel pressure bands must satisfy supply > minimum > trip")
        if self.manifold_volume_ft3 <= 0 or self.regulator_time_constant_s <= 0:
            raise ValueError("manifold volume and regulator time constant must be positive")
        if self.delivered_to_cell_time_constant_s <= 0:
            raise ValueError("delivered-to-cell time constant must be positive")
        if not 0 < self.max_fuel_utilisation <= 1 or not 0 <= self.regulator_droop_fraction < 1:
            raise ValueError("fuel utilisation/droop fractions must be in range")
        if self.maximum_supply_flow_scfm is not None and self.maximum_supply_flow_scfm <= 0:
            raise ValueError("maximum_supply_flow_scfm must be positive when supplied")
        self.provenance = {**self.provenance,
            "supply_pressure_psig": "vendor_published",
            "minimum_block_inlet_pressure_psig": "vendor_published",
            "block_trip_pressure_psig": "proposed", "manifold_volume_ft3": "proposed",
            "regulator_time_constant_s": "proposed", "regulator_droop_fraction": "proposed",
            "distribution_loss_psi": "proposed", "maximum_supply_flow_scfm": "site_specific",
            "delivered_to_cell_time_constant_s": "proposed", "max_fuel_utilisation": "proposed"}


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


@dataclass
class BlockFuelCellConfig:
    """Configuration for one G-1 block-addressable fuel-cell unit."""

    asset_id: str
    block_rated_mw: float
    block_count: int
    initial_running_blocks: int = 0
    initial_hot_standby_blocks: int | None = None
    # requested_* is the G-2 public contract.  The old spelling remains an
    # input alias so saved G-1 scenarios and direct Python construction work.
    requested_commit_rate_blocks_per_s: float | None = None
    commit_rate_blocks_per_s: float | None = None
    decommit_rate_blocks_per_s: float = 1.0
    cold_start_s: float = 8.0 * 60.0 * 60.0
    warm_start_s: float = 4.0 * 60.0 * 60.0
    hot_start_s: float = DEFAULT_BLOCK_FUEL_CELL_HOT_START_S
    hot_standby: bool = True
    min_stable_frac: float = 0.5
    hot_standby_floor_blocks: int = 0
    dispatch_mechanism: str = "hybrid"
    readiness_dwell_s: float = 0.0
    # Per-input source labels supplied by FuelCellUnitSpec.  Kept with the
    # runtime configuration so telemetry never has to reconstruct provenance.
    provenance: dict[str, str] = field(default_factory=dict)
    # Appended to retain positional compatibility with the original G-1
    # configuration.  A supplied value is a cooling duration, not a start
    # duration; omitted legacy payloads use the compatibility fallback below.
    controlled_cooling_s: float | None = None
    # G-2 fuel and topology inputs. Group membership is addressing only.
    electrical_groups: list[tuple[str, int]] = field(default_factory=list)
    beginning_of_life_heat_rate_btu_per_kwh: float = 5811.0
    end_of_life_heat_rate_btu_per_kwh: float = 7127.0
    degradation_fraction: float = 0.5
    part_load_heat_rate_multiplier: float = 1.0
    gas_heating_value_btu_per_scf: float = 1030.0
    hot_standby_fuel_fraction: float = 0.10
    gas_price_usd_per_mmbtu: float | None = 5.0
    fuel_system: FuelSystemConfig | None = None

    def __post_init__(self) -> None:
        if not self.asset_id or self.block_rated_mw <= 0 or self.block_count < 1:
            raise ValueError("fuel-cell block asset_id, rating, and count must be valid")
        if self.initial_hot_standby_blocks is None:
            self.initial_hot_standby_blocks = (
                self.block_count - self.initial_running_blocks
            )
        if self.initial_running_blocks + self.initial_hot_standby_blocks > self.block_count:
            raise ValueError("initial block states cannot exceed block_count")
        if self.hot_standby_floor_blocks > self.block_count:
            raise ValueError("hot_standby_floor_blocks cannot exceed block_count")
        if self.requested_commit_rate_blocks_per_s is None:
            self.requested_commit_rate_blocks_per_s = (
                1.0 if self.commit_rate_blocks_per_s is None else self.commit_rate_blocks_per_s)
        if self.requested_commit_rate_blocks_per_s <= 0 or self.decommit_rate_blocks_per_s <= 0:
            raise ValueError("block commit/decommit rates must be positive")
        # Canonicalize the legacy member too; code outside this module used it.
        self.commit_rate_blocks_per_s = self.requested_commit_rate_blocks_per_s
        if min(self.cold_start_s, self.warm_start_s, self.hot_start_s) <= 0:
            raise ValueError("fuel-cell start durations must be positive")
        if self.controlled_cooling_s is not None and self.controlled_cooling_s <= 0:
            raise ValueError("controlled_cooling_s must be positive when supplied")
        if not self.hot_start_s <= self.warm_start_s <= self.cold_start_s:
            raise ValueError("expected hot_start_s <= warm_start_s <= cold_start_s")
        if not 0 <= self.min_stable_frac <= 1:
            raise ValueError("min_stable_frac must be between zero and one")
        if self.dispatch_mechanism not in {"discrete_blocks", "modulating", "hybrid"}:
            raise ValueError("unknown fuel-cell dispatch mechanism")
        if self.beginning_of_life_heat_rate_btu_per_kwh <= 0 or self.end_of_life_heat_rate_btu_per_kwh <= 0:
            raise ValueError("fuel-cell heat rates must be positive")
        if not 0 <= self.degradation_fraction <= 1 or self.part_load_heat_rate_multiplier <= 0:
            raise ValueError("fuel-cell degradation/multiplier invalid")
        if self.gas_heating_value_btu_per_scf <= 0 or self.hot_standby_fuel_fraction < 0:
            raise ValueError("fuel inputs must be non-negative with positive heating value")
        if self.gas_price_usd_per_mmbtu is not None and self.gas_price_usd_per_mmbtu < 0:
            raise ValueError("gas price must be non-negative")
        if not self.electrical_groups:
            self.electrical_groups = [("all_blocks", self.block_count)]
        if (sum(n for _, n in self.electrical_groups) != self.block_count
                or any(
                    not name.strip()
                    or not any(character.isalpha() for character in name)
                    or n <= 0
                    for name, n in self.electrical_groups
                )
                or len({name for name, _ in self.electrical_groups}) != len(self.electrical_groups)):
            raise ValueError(
                "electrical groups must have unique human-meaningful names, "
                "positive counts, and sum to block_count"
            )
        self.provenance = {
            **self.provenance,
            "beginning_of_life_heat_rate_btu_per_kwh": "vendor_published",
            "end_of_life_heat_rate_btu_per_kwh": "vendor_published",
            "degradation_fraction": "site_specific",
            "part_load_heat_rate_multiplier": "proposed",
            "gas_heating_value_btu_per_scf": "site_specific",
            "hot_standby_fuel_fraction": "proposed",
            "gas_price_usd_per_mmbtu": "site_specific",
        }
        if self.fuel_system is not None:
            self.provenance.update(self.fuel_system.provenance)

    @property
    def rated_mw(self) -> float:
        return self.block_rated_mw * self.block_count

    @property
    def cooling_duration_s(self) -> float:
        """Duration of the controlled hot-to-warm thermal transition.

        ``warm_start_s`` was used as this timer in the first G-1 model.  Keep
        that value as the compatibility fallback, while retaining it as the
        actual warm-start path below.
        """
        return (
            self.warm_start_s
            if self.controlled_cooling_s is None
            else self.controlled_cooling_s
        )


@dataclass
class _FuelCellBlock:
    state: FuelCellState
    timer_s: float = 0.0
    output_mw: float = 0.0
    dwell_s: float = 0.0
    # Off hardware can be thermally cold or retained at warm readiness.  HOT
    # is represented by HOT_STANDBY/RUNNING; retaining it here while cooling
    # makes the hot -> warm decay explicit.
    thermal_readiness: str = "cold"
    electrical_group_id: str = "all_blocks"
    tripped: bool = False


@dataclass
class BlockFuelCellArray(AssetModule):
    """G-1 block-level array with explicit thermal eligibility.

    ``available_mw`` intentionally counts RUNNING blocks only: cold, warming,
    and hot-standby hardware supplies neither dispatch capacity nor contingency
    reserve until it has completed its start/dwell transition.
    """

    config: BlockFuelCellConfig
    blocks: list[_FuelCellBlock] = field(default_factory=list)
    _load_following_target_mw: float | None = None
    _commit_credit: float = 0.0
    _decommit_credit: float = 0.0
    cumulative_fuel_mmbtu: float = 0.0
    cumulative_co2_tonnes: float = 0.0
    total_fuel_demand_scfm: float = 0.0
    hot_standby_parasitic_scfm: float = 0.0
    manifold_pressure_psig: float | None = None
    furthest_inlet_pressure_psig: float | None = None
    minimum_manifold_pressure_psig: float | None = None
    minimum_inlet_pressure_psig: float | None = None
    fuel_delivered_scfm: float = 0.0
    pressure_derated_block_count: int = 0
    utilisation_clamped_block_count: int = 0
    achieved_commit_rate_blocks_per_s: float = 0.0
    fuel_binding_constraint: str = "request"
    pressure_derate_alert: dict | None = None
    pressure_trip_alert: dict | None = None
    utilisation_clamp_alert: dict | None = None
    supply_limit_alert: dict | None = None
    _regulator_flow_scfm: float = 0.0
    _fuel_limited_capacity_mw: float | None = None

    def __post_init__(self) -> None:
        if not self.blocks:
            group_ids = [name for name, count in self.config.electrical_groups for _ in range(count)]
            self.blocks = [
                _FuelCellBlock(
                    FuelCellState.RUNNING if i < self.config.initial_running_blocks
                    else FuelCellState.HOT_STANDBY
                    if i < self.config.initial_running_blocks + self.config.initial_hot_standby_blocks
                    else FuelCellState.COLD,
                    output_mw=(
                        self._running_block_floor_mw
                        if i < self.config.initial_running_blocks else 0.0
                    ),
                    thermal_readiness=(
                        "hot"
                        if i < self.config.initial_running_blocks + self.config.initial_hot_standby_blocks
                        else "cold"
                    ),
                    electrical_group_id=group_ids[i],
                )
                for i in range(self.config.block_count)
            ]
        if self.config.fuel_system is not None and self.manifold_pressure_psig is None:
            self.manifold_pressure_psig = self.config.fuel_system.supply_pressure_psig
            self.furthest_inlet_pressure_psig = (
                self.manifold_pressure_psig - self.config.fuel_system.distribution_loss_psi)
            self.minimum_manifold_pressure_psig = self.manifold_pressure_psig
            self.minimum_inlet_pressure_psig = self.furthest_inlet_pressure_psig
            # Existing running plant is already in gas-flow equilibrium.  This
            # prevents an authored initial-running state being spuriously
            # starved solely because fuel-system telemetry was enabled.
            rate = self.effective_heat_rate_btu_per_kwh / self.config.gas_heating_value_btu_per_scf / 60.0
            initial = self.output_mw() * 1000.0 * rate
            initial += sum(b.state == FuelCellState.HOT_STANDBY for b in self.blocks) * self.config.block_rated_mw * 1000.0 * rate * self.config.hot_standby_fuel_fraction
            self._regulator_flow_scfm = (
                initial
                if self.config.fuel_system.maximum_supply_flow_scfm is None
                else min(
                    initial,
                    self.config.fuel_system.maximum_supply_flow_scfm,
                )
            )
            self.fuel_delivered_scfm = initial
            self._fuel_limited_capacity_mw = (
                self.config.block_rated_mw
                * sum(b.state == FuelCellState.RUNNING for b in self.blocks)
            )

    @property
    def asset_id(self) -> str:
        return self.config.asset_id

    @property
    def state(self) -> FuelCellState:
        # Retains the old module's scalar status API while favouring the state
        # that is currently producing.
        if any(b.state == FuelCellState.RUNNING for b in self.blocks):
            return FuelCellState.RUNNING
        if any(b.state == FuelCellState.WARMING for b in self.blocks):
            return FuelCellState.WARMING
        if any(b.state == FuelCellState.HOT_STANDBY for b in self.blocks):
            return FuelCellState.HOT_STANDBY
        if any(b.state == FuelCellState.CONTROLLED_COOLING for b in self.blocks):
            return FuelCellState.CONTROLLED_COOLING
        return FuelCellState.COLD

    @property
    def time_to_ready_s(self) -> float | None:
        timers = [b.timer_s for b in self.blocks if b.state == FuelCellState.WARMING]
        if timers:
            return min(timers)
        return 0.0 if any(b.state == FuelCellState.HOT_STANDBY for b in self.blocks) else None

    @property
    def available_mw(self) -> float:
        state_capacity_mw = self.config.block_rated_mw * sum(
            b.state == FuelCellState.RUNNING for b in self.blocks
        )
        if self.config.fuel_system is None:
            return state_capacity_mw
        return min(
            state_capacity_mw,
            max(0.0, self._fuel_limited_capacity_mw or 0.0),
        )

    def output_mw(self) -> float:
        return sum(b.output_mw for b in self.blocks)

    @property
    def effective_heat_rate_btu_per_kwh(self) -> float:
        cfg = self.config
        return (cfg.beginning_of_life_heat_rate_btu_per_kwh +
                (cfg.end_of_life_heat_rate_btu_per_kwh - cfg.beginning_of_life_heat_rate_btu_per_kwh)
                * cfg.degradation_fraction) * cfg.part_load_heat_rate_multiplier

    def fuel_telemetry(self) -> dict[str, float]:
        return {"total_fuel_demand_scfm": self.total_fuel_demand_scfm,
                "hot_standby_parasitic_scfm": self.hot_standby_parasitic_scfm,
                "cumulative_fuel_mmbtu": self.cumulative_fuel_mmbtu,
                "cumulative_co2_tonnes": self.cumulative_co2_tonnes}

    def trip(self, electrical_group_id: str | None = None) -> int:
        """Force addressed blocks cold; ordinary advance never revives them."""
        selected = [b for b in self.blocks if electrical_group_id is None or b.electrical_group_id == electrical_group_id]
        for block in selected:
            block.state, block.timer_s, block.dwell_s, block.output_mw, block.thermal_readiness = (
                FuelCellState.COLD, 0.0, 0.0, 0.0, "cold")
            block.tripped = True
        return len(selected)

    @property
    def _running_block_floor_mw(self) -> float:
        """Smallest physically valid output of one committed block."""
        if self.config.dispatch_mechanism == "discrete_blocks":
            return self.config.block_rated_mw
        return self.config.block_rated_mw * self.config.min_stable_frac

    @property
    def minimum_dispatchable_output_mw(self) -> float:
        """Current physical output floor of committed, running blocks."""
        return sum(
            self._running_block_floor_mw
            for block in self.blocks
            if block.state == FuelCellState.RUNNING
        )

    @property
    def commanded_output_mw(self) -> float:
        """Dispatch request, distinct from the rate/readiness-limited output."""
        return self.config.rated_mw if self._load_following_target_mw is None else self._load_following_target_mw

    def readiness_summary(self, fast_window_s: float) -> dict[str, float | int]:
        counts = {
            state.value: sum(block.state == state for block in self.blocks)
            for state in FuelCellState
        }
        # A running block's rated capacity is already installed on the bus; it
        # is not reserve.  Only the unused upward margin above its achieved
        # output can respond to the event.
        if self.config.fuel_system is None:
            running_headroom_mw = sum(
                max(0.0, self.config.block_rated_mw - block.output_mw)
                for block in self.blocks
                if block.state == FuelCellState.RUNNING
            )
        else:
            running_headroom_mw = max(0.0, self.available_mw - self.output_mw())
        # A standby block remains unavailable *now*.  It is fast reserve only
        # when its synchronisation and required dwell fit the event window.
        fast_hot = sum(
            block.state == FuelCellState.HOT_STANDBY
            and block.dwell_s == 0.0
            and self.config.hot_start_s + self.config.readiness_dwell_s <= fast_window_s
            for block in self.blocks
        )
        # A live manifold pressure or fuel-delivery constraint is common-mode:
        # additional blocks on that same manifold are not independent reserve.
        if (
            self.config.fuel_system is not None
            and (
                self.pressure_derate_alert is not None
                or self.pressure_trip_alert is not None
                or self.utilisation_clamp_alert is not None
                or self.supply_limit_alert is not None
            )
        ):
            fast_hot = 0
        # This is deliberately distinct from both available_now and
        # available_fast.  It describes the capacity of hardware that is
        # already thermally HOT and will close a dispatch deficit after its
        # outstanding hot-start transition.  Blocks already in that dwell are
        # included: they remain HOT_STANDBY until it completes.  It is not
        # event/contingency credit because neither idle nor synchronising
        # standby hardware is delivering power now.
        eventual_hot_closure = sum(
            block.state == FuelCellState.HOT_STANDBY
            for block in self.blocks
        )
        return {
            **counts,
            "available_now_mw": running_headroom_mw,
            "available_fast_mw": (
                running_headroom_mw + fast_hot * self.config.block_rated_mw
            ),
            "eventual_hot_closure_mw": (
                eventual_hot_closure * self.config.block_rated_mw
            ),
            "minimum_output_mw": self.minimum_dispatchable_output_mw,
        }

    def set_load_following_target_mw(self, target_mw: float) -> None:
        if not math.isfinite(target_mw):
            raise ValueError("fuel-cell load-following target must be finite")
        self._load_following_target_mw = max(0.0, min(self.config.rated_mw, target_mw))

    def command_start(self, sim_time: float) -> bool:
        del sim_time
        # Retained-warm hardware is deliberately selected first.  It follows
        # the warm-start path; genuinely cold hardware follows cold-start.
        cold = next(
            (
                b for b in self.blocks
                if not b.tripped
                and b.state == FuelCellState.COLD
                and b.thermal_readiness == "warm"
            ),
            None,
        )
        if cold is None:
            cold = next(
                (
                    b for b in self.blocks
                    if not b.tripped
                    and b.state == FuelCellState.COLD
                    and b.thermal_readiness == "cold"
                ),
                None,
            )
        if cold is None:
            return False
        cold.timer_s = (
            self.config.warm_start_s
            if cold.thermal_readiness == "warm"
            else self.config.cold_start_s
        )
        cold.state = FuelCellState.WARMING
        return True

    def command_run(self, sim_time: float) -> bool:
        del sim_time
        # A block already in its hot-start/readiness dwell is committed; do not
        # select and restart its timer on each dispatch tick.
        standby = next(
            (b for b in self.blocks
             if b.state == FuelCellState.HOT_STANDBY and b.dwell_s == 0.0),
            None,
        )
        if standby is None:
            return False
        # Hot standby still needs its configured hot-start synchronisation plus
        # any site-specific readiness dwell before it becomes dispatchable.
        standby.dwell_s = self.config.hot_start_s + self.config.readiness_dwell_s
        if standby.dwell_s == 0:
            standby.state = FuelCellState.RUNNING
            standby.output_mw = self._running_block_floor_mw
            standby.thermal_readiness = "hot"
        return True

    def command_stop(self, sim_time: float) -> bool:
        del sim_time
        running = [b for b in self.blocks if b.state == FuelCellState.RUNNING]
        if not running:
            return False
        block = running[-1]
        block.output_mw = 0.0
        if self.config.hot_standby and sum(b.state == FuelCellState.HOT_STANDBY for b in self.blocks) < self.config.hot_standby_floor_blocks:
            block.state = FuelCellState.HOT_STANDBY
            block.thermal_readiness = "hot"
        else:
            # Cooling is non-interruptible.  On completion the block is off
            # but retained warm, so its next start uses warm_start_s rather
            # than falling through the cold-start path.
            block.state = FuelCellState.CONTROLLED_COOLING
            block.timer_s = self.config.cooling_duration_s
            block.thermal_readiness = "hot"
        return True

    def _requested_running_blocks(self, target_mw: float) -> int:
        """Return the commitment implied by the selected physical mechanism.

        Discrete blocks are binary sources: any committed block produces its
        full rating.  Modulating hardware keeps all blocks online whenever it
        is requested, so its aggregate minimum is all block minimums.  Hybrid
        commitment selects only enough blocks to cover the request, then
        modulates those blocks.  Thus requests below a relevant stable floor
        intentionally produce that floor rather than an unreported fraction.
        """
        if target_mw <= 0.0:
            return 0
        blocks_to_cover_request = math.ceil(target_mw / self.config.block_rated_mw)
        if self.config.dispatch_mechanism == "modulating":
            return self.config.block_count
        return min(self.config.block_count, blocks_to_cover_request)

    @property
    def _committed_blocks(self) -> int:
        """Blocks producing now or already committed through hot-start dwell.

        A synchronising hot-standby block is an outstanding commitment, but it
        is deliberately not RUNNING: it has no output or contingency credit
        until the dwell completes.
        """
        return sum(
            block.state == FuelCellState.RUNNING
            or (
                block.state == FuelCellState.HOT_STANDBY
                and block.dwell_s > 0.0
            )
            for block in self.blocks
        )

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        del sim_time
        if dt_seconds < 0:
            raise ValueError("BlockFuelCellArray.advance() requires non-negative dt")
        target = self._load_following_target_mw
        if target is None:
            target = self.config.rated_mw
        wanted = self._requested_running_blocks(target)
        committed_before = self._committed_blocks
        running_before = sum(b.state == FuelCellState.RUNNING for b in self.blocks)
        productive_output_before = self.output_mw()
        # Commitment bandwidth is an interval-local physical rate, not stored
        # dispatch credit.  In particular, a settled baseline must not bank
        # unused starts and spend them at the next peak.  Dwell blocks count as
        # already committed so repeated ticks cannot over-command transitions.
        if self._committed_blocks >= wanted:
            self._commit_credit = 0.0
        else:
            self._commit_credit += self.config.commit_rate_blocks_per_s * dt_seconds
        while self._committed_blocks < wanted and self._commit_credit >= 1:
            if not self.command_run(0.0):
                if not self.command_start(0.0):
                    break
            self._commit_credit -= 1
        self._decommit_credit += self.config.decommit_rate_blocks_per_s * dt_seconds
        while sum(b.state == FuelCellState.RUNNING for b in self.blocks) > wanted and self._decommit_credit >= 1:
            if not self.command_stop(0.0):
                break
            self._decommit_credit -= 1
        # First complete every thermal transition.  Output allocation follows
        # in a separate pass so an interval-end snapshot cannot report a block
        # as RUNNING before that same block has been assigned its output.
        for block in self.blocks:
            if block.state in (FuelCellState.WARMING, FuelCellState.CONTROLLED_COOLING):
                block.timer_s = max(0.0, block.timer_s - dt_seconds)
                if block.timer_s == 0:
                    if block.state == FuelCellState.WARMING:
                        block.state = FuelCellState.HOT_STANDBY
                        block.thermal_readiness = "hot"
                    else:
                        block.state = FuelCellState.COLD
                        block.thermal_readiness = "warm"
            elif block.state == FuelCellState.HOT_STANDBY and block.dwell_s:
                block.dwell_s = max(0.0, block.dwell_s - dt_seconds)
                if block.dwell_s == 0:
                    block.state = FuelCellState.RUNNING
                    block.output_mw = self._running_block_floor_mw
                    block.thermal_readiness = "hot"

        running_blocks = [
            block for block in self.blocks
            if block.state == FuelCellState.RUNNING
        ]
        per_block_target = target / max(1, len(running_blocks))
        if self.config.dispatch_mechanism == "discrete_blocks":
            per_block_target = self.config.block_rated_mw
        for block in running_blocks:
            block.output_mw = max(
                self.config.block_rated_mw * self.config.min_stable_frac,
                min(self.config.block_rated_mw, per_block_target),
            )
        # Integrate once, at the interval-end state. HOT_STANDBY includes a
        # block in hot-start dwell by design.
        rate = self.effective_heat_rate_btu_per_kwh / self.config.gas_heating_value_btu_per_scf / 60.0
        running_scfm = self.output_mw() * 1000.0 * rate
        self.hot_standby_parasitic_scfm = sum(
            b.state == FuelCellState.HOT_STANDBY for b in self.blocks
        ) * self.config.block_rated_mw * 1000.0 * rate * self.config.hot_standby_fuel_fraction
        self.total_fuel_demand_scfm = running_scfm + self.hot_standby_parasitic_scfm
        used_mmbtu = (
            self.total_fuel_demand_scfm
            * dt_seconds
            / 60.0
            * self.config.gas_heating_value_btu_per_scf
            / 1_000_000.0
        )
        self.cumulative_fuel_mmbtu += used_mmbtu
        self.cumulative_co2_tonnes += used_mmbtu * 53.06 / 1000.0
        self.achieved_commit_rate_blocks_per_s = (
            max(0, self._committed_blocks - committed_before) / dt_seconds
            if dt_seconds else 0.0
        )
        if self.config.fuel_system is not None:
            self._apply_fuel_system(
                target, dt_seconds, self.total_fuel_demand_scfm,
                productive_output_before, running_before, wanted, committed_before,
            )

    def _apply_fuel_system(self, demand_mw: float, dt_seconds: float,
                           pre_hydraulic_total_scfm: float,
                           productive_output_before: float,
                           running_before: int, wanted_blocks: int,
                           committed_before: int) -> None:
        """Advance the coupled regulator/manifold/cell loop in small substeps.

        Gas inventory is ideal-gas standard cubic feet:
        C = V/14.7 [scf/psi], so dP/dt = (q_reg-q_cell)/C.  The regulator and
        cell delivery are first-order lags.  No fitted pressure constants are
        used; the only conversion is atmospheric pressure at standard volume.
        """
        cfg = self.config.fuel_system
        assert cfg is not None
        rate = self.effective_heat_rate_btu_per_kwh / cfg_or_hv(self.config) / 60.0
        demand_scfm = max(0.0, demand_mw) * 1000.0 * rate
        standby = self.hot_standby_parasitic_scfm
        command = demand_scfm + standby
        pressure = float(self.manifold_pressure_psig or cfg.supply_pressure_psig)
        # At least ten hydraulic evaluations per report interval, capped at
        # 100 ms to resolve the 2 s regulator without report-tick dependence.
        n = max(1, math.ceil(dt_seconds / 0.1))
        h = dt_seconds / n
        self.pressure_derate_alert = self.pressure_trip_alert = None
        self.utilisation_clamp_alert = self.supply_limit_alert = None
        self.minimum_manifold_pressure_psig = pressure
        self.minimum_inlet_pressure_psig = pressure - cfg.distribution_loss_psi
        tripped = False
        delivered_scf = 0.0
        for _ in range(n):
            inlet = pressure - cfg.distribution_loss_psi
            # A droop regulator requests more flow as outlet pressure falls.
            # With no finite supply rating there is no physical normalization
            # for droop; retaining the full pre-staged command exposes the
            # analytic first-order manifold transient instead of inventing an
            # unbounded pressure-feedback gain.  For a rated supply, droop is
            # bounded additional demand: q*=min(qmax, qcmd+qmax*droop*ΔP/Ps).
            requested_supply = command
            if cfg.maximum_supply_flow_scfm is not None:
                requested_supply += (
                    cfg.maximum_supply_flow_scfm * cfg.regulator_droop_fraction
                    * max(0.0, cfg.supply_pressure_psig - pressure)
                    / cfg.supply_pressure_psig
                )
                if requested_supply > cfg.maximum_supply_flow_scfm:
                    self.supply_limit_alert = {
                        "asset_id": self.asset_id, "maximum_supply_flow_scfm": cfg.maximum_supply_flow_scfm,
                        "requested_supply_flow_scfm": requested_supply}
                requested_supply = min(requested_supply, cfg.maximum_supply_flow_scfm)
            self._regulator_flow_scfm += (requested_supply - self._regulator_flow_scfm) * min(1.0, h / cfg.regulator_time_constant_s)
            # The cell's commanded draw has its own transport/chemical lag.
            # It is intentionally not made to follow regulator flow: the
            # resulting inventory difference is precisely the manifold
            # pressure transient the model exists to resolve.
            self.fuel_delivered_scfm += (command - self.fuel_delivered_scfm) * min(1.0, h / cfg.delivered_to_cell_time_constant_s)
            delivered_scf += self.fuel_delivered_scfm * h / 60.0
            # Manifold outflow is the commanded metering-valve draw.  Delivered
            # fuel is separately lagged for electrochemical power support; using
            # that delayed signal here would invent gas inventory during a load
            # step and erase the regulator transient.
            pressure += ((self._regulator_flow_scfm - command) / 60.0
                         * h / (cfg.manifold_volume_ft3 / 14.7))
            pressure = min(cfg.supply_pressure_psig, max(0.0, pressure))
            inlet_after = pressure - cfg.distribution_loss_psi
            self.minimum_manifold_pressure_psig = min(self.minimum_manifold_pressure_psig, pressure)
            self.minimum_inlet_pressure_psig = min(self.minimum_inlet_pressure_psig, inlet_after)
            # Latch the band event at the substep where it occurred.  It must
            # survive a later pressure recovery in the same report interval.
            if inlet_after < cfg.block_trip_pressure_psig and not tripped:
                tripped = True
                self.pressure_trip_alert = {
                    "common_mode": True, "asset_id": self.asset_id,
                    "affected_block_count": len(self.blocks),
                    "minimum_inlet_pressure_psig": inlet_after,
                    "minimum_block_inlet_pressure_psig": cfg.minimum_block_inlet_pressure_psig,
                    "block_trip_pressure_psig": cfg.block_trip_pressure_psig}
            elif inlet_after < cfg.minimum_block_inlet_pressure_psig and self.pressure_derate_alert is None:
                self.pressure_derate_alert = {
                    "common_mode": True, "asset_id": self.asset_id,
                    "affected_block_count": len(self.blocks),
                    "minimum_inlet_pressure_psig": inlet_after,
                    "minimum_block_inlet_pressure_psig": cfg.minimum_block_inlet_pressure_psig,
                    "block_trip_pressure_psig": cfg.block_trip_pressure_psig}
        inlet = pressure - cfg.distribution_loss_psi
        self.manifold_pressure_psig, self.furthest_inlet_pressure_psig = pressure, inlet
        for alert in (self.pressure_derate_alert, self.pressure_trip_alert):
            if alert is not None:
                alert["minimum_inlet_pressure_psig"] = self.minimum_inlet_pressure_psig
        running = [b for b in self.blocks if b.state == FuelCellState.RUNNING]
        pressure_factor = 1.0
        if tripped:
            # This is one manifold common-mode event, not a collection of
            # independent component failures; do not set block.tripped.
            for block in self.blocks:
                block.state, block.timer_s, block.dwell_s, block.output_mw = (
                    FuelCellState.COLD, 0.0, 0.0, 0.0)
                block.thermal_readiness = "cold"
            running = []
            pressure_factor = 0.0
        elif self.pressure_derate_alert is not None:
            pressure_factor = ((self.minimum_inlet_pressure_psig - cfg.block_trip_pressure_psig) /
                               (cfg.minimum_block_inlet_pressure_psig - cfg.block_trip_pressure_psig))
        self.pressure_derated_block_count = len(running) if pressure_factor < 1 else 0
        # Heat-rate demand is fuel input at the configured operating point.
        # Utilisation = demanded_fuel / delivered_fuel; therefore enforcing
        # utilisation <= Umax gives Pmax=q_delivered/(scfm_per_mw * Umax).
        power_supporting_fuel_scfm = max(
            0.0, self.fuel_delivered_scfm - self.hot_standby_parasitic_scfm
        )
        supported_mw = (
            power_supporting_fuel_scfm
            / (1000.0 * rate * cfg.max_fuel_utilisation)
        )
        # Fuel may be pre-staged for the full target before electrical
        # synchronisation, but only RUNNING blocks can draw current.
        electrically_drawable_mw = min(
            demand_mw,
            len(running) * self.config.block_rated_mw,
        )
        desired_mw = electrically_drawable_mw * pressure_factor
        actual_mw = min(desired_mw, supported_mw)
        self._fuel_limited_capacity_mw = min(
            len(running) * self.config.block_rated_mw * pressure_factor,
            supported_mw,
        )
        self.utilisation_clamp_alert = (
            {"asset_id": self.asset_id, "demand_mw": desired_mw,
             "supported_mw": supported_mw, "max_fuel_utilisation": cfg.max_fuel_utilisation}
            if actual_mw + 1e-9 < desired_mw else None)
        self.utilisation_clamped_block_count = len(running) if self.utilisation_clamp_alert is not None else 0
        if not running:
            actual_mw = 0.0
        elif self.config.dispatch_mechanism == "discrete_blocks":
            # A binary block cannot claim a fractional electrical output.
            actual_mw = min(actual_mw, len(running) * self.config.block_rated_mw)
        per_block = actual_mw / len(running) if running else 0.0
        for block in running:
            block.output_mw = min(self.config.block_rated_mw, per_block)
        self.total_fuel_demand_scfm = command
        used = delivered_scf * cfg_or_hv(self.config) / 1_000_000.0
        # replace the optimistic pre-hydraulic accounting added by G-1 above.
        self.cumulative_fuel_mmbtu -= (
            pre_hydraulic_total_scfm * dt_seconds / 60.0 * cfg_or_hv(self.config) / 1_000_000.0)
        self.cumulative_fuel_mmbtu += used
        self.cumulative_co2_tonnes -= (
            pre_hydraulic_total_scfm * dt_seconds / 60.0 * cfg_or_hv(self.config) / 1_000_000.0) * 53.06 / 1000.0
        self.cumulative_co2_tonnes += used * 53.06 / 1000.0
        # Physical achievement counts only new productive electrical equivalent
        # blocks, never merely a RUNNING state transition.  Thus pressure and
        # utilisation starvation removes commitment credit.  The ideal G-1
        # branch above deliberately retains its historical state-count result.
        newly_running = max(0, sum(b.state == FuelCellState.RUNNING for b in self.blocks) - running_before)
        productive_equivalent = max(0.0, self.output_mw() - productive_output_before) / self.config.block_rated_mw
        achieved = (productive_equivalent / dt_seconds) if dt_seconds else 0.0
        achieved = min(achieved, newly_running / dt_seconds if dt_seconds else 0.0,
                       float(self.config.requested_commit_rate_blocks_per_s))
        self.achieved_commit_rate_blocks_per_s = achieved
        requested_starts = wanted_blocks > committed_before
        if self.pressure_trip_alert is not None:
            self.fuel_binding_constraint = "fuel_pressure"
        elif self.pressure_derate_alert is not None:
            self.fuel_binding_constraint = "fuel_pressure"
        elif self.utilisation_clamp_alert is not None:
            self.fuel_binding_constraint = "utilisation"
        elif (requested_starts
              and newly_running / dt_seconds + 1e-9 < float(self.config.requested_commit_rate_blocks_per_s)):
            self.fuel_binding_constraint = "thermal"
        else:
            self.fuel_binding_constraint = "request"


def cfg_or_hv(config: BlockFuelCellConfig) -> float:
    """Named helper keeps fuel equations explicit at their heating-value basis."""
    return config.gas_heating_value_btu_per_scf


@dataclass
class BlockFuelCellFleet:
    """Compatibility-shaped aggregate view over multiple block arrays."""

    arrays: list[BlockFuelCellArray]
    _target_mw: float | None = None

    @property
    def state(self) -> FuelCellState:
        return next(
            (a.state for a in self.arrays if a.state == FuelCellState.RUNNING),
            next((a.state for a in self.arrays if a.state == FuelCellState.WARMING),
                 FuelCellState.COLD),
        )

    @property
    def time_to_ready_s(self) -> float | None:
        values = [a.time_to_ready_s for a in self.arrays if a.time_to_ready_s is not None]
        return min(values) if values else None

    @property
    def available_mw(self) -> float:
        return sum(a.available_mw for a in self.arrays)

    @property
    def rated_mw(self) -> float:
        return sum(a.config.rated_mw for a in self.arrays)

    def output_mw(self) -> float:
        return sum(a.output_mw() for a in self.arrays)

    @property
    def total_fuel_demand_scfm(self) -> float:
        return sum(a.total_fuel_demand_scfm for a in self.arrays)

    @property
    def hot_standby_parasitic_scfm(self) -> float:
        return sum(a.hot_standby_parasitic_scfm for a in self.arrays)

    @property
    def manifold_pressure_psig(self) -> float | None:
        values = [a.manifold_pressure_psig for a in self.arrays if a.manifold_pressure_psig is not None]
        return min(values) if values else None

    @property
    def minimum_manifold_pressure_psig(self) -> float | None:
        values = [a.minimum_manifold_pressure_psig for a in self.arrays if a.minimum_manifold_pressure_psig is not None]
        return min(values) if values else None

    @property
    def minimum_inlet_pressure_psig(self) -> float | None:
        values = [a.minimum_inlet_pressure_psig for a in self.arrays if a.minimum_inlet_pressure_psig is not None]
        return min(values) if values else None

    @property
    def furthest_inlet_pressure_psig(self) -> float | None:
        values = [a.furthest_inlet_pressure_psig for a in self.arrays if a.furthest_inlet_pressure_psig is not None]
        return min(values) if values else None

    @property
    def fuel_delivered_scfm(self) -> float:
        return sum(a.fuel_delivered_scfm for a in self.arrays)

    @property
    def pressure_derated_block_count(self) -> int:
        return sum(a.pressure_derated_block_count for a in self.arrays)

    @property
    def utilisation_clamped_block_count(self) -> int:
        return sum(a.utilisation_clamped_block_count for a in self.arrays)

    @property
    def requested_commit_rate_blocks_per_s(self) -> float:
        return sum(float(a.config.requested_commit_rate_blocks_per_s) for a in self.arrays)

    @property
    def achieved_commit_rate_blocks_per_s(self) -> float:
        return sum(a.achieved_commit_rate_blocks_per_s for a in self.arrays)

    @property
    def fuel_binding_constraint(self) -> str:
        order = ("fuel_pressure", "utilisation", "thermal", "request")
        values = {a.fuel_binding_constraint for a in self.arrays}
        return next(item for item in order if item in values)

    @property
    def pressure_derate_alert(self) -> dict | None:
        return next((a.pressure_derate_alert for a in self.arrays if a.pressure_derate_alert is not None), None)

    @property
    def pressure_trip_alert(self) -> dict | None:
        return next((a.pressure_trip_alert for a in self.arrays if a.pressure_trip_alert is not None), None)

    @property
    def utilisation_clamp_alert(self) -> dict | None:
        return next((a.utilisation_clamp_alert for a in self.arrays if a.utilisation_clamp_alert is not None), None)

    @property
    def supply_limit_alert(self) -> dict | None:
        return next((a.supply_limit_alert for a in self.arrays if a.supply_limit_alert is not None), None)

    @property
    def cumulative_fuel_mmbtu(self) -> float:
        return sum(a.cumulative_fuel_mmbtu for a in self.arrays)

    @property
    def cumulative_co2_tonnes(self) -> float:
        return sum(a.cumulative_co2_tonnes for a in self.arrays)

    def trip(self, asset_id: str, electrical_group_id: str | None = None) -> int:
        for array in self.arrays:
            if array.asset_id == asset_id:
                return array.trip(electrical_group_id)
        return 0

    @property
    def commanded_output_mw(self) -> float:
        return self.rated_mw if self._target_mw is None else self._target_mw

    def readiness_summary(self, fast_window_s: float) -> dict[str, float | int]:
        result: dict[str, float | int] = {
            state.value: 0 for state in FuelCellState
        }
        result.update(
            available_now_mw=0.0,
            available_fast_mw=0.0,
            eventual_hot_closure_mw=0.0,
            minimum_output_mw=0.0,
        )
        for array in self.arrays:
            summary = array.readiness_summary(fast_window_s)
            for key, value in summary.items():
                result[key] += value
        return result

    @property
    def provenance(self) -> dict[str, dict[str, str]]:
        return {array.asset_id: dict(array.config.provenance) for array in self.arrays}

    def set_load_following_target_mw(self, target_mw: float) -> None:
        if not math.isfinite(target_mw):
            raise ValueError("fuel-cell load-following target must be finite")
        self._target_mw = max(0.0, min(self.rated_mw, target_mw))

    def advance(self, sim_time: float, dt_seconds: float) -> None:
        remaining = self.rated_mw if self._target_mw is None else self._target_mw
        for array in self.arrays:
            array.set_load_following_target_mw(min(array.config.rated_mw, remaining))
            array.advance(sim_time, dt_seconds)
            remaining = max(0.0, remaining - array.config.rated_mw)