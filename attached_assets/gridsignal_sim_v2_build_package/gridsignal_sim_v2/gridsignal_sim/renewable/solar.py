"""
Renewable-supply simulation and reserve arithmetic.

This module is the reference implementation for the standalone Renewable Supply
Console.  The browser console mirrors these formulas for offline rendering, but
whenever the server is reachable the client consumes the scalars computed here.

Spec anchors:
  §3      site configuration — 20 banks × 0.25 MW across 4 feeders
  §4.1    expected output from measured POA
  §4.2    four-state classifier with 3-tick hysteresis
  §5      contingency groups — feeder-level N−1
  §7.1.1  non-dispatchable supply, net dispatch requirement
  §7.1.2  grid-forming anchor constraint on BESS bridging
  §7.2    dispatch arbitration, step 4 insufficient-reserve check
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from renewable.config import CONFIG, SiteConfig


# ---------------------------------------------------------------------------
# state dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BankState:
    """State for one inverter bank (0.25 MW AC, 6 strings).

    `state` and `reason` are managed by _update_bank_classifier(); stressors
    may override them directly.  `_cand_state` / `_cand_ticks` are private
    hysteresis counters and are excluded from the API snapshot.
    """
    id: str
    feeder_id: str                          # "fdr-A" | "" (no feeder topology)
    rated_mw: float
    strings_total: int = 6
    strings_out: int = 0
    derate: float = 1.0                     # re-rating per §27.4
    inverter_temp_c: float = 41.0
    soil_bias: float = 1.0                  # per-bank soiling/mismatch spread
    telemetry_age_s: float = 0.0
    fault: Optional[str] = None             # "arc_fault" | "overtemp" | "feeder_open" | "operator_shutdown" | None
    # classifier outputs — managed by _update_bank_classifier
    state: str = "nominal"                  # nominal | degraded | out | no_comms
    reason: Optional[str] = None           # strings_open | inverter_derate | unknown | None
    # operator-commanded shutdown — distinct from a fault; reversible via bank_on / feeder_on
    operator_shutdown: bool = False
    # private hysteresis state (excluded from JSON output)
    _cand_state: str = field(default="nominal", init=False, repr=False, compare=False)
    _cand_ticks: int  = field(default=0,         init=False, repr=False, compare=False)
    # tick number when bank last transitioned TO out/no_comms (for common-cause detection)
    _state_changed_t: int = field(default=-999,  init=False, repr=False, compare=False)


# Backward-compat alias — external code that imports BlockState still works.
BlockState = BankState


@dataclass
class PlantState:
    poa: float
    clear_sky_poa: float
    module_temp_c: float
    soiling: float
    cloud_factor: float = 1.0
    cloud_target: float = 1.0
    p_compute_mw: float = 0.0
    p_compute_target_mw: float = 0.0
    bess_soc: float = 0.82
    # Primary name is `blocks` for backward compat with console.html and tests.
    blocks: List[BankState] = field(default_factory=list)
    t: int = 0

    @property
    def banks(self) -> List[BankState]:
        """Alias — spec §3 uses 'banks'; console.html uses 'blocks'."""
        return self.blocks


@dataclass
class ReserveResult:
    """Outcome of the §7.2 step 4 check for a single contingency."""
    delta_p_mw: float
    dt_lead_s: float
    ramp_time_s: float
    gap_s: float
    peak_shortfall_mw: float
    bridging_available_mw: float
    energy_needed_mwh: float
    sustainable_duration_s: float
    passes: bool
    deficit_mw: float
    deficit_s: float

    def to_dict(self) -> Dict:
        """JSON-safe form.

        ramp_time_s and sustainable_duration_s are legitimately infinite when no
        turbine is online or when the shortfall is zero.  Infinity is not valid
        JSON, so it is emitted as null and the console renders it as the
        unbounded symbol rather than as a number.
        """
        return {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                for k, v in asdict(self).items()}


# ---------------------------------------------------------------------------
# physics helpers
# ---------------------------------------------------------------------------

def temp_derate(cfg: SiteConfig, module_temp_c: float) -> float:
    return 1.0 - cfg.temp_derate_per_k * max(0.0, module_temp_c - cfg.temp_ref_c)


def _bank_physical_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    """Raw physics output — state-agnostic.

    Computes bank output from first principles (irradiance × soiling × string-loss
    × temperature-derate) regardless of the current `b.state`.  Used exclusively
    by _update_bank_classifier() so that a bank in 'out' or 'no_comms' can
    re-enter normal classification when physical conditions recover.

    Do NOT use this for reserve arithmetic or the SLD tile — use
    counted_output_mw() instead (which correctly returns zero for out/no_comms).
    """
    measured_poa = st.poa * st.cloud_factor
    irradiance = measured_poa / 1000.0
    sl = 1.0 - (b.strings_out / b.strings_total) if b.strings_total > 0 else 1.0
    raw = (b.rated_mw
           * irradiance
           * (1.0 - st.soiling)
           * temp_derate(cfg, st.module_temp_c)
           * sl
           * b.derate
           * b.soil_bias)
    return max(0.0, min(raw, b.rated_mw))


def bank_output_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    """Instantaneous AC output of one bank as seen at the inverter terminals.

    For 'nominal' and 'degraded' banks this is the full physics output including
    soiling, string loss, temperature derate, and the per-bank soil_bias spread.

    For 'out' and 'no_comms' banks the meter reads zero (inverter disconnected or
    telemetry absent).  Reserve checks and the SLD tile consume this value via
    counted_output_mw() which is zero for those states.

    NOTE: the classifier calls _bank_physical_mw() (not this function) so that
    recovery from 'out' and 'no_comms' is possible when conditions improve.
    """
    if b.state in ("out", "no_comms"):
        return 0.0
    return _bank_physical_mw(cfg, st, b)


def bank_expected_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    """Expected output from measured POA — spec §4.1.

    Soiling, string faults, inverter derates, and soil_bias are EXCLUDED on
    purpose so they surface as shortfall against an unchanged expectation rather
    than being absorbed into the target.

    expected_mw = rated_mw × (POA_measured / 1000) × temp_derate(module_temp_c)
    """
    measured_poa = st.poa * st.cloud_factor
    return max(0.0, min(
        b.rated_mw * (measured_poa / 1000.0) * temp_derate(cfg, st.module_temp_c),
        b.rated_mw,
    ))


def bank_clear_sky_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    """Expected output under the clear-sky model (for performance-ratio metric).

    Excludes soiling and string faults deliberately: performance ratio must be
    able to expose them.
    """
    irradiance = st.clear_sky_poa / 1000.0
    return max(0.0, min(
        b.rated_mw * irradiance * temp_derate(cfg, st.module_temp_c),
        b.rated_mw,
    ))


def counted_output_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    """Contribution of one bank to P_renewable(t).

    §27.4 / §4.3 + operator control:
      - operator_shutdown: counted at zero immediately, regardless of classifier
        state.  The classifier may lag by up to one tick; checking the flag
        directly ensures p_renewable_mw reflects the operator's action as soon
        as bank_off() is called, not one tick later.
      - out / no_comms: counted at zero (conservative).
      - degraded: counted at measured output.
    """
    if b.operator_shutdown or b.state in ("out", "no_comms"):
        return 0.0
    return bank_output_mw(cfg, st, b)


# Backward-compat alias
def block_output_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    return bank_output_mw(cfg, st, b)


# Backward-compat alias
def clear_sky_block_mw(cfg: SiteConfig, st: PlantState, b: BankState) -> float:
    return bank_clear_sky_mw(cfg, st, b)


# ---------------------------------------------------------------------------
# classifier — spec §4.2
# ---------------------------------------------------------------------------

def _raw_state(measured: float, expected: float) -> str:
    """Compute the instantaneous classifier state from measured vs expected.

    When expected == 0 (night) any measured value is nominal — zero output is
    unremarkable when expectation is also zero (TC-SOL-14).
    """
    if expected <= 0.0:
        return "nominal"
    ratio = measured / expected
    if ratio >= 0.92:
        return "nominal"
    if ratio >= 0.05:
        return "degraded"
    return "out"


def _derive_reason(b: BankState) -> Optional[str]:
    """Derive degraded reason code from observable fields (spec §4.2)."""
    if b.state != "degraded":
        return None
    if b.strings_out > 0:
        return "strings_open"
    if b.inverter_temp_c > 70.0:
        return "inverter_derate"
    # soiling (persistent ≥ 30 min) and shading (time-of-day periodic) require
    # time-series history not available in this snapshot model → unknown.
    return "unknown"


def _update_bank_classifier(cfg: SiteConfig, st: PlantState, b: BankState) -> None:
    """Update b.state and b.reason in place after one tick.

    State-machine semantics (spec §4.2):

    1. no_comms — immediate in both directions.
       Entry: telemetry_age_s > 10 → no_comms, hysteresis reset.
       Exit:  telemetry restored (age ≤ 10) → reset to nominal and re-enter
              the hysteresis loop from a clean slate; the hysteresis will
              correct to degraded/out over the next ticks if physics warrants.

    2. out (latched) — b.fault is set by an explicit stressor (arc_fault etc.).
       Stays 'out' regardless of physical output until fault is cleared by a
       reset stressor.  Prevents an accidental re-classification of a broken
       inverter as "nominal" just because the classifier observed zero vs zero.

    3. out / degraded / nominal (classifier-assigned, b.fault is None).
       3-tick hysteresis in both upgrade and downgrade directions using the
       RAW PHYSICS output (_bank_physical_mw, state-agnostic) — not the
       conservative counted value — so that a bank that physically recovers
       (strings reconnected, soiling cleared) can transition back to nominal.
    """
    # ── 1. no_comms — immediate both ways ───────────────────────────────────
    if b.telemetry_age_s > 10.0:
        if b.state != "no_comms":
            # First tick of comms loss: reset candidate so no stale ticks carry over.
            b._cand_state = "no_comms"
            b._cand_ticks = 0
            b._state_changed_t = st.t   # record transition tick for common-cause detection
        b.state = "no_comms"
        b.reason = None
        return

    if b.state == "no_comms":
        # Telemetry just restored: reset to nominal and restart hysteresis.
        b.state = "nominal"
        b._cand_state = "nominal"
        b._cand_ticks = 0
        # Fall through to normal hysteresis — this tick's measurement will
        # begin the first tick of the new candidate sequence if needed.

    # ── 2. Latched fault — stays out until fault is explicitly cleared ───────
    if b.fault is not None:
        if b.state != "out":
            # First tick the classifier locks a bank into the latched-fault path —
            # record it so the common-cause detector can catch simultaneous trips
            # (e.g. a POI trip that was set outside the classifier).
            b._state_changed_t = st.t
        b.state = "out"
        b.reason = None
        return

    # ── 3. Normal hysteresis using raw physics output ────────────────────────
    # _bank_physical_mw() ignores b.state so a previously-out bank can recover.
    physical  = _bank_physical_mw(cfg, st, b)
    expected  = bank_expected_mw(cfg, st, b)
    candidate = _raw_state(physical, expected)

    if candidate == b.state:
        # Stable — reset candidate tracker.
        b._cand_state = candidate
        b._cand_ticks = 0
    else:
        # Building toward a transition.
        if candidate == b._cand_state:
            b._cand_ticks += 1
        else:
            b._cand_state = candidate
            b._cand_ticks = 1

        if b._cand_ticks >= 3:
            old_state = b.state
            b.state = candidate
            b._cand_state = candidate
            b._cand_ticks = 0
            # Record when a bank first enters 'out' (for common-cause detection FR-SOL-2)
            if candidate == "out" and old_state != "out":
                b._state_changed_t = st.t

    b.reason = _derive_reason(b)


# ---------------------------------------------------------------------------
# plant-level aggregates
# ---------------------------------------------------------------------------

def p_renewable_mw(cfg: SiteConfig, st: PlantState) -> float:
    """P_renewable(t) = Σ counted_output_mw(bank) — spec invariant §2."""
    return sum(counted_output_mw(cfg, st, b) for b in st.blocks)


def _pms_p_renewable(cfg: SiteConfig, st: PlantState) -> float:
    """PMS-visible solar: physical output regardless of telemetry state.

    Used by the reconciliation check (FR-SOL-1) to detect situations where the
    physics engine shows generation that comms-loss banks are hiding from the
    counted value.  A sustained gap between this and p_renewable_mw() (> 0.15 MW
    for 5 consecutive ticks) raises a reconciliation_divergence advisory.
    """
    return sum(_bank_physical_mw(cfg, st, b) for b in st.blocks)


def p_clear_sky_mw(cfg: SiteConfig, st: PlantState) -> float:
    return sum(bank_clear_sky_mw(cfg, st, b) for b in st.blocks)


def p_cooling_mw(cfg: SiteConfig, st: PlantState) -> float:
    return st.p_compute_mw * cfg.pue_cooling_fraction


def p_total_mw(cfg: SiteConfig, st: PlantState) -> float:
    return st.p_compute_mw + p_cooling_mw(cfg, st)


def p_dispatch_required_mw(cfg: SiteConfig, st: PlantState) -> float:
    """§7.1.1  P_dispatch_required(t) = P_total(t) − P_renewable(t)"""
    return p_total_mw(cfg, st) - p_renewable_mw(cfg, st)


# ---------------------------------------------------------------------------
# contingency functions — spec §5
# ---------------------------------------------------------------------------

def _feeder_counted_outputs(cfg: SiteConfig, st: PlantState) -> Dict[str, float]:
    """Map feeder_id → sum of counted_output_mw for banks on that feeder.

    Degenerate case (no feeder topology): each bank gets its own group keyed by
    bank id, so largest_feeder_mw() == largest_bank_mw() (spec §5 degenerate).
    """
    totals: Dict[str, float] = {}
    for b in st.blocks:
        key = b.feeder_id if b.feeder_id else b.id
        totals[key] = totals.get(key, 0.0) + counted_output_mw(cfg, st, b)
    return totals


def largest_feeder_mw(cfg: SiteConfig, st: PlantState) -> float:
    """Largest single-feeder contingency (spec §5, AC-RES-1)."""
    totals = _feeder_counted_outputs(cfg, st)
    return max(totals.values()) if totals else 0.0


def _largest_feeder_id(cfg: SiteConfig, st: PlantState) -> str:
    totals = _feeder_counted_outputs(cfg, st)
    if not totals:
        return ""
    return max(totals, key=lambda k: totals[k])


def largest_bank_mw(cfg: SiteConfig, st: PlantState) -> float:
    """Largest single-bank contingency."""
    outs = [counted_output_mw(cfg, st, b) for b in st.blocks]
    return max(outs) if outs else 0.0


# Backward-compat alias
def largest_block_mw(cfg: SiteConfig, st: PlantState) -> float:
    return largest_bank_mw(cfg, st)


# ---------------------------------------------------------------------------
# fleet capability
# ---------------------------------------------------------------------------

def fleet_ramp_mw_per_s(cfg: SiteConfig) -> float:
    return sum(t.ramp_mw_per_s for t in cfg.turbines if t.online)


def bess_bridging_mw(cfg: SiteConfig, st: PlantState) -> float:
    """§7.1.2  BESS_bridging_available(t)
              = min(rated, usable SoC) - P_anchor_reserve

    The anchor reserve is withheld before anything else, which is why usable
    bridging falls faster than state of charge does.
    """
    anchor = cfg.anchor_reserve_mw if cfg.islanded else 0.0
    return max(0.0, min(cfg.bess_rated_mw, cfg.bess_rated_mw * st.bess_soc) - anchor)


def bess_usable_mwh(cfg: SiteConfig, st: PlantState) -> float:
    return cfg.bess_mwh * st.bess_soc * cfg.bess_usable_fraction


# ---------------------------------------------------------------------------
# reserve check — spec §7.2 step 4
# ---------------------------------------------------------------------------

def reserve_check(cfg: SiteConfig, st: PlantState,
                  delta_p_mw: float, dt_lead_s: float = 0.0) -> ReserveResult:
    """§7.2 step 4.

    A supply-side loss carries dt_lead = 0: there is no advance signal for an
    inverter trip or a severed feeder.  A compute step-load carries the 30–60 s
    of queue warning the product exists to exploit.  A compound event carries
    the shorter of the two, which is zero.

    The shortfall the BESS must cover declines linearly as the turbines ramp;
    it is not a flat draw.  Sustainable duration is compared as a duration
    against the gap window, never as an energy-like product.
    """
    r = fleet_ramp_mw_per_s(cfg)
    ramp_time = delta_p_mw / r if r > 0 else math.inf
    gap = max(0.0, ramp_time - dt_lead_s)
    peak = max(0.0, delta_p_mw - r * dt_lead_s)

    bridging = bess_bridging_mw(cfg, st)
    usable   = bess_usable_mwh(cfg, st)

    energy_needed = (peak * gap / 2.0) / 3600.0 if math.isfinite(gap) else math.inf
    sustainable_s = (usable / peak) * 3600.0 if peak > 0 else math.inf

    power_ok  = peak <= bridging
    energy_ok = energy_needed <= usable

    return ReserveResult(
        delta_p_mw=delta_p_mw,
        dt_lead_s=dt_lead_s,
        ramp_time_s=ramp_time,
        gap_s=gap,
        peak_shortfall_mw=peak,
        bridging_available_mw=bridging,
        energy_needed_mwh=energy_needed,
        sustainable_duration_s=sustainable_s,
        passes=power_ok and energy_ok,
        deficit_mw=max(0.0, peak - bridging),
        deficit_s=0.0 if energy_ok else max(0.0, gap - sustainable_s),
    )


# ---------------------------------------------------------------------------
# snapshot helpers
# ---------------------------------------------------------------------------

def _build_feeder_snapshots(cfg: SiteConfig, st: PlantState) -> List[Dict]:
    """Build per-feeder snapshot entries for GET /api/solar/state."""
    feeder_banks: Dict[str, List[BankState]] = {}
    for b in st.blocks:
        key = b.feeder_id if b.feeder_id else b.id
        feeder_banks.setdefault(key, []).append(b)

    result = []
    for fid, banks in feeder_banks.items():
        label = ("Feeder " + fid[4:]) if fid.startswith("fdr-") else fid
        output   = sum(counted_output_mw(cfg, st, b) for b in banks)
        expected = sum(bank_expected_mw(cfg, st, b) for b in banks)

        states = {b.state for b in banks}
        if states & {"out", "no_comms"}:
            f_state = "degraded"
        elif "degraded" in states:
            f_state = "degraded"
        else:
            f_state = "nominal"

        result.append({
            "id":               fid,
            "label":            label,
            "output_mw":        output,
            "expected_mw":      expected,
            "bank_ids":         [b.id for b in banks],
            "state":            f_state,
            # True only when every bank in the feeder was shut down by the operator
            "operator_shutdown": all(b.operator_shutdown for b in banks),
        })
    return result


def _build_bank_snapshots(cfg: SiteConfig, st: PlantState) -> List[Dict]:
    return [{
        "id":                b.id,
        "feeder_id":         b.feeder_id,
        "rated_mw":          b.rated_mw,
        "output_mw":         bank_output_mw(cfg, st, b),
        "expected_mw":       bank_expected_mw(cfg, st, b),
        "counted_output_mw": counted_output_mw(cfg, st, b),
        "state":             b.state,
        "reason":            b.reason,
        "strings_out":       b.strings_out,
        "strings_total":     b.strings_total,
        "inverter_temp_c":   b.inverter_temp_c,
        "telemetry_age_s":   b.telemetry_age_s,
        "operator_shutdown": b.operator_shutdown,
    } for b in st.blocks]


# ---------------------------------------------------------------------------
# simulator
# ---------------------------------------------------------------------------

class SolarSim:
    """Tick-driven simulation of the PV plant and its supply exposure.

    One instance per process.  Ticked at 1 Hz from a background task in
    api/app.py lifespan.
    """

    def __init__(self, cfg: SiteConfig = CONFIG, seed: Optional[int] = None):
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.log: List[Dict] = []
        self.state = self._seed_state()
        # Advisory state (FR-SOL-1 / FR-SOL-2)
        self._advisories: List[Dict] = []
        self._recon_diverge_ticks: int = 0
        # Run-loop sync: set by update_from_run() each tick while a run is
        # active so snapshot() reports the same plant total as the SLD tile.
        self._run_p_renewable_mw: Optional[float] = None
        self._log(
            "Session started. Seed: clear afternoon, %d banks online, %s."
            % (cfg.banks,
               "islanded with BESS as grid-forming anchor" if cfg.islanded
               else "grid-connected"),
            "",
        )

    # -- lifecycle ---------------------------------------------------------

    def _seed_state(self) -> PlantState:
        cfg = self.cfg
        banks: List[BankState] = []
        feeder_ids     = cfg.feeder_ids
        banks_per_fdr  = cfg.banks_per_feeder

        for i in range(cfg.banks):
            if feeder_ids:
                fdr_idx  = min(i // banks_per_fdr, len(feeder_ids) - 1)
                feeder_id = feeder_ids[fdr_idx]
            else:
                feeder_id = ""

            banks.append(BankState(
                id=f"bank-{i+1:02d}",
                feeder_id=feeder_id,
                rated_mw=cfg.bank_rated_ac_mw,
                strings_total=cfg.strings_per_bank,
                inverter_temp_c=41.0 + i * 0.5,   # small spread, mean ≈ 46 °C
            ))

        return PlantState(
            poa=cfg.poa_seed,
            clear_sky_poa=cfg.clear_sky_poa_seed,
            module_temp_c=cfg.module_temp_c_seed,
            soiling=cfg.soiling_loss,
            p_compute_mw=cfg.p_compute_seed_mw,
            p_compute_target_mw=cfg.p_compute_seed_mw,
            bess_soc=cfg.bess_soc,
            blocks=banks,
        )

    def reset(self) -> None:
        for t in self.cfg.turbines:
            t.online = t.id in ("gt-01", "gt-02")
        self.state = self._seed_state()
        self._advisories = []
        self._recon_diverge_ticks = 0
        self._run_p_renewable_mw = None
        self._log("Reset to nominal seed state.", "")

    # -- run-loop sync --------------------------------------------------------

    def live_aggregate_mw(self) -> float:
        """Direct feeder-physics aggregate: Σ counted_output_mw across all banks.

        Called by RunManager._drive() every tick to replace the Mistral forecast
        value in tick_result.p_renewable_mw.  This is the authoritative source:
        feeder A + feeder B + feeder C + feeder D — no AI inference involved.

        Unlike the old operator_override_mw() this runs unconditionally so the
        SLD tile, hero value, history, and WS clients always reflect the live
        bank fleet, not a pre-run irradiance curve.
        """
        return p_renewable_mw(self.cfg, self.state)

    # kept for back-compat; callers should prefer live_aggregate_mw()
    def operator_override_mw(self) -> float:
        return self.live_aggregate_mw()

    def update_from_run(self, p_renewable_mw: float) -> None:
        """Called each tick by the run loop so snapshot() reports the same
        plant total as the SLD tile.

        When set, snapshot() scales per-bank outputs proportionally so the bank
        panel and the SLD tile show an identical headline.  Fault-injected banks
        (state=out or no_comms) suppress the scaling so operator-injected events
        remain authoritative.
        """
        self._run_p_renewable_mw = p_renewable_mw

    def clear_run_sync(self) -> None:
        """Clear the run-loop sync value when a run ends or is cancelled.

        Restores snapshot() to its standalone physics output so the panel
        continues to show live irradiance-derived numbers between runs.
        """
        self._run_p_renewable_mw = None

    # -- tick --------------------------------------------------------------

    def tick(self) -> None:
        st, cfg, rng = self.state, self.cfg, self.rng
        st.t += 1

        st.cloud_factor += (st.cloud_target - st.cloud_factor) * 0.12
        if abs(st.cloud_target - st.cloud_factor) < 0.004:
            st.cloud_factor = st.cloud_target

        st.p_compute_mw += (st.p_compute_target_mw - st.p_compute_mw) * 0.18

        st.poa = _clamp(st.poa - 0.06 + (rng.random() - 0.5) * 1.6, 300, 1050)
        st.clear_sky_poa = _clamp(st.clear_sky_poa - 0.06, 320, 1100)
        st.module_temp_c = _clamp(
            st.module_temp_c + (0.01 if st.cloud_factor > 0.9 else -0.05)
            + (rng.random() - 0.5) * 0.1, 20, 70)

        for b in st.blocks:
            b.inverter_temp_c = _clamp(
                b.inverter_temp_c + (rng.random() - 0.5) * 0.3, 25, 85)

        # Update classifier for each bank after physics state has settled.
        for b in st.blocks:
            _update_bank_classifier(cfg, st, b)

        # Advisory checks run after the full tick so classifiers are settled.
        self._run_advisory_checks()

    # -- advisory engine ---------------------------------------------------

    def _run_advisory_checks(self) -> None:
        """Rebuild self._advisories after each tick.

        FR-SOL-2  Common-cause detection
            If ≥ 3 banks on the same feeder transitioned to out or no_comms
            within the last 5 ticks, emit exactly ONE common_cause advisory
            at feeder scope rather than N individual bank events.

        FR-SOL-1  Reconciliation check
            PMS-visible solar (physical output regardless of telemetry state)
            vs. modelled counted solar.  If they diverge by > 0.15 MW for 5
            consecutive ticks, raise a reconciliation_divergence advisory
            naming the suspected stale banks.
        """
        cfg, st = self.cfg, self.state
        advisories: List[Dict] = []

        # ── FR-SOL-2: Common-cause detection ────────────────────────────────
        feeder_fails: Dict[str, List[BankState]] = {}
        for b in st.blocks:
            if b.state in ("out", "no_comms") and (st.t - b._state_changed_t) <= 5:
                key = b.feeder_id if b.feeder_id else b.id
                feeder_fails.setdefault(key, []).append(b)

        for feeder_id, banks in feeder_fails.items():
            if len(banks) >= 3:
                advisories.append({
                    "code":    "common_cause",
                    "scope":   "feeder",
                    "feeder":  feeder_id,
                    "banks":   [b.id for b in banks],
                    "message": (
                        "%d banks on %s entered a failed state within 5 ticks"
                        " — likely feeder fault, not independent bank trips"
                        " (FR-SOL-2)." % (len(banks), feeder_id)
                    ),
                })

        # ── FR-SOL-1: Reconciliation check ──────────────────────────────────
        pms_solar     = _pms_p_renewable(cfg, st)
        counted_solar = p_renewable_mw(cfg, st)
        divergence    = pms_solar - counted_solar

        if divergence > 0.15:
            self._recon_diverge_ticks += 1
        else:
            self._recon_diverge_ticks = 0

        if self._recon_diverge_ticks >= 5:
            suspect = [b.id for b in st.blocks
                       if b.state == "no_comms"
                       and _bank_physical_mw(cfg, st, b) > 0.01]
            advisories.append({
                "code":    "reconciliation_divergence",
                "scope":   "plant",
                "banks":   suspect,
                "message": (
                    "PMS net-demand diverges from model by %.2f MW for %d "
                    "consecutive ticks — suspected stale telemetry on: %s "
                    "(FR-SOL-1)." % (
                        divergence, self._recon_diverge_ticks,
                        ", ".join(suspect) if suspect else "unknown",
                    )
                ),
            })

        self._advisories = advisories

    # -- stressors ---------------------------------------------------------

    def inject(self, kind: str, target: Optional[str] = None) -> Dict:
        st, cfg = self.state, self.cfg

        if kind == "cloud":
            st.cloud_target = 0.42
            self._log(
                "Cloud transient injected — POA falling to ~42%%. Plant-wide ramp "
                "bounded at %.2f MW/s by array diversity; this is not a step change."
                % cfg.cloud_ramp_bound_mw_per_s, "warn")

        elif kind == "cloud_clear":
            st.cloud_target = 1.0
            self._log("Cloud field cleared. Output recovering.", "")

        elif kind == "trip":
            live = [b for b in st.blocks if b.state not in ("out", "no_comms")]
            if not live:
                self._log("All banks already offline.", "bad")
            else:
                b = self.rng.choice(live)
                b.state    = "out"
                b.fault    = "arc_fault"
                b._cand_state = "out"
                b._cand_ticks = 0
                b._state_changed_t = st.t   # record for common-cause window
                self._log(
                    "%s tripped — DC arc-fault. %.2f MW step change, "
                    "Δt_lead = 0. BESS bridging engaged." % (b.id, b.rated_mw), "bad")

        elif kind == "poi":
            for b in st.blocks:
                b.state    = "out"
                b.fault    = "feeder_open"
                b._cand_state = "out"
                b._cand_ticks = 0
                b._state_changed_t = st.t   # simultaneous trip — common-cause per feeder
            self._log(
                "POI breaker open — entire array disconnected. This is the sizing "
                "contingency: a step change with no advance signal.", "bad")

        elif kind == "soil":
            st.soiling = _clamp(st.soiling + 0.035, 0, 0.25)
            self.rng.choice(st.blocks).strings_out += 2
            self._log(
                "Soiling stepped to %.1f%% and two strings opened. Degraded, not "
                "unavailable — the bank is counted at re-rated capability (§27.4)."
                % (st.soiling * 100), "warn")

        elif kind == "spike":
            st.p_compute_target_mw = st.p_compute_mw + 6.0
            self._log(
                "Compute step-load +6.00 MW staged from queue telemetry. "
                "Δt_lead = 30 s on this term only.", "warn")

        elif kind == "turbine":
            on = [t for t in cfg.turbines if t.online]
            if len(on) <= 1:
                self._log("Cannot take the last turbine offline while islanded.", "bad")
            else:
                on[-1].online = False
                self._log(
                    "%s offline. Ramp now %.2f MW/s — every gap window lengthens."
                    % (on[-1].id, fleet_ramp_mw_per_s(cfg)), "bad")

        elif kind == "bess":
            st.bess_soc = 0.30 if st.bess_soc > 0.4 else cfg.bess_soc
            self._log(
                "BESS state of charge set to %.0f%%. Anchor-adjusted bridging is now "
                "%.2f MW — the anchor duty is withheld first, so usable bridging "
                "falls faster than SoC."
                % (st.bess_soc * 100, bess_bridging_mw(cfg, st)),
                "bad" if st.bess_soc < 0.4 else "")

        elif kind == "feeder_open":
            # Trip entire fdr-B: feeder breaker opens, telemetry drops AND power stops.
            # Setting derate=0 models the open feeder (no current flow); telemetry_age_s
            # keeps classifier in no_comms.  Sets _state_changed_t so the common-cause
            # advisory fires on the next tick (FR-SOL-2).
            fdr_b = [b for b in st.blocks if b.feeder_id == "fdr-B"]
            if not fdr_b:
                return {"ok": False, "error": "no banks on fdr-B in current config"}
            for b in fdr_b:
                b.telemetry_age_s = 999.0
                b.derate = 0.0          # feeder open → no physical output
                b.state = "no_comms"
                b._cand_state = "no_comms"
                b._cand_ticks = 0
                b._state_changed_t = st.t   # for FR-SOL-2 common-cause window
            self._log(
                "fdr-B feeder breaker opened — %d banks disconnected. "
                "Telemetry and output both zero. Common-cause advisory expected."
                % len(fdr_b), "bad")

        elif kind == "bank_trip":
            # Same as 'trip': one random bank trips to out (arc-fault latch).
            live = [b for b in st.blocks if b.state not in ("out", "no_comms")]
            if not live:
                self._log("All banks already offline.", "bad")
            else:
                b = self.rng.choice(live)
                b.state = "out"
                b.fault = "arc_fault"
                b._cand_state = "out"
                b._cand_ticks = 0
                b._state_changed_t = st.t
                self._log(
                    "%s bank-trip — DC arc-fault. %.2f MW step, Δt_lead=0."
                    % (b.id, b.rated_mw), "bad")

        elif kind == "bank_derate":
            # Push one bank into degraded via inverter overtemp.  The bank continues
            # to produce, but at reduced capability (~80% due to thermal derate).
            live = [b for b in st.blocks if b.state not in ("out", "no_comms")]
            if not live:
                self._log("No live banks to derate.", "bad")
            else:
                b = self.rng.choice(live)
                b.inverter_temp_c = 82.0    # sustained overtemp → reason=inverter_derate
                b.derate = 0.80             # 20% nameplate reduction
                b.state = "degraded"
                b.reason = "inverter_derate"
                b._cand_state = "degraded"
                b._cand_ticks = 0
                self._log(
                    "%s inverter overtemp — derated to 80%%. Counted at measured, not "
                    "zero (§27.4)." % b.id, "warn")

        elif kind == "comms_loss":
            # Telemetry loss on fdr-A: banks are still generating but we can't see them.
            # derate is deliberately left at 1.0 so _pms_p_renewable() shows output while
            # counted_output_mw() returns 0 (no_comms) → triggers reconciliation_divergence
            # after 5 consecutive ticks (FR-SOL-1).
            fdr_a = [b for b in st.blocks if b.feeder_id == "fdr-A"]
            if not fdr_a:
                return {"ok": False, "error": "no banks on fdr-A in current config"}
            for b in fdr_a:
                b.telemetry_age_s = 999.0   # comms drop
                b.state = "no_comms"
                b._cand_state = "no_comms"
                b._cand_ticks = 0
                b._state_changed_t = st.t
                # derate unchanged — physical output continues (FR-SOL-1 trigger)
            self._log(
                "fdr-A comms loss — %d banks invisible to model but still generating. "
                "Reconciliation divergence expected within 5 ticks (FR-SOL-1)."
                % len(fdr_a), "warn")

        elif kind == "reset":
            self.reset()

        elif kind == "bank_off":
            if not target:
                return {"ok": False, "error": "bank_off requires ?target=<bank_id>"}
            b = next((b for b in st.blocks if b.id == target), None)
            if b is None:
                return {"ok": False, "error": "unknown bank: %s" % target}
            b.operator_shutdown = True
            b.fault = "operator_shutdown"
            b.state = "out"
            b._cand_state = "out"
            b._cand_ticks = 0
            b.derate = 0.0
            b._state_changed_t = st.t
            self._log("%s shut down by operator. Output: 0 MW." % target, "warn")
            return {"ok": True, "kind": kind, "message": "%s offline" % target}

        elif kind == "bank_on":
            if not target:
                return {"ok": False, "error": "bank_on requires ?target=<bank_id>"}
            b = next((b for b in st.blocks if b.id == target), None)
            if b is None:
                return {"ok": False, "error": "unknown bank: %s" % target}
            b.operator_shutdown = False
            b.fault = None
            b.state = "nominal"
            b._cand_state = "nominal"
            b._cand_ticks = 0
            b.derate = 1.0
            b.telemetry_age_s = 0.0
            self._log("%s restored by operator. Returning to nominal." % target, "")
            return {"ok": True, "kind": kind, "message": "%s online" % target}

        elif kind == "feeder_off":
            if not target:
                return {"ok": False, "error": "feeder_off requires ?target=<feeder_id>"}
            banks = [b for b in st.blocks if b.feeder_id == target]
            if not banks:
                return {"ok": False, "error": "no banks found on feeder: %s" % target}
            for b in banks:
                b.operator_shutdown = True
                b.fault = "operator_shutdown"
                b.state = "out"
                b._cand_state = "out"
                b._cand_ticks = 0
                b.derate = 0.0
                b._state_changed_t = st.t
            self._log(
                "%s shut down by operator — %d banks offline." % (target, len(banks)), "warn")
            return {"ok": True, "kind": kind,
                    "message": "%s offline (%d banks)" % (target, len(banks))}

        elif kind == "feeder_on":
            if not target:
                return {"ok": False, "error": "feeder_on requires ?target=<feeder_id>"}
            banks = [b for b in st.blocks if b.feeder_id == target]
            if not banks:
                return {"ok": False, "error": "no banks found on feeder: %s" % target}
            for b in banks:
                b.operator_shutdown = False
                b.fault = None
                b.state = "nominal"
                b._cand_state = "nominal"
                b._cand_ticks = 0
                b.derate = 1.0
                b.telemetry_age_s = 0.0
            self._log(
                "%s restored by operator — %d banks returning to nominal." % (target, len(banks)), "")
            return {"ok": True, "kind": kind,
                    "message": "%s online (%d banks)" % (target, len(banks))}

        else:
            return {"ok": False, "error": "unknown stressor: %s" % kind}

        return {"ok": True, "kind": kind}

    # -- snapshot ----------------------------------------------------------

    def snapshot(self) -> Dict:
        cfg, st = self.cfg, self.state
        solar      = p_renewable_mw(cfg, st)
        clear_sky  = p_clear_sky_mw(cfg, st)
        total      = p_total_mw(cfg, st)
        p_expected = sum(bank_expected_mw(cfg, st, b) for b in st.blocks)

        banks_reporting = sum(1 for b in st.blocks if b.state != "no_comms")
        n1_feeder_mw    = largest_feeder_mw(cfg, st)
        n1_feeder_id    = _largest_feeder_id(cfg, st)
        n1_bank_mw      = largest_bank_mw(cfg, st)

        # Reserve check: N−1 sized on feeder (spec §5 / AC-RES-1)
        rc_n1_feeder = reserve_check(cfg, st, n1_feeder_mw, 0.0)
        rc_n1_bank   = reserve_check(cfg, st, n1_bank_mw,   0.0)
        rc_plant     = reserve_check(cfg, st, solar,        0.0)
        rc_compound  = reserve_check(cfg, st, solar + 6.0,  0.0)

        bank_snaps   = _build_bank_snapshots(cfg, st)
        feeder_snaps = _build_feeder_snapshots(cfg, st)

        # No run-sync scaling.  tick_result.p_renewable_mw is now always set to
        # live_aggregate_mw() — the same physics sum as `solar` here — so there
        # is nothing to reconcile.  Feeder and bank values are computed directly
        # from counted_output_mw / bank_output_mw and sum correctly by
        # construction: feeder.output_mw = Σ bank.counted_output_mw for that
        # feeder.  No AI-derived value touches these numbers.

        return {
            "t": st.t,
            "wall_clock": time.strftime("%H:%M:%S"),
            "site": {
                "id":                       cfg.site_id,
                "islanded":                 cfg.islanded,
                "plant_rated_ac_mw":        cfg.plant_rated_ac_mw,
                "plant_rated_dc_mwp":       cfg.plant_rated_dc_mwp,
                "banks":                    cfg.banks,
                "blocks":                   cfg.banks,           # compat alias
                "bank_rated_ac_mw":         cfg.bank_rated_ac_mw,
                "block_rated_ac_mw":        cfg.bank_rated_ac_mw, # compat alias
                "dcac_ratio":               cfg.dcac_ratio,
                "strings_per_bank":         cfg.strings_per_bank,
                "strings_per_block":        cfg.strings_per_bank, # compat alias
                "feeders":                  list(cfg.feeder_ids),
                "mount":                    cfg.mount,
                "cloud_ramp_bound_mw_per_s": cfg.cloud_ramp_bound_mw_per_s,
                "bess_rated_mw":            cfg.bess_rated_mw,
                "bess_mwh":                 cfg.bess_mwh,
                "anchor_reserve_mw":        cfg.anchor_reserve_mw,
            },
            "atmosphere": {
                "poa":            st.poa * st.cloud_factor,
                "poa_clear_sky":  st.clear_sky_poa,
                "cloud_factor":   st.cloud_factor,
                "module_temp_c":  st.module_temp_c,
                "soiling":        st.soiling,
            },
            "power": {
                "p_renewable_mw":       solar,
                "p_expected_mw":        p_expected,
                "banks_reporting":      banks_reporting,
                "banks_total":          len(st.blocks),
                "p_clear_sky_mw":       clear_sky,
                "performance_ratio":    (solar / clear_sky * 100.0) if clear_sky else 0.0,
                "p_compute_mw":         st.p_compute_mw,
                "p_cooling_mw":         p_cooling_mw(cfg, st),
                "p_total_mw":           total,
                "p_dispatch_required_mw": p_dispatch_required_mw(cfg, st),
                "share_of_site_draw_pct": (solar / total * 100.0) if total else 0.0,
                "clipping":             solar >= cfg.plant_rated_ac_mw * 0.995,
            },
            "fleet": {
                "turbines": [{"id": t.id, "mw": t.mw, "online": t.online,
                              "ramp_mw_per_s": t.ramp_mw_per_s} for t in cfg.turbines],
                "fleet_ramp_mw_per_s": fleet_ramp_mw_per_s(cfg),
                "bess_soc":            st.bess_soc,
                "bess_bridging_mw":    bess_bridging_mw(cfg, st),
                "bess_usable_mwh":     bess_usable_mwh(cfg, st),
            },
            # Primary key 'banks'; 'blocks' retained as alias for one release.
            "banks":  bank_snaps,
            "blocks": bank_snaps,
            "feeders": feeder_snaps,
            "exposure": {
                "largest_bank_mw":      n1_bank_mw,
                "largest_feeder_mw":    n1_feeder_mw,
                "largest_feeder_id":    n1_feeder_id,
                "plant_loss_mw":        solar,
                "cloud_ramp_mw_per_s":  cfg.cloud_ramp_bound_mw_per_s,
                # compat alias
                "n1_block_mw":          n1_bank_mw,
            },
            "reserve": {
                "n1_feeder":  rc_n1_feeder.to_dict(),
                "n1_bank":    rc_n1_bank.to_dict(),
                "n1":         rc_n1_feeder.to_dict(),   # compat alias: n1 = feeder figure
                "plant":      rc_plant.to_dict(),
                "compound":   rc_compound.to_dict(),
            },
            "log":        self.log[:40],
            "advisories": list(self._advisories),
        }

    # -- internals ---------------------------------------------------------

    def _log(self, msg: str, kind: str = "") -> None:
        self.log.insert(0, {"ts": time.strftime("%H:%M:%S"), "msg": msg, "kind": kind})
        del self.log[60:]


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)
