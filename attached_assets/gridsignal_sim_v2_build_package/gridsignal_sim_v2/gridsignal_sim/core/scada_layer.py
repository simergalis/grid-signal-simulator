"""
core/scada_layer.py — §4.6 simulated SCADA layer + §28 physical execution layer.

SimulatedScadaLayer: protocol-tagged command bus between DispatchArbitrator
output and the asset-module layer. Each channel is tagged with a protocol type
(Modbus, DNP3, IEC 61850 GOOSE/MMS per §4.6.1), configurable command latency
(in simulated ticks), message-loss probability, and max-message-size tolerance.
Defaults per protocol per §4.6.2. Uses a seeded RNG — not real randomness —
so the determinism NFR (functional spec §11; design spec §2 principle 3) holds.

SimulatedPMS: §28.4 power management system with its own shed priority order,
independent of GridSignal's curtailment priority. Where the two disagree the
mismatch is reported as a commissioning defect — the PMS order is authoritative
and GridSignal does not override it (§28.4, TC-65).

Fast load shed (TC-64): when the PMS fires a protective fast shed, GridSignal
observes the resulting load drop and must NOT compose a curtailment command in
response. It must reconcile against measured state and re-plan. The event is
recorded for forecast-error attribution as a predictive-staging failure (TC-66).

Transition modes (TC-67): OPEN_TRANSITION (default) — loss of utility supply is
a coverage discontinuity, not a smooth capacity reduction. The gap is modelled
as a temporary increase in P_dispatch_required_mw for open_transition_duration_s
seconds. GridSignal must ride through it with dispatchable assets.

Command egress boundary (TC-68): EVERY outbound command passes through
_egress_log, regardless of delivery fate. GridSignal must never issue protection
commands (islanding, synchro-check, anti-islanding, droop, protective-shed).
issue_command() raises ValueError if a protection command is attempted. Tests
capture egress_log and assert no PROTECTION_COMMANDS appear in any run.

Timing analysis (mandatory per Step 11 build plan prompt):

    Does adding this layer change evaluate_tick()'s timing characteristics
    enough to matter for design spec §4.3's "no threading needed" analysis?

    No. Simulated latency uses simulated time, not wall time — no real delay is
    introduced. deliver_pending(sim_time) is a synchronous O(pending_commands)
    scan run once per tick; the queue is bounded by asset count × protocol
    buffer. No blocking I/O. No thread synchronisation. The seeded RNG is a
    synchronous call. The §4.3 "no threading needed" conclusion is unchanged.

    Architectural decision (stated explicitly per the build plan prompt):
    The SCADA layer records what commands WOULD be sent and simulates their
    fate (delivered/dropped/truncated), but asset physics still advance
    synchronously each tick. This is correct for the simulator: the simulator
    models data-centre physics, not real-time control delays affecting that
    physics. If a future step requires modelling ACTUAL asset response delays
    (e.g., turbine setpoint takes N ticks to apply), that is a different design
    decision requiring explicit documentation — it changes the determinism
    architecture and must not be introduced silently. That decision belongs to
    Step 14+, not here.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import PmsConfig, TransitionMode

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# §4.6.1 Protocol definitions
# ---------------------------------------------------------------------------

class ProtocolType(str, Enum):
    """§4.6.1 protocol channel types."""
    MODBUS         = "modbus"           # §4.6.1 row 1
    DNP3           = "dnp3"             # §4.6.1 row 2 — degraded-link fault target
    IEC61850_GOOSE = "iec61850_goose"   # §4.6.1 row 3
    IEC61850_MMS   = "iec61850_mms"     # §4.6.1 row 4


@dataclass(frozen=True)
class ProtocolConfig:
    """Per-protocol latency and fidelity parameters (§4.6.2 defaults).

    latency_ticks:     simulated ticks before delivery (0 = same-tick).
    loss_probability:  per-command probability of silent drop [0.0, 1.0].
    max_message_bytes: commands whose payload exceeds this are TRUNCATED.
    degraded:          when True, effective loss = loss_prob × DEGRADED_FACTOR.
                       Models a degraded-link fault (§4.6.1 DNP3 row, TC).
    """
    latency_ticks:    int   = 1
    loss_probability: float = 0.001
    max_message_bytes: int  = 2048
    degraded: bool = False

    # CHOSEN (PROTO-11): a degraded link raises effective loss probability by 10×.
    DEGRADED_FACTOR: float = 10.0

    @property
    def effective_loss_probability(self) -> float:
        p = self.loss_probability * (self.DEGRADED_FACTOR if self.degraded else 1.0)
        return min(1.0, p)


# §4.6.2 protocol defaults.
_PROTOCOL_DEFAULTS: dict[ProtocolType, ProtocolConfig] = {
    ProtocolType.MODBUS:         ProtocolConfig(latency_ticks=1, loss_probability=0.001,  max_message_bytes=256),
    ProtocolType.DNP3:           ProtocolConfig(latency_ticks=2, loss_probability=0.005,  max_message_bytes=2048),
    ProtocolType.IEC61850_GOOSE: ProtocolConfig(latency_ticks=0, loss_probability=0.0001, max_message_bytes=1500),
    ProtocolType.IEC61850_MMS:   ProtocolConfig(latency_ticks=1, loss_probability=0.001,  max_message_bytes=65535),
}


# ---------------------------------------------------------------------------
# Command types and egress records
# ---------------------------------------------------------------------------

class CommandType(str, Enum):
    """Command types the SCADA layer can carry.

    GridSignal may only issue the first group.
    PROTECTION_COMMANDS (the second group) must never appear in the egress log
    (TC-68): protection is the PMS's domain, not GridSignal's.
    """
    # GridSignal MAY issue:
    TURBINE_SETPOINT = "turbine_setpoint"
    BESS_DISPATCH    = "bess_dispatch"
    LOAD_CURTAILMENT = "load_curtailment"
    PRE_STAGING      = "pre_staging"

    # GridSignal must NEVER issue (TC-68):
    ISLANDING        = "islanding"
    SYNCHRO_CHECK    = "synchro_check"
    ANTI_ISLANDING   = "anti_islanding"
    DROOP            = "droop"
    PROTECTIVE_SHED  = "protective_shed"


# Commands GridSignal must never issue (TC-68).
PROTECTION_COMMANDS: frozenset[CommandType] = frozenset({
    CommandType.ISLANDING,
    CommandType.SYNCHRO_CHECK,
    CommandType.ANTI_ISLANDING,
    CommandType.DROOP,
    CommandType.PROTECTIVE_SHED,
})


class CommandFate(str, Enum):
    PENDING   = "pending"    # not yet at target sim_time
    DELIVERED = "delivered"  # successfully arrived at target time
    DROPPED   = "dropped"    # lost due to message-loss probability
    TRUNCATED = "truncated"  # payload exceeded max_message_bytes
    EXPIRED   = "expired"    # target tick passed; evicted from queue


@dataclass
class CommandRecord:
    """One entry in the SCADA egress log.

    Every command issued appears here — delivered or not — so TC-68 can
    inspect the full egress boundary without relying on delivery fate.
    """
    command_id:           str
    command_type:         CommandType
    protocol:             ProtocolType
    asset_id:             str
    issued_at_sim_time:   float
    target_sim_time:      float       # earliest delivery time (issued + latency)
    payload_bytes:        int         = 64    # CHOSEN (PROTO-11)
    fate:                 CommandFate = CommandFate.PENDING


# ---------------------------------------------------------------------------
# SimulatedScadaLayer
# ---------------------------------------------------------------------------

class SimulatedScadaLayer:
    """§4.6 simulated SCADA layer — protocol-tagged command bus.

    Protocol assignment: supply a dict {asset_id: ProtocolType} at
    construction. Assets not in the map default to DNP3 (conservative —
    higher latency, higher loss).

    Determinism: the seeded RNG (default seed=42) guarantees byte-identical
    message-loss patterns for the same command sequence and seed. Tests may
    supply a fixed seed to get reproducible drop/deliver outcomes.

    TC-68 guard: issue_command() raises ValueError for any PROTECTION command.
    GridSignal advises and stages; it does not command protection relays.
    """

    def __init__(
        self,
        protocol_map: Optional[dict[str, ProtocolType]] = None,
        seed: int = 42,
    ) -> None:
        self._protocol_map: dict[str, ProtocolType] = protocol_map or {}
        self._rng = random.Random(seed)
        self._pending: list[CommandRecord] = []
        self._egress_log: list[CommandRecord] = []
        self._command_counter: int = 0
        self._degraded_assets: set[str] = set()

    # ------------------------------------------------------------------
    # Protocol helpers
    # ------------------------------------------------------------------

    def _protocol_for(self, asset_id: str) -> ProtocolType:
        return self._protocol_map.get(asset_id, ProtocolType.DNP3)

    def _config_for(self, protocol: ProtocolType, degraded: bool) -> ProtocolConfig:
        base = _PROTOCOL_DEFAULTS[protocol]
        if degraded:
            return ProtocolConfig(
                latency_ticks=base.latency_ticks,
                loss_probability=base.loss_probability,
                max_message_bytes=base.max_message_bytes,
                degraded=True,
            )
        return base

    # ------------------------------------------------------------------
    # Command issue / delivery
    # ------------------------------------------------------------------

    def issue_command(
        self,
        command_type: CommandType,
        asset_id: str,
        payload_bytes: int,
        sim_time: float,
        dt_seconds: float,
        degraded_link: bool = False,
    ) -> CommandRecord:
        """Issue one command to the egress boundary.

        TC-68: raises ValueError if command_type is a PROTECTION command.
        GridSignal must never issue islanding, synchro-check, anti-islanding,
        droop, or protective-shed commands.

        Message-loss and truncation fate is determined at issue time (seeded
        RNG). Pending commands are stored for deliver_pending() to drain.

        Returns the CommandRecord (fate set immediately for dropped/truncated;
        PENDING for commands that passed the protocol layer).
        """
        if command_type in PROTECTION_COMMANDS:
            raise ValueError(
                f"TC-68 VIOLATION: GridSignal must not issue protection command "
                f"{command_type.value!r}.  Protection is the PMS's domain (§28.4). "
                f"asset_id={asset_id!r} sim_time={sim_time:.1f}"
            )

        self._command_counter += 1
        protocol = self._protocol_for(asset_id)
        is_degraded = degraded_link or (asset_id in self._degraded_assets)
        cfg = self._config_for(protocol, is_degraded)

        rec = CommandRecord(
            command_id=f"cmd-{self._command_counter:06d}",
            command_type=command_type,
            protocol=protocol,
            asset_id=asset_id,
            issued_at_sim_time=sim_time,
            target_sim_time=sim_time + cfg.latency_ticks * dt_seconds,
            payload_bytes=payload_bytes,
            fate=CommandFate.PENDING,
        )

        # Protocol-layer fate (seeded RNG — deterministic).
        if payload_bytes > cfg.max_message_bytes:
            rec.fate = CommandFate.TRUNCATED
            _log.warning(
                "SCADA %s: TRUNCATED — payload %d B > %s max %d B (sim_time=%.1f)",
                rec.command_id, payload_bytes, protocol.value,
                cfg.max_message_bytes, sim_time,
            )
        elif self._rng.random() < cfg.effective_loss_probability:
            rec.fate = CommandFate.DROPPED
            _log.debug(
                "SCADA %s: DROPPED — %s loss_prob=%.4f (sim_time=%.1f)",
                rec.command_id, protocol.value,
                cfg.effective_loss_probability, sim_time,
            )
        else:
            self._pending.append(rec)

        self._egress_log.append(rec)
        return rec

    def deliver_pending(self, sim_time: float) -> list[CommandRecord]:
        """Advance the queue — deliver all commands whose target_sim_time ≤ sim_time.

        Returns the list of newly-delivered CommandRecords.
        O(pending_commands) per tick — bounded by asset count × latency ticks.
        Synchronous; no threading. See module docstring timing analysis.
        """
        delivered: list[CommandRecord] = []
        still_pending: list[CommandRecord] = []
        for rec in self._pending:
            if sim_time >= rec.target_sim_time:
                rec.fate = CommandFate.DELIVERED
                delivered.append(rec)
            else:
                still_pending.append(rec)
        self._pending = still_pending
        return delivered

    def set_degraded_link(self, asset_id: str, degraded: bool) -> None:
        """Mark (or clear) a degraded-link fault for an asset (§4.6.1 DNP3 row).

        Affects commands issued AFTER this call. In-flight PENDING commands
        had their fate set at issue time and are not retroactively affected.
        This matches physical link behaviour: a fault changes future frames,
        not frames already in transit.
        """
        if degraded:
            self._degraded_assets.add(asset_id)
        else:
            self._degraded_assets.discard(asset_id)

    def is_link_degraded(self, asset_id: str) -> bool:
        return asset_id in self._degraded_assets

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def egress_log(self) -> list[CommandRecord]:
        """All commands ever issued — delivered, dropped, truncated, or still pending.

        TC-68 test fixture: inspect this list and assert no PROTECTION_COMMANDS.
        """
        return self._egress_log

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def commands_issued_this_tick(self, sim_time: float, dt_seconds: float) -> int:
        """Count commands issued in the tick whose start is sim_time - dt_seconds."""
        window_start = sim_time - dt_seconds + 1e-9
        return sum(
            1 for r in self._egress_log
            if window_start <= r.issued_at_sim_time <= sim_time
        )


# ---------------------------------------------------------------------------
# §28.4 Simulated PMS
# ---------------------------------------------------------------------------

@dataclass
class _FastShedState:
    shed_load_mw: float
    started_at:   float
    duration_s:   float


@dataclass
class _TransitionState:
    gap_mw:     float
    started_at: float
    duration_s: float


class SimulatedPMS:
    """§28.4 simulated Power Management System.

    The PMS holds its own shed priority order, independent of GridSignal's
    curtailment priority (TC-65). Where the two disagree, a commissioning
    defect is reported — the PMS order is authoritative.

    TC-64: when a fast load shed fires, GridSignal MUST NOT compose a
    curtailment command in response. It must enter reconciliation and re-plan
    against measured state.

    TC-66: fast shed events are recorded for forecast-error attribution as
    predictive-staging failures.

    TC-67: OPEN_TRANSITION (default) — loss of utility supply is modelled as
    a coverage discontinuity (brief gap_mw increase) for open_transition_duration_s
    seconds. GridSignal must ride through it with dispatchable assets, not
    treat it as a smooth capacity reduction it can anticipate.

    Hold analysis (D1/D2/D4 pattern required for all stateful objects):

    Fast shed:
      Bound:    config.fast_shed_duration_s — CHOSEN (PROTO-11).
      Terminal: duration elapses; no external release signal required.
      No-release: shed auto-clears via the duration bound. The PMS retains
          physical authority even if the GridSignal controller is partitioned;
          the shed is bounded and terminates regardless of GridSignal state.

    Open-transition gap:
      Bound:    config.open_transition_duration_s — CHOSEN (PROTO-11).
      Terminal: duration elapses.
      No-release: the gap is a physical phenomenon (utility supply stabilisation)
          modelled as a fixed-duration event. If real stabilisation takes longer,
          the simulation conservatively clears early — an acceptable simplification
          documented here (PROTO-11). Variable-duration restoration is a Step 14+
          feature.
    """

    def __init__(self, config: PmsConfig) -> None:
        self.config = config
        self._fast_shed: Optional[_FastShedState] = None
        self._transition: Optional[_TransitionState] = None
        # TC-66: record of every fast shed event for forecast-error attribution.
        self._fast_shed_log: list[tuple[float, float]] = []   # (started_at, shed_mw)

    def inject_fast_shed(self, shed_load_mw: float, sim_time: float) -> None:
        """Inject a protective fast load shed event (TC-64/TC-66).

        shed_load_mw: MW of IT load the PMS has immediately shed.
        Auto-clears after config.fast_shed_duration_s (CHOSEN, PROTO-11).

        GridSignal must observe the resulting load reduction without composing
        a curtailment command in response (TC-64). The event is appended to
        fast_shed_log for forecast-error attribution (TC-66).
        """
        self._fast_shed = _FastShedState(
            shed_load_mw=shed_load_mw,
            started_at=sim_time,
            duration_s=self.config.fast_shed_duration_s,
        )
        self._fast_shed_log.append((sim_time, shed_load_mw))
        _log.info(
            "PMS: fast load shed at sim_time=%.1f — %.2f MW for %.0fs "
            "(TC-64/TC-66, CHOSEN PROTO-11).",
            sim_time, shed_load_mw, self.config.fast_shed_duration_s,
        )

    def inject_transition(self, sim_time: float) -> None:
        """Inject a utility-supply transition event (TC-67).

        OPEN_TRANSITION (default): models the coverage gap as a temporary
        increase in P_dispatch_required_mw for open_transition_duration_s.
        CLOSED_TRANSITION: modelled as a no-op in this simulator version
        (no gap — supply is continuous through the transfer).
        """
        if self.config.transition_mode != TransitionMode.OPEN_TRANSITION:
            _log.debug(
                "PMS: inject_transition — mode is %s; CLOSED_TRANSITION is a "
                "no-op in this simulator version.",
                self.config.transition_mode.value,
            )
            return
        self._transition = _TransitionState(
            gap_mw=self.config.open_transition_gap_mw,
            started_at=sim_time,
            duration_s=self.config.open_transition_duration_s,
        )
        _log.info(
            "PMS: open-transition at sim_time=%.1f — +%.2f MW for %.0fs "
            "(TC-67, CHOSEN PROTO-11).",
            sim_time, self.config.open_transition_gap_mw,
            self.config.open_transition_duration_s,
        )

    def tick(self, sim_time: float, dt_seconds: float) -> tuple[float, float]:
        """Advance the PMS one simulation tick.

        Returns (fast_shed_load_mw, transition_gap_mw).

        fast_shed_load_mw: MW of load currently shed by the PMS fast shed.
            0.0 when no shed is active. When > 0, GridSignal must NOT curtail
            in response (TC-64).
        transition_gap_mw: temporary additional P_dispatch_required from an
            open-transition coverage gap. 0.0 when no transition is active.
            GridSignal must ride through this with dispatchable assets (TC-67).
        """
        fast_shed_mw = 0.0
        if self._fast_shed is not None:
            if sim_time - self._fast_shed.started_at > self._fast_shed.duration_s:
                _log.debug(
                    "PMS: fast shed auto-cleared at sim_time=%.1f "
                    "(started=%.1f, duration=%.0fs).",
                    sim_time, self._fast_shed.started_at, self._fast_shed.duration_s,
                )
                self._fast_shed = None
            else:
                fast_shed_mw = self._fast_shed.shed_load_mw

        transition_gap_mw = 0.0
        if self._transition is not None:
            if sim_time - self._transition.started_at > self._transition.duration_s:
                _log.debug(
                    "PMS: open-transition gap auto-cleared at sim_time=%.1f.",
                    sim_time,
                )
                self._transition = None
            else:
                transition_gap_mw = self._transition.gap_mw

        return fast_shed_mw, transition_gap_mw

    def check_order_conflict(
        self, gs_curtailment_order: list[str]
    ) -> Optional[str]:
        """Compare GridSignal's proposed curtailment order against the PMS shed
        priority order (TC-65).

        gs_curtailment_order: ordered list of response_kind / asset IDs GridSignal
            would curtail first (index 0 = first).

        Returns a commissioning-defect description if the orders diverge on
        items that appear in both lists.  Returns None if they agree, if
        shed_priority_order is not configured, or if there is no overlap.

        The PMS order is authoritative (§28.4). GridSignal must not override it.
        Disagreement is a commissioning defect to resolve before go-live.
        """
        pms_order = self.config.shed_priority_order
        if not pms_order or not gs_curtailment_order:
            return None
        # Compare only items present in both lists, preserving each list's order.
        gs_set = set(gs_curtailment_order)
        pms_relevant = [x for x in pms_order if x in gs_set]
        pms_set = set(pms_order)
        gs_relevant = [x for x in gs_curtailment_order if x in pms_set]
        if pms_relevant != gs_relevant:
            return (
                f"commissioning_defect: curtailment order mismatch — "
                f"PMS shed order {pms_relevant} ≠ GridSignal order {gs_relevant}. "
                f"PMS order is authoritative (§28.4, TC-65). Resolve before go-live."
            )
        return None

    @property
    def is_fast_shed_active(self) -> bool:
        return self._fast_shed is not None

    @property
    def is_transition_active(self) -> bool:
        return self._transition is not None

    @property
    def fast_shed_log(self) -> list[tuple[float, float]]:
        """TC-66 record: all fast shed events (started_at_sim_time, shed_mw)."""
        return self._fast_shed_log
