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

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import TickResult as SimTickResult

logger = logging.getLogger("gridsignal.fabric_engine")

# Default config paths relative to the gridsignal_sim/ root (where uvicorn is
# launched from by start_prod.sh).  Override via environment variables.
_CFG_DIR = Path(os.environ.get("GS_FABRIC_CONFIG_DIR", "config"))
_FIXTURE      = _CFG_DIR / "fabric_fixture_default.json"
_CONSTANTS    = _CFG_DIR / "fabric_constants.json"
_PROFILES     = _CFG_DIR / "workload_traffic_profiles.json"
_SCENARIOS_DIR = _CFG_DIR / "scenarios"

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


# ---------------------------------------------------------------------------
# Fabric assertion evaluator (Phase 10 — S1–S8 scenarios)
# ---------------------------------------------------------------------------

@dataclass
class _FabricTickRecord:
    """Per-tick snapshot used by fabric assertion evaluation."""
    sim_time_s: float
    phases: Dict[str, str]               # job_id → phase name
    # Aggregated fabric metrics keyed by fabric_id
    mean_u: Dict[str, float]             # e.g. {"compute": 0.3, "storage": 0.1}
    loss: Dict[str, float]               # e.g. {"compute": 0.0, "storage": 0.0}
    congested_links: Dict[str, int]      # per fabric_id
    # Control path
    control_breached: bool
    control_total_ms: float
    control_gateway_ms: float
    control_dominant: str
    control_budget_ms: float
    # Discrimination
    verdict: str                          # "checkpoint_corroborated" | "no_corroboration" | …
    phase_discrimination_available: bool
    capability_tier: str
    # Per-link telemetry fields
    crc_errors: Dict[str, int]           # link_id → crc_errors
    elephant_flow_present: Dict[str, bool]  # link_id → bool


def _extract_tick_record(result: Any) -> _FabricTickRecord:
    """Extract a _FabricTickRecord from a fabric.model.TickResult."""
    # Aggregate by fabric_id
    mean_u: Dict[str, float] = {}
    loss: Dict[str, float] = {}
    congested: Dict[str, int] = {}
    crc_errors: Dict[str, int] = {}
    elephant_flow_present: Dict[str, bool] = {}

    for agg_id, agg in result.aggregates.items():
        mean_u[agg_id] = agg.mean_u
        loss[agg_id] = agg.loss_p_weighted
        congested[agg_id] = agg.congested_links

    for ls in result.links:
        crc_errors[ls.link_id] = getattr(ls, "crc_errors", 0)

    # elephant_flow_present lives in the telemetry list (list[dict]).
    for ev in getattr(result, "telemetry", []):
        link_id = ev.get("link_id", "")
        if link_id and "elephant_flow_present" in ev:
            elephant_flow_present[link_id] = bool(ev["elephant_flow_present"])

    cp = result.control
    disc = result.discrimination if isinstance(result.discrimination, dict) else {}
    return _FabricTickRecord(
        sim_time_s=result.sim_time_s,
        phases=dict(result.phases),
        mean_u=mean_u,
        loss=loss,
        congested_links=congested,
        control_breached=cp.breached,
        control_total_ms=cp.l_total_ms,
        control_gateway_ms=cp.l_gateway_ms,
        control_dominant=cp.dominant_term,
        control_budget_ms=cp.budget_ms,
        verdict=disc.get("verdict", ""),
        phase_discrimination_available=bool(disc.get("phase_discrimination_available", True)),
        capability_tier=str(disc.get("capability_tier", "current")),
        crc_errors=crc_errors,
        elephant_flow_present=elephant_flow_present,
    )


def evaluate_fabric_assertions(
    assertions: List[Dict],
    records: List[_FabricTickRecord],
) -> List[Any]:
    """Evaluate fabric-specific assertions against accumulated tick records.

    Returns a list of runtime.verdict.AssertionResult objects.
    Each assertion dict has at minimum a 'check' key; other keys depend on
    the check type.

    Assertion types handled:
      phase_exists               — phase appeared in any tick
      verdict_exists             — verdict was emitted at least once
      verdict_never              — verdict was never emitted
      metric_always              — FabricModel metric satisfies op on every tick
      metric_in_phase            — metric satisfies op in ticks where phase is active
      telemetry_field_in_phase   — link telemetry field has expected value in phase
      control_breach_exists      — NFR-2 budget was breached at least once
      gateway_in_breach          — gateway latency > value during breach ticks
      dominant_in_breach_not     — dominant term is NOT the named term during breach
      control_budget             — budget_ms == value on every tick
      capability_tier_assertion  — discrimination reports a specific tier
      phase_discrimination_false — phase_discrimination_available is False
      crc_errors_present         — CRC errors > 0 on a specific link
    """
    from runtime.verdict import AssertionResult

    results = []

    def _get_metric(rec: _FabricTickRecord, metric_key: str) -> float:
        """Resolve 'mean_u.compute', 'loss.storage', 'congested_links.storage',
        'control_latency_ms' → float."""
        if "." in metric_key:
            prefix, fabric_id = metric_key.split(".", 1)
            if prefix == "mean_u":
                return rec.mean_u.get(fabric_id, 0.0)
            if prefix == "loss":
                return rec.loss.get(fabric_id, 0.0)
            if prefix == "congested_links":
                return float(rec.congested_links.get(fabric_id, 0))
        if metric_key == "control_latency_ms":
            return rec.control_total_ms
        return 0.0

    def _op_check(val: float, op: str, threshold: float) -> bool:
        if op == "<":   return val < threshold
        if op == "<=":  return val <= threshold
        if op == ">":   return val > threshold
        if op == ">=":  return val >= threshold
        if op == "==":  return abs(val - threshold) < 1e-9
        if op == "!=":  return abs(val - threshold) >= 1e-9
        return False

    def _active_phase(rec: _FabricTickRecord, phase: str) -> bool:
        """True if any job is in the named phase at this tick."""
        return phase in rec.phases.values()

    for assertion in assertions:
        check = assertion.get("check", "")
        desc = assertion.get("description", check)

        try:
            if check == "phase_exists":
                target = assertion["phase"]
                found = any(_active_phase(r, target) for r in records)
                results.append(AssertionResult(
                    check=check,
                    status="PASS" if found else "FAIL",
                    detail=f"Phase '{target}' {'found' if found else 'not found'} in {len(records)} ticks — {desc}",
                ))

            elif check == "verdict_exists":
                target = assertion["verdict"]
                found = any(r.verdict == target for r in records)
                results.append(AssertionResult(
                    check=check,
                    status="PASS" if found else "FAIL",
                    detail=f"Verdict '{target}' {'emitted' if found else 'never emitted'} — {desc}",
                ))

            elif check == "verdict_never":
                target = assertion["verdict"]
                found = any(r.verdict == target for r in records)
                results.append(AssertionResult(
                    check=check,
                    status="FAIL" if found else "PASS",
                    detail=f"Verdict '{target}' {'was emitted (unexpected)' if found else 'never emitted (correct)'} — {desc}",
                ))

            elif check == "metric_always":
                metric = assertion["metric"]
                op = assertion["op"]
                threshold = float(assertion["value"])
                failing = []
                for r in records:
                    v = _get_metric(r, metric)
                    if not _op_check(v, op, threshold):
                        failing.append(v)
                if failing:
                    results.append(AssertionResult(
                        check=check,
                        status="FAIL",
                        detail=f"{len(failing)} ticks violated {metric} {op} {threshold}; worst={max(failing):.4f} — {desc}",
                    ))
                else:
                    vals = [_get_metric(r, metric) for r in records]
                    peak = max(vals) if vals else 0.0
                    results.append(AssertionResult(
                        check=check,
                        status="PASS",
                        detail=f"All {len(records)} ticks: {metric} {op} {threshold}; peak={peak:.4f} — {desc}",
                    ))

            elif check == "metric_in_phase":
                target_phase = assertion["phase"]
                metric = assertion["metric"]
                op = assertion["op"]
                threshold = float(assertion["value"])
                aggregate = assertion.get("aggregate", "max")
                phase_recs = [r for r in records if _active_phase(r, target_phase)]
                if not phase_recs:
                    results.append(AssertionResult(
                        check=check,
                        status="INCONCLUSIVE",
                        detail=f"Phase '{target_phase}' never observed — cannot evaluate {metric} — {desc}",
                    ))
                    continue
                vals = [_get_metric(r, metric) for r in phase_recs]
                if aggregate == "max":
                    agg_val = max(vals)
                elif aggregate == "min":
                    agg_val = min(vals)
                else:
                    agg_val = sum(vals) / len(vals)
                passed = _op_check(agg_val, op, threshold)
                results.append(AssertionResult(
                    check=check,
                    status="PASS" if passed else "FAIL",
                    detail=(
                        f"Phase '{target_phase}': {aggregate}({metric})={agg_val:.4f} "
                        f"{'satisfies' if passed else 'violates'} {op} {threshold} — {desc}"
                    ),
                ))

            elif check == "telemetry_field_in_phase":
                target_phase = assertion["phase"]
                field_name = assertion["field"]
                expected = assertion["value"]
                phase_recs = [r for r in records if _active_phase(r, target_phase)]
                if not phase_recs:
                    results.append(AssertionResult(
                        check=check,
                        status="INCONCLUSIVE",
                        detail=f"Phase '{target_phase}' never observed — {desc}",
                    ))
                    continue
                # elephant_flow_present is a per-link dict; check if any link has it True
                if field_name == "elephant_flow_present":
                    found = any(
                        any(v for v in r.elephant_flow_present.values())
                        for r in phase_recs
                    )
                    results.append(AssertionResult(
                        check=check,
                        status="PASS" if (found == expected) else "FAIL",
                        detail=f"elephant_flow_present={'any True' if found else 'all False'} in phase '{target_phase}' — {desc}",
                    ))
                else:
                    results.append(AssertionResult(
                        check=check,
                        status="INCONCLUSIVE",
                        detail=f"Unknown telemetry field '{field_name}' — {desc}",
                    ))

            elif check == "control_breach_exists":
                found = any(r.control_breached for r in records)
                results.append(AssertionResult(
                    check=check,
                    status="PASS" if found else "FAIL",
                    detail=f"NFR-2 breach {'found' if found else 'never observed'} in {len(records)} ticks — {desc}",
                ))

            elif check == "gateway_in_breach":
                threshold = float(assertion["value"])
                breach_recs = [r for r in records if r.control_breached]
                if not breach_recs:
                    results.append(AssertionResult(
                        check=check,
                        status="INCONCLUSIVE",
                        detail=f"No breach ticks observed — cannot check gateway term — {desc}",
                    ))
                    continue
                max_gw = max(r.control_gateway_ms for r in breach_recs)
                passed = max_gw > threshold
                results.append(AssertionResult(
                    check=check,
                    status="PASS" if passed else "FAIL",
                    detail=f"Max gateway_ms during breach: {max_gw:.1f} {'>' if passed else '<='} {threshold} — {desc}",
                ))

            elif check == "dominant_in_breach_not":
                term = assertion["term"]
                breach_recs = [r for r in records if r.control_breached]
                if not breach_recs:
                    results.append(AssertionResult(
                        check=check,
                        status="INCONCLUSIVE",
                        detail=f"No breach ticks observed — cannot check dominant term — {desc}",
                    ))
                    continue
                all_not = all(r.control_dominant != term for r in breach_recs)
                results.append(AssertionResult(
                    check=check,
                    status="PASS" if all_not else "FAIL",
                    detail=(
                        f"Dominant term is {'never' if all_not else 'sometimes'} '{term}' during breach — {desc}"
                    ),
                ))

            elif check == "control_budget":
                expected_budget = float(assertion["value"])
                wrong = [r for r in records if abs(r.control_budget_ms - expected_budget) > 1.0]
                if wrong:
                    results.append(AssertionResult(
                        check=check,
                        status="FAIL",
                        detail=f"{len(wrong)} ticks had budget_ms ≠ {expected_budget} — {desc}",
                    ))
                else:
                    results.append(AssertionResult(
                        check=check,
                        status="PASS",
                        detail=f"All {len(records)} ticks: budget_ms == {expected_budget} — {desc}",
                    ))

            elif check == "capability_tier_assertion":
                tier = assertion["tier"]
                wrong = [r for r in records if r.capability_tier != tier]
                if wrong:
                    actual = records[0].capability_tier if records else "unknown"
                    results.append(AssertionResult(
                        check=check,
                        status="FAIL",
                        detail=f"Expected tier '{tier}', observed '{actual}' — {desc}",
                    ))
                else:
                    results.append(AssertionResult(
                        check=check,
                        status="PASS" if records else "INCONCLUSIVE",
                        detail=f"All {len(records)} ticks report tier '{tier}' — {desc}",
                    ))

            elif check == "phase_discrimination_false":
                wrong = [r for r in records if r.phase_discrimination_available]
                if wrong:
                    results.append(AssertionResult(
                        check=check,
                        status="FAIL",
                        detail=f"{len(wrong)} ticks had phase_discrimination_available=True (expected False) — {desc}",
                    ))
                else:
                    results.append(AssertionResult(
                        check=check,
                        status="PASS" if records else "INCONCLUSIVE",
                        detail=f"All {len(records)} ticks: phase_discrimination_available=False — {desc}",
                    ))

            elif check == "crc_errors_present":
                link_id = assertion.get("link_id", "")
                found = any(r.crc_errors.get(link_id, 0) > 0 for r in records)
                results.append(AssertionResult(
                    check=check,
                    status="PASS" if found else "FAIL",
                    detail=f"CRC errors on '{link_id}': {'present' if found else 'absent'} — {desc}",
                ))

            else:
                results.append(AssertionResult(
                    check=check,
                    status="INCONCLUSIVE",
                    detail=f"Unknown fabric assertion type: '{check}' — {desc}",
                ))
        except Exception as exc:
            results.append(AssertionResult(
                check=check,
                status="INCONCLUSIVE",
                detail=f"Evaluation error: {exc} — {desc}",
            ))

    return results


class FabricEngine:
    """
    Wraps FabricModel and maintains the live-job state for an active run.
    Thread-safe for reads (latest_result is replaced atomically).

    When scenario_data is provided (from a fabric stress scenario JSON),
    the engine uses the scenario's defined job timelines, stressors, seed,
    and file paths (fixture, constants, profiles).  Accumulated TickResult
    objects are stored in a RunResult so the canonical fabric.scenario
    assertion evaluator handles all assertion types correctly.
    """

    def __init__(
        self,
        seed: int = 42,
        capability_tier: str = "current",
        scenario_data: Optional[dict] = None,
    ) -> None:
        self._seed = seed
        self._capability_tier = capability_tier
        self._jobs: list[LiveFabricJob] = []
        self._tick_counter: int = 0
        self.latest_result = None          # fabric.model.TickResult or None
        self.latest_link_utilisation: dict[str, float] = {}
        self._model = None                 # lazy-initialised on first step()

        # Fabric stress scenario support (loaded via fabric.scenario.Scenario)
        self._fabric_scenario = None       # fabric.scenario.Scenario or None
        self._fabric_run_result = None     # fabric.scenario.RunResult or None

        if scenario_data is not None:
            self._load_scenario(scenario_data)

    @property
    def has_fabric_assertions(self) -> bool:
        """True when a fabric scenario with assertions is loaded."""
        return (
            self._fabric_scenario is not None
            and bool(getattr(self._fabric_scenario, "assertions", []))
        )

    def _load_scenario(self, data: dict) -> None:
        """Load a fabric stress scenario via fabric.scenario.Scenario.load().

        This uses the scenario's declared seed, fixture, constants, and profiles
        files, ensuring deterministic and spec-correct execution.
        """
        try:
            from fabric.scenario import Scenario, RunResult, _extract_sample, _dominant_phase
            import tempfile, os

            # Scenario.load() expects a file path.  Write the data dict to a
            # temporary file so we can use the canonical loader.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir="/tmp"
            ) as f:
                json.dump(data, f)
                tmp_path = f.name

            try:
                cfg_dir = _CFG_DIR
                scenario = Scenario.load(tmp_path, config_dir=cfg_dir)
            finally:
                os.unlink(tmp_path)

            self._fabric_scenario = scenario
            # Use scenario seed and tier for the model
            self._seed = scenario.seed
            self._capability_tier = scenario.capability_tier

            # Initialise an empty RunResult to accumulate ticks during the run
            self._fabric_run_result = RunResult(scenario=scenario)

            logger.info(
                "FabricEngine: loaded scenario '%s' via Scenario.load() — "
                "%d jobs, %d stressors, %d assertions, tier=%s, seed=%d",
                scenario.scenario_id,
                len(scenario.jobs),
                len(scenario.assertions),
                len(scenario.assertions),
                scenario.capability_tier,
                scenario.seed,
            )
        except Exception:
            logger.exception("FabricEngine: failed to load scenario data")
            self._fabric_scenario = None
            self._fabric_run_result = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from fabric.model import FabricModel

            # When a fabric scenario is loaded, use its declared file paths
            # so the correct traffic profile, constants, and fixture are used.
            if self._fabric_scenario is not None:
                fixture   = self._fabric_scenario.fixture_file
                constants = self._fabric_scenario.constants_file
                profiles  = self._fabric_scenario.profiles_file
            else:
                fixture, constants, profiles = _FIXTURE, _CONSTANTS, _PROFILES

            self._model = FabricModel.from_files(
                fixture, constants, profiles,
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

        When a fabric stress scenario is loaded, the scenario's job timelines
        and stressors are used.  Each TickResult is accumulated in
        _fabric_run_result so assertion evaluation can use the full timeline.
        """
        self._ensure_model()
        if self._model is None:
            return None

        # Choose job list: scenario jobs take priority over live-derived jobs.
        if self._fabric_scenario is not None:
            jobs = self._fabric_scenario.jobs
            stressors = self._fabric_scenario.stressors
            asset_cls = self._fabric_scenario.asset_class
        else:
            stressors = None
            asset_cls = asset_class
            if not self._jobs:
                # No jobs yet — still produce fabric background traffic
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
                stressors=stressors,
                dt_s=dt_s,
                asset_class=asset_cls,
            )
            self._tick_counter += 1
            self.latest_result = result
            # Build the per-link utilisation dict (link_id → u) for the heat strip.
            self.latest_link_utilisation = {
                s.link_id: round(s.u, 4) for s in result.links
            }
            # Accumulate raw TickResult objects for post-run assertion evaluation.
            if self._fabric_run_result is not None:
                try:
                    from fabric.scenario import _extract_sample, _dominant_phase
                    self._fabric_run_result.ticks.append(result)
                    self._fabric_run_result.samples.append(_extract_sample(result))
                    self._fabric_run_result.phases.append(_dominant_phase(result))
                except Exception:
                    logger.debug("FabricEngine: failed to accumulate tick for RunResult",
                                 exc_info=True)
            return result
        except Exception:
            logger.exception("FabricEngine: tick() raised")
            return None

    def evaluate_scenario_assertions(self) -> List[Any]:
        """Evaluate all fabric scenario assertions against accumulated tick records.

        Delegates to fabric.scenario.RunResult.report() so all assertion types
        (including gray_loss_elevated, telemetry_field_in_phase, etc.) are handled
        by the canonical evaluator with correct field names.

        Returns a list of runtime.verdict.AssertionResult objects, or an empty
        list when no fabric scenario is loaded.
        """
        if self._fabric_run_result is None or self._fabric_scenario is None:
            return []
        if not self._fabric_scenario.assertions:
            return []
        from runtime.verdict import AssertionResult
        try:
            report = self._fabric_run_result.report()
        except Exception:
            logger.exception("FabricEngine: RunResult.report() failed")
            return []
        results = []
        for row in report.get("assertions", []):
            status = "PASS" if row.get("passed") else "FAIL"
            desc = row.get("description", "")
            metric = row.get("metric") or "?"
            expected = row.get("expected") or "?"
            observed = row.get("observed")
            obs_str = f"{observed:.4g}" if isinstance(observed, float) else str(observed)
            detail = f"{metric} {expected}; observed={obs_str} — {desc}"
            check_id = row.get("id", "fabric-check")
            results.append(AssertionResult(check=check_id, status=status, detail=detail))
        return results

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
