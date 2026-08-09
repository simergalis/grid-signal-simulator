"""NAR-001 Phase A' invariant residual harness.

Standalone. Imports nothing from core/, runtime/, renewable/, api/ or frontend/.
Sole input contract: the recorder's JSONL, one line per received WebSocket
message, of the form {"seq": int, "received_wall_utc": str, "payload": {...}}.
"""
from .checkers import TickCtx, run_all, CHECKERS
from .detector import (ChangeDetector, ChangeRecord, SignalSpec, REGISTRY,
                       MissingParameters, required_parameters)
from .cooccurrence import co_occurrence, redundant_pairs, summarise
from .calibration import scan, format_scan, emissions_at
from .trend import (TrendAggregator, TrendFact, notable, trend_parameters,
                    MissingTrendParameters)
from .framefact import FrameFact, assemble, fold_redundant
from .narrator import narrate
from .smoke import main as smoke_main
from .contracts import ResidualRecord, EVALUATED, NOT_EVALUABLE
from .load import load_recording, preflight, constant_fields
from .report import analyse, write_report, main

__all__ = ["TickCtx", "run_all", "CHECKERS", "ChangeDetector", "ChangeRecord",
           "SignalSpec", "REGISTRY", "MissingParameters", "required_parameters",
           "co_occurrence", "redundant_pairs", "summarise",
           "scan", "format_scan", "emissions_at",
           "TrendAggregator", "TrendFact", "notable", "trend_parameters",
           "MissingTrendParameters", "FrameFact", "assemble",
           "fold_redundant", "narrate", "smoke_main",
           "ResidualRecord", "EVALUATED",
           "NOT_EVALUABLE", "load_recording", "preflight", "constant_fields",
           "analyse", "write_report", "main"]
