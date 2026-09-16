"""Forecast-driven turbine commitment for Addendum H Phase 2a.

This module owns policy only. Turbine state changes still pass through
RunContext's production operator-command drain so the controller cannot create
a second turbine state machine.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from core.asset_modules import TurbineState


ALLOWED_FORECAST_LEAD_SECONDS = (0.0, 150.0, 300.0, 600.0, 1200.0)
DEFAULT_FORECAST_LEAD_SECONDS = 600.0
DEFAULT_BACKGROUND_WINDOW_SECONDS = 900.0
DEFAULT_HOT_START_LOOKAHEAD_SECONDS = 300.0
DEFAULT_RAMP_TO_LOAD_SECONDS = 60.0
DEFAULT_STOP_LOOKAHEAD_SECONDS = 1200.0
DEFAULT_FLOOR_SYNCHRONIZED = 1
DEFAULT_SENSITIVITY_MW = 2.0
DEFAULT_BESS_ALLOWANCE_SOC_THRESHOLD = 0.50


@dataclass(frozen=True)
class CommitmentForecast:
    sim_time_s: float
    background_mean_mw: float
    background_std_mw: float
    forecast_mw: float
    peak_forecast_mw: float
    minimum_forecast_mw: float
    profile: tuple[tuple[float, float], ...] = ()
    announced_event_ids: tuple[str, ...] = ()
    announced_workload_mw: float = 0.0

    def peak_over(self, horizon_seconds: float) -> float:
        end = self.sim_time_s + max(0.0, horizon_seconds)
        values = [mw for timestamp, mw in self.profile if timestamp <= end + 1e-9]
        return max(values, default=self.forecast_mw)

    def minimum_over(self, horizon_seconds: float) -> float:
        end = self.sim_time_s + max(0.0, horizon_seconds)
        values = [mw for timestamp, mw in self.profile if timestamp <= end + 1e-9]
        return min(values, default=self.forecast_mw)


@dataclass(frozen=True)
class CommitmentLogRecord:
    sim_time_s: float
    unit_id: str
    action: str
    thermal_tier: str
    reason: str
    forecast_mw: float
    peak_forecast_mw: float
    synchronized_capacity_mw: float
    bess_soc_fraction: float
    accepted: bool = True
    changed_state: bool = False
    source: str = "forecast_commitment"
    refusal_reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sim_time_s": round(self.sim_time_s, 3),
            "unit_id": self.unit_id,
            "action": self.action,
            "thermal_tier": self.thermal_tier,
            "reason": self.reason,
            "forecast_mw": round(self.forecast_mw, 4),
            "peak_forecast_mw": round(self.peak_forecast_mw, 4),
            "synchronized_capacity_mw": round(self.synchronized_capacity_mw, 4),
            "bess_soc_fraction": round(self.bess_soc_fraction, 6),
            "accepted": self.accepted,
            "changed_state": self.changed_state,
            "source": self.source,
            "refusal_reason": self.refusal_reason,
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
    bess_allowance_soc_threshold_fraction: float = (
        DEFAULT_BESS_ALLOWANCE_SOC_THRESHOLD
    )
    log: list[CommitmentLogRecord] = field(default_factory=list)
    forecast_history: list[CommitmentForecast] = field(default_factory=list)
    constraint_violation_reasons: list[str] = field(default_factory=list)
    _pending_request_keys: set[tuple[str, str]] = field(default_factory=set, repr=False)
    _cascade_release_ticks: set[int] = field(default_factory=set, repr=False)
    _observed_start_counts: dict[str, int] = field(default_factory=dict, repr=False)

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

    @staticmethod
    def _event_type(event: Any) -> str:
        return getattr(event.event_type, "value", str(event.event_type))

    @staticmethod
    def _is_load_event(event: Any) -> bool:
        return ForecastDrivenTurbineController._event_type(event) in {
            "starting",
            "running",
            "scale",
        }

    def _event_power_mw(
        self,
        event: Any,
        power_for_event: Callable[[Any], float],
    ) -> float:
        if not self._is_load_event(event):
            return 0.0
        return max(0.0, float(power_for_event(event)))

    def _job_state_at(
        self,
        *,
        timestamp: float,
        events: list[Any],
        power_for_event: Callable[[Any], float],
    ) -> dict[str, tuple[float, str, float]]:
        """Return one target-power entry per active job at ``timestamp``.

        Processing events into a job map, rather than summing event powers,
        prevents overlapping STARTING/SCALE records for one job from being
        double-counted. Matching JOB_END records remove the job for all later
        profile samples.
        """
        state: dict[str, tuple[float, str, float]] = {}
        for event in sorted(events, key=lambda item: (item.timestamp, item.event_id)):
            if event.timestamp > timestamp:
                break
            event_type = self._event_type(event)
            if event_type in {"starting", "running", "scale"}:
                state[event.job_id] = (
                    self._event_power_mw(event, power_for_event),
                    str(event.event_id),
                    float(event.timestamp),
                )
            elif event_type in {
                "job_end",
                "cancelled",
                "job_failed",
                "job_timeout",
                "job_preempted",
            }:
                state.pop(event.job_id, None)
        return state

    def _announced_start_times(
        self,
        *,
        sim_time_s: float,
        events: list[Any],
    ) -> dict[str, float]:
        cutoff = sim_time_s + self.forecast_lead_seconds
        starts: dict[str, float] = {}
        for event in sorted(events, key=lambda item: (item.timestamp, item.event_id)):
            if self._event_type(event) not in {"starting", "running"}:
                continue
            if event.timestamp <= cutoff:
                starts[event.job_id] = min(
                    starts.get(event.job_id, float("inf")),
                    float(event.timestamp),
                )
        return starts

    def _background_samples(
        self,
        *,
        sim_time_s: float,
        events: list[Any],
        measured_history: list[tuple[float, float]],
        power_for_event: Callable[[Any], float],
        cooling_fraction: float,
    ) -> list[float]:
        """Remove known scripted/running load from measured site demand.

        The remainder is the measured background. It is only derived from
        timestamps already in history, so this subtraction does not introduce
        future information into the controller.
        """
        samples: list[float] = []
        window_start = sim_time_s - self.background_window_seconds
        for timestamp, value in measured_history:
            if not window_start <= timestamp < sim_time_s:
                continue
            job_state = self._job_state_at(
                timestamp=timestamp,
                events=events,
                power_for_event=power_for_event,
            )
            scripted = sum(power for power, _, _ in job_state.values())
            scripted *= 1.0 + max(0.0, cooling_fraction)
            samples.append(max(0.0, float(value) - scripted))
        return samples

    def forecast(
        self,
        *,
        sim_time_s: float,
        events: list[Any],
        measured_history: list[tuple[float, float]],
        power_for_event: Callable[[Any], float],
        cooling_fraction: float = 0.0,
        horizon_seconds: Optional[float] = None,
        step_seconds: float = 5.0,
    ) -> CommitmentForecast:
        """Build a no-look-ahead, time-profiled site-demand forecast."""
        samples = self._background_samples(
            sim_time_s=sim_time_s,
            events=events,
            measured_history=measured_history,
            power_for_event=power_for_event,
            cooling_fraction=cooling_fraction,
        )
        mean = statistics.fmean(samples) if samples else 0.0
        std = statistics.pstdev(samples) if len(samples) > 1 else 0.0
        background = max(0.0, mean + std)
        horizon = (
            self.stop_lookahead_seconds
            if horizon_seconds is None
            else max(0.0, float(horizon_seconds))
        )
        announced_starts = self._announced_start_times(
            sim_time_s=sim_time_s,
            events=events,
        )
        profile: list[tuple[float, float]] = []
        point_count = max(1, int(math.ceil(horizon / max(step_seconds, 0.1))))
        for index in range(point_count + 1):
            timestamp = min(sim_time_s + index * step_seconds, sim_time_s + horizon)
            job_state = self._job_state_at(
                timestamp=timestamp,
                events=events,
                power_for_event=power_for_event,
            )
            announced_power = sum(
                power
                for job_id, (power, _, _) in job_state.items()
                if job_id in announced_starts
            )
            total = background + announced_power * (1.0 + max(0.0, cooling_fraction))
            profile.append((timestamp, total))

        current = profile[0][1] if profile else background
        peak = max((value for _, value in profile), default=current)
        minimum = min((value for _, value in profile), default=current)
        announced_ids = tuple(
            event.event_id
            for event in sorted(events, key=lambda item: (item.timestamp, item.event_id))
            if self._event_type(event) in {"starting", "running"}
            and event.job_id in announced_starts
            and event.timestamp == announced_starts[event.job_id]
        )
        announced_workload = max(
            (
                sum(
                    power
                    for job_id, (power, _, _) in self._job_state_at(
                        timestamp=timestamp,
                        events=events,
                        power_for_event=power_for_event,
                    ).items()
                    if job_id in announced_starts
                )
                for timestamp, _ in profile
            ),
            default=0.0,
        )
        result = CommitmentForecast(
            sim_time_s=sim_time_s,
            background_mean_mw=mean,
            background_std_mw=std,
            forecast_mw=current,
            peak_forecast_mw=peak,
            minimum_forecast_mw=minimum,
            profile=tuple(profile),
            announced_event_ids=announced_ids,
            announced_workload_mw=announced_workload,
        )
        self.forecast_history.append(result)
        return result

    @staticmethod
    def _synchronized_capacity(turbines: list[Any]) -> float:
        return sum(
            max(0.0, float(turbine.config.rated_mw))
            for turbine in turbines
            if turbine.is_on_bus
        )

    def _bess_allowance(self, bess_units: list[Any]) -> tuple[float, float]:
        """Return bridgeable BESS MW and the conservative SoC reading.

        The SoC threshold controls whether the allowance is counted. It is
        intentionally separate from the BESS's 1 MW grid-forming anchor
        reserve, which is a power-limit constraint.
        """
        if not bess_units:
            return 0.0, 0.0
        soc = min(float(getattr(unit, "soc_fraction", 0.0)) for unit in bess_units)
        if soc < self.bess_allowance_soc_threshold_fraction:
            return 0.0, soc
        allowance = sum(
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
        return allowance, soc

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
        synchronized = [
            turbine for turbine in turbines
            if turbine.state == TurbineState.SYNCHRONISED
        ]
        return max(
            synchronized,
            key=lambda turbine: (
                -float(getattr(turbine, "_run_start_s", float("-inf")))
                if math.isnan(float(getattr(turbine, "_run_start_s", float("nan"))))
                else float(getattr(turbine, "_run_start_s")),
                turbine.config.asset_id,
            ),
            default=None,
        )

    def evaluate(
        self,
        *,
        ctx: Any,
        power_for_event: Callable[[Any], float],
    ) -> CommitmentForecast | None:
        if not self.enabled:
            return None
        cooling_fraction = float(getattr(ctx.sim_state.site, "alpha_max", 0.0))
        forecast = self.forecast(
            sim_time_s=ctx.sim_time,
            events=ctx.events,
            measured_history=ctx._measured_site_demand_history,
            power_for_event=power_for_event,
            cooling_fraction=cooling_fraction,
            horizon_seconds=self.stop_lookahead_seconds,
        )
        turbines = ctx.sim_state.turbines
        synchronized = [turbine for turbine in turbines if turbine.is_on_bus]
        synchronized_capacity = self._synchronized_capacity(turbines)
        bess_allowance, soc = self._bess_allowance(ctx.sim_state.bess_units)

        if self.mode == "baseline":
            if len([t for t in synchronized if t.state == TurbineState.SYNCHRONISED]) < 3:
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

        start_horizon = self.hot_start_lookahead_seconds + self.ramp_to_load_seconds
        start_peak = forecast.peak_over(start_horizon)
        if start_peak > synchronized_capacity + bess_allowance:
            candidate = self._candidate_start(turbines)
            if candidate is not None:
                self._queue(
                    ctx,
                    candidate,
                    "trip" if candidate.config.hot_standby else "start",
                    (
                        "forecast peak exceeds synchronized capacity plus BESS "
                        f"allowance over {start_horizon:.0f}s"
                    ),
                    forecast,
                    synchronized_capacity,
                    soc,
                )
            return forecast

        if len([t for t in synchronized if t.state == TurbineState.SYNCHRONISED]) <= self.floor_synchronized:
            return forecast
        candidate = self._candidate_stop(turbines)
        if candidate is None:
            return forecast

        stop_peak = forecast.peak_over(self.stop_lookahead_seconds)
        stop_minimum = forecast.minimum_over(self.stop_lookahead_seconds)
        remaining = [
            turbine for turbine in synchronized
            if turbine is not candidate
        ]
        remaining_capacity = sum(
            max(0.0, float(turbine.config.rated_mw))
            for turbine in remaining
        )
        remaining_msl = sum(
            max(0.0, float(turbine.config.p_min_stable_frac))
            * max(0.0, float(turbine.config.rated_mw))
            for turbine in remaining
        )

        if stop_peak > remaining_capacity + bess_allowance + self.sensitivity_mw:
            self._refused(
                ctx=ctx,
                turbine=candidate,
                action="stop",
                reason="stop refused: unit is needed within 1,200s",
                forecast=forecast,
                synchronized_capacity=synchronized_capacity,
                soc=soc,
            )
        elif remaining_msl > stop_minimum + self.sensitivity_mw:
            self._refused(
                ctx=ctx,
                turbine=candidate,
                action="stop",
                reason="stop refused: remaining units would over-generate",
                forecast=forecast,
                synchronized_capacity=synchronized_capacity,
                soc=soc,
            )
        elif (
            candidate.config.min_run_enabled
            and not math.isnan(float(getattr(candidate, "_run_start_s", float("nan"))))
            and ctx.sim_time - candidate._run_start_s < candidate.config.t_min_run_s
        ):
            self._refused(
                ctx=ctx,
                turbine=candidate,
                action="stop",
                reason="stop refused: minimum run time has not elapsed",
                forecast=forecast,
                synchronized_capacity=synchronized_capacity,
                soc=soc,
            )
        else:
            self._queue(
                ctx,
                candidate,
                "stop",
                (
                    "forecast peak and minimum support controlled stop over "
                    f"{self.stop_lookahead_seconds:.0f}s"
                ),
                forecast,
                synchronized_capacity,
                soc,
            )
        return forecast

    def _metadata(
        self,
        *,
        turbine: Any,
        action: str,
        reason: str,
        forecast: CommitmentForecast,
        synchronized_capacity: float,
        soc: float,
    ) -> dict[str, Any]:
        thermal_state = getattr(
            turbine,
            "_thermal_state",
            getattr(getattr(turbine, "config", None), "initial_thermal_state", "unknown"),
        )
        return {
            "thermal_tier": getattr(thermal_state, "value", str(thermal_state)),
            "reason": reason,
            "forecast_mw": forecast.forecast_mw,
            "peak_forecast_mw": forecast.peak_forecast_mw,
            "synchronized_capacity_mw": synchronized_capacity,
            "bess_soc_fraction": soc,
            "action": action,
        }

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
        metadata = self._metadata(
            turbine=turbine,
            action=action,
            reason=reason,
            forecast=forecast,
            synchronized_capacity=synchronized_capacity,
            soc=soc,
        )
        ctx.enqueue_unit_command(
            turbine.config.asset_id,
            action,
            source="forecast_commitment",
            metadata={"controller": self, **metadata},
        )

    def _refused(
        self,
        *,
        ctx: Any,
        turbine: Any,
        action: str,
        reason: str,
        forecast: CommitmentForecast,
        synchronized_capacity: float,
        soc: float,
    ) -> None:
        self.command_result(
            {
                "unit_id": turbine.config.asset_id,
                "action": action,
                "sim_time_s": ctx.sim_time,
                "source": "forecast_commitment",
                **self._metadata(
                    turbine=turbine,
                    action=action,
                    reason=reason,
                    forecast=forecast,
                    synchronized_capacity=synchronized_capacity,
                    soc=soc,
                ),
            },
            accepted=False,
            changed_state=False,
            refusal_reason=reason,
        )

    def command_result(
        self,
        metadata: dict[str, Any],
        *,
        accepted: bool,
        changed_state: bool = False,
        refusal_reason: Optional[str] = None,
    ) -> None:
        key = (
            metadata.get("unit_id", ""),
            metadata.get("requested_action", metadata.get("action", "")),
        )
        self._pending_request_keys.discard(key)
        action = str(metadata.get("action", ""))
        self.log.append(
            CommitmentLogRecord(
                sim_time_s=float(metadata.get("sim_time_s", 0.0)),
                unit_id=str(metadata.get("unit_id", "")),
                action=action,
                thermal_tier=str(metadata.get("thermal_tier", "unknown")),
                reason=str(metadata.get("reason", "")),
                forecast_mw=float(metadata.get("forecast_mw", 0.0)),
                peak_forecast_mw=float(
                    metadata.get("peak_forecast_mw", metadata.get("forecast_mw", 0.0))
                ),
                synchronized_capacity_mw=float(
                    metadata.get("synchronized_capacity_mw", 0.0)
                ),
                bess_soc_fraction=float(metadata.get("bess_soc_fraction", 0.0)),
                accepted=accepted,
                changed_state=changed_state,
                source=str(metadata.get("source", "forecast_commitment")),
                refusal_reason=refusal_reason or metadata.get("refusal_reason"),
            )
        )

    def record_command_result(
        self,
        *,
        metadata: dict[str, Any],
        accepted: bool,
        changed_state: bool,
        refusal_reason: Optional[str],
    ) -> None:
        """Record controller, operator, cascade, and other command outcomes."""
        self.command_result(
            metadata,
            accepted=accepted,
            changed_state=changed_state,
            refusal_reason=refusal_reason,
        )

    def record_tick(self, ctx: Any, result: Any) -> None:
        """Record hard constraints, cascade releases, and start reconciliation."""
        for unit in ctx.sim_state.bess_units:
            if getattr(unit.config, "grid_forming", False):
                allowed = max(
                    0.0,
                    float(unit.config.rated_mw) - float(unit.config.p_anchor_reserve_mw),
                )
                actual = max(0.0, float(getattr(unit, "_current_output_mw", 0.0)))
                if actual > allowed + 1e-6:
                    self.constraint_violation_reasons.append(
                        f"bess_anchor_reserve_power:{result.sim_time_seconds:.1f}s:"
                        f"{actual:.6f}>{allowed:.6f}MW"
                    )

        if (
            getattr(result, "contingency_release_alert", False)
            and result.tick_index not in self._cascade_release_ticks
        ):
            self._cascade_release_ticks.add(result.tick_index)
            release_id = getattr(result, "contingency_release_turbine_id", None)
            forecast = self.forecast_history[-1] if self.forecast_history else None
            self.log.append(
                CommitmentLogRecord(
                    sim_time_s=float(result.sim_time_seconds),
                    unit_id=str(release_id or "unknown"),
                    action="release",
                    thermal_tier="automatic",
                    reason="automatic contingency cascade release",
                    forecast_mw=float(forecast.forecast_mw if forecast else 0.0),
                    peak_forecast_mw=float(
                        forecast.peak_forecast_mw if forecast else 0.0
                    ),
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
                    accepted=True,
                    changed_state=True,
                    source="automatic_contingency",
                )
            )

        # Detect starts that entered through an existing production path rather
        # than through the forecast controller's command queue.
        for turbine in ctx.sim_state.turbines:
            current = int(getattr(turbine, "_start_count", 0))
            logged = sum(
                1
                for record in self.log
                if record.unit_id == turbine.config.asset_id
                and record.action in {"start", "release"}
                and record.accepted
                and record.changed_state
            )
            previous = self._observed_start_counts.get(turbine.config.asset_id, 0)
            if current > logged and current > previous:
                for _ in range(current - max(logged, previous)):
                    self.log.append(
                        CommitmentLogRecord(
                            sim_time_s=float(result.sim_time_seconds),
                            unit_id=turbine.config.asset_id,
                            action="start",
                            thermal_tier=getattr(
                                getattr(
                                    turbine,
                                    "_thermal_state",
                                    getattr(
                                        turbine.config,
                                        "initial_thermal_state",
                                        "unknown",
                                    ),
                                ),
                                "value",
                                str(
                                    getattr(
                                        turbine,
                                        "_thermal_state",
                                        getattr(
                                            turbine.config,
                                            "initial_thermal_state",
                                            "unknown",
                                        ),
                                    )
                                ),
                            ),
                            reason="production start not initiated by forecast controller",
                            forecast_mw=float(
                                self.forecast_history[-1].forecast_mw
                                if self.forecast_history
                                else 0.0
                            ),
                            peak_forecast_mw=float(
                                self.forecast_history[-1].peak_forecast_mw
                                if self.forecast_history
                                else 0.0
                            ),
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
                            accepted=True,
                            changed_state=True,
                            source="production",
                        )
                    )
            self._observed_start_counts[turbine.config.asset_id] = current

        expected = {
            turbine.config.asset_id: int(getattr(turbine, "_start_count", 0))
            for turbine in ctx.sim_state.turbines
        }
        actual = {
            unit_id: sum(
                1
                for record in self.log
                if record.unit_id == unit_id
                and record.action in {"start", "release"}
                and record.accepted
                and record.changed_state
            )
            for unit_id in expected
        }
        for unit_id, count in expected.items():
            if actual.get(unit_id, 0) != count:
                self.constraint_violation_reasons.append(
                    f"start_count_reconciliation:{unit_id}:"
                    f"asset={count}:log={actual.get(unit_id, 0)}"
                )

    @property
    def start_counts(self) -> dict[str, int]:
        return {
            unit_id: sum(
                1
                for record in self.log
                if record.unit_id == unit_id
                and record.action in {"start", "release"}
                and record.accepted
                and record.changed_state
            )
            for unit_id in sorted({record.unit_id for record in self.log})
        }

    @property
    def constraints_valid(self) -> bool:
        return not self.constraint_violation_reasons