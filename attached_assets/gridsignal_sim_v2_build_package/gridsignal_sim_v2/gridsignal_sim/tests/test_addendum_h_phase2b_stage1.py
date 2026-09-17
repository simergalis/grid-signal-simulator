"""Addendum H Phase 2b-1 registration and evidence checks.

TC numbering continues from Addendum H Phase 2a at TC-137.
"""

from __future__ import annotations

import json
import pytest
from types import SimpleNamespace
from pathlib import Path

from api.schemas import ScenarioSpec
from runtime.phase2b_reference import expand_phase2b_reference_spec


ROOT = Path(__file__).parents[1]
RESULTS = ROOT.parents[3] / "docs" / "addendum-h-phase2b-results"
SCENARIOS = ROOT / "config" / "scenarios"


def _expanded(scenario_id: str) -> dict:
    raw = json.loads((SCENARIOS / f"{scenario_id}.json").read_text())
    ScenarioSpec.model_validate(raw)
    return expand_phase2b_reference_spec(raw)


def test_tc137_phase2b_reference_registration_and_topology() -> None:
    for scenario_id, family, days in (
        ("scenario-h1-k8s-ray-24h", "h1", 1),
        ("scenario-h1-k8s-ray-7d", "h1", 7),
        ("scenario-h2-slurm-24h", "h2", 1),
        ("scenario-h2-slurm-7d", "h2", 7),
    ):
        spec = _expanded(scenario_id)
        assert spec["end_sim_time"] == days * 86400.0
        assert sum(
            turbine.get("initial_state", "offline") == "spinning"
            for turbine in spec["turbine_units"]
        ) == 2
        assert len(spec["turbine_units"]) == 4
        assert len(spec["bess_units"]) == 1
        assert spec["bess_units"][0]["rated_mw"] == 30.0
        schedulers = {cluster["scheduler_type"] for cluster in spec["kube_clusters"]}
        assert schedulers == ({"K8S", "RAY"} if family == "h1" else {"SLURM"})
        assert ("slurm_config" in spec) is (family == "h2")


def test_tc138_cluster_timing_and_unique_ids() -> None:
    for scenario_id, family in (
        ("scenario-h1-k8s-ray-24h", "h1"),
        ("scenario-h1-k8s-ray-7d", "h1"),
        ("scenario-h2-slurm-24h", "h2"),
        ("scenario-h2-slurm-7d", "h2"),
    ):
        spec = _expanded(scenario_id)
        events = spec["workload_events"]
        assert len({event["event_id"] for event in events}) == len(events)
        starts = sorted(
            event["timestamp"]
            for event in events
            if event["event_type"] == "starting"
        )
        assert starts
        if family == "h1":
            expected_local_starts = {
                hour * 3600.0 + phase
                for hour in (8, 10, 12, 14, 16, 18)
                for phase in (30.0, 920.0, 1850.0, 2700.0)
            }
            assert all(
                (timestamp % 86400.0) in expected_local_starts
                for timestamp in starts
            )
        else:
            expected_local_starts = {
                hour * 3600.0 + 310.0
                for hour in (8, 10, 12, 14, 16, 18)
            }
            assert all(
                (timestamp % 86400.0) in expected_local_starts
                for timestamp in starts
            )
        if family == "h2":
            jobs = spec["slurm_config"]["jobs"]
            assert len({job["job_id"] for job in jobs}) == len(jobs)


def test_tc139_replayed_compute_trace_is_identical_tick_by_tick() -> None:
    manifest = json.loads((RESULTS / "stage1_summary.json").read_text())
    assert len(manifest["scenarios"]) == 2
    for scenario in manifest["scenarios"]:
        assert scenario["identical_compute_trace"] is True
        assert scenario["max_compute_trace_diff_mw"] <= 1e-9
        for run in scenario["runs"].values():
            assert run["compute_description"] == "scheduler-shaped GPU workload demand"


def test_tc140_24h_energy_balance_closes() -> None:
    manifest = json.loads((RESULTS / "stage1_summary.json").read_text())
    for scenario in manifest["scenarios"]:
        for run in scenario["runs"].values():
            assert run["energy_balance"]["closure_status"] is True
            # D4 is retained as a separate routing diagnostic.  Energy closure
            # uses the authoritative physical supply/load ledger.
            assert (
                run["energy_balance"]["max_abs_physical_ledger_defect_mw"]
                <= 1e-3
            )


def test_tc141_24h_start_stop_reconciliation() -> None:
    manifest = json.loads((RESULTS / "stage1_summary.json").read_text())
    for scenario in manifest["scenarios"]:
        for run in scenario["runs"].values():
            assert run["start_count_reconciled"] is True
            assert run["constraints_valid"] is True


def test_tc142_phase2b_expansion_attaches_aeroderivative_fuel_to_all_four_units() -> None:
    """IMPL-H58: expansion changes only copied Phase 2b fleet metadata."""
    base = json.loads(
        (SCENARIOS / "scenario-uneven-multisched-01.json").read_text()
    )
    assert all("gt_mode" not in turbine for turbine in base["turbine_units"])
    for scenario_id in (
        "scenario-h1-k8s-ray-24h",
        "scenario-h1-k8s-ray-7d",
        "scenario-h2-slurm-24h",
        "scenario-h2-slurm-7d",
    ):
        expanded = _expanded(scenario_id)
        assert [turbine["gt_mode"] for turbine in expanded["turbine_units"]] == [
            "aero",
            "aero",
            "aero",
            "aero",
        ]


def test_tc143_short_phase2b_run_has_nonzero_turbine_fuel() -> None:
    """IMPL-H58: a synchronized short run cannot silently report zero fuel."""
    from runtime.scenario_factory import build_run_context_from_spec
    from scripts.run_phase2b_stage1 import _phase2b_fuel_guard

    spec = _expanded("scenario-h1-k8s-ray-24h")
    spec["end_sim_time"] = 60.0
    spec["workload_events"] = []
    spec.pop("kube_clusters", None)
    spec.pop("slurm_config", None)
    spec["turbine_commitment_mode"] = "baseline"
    ctx = build_run_context_from_spec("tc143-phase2b-fuel", spec)
    ticks = [ctx.step() for _ in range(12)]

    guard = _phase2b_fuel_guard("tc143", ctx, ticks)
    assert guard["guard_status"] == "PASS"
    total_fuel = sum(
        float(row.get("total_fuel_mmbtu", 0.0) or 0.0)
        for row in ticks[-1].turbine_fuel_telemetry
        if row.get("fuel_modelled")
    )
    assert total_fuel > 0.0


def test_tc144_zero_phase2b_fuel_fails_loudly() -> None:
    from scripts.run_phase2b_stage1 import _phase2b_fuel_guard

    turbine = SimpleNamespace(
        is_on_bus=True,
        fuel_modelled=True,
        config=SimpleNamespace(asset_id="turbine-0"),
    )
    ctx = SimpleNamespace(sim_state=SimpleNamespace(turbines=[turbine]))
    ticks = [
        SimpleNamespace(
            turbine_fuel_telemetry=[
                {
                    "asset_id": "turbine-0",
                    "fuel_modelled": True,
                    "total_fuel_mmbtu": 0.0,
                }
            ]
        )
    ]
    with pytest.raises(AssertionError, match="zero fuel telemetry"):
        _phase2b_fuel_guard("tc144", ctx, ticks)


def test_tc145_phase2b_acceptance_comparison_fails_when_informed_is_worse() -> None:
    """IMPL-H59: informed unserved energy and peak must be no worse."""
    from scripts.run_phase2b_stage1 import _phase2b_acceptance_verdict

    common = {
        "energy_balance": {"closure_status": True},
        "hard_violations": [],
        "start_count_reconciled": True,
        "constraints_valid": True,
    }
    baseline = {"unserved_mwh": 1.0, "peak_unserved_mw": 2.0}
    informed = {"unserved_mwh": 1.1, "peak_unserved_mw": 2.0}
    result = _phase2b_acceptance_verdict(
        summary=common,
        baseline=baseline,
        informed=informed,
        trace_equal=True,
    )
    assert result["acceptance_verdict"] == "FAIL"
    assert result["informed_vs_baseline"]["unserved_energy_no_worse"] is False


def test_tc146_phase2b_acceptance_comparison_passes_when_informed_is_equal() -> None:
    from scripts.run_phase2b_stage1 import _phase2b_acceptance_verdict

    common = {
        "energy_balance": {"closure_status": True},
        "hard_violations": [],
        "start_count_reconciled": True,
        "constraints_valid": True,
    }
    equal = {"unserved_mwh": 1.0, "peak_unserved_mw": 2.0}
    result = _phase2b_acceptance_verdict(
        summary=common,
        baseline=equal,
        informed=equal,
        trace_equal=True,
    )
    assert result["acceptance_verdict"] == "PASS"


def _stop_floor_context() -> object:
    from runtime.scenario_factory import build_run_context_from_spec

    spec = json.loads(
        (SCENARIOS / "scenario-uneven-multisched-01.json").read_text()
    )
    spec["end_sim_time"] = 60.0
    spec["workload_events"] = []
    spec.pop("kube_clusters", None)
    spec.pop("slurm_config", None)
    spec["turbine_commitment_mode"] = "informed"
    return build_run_context_from_spec("tc146-stop-floor", spec)


def test_tc147_stop_refuses_when_post_stop_core_n_minus_one_floor_breaches() -> None:
    """IMPL-H60: stop refusal uses core demand + largest-unit reserve floor."""
    from runtime.turbine_commitment import CommitmentForecast

    ctx = _stop_floor_context()
    controller = ctx.turbine_commitment_controller
    controller.forecast = lambda **_: CommitmentForecast(
        sim_time_s=0.0,
        background_mean_mw=10.0,
        background_std_mw=0.0,
        forecast_mw=10.0,
        peak_forecast_mw=10.0,
        minimum_forecast_mw=10.0,
        profile=((0.0, 10.0), (600.0, 10.0)),
    )
    controller.evaluate(ctx=ctx, power_for_event=ctx._event_power_mw)

    assert controller.log
    assert controller.log[-1].accepted is False
    assert "post-stop N-1 reserve floor" in (controller.log[-1].refusal_reason or "")
    details = controller.stop_floor_refusals[-1]
    assert details["post_stop_floor_mw"] == 35.0
    assert details["remaining_turbine_capacity_mw"] == 25.0
    assert details["bess_included_in_floor"] is False


def test_tc148_stop_remains_allowed_when_post_stop_core_floor_is_satisfied() -> None:
    from runtime.turbine_commitment import CommitmentForecast

    ctx = _stop_floor_context()
    for turbine in ctx.sim_state.turbines:
        turbine.config.min_run_enabled = False
    controller = ctx.turbine_commitment_controller
    controller.forecast = lambda **_: CommitmentForecast(
        sim_time_s=0.0,
        background_mean_mw=0.0,
        background_std_mw=0.0,
        forecast_mw=0.0,
        peak_forecast_mw=0.0,
        minimum_forecast_mw=0.0,
        profile=((0.0, 0.0), (600.0, 0.0)),
    )
    controller.evaluate(ctx=ctx, power_for_event=ctx._event_power_mw)

    assert not controller.stop_floor_refusals
    assert not [record for record in controller.log if not record.accepted]


def test_tc149_reserve_floor_refusal_dedup_keeps_numeric_payload() -> None:
    """IMPL-H65: stable reserve-floor refusals compact without losing evidence."""
    from runtime.turbine_commitment import ForecastDrivenTurbineController

    controller = ForecastDrivenTurbineController(mode="informed")
    base = {
        "unit_id": "gt-hot-01",
        "action": "stop",
        "requested_action": "stop",
        "source": "forecast_commitment",
        "reason": "",
    }
    refusal_one = (
        "stop refused: post-stop N-1 reserve floor 35.000 MW exceeds "
        "remaining turbine capacity 25.000 MW by 10.000 MW at forecast "
        "600s within 1200s; unit is needed within the stop look-ahead"
    )
    refusal_two = (
        "stop refused: post-stop N-1 reserve floor 36.000 MW exceeds "
        "remaining turbine capacity 25.000 MW by 11.000 MW at forecast "
        "605s within 1200s; unit is needed within the stop look-ahead"
    )
    controller.command_result(
        {**base, "sim_time_s": 0.0, "reason": refusal_one},
        accepted=False,
        refusal_reason=refusal_one,
    )
    controller.command_result(
        {**base, "sim_time_s": 5.0, "reason": refusal_one},
        accepted=False,
        refusal_reason=refusal_one,
    )
    controller.command_result(
        {**base, "sim_time_s": 10.0, "reason": refusal_two},
        accepted=False,
        refusal_reason=refusal_two,
    )
    different_reason = "stop refused: forecast burst arrives before restart window"
    controller.command_result(
        {**base, "sim_time_s": 15.0, "reason": different_reason},
        accepted=False,
        refusal_reason=different_reason,
    )

    assert len(controller.log) == 2
    assert controller.log[0].refusal_reason == refusal_one
    assert controller.log[0].suppressed_repeat_count == 2
    assert controller.log[1].refusal_reason == different_reason
    assert controller.suppressed_refusal_count == 2