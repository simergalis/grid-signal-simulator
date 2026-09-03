"""Phase 1-2 Addendum H BESS sizing sweep and aggregation tools.

This package is intentionally outside ``core/``.  It is a thin scenario and
trace/aggregation layer around the existing dispatch implementation; it does
not contain an independent shortfall or bridging calculation.
"""

from .aggregation import (
    DEFAULT_MARGIN_PCT,
    BessSizingAggregation,
    PercentileSummary,
    ScenarioSizingMetrics,
    aggregate_bess_sizing_sweep,
    integrate_bess_output_mwh,
)
from .driver import (
    BessSizingSweepResult,
    ScenarioTrace,
    StageTrace,
    TickTrace,
    run_bess_sizing_scenario,
    run_bess_sizing_sweep,
)
from .models import (
    AnchorMode,
    BessSizingFleetConfig,
    BessSizingScenario,
    DispatchStep,
    RenewableSample,
    ScenarioType,
    SocCyclingPolicy,
    ThermalParameters,
    WorkloadEnvelope,
)
from .scenarios import (
    generate_bess_sizing_scenarios,
    generate_seeded_workload_envelope,
    make_tc_h1_worked_example,
)

__all__ = [
    "AnchorMode",
    "DEFAULT_MARGIN_PCT",
    "BessSizingAggregation",
    "BessSizingFleetConfig",
    "BessSizingScenario",
    "BessSizingSweepResult",
    "DispatchStep",
    "PercentileSummary",
    "RenewableSample",
    "ScenarioTrace",
    "ScenarioType",
    "ScenarioSizingMetrics",
    "SocCyclingPolicy",
    "StageTrace",
    "ThermalParameters",
    "TickTrace",
    "WorkloadEnvelope",
    "aggregate_bess_sizing_sweep",
    "generate_bess_sizing_scenarios",
    "generate_seeded_workload_envelope",
    "integrate_bess_output_mwh",
    "make_tc_h1_worked_example",
    "run_bess_sizing_scenario",
    "run_bess_sizing_sweep",
]