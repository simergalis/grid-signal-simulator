"""
Acceptance tests TC-77 .. TC-85.

Engine Spec Addendum A, new section 16.14 (Simulator fabric model and
corroboration substrate). Each test name carries its TC id so a failure in CI
names the acceptance row directly rather than an internal function.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fabric import FabricModel, InstrumentPlane, Job, StressorSet  # noqa: E402
from fabric.scenario import Scenario, metrics, run  # noqa: E402

CFG = ROOT / "config"
SCN = CFG / "scenarios"


def load(scenario_id: str) -> Scenario:
    """Load a fabric regression scenario by its public scenario ID.

    The scenario files retain their historical filenames for source-link and
    archive compatibility, while their public IDs are descriptive.
    """
    for path in SCN.glob("*.json"):
        if json.loads(path.read_text()).get("scenario_id") == scenario_id:
            return Scenario.load(path, config_dir=CFG)
    raise FileNotFoundError(f"Fabric regression scenario not found: {scenario_id}")


@pytest.fixture(scope="module")
def baseline_run():
    return run(load("regression-test-healthy-training-baseline"))


# ---------------------------------------------------------------- TC-77 ----


def test_tc77_fabric_stream_is_reproducible():
    """Two runs of the same scenario at the same seed produce byte-identical
    NetworkTelemetry streams, including event ordering and derived metrics."""
    sc = load("regression-test-checkpoint-storage-hotspot")
    a, b = run(sc), run(sc)

    assert len(a.ticks) == len(b.ticks)
    for ta, tb in zip(a.ticks, b.ticks):
        assert ta.telemetry == tb.telemetry, f"telemetry diverged at tick {ta.tick}"
        assert [
            (s.link_id, s.u, s.loss_p, s.congested, s.headroom_bps) for s in ta.links
        ] == [
            (s.link_id, s.u, s.loss_p, s.congested, s.headroom_bps) for s in tb.links
        ]
        assert ta.control.l_total_ms == tb.control.l_total_ms
        assert ta.discrimination == tb.discrimination


def test_tc77b_tick_is_addressable_without_replay():
    """Counter-based addressing means a draw at tick n does not depend on
    ticks 0..n-1 having been evaluated (12.7 point 3)."""
    from fabric import prng

    direct = prng.uniform(42, "fabric.ecmp", 500, "job-alpha/ckpt/f3")
    for t in range(500):
        prng.uniform(42, "fabric.ecmp", t, "job-alpha/ckpt/f3")
    assert prng.uniform(42, "fabric.ecmp", 500, "job-alpha/ckpt/f3") == direct


# ---------------------------------------------------------------- TC-78 ----


def test_tc78_new_substream_does_not_perturb_existing_ones():
    """Adding a substream must not shift any pre-existing draw. This is the
    property a stateful generator does not have, and the reason 12.7 mandates
    tuple addressing."""
    from fabric import prng

    before = [
        prng.uniform(42, "fabric.ecmp", t, f"flow{i}")
        for t in range(20)
        for i in range(5)
    ]

    original = set(prng.SUBSTREAMS)
    prng.SUBSTREAMS = frozenset(original | {"fabric.newthing"})
    try:
        for t in range(20):
            prng.uniform(42, "fabric.newthing", t, "whatever")
        after = [
            prng.uniform(42, "fabric.ecmp", t, f"flow{i}")
            for t in range(20)
            for i in range(5)
        ]
    finally:
        prng.SUBSTREAMS = frozenset(original)

    assert before == after


def test_tc78b_undeclared_substream_is_rejected():
    from fabric import prng

    with pytest.raises(ValueError, match="undeclared PRNG substream"):
        prng.uniform(42, "fabric.typo", 0, "x")


# ---------------------------------------------------------------- TC-79 ----


def test_tc79_derived_metrics_are_mutually_consistent(baseline_run):
    """carried + headroom == capacity exactly, on every link, every tick; and
    `congested` is true only where u >= 0.85 has held for >= 2 ticks; and no
    link reports loss below the knee.

    Note the identity is stated on CARRIED, not offered. Under oversubscription
    demand may exceed capacity, and `offered + headroom == capacity` is then
    false by construction. See the spec correction note."""
    u_cong = 0.85
    u_knee = 0.90
    prev_over = {}

    for tr in baseline_run.ticks:
        for s in tr.links:
            assert s.carried_bps + s.headroom_bps == pytest.approx(
                s.capacity_bps, rel=1e-12, abs=1e-6
            ), f"identity broken on {s.link_id} at tick {s.tick}"

            if s.congested:
                assert s.u >= u_cong, f"{s.link_id} congested below threshold"
                assert prev_over.get(s.link_id, False), (
                    f"{s.link_id} congested without a sustained prior tick"
                )
            if s.u < u_knee and s.loss_p > 0:
                pytest.fail(f"{s.link_id} reports loss at u={s.u:.3f}, below the knee")

            prev_over[s.link_id] = s.u >= u_cong


# ---------------------------------------------------------------- TC-80 ----


def test_tc80_loss_is_monotonic_and_knee_shaped():
    """Sweep u from 0.0 to 1.0 on one link: zero below 0.90, non-decreasing
    throughout, reaching P_MAX at saturation."""
    m = FabricModel.from_files(
        CFG / "fabric_fixture_default.json",
        CFG / "fabric_constants.json",
        CFG / "workload_traffic_profiles.json",
        seed=42,
    )
    link = m.topology.fabrics["storage"].links[0]
    p_max = m.k("link_metrics", "P_MAX")

    losses = []
    for i in range(0, 101):
        u = i / 100.0
        st = m._link_state(link, u * link.capacity_bps, i, False, None, None)
        losses.append(st.loss_p)
        if u < 0.90:
            assert st.loss_p == 0.0, f"loss at u={u:.2f} below the knee"

    assert all(b >= a - 1e-15 for a, b in zip(losses, losses[1:])), "loss not monotonic"
    assert losses[-1] == pytest.approx(p_max, rel=1e-9)


# ---------------------------------------------------------------- TC-81 ----


def test_tc81_checkpoint_produces_the_discriminating_signature():
    """Compute quiesces, storage carries sustained write elephants, and at
    least one storage uplink congests from ECMP collision."""
    r = run(load("regression-test-checkpoint-storage-hotspot"))
    ck = [
        (t, s)
        for t, s, p in zip(r.ticks, r.samples, r.phases)
        if p == "checkpoint"
    ]
    assert ck, "scenario never reached the checkpoint phase"

    assert max(s["congested_links.storage"] for _, s in ck) >= 1
    assert max(s["mean_u.compute"] for _, s in ck) < 0.05
    assert any(
        t.discrimination["verdict"] == "checkpoint_corroborated" for t, _ in ck
    )
    assert any(
        e.get("elephant_flow_present") for t, _ in ck for e in t.telemetry
    ), "elephant flow class not emitted at current tier"


# ---------------------------------------------------------------- TC-82 ----


def test_tc82_job_end_withholds_corroboration():
    """The compute fabric quiesces identically to TC-81 and no sustained
    storage burst appears. The corroboration path does not resolve.

    This is the row that matters commercially: a corroboration path firing on
    job end either ramps turbines down into a checkpoint or holds staging
    through a genuine completion."""
    r = run(load("regression-test-clean-job-termination"))
    je = [
        (t, s)
        for t, s, p in zip(r.ticks, r.samples, r.phases)
        if p == "job_end"
    ]
    assert je, "scenario never reached the job_end phase"

    assert max(s["mean_u.compute"] for _, s in je) < 0.05, "compute did not quiesce"
    assert not any(
        t.discrimination["verdict"] == "checkpoint_corroborated" for t, _ in je
    )
    assert not any(
        t.discrimination["verdict"] == "checkpoint_corroborated" for t in r.ticks
    ), "corroboration fired somewhere in a scenario containing no checkpoint"


def test_tc82b_weight_load_read_does_not_corroborate():
    """Weight load at job start is an elephant flow of comparable size to a
    checkpoint. Direction is what separates them; a rate-only test would
    corroborate a checkpoint at the moment the job begins."""
    r = run(load("regression-test-healthy-training-baseline"))
    wl = [
        t
        for t, p in zip(r.ticks, r.phases)
        if p == "starting.weight_load"
    ]
    assert wl, "scenario never reached weight load"
    assert not any(
        t.discrimination["verdict"] == "checkpoint_corroborated" for t in wl
    )


# ---------------------------------------------------------------- TC-83 ----


def test_tc83_corroboration_cannot_override_higher_precedence():
    """The fabric model emits a verdict; it does not emit a classification.
    The record carries the precedence rule and the verdict is advisory by
    construction -- there is no code path by which it reaches dispatch."""
    r = run(load("regression-test-checkpoint-storage-hotspot"))
    corr = [
        t for t in r.ticks
        if t.discrimination["verdict"] == "checkpoint_corroborated"
    ]
    assert corr

    d = corr[0].discrimination
    assert "scheduler event > power-shape heuristic > network corroboration" in (
        d["precedence_note"]
    )
    # The verdict vocabulary contains no term that asserts a classification.
    verdicts = {t.discrimination["verdict"] for t in r.ticks}
    assert verdicts <= {
        "checkpoint_corroborated",
        "no_corroboration",
        "not_applicable",
        "unavailable",
    }
    assert "checkpoint_confirmed" not in verdicts
    assert "job_end_confirmed" not in verdicts


# ---------------------------------------------------------------- TC-84 ----


def test_tc84_control_path_breaches_nfr2_without_compute_loss():
    """L_control exceeds 2000 ms; the compute fabric is untouched; and the
    breach is attributed to the correct term."""
    r = run(load("regression-test-control-path-latency-isolation"))

    breaches = [t for t in r.ticks if t.control.breached]
    assert breaches, "no NFR-2 breach produced under stress"

    assert max(s["loss.compute"] for s in r.samples) == 0.0
    assert max(t.control.l_gateway_ms for t in breaches) > 1000.0
    assert all(t.control.dominant_term != "fabric" for t in breaches), (
        "fabric transit dominating the budget indicates the latency model has drifted"
    )
    assert all(t.control.budget_ms == 2000.0 for t in r.ticks)


def test_tc84b_baseline_holds_the_budget_with_margin(baseline_run):
    worst = max(t.control.l_total_ms for t in baseline_run.ticks)
    assert worst < 2000.0
    assert worst < 1000.0, (
        "unstressed control latency should sit far inside the budget; breaking "
        "NFR-2 must require a real stressor, not a pessimistic default"
    )


# ---------------------------------------------------------------- TC-85 ----


def test_tc85_session_transport_is_measured_not_simulated():
    """WS tick latency and API round-trip continue to report live measured
    values while the simulation is stopped. A zero, a frozen value, or a value
    derived from the simulation clock fails."""
    inst = InstrumentPlane()

    # Simulation is not running at all. The instrument plane must not care.
    for _ in range(12):
        payload = inst.stamp_tick({"tick": 0})
        # t_emit_ns is now a string (JS-safe serialisation); observe_tick accepts both.
        assert isinstance(payload["t_emit_ns"], str), "stamp_tick must return a string"
        time.sleep(0.002)
        inst.observe_tick(payload["t_emit_ns"])
        inst.observe_api(3.5)

    view = inst.modal_view()
    assert view["measured"] is True
    assert view["samples"]["ws"] == 12
    assert view["ws_tick_latency_ms"] is not None
    assert view["ws_tick_latency_ms"] > 0.0, "a zero here is a synthesised value"


def test_observe_tick_rejects_future_timestamp():
    """A t_emit_ns in the future must be rejected (fabrication / clock skew)."""
    inst = InstrumentPlane()
    future_ns = time.monotonic_ns() + 5_000_000_000  # 5 s in the future
    accepted = inst.observe_tick(future_ns)
    assert accepted is False
    assert inst.modal_view()["samples"]["ws"] == 0


def test_observe_tick_rejects_stale_timestamp():
    """A t_emit_ns older than 30 s must be rejected (stale / old nonce)."""
    inst = InstrumentPlane()
    stale_ns = time.monotonic_ns() - 31_000_000_000  # 31 s ago
    accepted = inst.observe_tick(stale_ns)
    assert accepted is False
    assert inst.modal_view()["samples"]["ws"] == 0


def test_observe_tick_rejects_replay():
    """The same nonce must be accepted at most once (replay protection)."""
    inst = InstrumentPlane()
    payload = inst.stamp_tick({"tick": 0})
    time.sleep(0.002)
    t = payload["t_emit_ns"]

    first = inst.observe_tick(t)
    second = inst.observe_tick(t)

    assert first is True, "first observation of a valid nonce must be accepted"
    assert second is False, "replayed nonce must be rejected"
    assert inst.modal_view()["samples"]["ws"] == 1, "only one sample from one nonce"


def test_observe_tick_accepts_string_input():
    """stamp_tick serialises t_emit_ns as a string; observe_tick must accept it."""
    inst = InstrumentPlane()
    payload = inst.stamp_tick({"tick": 0})
    assert isinstance(payload["t_emit_ns"], str)
    time.sleep(0.001)
    accepted = inst.observe_tick(payload["t_emit_ns"])  # string, not int
    assert accepted is True
    assert inst.modal_view()["samples"]["ws"] == 1


def test_tc85b_instrument_plane_cannot_read_the_simulation_clock():
    """Structural guard. If a future edit gives this module access to sim
    time, this test names the defect."""
    import fabric.instrument as instrument

    src = Path(instrument.__file__).read_text()
    for forbidden in ("from .model", "from .traffic", "sim_time", "FabricModel"):
        assert forbidden not in src, (
            f"instrument plane references {forbidden!r}; session transport "
            f"metrics must not be derivable from the simulation"
        )


# ---------------------------------------------------------------- TC-86 ----


def test_tc86_ws_tick_latency_populates_after_run_starts() -> None:
    """Integration test: the complete latency path populates ws_tick_latency_ms.

    Supplements TC-85 (unit test) by covering the entire HTTP wiring:
      broadcast() stamps t_emit_ns → client echoes it to
      POST /api/session/observe-tick → GET /api/session/transport
      returns a non-zero ws_tick_latency_ms.

    Three ticks are delivered and echoed so the ring buffer has enough
    samples to produce a non-None percentile.  This catches regressions
    where the observe-tick endpoint is de-registered, or the WS broadcast
    stops stamping t_emit_ns, without touching TC-85 (which stays unit-level).
    """
    from fastapi.testclient import TestClient
    from api.app import create_app

    with TestClient(create_app()) as client:
        # Start a run at max speed so WS ticks arrive immediately.
        run_body = {
            "job_id": "tc86-latency-test",
            "node_count": 5,
            "end_sim_time": 1e15,   # never reached during the test
            "playback_speed": 0.0,  # max-speed sentinel — wall_clock_sleep = 0
        }
        run_id = client.post("/runs", json=run_body).json()["run_id"]

        # Collect 3 ticks from the WS stream, capturing t_emit_ns from each.
        t_emit_values: list[str] = []
        with client.websocket_connect(f"/ws/{run_id}") as ws:
            for _ in range(3):
                data = ws.receive_json()
                t_emit_ns = data.get("t_emit_ns")
                assert t_emit_ns is not None, (
                    "WS tick must carry t_emit_ns (broadcast() must stamp it)"
                )
                assert isinstance(t_emit_ns, str), (
                    "t_emit_ns must be a string in the WS payload "
                    "(JS-safe: monotonic_ns exceeds Number.MAX_SAFE_INTEGER "
                    "after ~104 days of host uptime)"
                )
                t_emit_values.append(t_emit_ns)

        # Echo each nonce back to POST /api/session/observe-tick, exactly
        # as the frontend does after receiving the tick payload.
        for t_emit_ns in t_emit_values:
            obs_resp = client.post(
                "/api/session/observe-tick", json={"t_emit_ns": t_emit_ns}
            )
            assert obs_resp.status_code == 200, (
                f"observe-tick rejected a valid nonce {t_emit_ns!r}: "
                f"{obs_resp.json()}"
            )
            assert obs_resp.json()["recorded"] is True, (
                f"observe-tick returned recorded=False for nonce {t_emit_ns!r}"
            )

        # GET /api/session/transport must now show the echoed samples and a
        # non-zero ws_tick_latency_ms (p50 of the ring buffer).
        transport = client.get("/api/session/transport").json()

        assert transport["samples"]["ws"] >= 3, (
            f"Expected at least 3 ws samples after echoing 3 ticks, "
            f"got {transport['samples']['ws']}"
        )
        assert transport["ws_tick_latency_ms"] is not None, (
            "ws_tick_latency_ms must not be None after valid observations"
        )
        assert transport["ws_tick_latency_ms"] > 0, (
            f"ws_tick_latency_ms must be > 0 after real round-trips, "
            f"got {transport['ws_tick_latency_ms']}"
        )


# ------------------------------------------------------- scenario suite ----


@pytest.mark.parametrize(
    "name",
    [
        "regression-test-healthy-training-baseline",
        "regression-test-checkpoint-storage-hotspot",
        "regression-test-clean-job-termination",
        "regression-test-control-path-latency-isolation",
        "regression-test-gray-link-failure",
        "regression-test-degraded-fabric-observability",
        "regression-test-slow-checkpoint",
        "regression-test-transceiver-degradation",
    ],
)
def test_scenario_assertions(name):
    report = run(load(name)).report()
    failed = [a for a in report["assertions"] if not a["passed"]]
    assert not failed, "\n".join(
        f"{a['id']}: {a.get('metric')} {a.get('expected')} "
        f"observed={a.get('observed')} -- {a.get('description', '')}"
        for a in failed
    )
