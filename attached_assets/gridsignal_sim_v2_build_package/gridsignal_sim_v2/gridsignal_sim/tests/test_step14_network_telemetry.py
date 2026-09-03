"""
tests/test_step14_network_telemetry.py — Step 14 network telemetry tests.

TC-50  Fabric traffic rise without WorkloadSignal → no forecast change, only
       a missed-job FabricFinding (informational only).
TC-51  checkpoint_start is authoritative; fabric evidence cannot override it.
TC-69  Cross-source correlation window = max(bound_a, bound_b) — looser bound.
TC-70  Declared PTP + |skew| > 2 ms → effective discipline demoted to NTP.
TC-71  BASELINE capability tier → ingestion continues, roles degrade.
TC-72  Optical power outside [-40, +10] dBm → quarantined with reason string.
TC-73  Fabric corroboration alone does NOT increment reconciliation_count.
TC-74  NetworkTelemetry in dispatch path → NetworkTelemetryDispatchError.
"""
from __future__ import annotations

import pytest

from core.network_telemetry import (
    CapabilityTier,
    ClockDiscipline,
    ClockClassModel,
    NetworkTelemetry,
    NetworkTelemetryDispatchError,
    NetworkTelemetryIngestor,
    NTP_BOUND_MS,
    PTP_BOUND_MS,
    PTP_SKEW_MAX_MS,
    assert_not_in_dispatch_path,
)
from core.ingest import IngestStatus
from core.corroboration import (
    CorroborationRecord,
    CorroborationResult,
    FabricCorroborator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _telemetry(
    *,
    event_id: str = "evt-1",
    switch_id: str = "sw-rack-01",
    interface_id: str = "Ethernet1/1",
    throughput_rx_bps: float = 1e8,
    throughput_tx_bps: float = 1e8,
    error_counters: dict | None = None,
    optical_power_tx_dbm: float = -3.0,
    optical_power_rx_dbm: float = -5.0,
    sample_interval_ms: float = 1000.0,
    timestamp: float = 0.0,
    clock_discipline: ClockDiscipline = ClockDiscipline.NTP,
    observed_skew_ms: float = 0.0,
) -> NetworkTelemetry:
    return NetworkTelemetry(
        event_id=event_id,
        switch_id=switch_id,
        site_id="site-test",
        interface_id=interface_id,
        throughput_rx_bps=throughput_rx_bps,
        throughput_tx_bps=throughput_tx_bps,
        error_counters=error_counters if error_counters is not None else {},
        optical_power_tx_dbm=optical_power_tx_dbm,
        optical_power_rx_dbm=optical_power_rx_dbm,
        sample_interval_ms=sample_interval_ms,
        timestamp=timestamp,
        clock_discipline=clock_discipline,
        observed_skew_ms=observed_skew_ms,
    )


def _high_throughput(**kw) -> NetworkTelemetry:
    """A NetworkTelemetry record with throughput above the rise threshold."""
    kw.setdefault("throughput_rx_bps", 2e9)  # > 1 Gbps threshold
    return _telemetry(**kw)


def _make_ingestor(capability: CapabilityTier = CapabilityTier.ENHANCED) -> NetworkTelemetryIngestor:
    return NetworkTelemetryIngestor(capability=capability)


# ===========================================================================
# TC-74: dispatch-path ineligibility by contract
# ===========================================================================

class TestTC74DispatchIneligible:
    """TC-74: routing NetworkTelemetry into the dispatch path is non-conforming."""

    def test_assert_not_in_dispatch_path_raises(self) -> None:
        t = _telemetry()
        with pytest.raises(NetworkTelemetryDispatchError, match="TC-74"):
            assert_not_in_dispatch_path(t)

    def test_error_is_type_error_subclass(self) -> None:
        """TypeError subclass — cannot be silently swallowed by broad except Exception."""
        t = _telemetry()
        with pytest.raises(TypeError):
            assert_not_in_dispatch_path(t)

    def test_error_message_says_non_conforming_not_misconfiguration(self) -> None:
        t = _telemetry(switch_id="sw-99")
        with pytest.raises(NetworkTelemetryDispatchError) as exc_info:
            assert_not_in_dispatch_path(t)
        msg = str(exc_info.value)
        assert "non-conforming" in msg.lower() or "NON-CONFORMING" in msg
        # Must NOT say "misconfigured" or "misconfiguration" as the primary label.
        assert "misconfiguration" not in msg.lower() or "not a misconfiguration" in msg.lower()

    def test_validated_telemetry_stays_in_store_not_dispatch(self) -> None:
        """Validated records go to the telemetry store, never to dispatch."""
        ingestor = _make_ingestor()
        t = _telemetry(event_id="ev-x")
        result = ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.ACCEPTED
        # Record is in the telemetry store.
        assert ingestor.record_count == 1
        # Attempting to route to dispatch path raises.
        with pytest.raises(NetworkTelemetryDispatchError):
            assert_not_in_dispatch_path(t)


# ===========================================================================
# TC-70: PTP demotion on skew contradiction
# ===========================================================================

class TestTC70ClockDemotion:
    """TC-70: declared PTP + |observed_skew_ms| > 2 ms → demoted to NTP."""

    def setup_method(self) -> None:
        self.model = ClockClassModel()

    def test_ptp_within_threshold_stays_ptp(self) -> None:
        t = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=1.5)
        assert self.model.effective_discipline(t) == ClockDiscipline.PTP

    def test_ptp_at_threshold_stays_ptp(self) -> None:
        t = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=PTP_SKEW_MAX_MS)
        assert self.model.effective_discipline(t) == ClockDiscipline.PTP

    def test_ptp_above_threshold_demoted_to_ntp(self) -> None:
        """TC-70: skew > 2 ms with declared PTP → effective discipline is NTP."""
        t = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=5.0)
        assert self.model.effective_discipline(t) == ClockDiscipline.NTP

    def test_ptp_negative_skew_above_magnitude_demoted(self) -> None:
        """Demotion is on |skew| — negative skew of equal magnitude also demotes."""
        t = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=-3.0)
        assert self.model.effective_discipline(t) == ClockDiscipline.NTP

    def test_ntp_never_demoted(self) -> None:
        """NTP source cannot be further demoted regardless of skew."""
        t = _telemetry(clock_discipline=ClockDiscipline.NTP, observed_skew_ms=999.0)
        assert self.model.effective_discipline(t) == ClockDiscipline.NTP

    def test_demotion_is_per_record_not_sticky(self) -> None:
        """Demotion is per-record — a later record with low skew is not demoted."""
        t1 = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=5.0)
        t2 = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=0.5)
        assert self.model.effective_discipline(t1) == ClockDiscipline.NTP
        assert self.model.effective_discipline(t2) == ClockDiscipline.PTP

    def test_bound_ms_ptp(self) -> None:
        t = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=0.0)
        assert self.model.bound_ms(t) == PTP_BOUND_MS

    def test_bound_ms_ntp(self) -> None:
        t = _telemetry(clock_discipline=ClockDiscipline.NTP)
        assert self.model.bound_ms(t) == NTP_BOUND_MS

    def test_bound_ms_demoted_ptp_equals_ntp_bound(self) -> None:
        """TC-70: a demoted PTP source uses the NTP bound for correlation."""
        t = _telemetry(clock_discipline=ClockDiscipline.PTP, observed_skew_ms=5.0)
        assert self.model.bound_ms(t) == NTP_BOUND_MS


# ===========================================================================
# TC-69: Cross-source correlation at looser bound
# ===========================================================================

class TestTC69CorrelationWindow:
    """TC-69: correlation window = max(bound_a, bound_b) — looser bound wins."""

    def setup_method(self) -> None:
        self.model = ClockClassModel()

    def test_both_ptp_uses_ptp_bound(self) -> None:
        a = _telemetry(event_id="a", clock_discipline=ClockDiscipline.PTP, observed_skew_ms=0.5)
        b = _telemetry(event_id="b", clock_discipline=ClockDiscipline.PTP, observed_skew_ms=0.5)
        assert self.model.correlation_window_ms(a, b) == PTP_BOUND_MS

    def test_one_ntp_uses_ntp_bound(self) -> None:
        """TC-69: one NTP source makes the window 2000 ms (looser)."""
        a = _telemetry(event_id="a", clock_discipline=ClockDiscipline.PTP, observed_skew_ms=0.5)
        b = _telemetry(event_id="b", clock_discipline=ClockDiscipline.NTP)
        window = self.model.correlation_window_ms(a, b)
        assert window == NTP_BOUND_MS

    def test_both_ntp_uses_ntp_bound(self) -> None:
        a = _telemetry(event_id="a", clock_discipline=ClockDiscipline.NTP)
        b = _telemetry(event_id="b", clock_discipline=ClockDiscipline.NTP)
        assert self.model.correlation_window_ms(a, b) == NTP_BOUND_MS

    def test_demoted_ptp_uses_ntp_bound(self) -> None:
        """TC-69 + TC-70: a demoted PTP source widens the correlation window."""
        a = _telemetry(event_id="a", clock_discipline=ClockDiscipline.PTP, observed_skew_ms=5.0)
        b = _telemetry(event_id="b", clock_discipline=ClockDiscipline.PTP, observed_skew_ms=0.5)
        # a is demoted → NTP bound → window = max(2000, 2) = 2000
        assert self.model.correlation_window_ms(a, b) == NTP_BOUND_MS

    def test_symmetry_a_b_equals_b_a(self) -> None:
        """Correlation window is symmetric."""
        a = _telemetry(event_id="a", clock_discipline=ClockDiscipline.PTP)
        b = _telemetry(event_id="b", clock_discipline=ClockDiscipline.NTP)
        assert self.model.correlation_window_ms(a, b) == self.model.correlation_window_ms(b, a)


# ===========================================================================
# TC-71: BASELINE capability tier
# ===========================================================================

class TestTC71CapabilityTier:
    """TC-71: BASELINE degrades roles, not ingestion."""

    def test_baseline_ingestion_continues(self) -> None:
        """TC-71: BASELINE ingestor accepts valid telemetry."""
        ingestor = _make_ingestor(CapabilityTier.BASELINE)
        t = _telemetry(event_id="ev-bl-1")
        result = ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.ACCEPTED

    def test_baseline_roles_degraded(self) -> None:
        """TC-71: BASELINE ingestor has optical_monitoring_enabled=False."""
        ingestor = _make_ingestor(CapabilityTier.BASELINE)
        assert ingestor.optical_monitoring_enabled is False
        assert ingestor.full_clock_analysis_enabled is False
        assert ingestor.corroboration_enabled is False

    def test_enhanced_roles_active(self) -> None:
        """ENHANCED ingestor has all roles active."""
        ingestor = _make_ingestor(CapabilityTier.ENHANCED)
        assert ingestor.optical_monitoring_enabled is True
        assert ingestor.full_clock_analysis_enabled is True
        assert ingestor.corroboration_enabled is True

    def test_baseline_quarantine_still_works(self) -> None:
        """TC-71: BASELINE still quarantines domain-invalid records."""
        ingestor = _make_ingestor(CapabilityTier.BASELINE)
        t = _telemetry(event_id="ev-bl-bad", optical_power_tx_dbm=999.0)  # TC-72 violation
        result = ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.QUARANTINED

    def test_baseline_dedup_still_works(self) -> None:
        """TC-71: BASELINE still deduplicates."""
        ingestor = _make_ingestor(CapabilityTier.BASELINE)
        t = _telemetry(event_id="ev-dup")
        ingestor.ingest(t, sim_time=0.0)
        result2 = ingestor.ingest(t, sim_time=5.0)
        assert result2.status == IngestStatus.DUPLICATE


# ===========================================================================
# TC-72: Optical power domain validation → quarantine
# ===========================================================================

class TestTC72OpticalPowerValidation:
    """TC-72: optical_power outside [-40, +10] dBm → quarantine."""

    def setup_method(self) -> None:
        self.ingestor = _make_ingestor()

    def test_valid_optical_power_accepted(self) -> None:
        t = _telemetry(
            event_id="ev-opt-ok",
            optical_power_tx_dbm=-3.0,
            optical_power_rx_dbm=-6.0,
        )
        result = self.ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.ACCEPTED

    def test_optical_power_tx_above_range_quarantined(self) -> None:
        """TC-72: tx power > +10 dBm → quarantined."""
        t = _telemetry(event_id="ev-opt-hi", optical_power_tx_dbm=15.0)
        result = self.ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.QUARANTINED
        assert "optical_power" in result.reason.lower()

    def test_optical_power_tx_below_range_quarantined(self) -> None:
        """TC-72: tx power < -40 dBm → quarantined."""
        t = _telemetry(event_id="ev-opt-lo", optical_power_tx_dbm=-50.0)
        result = self.ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.QUARANTINED

    def test_optical_power_rx_out_of_range_quarantined(self) -> None:
        """TC-72: rx power out of range → quarantined."""
        t = _telemetry(event_id="ev-opt-rx-bad", optical_power_rx_dbm=999.0)
        result = self.ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.QUARANTINED

    def test_quarantine_record_stored(self) -> None:
        """TC-72: quarantined record is in the quarantine store with a reason."""
        t = _telemetry(event_id="ev-opt-q", optical_power_tx_dbm=20.0)
        self.ingestor.ingest(t, sim_time=0.0)
        records = self.ingestor.quarantine.all_records()
        assert len(records) == 1
        assert records[0].event_id == "ev-opt-q"
        assert "optical_power" in records[0].reason.lower()

    def test_quarantine_raw_payload_is_text_not_json(self) -> None:
        """§17.2: raw_payload is stored as TEXT — parser failures don't lose data."""
        t = _telemetry(event_id="ev-raw-txt", optical_power_tx_dbm=50.0)
        self.ingestor.ingest(t, sim_time=0.0)
        records = self.ingestor.quarantine.all_records()
        assert isinstance(records[0].raw_payload, str)
        assert len(records[0].raw_payload) > 0

    def test_negative_error_counter_quarantined(self) -> None:
        t = _telemetry(event_id="ev-ec-neg", error_counters={"crc": -1})
        result = self.ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.QUARANTINED

    def test_zero_sample_interval_quarantined(self) -> None:
        t = _telemetry(event_id="ev-si-zero", sample_interval_ms=0.0)
        result = self.ingestor.ingest(t, sim_time=0.0)
        assert result.status == IngestStatus.QUARANTINED


# ===========================================================================
# TC-73: Fabric corroboration does NOT count toward reconciliation threshold
# ===========================================================================

class TestTC73CorroborationNotReconciliation:
    """TC-73: throughput is not a magnitude proxy; fabric corroboration never
    increments the §17.3 reconciliation counter."""

    def test_reconciliation_count_zero_initially(self) -> None:
        c = FabricCorroborator()
        assert c.reconciliation_count == 0

    def test_fabric_rise_does_not_increment_reconciliation(self) -> None:
        """TC-73: ingesting a high-throughput record must NOT increment reconciliation_count."""
        c = FabricCorroborator()
        t = _high_throughput(event_id="ev-rise-1", timestamp=10.0)
        c.ingest_telemetry(t, sim_time=10.0)
        assert c.reconciliation_count == 0, (
            "TC-73: fabric telemetry must NEVER increment reconciliation_count; "
            f"got {c.reconciliation_count}"
        )

    def test_multiple_fabric_rises_do_not_increment(self) -> None:
        """TC-73: many fabric rises, reconciliation stays 0."""
        c = FabricCorroborator()
        for i in range(10):
            t = _high_throughput(event_id=f"ev-{i}", timestamp=float(i))
            c.ingest_telemetry(t, sim_time=float(i))
        assert c.reconciliation_count == 0

    def test_advance_reconciliation_count_works_from_workload_path(self) -> None:
        """Only the WorkloadSignal path increments reconciliation_count."""
        c = FabricCorroborator()
        c.advance_reconciliation_count()
        c.advance_reconciliation_count()
        assert c.reconciliation_count == 2

    def test_fabric_rise_after_workload_does_not_double_count(self) -> None:
        """TC-73: WorkloadSignal count + fabric rise = only WorkloadSignal count."""
        c = FabricCorroborator()
        c.advance_reconciliation_count()  # WorkloadSignal event
        t = _high_throughput(event_id="ev-after", timestamp=5.0)
        c.ingest_telemetry(t, sim_time=5.0)
        assert c.reconciliation_count == 1  # unchanged by fabric


# ===========================================================================
# TC-50: Fabric rise without WorkloadSignal → FabricFinding only
# ===========================================================================

class TestTC50FabricRiseWithoutWorkload:
    """TC-50: fabric traffic rise with no preceding WorkloadSignal produces
    no forecast change and no staging action — only a FabricFinding."""

    def test_unmatched_rise_produces_finding(self) -> None:
        """TC-50: no registered job → FabricFinding emitted."""
        c = FabricCorroborator()
        t = _high_throughput(event_id="ev-unmatched", switch_id="sw-01", timestamp=100.0)
        finding = c.ingest_telemetry(t, sim_time=100.0)
        assert finding is not None
        assert finding.finding_type == "unmatched_fabric_rise"
        assert finding.switch_id == "sw-01"

    def test_finding_has_no_forecast_state(self) -> None:
        """TC-50: FabricFinding has no reference to SimulationState or dispatch path."""
        from core.corroboration import FabricFinding
        # FabricFinding has only informational fields — no power values, no dispatch refs.
        fields = {f.name for f in __import__('dataclasses').fields(FabricFinding)}
        dispatch_fields = {"p_total_mw", "turbine_output_mw", "bess_output_mw",
                           "dispatch_required_mw", "staging_result"}
        assert fields.isdisjoint(dispatch_fields), (
            f"TC-50: FabricFinding must not carry dispatch-path fields: "
            f"{fields & dispatch_fields}"
        )

    def test_low_throughput_no_finding(self) -> None:
        """Below the rise threshold: no finding emitted."""
        c = FabricCorroborator()
        t = _telemetry(event_id="ev-low", throughput_rx_bps=1e6)  # below threshold
        finding = c.ingest_telemetry(t, sim_time=0.0)
        assert finding is None

    def test_finding_stored_in_all_findings(self) -> None:
        c = FabricCorroborator()
        t = _high_throughput(event_id="ev-store")
        c.ingest_telemetry(t, sim_time=0.0)
        assert len(c.all_findings()) == 1


# ===========================================================================
# TC-51: checkpoint_start is authoritative; fabric cannot override
# ===========================================================================

class TestTC51CheckpointStartAuthoritative:
    """TC-51: scheduler checkpoint_start is authoritative; fabric evidence
    cannot override it."""

    def test_checkpoint_start_sets_authoritative_result(self) -> None:
        c = FabricCorroborator()
        c.register_predicted_start("job-A", sim_time=0.0)
        c.apply_checkpoint_start("job-A", sim_time=5.0)
        record = c.get_record("job-A")
        assert record is not None
        assert record.result == CorroborationResult.AUTHORITATIVE_START
        assert record.authoritative_event == "checkpoint_start"

    def test_fabric_rise_after_checkpoint_does_not_change_result(self) -> None:
        """TC-51: fabric evidence cannot override an authoritative checkpoint_start."""
        c = FabricCorroborator()
        c.register_predicted_start("job-B", sim_time=0.0)
        c.apply_checkpoint_start("job-B", sim_time=5.0)

        # Fabric traffic rise arrives after checkpoint_start.
        t = _high_throughput(event_id="ev-after-ckpt", timestamp=8.0)
        # patch: make the corroborator see job-B as matching
        record = c.get_record("job-B")
        result_before = record.result
        record.try_corroborate_from_fabric(8.0)

        # Result must remain AUTHORITATIVE_START — fabric cannot override it.
        assert record.result == CorroborationResult.AUTHORITATIVE_START, (
            f"TC-51: result changed from {result_before} to {record.result} "
            "after fabric evidence — fabric must not override authoritative checkpoint."
        )

    def test_checkpoint_without_prior_prediction(self) -> None:
        """TC-51: checkpoint_start for an unregistered job creates an authoritative record."""
        c = FabricCorroborator()
        c.apply_checkpoint_start("job-unknown", sim_time=10.0)
        record = c.get_record("job-unknown")
        assert record is not None
        assert record.result == CorroborationResult.AUTHORITATIVE_START

    def test_fabric_before_checkpoint_then_checkpoint(self) -> None:
        """TC-51: fabric rise first (CORROBORATED), then checkpoint → still AUTHORITATIVE."""
        c = FabricCorroborator()
        c.register_predicted_start("job-C", sim_time=0.0, corroboration_window_s=60.0)

        # Fabric rise arrives first, within the window.
        t = _high_throughput(event_id="ev-early", timestamp=5.0)
        c.ingest_telemetry(t, sim_time=5.0)
        record = c.get_record("job-C")
        # At this point result could be CORROBORATED (fabric matched).

        # Now checkpoint_start arrives — must override to AUTHORITATIVE.
        c.apply_checkpoint_start("job-C", sim_time=10.0)
        assert record.result == CorroborationResult.AUTHORITATIVE_START


# ===========================================================================
# §17.1 Deduplication and §17.2 quarantine (shared machinery)
# ===========================================================================

class TestSharedIngestMachinery:
    """Verify §17.1-17.2 machinery works identically for NetworkTelemetry."""

    def test_duplicate_event_id_rejected(self) -> None:
        ingestor = _make_ingestor()
        t = _telemetry(event_id="ev-dup-x")
        ingestor.ingest(t, sim_time=0.0)
        result2 = ingestor.ingest(t, sim_time=5.0)
        assert result2.status == IngestStatus.DUPLICATE

    def test_different_event_ids_both_accepted(self) -> None:
        ingestor = _make_ingestor()
        t1 = _telemetry(event_id="ev-1")
        t2 = _telemetry(event_id="ev-2")
        r1 = ingestor.ingest(t1, sim_time=0.0)
        r2 = ingestor.ingest(t2, sim_time=0.0)
        assert r1.status == IngestStatus.ACCEPTED
        assert r2.status == IngestStatus.ACCEPTED
        assert ingestor.record_count == 2

    def test_dedup_window_expiry_allows_re_entry(self) -> None:
        """§17.1 rolling window: same event_id accepted again after window expires."""
        from core.ingest import Deduplicator
        dedup = Deduplicator(window_sim_s=100.0)
        assert not dedup.is_duplicate("ev-x", 0.0)
        assert dedup.is_duplicate("ev-x", 50.0)    # within window
        assert not dedup.is_duplicate("ev-x", 200.0)  # past window — fresh entry

    def test_quarantine_stores_raw_payload(self) -> None:
        """§17.2: quarantine raw_payload is TEXT, not JSON object."""
        ingestor = _make_ingestor()
        bad = _telemetry(event_id="ev-q1", sample_interval_ms=-1.0)
        result = ingestor.ingest(bad, sim_time=0.0)
        assert result.status == IngestStatus.QUARANTINED
        qr = ingestor.quarantine.all_records()[0]
        assert isinstance(qr.raw_payload, str)
        assert len(qr.raw_payload) > 0
