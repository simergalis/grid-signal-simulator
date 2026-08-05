"""
tests/test_fabric_tick_payload.py — Task 35 verification

End-to-end checks that the fabric field flows from FabricEngine.step()
through _tick_result_to_dict() and out to the WebSocket tick payload.

TC-P35-1  FabricEngine.modal_view() returns all FabricModalView keys.
TC-P35-2  _tick_result_to_dict carries "fabric" when fabric_modal is set.
TC-P35-3  "fabric" is null in the payload when fabric_modal is None (headless path).
TC-P35-4  The control sub-dict contains all FabricControlPath fields.
TC-P35-5  The discrimination sub-dict contains all FabricDiscrimination fields.
TC-P35-6  FabricEngine.step() returns non-None for all three capability tiers.
TC-P35-7  WS tick from a spec-path run includes a non-null "fabric" key.
"""

from __future__ import annotations

import dataclasses
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_engine(seed: int = 42, tier: str = "current"):
    from runtime.fabric_engine import FabricEngine
    return FabricEngine(seed=seed, capability_tier=tier)


# The complete key sets expected by the TypeScript FabricModalView interface.
_MODAL_VIEW_KEYS = frozenset({
    "topology_nodes",
    "congested_links",
    "bandwidth_headroom_frac",
    "packet_loss",
    "retransmit_rate",
    "control_latency_ms",
    "control",
    "discrimination",
    "link_utilisation",
})

_CONTROL_PATH_KEYS = frozenset({
    "l_fabric_ms",
    "l_gateway_ms",
    "l_retransmit_ms",
    "l_asset_ack_ms",
    "breached",
    "dominant_term",
    "budget_ms",
})

_DISCRIMINATION_KEYS = frozenset({
    "verdict",
    "phase_discrimination_available",
    "capability_tier",
    "compute_quiesced",
    "storage_elephant_sustained",
    "precedence_note",
})

# ---------------------------------------------------------------------------
# TC-P35-1: modal_view() key completeness
# ---------------------------------------------------------------------------

def test_tc_p35_1_modal_view_all_keys():
    """FabricEngine.modal_view() must return exactly the keys required by the
    TypeScript FabricModalView interface (no missing, no crash)."""
    engine = _build_engine()
    result = engine.step(sim_time_s=10.0, dt_s=5.0)
    assert result is not None, "FabricEngine.step() must not return None"

    mv = engine.modal_view()
    assert mv is not None, "modal_view() must not return None after a successful step()"

    missing = _MODAL_VIEW_KEYS - set(mv.keys())
    assert not missing, (
        f"modal_view() is missing keys required by FabricModalView: {missing}"
    )


# ---------------------------------------------------------------------------
# TC-P35-2: _tick_result_to_dict includes "fabric" when set
# ---------------------------------------------------------------------------

@contextmanager
def _plane_guard_active():
    from core._plane_guard import _EVALUATE_TICK_PERMITTED
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


def _minimal_tick_result():
    """Build a minimal TickResult via evaluate_tick (the authorised path)."""
    from core.asset_modules import (
        GPUModule, TurbineModule, BessModule, SolarModule, CoolingModule,
        IrradianceProfile,
    )
    from core.models import (
        SiteConfig, IslandMode, HardwareProfile,
        TurbineConfig, BessConfig, SolarConfig,
    )
    from core.sim_clock import SimClock
    from core.simulation_core import SimulationState, evaluate_tick

    site = SiteConfig(frequency_nominal_hz=50.0, power_factor=0.85, site_id="p35-test", pue_base=1.03, uncalibrated=False,
                      island_mode=IslandMode.ISLANDED)
    hw = {"hw-a": HardwareProfile("hw-a", rated_kw=10.0)}
    gpu = GPUModule(asset_id="gpu-0", site=site, hardware_library=hw)
    turbine = TurbineModule(TurbineConfig(asset_id="t-0", rated_mw=10.0, r_asset_mw_per_s=0.5))
    bess = BessModule(BessConfig(asset_id="bess-0", rated_mw=10.0, usable_mwh=5.0,
                                  grid_forming=False))
    solar = SolarModule(SolarConfig(asset_id="sol-0", rated_mw=0.0),
                        irradiance_profile=IrradianceProfile([(0.0, 0.0)]))
    cooling = CoolingModule(asset_id="cool-0", site=site)
    state = SimulationState(run_id="p35-test", site=site, gpu_modules=[gpu],
                            turbines=[turbine], bess_units=[bess],
                            solar_arrays=[solar], cooling=cooling)
    clock = SimClock(sim_time=0.0, dt_seconds=5.0, wall_stamp_utc=None,
                     rate=1.0, tick_seq=0)
    with _plane_guard_active():
        return evaluate_tick(state, clock)


def test_tc_p35_2_fabric_in_payload_when_set():
    """_tick_result_to_dict must include a non-null 'fabric' key when
    tick.fabric_modal is populated by FabricEngine.modal_view()."""
    from runtime.run_manager import _tick_result_to_dict

    engine = _build_engine(seed=99)
    engine.step(sim_time_s=5.0, dt_s=5.0)
    modal = engine.modal_view()
    assert modal is not None

    tick = _minimal_tick_result()
    tick_with_fabric = dataclasses.replace(tick, fabric_modal=modal)

    payload = _tick_result_to_dict(tick_with_fabric)
    assert "fabric" in payload, "'fabric' key must be present in _tick_result_to_dict output"
    fab = payload["fabric"]
    assert fab is not None, "'fabric' value must be non-null when FabricEngine is wired"

    missing = _MODAL_VIEW_KEYS - set(fab.keys())
    assert not missing, (
        f"'fabric' payload is missing FabricModalView keys: {missing}"
    )


# ---------------------------------------------------------------------------
# TC-P35-3: "fabric" is null in headless path
# ---------------------------------------------------------------------------

def test_tc_p35_3_fabric_null_when_not_wired():
    """When fabric_modal is None (headless / direct-job-id path), 'fabric'
    must be present in the payload but null — never absent."""
    from runtime.run_manager import _tick_result_to_dict

    tick = _minimal_tick_result()
    # Ensure fabric_modal is None (default)
    tick_no_fabric = dataclasses.replace(tick, fabric_modal=None)

    payload = _tick_result_to_dict(tick_no_fabric)
    assert "fabric" in payload, (
        "'fabric' key must always be present (null, not absent) in the payload"
    )
    assert payload["fabric"] is None, (
        "'fabric' must be null when FabricEngine is not wired"
    )


# ---------------------------------------------------------------------------
# TC-P35-4: control sub-dict shape
# ---------------------------------------------------------------------------

def test_tc_p35_4_control_path_keys():
    """The 'control' sub-dict inside modal_view() must contain all
    FabricControlPath fields expected by the TypeScript interface."""
    engine = _build_engine()
    engine.step(sim_time_s=10.0, dt_s=5.0)
    mv = engine.modal_view()

    ctrl = mv["control"]
    assert isinstance(ctrl, dict), "'control' must be a dict"

    missing = _CONTROL_PATH_KEYS - set(ctrl.keys())
    assert not missing, (
        f"'control' sub-dict is missing FabricControlPath keys: {missing}"
    )
    assert isinstance(ctrl["breached"], bool), "'breached' must be bool"
    assert isinstance(ctrl["dominant_term"], str), "'dominant_term' must be str"
    assert ctrl["budget_ms"] > 0, "'budget_ms' must be positive"


# ---------------------------------------------------------------------------
# TC-P35-5: discrimination sub-dict shape
# ---------------------------------------------------------------------------

def test_tc_p35_5_discrimination_keys():
    """The 'discrimination' sub-dict must contain all FabricDiscrimination
    fields expected by the TypeScript interface."""
    engine = _build_engine()
    engine.step(sim_time_s=10.0, dt_s=5.0)
    mv = engine.modal_view()

    disc = mv["discrimination"]
    assert isinstance(disc, dict), "'discrimination' must be a dict"

    missing = _DISCRIMINATION_KEYS - set(disc.keys())
    assert not missing, (
        f"'discrimination' is missing FabricDiscrimination keys: {missing}"
    )
    assert isinstance(disc["verdict"], str), "'verdict' must be str"
    assert isinstance(disc["compute_quiesced"], bool)
    assert isinstance(disc["storage_elephant_sustained"], bool)


# ---------------------------------------------------------------------------
# TC-P35-6: step() returns non-None for all capability tiers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", ["current", "degraded", "advanced"])
def test_tc_p35_6_step_non_null_all_tiers(tier):
    """FabricEngine.step() must produce a non-None result for every capability
    tier string so that modal_view() is always available during a demo run."""
    engine = _build_engine(seed=0, tier=tier)
    result = engine.step(sim_time_s=30.0, dt_s=5.0)
    assert result is not None, (
        f"FabricEngine.step() returned None for capability_tier={tier!r}"
    )
    mv = engine.modal_view()
    assert mv is not None, (
        f"modal_view() returned None after successful step() for tier={tier!r}"
    )


# ---------------------------------------------------------------------------
# TC-P35-7: WS tick from a spec-path run includes non-null "fabric"
# ---------------------------------------------------------------------------

def test_tc_p35_7_ws_tick_contains_fabric():
    """A WebSocket tick from a spec-path run (demo-20mw) must carry a non-null
    'fabric' key — confirming the FabricEngine is wired by scenario_factory."""
    from fastapi.testclient import TestClient
    from api.app import create_app

    body = {
        "scenario_id": "demo-20mw",
        "playback_speed": 0.0,
    }
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=body).json()["run_id"]

        with client.websocket_connect(f"/ws/{run_id}") as ws:
            data = ws.receive_json()

    assert "fabric" in data, (
        "WebSocket tick payload from a spec-path run must include a 'fabric' key"
    )
    fab = data["fabric"]
    assert fab is not None, (
        "The 'fabric' key must be non-null for spec-path runs — FabricEngine "
        "should be wired by scenario_factory._build_fabric_engine()"
    )

    missing = _MODAL_VIEW_KEYS - set(fab.keys())
    assert not missing, (
        f"Live WS tick 'fabric' payload is missing FabricModalView keys: {missing}"
    )

    # Spot-check the most important display values the modal renders
    assert isinstance(fab["control_latency_ms"], (int, float)), \
        "'control_latency_ms' must be numeric"
    assert isinstance(fab["topology_nodes"], int), \
        "'topology_nodes' must be int"
    assert isinstance(fab["link_utilisation"], dict) and len(fab["link_utilisation"]) > 0, \
        "'link_utilisation' must be a non-empty dict"
    assert isinstance(fab["control"], dict), "'control' must be a dict"
    assert isinstance(fab["discrimination"], dict), "'discrimination' must be a dict"
