"""D6a-X additive measured non-GPU load tests (TC-ISL-44 through 51)."""

from __future__ import annotations

import json
import copy
import math
import random
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from api.schemas import ScenarioSpec
from core.models import NON_GPU_COOLING_JOB_ID
from core.physical_identity import physical_tick_json
from core.simulation_core import _non_gpu_load_mw_at
from runtime.persistence import _tick_to_json
from runtime.run_manager import TICK_INTERVAL_SIM_SECONDS, _tick_result_to_dict
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


def test_tc_isl_50_cpu_profile_samples_are_isolated_from_gpu_envelopes():
    """TC-ISL-50 — CPU zero/back transitions update/end only their own envelope."""
    cooling = build_run_context_from_spec(
        "tc-isl-d6ax2-envelope",
        _spec([[0.0, 1.0], [5.0, 0.0], [10.0, 2.0], [15.0, 0.0]]),
        playback_speed=0.0,
        run_seed=42,
        execution_mode="headless",
    ).sim_state.cooling
    cooling.register_job_start("gpu-existing", 0.0)
    cooling.record_job_compute(
        0.0, {"gpu-existing": 2.0, NON_GPU_COOLING_JOB_ID: 1.0}
    )

    # A GPU job starts on the same tick that the CPU draw steps down.
    cooling.register_job_start("gpu-starting", 5.0)
    cooling.record_job_compute(
        5.0,
        {
            "gpu-existing": 2.0,
            "gpu-starting": 0.75,
            NON_GPU_COOLING_JOB_ID: 0.0,
        },
    )
    cooling.record_job_compute(
        10.0,
        {
            "gpu-existing": 2.0,
            "gpu-starting": 0.75,
            NON_GPU_COOLING_JOB_ID: 2.0,
        },
    )
    cooling.record_job_compute(
        15.0,
        {
            "gpu-existing": 2.0,
            "gpu-starting": 0.75,
            NON_GPU_COOLING_JOB_ID: 0.0,
        },
    )
    cooling.record_job_compute(
        20.0,
        {
            "gpu-existing": 2.0,
            "gpu-starting": 0.75,
            NON_GPU_COOLING_JOB_ID: 1.5,
        },
    )
    cooling.record_job_compute(
        25.0,
        {
            "gpu-existing": 2.0,
            "gpu-starting": 0.75,
            NON_GPU_COOLING_JOB_ID: 0.0,
        },
    )
    cooling.register_job_end(NON_GPU_COOLING_JOB_ID, 25.0)

    assert list(cooling._envelopes["gpu-existing"].history) == [
        (0.0, 2.0),
        (5.0, 2.0),
        (10.0, 2.0),
        (15.0, 2.0),
        (20.0, 2.0),
        (25.0, 2.0),
    ]
    assert list(cooling._envelopes["gpu-starting"].history) == [
        (5.0, 0.75),
        (10.0, 0.75),
        (15.0, 0.75),
        (20.0, 0.75),
        (25.0, 0.75),
    ]
    assert cooling._envelopes["gpu-starting"].end_t is None
    assert cooling._envelopes["gpu-existing"].end_t is None
    assert list(cooling._envelopes[NON_GPU_COOLING_JOB_ID].history) == [
        (0.0, 1.0),
        (5.0, 0.0),
        (10.0, 2.0),
        (15.0, 0.0),
        (20.0, 1.5),
        (25.0, 0.0),
    ]
    assert cooling._envelopes[NON_GPU_COOLING_JOB_ID].end_t == 25.0


# PROPOSED_HERE for D6a-X2: 1e-6 MWh (1 Wh) is above accumulated floating-point
# noise while remaining negligible beside the measured CPU/cooling energies.
_D6AX2_ADDITIVITY_TOLERANCE_MWH = 1e-6


def _pin_null_seeds(value, seed):
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if key in {"seed", "rng_seed"} and child is None:
                value[key] = seed
            else:
                _pin_null_seeds(child, seed)
        if isinstance(value.get("kube_config"), dict):
            value["kube_config"]["rng_seed"] = seed
        for key, seed_key in (
            ("cluster_gen_config", "rng_seed"),
            ("stressor_gen_config", "rng_seed"),
            ("param_sampling_config", "seed"),
            ("telemetry_corruption_config", "seed"),
        ):
            if isinstance(value.get(key), dict) and value[key].get(seed_key) is None:
                value[key][seed_key] = seed
    elif isinstance(value, list):
        for child in value:
            _pin_null_seeds(child, seed)


def _envelope_cooling_mw(cooling, envelope, evaluation_time):
    site = cooling.site
    if evaluation_time < envelope.onset_t + site.dt_thermal_seconds:
        return 0.0
    elapsed = evaluation_time - envelope.onset_t - site.dt_thermal_seconds
    alpha = site.alpha_max * (1.0 - math.exp(-elapsed / site.tau_seconds))
    return alpha * cooling._lagged_mw(
        copy.copy(envelope), evaluation_time - site.dt_thermal_seconds
    )


def _run_s10_full_profile(spec_path, *, seed=1729):
    spec = ScenarioSpec.model_validate_json(spec_path.read_bytes()).model_dump(
        mode="json"
    )
    _pin_null_seeds(spec, seed)
    random.seed(seed)
    np.random.seed(seed)
    with patch("time.time", return_value=1792454400.0):
        ctx = build_run_context_from_spec(
            "tc-isl-d6ax2-s10",
            spec,
            playback_speed=0.0,
            run_seed=seed,
            execution_mode="headless",
        )
        ticks = []
        cpu_cooling_mwh = 0.0
        non_cpu_cooling_mwh = 0.0
        non_cpu_cooling_series_mw = []
        while ctx.sim_time < ctx.end_sim_time:
            tick = ctx.step()
            ticks.append(tick)
            evaluation_time = tick.sim_time_seconds - TICK_INTERVAL_SIM_SECONDS
            cooling = ctx.sim_state.cooling
            cpu_env = cooling._envelopes.get(NON_GPU_COOLING_JOB_ID)
            if cpu_env is not None:
                cpu_cooling_mw = _envelope_cooling_mw(
                    cooling, cpu_env, evaluation_time
                )
                cpu_cooling_mwh += (
                    cpu_cooling_mw * TICK_INTERVAL_SIM_SECONDS / 3600.0
                )
            non_cpu_mw = sum(
                _envelope_cooling_mw(cooling, env, evaluation_time)
                for key, env in cooling._envelopes.items()
                if key != NON_GPU_COOLING_JOB_ID
            )
            non_cpu_cooling_series_mw.append(non_cpu_mw)
            non_cpu_cooling_mwh += (
                non_cpu_mw * TICK_INTERVAL_SIM_SECONDS / 3600.0
            )
        return {
            "ticks": ticks,
            "cpu_cooling_mwh": cpu_cooling_mwh,
            "non_cpu_cooling_mwh": non_cpu_cooling_mwh,
            "non_cpu_cooling_mw": non_cpu_cooling_series_mw,
        }


def test_tc_isl_51_s10_cpu_profile_is_full_scale_additive():
    """TC-ISL-51 — full S10 CPU profile preserves GPU heat and adds demand."""
    package = Path(__file__).resolve().parents[1]
    workspace = Path(__file__).resolve().parents[5]
    current_path = (
        package / "config" / "scenarios" / "S10_mit_supercloud_2021-08-11.json"
    )
    candidate_path = (
        workspace / "tools" / "dr_isl" / "d6" / "S10_2021-08-11_cpu_candidate.json"
    )
    current = _run_s10_full_profile(current_path)
    candidate = _run_s10_full_profile(candidate_path)
    current_ticks = current["ticks"]
    candidate_ticks = candidate["ticks"]
    assert len(current_ticks) == len(candidate_ticks) == 17280

    current_gpu_mwh = sum(
        tick.p_compute_demand_mw * TICK_INTERVAL_SIM_SECONDS / 3600.0
        for tick in current_ticks
    )
    candidate_gpu_mwh = sum(
        tick.p_compute_demand_mw * TICK_INTERVAL_SIM_SECONDS / 3600.0
        for tick in candidate_ticks
    )
    assert candidate_gpu_mwh == pytest.approx(current_gpu_mwh, abs=1e-12)

    # In the base S10 there is no floor envelope: all existing envelopes are
    # GPU job envelopes. Subtracting the candidate's dedicated CPU envelope
    # contribution yields the GPU-attributable cooling trajectory.
    assert current["non_cpu_cooling_mwh"] == pytest.approx(
        sum(
            tick.p_cooling_demand_mw * TICK_INTERVAL_SIM_SECONDS / 3600.0
            for tick in current_ticks
        ),
        abs=_D6AX2_ADDITIVITY_TOLERANCE_MWH,
    )
    max_gpu_cooling_difference_mw = max(
        abs(candidate["non_cpu_cooling_mw"][index] - tick.p_cooling_demand_mw)
        for index, tick in enumerate(current_ticks)
    )
    assert candidate["non_cpu_cooling_mwh"] == pytest.approx(
        current["non_cpu_cooling_mwh"],
        abs=_D6AX2_ADDITIVITY_TOLERANCE_MWH,
    )
    assert max_gpu_cooling_difference_mw <= 1e-9

    current_demand_mwh = sum(
        tick.p_demand_mw * TICK_INTERVAL_SIM_SECONDS / 3600.0
        for tick in current_ticks
    )
    candidate_demand_mwh = sum(
        tick.p_demand_mw * TICK_INTERVAL_SIM_SECONDS / 3600.0
        for tick in candidate_ticks
    )
    cpu_it_mwh = sum(
        float(tick.p_non_gpu_demand_mw or 0.0)
        * TICK_INTERVAL_SIM_SECONDS
        / 3600.0
        for tick in candidate_ticks
    )
    demand_increase_mwh = candidate_demand_mwh - current_demand_mwh
    expected_increase_mwh = cpu_it_mwh + candidate["cpu_cooling_mwh"]
    assert demand_increase_mwh == pytest.approx(
        expected_increase_mwh, abs=_D6AX2_ADDITIVITY_TOLERANCE_MWH
    )
