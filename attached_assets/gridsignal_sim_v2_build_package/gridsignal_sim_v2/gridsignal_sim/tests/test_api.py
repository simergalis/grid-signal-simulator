"""
tests/test_api.py — Step 6: FastAPI endpoint acceptance tests.

These tests verify the simulator's HTTP/WebSocket API wiring added in
Step 6.  They are NOT v2.5 Addendum A acceptance tests; the TC-xx labels
that appeared in the previous draft were incorrect (see note below).

NOTE ON TC NUMBERING
--------------------
v2.5 Addendum A §16.8 / §16.9 test IDs TC-36 through TC-43 are reserved
acceptance criteria against the full production spec surface:

  TC-34  restart preserves 15-minute dedupe window (§17.1)    → deferred Step 10
  TC-35  restart preserves grace-period elapsed time           → DONE (Step 5)
  TC-36  restart yields to measured state, not reconstructed   → deferred Step 10
  TC-41  curtailment ladder ordering mandatory                 → deferred Step 9
  TC-42  C/D tiers never execute autonomously                  → deferred Step 9
  TC-43  degraded forecasts never curtail autonomously         → deferred Step 9

None of those behaviours (dedupe window, grace-period reconciliation,
curtailment ladder) exist in the codebase yet.  Applying those IDs to the
HTTP CRUD tests below would have marked them covered in Step 17's
traceability sweep.  The tests are renamed to describe what they actually
verify, and the deferred cases are noted above so Step 9 / Step 10 know
what they must close.

REST tests use FastAPI's TestClient (sync, handles lifespan correctly)
so every test gets a fresh RunManager and WebSocketHub and cannot
interfere with siblings.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _long_run_body(**overrides) -> dict:
    """A run body guaranteed to still be active during any realistic test.

    ``playback_speed=0`` is the max-speed sentinel (wall_clock_sleep = 0 s).
    At that speed 14 400 simulated seconds requires only 2 880 ticks and can
    finish in milliseconds — fast enough to be gone before a follow-up GET.
    ``end_sim_time=1e15`` is astronomically unreachable (2e14 ticks) so the
    run is always in-flight when the test inspects it.
    """
    return {
        "job_id": "api-test-job",
        "node_count": 5,
        "end_sim_time": 1e15,      # never reachable during a test
        "playback_speed": 0.0,     # max speed so the WS test gets a tick fast
        **overrides,
    }


# ---------------------------------------------------------------------------
# POST /runs returns 201 + run_id
# ---------------------------------------------------------------------------

def test_post_run_returns_201_and_run_id() -> None:
    """POST /runs must return HTTP 201 and a body containing a run_id string."""
    with TestClient(create_app()) as client:
        resp = client.post("/runs", json=_long_run_body())
    assert resp.status_code == 201
    body = resp.json()
    assert "run_id" in body
    assert isinstance(body["run_id"], str)
    assert body["run_id"].startswith("run-")


# ---------------------------------------------------------------------------
# GET /runs lists the new run
# ---------------------------------------------------------------------------

def test_get_runs_lists_active_run() -> None:
    """After POST /runs the run_id must appear in GET /runs."""
    with TestClient(create_app()) as client:
        post_resp = client.post("/runs", json=_long_run_body())
        run_id = post_resp.json()["run_id"]

        list_resp = client.get("/runs")

    assert list_resp.status_code == 200
    assert run_id in list_resp.json()["run_ids"]


# ---------------------------------------------------------------------------
# GET /runs/{run_id} reports active=True while run is in flight
# ---------------------------------------------------------------------------

def test_get_run_status_active() -> None:
    """A run that has not finished must report active=True."""
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]
        status_resp = client.get(f"/runs/{run_id}")

    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["run_id"] == run_id
    assert body["active"] is True


# ---------------------------------------------------------------------------
# GET /runs/{run_id} returns 404 for unknown run_id
# ---------------------------------------------------------------------------

def test_get_run_status_not_found() -> None:
    """A run_id that was never started must return HTTP 404."""
    with TestClient(create_app()) as client:
        resp = client.get("/runs/run-does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /runs/{run_id} cancels and removes the run
# ---------------------------------------------------------------------------

def test_delete_run_cancels_and_removes() -> None:
    """DELETE /runs/{run_id} must return 204 and remove the run
    from GET /runs."""
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]

        delete_resp = client.delete(f"/runs/{run_id}")
        assert delete_resp.status_code == 204

        list_resp = client.get("/runs")
        assert run_id not in list_resp.json()["run_ids"]


# ---------------------------------------------------------------------------
# DELETE /runs/{run_id} returns 404 for unknown run_id
# ---------------------------------------------------------------------------

def test_delete_run_not_found() -> None:
    """DELETE on an unknown run_id must return HTTP 404."""
    with TestClient(create_app()) as client:
        resp = client.delete("/runs/run-does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /runs with invalid body returns 422
# ---------------------------------------------------------------------------

def test_post_run_invalid_body_returns_422() -> None:
    """An empty body — no scenario_id, no job_id, no node_count — must be
    rejected with 422.

    After the F1 fix, job_id and node_count are Optional fields validated
    together by a model_validator.  An empty body triggers that validator,
    which raises a ValueError whose message names both missing fields.
    The response is still 422; the error detail is now a model-level
    ValidationError rather than per-field missing-field errors, so we
    check the raw response text instead of drilling into loc tuples.
    """
    with TestClient(create_app()) as client:
        resp = client.post("/runs", json={})   # no scenario_preset, job_id, or node_count
    assert resp.status_code == 422
    body_text = resp.text
    # The model_validator message is:
    #   "Fields ['job_id', 'node_count'] are required when scenario_id is not provided."
    assert "job_id" in body_text
    assert "node_count" in body_text


# ---------------------------------------------------------------------------
# WebSocket subscriber receives at least one tick in correct format
# ---------------------------------------------------------------------------

def test_websocket_subscriber_receives_tick_payload() -> None:
    """A WebSocket subscriber connected to /ws/{run_id} must receive at
    least one tick payload containing the expected fields.

    The run is started at max speed (playback_speed=0) with a long
    end_sim_time so it is still active when the WebSocket connects.

    Invariant check: wall_stamp_utc must NOT appear in the broadcast
    payload — it is a runtime-internal / persistence-only field and is
    explicitly excluded from WebSocket output (Design Spec §4.4).
    """
    with TestClient(create_app()) as client:
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]

        with client.websocket_connect(f"/ws/{run_id}") as ws:
            data = ws.receive_json()

    # Required fields from _tick_result_to_dict in runtime/run_manager.py
    required = {
        "run_id", "tick_index", "sim_time_seconds",
        "p_compute_mw", "p_cooling_mw", "p_total_mw", "net_demand_mw",
        "turbine_output_mw", "bess_output_mw", "bess_soc_fraction",
        "confidence_lower_mw", "confidence_upper_mw",
        "data_quality_tags", "insufficient_reserve_alert", "checkpoint_states",
    }
    missing = required - data.keys()
    assert not missing, f"Tick payload missing keys: {missing}"
    assert data["run_id"] == run_id
    assert isinstance(data["tick_index"], int)
    assert isinstance(data["p_total_mw"], float)

    # wall_stamp_utc must NOT be broadcast (runtime-internal only)
    assert "wall_stamp_utc" not in data, (
        "wall_stamp_utc is a runtime-internal field and must not appear "
        "in WebSocket tick payloads"
    )

    # Phase 10 §12.10 — t_emit_ns must be present and serialised as a string.
    # String serialisation prevents JavaScript safe-integer loss on long-lived hosts.
    assert "t_emit_ns" in data, "WS tick payload must include t_emit_ns for latency measurement"
    assert isinstance(data["t_emit_ns"], str), (
        "t_emit_ns must be a string in the WS payload (JS-safe: monotonic_ns "
        "exceeds Number.MAX_SAFE_INTEGER after ~104 days of host uptime)"
    )


# ---------------------------------------------------------------------------
# GET /api/session/transport — returns 200 even with no active run (TC-85)
# ---------------------------------------------------------------------------

def test_session_transport_returns_200_when_no_run_active() -> None:
    """GET /api/session/transport must return HTTP 200 with a valid response
    body even when no simulation is running (TC-85 invariant)."""
    with TestClient(create_app()) as client:
        resp = client.get("/api/session/transport")
    assert resp.status_code == 200
    body = resp.json()
    assert "measured" in body
    assert "samples" in body
    assert "ws" in body["samples"]
    assert "api" in body["samples"]


# ---------------------------------------------------------------------------
# POST /api/session/observe-tick — validation tests
# ---------------------------------------------------------------------------

def test_observe_tick_returns_400_on_missing_field() -> None:
    """POST /api/session/observe-tick with no t_emit_ns field must return 400."""
    with TestClient(create_app()) as client:
        resp = client.post("/api/session/observe-tick", json={})
    assert resp.status_code == 400
    assert resp.json()["recorded"] is False


def test_observe_tick_returns_400_on_non_integer_value() -> None:
    """POST /api/session/observe-tick with a non-numeric t_emit_ns must return 400."""
    with TestClient(create_app()) as client:
        resp = client.post("/api/session/observe-tick", json={"t_emit_ns": "not-a-number"})
    assert resp.status_code == 400
    assert resp.json()["recorded"] is False


def test_observe_tick_returns_400_on_future_timestamp() -> None:
    """A t_emit_ns in the future (server not yet at that clock value) must be rejected."""
    future_ns = time.monotonic_ns() + 5_000_000_000  # 5 s in the future
    with TestClient(create_app()) as client:
        resp = client.post("/api/session/observe-tick", json={"t_emit_ns": str(future_ns)})
    assert resp.status_code == 400
    assert resp.json()["recorded"] is False


def test_observe_tick_returns_400_on_stale_timestamp() -> None:
    """A t_emit_ns older than 30 s must be rejected (stale nonce / old value)."""
    stale_ns = time.monotonic_ns() - 31_000_000_000  # 31 s ago
    with TestClient(create_app()) as client:
        resp = client.post("/api/session/observe-tick", json={"t_emit_ns": str(stale_ns)})
    assert resp.status_code == 400
    assert resp.json()["recorded"] is False


# ---------------------------------------------------------------------------
# End-to-end: WS tick → observe-tick → GET /api/session/transport
# ---------------------------------------------------------------------------

def test_observe_tick_e2e_broadcast_to_histogram() -> None:
    """A t_emit_ns stamped on a live WS tick must be accepted by
    POST /api/session/observe-tick and increment the ws sample count
    returned by GET /api/session/transport.

    This is the end-to-end path the frontend takes:
      broadcast() stamps t_emit_ns → client echoes via POST → GET reports samples.
    """
    with TestClient(create_app()) as client:
        # Start a run at max speed so a WS tick arrives quickly.
        run_id = client.post("/runs", json=_long_run_body()).json()["run_id"]

        with client.websocket_connect(f"/ws/{run_id}") as ws:
            data = ws.receive_json()

        t_emit_ns = data.get("t_emit_ns")
        assert t_emit_ns is not None, "WS tick must carry t_emit_ns"
        assert isinstance(t_emit_ns, str), "t_emit_ns must be a string in the WS payload"

        # Baseline sample count before we echo the nonce back.
        before = client.get("/api/session/transport").json()["samples"]["ws"]

        # Simulate what the frontend does: echo the nonce to observe-tick.
        obs_resp = client.post("/api/session/observe-tick", json={"t_emit_ns": t_emit_ns})
        assert obs_resp.status_code == 200, f"observe-tick rejected: {obs_resp.json()}"
        assert obs_resp.json()["recorded"] is True

        # The transport endpoint must now show exactly one more sample.
        after = client.get("/api/session/transport").json()["samples"]["ws"]
        assert after == before + 1, (
            f"Expected {before + 1} ws samples after observe-tick, got {after}"
        )

        # Replaying the same nonce must be rejected.
        replay_resp = client.post("/api/session/observe-tick", json={"t_emit_ns": t_emit_ns})
        assert replay_resp.status_code == 400, "replayed nonce must be rejected with 400"
        assert replay_resp.json()["recorded"] is False


# ---------------------------------------------------------------------------
# Duration override: RunContext.end_sim_time must equal the request body's
# end_sim_time, not the scenario spec's stored default.
#
# Regression guard for the bug where build_run_context_from_spec read
# end_sim_time from spec_data BEFORE the operator override was written back,
# causing runs to silently stop after 300 s even when 1800 s was requested.
# ---------------------------------------------------------------------------

def _make_minimal_spec(*, end_sim_time: float = 300.0, with_corruption: bool = False):
    """Return a minimal ScenarioSpec with no solar, no LLM generators.

    Using solar_rated_mw=0 avoids generate_solar_forecast() so the test
    never makes a network call.  The spec is deliberately bare-bones to
    keep POST /runs fast.
    """
    from api.schemas import (
        BessUnitSpec,
        ScenarioSpec,
        TelemetryCorruptionConfigSpec,
        TurbineUnitSpec,
    )

    return ScenarioSpec(
        name="test-duration-override",
        description="Minimal scenario for end_sim_time override regression tests.",
        bess_units=[
            BessUnitSpec(
                asset_id="bess-0",
                rated_mw=5.0,
                usable_mwh=2.5,
                grid_forming=True,
            )
        ],
        turbine_units=[
            TurbineUnitSpec(
                asset_id="turbine-0",
                rated_mw=10.0,
                r_asset_mw_per_s=0.2,
            )
        ],
        solar_rated_mw=0.0,           # no solar → no generate_solar_forecast call
        end_sim_time=end_sim_time,
        telemetry_corruption_config=(
            TelemetryCorruptionConfigSpec(noise_sigma=0.05) if with_corruption else None
        ),
    )


def test_scenario_end_sim_time_override_honoured() -> None:
    """POST /runs with end_sim_time=1e15 must override the stored spec default (300 s).

    The scenario's spec_json stores end_sim_time=300.  The request body supplies
    end_sim_time=1e15.  RunContext.end_sim_time must equal 1e15, not 300.

    Using 1e15 guarantees the run is still active when we inspect the context
    (2e14 ticks would take far longer than any test timeout).  This makes the
    check timing-insensitive: get_context() returns None only if the run
    completed, which is impossible for end_sim_time=1e15.

    Failure mode if the bug returns: end_sim_time == 300, and get_context()
    returns None (the run completed almost instantly because spec said 300 s).
    """
    SPEC_DEFAULT_S = 300.0
    OVERRIDE_S = 1e15   # astronomically large — run is guaranteed still in-flight

    with TestClient(create_app()) as client:
        # Register a minimal scenario whose spec says end_sim_time=SPEC_DEFAULT_S.
        store = client.app.state.scenario_store
        rec = store.create(_make_minimal_spec(end_sim_time=SPEC_DEFAULT_S))
        scenario_id = rec.scenario_id

        # POST /runs with an explicit override.
        resp = client.post(
            "/runs",
            json={
                "scenario_id": scenario_id,
                "end_sim_time": OVERRIDE_S,
                "playback_speed": 0.0,
            },
        )
        assert resp.status_code == 201, f"POST /runs failed: {resp.text}"
        run_id = resp.json()["run_id"]

        # The run must still be active (end_sim_time=1e15 is unreachable).
        manager = client.app.state.run_manager
        ctx = manager.get_context(run_id)
        assert ctx is not None, (
            f"Run {run_id!r} is not active — it completed before we could inspect it. "
            f"This should be impossible for end_sim_time={OVERRIDE_S}; "
            f"the bug may have caused it to run for only {SPEC_DEFAULT_S} s instead."
        )

        # The key assertion: the override must reach RunContext, not the spec default.
        assert ctx.end_sim_time == OVERRIDE_S, (
            f"RunContext.end_sim_time is {ctx.end_sim_time}, expected {OVERRIDE_S}. "
            f"If it equals {SPEC_DEFAULT_S}, build_run_context_from_spec is reading "
            f"end_sim_time from the stored spec_data before the operator override "
            f"(spec_data['end_sim_time'] = _sim_duration) is applied."
        )
        assert ctx.end_sim_time != SPEC_DEFAULT_S, (
            f"RunContext.end_sim_time matches the spec default ({SPEC_DEFAULT_S} s), "
            f"not the requested override ({OVERRIDE_S} s)."
        )


def test_scenario_n_ticks_uses_overridden_duration() -> None:
    """generate_corruption_schedule must be called with n_ticks from the overridden
    duration, not from the scenario spec's stored end_sim_time.

    The scenario spec stores end_sim_time=300 → n_ticks_spec = 60.
    The request body supplies end_sim_time=1800 → n_ticks_override = 360.

    We patch generate_corruption_schedule so we can inspect the n_ticks argument
    it receives without depending on run timing (the patched version still returns
    a valid schedule so the run can proceed normally).

    If the bug returns: generate_corruption_schedule is called with n_ticks=60
    (spec default), and a run that actually advances 360 ticks will eventually hit
    TelemetryCorruptionSchedule.for_tick() out-of-range and raise RuntimeError.
    """
    TICK_INTERVAL_S = 5          # TICK_INTERVAL_SIM_SECONDS in run_manager.py
    SPEC_DEFAULT_S = 300.0
    OVERRIDE_S = 1800.0
    expected_n_ticks = max(1, int(OVERRIDE_S / TICK_INTERVAL_S))   # 360
    wrong_n_ticks    = max(1, int(SPEC_DEFAULT_S / TICK_INTERVAL_S))  # 60

    # We need to capture n_ticks but still return a real schedule object so the
    # run can start without errors.  Build a thin wrapper around the real function.
    from runtime.telemetry_corruption import (
        CorruptionEntry,
        TelemetryCorruptionSchedule,
        generate_corruption_schedule as _real_gen,
    )

    captured_n_ticks: list[int] = []

    def _spy_generate(n_ticks: int, **kwargs) -> TelemetryCorruptionSchedule:
        captured_n_ticks.append(n_ticks)
        return _real_gen(n_ticks, **kwargs)

    with patch(
        "api.routes.runs.generate_corruption_schedule",
        side_effect=_spy_generate,
    ):
        with TestClient(create_app()) as client:
            store = client.app.state.scenario_store
            rec = store.create(
                _make_minimal_spec(
                    end_sim_time=SPEC_DEFAULT_S,
                    with_corruption=True,
                )
            )

            resp = client.post(
                "/runs",
                json={
                    "scenario_id": rec.scenario_id,
                    "end_sim_time": OVERRIDE_S,
                    "playback_speed": 0.0,
                },
            )
            assert resp.status_code == 201, f"POST /runs failed: {resp.text}"

    # Exactly one generate_corruption_schedule call must have occurred during POST.
    assert len(captured_n_ticks) >= 1, (
        "generate_corruption_schedule was never called. "
        "Either the scenario's telemetry_corruption_config was not propagated, "
        "or the call was gated behind a condition that was not met."
    )

    actual_n_ticks = captured_n_ticks[0]
    assert actual_n_ticks == expected_n_ticks, (
        f"generate_corruption_schedule received n_ticks={actual_n_ticks}, "
        f"expected {expected_n_ticks} (= {OVERRIDE_S} s / {TICK_INTERVAL_S} s per tick). "
        f"{'BUG: n_ticks equals the spec default — _sim_duration was not applied before _n_ticks was computed.' if actual_n_ticks == wrong_n_ticks else ''}"
    )


# ---------------------------------------------------------------------------
# POST /scenarios rejects invalid hot_start_s / warm_start_s / cold_start_s ordering
# ---------------------------------------------------------------------------

def _minimal_scenario_body(**turbine_overrides) -> dict:
    """Return a minimal ScenarioSpec dict for POST /scenarios.

    Supplies the minimum required fields so the request reaches schema
    validation.  ``turbine_overrides`` are merged into the single turbine
    unit's dict to allow per-test field injection.
    """
    turbine: dict = {
        "asset_id": "turbine-0",
        "rated_mw": 10.0,
        "r_asset_mw_per_s": 0.2,
    }
    turbine.update(turbine_overrides)
    return {
        "name": "ordering-test-scenario",
        "description": "Minimal scenario for start-duration ordering tests.",
        "turbine_units": [turbine],
        "bess_units": [
            {
                "asset_id": "bess-0",
                "rated_mw": 5.0,
                "usable_mwh": 2.5,
                "grid_forming": True,
            }
        ],
        "solar_rated_mw": 0.0,
    }


def test_post_scenarios_rejects_cold_faster_than_hot() -> None:
    """POST /scenarios must return 422 when cold_start_s < hot_start_s.

    cold_start_s=100, warm_start_s=200, hot_start_s=300 violates the ordering
    constraint (a cold unit would sync faster than a hot one).  The Pydantic
    model_validator on TurbineUnitSpec must catch this and FastAPI must surface
    it as a 422 Unprocessable Entity response.
    """
    body = _minimal_scenario_body(
        cold_start_s=100.0,   # cold is faster than hot — nonsensical
        warm_start_s=200.0,
        hot_start_s=300.0,
    )
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 422, (
        f"Expected 422 for invalid start-duration ordering, got {resp.status_code}. "
        f"Body: {resp.text}"
    )
    # The error detail must mention the ordering violation so operators can diagnose it.
    detail = resp.text.lower()
    assert any(kw in detail for kw in ("hot_start_s", "warm_start_s", "cold_start_s", "ordering")), (
        f"422 response detail does not mention start-duration fields: {resp.text}"
    )


def test_post_scenarios_rejects_warm_faster_than_hot() -> None:
    """POST /scenarios must return 422 when warm_start_s <= hot_start_s.

    hot_start_s=500, warm_start_s=300, cold_start_s=900 violates
    hot_start_s < warm_start_s.
    """
    body = _minimal_scenario_body(
        hot_start_s=500.0,
        warm_start_s=300.0,   # warm faster than hot — nonsensical
        cold_start_s=900.0,
    )
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 422, (
        f"Expected 422 for warm_start_s < hot_start_s, got {resp.status_code}. "
        f"Body: {resp.text}"
    )


def test_post_scenarios_rejects_cold_equal_to_warm() -> None:
    """POST /scenarios must return 422 when cold_start_s == warm_start_s.

    Equal values do not satisfy the strict ordering; cold must be strictly
    greater than warm.
    """
    body = _minimal_scenario_body(
        hot_start_s=300.0,
        warm_start_s=600.0,
        cold_start_s=600.0,   # equal — not strictly greater
    )
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 422, (
        f"Expected 422 for cold_start_s == warm_start_s, got {resp.status_code}. "
        f"Body: {resp.text}"
    )


def test_post_scenarios_accepts_valid_start_duration_ordering() -> None:
    """POST /scenarios must return 201 when hot_start_s < warm_start_s < cold_start_s.

    300 < 600 < 900 is a physically sensible ordering; the validator must
    accept it and the scenario store must persist the record.
    """
    body = _minimal_scenario_body(
        hot_start_s=300.0,
        warm_start_s=600.0,
        cold_start_s=900.0,
    )
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 201, (
        f"Expected 201 for valid start-duration ordering, got {resp.status_code}. "
        f"Body: {resp.text}"
    )
    assert "scenario_id" in resp.json(), (
        f"Response missing scenario_id: {resp.text}"
    )


def test_post_scenarios_rejects_hot_start_larger_than_defaults() -> None:
    """POST /scenarios must return 422 when hot_start_s alone exceeds the default warm_start_s.

    Supplying only hot_start_s=1000 leaves warm=600 (default) and cold=900 (default).
    The effective triplet is hot=1000, warm=600, cold=900 — hot > warm — which
    violates the ordering constraint and must be caught at schema time.
    """
    body = _minimal_scenario_body(
        hot_start_s=1000.0,  # exceeds default warm (600) — violates hot < warm
    )
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 422, (
        f"Expected 422 for hot_start_s=1000 (> default warm_start_s=600), "
        f"got {resp.status_code}. Body: {resp.text}"
    )
    # The error detail must cite the effective values so the author knows what to fix.
    assert "default" in resp.text.lower() or "effective" in resp.text.lower(), (
        f"422 detail should mention effective/default values: {resp.text}"
    )


def test_post_scenarios_rejects_cold_start_below_default_warm() -> None:
    """POST /scenarios must return 422 when cold_start_s alone is shorter than the default warm_start_s.

    Supplying only cold_start_s=100 leaves warm=600 (default) and hot=300 (default).
    The effective triplet is hot=300, warm=600, cold=100 — warm > cold — rejected.
    """
    body = _minimal_scenario_body(
        cold_start_s=100.0,  # shorter than default warm (600) — violates warm < cold
    )
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 422, (
        f"Expected 422 for cold_start_s=100 (< default warm_start_s=600), "
        f"got {resp.status_code}. Body: {resp.text}"
    )


def test_post_scenarios_accepts_valid_cold_only_override() -> None:
    """POST /scenarios must return 201 when only cold_start_s is set and it exceeds default warm.

    cold_start_s=1200 with warm=null (default 600) and hot=null (default 300) gives
    effective hot=300 < warm=600 < cold=1200 — valid ordering, must be accepted.
    """
    body = _minimal_scenario_body(
        cold_start_s=1200.0,  # longer than default warm (600) — valid
    )
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 201, (
        f"Expected 201 for cold_start_s=1200 (> default warm_start_s=600), "
        f"got {resp.status_code}. Body: {resp.text}"
    )
    assert "scenario_id" in resp.json()


def test_post_scenarios_accepts_no_start_duration_overrides() -> None:
    """POST /scenarios must return 201 when all start-duration fields are omitted.

    No override means all three are None.  The validator must skip the check
    entirely — using defaults (300 < 600 < 900) which trivially satisfy the invariant.
    """
    body = _minimal_scenario_body()  # no cold/warm/hot overrides
    with TestClient(create_app()) as client:
        resp = client.post("/scenarios", json=body)
    assert resp.status_code == 201, (
        f"Expected 201 when no start-duration fields are set, "
        f"got {resp.status_code}. Body: {resp.text}"
    )
    assert "scenario_id" in resp.json()
