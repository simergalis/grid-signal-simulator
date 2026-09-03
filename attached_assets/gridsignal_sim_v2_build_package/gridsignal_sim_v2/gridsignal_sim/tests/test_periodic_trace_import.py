from runtime.periodic_trace_import import TraceDomainConfig, import_periodic_trace
from api.routes.trace_import import _domain_configs


HEADER = (
    "site_id,date,time,mw_measured,measurement_source,"
    "kubernetes_node_count,kubernetes_request_rate,"
    "slurm_node_count,slurm_request_rate,ray_node_count,ray_request_rate"
)


def row(date, mw="10", kube="2", slurm="3", ray="1"):
    return f"sj1,{date},12:00:00,{mw},utility_meter,{kube},,{slurm},,{ray},"


def test_normal_file_imports_and_calculates_steady_state_power():
    report = import_periodic_trace(
        HEADER + "\n" + row("2026-08-01") + "\n" + row("2026-08-02"),
        pue=1.37,
    )
    assert report["accepted_rows"] == 2
    assert report["total_rows"] == 2
    assert report["conflict_count"] == 0
    assert report["accepted"][0]["predicted_mw"] == round((5 * 10.2 + 126) / 1000 * 1.37, 6)


def test_negative_measured_power_is_quarantined_individually():
    text = HEADER + "\n" + row("2026-08-01", mw="-1") + "\n" + row("2026-08-02", mw="11")
    report = import_periodic_trace(text)
    assert report["accepted_rows"] == 1
    assert report["quarantined_rows"] == 1
    assert "mw_measured must be >= 0" in report["quarantined"][0]["reason"]


def test_over_cap_is_quarantined_not_clipped():
    report = import_periodic_trace(
        HEADER + "\n" + row("2026-08-01", kube="11"),
        domains={"kubernetes": TraceDomainConfig(configured=True, max_units=10)},
    )
    assert report["accepted_rows"] == 0
    assert "exceeds configured maximum 10 nodes" in report["quarantined"][0]["reason"]


def test_negative_node_count_is_quarantined():
    report = import_periodic_trace(HEADER + "\n" + row("2026-08-01", slurm="-1"))
    assert report["accepted_rows"] == 0
    assert "slurm_node_count must be >= 0" in report["quarantined"][0]["reason"]


def test_duplicate_keeps_first_and_logs_second_conflict():
    report = import_periodic_trace(
        HEADER + "\n" + row("2026-08-01", mw="10") + "\n" + row("2026-08-01", mw="99")
    )
    assert report["accepted_rows"] == 1
    assert report["accepted"][0]["mw_measured"] == 10
    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["conflict_with_row"] == 2


def test_valid_duplicate_can_follow_an_invalid_first_row():
    report = import_periodic_trace(
        HEADER + "\n" +
        row("2026-08-01", mw="-1") + "\n" +
        row("2026-08-01", mw="10")
    )
    assert report["quarantined_rows"] == 1
    assert report["accepted_rows"] == 1
    assert report["conflict_count"] == 0
    assert report["accepted"][0]["row"] == 3
    assert report["accepted"][0]["mw_measured"] == 10


def test_import_prediction_has_no_checkpoint_or_thermal_lag_adjustment():
    report = import_periodic_trace(HEADER + "\n" + row("2026-08-01"))
    assert report["accepted"][0]["predicted_mw"] == round((5 * 10.2 + 126) / 1000 * 1.37, 6)


def test_route_config_normalises_k8s_caps_and_inference_requirements():
    domains = _domain_configs({
        "kube_clusters": [
            {"scheduler_type": "K8S", "max_nodes": 10, "capacity_unit": "node"},
            {"scheduler_type": "RAY", "max_nodes": 3, "capacity_unit": "rack"},
        ],
        "workload_events": [
            {"workload_class": "inference", "scheduler_domain": "K8S"},
        ],
    })
    report = import_periodic_trace(
        HEADER + "\n" + row("2026-08-01", kube="11"),
        domains=domains,
    )
    assert report["accepted_rows"] == 0
    assert "kubernetes_node_count exceeds configured maximum 10 nodes" in report["quarantined"][0]["reason"]
    assert "kubernetes_request_rate is required for configured inference workload" in report["quarantined"][0]["reason"]


def test_whitespace_required_value_is_quarantined_not_a_file_level_mix():
    report = import_periodic_trace(
        HEADER + "\n" + row("2026-08-01") + "\n" +
        "   ,2026-08-02,12:00:00,10,utility_meter,2,,3,,1,"
    )
    assert report["accepted_rows"] == 1
    assert report["quarantined_rows"] == 1
    assert "site_id is required" in report["quarantined"][0]["reason"]


def test_site_capacity_lookup_warns_for_unknown_site_without_skipping_import():
    report = import_periodic_trace(
        HEADER + "\n" + "unknown-site,2026-08-01,12:00:00,10,utility_meter,2000,,2000,,2000,",
        site_domain_configs={
            "equinix-sj-2": {
                "kubernetes": TraceDomainConfig(configured=True, max_units=950),
            },
        },
    )
    assert report["accepted_rows"] == 1
    assert report["quarantined_rows"] == 0
    assert report["site_capacity_validation"]["status"] == "not_configured"
    assert len(report["warnings"]) == 1
    assert "unknown-site" in report["warnings"][0]
    assert "could not be performed" in report["warnings"][0]