"""Phase 3 H.8 SoC policy helpers for BESS sizing.

The policy is deliberately pure and output-oriented.  It describes how a
recommended usable-energy nameplate is split between routine dispatch and an
emergency floor; it does not mutate a live BESS or site configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import SocCyclingPolicy


# PROPOSED_HERE: unvalidated default normal-dispatch depth, mirroring SJ-1's
# configured bess_normal_dispatch_depth_fraction.
DEFAULT_NORMAL_DISPATCH_DEPTH_PCT = 0.03

# PROPOSED_HERE: unvalidated SJ-1-derived emergency floor.  SJ-1 starts at
# 0.95 SoC and holds back 0.03 for normal dispatch, leaving 0.92.
DEFAULT_EMERGENCY_RESERVE_FLOOR_PCT = 0.92


@dataclass(frozen=True)
class EffectiveSocCyclingPolicy:
    """Resolved fractional SoC bands used by recommendation sizing."""

    normal_dispatch_depth_pct: float
    emergency_reserve_floor_pct: float
    normal_defaulted: bool
    emergency_defaulted: bool


@dataclass(frozen=True)
class SocEnergySplit:
    """Energy split for one proposed usable-energy rating."""

    usable_mwh: float
    normal_dispatch_band_mwh: float
    emergency_reserve_mwh: float


def resolve_soc_cycling_policy(
    policy: SocCyclingPolicy,
) -> EffectiveSocCyclingPolicy:
    """Resolve Phase 1 zero placeholders to the documented SJ-1 defaults.

    The Phase 1 policy fields use fractional values in [0, 1], despite their
    ``_pct`` suffix.  A zero value is the Phase 1 unset placeholder; Phase 3
    resolves it explicitly rather than allowing a divide-by-zero sizing result.
    """

    normal_defaulted = policy.normal_dispatch_depth_pct <= 0.0
    emergency_defaulted = policy.emergency_reserve_floor_pct <= 0.0
    normal_depth = (
        DEFAULT_NORMAL_DISPATCH_DEPTH_PCT
        if normal_defaulted
        else policy.normal_dispatch_depth_pct
    )
    emergency_floor = (
        DEFAULT_EMERGENCY_RESERVE_FLOOR_PCT
        if emergency_defaulted
        else policy.emergency_reserve_floor_pct
    )
    if normal_depth > 1.0:
        raise ValueError("normal_dispatch_depth_pct must be at most 1.0")
    if emergency_floor > 1.0:
        raise ValueError("emergency_reserve_floor_pct must be at most 1.0")
    if normal_depth + emergency_floor > 1.0:
        raise ValueError(
            "normal dispatch depth plus emergency reserve floor must be at most 1.0"
        )
    return EffectiveSocCyclingPolicy(
        normal_dispatch_depth_pct=normal_depth,
        emergency_reserve_floor_pct=emergency_floor,
        normal_defaulted=normal_defaulted,
        emergency_defaulted=emergency_defaulted,
    )


def split_soc_energy(
    usable_mwh: float,
    policy: SocCyclingPolicy,
) -> SocEnergySplit:
    """Split usable energy into routine and emergency bands.

    The emergency band is held outside the normal-dispatch band.  This helper
    performs no dispatch and cannot release the emergency band; the later live
    control-plane phase owns that behavior.
    """

    if usable_mwh < 0.0:
        raise ValueError("usable_mwh must not be negative")
    effective = resolve_soc_cycling_policy(policy)
    return SocEnergySplit(
        usable_mwh=usable_mwh,
        normal_dispatch_band_mwh=(
            usable_mwh * effective.normal_dispatch_depth_pct
        ),
        emergency_reserve_mwh=(
            usable_mwh * effective.emergency_reserve_floor_pct
        ),
    )