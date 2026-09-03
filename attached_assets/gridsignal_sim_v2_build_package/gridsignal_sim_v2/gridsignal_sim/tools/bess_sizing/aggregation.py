"""Phase 2 aggregation for the Addendum H BESS sizing sweep.

This module consumes the raw ``ScenarioTrace`` objects produced by the Phase 1
driver.  It does not run dispatch, alter traces, implement SoC cycling, or
create a recommendation record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import (
    AnchorMode,
    BessSizingScenario,
    BessSizingSweepResult,
    ScenarioTrace,
    ScenarioType,
)


# PROPOSED_HERE: unvalidated default margin per Addendum H BSZ-2 open item.
DEFAULT_MARGIN_PCT = 0.10


@dataclass(frozen=True)
class ScenarioSizingMetrics:
    """H.5/H.6 values derived from one complete raw scenario trace."""

    scenario_id: str
    scenario_type: ScenarioType
    raw_peak_bess_output_mw: float
    anchor_reserve_mw: float
    peak_power_mw: float
    energy_integral_mwh: float


@dataclass(frozen=True)
class PercentileSummary:
    """P50, P95, margin-adjusted P95, and P100 for one sizing dimension."""

    p50: float
    p95: float
    p95_with_margin: float
    p100: float


@dataclass(frozen=True)
class BessSizingAggregation:
    """H.5-H.7 output with both per-run evidence and exposed percentiles."""

    per_scenario: tuple[ScenarioSizingMetrics, ...]
    power_mw: PercentileSummary
    energy_mwh: PercentileSummary


def _linear_percentile(values: Sequence[float], percentile: float) -> float:
    """Return a linearly interpolated percentile from a non-empty sample."""

    if not values:
        raise ValueError("cannot calculate a percentile from an empty sample")
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("percentile must be between 0 and 100")

    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percentile / 100.0
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return (
        ordered[lower_index]
        + (ordered[upper_index] - ordered[lower_index]) * fraction
    )


def _anchor_reserve_mw(scenario: BessSizingScenario) -> float:
    """Return the scenario-configured anchor reserve used by the Phase 1 run.

    ``BessSizingScenario.p_anchor_reserve_mw`` is the scenario configuration
    field consumed by the Phase 1 driver when it materializes the designated
    anchor BESS.  Reading it here keeps H.5 aligned with the exact scenario
    configuration that produced the raw trace; no catalogue or numeric
    fallback is introduced.
    """

    if scenario.anchor_mode != AnchorMode.GRID_FORMING:
        return 0.0
    return scenario.p_anchor_reserve_mw


def _peak_bess_output_mw(trace: ScenarioTrace) -> float:
    """Return the raw peak BESS output for one complete trace."""

    series = trace.bess_output_series_mw
    if not series:
        raise ValueError(
            f"scenario {trace.scenario_id!r} has no BESS output samples"
        )
    return max(series)


def integrate_bess_output_mwh(trace: ScenarioTrace) -> float:
    """Integrate BESS output over the full recorded run with trapezoids.

    The trace timestamps are used directly, so every interval from the first
    recorded tick through the last recorded tick is included.  Trapezoidal
    integration is used because the raw samples are timestamped outputs and
    this avoids assuming an unobserved step change between ticks.  The result
    intentionally covers the full trace rather than a separately identified
    shortfall window, including any extended BESS hold behavior.
    """

    ticks = trace.tick_traces
    if not ticks:
        raise ValueError(
            f"scenario {trace.scenario_id!r} has no BESS output samples"
        )
    if len(ticks) == 1:
        return 0.0

    energy_mwh = 0.0
    for previous, current in zip(ticks, ticks[1:]):
        interval_s = current.time_s - previous.time_s
        if interval_s < 0.0:
            raise ValueError(
                f"scenario {trace.scenario_id!r} has decreasing tick timestamps"
            )
        energy_mwh += (
            0.5
            * (previous.bess_output_mw + current.bess_output_mw)
            * interval_s
            / 3600.0
        )
    return energy_mwh


def _percentile_summary(values: Sequence[float]) -> PercentileSummary:
    p50 = _linear_percentile(values, 50.0)
    p95 = _linear_percentile(values, 95.0)
    return PercentileSummary(
        p50=p50,
        p95=p95,
        p95_with_margin=p95 * (1.0 + DEFAULT_MARGIN_PCT),
        p100=_linear_percentile(values, 100.0),
    )


def _pair_scenarios_and_traces(
    sweep: BessSizingSweepResult,
    scenarios: Sequence[BessSizingScenario],
) -> tuple[tuple[BessSizingScenario, ScenarioTrace], ...]:
    scenario_by_id: dict[str, BessSizingScenario] = {}
    for scenario in scenarios:
        if scenario.scenario_id in scenario_by_id:
            raise ValueError(
                f"duplicate scenario ID {scenario.scenario_id!r}"
            )
        scenario_by_id[scenario.scenario_id] = scenario

    trace_by_id: dict[str, ScenarioTrace] = {}
    for trace in sweep.traces:
        if trace.scenario_id in trace_by_id:
            raise ValueError(f"duplicate trace ID {trace.scenario_id!r}")
        trace_by_id[trace.scenario_id] = trace

    missing_traces = sorted(set(scenario_by_id) - set(trace_by_id))
    unexpected_traces = sorted(set(trace_by_id) - set(scenario_by_id))
    if missing_traces or unexpected_traces:
        raise ValueError(
            "scenario/trace IDs must match exactly; "
            f"missing_traces={missing_traces}, "
            f"unexpected_traces={unexpected_traces}"
        )

    return tuple(
        (scenario, trace)
        for scenario in scenarios
        for trace in (trace_by_id[scenario.scenario_id],)
    )


def aggregate_bess_sizing_sweep(
    sweep: BessSizingSweepResult,
    scenarios: Sequence[BessSizingScenario],
) -> BessSizingAggregation:
    """Calculate H.5-H.7 power, energy, and percentile sizing evidence.

    H.5 uses the peak raw BESS output from each trace and adds the configured
    anchor reserve only for grid-forming scenarios.  H.6 uses the full-run
    trapezoidal integral from :func:`integrate_bess_output_mwh`.  H.7 exposes
    all requested percentile values independently for power and energy.

    This function intentionally stops before H.8-H.10: it does not implement
    SoC cycling, broader anchor integration, recommendation records, or queue
    interaction.
    """

    paired = _pair_scenarios_and_traces(sweep, scenarios)
    if not paired:
        raise ValueError("cannot aggregate an empty BESS sizing sweep")

    per_scenario = []
    for scenario, trace in paired:
        raw_peak_mw = _peak_bess_output_mw(trace)
        anchor_reserve_mw = _anchor_reserve_mw(scenario)
        per_scenario.append(
            ScenarioSizingMetrics(
                scenario_id=scenario.scenario_id,
                scenario_type=scenario.scenario_type,
                raw_peak_bess_output_mw=raw_peak_mw,
                anchor_reserve_mw=anchor_reserve_mw,
                peak_power_mw=raw_peak_mw + anchor_reserve_mw,
                energy_integral_mwh=integrate_bess_output_mwh(trace),
            )
        )

    power_values = tuple(metric.peak_power_mw for metric in per_scenario)
    energy_values = tuple(
        metric.energy_integral_mwh for metric in per_scenario
    )
    return BessSizingAggregation(
        per_scenario=tuple(per_scenario),
        power_mw=_percentile_summary(power_values),
        energy_mwh=_percentile_summary(energy_values),
    )