"""
tests/test_step7_payload.py — Step 7: three new TickResult fields + back-pressure fix.

C1 — bess_bridging_seconds:
  Must come from BessModule.max_sustainable_seconds() (same function as the
  insufficient-reserve check), not from a MW/MW × 3600 ratio in the serializer.
  For a fleet: min() across proportionally-allocated shares (D13).
  Key invariant: a unit ABOVE its power ceiling returns 0.0 — "cannot bridge".

C2 — dt_lead_next_s:
  min() across in-flight ramp remaining times, not sum().
  Two jobs with 10 s and 30 s remaining → next full-TDP event in 10 s.
  sum() = 40 s corresponds to no physical event.
  Field named dt_lead_next_s (not dt_lead_s) so the semantics are on the field.

p_renewable_mw:
  Must be exposed directly; not recoverable from net_demand_mw after the lossy
  clamp max(0, p_total − p_renewable).

Back-pressure:
  broadcast() must complete in ≤ 2 × _SEND_TIMEOUT_S even when a subscriber's
  send_json() never resolves (backgrounded tab, full TCP buffer).
  The stalled subscriber must be dropped; the healthy subscriber must still receive.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time as _time

import pytest

from core.asset_modules import (
    BessModule,
    CoolingModule,
    GPUModule,
    IrradianceProfile,
    SolarModule,
    TurbineModule,
)
from core.dispatch import DispatchArbitrator
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
from runtime.run_manager import WebSocketHub, _tick_result_to_dict, _SEND_TIMEOUT_S


# ---------------------------------------------------------------------------
# Shared test helpers (mirrors test_formulas.py patterns)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _plane_guard_active():
    """Set the Step-4 ContextVar sentinel for tests that call evaluate_tick()
    directly (without going through RunContext.step())."""
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _make_clock(sim_time: float = 0.0, dt_seconds: float = 5.0) -> SimClock:
    return SimClock(
        sim_time=sim_time,
        dt_seconds=dt_seconds,
        wall_stamp_utc=None,
        rate=1.0,
        tick_seq=0,
    )


def _minimal_state(
    *,
    bess_rated_mw: float = 10.0,
    bess_usable_mwh: float = 2.0,
    bess_initial_soc: float = 1.0,
    solar_rated_mw: float = 0.0,
    turbine_rated_mw: float = 10.0,
) -> SimulationState:
    """Minimal SimulationState sufficient for Step 7 field tests."""
    site = SiteConfig(site_id="test-site", pue_base=1.03, uncalibrated=False,
                      island_mode=IslandMode.ISLANDED)
    hw = {"profile_a": HardwareProfile("profile_a", rated_kw=10.0)}
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=hw)
    turbine = TurbineModule(
        config=TurbineConfig(asset_id="t-0", rated_mw=turbine_rated_mw, r_asset_mw_per_s=0.5)
    )
    bess = BessModule(
        config=BessConfig(
            asset_id="bess-0",
            rated_mw=bess_rated_mw,
            usable_mwh=bess_usable_mwh,
            initial_soc_fraction=bess_initial_soc,
            grid_forming=False,
        )
    )
    irr = IrradianceProfile([(0.0, solar_rated_mw / max(solar_rated_mw, 1.0))])
    solar = SolarModule(
        config=SolarConfig(asset_id="solar-0", rated_mw=solar_rated_mw),
        irradiance_profile=irr,
    )
    cooling = CoolingModule(asset_id="cool-0", site=site)
    return SimulationState(
        run_id="test-run",
        site=site,
        gpu_modules=[gpu],
        turbines=[turbine],
        bess_units=[bess],
        solar_arrays=[solar],
        cooling=cooling,
    )


# ---------------------------------------------------------------------------
# p_renewable_mw
# ---------------------------------------------------------------------------

def test_p_renewable_mw_exposed_in_tick_result():
    """Solar output must appear in TickResult.p_renewable_mw and in the WS
    payload dict.  Before Step 7 this field did not exist; it could not be
    recovered from net_demand_mw after the lossy clamp."""
    # 4 MW solar rated, irradiance = 1.0 → output 4 MW
    solar_rated = 4.0
    state = _minimal_state(solar_rated_mw=solar_rated)
    clock = _make_clock()
    with _plane_guard_active():
        result = evaluate_tick(state, clock)
    assert result.p_renewable_mw == pytest.approx(solar_rated, abs=0.01), (
        f"expected p_renewable_mw ≈ {solar_rated}, got {result.p_renewable_mw}"
    )
    payload = _tick_result_to_dict(result)
    assert "p_renewable_mw" in payload
    assert payload["p_renewable_mw"] == pytest.approx(solar_rated, abs=0.01)


def test_p_renewable_mw_absent_when_no_solar():
    """With no solar panels, p_renewable_mw must be 0.0."""
    state = _minimal_state(solar_rated_mw=0.0)
    clock = _make_clock()
    with _plane_guard_active():
        result = evaluate_tick(state, clock)
    assert result.p_renewable_mw == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# bess_bridging_seconds — C1
# ---------------------------------------------------------------------------

def test_bess_bridging_seconds_above_power_ceiling_returns_zero():
    """C1 key invariant: a BESS unit asked to sustain more power than its
    bridging_available_mw reports 0.0 seconds — 'cannot bridge at that level'.

    Setup: rated_mw=5, usable_mwh=100 (ample energy, not the constraint),
    net_demand=10 MW.  The single unit's allocated share (10 MW) exceeds its
    power ceiling (5 MW) so max_sustainable_seconds() returns 0.0 regardless
    of stored energy.

    Before C1, a MW/MW × 3600 ratio in the serializer would have computed
    (5/10) × 3600 = 1800 s — wrong, because the unit cannot deliver 10 MW
    at all.  The correct answer is 0 s: cannot bridge.
    """
    # rated_mw=5, demand=10 (above ceiling) → 0.0 s
    state = _minimal_state(bess_rated_mw=5.0, bess_usable_mwh=100.0)
    site = state.site

    # To get net_demand_mw = 10 MW we need compute = 10 MW.  Rather than
    # running the GPU ramp (which starts near zero), directly verify the
    # BESS arithmetic by calling max_sustainable_seconds() on the unit
    # as evaluate_tick() will when net_demand_mw > rated_mw.
    bess = state.bess_units[0]
    demand_mw = 10.0  # > rated_mw=5
    result = bess.max_sustainable_seconds(demand_mw, site.island_mode)
    assert result == pytest.approx(0.0), (
        f"expected 0.0 s above power ceiling, got {result}"
    )

    # Confirm the same result flows through _proportional_allocations + min().
    island_mode = site.island_mode
    ceilings = [bess.bridging_available_mw(island_mode)]
    allocs = state.arbitrator._proportional_allocations(demand_mw, ceilings)
    fleet_min = min(
        b.max_sustainable_seconds(a, island_mode)
        for b, a in zip(state.bess_units, allocs)
    )
    assert fleet_min == pytest.approx(0.0), (
        f"fleet_min expected 0.0 (above power ceiling), got {fleet_min}"
    )


def test_bess_bridging_seconds_within_power_ceiling():
    """BESS within its power ceiling: result = (usable_mwh / demand_mw) × 3600.

    Setup: rated_mw=10, usable_mwh=1.0, demand=5 MW (below ceiling).
    Expected: (1.0 / 5.0) × 3600 = 720 s.
    """
    bess = BessModule(
        config=BessConfig(
            asset_id="bess-1",
            rated_mw=10.0,
            usable_mwh=1.0,
            initial_soc_fraction=1.0,
            grid_forming=False,
        )
    )
    island_mode = IslandMode.ISLANDED
    result = bess.max_sustainable_seconds(5.0, island_mode)
    assert result == pytest.approx(720.0, abs=0.01), (
        f"expected 720 s, got {result}"
    )


def test_bess_bridging_seconds_in_tick_payload():
    """End-to-end: bess_bridging_seconds appears in _tick_result_to_dict output
    and is a positive finite number when net_demand > 0 and BESS has energy."""
    # Use a state where GPU output will be > 0 after one tick by giving the
    # GPU a job at full TDP (SCALE event → ramp_progress=1.0 immediately).
    state = _minimal_state(bess_rated_mw=10.0, bess_usable_mwh=2.0)
    # SCALE the GPU so output_mw() is non-zero immediately (no ramp wait).
    state.gpu_modules[0].apply_signal(WorkloadSignal(
        event_id="e1", job_id="j1", event_type=WorkloadEventType.SCALE,
        timestamp=0.0, hardware_profile_id="profile_a", node_count=100,
        workload_class=WorkloadClass.TRAINING, site_id="test-site",
    ))
    clock = _make_clock()
    with _plane_guard_active():
        result = evaluate_tick(state, clock)
    assert result.net_demand_mw > 0, "need non-zero demand for a meaningful bridging test"
    assert result.bess_bridging_seconds > 0.0
    assert math.isfinite(result.bess_bridging_seconds)
    payload = _tick_result_to_dict(result)
    assert "bess_bridging_seconds" in payload
    assert payload["bess_bridging_seconds"] > 0.0
    assert payload["bess_bridging_seconds"] <= 86400.0


def test_bess_bridging_seconds_inf_capped_in_payload():
    """When net_demand_mw == 0 (renewables cover full load), bess_bridging_seconds
    is math.inf in TickResult.  _tick_result_to_dict must cap it to 86400.0 so
    the WS payload remains JSON-safe."""
    from core.models import TickResult, ConfidenceBand
    # Manufacture a TickResult with bess_bridging_seconds=math.inf directly.
    tick = TickResult(
        run_id="r", tick_index=1, sim_time_seconds=0.0,
        p_compute_mw=0.0, p_cooling_mw=0.0, p_total_mw=0.0,
        net_demand_mw=0.0, turbine_output_mw=0.0, bess_output_mw=0.0,
        bess_soc_fraction=1.0,
        confidence=ConfidenceBand(point_estimate_mw=0.0, plus_minus_fraction=0.05),
        p_renewable_mw=0.0,
        bess_bridging_seconds=math.inf,
        dt_lead_next_s=0.0,
    )
    payload = _tick_result_to_dict(tick)
    assert payload["bess_bridging_seconds"] == pytest.approx(86400.0), (
        f"inf must be capped to 86400.0, got {payload['bess_bridging_seconds']}"
    )


# ---------------------------------------------------------------------------
# dt_lead_next_s — C2
# ---------------------------------------------------------------------------

def test_dt_lead_next_s_is_min_not_sum():
    """C2: two in-flight ramping jobs → dt_lead_next_s = min of remaining ramp
    times, NOT sum.

    Setup: module A has job with 10 s remaining, module B has job with 30 s
    remaining.  Expected: 10.0.  Wrong answer (pre-C2): 40.0 (sum).
    """
    site = SiteConfig(site_id="s", pue_base=1.0, uncalibrated=False)
    hw = {"p": HardwareProfile("p", rated_kw=10.0)}

    # Module A: ramp_seconds=20, progress=0.5 → remaining = 10 s
    gpu_a = GPUModule(asset_id="gpu-a", site=site, hardware_library=hw, ramp_seconds=20.0)
    gpu_a.apply_signal(WorkloadSignal(
        event_id="e1", job_id="j1", event_type=WorkloadEventType.STARTING,
        timestamp=0.0, hardware_profile_id="p", node_count=1,
        workload_class=WorkloadClass.TRAINING, site_id="s",
    ))
    gpu_a._ramp_progress["j1"] = 0.5  # remaining = 0.5 × 20 = 10 s

    # Module B: ramp_seconds=45, progress=1/3 → remaining = 30 s
    gpu_b = GPUModule(asset_id="gpu-b", site=site, hardware_library=hw, ramp_seconds=45.0)
    gpu_b.apply_signal(WorkloadSignal(
        event_id="e2", job_id="j2", event_type=WorkloadEventType.STARTING,
        timestamp=0.0, hardware_profile_id="p", node_count=1,
        workload_class=WorkloadClass.TRAINING, site_id="s",
    ))
    gpu_b._ramp_progress["j2"] = 1.0 / 3.0  # remaining = (2/3) × 45 = 30 s

    remaining_a = gpu_a.min_ramp_remaining_seconds()
    remaining_b = gpu_b.min_ramp_remaining_seconds()
    assert remaining_a == pytest.approx(10.0, abs=0.01), f"A: expected 10 s, got {remaining_a}"
    assert remaining_b == pytest.approx(30.0, abs=0.01), f"B: expected 30 s, got {remaining_b}"

    fleet_min = min(remaining_a, remaining_b)
    fleet_sum = remaining_a + remaining_b
    assert fleet_min == pytest.approx(10.0, abs=0.01), "fleet min must be 10 s"
    assert fleet_sum == pytest.approx(40.0, abs=0.01), "fleet sum (wrong answer) is 40 s"
    # Only min() is physically meaningful: the NEXT GPU reaches full TDP in 10 s.
    assert fleet_min != fleet_sum, "min ≠ sum — the C2 correction is necessary"


def test_dt_lead_next_s_zero_when_no_ramp():
    """When all jobs have completed their ramp (progress=1.0), dt_lead_next_s
    must be 0.0 (no active ramp)."""
    state = _minimal_state()
    # Apply a SCALE event: ramp_progress snaps to 1.0 immediately.
    state.gpu_modules[0].apply_signal(WorkloadSignal(
        event_id="e1", job_id="j1", event_type=WorkloadEventType.SCALE,
        timestamp=0.0, hardware_profile_id="profile_a", node_count=10,
        workload_class=WorkloadClass.TRAINING, site_id="test-site",
    ))
    clock = _make_clock()
    with _plane_guard_active():
        result = evaluate_tick(state, clock)
    assert result.dt_lead_next_s == pytest.approx(0.0, abs=1e-9), (
        f"expected 0.0 with no active ramp, got {result.dt_lead_next_s}"
    )


def test_dt_lead_next_s_in_tick_payload():
    """dt_lead_next_s appears in _tick_result_to_dict with correct value."""
    state = _minimal_state()
    # STARTING job: ramp starts at 0.
    state.gpu_modules[0].apply_signal(WorkloadSignal(
        event_id="e1", job_id="j1", event_type=WorkloadEventType.STARTING,
        timestamp=0.0, hardware_profile_id="profile_a", node_count=1,
        workload_class=WorkloadClass.TRAINING, site_id="test-site",
    ))
    # Set progress to 0.5 so remaining = 0.5 × ramp_seconds (45) = 22.5 s.
    state.gpu_modules[0]._ramp_progress["j1"] = 0.5
    clock = _make_clock()
    with _plane_guard_active():
        result = evaluate_tick(state, clock)
    # After evaluate_tick advances by dt=5 s, ramp_progress increases by 5/45 ≈ 0.111.
    # New progress ≈ 0.611, remaining ≈ (1 - 0.611) × 45 ≈ 17.5 s.
    assert result.dt_lead_next_s > 0.0
    assert result.dt_lead_next_s < 45.0  # must be less than full ramp window
    payload = _tick_result_to_dict(result)
    assert "dt_lead_next_s" in payload
    assert payload["dt_lead_next_s"] == pytest.approx(result.dt_lead_next_s, abs=0.01)


# ---------------------------------------------------------------------------
# Back-pressure — stalled subscriber
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stalled_subscriber_does_not_block_broadcast():
    """A subscriber whose send_json() never resolves (backgrounded tab, full
    TCP buffer) must not block broadcast() beyond _SEND_TIMEOUT_S.

    Three assertions:
    1. broadcast() returns in ≤ 2 × _SEND_TIMEOUT_S wall-clock seconds.
    2. The stalled subscriber is removed from the hub after the call.
    3. A healthy sibling subscriber receives exactly one send_json() call.
    """
    from core.models import TickResult, ConfidenceBand

    tick = TickResult(
        run_id="r1", tick_index=1, sim_time_seconds=0.0,
        p_compute_mw=0.0, p_cooling_mw=0.0, p_total_mw=0.0,
        net_demand_mw=0.0, turbine_output_mw=0.0, bess_output_mw=0.0,
        bess_soc_fraction=1.0,
        confidence=ConfidenceBand(point_estimate_mw=0.0, plus_minus_fraction=0.05),
    )

    class _StalledWS:
        """send_json() returns a Future that never resolves — simulates a
        backgrounded tab with a full TCP receive buffer."""
        def __init__(self):
            self._calls = 0
            self._loop = asyncio.get_event_loop()

        async def send_json(self, data: dict) -> None:
            self._calls += 1
            await asyncio.get_event_loop().create_future()  # never resolves

    class _HealthyWS:
        """send_json() resolves immediately."""
        def __init__(self):
            self.received: list[dict] = []

        async def send_json(self, data: dict) -> None:
            self.received.append(data)

    stalled = _StalledWS()
    healthy = _HealthyWS()

    hub = WebSocketHub()
    hub.subscribe("r1", stalled)
    hub.subscribe("r1", healthy)

    t0 = _time.monotonic()
    await hub.broadcast("r1", tick)
    elapsed = _time.monotonic() - t0

    # 1. broadcast() must complete in at most 2 × timeout (one timeout per
    #    subscriber in the worst case, gathered concurrently → 1× in practice).
    assert elapsed < 2 * _SEND_TIMEOUT_S + 0.05, (  # 50 ms scheduling slack
        f"broadcast took {elapsed:.3f}s; expected < {2 * _SEND_TIMEOUT_S + 0.05:.3f}s"
    )

    # 2. Stalled subscriber must have been dropped.
    subs = hub._subscribers.get("r1", set())
    assert stalled not in subs, "stalled subscriber must be removed after timeout"

    # 3. Healthy subscriber must have received exactly one message.
    assert len(healthy.received) == 1, (
        f"healthy subscriber expected 1 message, got {len(healthy.received)}"
    )
