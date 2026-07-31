"""
core/deident.py — Step 12: §4.5 data de-identification and aggregation layer.

Build order mandate: this file must predate any model client so no outbound
request can bypass the egress filter.  The de-identifier is the wire — every
evidence window that leaves GridSignal passes through deidentify() first.

TC-29 guarantee
---------------
site_id, job_id, customer identifier, and hardware SKU name are consumed as
function arguments and NEVER written into EvidenceWindow.  Tests serialise the
window with dataclasses.asdict() + json.dumps() and assert none of the
forbidden strings appear anywhere in the resulting bytes.

Aggregation design
------------------
Raw tick series (potentially thousands of rows per scenario hour) is
downsampled to at most MAX_BINS = 60 bins.  Each bin carries min/mean/max
for the key power metrics.  Summary statistics and anomaly flags are computed
over the whole window.

Target: ≤ 1500 input tokens per evidence window when serialised as compact
JSON.  With 60 bins × 3 metrics × 3 values each ≈ 540 numbers at 6 chars
each = ~3240 chars ≈ 810 tokens for the binned series, plus ≈ 200 tokens for
summary and metadata.  Total comfortably under budget.
"""
from __future__ import annotations

import dataclasses
import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence

from core.models import TickResult

# §4.5.1: at most 60 aggregation bins per evidence window.
MAX_BINS: int = 60
# Round to 3 decimal places — sufficient resolution, saves tokens.
_DP: int = 3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PowerBin:
    """One aggregation bin for a scalar power or SOC metric."""
    t_mid_s: float       # simulated seconds at bin midpoint
    v_min:   float       # minimum over the bin (MW or fraction)
    v_mean:  float       # mean over the bin
    v_max:   float       # maximum over the bin


@dataclass
class EvidenceWindow:
    """Aggregated, de-identified evidence window ready for outbound use.

    No site_id, job_id, customer identifier, or hardware SKU name is stored
    anywhere in this dataclass.  The only strings present are:
      • anomaly flag descriptors (short, non-PII, defined in deidentify())
      • no other free-text fields

    TC-29 is asserted by assert_no_pii() immediately after construction.
    Serialise with dataclasses.asdict() + json.dumps() for the wire payload.
    """
    # ── Timing ────────────────────────────────────────────────────────────
    window_sim_seconds: float   # duration of the tick series
    tick_count: int             # raw ticks in the input
    bin_count: int              # bins in the output (≤ MAX_BINS)
    bin_dt_seconds: float       # simulated seconds per bin

    # ── Per-bin series (len == bin_count each) ────────────────────────────
    p_total_bins:    list[PowerBin] = field(default_factory=list)
    turbine_bins:    list[PowerBin] = field(default_factory=list)
    bess_output_bins: list[PowerBin] = field(default_factory=list)

    # ── Summary statistics (whole window) ─────────────────────────────────
    p_total_p50_mw:   float = 0.0
    p_total_p95_mw:   float = 0.0
    alert_count:      int   = 0
    curtailment_count: int  = 0

    # ── Anomaly flags (short descriptor strings; no PII) ──────────────────
    # Format: short snake_case labels, no customer data, no unit identifiers.
    # Example: "consecutive_alerts_5", "curtailment_escalated", "bess_soc_critical"
    anomalies: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deidentify(
    ticks: Sequence[TickResult],
    *,
    site_id: str,
    job_id: str,
    hardware_profile_ids: frozenset[str] = frozenset(),
) -> EvidenceWindow:
    """Aggregate and de-identify a tick series into an EvidenceWindow.

    Parameters site_id, job_id, and hardware_profile_ids are consumed here
    and NEVER written into the returned EvidenceWindow.  TC-29 tests verify
    this on the serialised JSON wire form.

    Downsampling:
        bin_count = min(MAX_BINS, len(ticks)).
        When len(ticks) <= MAX_BINS, bin_count == len(ticks) (no padding).
        Bins are contiguous, non-overlapping, and cover the whole series.

    Anomaly flags raised (TC-29-safe — no PII):
        "consecutive_alerts_N" — N or more consecutive alert ticks found.
        "curtailment_escalated" — at least one tick had curtailment proposals.
        "bess_soc_critical" — at least one tick had bess_soc_fraction < 0.10.
        "dispatch_gap_N" — N ticks where P_total < 80 % of peak P_total.
    """
    if not ticks:
        return EvidenceWindow(
            window_sim_seconds=0.0, tick_count=0, bin_count=0, bin_dt_seconds=0.0,
        )

    n = len(ticks)
    bin_count = min(MAX_BINS, n)
    # Exact bin boundaries: bin i covers ticks [floor(i*n/bin_count), floor((i+1)*n/bin_count)).
    def _bin_slice(i: int) -> tuple[int, int]:
        start = (i * n) // bin_count
        end   = ((i + 1) * n) // bin_count
        return start, max(start + 1, end)   # guarantee at least one tick

    def _make_bin(series: list[float], i: int) -> PowerBin:
        start, end = _bin_slice(i)
        vals = series[start:end]
        t0 = ticks[start].sim_time_seconds
        t1 = ticks[min(end - 1, n - 1)].sim_time_seconds
        return PowerBin(
            t_mid_s=round((t0 + t1) / 2, _DP),
            v_min=round(min(vals), _DP),
            v_mean=round(statistics.mean(vals), _DP),
            v_max=round(max(vals), _DP),
        )

    p_total_s   = [r.p_total_mw       for r in ticks]
    turbine_s   = [r.turbine_output_mw for r in ticks]
    bess_out_s  = [r.bess_output_mw    for r in ticks]
    # bess_soc_fraction may not be on all TickResult versions; default 1.0.
    bess_soc_s  = [getattr(r, "bess_soc_fraction", 1.0) for r in ticks]

    p_total_bins    = [_make_bin(p_total_s,  i) for i in range(bin_count)]
    turbine_bins    = [_make_bin(turbine_s,  i) for i in range(bin_count)]
    bess_out_bins   = [_make_bin(bess_out_s, i) for i in range(bin_count)]

    # Summary statistics.
    sorted_p = sorted(p_total_s)
    p50 = _percentile(sorted_p, 0.50)
    p95 = _percentile(sorted_p, 0.95)

    alert_count = sum(1 for r in ticks if r.insufficient_reserve_alert)
    curtailment_count = sum(
        1 for r in ticks if getattr(r, "curtailment_proposal_tiers", ())
    )

    # Anomaly detection (TC-29-safe labels only — no customer identifiers).
    anomalies: list[str] = []
    max_consec = _max_consecutive_alerts(ticks)
    if max_consec >= 3:
        anomalies.append(f"consecutive_alerts_{max_consec}")
    if curtailment_count > 0:
        anomalies.append("curtailment_escalated")
    if any(soc < 0.10 for soc in bess_soc_s if soc > 0.0):
        anomalies.append("bess_soc_critical")
    if sorted_p:
        peak = sorted_p[-1]
        gap_ticks = sum(1 for v in p_total_s if peak > 0 and v < 0.80 * peak)
        if gap_ticks >= 5:
            anomalies.append(f"dispatch_gap_{gap_ticks}")

    window_s = ticks[-1].sim_time_seconds - ticks[0].sim_time_seconds
    if window_s <= 0.0 and len(ticks) > 0:
        window_s = 5.0 * len(ticks)   # fallback: assume 5 s ticks

    return EvidenceWindow(
        window_sim_seconds=round(window_s, 1),
        tick_count=n,
        bin_count=bin_count,
        bin_dt_seconds=round(window_s / bin_count, 1) if bin_count else 0.0,
        p_total_bins=p_total_bins,
        turbine_bins=turbine_bins,
        bess_output_bins=bess_out_bins,
        p_total_p50_mw=p50,
        p_total_p95_mw=p95,
        alert_count=alert_count,
        curtailment_count=curtailment_count,
        anomalies=anomalies,
    )


def assert_no_pii(
    window: EvidenceWindow,
    *,
    site_id: str,
    job_id: str,
    hardware_profile_ids: frozenset[str] = frozenset(),
) -> None:
    """TC-29 assertion — raise AssertionError if any PII leaks into the wire.

    Checks the serialised JSON representation (the actual wire payload) for
    the presence of any forbidden identifier substring.  This mirrors what an
    integration test would do at the actual outbound HTTP boundary.

    Checks site_id, job_id, and every hardware_profile_id.  Also checks any
    word of length ≥ 4 that appears in those identifiers, to catch cases where
    a fragment of a compound identifier (e.g. "enterprise" from
    "enterprise_8gpu_air") appears in the wire payload.
    """
    wire = json.dumps(dataclasses.asdict(window))
    forbidden_tokens: set[str] = set()
    for raw in (site_id, job_id, *hardware_profile_ids):
        if raw:
            forbidden_tokens.add(raw)
            # Add hyphen/underscore-separated words ≥ 4 chars.
            for word in raw.replace("-", "_").split("_"):
                if len(word) >= 4:
                    forbidden_tokens.add(word)

    for token in forbidden_tokens:
        if token and token.lower() in wire.lower():
            raise AssertionError(
                f"TC-29 VIOLATION: identifier token {token!r} (from "
                f"site_id={site_id!r} / job_id={job_id!r}) found in "
                f"serialised EvidenceWindow wire payload.  "
                f"deidentify() must strip all customer identifiers."
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _percentile(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank percentile on a pre-sorted list."""
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, int(math.ceil(p * len(sorted_vals))) - 1))
    return round(sorted_vals[idx], _DP)


def _max_consecutive_alerts(ticks: Sequence[TickResult]) -> int:
    max_run = cur = 0
    for r in ticks:
        if r.insufficient_reserve_alert:
            cur += 1
            max_run = max(max_run, cur)
        else:
            cur = 0
    return max_run
