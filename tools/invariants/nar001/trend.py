"""TrendAggregator -- multi-scale trend facts over a bounded sim-time history.

A window digest cannot represent a trend. Compute demand descending 65 -> 38 MW
across five minutes in a dozen small decrements produces, in any 30 s window, one
step of a fraction of a megawatt. The narration from that would be true and
useless. This module computes the trend separately and hands it over as a fact.

Windows are measured in **simulated seconds**, never wall seconds and never tick
counts, so a run at 10x playback yields the same trends as the same run at 1x.

The model never computes a slope. Slopes, directions, and step counts are
produced here, deterministically, and are copied verbatim downstream like any
other numeral.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .access import resolve_number
from .detector import LEVEL, REGISTRY, SignalSpec

RISING, FALLING, FLAT, OSCILLATING, INSUFFICIENT = (
    "rising", "falling", "flat", "oscillating", "insufficient")

# Catalogue keys. Values are supplied by the caller; this module defines none.
WINDOWS_KEY = "trend_windows_s"
REVERSALS_KEY = "trend_reversal_n"
TREND_PARAMETERS = (WINDOWS_KEY, REVERSALS_KEY)


@dataclass(frozen=True)
class TrendFact:
    run_id: str
    seq: int
    t_sim_s: float | None
    signal: str
    domain: str
    window_s: float
    units: str | None
    n_samples: int
    span_s: float
    first: float
    last: float
    delta: float
    slope_per_min: float          # least squares over the window
    net_slope_per_min: float      # (last - first) / span; differs when oscillating
    direction: str
    monotonic_fraction: float | None   # None when the signal did not move
    n_moves: int                       # non-zero deltas in the window
    n_sign_reversals: int
    step_count: int
    mean_step: float | None
    peak_in_window: float
    trough_in_window: float
    run_peak: float
    run_trough: float
    pct_from_run_peak: float | None
    step_band: float | None       # the signal's own deadband, reused as the step size
    band_key: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MissingTrendParameters(KeyError):
    def __init__(self, keys: list[str]):
        self.keys = sorted(keys)
        super().__init__(
            "catalogue is missing required trend parameters: " + ", ".join(self.keys))


@dataclass
class _History:
    samples: deque = field(default_factory=deque)   # (t_sim_s, value)
    run_peak: float | None = None
    run_trough: float | None = None


def _least_squares_slope(points: list[tuple[float, float]]) -> float:
    n = len(points)
    if n < 2:
        return 0.0
    mx = sum(t for t, _ in points) / n
    my = sum(v for _, v in points) / n
    num = sum((t - mx) * (v - my) for t, v in points)
    den = sum((t - mx) ** 2 for t, _ in points)
    return num / den if den else 0.0


class TrendAggregator:
    """Ingest ticks with update(); read trends with facts().

    facts() is deliberately not called per tick. Emitting every signal at every
    window on every tick would produce more trend records than change records,
    for a quantity that by definition changes slowly. The assembler calls it once
    per narration window.
    """

    def __init__(self, catalogue: dict[str, Any],
                 registry: Iterable[SignalSpec] = REGISTRY):
        missing = [k for k in TREND_PARAMETERS if k not in catalogue]
        if missing:
            raise MissingTrendParameters(missing)
        self.catalogue = dict(catalogue)
        self.windows = [float(w) for w in catalogue[WINDOWS_KEY]]
        if not self.windows:
            raise MissingTrendParameters([WINDOWS_KEY])
        self.max_window_s = max(self.windows)
        self.reversal_n = int(catalogue[REVERSALS_KEY])
        # Trend-eligible signals are the deadbanded numeric ones. Edges, sets and
        # counts have no slope.
        self.specs = [s for s in registry
                      if s.kind == LEVEL and not s.per_unit and s.band_key]
        self.history: dict[str, _History] = {s.signal: _History() for s in self.specs}
        self.last_t: float | None = None

    # -- ingest -----------------------------------------------------------
    def update(self, payload: dict[str, Any]) -> None:
        t_res = resolve_number(payload, "sim_time_seconds")
        if not t_res.ok:
            return
        t = t_res.value
        self.last_t = t
        for spec in self.specs:
            r = resolve_number(payload, *spec.aliases)
            if not r.ok:
                continue          # null or absent: no sample, never a substituted value
            h = self.history[spec.signal]
            h.samples.append((t, r.value))
            h.run_peak = r.value if h.run_peak is None else max(h.run_peak, r.value)
            h.run_trough = r.value if h.run_trough is None else min(h.run_trough, r.value)
            # The ring is bounded by simulated time, not by a sample count, so a
            # change of tick rate cannot silently change the window length.
            cutoff = t - self.max_window_s
            while h.samples and h.samples[0][0] < cutoff:
                h.samples.popleft()

    # -- read -------------------------------------------------------------
    def facts(self, run_id: str, seq: int) -> list[TrendFact]:
        out: list[TrendFact] = []
        for spec in self.specs:
            for window in self.windows:
                f = self._fact(run_id, seq, spec, window)
                if f is not None:
                    out.append(f)
        return out

    def _fact(self, run_id, seq, spec: SignalSpec, window_s: float) -> TrendFact | None:
        h = self.history[spec.signal]
        if self.last_t is None or not h.samples:
            return None
        cutoff = self.last_t - window_s
        pts = [(t, v) for t, v in h.samples if t >= cutoff]
        band = float(self.catalogue[spec.band_key]) if spec.band_key in self.catalogue \
            else None

        if len(pts) < 2:
            return TrendFact(
                run_id=run_id, seq=seq, t_sim_s=self.last_t, signal=spec.signal,
                domain=spec.domain, window_s=window_s, units=spec.units,
                n_samples=len(pts), span_s=0.0,
                first=pts[0][1] if pts else 0.0, last=pts[-1][1] if pts else 0.0,
                delta=0.0, slope_per_min=0.0, net_slope_per_min=0.0,
                direction=INSUFFICIENT, monotonic_fraction=None, n_moves=0,
                n_sign_reversals=0,
                step_count=0, mean_step=None,
                peak_in_window=pts[0][1] if pts else 0.0,
                trough_in_window=pts[0][1] if pts else 0.0,
                run_peak=h.run_peak, run_trough=h.run_trough,
                pct_from_run_peak=None, step_band=band, band_key=spec.band_key)

        vals = [v for _, v in pts]
        span = pts[-1][0] - pts[0][0]
        delta = vals[-1] - vals[0]
        deltas = [b - a for a, b in zip(vals, vals[1:])]
        nonzero = [d for d in deltas if d != 0.0]
        signs = [1 if d > 0 else -1 for d in nonzero]
        reversals = sum(1 for a, b in zip(signs, signs[1:]) if a != b)
        # None, not 0.0, when nothing moved. Zero already means "maximally
        # non-monotonic", so a still signal reported as 0.0 reads as erratic --
        # the opposite of the truth.
        monotonic = (max(sum(1 for s in signs if s > 0),
                         sum(1 for s in signs if s < 0)) / len(signs)) if signs else None

        slope_min = _least_squares_slope(pts) * 60.0
        net_slope_min = (delta / span * 60.0) if span > 0 else 0.0

        # A step is a movement the detector would itself have reported, so the
        # signal's own deadband is the step size. No separate parameter, and the
        # two stay consistent by construction.
        steps = [d for d in deltas if band is not None and abs(d) >= band]
        mean_step = (sum(steps) / len(steps)) if steps else None

        direction = self._direction(delta, band, reversals)

        pct = None
        if h.run_peak not in (None, 0.0):
            pct = (vals[-1] - h.run_peak) / abs(h.run_peak) * 100.0

        return TrendFact(
            run_id=run_id, seq=seq, t_sim_s=self.last_t, signal=spec.signal,
            domain=spec.domain, window_s=window_s, units=spec.units,
            n_samples=len(pts), span_s=span, first=vals[0], last=vals[-1],
            delta=delta, slope_per_min=slope_min, net_slope_per_min=net_slope_min,
            direction=direction, monotonic_fraction=monotonic,
            n_moves=len(nonzero), n_sign_reversals=reversals, step_count=len(steps), mean_step=mean_step,
            peak_in_window=max(vals), trough_in_window=min(vals),
            run_peak=h.run_peak, run_trough=h.run_trough, pct_from_run_peak=pct,
            step_band=band, band_key=spec.band_key)

    def _direction(self, delta: float, band: float | None, reversals: int) -> str:
        # Oscillating is tested first and regardless of net movement. A signal
        # that ends where it started after three excursions is not flat, and
        # calling it flat is how a narrator reassures an operator about an
        # unstable loop.
        if reversals >= self.reversal_n:
            return OSCILLATING
        if band is not None and abs(delta) < band:
            return FLAT
        if delta > 0:
            return RISING
        if delta < 0:
            return FALLING
        return FLAT


def notable(facts: Iterable[TrendFact]) -> list[TrendFact]:
    """Drop trends that say nothing: flat and insufficient.

    Mechanical, not salience. On a realistic run most signals are constant most
    of the time -- 41 of 57 facts on the SC-20 synthetic run were flat -- so a
    digest carrying every trend would be mostly padding. This removes the ones
    with no content; it does not rank what remains, which is the open question
    (NAR-3).
    """
    return [f for f in facts if f.direction not in (FLAT, INSUFFICIENT)]


def trend_parameters() -> list[str]:
    return sorted(TREND_PARAMETERS)
