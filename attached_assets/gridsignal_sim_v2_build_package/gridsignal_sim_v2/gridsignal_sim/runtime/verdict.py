"""
runtime/verdict.py — Scenario assertion evaluation and verdict computation (Step 9).

Pure module: no I/O, no SQLAlchemy imports.  Receives completed tick data as
EvalRow NamedTuples and returns a VerdictResult that _drive() serialises to JSON
before persisting via sink.finalize().

H1 gap rule (per assertion type):
  no_insufficient_reserve_alert  gaps → INCONCLUSIVE (universal quantifier)
  max_p_total_mw                 gaps → INCONCLUSIVE (universal quantifier)
  alert_fires                    retained row satisfies → PASS; else INCONCLUSIVE
  min_final_bess_soc             PASS/FAIL unless the final tick is missing
  pue_base_in_declared_range     PASS/FAIL from runtime config + PARAM-06 bounds

AssertionSpec is defined here rather than in api/schemas.py so that runtime/ code
(run_manager.py, scenario_factory.py) can import it without creating a runtime/ → api/
circular dependency.  api/schemas.py imports from here; that direction is fine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Annotated, Literal, NamedTuple, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# AssertionSpec — discriminated union by 'check'
# ---------------------------------------------------------------------------

class NoReserveAlertAssertion(BaseModel):
    """Assert that no tick fires insufficient_reserve_alert.

    Universal quantifier: gaps make verification incomplete → INCONCLUSIVE.
    A dropped tick might have fired the alert.
    """
    check: Literal["no_insufficient_reserve_alert"] = "no_insufficient_reserve_alert"


class AlertFiresAssertion(BaseModel):
    """Assert that at least one tick fires insufficient_reserve_alert.

    Existential quantifier: a retained tick can satisfy it despite gaps.
    PASS when any retained tick fired; INCONCLUSIVE (not FAIL) when no
    retained tick fired but gaps exist — a dropped tick may have fired.
    """
    check: Literal["alert_fires"] = "alert_fires"


class DecliningFuelCellReserveAlertFiresAssertion(BaseModel):
    """Assert that the block-array declining-reserve alert was retained.

    This is an existential assertion.  A retained alert is sufficient evidence
    even when timeseries writes have gaps; without retained evidence, gaps make
    the result INCONCLUSIVE rather than FAIL.
    """
    check: Literal["declining_fuel_cell_reserve_alert_fires"] = (
        "declining_fuel_cell_reserve_alert_fires"
    )


class MaxPTotalAssertion(BaseModel):
    """Assert that p_total_mw ≤ threshold_mw on every tick.

    Universal quantifier: gaps → INCONCLUSIVE.
    A dropped tick might have exceeded the threshold.
    """
    check: Literal["max_p_total_mw"] = "max_p_total_mw"
    threshold_mw: float = Field(gt=0)


class MinFinalBessSocAssertion(BaseModel):
    """Assert that the final tick's bess_soc_fraction ≥ threshold.

    PASS/FAIL when the final tick is retained; INCONCLUSIVE when the final
    tick is missing (dropped or the run was cancelled before end_sim_time).
    """
    check: Literal["min_final_bess_soc"] = "min_final_bess_soc"
    threshold: float = Field(ge=0.0, le=1.0)


class PueBaseInDeclaredRangeAssertion(BaseModel):
    """Assert that runtime pue_base remains within PARAM-06's declared range."""
    check: Literal["pue_base_in_declared_range"] = "pue_base_in_declared_range"


class PersistentFuelCellDeficitAssertion(BaseModel):
    """Assert a contiguous, commanded-minus-achieved fuel-cell deficit."""
    check: Literal["persistent_fuel_cell_deficit"] = "persistent_fuel_cell_deficit"
    expected_deficit_mw: float = Field(ge=0.0)
    duration_s: float = Field(gt=0.0)
    tick_seconds: float = Field(default=15.0, gt=0.0)
    tolerance_mw: float = Field(default=0.325, ge=0.0)


class PeakFuelCellArrayOutputAssertion(BaseModel):
    """Assert the peak achieved block-array output, with one-block tolerance."""
    check: Literal["peak_fuel_cell_array_output"] = "peak_fuel_cell_array_output"
    expected_mw: float = Field(ge=0.0)
    tolerance_mw: float = Field(default=0.325, ge=0.0)


class NoColdWarmingContingencyCapacityAssertion(BaseModel):
    """Assert cold/warming blocks are absent from immediately available capacity."""
    check: Literal["no_cold_warming_contingency_capacity"] = (
        "no_cold_warming_contingency_capacity"
    )
    block_rated_mw: float = Field(default=0.325, gt=0.0)
    tolerance_mw: float = Field(default=1e-9, ge=0.0)


class FuelCellCommandedAndAchievedReportedAssertion(BaseModel):
    """Assert both fuel-cell dispatch request and measured output were captured."""
    check: Literal["fuel_cell_commanded_and_achieved_reported"] = (
        "fuel_cell_commanded_and_achieved_reported"
    )


# Pydantic v2 discriminated union — validated via TypeAdapter(AssertionSpec)
AssertionSpec = Annotated[
    Union[
        NoReserveAlertAssertion,
        AlertFiresAssertion,
        DecliningFuelCellReserveAlertFiresAssertion,
        MaxPTotalAssertion,
        MinFinalBessSocAssertion,
        PueBaseInDeclaredRangeAssertion,
        PersistentFuelCellDeficitAssertion,
        PeakFuelCellArrayOutputAssertion,
        NoColdWarmingContingencyCapacityAssertion,
        FuelCellCommandedAndAchievedReportedAssertion,
    ],
    Field(discriminator="check"),
]


# ---------------------------------------------------------------------------
# EvalRow — lightweight tick summary (no Pydantic overhead in the hot path)
# ---------------------------------------------------------------------------

class EvalRow(NamedTuple):
    tick_index: int
    p_demand_mw: float
    bess_soc_fraction: float
    insufficient_reserve_alert: bool
    # G-1 telemetry. Defaults retain compatibility with Step 9 callers.
    fuel_cell_commanded_output_mw: Optional[float] = None
    fuel_cell_achieved_output_mw: Optional[float] = None
    fuel_cell_available_now_mw: Optional[float] = None
    fuel_cell_running_blocks: Optional[int] = None
    fuel_cell_cold_blocks: Optional[int] = None
    fuel_cell_warming_blocks: Optional[int] = None
    # Interval-end simulation timestamp.  Deficit duration is proved from
    # adjacent retained timestamps, never from assertion-supplied cadence.
    sim_time_seconds: Optional[float] = None
    # Explicit value supplied to contingency/reserve accounting from blocks
    # that are cold or warming.  It must be zero; available_now alone cannot
    # prove that accounting did not include those blocks elsewhere.
    fuel_cell_cold_warming_contingency_contribution_mw: Optional[float] = None
    # The full alert record is retained because its event-window evidence is
    # useful to callers, while verdict evaluation only needs its presence.
    fuel_cell_declining_reserve_alert: Optional[dict] = None


# ---------------------------------------------------------------------------
# AssertionResult + VerdictResult
# ---------------------------------------------------------------------------

@dataclass
class AssertionResult:
    check: str
    status: str   # "PASS" | "FAIL" | "INCONCLUSIVE"
    detail: str


@dataclass
class VerdictResult:
    overall: str  # "PASS" | "FAIL" | "INCONCLUSIVE"
    tick_count: int
    dropped_ticks: int
    gap_count: int
    assertions: list[AssertionResult] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "overall": self.overall,
            "tick_count": self.tick_count,
            "dropped_ticks": self.dropped_ticks,
            "gap_count": self.gap_count,
            "assertions": [
                {"check": a.check, "status": a.status, "detail": a.detail}
                for a in self.assertions
            ],
        })


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

def _count_gaps(rows: list[EvalRow]) -> int:
    """Count positions where tick_index jumps by more than 1 (dropped ticks)."""
    gaps = 0
    for i in range(1, len(rows)):
        if rows[i].tick_index > rows[i - 1].tick_index + 1:
            gaps += 1
    return gaps


# ---------------------------------------------------------------------------
# Per-assertion evaluation helpers
# ---------------------------------------------------------------------------

def _eval_one(
    assertion: object,
    rows: list[EvalRow],
    has_gaps: bool,
    expected_last_tick_index: Optional[int],
    pue_base: Optional[float],
    pue_base_bounds: Optional[tuple[float, float]],
) -> AssertionResult:
    """Evaluate a single assertion against the retained rows.

    Duck-typed on assertion.check — accepts both AssertionSpec Pydantic
    objects and plain dicts (``assertion['check']``) so that
    evaluate_verdict() does not need to parse the spec.
    """
    if isinstance(assertion, dict):
        check: str = assertion["check"]
        threshold_mw = assertion.get("threshold_mw", 0.0)
        threshold = assertion.get("threshold", 0.0)
        expected_deficit_mw = assertion.get("expected_deficit_mw", 0.0)
        duration_s = assertion.get("duration_s", 0.0)
        tick_seconds = assertion.get("tick_seconds", 15.0)
        expected_mw = assertion.get("expected_mw", 0.0)
        tolerance_mw = assertion.get("tolerance_mw", 0.325)
        block_rated_mw = assertion.get("block_rated_mw", 0.325)
    else:
        check = assertion.check  # type: ignore[union-attr]
        threshold_mw = getattr(assertion, "threshold_mw", 0.0)
        threshold = getattr(assertion, "threshold", 0.0)
        expected_deficit_mw = getattr(assertion, "expected_deficit_mw", 0.0)
        duration_s = getattr(assertion, "duration_s", 0.0)
        tick_seconds = getattr(assertion, "tick_seconds", 15.0)
        expected_mw = getattr(assertion, "expected_mw", 0.0)
        tolerance_mw = getattr(assertion, "tolerance_mw", 0.325)
        block_rated_mw = getattr(assertion, "block_rated_mw", 0.325)

    if check == "declining_fuel_cell_reserve_alert_fires":
        alert_count = sum(
            1 for row in rows if row.fuel_cell_declining_reserve_alert is not None
        )
        if alert_count:
            return AssertionResult(
                check, "PASS",
                f"{alert_count} / {len(rows)} retained ticks fired the declining fuel-cell reserve alert",
            )
        if has_gaps:
            return AssertionResult(
                check, "INCONCLUSIVE",
                "No declining fuel-cell reserve alert in retained rows, "
                "but gaps exist — dropped ticks may have fired",
            )
        return AssertionResult(
            check, "FAIL",
            f"0 / {len(rows)} retained ticks fired the declining fuel-cell reserve alert",
        )

    if check == "persistent_fuel_cell_deficit":
        # ``tick_seconds`` is retained in the input schema for compatibility,
        # but is deliberately not evidence: callers can supply a cadence that
        # does not match the retained simulation.  A qualifying duration is
        # the sum of actual timestamp deltas across adjacent tick indices.
        longest_s = 0.0
        run_s = 0.0
        previous_matching: Optional[EvalRow] = None
        matching_timestamp_missing = False
        for row in rows:
            matching = (
                row.fuel_cell_commanded_output_mw is not None
                and row.fuel_cell_achieved_output_mw is not None
                and abs(
                    (row.fuel_cell_commanded_output_mw -
                     row.fuel_cell_achieved_output_mw) - expected_deficit_mw
                ) <= tolerance_mw
            )
            if not matching:
                previous_matching = None
                run_s = 0.0
                continue
            if row.sim_time_seconds is None:
                matching_timestamp_missing = True
            if (
                previous_matching is not None
                and row.tick_index == previous_matching.tick_index + 1
                and row.sim_time_seconds is not None
                and previous_matching.sim_time_seconds is not None
                and row.sim_time_seconds > previous_matching.sim_time_seconds
            ):
                run_s += row.sim_time_seconds - previous_matching.sim_time_seconds
            else:
                run_s = 0.0
            longest_s = max(longest_s, run_s)
            previous_matching = row
        if longest_s >= duration_s:
            return AssertionResult(check, "PASS",
                f"Fuel-cell deficit {expected_deficit_mw:.3f} MW ± {tolerance_mw:.3f} "
                f"persisted {longest_s:.0f} s from adjacent retained timestamps "
                f"(required {duration_s:.0f} s)")
        if has_gaps:
            return AssertionResult(check, "INCONCLUSIVE",
                f"Longest timestamp-proven matching deficit was {longest_s:.0f} s; "
                "gaps could contain the interval needed for PASS")
        if matching_timestamp_missing:
            return AssertionResult(check, "INCONCLUSIVE",
                "Matching deficit rows omitted simulation timestamps; cannot prove duration")
        return AssertionResult(check, "FAIL",
            f"Longest timestamp-proven matching fuel-cell deficit was {longest_s:.0f} s, "
            f"required {duration_s:.0f} s")

    if check == "peak_fuel_cell_array_output":
        values = [r.fuel_cell_achieved_output_mw for r in rows
                  if r.fuel_cell_achieved_output_mw is not None]
        if not values:
            return AssertionResult(check, "INCONCLUSIVE", "No achieved fuel-cell telemetry retained")
        peak = max(values)
        status = "PASS" if abs(peak - expected_mw) <= tolerance_mw else "FAIL"
        return AssertionResult(check, status,
            f"Peak achieved fuel-cell output {peak:.3f} MW; expected "
            f"{expected_mw:.3f} MW ± {tolerance_mw:.3f} MW")

    if check == "no_cold_warming_contingency_capacity":
        missing = sum(
            r.fuel_cell_cold_warming_contingency_contribution_mw is None
            for r in rows
        )
        violations = [
            r for r in rows
            if r.fuel_cell_cold_warming_contingency_contribution_mw is not None
            and abs(r.fuel_cell_cold_warming_contingency_contribution_mw) > tolerance_mw
        ]
        if violations:
            return AssertionResult(check, "FAIL",
                f"{len(violations)} tick(s) contributed cold/warming fuel-cell capacity "
                "to contingency accounting")
        if missing:
            return AssertionResult(check, "INCONCLUSIVE",
                f"{missing} / {len(rows)} retained ticks omitted cold/warming "
                "contingency-contribution telemetry")
        if has_gaps:
            return AssertionResult(check, "INCONCLUSIVE",
                "Cold/warming contingency contribution was zero in retained rows, but gaps exist")
        return AssertionResult(check, "PASS",
            "Cold/warming fuel-cell contingency contribution was 0 MW on all retained ticks")

    if check == "fuel_cell_commanded_and_achieved_reported":
        missing = sum(
            r.fuel_cell_commanded_output_mw is None or
            r.fuel_cell_achieved_output_mw is None for r in rows
        )
        if missing:
            return AssertionResult(check, "FAIL",
                f"{missing} / {len(rows)} retained ticks omitted commanded or achieved fuel-cell output")
        if has_gaps:
            return AssertionResult(check, "INCONCLUSIVE",
                "Commanded and achieved output present in retained rows, but gaps exist")
        return AssertionResult(check, "PASS",
            f"Commanded and achieved fuel-cell output reported on all {len(rows)} ticks")

    if check == "no_insufficient_reserve_alert":
        alert_count = sum(1 for r in rows if r.insufficient_reserve_alert)
        if alert_count > 0:
            return AssertionResult(
                check=check, status="FAIL",
                detail=f"{alert_count} / {len(rows)} retained ticks fired the alert",
            )
        if has_gaps:
            return AssertionResult(
                check=check, status="INCONCLUSIVE",
                detail=(
                    f"0 alert ticks in {len(rows)} retained rows, "
                    "but gaps exist — dropped ticks may have fired"
                ),
            )
        return AssertionResult(
            check=check, status="PASS",
            detail=f"0 / {len(rows)} ticks fired the alert",
        )

    if check == "alert_fires":
        alert_count = sum(1 for r in rows if r.insufficient_reserve_alert)
        if alert_count > 0:
            return AssertionResult(
                check=check, status="PASS",
                detail=f"{alert_count} / {len(rows)} retained ticks fired the alert",
            )
        if has_gaps:
            return AssertionResult(
                check=check, status="INCONCLUSIVE",
                detail=(
                    "No alert in retained rows, "
                    "but gaps exist — dropped ticks may have fired"
                ),
            )
        return AssertionResult(
            check=check, status="FAIL",
            detail=f"0 / {len(rows)} ticks fired the alert",
        )

    if check == "max_p_total_mw":
        violating = [r for r in rows if r.p_demand_mw > threshold_mw]
        if violating:
            peak = max(r.p_demand_mw for r in violating)
            return AssertionResult(
                check=check, status="FAIL",
                detail=(
                    f"{len(violating)} tick(s) exceeded {threshold_mw} MW; "
                    f"peak {peak:.3f} MW"
                ),
            )
        if has_gaps:
            return AssertionResult(
                check=check, status="INCONCLUSIVE",
                detail=(
                    f"All {len(rows)} retained ticks within {threshold_mw} MW, "
                    "but gaps exist — dropped ticks may have exceeded threshold"
                ),
            )
        peak = max((r.p_demand_mw for r in rows), default=0.0)
        return AssertionResult(
            check=check, status="PASS",
            detail=f"Peak {peak:.3f} MW ≤ {threshold_mw} MW across {len(rows)} ticks",
        )

    if check == "min_final_bess_soc":
        if not rows:
            return AssertionResult(
                check=check, status="INCONCLUSIVE",
                detail="No timeseries rows retained",
            )
        last = rows[-1]
        # Final tick is missing when the last retained tick_index < expected last.
        # Cannot confirm finality without expected_last_tick_index when gaps exist.
        final_missing = False
        if expected_last_tick_index is not None:
            final_missing = last.tick_index < expected_last_tick_index
        elif has_gaps:
            final_missing = True

        if final_missing:
            suffix = (
                f", expected {expected_last_tick_index}"
                if expected_last_tick_index is not None
                else ""
            )
            return AssertionResult(
                check=check, status="INCONCLUSIVE",
                detail=f"Final tick not retained (last: {last.tick_index}{suffix})",
            )
        soc = last.bess_soc_fraction
        if soc >= threshold:
            return AssertionResult(
                check=check, status="PASS",
                detail=f"Final BESS SoC {soc:.1%} ≥ {threshold:.1%}",
            )
        return AssertionResult(
            check=check, status="FAIL",
            detail=f"Final BESS SoC {soc:.1%} < {threshold:.1%}",
        )

    if check == "pue_base_in_declared_range":
        if pue_base is None or pue_base_bounds is None:
            return AssertionResult(
                check=check, status="INCONCLUSIVE",
                detail="Runtime pue_base or PARAM-06 catalogue bounds unavailable",
            )
        lower, upper = pue_base_bounds
        passed = lower <= pue_base <= upper
        return AssertionResult(
            check=check,
            status="PASS" if passed else "FAIL",
            detail=(
                f"pue_base {pue_base:g} "
                f"{'within' if passed else 'outside'} "
                f"PARAM-06 range [{lower:g}, {upper:g}]"
            ),
        )

    # Unknown check — never crash; mark INCONCLUSIVE.
    return AssertionResult(
        check=str(check), status="INCONCLUSIVE",
        detail=f"Unknown assertion type: {check!r}",
    )


# ---------------------------------------------------------------------------
# evaluate_verdict — public entry point
# ---------------------------------------------------------------------------

def evaluate_verdict(
    assertions: list,
    rows: list[EvalRow],
    dropped_ticks: int,
    expected_last_tick_index: Optional[int] = None,
    pue_base: Optional[float] = None,
    pue_base_bounds: Optional[tuple[float, float]] = None,
) -> VerdictResult:
    """Evaluate all assertions against the completed run's timeseries rows.

    Parameters
    ----------
    assertions:
        list of AssertionSpec Pydantic objects or plain dicts with a 'check' key.
    rows:
        EvalRow NamedTuples, ordered ascending by tick_index.  May be empty
        (all ticks dropped).
    dropped_ticks:
        Count of RunTimeseries rows lost due to write-queue pressure (§22.2).
        Non-zero → has_gaps may be True even if retained rows show no skip.
    expected_last_tick_index:
        tick_index of the final tick of a fully-completed run.  Used by
        min_final_bess_soc to detect a missing final tick.  None = unknown.
    pue_base:
        Runtime SiteConfig value used by pue_base_in_declared_range.
    pue_base_bounds:
        PARAM-06 (minimum, maximum) supplied by the catalogue-aware caller.

    Returns
    -------
    VerdictResult with overall PASS | FAIL | INCONCLUSIVE and per-assertion
    details.  INCONCLUSIVE when assertions is empty.

    H1 gap rules:
       - Universal assertions (no_insufficient_reserve_alert, max_p_total_mw,
         no_cold_warming_contingency_capacity):
        FAIL if a retained tick violates; INCONCLUSIVE if no violation but gaps
        exist; PASS only when all retained ticks pass AND no gaps.
       - Existential assertions (alert_fires,
         declining_fuel_cell_reserve_alert_fires):
        PASS if any retained tick fired; INCONCLUSIVE if none fired but gaps
        exist; FAIL only when no retained tick fired AND no gaps.
      - Final-point assertion (min_final_bess_soc):
        PASS/FAIL when the final tick is present; INCONCLUSIVE when missing.

    Overall: FAIL if any FAIL; INCONCLUSIVE if any INCONCLUSIVE (and no FAIL);
    PASS if all PASS.  Empty assertions list → INCONCLUSIVE.
    """
    gap_count = _count_gaps(rows)
    # has_gaps is True whenever there are in-sequence gaps OR the sink reported
    # dropped ticks (the latter may not show up as sequence gaps in retained rows).
    has_gaps = gap_count > 0 or dropped_ticks > 0

    if not assertions:
        return VerdictResult(
            overall="INCONCLUSIVE",
            tick_count=len(rows),
            dropped_ticks=dropped_ticks,
            gap_count=gap_count,
        )

    results = [
        _eval_one(
            a,
            rows,
            has_gaps,
            expected_last_tick_index,
            pue_base,
            pue_base_bounds,
        )
        for a in assertions
    ]

    statuses = {r.status for r in results}
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "INCONCLUSIVE" in statuses:
        overall = "INCONCLUSIVE"
    else:
        overall = "PASS"

    return VerdictResult(
        overall=overall,
        tick_count=len(rows),
        dropped_ticks=dropped_ticks,
        gap_count=gap_count,
        assertions=results,
    )
