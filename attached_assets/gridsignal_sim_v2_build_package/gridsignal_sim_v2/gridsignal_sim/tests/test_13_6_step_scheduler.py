"""
tests/test_13_6_step_scheduler.py — Regression guard for the COMPUTE RACKS
tile fix that wires the 0.70 s step-phase cycle into GPUModule.advance() for
scripted-event scenarios (demo-20mw, demo-5mw, demo-alert).

Before the fix:
  - load_config was None on all GPUModules in the non-kube (scripted) path.
  - effective_mult = 1.0 every tick → p_compute_mw pinned at full TDP.
  - The COMPUTE RACKS tile showed a flat line at peak MW.

After the fix:
  - scenario_factory wires LoadProfileConfig and _auto_step_period_s = 0.70 s
    from the ScenarioSpec's load_config field.
  - With dt_seconds (5.0 s) >> step_period (0.70 s), advance() applies the
    duty-cycle average: effective_mult = 1 + phase_coherence*(avg − 1) < 1.
    Defaults: f_compute=0.72, p_comm_ratio=0.55, phase_coherence=0.85 →
      duty_avg      = 0.72 + 0.28 * 0.55 = 0.874
      effective_mult = 1 + 0.85 * (0.874 − 1) = 0.8929
  - Settled p_compute_mw ≈ 89 % of peak TDP → tile is no longer frozen at peak.

Regressions caught by this file:
  A) load_config = None   → effective_mult = 1.0 → frozen at 100 % peak.
  B) _auto_step_period_s = 0 with step_phase = 0.0 (default) →
       raw_profile = 1.0 (compute phase every tick) → frozen at 100 % peak.

TC-13-6-A (structural): after build_run_context_from_spec, each GPUModule
    attached to a demo-20mw context has load_config set (not None) and
    _auto_step_period_s > 0.

TC-13-6-B (behavioral): across ticks where sim_time > 35 s (ramp definitely
    complete — dt_lead_seconds = 30 s for demo-20mw), max(p_compute_demand_mw)
    is below 0.98 × theoretical peak TDP.  This rules out both regressions A
    and B, which would pin the value at 100 % peak.  The threshold is loose
    enough to be insensitive to noise (noise_sigma_fraction = 0.005 << 2 %).

TC-13-6-C (spread): across those same post-ramp ticks, the power must be
    positive and within the valid effective-mult band:
      0.5 × peak < settled_mw < 0.98 × peak
    This confirms the phase profile is applied (not zeroed out) and is the
    physically correct sub-peak value rather than a clamped-to-zero artifact.
"""
from __future__ import annotations

import asyncio
import json as _json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — identical to other test files in this directory
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.routes.scenarios import build_seeded_store          # noqa: E402
from runtime.scenario_factory import build_run_context_from_spec  # noqa: E402
from runtime.run_manager import RunManager, WebSocketHub      # noqa: E402


# ---------------------------------------------------------------------------
# Constants (must match scenario_factory._STEP_PERIOD_S and LoadProfileConfig
# defaults — any change there breaks TC-13-6-A/B; update both together)
# ---------------------------------------------------------------------------
_DEMO_NODES     = 600
_RATED_KW       = 10.2          # enterprise_8gpu_air rated kW per node
_PUE_BASE       = 1.03          # SiteConfig default for scripted scenarios
_PEAK_MW        = _DEMO_NODES * _RATED_KW * _PUE_BASE / 1000.0
# ≈ 6.3036 MW — theoretical TDP at ramp progress = 1.0, effective_mult = 1.0

_F_COMPUTE      = 0.72          # LoadProfileConfig default
_P_COMM_RATIO   = 0.55          # LoadProfileConfig default
_PHASE_COHERENCE = 0.85         # LoadProfileConfig default
_DUTY_AVG       = _F_COMPUTE + (1.0 - _F_COMPUTE) * _P_COMM_RATIO   # 0.874
_EXPECTED_MULT  = 1.0 + _PHASE_COHERENCE * (_DUTY_AVG - 1.0)         # 0.8929
_EXPECTED_MW    = _PEAK_MW * _EXPECTED_MULT   # ≈ 5.629 MW at steady state

# Regression bound: settled power must be below this fraction of peak.
# 0.98 leaves ample room for noise (noise_sigma_fraction=0.005 → ±0.5 %)
# while still catching regressions that produce effective_mult = 1.0.
_FROZEN_AT_PEAK_FRACTION = 0.98

# Ramp completes at dt_lead_seconds = 30 s for demo-20mw. Use 35 s guard.
_POST_RAMP_THRESHOLD_S = 35.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_spec(scenario_id: str) -> dict:
    """Return the plain-dict spec for a seeded scenario."""
    store = build_seeded_store()
    rec = store.get(scenario_id)
    assert rec is not None, f"Scenario '{scenario_id}' not in seeded store"
    return _json.loads(rec.spec_json)


def _run_demo_20mw_sync() -> list:
    """
    Build and fully run demo-20mw via the spec path.

    Returns ctx.sink.rows — a list of TickResult objects.
    Uses playback_speed=0.0 (instant) so the run completes without
    real-time sleep.
    """
    async def _go() -> list:
        spec_data = _get_spec("demo-20mw")
        ctx = build_run_context_from_spec(
            run_id="tc-13-6-demo-20mw",
            spec_data=spec_data,
            playback_speed=0.0,
        )
        hub = WebSocketHub()
        manager = RunManager(hub)
        await manager.start_run(ctx)
        await manager._tasks[ctx.run_id]
        return ctx.sink.rows

    return asyncio.run(_go())


# ---------------------------------------------------------------------------
# TC-13-6-A: structural — load_config and _auto_step_period_s wired
# ---------------------------------------------------------------------------

class TestTC136Structural:
    """GPUModules in a demo-20mw context must have load_config set."""

    @pytest.fixture(scope="class")
    def ctx(self):
        spec_data = _get_spec("demo-20mw")
        return build_run_context_from_spec(
            run_id="tc-13-6-struct",
            spec_data=spec_data,
        )

    def test_gpu_modules_have_load_config(self, ctx):
        """TC-13-6-A: every GPUModule must have load_config set (not None).

        Regression A: if scenario_factory stops wiring the top-level
        load_config dict, load_config stays None and effective_mult reverts
        to 1.0 (frozen at peak).
        """
        gpu_mods = ctx.sim_state.gpu_modules
        assert gpu_mods, "sim_state.gpu_modules must not be empty for demo-20mw"
        for gm in gpu_mods:
            assert gm.load_config is not None, (
                f"GPUModule {gm.asset_id!r} has load_config=None; "
                "scenario_factory must wire load_config from the spec's "
                "top-level 'load_config' dict for non-kube (scripted) scenarios."
            )

    def test_gpu_modules_have_auto_step_period(self, ctx):
        """TC-13-6-A: every GPUModule must have _auto_step_period_s > 0.

        Regression B: if _auto_step_period_s is 0, step_phase is never
        updated (stays at 0.0 = start of compute phase) and raw_profile is
        permanently 1.0 → effective_mult = 1.0 → frozen at peak.
        """
        for gm in ctx.sim_state.gpu_modules:
            assert gm._auto_step_period_s > 0.0, (
                f"GPUModule {gm.asset_id!r} has _auto_step_period_s="
                f"{gm._auto_step_period_s}; must be > 0 for non-kube "
                "scripted scenarios with load_config set."
            )


# ---------------------------------------------------------------------------
# TC-13-6-B / TC-13-6-C: behavioral — settled power below peak
# ---------------------------------------------------------------------------

class TestTC136Behavioral:
    """
    Post-ramp p_compute_demand_mw must be below the frozen-at-peak threshold.

    The class-scoped fixture runs the full 300-second demo-20mw once and
    caches the results so all assertions share a single run.
    """

    @pytest.fixture(scope="class")
    def post_ramp_rows(self):
        rows = _run_demo_20mw_sync()
        assert rows, "demo-20mw produced no ticks"
        post = [r for r in rows if r.sim_time_seconds > _POST_RAMP_THRESHOLD_S]
        assert len(post) >= 10, (
            f"Expected ≥ 10 post-ramp ticks (sim_time > {_POST_RAMP_THRESHOLD_S} s) "
            f"but got {len(post)}.  end_sim_time=300 s should yield ~53 such ticks."
        )
        return post

    def test_settled_power_below_peak_ceiling(self, post_ramp_rows):
        """TC-13-6-B: no post-ramp tick should be at frozen-at-peak level.

        Checks max(p_compute_demand_mw) < 0.98 × peak_TDP across all ticks
        after the ramp window closes.  Any regression that resets effective_mult
        to 1.0 (load_config=None or _auto_step_period_s=0) would produce
        p_compute_mw ≈ _PEAK_MW and fail this assertion.
        """
        ceiling = _FROZEN_AT_PEAK_FRACTION * _PEAK_MW
        max_mw  = max(r.p_compute_demand_mw for r in post_ramp_rows)
        assert max_mw < ceiling, (
            f"TC-13-6-B FAIL — post-ramp max p_compute_mw={max_mw:.4f} MW "
            f"≥ ceiling {ceiling:.4f} MW ({_FROZEN_AT_PEAK_FRACTION*100:.0f}% "
            f"of peak {_PEAK_MW:.4f} MW).  "
            "This indicates load_config is None or _auto_step_period_s=0, "
            "causing effective_mult=1.0 and the tile to freeze at peak MW."
        )

    def test_settled_power_above_floor(self, post_ramp_rows):
        """TC-13-6-C lower bound: settled power must be above 50 % of peak.

        Guards against a bug where effective_mult is accidentally set to 0
        (e.g. phase_coherence=0 with p_comm_ratio=0) that would silence the
        tile entirely.  The duty-cycle effective_mult ≈ 0.893 far exceeds 0.5.
        """
        floor = 0.50 * _PEAK_MW
        min_mw = min(r.p_compute_demand_mw for r in post_ramp_rows)
        assert min_mw > floor, (
            f"TC-13-6-C FAIL — post-ramp min p_compute_mw={min_mw:.4f} MW "
            f"≤ floor {floor:.4f} MW (50% of peak {_PEAK_MW:.4f} MW).  "
            "The phase profile appears to have over-suppressed compute power."
        )

    def test_settled_power_near_expected(self, post_ramp_rows):
        """TC-13-6-C band check: settled power must be close to the expected
        duty-cycle value (_EXPECTED_MW ≈ 89 % of peak, ± 5 %).

        This confirms the load_config defaults (f_compute=0.72, p_comm_ratio=0.55,
        phase_coherence=0.85) are applied correctly and not accidentally changed.
        """
        tol_mw  = 0.05 * _PEAK_MW   # ±5 % of peak ≈ ±0.315 MW
        avg_mw  = sum(r.p_compute_demand_mw for r in post_ramp_rows) / len(post_ramp_rows)
        assert abs(avg_mw - _EXPECTED_MW) < tol_mw, (
            f"TC-13-6-C FAIL — post-ramp mean p_compute_mw={avg_mw:.4f} MW "
            f"deviates from expected {_EXPECTED_MW:.4f} MW by "
            f"{abs(avg_mw - _EXPECTED_MW):.4f} MW (> tol {tol_mw:.4f} MW).  "
            "Check LoadProfileConfig defaults: f_compute, p_comm_ratio, phase_coherence."
        )
