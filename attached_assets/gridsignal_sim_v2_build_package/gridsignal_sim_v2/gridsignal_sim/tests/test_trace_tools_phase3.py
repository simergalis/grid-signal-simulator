from copy import deepcopy
import asyncio
import inspect
import json
from types import SimpleNamespace

from api.routes import trace_comparison, trace_import
from api.routes.scenarios import build_seeded_store
from runtime.periodic_trace_comparison import compare_import_report
from runtime.periodic_trace_import import import_periodic_trace


HEADER = (
    "site_id,date,time,mw_measured,measurement_source,"
    "kubernetes_node_count,kubernetes_request_rate,"
    "slurm_node_count,slurm_request_rate,ray_node_count,ray_request_rate"
)


def realistic_csv() -> str:
    return "\n".join([
        HEADER,
        "sj-2,2026-08-01,12:00:00,1.2,utility_meter,2,,3,,1,",
        "sj-2,2026-08-01,12:05:00,-1,utility_meter,2,,3,,1,",
        "sj-2,2026-08-01,12:10:00,2.1,utility_meter,4,,5,,2,",
        "sj-2,2026-08-01,12:15:00,2.2,utility_meter,4,,-1,,2,",
        "sj-2,2026-08-01,12:20:00,3.0,utility_meter,8,,8,,3,",
    ])


class AnalyticalRequest:
    """Minimal request shape for testing route handlers without auth tier input."""

    def __init__(self, state, *, body: bytes = b"", query_params=None):
        self.app = SimpleNamespace(state=state)
        self._body = body
        self.query_params = query_params or {}
        self.headers = {"content-length": str(len(body))}

    async def body(self):
        return self._body

    async def json(self):
        return json.loads(self._body)


def analytical_state():
    return SimpleNamespace(
        trace_imports={},
        trace_comparisons={},
        # Sentinels represent the separately owned live-control/audit channels.
        control_plane_events=[],
        approval_workflow_entries=[],
    )


def scenario_state(*, pue=1.074, scenario_domains=None):
    spec = {
        "pue_base": pue,
        "kube_config": None,
        "kube_clusters": scenario_domains or [],
    }
    record = SimpleNamespace(spec_json=json.dumps(spec))
    return SimpleNamespace(
        trace_imports={},
        trace_comparisons={},
        scenario_store=SimpleNamespace(get=lambda _scenario_id: record),
        control_plane_events=[],
        approval_workflow_entries=[],
    )


def cap_case_csv(*, site_id="equinix-sj-2", kube="317", slurm="594", ray="25"):
    return "\n".join([
        HEADER,
        f"{site_id},2026-08-01,12:00:00,10,utility_meter,{kube},,{slurm},,{ray},",
    ])


def test_analytical_routes_are_regular_authenticated_routes_without_tier_or_approval_dependencies():
    routes = {
        route.path: route
        for route in [*trace_import.router.routes, *trace_comparison.router.routes]
        if route.path in {
            "/api/scenario-planner/import-trace",
            "/api/scenario-planner/compare-trace/{import_id}",
        }
    }
    assert set(routes) == {
        "/api/scenario-planner/import-trace",
        "/api/scenario-planner/compare-trace/{import_id}",
    }
    for route in routes.values():
        assert not route.dependant.dependencies
        assert "role" not in inspect.signature(route.endpoint).parameters


def test_import_and_comparison_remain_unchanged_for_all_operating_tiers():
    for tier in ("autonomous", "confirm", "human_only"):
        state = analytical_state()
        imported = asyncio.run(trace_import.import_trace(
            AnalyticalRequest(state, body=realistic_csv().encode("utf-8"))
        ))
        comparison = asyncio.run(trace_comparison.compare_trace(
            imported["import_id"],
            AnalyticalRequest(state, body=b"{}"),
        ))
        assert comparison["valid_samples"] == 3
        assert comparison["comparison_id"]
        assert tier in {"autonomous", "confirm", "human_only"}


def test_import_and_comparison_do_not_create_control_plane_or_approval_events():
    state = analytical_state()
    imported = asyncio.run(trace_import.import_trace(
        AnalyticalRequest(state, body=realistic_csv().encode("utf-8"))
    ))
    imported_before = deepcopy(imported)
    comparison = asyncio.run(trace_comparison.compare_trace(
        imported["import_id"],
        AnalyticalRequest(state, body=b"{}"),
    ))
    assert imported == imported_before
    assert state.control_plane_events == []
    assert state.approval_workflow_entries == []
    assert not any(
        key in comparison
        for key in ("dispatch_action", "control_event", "approval_workflow_entry")
    )


def test_realistic_trace_completes_import_then_comparison_with_quarantine_summary():
    state = analytical_state()
    imported = asyncio.run(trace_import.import_trace(
        AnalyticalRequest(state, body=realistic_csv().encode("utf-8"))
    ))
    assert imported["total_rows"] == 5
    assert imported["accepted_rows"] == 3
    assert imported["quarantined_rows"] == 2
    assert "mw_measured must be >= 0" in imported["quarantined"][0]["reason"]
    assert "slurm_node_count must be >= 0" in imported["quarantined"][1]["reason"]

    comparison = asyncio.run(trace_comparison.compare_trace(
        imported["import_id"],
        AnalyticalRequest(state, body=b"{}"),
    ))
    assert comparison["import_id"] == imported["import_id"]
    assert comparison["valid_samples"] == 3
    assert comparison["window"] == imported["window"]
    assert comparison["data_quality"] == {
        "total_rows": 5,
        "accepted_rows": 3,
        "quarantined_rows": 2,
        "quarantined_by_reason": imported["quarantined_by_reason"],
        "conflict_count": 0,
    }
    assert comparison["baseline"]["firm_capacity_mw"] == max(
        row["predicted_mw"] for row in imported["accepted"]
    )
    assert comparison["pas"]["confidence_placeholder_used"] is True


def test_exact_sj2_ray_overage_is_quarantined_by_site_cap():
    imported = asyncio.run(trace_import.import_trace(
        AnalyticalRequest(
            scenario_state(),
            body=cap_case_csv().encode("utf-8"),
            query_params={"scenario_id": "scenario-equinix-sj-2-24h"},
        )
    ))
    assert imported["accepted_rows"] == 0
    assert imported["quarantined_rows"] == 1
    assert imported["quarantined"][0]["reason"] == (
        "ray_node_count exceeds configured maximum 21 racks"
    )


def test_site_cap_overage_is_quarantined_regardless_of_scenario_id():
    for scenario_id, scenario_domains in (
        ("scenario-with-small-ray-cap", [
            {"scheduler_type": "RAY", "max_nodes": 3, "capacity_unit": "rack"},
        ]),
        ("scenario-without-domain-caps", []),
    ):
        imported = asyncio.run(trace_import.import_trace(
            AnalyticalRequest(
                scenario_state(scenario_domains=scenario_domains),
                body=cap_case_csv(kube="951", slurm="951", ray="22").encode("utf-8"),
                query_params={"scenario_id": scenario_id},
            )
        ))
        assert imported["accepted_rows"] == 0
        assert imported["quarantined_rows"] == 1
        reason = imported["quarantined"][0]["reason"]
        assert "kubernetes_node_count exceeds configured maximum 950 nodes" in reason
        assert "slurm_node_count exceeds configured maximum 950 nodes" in reason
        assert "ray_node_count exceeds configured maximum 21 racks" in reason


def test_same_csv_has_identical_cap_validation_across_scenario_ids():
    reports = []
    for scenario_id in ("scenario-one", "scenario-two"):
        reports.append(asyncio.run(trace_import.import_trace(
            AnalyticalRequest(
                scenario_state(
                    pue=1.074,
                    scenario_domains=[
                        {"scheduler_type": "RAY", "max_nodes": 3, "capacity_unit": "rack"},
                    ],
                ),
                body=cap_case_csv().encode("utf-8"),
                query_params={"scenario_id": scenario_id},
            )
        )))
    cap_results = [
        (
            report["accepted_rows"],
            report["quarantined_rows"],
            report["quarantined_by_reason"],
            report["site_capacity_validation"],
        )
        for report in reports
    ]
    assert cap_results[0] == cap_results[1]


def test_unknown_site_has_explicit_warning_and_remains_advisory():
    imported = asyncio.run(trace_import.import_trace(
        AnalyticalRequest(
            analytical_state(),
            body=cap_case_csv(
                site_id="unregistered-site",
                kube="2000",
                slurm="2000",
                ray="2000",
            ).encode("utf-8"),
        )
    ))
    assert imported["accepted_rows"] == 1
    assert imported["quarantined_rows"] == 0
    assert imported["site_capacity_validation"]["status"] == "not_configured"
    assert imported["warnings"] == [
        "Domain-cap validation could not be performed for site_id 'unregistered-site': "
        "no site-level capacity configuration is available."
    ]


def test_scenario_lookup_and_pue_selection_remain_unchanged():
    state = scenario_state(
        pue=1.23,
        scenario_domains=[
            {"scheduler_type": "K8S", "max_nodes": 1, "capacity_unit": "node"},
        ],
    )
    imported = asyncio.run(trace_import.import_trace(
        AnalyticalRequest(
            state,
            body=cap_case_csv(kube="2", slurm="3", ray="1").encode("utf-8"),
            query_params={"scenario_id": "scenario-with-existing-settings"},
        )
    ))
    assert imported["pue"] == 1.23
    assert imported["accepted_rows"] == 1
    assert imported["warnings"] == []
    assert imported["accepted"][0]["predicted_mw"] == round((5 * 10.2 + 126) / 1000 * 1.23, 6)

    seeded = build_seeded_store()
    turbine_spec = json.loads(seeded.get("scenario-turbine-01").spec_json)
    assert [cluster["max_nodes"] for cluster in turbine_spec["kube_clusters"]] == [950, 950, 21]
    assert [cluster["capacity_unit"] for cluster in turbine_spec["kube_clusters"]] == ["node", "node", "rack"]