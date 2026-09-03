"""
tests/test_step12_advisory.py — Step 12: advisory scaffolding.

TC-29 — no site_id, job_id, customer identifier, or hardware SKU name in any
         outbound request body.  Captured at the wire (serialised EvidenceWindow
         JSON), not the call site.

TC-30 — out-of-bounds proposal auto-rejected at generation, never reaching a
         reviewer.

LP-1  — with both MISTRAL_API_KEY and ANTHROPIC_API_KEY absent the entire
         application runs as a deterministic simulator with no agents and NO
         ERRORS.  Verified through configuration (monkeypatching), not failure.

Hold-question tests:
  • What bounds a proposal's lifetime?
  • What makes a state terminal?
  • What happens if the reviewing event never arrives?
"""
from __future__ import annotations

import dataclasses
import json
import os
from typing import Optional

import pytest

from core.deident import (
    EvidenceWindow, MAX_BINS, assert_no_pii, deidentify,
)
from core.models import (
    BessConfig, SiteConfig, TurbineConfig,
    IslandMode, OperatingTier,
)
from runtime.advisory_gate import (
    DEFAULT_PROPOSAL_LIFETIME_S,
    MAX_CONFIDENCE,
    MAX_PROPOSAL_LIFETIME_S,
    MAX_PROPOSAL_MW,
    MIN_CONFIDENCE,
    MIN_PROPOSAL_LIFETIME_S,
    MIN_PROPOSAL_MW,
    TERMINAL_STATES,
    VALID_PROPOSAL_KINDS,
    AdvisoryGate,
    Proposal,
    ProposalState,
    make_proposal,
)
from runtime.advisory_principal import AdvisoryPrincipal
from runtime.advisory_router import AdvisoryRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_tick(
    p_demand_mw: float = 10.0,
    turbine_mw: float = 8.0,
    bess_mw: float = 2.0,
    sim_time_seconds: float = 5.0,
    alert: bool = False,
) -> object:
    """Return a minimal TickResult-compatible object for deidentify() tests."""
    # Use a plain namespace so we don't need a full SimulationState.
    class FakeTick:
        pass
    r = FakeTick()
    r.p_demand_mw           = p_demand_mw
    r.turbine_output_mw    = turbine_mw
    r.bess_output_mw       = bess_mw
    r.sim_time_seconds     = sim_time_seconds
    r.insufficient_reserve_alert = alert
    r.curtailment_proposal_tiers = ()
    return r


def _make_ticks(n: int, *, base_time: float = 5.0, dt: float = 5.0) -> list:
    return [
        _make_tick(
            p_demand_mw=10.0 + i * 0.1,
            sim_time_seconds=base_time + i * dt,
        )
        for i in range(n)
    ]


def _make_proposal(
    kind: str = "curtailment",
    impact_mw: float = 2.0,
    confidence: float = 0.8,
    created_at: float = 0.0,
    lifetime_s: float = DEFAULT_PROPOSAL_LIFETIME_S,
) -> Proposal:
    return make_proposal(
        kind=kind,
        estimated_impact_mw=impact_mw,
        confidence=confidence,
        reasoning="unit_test_reasoning",
        created_at_sim_time=created_at,
        lifetime_s=lifetime_s,
    )


# ---------------------------------------------------------------------------
# TC-29: no PII in the wire payload
# ---------------------------------------------------------------------------

class TestTC29NoPII:
    """TC-29: deidentify() must strip site_id, job_id, and hardware SKU names
    from the wire payload.  Captured at the serialised JSON level.
    """

    SITE_ID = "site-customer-acme-corp-0042"
    JOB_ID  = "job-secret-training-run-XYZ"
    SKUS    = frozenset({"enterprise_8gpu_air", "highend_a100_nvlink"})

    def _deident(self, n: int = 30) -> EvidenceWindow:
        ticks = _make_ticks(n)
        return deidentify(
            ticks,
            site_id=self.SITE_ID,
            job_id=self.JOB_ID,
            hardware_profile_ids=self.SKUS,
        )

    def test_tc29_wire_has_no_site_id(self) -> None:
        window = self._deident()
        wire = json.dumps(dataclasses.asdict(window))
        assert self.SITE_ID not in wire, (
            f"TC-29: site_id {self.SITE_ID!r} must not appear in wire payload"
        )

    def test_tc29_wire_has_no_job_id(self) -> None:
        window = self._deident()
        wire = json.dumps(dataclasses.asdict(window))
        assert self.JOB_ID not in wire, (
            f"TC-29: job_id {self.JOB_ID!r} must not appear in wire payload"
        )

    def test_tc29_wire_has_no_sku_name(self) -> None:
        window = self._deident()
        wire = json.dumps(dataclasses.asdict(window))
        for sku in self.SKUS:
            assert sku not in wire, (
                f"TC-29: hardware SKU {sku!r} must not appear in wire payload"
            )

    def test_tc29_wire_has_no_customer_word(self) -> None:
        """TC-29: even substrings of compound identifiers must be absent."""
        window = self._deident()
        wire = json.dumps(dataclasses.asdict(window))
        # "acme" appears in SITE_ID; assert_no_pii checks 4+ char words.
        assert "acme" not in wire.lower(), (
            "TC-29: word fragment 'acme' from site_id must not appear in wire"
        )

    def test_tc29_assert_no_pii_passes_for_clean_window(self) -> None:
        """assert_no_pii() must not raise for a clean EvidenceWindow."""
        window = self._deident()
        # Must not raise:
        assert_no_pii(
            window,
            site_id=self.SITE_ID,
            job_id=self.JOB_ID,
            hardware_profile_ids=self.SKUS,
        )

    def test_tc29_assert_no_pii_raises_on_leak(self) -> None:
        """assert_no_pii() must raise AssertionError when PII leaks in."""
        window = self._deident()
        # Manually inject PII into the anomaly flags (simulating a bug).
        window.anomalies.append(self.SITE_ID)
        with pytest.raises(AssertionError, match="TC-29 VIOLATION"):
            assert_no_pii(
                window,
                site_id=self.SITE_ID,
                job_id=self.JOB_ID,
                hardware_profile_ids=self.SKUS,
            )

    def test_tc29_empty_ticks_produces_empty_window(self) -> None:
        """TC-29: empty tick list produces an empty window with no PII."""
        window = deidentify(
            [], site_id=self.SITE_ID, job_id=self.JOB_ID,
            hardware_profile_ids=self.SKUS,
        )
        wire = json.dumps(dataclasses.asdict(window))
        assert self.SITE_ID not in wire
        assert self.JOB_ID not in wire

    def test_tc29_bin_count_at_most_60(self) -> None:
        """Aggregation: at most MAX_BINS=60 bins regardless of tick count."""
        ticks = _make_ticks(300)
        window = deidentify(ticks, site_id="s", job_id="j")
        assert window.bin_count <= MAX_BINS, (
            f"TC-29/aggregation: bin_count={window.bin_count} exceeds MAX_BINS={MAX_BINS}"
        )

    def test_tc29_fewer_ticks_than_bins_uses_one_per_bin(self) -> None:
        """Aggregation: when ticks < MAX_BINS, bin_count == tick_count."""
        ticks = _make_ticks(20)
        window = deidentify(ticks, site_id="s", job_id="j")
        assert window.bin_count == 20

    def test_tc29_anomaly_consecutive_alerts(self) -> None:
        """Aggregation: >= 3 consecutive alert ticks → 'consecutive_alerts_N' flag."""
        ticks = _make_ticks(10)
        for i in range(3, 7):
            ticks[i].insufficient_reserve_alert = True
        window = deidentify(ticks, site_id="s", job_id="j")
        consec = [a for a in window.anomalies if a.startswith("consecutive_alerts_")]
        assert consec, (
            "Aggregation: >= 3 consecutive alerts must produce 'consecutive_alerts_N' anomaly"
        )

    def test_tc29_anomaly_curtailment_escalated(self) -> None:
        """Aggregation: curtailment proposals present → 'curtailment_escalated' flag."""
        ticks = _make_ticks(5)
        ticks[2].curtailment_proposal_tiers = ("a_defer",)
        window = deidentify(ticks, site_id="s", job_id="j")
        assert "curtailment_escalated" in window.anomalies


# ---------------------------------------------------------------------------
# TC-30: out-of-bounds proposal rejected at generation
# ---------------------------------------------------------------------------

class TestTC30OOBRejection:
    """TC-30: out-of-bounds proposals must be auto-rejected by the gate at
    generation time — they must never reach a reviewer.
    """

    def _gate(self) -> AdvisoryGate:
        return AdvisoryGate()

    # ── Bound violations ─────────────────────────────────────────────────

    def test_tc30_impact_above_max_rejected(self) -> None:
        gate = self._gate()
        p = _make_proposal(impact_mw=MAX_PROPOSAL_MW + 0.001)
        result = gate.validate(p)
        assert not result, "TC-30: impact above MAX_PROPOSAL_MW must be rejected"
        assert p.state == ProposalState.REJECTED
        assert p.rejection_reason and "TC-30" in p.rejection_reason

    def test_tc30_impact_below_min_rejected(self) -> None:
        gate = self._gate()
        p = _make_proposal(impact_mw=MIN_PROPOSAL_MW - 0.001)
        result = gate.validate(p)
        assert not result
        assert p.state == ProposalState.REJECTED

    def test_tc30_confidence_above_1_rejected(self) -> None:
        gate = self._gate()
        p = _make_proposal(confidence=1.001)
        result = gate.validate(p)
        assert not result
        assert p.state == ProposalState.REJECTED

    def test_tc30_confidence_below_0_rejected(self) -> None:
        gate = self._gate()
        p = _make_proposal(confidence=-0.001)
        result = gate.validate(p)
        assert not result
        assert p.state == ProposalState.REJECTED

    def test_tc30_unknown_kind_rejected(self) -> None:
        gate = self._gate()
        p = _make_proposal(kind="direct_trip_relay")
        result = gate.validate(p)
        assert not result, "TC-30: unknown proposal kind must be rejected"
        assert p.state == ProposalState.REJECTED

    def test_tc30_lifetime_too_short_rejected(self) -> None:
        """Lifetime below MIN_PROPOSAL_LIFETIME_S violates TC-30."""
        gate = self._gate()
        p = Proposal(
            kind="curtailment", estimated_impact_mw=2.0, confidence=0.8,
            reasoning="test", created_at_sim_time=0.0,
            expires_at_sim_time=10.0,   # 10 s < MIN (30 s)
        )
        assert not gate.validate(p)
        assert p.state == ProposalState.REJECTED

    def test_tc30_lifetime_too_long_rejected(self) -> None:
        gate = self._gate()
        p = Proposal(
            kind="curtailment", estimated_impact_mw=2.0, confidence=0.8,
            reasoning="test", created_at_sim_time=0.0,
            expires_at_sim_time=MAX_PROPOSAL_LIFETIME_S + 1.0,
        )
        assert not gate.validate(p)
        assert p.state == ProposalState.REJECTED

    def test_tc30_valid_proposal_passes(self) -> None:
        gate = self._gate()
        p = _make_proposal()
        assert gate.validate(p), "TC-30: valid proposal must pass the gate"
        assert p.state == ProposalState.PENDING

    def test_tc30_all_valid_kinds_pass(self) -> None:
        gate = self._gate()
        for kind in VALID_PROPOSAL_KINDS:
            p = _make_proposal(kind=kind)
            assert gate.validate(p), f"TC-30: kind={kind!r} must pass the gate"

    def test_tc30_rejected_never_reaches_pending(self) -> None:
        """TC-30 core: rejected proposals are never in pending_proposals()."""
        gate = self._gate()
        bad = _make_proposal(impact_mw=MAX_PROPOSAL_MW + 1.0)
        gate.validate(bad)
        assert bad not in gate.pending_proposals(), (
            "TC-30: rejected proposals must never appear in pending_proposals()"
        )

    # ── make_proposal lifetime clamping ──────────────────────────────────

    def test_make_proposal_clamps_lifetime_to_min(self) -> None:
        p = make_proposal(
            kind="curtailment", estimated_impact_mw=2.0, confidence=0.8,
            reasoning="test", created_at_sim_time=100.0, lifetime_s=1.0,
        )
        actual_lifetime = p.expires_at_sim_time - p.created_at_sim_time
        assert actual_lifetime == pytest.approx(MIN_PROPOSAL_LIFETIME_S), (
            "make_proposal must clamp lifetime to MIN_PROPOSAL_LIFETIME_S"
        )

    def test_make_proposal_clamps_lifetime_to_max(self) -> None:
        p = make_proposal(
            kind="curtailment", estimated_impact_mw=2.0, confidence=0.8,
            reasoning="test", created_at_sim_time=0.0,
            lifetime_s=MAX_PROPOSAL_LIFETIME_S + 9999.0,
        )
        actual_lifetime = p.expires_at_sim_time - p.created_at_sim_time
        assert actual_lifetime == pytest.approx(MAX_PROPOSAL_LIFETIME_S), (
            "make_proposal must clamp lifetime to MAX_PROPOSAL_LIFETIME_S"
        )


# ---------------------------------------------------------------------------
# Hold questions: lifetime, terminal states, expiry
# ---------------------------------------------------------------------------

class TestProposalLifecycle:
    """Tests for the three hold questions."""

    def test_hold_q1_lifetime_is_bounded(self) -> None:
        """Hold Q1: proposal lifetime is bounded — no proposal lives indefinitely."""
        p = _make_proposal(created_at=0.0, lifetime_s=DEFAULT_PROPOSAL_LIFETIME_S)
        assert p.expires_at_sim_time < float("inf"), (
            "Hold Q1: every proposal must have a finite expires_at_sim_time"
        )
        assert p.expires_at_sim_time > p.created_at_sim_time

    def test_hold_q2_terminal_states_are_final(self) -> None:
        """Hold Q2: terminal states cannot be transitioned further."""
        gate = AdvisoryGate()
        p = _make_proposal()
        gate.validate(p)
        gate.accept(p.proposal_id)
        assert p.state == ProposalState.ACCEPTED
        # Accepting again must raise.
        with pytest.raises(ValueError, match="terminal"):
            gate.accept(p.proposal_id)
        # Rejecting a terminal must raise.
        with pytest.raises(ValueError, match="terminal"):
            gate.reject(p.proposal_id, "second_rejection")

    def test_hold_q2_all_terminal_states(self) -> None:
        """Hold Q2: TERMINAL_STATES covers ACCEPTED, REJECTED, EXPIRED, SUPERSEDED."""
        assert ProposalState.ACCEPTED   in TERMINAL_STATES
        assert ProposalState.REJECTED   in TERMINAL_STATES
        assert ProposalState.EXPIRED    in TERMINAL_STATES
        assert ProposalState.SUPERSEDED in TERMINAL_STATES
        assert ProposalState.PENDING not in TERMINAL_STATES

    def test_hold_q3_reviewing_event_never_arrives_expires_proposal(self) -> None:
        """Hold Q3: if the reviewing event never arrives, gate.tick() expires it."""
        gate = AdvisoryGate()
        p = _make_proposal(created_at=0.0, lifetime_s=30.0)
        gate.validate(p)
        assert p.state == ProposalState.PENDING

        # Tick just before expiry — still pending.
        expired = gate.tick(sim_time=29.0)
        assert not expired
        assert p.state == ProposalState.PENDING

        # Tick at or past expiry — proposal transitions to EXPIRED.
        expired = gate.tick(sim_time=30.0)
        assert len(expired) == 1
        assert expired[0].proposal_id == p.proposal_id
        assert p.state == ProposalState.EXPIRED

    def test_hold_q3_tick_after_expiry_is_noop(self) -> None:
        """Hold Q3: ticking past an already-expired proposal is a no-op."""
        gate = AdvisoryGate()
        p = _make_proposal(created_at=0.0, lifetime_s=30.0)
        gate.validate(p)
        gate.tick(sim_time=30.0)   # expires it
        expired_again = gate.tick(sim_time=60.0)
        assert expired_again == [], (
            "Ticking an already-expired proposal must produce no new expirations"
        )

    def test_hold_q3_multiple_proposals_all_expire(self) -> None:
        """Hold Q3: multiple PENDING proposals all expire at their own deadlines."""
        gate = AdvisoryGate()
        p1 = _make_proposal(created_at=0.0, lifetime_s=30.0)
        p2 = _make_proposal(created_at=0.0, lifetime_s=60.0)
        gate.validate(p1)
        gate.validate(p2)

        # Only p1 expires at t=30.
        expired_30 = gate.tick(sim_time=30.0)
        assert len(expired_30) == 1
        assert expired_30[0].proposal_id == p1.proposal_id
        assert p2.state == ProposalState.PENDING

        # p2 expires at t=60.
        expired_60 = gate.tick(sim_time=60.0)
        assert len(expired_60) == 1
        assert expired_60[0].proposal_id == p2.proposal_id

    def test_supersede_is_idempotent_on_terminal(self) -> None:
        """Superseding an already-terminal proposal is a no-op (not an error)."""
        gate = AdvisoryGate()
        p = _make_proposal()
        gate.validate(p)
        gate.accept(p.proposal_id)
        assert p.state == ProposalState.ACCEPTED
        # Should not raise:
        gate.supersede(p.proposal_id)
        assert p.state == ProposalState.ACCEPTED   # unchanged


# ---------------------------------------------------------------------------
# LP-1: no API keys → pure deterministic simulator, no errors
# ---------------------------------------------------------------------------

class TestLP1NoAgentKeys:
    """LP-1: with both MISTRAL_API_KEY and ANTHROPIC_API_KEY absent the entire
    application must run as a deterministic simulator with NO AGENTS and
    NO ERRORS.  This is verified through configuration, not failure.
    """

    def test_lp1_router_has_no_agent_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1: AdvisoryRouter.has_agent is False when both keys are absent."""
        monkeypatch.delenv("MISTRAL_API_KEY",   raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        router = AdvisoryRouter()
        assert not router.has_agent, (
            "LP-1: router.has_agent must be False when both API keys are absent"
        )
        assert router.backend is None

    def test_lp1_router_route_returns_none_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1: route() returns None immediately (no network call) without keys."""
        monkeypatch.delenv("MISTRAL_API_KEY",   raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        router = AdvisoryRouter()
        evidence = EvidenceWindow(window_sim_seconds=300.0, tick_count=60,
                                  bin_count=60, bin_dt_seconds=5.0)
        result = router.route(evidence, sim_time=0.0)
        assert result is None, "LP-1: route() must return None without API keys"

    def test_lp1_principal_has_no_agent_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1: AdvisoryPrincipal.has_agent is False without keys."""
        monkeypatch.delenv("MISTRAL_API_KEY",   raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        principal = AdvisoryPrincipal()
        assert not principal.has_agent

    def test_lp1_maybe_advise_returns_none_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1: maybe_advise() is a no-op, returns None, raises nothing."""
        monkeypatch.delenv("MISTRAL_API_KEY",   raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        principal = AdvisoryPrincipal()
        ticks = _make_ticks(120)
        # Must not raise:
        result = principal.maybe_advise(
            ticks, sim_time=600.0,
            site_id="site-secret", job_id="job-secret",
        )
        assert result is None

    def test_lp1_full_sim_loop_no_errors_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1: a complete 60-tick simulation loop with the advisory principal
        active but no keys produces no errors and identical tick results.
        """
        monkeypatch.delenv("MISTRAL_API_KEY",   raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        principal = AdvisoryPrincipal()
        ticks = _make_ticks(60)
        proposals_made = 0

        for i, tick in enumerate(ticks):
            sim_time = tick.sim_time_seconds
            # Expire proposals — must not raise.
            principal.tick(sim_time)
            # Advisory call — must return None without keys.
            result = principal.maybe_advise(
                ticks[:i+1], sim_time=sim_time,
                site_id="site-classified", job_id="job-classified",
            )
            if result is not None:
                proposals_made += 1

        assert proposals_made == 0, (
            f"LP-1: no proposals should be made without API keys; "
            f"got {proposals_made}"
        )
        assert principal.all_proposals() == [], (
            "LP-1: proposal list must be empty after LP-1 no-op run"
        )

    def test_lp1_principal_tick_is_noop_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1: tick() must not raise and returns [] without keys."""
        monkeypatch.delenv("MISTRAL_API_KEY",   raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        principal = AdvisoryPrincipal()
        expired = principal.tick(sim_time=9999.0)
        assert expired == []

    def test_lp1_router_with_only_mistral_key_has_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1 complement: MISTRAL_API_KEY present → has_agent=True, backend='mistral'."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-real")
        router = AdvisoryRouter()
        assert router.has_agent
        assert router.backend == "mistral"

    def test_lp1_router_with_only_anthropic_key_has_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LP-1 complement: ANTHROPIC_API_KEY present → has_agent=True, backend='anthropic'."""
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        router = AdvisoryRouter()
        assert router.has_agent
        assert router.backend == "anthropic"


# ---------------------------------------------------------------------------
# EvidenceWindow structure tests
# ---------------------------------------------------------------------------

class TestEvidenceWindowStructure:
    """Structural tests for the aggregation layer."""

    def test_bin_count_does_not_exceed_max_bins(self) -> None:
        ticks = _make_ticks(300)
        window = deidentify(ticks, site_id="s", job_id="j")
        assert window.bin_count <= MAX_BINS
        assert len(window.p_total_bins)    == window.bin_count
        assert len(window.turbine_bins)    == window.bin_count
        assert len(window.bess_output_bins) == window.bin_count

    def test_summary_stats_are_non_negative(self) -> None:
        ticks = _make_ticks(30)
        window = deidentify(ticks, site_id="s", job_id="j")
        assert window.p_total_p50_mw >= 0.0
        assert window.p_total_p95_mw >= 0.0
        assert window.p_total_p95_mw >= window.p_total_p50_mw, (
            "p95 must be >= p50"
        )

    def test_alert_count_matches_input(self) -> None:
        ticks = _make_ticks(10)
        ticks[3].insufficient_reserve_alert = True
        ticks[7].insufficient_reserve_alert = True
        window = deidentify(ticks, site_id="s", job_id="j")
        assert window.alert_count == 2

    def test_curtailment_count_matches_input(self) -> None:
        ticks = _make_ticks(10)
        ticks[5].curtailment_proposal_tiers = ("a_defer",)
        window = deidentify(ticks, site_id="s", job_id="j")
        assert window.curtailment_count == 1

    def test_bin_min_le_mean_le_max(self) -> None:
        ticks = _make_ticks(60)
        window = deidentify(ticks, site_id="s", job_id="j")
        for b in window.p_total_bins:
            assert b.v_min <= b.v_mean <= b.v_max, (
                f"Bin min/mean/max invariant violated: "
                f"min={b.v_min} mean={b.v_mean} max={b.v_max}"
            )


# ---------------------------------------------------------------------------
# N2: transport-layer mock — exact wire bytes captured and checked for PII
# ---------------------------------------------------------------------------

class TestN2TransportLayerWireCapture:
    """N2: verify TC-29 at the actual HTTP transport layer, not just at the
    EvidenceWindow boundary.

    The outbound Mistral/Anthropic HTTP request body is captured via a
    transport-level monkeypatch of urllib.request.urlopen *before any bytes
    leave the process*.  The captured bytes are then checked for PII tokens.

    This test demonstrates option (b): a transport mock that asserts the exact
    bytes on the wire.  It runs on every pytest invocation without requiring
    real API keys.
    """

    SITE_ID = "site-n2-transport-test-acme-corp"
    JOB_ID  = "job-n2-classified-run-XYZ-1234"
    SKUS    = frozenset({"enterprise_8gpu_air", "midrange_4gpu_water"})

    def _make_evidence(self) -> EvidenceWindow:
        ticks = _make_ticks(60)
        return deidentify(
            ticks,
            site_id=self.SITE_ID,
            job_id=self.JOB_ID,
            hardware_profile_ids=self.SKUS,
        )

    def test_n2_outbound_bytes_contain_no_pii(self) -> None:
        """N2: exact bytes captured at transport layer contain no PII tokens."""
        from unittest.mock import patch, MagicMock
        import urllib.request as _urllib_req
        from runtime.advisory_router import AdvisoryRouter

        captured_body: dict = {}

        # Fake response shaped like Mistral's success JSON.
        fake_resp_body = json.dumps({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": '{"kind":"curtailment","estimated_impact_mw":2.0,'
                               '"confidence":0.75,"reasoning":"test_n2","suggested_tier":null}',
                }
            }]
        }).encode()

        def fake_urlopen(req, timeout=None):
            captured_body.update(json.loads(req.data.decode()))
            resp = MagicMock()
            resp.read.return_value = fake_resp_body
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        evidence = self._make_evidence()

        with patch.object(_urllib_req, "urlopen", fake_urlopen):
            # Inject a fake key so the router thinks it has a backend.
            import os
            original = os.environ.get("MISTRAL_API_KEY")
            os.environ["MISTRAL_API_KEY"] = "fake-key-n2-test"
            try:
                router = AdvisoryRouter()
                proposal = router.route(evidence, sim_time=300.0)
            finally:
                if original is None:
                    del os.environ["MISTRAL_API_KEY"]
                else:
                    os.environ["MISTRAL_API_KEY"] = original

        # Verify bytes were captured.
        assert captured_body, "N2: no bytes captured — urlopen was not called."

        # Serialise the captured request body and check for PII.
        wire_bytes = json.dumps(captured_body)
        forbidden = (
            [self.SITE_ID, self.JOB_ID]
            + list(self.SKUS)
            + ["acme", "classified", "enterprise", "midrange"]
        )
        for token in forbidden:
            assert token.lower() not in wire_bytes.lower(), (
                f"N2 TC-29 VIOLATION: token {token!r} found in outbound wire bytes.\n"
                f"Wire length: {len(wire_bytes)} chars."
            )

    def test_n2_outbound_request_structure(self) -> None:
        """N2: outbound request has model, messages, and no extra fields."""
        from unittest.mock import patch, MagicMock
        import urllib.request as _urllib_req
        from runtime.advisory_router import AdvisoryRouter

        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured.update(json.loads(req.data.decode()))
            resp = MagicMock()
            resp.read.return_value = json.dumps({
                "choices": [{"message": {"role": "assistant", "content":
                    '{"kind":"load_defer","estimated_impact_mw":0.1,"confidence":0.0,'
                    '"reasoning":"test","suggested_tier":null}'}}]
            }).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        evidence = self._make_evidence()

        import os
        original = os.environ.get("MISTRAL_API_KEY")
        os.environ["MISTRAL_API_KEY"] = "fake-key-n2-structure"
        try:
            with patch.object(_urllib_req, "urlopen", fake_urlopen):
                router = AdvisoryRouter()
                router.route(evidence, sim_time=100.0)
        finally:
            if original is None:
                del os.environ["MISTRAL_API_KEY"]
            else:
                os.environ["MISTRAL_API_KEY"] = original

        assert "model" in captured, "N2: outbound body must have 'model' field."
        assert "messages" in captured, "N2: outbound body must have 'messages' field."
        msgs = captured["messages"]
        assert any(m.get("role") == "system" for m in msgs), (
            "N2: system message must be present."
        )
        assert any(m.get("role") == "user" for m in msgs), (
            "N2: user message must be present."
        )
        # System message must contain no PII.
        system_content = next(
            m["content"] for m in msgs if m.get("role") == "system"
        )
        for token in [self.SITE_ID, self.JOB_ID] + list(self.SKUS):
            assert token.lower() not in system_content.lower(), (
                f"N2: PII token {token!r} found in system prompt."
            )

    def test_n2_agent_system_prompt_override_captured_at_wire(self) -> None:
        """N2: when an agent passes a custom system_prompt, the wire uses it."""
        from unittest.mock import patch, MagicMock
        import urllib.request as _urllib_req
        from runtime.advisory_router import AdvisoryRouter

        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured.update(json.loads(req.data.decode()))
            resp = MagicMock()
            resp.read.return_value = json.dumps({
                "choices": [{"message": {"role": "assistant", "content":
                    '{"kind":"curtailment","estimated_impact_mw":1.0,'
                    '"confidence":0.5,"reasoning":"test","suggested_tier":null}'}}]
            }).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        evidence = self._make_evidence()
        custom_prompt = "CUSTOM_SYSTEM_PROMPT_MARKER: advisory agent test"

        import os
        original = os.environ.get("MISTRAL_API_KEY")
        os.environ["MISTRAL_API_KEY"] = "fake-key-n2-custom"
        try:
            with patch.object(_urllib_req, "urlopen", fake_urlopen):
                router = AdvisoryRouter()
                router.route(evidence, sim_time=200.0, system_prompt=custom_prompt)
        finally:
            if original is None:
                del os.environ["MISTRAL_API_KEY"]
            else:
                os.environ["MISTRAL_API_KEY"] = original

        wire = json.dumps(captured)
        assert "CUSTOM_SYSTEM_PROMPT_MARKER" in wire, (
            "N2: custom system_prompt must appear in the outbound wire bytes."
        )
        # Still no PII.
        for token in [self.SITE_ID, self.JOB_ID] + list(self.SKUS):
            assert token.lower() not in wire.lower(), (
                f"N2: PII token {token!r} found in wire even with custom prompt."
            )
