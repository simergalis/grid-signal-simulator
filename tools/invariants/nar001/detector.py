"""ChangeDetector -- deterministic change detection over consecutive tick payloads.

RATE detects *sustained* ramps only. Requiring consecutive confirmations means a
single-tick step change -- exactly one tick of high derivative -- can never
satisfy the predicate and is structurally invisible to it. That is deliberate: a
single-tick derivative on a coarse tick is indistinguishable from noise. Step
changes are LEVEL's job, and LEVEL catches them on the tick they land. Do not
add a step-detection role to RATE by dropping the confirmation count; that
reintroduces the noise the count exists to suppress.

Deterministic function of (state, payload). No I/O, no clock reads, no RNG, no
literals: every deadband, rate band, and confirmation count is supplied by the
caller from the runtime parameter catalogue. A missing parameter raises at
construction with the full list, rather than being defaulted.

A change is a fact, not an opinion. This module reports what moved. It does not
rank, score, classify severity, or attribute cause -- interpretation happens once,
downstream, so there is one place to look when the interpretation is wrong.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .access import NULL, OK, resolve, resolve_number

# Change kinds
LEVEL = "level"                 # continuous, deadbanded against last reported value
EDGE = "edge"                   # discrete transition, never deadbanded
RATE = "rate"                   # sustained d/dt past a band; see the note below
SET = "set"                     # collection membership change
AVAILABILITY = "availability"   # a field appearing, disappearing, or going null
COUNT = "count"                 # length of a collection changed

# Domains
SCHED, LOAD, GEN, DEMAND, RENEW, THERM, VERDICT = (
    "SCHED", "LOAD", "GEN", "DEMAND", "RENEW", "THERM", "VERDICT")


@dataclass(frozen=True)
class ChangeRecord:
    seq: int
    run_id: str
    t_sim_s: float | None
    domain: str
    signal: str
    kind: str
    prev: Any
    curr: Any
    delta: Any = None
    units: str | None = None
    deadband_applied: float | None = None
    deadband_key: str | None = None
    wire_path: str | None = None
    spec_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SignalSpec:
    signal: str
    domain: str
    kind: str
    aliases: tuple[str, ...]
    band_key: str | None = None       # catalogue key for the deadband or rate band
    confirm_key: str | None = None    # catalogue key for consecutive confirmations
    units: str | None = None
    spec_ref: str | None = None
    per_unit: bool = False            # expand over turbine_units[]


def _u(template: str, i: int) -> str:
    return template.format(i=i)


# ---------------------------------------------------------------------------
# Registry. Wire names are those confirmed by the NAR-001 inventory; where the
# wire carries two names for one quantity both are listed and the first to
# resolve is used, with the path recorded on every emitted record.
#
# band_key values name catalogue parameters. This module supplies none of their
# values. Candidate existing keys with overlapping semantics are noted in
# CANDIDATE_EXISTING_KEYS below but are deliberately not wired -- reusing or
# adding a key is a configuration decision, not a detector decision.
# ---------------------------------------------------------------------------
REGISTRY: tuple[SignalSpec, ...] = (
    # --- scheduler / workload -------------------------------------------------
    SignalSpec("SCHED.checkpoint_states", SCHED, SET, ("checkpoint_states",),
               spec_ref="§6.2"),
    SignalSpec("SCHED.dt_lead_next_s", SCHED, LEVEL, ("dt_lead_next_s",),
               band_key="deadband_dt_lead_s", units="s", spec_ref="§7.2"),
    SignalSpec("SCHED.step_kind", SCHED, EDGE, ("step_kind",)),
    SignalSpec("SCHED.step_phase", SCHED, LEVEL, ("step_phase",),
               band_key="deadband_step_phase", units="fraction"),
    SignalSpec("SCHED.active_jobs", SCHED, EDGE, ("kube_metrics.active_jobs",),
               units="count"),
    SignalSpec("SCHED.admitted_nodes", SCHED, EDGE, ("kube_metrics.admitted_nodes",),
               units="count"),
    SignalSpec("SCHED.node_count", SCHED, EDGE, ("kube_metrics.node_count",),
               units="count"),

    # --- load -----------------------------------------------------------------
    SignalSpec("LOAD.p_compute_demand_mw", LOAD, LEVEL,
               ("p_compute_demand_mw", "p_compute_mw"),
               band_key="deadband_power_mw", units="MW", spec_ref="§4"),
    SignalSpec("LOAD.p_demand_mw", LOAD, LEVEL, ("p_demand_mw", "p_total_mw"),
               band_key="deadband_power_mw", units="MW", spec_ref="§4"),
    SignalSpec("LOAD.p_demand_rate", LOAD, RATE, ("p_demand_mw", "p_total_mw"),
               band_key="rate_band_mw_per_s", confirm_key="rate_confirm_ticks",
               units="MW/s"),
    SignalSpec("LOAD.net_demand_mw", LOAD, LEVEL, ("net_demand_mw",),
               band_key="deadband_power_mw", units="MW"),
    SignalSpec("LOAD.p_served_mw", LOAD, LEVEL, ("p_served_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§23"),
    SignalSpec("LOAD.p_unserved_mw", LOAD, LEVEL, ("p_unserved_mw",),
               band_key="deadband_power_small_mw", units="MW", spec_ref="§23"),

    # --- generation and storage ----------------------------------------------
    SignalSpec("GEN.unit_state", GEN, EDGE, ("turbine_units[{i}].state",),
               per_unit=True, spec_ref="§7.1.3"),
    SignalSpec("GEN.unit_output_mw", GEN, LEVEL, ("turbine_units[{i}].output_mw",),
               band_key="deadband_power_mw", units="MW", per_unit=True),
    SignalSpec("GEN.unit_count", GEN, COUNT, ("turbine_units",), units="count"),
    SignalSpec("GEN.turbine_output_mw", GEN, LEVEL, ("turbine_output_mw",),
               band_key="deadband_power_mw", units="MW"),
    SignalSpec("GEN.p_generation_mw", GEN, LEVEL, ("p_generation_mw",),
               band_key="deadband_power_mw", units="MW"),
    SignalSpec("GEN.d4_balance_defect_mw", GEN, LEVEL, ("d4_balance_defect_mw",),
               band_key="deadband_power_small_mw", units="MW"),
    SignalSpec("GEN.grid_exchange_mw", GEN, LEVEL, ("grid_exchange_mw",),
               band_key="deadband_power_mw", units="MW"),
    SignalSpec("GEN.asset_delivery_error_mw", GEN, LEVEL,
               ("asset_delivery_error_mw",),
               band_key="deadband_power_small_mw", units="MW"),
    SignalSpec("GEN.frequency_forcing_mw", GEN, LEVEL, ("frequency_forcing_mw",),
               band_key="deadband_power_mw", units="MW"),
    SignalSpec("GEN.protection_provisional", GEN, EDGE, ("protection_provisional",),
               spec_ref="§28.4"),
    SignalSpec("GEN.bess_rated_mw", GEN, EDGE, ("bess_rated_mw",), units="MW"),
    SignalSpec("GEN.bess_usable_mwh", GEN, EDGE, ("bess_usable_mwh",), units="MWh"),
    SignalSpec("GEN.bess_output_mw", GEN, LEVEL, ("bess_output_mw",),
               band_key="deadband_power_mw", units="MW"),
    SignalSpec("GEN.bess_soc_fraction", GEN, LEVEL, ("bess_soc_fraction",),
               band_key="deadband_soc_fraction", units="fraction"),
    SignalSpec("GEN.committed_rated_mw", GEN, LEVEL,
               ("commitment_block.committed_rated_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§7.1.2"),
    SignalSpec("GEN.reserve_floor_mw", GEN, LEVEL,
               ("commitment_block.reserve_floor_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§7.1.2"),
    SignalSpec("GEN.reserve_satisfied", GEN, EDGE,
               ("commitment_block.reserve_satisfied",), spec_ref="§7.2"),
    SignalSpec("GEN.commitment_action", GEN, EDGE, ("commitment_block.action",),
               spec_ref="§7.1.3"),
    SignalSpec("GEN.frequency_hz", GEN, LEVEL, ("frequency_hz",),
               band_key="deadband_frequency_hz", units="Hz", spec_ref="§28.4"),
    SignalSpec("GEN.contingency_state", GEN, EDGE, ("contingency_coverage.state",),
               spec_ref="§7.2"),
    SignalSpec("GEN.shed_required_mw", GEN, LEVEL,
               ("contingency_coverage.shed_required_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§23"),

    # --- demand / forecast ----------------------------------------------------
    SignalSpec("DEMAND.forecast_mw", DEMAND, LEVEL, ("forecast_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§12"),
    SignalSpec("DEMAND.confidence_lower_mw", DEMAND, LEVEL, ("confidence_lower_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§12"),
    SignalSpec("DEMAND.confidence_upper_mw", DEMAND, LEVEL, ("confidence_upper_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§12"),
    SignalSpec("DEMAND.data_quality_tags", DEMAND, SET, ("data_quality_tags",),
               spec_ref="§5.1"),
    SignalSpec("DEMAND.insufficient_reserve_alert", DEMAND, EDGE,
               ("insufficient_reserve_alert",), spec_ref="§7.2"),

    # --- renewable ------------------------------------------------------------
    SignalSpec("RENEW.p_renewable_mw", RENEW, LEVEL, ("p_renewable_mw",),
               band_key="deadband_power_mw", units="MW", spec_ref="§7.1.1"),
    SignalSpec("RENEW.p_expected_mw", RENEW, LEVEL, ("p_expected_mw",),
               band_key="deadband_power_mw", units="MW"),
    SignalSpec("RENEW.banks_reporting", RENEW, EDGE, ("banks_reporting",),
               units="count"),
    SignalSpec("RENEW.solar_conditions", RENEW, EDGE, ("solar_conditions",)),

    # --- thermal --------------------------------------------------------------
    SignalSpec("THERM.p_cooling_demand_mw", THERM, LEVEL,
               ("p_cooling_demand_mw", "p_cooling_mw"),
               band_key="deadband_power_mw", units="MW", spec_ref="§8"),
    # Ratings are configuration. Any change matters, including one smaller than
    # a power deadband, so these are edges rather than deadbanded levels.
    SignalSpec("THERM.rated_cooling_mw", THERM, EDGE, ("rated_cooling_mw",),
               units="MW"),
    SignalSpec("THERM.ambient_avg_c", THERM, LEVEL, ("ambient_avg_c",),
               band_key="deadband_temp_c", units="degC"),
    SignalSpec("THERM.compute_inlet_temp_c", THERM, LEVEL, ("compute_inlet_temp_c",),
               band_key="deadband_temp_c", units="degC"),
)

# Existing catalogue keys whose semantics overlap the bands this module needs.
# Recorded so the overlap is visible; deliberately not wired. Choosing to reuse
# one, or to add a new key, is a configuration decision requiring a DR.
CANDIDATE_EXISTING_KEYS: dict[str, tuple[str, ...]] = {
    "deadband_power_mw": ("levelled_off_epsilon_mw", "levelled_off_tol_mw"),
    "deadband_power_small_mw": ("levelled_off_epsilon_mw",),
    "rate_confirm_ticks": ("levelled_off_window_s", "commit_confirm_s"),
}


class MissingParameters(KeyError):
    """Raised when the catalogue lacks bands the registry requires.

    Stop and report rather than invent a constant: every missing key is listed
    at once so the caller sees the whole gap, not the first one.
    """

    def __init__(self, keys: list[str]):
        self.keys = sorted(keys)
        super().__init__(
            "catalogue is missing required parameters: " + ", ".join(self.keys))


@dataclass
class _SignalState:
    last_reported: Any = None      # value at last emission -- hysteresis baseline
    last_seen: Any = None          # value at previous tick
    availability: str | None = None
    rate_confirmations: int = 0
    rate_armed: bool = True
    seen: bool = False


@dataclass
class DetectorState:
    signals: dict[str, _SignalState] = field(default_factory=dict)
    last_sim_time_s: float | None = None

    def get(self, key: str) -> _SignalState:
        st = self.signals.get(key)
        if st is None:
            st = _SignalState()
            self.signals[key] = st
        return st


class ChangeDetector:
    """Emits ChangeRecords for what moved between consecutive tick payloads."""

    def __init__(self, catalogue: dict[str, Any],
                 registry: Iterable[SignalSpec] = REGISTRY):
        self.registry = tuple(registry)
        missing = []
        for spec in self.registry:
            for key in (spec.band_key, spec.confirm_key):
                if key is not None and key not in catalogue:
                    missing.append(key)
        if missing:
            raise MissingParameters(list(set(missing)))
        self.catalogue = dict(catalogue)
        self.state = DetectorState()

    # -- helpers ----------------------------------------------------------
    def _band(self, spec: SignalSpec) -> float:
        return float(self.catalogue[spec.band_key])

    def _paths(self, spec: SignalSpec, payload: dict) -> list[tuple[str, tuple[str, ...]]]:
        """(state_key, aliases) pairs -- one per unit for per-unit signals."""
        if not spec.per_unit:
            return [(spec.signal, spec.aliases)]
        units = resolve(payload, "turbine_units")
        n = len(units.value) if units.ok and isinstance(units.value, list) else 0
        return [(f"{spec.signal}[{i}]", tuple(_u(a, i) for a in spec.aliases))
                for i in range(n)]

    def _rec(self, spec, key, seq, run_id, t, kind, prev, curr, **kw) -> ChangeRecord:
        return ChangeRecord(
            seq=seq, run_id=run_id, t_sim_s=t, domain=spec.domain, signal=key,
            kind=kind, prev=prev, curr=curr, units=spec.units,
            spec_ref=spec.spec_ref, **kw)

    # -- main -------------------------------------------------------------
    def step(self, run_id: str, seq: int, payload: dict[str, Any]) -> list[ChangeRecord]:
        t_res = resolve_number(payload, "sim_time_seconds")
        t = t_res.value if t_res.ok else None
        dt = (t - self.state.last_sim_time_s
              if t is not None and self.state.last_sim_time_s is not None else None)

        out: list[ChangeRecord] = []
        for spec in self.registry:
            for key, aliases in self._paths(spec, payload):
                out.extend(self._one(spec, key, aliases, run_id, seq, t, dt, payload))

        if t is not None:
            self.state.last_sim_time_s = t
        return out

    def _one(self, spec, key, aliases, run_id, seq, t, dt, payload) -> list[ChangeRecord]:
        st = self.state.get(key)
        out: list[ChangeRecord] = []

        if spec.kind == COUNT:
            r = resolve(payload, *aliases)
            curr = len(r.value) if r.ok and isinstance(r.value, (list, tuple)) else None
            if st.seen and curr != st.last_seen:
                out.append(self._rec(spec, key, seq, run_id, t, COUNT,
                                     st.last_seen, curr, wire_path=r.path))
            st.last_seen, st.seen = curr, True
            return out

        raw = resolve(payload, *aliases)

        # Availability transitions are changes in their own right: a field going
        # null is information, and coercing it to a value would destroy it.
        avail = raw.state
        if st.availability is not None and avail != st.availability:
            out.append(self._rec(spec, key, seq, run_id, t, AVAILABILITY,
                                 st.availability, avail, wire_path=raw.path))
        st.availability = avail
        if avail != OK:
            if avail == NULL:
                st.last_seen = None
            return out

        if spec.kind == SET:
            curr = self._as_set(raw.value)
            if st.seen and curr != st.last_seen:
                added = sorted(curr - (st.last_seen or set()))
                removed = sorted((st.last_seen or set()) - curr)
                out.append(self._rec(spec, key, seq, run_id, t, SET,
                                     sorted(st.last_seen or set()), sorted(curr),
                                     delta={"added": added, "removed": removed},
                                     wire_path=raw.path))
            st.last_seen, st.seen = curr, True
            return out

        if spec.kind == EDGE:
            curr = raw.value
            # Discrete transitions are never deadbanded and never suppressed.
            if st.seen and curr != st.last_seen:
                out.append(self._rec(spec, key, seq, run_id, t, EDGE,
                                     st.last_seen, curr, wire_path=raw.path))
            st.last_seen, st.seen = curr, True
            return out

        num = resolve_number(payload, *aliases)
        if not num.ok:
            return out
        curr = num.value

        if spec.kind == LEVEL:
            band = self._band(spec)
            if not st.seen:
                st.last_reported, st.last_seen, st.seen = curr, curr, True
                return out
            # Hysteresis is against the last *reported* value, not the last tick:
            # comparing to the previous tick lets a slow ramp emit nothing and a
            # dithering signal emit forever.
            if abs(curr - st.last_reported) >= band:
                out.append(self._rec(spec, key, seq, run_id, t, LEVEL,
                                     st.last_reported, curr,
                                     delta=curr - st.last_reported,
                                     deadband_applied=band,
                                     deadband_key=spec.band_key,
                                     wire_path=num.path))
                st.last_reported = curr
            st.last_seen = curr
            return out

        if spec.kind == RATE:
            band = self._band(spec)
            raw_need = self.catalogue[spec.confirm_key]
            if raw_need != raw_need or raw_need in (float("inf"), float("-inf")):
                st.last_seen, st.seen = curr, True
                return out          # unreachable confirmation count = disabled
            need = int(raw_need)
            if not st.seen or dt is None or dt <= 0:
                st.last_seen, st.seen = curr, True
                return out
            rate = (curr - st.last_seen) / dt
            if abs(rate) >= band:
                st.rate_confirmations += 1
                # Single-tick derivative on a coarse tick is noise; a rate must
                # be confirmed on consecutive ticks before it is reported, and
                # must fall back inside the band before it can fire again.
                if st.rate_confirmations >= need and st.rate_armed:
                    out.append(self._rec(spec, key, seq, run_id, t, RATE,
                                         st.last_seen, curr, delta=rate,
                                         deadband_applied=band,
                                         deadband_key=spec.band_key,
                                         wire_path=num.path))
                    st.rate_armed = False
            else:
                st.rate_confirmations = 0
                st.rate_armed = True
            st.last_seen = curr
            return out

        return out

    @staticmethod
    def _as_set(value: Any) -> set:
        if isinstance(value, dict):
            return {f"{k}={v}" for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return set(value)
        return {value}


def band_parameters(registry: Iterable[SignalSpec] = REGISTRY) -> list[str]:
    """Catalogue keys that are magnitudes (deadbands and rate bands)."""
    return sorted({s.band_key for s in registry if s.band_key})


def confirmation_parameters(registry: Iterable[SignalSpec] = REGISTRY) -> list[str]:
    """Catalogue keys that are integer counts of consecutive confirmations.

    Kept distinct from bands because they are not interchangeable: writing a
    magnitude into a count is a type error that a sweep would otherwise make.
    """
    return sorted({s.confirm_key for s in registry if s.confirm_key})


def required_parameters(registry: Iterable[SignalSpec] = REGISTRY) -> list[str]:
    """Every catalogue key the registry needs. Supplied by the caller, never here."""
    return sorted(set(band_parameters(registry)) | set(confirmation_parameters(registry)))
