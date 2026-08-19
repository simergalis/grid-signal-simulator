"""Regression coverage for the grid-limited Kubernetes scenario."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.routes.scenarios import build_seeded_store
from api.schemas import ScenarioSpec
from core.kube_demand import KubeConfig, KubeDemandAgent
from runtime.run_manager import _tick_result_to_dict
from runtime.scenario_factory import build_run_context_from_spec
from tests.test_forecast_path import _run_tick, _starting_signal


_SCENARIO_ID = "scenario-equinix-sj-1"
_SCENARIO_PATH = (
    Path(__file__).parents[1]
    / "config"
    / "scenarios"
    / f"{_SCENARIO_ID}.json"
)
_SOURCE_PATH = (
    Path(__file__).parents[1]
    / "config"
    / "scenarios"
    / "scenario-kube-peak-overage.json"
)


def _load_raw(path: Path) -> dict:
    return json.loads(path.read_text())


def _grid_only_tick(grid_import_limit_mw: float | None):
    spec = {
        "name": "grid-import-limit-physics-test",
        "description": "Grid-only balance test.",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 0.0,
        "workload_events": [],
        "bess_units": [],
        "turbine_units": [],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "island_mode": False,
        "grid_import_limit_mw": grid_import_limit_mw,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "pue_base": 1.03,
        "end_sim_time": 60.0,
    }
    ctx = build_run_context_from_spec("grid-cap-test", spec)
    signal = _starting_signal(nodes=2000, ramp_s=1.0, timestamp=0.0)
    ctx.sim_state.apply_workload_signal(signal, dt_lead_seconds=0.0)
    return _run_tick(ctx.sim_state, sim_time=5.0, dt=5.0)


def test_scenario_location_defaults_to_santa_clara() -> None:
    spec = ScenarioSpec.model_validate(
        {
            "name": "default-location-test",
            "description": "Uses the canonical scenario location.",
        }
    )

    assert spec.site_name == "Santa Clara, CA, USA"
    assert spec.site_latitude == pytest.approx(37.3541)
    assert spec.site_longitude == pytest.approx(-121.9552)
    assert spec.site_utc_offset_h == pytest.approx(-8.1303466667)


def test_seeded_scenario_without_location_uses_santa_clara_defaults() -> None:
    record = build_seeded_store().get("demo-alert")
    assert record is not None

    spec = ScenarioSpec.model_validate_json(record.spec_json)
    assert spec.site_name == "Santa Clara, CA, USA"
    assert spec.site_latitude == pytest.approx(37.3541)
    assert spec.site_longitude == pytest.approx(-121.9552)


def test_scenario_schema_and_requested_capacities() -> None:
    spec = ScenarioSpec.model_validate_json(_SCENARIO_PATH.read_text())

    assert spec.site_name == "San Jose, CA, USA"
    assert spec.site_latitude == pytest.approx(37.3382)
    assert spec.site_longitude == pytest.approx(-121.8863)
    assert spec.site_utc_offset_h == pytest.approx(-8.0)
    assert spec.island_mode is False
    assert spec.grid_import_limit_mw == pytest.approx(5.0)
    assert len(spec.bess_units) == 1
    assert spec.bess_units[0].rated_mw == pytest.approx(30.0)
    assert spec.bess_units[0].usable_mwh == pytest.approx(60.0)
    assert spec.turbine_units == []
    assert spec.fuel_cell_rated_mw * spec.fuel_cell_stack_count == pytest.approx(24.0)


def test_scenario_preserves_generator_timing_and_caps_each_job_below_7mw() -> None:
    scenario = _load_raw(_SCENARIO_PATH)
    source = _load_raw(_SOURCE_PATH)
    clusters = scenario["kube_clusters"]
    source_kube = source["kube_config"]

    timing_fields = (
        "mean_interarrival_s",
        "mean_job_duration_s",
        "min_job_duration_s",
        "reorder_window_s",
        "ntp_jitter_s",
    )
    for cluster in clusters:
        assert {key: cluster[key] for key in timing_fields} == {
            key: source_kube[key] for key in timing_fields
        }

    assert [cluster["max_job_nodes"] for cluster in clusters] == [300, 300, 42]
    assert [cluster["rng_seed"] for cluster in clusters] == [42, 1042, 2042]
    assert sum(cluster["workload_share"] for cluster in clusters) == pytest.approx(1.0)
    aggregate_arrival_rate = sum(
        cluster["workload_share"] / cluster["mean_interarrival_s"]
        for cluster in clusters
    )
    assert aggregate_arrival_rate == pytest.approx(
        1.0 / source_kube["mean_interarrival_s"]
    )

    generator = scenario["generator_config"]
    source_generator = source["generator_config"]
    assert generator["ratePerMinute"] == source_generator["ratePerMinute"]
    assert generator["burstMode"] == source_generator["burstMode"]
    assert generator["burstSize"] == source_generator["burstSize"]
    assert generator["burstIntervalSeconds"] == source_generator["burstIntervalSeconds"]
    assert generator["jobSizes"] == source_generator["jobSizes"]
    assert generator["maxJobsPerTenant"] == source_generator["maxJobsPerTenant"]
    assert generator["jobDurationRange"] == source_generator["jobDurationRange"]
    assert generator["tenantWeights"] == {
        "a": pytest.approx(0.425),
        "b": pytest.approx(0.425),
        "c": pytest.approx(0.15),
    }

    profile_kw = {
        "enterprise_8gpu_air": 10.2,
        "nextgen_rack_liquid": 120.0,
    }
    for cluster in clusters:
        max_job_units = min(cluster["max_job_nodes"], cluster["max_nodes"])
        max_job_mw_including_pue = (
            max_job_units
            * profile_kw[cluster["hardware_profile_id"]]
            * scenario["pue_base"]
            / 1000.0
        )
        assert max_job_mw_including_pue < 7.0


def test_sj1_job_caps_are_cluster_specific_and_capacity_bounded() -> None:
    spec = ScenarioSpec.model_validate_json(_SCENARIO_PATH.read_text())
    ctx = build_run_context_from_spec(
        "sj1-job-cap-policy",
        spec.model_dump(mode="json"),
    )
    by_cluster = {
        agent.config.cluster_id: agent.config
        for agent in ctx.sim_state.kube_agents
    }

    assert by_cluster["sj1-k8s-h100"].max_job_nodes == 300
    assert by_cluster["sj1-slurm-h100"].max_job_nodes == 300
    assert by_cluster["sj1-ray-gb200"].max_job_nodes == 42

    # The policy ceiling is per cluster, and a policy ceiling cannot override
    # the cluster's own total capacity (21 racks for Ray).
    assert min(
        by_cluster["sj1-k8s-h100"].max_job_nodes,
        by_cluster["sj1-k8s-h100"].max_nodes,
    ) == 300
    assert min(
        by_cluster["sj1-ray-gb200"].max_job_nodes,
        by_cluster["sj1-ray-gb200"].max_nodes,
    ) == 21


def test_per_cluster_job_cap_bounds_generated_job_units() -> None:
    def first_job_units(*, max_nodes: int, max_job_nodes: int) -> int:
        agent = KubeDemandAgent(
            KubeConfig(
                max_nodes=max_nodes,
                min_nodes=1,
                min_job_nodes=1,
                max_job_nodes=max_job_nodes,
                mean_job_nodes=10_000,
                job_node_std=0.0,
                reorder_window_s=0.0,
                ntp_jitter_s=0.0,
                rng_seed=7,
            )
        )
        signals, _metrics = agent.tick(sim_time=0.0, dt_seconds=1.0)
        assert len(signals) == 1
        return signals[0].node_count

    assert first_job_units(max_nodes=708, max_job_nodes=300) == 300
    # The per-cluster policy can express a 42-rack ceiling, but cannot make a
    # 21-rack cluster admit more capacity than it owns.
    assert first_job_units(max_nodes=21, max_job_nodes=42) == 21


def test_sj1_factory_builds_requested_independent_cluster_fleet() -> None:
    spec = ScenarioSpec.model_validate_json(_SCENARIO_PATH.read_text())
    ctx = build_run_context_from_spec(
        "sj1-cluster-shape",
        spec.model_dump(mode="json"),
    )
    agents = ctx.sim_state.kube_agents

    assert [
        (
            agent.config.cluster_id,
            agent.config.scheduler_type,
            agent.config.hardware_profile_id,
            agent.config.max_nodes,
            agent.config.capacity_unit,
            agent.config.gpus_per_unit,
        )
        for agent in agents
    ] == [
        ("sj1-k8s-h100", "K8S", "enterprise_8gpu_air", 708, "node", 8),
        ("sj1-slurm-h100", "SLURM", "enterprise_8gpu_air", 708, "node", 8),
        ("sj1-ray-gb200", "RAY", "nextgen_rack_liquid", 21, "rack", 72),
    ]

    h100_gpus = sum(
        agent.config.max_nodes * agent.config.gpus_per_unit
        for agent in agents
        if agent.config.hardware_profile_id == "enterprise_8gpu_air"
    )
    gb200_gpus = sum(
        agent.config.max_nodes * agent.config.gpus_per_unit
        for agent in agents
        if agent.config.hardware_profile_id == "nextgen_rack_liquid"
    )
    assert h100_gpus == 11_328
    assert gb200_gpus == 1_512
    assert h100_gpus + gb200_gpus == 12_840

    h100_mw = 2 * 708 * 10.2 / 1000.0
    gb200_mw = 21 * 120.0 / 1000.0
    total_it_mw = h100_mw + gb200_mw
    assert total_it_mw == pytest.approx(16.9632)
    assert round(total_it_mw, 1) == pytest.approx(17.0)
    assert h100_mw / total_it_mw == pytest.approx(0.8514, abs=1e-4)
    assert gb200_mw / total_it_mw == pytest.approx(0.1486, abs=1e-4)


def test_sj1_cluster_admission_is_independent_and_payload_keeps_identity() -> None:
    spec = ScenarioSpec.model_validate_json(_SCENARIO_PATH.read_text())
    ctx = build_run_context_from_spec(
        "sj1-independent-capacity",
        spec.model_dump(mode="json"),
    )

    tick = None
    for _ in range(80):
        tick = ctx.step()
    assert tick is not None
    metrics = tick.kube_metrics
    assert metrics is not None

    by_cluster = {m.cluster_id: m for m in metrics.cluster_metrics}
    assert set(by_cluster) == {
        "sj1-k8s-h100",
        "sj1-slurm-h100",
        "sj1-ray-gb200",
    }
    assert all(m.admitted_units <= m.max_units for m in by_cluster.values())
    # Both H100 clusters can admit beyond one 708-node shared ceiling in
    # aggregate, proving their capacity accumulators are independent.
    assert (
        by_cluster["sj1-k8s-h100"].admitted_units
        + by_cluster["sj1-slurm-h100"].admitted_units
    ) > 708
    assert metrics.total_gpu_capacity == 12_840

    payload = _tick_result_to_dict(tick)
    assert payload["kube_metrics"]["total_gpu_capacity"] == 12_840
    assert {
        cluster["capacity_unit"]
        for cluster in payload["kube_metrics"]["cluster_metrics"]
    } == {"node", "rack"}
    for job in (
        payload["kube_metrics"]["pending_jobs"]
        + payload["kube_metrics"]["active_jobs_detail"]
    ):
        assert job["cluster_id"]
        assert job["capacity_unit"] in {"node", "rack"}
        assert job["gpus_per_unit"] in {8, 72}


def test_sj1_multicluster_replay_is_deterministic() -> None:
    spec_data = ScenarioSpec.model_validate_json(
        _SCENARIO_PATH.read_text()
    ).model_dump(mode="json")
    contexts = [
        build_run_context_from_spec(f"sj1-replay-{index}", spec_data)
        for index in range(2)
    ]

    traces = []
    for ctx in contexts:
        trace = []
        for _ in range(50):
            tick = ctx.step()
            metrics = tick.kube_metrics
            assert metrics is not None
            trace.append((
                round(tick.p_compute_demand_mw, 6),
                tuple(
                    (m.cluster_id, m.scheduled_units, m.admitted_units)
                    for m in metrics.cluster_metrics
                ),
                tuple(job.event_id for job in metrics.active_jobs_detail),
            ))
        traces.append(trace)

    assert traces[0] == traces[1]


def test_legacy_single_kube_config_still_builds_one_shared_fleet() -> None:
    source = ScenarioSpec.model_validate_json(_SOURCE_PATH.read_text())
    ctx = build_run_context_from_spec(
        "legacy-shared-kube-fleet",
        source.model_dump(mode="json"),
    )

    assert len(ctx.sim_state.kube_agents) == 3
    assert {
        agent.config.cluster_id for agent in ctx.sim_state.kube_agents
    } == {"legacy-shared-fleet"}
    assert {
        agent.config.max_nodes for agent in ctx.sim_state.kube_agents
    } == {source.kube_config.max_nodes}


def test_multicluster_schema_rejects_ambiguous_or_unbalanced_config() -> None:
    cluster = {
        "cluster_id": "cluster-a",
        "tenant_id": "tenant-a",
        "scheduler_type": "K8S",
        "capacity_unit": "node",
        "workload_share": 1.0,
        "max_nodes": 100,
        "min_nodes": 10,
    }
    base = {
        "name": "invalid-kube-cluster-shape",
        "description": "Schema validation fixture.",
    }

    with pytest.raises(ValueError, match="mutually exclusive"):
        ScenarioSpec.model_validate({
            **base,
            "kube_config": {"max_nodes": 100, "min_nodes": 10},
            "kube_clusters": [cluster],
        })

    with pytest.raises(ValueError, match="must sum to 1.0"):
        ScenarioSpec.model_validate({
            **base,
            "kube_clusters": [
                {**cluster, "workload_share": 0.6},
                {
                    **cluster,
                    "cluster_id": "cluster-b",
                    "tenant_id": "tenant-b",
                    "scheduler_type": "SLURM",
                    "workload_share": 0.3,
                },
            ],
        })

    with pytest.raises(ValueError, match="max_job_nodes"):
        ScenarioSpec.model_validate({
            **base,
            "kube_clusters": [{
                **cluster,
                "min_job_nodes": 50,
                "max_job_nodes": 49,
            }],
        })


def test_seeded_store_exposes_scenario_and_factory_wires_grid_limit() -> None:
    record = build_seeded_store().get(_SCENARIO_ID)
    assert record is not None
    spec = ScenarioSpec.model_validate_json(record.spec_json)
    assert spec.grid_import_limit_mw == pytest.approx(5.0)

    ctx = build_run_context_from_spec(
        "grid-limited-seed-test",
        spec.model_dump(mode="json"),
    )
    assert ctx.site_name == "San Jose, CA, USA"
    assert ctx.site_lat == pytest.approx(37.3382)
    assert ctx.site_lon == pytest.approx(-121.8863)
    assert ctx.site_utc_offset_h == pytest.approx(-8.0)
    assert ctx.sim_state.site.grid_import_limit_mw == pytest.approx(5.0)


def test_grid_import_is_physically_capped_and_d4_remains_balanced() -> None:
    tick = _grid_only_tick(10.0)

    assert tick.p_demand_mw > 10.0
    assert tick.grid_exchange_mw == pytest.approx(-10.0, abs=1e-9)
    assert tick.frequency_forcing_mw < 0.0
    # The physical D4 defect reports the generation deficit rather than treating
    # unmet demand as served.  It therefore matches the residual that could not
    # pass through the capped PCC.
    assert tick.d4_balance_defect_mw == pytest.approx(
        tick.frequency_forcing_mw,
        abs=1e-9,
    )
    assert tick.p_unserved_mw == pytest.approx(-tick.frequency_forcing_mw, abs=1e-9)
    assert tick.p_generation_mw == pytest.approx(10.0, abs=1e-9)


def test_unset_grid_import_limit_preserves_unlimited_grid_balancing() -> None:
    tick = _grid_only_tick(None)

    assert tick.p_demand_mw > 10.0
    assert -tick.grid_exchange_mw == pytest.approx(tick.p_demand_mw, abs=1e-9)
    assert tick.frequency_forcing_mw == 0.0
    assert tick.d4_balance_defect_mw == pytest.approx(0.0, abs=1e-9)


def test_grid_import_limit_does_not_cap_export() -> None:
    spec = {
        "name": "grid-export-uncapped-physics-test",
        "description": "A synchronised turbine exports surplus through a zero-import PCC.",
        "hardware_profile_id": "enterprise_8gpu_air",
        "dt_lead_seconds": 0.0,
        "workload_events": [],
        "bess_units": [],
        "turbine_units": [
            {
                "asset_id": "turbine-0",
                "rated_mw": 25.0,
                "r_asset_mw_per_s": 0.2,
                "p_min_stable_frac": 0.4,
                "hot_standby": False,
            }
        ],
        "solar_rated_mw": 0.0,
        "fuel_cell_enabled": False,
        "island_mode": False,
        "grid_import_limit_mw": 0.0,
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
        "pue_base": 1.03,
        "end_sim_time": 60.0,
    }
    ctx = build_run_context_from_spec("grid-export-test", spec)
    tick = _run_tick(ctx.sim_state, sim_time=5.0, dt=5.0)

    assert tick.turbine_output_mw > 0.0
    assert tick.grid_exchange_mw == pytest.approx(
        tick.turbine_output_mw - tick.p_demand_mw,
        abs=1e-9,
    )
    assert tick.grid_exchange_mw > 0.0
    assert tick.frequency_forcing_mw == 0.0