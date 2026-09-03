from datetime import date, timedelta
import asyncio
from types import SimpleNamespace

import pytest

from api.routes import advisory, capacity_outlook
from runtime.advisory_gate import AdvisoryGate
from runtime.capacity_outlook import build_capacity_outlook
from runtime.capacity_outlook import SITE_FIRM_CAPACITY_MW


def imported(values_by_date):
    rows = []
    for index, (stamp, value) in enumerate(values_by_date, start=1):
        rows.append({"row": index, "timestamp": stamp, "predicted_mw": value})
    return {
        "import_id": "trace-capacity-test",
        "site_id": "test-site",
        "window": {"start": rows[0]["timestamp"], "end": rows[-1]["timestamp"]},
        "accepted": rows,
    }


def test_weekday_percentile_uses_the_correct_weekday_distribution():
    # 2026-08-02 is Sunday; Sundays are deliberately much higher.
    samples = [
        ("2026-08-02T00:00:00", 10.0),
        ("2026-08-09T00:00:00", 20.0),
        ("2026-08-03T00:00:00", 2.0),
        ("2026-08-04T00:00:00", 3.0),
        ("2026-08-05T00:00:00", 4.0),
        ("2026-08-06T00:00:00", 5.0),
        ("2026-08-07T00:00:00", 6.0),
        ("2026-08-08T00:00:00", 7.0),
    ]
    report = build_capacity_outlook(imported(samples), percentile=90, horizon_days=7, firm_capacity_mw=100)
    assert report["weekday_percentiles"]["0"] == 19.0
    assert report["weekday_percentiles"]["1"] == 2.0


@pytest.mark.parametrize("horizon", [7, 30])
def test_projection_tiles_each_future_date_by_weekday(horizon):
    start = date(2026, 8, 2)
    samples = [(f"{start + timedelta(days=i)}T00:00:00", float(i + 1)) for i in range(7)]
    report = build_capacity_outlook(imported(samples), percentile=50, horizon_days=horizon, firm_capacity_mw=100)
    for index, item in enumerate(report["projected_series"]):
        expected_weekday = ((start + timedelta(days=7) + timedelta(days=index)).weekday() + 1) % 7
        assert item["projected_mw"] == report["weekday_percentiles"][str(expected_weekday)]


def test_shortfall_is_only_flagged_above_firm_capacity():
    samples = [(f"2026-08-{day:02d}T00:00:00", value) for day, value in [(2, 10), (3, 12), (4, 8), (5, 9), (6, 11), (7, 7), (8, 6)]]
    report = build_capacity_outlook(imported(samples), percentile=100, horizon_days=7, firm_capacity_mw=10)
    assert report["shortfall_days"]
    assert all(item["projected_mw"] > 10 for item in report["shortfall_days"])
    no_shortfall = build_capacity_outlook(imported(samples), percentile=100, horizon_days=7, firm_capacity_mw=12)
    assert no_shortfall["shortfall_days"] == []


def test_same_import_and_settings_are_identical():
    samples = [(f"2026-08-{day:02d}T00:00:00", float(day)) for day in range(2, 9)]
    first = build_capacity_outlook(imported(samples), percentile=90, horizon_days=30, firm_capacity_mw=20)
    second = build_capacity_outlook(imported(samples), percentile=90, horizon_days=30, firm_capacity_mw=20)
    assert first == second


def test_seeded_firm_capacity_matches_equinix_archetype_without_touching_turbine():
    assert SITE_FIRM_CAPACITY_MW["equinix-sj-1"] == 29.0
    assert SITE_FIRM_CAPACITY_MW["equinix-sj-2"] == 29.0
    assert "turbine-01" not in SITE_FIRM_CAPACITY_MW


def test_projecting_a_saved_import_uses_the_persisted_import_lookup(monkeypatch):
    saved = imported([
        (f"2026-08-{2 + i:02d}T00:00:00", float(i + 1))
        for i in range(7)
    ])
    seen = {}

    async def load(import_id):
        seen["import_id"] = import_id
        return saved

    async def persist(report):
        seen["report"] = report

    monkeypatch.setattr(capacity_outlook, "load_trace_import_report", load)
    monkeypatch.setattr(capacity_outlook, "persist_capacity_outlook_report", persist)
    request = SimpleNamespace(
        json=lambda: asyncio.sleep(0, result={"import_id": saved["import_id"], "horizon_days": 7, "percentile": 90}),
    )
    report = asyncio.run(capacity_outlook.project(request))
    assert seen["import_id"] == saved["import_id"]
    assert report["import_id"] == saved["import_id"]
    assert seen["report"]["outlook_id"] == report["outlook_id"]


def test_submitting_shortfall_creates_existing_pending_reservation_proposal(monkeypatch):
    report = build_capacity_outlook(
        imported([
            (f"2026-08-{2 + i:02d}T00:00:00", 25.0 if i == 0 else 1.0)
            for i in range(7)
        ]),
        percentile=90, horizon_days=7, firm_capacity_mw=20,
    )
    gate = AdvisoryGate()
    registry = SimpleNamespace(get_gate=lambda: gate, all_proposals=gate.all_proposals)
    manager = SimpleNamespace(
        get_registry=lambda run_id: registry if run_id == "run-1" else None,
        get_context=lambda run_id: SimpleNamespace(sim_time=12.0),
    )
    async def load(_outlook_id):
        return report
    monkeypatch.setattr(capacity_outlook, "load_capacity_outlook_report", load)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(run_manager=manager)),
        headers={"content-length": "18"},
        json=lambda: asyncio.sleep(0, result={"run_id": "run-1"}),
    )
    result = asyncio.run(capacity_outlook.submit_proposal(report["outlook_id"], request))
    proposal = gate.get(result["proposal_id"])
    assert result["state"] == "pending"
    assert proposal is not None
    assert proposal.kind == "reservation"
    assert proposal.state.value == "pending"
    manager.get_context = lambda run_id: SimpleNamespace(sim_time=12.0) if run_id == "run-1" else None
    manager.get_completed = lambda _run_id: None
    listed = asyncio.run(advisory.list_proposals("run-1", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(run_manager=manager)))))
    assert any(item.proposal_id == result["proposal_id"] and item.state == "pending" for item in listed.proposals)


def test_submitting_shortfall_creates_standalone_pending_proposal(monkeypatch):
    report = build_capacity_outlook(
        imported([
            (f"2026-08-{2 + i:02d}T00:00:00", 25.0)
            for i in range(7)
        ]),
        percentile=90, horizon_days=7, firm_capacity_mw=20,
    )
    gate = AdvisoryGate()
    registry = SimpleNamespace(get_gate=lambda: gate, all_proposals=gate.all_proposals)
    manager = SimpleNamespace(
        get_registry=lambda _run_id: registry,
        create_advisory_registry=lambda _registry_id: registry,
        get_context=lambda _run_id: None,
        get_completed=lambda _run_id: None,
    )
    async def load(_outlook_id):
        return report
    monkeypatch.setattr(capacity_outlook, "load_capacity_outlook_report", load)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(run_manager=manager)),
        headers={"content-length": "0"},
        json=lambda: asyncio.sleep(0, result={}),
    )
    result = asyncio.run(capacity_outlook.submit_proposal(report["outlook_id"], request))
    assert result["state"] == "pending"
    listed = asyncio.run(advisory.list_proposals(
        f"capacity-outlook-{report['outlook_id']}",
        SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(run_manager=manager))),
    ))
    assert any(item.proposal_id == result["proposal_id"] and item.state == "pending" for item in listed.proposals)