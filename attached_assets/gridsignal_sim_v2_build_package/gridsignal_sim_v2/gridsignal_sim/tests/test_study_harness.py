from __future__ import annotations

import json
from pathlib import Path

import pytest

from study_harness.acceptance import AcceptanceCondition, compare_metrics
from study_harness.artifacts import ArtifactWriter
from study_harness.errors import (
    BuildParityMismatchError,
    FuelComponentReconciliationError,
    StartFuelReconciliationError,
)
from study_harness.manifest import RunManifestCache, make_run_identity
from study_harness.metrics import collect_metrics


def _row(
    *,
    total: float,
    start_fuel: float = 0.0,
    no_load_fuel: float = 0.0,
    start_count: int = 0,
    fuel_this_tick: float = 0.0,
) -> dict:
    return {
        "asset_id": "gt-01",
        "fuel_modelled": True,
        "load_fuel_mmbtu": total - start_fuel - no_load_fuel,
        "no_load_fuel_mmbtu": no_load_fuel,
        "hot_standby_fuel_mmbtu": 0.0,
        "start_fuel_mmbtu": start_fuel,
        "total_fuel_mmbtu": total,
        "start_count": start_count,
        "fuel_mmbtu_this_tick": fuel_this_tick,
    }


def _tick(
    time_s: float,
    row: dict,
    *,
    unserved: float = 0.0,
    curtailed: float = 0.0,
    output: float = 10.0,
    forecast: float | None = None,
) -> dict:
    result = {
        "sim_time_seconds": time_s,
        "p_compute_demand_mw": 10.0,
        "p_total_mw": 10.0,
        "p_generation_mw": 10.0 - unserved,
        "p_served_mw": 10.0 - unserved,
        "p_unserved_mw": unserved,
        "p_imbalance_mw": 0.0,
        "p_dispatch_curtailed_mw": curtailed,
        "bess_soc_fraction": 0.8,
        "turbine_fuel_telemetry": [row],
        "turbine_units": [
            {
                "asset_id": "gt-01",
                "state": "synchronised",
                "breaker_closed": True,
                "output_mw": output,
                "rated_mw": 25.0,
            }
        ],
    }
    if forecast is not None:
        result["forecast_mw"] = forecast
    return result


def _record(
    *,
    start_events: list[dict] | None = None,
    total: float = 10.0,
    start_fuel: float = 0.0,
) -> dict:
    return {
        "scenario_id": "test",
        "mode": "baseline",
        "engine_commit": "engine",
        "harness_commit": "harness",
        "turbine_fuel_mmbtu": total,
        "fuel_by_component_mmbtu": {
            "load_fuel_mmbtu": total - start_fuel,
            "no_load_fuel_mmbtu": 0.0,
            "hot_standby_fuel_mmbtu": 0.0,
            "start_fuel_mmbtu": start_fuel,
        },
        "starts": start_events or [],
    }


def test_metric_reconciliation_and_start_fuel_tier_arithmetic() -> None:
    ticks = [
        _tick(5.0, _row(total=4.0, start_fuel=8.0, start_count=1, fuel_this_tick=4.0)),
        _tick(10.0, _row(total=10.0, start_fuel=20.0, start_count=2, fuel_this_tick=6.0)),
    ]
    record = _record(
        total=10.0,
        start_fuel=20.0,
        start_events=[
            {"action": "start", "tier_fuel_mmbtu": 8.0},
            {"action": "release", "tier_fuel_mmbtu": 12.0},
        ],
    )
    metrics = collect_metrics(ticks, run_record=record)
    assert metrics["fuel_reconciled"] is True
    assert metrics["start_fuel_reconciliation"]["tier_sum_mmbtu"] == 20.0

    with pytest.raises(StartFuelReconciliationError):
        collect_metrics(
            ticks,
            run_record={
                **record,
                "starts": [{"action": "start", "tier_fuel_mmbtu": 8.0}],
            },
        )

    with pytest.raises(FuelComponentReconciliationError):
        collect_metrics(
            ticks,
            run_record={
                **record,
                "turbine_fuel_mmbtu": 11.0,
            },
        )


def test_curtailment_is_range_checked_and_attributed_separately() -> None:
    metrics = collect_metrics(
        [
            _tick(
                5.0,
                _row(total=0.2, no_load_fuel=0.1, fuel_this_tick=0.2),
                curtailed=2.0,
            )
        ],
        run_record=_record(total=0.2),
    )
    assert metrics["dispatch_curtailment_mwh"] > 0.0
    assert metrics["dispatch_curtailment_interval_exposure_fuel_mmbtu"] == 0.2
    assert metrics["dispatch_curtailment_attributable_fuel_mmbtu"] == pytest.approx(
        0.02
    )
    assert (
        metrics["dispatch_curtailment_interval_exposure_fuel_mmbtu"]
        != metrics["dispatch_curtailment_attributable_fuel_mmbtu"]
    )


def test_unserved_energy_is_supply_sensitive() -> None:
    baseline = collect_metrics(
        [
            _tick(5.0, _row(total=1.0), unserved=0.0),
            _tick(10.0, _row(total=2.0), unserved=2.0),
        ],
        run_record=_record(total=2.0),
    )
    informed = collect_metrics(
        [
            _tick(5.0, _row(total=1.0), unserved=0.0),
            _tick(10.0, _row(total=2.0), unserved=0.5),
        ],
        run_record=_record(total=2.0),
    )
    assert informed["unserved_mwh"] < baseline["unserved_mwh"]


def test_induced_forecast_miss_is_reported() -> None:
    metrics = collect_metrics(
        [_tick(5.0, _row(total=1.0), forecast=1.0)],
        run_record=_record(total=1.0),
    )
    assert metrics["forecast"]["miss_count"] == 1
    assert metrics["forecast"]["miss_peak_mw"] == 9.0


def test_commitment_distinct_key_keeps_same_action_at_different_times() -> None:
    metrics = collect_metrics(
        [_tick(5.0, _row(total=1.0))],
        run_record={
            **_record(total=1.0),
            "commitment_log": [
                {
                    "unit_id": "gt-01",
                    "action": "stop",
                    "source": "core_commitment",
                    "sim_time_s": 5.0,
                    "reason": "same",
                    "accepted": True,
                    "changed_state": True,
                },
                {
                    "unit_id": "gt-01",
                    "action": "stop",
                    "source": "core_commitment",
                    "sim_time_s": 10.0,
                    "reason": "same",
                    "accepted": True,
                    "changed_state": True,
                },
            ],
        },
    )
    assert metrics["commitment"]["distinct_event_count"] == 2
    assert metrics["commitment"]["suppressed_repeat_count"] == 0


def test_acceptance_has_fixed_enumeration_and_fails_worse_informed() -> None:
    baseline = {
        "engine_commit": "e",
        "harness_commit": "h",
        "constraints_valid": True,
        "fuel_reconciled": True,
        "energy_balance": {"closure_status": True},
        "unserved_mwh": 1.0,
        "peak_unserved_mw": 1.0,
        "compute_trace_sha256": "same",
    }
    informed = {
        **baseline,
        "mode": "informed",
        "unserved_mwh": 2.0,
        "peak_unserved_mw": 2.0,
    }
    comparison = compare_metrics(baseline, informed)
    assert comparison["verdict"] == "FAIL"
    assert set(comparison["conditions"]) == {
        condition.value for condition in AcceptanceCondition
    }
    assert comparison["conditions"]["informed_unserved_energy_no_worse"] is False


def test_acceptance_refuses_mismatched_build_parity() -> None:
    baseline = {
        "engine_commit": "e1",
        "harness_commit": "h",
    }
    informed = {"engine_commit": "e2", "harness_commit": "h"}
    with pytest.raises(BuildParityMismatchError) as raised:
        compare_metrics(baseline, informed)
    assert raised.value.baseline_engine_commit == "e1"
    assert raised.value.informed_engine_commit == "e2"


def test_identity_and_cache_make_identical_runs_non_executing(tmp_path: Path) -> None:
    identity = make_run_identity(
        scenario_id="s",
        mode="baseline",
        parameter_set={"alpha": 1},
        seed=7,
        duration_seconds=10,
        tick_seconds=5,
        engine_commit="e",
        harness_commit="h",
    )
    cache = RunManifestCache(tmp_path)
    calls = []

    def execute() -> dict:
        calls.append("executed")
        return {"identity_digest": identity.digest, "value": 42}

    first, first_hit = cache.get_or_execute(identity, execute)
    second, second_hit = cache.get_or_execute(identity, execute)
    assert first["value"] == second["value"] == 42
    assert first_hit is False
    assert second_hit is True
    assert calls == ["executed"]
    assert json.loads((tmp_path / "manifest.json").read_text())["runs"]


def test_artifact_writer_verifies_existing_bounded_outputs(tmp_path: Path) -> None:
    identity = make_run_identity(
        scenario_id="s",
        mode="baseline",
        parameter_set={},
        seed=None,
        duration_seconds=5,
        tick_seconds=5,
        engine_commit="e",
        harness_commit="h",
    )
    result = ArtifactWriter(tmp_path, json_cap_bytes=10_000).write(
        identity=identity,
        record={"identity_digest": identity.digest},
        summary={"status": "PASS"},
        tick_rows=[{"tick_index": 1}],
    )
    assert all(Path(path).is_file() for path in result.paths.values())
    assert all(size > 0 for size in result.sizes_bytes.values())