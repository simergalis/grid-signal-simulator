"""
tests/test_frequency_mode_guard.py — Regression guard: frequency_hz grid-connected invariant.

Phase 11.3 added a swing equation that deviates frequency_hz from 50 Hz only in islanded
mode.  This file catches the regression where a mode-flag bug silently activates the swing
equation in grid-connected mode and shows operators a false frequency deviation alarm.

MG1 : Grid-connected + depleted BESS → frequency_hz == 50.0 on every one of 50 ticks.
MG2 : Islanded + depleted BESS      → at least one tick has frequency_hz ≠ 50.0.
MG3 : WS broadcast dict has frequency_hz == 50.0 in grid-connected mode.
"""

from __future__ import annotations

import contextlib

import pytest

# ---------------------------------------------------------------------------
# Plane-guard helper (mirrors test_forecast_path.py pattern)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _plane_guard_active():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


# ---------------------------------------------------------------------------
# Shared imports
# ---------------------------------------------------------------------------

from core.asset_modules import BessModule, CoolingModule, GPUModule, TurbineModule
from core.models import (
    BessConfig,
    HardwareProfile,
    IslandMode,
    SiteConfig,
    TurbineConfig,
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HW_LIBRARY = {
    "enterprise_8gpu_air": HardwareProfile(
        profile_id="enterprise_8gpu_air",
        rated_kw=10.2,
    ),
}


def _make_state(island_mode: IslandMode, bess_soc: float = 0.0) -> SimulationState:
    """Minimal SimulationState with depleted BESS, variable island mode."""
    site = SiteConfig(
        site_id="test-mg",
        pue_base=1.03,
        alpha_max=0.20,
        tau_seconds=20.0,
        dt_thermal_seconds=90.0,
        uncalibrated=False,
        workload_signal_stale_s=30.0,
        island_mode=island_mode,
        inertia_constant_s=4.0,
        frequency_nominal_hz=50.0,
        power_factor=0.85,
        governor_droop=0.04,
    )
    gpu = GPUModule(
        asset_id="gpu-0",
        site=site,
        hardware_library=_HW_LIBRARY,
        ramp_seconds=1.0,
    )
    turbine = TurbineModule(
        TurbineConfig(
            asset_id="gt-1",
            rated_mw=10.0,
            r_asset_mw_per_s=5.0,
        )
    )
    # Depleted BESS: tiny usable capacity so there is always a non-zero balance
    # residual the swing equation could act on (regression bait), yet no
    # division-by-zero in BessModule initialisation.
    bess = BessModule(
        BessConfig(
            asset_id="bess-1",
            rated_mw=5.0,
            usable_mwh=0.01,
            initial_soc_fraction=bess_soc,
            p_anchor_reserve_mw=0.0,
            grid_forming=False,
        )
    )
    cooling = CoolingModule(asset_id="cooling-0", site=site)
    state = SimulationState(
        run_id="test-mg",
        site=site,
        gpu_modules=[gpu],
        turbines=[turbine],
        bess_units=[bess],
        solar_arrays=[],
        cooling=cooling,
    )
    # Activate a GPU job so there is a real load and a non-trivial balance residual.
    sig = WorkloadSignal(
        event_id="ev-job-mg-start",
        job_id="job-mg",
        event_type=WorkloadEventType.STARTING,
        timestamp=0.0,
        node_count=10,
        hardware_profile_id="enterprise_8gpu_air",
        workload_class=WorkloadClass.TRAINING,
        site_id="test-mg",
    )
    state.apply_workload_signal(sig, dt_lead_seconds=0.0)
    return state


def _run_tick(state: SimulationState, sim_time: float, dt: float = 0.1):
    """Run one evaluate_tick under the plane guard and return the TickResult."""
    clock = SimClock(
        sim_time=sim_time,
        dt_seconds=dt,
        wall_stamp_utc=0.0,
        rate=1.0,
        tick_seq=0,
    )
    with _plane_guard_active():
        return evaluate_tick(state, clock)


def _run_n_ticks(state: SimulationState, n: int, dt: float = 0.1):
    """Run *n* consecutive ticks and return the list of TickResults."""
    results = []
    for i in range(n):
        results.append(_run_tick(state, sim_time=i * dt, dt=dt))
    return results


# ===========================================================================
# MG1 — Grid-connected: frequency_hz must stay at nominal for all 50 ticks
# ===========================================================================

class TestGridConnectedFrequencyInvariant:
    """MG1: With island_mode=GRID_TIE and depleted BESS, frequency_hz must
    equal frequency_nominal_hz (50.0 Hz) on *every* tick for 50 ticks.

    Rationale: the swing equation is engaged only in islanded mode.
    A regression that accidentally runs it in grid-connected mode would
    cause at least one tick to deviate from 50 Hz.
    """

    def test_MG1_grid_tie_frequency_stays_at_nominal_50_ticks(self):
        """MG1: frequency_hz == 50.0 on each of 50 ticks in grid-connected mode
        with a depleted BESS (creates a non-zero balance residual that would
        drive the swing equation if the mode guard were missing).
        """
        state = _make_state(island_mode=IslandMode.GRID_TIE, bess_soc=0.0)
        nominal_hz = state.site.frequency_nominal_hz  # 50.0

        ticks = _run_n_ticks(state, n=50)

        deviations = [
            (i, t.frequency_hz)
            for i, t in enumerate(ticks)
            if t.frequency_hz != pytest.approx(nominal_hz, abs=1e-9)
        ]
        assert not deviations, (
            f"MG1: frequency_hz deviated from {nominal_hz} Hz in grid-connected "
            f"mode (BESS depleted) on tick(s): "
            + ", ".join(f"tick {i}: {f_hz:.6f} Hz" for i, f_hz in deviations)
        )


# ===========================================================================
# MG2 — Islanded: at least one tick must deviate from nominal
# ===========================================================================

class TestIslandedFrequencyDeviates:
    """MG2: With island_mode=ISLANDED and depleted BESS, at least one of 50
    ticks must have frequency_hz ≠ 50.0.

    This is the mirror test: if the swing equation is suppressed everywhere it
    would never activate, and both MG1 and MG2 would trivially pass even if
    the guard logic were inverted.  MG2 proves the swing equation *is* live in
    islanded mode.
    """

    def test_MG2_islanded_frequency_deviates_from_nominal(self):
        """MG2: At least one of 50 ticks has frequency_hz ≠ 50.0 in islanded mode
        with a depleted BESS driving a non-zero balance residual.
        """
        state = _make_state(island_mode=IslandMode.ISLANDED, bess_soc=0.0)
        nominal_hz = state.site.frequency_nominal_hz  # 50.0

        ticks = _run_n_ticks(state, n=50)

        any_deviation = any(
            abs(t.frequency_hz - nominal_hz) > 1e-9
            for t in ticks
        )
        assert any_deviation, (
            f"MG2: expected at least one tick with frequency_hz ≠ {nominal_hz} Hz "
            f"in islanded mode (depleted BESS); all 50 ticks returned exactly "
            f"{nominal_hz} Hz — the swing equation may be inactive."
        )


# ===========================================================================
# MG3 — WS broadcast dict has frequency_hz == 50.0 in grid-connected mode
# ===========================================================================

class TestWsBroadcastFrequencyGridConnected:
    """MG3: The _tick_result_to_dict WS payload also emits frequency_hz == 50.0
    in grid-connected mode.

    Ensures that even if a future refactor copies the raw TickResult field
    differently into the broadcast payload, the operator UI is not fed a
    spurious deviation value.
    """

    def test_MG3_ws_dict_frequency_hz_is_nominal_in_grid_tie(self):
        """MG3: _tick_result_to_dict emits frequency_hz == frequency_nominal_hz
        in grid-connected mode with depleted BESS.
        """
        from runtime.run_manager import _tick_result_to_dict

        state = _make_state(island_mode=IslandMode.GRID_TIE, bess_soc=0.0)
        nominal_hz = state.site.frequency_nominal_hz  # 50.0

        tick = _run_tick(state, sim_time=5.0)
        d = _tick_result_to_dict(tick)

        assert "frequency_hz" in d, (
            "MG3: 'frequency_hz' key missing from _tick_result_to_dict output"
        )
        assert d["frequency_hz"] == pytest.approx(nominal_hz, abs=1e-9), (
            f"MG3: WS broadcast frequency_hz must be {nominal_hz} Hz in "
            f"grid-connected mode (BESS depleted); got {d['frequency_hz']:.6f} Hz"
        )
