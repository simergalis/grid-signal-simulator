"""Phase 1 -- bound the governor droop correction.

The current expression is

    _p_dispatch_droop_mw = max(0.0, min(p_dispatch_required_mw
                                        + _droop_correction_mw,
                                        _sync_ceiling_mw))

with

    _droop_correction_mw = sum(-Δf / (R_i * f0) * (rated_i / pf_i)
                               for on-bus units)

The droop formula itself is standard and correct. Two things are missing around
it, and together they produced the surplus measured on `demo-20mw`: a reported
reserve floor of 42.0 MW with a largest on-bus unit of 7.0 MW implies a demand
basis of exactly 35.0 MW -- five units at nameplate, the full fleet -- against an
actual demand of 6.861 MW. Generation followed to 21.2 MW into a 6.86 MW load.

What is missing:

1. **No bound on Δf.** The correction is linear in frequency error with nothing
   limiting the error. Beyond a few hundred millihertz a real plant is in
   protection, not in governor action, so an unbounded Δf drives a correction
   that no machine would ever be asked for.

2. **No per-unit headroom limit before summing.** A unit already at nameplate
   cannot contribute more; a unit at minimum stable load cannot contribute less.
   Clamping only the fleet total at `_sync_ceiling_mw` means the ceiling itself
   becomes the operating point, which is exactly what was observed.

The fleet clamp is kept as a final guard. It stops being the binding constraint.

Pure functions. No I/O, no clock, no RNG.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DroopUnit:
    """One on-bus machine's droop parameters and current operating point."""
    unit_id: str
    rated_mw: float
    output_mw: float
    droop_r: float                  # per-unit droop, e.g. 0.04 for 4 %
    power_factor: float = 1.0
    msl_mw: float = 0.0             # minimum stable load


@dataclass(frozen=True)
class UnitDroopResponse:
    unit_id: str
    unbounded_mw: float             # what the raw formula asks for
    bounded_mw: float               # what the machine can actually deliver
    headroom_limited: bool


@dataclass(frozen=True)
class DroopResult:
    correction_mw: float
    unbounded_correction_mw: float
    frequency_error_hz: float       # after clamping
    raw_frequency_error_hz: float   # as measured
    frequency_error_clamped: bool
    in_deadband: bool
    per_unit: tuple[UnitDroopResponse, ...]
    fleet_ceiling_binding: bool


def droop_correction(
    units: Sequence[DroopUnit],
    *,
    frequency_hz: float,
    frequency_nominal_hz: float,
    governor_deadband_hz: float,
    max_frequency_error_hz: float,
) -> DroopResult:
    """Fleet droop correction, bounded per unit by headroom and by Δf.

    `max_frequency_error_hz` is the excursion beyond which governor action is no
    longer the operative mechanism. It is a catalogue parameter; this module
    supplies no value for it. A sensible basis is the tightest protective
    threshold the site declares, since past that point the machine trips rather
    than governs -- but that is a configuration decision, not one to make here.
    """
    raw_err = frequency_hz - frequency_nominal_hz

    if abs(raw_err) <= governor_deadband_hz:
        return DroopResult(0.0, 0.0, 0.0, raw_err, False, True, (), False)

    clamped = max(-max_frequency_error_hz, min(max_frequency_error_hz, raw_err))
    was_clamped = clamped != raw_err

    responses: list[UnitDroopResponse] = []
    for u in units:
        if u.droop_r <= 0.0 or u.power_factor <= 0.0:
            continue
        # Standard governor characteristic. S_base = rated / pf; assuming pf = 1.0
        # overstates the response, and therefore df/dt, by roughly 18 % at
        # pf 0.85.
        s_base = u.rated_mw / u.power_factor
        unbounded = (-clamped / (u.droop_r * frequency_nominal_hz)) * s_base

        # A machine cannot deliver past nameplate nor unload below MSL, so the
        # limit is applied per unit before summing rather than to the fleet
        # total afterwards.
        up = max(0.0, u.rated_mw - u.output_mw)
        down = min(0.0, u.msl_mw - u.output_mw)
        bounded = min(unbounded, up) if unbounded >= 0.0 else max(unbounded, down)

        responses.append(UnitDroopResponse(
            unit_id=u.unit_id, unbounded_mw=unbounded, bounded_mw=bounded,
            headroom_limited=bounded != unbounded))

    return DroopResult(
        correction_mw=sum(r.bounded_mw for r in responses),
        unbounded_correction_mw=sum(r.unbounded_mw for r in responses),
        frequency_error_hz=clamped,
        raw_frequency_error_hz=raw_err,
        frequency_error_clamped=was_clamped,
        in_deadband=False,
        per_unit=tuple(responses),
        fleet_ceiling_binding=False,
    )


def dispatch_requirement_mw(
    p_dispatch_required_mw: float,
    droop: DroopResult,
    sync_ceiling_mw: float,
) -> tuple[float, DroopResult]:
    """Apply the bounded correction and the fleet guard.

    Returns the dispatch requirement and the droop result with
    `fleet_ceiling_binding` set, so a caller can tell whether the guard was
    reached. Under the bounded correction it should not be, except during a
    genuine full-fleet demand; if it binds routinely, the bound is wrong or the
    frequency model is unstable, and that is worth knowing rather than hiding.
    """
    raw = p_dispatch_required_mw + droop.correction_mw
    clamped = max(0.0, min(raw, sync_ceiling_mw))
    binding = raw > sync_ceiling_mw
    return clamped, DroopResult(
        correction_mw=droop.correction_mw,
        unbounded_correction_mw=droop.unbounded_correction_mw,
        frequency_error_hz=droop.frequency_error_hz,
        raw_frequency_error_hz=droop.raw_frequency_error_hz,
        frequency_error_clamped=droop.frequency_error_clamped,
        in_deadband=droop.in_deadband,
        per_unit=droop.per_unit,
        fleet_ceiling_binding=binding,
    )


def fleet_droop_gain_mw_per_hz(units: Sequence[DroopUnit],
                               frequency_nominal_hz: float) -> float:
    """Σ rated/(pf·R·f0) -- the fleet's stiffness, used by the swing model."""
    return sum((u.rated_mw / u.power_factor) / (u.droop_r * frequency_nominal_hz)
               for u in units if u.droop_r > 0.0 and u.power_factor > 0.0)
