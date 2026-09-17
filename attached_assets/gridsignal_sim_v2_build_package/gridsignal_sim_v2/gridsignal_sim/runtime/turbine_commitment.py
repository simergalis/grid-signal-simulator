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
DEFAULT_PRELOAD_MARGIN_SECONDS = 30.0


def summarize_unserved_ticks(
    ticks: list[Any],
    *,
    dt_seconds: float = 5.0,
) -> dict[str, Any]:
    """Return explicit unserved-energy, peak-power, and interval metrics.

    The simulator reports ``p_unserved_mw`` at interval end.  Energy is therefore
    the sum of each interval's positive power multiplied by the configured
    interval duration; it is never inferred from the run verdict.
    """
    dt_hours = max(0.0, float(dt_seconds)) / 3600.0
    energy_mwh = 0.0
    peak_mw = 0.0
    intervals: list[dict[str, float]] = []
    open_interval: Optional[dict[str, float]] = None
    for tick in ticks:
        value = (
            tick.get("p_unserved_mw", 0.0)
            if isinstance(tick, dict)
            else getattr(tick, "p_unserved_mw", 0.0)
        )
        sim_time = (
            tick.get("sim_time_seconds", 0.0)
            if isinstance(tick, dict)
            else getattr(tick, "sim_time_seconds", 0.0)
        )
        unserved_mw = max(0.0, float(value or 0.0))
        end_s = float(sim_time)
        start_s = end_s - max(0.0, float(dt_seconds))
        energy_mwh += unserved_mw * dt_hours
        peak_mw = max(peak_mw, unserved_mw)
        if unserved_mw > 1e-9:
            if open_interval is None:
                open_interval = {
                    "start_sim_time_s": start_s,
                    "end_sim_time_s": end_s,
                    "peak_unserved_mw": unserved_mw,
                }
            else:
                open_interval["end_sim_time_s"] = end_s
                open_interval["peak_unserved_mw"] = max(
                    open_interval["peak_unserved_mw"], unserved_mw
                )
        elif open_interval is not None:
            intervals.append(open_interval)
            open_interval = None
    if open_interval is not None:
        intervals.append(open_interval)
    return {
        "unserved_energy_mwh": round(energy_mwh, 9),
        "peak_unserved_mw": round(peak_mw, 9),
        "unserved_interval_count": len(intervals),
        "unserved_intervals": intervals,
    }


def unserved_comparison_verdict(
    baseline: dict[str, Any],
    informed: dict[str, Any],
) -> dict[str, Any]:
    """Compare informed mode against baseline without hiding either metric."""
    energy_ok = float(informed.get("unserved_energy_mwh", 0.0)) <= (
        float(baseline.get("unserved_energy_mwh", 0.0)) + 1e-9
    )
    peak_ok = float(informed.get("peak_unserved_mw", 0.0)) <= (
        float(baseline.get("peak_unserved_mw", 0.0)) + 1e-9
    )
    return {
        "verdict": "PASS" if energy_ok and peak_ok else "FAIL",
        "unserved_energy_no_worse": energy_ok,
        "peak_unserved_no_worse": peak_ok,
        "baseline_unserved_energy_mwh": float(
            baseline.get("unserved_energy_mwh", 0.0)
        ),
        "informed_unserved_energy_mwh": float(
            informed.get("unserved_energy_mwh", 0.0)
        ),
        "baseline_peak_unserved_mw": float(baseline.get("peak_unserved_mw", 0.0)),
        "informed_peak_unserved_mw": float(informed.get("peak_unserved_mw", 0.0)),
    }


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
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    controller_approved: Optional[bool] = None
    suppressed_repeat_count: int = 0

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
            "from_state": self.from_state,
            "to_state": self.to_state,
            "controller_approved": self.controller_approved,
            "suppressed_repeat_count": self.suppressed_repeat_count,
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
    preload_margin_seconds: float = DEFAULT_PRELOAD_MARGIN_SECONDS
    bess_allowance_soc_threshold_fraction: float = (
        DEFAULT_BESS_ALLOWANCE_SOC_THRESHOLD
    )
    log: list[CommitmentLogRecord] = field(default_factory=list)
    forecast_history: list[CommitmentForecast] = field(default_factory=list)
    constraint_violation_reasons: list[str] = field(default_factory=list)
    _pending_request_keys: set[tuple[str, str]] = field(default_factory=set, repr=False)
    _cascade_release_ticks: set[int] = field(default_factory=set, repr=False)
    _observed_start_counts: dict[str, int] = field(default_factory=dict, repr=False)
    _last_refusal_signature: dict[tuple[str, str], tuple[str, str]] = field(
        default_factory=dict, repr=False
    )
    _suppressed_refusal_counts: dict[tuple[str, str], int] = field(
        default_factory=dict, repr=False
    )
    preload_actions: list[dict[str, Any]] = field(default_factory=list)
    preload_fuel_mmbtu: float = 0.0
    unserved_energy_mwh: float = 0.0
    peak_unserved_mw: float = 0.0
    unserved_intervals: list[dict[str, float]] = field(default_factory=list)
    _open_unserved_interval: Optional[dict[str, float]] = field(
        default=None, repr=False
    )
    forecast_miss_count: int = 0
    forecast_miss_peak_mw: float = 0.0
    _latest_forecast: Optional[CommitmentForecast] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.mode not in {"disabled", "baseline", "informed"}:
            raise ValueError("turbine commitment mode must be disabled, baseline, or informed")
        if self.forecast_lead_seconds not in ALLOWED_FORECAST_LEAD_SECONDS:
            raise ValueError(
                "forecast lead must be one of 0, 150, 300, 600, or 1,200 seconds"
            )
        self.floor_synchronized = max(1, int(self.floor_synchronized))
        self.sensitivity_mw = max(0.0, float(self.sensitivity_mw))
        self.preload_margin_seconds = max(0.0, float(self.preload_margin_seconds))

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
            if self._event_type(event) not in {"starting", "running", "scale"}:
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
        for sample in measured_history:
            timestamp = float(sample[0])
            value = float(sample[1])
            if not window_start <= timestamp < sim_time_s:
                continue
            job_state = self._job_state_at(
                timestamp=timestamp,
                events=events,
                power_for_event=power_for_event,
            )
            scripted = sum(power for power, _, _ in job_state.values())
            if len(sample) >= 4:
                # RunContext stores the actual lagged cooling producer beside
                # measured demand.  Older callers still use the multiplier
                # fallback so the controller remains backwards-compatible.
                scripted += max(0.0, float(sample[3]))
            else:
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
            if self._event_type(event) in {"starting", "running", "scale"}
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
            if turbine.state == TurbineState.SYNCHRONISED
            and not getattr(turbine.config, "hot_standby", False)
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

    def _future_burst_refusal(
        self,
        *,
        state: Any,
        turbine: Any,
        sim_time_s: float,
        forecast: Optional[CommitmentForecast],
        remaining_msl_mw: float,
        bess_allowance_mw: float,
    ) -> Optional[str]:
        """Keep a unit committed when it cannot be restarted before a burst.

        The normal stop gate is a power-capacity check.  This additional gate
        covers the interval immediately after a stop: a unit is unavailable
        while it unloads, cools through minimum-down time, and starts again.
        During that window, remaining MSL plus BESS power is the conservative
        physical bridge.  Unloading units are intentionally not credited.
        """
        if forecast is None:
            return None
        config = turbine.config
        restart_delay = (
            max(0.0, float(getattr(config, "unload_tail_s", 0.0)))
            + (
                max(0.0, float(getattr(config, "t_min_down_s", 0.0)))
                if getattr(config, "min_down_enabled", False)
                else 0.0
            )
            + max(
                0.0,
                float(getattr(config, "hot_start_s", 0.0)),
                float(getattr(config, "warm_start_s", 0.0)),
                float(getattr(config, "cold_start_s", 0.0)),
            )
            + self.ramp_to_load_seconds
        )
        protection_end = sim_time_s + restart_delay
        announced_starts = self._announced_start_times(
            sim_time_s=sim_time_s,
            events=list(getattr(state, "events", [])),
        )
        for burst_time in sorted(set(announced_starts.values())):
            if burst_time <= sim_time_s + 1e-9 or burst_time > protection_end + 1e-9:
                continue
            predicted_at_onset = next(
                (
                    float(power)
                    for timestamp, power in forecast.profile
                    if timestamp >= burst_time - 1e-9
                ),
                forecast.peak_over(max(0.0, burst_time - sim_time_s)),
            )
            if predicted_at_onset > (
                remaining_msl_mw + bess_allowance_mw + self.sensitivity_mw
            ):
                return (
                    "stop refused: forecast burst at "
                    f"{burst_time:.0f}s arrives before unit restart window "
                    f"({protection_end:.0f}s)"
                )
        return None

    def evaluate(
        self,
        *,
        ctx: Any,
        power_for_event: Callable[[Any], float],
    ) -> CommitmentForecast | None:
        if not self.enabled:
            return None
        # The preload request is a per-tick setpoint overlay, not a second
        # turbine state machine.  Clear the previous request before evaluating
        # the current forecast so it cannot persist after a burst ends.
        setattr(ctx.sim_state, "_preload_targets_mw", {})
        setattr(ctx.sim_state, "_preload_active_units", set())
        setattr(ctx.sim_state, "_commitment_forecast", None)
        # DR-2026-09-17-BASELINE: baseline is the measured core commitment
        # engine only.  It must not consume forecast input or create forecast
        # controller actions.
        if self.mode == "baseline":
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
        self._latest_forecast = forecast
        setattr(ctx.sim_state, "_commitment_forecast", forecast)
        turbines = ctx.sim_state.turbines
        # Commitment reserve is the capacity that can respond upward.  An
        # UNLOADING unit remains electrically on the bus for physical balance,
        # but it cannot provide upward reserve and must not justify another
        # stop in the same rundown sequence.
        synchronized = [
            turbine
            for turbine in turbines
            if turbine.state == TurbineState.SYNCHRONISED
            and not getattr(turbine.config, "hot_standby", False)
        ]
        synchronized_capacity = self._synchronized_capacity(turbines)
        bess_allowance, soc = self._bess_allowance(ctx.sim_state.bess_units)

        # In informed mode the forecast controller is the single commitment
        # authority, but core still owns the measured proposal.  Preload is the
        # only proactive action generated here; commit/decommit proposals are
        # adjudicated after the core has measured the current tick.
        self._evaluate_preload(ctx, forecast, power_for_event)
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
        future_burst_reason = self._future_burst_refusal(
            state=ctx,
            turbine=candidate,
            sim_time_s=ctx.sim_time,
            forecast=forecast,
            remaining_msl_mw=remaining_msl,
            bess_allowance_mw=bess_allowance,
        )
        if future_burst_reason is not None:
            self._refused(
                ctx=ctx,
                turbine=candidate,
                action="stop",
                reason=future_burst_reason,
                forecast=forecast,
                synchronized_capacity=synchronized_capacity,
                soc=soc,
            )
        elif stop_peak + self.sensitivity_mw > remaining_capacity + bess_allowance:
            self._refused(
                ctx=ctx,
                turbine=candidate,
                action="stop",
                reason="stop refused: unit is needed within 1,200s",
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

    def _evaluate_preload(
        self,
        ctx: Any,
        forecast: CommitmentForecast,
        power_for_event: Callable[[Any], float],
    ) -> None:
        """Pre-load synchronized turbines ahead of a known burst.

        Targets are consumed by the existing loading layer, which applies each
        turbine's configured ramp limit.  The BESS arbitrator then gets first
        refusal on the resulting surplus and charges within its own limits.
        """
        turbines = [
            turbine
            for turbine in ctx.sim_state.turbines
            if turbine.state == TurbineState.SYNCHRONISED
            and not turbine.config.hot_standby
        ]
        if not turbines:
            return
        future_starts = [
            event
            for event in ctx.events
            if self._event_type(event) in {"starting", "running", "scale"}
            and ctx.sim_time < float(event.timestamp) <= ctx.sim_time + self.forecast_lead_seconds
        ]
        if not future_starts:
            return
        event = min(future_starts, key=lambda item: (item.timestamp, item.event_id))
        onset_s = float(event.timestamp)
        onset_values = [
            mw for timestamp, mw in forecast.profile if abs(timestamp - onset_s) < 1e-6
        ]
        if onset_values:
            onset_demand_mw = max(onset_values)
        else:
            onset_demand_mw = forecast.peak_over(max(0.0, onset_s - ctx.sim_time))
        bess_allowance, _ = self._bess_allowance(ctx.sim_state.bess_units)
        current_output_mw = sum(max(0.0, turbine.output_mw()) for turbine in turbines)
        target_total_mw = min(
            sum(max(0.0, float(turbine.config.rated_mw)) for turbine in turbines),
            max(0.0, onset_demand_mw - bess_allowance),
        )
        delta_mw = max(0.0, target_total_mw - current_output_mw)
        ramp_rate_mw_s = sum(
            max(0.0, float(turbine.config.r_asset_mw_per_s))
            for turbine in turbines
        )
        if delta_mw <= 1e-9 or ramp_rate_mw_s <= 1e-9:
            return
        ramp_seconds = delta_mw / ramp_rate_mw_s
        time_to_onset_s = onset_s - ctx.sim_time
        if time_to_onset_s > ramp_seconds + self.preload_margin_seconds:
            return

        # Do not create unabsorbable islanded surplus.  The existing BESS
        # charge path is the only allowed sink for this temporary generation.
        dt_hours = max(0.0, float(getattr(ctx, "dt_seconds", 5.0))) / 3600.0
        charge_capacity_mw = sum(
            min(
                max(0.0, float(unit.config.rated_mw)),
                max(0.0, float(unit.config.usable_mwh) - float(unit.soc_mwh))
                / max(dt_hours, 1e-9),
            )
            for unit in ctx.sim_state.bess_units
            if not getattr(unit, "tripped", False)
        )
        current_demand_mw = max(0.0, float(forecast.forecast_mw))
        # Preloading is a temporary increase above current demand.  Do not
        # reject a useful partial preload merely because the full burst target
        # would exceed the BESS charge ceiling.  Cap the target at the largest
        # physically absorbable level; the burst forecast still determines the
        # uncapped target and the normal loading layer handles the remainder.
        target_total_mw = min(
            target_total_mw,
            current_demand_mw + charge_capacity_mw,
        )

        remaining = target_total_mw
        targets: dict[str, float] = {}
        for turbine in turbines:
            minimum = max(
                0.0,
                float(turbine.config.p_min_stable_frac)
                * float(turbine.config.rated_mw),
            )
            target = min(
                max(minimum, remaining),
                max(0.0, float(turbine.config.rated_mw)),
            )
            targets[turbine.config.asset_id] = target
            remaining = max(0.0, remaining - target)
        if not targets:
            return
        setattr(ctx.sim_state, "_preload_targets_mw", targets)
        setattr(ctx.sim_state, "_preload_active_units", set(targets))
        setattr(ctx.sim_state, "_preload_normal_output_mw", current_output_mw)
        action = {
            "sim_time_s": float(ctx.sim_time),
            "unit_ids": sorted(targets),
            "target_mw": round(sum(targets.values()), 6),
            "normal_output_mw": round(current_output_mw, 6),
            "incremental_target_mw": round(delta_mw, 6),
            "reason": "forecast burst preload within ramp window",
            "forecast_mw": round(float(onset_demand_mw), 6),
            "burst_sim_time_s": onset_s,
            "ramp_seconds": round(ramp_seconds, 6),
            "margin_seconds": self.preload_margin_seconds,
        }
        self.preload_actions.append(action)

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

    def record_transition(
        self,
        *,
        turbine: Any,
        sim_time_s: float,
        action: str,
        source: str,
        reason: str,
        from_state: Any,
        to_state: Any,
        controller_approved: Optional[bool],
        forecast: Optional[CommitmentForecast] = None,
        synchronized_capacity_mw: Optional[float] = None,
        bess_soc_fraction: Optional[float] = None,
    ) -> None:
        """Record one authoritative turbine state transition.

        This is intentionally separate from command-result logging: a command
        can be accepted without changing state, while every actual transition
        must carry the before/after state pair.
        """
        forecast = forecast or self._latest_forecast
        self.log.append(
            CommitmentLogRecord(
                sim_time_s=float(sim_time_s),
                unit_id=str(turbine.config.asset_id),
                action=str(action),
                thermal_tier=str(
                    getattr(
                        getattr(turbine, "_thermal_state", None),
                        "value",
                        getattr(turbine.config, "initial_thermal_state", "unknown"),
                    )
                ),
                reason=str(reason),
                forecast_mw=float(forecast.forecast_mw if forecast else 0.0),
                peak_forecast_mw=float(
                    forecast.peak_forecast_mw if forecast else 0.0
                ),
                synchronized_capacity_mw=float(synchronized_capacity_mw or 0.0),
                bess_soc_fraction=float(bess_soc_fraction or 0.0),
                accepted=True,
                changed_state=True,
                source=str(source),
                from_state=getattr(from_state, "value", str(from_state)),
                to_state=getattr(to_state, "value", str(to_state)),
                controller_approved=controller_approved,
            )
        )

    def adjudicate_core_proposal(
        self,
        *,
        state: Any,
        decision: Any,
        sim_time_s: float,
        synchronized_capacity_mw: float,
        bess_soc_fraction: float,
    ) -> bool:
        """Accept or veto a measured core commitment proposal in informed mode."""
        unit_id = str(decision.target_unit_id or "")
        turbine = next(
            (item for item in state.turbines if item.config.asset_id == unit_id),
            None,
        )
        if turbine is None:
            return False
        forecast = getattr(state, "_commitment_forecast", None)
        allowance, _ = self._bess_allowance(state.bess_units)
        accepted = True
        refusal_reason: Optional[str] = None
        if decision.action == "commit":
            if turbine.state != TurbineState.OFFLINE:
                accepted = False
                refusal_reason = (
                    "forecast controller veto: unit is not offline and cannot start"
                )
            elif (
                turbine.config.min_down_enabled
                and not math.isnan(float(getattr(turbine, "_stop_time_s", float("nan"))))
                and sim_time_s - turbine._stop_time_s < turbine.config.t_min_down_s
            ):
                accepted = False
                refusal_reason = (
                    "forecast controller veto: minimum down time has not elapsed"
                )
            horizon = self.hot_start_lookahead_seconds + self.ramp_to_load_seconds
            if accepted and forecast is not None and not decision.floor_violated:
                if forecast.peak_over(horizon) <= (
                    synchronized_capacity_mw + allowance + self.sensitivity_mw
                ):
                    accepted = False
                    refusal_reason = (
                        "forecast controller veto: measured commit is not needed "
                        f"within {horizon:.0f}s"
                    )
        elif decision.action == "decommit":
            remaining = [
                item for item in state.turbines
                if (
                    item is not turbine
                    and item.state == TurbineState.SYNCHRONISED
                    and not getattr(item.config, "hot_standby", False)
                )
            ]
            remaining_capacity = sum(
                max(0.0, float(item.config.rated_mw)) for item in remaining
            )
            remaining_msl = sum(
                max(0.0, float(item.config.p_min_stable_frac))
                * max(0.0, float(item.config.rated_mw))
                for item in remaining
            )
            if forecast is not None:
                future_burst_reason = self._future_burst_refusal(
                    state=state,
                    turbine=turbine,
                    sim_time_s=sim_time_s,
                    forecast=forecast,
                    remaining_msl_mw=remaining_msl,
                    bess_allowance_mw=allowance,
                )
                if future_burst_reason is not None:
                    accepted = False
                    refusal_reason = future_burst_reason
                elif forecast.peak_over(self.stop_lookahead_seconds) + self.sensitivity_mw > (
                    remaining_capacity + allowance
                ):
                    accepted = False
                    refusal_reason = "forecast controller veto: unit is needed within 1,200s"
            if (
                accepted
                and turbine.config.min_run_enabled
                and not math.isnan(float(getattr(turbine, "_run_start_s", float("nan"))))
                and sim_time_s - turbine._run_start_s < turbine.config.t_min_run_s
            ):
                accepted = False
                refusal_reason = (
                    "forecast controller veto: minimum run time has not elapsed"
                )

        self.command_result(
            {
                "unit_id": unit_id,
                "action": f"proposal_{decision.action}",
                "sim_time_s": sim_time_s,
                "thermal_tier": "controller",
                "reason": str(decision.reason),
                "forecast_mw": float(forecast.forecast_mw if forecast else 0.0),
                "peak_forecast_mw": float(
                    forecast.peak_forecast_mw if forecast else 0.0
                ),
                "synchronized_capacity_mw": synchronized_capacity_mw,
                "bess_soc_fraction": bess_soc_fraction,
                "source": "core_commitment_proposal",
                "refusal_reason": refusal_reason,
                "controller_approved": accepted,
            },
            accepted=accepted,
            changed_state=False,
            refusal_reason=refusal_reason,
        )
        return accepted

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
        refusal_key = (str(metadata.get("unit_id", "")), action)
        refusal_signature = (
            str(refusal_reason or metadata.get("refusal_reason") or ""),
            str(metadata.get("source", "forecast_commitment")),
        )
        if not accepted:
            if self._last_refusal_signature.get(refusal_key) == refusal_signature:
                suppressed = self._suppressed_refusal_counts.get(refusal_key, 0) + 1
                self._suppressed_refusal_counts[refusal_key] = suppressed
                for index in range(len(self.log) - 1, -1, -1):
                    previous = self.log[index]
                    if (
                        not previous.accepted
                        and previous.unit_id == str(metadata.get("unit_id", ""))
                        and previous.action == action
                    ):
                        self.log[index] = CommitmentLogRecord(
                            **{
                                **previous.__dict__,
                                "suppressed_repeat_count": suppressed,
                            }
                        )
                        break
                return
            self._last_refusal_signature[refusal_key] = refusal_signature
            self._suppressed_refusal_counts[refusal_key] = 0
        else:
            self._last_refusal_signature.pop(refusal_key, None)
            self._suppressed_refusal_counts.pop(refusal_key, None)
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
                from_state=metadata.get("from_state"),
                to_state=metadata.get("to_state"),
                controller_approved=metadata.get("controller_approved"),
                suppressed_repeat_count=self._suppressed_refusal_counts.get(
                    refusal_key, 0
                ),
            )
        )

    @property
    def suppressed_refusal_count(self) -> int:
        return sum(self._suppressed_refusal_counts.values())

    @property
    def suppressed_repeat_count(self) -> int:
        return self.suppressed_refusal_count

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
        dt_seconds = max(0.0, float(getattr(ctx, "dt_seconds", 5.0)))
        unserved_mw = max(0.0, float(getattr(result, "p_unserved_mw", 0.0) or 0.0))
        self.unserved_energy_mwh += unserved_mw * dt_seconds / 3600.0
        self.peak_unserved_mw = max(self.peak_unserved_mw, unserved_mw)
        end_s = float(getattr(result, "sim_time_seconds", 0.0))
        if unserved_mw > 1e-9:
            if self._open_unserved_interval is None:
                self._open_unserved_interval = {
                    "start_sim_time_s": end_s - dt_seconds,
                    "end_sim_time_s": end_s,
                    "peak_unserved_mw": unserved_mw,
                }
            else:
                self._open_unserved_interval["end_sim_time_s"] = end_s
                self._open_unserved_interval["peak_unserved_mw"] = max(
                    self._open_unserved_interval["peak_unserved_mw"], unserved_mw
                )
        elif self._open_unserved_interval is not None:
            self.unserved_intervals.append(self._open_unserved_interval)
            self._open_unserved_interval = None
        if self.mode == "informed" and self.forecast_history:
            forecast = self.forecast_history[-1]
            actual_demand = float(getattr(result, "p_demand_mw", 0.0) or 0.0)
            miss = max(0.0, actual_demand - forecast.peak_forecast_mw)
            if miss > self.sensitivity_mw:
                self.forecast_miss_count += 1
                self.forecast_miss_peak_mw = max(self.forecast_miss_peak_mw, miss)
        active_preload_units = set(
            getattr(ctx.sim_state, "_preload_active_units", set())
        )
        if active_preload_units:
            normal_output_mw = float(
                getattr(ctx.sim_state, "_preload_normal_output_mw", 0.0)
            )
            actual_output_mw = sum(
                max(0.0, float(turbine.output_mw()))
                for turbine in ctx.sim_state.turbines
                if turbine.config.asset_id in active_preload_units
            )
            incremental_fraction = (
                max(0.0, actual_output_mw - normal_output_mw)
                / max(actual_output_mw, 1e-9)
            )
            for turbine in ctx.sim_state.turbines:
                if turbine.config.asset_id in active_preload_units:
                    self.preload_fuel_mmbtu += max(
                        0.0, float(getattr(turbine, "_last_interval_fuel_mmbtu", 0.0))
                    ) * incremental_fraction
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
            # The actual state transition is recorded by the core transition
            # hook.  Keep the alert bookkeeping here without creating a second
            # synthetic transition record.

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
                reason = (
                    f"start_count_reconciliation:{unit_id}:"
                    f"asset={count}:log={actual.get(unit_id, 0)}:"
                    "untracked_path=production_command_or_cascade"
                )
                if reason not in self.constraint_violation_reasons:
                    self.constraint_violation_reasons.append(reason)

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

    @property
    def hard_violation_reasons(self) -> list[str]:
        return self.constraint_violation_reasons