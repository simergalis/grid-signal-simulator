"""
core/network_telemetry.py — §25 NetworkTelemetry ingest contract.

Step 14.

DISPATCH-PATH INELIGIBLE BY CONTRACT (TC-74)
NetworkTelemetry is a separate ingest class.  It shares the §17.1-17.2
machinery (Deduplicator + Quarantine + domain validation) with WorkloadSignal,
but it is structurally barred from the forecast path.  The bar is at the type
level — assert_not_in_dispatch_path() raises NetworkTelemetryDispatchError
(a TypeError subclass) so that any adapter attempting to route telemetry into
the forecast path fails explicitly, not silently.  This is a NON-CONFORMING
USE, not a misconfiguration (TC-74).

§25.3 capability tiers (TC-71)
A BASELINE platform degrades ROLES, not ingestion.  NetworkTelemetryIngestor
still accepts and validates telemetry on a BASELINE platform; it is the role
surface (optical monitoring, corroboration, full clock-class analysis) that
degrades.  Ingestion never stops.

§11.4 clock-class model (TC-69, TC-70)
PTP vs NTP with demotion when observed skew contradicts declared discipline.
  TC-70: declared PTP + |observed_skew_ms| > PTP_SKEW_MAX_MS → demote to NTP.
  TC-69: cross-source correlation window = MAX(bound(source_A), bound(source_B)).
         "Looser bound" means higher uncertainty, which is conservative.

TC-72: domain validation
  optical_power_tx_dbm and optical_power_rx_dbm outside the physical range
  [-40, +10] dBm are quarantined (non-physical measurement or sensor fault).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.ingest import BaseIngestor, Deduplicator, IngestResult, IngestStatus, Quarantine


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ClockDiscipline(str, Enum):
    """§11.4 declared synchronisation discipline."""
    PTP = "ptp"   # IEEE 1588 precision time protocol — ±2 ms nominal bound
    NTP = "ntp"   # Network Time Protocol — ±2 s nominal bound


class CapabilityTier(str, Enum):
    """§25.3 platform capability tier.

    BASELINE:  ingestion always continues; roles/features degrade (TC-71).
    ENHANCED:  full capability — all roles active.
    """
    BASELINE = "baseline"
    ENHANCED = "enhanced"


# Clock uncertainty bounds (§11.4).
PTP_BOUND_MS: float = 2.0      # ±2 ms (IEEE 1588 synchronisation)
NTP_BOUND_MS: float = 2000.0   # ±2 s (NTP model)
PTP_SKEW_MAX_MS: float = 2.0   # TC-70: threshold above which PTP is demoted

# Optical power physical range.
_OPTICAL_DBM_MIN: float = -40.0
_OPTICAL_DBM_MAX: float =  10.0


# ---------------------------------------------------------------------------
# NetworkTelemetry record
# ---------------------------------------------------------------------------

@dataclass
class NetworkTelemetry:
    """§25.2 NetworkTelemetry ingest contract.

    DISPATCH-PATH INELIGIBLE BY CONTRACT (TC-74).
    Any adapter routing this record into the forecast/dispatch path is
    non-conforming.  Call assert_not_in_dispatch_path() at the adapter
    boundary to enforce this contractually rather than by convention.

    Fields follow §25.2:
      switch_id        — fabric switch identifier (site-internal, not customer)
      site_id          — site scoping (shared namespace with WorkloadSignal)
      interface_id     — switch port identifier
      throughput_rx_bps — received byte rate (sampled, NOT counter delta)
      throughput_tx_bps — transmitted byte rate (sampled, NOT counter delta)
      error_counters   — named counter dict; all values must be >= 0
      optical_power_tx_dbm — TX optical power in dBm
      optical_power_rx_dbm — RX optical power in dBm
      sample_interval_ms — sampling interval; must be > 0
      timestamp        — simulated seconds since run start
      event_id         — §17.1 deduplification key
      clock_discipline — declared synchronisation discipline (§11.4)
      observed_skew_ms — measured skew vs reference; used for TC-70 demotion
    """
    event_id:             str
    switch_id:            str
    site_id:              str
    interface_id:         str
    throughput_rx_bps:    float
    throughput_tx_bps:    float
    error_counters:       dict[str, int]
    optical_power_tx_dbm: float
    optical_power_rx_dbm: float
    sample_interval_ms:   float
    timestamp:            float   # simulated seconds
    clock_discipline:     ClockDiscipline = ClockDiscipline.NTP
    observed_skew_ms:     float   = 0.0


# ---------------------------------------------------------------------------
# TC-74 contract enforcement
# ---------------------------------------------------------------------------

class NetworkTelemetryDispatchError(TypeError):
    """TC-74: raised when NetworkTelemetry enters the dispatch/forecast path.

    This is a contract violation (non-conforming use), not a misconfiguration.
    The TypeError subclass ensures it cannot be silently caught by a broad
    except Exception block that a misconfiguration handler might have.
    """


def assert_not_in_dispatch_path(telemetry: "NetworkTelemetry") -> None:
    """TC-74 enforcement point.

    Call this at any boundary that separates the telemetry store from the
    forecast/dispatch path.  Raises NetworkTelemetryDispatchError immediately
    — there is no "check and return" form because dispatch-path ineligibility
    is absolute, not conditional.

    Example:
        def _apply_to_forecast(event):
            if isinstance(event, NetworkTelemetry):
                assert_not_in_dispatch_path(event)  # always raises
            ...
    """
    raise NetworkTelemetryDispatchError(
        f"TC-74 NON-CONFORMING: NetworkTelemetry (switch_id={telemetry.switch_id!r}, "
        f"interface_id={telemetry.interface_id!r}) may not enter the dispatch or "
        f"forecast path.  NetworkTelemetry is dispatch-path ineligible by contract "
        f"(§25.1).  This is a non-conforming use, not a misconfiguration — there is "
        f"no configuration that makes this legal."
    )


# ---------------------------------------------------------------------------
# §11.4 Clock-class model
# ---------------------------------------------------------------------------

class ClockClassModel:
    """§11.4 clock-class model: PTP vs NTP with demotion on skew contradiction.

    TC-70: when a source declares PTP discipline but measured skew exceeds
    PTP_SKEW_MAX_MS (±2 ms), the source is demoted to NTP-class clock.
    The demotion is per-record (not sticky) — each telemetry record is
    evaluated independently.

    TC-69: cross-source correlation uses the LOOSER (higher uncertainty) bound.
    Two PTP sources → 2 ms window.  One NTP source → 2 s window regardless of
    whether the other source is PTP.  "Looser" = max() of the two bounds.
    """

    def effective_discipline(self, t: NetworkTelemetry) -> ClockDiscipline:
        """Effective clock class after demotion check (TC-70)."""
        if (t.clock_discipline == ClockDiscipline.PTP
                and abs(t.observed_skew_ms) > PTP_SKEW_MAX_MS):
            # TC-70: declared PTP but skew contradicts it → demote to NTP.
            return ClockDiscipline.NTP
        return t.clock_discipline

    def bound_ms(self, t: NetworkTelemetry) -> float:
        """Uncertainty bound in milliseconds for a single source."""
        eff = self.effective_discipline(t)
        return NTP_BOUND_MS if eff == ClockDiscipline.NTP else PTP_BOUND_MS

    def correlation_window_ms(
        self,
        a: NetworkTelemetry,
        b: NetworkTelemetry,
    ) -> float:
        """TC-69: correlation window = max(bound(a), bound(b)).

        Cross-source timestamps are reported at the LOOSER bound — the one
        with higher uncertainty.  This is conservative: it widens the window
        rather than claiming tighter synchronisation than the data supports.
        """
        return max(self.bound_ms(a), self.bound_ms(b))


# ---------------------------------------------------------------------------
# §17.1-17.2 NetworkTelemetry ingestor
# ---------------------------------------------------------------------------

class NetworkTelemetryIngestor(BaseIngestor):
    """§17.1-17.2 ingest for NetworkTelemetry.

    Shares the Deduplicator + Quarantine machinery from core/ingest.py with
    WorkloadSignalIngestor.  A second ingestion path with different rules
    would be a second set of bugs.

    TC-71: BASELINE capability tier — ingestion continues, roles degrade.
    TC-72: optical_power outside [-40, +10] dBm → quarantined.
    TC-74: NetworkTelemetry is NEVER routed to the forecast/dispatch path.

    Roles that degrade on BASELINE (but ingestion always continues):
      • optical_monitoring_enabled — optical power analysis disabled
      • full_clock_analysis_enabled — only basic skew check, no PTP analysis
      • corroboration_enabled — fabric-to-job corroboration disabled
    """

    def __init__(
        self,
        capability: CapabilityTier = CapabilityTier.ENHANCED,
        deduplicator: Optional[Deduplicator] = None,
        quarantine: Optional[Quarantine] = None,
    ) -> None:
        super().__init__(deduplicator=deduplicator, quarantine=quarantine)
        self._capability = capability
        self._clock_model = ClockClassModel()
        # Validated records — keyed by event_id for fast lookup.
        self._store: dict[str, NetworkTelemetry] = {}

    @property
    def capability(self) -> CapabilityTier:
        return self._capability

    # TC-71: role flags degrade on BASELINE, ingestion never stops.
    @property
    def optical_monitoring_enabled(self) -> bool:
        return self._capability == CapabilityTier.ENHANCED

    @property
    def full_clock_analysis_enabled(self) -> bool:
        return self._capability == CapabilityTier.ENHANCED

    @property
    def corroboration_enabled(self) -> bool:
        return self._capability == CapabilityTier.ENHANCED

    def ingest(self, telemetry: NetworkTelemetry, sim_time: float) -> IngestResult:
        """Run the shared §17.1-17.2 pipeline on a NetworkTelemetry record.

        TC-71: ingest always proceeds regardless of capability tier.
        TC-72: optical power out of range → quarantined.
        TC-74: validated records are stored in the telemetry store, NEVER
               routed to the forecast/dispatch path.
        """
        result = self._ingest(telemetry, event_id=telemetry.event_id, sim_time=sim_time)
        if result.status == IngestStatus.ACCEPTED:
            self._store[telemetry.event_id] = telemetry
        return result

    def validate_domain(self, record: NetworkTelemetry, sim_time: float) -> str:
        """§17.2 domain rule hook for NetworkTelemetry.

        Returns empty string if valid, or a quarantine reason string.

        Rules:
          1. sample_interval_ms must be > 0.
          2. throughput values must be >= 0.
          3. error_counters values must be >= 0.
          4. optical_power_tx/rx_dbm must be in [-40, +10] dBm (TC-72).
          5. timestamp must be >= 0.
        """
        if not isinstance(record, NetworkTelemetry):
            return f"unexpected type: {type(record).__name__}"

        if record.sample_interval_ms <= 0:
            return (
                f"sample_interval_ms={record.sample_interval_ms} is not positive — "
                "sampled rate requires a positive interval"
            )

        if record.throughput_rx_bps < 0:
            return f"throughput_rx_bps={record.throughput_rx_bps} is negative"

        if record.throughput_tx_bps < 0:
            return f"throughput_tx_bps={record.throughput_tx_bps} is negative"

        for name, count in (record.error_counters or {}).items():
            if count < 0:
                return f"error_counter {name!r} is negative: {count}"

        # TC-72: optical power domain check.
        if not (_OPTICAL_DBM_MIN <= record.optical_power_tx_dbm <= _OPTICAL_DBM_MAX):
            return (
                f"optical_power_tx_dbm={record.optical_power_tx_dbm} dBm is outside "
                f"physical range [{_OPTICAL_DBM_MIN}, {_OPTICAL_DBM_MAX}] dBm — "
                "likely sensor fault or wiring error"
            )
        if not (_OPTICAL_DBM_MIN <= record.optical_power_rx_dbm <= _OPTICAL_DBM_MAX):
            return (
                f"optical_power_rx_dbm={record.optical_power_rx_dbm} dBm is outside "
                f"physical range [{_OPTICAL_DBM_MIN}, {_OPTICAL_DBM_MAX}] dBm — "
                "likely sensor fault or wiring error"
            )

        if record.timestamp < 0:
            return f"timestamp={record.timestamp} is negative"

        return ""

    def all_records(self) -> list[NetworkTelemetry]:
        """All validated (non-quarantined, non-duplicate) telemetry records."""
        return list(self._store.values())

    @property
    def record_count(self) -> int:
        return len(self._store)
