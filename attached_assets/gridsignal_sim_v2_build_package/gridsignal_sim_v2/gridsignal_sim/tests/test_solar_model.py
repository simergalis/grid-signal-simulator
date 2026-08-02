"""
Deterministic checks on the renewable solar model and the §7.2 step 4 reserve
arithmetic.

The seed-point tests exist so that any change to renewable/config.py that
silently moves the reference operating point fails loudly rather than quietly
invalidating every screenshot and every number in the spec.
"""

import math

import pytest

from renewable.config import SiteConfig
from renewable.solar import (
    SolarSim, PlantState, BlockState,
    p_renewable_mw, p_clear_sky_mw, p_total_mw, p_dispatch_required_mw,
    largest_block_mw, fleet_ramp_mw_per_s, bess_bridging_mw, bess_usable_mwh,
    reserve_check, temp_derate,
)


@pytest.fixture
def sim():
    return SolarSim(SiteConfig(), seed=1)


# ---------------------------------------------------------------------------
# seed operating point — the reference the console and the spec both quote
# ---------------------------------------------------------------------------

def test_seed_solar_output(sim):
    assert p_renewable_mw(sim.cfg, sim.state) == pytest.approx(4.29, abs=0.01)


def test_seed_net_dispatch_requirement(sim):
    assert p_dispatch_required_mw(sim.cfg, sim.state) == pytest.approx(7.75, abs=0.02)


def test_seed_share_of_site_draw(sim):
    solar = p_renewable_mw(sim.cfg, sim.state)
    total = p_total_mw(sim.cfg, sim.state)
    assert solar / total * 100 == pytest.approx(35.6, abs=0.1)


def test_net_requirement_is_total_minus_renewable(sim):
    """§7.1.1 — the definition, asserted directly."""
    cfg, st = sim.cfg, sim.state
    assert p_dispatch_required_mw(cfg, st) == pytest.approx(
        p_total_mw(cfg, st) - p_renewable_mw(cfg, st))


def test_performance_ratio_exposes_soiling(sim):
    """Clear-sky model excludes soiling, so PR must sit below 100%."""
    pr = p_renewable_mw(sim.cfg, sim.state) / p_clear_sky_mw(sim.cfg, sim.state)
    assert 0.90 < pr < 0.97


# ---------------------------------------------------------------------------
# block-level physics
# ---------------------------------------------------------------------------

def test_output_clips_at_inverter_nameplate(sim):
    sim.state.poa = 1400          # unphysical, to force the clip
    for b in sim.state.blocks:
        assert b.rated_mw >= 0
    assert p_renewable_mw(sim.cfg, sim.state) <= sim.cfg.plant_rated_ac_mw + 1e-9


def test_faulted_block_produces_nothing(sim):
    before = p_renewable_mw(sim.cfg, sim.state)
    sim.state.blocks[0].state = "fault"
    after = p_renewable_mw(sim.cfg, sim.state)
    assert after < before
    assert after == pytest.approx(before - 0.85, abs=0.02)


def test_open_strings_derate_rather_than_exclude(sim):
    """§27.4 — a degraded block is counted at re-rated capability, not zero."""
    b = sim.state.blocks[2]
    full = p_renewable_mw(sim.cfg, sim.state)
    b.strings_out = 6                       # a quarter of the block
    partial = p_renewable_mw(sim.cfg, sim.state)
    assert 0 < partial < full
    assert partial > full - b.rated_mw      # not excluded entirely


def test_temperature_derate_direction(sim):
    assert temp_derate(sim.cfg, 25) == pytest.approx(1.0)
    assert temp_derate(sim.cfg, 60) < temp_derate(sim.cfg, 40) < 1.0


def test_n1_is_the_largest_producing_block(sim):
    outs = sorted(_b_out(sim, b) for b in sim.state.blocks)
    assert largest_block_mw(sim.cfg, sim.state) == pytest.approx(outs[-1])


def _b_out(sim, b):
    from renewable.solar import block_output_mw
    return block_output_mw(sim.cfg, sim.state, b)


# ---------------------------------------------------------------------------
# §7.1.2 anchor constraint
# ---------------------------------------------------------------------------

def test_anchor_reserve_is_withheld_while_islanded(sim):
    cfg, st = sim.cfg, sim.state
    expected = min(cfg.bess_rated_mw, cfg.bess_rated_mw * st.bess_soc) - cfg.anchor_reserve_mw
    assert bess_bridging_mw(cfg, st) == pytest.approx(expected)


def test_grid_connected_site_withholds_nothing():
    cfg = SiteConfig(islanded=False)
    s = SolarSim(cfg, seed=1)
    assert bess_bridging_mw(cfg, s.state) == pytest.approx(
        min(cfg.bess_rated_mw, cfg.bess_rated_mw * s.state.bess_soc))


def test_bridging_falls_faster_than_soc(sim):
    cfg, st = sim.cfg, sim.state
    before = bess_bridging_mw(cfg, st)
    st.bess_soc = st.bess_soc / 2
    after = bess_bridging_mw(cfg, st)
    assert after < before / 2      # anchor duty comes off the top


# ---------------------------------------------------------------------------
# §7.2 step 4 reserve check
# ---------------------------------------------------------------------------

def test_plant_loss_is_covered_at_seed(sim):
    solar = p_renewable_mw(sim.cfg, sim.state)
    rc = reserve_check(sim.cfg, sim.state, solar, dt_lead_s=0.0)
    assert rc.passes
    assert rc.deficit_mw == 0.0


def test_supply_loss_carries_no_lead_time(sim):
    """§7.1.1 — with dt_lead = 0 the peak shortfall equals the full step."""
    rc = reserve_check(sim.cfg, sim.state, 4.29, dt_lead_s=0.0)
    assert rc.peak_shortfall_mw == pytest.approx(4.29)
    assert rc.gap_s == pytest.approx(rc.ramp_time_s)


def test_compute_lead_time_reduces_the_peak(sim):
    """A 20 MW job with 30 s of warning: turbines have already made 6 MW."""
    cfg = sim.cfg
    for t in cfg.turbines:
        t.online = t.id in ("gt-01",)          # single turbine, r = 0.2 MW/s
    rc = reserve_check(cfg, sim.state, 20.0, dt_lead_s=30.0)
    assert rc.ramp_time_s == pytest.approx(100.0)
    assert rc.peak_shortfall_mw == pytest.approx(14.0)   # 20 - 0.2*30
    assert rc.gap_s == pytest.approx(70.0)


def test_shortfall_declines_rather_than_being_flat(sim):
    """Energy is the triangle under a declining shortfall, not peak * gap."""
    rc = reserve_check(sim.cfg, sim.state, 8.0, dt_lead_s=0.0)
    flat = rc.peak_shortfall_mw * rc.gap_s / 3600.0
    assert rc.energy_needed_mwh == pytest.approx(flat / 2.0)


def test_compound_event_is_additive_and_fails_at_seed(sim):
    """§7.1.1 — a plant loss coincident with a compute step is the sizing case."""
    solar = p_renewable_mw(sim.cfg, sim.state)
    rc = reserve_check(sim.cfg, sim.state, solar + 6.0, dt_lead_s=0.0)
    assert rc.delta_p_mw == pytest.approx(solar + 6.0)
    assert not rc.passes
    assert rc.deficit_mw > 0


def test_low_soc_escalates_plant_loss_to_a_failure(sim):
    sim.inject("bess")
    solar = p_renewable_mw(sim.cfg, sim.state)
    rc = reserve_check(sim.cfg, sim.state, solar, dt_lead_s=0.0)
    assert not rc.passes


def test_losing_a_turbine_lengthens_every_gap(sim):
    solar = p_renewable_mw(sim.cfg, sim.state)
    before = reserve_check(sim.cfg, sim.state, solar).gap_s
    sim.inject("turbine")
    after = reserve_check(sim.cfg, sim.state, solar).gap_s
    assert after > before


def test_no_turbines_online_gives_infinite_ramp_time(sim):
    for t in sim.cfg.turbines:
        t.online = False
    assert fleet_ramp_mw_per_s(sim.cfg) == 0
    rc = reserve_check(sim.cfg, sim.state, 4.0)
    assert math.isinf(rc.ramp_time_s)


def test_sustainable_duration_is_a_duration_not_an_energy(sim):
    """The check compares seconds to seconds. Guard against the MW*s error."""
    rc = reserve_check(sim.cfg, sim.state, 4.0)
    usable = bess_usable_mwh(sim.cfg, sim.state)
    assert rc.sustainable_duration_s == pytest.approx(usable / 4.0 * 3600.0)


def test_solar_never_contributes_to_ramp_capability(sim):
    """§7.1.1 — bridging must be identical whether or not the sun is shining."""
    with_sun = bess_bridging_mw(sim.cfg, sim.state)
    for b in sim.state.blocks:
        b.state = "fault"
    assert bess_bridging_mw(sim.cfg, sim.state) == pytest.approx(with_sun)


# ---------------------------------------------------------------------------
# stressors and snapshot contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["cloud", "trip", "poi", "soil",
                                  "spike", "turbine", "bess", "reset"])
def test_every_stressor_applies_cleanly(sim, kind):
    assert sim.inject(kind)["ok"] is True
    snap = sim.snapshot()
    assert snap["power"]["p_renewable_mw"] >= 0


def test_unknown_stressor_is_rejected(sim):
    assert sim.inject("nope")["ok"] is False


def test_poi_loss_zeroes_the_plant(sim):
    sim.inject("poi")
    assert p_renewable_mw(sim.cfg, sim.state) == pytest.approx(0.0)


def test_reset_restores_the_seed_point(sim):
    sim.inject("poi")
    sim.inject("turbine")
    sim.inject("bess")
    sim.inject("reset")
    assert p_renewable_mw(sim.cfg, sim.state) == pytest.approx(4.29, abs=0.01)
    assert fleet_ramp_mw_per_s(sim.cfg) == pytest.approx(0.4)


def test_snapshot_has_the_keys_the_console_consumes(sim):
    snap = sim.snapshot()
    for key in ("site", "atmosphere", "power", "fleet", "blocks",
                "exposure", "reserve", "log"):
        assert key in snap
    assert len(snap["blocks"]) == sim.cfg.blocks
    for k in ("n1", "plant", "compound"):
        assert "passes" in snap["reserve"][k]


def test_ticking_keeps_output_physical(sim):
    for _ in range(300):
        sim.tick()
    solar = p_renewable_mw(sim.cfg, sim.state)
    assert 0 <= solar <= sim.cfg.plant_rated_ac_mw


def test_snapshot_is_json_safe_with_no_generation(sim):
    """Infinity is not valid JSON. A dark plant with no shortfall produces it."""
    import json
    sim.inject("poi")
    for t in sim.cfg.turbines:
        t.online = False
    json.dumps(sim.snapshot())          # must not raise
    assert sim.snapshot()["reserve"]["plant"]["ramp_time_s"] is None
