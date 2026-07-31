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


# Pydantic v2 discriminated union — validated via TypeAdapter(AssertionSpec)
AssertionSpec = Annotated[
    Union[
        NoReserveAlertAssertion,
        AlertFiresAssertion,
        MaxPTotalAssertion,
        MinFinalBessSocAssertion,
    ],
    Field(discriminator="check"),
]


# ---------------------------------------------------------------------------
# EvalRow — lightweight tick summary (no Pydantic overhead in the hot path)
# ---------------------------------------------------------------------------

class EvalRow(NamedTuple):
    tick_index: int
    p_total_mw: float
    bess_soc_fraction: float
    insufficient_reserve_alert: bool


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
    else:
        check = assertion.check  # type: ignore[union-attr]
        threshold_mw = getattr(assertion, "threshold_mw", 0.0)
        threshold = getattr(assertion, "threshold", 0.0)

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
        violating = [r for r in rows if r.p_total_mw > threshold_mw]
        if violating:
            peak = max(r.p_total_mw for r in violating)
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
        peak = max((r.p_total_mw for r in rows), default=0.0)
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

    Returns
    -------
    VerdictResult with overall PASS | FAIL | INCONCLUSIVE and per-assertion
    details.  INCONCLUSIVE when assertions is empty.

    H1 gap rules:
      - Universal assertions (no_insufficient_reserve_alert, max_p_total_mw):
        FAIL if a retained tick violates; INCONCLUSIVE if no violation but gaps
        exist; PASS only when all retained ticks pass AND no gaps.
      - Existential assertion (alert_fires):
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
        _eval_one(a, rows, has_gaps, expected_last_tick_index)
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
