"""Addendum H Phase 2b-1 registration and evidence checks.

TC numbering continues from Addendum H Phase 2a at TC-137.
"""

from __future__ import annotations

import json
import copy
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
    """IMPL-H60: core-proposed stop refusal uses the N-1 reserve floor.

    IMPL-ISL-30 §3 disables forecast-origin stops; exercise the surviving
    core-decommit adjudication path directly.
    """
    from runtime.turbine_commitment import CommitmentForecast

    ctx = _stop_floor_context()
    controller = ctx.turbine_commitment_controller
    forecast = CommitmentForecast(
        sim_time_s=0.0,
        background_mean_mw=10.0,
        background_std_mw=0.0,
        forecast_mw=10.0,
        peak_forecast_mw=10.0,
        minimum_forecast_mw=10.0,
        profile=((0.0, 10.0), (600.0, 10.0)),
    )
    ctx.sim_state._commitment_forecast = forecast
    accepted = controller.adjudicate_core_proposal(
        state=ctx.sim_state,
        decision=SimpleNamespace(
            action="decommit",
            target_unit_id="gt-spin-01",
            reason="core unload",
            floor_violated=False,
        ),
        sim_time_s=0.0,
        synchronized_capacity_mw=50.0,
        bess_soc_fraction=0.0,
    )

    assert accepted is False
    assert controller.log[-1].accepted is False
    assert controller.log[-1].source == "core_commitment_proposal"
    assert "post-stop N-1 reserve floor" in (controller.log[-1].refusal_reason or "")
    assert controller.log[-1].evidence is not None
    assert controller.log[-1].evidence["post_stop_floor_mw"] == 35.0
    assert controller.log[-1].evidence["remaining_turbine_capacity_mw"] == 25.0
    assert controller.log[-1].evidence["triggering_announced_jobs"] == []
    assert (
        controller.log[-1].evidence["required_capacity_comparison"][
            "reserve_deficit_mw"
        ]
        == 10.0
    )
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


def test_tc150_replay_unserved_energy_uses_each_run_supply() -> None:
    """A supply-starved informed fixture must diverge from the baseline run."""
    from runtime.scenario_factory import build_run_context_from_spec
    from runtime.turbine_commitment import summarize_unserved_ticks

    base = _expanded("scenario-h1-k8s-ray-24h")
    replay = [(45.0, 15.0)] * 12
    results = {}
    for mode, spinning_count in (("baseline", 2), ("informed", 0)):
        spec = copy.deepcopy(base)
        spec.update(
            {
                "end_sim_time": 60.0,
                "workload_events": [],
                "initial_spinning_count": spinning_count,
                "island_mode": True,
                "turbine_commitment_mode": mode,
            }
        )
        spec.pop("kube_clusters", None)
        spec.pop("slurm_config", None)
        for index, turbine in enumerate(spec["turbine_units"]):
            turbine.update(
                {
                    "initial_state": (
                        "spinning" if index < spinning_count else "offline"
                    ),
                    "hot_standby": False,
                    "min_run_enabled": False,
                    "min_down_enabled": False,
                }
            )
        ctx = build_run_context_from_spec(f"tc150-{mode}", spec, playback_speed=0.0)
        ctx.sim_state.demand_replay_trace = replay
        ticks = [ctx.step() for _ in replay]
        results[mode] = summarize_unserved_ticks(ticks)

    assert results["baseline"]["unserved_energy_mwh"] == pytest.approx(
        0.041666667
    )
    assert results["informed"]["unserved_energy_mwh"] == pytest.approx(
        0.516666667
    )
    assert (
        results["informed"]["unserved_energy_mwh"]
        > results["baseline"]["unserved_energy_mwh"]
    )


def test_tc151_attributable_curtailment_fuel_stays_within_curve_range() -> None:
    """Attributable fuel per curtailed MWh must use the fuel curve range."""
    from core.models import AERODERIVATIVE_FUEL_PARAMETERS
    from scripts.run_phase2a_smoke import _extended_metrics

    turbine = SimpleNamespace(
        config=SimpleNamespace(
            asset_id="gt-01",
            rated_mw=25.0,
            fuel=AERODERIVATIVE_FUEL_PARAMETERS,
        )
    )
    tick = SimpleNamespace(
        p_dispatch_curtailed_mw=10.0,
        turbine_units=[
            {
                "asset_id": "gt-01",
                "breaker_closed": True,
                "state": "synchronised",
                "output_mw": 12.5,
                "rated_mw": 25.0,
            }
        ],
        turbine_fuel_telemetry=[],
        sim_time_seconds=5.0,
    )
    controller = SimpleNamespace(
        preload_fuel_mmbtu=0.0,
        suppressed_preload_repeat_count=0,
        unserved_intervals=[],
        forecast_miss_count=0,
        forecast_miss_peak_mw=0.0,
    )
    metrics = _extended_metrics([tick], controller, [], [], [turbine])
    curtailed_mwh = 10.0 * 5.0 / 3600.0
    fuel_per_mwh = (
        metrics["dispatch_curtailment_attributable_fuel_mmbtu"]
        / curtailed_mwh
    )
    curve_rates = [
        rate / 1000.0
        for _, rate in AERODERIVATIVE_FUEL_PARAMETERS.part_load_heat_rate_btu_per_kwh
    ]
    assert min(curve_rates) <= fuel_per_mwh <= max(curve_rates)


# PROPOSED_HERE: These locally captured hashes anchor pre-Phase-1 H expansions;
# they are regression evidence, not vendor-sourced constants.
# DR-2026-10-20-ISLAND-COLLAPSE D9c: timing-only refresh; tools/dr_isl/H_IDENTITY_MAP_D9c.md.
H_EXPANSION_SHA256_BASELINE = {
    "scenario-h1-k8s-ray-24h": (
        "327835d3b1305e731c4397a19a772a877458ec4954b3406474f38f4e1ba0b050"
    ),
    "scenario-h1-k8s-ray-7d": (
        "d8472fe04f6d2fe7be231e103b76bc70bb6798feabdc8ca7d3846200dc074c2a"
    ),
    "scenario-h2-slurm-24h": (
        "b20b073ccb60e1167601175ac3da8a25615398f1847fadeadc59b269d2a55bcb"
    ),
    "scenario-h2-slurm-7d": (
        "46100ac7301ee7f375c5e4b510ce76242a306a09d69f4a81802f31a9982088bb"
    ),
}


def test_tc156_phase1_h_expansions_match_prechange_hashes(
    tmp_path: Path,
) -> None:
    """Phase 1 refactoring must leave every H expansion byte-identical."""
    import hashlib

    from study_harness.executor import (
        STUDY_CLASS_ADDENDUM_H,
        StudyRunExecutor,
    )

    executor = StudyRunExecutor(output_dir=tmp_path / "h-expansions")
    for scenario_id, expected_hash in H_EXPANSION_SHA256_BASELINE.items():
        expanded = executor._expanded_spec(scenario_id, None, None)
        canonical = json.dumps(
            expanded,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        assert hashlib.sha256(canonical).hexdigest() == expected_hash
        assert (
            executor._study_class_for_scenario(scenario_id)
            == STUDY_CLASS_ADDENDUM_H
        )


def test_tc157_base_demo_loader_only_adds_study_fuel_overlay(
    tmp_path: Path,
) -> None:
    from study_harness.executor import (
        BASE_DEMO_SCENARIO_ID,
        STUDY_CLASS_BASE_DEMO,
        StudyRunExecutor,
    )

    base_path = SCENARIOS / f"{BASE_DEMO_SCENARIO_ID}.json"
    on_disk = json.loads(base_path.read_text())
    # D8 supersedes DR-2026-09-24-BASE-STUDY Phase 1.2 raw loading.
    from api.schemas import ScenarioSpec
    expected = ScenarioSpec.model_validate_json(base_path.read_bytes()).model_dump(mode="json")
    # PROPOSED_HERE: Assert the harness-only overlay already used by Phase 2b.
    for turbine in expected.get("turbine_units", []):
        turbine["gt_mode"] = "aero"

    executor = StudyRunExecutor(output_dir=tmp_path / "base-loader")
    loaded = executor._expanded_spec(BASE_DEMO_SCENARIO_ID, None, None)
    assert loaded.pop("study_input_provenance")["canonicalised"] is True
    assert loaded == expected
    assert executor._study_class_for_scenario(BASE_DEMO_SCENARIO_ID) == (
        STUDY_CLASS_BASE_DEMO
    )
    assert all("gt_mode" not in turbine for turbine in on_disk["turbine_units"])


def test_tc158_unsupported_scenario_has_typed_error_and_supported_ids(
    tmp_path: Path,
) -> None:
    from study_harness import UnsupportedScenarioError
    from study_harness.executor import (
        BASE_DEMO_SCENARIO_ID,
        StudyRunExecutor,
    )
    from scripts.run_phase2b_stage1 import REFERENCE_IDS

    executor = StudyRunExecutor(output_dir=tmp_path / "unsupported")
    unsupported_id = "scenario-not-supported-by-study-harness"
    with pytest.raises(UnsupportedScenarioError) as raised:
        executor._expanded_spec(unsupported_id, None, None)

    message = str(raised.value)
    assert unsupported_id in message
    for scenario_id in sorted([*REFERENCE_IDS, BASE_DEMO_SCENARIO_ID]):
        assert scenario_id in message
    assert raised.value.scenario_id == unsupported_id


def test_tc159_base_demo_baseline_run_reconciles_full_day(
    tmp_path: Path,
) -> None:
    from study_harness.executor import (
        BASE_DEMO_SCENARIO_ID,
        STUDY_CLASS_BASE_DEMO,
        StudyRunExecutor,
    )

    executor = StudyRunExecutor(output_dir=tmp_path / "base-baseline")
    record = executor.run_mode(
        scenario_id=BASE_DEMO_SCENARIO_ID,
        mode="baseline",
        reuse_cache=False,
    )

    assert record["status"] == "PASS"
    assert record["study_class"] == STUDY_CLASS_BASE_DEMO
    assert (
        record["identity"]["parameter_set"]["study_class"]
        == STUDY_CLASS_BASE_DEMO
    )
    assert record["fuel_reconciled"] is True
    assert record["start_fuel_reconciliation"]["passed"] is True
    assert record["energy_balance"]["closure_status"] is True
    assert record["turbine_fuel_mmbtu"] > 0.0
    assert len(record["daily_breakdown"]) == 1
    assert record["tick_count"] == 1440
    assert record["compute_trace_count"] == 1440
    assert (
        record["measured_start_event_count"]
        == record["start_fuel_reconciliation"]["measured_event_count"]
    )