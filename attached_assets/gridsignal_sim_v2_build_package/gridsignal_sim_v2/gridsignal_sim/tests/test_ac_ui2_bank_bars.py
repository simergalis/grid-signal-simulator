"""
tests/test_ac_ui2_bank_bars.py — AC-UI-2 bank list bar fill checks.

The bank list in the Renewable Supply Console (console.html Layer 2) shows one
proportional bar per bank.  The bar measures:

    fill_pct = counted_output_mw / bank_expected_mw × 100 %

where bank_expected_mw = rated × (POA_measured / 1000) × temp_derate
(§4.1 — soiling, string faults, and soil_bias are excluded from the expectation
so they surface as visible shortfall rather than being absorbed into the target).

AC-UI-2 states two invariants:

  1. At a healthy plant, no bar is shorter than 92% fill regardless of
     irradiance level.  Cloud cover changes both output and expectation by the
     same factor, so the ratio stays near 97% (the soiling residual).

  2. Reducing POA by 60% (cloud_factor=0.4) leaves all bars full and reduces
     only the plant-total headline — operators see the sky dimmed, not a fault
     array.

Violation of AC-UI-2 would make heavy cloud cover look like a bank-level fault
and destroy operator trust in the bar.
"""

from __future__ import annotations

import pytest

from renewable.config import SiteConfig
from renewable.solar import (
    SolarSim,
    bank_expected_mw,
    bank_output_mw,
    counted_output_mw,
    mistral_bank_mw,
    p_renewable_mw,
    _update_bank_classifier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bar_fills(sim: SolarSim) -> list[float]:
    """Return fill_pct for every bank, mirroring the JS renderBankList() formula.

    fill_pct = (cs > 0) ? clamp(o / cs * 100, 0, 100) : (o > 0 ? 100 : 0)

    where o = counted_output_mw  and  cs = bank_expected_mw.
    """
    cfg, st = sim.cfg, sim.state
    fills = []
    for b in st.blocks:
        o  = counted_output_mw(cfg, st, b)
        cs = bank_expected_mw(cfg, st, b)
        if cs > 0:
            fills.append(min(max(o / cs * 100.0, 0.0), 100.0))
        else:
            fills.append(100.0 if o > 0 else 0.0)
    return fills


# ---------------------------------------------------------------------------
# AC-UI-2 #1 — seed: all bars ≥ 92% at nominal irradiance
# ---------------------------------------------------------------------------

def test_ac_ui2_all_bars_above_92pct_at_seed():
    """At the seed operating point every bar must be ≥ 92% full.

    The seed plant is healthy (all banks nominal).  Expected accounts for
    current POA so the fill equals (1 − soiling) × soil_bias ≈ 97%.
    """
    sim = SolarSim(SiteConfig(), seed=1)
    fills = _bar_fills(sim)

    for i, pct in enumerate(fills):
        assert pct >= 92.0, (
            f"Bank {i+1} bar fill {pct:.1f}% < 92% at seed — "
            "healthy bank should not look like a fault at nominal irradiance"
        )


# ---------------------------------------------------------------------------
# AC-UI-2 #2 — 60% POA reduction: all bars remain ≥ 92%
# ---------------------------------------------------------------------------

def test_ac_ui2_60pct_poa_reduction_leaves_bars_full():
    """Reducing cloud_factor to 0.4 (60% reduction) must not shrink any bar.

    Both output and expected use poa × cloud_factor, so the ratio is invariant
    to irradiance.  No bar should drop below 92%.
    """
    sim = SolarSim(SiteConfig(), seed=1)
    sim.state.cloud_factor = 0.4          # 60% POA reduction

    # Run classifier once so any state-dependent paths are fresh.
    for b in sim.state.blocks:
        _update_bank_classifier(sim.cfg, sim.state, b)

    fills = _bar_fills(sim)

    for i, pct in enumerate(fills):
        assert pct >= 92.0, (
            f"Bank {i+1} bar fill {pct:.1f}% < 92% under 60% cloud cover — "
            "irradiance reduction must not make healthy banks look faulted"
        )


# ---------------------------------------------------------------------------
# AC-UI-2 #3 — 60% POA reduction reduces plant total, not per-bank ratio
# ---------------------------------------------------------------------------

def test_ac_ui2_60pct_poa_reduces_plant_total_not_bar_ratio():
    """Under 60% cloud cover:
    - p_renewable_mw drops by approximately 60%
    - median per-bank bar fill stays within 1 pp of the seed fill

    This confirms the bar isolates a bank's own condition from site-level
    irradiance.
    """
    sim_seed  = SolarSim(SiteConfig(), seed=1)
    sim_cloud = SolarSim(SiteConfig(), seed=1)
    sim_cloud.state.cloud_factor = 0.4

    solar_seed  = p_renewable_mw(sim_seed.cfg,  sim_seed.state)
    solar_cloud = p_renewable_mw(sim_cloud.cfg, sim_cloud.state)

    # Plant total must drop by ~60%
    ratio = solar_cloud / solar_seed
    assert ratio == pytest.approx(0.40, abs=0.03), (
        f"Expected plant output to drop ~60% under cloud_factor=0.4; "
        f"got {ratio*100:.1f}% of seed output"
    )

    # Per-bank fills must stay close to seed fills (within 2 pp per bank)
    fills_seed  = _bar_fills(sim_seed)
    fills_cloud = _bar_fills(sim_cloud)
    for i, (fs, fc) in enumerate(zip(fills_seed, fills_cloud)):
        assert abs(fc - fs) <= 2.0, (
            f"Bank {i+1}: fill changed from {fs:.1f}% to {fc:.1f}% under cloud "
            "cover — bar should not react to irradiance, only to bank condition"
        )


# ---------------------------------------------------------------------------
# AC-UI-2 #4 — extreme low irradiance (10% of clear-sky): bars still ≥ 92%
# ---------------------------------------------------------------------------

def test_ac_ui2_extreme_low_irradiance_leaves_bars_full():
    """Even at 10% irradiance (cloud_factor=0.1) a healthy plant's bars hold."""
    sim = SolarSim(SiteConfig(), seed=1)
    sim.state.cloud_factor = 0.1

    fills = _bar_fills(sim)
    for i, pct in enumerate(fills):
        assert pct >= 92.0, (
            f"Bank {i+1} fill {pct:.1f}% < 92% at cloud_factor=0.1 — "
            "bar must only respond to bank faults, not ambient irradiance"
        )


# ---------------------------------------------------------------------------
# AC-UI-2 #5 — degraded bank (strings_out) DOES show shortfall in bar
# ---------------------------------------------------------------------------

def test_ac_ui2_degraded_bank_shows_shortfall():
    """A bank with strings open must produce a fill noticeably below 100%.

    This confirms the bar is sensitive to actual bank faults while being
    insensitive to irradiance changes (AC-UI-2 constraint #1 above).
    """
    sim = SolarSim(SiteConfig(), seed=1)
    cfg, st = sim.cfg, sim.state

    b = st.blocks[0]
    # Open half the strings — output halved relative to expectation.
    b.strings_out = cfg.strings_per_bank // 2
    # Force the classifier to re-evaluate (3 ticks to reach degraded).
    for _ in range(3):
        _update_bank_classifier(cfg, st, b)
    assert b.state == "degraded", f"expected degraded, got {b.state!r}"

    o  = counted_output_mw(cfg, st, b)
    cs = bank_expected_mw(cfg, st, b)
    fill = o / cs * 100.0 if cs > 0 else 0.0

    assert fill < 70.0, (
        f"Bank with half its strings open should fill < 70%; got {fill:.1f}%. "
        "AC-UI-2 only protects healthy banks from irradiance noise."
    )


# ---------------------------------------------------------------------------
# AC-UI-2 #6 — out bank shows 0% fill (not confused with irradiance noise)
# ---------------------------------------------------------------------------

def test_ac_ui2_out_bank_fills_zero():
    """A tripped bank must render at 0% fill regardless of irradiance."""
    sim = SolarSim(SiteConfig(), seed=1)
    cfg, st = sim.cfg, sim.state

    b = st.blocks[3]
    b.state = "out"
    b.fault = "arc_fault"

    # Verify counted output is zero (the bar formula uses this)
    assert counted_output_mw(cfg, st, b) == pytest.approx(0.0)

    fills = _bar_fills(sim)
    assert fills[3] == pytest.approx(0.0), (
        f"Tripped bank bar fill must be 0%; got {fills[3]:.1f}%"
    )


# ---------------------------------------------------------------------------
# AC-UI-2 #7 — no_comms bank shows 0% fill
# ---------------------------------------------------------------------------

def test_ac_ui2_no_comms_bank_fills_zero():
    """A no_comms bank is counted as zero so its bar must be 0%."""
    sim = SolarSim(SiteConfig(), seed=1)
    cfg, st = sim.cfg, sim.state

    b = st.blocks[5]
    b.telemetry_age_s = 15.0
    _update_bank_classifier(cfg, st, b)
    assert b.state == "no_comms"

    fills = _bar_fills(sim)
    assert fills[5] == pytest.approx(0.0), (
        f"no_comms bank bar fill must be 0%; got {fills[5]:.1f}%"
    )


# ---------------------------------------------------------------------------
# AC-UI-2 #8 — irradiance variation does NOT flip any nominal bank to degraded
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cloud_factor", [1.0, 0.7, 0.4, 0.1])
def test_ac_ui2_cloud_does_not_flip_bank_state(cloud_factor):
    """Cloud cover alone must never push a healthy bank's classifier to degraded.

    The ratio output/expected is ~97% at all irradiance levels (soiling only),
    well above the 92% degraded threshold, so the classifier stays at nominal.
    """
    sim = SolarSim(SiteConfig(), seed=1)
    sim.state.cloud_factor = cloud_factor

    for b in sim.state.blocks:
        _update_bank_classifier(sim.cfg, sim.state, b)

    for b in sim.state.blocks:
        assert b.state == "nominal", (
            f"Bank {b.id} flipped to {b.state!r} at cloud_factor={cloud_factor} — "
            "healthy banks must stay nominal regardless of irradiance"
        )


# ---------------------------------------------------------------------------
# AC-UI-2 #9 — night (poa=0): expected=0 so fill formula returns 0, not NaN
# ---------------------------------------------------------------------------

def test_ac_ui2_night_poa_zero_no_nan_fill():
    """At night (poa=0) bank_expected_mw = 0.  The fill formula must handle
    zero-denominator gracefully and return 0% (not NaN or error).

    TC-SOL-14 already confirms all banks are nominal at night; this test
    confirms the bar formula itself is safe.
    """
    sim = SolarSim(SiteConfig(), seed=1)
    sim.state.poa = 0.0
    sim.state.cloud_factor = 1.0

    fills = _bar_fills(sim)

    for i, pct in enumerate(fills):
        assert pct == pytest.approx(0.0, abs=1e-9), (
            f"Bank {i+1} fill at night should be exactly 0%; got {pct}"
        )
        # Most importantly — must be a plain float, not NaN or inf
        import math
        assert math.isfinite(pct), f"Bank {i+1} fill is not finite: {pct}"


# ---------------------------------------------------------------------------
# AC-UI-2 #10 — fill ratio is consistent with the snapshot's counted_output_mw
# ---------------------------------------------------------------------------

def test_ac_ui2_fill_matches_snapshot_fields():
    """The bar formula (counted_output_mw / bank_expected_mw) must agree with
    snapshot fields.  If the snapshot is wired to different physics the bars
    would show a different value than the underlying model.

    Under the three-tier Mistral aggregation, counted_output_mw in the snapshot
    is mistral_bank_mw(fraction, b) — not the POA-physics value.  expected_mw
    remains POA-based (used for the classifier, not the output path).
    """
    FRACTION = 0.85
    sim = SolarSim(SiteConfig(), seed=1)
    sim.set_mistral_fraction(FRACTION)
    snap = sim.snapshot()

    cfg, st = sim.cfg, sim.state
    for bank_snap in snap["banks"]:
        b_id = bank_snap["id"]
        b = next(b for b in st.blocks if b.id == b_id)

        snap_counted = bank_snap["counted_output_mw"]
        snap_expected = bank_snap["expected_mw"]

        # Three-tier Mistral formula: output = fraction × rated_mw for enabled banks.
        model_out = mistral_bank_mw(FRACTION, b)
        model_exp = bank_expected_mw(cfg, st, b)

        assert snap_counted == pytest.approx(model_out, abs=1e-9), (
            f"Bank {b_id}: snapshot counted_output_mw "
            f"({snap_counted}) != mistral_bank_mw ({model_out:.6f})"
        )
        assert snap_expected == pytest.approx(model_exp, abs=1e-9), (
            f"Bank {b_id}: snapshot expected_mw "
            f"({snap_expected}) != model ({model_exp:.6f})"
        )
