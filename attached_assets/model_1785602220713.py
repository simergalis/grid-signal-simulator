"""
Fabric model. Simulator Spec Section 12.

Every plant-plane field the Network Fabric modal shows is DERIVED from one
offered-load model. Independently generated fields are individually plausible
and mutually contradictory, and the contradiction is found by the first person
who does arithmetic on the screen.

No model inference anywhere in this path. Arithmetic over a seeded PRNG only,
for the same reason Engine Spec 21.1 excludes inference from the control plane:
a non-reproducible input makes scenario assertions untestable.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from . import prng
from .stressors import StressorSet
from .topology import Fabric, Topology
from .traffic import Flow, Job, TrafficProfiles, flows_for

# Retransmission model constants (12.6, refined)
RTO_MIN_MS = 200.0
RTO_MAX_RETRIES = 6
COMMAND_PACKETS = 4
U_CLIP = 0.995  # guards the 1/(1-u) queueing terms


# --------------------------------------------------------------------------
# Result records  (Simulator Spec 12.11 data model)
# --------------------------------------------------------------------------


@dataclass
class LinkState:
    link_id: str
    fabric_id: str
    tick: int
    demand_bps: float
    carried_bps: float
    capacity_bps: float
    u: float
    headroom_bps: float
    q_frac: float
    congested: bool
    loss_p: float
    retransmit_r: float
    down: bool = False
    optical_power_dbm: float = -1.5
    crc_errors: int = 0


@dataclass
class ControlPathSample:
    tick: int
    l_fabric_ms: float
    l_gateway_ms: float
    l_retransmit_ms: float
    l_asset_ack_ms: float
    l_total_ms: float
    budget_ms: float
    breached: bool
    dominant_term: str
    asset_class: str


@dataclass
class FabricAggregate:
    fabric_id: str
    capacity_bps: float
    carried_bps: float
    headroom_bps: float
    mean_u: float
    max_u: float
    congested_links: int
    link_count: int
    loss_p_weighted: float
    retransmit_r_weighted: float


@dataclass
class TickResult:
    tick: int
    sim_time_s: float
    phases: dict[str, str]
    links: list[LinkState]
    aggregates: dict[str, FabricAggregate]
    control: ControlPathSample
    discrimination: dict
    telemetry: list[dict]

    def modal_view(self) -> dict:
        """Exactly the plant-plane fields the Network Fabric modal renders."""
        agg = self.aggregates
        total_cap = sum(a.capacity_bps for a in agg.values())
        total_head = sum(a.headroom_bps for a in agg.values())
        carried = sum(a.carried_bps for a in agg.values())
        wl = (
            sum(a.loss_p_weighted * a.carried_bps for a in agg.values()) / carried
            if carried > 0
            else 0.0
        )
        wr = (
            sum(a.retransmit_r_weighted * a.carried_bps for a in agg.values()) / carried
            if carried > 0
            else 0.0
        )
        return {
            "topology_nodes": sum(a.link_count for a in agg.values()),
            "congested_links": sum(a.congested_links for a in agg.values()),
            "bandwidth_headroom_frac": (total_head / total_cap) if total_cap else 0.0,
            "packet_loss": wl,
            "retransmit_rate": wr,
            "control_latency_ms": self.control.l_total_ms,
        }


# --------------------------------------------------------------------------


@dataclass
class FabricModel:
    topology: Topology
    profiles: TrafficProfiles
    constants: dict
    seed: int
    capability_tier: str = "current"

    _congest_run: dict[str, int] = field(default_factory=dict, init=False)
    _elephant_run_s: float = field(default=0.0, init=False)
    _quiesce_run_s: float = field(default=0.0, init=False)
    _last_emit: dict[str, float] = field(default_factory=dict, init=False)

    # -- config helpers ----------------------------------------------------

    @classmethod
    def from_files(
        cls,
        fixture_path: str | Path,
        constants_path: str | Path,
        profiles_path: str | Path,
        seed: int,
        capability_tier: str | None = None,
    ) -> "FabricModel":
        from .topology import load_topology

        topo = load_topology(fixture_path)
        consts = json.loads(Path(constants_path).read_text())
        profs = TrafficProfiles.load(profiles_path)
        return cls(
            topology=topo,
            profiles=profs,
            constants=consts,
            seed=seed,
            capability_tier=capability_tier or topo.capability_tier,
        )

    def k(self, group: str, name: str) -> float:
        return float(self.constants[group][name])

    def reset(self) -> None:
        """Clear cross-tick state. Required before a replay so a run is
        reproducible from tick 0 (12.7)."""
        self._congest_run.clear()
        self._elephant_run_s = 0.0
        self._quiesce_run_s = 0.0
        self._last_emit.clear()

    # -- routing (12.4) ----------------------------------------------------

    def _assign(
        self, fabric: Fabric, flows: list[Flow], ecmp_offset: int, tick: int
    ) -> dict[str, float]:
        """
        Map offered flows onto leaf uplinks and return demand per link_id.

        Elephant flows on an ecmp_hash fabric are pinned to ONE uplink by hash
        of the flow identity -- a balls-in-bins draw. This is the whole reason
        hotspots appear during checkpoint and not during steady training.

        Many-small traffic, and any traffic on a sprayed fabric, is spread
        across the uplink group with a small imbalance term. Spraying works for
        many-small and fails for few-large; that asymmetry is the model.

        The hash is addressed at tick=0 so a flow's uplink is stable for its
        lifetime rather than rehashing every tick.
        """
        demand: dict[str, float] = {}
        sigma = self.k("link_metrics", "SPRAY_IMBALANCE_SIGMA")

        for fl in flows:
            leaf = fl.leaf_index % fabric.leaf_count
            pinned = fl.kind == "elephant" and fabric.routing_mode == "ecmp_hash"
            if pinned:
                up = prng.randint(
                    self.seed + ecmp_offset,
                    "fabric.ecmp",
                    0,
                    fl.flow_id,
                    fabric.leaf_uplinks,
                )
                lid = fabric.link(leaf, up).link_id
                demand[lid] = demand.get(lid, 0.0) + fl.rate_bps
            else:
                per = fl.rate_bps / fabric.leaf_uplinks
                for up in range(fabric.leaf_uplinks):
                    lid = fabric.link(leaf, up).link_id
                    jit = 1.0 + sigma * prng.normal(
                        self.seed, "fabric.jitter", tick, lid
                    )
                    demand[lid] = demand.get(lid, 0.0) + per * max(0.0, jit)
        return demand

    # -- derived metrics (12.5) -------------------------------------------

    def _link_state(
        self,
        link,
        demand: float,
        tick: int,
        down: bool,
        gray_loss: float | None,
        degrade: float | None,
    ) -> LinkState:
        cap = 0.0 if down else link.capacity_bps
        u = (demand / cap) if cap > 0 else (1.0 if demand > 0 else 0.0)

        carried = min(demand, cap)
        headroom = max(0.0, cap - demand)

        if u >= 1.0:
            q_frac = 1.0
        else:
            q_frac = min(1.0, max(0.0, (u * u) / (1.0 - u)))

        u_knee = self.k("link_metrics", "U_KNEE")
        p_max = self.k("link_metrics", "P_MAX")
        if u < u_knee:
            loss = 0.0
        else:
            x = min(1.0, (u - u_knee) / (1.0 - u_knee))
            loss = p_max * x * x
        if gray_loss is not None:
            loss = max(loss, gray_loss)

        u_cong = self.k("link_metrics", "U_CONGEST")
        sustain = int(self.k("link_metrics", "U_CONGEST_SUSTAIN_TICKS"))
        run = self._congest_run.get(link.link_id, 0)
        run = run + 1 if u >= u_cong else 0
        self._congest_run[link.link_id] = run
        congested = run >= sustain

        crc = 0
        opt = -1.5
        if degrade is not None:
            opt = -1.5 - 8.0 * degrade
            crc = int(1000 * degrade * prng.uniform(
                self.seed, "fabric.faults", tick, link.link_id))
            loss = max(loss, 1.0e-4 * degrade)

        return LinkState(
            link_id=link.link_id,
            fabric_id=link.fabric_id,
            tick=tick,
            demand_bps=demand,
            carried_bps=carried,
            capacity_bps=cap,
            u=u,
            headroom_bps=headroom,
            q_frac=q_frac,
            congested=congested,
            loss_p=loss,
            retransmit_r=loss * self.k("link_metrics", "K_RTX"),
            down=down,
            optical_power_dbm=opt,
            crc_errors=crc,
        )

    # -- control path (12.6) ----------------------------------------------

    def _control_path(
        self,
        tick: int,
        frontend_states: list[LinkState],
        compute_agg: FabricAggregate,
        asset_class: str,
    ) -> ControlPathSample:
        cp = self.topology.control_path
        active = [s for s in frontend_states if not s.down]
        u = min(U_CLIP, max((s.u for s in active), default=0.0))
        loss = max((s.loss_p for s in active), default=0.0)

        # Fabric transit: serialisation + propagation + M/M/1 queueing.
        base_ns = self.topology.hop_latency_ns
        prop_ns = self.topology.cable_prop_ns_per_m * self.topology.mean_cable_length_m
        l_fabric_ns = cp.hops * (base_ns * (1.0 / (1.0 - u)) + prop_ns)

        # PFC head-of-line blocking, lossless fabrics only. Latency
        # catastrophe with a clean loss counter.
        pfc_q = self.k("pfc", "PFC_THRESHOLD_Q_FRAC")
        fe = self.topology.fabrics["frontend"]
        if fe.lossless and max((s.q_frac for s in active), default=0.0) >= pfc_q:
            l_fabric_ns *= prng.lognormal(
                self.seed, "fabric.pfc", tick, "frontend",
                self.k("pfc", "PFC_MULTIPLIER_MEDIAN"),
                self.k("pfc", "PFC_MULTIPLIER_SIGMA"),
            )
        l_fabric_ms = l_fabric_ns / 1.0e6

        # Protocol gateway is a serial resource with a poll cycle. Congestion
        # on its network side queues commands -- this, not fabric transit, is
        # what actually consumes an NFR-2 budget measured in seconds.
        l_gateway_ms = cp.gateway_ms / (1.0 - u)

        # Retransmission: a dropped command packet costs an RTO with
        # exponential backoff.
        p_cmd = 1.0 - (1.0 - loss) ** COMMAND_PACKETS
        l_rtx_ms = 0.0
        r = prng.uniform(self.seed, "fabric.loss", tick, "control_cmd")
        if p_cmd > 0.0 and r < p_cmd:
            retries = 1
            while (
                retries < RTO_MAX_RETRIES
                and prng.uniform(self.seed, "fabric.loss", tick, f"rtx{retries}") < p_cmd
            ):
                retries += 1
            l_rtx_ms = RTO_MIN_MS * (2 ** retries - 1)

        l_ack_ms = cp.asset_ack_ms.get(asset_class, 100.0)

        jitter = prng.lognormal(
            self.seed, "fabric.jitter", tick, "control_path",
            1.0, self.k("control_path", "JITTER_SIGMA"),
        )
        terms = {
            "fabric": l_fabric_ms,
            "gateway": l_gateway_ms,
            "retransmit": l_rtx_ms,
            "asset_ack": l_ack_ms,
        }
        total = sum(terms.values()) * jitter
        return ControlPathSample(
            tick=tick,
            l_fabric_ms=l_fabric_ms,
            l_gateway_ms=l_gateway_ms,
            l_retransmit_ms=l_rtx_ms,
            l_asset_ack_ms=l_ack_ms,
            l_total_ms=total,
            budget_ms=cp.nfr2_budget_ms,
            breached=total > cp.nfr2_budget_ms,
            dominant_term=max(terms, key=terms.get),
            asset_class=asset_class,
        )

    # -- 25.5 corroboration ------------------------------------------------

    def _discriminate(
        self,
        aggregates: dict[str, FabricAggregate],
        storage_flows: list[Flow],
        dt_s: float,
    ) -> dict:
        d = self.profiles.discrimination
        quiesce_u = float(d["COMPUTE_QUIESCE_UTIL"])
        min_rate = float(d["ELEPHANT_MIN_RATE_BPS"])
        sustain_s = float(d["ELEPHANT_SUSTAIN_S"])

        # Quiescence is sustained, not instantaneous: the gap between allreduce
        # bursts is itself a quiet compute fabric and is not a phase change.
        quiet_now = aggregates["compute"].mean_u < quiesce_u
        self._quiesce_run_s = self._quiesce_run_s + dt_s if quiet_now else 0.0
        compute_quiesced = self._quiesce_run_s >= float(
            d.get("COMPUTE_QUIESCE_SUSTAIN_S", 0.0)
        )

        # Direction is the physical discriminator. A checkpoint is a WRITE.
        # Weight load at job start is an equally large READ, and a signature
        # that ignored direction would fire on job start -- corroborating a
        # checkpoint at the exact moment the job is beginning.
        elephant_now = sum(
            f.rate_bps
            for f in storage_flows
            if f.kind == "elephant" and f.direction == "write"
        ) >= min_rate
        self._elephant_run_s = self._elephant_run_s + dt_s if elephant_now else 0.0
        sustained = self._elephant_run_s >= sustain_s

        tiers = self.constants["capability_tiers"]
        available = bool(tiers[self.capability_tier]["phase_discrimination"])

        if not available:
            verdict = "unavailable"
        elif compute_quiesced and sustained:
            verdict = "checkpoint_corroborated"
        elif compute_quiesced and not sustained:
            verdict = "no_corroboration"
        else:
            verdict = "not_applicable"

        return {
            "phase_discrimination_available": available,
            "capability_tier": self.capability_tier,
            "compute_quiesced": compute_quiesced,
            "compute_quiesce_run_s": self._quiesce_run_s,
            "storage_elephant_sustained": sustained,
            "elephant_run_s": self._elephant_run_s,
            "verdict": verdict,
            "precedence_note": (
                "scheduler event > power-shape heuristic > network corroboration "
                "(Engine 25.5). This verdict may resolve the ambiguous case only; "
                "it may never override a higher-precedence signal."
            ),
        }

    # -- emission (12.9) ---------------------------------------------------

    def _telemetry(self, states: list[LinkState], sim_time_s: float) -> list[dict]:
        tiers = self.constants["capability_tiers"][self.capability_tier]
        classes = set(tiers["signal_classes"])
        interval_ms = float(self.constants["emission"]["fabric_emission_interval_ms"])
        events = []
        for s in states:
            prev = self._last_emit.get(s.link_id)
            if prev is not None and abs(s.u - prev) < 0.01 and not s.congested:
                continue  # on_change, per Engine 25.4
            self._last_emit[s.link_id] = s.u
            ev = {
                "event_id": f"{self.topology.site_id}:{s.link_id}:{s.tick}",
                "switch_id": s.link_id.split("/up")[0],
                "site_id": self.topology.site_id,
                "timestamp_s": sim_time_s,
                "interface_id": s.link_id,
                "throughput_tx": s.carried_bps,
                "throughput_rx": s.carried_bps * 0.92,
                "error_counters": {
                    "crc": s.crc_errors,
                    "drops": int(s.loss_p * 1e6),
                    "link_flaps": 1 if s.down else 0,
                },
                "optical_power_tx": s.optical_power_dbm,
                "optical_power_rx": s.optical_power_dbm - 0.4,
                "sample_interval_ms": interval_ms,
                "emission_mode": self.constants["emission"]["mode"],
                "capability_tier": self.capability_tier,
            }
            if "congestion_queue_depth" in classes:
                ev["queue_depth_frac"] = s.q_frac
            if "elephant_flow" in classes:
                ev["elephant_flow_present"] = s.u >= 0.45 and s.carried_bps > 1.0e11
            if "microburst" in classes:
                ev["microburst_count"] = int(s.q_frac * 12)
            events.append(ev)
        return events

    # -- tick --------------------------------------------------------------

    def tick(
        self,
        tick: int,
        sim_time_s: float,
        jobs: list[Job],
        stressors: StressorSet | None = None,
        dt_s: float = 1.0,
        asset_class: str = "turbine",
    ) -> TickResult:
        st = stressors or StressorSet()
        down = st.downed_links(sim_time_s)
        gray = st.gray_failures(sim_time_s)
        degraded = st.degraded_transceivers(sim_time_s)
        ecmp_off = st.ecmp_seed_offset(sim_time_s)

        # 1. offered load from job phases
        by_fabric: dict[str, list[Flow]] = {k: [] for k in self.topology.fabrics}
        phases: dict[str, str] = {}
        compute = self.topology.fabrics["compute"]
        for job in jobs:
            phase, flows = flows_for(
                job, sim_time_s, self.profiles,
                self.topology.nodes_per_leaf, compute.leaf_capacity_bps(),
            )
            phases[job.job_id] = phase
            for f in flows:
                by_fabric[f.fabric_id].append(f)

        # forced control-path congestion is offered load, not a magic number
        sev = st.control_congestion(sim_time_s)
        if sev > 0:
            fe = self.topology.fabrics["frontend"]
            for leaf in range(fe.leaf_count):
                by_fabric["frontend"].append(
                    Flow(f"stress/cpc/l{leaf}", "stressor", "frontend",
                         sev * fe.leaf_capacity_bps(), leaf, "many_small")
                )

        # 2. route, 3. derive
        states: list[LinkState] = []
        aggregates: dict[str, FabricAggregate] = {}
        for fid, fab in self.topology.fabrics.items():
            demand = self._assign(fab, by_fabric[fid], ecmp_off, tick)
            fstates = [
                self._link_state(
                    link, demand.get(link.link_id, 0.0), tick,
                    link.link_id in down,
                    gray.get(link.link_id),
                    degraded.get(link.link_id),
                )
                for link in fab.links
            ]
            states.extend(fstates)
            cap = sum(s.capacity_bps for s in fstates)
            carried = sum(s.carried_bps for s in fstates)
            aggregates[fid] = FabricAggregate(
                fabric_id=fid,
                capacity_bps=cap,
                carried_bps=carried,
                headroom_bps=sum(s.headroom_bps for s in fstates),
                mean_u=(carried / cap) if cap else 0.0,
                max_u=max((s.u for s in fstates), default=0.0),
                congested_links=sum(1 for s in fstates if s.congested),
                link_count=len(fstates),
                loss_p_weighted=(
                    sum(s.loss_p * s.carried_bps for s in fstates) / carried
                    if carried else 0.0
                ),
                retransmit_r_weighted=(
                    sum(s.retransmit_r * s.carried_bps for s in fstates) / carried
                    if carried else 0.0
                ),
            )

        control = self._control_path(
            tick, [s for s in states if s.fabric_id == "frontend"],
            aggregates["compute"], asset_class,
        )
        disc = self._discriminate(aggregates, by_fabric["storage"], dt_s)
        telem = self._telemetry(states, sim_time_s)

        return TickResult(
            tick=tick,
            sim_time_s=sim_time_s,
            phases=phases,
            links=states,
            aggregates=aggregates,
            control=control,
            discrimination=disc,
            telemetry=telem,
        )
