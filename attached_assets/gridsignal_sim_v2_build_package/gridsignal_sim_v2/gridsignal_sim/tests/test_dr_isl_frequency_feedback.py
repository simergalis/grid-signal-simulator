"""OPEN-ISL-3 acceptance tests TC-ISL-26–30."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.schemas import ScenarioSpec
from api.routes.runs import get_energy_summary
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.frequency_reporting import (
    frequency_feedback_configured,
    protection_is_configured,
)
from mcp_server.server import StudyService
from runtime.scenario_factory import build_run_context_from_spec
from study_harness.acceptance import compare_metrics
from study_harness.metrics import collect_metrics


def _site(**updates):
    values = {
        "island_mode": True,
        "frequency_nominal_hz": 60.0,
        "ufls_stage1_hz": None,
        "of_trip_hz": None,
        "ufls_stages": [],
        "relay_81u_threshold_hz": None,
        "island_collapse_hz": None,
        "of_warning_hz": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _context(**overrides):
    # PROPOSED_HERE: synthetic, zero-load fixture isolates reporting metadata.
    spec_data = {
        "name": "TC-ISL-26",
        "island_mode": True,
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "pue_base": 1.0,
        "bess_units": [{
            "asset_id": "bess-test",
            "rated_mw": 10.0,
            "usable_mwh": 20.0,
            "initial_soc_fraction": 1.0,
            "grid_forming": True,
        }],
    }
    spec_data.update(overrides)
    spec = ScenarioSpec.model_validate(spec_data)
    return build_run_context_from_spec(
        "tc-isl-frequency-feedback",
        spec.model_dump(mode="json"),
        playback_speed=0.0,
    )


def _metrics(*, feedback, invalid=0, protection=False):
    return {
        "engine_commit": "engine",
        "harness_commit": "harness",
        "constraints_valid": True,
        "hard_violations": [],
        "energy_balance": {"closure_status": True},
        "fuel_reconciled": True,
        "compute_trace_sha256": "same-trace",
        "unserved_mwh": 0.0,
        "peak_unserved_mw": 0.0,
        "frequency_feedback_configured": feedback,
        "protection_configured": protection,
        "invalid_frequency_tick_count": invalid,
        "invalid_frequency_fraction": float(invalid > 0),
    }


def _compare_service(baseline, informed):
    service = object.__new__(StudyService)
    run_records = {
        "baseline": {**baseline, "study_class": "base_demo"},
        "informed": {**informed, "study_class": "base_demo"},
    }
    state = SimpleNamespace(scenario_id="scenario-uneven-multisched-01", ticks_path=None)
    service._record = lambda run_id: (state, run_records[run_id])
    return service


def test_tc_isl_26_unprotected_invalid_ticks_are_informational_and_reported():
    ctx = _context()
    assert ctx.metadata["frequency_feedback_configured"] is False
    ctx.sim_state._frequency_hz = 70.0  # PROPOSED_HERE: invalid-frequency fixture.
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        tick = ctx.step()
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)
    assert tick.frequency_hz > 66.0
    assert tick.frequency_valid is False
    metrics = collect_metrics(
        [tick],
        frequency_feedback_configured=ctx.metadata["frequency_feedback_configured"],
    )
    assert metrics["frequency_feedback_configured"] is False
    assert metrics["protection_configured"] is False
    assert metrics["invalid_frequency_tick_count"] == 1
    assert metrics["invalid_frequency_fraction"] == 1.0
    compared = compare_metrics(_metrics(feedback=False, invalid=1),
                               _metrics(feedback=False, invalid=1))
    assert compared["verdict"] == "PASS"
    assert compared["frequency_inputs"]["baseline_invalid_frequency_fraction"] == 1.0
    print({
        "TC-ISL-26": {
            key: metrics[key] for key in (
                "frequency_feedback_configured", "protection_configured",
                "invalid_frequency_tick_count", "invalid_frequency_fraction",
            )
        },
        "actual_frequency_hz": tick.frequency_hz,
        "validity": compared["verdict"],
    })


def test_tc_isl_27_configured_feedback_with_invalid_ticks_fails_comparison():
    left = _metrics(feedback=True, invalid=1, protection=True)
    right = _metrics(feedback=True, invalid=1, protection=True)
    comparison = compare_metrics(left, right)
    assert comparison["conditions"]["baseline_valid"] is False
    assert comparison["conditions"]["informed_valid"] is False
    assert comparison["verdict"] == "FAIL"
    assert len(comparison["condition_order"]) == 10
    assert set(comparison["condition_inputs"]) == set(comparison["conditions"])
    for condition_inputs in comparison["condition_inputs"].values():
        assert condition_inputs["baseline_frequency_feedback_configured"] is True
        assert condition_inputs["baseline_protection_configured"] is True
        assert condition_inputs["baseline_invalid_frequency_tick_count"] == 1
        assert condition_inputs["baseline_invalid_frequency_fraction"] == 1.0
        assert condition_inputs["informed_frequency_feedback_configured"] is True
        assert condition_inputs["informed_protection_configured"] is True
        assert condition_inputs["informed_invalid_frequency_tick_count"] == 1
        assert condition_inputs["informed_invalid_frequency_fraction"] == 1.0
    service = _compare_service(left, right)
    response = service.compare("baseline", "informed")
    assert response["verdict"] == "FAIL"
    assert all(
        condition["inputs"]["baseline_frequency_feedback_configured"] is True
        and condition["inputs"]["informed_invalid_frequency_tick_count"] == 1
        for condition in response["conditions"]["items"]
    )
    assert response["frequency_inputs"]["baseline_invalid_frequency_tick_count"] == 1
    from study_harness.executor import make_study_run_identity
    identity = make_study_run_identity(
        scenario_id="scenario-uneven-multisched-01",
        mode="baseline",
        spec={"end_sim_time": 7200.0},
        seed=42,
        tick_seconds=5.0,
        engine_commit="5fbf357",
        harness_commit="5fbf357",
    )
    assert identity.payload()["parameter_set"]["frequency_reporting_metrics_version"] == 2
    print({"TC-ISL-27": response["verdict"], "conditions": len(response["conditions"]),
           "inputs": response["frequency_inputs"]})


def test_tc_isl_28_configured_feedback_with_zero_invalid_ticks_is_valid():
    comparison = compare_metrics(
        _metrics(feedback=True, invalid=0, protection=True),
        _metrics(feedback=True, invalid=0, protection=True),
    )
    assert comparison["conditions"]["baseline_valid"] is True
    assert comparison["conditions"]["informed_valid"] is True
    assert comparison["verdict"] == "PASS"
    print({"TC-ISL-28": comparison["verdict"],
           "invalid_count": comparison["frequency_inputs"]["baseline_invalid_frequency_tick_count"]})


def test_tc_isl_29_grid_tied_frequency_is_not_feedback_even_when_protection_is_reported():
    site = _site(island_mode=False, ufls_stage1_hz=59.0,
                 relay_81u_threshold_hz=57.5)
    assert frequency_feedback_configured(site) is False
    assert protection_is_configured(site) is True
    ctx = _context(island_mode=False, ufls_stage1_hz=59.0)
    assert ctx.metadata["frequency_feedback_configured"] is False
    # MCP energy section exposes the same four fields from its persisted record.
    service = object.__new__(StudyService)
    state = SimpleNamespace(scenario_id="scenario-uneven-multisched-01")
    record = {
        "study_class": "base_demo",
        "frequency_feedback_configured": False,
        "protection_configured": True,
        "invalid_frequency_tick_count": 1,
        "invalid_frequency_fraction": 0.25,
        "fuel_by_component_mmbtu": {},
        "turbine_fuel_mmbtu": 0.0,
    }
    service._record = lambda run_id: (state, record)
    mcp_metrics = service.metrics("run", section="energy", page=1, page_size=20)
    assert mcp_metrics["energy"] == {
        "frequency_feedback_configured": False,
        "protection_configured": True,
        "invalid_frequency_tick_count": 1,
        "invalid_frequency_fraction": 0.25,
    }

    completed = SimpleNamespace(
        scenario_name="grid-tied-test",
        tick_dicts=[
            {"frequency_valid": True, "protection_configured": True},
            {"frequency_valid": False, "protection_configured": True},
            {"frequency_valid": True, "protection_configured": True},
            {"frequency_valid": True, "protection_configured": True},
        ],
        frequency_feedback_configured=False,
        protection_configured=True,
        invalid_frequency_tick_count=1,
        invalid_frequency_fraction=0.25,
        turbine_fuel_status="not_modelled",
        turbine_fuel_type=None,
        turbine_fuel_units=None,
        turbine_total_fuel_mmbtu=None,
        turbine_start_count=0,
        turbine_synchronized_headroom_mwh=0.0,
        turbine_minutes_below_low_load_threshold=0.0,
        turbine_fuel_telemetry=[],
        turbine_fuel_parameter_provenance=None,
    )
    manager = SimpleNamespace(get_context=lambda _: None, get_completed=lambda _: completed)
    with patch("api.routes.runs.compute_run_cost_from_completed", return_value=({}, {})):
        rest_metrics = asyncio.run(get_energy_summary("run", manager=manager))
    assert {key: rest_metrics[key] for key in mcp_metrics["energy"]} == mcp_metrics["energy"]
    import json
    from datetime import datetime, timezone
    from api.routes.runs import _load_completed_from_db

    persisted = {
        "overall": "PASS",
        "tick_count": 4,
        "dropped_ticks": 0,
        "gap_count": 0,
        **record,
    }
    row = SimpleNamespace(
        scenario_id="scenario-uneven-multisched-01",
        name="grid-tied-test",
        verdict=json.dumps(persisted),
        completed_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
    )

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, *args, **kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: row)

    with patch("api.db._SessionLocal", lambda: _FakeSession()):
        restored = asyncio.run(_load_completed_from_db("run"))
    assert {
        "frequency_feedback_configured": restored.frequency_feedback_configured,
        "protection_configured": restored.protection_configured,
        "invalid_frequency_tick_count": restored.invalid_frequency_tick_count,
        "invalid_frequency_fraction": restored.invalid_frequency_fraction,
    } == mcp_metrics["energy"]
    print({"TC-ISL-29": {"feedback": False, "protection": True,
                         "MCP": mcp_metrics["energy"], "REST": {
                             key: rest_metrics[key] for key in mcp_metrics["energy"]
                         }, "DB_restore": mcp_metrics["energy"]}})


@pytest.mark.parametrize(("overrides", "module", "path"), [
    ({"ufls_stage1_hz": 59.0}, None, "dispatch_droop_underfrequency"),
    ({"of_trip_hz": 61.0}, None, "dispatch_droop_overfrequency"),
    ({"ufls_stages": [{"threshold_hz": 58.0, "delay_s": 0.1,
                       "block_fraction": 0.1}]}, None, "ufls"),
    ({"relay_81u_threshold_hz": 57.5}, None, "81u"),
    ({"island_collapse_hz": 57.0}, None, "island_collapse"),
    ({"of_warning_hz": 61.0, "of_trip_hz": 62.0}, None,
     "renewable_overfrequency_curtailment"),
    ({}, SimpleNamespace(arrays=[SimpleNamespace(
        config=SimpleNamespace(ieee_1547_category=3), blocks=[object()]
    )]), "fuel_cell_ride_through"),
])
def test_tc_isl_30_each_frequency_feedback_path_triggers(overrides, module, path):
    # PROPOSED_HERE: thresholds/categories here are synthetic path-isolation fixtures.
    assert frequency_feedback_configured(_site(**overrides), module) is True
    print({"TC-ISL-30": path, "frequency_feedback_configured": True})


def test_tc_isl_30_disabled_81u_threshold_does_not_trigger_feedback():
    # PROPOSED_HERE: nominal + 0.1 Hz exercises the existing disabled-relay guard.
    site = _site(relay_81u_threshold_hz=60.1)
    assert frequency_feedback_configured(site) is False
