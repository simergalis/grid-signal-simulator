"""
tests/test_stochastic_step.py — Acceptance tests for the stochastic step
scheduler and within-step load profile.

Sections
--------
T1–T7  : StepScheduler timing properties
S1–S3  : Spectral / frequency content
L1–L3  : Load profile amplitude and coherence
D1–D3  : RNG stream isolation

All tests operate on core code directly (no HTTP, no asyncio, no evaluate_tick
guard) so they run in any Python shell.  StepScheduler and GPUModule are driven
via thin helpers that do not touch run_manager or scenario_factory.

Regression fixture (S3):
    tests/fixtures/step_baseline_600s_10hz.json
    Contains the first 600 s of step events at 10 Hz with seed=42.
    On first run (no file) the fixture is generated and the test passes.
    On subsequent runs the captured sequence is compared deterministically.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

from core.step_config import LoadProfileConfig, StepTimingConfig
from core.step_scheduler import StepScheduler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_BASELINE_FILE = _FIXTURE_DIR / "step_baseline_600s_10hz.json"


# ---------------------------------------------------------------------------
# Simulation helpers (no HTTP / asyncio / evaluate_tick guard)
# ---------------------------------------------------------------------------


def _simulate_step_sequence(
    duration_s: float,
    hz: float,
    seed: int,
    config: Optional[StepTimingConfig] = None,
) -> dict:
    """Drive StepScheduler directly for `duration_s` at `hz` tick rate.

    Returns a dict with:
      - steps: list of {"sim_time": float, "kind": str} for every fired step
      - phases: list of float (step_phase at each tick)
      - n_ticks: int
    """
    if config is None:
        config = StepTimingConfig()
    ss = np.random.SeedSequence(seed)
    rng = np.random.default_rng(ss.spawn(1)[0])
    sched = StepScheduler(config=config)

    dt = 1.0 / hz
    n_ticks = round(duration_s / dt)
    steps = []
    phases = []
    for i in range(n_ticks):
        t = i * dt
        fired, phase, kind = sched.tick(t, dt, rng)
        phases.append(phase)
        if fired:
            steps.append({"sim_time": round(t, 6), "kind": kind})
    return {"steps": steps, "phases": phases, "n_ticks": n_ticks}


def _simulate_compute_load(
    duration_s: float,
    hz: float,
    seed: int,
    base_draw_mw: float = 10.0,
    step_config: Optional[StepTimingConfig] = None,
    load_config: Optional[LoadProfileConfig] = None,
    phase_coherence_override: Optional[float] = None,
) -> dict:
    """Drive StepScheduler + first-order lag to produce per-tick compute MW.

    Mimics what simulation_core / GPUModule do together without instantiating
    the full SimulationState.

    Returns: {"mw": list[float], "phases": list[float], "n_ticks": int}
    """
    if step_config is None:
        step_config = StepTimingConfig()
    if load_config is None:
        load_config = LoadProfileConfig()
    if phase_coherence_override is not None:
        load_config = LoadProfileConfig(
            f_compute=load_config.f_compute,
            p_comm_ratio=load_config.p_comm_ratio,
            tau_gpu_s=load_config.tau_gpu_s,
            phase_coherence=phase_coherence_override,
            noise_sigma_fraction=load_config.noise_sigma_fraction,
        )

    ss = np.random.SeedSequence(seed)
    children = ss.spawn(2)
    rng_step = np.random.default_rng(children[0])
    rng_load = np.random.default_rng(children[1])

    sched = StepScheduler(config=step_config)
    lag = 1.0  # starts in compute phase

    dt = 1.0 / hz
    n_ticks = round(duration_s / dt)
    mw_series = []
    phase_series = []

    for i in range(n_ticks):
        t = i * dt
        _fired, phase, _kind = sched.tick(t, dt, rng_step)

        # Update lag (replicates GPUModule.advance logic)
        raw_profile = (
            1.0 if phase < load_config.f_compute
            else load_config.p_comm_ratio
        )
        alpha = 1.0 - math.exp(-dt / max(load_config.tau_gpu_s, 1e-9))
        lag += alpha * (raw_profile - lag)

        # Compute effective draw (replicates GPUModule.per_job_compute_mw logic)
        eff_mult = 1.0 + load_config.phase_coherence * (lag - 1.0)
        mw = base_draw_mw * eff_mult
        noise = rng_load.normal(0.0, base_draw_mw * load_config.noise_sigma_fraction)
        mw = max(0.0, mw + noise)
        mw_series.append(mw)
        phase_series.append(phase)

    return {"mw": mw_series, "phases": phase_series, "n_ticks": n_ticks}


# ===========================================================================
# T1–T7: StepScheduler timing properties
# ===========================================================================


class TestStepSchedulerTiming:
    """T1–T7: core StepScheduler guarantees."""

    def test_T1_median_step_close_to_spec(self):
        """T1 — Empirical median inter-step duration is within ±15% of median_step_s."""
        result = _simulate_step_sequence(duration_s=600, hz=100, seed=42)
        steps = result["steps"]
        assert len(steps) > 200, "Need enough steps to estimate median reliably"

        durations = [
            steps[i + 1]["sim_time"] - steps[i]["sim_time"]
            for i in range(len(steps) - 1)
        ]
        empirical_median = float(np.median(durations))
        expected = StepTimingConfig().median_step_s
        assert abs(empirical_median - expected) / expected < 0.15, (
            f"Empirical median {empirical_median:.4f} s deviates >15% from "
            f"spec default {expected} s"
        )

    def test_T2_step_phase_in_unit_interval(self):
        """T2 — step_phase ∈ [0, 1) on every tick."""
        result = _simulate_step_sequence(duration_s=60, hz=100, seed=0)
        phases = result["phases"]
        assert len(phases) > 0
        # Ignore the first tick (initialisation returns 0.0 unconditionally).
        for i, ph in enumerate(phases[1:], start=1):
            assert 0.0 <= ph < 1.0, (
                f"Tick {i}: step_phase={ph} outside [0, 1)"
            )

    def test_T3_step_kind_values(self):
        """T3 — step_kind is always "training" or "checkpoint"."""
        result = _simulate_step_sequence(duration_s=1200, hz=10, seed=7)
        steps = result["steps"]
        valid_kinds = {"training", "checkpoint"}
        for s in steps:
            assert s["kind"] in valid_kinds, f"Unexpected step_kind: {s['kind']!r}"

    def test_T4_checkpoint_steps_exist(self):
        """T4 — At least one checkpoint step appears in a 1200 s run."""
        result = _simulate_step_sequence(duration_s=1200, hz=10, seed=7)
        steps = result["steps"]
        ckpt_steps = [s for s in steps if s["kind"] == "checkpoint"]
        assert len(ckpt_steps) >= 1, (
            f"No checkpoint steps in 1200 s run; got {len(steps)} total steps"
        )

    def test_T5_checkpoint_step_longer_than_median(self):
        """T5 — Checkpoint step durations are ≥ ckpt_min_s (≥ 5 s by default)."""
        config = StepTimingConfig()
        result = _simulate_step_sequence(duration_s=2000, hz=10, seed=13, config=config)
        steps = result["steps"]

        # Build list of (index_in_steps, duration_s, kind) tuples
        events = []
        for i in range(len(steps) - 1):
            d = steps[i + 1]["sim_time"] - steps[i]["sim_time"]
            events.append((i, d, steps[i]["kind"]))

        ckpt_events = [(i, d, k) for (i, d, k) in events if k == "checkpoint"]
        if not ckpt_events:
            pytest.skip("No checkpoint step fired in this seed/duration; extend duration")

        for _i, dur, _k in ckpt_events:
            assert dur >= config.ckpt_min_s * 0.9, (
                f"Checkpoint duration {dur:.2f} s < ckpt_min_s * 0.9 = "
                f"{config.ckpt_min_s * 0.9:.2f} s"
            )

    def test_T6_checkpoint_step_at_interval(self):
        """T6 — A checkpoint fires roughly every ckpt_interval_steps ± ckpt_jitter_steps steps."""
        config = StepTimingConfig()
        result = _simulate_step_sequence(duration_s=2000, hz=10, seed=13, config=config)
        steps = result["steps"]
        ckpt_indices = [i for i, s in enumerate(steps) if s["kind"] == "checkpoint"]

        if len(ckpt_indices) < 2:
            pytest.skip("Not enough checkpoints; extend duration or reduce seed")

        # Gaps between consecutive checkpoint events
        gaps = [
            ckpt_indices[j + 1] - ckpt_indices[j]
            for j in range(len(ckpt_indices) - 1)
        ]
        lo = config.ckpt_interval_steps - config.ckpt_jitter_steps * 2
        hi = config.ckpt_interval_steps + config.ckpt_jitter_steps * 2
        for g in gaps:
            assert lo <= g <= hi, (
                f"Checkpoint gap {g} steps outside [{lo}, {hi}] range"
            )

    def test_T7_tick_rate_independence(self):
        """T7 — Step count in 300 s is not dominated by tick rate.

        A tick-rate-independent scheduler produces roughly the same number of
        steps at 10 Hz and 100 Hz (within ±10%).  The old tick % 7 approach
        would give 10× more steps at 100 Hz than at 10 Hz.
        """
        config = StepTimingConfig()
        # Same seed, same duration, two different tick rates
        r10 = _simulate_step_sequence(duration_s=300, hz=10, seed=42, config=config)
        r100 = _simulate_step_sequence(duration_s=300, hz=100, seed=42, config=config)

        n10 = len(r10["steps"])
        n100 = len(r100["steps"])
        assert n10 > 0 and n100 > 0, "No steps fired at one or both tick rates"

        ratio = max(n10, n100) / min(n10, n100)
        assert ratio < 1.10, (
            f"Step count ratio {ratio:.3f} between 10 Hz ({n10}) and 100 Hz ({n100}) "
            f"is ≥ 1.10 — scheduler appears tick-rate-dependent (old tick % N bug?)"
        )


# ===========================================================================
# S1–S3: Spectral / frequency tests
# ===========================================================================


class TestSpectral:
    """S1–S3: step frequency lives near the expected band in the power spectrum."""

    # Target frequency band: 1/0.70 ≈ 1.43 Hz ± 50%  → [0.71, 2.14] Hz
    F_STEP_HZ = 1.0 / StepTimingConfig().median_step_s
    F_LOW = F_STEP_HZ * 0.5
    F_HIGH = F_STEP_HZ * 1.5

    def _step_count_series(self, duration_s: float, hz: float, seed: int) -> list:
        """Per-tick binary series: 1 if a step fired this tick, else 0."""
        config = StepTimingConfig()
        rng = np.random.default_rng(np.random.SeedSequence(seed).spawn(1)[0])
        sched = StepScheduler(config=config)
        dt = 1.0 / hz
        n_ticks = round(duration_s / dt)
        series = []
        for i in range(n_ticks):
            fired, _ph, _kind = sched.tick(i * dt, dt, rng)
            series.append(1.0 if fired else 0.0)
        return series

    def test_S1_dominant_frequency_in_band(self):
        """S1 — The dominant FFT peak (above DC) falls near 1/median_step_s.

        For a lognormal renewal process (CV=0.08), the step-train power
        spectrum has a clear but stochastically broadened peak near the mean
        firing rate.  The energy in any narrow band is small compared to the
        total spread, so we test the LOCATION of the peak rather than an
        energy-fraction criterion.

        Criterion: the frequency bin that contains the maximum spectral power
        above DC must lie within [F_step * 0.50, F_step * 1.50].
        """
        hz = 100.0  # high sample rate for frequency resolution
        series = self._step_count_series(duration_s=600, hz=hz, seed=42)
        fft_mag = np.abs(np.fft.rfft(series))
        freqs = np.fft.rfftfreq(len(series), d=1.0 / hz)

        # Find the frequency of the maximum power above DC.
        dc_idx = 1
        peak_bin = np.argmax(fft_mag[dc_idx:])
        peak_freq = freqs[dc_idx:][peak_bin]

        assert self.F_LOW <= peak_freq <= self.F_HIGH, (
            f"Dominant spectral peak at {peak_freq:.3f} Hz is outside the "
            f"expected band [{self.F_LOW:.2f}, {self.F_HIGH:.2f}] Hz "
            f"(based on median_step_s={StepTimingConfig().median_step_s} s)."
        )

    def test_S2_no_harmonic_at_tick_rate(self):
        """S2 — No sharp aliasing spike at 1/dt (10 Hz) in a 100 Hz series.

        A spike at 10 Hz would indicate the scheduler was snapping steps to
        the tick grid (the old tick % N bug).
        """
        hz = 100.0
        series = self._step_count_series(duration_s=600, hz=hz, seed=42)
        fft_mag = np.abs(np.fft.rfft(series))
        freqs = np.fft.rfftfreq(len(series), d=1.0 / hz)

        # Check around 10 Hz (±0.5 Hz)
        alias_mask = (freqs >= 9.5) & (freqs <= 10.5)
        if not alias_mask.any():
            pytest.skip("No FFT bins near 10 Hz")

        alias_peak = fft_mag[alias_mask].max()
        # Should be smaller than the dominant step-frequency peak
        dc_idx = 1
        step_band_mask = (freqs >= self.F_LOW) & (freqs <= self.F_HIGH)
        step_peak = fft_mag[step_band_mask].max() if step_band_mask.any() else 1.0

        assert alias_peak < step_peak * 0.5, (
            f"Aliasing spike at ~10 Hz ({alias_peak:.1f}) is too large relative "
            f"to step-frequency peak ({step_peak:.1f}) — scheduler may be grid-snapping"
        )

    def test_S3_deterministic_fixture(self):
        """S3 — Seed-42 step sequence matches a saved fixture; auto-generates on first run."""
        result = _simulate_step_sequence(duration_s=600, hz=10, seed=42)
        captured = {
            "seed": 42,
            "duration_s": 600,
            "hz": 10,
            "steps": result["steps"],
        }

        if not _BASELINE_FILE.exists():
            # First run: generate the fixture file.
            _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            _BASELINE_FILE.write_text(
                json.dumps(captured, indent=2), encoding="utf-8"
            )
            return  # pass on first run

        # Subsequent runs: compare against the fixture.
        saved = json.loads(_BASELINE_FILE.read_text(encoding="utf-8"))
        saved_steps = saved["steps"]
        new_steps = captured["steps"]

        assert len(new_steps) == len(saved_steps), (
            f"Step count changed: got {len(new_steps)}, expected {len(saved_steps)}"
        )
        for i, (n, s) in enumerate(zip(new_steps, saved_steps)):
            assert abs(n["sim_time"] - s["sim_time"]) < 1e-4, (
                f"Step {i} sim_time changed: {n['sim_time']} vs saved {s['sim_time']}"
            )
            assert n["kind"] == s["kind"], (
                f"Step {i} kind changed: {n['kind']!r} vs saved {s['kind']!r}"
            )


# ===========================================================================
# L1–L3: Load profile amplitude and coherence
# ===========================================================================


class TestLoadProfile:
    """L1–L3: within-step power profile amplitude and coherence."""

    def test_L1_peak_to_peak_above_threshold(self):
        """L1 — Peak-to-peak oscillation ≥ 20% of mean (default phase_coherence=0.85).

        The default configuration (f_compute=0.72, p_comm_ratio=0.55,
        phase_coherence=0.85) gives a ≈42% peak-to-peak in the steady-state
        signal (after the ramp period and tau_gpu_s transient).
        """
        # Skip the first 180 s (ramp + OU warm-up); measure the remaining 420 s.
        warmup_s = 180
        total_s = 600
        hz = 100.0
        result = _simulate_compute_load(
            duration_s=total_s, hz=hz, seed=42, base_draw_mw=10.0
        )
        mw = np.array(result["mw"])
        warmup_ticks = int(warmup_s * hz)
        mw_steady = mw[warmup_ticks:]

        mean_val = mw_steady.mean()
        assert mean_val > 0.0
        ptp = mw_steady.max() - mw_steady.min()
        ptp_fraction = ptp / mean_val

        assert ptp_fraction >= 0.20, (
            f"Peak-to-peak {ptp_fraction:.1%} of mean is below 20% threshold. "
            f"mean={mean_val:.3f} MW, peak={mw_steady.max():.3f}, "
            f"trough={mw_steady.min():.3f}"
        )

    def test_L2_incoherent_fleet_is_flat(self):
        """L2 — With phase_coherence=0.0 the effective profile is near 1.0 everywhere.

        effective_profile = 1 + 0 * (lag - 1) = 1.0 → compute_mw ≈ base_draw.
        The noise sigma is 0.5% so peak-to-peak should be ≤ 3% of mean.
        """
        warmup_s = 60
        total_s = 300
        hz = 100.0
        result = _simulate_compute_load(
            duration_s=total_s, hz=hz, seed=42, base_draw_mw=10.0,
            phase_coherence_override=0.0,
        )
        mw = np.array(result["mw"])
        warmup_ticks = int(warmup_s * hz)
        mw_steady = mw[warmup_ticks:]

        mean_val = mw_steady.mean()
        # Use the 1st–99th percentile range instead of strict max–min to
        # avoid sensitivity to Gaussian extremes over ~24 000 samples
        # (max–min ≈ 5–6 σ, which at σ=0.5% of mean gives ~3–4% p-p).
        # The 1st–99th percentile range stays within ≈ 2.6 σ ≈ 1.3% of mean,
        # well below the 3% ceiling that confirms phase suppression.
        ptp = float(np.percentile(mw_steady, 99) - np.percentile(mw_steady, 1))
        ptp_fraction = ptp / mean_val

        assert ptp_fraction <= 0.03, (
            f"With phase_coherence=0 expected flat signal (1st–99th p-p ≤3%) "
            f"but got {ptp_fraction:.1%}. Phase coherence suppression broken?"
        )

    def test_L3_load_config_none_unchanged(self):
        """L3 — Without load_config the per_job_compute_mw is the pure ramp formula.

        Instantiate GPUModule directly (no SimulationState) and verify that
        without load_config the return value is base_draw × ramp_multiplier
        exactly, with no noise or profile modulation.
        """
        from core.asset_modules import GPUModule
        from core.models import (
            GENERIC_FALLBACK_PROFILE,
            HardwareProfile,
            SiteConfig,
        )

        site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="test", pue_base=1.0)
        profile = GENERIC_FALLBACK_PROFILE  # rated_kw known
        hw_lib = {"test_profile": profile}

        gpu = GPUModule(
            asset_id="test-gpu-0",
            site=site,
            hardware_library=hw_lib,
            ramp_seconds=1.0,   # short ramp; advance past it below
            # load_config intentionally omitted (defaults to None)
        )

        # Admit a job
        from core.models import WorkloadClass, WorkloadEventType, WorkloadSignal
        sig = WorkloadSignal(
            event_id="e1",
            job_id="j1",
            event_type=WorkloadEventType.STARTING,
            timestamp=0.0,
            hardware_profile_id="test_profile",
            node_count=10,
            workload_class=WorkloadClass.TRAINING,
            site_id="test",
            renewable_shortfall_mw=0.0,
        )
        gpu.apply_signal(sig)
        # Advance past the ramp window (2 × ramp_seconds) so progress reaches 1.0.
        gpu.advance(sim_time=0.0, dt_seconds=2.0)

        # With load_config=None, no profile modulation applied.
        # Result must equal full_kw * ramp_multiplier(1.0) = full_kw exactly.
        expected = 10 * profile.rated_kw * site.pue_base / 1000.0
        actual = gpu.per_job_compute_mw("j1")
        assert math.isclose(actual, expected, rel_tol=1e-9), (
            f"Without load_config expected {expected:.6f} MW, got {actual:.6f} MW. "
            f"Possible regression: profile applied when load_config is None."
        )


# ===========================================================================
# D1–D3: RNG stream isolation
# ===========================================================================


class TestRngIsolation:
    """D1–D3: stream independence between job scheduling, step, and load noise."""

    def _make_agent(
        self,
        rng_step=None,
        rng_load=None,
        step_config: Optional[StepTimingConfig] = None,
        load_config: Optional[LoadProfileConfig] = None,
    ):
        from core.kube_demand import KubeConfig, KubeDemandAgent
        config = KubeConfig(
            rng_seed=42,
            step_config=step_config,
            load_config=load_config,
        )
        return KubeDemandAgent(
            config,
            site_id="test-site",
            rng_step=rng_step,
            rng_load=rng_load,
        )

    def test_D1_step_scheduler_created_when_config_set(self):
        """D1 — StepScheduler is wired when step_config is provided."""
        agent = self._make_agent(step_config=StepTimingConfig())
        assert agent._step_scheduler is not None, (
            "StepScheduler not created even though step_config was provided"
        )

    def test_D2_step_scheduler_absent_without_config(self):
        """D2 — No StepScheduler when step_config is None (backward compat)."""
        agent = self._make_agent()
        assert agent._step_scheduler is None, (
            "StepScheduler unexpectedly created when step_config was not provided"
        )

    def test_D3_stream_isolation(self):
        """D3 — Adding draws to rng_step does not affect rng_load (and vice versa).

        Inject two externally-created generators so we can predict exactly
        what each stream will produce.  Exhaust rng_step with 100 draws and
        confirm rng_load output is unchanged relative to the control case.
        """
        from core.kube_demand import KubeConfig, KubeDemandAgent

        seed = 999
        ss = np.random.SeedSequence(seed)
        children = ss.spawn(2)

        # Control: fresh rng_load from the same child, no rng_step interference
        rng_load_ctrl = np.random.default_rng(children[1])
        ctrl_samples = rng_load_ctrl.normal(0, 1, size=10).tolist()

        # Experiment: inject rng_step into an agent with step_config active.
        # The agent will call rng_step inside its step scheduler every tick.
        # rng_load should be untouched by those draws.
        rng_step_exp = np.random.default_rng(children[0])
        rng_load_exp = np.random.default_rng(children[1])  # same seed as ctrl

        agent = self._make_agent(
            rng_step=rng_step_exp,
            rng_load=rng_load_exp,
            step_config=StepTimingConfig(),
        )

        # Run the scheduler for 100 ticks — this draws from rng_step many times.
        _mock_grid_state = None
        for i in range(100):
            agent.tick(sim_time=float(i) * 0.1, dt_seconds=0.1, grid_state=_mock_grid_state)

        # Now draw from rng_load_exp (the same object injected into the agent).
        # It should be identical to the control because rng_step draws never
        # touch rng_load.
        exp_samples = agent.rng_load.normal(0, 1, size=10).tolist()

        for i, (c, e) in enumerate(zip(ctrl_samples, exp_samples)):
            assert math.isclose(c, e, rel_tol=1e-12), (
                f"Sample {i}: rng_load={e:.8f} diverged from control {c:.8f}. "
                f"rng_step draws leaked into rng_load stream."
            )
