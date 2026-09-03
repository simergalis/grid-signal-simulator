"""
fabric — GridSignal Simulator Fabric Model (Spec Section 12).

Public surface re-exported here so tests can import without path gymnastics:

    from fabric import FabricModel, InstrumentPlane, Job, StressorSet
    from fabric import prng
    from fabric.scenario import Scenario, metrics, run
"""

from .instrument import InstrumentPlane
from .model import FabricModel, TickResult, LinkState, ControlPathSample, FabricAggregate
from .stressors import StressorSet
from .traffic import Flow, Job, TrafficProfiles
from . import prng

__all__ = [
    "FabricModel",
    "TickResult",
    "LinkState",
    "ControlPathSample",
    "FabricAggregate",
    "InstrumentPlane",
    "StressorSet",
    "Flow",
    "Job",
    "TrafficProfiles",
    "prng",
]
