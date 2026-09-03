"""
Injectable stressor library (Simulator Spec 12.8).

Stressors are declared in the scenario JSON and evaluated at runtime by the
FabricModel.  Each stressor has an optional time window; outside the window
the stressor is inactive (returns empty / zero).

All stressor effects are offered-load or link-property modifications.  No
stressor ever injects a metric value directly -- adding 0.03 to a loss counter
rather than routing that much traffic through a degraded link is how
independently-generated fields become mutually contradictory.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DownedLink:
    link_id: str
    start_s: float
    end_s: float


@dataclass
class GrayFailure:
    link_id: str
    loss_floor: float   # additional loss injected (additive floor)
    start_s: float
    end_s: float


@dataclass
class DegradedTransceiver:
    link_id: str
    severity: float     # 0-1; scales optical-power shift and CRC rate
    start_s: float
    end_s: float


@dataclass
class ControlCongestion:
    severity: float     # 0-1; fraction of frontend leaf capacity injected
    start_s: float
    end_s: float


@dataclass
class EcmpSeedShift:
    offset: int         # added to seed before ECMP hash (shifts all flow pins)
    start_s: float
    end_s: float


@dataclass
class StressorSet:
    """
    Collection of stressors active for a scenario run.  Passed to
    FabricModel.tick() on every call; methods filter by sim_time_s.
    """
    downed: list[DownedLink] = field(default_factory=list)
    gray: list[GrayFailure] = field(default_factory=list)
    degraded: list[DegradedTransceiver] = field(default_factory=list)
    control: list[ControlCongestion] = field(default_factory=list)
    ecmp_shifts: list[EcmpSeedShift] = field(default_factory=list)

    def downed_links(self, sim_time_s: float) -> set[str]:
        return {
            d.link_id
            for d in self.downed
            if d.start_s <= sim_time_s < d.end_s
        }

    def gray_failures(self, sim_time_s: float) -> dict[str, float]:
        result: dict[str, float] = {}
        for g in self.gray:
            if g.start_s <= sim_time_s < g.end_s:
                result[g.link_id] = max(result.get(g.link_id, 0.0), g.loss_floor)
        return result

    def degraded_transceivers(self, sim_time_s: float) -> dict[str, float]:
        result: dict[str, float] = {}
        for dt in self.degraded:
            if dt.start_s <= sim_time_s < dt.end_s:
                result[dt.link_id] = max(result.get(dt.link_id, 0.0), dt.severity)
        return result

    def control_congestion(self, sim_time_s: float) -> float:
        sev = 0.0
        for cc in self.control:
            if cc.start_s <= sim_time_s < cc.end_s:
                sev = max(sev, cc.severity)
        return sev

    def ecmp_seed_offset(self, sim_time_s: float) -> int:
        for es in self.ecmp_shifts:
            if es.start_s <= sim_time_s < es.end_s:
                return es.offset
        return 0

    @classmethod
    def from_list(cls, specs: list[dict]) -> "StressorSet":
        """Build a StressorSet from the scenario JSON stressor list."""
        ss = cls()
        for spec in specs:
            kind = spec["kind"]
            s, e = float(spec.get("start_s", 0.0)), float(spec.get("end_s", 1e9))
            if kind == "down_link":
                ss.downed.append(DownedLink(spec["link_id"], s, e))
            elif kind == "gray_failure":
                ss.gray.append(GrayFailure(spec["link_id"], float(spec["loss_floor"]), s, e))
            elif kind == "degraded_transceiver":
                ss.degraded.append(
                    DegradedTransceiver(spec["link_id"], float(spec["severity"]), s, e)
                )
            elif kind == "control_congestion":
                ss.control.append(ControlCongestion(float(spec["severity"]), s, e))
            elif kind == "ecmp_shift":
                ss.ecmp_shifts.append(EcmpSeedShift(int(spec["offset"]), s, e))
        return ss
