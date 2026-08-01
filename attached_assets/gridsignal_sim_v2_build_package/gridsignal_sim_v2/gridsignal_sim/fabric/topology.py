"""
Topology fixture loading (Simulator Spec 12.2).

Reads ``fabric_fixture_default.json`` (or a variant supplied by a scenario)
and constructs the Topology object the FabricModel consumes.  All link IDs are
constructed deterministically from fabric name, leaf index, and uplink index so
that the PRNG addressing in model._assign() is stable across configuration
changes that preserve topology shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Link:
    link_id: str
    fabric_id: str
    capacity_bps: float


@dataclass
class Fabric:
    fabric_id: str
    leaf_count: int
    leaf_uplinks: int
    link_capacity_bps: float
    routing_mode: str   # "ecmp_hash" or "spray"
    lossless: bool
    links: list[Link] = field(default_factory=list)

    def link(self, leaf: int, uplink: int) -> Link:
        idx = leaf * self.leaf_uplinks + uplink
        return self.links[idx]

    def leaf_capacity_bps(self) -> float:
        return self.leaf_uplinks * self.link_capacity_bps


@dataclass(frozen=True)
class ControlPath:
    hops: int
    gateway_ms: float
    asset_ack_ms: dict[str, float]
    nfr2_budget_ms: float


@dataclass
class Topology:
    site_id: str
    capability_tier: str
    hop_latency_ns: float
    cable_prop_ns_per_m: float
    mean_cable_length_m: float
    nodes_per_leaf: int
    fabrics: dict[str, Fabric]
    control_path: ControlPath


def _build_links(fabric_id: str, fab: Fabric) -> list[Link]:
    links = []
    for leaf in range(fab.leaf_count):
        for up in range(fab.leaf_uplinks):
            lid = f"{fabric_id}/leaf{leaf}/up{up}"
            links.append(Link(link_id=lid, fabric_id=fabric_id,
                               capacity_bps=fab.link_capacity_bps))
    return links


def load_topology(fixture_path: str | Path) -> Topology:
    data = json.loads(Path(fixture_path).read_text())

    fabrics: dict[str, Fabric] = {}
    for fid, fspec in data["fabrics"].items():
        cap_bps = float(fspec["link_capacity_gbps"]) * 1e9
        fab = Fabric(
            fabric_id=fid,
            leaf_count=int(fspec["leaf_count"]),
            leaf_uplinks=int(fspec["leaf_uplinks"]),
            link_capacity_bps=cap_bps,
            routing_mode=fspec["routing_mode"],
            lossless=bool(fspec.get("lossless", False)),
        )
        fab.links = _build_links(fid, fab)
        fabrics[fid] = fab

    cp_spec = data["control_path"]
    cp = ControlPath(
        hops=int(cp_spec["hops"]),
        gateway_ms=float(cp_spec["gateway_ms"]),
        asset_ack_ms={k: float(v) for k, v in cp_spec["asset_ack_ms"].items()},
        nfr2_budget_ms=float(cp_spec["nfr2_budget_ms"]),
    )

    return Topology(
        site_id=data["site_id"],
        capability_tier=data.get("capability_tier", "current"),
        hop_latency_ns=float(data["hop_latency_ns"]),
        cable_prop_ns_per_m=float(data["cable_prop_ns_per_m"]),
        mean_cable_length_m=float(data["mean_cable_length_m"]),
        nodes_per_leaf=int(data["nodes_per_leaf"]),
        fabrics=fabrics,
        control_path=cp,
    )
