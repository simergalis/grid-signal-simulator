"""test_task_61.py — Task #61: operator dashboard reflects corrupted SoC.

"Confirm the operator dashboard reflects corrupted SoC readings the same way
the physics engine does."

Root cause
----------
_apply_soc_corruption() used corrupted_soc_mwh internally to recompute
contingency_coverage, but only emitted bess_soc_fraction (clean physics value)
in the tick payload.  The dashboard received the ground-truth physics SoC —
not the corrupted sensor reading the physics engine actually used — so there
was no way for operators to see what value drove the contingency calculation.

Fix
---
Added bess_soc_corrupted_fraction: Optional[float] to TickResult (models.py).
_apply_soc_corruption() now stamps it (alongside contingency_coverage) whenever
a non-dropout corruption entry produces an effective change:

    bess_soc_corrupted_fraction = corrupted_soc_mwh / total_usable_mwh

This is the same normalised value used to build the corrupted BESS snapshots,
so contingency_coverage.bess_usable_energy_mwh == bess_soc_corrupted_fraction
× total_usable_mwh (within floating-point precision).

None on clean ticks, dropout ticks, and when corruption produces no effective
change (|corrupted − clean| < 1e-9 after clamping).

_tick_result_to_dict() serialises the field.  TickPayload in types.ts declares
the matching number | null field (payload guard enforced).

Test strategy (TC-61)
---------------------
  61-1  TickResult.bess_soc_corrupted_fraction field exists; default is None.
  61-2  Staleness corruption: bess_soc_corrupted_fraction equals the stale
        SoC / total_usable_mwh and equals contingency bess_usable_energy_mwh
        / total_usable_mwh — physics and dashboard agree on the same value.
  61-3  Dropout: bess_soc_corrupted_fraction stays None.
  61-4  Clean entry (fast path): bess_soc_corrupted_fraction stays None.
  61-5  Gaussian noise: bess_soc_corrupted_fraction is non-None and differs
        from bess_soc_fraction (clean physics value).
  61-6  _tick_result_to_dict() includes bess_soc_corrupted_fraction key.
  61-7  Serialised value is None for clean ticks and a float for corrupted ticks.
  61-8  Corrupted fraction and contingency bess_usable_energy_mwh are
        consistent: fraction × total_usable_mwh ≈ contingency energy (MWh).
"""
from __future__ import annotations

import dataclasses
import math
from typing import Optional

import pytest

from core.models import TickResult
from runtime.run_manager import _apply_soc_corruption, _tick_result_to_dict
from runtime.telemetry_corruption import (
    CorruptionEntry,
    TelemetryCorruptionSchedule,
)


# ---------------------------------------------------------------------------
# Constants matching test_telemetry_corruption_wiring.py geometry
# ---------------------------------------------------------------------------

_N_WARMUP_TICKS = 5
_STALE_SOC_LOW  = 0.001   # MWh — triggers energy-test failure after warmup
_STALE_SOC_HIGH = 1.5     # MWh — passes energy test
BESS_USABLE_MWH = 2.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_schedule_uniform(
    entry: CorruptionEntry,
    n_ticks: int = 20,
) -> TelemetryCorruptionSchedule:
    return TelemetryCorruptionSchedule(
        schedule=[entry] * n_ticks,
        seed=42,
        noise_sigma=entry.noise_sigma,
        dropout_prob=1.0 if entry.dropout else 0.0,
        max_stale=entry.staleness,
    )


def _make_ctx_and_warmed_tick(bess_soc_mwh: float = BESS_USABLE_MWH):
    """Return (ctx, tick) after N_WARMUP_TICKS with BESS SoC overridden."""
    from runtime.scenario_factory import build_run_context

    ctx = build_run_context(
        run_id="test-61-run",
        job_id="job-61",
        node_count=500,
        turbine_count=2,
        turbine_rated_mw=15.0,
        r_asset_mw_per_s=0.2,
        bess_rated_mw=5.0,
        bess_usable_mwh=BESS_USABLE_MWH,
        end_sim_time=300.0,
    )
    tick = None
    for _ in range(_N_WARMUP_TICKS):
        tick = ctx.step()
    for b in ctx.sim_state.bess_units:
        b.soc_mwh = bess_soc_mwh
    assert tick is not None
    return ctx, tick


# ---------------------------------------------------------------------------
# TC-61: corrupted SoC fraction propagates to operator dashboard
# ---------------------------------------------------------------------------

class TestTC_61_CorruptedSoCReflectedOnDashboard:
    """TC-61: dashboard receives the same corrupted SoC the physics engine used."""

    # ── 61-1: field presence ──────────────────────────────────────────────

    def test_tick_result_has_bess_soc_corrupted_fraction_field(self) -> None:
        """TickResult.bess_soc_corrupted_fraction exists and defaults to None."""
        fields = {f.name: f for f in dataclasses.fields(TickResult)}
        assert "bess_soc_corrupted_fraction" in fields, (
            "TickResult must have bess_soc_corrupted_fraction field (Task #61)"
        )

    def test_tick_result_corrupted_fraction_default_is_none(self) -> None:
        """bess_soc_corrupted_fraction default must be None (clean-path safe)."""
        fields = {f.name: f for f in dataclasses.fields(TickResult)}
        default = fields["bess_soc_corrupted_fraction"].default
        assert default is None, (
            f"bess_soc_corrupted_fraction default must be None, got {default!r}"
        )

    # ── 61-2: staleness stamps the correct corrupted fraction ─────────────

    def test_staleness_corruption_stamps_corrupted_fraction(self) -> None:
        """Staleness=1 → bess_soc_corrupted_fraction = stale_soc / total_usable."""
        ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=BESS_USABLE_MWH)
        ctx.telemetry_corruption = _make_schedule_uniform(
            CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
        )
        ctx._bess_soc_history = [_STALE_SOC_LOW]

        result = _apply_soc_corruption(ctx, tick)

        assert result.bess_soc_corrupted_fraction is not None, (
            "bess_soc_corrupted_fraction must be non-None after staleness corruption"
        )
        expected_fraction = _STALE_SOC_LOW / BESS_USABLE_MWH
        assert result.bess_soc_corrupted_fraction == pytest.approx(
            expected_fraction, abs=1e-6
        ), (
            f"bess_soc_corrupted_fraction must equal stale_soc / total_usable "
            f"({_STALE_SOC_LOW} / {BESS_USABLE_MWH} = {expected_fraction:.6f}); "
            f"got {result.bess_soc_corrupted_fraction}"
        )

    def test_corrupted_fraction_differs_from_clean_soc_fraction(self) -> None:
        """bess_soc_corrupted_fraction ≠ bess_soc_fraction — operator sees sensor value."""
        ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=BESS_USABLE_MWH)
        ctx.telemetry_corruption = _make_schedule_uniform(
            CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
        )
        ctx._bess_soc_history = [_STALE_SOC_LOW]

        result = _apply_soc_corruption(ctx, tick)

        assert result.bess_soc_corrupted_fraction is not None
        assert result.bess_soc_fraction != pytest.approx(
            result.bess_soc_corrupted_fraction, abs=1e-4
        ), (
            "Corrupted fraction must differ from clean physics fraction when "
            "stale SoC is significantly below the clean value. "
            f"clean={result.bess_soc_fraction:.4f}, "
            f"corrupted={result.bess_soc_corrupted_fraction:.4f}"
        )

    # ── 61-3: dropout keeps None ──────────────────────────────────────────

    def test_dropout_keeps_corrupted_fraction_none(self) -> None:
        """Dropout ticks must leave bess_soc_corrupted_fraction as None."""
        ctx, tick = _make_ctx_and_warmed_tick()
        ctx.telemetry_corruption = _make_schedule_uniform(
            CorruptionEntry(noise_sigma=0.0, dropout=True, staleness=0)
        )

        result = _apply_soc_corruption(ctx, tick)

        assert result.bess_soc_corrupted_fraction is None, (
            "Dropout must leave bess_soc_corrupted_fraction None — "
            "no corrupted reading was delivered to the physics engine"
        )

    # ── 61-4: clean entry fast path keeps None ────────────────────────────

    def test_clean_entry_keeps_corrupted_fraction_none(self) -> None:
        """Clean entry (no corruption) must leave bess_soc_corrupted_fraction as None."""
        ctx, tick = _make_ctx_and_warmed_tick()
        ctx.telemetry_corruption = _make_schedule_uniform(
            CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=0)
        )

        result = _apply_soc_corruption(ctx, tick)

        assert result.bess_soc_corrupted_fraction is None, (
            "Clean entry (fast path) must leave bess_soc_corrupted_fraction None"
        )

    # ── 61-5: Gaussian noise stamps non-None fraction ─────────────────────

    def test_gaussian_noise_stamps_non_none_corrupted_fraction(self) -> None:
        """Gaussian noise corruption (sigma > 0) → bess_soc_corrupted_fraction non-None."""
        ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=1.0)
        ctx.telemetry_corruption = _make_schedule_uniform(
            CorruptionEntry(noise_sigma=0.5, dropout=False, staleness=0),
            n_ticks=20,
        )

        # Run multiple ticks to overcome the < 1e-9 no-effective-change guard.
        # With sigma=0.5 on a 1.0 MWh SoC the expected absolute noise >> 1e-9.
        results = []
        for _ in range(10):
            result = _apply_soc_corruption(ctx, tick)
            results.append(result)

        non_none = [r for r in results if r.bess_soc_corrupted_fraction is not None]
        assert non_none, (
            "At least one tick with sigma=0.5 noise must produce a non-None "
            "bess_soc_corrupted_fraction; if all are None the noise amplitude "
            "is below 1e-9, which is a precision bug."
        )
        for r in non_none:
            assert 0.0 <= r.bess_soc_corrupted_fraction <= 1.0, (
                "bess_soc_corrupted_fraction must be in [0, 1] (clamped to "
                "[0, usable_mwh] then normalised by usable_mwh)"
            )

    # ── 61-6: serialisation — key present in tick dict ────────────────────

    def test_tick_dict_includes_bess_soc_corrupted_fraction_key(self) -> None:
        """_tick_result_to_dict() must include 'bess_soc_corrupted_fraction'."""
        from runtime.scenario_factory import build_run_context_from_spec
        import json, pathlib

        spec_path = (
            pathlib.Path(__file__).parent.parent
            / "config/scenarios/demo-turbine-fc-bess-20-tenants-overage.json"
        )
        spec = json.loads(spec_path.read_text())
        spec["end_sim_time"] = 10.0
        ctx = build_run_context_from_spec("test-61-6", spec)
        tick = ctx.step()

        d = _tick_result_to_dict(tick)
        assert "bess_soc_corrupted_fraction" in d, (
            "_tick_result_to_dict must serialise bess_soc_corrupted_fraction (Task #61)"
        )

    # ── 61-7: serialised value matches field semantics ────────────────────

    def test_tick_dict_corrupted_fraction_is_none_for_clean_ticks(self) -> None:
        """Clean ticks (no corruption schedule) serialise bess_soc_corrupted_fraction as None."""
        from runtime.scenario_factory import build_run_context_from_spec
        import json, pathlib

        spec_path = (
            pathlib.Path(__file__).parent.parent
            / "config/scenarios/demo-turbine-fc-bess-20-tenants-overage.json"
        )
        spec = json.loads(spec_path.read_text())
        spec["end_sim_time"] = 10.0
        ctx = build_run_context_from_spec("test-61-7", spec)
        tick = ctx.step()

        d = _tick_result_to_dict(tick)
        assert d["bess_soc_corrupted_fraction"] is None, (
            "bess_soc_corrupted_fraction must serialise as null on clean ticks"
        )

    def test_tick_dict_corrupted_fraction_is_float_when_stamped(self) -> None:
        """Stamped bess_soc_corrupted_fraction serialises as a rounded float."""
        from runtime.scenario_factory import build_run_context_from_spec
        import json, pathlib

        spec_path = (
            pathlib.Path(__file__).parent.parent
            / "config/scenarios/demo-turbine-fc-bess-20-tenants-overage.json"
        )
        spec = json.loads(spec_path.read_text())
        spec["end_sim_time"] = 10.0
        ctx = build_run_context_from_spec("test-61-7b", spec)
        tick = ctx.step()

        stamped = dataclasses.replace(tick, bess_soc_corrupted_fraction=0.123456789)
        d = _tick_result_to_dict(stamped)
        assert d["bess_soc_corrupted_fraction"] == round(0.123456789, 4), (
            "bess_soc_corrupted_fraction must be rounded to 4 decimal places "
            "in the tick dict (same precision as bess_soc_fraction)"
        )

    # ── 61-8: corrupted fraction consistent with contingency energy ────────

    def test_corrupted_fraction_consistent_with_contingency_energy(self) -> None:
        """Key assertion for Task #61: dashboard value and physics contingency agree.

        After staleness corruption the physics engine recomputes contingency_coverage
        using corrupted_soc_mwh.  The stamped bess_soc_corrupted_fraction is
        corrupted_soc_mwh / total_usable_mwh.  Therefore:

            bess_soc_corrupted_fraction × total_usable_mwh
            ≈ contingency_coverage.bess_usable_energy_mwh

        This is the invariant that guarantees the dashboard shows exactly the
        same SoC value the physics engine used for contingency decisions.
        """
        ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=BESS_USABLE_MWH)
        ctx.telemetry_corruption = _make_schedule_uniform(
            CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
        )
        ctx._bess_soc_history = [_STALE_SOC_HIGH]

        result = _apply_soc_corruption(ctx, tick)

        assert result.bess_soc_corrupted_fraction is not None, (
            "Staleness corruption must stamp bess_soc_corrupted_fraction"
        )

        total_usable = BESS_USABLE_MWH  # single BESS unit in the fixture
        dashboard_soc_mwh = result.bess_soc_corrupted_fraction * total_usable
        physics_soc_mwh   = result.contingency_coverage.bess_usable_energy_mwh

        assert dashboard_soc_mwh == pytest.approx(physics_soc_mwh, abs=1e-6), (
            f"Dashboard SoC (fraction × usable = {dashboard_soc_mwh:.6f} MWh) "
            f"must equal physics contingency energy ({physics_soc_mwh:.6f} MWh). "
            "Divergence here means operators see a different value than what "
            "drove the contingency calculation — the core bug of Task #61."
        )
