import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.app import create_app
import api.app as app_module
import api.routes.ai as ai_module


class _ActiveUserSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, _model, _user_id):
        return SimpleNamespace(is_active=True)


def _authenticated_app(monkeypatch):
    monkeypatch.setattr(app_module, "decode_access_token", lambda _token: {"sub": "1"})
    monkeypatch.setattr(app_module, "_SessionLocal", lambda: _ActiveUserSession())
    def _fake_claude(question, context, _api_key):
        return context["deterministic_query_interpretation"]["reply"]
    monkeypatch.setattr(ai_module, "_call_anthropic_gridley", _fake_claude)
    app = create_app()
    return app


def _set_session(client: TestClient) -> None:
    client.cookies.set("gs_session", "test-session")


def test_gridley_query_is_grounded_and_includes_tick_reference(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "Show the current energy flow",
            "scenario_id": "demo-20mw",
            "tick": {
                "tick_index": 7,
                "sim_time_seconds": 35.0,
                "p_demand_mw": 12.5,
                "p_generation_mw": 11.0,
                "bess_output_mw": 2.0,
                "fuel_cell_output_mw": 0.0,
                "turbine_output_mw": 9.0,
                "data_quality_tags": ["uncalibrated_site"],
            },
        })
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "query"
    assert "tick #7" in body["reply"]
    assert "uncalibrated_site" in body["reply"]
    assert "12.5" in body["reply"]


def test_gridley_change_requires_confirmation_then_audits_and_undoes(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        proposal = client.post("/api/ai/gridley", json={
            "message": "Set pue_base to 1.10",
            "scenario_id": "demo-20mw",
        })
        assert proposal.status_code == 200
        assert proposal.json()["change"]["requires_confirmation"] is True

        applied = client.post("/api/ai/gridley", json={
            "message": "Set pue_base to 1.10",
            "confirmed": True,
            "scenario_id": "demo-20mw",
        })
        assert applied.status_code == 200
        assert applied.json()["audit_id"]
        scenario = client.app.state.scenario_store.get("demo-20mw")
        assert scenario is not None
        assert "1.1" in scenario.spec_json

        undo_proposal = client.post("/api/ai/gridley", json={
            "message": "undo",
            "action": "undo",
            "scenario_id": "demo-20mw",
        })
        assert undo_proposal.status_code == 200
        assert undo_proposal.json()["change"]["requires_confirmation"] is True

        undone = client.post("/api/ai/gridley", json={
            "message": "undo",
            "action": "undo",
            "confirmed": True,
            "scenario_id": "demo-20mw",
        })
        assert undone.status_code == 200
        scenario = client.app.state.scenario_store.get("demo-20mw")
        assert scenario is not None
        assert "1.1" not in scenario.spec_json


def test_gridley_saves_a_named_copy_only_after_confirmation(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        source = client.app.state.scenario_store.get("scenario-turbine-01")
        assert source is not None
        source_spec = source.spec_json
        before_count = len(client.app.state.scenario_store.list_all())

        needs_name = client.post("/api/ai/gridley", json={
            "message": "save this scenario with a new name",
            "scenario_id": "scenario-turbine-01",
        })
        assert needs_name.status_code == 200
        assert needs_name.json()["intent"] == "save_scenario_as"
        assert needs_name.json()["data"]["awaiting_scenario_name"] is True
        assert len(client.app.state.scenario_store.list_all()) == before_count

        proposal = client.post("/api/ai/gridley", json={
            "message": "save this scenario as Customer Scenario - turbine study copy",
            "scenario_id": "scenario-turbine-01",
        })
        proposal_body = proposal.json()
        assert proposal.status_code == 200
        assert proposal_body["change"]["requires_confirmation"] is True
        assert proposal_body["change"]["before"] == source.name
        assert proposal_body["change"]["after"] == "Customer Scenario - turbine study copy"
        assert len(client.app.state.scenario_store.list_all()) == before_count

        saved = client.post("/api/ai/gridley", json={
            "message": "Set save_scenario_as to Customer Scenario - turbine study copy",
            "confirmed": True,
            "scenario_id": "scenario-turbine-01",
        })
        saved_body = saved.json()
        assert saved.status_code == 200
        created_id = saved_body["data"]["created_scenario_id"]
        created = client.app.state.scenario_store.get(created_id)
        assert created is not None
        assert created_id != "scenario-turbine-01"
        assert created.name == "Customer Scenario - turbine study copy"
        assert created.spec_json != source_spec
        assert client.app.state.scenario_store.get("scenario-turbine-01").spec_json == source_spec
        assert len(client.app.state.scenario_store.list_all()) == before_count + 1
        audit = client.app.state.gridley_audit[-1]
        assert audit["action"] == "save_scenario_as"
        assert audit["created_scenario_id"] == created_id


def test_gridley_exports_to_device_without_mutating_the_scenario_store(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        source = client.app.state.scenario_store.get("scenario-turbine-01")
        assert source is not None
        before_count = len(client.app.state.scenario_store.list_all())
        before_spec = source.spec_json

        response = client.post("/api/ai/gridley", json={
            "message": "Save this scenario to my local PC",
            "scenario_id": "scenario-turbine-01",
        })
        body = response.json()
        assert response.status_code == 200
        assert body["intent"] == "export_scenario_to_device"
        assert body["change"]["parameter"] == "export_scenario_to_device"
        assert body["change"]["requires_confirmation"] is True
        assert body["data"]["local_only"] is True
        assert body["data"]["export_format"] == "gridsignal-scenario/v1"
        assert "run history" in body["reply"]
        assert len(client.app.state.scenario_store.list_all()) == before_count
        assert client.app.state.scenario_store.get("scenario-turbine-01").spec_json == before_spec


def test_gridley_refuses_live_hardware_requests(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "Set the live PMS battery setpoint to 3 MW",
            "scenario_id": "demo-20mw",
        })
    assert response.status_code == 200
    assert response.json()["intent"] == "out_of_scope"
    assert "live sites" in response.json()["reply"]


def test_gridley_answers_data_center_size_from_declared_design_peak(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "What is the size of this data center?",
            "scenario_id": "demo-20mw",
            "tick": {
                "tick_index": 6,
                "sim_time_seconds": 30.0,
                "p_demand_mw": 6.1862,
                "design_peak_load_mw": 20.0,
            },
        })
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "query"
    assert body["data"]["query_entry"] == "site_capacity"
    assert "20.00 MW" in body["reply"]
    assert "Energy flow" not in body["reply"]


def test_gridley_does_not_default_unknown_questions_to_energy_flow(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "What is the weather forecast for tomorrow?",
            "scenario_id": "demo-20mw",
            "tick": {"tick_index": 7, "sim_time_seconds": 35.0, "p_demand_mw": 12.5},
        })
        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "query"
        assert body["data"]["query_match"] == "no_match"
        assert "Energy flow" not in body["reply"]
        assert "not tracked" in body["reply"]


def test_gridley_catalogue_returns_entry_and_exact_live_value(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "What is the current site demand?",
            "scenario_id": "demo-20mw",
            "tick": {"tick_index": 8, "sim_time_seconds": 40.0, "p_demand_mw": 12.75},
        })
        body = response.json()
        assert body["intent"] == "query"
        assert body["data"]["query_entry"] == "site_demand"
        assert body["data"]["source"] == "energy_flow.demand_mw"
        assert body["data"]["value"] == 12.75


def test_gridley_retrieves_operator_knowledge_for_natural_variants() -> None:
    variants = [
        "How does GridSignal benefit a GPU data center operator?",
        "What does GridSignal do for someone running a GPU data center?",
        "Why would a GPU data center operator use GridSignal?",
        "What are the main advantages of GridSignal for GPU data center operators?",
        "How can GridSignal help me operate a GPU data center?",
        "What value does GridSignal provide to operators of GPU data centers?",
        "How does GridSignal help manage power in a GPU data center?",
        "Why is GridSignal useful for GPU data center operations?",
        "What problem does GridSignal solve for a GPU facility operator?",
        "How can a GPU data center operator use GridSignal's early warning?",
        "How does GridSignal help operators handle GPU workload spikes?",
        "What benefits does GridSignal bring to a multi-tenant GPU data center operator?",
        "How does GridSignal improve power planning for GPU data centers?",
        "What does an operator gain by using GridSignal at a GPU site?",
        "How does GridSignal help avoid reactive power events for GPU workloads?",
        "Can GridSignal help a GPU data center operator recover headroom?",
        "How does GridSignal support turbine and battery planning for GPU sites?",
        "How does GridSignal help when multiple schedulers share a GPU facility?",
        "Why should a data center operator connect GridSignal to Slurm, Kubernetes, and Ray?",
        "Explain GridSignal's benefits for someone operating a GPU data center.",
    ]

    for question in variants:
        chunks = ai_module._gridley_retrieve(question)
        assert chunks, question
        assert chunks[0]["source_id"] == "gridsignal-operator-benefits", question


def test_gridley_uses_grounded_operator_benefits_fallback_without_claude(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "Why is GridSignal useful for GPU data center operations?",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "query"
    assert body["data"]["provider"] == "deterministic_fallback"
    assert body["fallback"] is True
    assert "retrieval_sources" not in body["data"]
    assert "Grounded GridSignal guidance" in body["reply"]
    assert "The operational gap" not in body["reply"]
    assert "Slurm, Kubernetes, and Ray" in body["reply"]
    assert "does not replace or directly command" in body["reply"]
    assert not client.app.state.gridley_unmatched_queries


def test_gridley_sends_retrieved_knowledge_and_snapshot_to_claude(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict = {}

    def _fake_long_claude(question, context, _api_key):
        captured["question"] = question
        captured["context"] = context
        return "Expanded operator and investor guidance from Claude."

    with TestClient(_authenticated_app(monkeypatch)) as client:
        monkeypatch.setattr(ai_module, "_call_anthropic_gridley", _fake_long_claude)
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "How does GridSignal benefit a GPU data center operator?",
            "scenario_id": "demo-20mw",
            "tick": {"tick_index": 3, "sim_time_seconds": 15.0, "site_id": "should-not-send"},
        })

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["provider"] == "anthropic"
    assert body["fallback"] is False
    assert body["reply"] == "Expanded operator and investor guidance from Claude."
    assert "retrieval_sources" not in body["data"]
    assert captured["context"]["response_style"] == "operator_trainee_and_investor"
    assert all(set(chunk) == {"content"} for chunk in captured["context"]["retrieved_knowledge"])
    assert any("Slurm" in chunk["content"] for chunk in captured["context"]["retrieved_knowledge"])
    assert captured["context"]["authoritative_simulator_snapshot"]["tick"] == 3
    assert "site_id" not in json.dumps(captured["context"])
    assert "job_id" not in json.dumps(captured["context"])
    assert "hardware_profile" not in json.dumps(captured["context"])


def test_gridley_uses_claude_but_keeps_telemetry_questions_compact(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict = {}

    def _fake_claude(question, context, _api_key):
        captured["context"] = context
        return "The current observed site demand is 12.75 MW."

    with TestClient(_authenticated_app(monkeypatch)) as client:
        monkeypatch.setattr(ai_module, "_call_anthropic_gridley", _fake_claude)
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "What is the current site demand?",
            "scenario_id": "demo-20mw",
            "tick": {"tick_index": 8, "sim_time_seconds": 40.0, "p_demand_mw": 12.75},
        })

    body = response.json()
    assert response.status_code == 200
    assert body["data"]["provider"] == "anthropic"
    assert body["reply"] == "The current observed site demand is 12.75 MW."
    assert captured["context"]["response_style"] == "operator_compact"
    assert captured["context"]["authoritative_simulator_snapshot"]["energy_flow"]["demand_mw"] == 12.75


def test_gridley_logs_no_match_with_question_and_scenario_context(monkeypatch) -> None:
    with TestClient(_authenticated_app(monkeypatch)) as client:
        _set_session(client)
        response = client.post("/api/ai/gridley", json={
            "message": "Tell me the outside humidity",
            "scenario_id": "demo-20mw",
            "tick": {"tick_index": 2, "sim_time_seconds": 10.0},
        })
        assert response.json()["data"]["query_match"] == "no_match"

        response = client.post("/api/ai/gridley", json={
            "message": "Banana telemetry",
            "scenario_id": "demo-20mw",
        })
        body = response.json()
        assert body["data"]["query_match"] == "no_match"
        record = client.app.state.gridley_unmatched_queries[-1]
        assert record["question"] == "Banana telemetry"
        assert record["scenario_id"] == "demo-20mw"
        assert record["scenario"] == "demo-20mw"
        assert record["timestamp"]