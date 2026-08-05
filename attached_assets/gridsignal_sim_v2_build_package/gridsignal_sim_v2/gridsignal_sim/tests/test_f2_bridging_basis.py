"""
tests/test_f2_bridging_basis.py — F2: bridging_basis field + binding-demand fix.

The F2 defect: bess_bridging_seconds was computed against current net_demand_mw.
At t=0 in demo-alert the GPU hasn't ramped yet so net_demand ≈ 0 MW, which made
bess_bridging_seconds = math.inf ("full reserve") even though the alert had
already fired.  The panel said "full reserve" beside "Insufficient reserve" —
contradictory to the operator.

The fix: use max(net_demand_mw, pending_peak_shortfall) as the binding demand.
When the pending staged prediction's peak shortfall is larger, use that.

bridging_basis names which figure was used:
  "predicted_peak" — staged prediction's peak shortfall is binding.
  "current_demand" — current net_demand_mw is the binding figure.
  "no_load"        — both are zero; no bridging required.

Test cases:
  1. demo-alert tick 1: alert fires + bridging_basis="predicted_peak" + bridging=0.0.
     The three must appear together — "Insufficient reserve" alongside "0 s cannot bridge".
  2. No GPU jobs (idle): binding demand = 0 → bridging_basis="no_load".
  3. Low demand within BESS ceiling, no pending alert: bridging_basis="current_demand".
  4. bridging_basis appears in _tick_result_to_dict payload.
  5. Panel and alert agree: if insufficient_reserve_alert is True in demo-alert,
     bess_bridging_seconds must be 0.0 — never 86400.
"""

from __future__ import annotations

import asyncio
import contextlib
import math

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
    WorkloadClass,
    WorkloadEventType,
    WorkloadSignal,
)
from core.sim_clock import SimClock
from core.simulation_core import SimulationState, evaluate_tick
from runtime.run_manager import RunManager, WebSocketHub, _tick_result_to_dict
from runtime.scenario_factory import build_run_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _plane_guard_active():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _make_clock(sim_time: float = 0.0, dt_seconds: float = 5.0) -> SimClock:
    return SimClock(sim_time=sim_time, dt_seconds=dt_seconds,
                    wall_stamp_utc=None, rate=1.0, tick_seq=0)


def _idle_state(bess_rated_mw: float = 10.0, bess_usable_mwh: float = 2.0) -> SimulationState:
    """Minimal state with no workload — net_demand will be 0.0 on the first tick."""
    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="test-f2", pue_base=1.03, uncalibrated=False,
                      island_mode=IslandMode.ISLANDED)
    hw = {"hw-a": HardwareProfile("hw-a", rated_kw=10.0)}
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=hw)
    turbine = TurbineModule(TurbineConfig(asset_id="t-0", rated_mw=10.0, r_asset_mw_per_s=0.5))
    bess = BessModule(BessConfig(asset_id="bess-0", rated_mw=bess_rated_mw,
                                  usable_mwh=bess_usable_mwh, grid_forming=False))
    solar = SolarModule(SolarConfig(asset_id="sol-0", rated_mw=0.0),
                        irradiance_profile=IrradianceProfile([(0.0, 0.0)]))
    cooling = CoolingModule(asset_id="cool-0", site=site)
    return SimulationState(run_id="f2-test", site=site, gpu_modules=[gpu],
                           turbines=[turbine], bess_units=[bess],
                           solar_arrays=[solar], cooling=cooling)


async def _run_demo_alert_full() -> list:
    """Run the demo-alert scenario to completion; return all TickResult rows."""
    hub = WebSocketHub()
    manager = RunManager(hub)
    ctx = build_run_context(
        "demo-alert-f2",
        job_id="job-alert",
        node_count=1900,
        turbine_rated_mw=25.0,
        bess_usable_mwh=2.5,
        bess_grid_forming=True,
        end_sim_time=300.0,
    )
    await manager.start_run(ctx)
    await manager._tasks[ctx.run_id]
    return ctx.sink.rows


# ---------------------------------------------------------------------------
# Test 1: demo-alert tick 1 — predicted_peak binding, bridging = 0.0
# ---------------------------------------------------------------------------

def test_bridging_basis_predicted_peak_at_alert_tick() -> None:
    """At tick 1 in demo-alert:
      - insufficient_reserve_alert must be True (scenario is designed for this).
      - bess_bridging_seconds must be 0.0 (5 MW ceiling < ~14 MW predicted peak).
      - bridging_basis must be "predicted_peak".

    Before F2 the basis was "no_load" / bridging = 86400 s ("full reserve")
    because net_demand_mw was 0.0 at t=0.  The panel and alert contradicted.
    """
    ticks = asyncio.run(_run_demo_alert_full())
    tick_1 = ticks[0]

    assert tick_1.insufficient_reserve_alert is True, (
        "demo-alert must fire the insufficient-reserve alert at tick 1"
    )
    assert tick_1.bess_bridging_seconds == pytest.approx(0.0, abs=1e-9), (
        f"Expected 0.0 s (BESS above power ceiling at predicted peak shortfall); "
        f"got {tick_1.bess_bridging_seconds:.1f} s — was F2 applied?"
    )
    assert tick_1.bridging_basis == "predicted_peak", (
        f"Expected 'predicted_peak' because pending_peak_shortfall "
        f"({tick_1.bess_bridging_seconds}) > net_demand_mw (0.0); "
        f"got {tick_1.bridging_basis!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: no load → bridging_basis = "no_load"
# ---------------------------------------------------------------------------

def test_bridging_basis_no_load_when_net_demand_zero() -> None:
    """When no GPU jobs are running and no prediction is staged,
    net_demand_mw = 0.0, so bridging_basis must be 'no_load' and
    bess_bridging_seconds must be math.inf (no dispatch required)."""
    state = _idle_state()
    clock = _make_clock()
    with _plane_guard_active():
        result = evaluate_tick(state, clock)

    assert result.net_demand_mw == pytest.approx(0.0, abs=1e-6)
    assert result.bridging_basis == "no_load", (
        f"Expected 'no_load' when demand is zero; got {result.bridging_basis!r}"
    )
    assert math.isinf(result.bess_bridging_seconds), (
        f"Expected math.inf for no-load bridging; got {result.bess_bridging_seconds}"
    )


# ---------------------------------------------------------------------------
# Test 3: demand within BESS ceiling, no pending alert → "current_demand"
# ---------------------------------------------------------------------------

def test_bridging_basis_current_demand_when_no_pending_alert() -> None:
    """When there is real net demand, no staged prediction, and the demand is
    within the BESS power ceiling, bridging_basis must be 'current_demand'
    and bess_bridging_seconds must be a finite positive value.

    We inject a net demand by setting up a state where the GPU has already
    been given a job (by firing the STARTING signal) and then advancing far
    enough that ramp_progress > 0.  For simplicity we directly verify the
    field against a state that has demand but no _pending_alert.
    """
    # Build a state where the BESS can cover demand
    state = _idle_state(bess_rated_mw=10.0, bess_usable_mwh=5.0)
    # Verify _pending_alert is None before the tick
    assert state._pending_alert is None

    # Manually set p_dispatch_required by giving the GPU a job
    hw = {"hw-a": HardwareProfile("hw-a", rated_kw=10.0)}
    signal = WorkloadSignal(
        event_id="evt-1",
        job_id="job-a",
        event_type=WorkloadEventType.STARTING,
        timestamp=0.0,
        hardware_profile_id="hw-a",
        node_count=20,   # 20 × 10 kW × 1.03 PUE ≈ 0.206 MW — within 10 MW BESS ceiling
        workload_class=WorkloadClass.TRAINING,
        site_id=state.site.site_id,
    )
    state.apply_workload_signal(signal, dt_lead_seconds=30.0)
    # After apply_workload_signal, _pending_alert might be set if gap_s > 0.
    # For 20 nodes, delta_p_mw ≈ 0.2 MW; required_ramp_s = 0.2/0.5 = 0.4 s;
    # gap_s = 0.4 - 30 = -29.6 s ≤ 0 → no alert.  Confirm.
    assert state._pending_alert is None, (
        "Small job with 30s lead should not trigger an alert"
    )

    # Advance several ticks so ramp_progress > 0 and we get actual net demand
    for step in range(10):
        sim_t = step * 5.0
        clock = _make_clock(sim_time=sim_t, dt_seconds=5.0)
        with _plane_guard_active():
            result = evaluate_tick(state, clock)

    # After 10 ticks (50 s sim time), ramp is well underway (~42% at 120 s default)
    assert result.net_demand_mw > 0.0, (
        "After ramp completes, net demand must be positive"
    )
    assert result.bridging_basis == "current_demand", (
        f"No pending alert + positive demand → basis must be 'current_demand'; "
        f"got {result.bridging_basis!r}"
    )
    assert result.bess_bridging_seconds > 0.0, (
        f"Demand within BESS ceiling → bridging_seconds must be > 0; "
        f"got {result.bess_bridging_seconds}"
    )


# ---------------------------------------------------------------------------
# Test 4: bridging_basis appears in _tick_result_to_dict payload
# ---------------------------------------------------------------------------

def test_bridging_basis_in_tick_payload() -> None:
    """bridging_basis must appear in the WS payload dict produced by
    _tick_result_to_dict, so the frontend can read it."""
    state = _idle_state()
    clock = _make_clock()
    with _plane_guard_active():
        result = evaluate_tick(state, clock)

    payload = _tick_result_to_dict(result)
    assert "bridging_basis" in payload, (
        "bridging_basis must be present in the _tick_result_to_dict payload"
    )
    assert payload["bridging_basis"] in ("predicted_peak", "current_demand", "no_load"), (
        f"bridging_basis must be one of the three canonical values; "
        f"got {payload['bridging_basis']!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: panel and alert can never contradict — the critical F2 invariant
# ---------------------------------------------------------------------------

def test_panel_and_alert_never_contradict_in_demo_alert() -> None:
    """If insufficient_reserve_alert is True on any tick, bess_bridging_seconds
    on that same tick must NOT be 86400.0 (the 'full reserve' sentinel).

    86400 means "full reserve — no dispatch required."  An alert means the
    reserve is insufficient.  These two cannot appear on the same tick.

    This test caught the pre-F2 defect: tick 1 had alert=True and
    bridging=86400.0 because net_demand_mw was 0 but the alert had
    already been staged.  After F2 the binding demand includes the
    predicted peak shortfall, so bridging is 0.0 on alerted ticks.
    """
    ticks = asyncio.run(_run_demo_alert_full())
    contradictions = [
        t for t in ticks
        if t.insufficient_reserve_alert and t.bess_bridging_seconds >= 86400.0
    ]
    assert not contradictions, (
        f"{len(contradictions)} tick(s) had both insufficient_reserve_alert=True "
        f"and bess_bridging_seconds ≥ 86400 (full-reserve sentinel).\n"
        f"First contradiction: tick {contradictions[0].tick_index}, "
        f"sim_time={contradictions[0].sim_time_seconds:.1f}s, "
        f"bridging={contradictions[0].bess_bridging_seconds:.1f}s, "
        f"basis={contradictions[0].bridging_basis!r}"
    )
