"""Phase 2 -- sub-tick integration of the swing equation.

The residual from phase 0 must move frequency. It cannot be integrated at the
tick rate: a 5.0 s tick against a collapse that completes in roughly 0.2 s would
show frequency jumping between samples with the nadir invisible, which is worse
than the present frozen behaviour because it looks like it is working.

So the tick remains the *reporting* cadence and the integration runs beneath it.
The nadir is captured from the sub-step trace, not from the tick boundary.

    2H·S/f0 · df/dt = P_accelerating
    df/dt = (P_imbalance - K_droop·Δf - K_damping·Δf) · f0 / (2·H·S)

Integrated with the explicit midpoint method (RK2): forward Euler needs a
substep an order of magnitude smaller for the same error, and the stiffness here
is set by H and the droop gain, both of which vary by scenario.

Two known limits on the numbers this produces, both pre-existing:

  * H is annotated in the spec as "CHOSEN -- no measured basis". Magnitudes are
    directionally right and numerically unreliable.
  * S_base must be rated/pf. Assuming pf = 1.0 overstates df/dt by roughly 18 %
    at pf 0.85. This module requires pf explicitly for that reason.

Adequate for demonstrating that a nadir exists. Not adequate for quoting a
frequency figure.

Pure functions. No I/O, no clock, no RNG.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

OK = "ok"
NO_INERTIA = "no_inertia"


class UnstableSubstep(ValueError):
    """Raised when the substep is too large for the system stiffness.

    Explicit integration of dy/dt = -y/tau is stable only for h < 2*tau. Past
    that the solution diverges rather than blurring: a 5 s step on a stiff
    fleet takes frequency to millions of hertz within one tick. Producing a
    number nobody can distinguish from a physics result is worse than
    refusing, so this refuses.
    """


@dataclass(frozen=True)
class SwingParameters:
    inertia_h_s: float              # H, seconds on the machine base
    s_base_mva: float               # Σ rated/pf over on-bus machines
    frequency_nominal_hz: float
    droop_gain_mw_per_hz: float     # Σ rated/(pf·R·f0); see droop.py
    load_damping_mw_per_hz: float = 0.0   # D·P_load/f0


@dataclass(frozen=True)
class ThresholdCrossing:
    label: str
    hz: float
    t_s: float
    direction: str                  # "below" | "above"


@dataclass(frozen=True)
class SwingResult:
    status: str
    f_start_hz: float
    f_end_hz: float
    nadir_hz: float
    nadir_t_s: float
    zenith_hz: float
    zenith_t_s: float
    df_dt_initial_hz_per_s: float
    substep_s: float
    n_substeps: int
    crossings: tuple[ThresholdCrossing, ...] = ()
    reason: str | None = None
    trace: tuple[tuple[float, float], ...] = field(default=())

    @property
    def nadir_below_reported(self) -> float:
        """How much of the excursion tick-boundary sampling would have missed."""
        return self.f_end_hz - self.nadir_hz


def _dfdt(delta_f: float, p_imbalance_mw: float, p: SwingParameters) -> float:
    p_acc = (p_imbalance_mw
             - p.droop_gain_mw_per_hz * delta_f
             - p.load_damping_mw_per_hz * delta_f)
    return p_acc * p.frequency_nominal_hz / (2.0 * p.inertia_h_s * p.s_base_mva)


def settling_frequency_hz(p_imbalance_mw: float, p: SwingParameters) -> float | None:
    """Frequency the governor characteristic settles to, ignoring dynamics."""
    k = p.droop_gain_mw_per_hz + p.load_damping_mw_per_hz
    if k <= 0.0:
        return None                 # nothing opposes the imbalance; no settle
    return p.frequency_nominal_hz + p_imbalance_mw / k


def time_constant_s(p: SwingParameters) -> float | None:
    """τ = 2HS / (f0·K). Sets how small a substep has to be."""
    k = p.droop_gain_mw_per_hz + p.load_damping_mw_per_hz
    if k <= 0.0 or p.s_base_mva <= 0.0:
        return None
    return (2.0 * p.inertia_h_s * p.s_base_mva) / (p.frequency_nominal_hz * k)


def recommended_substep_s(p: SwingParameters, tick_s: float,
                          *, steps_per_tau: float = 20.0) -> float:
    """A substep small enough for the stiffness, and never longer than the tick.

    `steps_per_tau` is a numerical-accuracy choice, not a physical parameter.
    Where no time constant exists (no droop, no damping) the response is a ramp
    with no curvature, so the tick itself is adequate and the caller's floor
    applies.
    """
    tau = time_constant_s(p)
    if tau is None or tau <= 0.0:
        return tick_s
    return min(tick_s, tau / steps_per_tau)


def integrate_tick(
    *,
    f_start_hz: float,
    p_imbalance_mw: float,
    params: SwingParameters,
    tick_s: float,
    substep_s: float,
    thresholds: Sequence[tuple[str, float, str]] = (),
    keep_trace: bool = False,
    enforce_stability: bool = True,
    stability_tau_multiple: float = 1.0,
) -> SwingResult:
    """Advance frequency over one tick, capturing the sub-tick extremes.

    `p_imbalance_mw` is the phase-0 balance defect at nominal frequency: positive
    is surplus generation and drives frequency up. It is held constant across the
    tick; the droop and damping terms respond within it.

    `thresholds` are (label, hz, direction) with direction "below" or "above".
    This module supplies none -- protective thresholds are site configuration and
    live outside GridSignal's scope per §28.4. They are evaluated here only so
    the simulator can model the consequence.
    """
    if params.s_base_mva <= 0.0 or params.inertia_h_s <= 0.0:
        # No rotating mass on the bus. Frequency is not defined by a swing
        # equation here -- it is set by a grid-forming inverter or by nothing at
        # all. Returning the previous value would be the frozen-frequency bug;
        # the caller has to handle this branch explicitly.
        return SwingResult(
            status=NO_INERTIA, f_start_hz=f_start_hz, f_end_hz=f_start_hz,
            nadir_hz=f_start_hz, nadir_t_s=0.0, zenith_hz=f_start_hz,
            zenith_t_s=0.0, df_dt_initial_hz_per_s=0.0, substep_s=substep_s,
            n_substeps=0,
            reason=("no inertia on bus (s_base_mva=%.4g, inertia_h_s=%.4g); "
                    "frequency is not determined by the swing equation"
                    % (params.s_base_mva, params.inertia_h_s)))

    if substep_s <= 0.0 or not math.isfinite(substep_s):
        raise ValueError(f"substep_s must be positive and finite, got {substep_s}")
    h = min(substep_s, tick_s)
    n = max(1, int(math.ceil(tick_s / h)))
    h = tick_s / n                  # distribute evenly rather than leaving a stub

    tau = time_constant_s(params)
    if enforce_stability and tau is not None and h > stability_tau_multiple * tau:
        raise UnstableSubstep(
            f"substep {h:g} s exceeds {stability_tau_multiple:g}x the system time "
            f"constant {tau:g} s; explicit integration would diverge. Use "
            f"recommended_substep_s() -- {recommended_substep_s(params, tick_s):g} s "
            f"here.")

    f0 = params.frequency_nominal_hz
    df = f_start_hz - f0
    df_dt0 = _dfdt(df, p_imbalance_mw, params)

    nadir, nadir_t = f_start_hz, 0.0
    zenith, zenith_t = f_start_hz, 0.0
    crossings: list[ThresholdCrossing] = []
    armed = {label: True for label, _, _ in thresholds}
    trace: list[tuple[float, float]] = [(0.0, f_start_hz)] if keep_trace else []

    for i in range(n):
        k1 = _dfdt(df, p_imbalance_mw, params)
        k2 = _dfdt(df + 0.5 * h * k1, p_imbalance_mw, params)
        df += h * k2
        t = (i + 1) * h
        f = f0 + df

        if f < nadir:
            nadir, nadir_t = f, t
        if f > zenith:
            zenith, zenith_t = f, t
        if keep_trace:
            trace.append((t, f))

        for label, hz, direction in thresholds:
            if not armed[label]:
                continue
            hit = f <= hz if direction == "below" else f >= hz
            if hit:
                crossings.append(ThresholdCrossing(label, hz, t, direction))
                armed[label] = False

    return SwingResult(
        status=OK, f_start_hz=f_start_hz, f_end_hz=f0 + df,
        nadir_hz=nadir, nadir_t_s=nadir_t, zenith_hz=zenith, zenith_t_s=zenith_t,
        df_dt_initial_hz_per_s=df_dt0, substep_s=h, n_substeps=n,
        crossings=tuple(crossings), trace=tuple(trace),
    )


def initial_rocof_hz_per_s(p_imbalance_mw: float, params: SwingParameters) -> float | None:
    """df/dt at the instant of a step, before any governor response.

    This is the quantity the product's claim rests on: unstaged, a step load
    produces a rate of change of frequency that risks a protection trip. Exposed
    separately because it is the headline number, and because it is the one a
    demo should show rather than an absolute frequency.
    """
    if params.s_base_mva <= 0.0 or params.inertia_h_s <= 0.0:
        return None
    return _dfdt(0.0, p_imbalance_mw, params)
