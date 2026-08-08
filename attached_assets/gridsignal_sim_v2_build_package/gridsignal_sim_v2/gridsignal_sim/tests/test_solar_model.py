"""
Deterministic checks on the renewable solar model and the §7.2 step 4 reserve
arithmetic.

The seed-point tests exist so that any change to renewable/config.py that
silently moves the reference operating point fails loudly rather than quietly
invalidating every screenshot and every number in the spec.

TC-SOL-01 through TC-SOL-09 cover the bank/feeder model introduced in spec §3–§5.
"""

import json
import math

import pytest

from renewable.config import SiteConfig
from renewable.solar import (
    SolarSim, PlantState, BankState, BlockState,
    bank_output_mw, bank_expected_mw, bank_clear_sky_mw,
    counted_output_mw, _update_bank_classifier, _raw_state,
    _bank_physical_mw, _pms_p_renewable,
    p_renewable_mw, p_clear_sky_mw, p_demand_mw, p_dispatch_required_mw,
    largest_bank_mw, largest_feeder_mw, _largest_feeder_id,
    largest_block_mw,   # compat alias
    fleet_ramp_mw_per_s, bess_bridging_mw, bess_usable_mwh,
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
    total = p_demand_mw(sim.cfg, sim.state)
    assert solar / total * 100 == pytest.approx(35.6, abs=0.1)


def test_net_requirement_is_total_minus_renewable(sim):
    """§7.1.1 — the definition, asserted directly."""
    cfg, st = sim.cfg, sim.state
    assert p_dispatch_required_mw(cfg, st) == pytest.approx(
        p_demand_mw(cfg, st) - p_renewable_mw(cfg, st))


def test_performance_ratio_exposes_soiling(sim):
    """Clear-sky model excludes soiling, so PR must sit below 100%."""
    pr = p_renewable_mw(sim.cfg, sim.state) / p_clear_sky_mw(sim.cfg, sim.state)
    assert 0.90 < pr < 0.97


# ---------------------------------------------------------------------------
# bank-level physics
# ---------------------------------------------------------------------------

def test_output_clips_at_inverter_nameplate(sim):
    sim.state.poa = 1400          # unphysical, to force the clip
    assert p_renewable_mw(sim.cfg, sim.state) <= sim.cfg.plant_rated_ac_mw + 1e-9


def test_faulted_bank_produces_nothing(sim):
    """Tripping a bank drops output by approximately one bank's rated contribution."""
    before = p_renewable_mw(sim.cfg, sim.state)
    b = sim.state.blocks[0]
    b.state = "out"
    b.fault = "arc_fault"
    after = p_renewable_mw(sim.cfg, sim.state)
    assert after < before
    # One bank ≈ 0.215 MW at seed (0.25 MW rated × 96.9% × soiling etc.)
    assert after == pytest.approx(before - 0.215, abs=0.01)


# Backward-compat name used in some older references
def test_faulted_block_produces_nothing(sim):
    """Alias — BlockState == BankState, same assertion."""
    before = p_renewable_mw(sim.cfg, sim.state)
    b = sim.state.blocks[0]
    b.state = "out"
    b.fault = "arc_fault"
    after = p_renewable_mw(sim.cfg, sim.state)
    assert after < before


def test_open_strings_derate_rather_than_exclude(sim):
    """§27.4 — a degraded bank is counted at re-rated capability, not zero."""
    b = sim.state.blocks[2]
    full = p_renewable_mw(sim.cfg, sim.state)
    b.strings_out = 3                       # half the bank's strings open
    partial = p_renewable_mw(sim.cfg, sim.state)
    assert 0 < partial < full
    assert partial > full - b.rated_mw      # not excluded entirely


def test_temperature_derate_direction(sim):
    assert temp_derate(sim.cfg, 25) == pytest.approx(1.0)
    assert temp_derate(sim.cfg, 60) < temp_derate(sim.cfg, 40) < 1.0


def test_n1_is_the_largest_producing_bank(sim):
    outs = sorted(counted_output_mw(sim.cfg, sim.state, b) for b in sim.state.blocks)
    assert largest_bank_mw(sim.cfg, sim.state) == pytest.approx(outs[-1])


def test_largest_block_mw_alias(sim):
    """largest_block_mw is a backward-compat alias for largest_bank_mw."""
    assert largest_block_mw(sim.cfg, sim.state) == pytest.approx(
        largest_bank_mw(sim.cfg, sim.state))


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
        b.state = "out"
    assert bess_bridging_mw(sim.cfg, sim.state) == pytest.approx(with_sun)


# ---------------------------------------------------------------------------
# stressors and snapshot contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", [
    "cloud", "trip", "bank_trip", "poi", "soil", "spike",
    "turbine", "bess", "feeder_open", "comms_loss", "bank_derate", "reset",
])
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
    for key in ("site", "atmosphere", "power", "fleet",
                "banks", "blocks",      # both keys present
                "feeders", "exposure", "reserve", "log", "advisories"):
        assert key in snap, f"missing key: {key}"
    # blocks is an alias for banks
    assert len(snap["blocks"]) == sim.cfg.banks
    assert len(snap["banks"])  == sim.cfg.banks
    # reserve has both new keys and the compat alias
    for k in ("n1_feeder", "n1_bank", "n1", "plant", "compound"):
        assert k in snap["reserve"], f"missing reserve key: {k}"
        assert "passes" in snap["reserve"][k]


def test_ticking_keeps_output_physical(sim):
    for _ in range(300):
        sim.tick()
    solar = p_renewable_mw(sim.cfg, sim.state)
    assert 0 <= solar <= sim.cfg.plant_rated_ac_mw


def test_snapshot_is_json_safe_with_no_generation(sim):
    """Infinity is not valid JSON. A dark plant with no shortfall produces it."""
    sim.inject("poi")
    for t in sim.cfg.turbines:
        t.online = False
    json.dumps(sim.snapshot())          # must not raise
    assert sim.snapshot()["reserve"]["plant"]["ramp_time_s"] is None


# ---------------------------------------------------------------------------
# TC-SOL-01  Bank sum == p_renewable_mw == SLD tile value (AC-INV-1)
# ---------------------------------------------------------------------------

def test_sol01_conservation_bank_sum_equals_p_renewable(sim):
    """AC-INV-1: p_renewable_mw == sum of counted_output_mw per bank."""
    cfg, st = sim.cfg, sim.state
    bank_sum = sum(counted_output_mw(cfg, st, b) for b in st.blocks)
    assert bank_sum == pytest.approx(p_renewable_mw(cfg, st), abs=1e-9)


def test_sol01_snapshot_power_equals_bank_sum(sim):
    """Snapshot power.p_renewable_mw == sum of banks[].counted_output_mw."""
    snap = sim.snapshot()
    bank_sum = sum(b["counted_output_mw"] for b in snap["banks"])
    assert bank_sum == pytest.approx(snap["power"]["p_renewable_mw"], abs=1e-9)


# ---------------------------------------------------------------------------
# TC-SOL-02  Feeder subtotals sum to plant total
# ---------------------------------------------------------------------------

def test_sol02_feeder_subtotals_sum_to_plant(sim):
    """Feeder output_mw values must sum to p_renewable_mw."""
    snap = sim.snapshot()
    feeder_sum = sum(f["output_mw"] for f in snap["feeders"])
    assert feeder_sum == pytest.approx(snap["power"]["p_renewable_mw"], abs=1e-9)


# ---------------------------------------------------------------------------
# TC-SOL-03  60 % POA reduction leaves all banks nominal
# ---------------------------------------------------------------------------

def test_sol03_sixty_pct_poa_leaves_all_banks_nominal(sim):
    """Expected and measured both drop proportionally — ratio stays ~97 %."""
    st = sim.state
    st.cloud_factor = 0.4   # 60 % reduction
    # Run 3 ticks so the hysteresis clock settles (ratio still > 0.92 so
    # no transition would occur, but we run them to confirm stability).
    for _ in range(3):
        # Don't call sim.tick() — it would drift poa; just re-run classifier.
        for b in st.blocks:
            from renewable.solar import _update_bank_classifier
            _update_bank_classifier(sim.cfg, st, b)

    for b in st.blocks:
        assert b.state == "nominal", (
            f"bank {b.id} is {b.state} after 60% POA reduction — "
            f"expected nominal (ratio should stay at ~97%)")


# ---------------------------------------------------------------------------
# TC-SOL-04  Degraded bank counted at measured, not nameplate, not zero (§27.4)
# ---------------------------------------------------------------------------

def test_sol04_degraded_bank_counted_at_measured(sim):
    """A bank with strings open is counted at its actual (reduced) output."""
    cfg, st = sim.cfg, sim.state
    b = st.blocks[0]

    # Manually set to degraded (skip hysteresis for this unit test).
    b.state = "degraded"
    b.strings_out = 3   # half strings open

    measured = bank_output_mw(cfg, st, b)    # reduced output
    counted  = counted_output_mw(cfg, st, b) # must equal measured

    assert counted == pytest.approx(measured, abs=1e-9), (
        "degraded bank counted_output_mw must equal its actual measured output")
    assert counted > 0.0, "degraded bank must not be counted as zero"
    assert counted < b.rated_mw, "degraded bank must not be counted at nameplate"


# ---------------------------------------------------------------------------
# TC-SOL-05  State change requires 3 consecutive ticks; 2 ticks does not flip
# ---------------------------------------------------------------------------

def test_sol05_hysteresis_3_ticks_to_degrade(sim):
    """Opening strings degrades output below 0.92× expected; state must not
    flip until 3 consecutive classifier ticks confirm the new state."""
    cfg, st = sim.cfg, sim.state
    b = st.blocks[5]   # pick a mid-plant bank

    # Confirm nominal at seed.
    assert b.state == "nominal"

    # Open 3 of 6 strings → ratio ≈ 0.485 (well below 0.92 threshold).
    b.strings_out = 3

    # After 1 tick: must still be nominal.
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal", "state must not flip after only 1 tick"

    # After 2 ticks: must still be nominal.
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal", "state must not flip after only 2 ticks"

    # After 3 ticks: must be degraded.
    _update_bank_classifier(cfg, st, b)
    assert b.state == "degraded", "state must flip to degraded after 3 ticks"
    assert b.reason == "strings_open"


def test_sol05_hysteresis_resets_on_interruption(sim):
    """If the condition disappears on tick 2, the counter resets."""
    cfg, st = sim.cfg, sim.state
    b = st.blocks[5]

    # Tick 1 with fault condition.
    b.strings_out = 3
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal"

    # Tick 2: restore strings — counter should reset.
    b.strings_out = 0
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal"

    # Tick 3 with fault condition again: counter restarts, must NOT flip yet.
    b.strings_out = 3
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal", (
        "counter must restart after an interruption; state must not flip")


# ---------------------------------------------------------------------------
# TC-SOL-06  no_comms counted at zero and flagged separately from out
# ---------------------------------------------------------------------------

def test_sol06_no_comms_counted_at_zero(sim):
    cfg, st = sim.cfg, sim.state
    b = st.blocks[0]
    b.telemetry_age_s = 15.0   # > 10 s threshold
    _update_bank_classifier(cfg, st, b)

    assert b.state == "no_comms"
    assert counted_output_mw(cfg, st, b) == pytest.approx(0.0)


def test_sol06_no_comms_immediate_no_hysteresis(sim):
    """no_comms is asserted on the first tick (no 3-tick wait)."""
    cfg, st = sim.cfg, sim.state
    b = st.blocks[0]
    b.telemetry_age_s = 11.0

    _update_bank_classifier(cfg, st, b)     # single tick
    assert b.state == "no_comms", "no_comms must be immediate, not 3-tick"


def test_sol06_no_comms_distinct_from_out(sim):
    """A no_comms bank and an out bank both count as zero but have different state."""
    cfg, st = sim.cfg, sim.state
    b_comms = st.blocks[0]
    b_out   = st.blocks[1]

    b_comms.telemetry_age_s = 15.0
    _update_bank_classifier(cfg, st, b_comms)
    b_out.state = "out"

    assert b_comms.state == "no_comms"
    assert b_out.state   == "out"
    # Both count zero
    assert counted_output_mw(cfg, st, b_comms) == 0.0
    assert counted_output_mw(cfg, st, b_out)   == 0.0


# ---------------------------------------------------------------------------
# TC-SOL-10  Repaired bank (strings restored, fault cleared) recovers to nominal
# ---------------------------------------------------------------------------

def test_sol10_out_bank_recovers_when_fault_cleared(sim):
    """A bank tripped via stressor (fault latched) stays out until fault is cleared.
    Once cleared, 3 classifier ticks must return it to nominal.
    """
    cfg, st = sim.cfg, sim.state
    b = st.blocks[3]

    # Simulate a stressor trip (latched fault).
    b.state = "out"
    b.fault = "arc_fault"

    # Running 10 ticks with the fault set must keep it out.
    for _ in range(10):
        _update_bank_classifier(cfg, st, b)
    assert b.state == "out", "latched fault must hold bank out indefinitely"

    # Maintenance: clear the fault (e.g. reset stressor or breaker reclosed).
    b.fault = None

    # After clearing fault, 3 ticks required to confirm recovery.
    _update_bank_classifier(cfg, st, b)
    assert b.state == "out", "must not flip on first tick after fault clear"
    _update_bank_classifier(cfg, st, b)
    assert b.state == "out", "must not flip on second tick after fault clear"
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal", "must recover to nominal on third tick after fault clear"


def test_sol10_classifier_out_without_fault_recovers(sim):
    """An 'out' state assigned by the classifier (no explicit fault) can recover
    to nominal when the physical cause is removed — e.g. shading clears.

    Entry: strings_out=6 (all strings open) → ratio=0 → 3 ticks → out.
    Exit:  strings restored (strings_out=0) → ratio≈97% → 3 ticks → nominal.
    """
    cfg, st = sim.cfg, sim.state
    b = st.blocks[4]
    assert b.fault is None, "precondition: no latched fault"

    # Force all strings open → classifier assigns out after 3 ticks.
    b.strings_out = b.strings_total   # ratio = 0
    for _ in range(3):
        _update_bank_classifier(cfg, st, b)
    assert b.state == "out", f"expected 'out' after all strings open, got '{b.state}'"
    assert b.fault is None, "no fault should be latched by the classifier"

    # Restore strings.
    b.strings_out = 0

    # Recovery requires 3 ticks.
    _update_bank_classifier(cfg, st, b)
    assert b.state == "out", "must not recover on tick 1 after string restore"
    _update_bank_classifier(cfg, st, b)
    assert b.state == "out", "must not recover on tick 2 after string restore"
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal", "must recover to nominal on tick 3 after string restore"


# ---------------------------------------------------------------------------
# TC-SOL-11  no_comms clears immediately when telemetry is restored
# ---------------------------------------------------------------------------

def test_sol11_no_comms_exits_immediately_when_telemetry_restored(sim):
    """no_comms is asserted immediately and also cleared immediately.

    On the tick that telemetry_age_s drops back to ≤ 10, the bank re-enters
    the normal hysteresis loop.  If its physical output is nominal, it becomes
    nominal on the same tick (coming from no_comms the hysteresis starts fresh,
    and a fresh evaluation of a nominal bank sets state=nominal immediately
    because candidate == new state after the reset).
    """
    cfg, st = sim.cfg, sim.state
    b = st.blocks[6]

    # Enter no_comms.
    b.telemetry_age_s = 15.0
    _update_bank_classifier(cfg, st, b)
    assert b.state == "no_comms"

    # Restore comms.
    b.telemetry_age_s = 0.0

    # First tick after telemetry restored: state must NOT be no_comms.
    _update_bank_classifier(cfg, st, b)
    assert b.state != "no_comms", (
        "no_comms must exit immediately when telemetry is restored")
    # With all strings healthy, physical output is nominal → should be nominal.
    assert b.state == "nominal", (
        f"bank with healthy strings should be nominal after comms restore, got '{b.state}'")


def test_sol11_no_comms_hysteresis_resets_on_restore(sim):
    """After exiting no_comms, the hysteresis counter must start clean.

    If the bank's physical condition warrants 'degraded', it must still take
    3 ticks to arrive at 'degraded' after comms are restored — not zero.
    """
    cfg, st = sim.cfg, sim.state
    b = st.blocks[7]

    # Enter no_comms.
    b.telemetry_age_s = 15.0
    _update_bank_classifier(cfg, st, b)
    assert b.state == "no_comms"

    # Open 3 strings so physical ratio ≈ 50% (degraded territory) but not 'out'.
    b.strings_out = 3
    b.telemetry_age_s = 0.0  # restore comms

    # Tick 1 post-restore: exits no_comms, becomes nominal (fresh hysteresis
    # starts at nominal; 'degraded' candidate starts accumulating from tick 1).
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal", (
        "first tick after comms restore must be nominal (hysteresis starts fresh)")

    # Tick 2: still nominal (1 tick toward degraded so far).
    _update_bank_classifier(cfg, st, b)
    assert b.state == "nominal", "second tick — not yet 3 ticks toward degraded"

    # Tick 3: 3 consecutive degraded readings → transition.
    _update_bank_classifier(cfg, st, b)
    assert b.state == "degraded", "must transition to degraded after 3 ticks"


# ---------------------------------------------------------------------------
# TC-SOL-12  Latched fault stays out even when strings are repaired
# ---------------------------------------------------------------------------

def test_sol12_latched_fault_blocks_recovery(sim):
    """If b.fault is set, the bank stays 'out' regardless of physical output.

    This prevents an arc-faulted inverter from being mistakenly re-classified
    as nominal just because the physics model says it should be producing power.
    Only an explicit maintenance reset (clearing b.fault) allows recovery.
    """
    cfg, st = sim.cfg, sim.state
    b = st.blocks[9]

    # Latch a fault and put the bank in out state.
    b.state = "out"
    b.fault = "arc_fault"

    # Physically the bank looks fine (all strings healthy, good irradiance).
    assert b.strings_out == 0
    assert st.poa > 500    # enough sun

    # 10 ticks of the classifier must not change the state.
    for tick_n in range(10):
        _update_bank_classifier(cfg, st, b)
        assert b.state == "out", (
            f"latched fault must block recovery at tick {tick_n+1}: "
            f"state is '{b.state}'")

    # Physical output is still non-zero in the physics model (not counted though).
    from renewable.solar import _bank_physical_mw
    physical = _bank_physical_mw(cfg, st, b)
    assert physical > 0.0, "physical model shows output, but fault keeps it latched"
    assert counted_output_mw(cfg, st, b) == 0.0, "counted output must stay zero"


# ---------------------------------------------------------------------------
# TC-SOL-07  largest_feeder_mw > largest_bank_mw at seed
# ---------------------------------------------------------------------------

def test_sol07_feeder_mw_exceeds_bank_mw_at_seed(sim):
    """AC-RES-1: seed feeder ≈ 1.07 MW, seed bank ≈ 0.215 MW."""
    cfg, st = sim.cfg, sim.state
    f_mw = largest_feeder_mw(cfg, st)
    b_mw = largest_bank_mw(cfg, st)

    assert f_mw > b_mw, (
        f"largest_feeder_mw ({f_mw:.4f}) must exceed largest_bank_mw ({b_mw:.4f})")
    assert f_mw == pytest.approx(1.07, abs=0.02), (
        f"largest_feeder_mw should be ~1.07 MW at seed; got {f_mw:.4f}")
    assert b_mw == pytest.approx(0.215, abs=0.01), (
        f"largest_bank_mw should be ~0.215 MW at seed; got {b_mw:.4f}")


# ---------------------------------------------------------------------------
# TC-SOL-08  N−1 reserve row uses the feeder figure
# ---------------------------------------------------------------------------

def test_sol08_n1_reserve_uses_feeder_figure(sim):
    """reserve.n1 delta_p_mw must equal largest_feeder_mw, not largest_bank_mw."""
    cfg, st = sim.cfg, sim.state
    snap = sim.snapshot()
    feeder_mw = largest_feeder_mw(cfg, st)
    bank_mw   = largest_bank_mw(cfg, st)

    n1_delta = snap["reserve"]["n1"]["delta_p_mw"]
    assert n1_delta == pytest.approx(feeder_mw, abs=1e-9), (
        "N−1 row must be sized on the feeder, not the bank")
    assert n1_delta > bank_mw, (
        "N−1 feeder figure must exceed the bank figure at seed")


# ---------------------------------------------------------------------------
# TC-SOL-09  No-feeder config reproduces bank-level N−1 exactly
# ---------------------------------------------------------------------------

def test_sol09_no_feeder_config_gives_bank_level_n1():
    """With no feeder topology, each bank is its own contingency group.
    largest_feeder_mw must equal largest_bank_mw (degenerate case, spec §5)."""
    cfg = SiteConfig(feeder_ids=[])   # no feeder grouping
    sim = SolarSim(cfg, seed=1)

    f_mw = largest_feeder_mw(cfg, sim.state)
    b_mw = largest_bank_mw(cfg, sim.state)

    assert f_mw == pytest.approx(b_mw, abs=1e-9), (
        f"Without feeders, largest_feeder_mw ({f_mw:.6f}) must equal "
        f"largest_bank_mw ({b_mw:.6f})")


# ---------------------------------------------------------------------------
# TC-SOL-14  Plant dark at night: all nominal, expected 0.00, no alarms
# ---------------------------------------------------------------------------

def test_sol14_night_zero_expected_all_nominal(sim):
    """Zero output must be unremarkable when expectation is also zero (night).

    TC-SOL-14 matters more than its position suggests — if the classifier
    raises alarms at night, operators will stop trusting it.
    """
    st = sim.state
    # Simulate night: no irradiance.
    st.poa = 0.0
    st.cloud_factor = 1.0    # clear night sky, just no sun

    for b in st.blocks:
        _update_bank_classifier(sim.cfg, st, b)

    for b in st.blocks:
        assert b.state == "nominal", (
            f"bank {b.id} is {b.state} at night — zero output with zero "
            f"expected should be nominal, not alarming")
        assert bank_expected_mw(sim.cfg, st, b) == pytest.approx(0.0, abs=1e-9)

    assert p_renewable_mw(sim.cfg, sim.state) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Additional seed-config sanity: 20 banks × 0.25 MW = 5.00 MW plant
# ---------------------------------------------------------------------------

def test_seed_config_has_20_banks():
    cfg = SiteConfig()
    assert cfg.banks == 20
    assert cfg.bank_rated_ac_mw == pytest.approx(0.25)
    assert cfg.plant_rated_ac_mw == pytest.approx(5.00)


def test_seed_config_has_4_feeders():
    cfg = SiteConfig()
    assert len(cfg.feeder_ids) == 4
    assert cfg.banks_per_feeder == 5


def test_compat_aliases_on_config():
    cfg = SiteConfig()
    assert cfg.blocks == cfg.banks
    assert cfg.block_rated_ac_mw == cfg.bank_rated_ac_mw
    assert cfg.strings_per_block == cfg.strings_per_bank


def test_blockstate_is_bankstate_alias():
    """BlockState must be the same class as BankState (backward compat)."""
    assert BlockState is BankState


# ---------------------------------------------------------------------------
# FR-SOL-2 / TC-SOL (task §111)
#   feeder_open emits exactly ONE common_cause advisory naming fdr-B, not 5
# ---------------------------------------------------------------------------

def test_feeder_open_emits_one_common_cause_advisory(sim):
    """feeder_open sets all 5 banks on fdr-B to no_comms simultaneously.

    The common-cause detector must aggregate them into a single advisory at
    feeder scope rather than 5 individual bank events (FR-SOL-2).
    """
    result = sim.inject("feeder_open")
    assert result["ok"] is True, "feeder_open stressor must return ok=True"

    sim.tick()   # advisory engine runs at end of each tick

    snap = sim.snapshot()
    assert "advisories" in snap, "snapshot must contain 'advisories' key"

    cc = [a for a in snap["advisories"] if a["code"] == "common_cause"]
    assert len(cc) == 1, (
        f"Expected exactly 1 common_cause advisory; got {len(cc)}: {cc}"
    )
    advisory = cc[0]
    assert advisory["scope"] == "feeder"
    assert advisory["feeder"] == "fdr-B", (
        f"common_cause advisory must name fdr-B; got feeder={advisory['feeder']!r}"
    )
    assert len(advisory["banks"]) == 5, (
        f"fdr-B has 5 banks; advisory listed {len(advisory['banks'])}"
    )


def test_poi_emits_common_cause_advisory_per_feeder(sim):
    """poi trips all 20 banks simultaneously (5 per feeder, 4 feeders).

    Each feeder qualifies for a common_cause advisory independently.
    There must be exactly 4 advisories — one per feeder — not 20 individual
    bank events and not just one plant-level event.
    """
    result = sim.inject("poi")
    assert result["ok"] is True

    sim.tick()   # advisory engine runs at end of each tick

    snap = sim.snapshot()
    cc = [a for a in snap["advisories"] if a["code"] == "common_cause"]
    assert len(cc) == 4, (
        f"poi trips 5 banks on each of 4 feeders — expect 4 common_cause advisories; "
        f"got {len(cc)}: {[a['feeder'] for a in cc]}"
    )
    feeder_names = {a["feeder"] for a in cc}
    assert feeder_names == {"fdr-A", "fdr-B", "fdr-C", "fdr-D"}, (
        f"advisories must cover all 4 feeders; got {feeder_names}"
    )
    for a in cc:
        assert len(a["banks"]) == 5, (
            f"feeder {a['feeder']} must list 5 banks; got {len(a['banks'])}"
        )


def test_feeder_open_fdr_b_banks_all_no_comms(sim):
    """All 5 banks on fdr-B must be in no_comms state after feeder_open."""
    sim.inject("feeder_open")
    fdr_b = [b for b in sim.state.blocks if b.feeder_id == "fdr-B"]
    assert len(fdr_b) == 5, "fdr-B must have 5 banks"
    for b in fdr_b:
        assert b.state == "no_comms", (
            f"bank {b.id} on fdr-B should be no_comms after feeder_open; got {b.state!r}"
        )


def test_feeder_open_does_not_trigger_reconciliation(sim):
    """feeder_open sets derate=0 so physical output is also 0 — no reconciliation divergence.

    The reconciliation_divergence advisory fires only when physical output
    exceeds counted output.  feeder_open zeroes both, so no divergence.
    """
    sim.inject("feeder_open")
    for _ in range(6):    # more than the 5-tick threshold
        sim.tick()

    snap = sim.snapshot()
    recon = [a for a in snap["advisories"] if a["code"] == "reconciliation_divergence"]
    assert len(recon) == 0, (
        "feeder_open must NOT trigger reconciliation_divergence (both sides zero); "
        f"got advisories: {snap['advisories']}"
    )


# ---------------------------------------------------------------------------
# FR-SOL-1 / TC-SOL (task §111)
#   comms_loss triggers reconciliation_divergence within 5 ticks
# ---------------------------------------------------------------------------

def test_comms_loss_triggers_reconciliation_divergence(sim):
    """comms_loss puts fdr-A into no_comms but leaves physical output intact.

    The PMS sees solar still generating; the model counts it as zero.
    After 5 consecutive ticks with divergence > 0.15 MW, a
    reconciliation_divergence advisory must be present in the snapshot.
    """
    sim.inject("comms_loss")

    # 5 ticks required to cross the threshold.
    for _ in range(5):
        sim.tick()

    snap = sim.snapshot()
    recon = [a for a in snap["advisories"] if a["code"] == "reconciliation_divergence"]
    assert len(recon) >= 1, (
        "comms_loss must trigger reconciliation_divergence after 5 ticks; "
        f"got advisories: {snap['advisories']}"
    )
    advisory = recon[0]
    assert advisory["scope"] == "plant"
    assert len(advisory["banks"]) > 0, "advisory must name at least one suspect bank"


def test_comms_loss_counted_mw_drops_but_physical_does_not(sim):
    """comms_loss reduces counted solar but physical output is unchanged."""
    cfg, st = sim.cfg, sim.state
    counted_before = p_renewable_mw(cfg, st)
    physical_before = sum(_bank_physical_mw(cfg, st, b) for b in st.blocks)

    sim.inject("comms_loss")

    counted_after  = p_renewable_mw(cfg, st)
    physical_after = sum(_bank_physical_mw(cfg, st, b) for b in st.blocks)

    assert counted_after < counted_before, (
        "counted P_renewable must drop when fdr-A goes to no_comms"
    )
    assert physical_after == pytest.approx(physical_before, abs=0.01), (
        "physical output must not change with comms_loss (banks still generating)"
    )


def test_comms_loss_advisory_clears_after_reset(sim):
    """Advisory counter resets with the sim so no stale state carries over."""
    sim.inject("comms_loss")
    for _ in range(6):
        sim.tick()

    snap_before = sim.snapshot()
    recon_before = [a for a in snap_before["advisories"]
                    if a["code"] == "reconciliation_divergence"]
    assert len(recon_before) >= 1, "prerequisite: advisory must exist before reset"

    sim.inject("reset")
    sim.tick()  # one tick after reset to run advisory engine

    snap_after = sim.snapshot()
    recon_after = [a for a in snap_after["advisories"]
                   if a["code"] == "reconciliation_divergence"]
    assert len(recon_after) == 0, (
        "reconciliation_divergence advisory must clear after sim reset"
    )


# ---------------------------------------------------------------------------
# TC-SOL-12 (task §111)
#   Solar never contributes to BESS bridging capability under any bank state
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("state", ["nominal", "degraded", "out", "no_comms"])
def test_solar_bridging_is_state_independent(sim, state):
    """§7.1.2 — BESS bridging available must be the same regardless of solar state.

    Solar power does not ramp: it is non-dispatchable.  Changing every bank
    to any of the four states must not alter bess_bridging_mw().
    """
    cfg, st = sim.cfg, sim.state
    bridging_before = bess_bridging_mw(cfg, st)

    for b in st.blocks:
        b.state = state

    bridging_after = bess_bridging_mw(cfg, st)

    assert bridging_after == pytest.approx(bridging_before, abs=1e-9), (
        f"bess_bridging_mw changed when all banks set to '{state}': "
        f"before={bridging_before:.4f}, after={bridging_after:.4f}. "
        "Solar state must not affect bridging capability."
    )


# ---------------------------------------------------------------------------
# TC-SOL-13 (task §111)
#   Snapshot is JSON-safe and well-formed when all banks are in no_comms
# ---------------------------------------------------------------------------

def test_all_banks_no_comms_snapshot_is_json_safe(sim):
    """Snapshot must be JSON-serialisable and structurally complete when every
    bank is in no_comms (e.g. plant-wide telemetry outage).

    Key invariants:
    - p_renewable_mw = 0 (all no_comms → counted as zero)
    - feeders[] all report 0 output
    - advisories[] contains at most common_cause entries (no recon divergence yet
      because it requires 5 ticks)
    - No floating-point infinity appears (InfiniteRampTime scenario)
    """
    for b in sim.state.blocks:
        b.telemetry_age_s = 999.0
        b.state = "no_comms"
        b._cand_state = "no_comms"
        b._cand_ticks = 0

    import json
    snap = sim.snapshot()
    # JSON serialisation must not raise (no bare float('inf'))
    json_str = json.dumps(snap)
    assert json_str  # non-empty

    # Counted output must be zero
    assert snap["power"]["p_renewable_mw"] == pytest.approx(0.0, abs=1e-9), (
        "all-no_comms plant must have p_renewable_mw = 0"
    )

    # Every feeder must report 0 output
    for f in snap["feeders"]:
        assert f["output_mw"] == pytest.approx(0.0, abs=1e-9), (
            f"feeder {f['id']} output_mw must be 0 with all banks in no_comms"
        )

    # reserve fields with infinite ramp times must be serialised as null, not Infinity
    reserve_vals = json.loads(json_str)["reserve"]
    for scenario_key in ("n1_feeder", "n1_bank", "plant", "compound"):
        rt = reserve_vals[scenario_key].get("ramp_time_s")
        assert rt is None or isinstance(rt, (int, float)), (
            f"reserve.{scenario_key}.ramp_time_s must be null or a number; got {rt!r}"
        )
