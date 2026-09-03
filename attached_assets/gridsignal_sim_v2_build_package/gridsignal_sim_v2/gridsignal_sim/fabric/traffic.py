"""
Job-phase to flow-set mapping (Simulator Spec 12.3).

``flows_for`` maps a Job at a given simulation time to the set of Flows it
places on each fabric.  Flow identity (flow_id) is stable for the life of the
job so the ECMP hash in model._assign() pins each elephant to the same uplink
regardless of which tick is being evaluated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Flow:
    flow_id: str
    source: str       # informational label: "job", "stressor", etc.
    fabric_id: str
    rate_bps: float
    leaf_index: int
    kind: str         # "elephant" (ECMP-pins on ecmp_hash) or "many_small" (spray)
    direction: str = "write"   # "write" or "read" -- only elephants are tested for direction


@dataclass
class PhaseSpec:
    name: str
    duration_s: float


@dataclass
class Job:
    job_id: str
    start_s: float
    phases: list[PhaseSpec]

    def current_phase(self, sim_time_s: float) -> str:
        t = self.start_s
        for p in self.phases:
            if sim_time_s < t + p.duration_s:
                return p.name
            t += p.duration_s
        return "idle"


@dataclass
class TrafficProfiles:
    """Per-phase flow templates and corroboration thresholds."""
    discrimination: dict
    phases: dict[str, list[dict]]

    @classmethod
    def load(cls, profiles_path: str | Path) -> "TrafficProfiles":
        data = json.loads(Path(profiles_path).read_text())
        return cls(
            discrimination=data["discrimination"],
            phases=data.get("phase_flows", {}),
        )


def flows_for(
    job: Job,
    sim_time_s: float,
    profiles: TrafficProfiles,
    nodes_per_leaf: int,
    leaf_capacity_bps_compute: float,
) -> tuple[str, list[Flow]]:
    """
    Return (phase_name, [Flow, ...]) for this job at sim_time_s.

    Flow generation follows the templates in ``profiles.phases[phase_name]``.
    Each template specifies:

    - fabric_id, kind, direction
    - For many_small per-leaf flows: rate_frac_of_leaf × leaf_capacity
    - For elephant flows: absolute rate_bps, leaf_index, count, flow_id_prefix
    """
    phase = job.current_phase(sim_time_s)
    templates = profiles.phases.get(phase, [])
    flows: list[Flow] = []

    for tpl in templates:
        fabric_id = tpl["fabric_id"]
        kind = tpl["kind"]
        direction = tpl.get("direction", "write")

        if kind == "many_small":
            # One many_small flow per leaf at rate_frac × leaf_capacity_bps.
            # leaf_capacity_bps is fabric-specific; for compute we use the
            # value passed in, for others it's stored in the template.
            if fabric_id == "compute":
                lcap = leaf_capacity_bps_compute
            else:
                lcap = float(tpl.get("leaf_capacity_override_bps", 1.0))
            rate = float(tpl["rate_frac"]) * lcap
            n_leaves = int(tpl["leaf_count"])
            for leaf in range(n_leaves):
                fid = f"{job.job_id}/{phase}/{fabric_id}/leaf{leaf}"
                flows.append(Flow(
                    flow_id=fid, source=job.job_id,
                    fabric_id=fabric_id, rate_bps=rate,
                    leaf_index=leaf, kind="many_small",
                    direction=direction,
                ))

        elif kind == "elephant":
            # Explicit elephant flows: count, leaf_index, rate_bps.
            count = int(tpl["count"])
            leaf_index = int(tpl["leaf_index"])
            rate_bps = float(tpl["rate_bps"])
            prefix = tpl.get("flow_id_prefix", f"{job.job_id}/{phase}/{fabric_id}/s")
            for n in range(count):
                fid = f"{prefix}{n}"
                flows.append(Flow(
                    flow_id=fid, source=job.job_id,
                    fabric_id=fabric_id, rate_bps=rate_bps,
                    leaf_index=leaf_index, kind="elephant",
                    direction=direction,
                ))

    return phase, flows
