"""
tests/test_telemetry_corruption_wiring.py — GT-2 acceptance tests.

Verify that the telemetry corruption schedule attached to RunContext is
consumed by _apply_soc_corruption and causes ContingencyCoverage to change
when the corrupted SoC crosses the energy-test threshold.

TC-GT2-A  Staleness substitutes the historical SoC value correctly
TC-GT2-B  Dropout leaves contingency_coverage unchanged
TC-GT2-C  Clean entry (all zeros) is the fast-path no-op
TC-GT2-D  Clamping: large upward stale SoC clamped to usable_mwh
TC-GT2-E  Clamping: negative stale SoC clamped to 0
TC-GT2-F  ContingencyState flips from COVERED → COVERED_WITH_SHED when
          corrupted SoC falls below the energy-test threshold
TC-GT2-G  _bess_soc_history tracks correctly for staleness=2 lookback
TC-GT2-H  ctx.telemetry_corruption defaults to None in a plain RunContext
TC-GT2-I  Gaussian noise corrupts bess_usable_energy_mwh deterministically
"""

from __future__ import annotations

import math
import random
from typing import Optional

import pytest

from core.contingency import ContingencyState
from runtime.run_manager import _apply_soc_corruption, _update_soc_history
from runtime.telemetry_corruption import (
    CorruptionEntry,
    TelemetryCorruptionSchedule,
    generate_corruption_schedule,
)


# ---------------------------------------------------------------------------
# Test geometry
# ---------------------------------------------------------------------------
#
# Two turbines, turbine_rated_mw=15.0, node_count=500, r=0.2 MW/s.
# After 5 ticks:
#   turbine output ≈ 2.6 MW each → tripped deficit ≈ 2.6 MW
#   surviving headroom = 15 - 2.6 = 12.4 MW > deficit → closable=True
#   time_to_close = 2.6 / 0.2 = 13.1 s
#   e_required = 0.5 × 2.6 × 13.1 / 3600 ≈ 0.0048 MWh
#   Clean BESS SoC = 2.0 MWh >> e_required → energy_test_passes=True
#
# To flip energy_test_passes: stale SoC = 0.001 MWh < e_required.

_N_WARMUP_TICKS  = 5      # ticks to reach meaningful turbine output
_STALE_SOC_LOW   = 0.001  # MWh — below e_required after warmup
_STALE_SOC_HIGH  = 1.5    # MWh — above e_required → still passes
BESS_USABLE_MWH  = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_schedule_uniform(entry: CorruptionEntry, n_ticks: int = 20) -> TelemetryCorruptionSchedule:
    """Schedule where every tick has the same CorruptionEntry."""
    return TelemetryCorruptionSchedule(
        schedule=[entry] * n_ticks,
        seed=None,
        noise_sigma=entry.noise_sigma,
        dropout_prob=1.0 if entry.dropout else 0.0,
        max_stale=entry.staleness,
    )


def _make_ctx_and_warmed_tick(bess_soc_mwh: float = BESS_USABLE_MWH):
    """Build a RunContext with 2 turbines, run _N_WARMUP_TICKS steps,
    override BESS SoC to bess_soc_mwh, then return (ctx, tick_result).

    After warmup the turbines are RAMPING/AT_TARGET with meaningful output,
    so e_required > 0 and the energy test is a real arithmetic check.
    """
    from runtime.scenario_factory import build_run_context

    ctx = build_run_context(
        run_id="test-corruption-run",
        job_id="job-t",
        node_count=500,
        turbine_count=2,
        turbine_rated_mw=15.0,
        r_asset_mw_per_s=0.2,
        bess_rated_mw=5.0,
        bess_usable_mwh=BESS_USABLE_MWH,
        end_sim_time=300.0,
    )

    # Run warmup ticks to reach non-trivial turbine output.
    tick = None
    for _ in range(_N_WARMUP_TICKS):
        tick = ctx.step()

    # Override BESS SoC to the desired value so we control the clean reading.
    for b in ctx.sim_state.bess_units:
        b.soc_mwh = bess_soc_mwh

    assert tick is not None
    return ctx, tick


# ---------------------------------------------------------------------------
# TC-GT2-A: Staleness substitutes the historical SoC value
# ---------------------------------------------------------------------------

def test_tc_gt2_a_staleness_substitutes_historical_soc():
    """Staleness=1 replaces bess_usable_energy_mwh with the value from 1 tick ago.

    We prime _bess_soc_history with a known low value (0.001 MWh), then call
    _apply_soc_corruption.  The output coverage's bess_usable_energy_mwh must
    equal the stale value.
    """
    ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=BESS_USABLE_MWH)

    ctx.telemetry_corruption = _make_schedule_uniform(
        CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
    )
    # Prime: tick index 5 → we want staleness=1 to read the entry at position -1
    ctx._bess_soc_history = [_STALE_SOC_LOW]

    result = _apply_soc_corruption(ctx, tick)

    cov = result.contingency_coverage
    assert cov is not None
    assert cov.bess_usable_energy_mwh == pytest.approx(_STALE_SOC_LOW, abs=1e-6), (
        f"Expected stale SoC {_STALE_SOC_LOW} MWh, got {cov.bess_usable_energy_mwh:.6f}"
    )
    # Physics SoC fraction must be unchanged
    assert result.bess_soc_fraction == tick.bess_soc_fraction, (
        "bess_soc_fraction (physics value) must be unchanged by corruption"
    )


# ---------------------------------------------------------------------------
# TC-GT2-B: Dropout leaves contingency_coverage unchanged
# ---------------------------------------------------------------------------

def test_tc_gt2_b_dropout_leaves_coverage_unchanged():
    """entry.dropout=True → original coverage object returned unchanged."""
    ctx, tick = _make_ctx_and_warmed_tick()
    original_coverage = tick.contingency_coverage

    ctx.telemetry_corruption = _make_schedule_uniform(
        CorruptionEntry(noise_sigma=0.0, dropout=True, staleness=0)
    )

    result = _apply_soc_corruption(ctx, tick)

    assert result.contingency_coverage is original_coverage, (
        "Dropout must leave contingency_coverage object unchanged"
    )


# ---------------------------------------------------------------------------
# TC-GT2-C: Clean entry (all zeros) is the fast-path no-op
# ---------------------------------------------------------------------------

def test_tc_gt2_c_clean_entry_returns_original_tick():
    """noise_sigma=0, dropout=False, staleness=0 → original tick returned (fast path)."""
    ctx, tick = _make_ctx_and_warmed_tick()

    ctx.telemetry_corruption = _make_schedule_uniform(
        CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=0)
    )

    result = _apply_soc_corruption(ctx, tick)

    assert result is tick, "Clean entry must return the original tick_result object (fast path)"


# ---------------------------------------------------------------------------
# TC-GT2-D: Clamping — large stale SoC clamped at usable_mwh
# ---------------------------------------------------------------------------

def test_tc_gt2_d_large_stale_soc_clamped_to_usable():
    """A stale SoC far above usable_mwh must be clamped to usable_mwh."""
    ctx, tick = _make_ctx_and_warmed_tick()

    ctx.telemetry_corruption = _make_schedule_uniform(
        CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
    )
    ctx._bess_soc_history = [1e9]  # absurd stale value

    result = _apply_soc_corruption(ctx, tick)

    cov = result.contingency_coverage
    assert cov is not None
    assert cov.bess_usable_energy_mwh <= BESS_USABLE_MWH + 1e-9, (
        f"bess_usable_energy_mwh {cov.bess_usable_energy_mwh:.4f} "
        f"must not exceed usable_mwh {BESS_USABLE_MWH}"
    )


# ---------------------------------------------------------------------------
# TC-GT2-E: Clamping — negative stale SoC clamped to 0
# ---------------------------------------------------------------------------

def test_tc_gt2_e_negative_stale_soc_clamped_to_zero():
    """A stale SoC below 0 must be clamped to 0."""
    ctx, tick = _make_ctx_and_warmed_tick()

    ctx.telemetry_corruption = _make_schedule_uniform(
        CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
    )
    ctx._bess_soc_history = [-999.0]  # negative stale value

    result = _apply_soc_corruption(ctx, tick)

    cov = result.contingency_coverage
    assert cov is not None
    assert cov.bess_usable_energy_mwh >= 0.0, (
        f"bess_usable_energy_mwh must be ≥ 0; got {cov.bess_usable_energy_mwh:.6f}"
    )


# ---------------------------------------------------------------------------
# TC-GT2-F: ContingencyState flips COVERED → COVERED_WITH_SHED
# ---------------------------------------------------------------------------

def test_tc_gt2_f_state_flips_when_soc_crosses_threshold():
    """End-to-end: staleness corruption with a very low stale SoC flips
    ContingencyState from COVERED to COVERED_WITH_SHED.

    Precondition verification:
    - After warmup, turbines are active and closable=True (surviving headroom > deficit).
    - Clean SoC (2.0 MWh) >> e_required → state=COVERED.
    - Stale SoC (0.001 MWh) < e_required → energy_test fails → state=COVERED_WITH_SHED
      (because shed_required=0 when closable, curtailable=37 MW ≥ 0 → COVERED_WITH_SHED).
    """
    ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=BESS_USABLE_MWH)

    # Verify the clean coverage
    clean_cov = tick.contingency_coverage
    assert clean_cov is not None, "Warmup must produce a non-None contingency_coverage"
    assert clean_cov.closable, (
        "Warmup scenario must be closable so energy test is the binding test"
    )
    assert clean_cov.energy_test_passes, (
        f"Clean SoC ({BESS_USABLE_MWH} MWh) must pass energy test; "
        f"e_required={0.5 * clean_cov.deficit_mw * clean_cov.time_to_close_s / 3600:.6f} MWh"
    )
    assert clean_cov.state == ContingencyState.COVERED, (
        f"Expected COVERED with clean SoC, got {clean_cov.state}"
    )

    # Compute e_required to verify _STALE_SOC_LOW is genuinely below it
    e_required = 0.5 * clean_cov.deficit_mw * clean_cov.time_to_close_s / 3600.0
    assert not math.isinf(e_required), "e_required must be finite"
    assert _STALE_SOC_LOW < e_required, (
        f"Stale SoC {_STALE_SOC_LOW} MWh must be below e_required {e_required:.6f} MWh"
    )

    # Apply corruption: substitute the low stale value
    ctx.telemetry_corruption = _make_schedule_uniform(
        CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=1)
    )
    ctx._bess_soc_history = [_STALE_SOC_LOW]  # primed with the low value

    result = _apply_soc_corruption(ctx, tick)

    corrupted_cov = result.contingency_coverage
    assert corrupted_cov is not None

    # bess_usable_energy_mwh must now reflect the stale value
    assert corrupted_cov.bess_usable_energy_mwh == pytest.approx(_STALE_SOC_LOW, abs=1e-6), (
        f"Expected stale SoC {_STALE_SOC_LOW} in coverage, "
        f"got {corrupted_cov.bess_usable_energy_mwh:.6f}"
    )

    # Energy test must fail (stale SoC below threshold)
    assert not corrupted_cov.energy_test_passes, (
        "Corrupted SoC below e_required must fail energy test"
    )

    # State must have changed from COVERED
    assert corrupted_cov.state in (
        ContingencyState.COVERED_WITH_SHED,
        ContingencyState.CANNOT_CARRY,
    ), f"Expected COVERED_WITH_SHED or CANNOT_CARRY, got {corrupted_cov.state}"

    # The original (clean) coverage must be unchanged — we have a new object
    assert clean_cov.energy_test_passes, "Original clean coverage must be unmodified"
    assert clean_cov.state == ContingencyState.COVERED


# ---------------------------------------------------------------------------
# TC-GT2-G: staleness=2 reads from two ticks ago
# ---------------------------------------------------------------------------

def test_tc_gt2_g_staleness_2_reads_two_ticks_ago():
    """Staleness=2 uses _bess_soc_history[-2], not [-1]."""
    ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=BESS_USABLE_MWH)

    ctx.telemetry_corruption = _make_schedule_uniform(
        CorruptionEntry(noise_sigma=0.0, dropout=False, staleness=2)
    )
    # history[-2] = 0.001, history[-1] = 0.5
    ctx._bess_soc_history = [_STALE_SOC_LOW, _STALE_SOC_HIGH]

    result = _apply_soc_corruption(ctx, tick)

    cov = result.contingency_coverage
    assert cov is not None
    # staleness=2 → history[-2] = _STALE_SOC_LOW (not _STALE_SOC_HIGH)
    assert cov.bess_usable_energy_mwh == pytest.approx(_STALE_SOC_LOW, abs=1e-6), (
        f"staleness=2 must read history[-2]={_STALE_SOC_LOW}, "
        f"got {cov.bess_usable_energy_mwh:.6f}"
    )


# ---------------------------------------------------------------------------
# TC-GT2-H: ctx.telemetry_corruption defaults to None
# ---------------------------------------------------------------------------

def test_tc_gt2_h_no_schedule_defaults_none():
    """A RunContext built without a corruption schedule must have the field = None."""
    from runtime.scenario_factory import build_run_context

    ctx = build_run_context(
        run_id="test-default-run",
        job_id="job-d",
        node_count=10,
        end_sim_time=30.0,
    )
    assert ctx.telemetry_corruption is None, (
        "telemetry_corruption must default to None when not set by runs.py"
    )


# ---------------------------------------------------------------------------
# TC-GT2-I: Gaussian noise — deterministic draw matches expected corrupted SoC
# ---------------------------------------------------------------------------

def test_tc_gt2_i_gaussian_noise_corrupts_soc_deterministically():
    """A noise schedule with a fixed seed produces a predictable corrupted SoC.

    We find a seed that produces a large downward gauss draw (< -0.40),
    then verify _apply_soc_corruption outputs the exact same corrupted value.
    This confirms the RNG is seeded from the schedule's seed and noise is
    applied correctly.
    """
    # Find a seed for gauss(0, 0.8) < -0.40
    chosen_seed: Optional[int] = None
    for seed in range(500):
        rng = random.Random(seed)
        if rng.gauss(0.0, 0.8) < -0.40:
            chosen_seed = seed
            break

    if chosen_seed is None:
        pytest.skip("No suitable seed found in 500 tries")

    ctx, tick = _make_ctx_and_warmed_tick(bess_soc_mwh=BESS_USABLE_MWH)

    entry = CorruptionEntry(noise_sigma=0.8, dropout=False, staleness=0)
    schedule = TelemetryCorruptionSchedule(
        schedule=[entry] * 20,
        seed=chosen_seed,
        noise_sigma=0.8,
        dropout_prob=0.0,
        max_stale=0,
    )
    ctx.telemetry_corruption = schedule

    # Predict the expected corrupted SoC using the same seed
    rng_predict = random.Random(chosen_seed)
    noise_draw = rng_predict.gauss(0.0, 0.8)
    clean_soc = BESS_USABLE_MWH  # ctx.sim_state bess_units SoC was set to this
    expected_corrupted = max(0.0, min(BESS_USABLE_MWH, clean_soc * (1.0 + noise_draw)))

    result = _apply_soc_corruption(ctx, tick)

    cov = result.contingency_coverage
    assert cov is not None

    if abs(expected_corrupted - clean_soc) < 1e-9:
        # Noise was negligible — fast path might be taken; coverage unchanged
        return

    assert cov.bess_usable_energy_mwh == pytest.approx(expected_corrupted, abs=1e-6), (
        f"bess_usable_energy_mwh {cov.bess_usable_energy_mwh:.6f} "
        f"!= expected corrupted value {expected_corrupted:.6f}"
    )

    # bess_soc_fraction (physics value) must be unchanged
    assert result.bess_soc_fraction == tick.bess_soc_fraction, (
        "bess_soc_fraction must not be affected by telemetry corruption"
    )
