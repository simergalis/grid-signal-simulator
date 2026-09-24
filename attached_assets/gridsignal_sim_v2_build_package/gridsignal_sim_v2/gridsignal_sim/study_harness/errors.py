"""Typed S1 harness failures."""

from __future__ import annotations

from typing import Any


class HarnessGuardError(AssertionError):
    """Base class for a guard that must stop a study run."""


class UnsupportedScenarioError(ValueError):
    """Raised when the study harness is asked to load an unknown scenario."""

    def __init__(
        self,
        *,
        scenario_id: str,
        supported_ids: list[str],
    ) -> None:
        self.scenario_id = scenario_id
        self.supported_ids = tuple(sorted(supported_ids))
        super().__init__(
            f"unsupported scenario ID {scenario_id!r}; "
            f"supported IDs: {', '.join(self.supported_ids)}"
        )


class FuelComponentReconciliationError(HarnessGuardError):
    def __init__(
        self,
        *,
        reported_total_mmbtu: float,
        component_sum_mmbtu: float,
        computed_total_mmbtu: float,
    ) -> None:
        self.reported_total_mmbtu = reported_total_mmbtu
        self.component_sum_mmbtu = component_sum_mmbtu
        self.computed_total_mmbtu = computed_total_mmbtu
        super().__init__(
            "fuel components do not reconcile: "
            f"reported_total={reported_total_mmbtu:.9f}, "
            f"reported_component_sum={component_sum_mmbtu:.9f}, "
            f"computed_total={computed_total_mmbtu:.9f}"
        )


class StartFuelReconciliationError(HarnessGuardError):
    def __init__(
        self,
        *,
        reported_start_fuel_mmbtu: float,
        measured_start_fuel_mmbtu: float,
        recorded_event_count: int,
        measured_event_count: int,
        release_charged: bool,
    ) -> None:
        self.reported_start_fuel_mmbtu = reported_start_fuel_mmbtu
        self.measured_start_fuel_mmbtu = measured_start_fuel_mmbtu
        self.recorded_event_count = recorded_event_count
        self.measured_event_count = measured_event_count
        self.release_charged = release_charged
        super().__init__(
            "start fuel does not reconcile with recorded start events: "
            f"reported={reported_start_fuel_mmbtu:.9f}, "
            f"measured={measured_start_fuel_mmbtu:.9f}, "
            f"recorded_events={recorded_event_count}, "
            f"measured_events={measured_event_count}, "
            f"hot_standby_release_charged={release_charged}"
        )


class FuelModelAbsentError(HarnessGuardError):
    def __init__(self, unit_ids: list[str]) -> None:
        self.unit_ids = tuple(unit_ids)
        super().__init__(
            "synchronized turbine(s) have no fuel model: "
            + ", ".join(sorted(unit_ids))
        )


class AttributableHeatRateError(HarnessGuardError):
    def __init__(
        self,
        *,
        unit_id: str,
        heat_rate_btu_per_kwh: float,
        minimum_btu_per_kwh: float,
        maximum_btu_per_kwh: float,
    ) -> None:
        self.unit_id = unit_id
        self.heat_rate_btu_per_kwh = heat_rate_btu_per_kwh
        self.minimum_btu_per_kwh = minimum_btu_per_kwh
        self.maximum_btu_per_kwh = maximum_btu_per_kwh
        super().__init__(
            f"{unit_id}: operating-point heat rate "
            f"{heat_rate_btu_per_kwh:.6f} Btu/kWh is outside the "
            f"plausible current-curve range "
            f"[{minimum_btu_per_kwh:.1f}, {maximum_btu_per_kwh:.1f}]"
        )


class BuildParityMismatchError(ValueError):
    def __init__(
        self,
        *,
        baseline_engine_commit: str,
        informed_engine_commit: str,
        baseline_harness_commit: str,
        informed_harness_commit: str,
    ) -> None:
        self.baseline_engine_commit = baseline_engine_commit
        self.informed_engine_commit = informed_engine_commit
        self.baseline_harness_commit = baseline_harness_commit
        self.informed_harness_commit = informed_harness_commit
        super().__init__(
            "build parity mismatch: "
            f"baseline(engine={baseline_engine_commit}, "
            f"harness={baseline_harness_commit}) versus "
            f"informed(engine={informed_engine_commit}, "
            f"harness={informed_harness_commit})"
        )


class ArtifactSizeError(ValueError):
    pass


class ArtifactPathError(IOError):
    pass


def error_payload(error: Exception) -> dict[str, Any]:
    """Serialize a typed guard without weakening the exception itself."""
    return {
        "type": type(error).__name__,
        "message": str(error),
    }