"""
tests/test_f5_sim_time_interval_end.py — F5: TickResult.sim_time_seconds is interval-end.

Before F5, sim_time_seconds = clock.sim_time (interval start).
A tick at clock.sim_time=0.0 described state after 5 s of advance() — labeled t=0
but physically at t=5.  For Δt_lead of 30-60 s the 5 s bias is 8-17% of the window
and carries into FR-1.5 MAPE as systematic offset.

After F5, sim_time_seconds = clock.sim_time + clock.dt_seconds.
All internal elapsed-time checks inside evaluate_tick() still use clock.sim_time
(interval-start); only the persisted/wire field changes.
"""

from __future__ import annotations

import contextlib
import pytest

from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.models import (
    BessConfig,
    HardwareProfile,
    IslandMode,
    SiteConfig,
    SolarConfig,
    TurbineConfig,
)
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from runtime.run_manager import _tick_result_to_dict


@contextlib.contextmanager
def _plane_guard_active():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _idle_state() -> SimulationState:
    site = SiteConfig(site_id="f5-test", pue_base=1.03, uncalibrated=False,
                      island_mode=IslandMode.ISLANDED)
    hw = {"hw-a": HardwareProfile("hw-a", rated_kw=10.0)}
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=hw)
    turbine = TurbineModule(TurbineConfig(asset_id="t-0", rated_mw=10.0, r_asset_mw_per_s=0.5))
    bess = BessModule(BessConfig(asset_id="bess-0", rated_mw=5.0, usable_mwh=2.0, grid_forming=False))
    solar = SolarModule(SolarConfig(asset_id="sol-0", rated_mw=0.0),
                        irradiance_profile=IrradianceProfile([(0.0, 0.0)]))
    cooling = CoolingModule(asset_id="cool-0", site=site)
    return SimulationState(run_id="f5-run", site=site, gpu_modules=[gpu],
                           turbines=[turbine], bess_units=[bess],
                           solar_arrays=[solar], cooling=cooling)


def _make_clock(sim_time: float = 0.0, dt: float = 5.0) -> SimClock:
    return SimClock(sim_time=sim_time, dt_seconds=dt, wall_stamp_utc=0.0,
                    rate=1.0, tick_seq=int(sim_time / dt))


# ---------------------------------------------------------------------------
# Core invariant
# ---------------------------------------------------------------------------

def test_sim_time_seconds_is_interval_end_first_tick() -> None:
    """First tick: clock.sim_time=0.0, dt=5.0 → TickResult.sim_time_seconds=5.0.

    Before F5 this returned 0.0; that labeled state-at-t=5 as t=0.
    """
    state = _idle_state()
    clock = _make_clock(sim_time=0.0)
    with _plane_guard_active():
        result = evaluate_tick(state, clock)

    assert result.sim_time_seconds == pytest.approx(5.0), (
        f"Expected sim_time_seconds=5.0 (interval end); got {result.sim_time_seconds:.2f}. "
        f"Was F5 applied to simulation_core.py?"
    )


def test_sim_time_seconds_is_interval_end_subsequent_ticks() -> None:
    """Each tick's sim_time_seconds = clock.sim_time + dt across multiple ticks."""
    state = _idle_state()
    expected_pairs = [
        (0.0, 5.0),
        (5.0, 10.0),
        (10.0, 15.0),
        (295.0, 300.0),
    ]
    for clock_t, expected_t in expected_pairs:
        clock = _make_clock(sim_time=clock_t)
        with _plane_guard_active():
            result = evaluate_tick(state, clock)
        assert result.sim_time_seconds == pytest.approx(expected_t), (
            f"For clock.sim_time={clock_t}: expected {expected_t}, "
            f"got {result.sim_time_seconds:.2f}"
        )


def test_sim_time_seconds_matches_dt() -> None:
    """sim_time_seconds = clock.sim_time + clock.dt_seconds for arbitrary dt."""
    state = _idle_state()
    for dt in (1.0, 5.0, 10.0, 0.5):
        clock = SimClock(sim_time=20.0, dt_seconds=dt, wall_stamp_utc=0.0,
                         rate=1.0, tick_seq=1)
        with _plane_guard_active():
            result = evaluate_tick(state, clock)
        assert result.sim_time_seconds == pytest.approx(20.0 + dt), (
            f"dt={dt}: expected {20.0 + dt}, got {result.sim_time_seconds:.4f}"
        )


# ---------------------------------------------------------------------------
# Wire payload
# ---------------------------------------------------------------------------

def test_sim_time_in_payload_is_interval_end() -> None:
    """_tick_result_to_dict must carry the interval-end sim_time_seconds."""
    state = _idle_state()
    clock = _make_clock(sim_time=0.0)
    with _plane_guard_active():
        result = evaluate_tick(state, clock)
    payload = _tick_result_to_dict(result)
    assert payload["sim_time_seconds"] == pytest.approx(5.0), (
        f"WS payload sim_time_seconds should be 5.0; got {payload['sim_time_seconds']}"
    )


# ---------------------------------------------------------------------------
# No regression: internal thresholds still use clock.sim_time
# ---------------------------------------------------------------------------

def test_internal_elapsed_unaffected_by_f5() -> None:
    """Internal elapsed checks (dt_lead countdown etc.) use clock.sim_time, not
    TickResult.sim_time_seconds.  F5 only changes the output field, not the logic.

    Proof: dt_lead_next_s on the first tick is 40.0 (45 - 5 = 40; advance consumed
    one dt_seconds step before the reading).  If internal logic had been shifted to
    use the interval-end time, the remaining ramp calculation would be wrong.
    """
    from core.models import (
        WorkloadClass, WorkloadEventType, WorkloadSignal,
    )
    state = _idle_state()
    # Inject a GPU job with 45 s ramp (default r_asset_mw_per_s=0.5 for 10 kW node)
    hw = {"hw-a": HardwareProfile("hw-a", rated_kw=10.0)}
    signal = WorkloadSignal(
        event_id="evt-f5", job_id="job-f5",
        event_type=WorkloadEventType.STARTING,
        timestamp=0.0, hardware_profile_id="hw-a",
        node_count=100, workload_class=WorkloadClass.TRAINING,
        site_id=state.site.site_id,
    )
    state.apply_workload_signal(signal, dt_lead_seconds=60.0)

    clock = _make_clock(sim_time=0.0)
    with _plane_guard_active():
        result = evaluate_tick(state, clock)

    # sim_time_seconds is now 5.0 (interval-end) — F5
    assert result.sim_time_seconds == pytest.approx(5.0)
    # But the ramp countdown is still 40.0 (45 - 5 = 40 s remaining after advance)
    assert result.dt_lead_next_s == pytest.approx(40.0, abs=1.0), (
        f"dt_lead_next_s should be ~40 s after first advance(); "
        f"got {result.dt_lead_next_s:.1f}. Internal logic must still use clock.sim_time."
    )
