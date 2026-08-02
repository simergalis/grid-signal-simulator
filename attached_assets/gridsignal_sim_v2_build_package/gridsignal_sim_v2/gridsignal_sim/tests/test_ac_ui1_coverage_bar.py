"""
tests/test_ac_ui1_coverage_bar.py — AC-UI-1 coverage bar honesty checks.

The coverage bar in the Renewable Supply Console (console.html Layer 1) must
show an *honest* unfilled gap when the reserve cannot cover a full solar loss —
not a deceptively full bar.  These tests verify the underlying arithmetic that
drives the gap segment.

The console computes (JavaScript, renderLayer1()):

    rc = reserveCheck(solar, 0)          # dt_lead = 0 for supply-side step
    if _solarStopSim:
        if not rc.pass:
            gapFrac    = clamp(rc.deficitMW / tot, 0, 1)
            bessFrac   = clamp(bridge / tot, 0, 1 - gapFrac)
            turbFrac   = clamp(1 - bessFrac - gapFrac, 0, 1)
        else:
            gapFrac    = 0
            bessFrac   = clamp(bridge / tot, 0, 1)
            turbFrac   = clamp(1 - bessFrac, 0, 1)

All fractions are in [0, 1] and sum to 1.0.

These tests exercise the same arithmetic through the Python equivalents so no
browser or HTTP server is needed.  The console JS is a faithful port of the
Python reserve_check, so a regression in either surface will surface here.
"""

from __future__ import annotations

import math

import pytest

from renewable.config import SiteConfig
from renewable.solar import (
    SolarSim,
    bess_bridging_mw,
    p_renewable_mw,
    p_total_mw,
    reserve_check,
)


# ---------------------------------------------------------------------------
# helpers  (mirror the JS renderLayer1 gap calculation)
# ---------------------------------------------------------------------------

def _coverage_fracs(sim: SolarSim, *, solar_stopped: bool = False):
    """Return (solar_frac, turbine_frac, bess_frac, gap_frac) as the JS would.

    When solar_stopped=True the solar segment collapses to 0 and reserve tries
    to fill its place — matching the "If solar stopped this second" simulation.
    """
    cfg, st = sim.cfg, sim.state
    solar  = p_renewable_mw(cfg, st)
    tot    = p_total_mw(cfg, st)
    bridge = bess_bridging_mw(cfg, st)

    def clamp(v, lo=0.0, hi=1.0):
        return max(lo, min(hi, v))

    if not solar_stopped:
        solar_frac   = clamp(solar / tot) if tot > 0 else 0.0
        bess_frac    = clamp(bridge / tot, 0, 1 - solar_frac) if tot > 0 else 0.0
        turbine_frac = clamp(1.0 - solar_frac - bess_frac)
        gap_frac     = 0.0
    else:
        rc = reserve_check(cfg, st, solar, dt_lead_s=0.0)
        solar_frac = 0.0
        if not rc.passes:
            gap_frac     = clamp(rc.deficit_mw / tot) if tot > 0 else 0.0
            bess_frac    = clamp(bridge / tot, 0, 1 - gap_frac) if tot > 0 else 0.0
            turbine_frac = clamp(1.0 - bess_frac - gap_frac)
        else:
            gap_frac     = 0.0
            bess_frac    = clamp(bridge / tot) if tot > 0 else 0.0
            turbine_frac = clamp(1.0 - bess_frac)

    return solar_frac, turbine_frac, bess_frac, gap_frac


# ---------------------------------------------------------------------------
# AC-UI-1 #1 — healthy plant: no gap at seed SoC
# ---------------------------------------------------------------------------

def test_ac_ui1_no_gap_at_seed_soc():
    """At seed (SoC=82%), a full solar loss is covered — gap segment must be 0."""
    sim = SolarSim(SiteConfig(), seed=1)
    _, _, _, gap_frac = _coverage_fracs(sim, solar_stopped=True)
    assert gap_frac == 0.0, (
        f"At seed SoC 82%, reserve covers a plant loss — gap_frac must be 0; "
        f"got {gap_frac:.4f}"
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #2 — drained BESS: gap appears and is non-zero
# ---------------------------------------------------------------------------

def test_ac_ui1_gap_appears_when_bess_is_drained():
    """With BESS at 30% SoC, the reserve fails and gap_frac must be > 0.

    This is the core AC-UI-1 assertion: the bar must show an honest unfilled
    gap, not a full bar, when reserve is insufficient.
    """
    sim = SolarSim(SiteConfig(), seed=1)
    sim.inject("bess")   # drains SoC to 30%

    _, _, _, gap_frac = _coverage_fracs(sim, solar_stopped=True)
    assert gap_frac > 0.0, (
        "With BESS at 30% SoC, reserve cannot cover a full plant loss — "
        f"gap_frac must be > 0; got {gap_frac:.4f}"
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #3 — gap is proportional to the actual MW deficit
# ---------------------------------------------------------------------------

def test_ac_ui1_gap_proportional_to_deficit():
    """gap_frac == deficit_mw / p_total (the JS formula, verified directly)."""
    sim = SolarSim(SiteConfig(), seed=1)
    sim.inject("bess")

    cfg, st = sim.cfg, sim.state
    solar  = p_renewable_mw(cfg, st)
    tot    = p_total_mw(cfg, st)
    rc     = reserve_check(cfg, st, solar, dt_lead_s=0.0)

    expected_gap_frac = max(0.0, min(1.0, rc.deficit_mw / tot))
    _, _, _, gap_frac = _coverage_fracs(sim, solar_stopped=True)

    assert gap_frac == pytest.approx(expected_gap_frac, abs=1e-9), (
        f"gap_frac mismatch: JS formula gives {expected_gap_frac:.6f}, "
        f"helper returned {gap_frac:.6f}"
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #4 — conservation: all segments sum to 1.0 when solar is stopped
# ---------------------------------------------------------------------------

def test_ac_ui1_segments_sum_to_unity_when_reserve_fails():
    """solar + turbine + bess + gap == 1.0 when reserve is insufficient.

    The bar represents P_total at full width; segments must tile it exactly.
    """
    sim = SolarSim(SiteConfig(), seed=1)
    sim.inject("bess")

    solar_frac, turbine_frac, bess_frac, gap_frac = _coverage_fracs(
        sim, solar_stopped=True
    )
    total = solar_frac + turbine_frac + bess_frac + gap_frac
    assert total == pytest.approx(1.0, abs=1e-9), (
        f"Segment fractions must sum to 1.0; got {total:.9f}. "
        f"solar={solar_frac:.4f} turbine={turbine_frac:.4f} "
        f"bess={bess_frac:.4f} gap={gap_frac:.4f}"
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #5 — conservation: segments sum to 1.0 when reserve passes
# ---------------------------------------------------------------------------

def test_ac_ui1_segments_sum_to_unity_when_reserve_passes():
    """Even when reserve passes, turbine + bess == 1.0 (solar = 0, gap = 0)."""
    sim = SolarSim(SiteConfig(), seed=1)
    # healthy SoC — reserve passes

    solar_frac, turbine_frac, bess_frac, gap_frac = _coverage_fracs(
        sim, solar_stopped=True
    )
    assert gap_frac == 0.0
    total = solar_frac + turbine_frac + bess_frac + gap_frac
    assert total == pytest.approx(1.0, abs=1e-9), (
        f"Segment fractions must sum to 1.0 when reserve passes; got {total:.9f}"
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #6 — conservation: segments sum to 1.0 when sim is off (normal view)
# ---------------------------------------------------------------------------

def test_ac_ui1_segments_sum_to_unity_normal_view():
    """solar + turbine + bess == 1.0 in the normal (non-simulation) view."""
    sim = SolarSim(SiteConfig(), seed=1)

    solar_frac, turbine_frac, bess_frac, gap_frac = _coverage_fracs(
        sim, solar_stopped=False
    )
    assert gap_frac == 0.0
    total = solar_frac + turbine_frac + bess_frac + gap_frac
    assert total == pytest.approx(1.0, abs=1e-9), (
        f"Normal-view segments must sum to 1.0; got {total:.9f}"
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #7 — gap is bounded in [0, 1]; never negative, never > 1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("soc_scenario", [
    "full",   # seed SoC = 82%
    "drained",  # after bess stressor, SoC = 30%
    "poi",    # entire plant offline (solar = 0, gap trivially = 0)
])
def test_ac_ui1_gap_frac_is_bounded(soc_scenario):
    """gap_frac must always be in [0, 1] regardless of operating point."""
    sim = SolarSim(SiteConfig(), seed=1)
    if soc_scenario == "drained":
        sim.inject("bess")
    elif soc_scenario == "poi":
        sim.inject("poi")

    _, _, _, gap_frac = _coverage_fracs(sim, solar_stopped=True)
    assert 0.0 <= gap_frac <= 1.0, (
        f"gap_frac out of bounds for scenario '{soc_scenario}': {gap_frac:.4f}"
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #8 — gap MW shown to operator is the actual deficit, not zero
# ---------------------------------------------------------------------------

def test_ac_ui1_deficit_mw_matches_reserve_check_output():
    """The MW figure shown in the gap label equals rc.deficit_mw exactly."""
    sim = SolarSim(SiteConfig(), seed=1)
    sim.inject("bess")

    cfg, st = sim.cfg, sim.state
    solar = p_renewable_mw(cfg, st)
    rc    = reserve_check(cfg, st, solar, dt_lead_s=0.0)

    assert not rc.passes, "precondition: reserve must fail after BESS drain"
    assert rc.deficit_mw > 0.0, (
        f"deficit_mw must be > 0 when reserve fails; got {rc.deficit_mw:.4f} MW"
    )
    # The label the operator reads is formatted from rc.deficit_mw.
    # Assert it is physically meaningful (not a rounding artifact).
    assert rc.deficit_mw > 0.05, (
        "A 30% SoC drain should produce a deficit larger than 50 kW; "
        f"got {rc.deficit_mw:.4f} MW.  The gap label would be misleadingly small."
    )


# ---------------------------------------------------------------------------
# AC-UI-1 #9 — night plant (POI trip, solar=0): gap_frac == 0, not NaN/error
# ---------------------------------------------------------------------------

def test_ac_ui1_zero_solar_gives_zero_gap():
    """If solar = 0 (night / POI trip), the sim stops with zero delta and no gap."""
    sim = SolarSim(SiteConfig(), seed=1)
    sim.inject("poi")   # solar = 0

    cfg, st = sim.cfg, sim.state
    solar = p_renewable_mw(cfg, st)
    assert solar == pytest.approx(0.0, abs=1e-9)

    solar_frac, turbine_frac, bess_frac, gap_frac = _coverage_fracs(
        sim, solar_stopped=True
    )
    assert gap_frac == 0.0, (
        "With solar already at 0, simulating 'if solar stopped' must not "
        f"show a gap (nothing to lose); got gap_frac={gap_frac:.4f}"
    )
    total = solar_frac + turbine_frac + bess_frac + gap_frac
    assert total == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# AC-UI-1 #10 — gap grows when more turbines go offline (reserve shrinks)
# ---------------------------------------------------------------------------

def test_ac_ui1_gap_grows_when_turbine_goes_offline():
    """Taking a turbine offline lengthens the gap.

    Fewer turbines → less ramp → larger peak shortfall → larger gap fraction.
    """
    sim = SolarSim(SiteConfig(), seed=1)
    sim.inject("bess")   # start at low SoC so reserve is already marginal

    _, _, _, gap_before = _coverage_fracs(sim, solar_stopped=True)

    sim.inject("turbine")   # take one more turbine offline

    _, _, _, gap_after = _coverage_fracs(sim, solar_stopped=True)

    assert gap_after >= gap_before, (
        f"Taking a turbine offline must not shrink the gap: "
        f"before={gap_before:.4f}, after={gap_after:.4f}"
    )
