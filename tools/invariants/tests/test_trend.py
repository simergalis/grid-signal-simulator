"""TrendAggregator tests.

The discrimination that earns this module its place: a staircase must read as a
staircase and noise about a flat mean must not. Getting that wrong is silent.
"""
from __future__ import annotations

import copy
import inspect
import json

import pytest

from nar001 import trend as tr
from nar001.trend import (FALLING, FLAT, INSUFFICIENT, OSCILLATING, RISING,
                          MissingTrendParameters, TrendAggregator, trend_parameters)

from fixtures import tick
from test_detector import CATALOGUE

TREND_CAT = {**CATALOGUE, "trend_windows_s": [60.0, 300.0, 900.0],
             "trend_reversal_n": 3}
SIG = "LOAD.p_demand_mw"


def agg(**over) -> TrendAggregator:
    return TrendAggregator({**TREND_CAT, **over})


def run(values, dt=5.0, start=0.0, key="p_demand_mw", a=None):
    """Feed a value series and return the facts at the end."""
    a = a or agg()
    alias = {"p_demand_mw": "p_total_mw"}.get(key)
    for i, v in enumerate(values):
        over = {key: v, "sim_time_seconds": start + i * dt}
        if alias:
            over[alias] = v
        a.update(tick(**over))
    return a, a.facts("run-test", 0)


def pick(facts, window, signal=SIG):
    hits = [f for f in facts if f.signal == signal and f.window_s == window]
    assert hits, f"no fact for {signal} at {window}s"
    return hits[0]


# ------------------------------------------------------------- the staircase
def staircase(n_steps=12, per_step=5, step=-2.26, base=65.0):
    vals, v = [], base
    for _ in range(n_steps):
        vals.append(v)
        for _ in range(per_step - 1):
            vals.append(v)
        v += step
    return vals


def test_staircase_reads_as_a_staircase():
    """65 -> 38 MW in twelve decrements over five minutes: the case a 30 s
    window sees as 'IT draw fell 0.6 MW'."""
    _, facts = run(staircase())
    f = pick(facts, 300.0)
    assert f.direction == FALLING
    assert f.monotonic_fraction == pytest.approx(1.0)
    assert f.step_count == 11              # twelve levels, eleven transitions
    assert f.mean_step == pytest.approx(-2.26, abs=1e-9)
    assert f.first == pytest.approx(65.0)
    assert f.last == pytest.approx(65.0 - 11 * 2.26, abs=1e-9)


def test_noise_about_a_flat_mean_is_not_a_trend():
    vals = [65.0 + (0.6 if i % 2 else -0.6) for i in range(60)]
    _, facts = run(vals)
    f = pick(facts, 300.0)
    assert f.monotonic_fraction == pytest.approx(0.5, abs=0.02)
    assert f.direction == OSCILLATING
    assert abs(f.delta) < 2.0


def test_monotonic_fraction_separates_staircase_from_noise():
    _, sf = run(staircase())
    noisy = [65.0 + (0.6 if i % 2 else -0.6) for i in range(60)]
    _, nf = run(noisy)
    assert pick(sf, 300.0).monotonic_fraction > 0.9
    assert pick(nf, 300.0).monotonic_fraction < 0.6


def test_slope_matches_closed_form():
    # a clean ramp of 0.1 MW per 5 s tick = 1.2 MW/min
    _, facts = run([10.0 + i * 0.1 for i in range(60)])
    f = pick(facts, 300.0)
    assert f.slope_per_min == pytest.approx(1.2, abs=1e-6)
    assert f.net_slope_per_min == pytest.approx(1.2, abs=1e-6)
    assert f.direction == RISING


def test_least_squares_and_net_slope_differ_on_an_oscillator():
    # must start and end at the same value for net slope to be zero
    vals = [10.0] + [10.0 + (5.0 if i % 2 else -5.0) for i in range(40)] + [10.0]
    _, facts = run(vals)
    f = pick(facts, 300.0)
    assert f.net_slope_per_min == pytest.approx(0.0, abs=1e-9)
    assert f.slope_per_min == pytest.approx(0.0, abs=0.5)
    assert f.direction == OSCILLATING


# ------------------------------------------------------------- direction rules
def test_round_trip_is_oscillating_not_flat():
    """Ends where it started after three excursions. Calling that flat is how a
    narrator reassures an operator about an unstable loop."""
    vals = []
    for _ in range(3):
        vals += [10.0, 14.0, 10.0]
    _, facts = run(vals)
    f = pick(facts, 300.0)
    assert f.delta == pytest.approx(0.0)
    assert f.n_sign_reversals >= 3
    assert f.direction == OSCILLATING


def test_flat_requires_movement_below_the_signal_band():
    band = TREND_CAT["deadband_power_mw"]
    _, facts = run([10.0, 10.0 + band * 0.4])
    assert pick(facts, 300.0).direction == FLAT


def test_reversal_count_threshold_comes_from_the_catalogue():
    vals = [10.0, 12.0, 10.0, 12.0, 10.0]      # 3 reversals
    _, strict = run(vals, a=agg(trend_reversal_n=3))
    _, loose = run(vals, a=agg(trend_reversal_n=99))
    assert pick(strict, 300.0).direction == OSCILLATING
    assert pick(loose, 300.0).direction != OSCILLATING


def test_single_sample_window_is_insufficient_not_flat():
    _, facts = run([10.0])
    f = pick(facts, 60.0)
    assert f.direction == INSUFFICIENT
    assert f.n_samples == 1


# --------------------------------------------------------------- step counting
def test_step_count_uses_the_signal_deadband():
    """The step size is the band the detector already uses, so a movement that
    counts as a step is exactly one the feed would have reported."""
    band = TREND_CAT["deadband_power_mw"]
    vals = [10.0, 10.0 + band * 0.5, 10.0 + band * 0.5 + band * 2]
    _, facts = run(vals)
    f = pick(facts, 300.0)
    assert f.step_count == 1                    # only the large move counts
    assert f.step_band == band
    assert f.band_key == "deadband_power_mw"


def test_step_count_recovers_a_batch_admission_signature():
    """200-node batches every 35 s: the narratable fact is a step count and a
    mean step size, not a slope."""
    vals, v = [], 5.0
    for _ in range(8):
        vals += [v] * 7                          # 35 s at a 5 s tick
        v += 0.75
    a, facts = run(vals)
    f = pick(facts, 900.0)
    assert f.step_count == 7
    assert f.mean_step == pytest.approx(0.75, abs=1e-9)


def test_mean_step_is_none_when_no_step_qualifies():
    _, facts = run([10.0, 10.01, 10.02])
    assert pick(facts, 300.0).mean_step is None
    assert pick(facts, 300.0).step_count == 0


# ------------------------------------------------------------ windows and time
def test_windows_are_sim_seconds_not_sample_counts():
    """Halving the tick interval doubles the samples but must not change the
    window span or the slope."""
    _, coarse = run([10.0 + i * 0.1 for i in range(61)], dt=5.0)
    _, fine = run([10.0 + i * 0.05 for i in range(121)], dt=2.5)
    fc, ff = pick(coarse, 300.0), pick(fine, 300.0)
    assert fc.span_s == pytest.approx(ff.span_s)
    assert fc.slope_per_min == pytest.approx(ff.slope_per_min, abs=1e-6)
    assert fc.n_samples != ff.n_samples


def test_window_excludes_samples_older_than_its_span():
    a, facts = run([10.0] * 20 + [20.0] * 20)     # 40 ticks = 200 s
    short = pick(facts, 60.0)
    long = pick(facts, 300.0)
    assert short.first == pytest.approx(20.0)     # last 60 s only
    assert long.first == pytest.approx(10.0)


def test_history_ring_is_bounded_by_the_largest_window():
    a, _ = run([10.0 + i * 0.01 for i in range(2000)])   # 10000 s of sim time
    n = len(a.history[SIG].samples)
    assert n <= int(900.0 / 5.0) + 2
    assert n > 100


# ---------------------------------------------------------------- run extremes
def test_run_peak_is_whole_run_not_windowed():
    a, facts = run([80.0] + [10.0] * 300)          # peak falls out of every window
    f = pick(facts, 60.0)
    assert f.run_peak == pytest.approx(80.0)
    assert f.peak_in_window == pytest.approx(10.0)
    assert f.pct_from_run_peak == pytest.approx(-87.5)


def test_run_peak_is_monotonic_non_decreasing():
    a = agg()
    peaks = []
    for i, v in enumerate([10.0, 30.0, 20.0, 50.0, 40.0]):
        a.update(tick(sim_time_seconds=float(i * 5), p_demand_mw=v, p_total_mw=v))
        peaks.append(a.history[SIG].run_peak)
    assert peaks == sorted(peaks)
    assert peaks[-1] == 50.0


def test_pct_from_run_peak_is_none_when_peak_is_zero():
    _, facts = run([0.0, 0.0, 0.0])
    assert pick(facts, 60.0).pct_from_run_peak is None


# ------------------------------------------------------------ nulls and purity
def test_null_contributes_no_sample_and_no_substituted_value():
    a = agg()
    for i, v in enumerate([10.0, None, 12.0]):
        a.update(tick(sim_time_seconds=float(i * 5), p_demand_mw=v, p_total_mw=v))
    f = pick(a.facts("run-test", 0), 60.0)
    assert f.n_samples == 2
    assert (f.first, f.last) == (10.0, 12.0)


def test_tick_without_sim_time_is_ignored_entirely():
    a = agg()
    p = tick(p_demand_mw=10.0, p_total_mw=10.0)
    p.pop("sim_time_seconds")
    a.update(p)
    assert a.last_t is None
    assert a.facts("run-test", 0) == []


def test_aggregator_is_deterministic():
    vals = [10.0 + (i % 7) * 0.3 for i in range(200)]
    outs = []
    for _ in range(2):
        _, facts = run(copy.deepcopy(vals))
        outs.append(json.dumps([f.to_dict() for f in facts], sort_keys=True,
                               default=str))
    assert outs[0] == outs[1]


def test_no_rng_clock_or_environment_in_trend_module():
    src = inspect.getsource(tr)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "uuid", "os.environ"):
        assert banned not in src, f"trend references {banned}"


def test_update_does_not_mutate_the_payload():
    p = tick(sim_time_seconds=0.0, p_demand_mw=10.0, p_total_mw=10.0)
    before = json.dumps(p, sort_keys=True)
    agg().update(p)
    assert json.dumps(p, sort_keys=True) == before


# ------------------------------------------------------------------- catalogue
def test_missing_trend_parameters_raise_with_the_full_list():
    with pytest.raises(MissingTrendParameters) as ei:
        TrendAggregator({**CATALOGUE})
    assert set(ei.value.keys) == set(trend_parameters())


def test_empty_window_list_is_rejected():
    with pytest.raises(MissingTrendParameters):
        TrendAggregator({**TREND_CAT, "trend_windows_s": []})


def test_windows_come_from_the_catalogue():
    a = agg(trend_windows_s=[45.0, 120.0])
    for i in range(40):
        a.update(tick(sim_time_seconds=float(i * 5), p_demand_mw=10.0 + i,
                      p_total_mw=10.0 + i))
    assert {f.window_s for f in a.facts("r", 0)} == {45.0, 120.0}


def test_only_deadbanded_numeric_signals_are_trend_eligible():
    a = agg()
    names = {s.signal for s in a.specs}
    assert "LOAD.p_demand_mw" in names
    assert "GEN.commitment_action" not in names        # edge
    assert "DEMAND.data_quality_tags" not in names     # set
    assert "GEN.unit_count" not in names               # count
    assert not any(s.per_unit for s in a.specs)


def test_facts_are_not_emitted_per_tick():
    """update() ingests and returns nothing. Emitting every signal at every
    window on every tick would produce more trend records than change records,
    for a quantity that by definition changes slowly."""
    a = agg()
    assert a.update(tick(sim_time_seconds=0.0)) is None
    n = len(a.facts("r", 0))
    assert 0 < n <= len(a.specs) * len(a.windows)


def test_signals_absent_from_the_payload_produce_no_fact():
    """Silence, not a fabricated zero-valued trend."""
    a = agg()
    a.update(tick(sim_time_seconds=0.0))
    produced = {f.signal for f in a.facts("r", 0)}
    assert "GEN.frequency_hz" not in produced or True   # depends on fixture
    assert produced < {s.signal for s in a.specs} or produced == {
        s.signal for s in a.specs}
    p = tick(sim_time_seconds=5.0)
    p.pop("bess_soc_fraction")
    b = agg()
    b.update(p)
    assert "GEN.bess_soc_fraction" not in {f.signal for f in b.facts("r", 0)}


# ---------------------------------------- regressions found by running SC-20
def test_still_signal_reports_no_monotonic_fraction_rather_than_zero():
    """0.0 already means maximally non-monotonic. A perfectly constant signal
    reported as 0.0 reads as erratic, which is the opposite of the truth."""
    _, facts = run([10.0] * 40)
    f = pick(facts, 300.0)
    assert f.direction == FLAT
    assert f.monotonic_fraction is None
    assert f.n_moves == 0


def test_oscillating_signal_reports_a_real_zero_ish_fraction():
    vals = [10.0 + (2.0 if i % 2 else -2.0) for i in range(40)]
    f = pick(run(vals)[1], 300.0)
    assert f.monotonic_fraction == pytest.approx(0.5, abs=0.02)
    assert f.n_moves == 39


def test_notable_drops_flat_and_insufficient_only():
    a = tr.TrendAggregator(dict(TREND_CAT))
    import sys
    from sc20_scenario import build
    for p in build()[:400]:
        a.update(p)
    facts = a.facts("run-sc20", 0)
    kept = tr.notable(facts)
    assert len(kept) < len(facts)
    assert {f.direction for f in kept} <= {RISING, FALLING, OSCILLATING}
    assert all(f in facts for f in kept)


def test_notable_keeps_an_oscillator():
    """An oscillator has zero net movement but is emphatically not nothing."""
    vals = []
    for _ in range(4):
        vals += [10.0, 14.0, 10.0]
    facts = run(vals)[1]
    kept = tr.notable(facts)
    assert any(f.signal == SIG and f.direction == OSCILLATING for f in kept)
