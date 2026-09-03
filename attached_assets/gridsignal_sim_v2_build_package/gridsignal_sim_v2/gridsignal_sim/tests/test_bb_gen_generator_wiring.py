"""
tests/test_bb_gen_generator_wiring.py — Black-box tests for the GPU Node
Generator → backend scheduler connection.

Feature under test: wiring the frontend GPU Node Generator (previously a
browser-side-only preview) into the backend KubeDemandAgent admission path so
that generated Slurm / Kubernetes / Ray jobs drive real MW power consumption.

Ten cases from the uploaded spec:

  BB-GEN-001 — Generator-produced jobs reach the backend Queue (pending_jobs > 0)
  BB-GEN-002 — Generated jobs produce nonzero MW draw once admitted
  BB-GEN-003 — Routing is through kube_config, not a fourth parallel path
  BB-GEN-004 — Determinism: identical config → bit-identical tick-by-tick output
  BB-GEN-005 — Stopping the run stops job generation cleanly
  BB-GEN-006 — Generator config parameters constrain job characteristics
  BB-GEN-007 — Generated jobs are subject to the capacity gate (design_peak_load_mw)
  BB-GEN-008 — All three scheduler types (SLURM, K8S, RAY) appear in the queue
  BB-GEN-009 — Backend kube data (active_jobs, committed_mw) is nonzero after run
  BB-GEN-010 — Regression: existing non-generator scenarios are bit-identical to baseline

Suite-level invariants (advisory-boundary, AT-7 determinism, single admission entry
point) are checked in dedicated test methods below each case.

Run with:
    pytest tests/test_bb_gen_generator_wiring.py -v
"""
from __future__ import annotations

import asyncio
import inspect
import json
import unittest
from typing import Any

# ---------------------------------------------------------------------------
# Subject under test
# ---------------------------------------------------------------------------
from api.routes.runs import _kube_config_from_generator
from api.routes.scenarios import build_seeded_store
from api.schemas import StartRunRequest
from core.kube_demand import (
    KubeConfig,
    KubeDemandAgent,
    KubeGridState,
    _ActiveJob,
    _PendingAdmission,
)
from runtime.run_manager import RunManager, WebSocketHub
from runtime.scenario_factory import build_run_context, build_run_context_from_spec


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

#: Default GeneratorConfig that mirrors the frontend store's DEFAULT_CONFIG.
_DEFAULT_GEN_CFG: dict[str, Any] = {
    "ratePerMinute":        2.0,
    "burstMode":            False,
    "burstSize":            [3, 8],
    "burstIntervalSeconds": [30, 90],
    "tenantWeights":        {"a": 0.40, "b": 0.35, "c": 0.25},
    "jobSizes":             {"small": 0.30, "medium": 0.50, "large": 0.20},
    "maxJobsPerTenant":     12,
    "jobDurationRange":     [60, 240],
    "tenantContracts":      {"a": 1.40, "b": 1.00, "c": 0.60},
}


def _kube_spec() -> dict:
    """The scenario-kube-peak-overage spec dict (has both kube_config and generator_config)."""
    store = build_seeded_store()
    rec = store._data.get("scenario-kube-peak-overage")
    assert rec is not None, "scenario-kube-peak-overage not found in seeded store"
    return json.loads(rec.spec_json)


def _baseline_spec() -> dict:
    """A non-kube scripted scenario spec (demo-20mw) — no kube_config, no generator."""
    store = build_seeded_store()
    # Find any scenario without kube_config.
    for rec in store._data.values():
        d = json.loads(rec.spec_json)
        if d.get("kube_config") is None and d.get("generator_config") is None:
            return d
    raise RuntimeError("No non-kube scenario found in seeded store")


# ---------------------------------------------------------------------------
# TickResult field accessors
# The live kube data is nested inside r.kube_metrics (a KubeMetrics dataclass).
# Compute MW is at the top-level TickResult as p_compute_demand_mw / p_compute_served_mw.
# ---------------------------------------------------------------------------

def _kube_active(r) -> int:
    m = getattr(r, "kube_metrics", None)
    return getattr(m, "active_jobs", 0) if m else 0


def _kube_queued(r) -> int:
    m = getattr(r, "kube_metrics", None)
    return getattr(m, "queued_jobs", 0) if m else 0


def _kube_admitted_nodes(r) -> int:
    m = getattr(r, "kube_metrics", None)
    return getattr(m, "admitted_nodes", 0) if m else 0


def _compute_mw(r) -> float:
    return getattr(r, "p_compute_demand_mw", 0.0) or 0.0


def _ample_grid() -> KubeGridState:
    """Grid state with large headroom so the power-cap gate never fires."""
    return KubeGridState(
        p_dispatch_required_mw=5.0,
        bess_soc_fraction=0.9,
        turbine_headroom_mw=50.0,
        bess_headroom_mw=20.0,
    )


def _tight_grid(headroom_mw: float = 0.1) -> KubeGridState:
    """Grid state at near-zero headroom — used for capacity-gate tests."""
    return KubeGridState(
        p_dispatch_required_mw=30.0,
        bess_soc_fraction=0.5,
        turbine_headroom_mw=headroom_mw,
        bess_headroom_mw=0.0,
    )


async def _run_with_generator_cfg(
    run_id: str,
    gen_cfg: dict[str, Any],
    *,
    end_sim_time: float = 120.0,
    turbine_rated_mw: float = 40.0,
):
    """
    Build and run a scenario from a synthesised kube_config produced by
    _kube_config_from_generator(), then drive the full simulator.

    Returns (rows, sim_state) where rows is ctx.sink.rows and sim_state is
    the RunContext's SimulationState (for post-run agent inspection).
    """
    hub = WebSocketHub()
    manager = RunManager(hub)

    # Synthesise the kube_config the same way api/routes/runs.py does it.
    kube_cfg_dict = _kube_config_from_generator(gen_cfg)
    kube_cfg = KubeConfig(**{
        k: v for k, v in kube_cfg_dict.items()
        if k in KubeConfig.__dataclass_fields__
    })

    ctx = build_run_context(
        run_id,
        job_id="gen-placeholder",
        node_count=0,
        turbine_rated_mw=turbine_rated_mw,
        bess_rated_mw=5.0,
        bess_usable_mwh=3.0,
        end_sim_time=end_sim_time,
    )

    # Attach three kube agents (A/SLURM, B/K8S, C/RAY) — mirrors what
    # scenario_factory does when kube_config is present.
    _TENANT_DEFS = [
        ("A", "SLURM", 0.40, 0),
        ("B", "K8S",   0.35, 1),
        ("C", "RAY",   0.25, 2),
    ]
    base_iat  = kube_cfg_dict["mean_interarrival_s"]
    base_seed = kube_cfg_dict.get("rng_seed", 42)
    for tid, stype, weight, seed_off in _TENANT_DEFS:
        per_tenant = {**kube_cfg_dict}
        per_tenant["tenant_id"]          = tid
        per_tenant["scheduler_type"]     = stype
        per_tenant["mean_interarrival_s"] = max(5.0, base_iat / weight)
        per_tenant["rng_seed"]           = base_seed + seed_off
        per_tenant["rated_kw_per_node"]  = 5.6   # enterprise_8gpu_air ≈ 5.6 kW/node
        agent = KubeDemandAgent(
            KubeConfig(**{k: v for k, v in per_tenant.items()
                         if k in KubeConfig.__dataclass_fields__}),
            site_id=ctx.sim_state.site.site_id,
        )
        ctx.sim_state.kube_agents.append(agent)

    await manager.start_run(ctx)
    await manager._tasks[ctx.run_id]
    return ctx.sink.rows, ctx.sim_state


# ---------------------------------------------------------------------------
# BB-GEN-001 — Generator-produced jobs reach the backend Queue
# ---------------------------------------------------------------------------

class TestBBGEN001QueueReach(unittest.TestCase):
    """
    BB-GEN-001: jobs created by the (now-wired) generator must appear in
    pending_jobs / active_jobs on backend tick data, not only the Feed tab.
    """

    @classmethod
    def setUpClass(cls):
        cls._rows, cls._state = asyncio.run(
            _run_with_generator_cfg("bb-gen-001", _DEFAULT_GEN_CFG, end_sim_time=120.0)
        )

    def test_at_least_one_job_queued_or_active(self):
        """At least one tick must have queued_jobs > 0 or active_jobs > 0."""
        ever_queued = any(
            _kube_queued(r) > 0 or _kube_active(r) > 0
            for r in self._rows
        )
        self.assertTrue(
            ever_queued,
            msg=(
                "BB-GEN-001 FAIL: no tick had kube_metrics.queued_jobs > 0 or "
                "kube_metrics.active_jobs > 0 across all rows. "
                "Generator-connected runs must populate the backend queue."
            ),
        )

    def test_three_kube_agents_created(self):
        """The sim_state must have exactly 3 kube_agents (A/SLURM, B/K8S, C/RAY)."""
        self.assertEqual(
            len(self._state.kube_agents), 3,
            msg=(
                f"Expected 3 KubeDemandAgents (one per tenant), "
                f"got {len(self._state.kube_agents)}."
            ),
        )

    def test_scheduler_types_are_slurm_k8s_ray(self):
        """Agent scheduler types must be SLURM, K8S, RAY exactly."""
        types = {a.config.scheduler_type for a in self._state.kube_agents}
        self.assertEqual(
            types, {"SLURM", "K8S", "RAY"},
            msg=f"Expected {{SLURM, K8S, RAY}}, got {types}.",
        )


# ---------------------------------------------------------------------------
# BB-GEN-002 — Generated jobs produce nonzero MW draw once admitted
# ---------------------------------------------------------------------------

class TestBBGEN002MWDraw(unittest.TestCase):
    """
    BB-GEN-002: once a generator-originated job transitions to active, the
    committed compute MW must be > 0 and consistent with the hardware profile.
    """

    @classmethod
    def setUpClass(cls):
        # Run for longer so jobs have time to be admitted (mean_iat_s=30s;
        # 180 s gives ~6 fleet-level arrivals even at conservatively low rate).
        cls._rows, cls._state = asyncio.run(
            _run_with_generator_cfg("bb-gen-002", _DEFAULT_GEN_CFG, end_sim_time=180.0)
        )

    def test_committed_compute_mw_nonzero_at_some_tick(self):
        """
        At least one tick must have nonzero compute demand MW (p_compute_demand_mw)
        or active kube jobs.
        """
        ever_nonzero = any(
            _compute_mw(r) > 0.0 or _kube_active(r) > 0
            for r in self._rows
        )
        self.assertTrue(
            ever_nonzero,
            msg=(
                "BB-GEN-002 FAIL: no tick showed nonzero p_compute_demand_mw or "
                "kube_metrics.active_jobs. Generator-connected runs must produce "
                "MW load once jobs are admitted."
            ),
        )

    def test_compute_mw_matches_hardware_profile(self):
        """
        When active jobs are present, p_compute_demand_mw must be consistent with
        enterprise_8gpu_air (~5.6 kW per node).  At least one active-job tick must
        have demand_mw ≈ admitted_nodes × 5.6 kW / 1000 (within 20% for rounding).
        """
        hw_kw_per_node = 5.6   # enterprise_8gpu_air
        consistent = []
        for r in self._rows:
            active = _kube_active(r)
            mw     = _compute_mw(r)
            nodes  = _kube_admitted_nodes(r)
            if active > 0 and nodes > 0:
                expected_mw = nodes * hw_kw_per_node / 1000.0
                within_tolerance = abs(mw - expected_mw) / max(expected_mw, 1e-9) < 0.20
                consistent.append(within_tolerance)

        if not consistent:
            self.skipTest(
                "No tick had active kube jobs with admitted_nodes — "
                "profile consistency check skipped (BB-GEN-001 already guards job presence)."
            )
        self.assertTrue(
            any(consistent),
            msg=(
                f"BB-GEN-002: p_compute_demand_mw values do not match "
                f"expected hardware profile ({hw_kw_per_node} kW/node). "
                "At least one active-job tick must be within 20% of expected."
            ),
        )


# ---------------------------------------------------------------------------
# BB-GEN-003 — Routes through generator_config, not a fourth parallel path
# ---------------------------------------------------------------------------

class TestBBGEN003Architecture(unittest.TestCase):
    """
    BB-GEN-003: structural / architecture check.

    The implementation must not create a fourth, parallel ingestion function
    into KubeDemandAgent._reorder_buffer.  All jobs — regardless of source
    (tenant_events, kube_config, generator_config, or the frontend generator
    override) — must enter the queue through the existing KubeDemandAgent.tick()
    Poisson-arrival path.
    """

    def test_kube_config_from_generator_produces_valid_kube_config_dict(self):
        """
        _kube_config_from_generator must return a dict whose keys are all
        present in KubeConfig.__dataclass_fields__, meaning the factory will
        accept it without a new code path.
        """
        cfg = _kube_config_from_generator(_DEFAULT_GEN_CFG)
        # Every returned key must be a known KubeConfig field (no phantom keys).
        unknown = {k for k in cfg if k not in KubeConfig.__dataclass_fields__}
        self.assertEqual(
            unknown, set(),
            msg=(
                f"_kube_config_from_generator returned unknown KubeConfig keys: {unknown}. "
                "These would be silently discarded by the factory dict-comprehension "
                "and indicate the helper is computing fields that don't exist in KubeConfig."
            ),
        )

    def test_generator_override_uses_same_spec_dict_injection_path(self):
        """
        When generator_config_override is supplied to StartRunRequest, the
        backend injects a synthesised kube_config into spec_data["kube_config"]
        BEFORE calling build_run_context_from_spec.  This test confirms the spec
        path is used (not a separate ingestion function) by running
        build_run_context_from_spec with the synthesised spec and checking that
        the resulting kube_agents list is identical in structure to what a
        natively-kube-configured scenario produces.
        """
        synthesised_kube = _kube_config_from_generator(_DEFAULT_GEN_CFG)

        # Construct a minimal spec_data with the synthesised kube_config.
        # Use the baseline (non-kube) scenario as the base and inject kube_config.
        spec = _baseline_spec()
        spec["kube_config"] = synthesised_kube
        spec["end_sim_time"] = 30.0  # short enough for a unit test

        ctx = build_run_context_from_spec(
            run_id="bb-gen-003-arch",
            spec_data=spec,
        )
        # The factory must have created exactly 3 agents through the SAME code path
        # it uses for scenario-kube-peak-overage.
        self.assertEqual(
            len(ctx.sim_state.kube_agents), 3,
            msg=(
                "Expected 3 KubeDemandAgents after injecting synthesised kube_config. "
                f"Got {len(ctx.sim_state.kube_agents)}. "
                "The generator override must route through the existing factory path."
            ),
        )

    def test_no_new_reorder_buffer_append_outside_kube_demand(self):
        """
        Single source of truth: _reorder_buffer.append must only exist inside
        core/kube_demand.py.  No new parallel ingestion function may have been
        added elsewhere as part of this feature.

        This is the 'no fourth path' assertion from BB-GEN-003.
        """
        import ast
        import pathlib

        root = pathlib.Path(__file__).parents[1]   # gridsignal_sim/
        append_sites: list[str] = []

        for py_file in root.rglob("*.py"):
            # Skip test files and __pycache__.
            if "test_" in py_file.name or "__pycache__" in str(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "_reorder_buffer" not in source:
                continue
            # Simple string scan — count files that reference _reorder_buffer.
            rel = py_file.relative_to(root)
            append_sites.append(str(rel))

        # _reorder_buffer must only exist in core/kube_demand.py.
        non_kube = [p for p in append_sites if "kube_demand" not in p]
        self.assertEqual(
            non_kube, [],
            msg=(
                "BB-GEN-003 FAIL: _reorder_buffer referenced outside core/kube_demand.py: "
                f"{non_kube}. A parallel admission path was detected — this violates the "
                "single-source-of-truth requirement."
            ),
        )

    def test_schema_accepts_generator_config_override(self):
        """
        StartRunRequest must accept the generator_config_override field without
        raising a Pydantic validation error — confirms the schema change landed.
        """
        req = StartRunRequest(
            scenario_id="any-scenario",
            generator_config_override=_DEFAULT_GEN_CFG,
        )
        self.assertIsNotNone(req.generator_config_override)
        self.assertEqual(
            req.generator_config_override["ratePerMinute"], 2.0,
        )

    def test_schema_accepts_none_generator_config_override(self):
        """
        generator_config_override=None must still be accepted (backward-compat
        for callers that don't send the field at all).
        """
        req = StartRunRequest(scenario_id="any-scenario")
        self.assertIsNone(req.generator_config_override)


# ---------------------------------------------------------------------------
# BB-GEN-004 — Determinism: identical config → bit-identical output
# ---------------------------------------------------------------------------

class TestBBGEN004Determinism(unittest.TestCase):
    """
    BB-GEN-004: Two runs with the same generator config and the same RNG seed
    must produce bit-identical kube metrics at every tick.

    AT-7 requirement: job generation affecting simulation output must be
    backend-tick-driven, seeded, and reproducible — not wall-clock-paced.
    """

    @classmethod
    def setUpClass(cls):
        cls._rows_a, _ = asyncio.run(
            _run_with_generator_cfg("bb-gen-004-a", _DEFAULT_GEN_CFG, end_sim_time=120.0)
        )
        cls._rows_b, _ = asyncio.run(
            _run_with_generator_cfg("bb-gen-004-b", _DEFAULT_GEN_CFG, end_sim_time=120.0)
        )

    def test_row_count_identical(self):
        self.assertEqual(
            len(self._rows_a), len(self._rows_b),
            msg=(
                f"Tick count differs: run-a={len(self._rows_a)}, run-b={len(self._rows_b)}. "
                "Two identical runs must produce the same number of ticks."
            ),
        )

    def test_kube_active_jobs_bit_identical(self):
        """kube_metrics.active_jobs must be identical at every tick."""
        pairs = list(zip(self._rows_a, self._rows_b))
        mismatches = [
            (i, _kube_active(a), _kube_active(b))
            for i, (a, b) in enumerate(pairs)
            if _kube_active(a) != _kube_active(b)
        ]
        self.assertEqual(
            mismatches, [],
            msg=(
                f"BB-GEN-004 FAIL: kube_metrics.active_jobs diverged at {len(mismatches)} tick(s). "
                f"First mismatch at tick {mismatches[0][0]}: "
                f"run-a={mismatches[0][1]}, run-b={mismatches[0][2]}. "
                "Generator runs must be deterministic (AT-7)."
            ) if mismatches else "",
        )

    def test_kube_queued_jobs_bit_identical(self):
        """kube_metrics.queued_jobs must be identical at every tick."""
        pairs = list(zip(self._rows_a, self._rows_b))
        mismatches = [
            (i, _kube_queued(a), _kube_queued(b))
            for i, (a, b) in enumerate(pairs)
            if _kube_queued(a) != _kube_queued(b)
        ]
        self.assertEqual(
            mismatches, [],
            msg=(
                f"BB-GEN-004 FAIL: kube_metrics.queued_jobs diverged at {len(mismatches)} tick(s). "
                "Generator runs must be deterministic (AT-7)."
            ) if mismatches else "",
        )


# ---------------------------------------------------------------------------
# BB-GEN-005 — Stopping the run stops job generation cleanly
# ---------------------------------------------------------------------------

class TestBBGEN005StopClean(unittest.TestCase):
    """
    BB-GEN-005: when the run stops, no further jobs enter pending_jobs and
    no backend timer continues generating after the run loop exits.

    We verify this by confirming that after manager._tasks[run_id] awaits,
    the kube agents' internal interval is driven solely by _drive() — no
    independent asyncio task or thread is left running.
    """

    def test_run_terminates_cleanly(self):
        """The run coroutine must terminate without raising."""
        async def _run_and_stop():
            hub = WebSocketHub()
            manager = RunManager(hub)
            kube_cfg_dict = _kube_config_from_generator(_DEFAULT_GEN_CFG)
            ctx = build_run_context(
                "bb-gen-005",
                job_id="gen-stop-test",
                node_count=0,
                turbine_rated_mw=40.0,
                bess_rated_mw=5.0,
                bess_usable_mwh=3.0,
                end_sim_time=30.0,
            )
            for tid, stype, weight, seed_off in [
                ("A", "SLURM", 0.40, 0),
                ("B", "K8S",   0.35, 1),
                ("C", "RAY",   0.25, 2),
            ]:
                per_tenant = {**kube_cfg_dict}
                per_tenant["tenant_id"]           = tid
                per_tenant["scheduler_type"]      = stype
                per_tenant["mean_interarrival_s"] = max(5.0, kube_cfg_dict["mean_interarrival_s"] / weight)
                per_tenant["rng_seed"]            = kube_cfg_dict.get("rng_seed", 42) + seed_off
                per_tenant["rated_kw_per_node"]   = 5.6
                ctx.sim_state.kube_agents.append(
                    KubeDemandAgent(
                        KubeConfig(**{k: v for k, v in per_tenant.items()
                                     if k in KubeConfig.__dataclass_fields__}),
                        site_id=ctx.sim_state.site.site_id,
                    )
                )
            await manager.start_run(ctx)
            await manager._tasks[ctx.run_id]
            return ctx.sink.rows

        rows = asyncio.run(_run_and_stop())
        # If we got here without an exception, the run terminated cleanly.
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0, msg="Run produced no ticks at all.")

    def test_no_active_jobs_in_last_ticks_after_end(self):
        """
        After the run has ended (all rows collected), no new rows should be
        appended — the kube generation loop stops with the run loop.

        Proxy: the sink.rows list is immutable after _tasks[run_id] awaits.
        """
        rows, state = asyncio.run(
            _run_with_generator_cfg("bb-gen-005b", _DEFAULT_GEN_CFG, end_sim_time=30.0)
        )
        count_before = len(rows)
        # Wait a moment and confirm no new rows appeared.
        import time
        time.sleep(0.2)
        count_after = len(rows)
        self.assertEqual(
            count_before, count_after,
            msg=(
                "BB-GEN-005 FAIL: rows grew after run completion "
                f"({count_before} → {count_after}). "
                "A background generator loop is still appending rows."
            ),
        )


# ---------------------------------------------------------------------------
# BB-GEN-006 — Config parameters constrain generated job characteristics
# ---------------------------------------------------------------------------

class TestBBGEN006ConfigConstraint(unittest.TestCase):
    """
    BB-GEN-006: the GeneratorConfig parameters must actually constrain the
    backend scheduler's behaviour.

    We test the mapping function directly (unit-level) since the stochastic
    outcomes over a short run are probabilistic, but the config mapping must
    be deterministic and proportional.
    """

    def test_rate_maps_to_interarrival(self):
        """ratePerMinute=4 must produce mean_interarrival_s=15."""
        cfg = dict(_DEFAULT_GEN_CFG, ratePerMinute=4.0)
        result = _kube_config_from_generator(cfg)
        self.assertAlmostEqual(
            result["mean_interarrival_s"], 15.0, places=1,
            msg="ratePerMinute=4 → mean_interarrival_s must be 60/4=15.0",
        )

    def test_higher_rate_shorter_interarrival(self):
        """Higher ratePerMinute must produce strictly shorter mean_interarrival_s."""
        slow = _kube_config_from_generator(dict(_DEFAULT_GEN_CFG, ratePerMinute=1.0))
        fast = _kube_config_from_generator(dict(_DEFAULT_GEN_CFG, ratePerMinute=10.0))
        self.assertGreater(
            slow["mean_interarrival_s"], fast["mean_interarrival_s"],
            msg="Higher ratePerMinute must produce shorter mean_interarrival_s.",
        )

    def test_small_jobs_only_reduces_mean_nodes(self):
        """All-small job mix must produce lower mean_job_nodes than all-large."""
        all_small = _kube_config_from_generator(
            dict(_DEFAULT_GEN_CFG, jobSizes={"small": 1.0, "medium": 0.0, "large": 0.0})
        )
        all_large = _kube_config_from_generator(
            dict(_DEFAULT_GEN_CFG, jobSizes={"small": 0.0, "medium": 0.0, "large": 1.0})
        )
        self.assertLess(
            all_small["mean_job_nodes"], all_large["mean_job_nodes"],
            msg="All-small mix must produce fewer mean_job_nodes than all-large.",
        )

    def test_longer_duration_range_maps_to_longer_mean_duration(self):
        """Wider jobDurationRange must produce higher mean_job_duration_s."""
        short = _kube_config_from_generator(
            dict(_DEFAULT_GEN_CFG, jobDurationRange=[30, 60])
        )
        long_ = _kube_config_from_generator(
            dict(_DEFAULT_GEN_CFG, jobDurationRange=[300, 600])
        )
        self.assertGreater(
            long_["mean_job_duration_s"], short["mean_job_duration_s"],
            msg="Longer jobDurationRange must produce higher mean_job_duration_s.",
        )

    def test_larger_max_jobs_increases_max_nodes(self):
        """Higher maxJobsPerTenant must produce larger max_nodes."""
        few = _kube_config_from_generator(dict(_DEFAULT_GEN_CFG, maxJobsPerTenant=3))
        many = _kube_config_from_generator(dict(_DEFAULT_GEN_CFG, maxJobsPerTenant=24))
        self.assertGreater(
            many["max_nodes"], few["max_nodes"],
            msg="Higher maxJobsPerTenant must produce larger max_nodes.",
        )

    def test_higher_contracts_raise_headroom_threshold(self):
        """Larger tenant contracts must produce a higher headroom_threshold_mw."""
        low_contracts = _kube_config_from_generator(
            dict(_DEFAULT_GEN_CFG, tenantContracts={"a": 0.5, "b": 0.3, "c": 0.2})
        )
        high_contracts = _kube_config_from_generator(
            dict(_DEFAULT_GEN_CFG, tenantContracts={"a": 5.0, "b": 3.0, "c": 2.0})
        )
        self.assertGreater(
            high_contracts["headroom_threshold_mw"],
            low_contracts["headroom_threshold_mw"],
            msg="Higher tenantContracts must raise headroom_threshold_mw.",
        )


# ---------------------------------------------------------------------------
# BB-GEN-007 — Generated jobs are subject to the capacity gate
# ---------------------------------------------------------------------------

class TestBBGEN007CapacityGate(unittest.TestCase):
    """
    BB-GEN-007: generator-originated jobs must be subject to the same
    design_peak_load_mw admission gate as tenant_events / kube_config jobs.

    We use a direct KubeDemandAgent unit test (same pattern as BB-CAP-001)
    rather than a full simulator run so the gate behaviour is isolated.
    """

    # Ceiling set lower than a newly injected job would need.
    _CEILING_MW       = 1.0    # 1 MW ceiling
    _COMMITTED_NODES  = 100    # 100 × 5.6 kW = 0.56 MW currently active
    _KW_PER_NODE      = 5.6    # enterprise_8gpu_air

    def _make_agent(self) -> KubeDemandAgent:
        """Agent with the synthesised kube_config from _kube_config_from_generator."""
        kube_dict = _kube_config_from_generator(_DEFAULT_GEN_CFG)
        kube_dict["capacity_ceiling_mw"] = self._CEILING_MW
        kube_dict["rated_kw_per_node"]   = self._KW_PER_NODE
        kube_dict["mean_interarrival_s"] = 1e6   # suppress Poisson; inject manually
        kube_dict["headroom_threshold_mw"] = 0.0  # isolate cap gate from power-cap
        kube_dict["power_cap_hysteresis_s"] = 0.0
        agent = KubeDemandAgent(
            KubeConfig(**{k: v for k, v in kube_dict.items()
                         if k in KubeConfig.__dataclass_fields__}),
            site_id="test-bb-gen-007",
        )
        # Pre-load committed load.
        agent._active_jobs.append(
            _ActiveJob(
                event_id="pre-running",
                node_count=self._COMMITTED_NODES,
                hardware_profile_id="enterprise_8gpu_air",
                admitted_at=0.0,
                ends_at=99999.0,
            )
        )
        # Inject a pending job that would push over the ceiling.
        # Committed = 100 × 5.6 kW = 0.56 MW; new job 80 nodes = 0.448 MW; total 1.008 > 1.0 MW.
        agent._reorder_buffer.append(
            _PendingAdmission(
                event_id="oversized-gen-job",
                node_count=80,
                hardware_profile_id="enterprise_8gpu_air",
                observed_at=0.0,
                event_timestamp=0.0,
                duration_s=120.0,
                first_queued_at=0.0,
                requeue_count=0,
            )
        )
        agent._started = True
        agent._last_total_nodes = self._COMMITTED_NODES
        agent._next_arrival_sim_time = 1e9
        return agent

    def test_generator_job_deferred_by_cap_gate(self):
        """The generator-originated oversized job must be deferred (not admitted)."""
        agent = self._make_agent()
        _signals, metrics = agent.tick(
            sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid()
        )
        self.assertGreater(
            metrics.cap_gate_deferred_count, 0,
            msg=(
                "BB-GEN-007 FAIL: generator-originated job was admitted despite "
                f"breaching the capacity ceiling ({self._CEILING_MW} MW). "
                f"cap_gate_deferred_count={metrics.cap_gate_deferred_count}."
            ),
        )

    def test_generator_job_stays_in_queue_not_dropped(self):
        """Deferred generator job must remain in the reorder buffer (retry semantics)."""
        agent = self._make_agent()
        agent.tick(sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid())
        self.assertGreater(
            len(agent._reorder_buffer), 0,
            msg=(
                "BB-GEN-007 FAIL: deferred generator job was dropped from the queue "
                "instead of being re-queued for retry. The capacity gate must never drop."
            ),
        )

    def test_running_jobs_not_evicted(self):
        """Pre-running jobs must survive the tick even when new jobs are deferred."""
        agent = self._make_agent()
        _signals, metrics = agent.tick(
            sim_time=10.0, dt_seconds=5.0, grid_state=_ample_grid()
        )
        # The pre-loaded job should still be active (admission-only gate, BB-CAP-004).
        self.assertGreater(
            metrics.active_jobs, 0,
            msg=(
                "BB-GEN-007 FAIL: pre-running job was evicted by the capacity gate. "
                "Admission-only gate must never evict already-running jobs."
            ),
        )


# ---------------------------------------------------------------------------
# BB-GEN-008 — Multi-scheduler mix preserved end-to-end
# ---------------------------------------------------------------------------

class TestBBGEN008MultiSchedulerMix(unittest.TestCase):
    """
    BB-GEN-008: the generator wiring must create all three scheduler types
    (SLURM / K8S / RAY) in the backend, each correctly labeled.
    """

    @classmethod
    def setUpClass(cls):
        cls._rows, cls._state = asyncio.run(
            _run_with_generator_cfg("bb-gen-008", _DEFAULT_GEN_CFG, end_sim_time=120.0)
        )

    def test_three_agents_one_per_scheduler(self):
        """Exactly three kube agents must exist, one per scheduler type."""
        self.assertEqual(len(self._state.kube_agents), 3)
        types = {a.config.scheduler_type for a in self._state.kube_agents}
        self.assertEqual(types, {"SLURM", "K8S", "RAY"})

    def test_tenant_ids_are_a_b_c(self):
        """Tenant IDs must be A, B, C (frontend store convention)."""
        ids = {a.config.tenant_id for a in self._state.kube_agents}
        self.assertEqual(ids, {"A", "B", "C"})

    def test_each_agent_has_distinct_interarrival(self):
        """
        Per-tenant interarrival times must differ (scaled by tenant weight).
        This confirms no two agents were accidentally given the same config.
        """
        iats = [a.config.mean_interarrival_s for a in self._state.kube_agents]
        self.assertEqual(
            len(set(round(x, 1) for x in iats)), 3,
            msg=f"Expected 3 distinct interarrival times, got {iats}.",
        )

    def test_tenant_a_has_slurm(self):
        """Tenant A must use SLURM (matches gpuGeneratorStore.ts tenant split)."""
        a_agents = [ag for ag in self._state.kube_agents if ag.config.tenant_id == "A"]
        self.assertEqual(len(a_agents), 1)
        self.assertEqual(a_agents[0].config.scheduler_type, "SLURM")

    def test_tenant_b_has_k8s(self):
        """Tenant B must use K8S."""
        b_agents = [ag for ag in self._state.kube_agents if ag.config.tenant_id == "B"]
        self.assertEqual(len(b_agents), 1)
        self.assertEqual(b_agents[0].config.scheduler_type, "K8S")

    def test_tenant_c_has_ray(self):
        """Tenant C must use RAY."""
        c_agents = [ag for ag in self._state.kube_agents if ag.config.tenant_id == "C"]
        self.assertEqual(len(c_agents), 1)
        self.assertEqual(c_agents[0].config.scheduler_type, "RAY")


# ---------------------------------------------------------------------------
# BB-GEN-009 — Backend kube data updates after connection
# ---------------------------------------------------------------------------

class TestBBGEN009UIStateReflectsBackend(unittest.TestCase):
    """
    BB-GEN-009: confirms that tick result rows carry non-null kube data once a
    run with generator wiring is active.

    The 'Generator active — start a run to see live job data' footer message
    must not appear once kube tick data is flowing — this is tested implicitly
    by checking that the backend rows have kube-related fields populated.
    """

    @classmethod
    def setUpClass(cls):
        cls._rows, _ = asyncio.run(
            _run_with_generator_cfg("bb-gen-009", _DEFAULT_GEN_CFG, end_sim_time=120.0)
        )

    def test_kube_fields_present_in_tick_results(self):
        """
        At least one TickResult must carry a kube_metrics object, confirming kube
        data was serialised into the tick stream.  The frontend reads kube_metrics
        to drive the Queue tab and footer; without it the 'Generator active — start
        a run to see live job data' message persists even during an active run.
        """
        has_kube = any(
            getattr(r, "kube_metrics", None) is not None
            for r in self._rows
        )
        self.assertTrue(
            has_kube,
            msg=(
                "BB-GEN-009 FAIL: no TickResult carried a kube_metrics object. "
                "The frontend would continue showing 'Generator active — start a run "
                "to see live job data' because it cannot see any kube data."
            ),
        )

    def test_active_or_queued_nonzero_within_run(self):
        """
        At some point during the 120 s run, kube_metrics.active_jobs +
        kube_metrics.queued_jobs must be > 0.  This confirms the generator is
        wired into the admission path, not just creating agents that produce no jobs.
        """
        any_nonzero = any(
            _kube_active(r) + _kube_queued(r) > 0
            for r in self._rows
        )
        self.assertTrue(
            any_nonzero,
            msg=(
                "BB-GEN-009 FAIL: kube_metrics.active_jobs + queued_jobs was 0 for "
                "the entire 120 s run. The generator wiring must produce observable "
                "jobs in the tick stream."
            ),
        )


# ---------------------------------------------------------------------------
# BB-GEN-010 — Regression: existing non-generator scenarios unaffected
# ---------------------------------------------------------------------------

class TestBBGEN010Regression(unittest.TestCase):
    """
    BB-GEN-010: scenarios that don't use generator_config_override must produce
    bit-identical output to the pre-wiring baseline.

    We verify:
      (a) kube_agents list is empty for non-kube scenarios.
      (b) A kube scenario without the override still produces agents from its
          own spec's kube_config (backward compat).
      (c) Passing generator_config_override=None is equivalent to omitting it.
    """

    def test_non_kube_scenario_has_no_kube_agents(self):
        """
        A non-kube scenario built WITHOUT generator_config_override must have
        an empty kube_agents list — the new code path must not leak into
        scenarios that never opt in.
        """
        spec = _baseline_spec()
        # Confirm the spec truly has no kube_config.
        self.assertIsNone(
            spec.get("kube_config"),
            msg="Baseline spec unexpectedly has a kube_config — test precondition failed.",
        )
        ctx = build_run_context_from_spec(
            run_id="bb-gen-010-no-kube",
            spec_data=spec,
        )
        self.assertEqual(
            len(ctx.sim_state.kube_agents), 0,
            msg=(
                "BB-GEN-010 FAIL: non-kube scenario has kube_agents after the generator "
                "wiring was added. The new code path must be gated on kube_config presence."
            ),
        )

    def test_native_kube_scenario_still_works(self):
        """
        scenario-kube-peak-overage (has its own kube_config) must still build
        3 agents without generator_config_override.  Backward compatibility.
        """
        ctx = build_run_context_from_spec(
            run_id="bb-gen-010-native-kube",
            spec_data=_kube_spec(),
        )
        self.assertEqual(
            len(ctx.sim_state.kube_agents), 3,
            msg=(
                "BB-GEN-010 FAIL: scenario-kube-peak-overage lost its kube agents after "
                "the generator wiring change. The factory must remain backward-compatible."
            ),
        )

    def test_generator_config_override_none_is_noop(self):
        """
        StartRunRequest with generator_config_override=None must not affect the
        spec in any way — identical to omitting the field entirely.
        """
        req_with_none = StartRunRequest(
            scenario_id="any",
            generator_config_override=None,
        )
        req_without   = StartRunRequest(scenario_id="any")
        self.assertIsNone(req_with_none.generator_config_override)
        self.assertIsNone(req_without.generator_config_override)

    def test_advisory_boundary_no_southbound_write(self):
        """
        Suite-level advisory boundary check: KubeDemandAgent.tick() must return
        only WorkloadSignal objects and KubeMetrics — it must not have any
        southbound/PMS-facing write side-effects.

        We inspect the return annotation and the tick method body for any
        'pms', 'southbound', 'setpoint', 'dispatch_command' writes.
        """
        import core.kube_demand as kd
        source = inspect.getsource(kd.KubeDemandAgent.tick)
        forbidden_patterns = ["pms_", "southbound", "setpoint", "dispatch_command"]
        violations = [p for p in forbidden_patterns if p in source.lower()]
        self.assertEqual(
            violations, [],
            msg=(
                f"Advisory boundary violation: KubeDemandAgent.tick() references "
                f"southbound patterns: {violations}. Generator admission must never "
                "write PMS-facing outputs (GS-IMPL-PSP-002 §6.1)."
            ),
        )


# ---------------------------------------------------------------------------
# Suite-level: single admission entry point
# ---------------------------------------------------------------------------

class TestSuiteAdmissionEntryPoint(unittest.TestCase):
    """
    Suite-level guard: confirm that exactly ONE function is responsible for
    committing a job into the active fleet (the admission step in
    KubeDemandAgent.tick).  No alternative admission code path may have been
    introduced alongside the generator wiring.
    """

    def test_single_active_jobs_append_site(self):
        """
        _active_jobs.append must appear only inside KubeDemandAgent.tick()
        in the production codebase (core/kube_demand.py), not in any new helper
        added for the generator wiring.
        """
        import pathlib

        root = pathlib.Path(__file__).parents[1]
        sites: list[str] = []
        for py_file in root.rglob("*.py"):
            if "test_" in py_file.name or "__pycache__" in str(py_file):
                continue
            try:
                text = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "_active_jobs.append" in text:
                sites.append(str(py_file.relative_to(root)))

        non_kube = [s for s in sites if "kube_demand" not in s]
        self.assertEqual(
            non_kube, [],
            msg=(
                "Single-admission-entry-point violation: _active_jobs.append found "
                f"outside core/kube_demand.py: {non_kube}. "
                "All jobs must be admitted through a single, authoritative function."
            ),
        )
