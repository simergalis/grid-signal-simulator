"""Forecast-driven turbine commitment for Addendum H Phase 2a.

This module deliberately owns policy only.  Turbine state changes still pass
through RunContext's production operator-command drain so the controller cannot
create a second turbine state machine.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from core.asset_modules import TurbineState


# PROPOSED_HERE: policy defaults are configuration, not physics constants.
ALLOWED_FORECAST_LEAD_SECONDS = (0.0, 150.0, 300.0, 600.0, 1200.0)
DEFAULT_FORECAST_LEAD_SECONDS = 600.0
DEFAULT_BACKGROUND_WINDOW_SECONDS = 900.0
DEFAULT_HOT_START_LOOKAHEAD_SECONDS = 300.0
DEFAULT_RAMP_TO_LOAD_SECONDS = 60.0
DEFAULT_STOP_LOOKAHEAD_SECONDS = 1200.0
DEFAULT_FLOOR_SYNCHRONIZED = 1
DEFAULT_SENSITIVITY_MW = 2.0
DEFAULT_ANCHOR_RESERVE_SOC_FRACTION = 0.50


@dataclass(frozen=True)
class CommitmentForecast:
    sim_time_s: float
    background_mean_mw: float
    background_std_mw: float
    forecast_mw: float
    peak_forecast_mw: float
    announced_event_ids: tuple[str, ...] = ()
    announced_workload_mw: float = 0.0


@dataclass(frozen=True)
class CommitmentLogRecord:
    sim_time_s: float
    unit_id: str
    action: str
    thermal_tier: str
    reason: str
    forecast_mw: float
    synchronized_capacity_mw: float
    bess_soc_fraction: float
    accepted: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "sim_time_s": round(self.sim_time_s, 3),
            "unit_id": self.unit_id,
            "action": self.action,
            "thermal_tier": self.thermal_tier,
            "reason": self.reason,
            "forecast_mw": round(self.forecast_mw, 4),
            "synchronized_capacity_mw": round(self.synchronized_capacity_mw, 4),
            "bess_soc_fraction": round(self.bess_soc_fraction, 6),
            "accepted": self.accepted,
        }


@dataclass
class ForecastDrivenTurbineController:
    """Small deterministic policy controller evaluated once per simulation tick."""

    mode: str = "disabled"
    forecast_lead_seconds: float = DEFAULT_FORECAST_LEAD_SECONDS
    background_window_seconds: float = DEFAULT_BACKGROUND_WINDOW_SECONDS
    hot_start_lookahead_seconds: float = DEFAULT_HOT_START_LOOKAHEAD_SECONDS
    ramp_to_load_seconds: float = DEFAULT_RAMP_TO_LOAD_SECONDS
    stop_lookahead_seconds: float = DEFAULT_STOP_LOOKAHEAD_SECONDS
    floor_synchronized: int = DEFAULT_FLOOR_SYNCHRONIZED
    sensitivity_mw: float = DEFAULT_SENSITIVITY_MW
    anchor_reserve_soc_fraction: float = DEFAULT_ANCHOR_RESERVE_SOC_FRACTION
    log: list[CommitmentLogRecord] = field(default_factory=list)
    forecast_history: list[CommitmentForecast] = field(default_factory=list)
    constraint_violation_reasons: list[str] = field(default_factory=list)
    _pending_request_keys: set[tuple[str, str]] = field(default_factory=set, repr=False)
    _cascade_release_ticks: set[int] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.mode not in {"disabled", "baseline", "informed"}:
            raise ValueError("turbine commitment mode must be disabled, baseline, or informed")
        if self.forecast_lead_seconds not in ALLOWED_FORECAST_LEAD_SECONDS:
            raise ValueError(
                "forecast lead must be one of 0, 150, 300, 600, or 1,200 seconds"
            )
        self.floor_synchronized = max(1, int(self.floor_synchronized))
        self.sensitivity_mw = max(0.0, float(self.sensitivity_mw))

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    def _event_power_mw(
        self,
        event: Any,
        power_for_event: Callable[[Any], float],
    ) -> float:
        event_type = getattr(event.event_type, "value", str(event.event_type))
        if event_type not in {"starting", "running", "scale"}:
            return 0.0
        return max(0.0, float(power_for_event(event)))

    def forecast(
        self,
        *,
        sim_time_s: float,
        events: list[Any],
        measured_history: list[tuple[float, float]],
        power_for_event: Callable[[Any], float],
    ) -> CommitmentForecast:
        """Build a no-look-ahead forecast from measured history and announced events."""
        window_start = sim_time_s - self.background_window_seconds
        samples = [
            value for timestamp, value in measured_history
            if window_start <= timestamp < sim_time_s
        ]
        mean = statistics.fmean(samples) if samples else 0.0
        std = statistics.pstdev(samples) if len(samples) > 1 else 0.0
        background = mean + std

        announced = [
            event for event in events
            if event.timestamp >= sim_time_s
            and event.timestamp - self.forecast_lead_seconds <= sim_time_s
        ]
        workload_mw = sum(self._event_power_mw(event, power_for_event) for event in announced)
        forecast_mw = background + workload_mw
        # The controller is deliberately bounded to its configured lead horizon.
        peak = forecast_mw
        self.forecast_history.append(
            CommitmentForecast(
                sim_time_s=sim_time_s,
                background_mean_mw=mean,
                background_std_mw=std,
                forecast_mw=forecast_mw,
                peak_forecast_mw=peak,
                announced_event_ids=tuple(event.event_id for event in announced),
                announced_workload_mw=workload_mw,
            )
        )
        return self.forecast_history[-1]

    @staticmethod
    def _synchronized_capacity(turbines: list[Any]) -> float:
        return sum(
            max(0.0, float(turbine.config.rated_mw))
            for turbine in turbines
            if turbine.state == TurbineState.SYNCHRONISED
        )

    def _bess_headroom(self, bess_units: list[Any]) -> tuple[float, float]:
        """Return power above anchor reserve and the most conservative SoC."""
        if not bess_units:
            return 0.0, 0.0
        soc = min(float(getattr(unit, "soc_fraction", 0.0)) for unit in bess_units)
        if soc < self.anchor_reserve_soc_fraction:
            return 0.0, soc
        headroom = sum(
            max(
                0.0,
                float(unit.config.rated_mw)
                - (
                    float(getattr(unit.config, "p_anchor_reserve_mw", 0.0))
                    if getattr(unit.config, "grid_forming", False)
                    else 0.0
                ),
            )
            for unit in bess_units
            if not getattr(unit, "tripped", False)
        )
        return headroom, soc

    def _candidate_start(self, turbines: list[Any]) -> Optional[Any]:
        standby = [
            turbine for turbine in turbines
            if turbine.state == TurbineState.OFFLINE
            and getattr(turbine.config, "hot_standby", False)
        ]
        if standby:
            return standby[0]
        offline = [
            turbine for turbine in turbines
            if turbine.state == TurbineState.OFFLINE
            and not getattr(turbine.config, "hot_standby", False)
        ]
        return offline[0] if offline else None

    def _candidate_stop(self, turbines: list[Any]) -> Optional[Any]:
        running = [
            turbine for turbine in turbines
            if turbine.state == TurbineState.SYNCHRONISED
        ]
        return running[-1] if running else None

    def evaluate(
        self,
        *,
        ctx: Any,
        power_for_event: Callable[[Any], float],
    ) -> CommitmentForecast | None:
        if not self.enabled:
            return None
        forecast = self.forecast(
            sim_time_s=ctx.sim_time,
            events=ctx.events,
            measured_history=ctx._measured_site_demand_history,
            power_for_event=power_for_event,
        )
        turbines = ctx.sim_state.turbines
        synchronized = [
            turbine for turbine in turbines
            if turbine.state == TurbineState.SYNCHRONISED
        ]
        synchronized_capacity = self._synchronized_capacity(turbines)
        bess_headroom, soc = self._bess_headroom(ctx.sim_state.bess_units)

        if self.mode == "baseline":
            if len(synchronized) < 3:
                candidate = self._candidate_start(turbines)
                if candidate is not None:
                    self._queue(
                        ctx,
                        candidate,
                        "trip" if candidate.config.hot_standby else "start",
                        "baseline minimum synchronized floor",
                        forecast,
                        synchronized_capacity,
                        soc,
                    )
            return forecast

        start_threshold = synchronized_capacity + bess_headroom
        if forecast.peak_forecast_mw > start_threshold:
            candidate = self._candidate_start(turbines)
            if candidate is not None:
                self._queue(
                    ctx,
                    candidate,
                    "trip" if candidate.config.hot_standby else "start",
                    (
                        "forecast exceeds synchronized capacity plus BESS headroom "
                        f"over {self.hot_start_lookahead_seconds + self.ramp_to_load_seconds:.0f}s"
                    ),
                    forecast,
                    synchronized_capacity,
                    soc,
                )
        elif (
            len(synchronized) > self.floor_synchronized
            and forecast.peak_forecast_mw
            < synchronized_capacity - self.sensitivity_mw
        ):
            candidate = self._candidate_stop(turbines)
            if candidate is not None:
                self._queue(
                    ctx,
                    candidate,
                    "stop",
                    (
                        "forecast remains below synchronized capacity by more than "
                        f"{self.sensitivity_mw:.1f} MW over {self.stop_lookahead_seconds:.0f}s"
                    ),
                    forecast,
                    synchronized_capacity,
                    soc,
                )
        return forecast

    def _queue(
        self,
        ctx: Any,
        turbine: Any,
        action: str,
        reason: str,
        forecast: CommitmentForecast,
        synchronized_capacity: float,
        soc: float,
    ) -> None:
        key = (turbine.config.asset_id, action)
        if key in self._pending_request_keys:
            return
        self._pending_request_keys.add(key)
        ctx.enqueue_unit_command(
            turbine.config.asset_id,
            action,
            source="forecast_commitment",
            metadata={
                "controller": self,
                "thermal_tier": getattr(getattr(turbine, "thermal_state", None), "value", "unknown"),
                "reason": reason,
                "forecast_mw": forecast.peak_forecast_mw,
                "synchronized_capacity_mw": synchronized_capacity,
                "bess_soc_fraction": soc,
            },
        )

    def command_result(self, metadata: dict[str, Any], *, accepted: bool) -> None:
        key = (metadata.get("unit_id", ""), metadata.get("action", ""))
        self._pending_request_keys.discard(key)
        self.log.append(
            CommitmentLogRecord(
                sim_time_s=float(metadata.get("sim_time_s", 0.0)),
                unit_id=str(metadata.get("unit_id", "")),
                action=str(metadata.get("action", "")),
                thermal_tier=str(metadata.get("thermal_tier", "unknown")),
                reason=str(metadata.get("reason", "")),
                forecast_mw=float(metadata.get("forecast_mw", 0.0)),
                synchronized_capacity_mw=float(
                    metadata.get("synchronized_capacity_mw", 0.0)
                ),
                bess_soc_fraction=float(metadata.get("bess_soc_fraction", 0.0)),
                accepted=accepted,
            )
        )

    def record_tick(self, ctx: Any, result: Any) -> None:
        """Record cascade misses and invalidate savings on hard violations."""
        unserved = float(getattr(result, "p_unserved_mw", 0.0) or 0.0)
        if unserved > 1e-6:
            self.constraint_violation_reasons.append(
                f"unserved_energy:{result.sim_time_seconds:.1f}s:{unserved:.4f}MW"
            )
        anchor_soc = [
            float(getattr(unit, "soc_fraction", 0.0))
            for unit in ctx.sim_state.bess_units
            if getattr(unit.config, "grid_forming", False)
        ]
        if anchor_soc and min(anchor_soc) < self.anchor_reserve_soc_fraction - 1e-9:
            self.constraint_violation_reasons.append(
                f"bess_anchor_reserve:{result.sim_time_seconds:.1f}s:"
                f"{min(anchor_soc):.6f}"
            )
        if (
            self.mode == "informed"
            and getattr(result, "contingency_release_alert", False)
            and result.tick_index not in self._cascade_release_ticks
        ):
            self._cascade_release_ticks.add(result.tick_index)
            release_id = getattr(result, "contingency_release_turbine_id", None)
            forecast = self.forecast_history[-1] if self.forecast_history else None
            self.log.append(
                CommitmentLogRecord(
                    sim_time_s=float(result.sim_time_seconds),
                    unit_id=str(release_id or "unknown"),
                    action="cascade_release",
                    thermal_tier="automatic",
                    reason="forecast miss: automatic contingency cascade release",
                    forecast_mw=float(forecast.peak_forecast_mw if forecast else 0.0),
                    synchronized_capacity_mw=self._synchronized_capacity(
                        ctx.sim_state.turbines
                    ),
                    bess_soc_fraction=min(
                        (
                            float(getattr(unit, "soc_fraction", 0.0))
                            for unit in ctx.sim_state.bess_units
                        ),
                        default=0.0,
                    ),
                )
            )

    @property
    def constraints_valid(self) -> bool:
        return not self.constraint_violation_reasons