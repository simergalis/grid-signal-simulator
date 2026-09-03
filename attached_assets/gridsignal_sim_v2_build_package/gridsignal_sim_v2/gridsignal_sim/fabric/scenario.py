"""
Scenario loading, execution, metric extraction, and assertion evaluation.

A Scenario is a JSON document that specifies a seed, jobs (with phase
timelines), stressors, and a list of assertions.  ``run()`` evaluates all
ticks, builds a RunResult, then evaluates every assertion so ``report()``
returns a pass/fail row per assertion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import FabricModel, TickResult
from .stressors import StressorSet
from .traffic import Job, PhaseSpec


# ---------------------------------------------------------------------------
# Scenario dataclass
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    scenario_id: str
    seed: int
    duration_s: float
    dt_s: float
    capability_tier: str
    asset_class: str
    profiles_file: str           # resolved path at load time
    fixture_file: str
    constants_file: str
    jobs: list[Job]
    stressors: StressorSet
    assertions: list[dict]

    @classmethod
    def load(cls, path: str | Path, config_dir: str | Path) -> "Scenario":
        path = Path(path)
        cfg = Path(config_dir)
        data = json.loads(path.read_text())

        jobs = []
        for j in data.get("jobs", []):
            phases = [PhaseSpec(p["name"], float(p["duration_s"]))
                      for p in j["phases"]]
            jobs.append(Job(
                job_id=j["job_id"],
                start_s=float(j.get("start_s", 0.0)),
                phases=phases,
            ))

        stressors = StressorSet.from_list(data.get("stressors", []))

        profiles_file = str(cfg / data.get("profiles", "workload_traffic_profiles.json"))
        fixture_file = str(cfg / data.get("fixture", "fabric_fixture_default.json"))
        constants_file = str(cfg / data.get("constants", "fabric_constants.json"))

        return cls(
            scenario_id=data["scenario_id"],
            seed=int(data.get("seed", 42)),
            duration_s=float(data["duration_s"]),
            dt_s=float(data.get("dt_s", 0.25)),
            capability_tier=data.get("capability_tier", "current"),
            asset_class=data.get("asset_class", "turbine"),
            profiles_file=profiles_file,
            fixture_file=fixture_file,
            constants_file=constants_file,
            jobs=jobs,
            stressors=stressors,
            assertions=data.get("assertions", []),
        )


# ---------------------------------------------------------------------------
# RunResult
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    scenario: Scenario
    ticks: list[TickResult] = field(default_factory=list)
    samples: list[dict] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)

    def report(self) -> dict:
        """Evaluate assertions and return a pass/fail report."""
        results = []
        for a in self.scenario.assertions:
            row = _evaluate(a, self)
            results.append(row)
        return {"scenario_id": self.scenario.scenario_id, "assertions": results}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def run(scenario: Scenario) -> RunResult:
    """
    Execute a scenario and return a RunResult.

    FabricModel.reset() is called before the first tick so that replaying
    the same scenario at the same seed produces identical output (12.7).
    """
    model = FabricModel.from_files(
        scenario.fixture_file,
        scenario.constants_file,
        scenario.profiles_file,
        seed=scenario.seed,
        capability_tier=scenario.capability_tier,
    )
    model.reset()

    result = RunResult(scenario=scenario)
    t = 0.0
    tick_idx = 0

    while t < scenario.duration_s - 1e-9:
        tr = model.tick(
            tick=tick_idx,
            sim_time_s=t,
            jobs=scenario.jobs,
            stressors=scenario.stressors,
            dt_s=scenario.dt_s,
            asset_class=scenario.asset_class,
        )
        result.ticks.append(tr)
        result.samples.append(_extract_sample(tr))
        result.phases.append(_dominant_phase(tr))
        t += scenario.dt_s
        tick_idx += 1

    return result


def metrics(result: RunResult) -> list[dict]:
    """Return the per-tick metric dicts (same as result.samples)."""
    return result.samples


# ---------------------------------------------------------------------------
# Sample extraction
# ---------------------------------------------------------------------------


def _extract_sample(tr: TickResult) -> dict:
    s: dict[str, Any] = {}
    for fid, agg in tr.aggregates.items():
        s[f"congested_links.{fid}"] = agg.congested_links
        s[f"mean_u.{fid}"] = agg.mean_u
        s[f"max_u.{fid}"] = agg.max_u
        s[f"loss.{fid}"] = agg.loss_p_weighted
        s[f"retransmit.{fid}"] = agg.retransmit_r_weighted
        s[f"headroom_frac.{fid}"] = (
            agg.headroom_bps / agg.capacity_bps if agg.capacity_bps else 1.0
        )
    s["control_latency_ms"] = tr.control.l_total_ms
    s["control_breached"] = tr.control.breached
    s["control_dominant"] = tr.control.dominant_term
    s["verdict"] = tr.discrimination.get("verdict", "unavailable")
    return s


def _dominant_phase(tr: TickResult) -> str:
    """Return the phase name for the first non-idle job in this tick."""
    for phase in tr.phases.values():
        if phase != "idle":
            return phase
    return "idle"


# ---------------------------------------------------------------------------
# Assertion evaluator
# ---------------------------------------------------------------------------

_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _evaluate(a: dict, r: RunResult) -> dict:
    check = a["check"]
    aid = a.get("id", "?")
    desc = a.get("description", check)

    try:
        if check == "phase_exists":
            phase = a["phase"]
            passed = any(p == phase for p in r.phases)
            return _row(aid, passed, desc, "phase_count",
                        f"> 0", sum(1 for p in r.phases if p == phase))

        if check == "metric_in_phase":
            phase = a["phase"]
            metric = a["metric"]
            op = a["op"]
            threshold = float(a["value"])
            fn = _OPS[op]
            phase_samples = [s[metric] for s, p in zip(r.samples, r.phases)
                             if p == phase and metric in s]
            if not phase_samples:
                return _row(aid, False, desc, metric,
                            f"{op} {threshold}", "no_phase_ticks")
            agg_fn = a.get("aggregate", "max")
            obs = max(phase_samples) if agg_fn == "max" else (
                min(phase_samples) if agg_fn == "min" else
                sum(phase_samples) / len(phase_samples)
            )
            passed = fn(obs, threshold)
            return _row(aid, passed, desc, metric,
                        f"{op} {threshold}", obs)

        if check == "metric_always":
            metric = a["metric"]
            op = a["op"]
            threshold = float(a["value"])
            fn = _OPS[op]
            vals = [s[metric] for s in r.samples if metric in s]
            if not vals:
                return _row(aid, False, desc, metric, f"{op} {threshold}", "no_data")
            obs = max(vals) if op in ("==", "<=", "<") else min(vals)
            passed = all(fn(v, threshold) for v in vals)
            return _row(aid, passed, desc, metric,
                        f"{op} {threshold}", max(vals) if not passed else obs)

        if check == "verdict_exists":
            verdict = a["verdict"]
            obs = sum(1 for s in r.samples if s.get("verdict") == verdict)
            return _row(aid, obs > 0, desc, "verdict_count", f"> 0", obs)

        if check == "verdict_never":
            verdict = a["verdict"]
            obs = sum(1 for s in r.samples if s.get("verdict") == verdict)
            return _row(aid, obs == 0, desc, "verdict_count", "== 0", obs)

        if check == "telemetry_field_in_phase":
            phase = a["phase"]
            fld = a["field"]
            expected = a["value"]
            phase_ticks = [t for t, p in zip(r.ticks, r.phases) if p == phase]
            hit = any(
                e.get(fld) == expected
                for t in phase_ticks
                for e in t.telemetry
            )
            return _row(aid, hit, desc, fld, f"== {expected}", hit)

        if check == "control_breach_exists":
            obs = sum(1 for t in r.ticks if t.control.breached)
            return _row(aid, obs > 0, desc, "breach_count", "> 0", obs)

        if check == "control_budget":
            budget = float(a["value"])
            obs_vals = [t.control.budget_ms for t in r.ticks]
            obs = obs_vals[0] if obs_vals else None
            passed = all(v == budget for v in obs_vals)
            return _row(aid, passed, desc, "budget_ms", f"== {budget}", obs)

        if check == "gateway_in_breach":
            threshold = float(a["value"])
            breaches = [t for t in r.ticks if t.control.breached]
            if not breaches:
                return _row(aid, False, desc, "l_gateway_ms",
                            f"> {threshold}", "no_breach_ticks")
            obs = max(t.control.l_gateway_ms for t in breaches)
            return _row(aid, obs > threshold, desc, "l_gateway_ms",
                        f"> {threshold}", obs)

        if check == "dominant_in_breach_not":
            forbidden = a["term"]
            breaches = [t for t in r.ticks if t.control.breached]
            if not breaches:
                return _row(aid, True, desc, "dominant_term", f"!= {forbidden}", "no_breach")
            obs = [t.control.dominant_term for t in breaches]
            passed = all(d != forbidden for d in obs)
            return _row(aid, passed, desc, "dominant_term",
                        f"!= {forbidden}", set(obs))

        if check == "capability_tier_assertion":
            tier = a["tier"]
            obs = r.ticks[0].discrimination.get("capability_tier") if r.ticks else None
            return _row(aid, obs == tier, desc, "capability_tier", f"== {tier}", obs)

        if check == "phase_discrimination_false":
            obs_vals = [t.discrimination.get("phase_discrimination_available")
                        for t in r.ticks]
            passed = all(v is False for v in obs_vals)
            return _row(aid, passed, desc, "phase_discrimination_available",
                        "== False", obs_vals[0] if obs_vals else None)

        if check == "gray_loss_elevated":
            link_id = a["link_id"]
            min_loss = float(a["min_loss"])
            max_loss = 0.0
            for tr in r.ticks:
                for ls in tr.links:
                    if ls.link_id == link_id:
                        max_loss = max(max_loss, ls.loss_p)
            passed = max_loss >= min_loss
            return _row(aid, passed, desc, f"loss.{link_id}",
                        f">= {min_loss}", max_loss)

        if check == "crc_errors_present":
            link_id = a.get("link_id")
            found = any(
                ls.crc_errors > 0
                for tr in r.ticks
                for ls in tr.links
                if link_id is None or ls.link_id == link_id
            )
            return _row(aid, found, desc, "crc_errors", "> 0", found)

        return _row(aid, False, desc, None, None, f"unknown check {check!r}")

    except Exception as exc:  # noqa: BLE001
        return _row(aid, False, desc, None, None, f"error: {exc}")


def _row(aid, passed, desc, metric, expected, observed):
    return {
        "id": aid,
        "passed": passed,
        "description": desc,
        "metric": metric,
        "expected": expected,
        "observed": observed,
    }
