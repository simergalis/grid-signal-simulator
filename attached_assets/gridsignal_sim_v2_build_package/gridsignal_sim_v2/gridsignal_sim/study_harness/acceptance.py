"""Fixed-enumeration comparison gates for S1."""

from __future__ import annotations

from enum import Enum
from typing import Any

from .errors import BuildParityMismatchError, ProvenanceUnknownError


class AcceptanceCondition(str, Enum):
    BUILD_PARITY = "build_parity"
    BASELINE_VALID = "baseline_valid"
    INFORMED_VALID = "informed_valid"
    BASELINE_ENERGY_BALANCE = "baseline_energy_balance"
    INFORMED_ENERGY_BALANCE = "informed_energy_balance"
    BASELINE_FUEL_RECONCILED = "baseline_fuel_reconciled"
    INFORMED_FUEL_RECONCILED = "informed_fuel_reconciled"
    IDENTICAL_COMPUTE_TRACE = "identical_compute_trace"
    INFORMED_UNSERVED_ENERGY_NO_WORSE = "informed_unserved_energy_no_worse"
    INFORMED_PEAK_UNSERVED_NO_WORSE = "informed_peak_unserved_no_worse"


def _commit(metrics: dict[str, Any], key: str) -> str:
    value = metrics.get(key)
    return "" if value is None else str(value).strip()


def compare_metrics(
    baseline: dict[str, Any],
    informed: dict[str, Any],
) -> dict[str, Any]:
    baseline_engine = _commit(baseline, "engine_commit")
    informed_engine = _commit(informed, "engine_commit")
    baseline_harness = _commit(baseline, "harness_commit")
    informed_harness = _commit(informed, "harness_commit")
    commits = (
        baseline_engine,
        informed_engine,
        baseline_harness,
        informed_harness,
    )
    if any(not value or value.lower() == "unknown" for value in commits):
        raise ProvenanceUnknownError(
            baseline_run_id=str(baseline.get("run_id") or ""),
            informed_run_id=str(informed.get("run_id") or ""),
            baseline_engine_commit=baseline_engine,
            informed_engine_commit=informed_engine,
            baseline_harness_commit=baseline_harness,
            informed_harness_commit=informed_harness,
        )
    if baseline_engine != informed_engine or baseline_harness != informed_harness:
        raise BuildParityMismatchError(
            baseline_engine_commit=baseline_engine,
            informed_engine_commit=informed_engine,
            baseline_harness_commit=baseline_harness,
            informed_harness_commit=informed_harness,
        )

    baseline_balance = bool(
        baseline.get("energy_balance", {}).get("closure_status", False)
    )
    informed_balance = bool(
        informed.get("energy_balance", {}).get("closure_status", False)
    )
    baseline_valid = not bool(baseline.get("hard_violations")) and bool(
        baseline.get("constraints_valid", True)
    )
    informed_valid = not bool(informed.get("hard_violations")) and bool(
        informed.get("constraints_valid", True)
    )
    conditions = {
        AcceptanceCondition.BUILD_PARITY.value: True,
        AcceptanceCondition.BASELINE_VALID.value: baseline_valid,
        AcceptanceCondition.INFORMED_VALID.value: informed_valid,
        AcceptanceCondition.BASELINE_ENERGY_BALANCE.value: baseline_balance,
        AcceptanceCondition.INFORMED_ENERGY_BALANCE.value: informed_balance,
        AcceptanceCondition.BASELINE_FUEL_RECONCILED.value: bool(
            baseline.get("fuel_reconciled", False)
        ),
        AcceptanceCondition.INFORMED_FUEL_RECONCILED.value: bool(
            informed.get("fuel_reconciled", False)
        ),
        AcceptanceCondition.IDENTICAL_COMPUTE_TRACE.value: bool(
            baseline.get("compute_trace_sha256")
            and baseline.get("compute_trace_sha256")
            == informed.get("compute_trace_sha256")
        ),
        AcceptanceCondition.INFORMED_UNSERVED_ENERGY_NO_WORSE.value: float(
            informed.get("unserved_mwh", 0.0)
        )
        <= float(baseline.get("unserved_mwh", 0.0)) + 1e-9,
        AcceptanceCondition.INFORMED_PEAK_UNSERVED_NO_WORSE.value: float(
            informed.get("peak_unserved_mw", 0.0)
        )
        <= float(baseline.get("peak_unserved_mw", 0.0)) + 1e-9,
    }
    return {
        "conditions": conditions,
        "condition_order": [condition.value for condition in AcceptanceCondition],
        "verdict": "PASS" if all(conditions.values()) else "FAIL",
        "informed_vs_baseline": {
            "baseline_unserved_mwh": float(baseline.get("unserved_mwh", 0.0)),
            "informed_unserved_mwh": float(informed.get("unserved_mwh", 0.0)),
            "baseline_peak_unserved_mw": float(
                baseline.get("peak_unserved_mw", 0.0)
            ),
            "informed_peak_unserved_mw": float(
                informed.get("peak_unserved_mw", 0.0)
            ),
        },
    }