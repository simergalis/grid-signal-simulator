"""
FabricEngine — Phase 10 bridge between the simulator run loop and FabricModel.

The fabric model (Simulator Spec Section 12) runs independently of the 5-second
forecast tick.  This bridge:

  1. Maintains a set of LiveFabricJob objects whose phase is derived from the
     simulator's workload-event timeline and checkpoint_states.
  2. Calls FabricModel.tick() once per simulator tick using the full 5-second
     dt_s so the discrimination accumulators advance correctly.
  3. Caches the latest TickResult so REST endpoints can serve it without
     replaying the run.

Phase derivation rules (in priority order):
  ① Before job start timestamp   → "idle"
  ② "starting" event fired       → "starting.weight_load"
  ③ Running, within checkpoint   → "checkpoint"  (time-based cycle)
  ④ Running, outside checkpoint  → "training"
  ⑤ After "stopped" event        → "idle"

The checkpoint cycle (rule ③) uses a deterministic period so every demo run
produces an identical hotspot sequence regardless of wall-clock timing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import TickResult as SimTickResult

logger = logging.getLogger("gridsignal.fabric_engine")

# Default config paths relative to the gridsignal_sim/ root (where uvicorn is
# launched from by start_prod.sh).  Override via environment variables.
_CFG_DIR = Path(os.environ.get("GS_FABRIC_CONFIG_DIR", "config"))
_FIXTURE      = _CFG_DIR / "fabric_fixture_default.json"
_CONSTANTS    = _CFG_DIR / "fabric_constants.json"
_PROFILES     = _CFG_DIR / "workload_traffic_profiles.json"

# Checkpoint cycle for the live demo: every CYCLE_PERIOD_S simulated seconds,
# the job phase switches to "checkpoint" for CKPT_DURATION_S seconds.
# After a 120 s training warmup (so the opening screen isn't immediately in
# a checkpoint), the cycle begins.
_WARMUP_S      = 120.0
_CYCLE_PERIOD_S = 600.0
_CKPT_DURATION_S = 300.0


@dataclass
class LiveFabricJob:
    """
    A fabric.Job-compatible object whose phase is derived dynamically from
    the simulator state rather than a fixed timeline.
    """
    job_id: str
    start_s: float     # sim_time when the job started (from WorkloadSignal)
    stopped: bool = False

    def current_phase(self, sim_time_s: float) -> str:
        if self.stopped or sim_time_s < self.start_s:
            return "idle"
        elapsed = sim_time_s - self.start_s
        if elapsed < 5.0:
            # Brief weight-load window at job start
            return "starting.weight_load"
        elapsed_after_warmup = elapsed - _WARMUP_S
        if elapsed_after_warmup < 0:
            return "training"
        # Deterministic checkpoint cycle
        phase_in_cycle = elapsed_after_warmup % _CYCLE_PERIOD_S
        if phase_in_cycle < _CKPT_DURATION_S:
            return "checkpoint"
        return "training"


class FabricEngine:
    """
    Wraps FabricModel and maintains the live-job state for an active run.
    Thread-safe for reads (latest_result is replaced atomically).
    """

    def __init__(self, seed: int = 42, capability_tier: str = "current") -> None:
        self._seed = seed
        self._capability_tier = capability_tier
        self._jobs: list[LiveFabricJob] = []
        self._tick_counter: int = 0
        self.latest_result = None          # fabric.model.TickResult or None
        self.latest_link_utilisation: dict[str, float] = {}
        self._model = None                 # lazy-initialised on first step()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from fabric.model import FabricModel
            self._model = FabricModel.from_files(
                _FIXTURE, _CONSTANTS, _PROFILES,
                seed=self._seed,
                capability_tier=self._capability_tier,
            )
            self._model.reset()
            logger.info("FabricEngine: model loaded (seed=%d, tier=%s)",
                        self._seed, self._capability_tier)
        except Exception:
            logger.exception("FabricEngine: failed to load fabric model — "
                             "fabric data will be absent from tick payloads")
            self._model = None

    def register_job(self, job_id: str, start_s: float) -> None:
        """Register a job that has reached its 'starting' event."""
        if not any(j.job_id == job_id for j in self._jobs):
            self._jobs.append(LiveFabricJob(job_id=job_id, start_s=start_s))

    def mark_stopped(self, job_id: str) -> None:
        for j in self._jobs:
            if j.job_id == job_id:
                j.stopped = True

    def step(
        self,
        sim_time_s: float,
        dt_s: float = 5.0,
        asset_class: str = "turbine",
    ) -> Optional[object]:
        """
        Advance the fabric model by one simulator tick.  Returns the fabric
        TickResult or None if the model failed to initialise.
        """
        self._ensure_model()
        if self._model is None:
            return None
        if not self._jobs:
            # No jobs yet — still produce fabric background traffic for baseline
            from fabric.traffic import Job, PhaseSpec
            placeholder = Job(
                job_id="job-alpha",
                start_s=0.0,
                phases=[PhaseSpec("training", 1e9)],
            )
            jobs = [placeholder]
        else:
            jobs = self._jobs  # type: ignore[assignment]

        try:
            result = self._model.tick(
                tick=self._tick_counter,
                sim_time_s=sim_time_s,
                jobs=jobs,
                stressors=None,
                dt_s=dt_s,
                asset_class=asset_class,
            )
            self._tick_counter += 1
            self.latest_result = result
            # Build the per-link utilisation dict (link_id → u) for the heat strip.
            self.latest_link_utilisation = {
                s.link_id: round(s.u, 4) for s in result.links
            }
            return result
        except Exception:
            logger.exception("FabricEngine: tick() raised")
            return None

    def modal_view(self) -> Optional[dict]:
        """Return the six modal-view fields plus link utilisation, or None."""
        if self.latest_result is None:
            return None
        mv = self.latest_result.modal_view()
        mv["link_utilisation"] = self.latest_link_utilisation
        mv["control"] = {
            "l_fabric_ms":     round(self.latest_result.control.l_fabric_ms, 2),
            "l_gateway_ms":    round(self.latest_result.control.l_gateway_ms, 2),
            "l_retransmit_ms": round(self.latest_result.control.l_retransmit_ms, 2),
            "l_asset_ack_ms":  round(self.latest_result.control.l_asset_ack_ms, 2),
            "breached":        self.latest_result.control.breached,
            "dominant_term":   self.latest_result.control.dominant_term,
            "budget_ms":       self.latest_result.control.budget_ms,
        }
        mv["discrimination"] = self.latest_result.discrimination
        return mv

    def update_from_tick(self, sim_tick: "SimTickResult") -> None:
        """
        Sync job state from the latest simulator TickResult.
        Called in _drive before step() so the phase derivation uses fresh state.
        """
        # Register any jobs that have reached a "running" checkpoint_state.
        for job_id, state in sim_tick.checkpoint_states.items():
            if state == "running":
                self.register_job(job_id, start_s=sim_tick.sim_time_seconds)
