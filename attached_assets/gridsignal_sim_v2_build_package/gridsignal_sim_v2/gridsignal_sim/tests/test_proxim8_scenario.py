import json
from pathlib import Path

from api.schemas import ScenarioSpec
from api.routes.scenarios import build_seeded_store
from mcp_server import server as server_module
from study_harness.executor import (
    PROXIM8_SCENARIO_ID,
    STUDY_CLASS_SCENARIO_JSON,
    study_class_for_scenario,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = (
    PACKAGE_ROOT
    / "config"
    / "scenarios"
    / f"{PROXIM8_SCENARIO_ID}.json"
)


def test_proxim8_scenario_loads_with_requested_scheduler_counts() -> None:
    raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    spec = ScenarioSpec.model_validate(raw)
    starts = [
        event
        for event in spec.workload_events
        if event.event_type == "starting"
    ]
    counts = {
        scheduler: sum(
            event.scheduler_type == scheduler
            for event in starts
        )
        for scheduler in ("SLURM", "K8S", "RAY")
    }

    assert spec.end_sim_time == 86400
    assert spec.grid_import_limit_mw == 5.0
    assert counts == {"SLURM": 10, "K8S": 1000, "RAY": 10000}
    assert any(
        event.scheduler_type == "K8S"
        and event.event_type == "starting"
        and event.timestamp == 0.0
        for event in spec.workload_events
    )
    assert all(
        event.cluster_id and event.workload_class
        for event in spec.workload_events
    )
    assert not {"kube_config", "kube_clusters", "slurm_config"} & raw.keys()
    assert PROXIM8_SCENARIO_ID in server_module.STUDY_SCENARIOS
    assert PROXIM8_SCENARIO_ID in server_module.SCENARIO_IDS
    assert study_class_for_scenario(PROXIM8_SCENARIO_ID) == STUDY_CLASS_SCENARIO_JSON
    assert build_seeded_store().get(PROXIM8_SCENARIO_ID) is not None
