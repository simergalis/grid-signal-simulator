"""D6a-X additive measured non-GPU load tests (TC-ISL-44 through 49)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.schemas import ScenarioSpec
from core.physical_identity import physical_tick_json
from core.simulation_core import _non_gpu_load_mw_at
from runtime.persistence import _tick_to_json
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec


_SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "scenarios"
    / "demo-islanded-ramp.json"
)


def _spec(profile=None, *, remove_sources=False):
    spec = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    spec.update(
        {
            "end_sim_time": 60.0,
            "workload_events": [],
            "tenant_events": [],
            "kube_config": None,
            "load_config": None,
            "cluster_gen_config": None,
            "stressor_gen_config": None,
            "workload_floor_fraction": None,
            "gpu_load_profile": [],
        }
    )
    if profile is not None:
        spec["non_gpu_load_profile_mw"] = profile
    else:
        spec.pop("non_gpu_load_profile_mw", None)
    if remove_sources:
        spec["turbine_units"] = []
        spec["bess_units"] = []
        spec["initial_spinning_count"] = 0
        spec["solar_rated_mw"] = 0.0
    return ScenarioSpec.model_validate(spec).model_dump(mode="json")


def _first_tick(profile=None, *, remove_sources=False):
    ctx = build_run_context_from_spec(
        "tc-isl-d6ax",
        _spec(profile, remove_sources=remove_sources),
        playback_speed=0.0,
        run_seed=42,
        execution_mode="headless",
    )
    return ctx.step()


def test_tc_isl_44_schema_validation_and_empty_profile():
    """TC-ISL-44 — D6a-X validates ordering and non-negative finite values."""
    assert ScenarioSpec.model_validate(_spec([])).non_gpu_load_profile_mw == []
    with pytest.raises(ValueError, match="strictly increasing"):
        ScenarioSpec.model_validate(_spec([[5.0, 1.0], [5.0, 2.0]]))
    with pytest.raises(ValueError, match="strictly increasing"):
        ScenarioSpec.model_validate(_spec([[6.0, 1.0], [5.0, 2.0]]))
    with pytest.raises(ValueError, match="load must be finite and >= 0"):
        ScenarioSpec.model_validate(_spec([[0.0, -0.1]]))
    with pytest.raises(ValueError, match="time must be finite and >= 0"):
        ScenarioSpec.model_validate(_spec([[-0.1, 1.0]]))


def test_tc_isl_45_profile_is_zero_before_first_then_holds_last():
    """TC-ISL-45 — D6a-X piecewise-constant lookup semantics."""
    profile = [(10.0, 1.25), (20.0, 0.5)]
    assert _non_gpu_load_mw_at(profile, 0.0) == 0.0
    assert _non_gpu_load_mw_at(profile, 9.999) == 0.0
    assert _non_gpu_load_mw_at(profile, 10.0) == 1.25
    assert _non_gpu_load_mw_at(profile, 19.999) == 1.25
    assert _non_gpu_load_mw_at(profile, 20.0) == 0.5
    assert _non_gpu_load_mw_at(profile, 100.0) == 0.5
    assert _non_gpu_load_mw_at([], 10.0) is None


def test_tc_isl_46_one_mw_non_gpu_is_additive_and_gpu_fields_unchanged():
    """TC-ISL-46 — a measured CPU profile does not rewrite GPU telemetry."""
    before = _first_tick()
    after = _first_tick([[0.0, 1.0]])
    assert after.p_non_gpu_demand_mw == 1.0
    assert before.p_compute_demand_mw == after.p_compute_demand_mw
    assert before.forecast_mw == after.forecast_mw
    # The first thermal interval has no lagged CPU cooling output.
    assert after.p_demand_mw == pytest.approx(before.p_demand_mw + 1.0)


def test_tc_isl_47_non_gpu_shortfall_is_unserved_and_balance_closes():
    """TC-ISL-47 — D7 treats non-GPU IT load as ordinary demand."""
    tick = _first_tick([[0.0, 1.0]], remove_sources=True)
    assert tick.p_non_gpu_demand_mw == 1.0
    assert tick.p_demand_mw == pytest.approx(1.0)
    assert tick.p_unserved_mw == pytest.approx(1.0)
    assert tick.p_served_mw == pytest.approx(0.0)
    assert tick.physical_balance is not None
    assert tick.physical_balance.passed


def test_tc_isl_48_forecast_point_does_not_receive_profile_as_forecast():
    """TC-ISL-48 — non-GPU profile is measured load, not a forecast input."""
    before = _first_tick()
    after = _first_tick([[0.0, 1.0]])
    assert before.forecast_mw == after.forecast_mw
    # With no workload signal the existing confidence fallback may use the
    # current measured p_demand; it is not future/profile-aware forecasting.


def test_tc_isl_49_unused_field_is_absent_and_hash_is_unchanged():
    """TC-ISL-49 — an unused optional field preserves legacy identity/wire shape."""
    legacy = {"tick_index": 1, "p_demand_mw": 2.0}
    unset = {**legacy, "p_non_gpu_demand_mw": None}
    explicit_zero = {**legacy, "p_non_gpu_demand_mw": 0.0}
    assert physical_tick_json(unset) == physical_tick_json(legacy)
    assert physical_tick_json(explicit_zero) != physical_tick_json(legacy)
    unused_tick = _first_tick()
    active_tick = _first_tick([[0.0, 1.0]])
    assert "p_non_gpu_demand_mw" not in _tick_result_to_dict(unused_tick)
    assert "p_non_gpu_demand_mw" not in json.loads(_tick_to_json(unused_tick))
    assert _tick_result_to_dict(active_tick)["p_non_gpu_demand_mw"] == 1.0
    assert json.loads(_tick_to_json(active_tick))["p_non_gpu_demand_mw"] == 1.0
