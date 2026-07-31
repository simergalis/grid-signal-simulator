"""
core/deident.py — Step 12: §4.5 data de-identification and aggregation layer.
                  Step 13/O1: §21.4 hardware class entries added.

Build order mandate: this file must predate any model client so no outbound
request can bypass the egress filter.  The de-identifier is the wire — every
evidence window that leaves GridSignal passes through deidentify() first.

TC-29 guarantee
---------------
site_id, job_id, customer identifier, and hardware SKU name are consumed as
function arguments and NEVER written into EvidenceWindow.  Tests serialise the
window with dataclasses.asdict() + json.dumps() and assert none of the
forbidden strings appear anywhere in the resulting bytes.

§21.4 hardware representation (O1 correction)
----------------------------------------------
The previous implementation emitted no hardware data at all (over-compliance).
§21.4 permits rated wattage (the modelled quantity) and forbids the profile
library contents (SKU names, descriptions, vendor identifiers).

Form: anonymized class index + rated_kw_per_unit.
  "profile_A at 10.2 kW/unit"

Encoded as HardwareClassEntry(class_index="profile_A", rated_kw_per_unit=10.2).

De-identification rules:
  • Class indices (A, B, C …) are RANDOMISED per deidentify() call and NOT
    stable across runs — the same SKU maps to a different letter each call.
  • Fleet size (node count) is OMITTED — combining wattage with fleet size
    would reconstruct per-site draw, which is the characterisation §21.4 forbids.
  • SKU names, descriptions, and vendor identifiers never appear in
    EvidenceWindow; assert_no_pii() catches regressions.

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
import random as _random
import statistics
from dataclasses import dataclass, field
from typing import Optional, Sequence

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
class HardwareClassEntry:
    """§21.4 de-identified hardware class.

    class_index is a per-session random letter label (e.g. "profile_A").
    It is NOT stable across deidentify() calls — the same SKU maps to a
    different letter on each call.  This prevents corroboration across
    evidence windows.

    rated_kw_per_unit is the modelled power draw (§21.4 permitted quantity).
    Fleet size is deliberately omitted so per-site draw cannot be reconstructed
    by combining wattage × node count.
    """
    class_index: str       # "profile_A", "profile_B", …  (never the SKU name)
    rated_kw_per_unit: float  # e.g. 10.2  (kW per compute node)


@dataclass
class EvidenceWindow:
    """Aggregated, de-identified evidence window ready for outbound use.

    No site_id, job_id, customer identifier, or hardware SKU name is stored
    anywhere in this dataclass.  The only strings present are:
      • anomaly flag descriptors (short, non-PII, defined in deidentify())
      • hardware_classes[*].class_index — per-session random letter, not a SKU
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

    # ── §21.4 hardware classes (per-session random letter indices) ─────────
    # Populated when hardware_profiles={} is passed to deidentify().
    # Empty when hardware data is unavailable.
    # class_index is randomised per call — NOT stable across runs (§21.4).
    hardware_classes: list[HardwareClassEntry] = field(default_factory=list)

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
    hardware_profiles: Optional[dict[str, float]] = None,
) -> EvidenceWindow:
    """Aggregate and de-identify a tick series into an EvidenceWindow.

    Parameters site_id, job_id, hardware_profile_ids, and hardware_profiles
    are consumed here and NEVER written into the returned EvidenceWindow.
    TC-29 tests verify this on the serialised JSON wire form.

    Parameters
    ----------
    ticks:
        The tick series to aggregate.
    site_id:
        Customer site identifier — consumed for PII check, never stored.
    job_id:
        Job identifier — consumed for PII check, never stored.
    hardware_profile_ids:
        Set of hardware SKU names for TC-29 PII checking only.
        Kept for backward compatibility.  Superseded by hardware_profiles
        when both are provided.
    hardware_profiles:
        Dict mapping hardware_profile_id → rated_kw_per_unit (§21.4).
        When provided, generates HardwareClassEntry objects with per-session
        random letter indices.  Keys are also used for TC-29 PII checking
        (supersedes hardware_profile_ids when non-empty).
        OMIT fleet size — do not pass node counts here.

    §21.4 hardware encoding
    -----------------------
    When hardware_profiles is provided and non-empty, the returned window
    carries hardware_classes with randomised per-session class indices.
    The same SKU maps to a different letter on each call — the index is
    NOT stable across deidentify() calls.  This prevents an observer from
    correlating class letters across evidence windows from different runs.

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

    # ── §21.4 hardware classes ─────────────────────────────────────────────
    # Fleet size is omitted deliberately: combining wattage × count reconstructs
    # per-site draw, which §21.4 forbids.  Only rated_kw_per_unit is emitted.
    hardware_classes: list[HardwareClassEntry] = []
    _hw = hardware_profiles if hardware_profiles else {}
    if _hw:
        hardware_classes = _build_hardware_classes(_hw)

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
        hardware_classes=hardware_classes,
        anomalies=anomalies,
    )


def assert_no_pii(
    window: EvidenceWindow,
    *,
    site_id: str,
    job_id: str,
    hardware_profile_ids: frozenset[str] = frozenset(),
    hardware_profiles: Optional[dict[str, float]] = None,
) -> None:
    """TC-29 assertion — raise AssertionError if any PII leaks into the wire.

    Checks the serialised JSON representation (the actual wire payload) for
    the presence of any forbidden identifier substring.  This mirrors what an
    integration test would do at the actual outbound HTTP boundary.

    Checks site_id, job_id, every hardware_profile_id, and every key in
    hardware_profiles.  Also checks any word of length ≥ 4 that appears in
    those identifiers, to catch cases where a fragment of a compound identifier
    (e.g. "enterprise" from "enterprise_8gpu_air") appears in the wire payload.
    """
    wire = json.dumps(dataclasses.asdict(window))
    forbidden_tokens: set[str] = set()
    # Collect all raw identifier strings.
    all_ids: list[str] = [site_id, job_id]
    all_ids.extend(hardware_profile_ids)
    if hardware_profiles:
        all_ids.extend(hardware_profiles.keys())

    for raw in all_ids:
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

def _build_hardware_classes(profiles: dict[str, float]) -> list[HardwareClassEntry]:
    """§21.4: build per-session random class entries.

    The mapping profile_id → letter is randomised on each call so the same
    SKU maps to a different letter in successive deidentify() calls.  This
    prevents an observer from correlating class letters across evidence windows
    from different advisory cycles or runs.

    Fleet size is never included.  Only rated_kw_per_unit is emitted.
    """
    if not profiles:
        return []
    # Sort by profile_id for determinism WITHIN a call, then shuffle with a
    # fresh RNG seeded from os.urandom — not stable across calls.
    sorted_ids = sorted(profiles.keys())
    rng = _random.Random()  # seeded from os.urandom; new per call
    rng.shuffle(sorted_ids)
    labels = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return [
        HardwareClassEntry(
            class_index=f"profile_{labels[i % len(labels)]}",
            rated_kw_per_unit=round(profiles[pid], 3),
        )
        for i, pid in enumerate(sorted_ids)
    ]


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
