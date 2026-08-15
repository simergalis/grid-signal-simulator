"""
Regression tests for operator-commanded bank and feeder controls.

Four inject kinds — bank_off, bank_on, feeder_off, feeder_on — let an operator
shut down and restore solar banks without simulating a fault.  These tests guard
the operator_shutdown latch and the classifier's respect for it against accidental
refactors.

TC-OP-1  bank_off / bank_on round-trip
TC-OP-2  feeder_off / feeder_on round-trip
TC-OP-3  Missing or unknown target is rejected
TC-OP-4  tick() does not reclassify a shutdown bank back to nominal
TC-OP-5  reset clears all operator shutdowns and restores the full plant
"""

import pytest

from renewable.config import SiteConfig
from renewable.solar import (
    SolarSim,
    BankState,
    counted_output_mw,
    p_renewable_mw,
    _update_bank_classifier,
)


@pytest.fixture
def sim():
    """Fresh simulator with a deterministic seed — 20 banks, 4 feeders."""
    return SolarSim(SiteConfig(), seed=1)


# ---------------------------------------------------------------------------
# TC-OP-1  bank_off sets output=0 / state=out / operator_shutdown=True;
#          bank_on restores physics output and clears operator_shutdown
# ---------------------------------------------------------------------------

def test_op1_bank_off_zeroes_output_and_sets_state(sim):
    """bank_off must immediately set state=out and counted output to 0."""
    cfg, st = sim.cfg, sim.state
    target = "bank-01"
    b = next(b for b in st.blocks if b.id == target)

    # Precondition: bank is producing at seed.
    assert counted_output_mw(cfg, st, b) > 0.0, "precondition: bank must produce at seed"

    result = sim.inject("bank_off", target=target)

    assert result["ok"] is True, f"bank_off must return ok=True; got {result}"
    assert b.state == "out",            "bank_off must set state='out'"
    assert b.operator_shutdown is True, "bank_off must set operator_shutdown=True"
    assert b.fault == "operator_shutdown", "bank_off must set fault='operator_shutdown'"
    assert counted_output_mw(cfg, st, b) == pytest.approx(0.0), \
        "counted_output_mw must be 0 immediately after bank_off"


def test_op1_bank_off_reflected_in_snapshot(sim):
    """Snapshot banks[].output_mw must be 0 for a shutdown bank (cold-start path)."""
    target = "bank-01"
    sim.inject("bank_off", target=target)

    snap = sim.snapshot()
    bank_snap = next(b for b in snap["banks"] if b["id"] == target)

    assert bank_snap["output_mw"] == pytest.approx(0.0), \
        "snapshot output_mw must be 0 after bank_off"
    assert bank_snap["state"] == "out", \
        "snapshot state must be 'out' after bank_off"
    assert bank_snap["operator_shutdown"] is True, \
        "snapshot operator_shutdown must be True after bank_off"


def test_op1_bank_on_restores_physics_and_clears_flag(sim):
    """bank_on after bank_off must restore physics output and clear operator_shutdown."""
    cfg, st = sim.cfg, sim.state
    target = "bank-01"
    b = next(b for b in st.blocks if b.id == target)

    sim.inject("bank_off", target=target)
    assert b.operator_shutdown is True   # precondition

    result = sim.inject("bank_on", target=target)

    assert result["ok"] is True,             "bank_on must return ok=True"
    assert b.operator_shutdown is False,     "bank_on must clear operator_shutdown"
    assert b.fault is None,                  "bank_on must clear fault"
    assert b.state == "nominal",             "bank_on must set state='nominal'"
    assert counted_output_mw(cfg, st, b) > 0.0, \
        "counted_output_mw must be positive again after bank_on (seed has sun)"


def test_op1_p_renewable_drops_on_bank_off_and_recovers_on_bank_on(sim):
    """Plant-level P_renewable must fall on bank_off and recover to within 1% on bank_on."""
    cfg, st = sim.cfg, sim.state
    target = "bank-03"
    baseline = p_renewable_mw(cfg, st)

    sim.inject("bank_off", target=target)
    after_off = p_renewable_mw(cfg, st)
    assert after_off < baseline, "P_renewable must decrease after bank_off"

    sim.inject("bank_on", target=target)
    after_on = p_renewable_mw(cfg, st)
    assert after_on == pytest.approx(baseline, rel=0.01), \
        "P_renewable must recover to near-baseline after bank_on"


# ---------------------------------------------------------------------------
# TC-OP-2  feeder_off sets all feeder banks to 0 and operator_shutdown=True;
#          feeder_on restores all banks and clears feeder operator_shutdown
# ---------------------------------------------------------------------------

def test_op2_feeder_off_zeros_all_banks_on_feeder(sim):
    """feeder_off must set every bank on the feeder to state=out / operator_shutdown=True."""
    cfg, st = sim.cfg, sim.state
    target_feeder = "fdr-A"
    fdr_banks = [b for b in st.blocks if b.feeder_id == target_feeder]
    assert len(fdr_banks) == 5, f"fdr-A must have 5 banks; got {len(fdr_banks)}"

    result = sim.inject("feeder_off", target=target_feeder)

    assert result["ok"] is True, f"feeder_off must return ok=True; got {result}"
    for b in fdr_banks:
        assert b.operator_shutdown is True, \
            f"bank {b.id}: operator_shutdown must be True after feeder_off"
        assert b.state == "out", \
            f"bank {b.id}: state must be 'out' after feeder_off"
        assert counted_output_mw(cfg, st, b) == pytest.approx(0.0), \
            f"bank {b.id}: counted_output_mw must be 0 after feeder_off"


def test_op2_feeder_snapshot_operator_shutdown_true(sim):
    """Feeder snapshot must show operator_shutdown=True only when ALL banks are shut down."""
    target_feeder = "fdr-C"
    sim.inject("feeder_off", target=target_feeder)

    snap = sim.snapshot()
    feeder_snap = next(f for f in snap["feeders"] if f["id"] == target_feeder)

    assert feeder_snap["output_mw"] == pytest.approx(0.0), \
        "feeder output_mw must be 0 after feeder_off"
    assert feeder_snap["operator_shutdown"] is True, \
        "feeder snapshot operator_shutdown must be True when all banks shut down"


def test_op2_feeder_on_restores_all_banks(sim):
    """feeder_on must restore every bank on the feeder: state=nominal, operator_shutdown=False."""
    cfg, st = sim.cfg, sim.state
    target_feeder = "fdr-B"
    fdr_banks = [b for b in st.blocks if b.feeder_id == target_feeder]

    sim.inject("feeder_off", target=target_feeder)
    # Verify precondition
    assert all(b.operator_shutdown for b in fdr_banks), \
        "precondition: all fdr-B banks must be shut down"

    result = sim.inject("feeder_on", target=target_feeder)

    assert result["ok"] is True, "feeder_on must return ok=True"
    for b in fdr_banks:
        assert b.operator_shutdown is False, \
            f"bank {b.id}: operator_shutdown must be False after feeder_on"
        assert b.fault is None, \
            f"bank {b.id}: fault must be None after feeder_on"
        assert b.state == "nominal", \
            f"bank {b.id}: state must be 'nominal' after feeder_on"
        assert counted_output_mw(cfg, st, b) > 0.0, \
            f"bank {b.id}: counted output must be positive after feeder_on"


def test_op2_feeder_snapshot_operator_shutdown_clears_after_feeder_on(sim):
    """Feeder snapshot operator_shutdown must go False after feeder_on."""
    target_feeder = "fdr-D"
    sim.inject("feeder_off", target=target_feeder)
    sim.inject("feeder_on",  target=target_feeder)

    snap = sim.snapshot()
    feeder_snap = next(f for f in snap["feeders"] if f["id"] == target_feeder)
    assert feeder_snap["operator_shutdown"] is False, \
        "feeder operator_shutdown must clear after feeder_on"


def test_op2_feeder_partial_shutdown_does_not_set_feeder_operator_shutdown(sim):
    """Feeder snapshot operator_shutdown is True only if ALL banks are shut down.

    Shutting down a single bank on a feeder must not set the feeder-level flag.
    """
    cfg, st = sim.cfg, sim.state
    target_feeder = "fdr-A"
    fdr_banks = [b for b in st.blocks if b.feeder_id == target_feeder]

    # Shut down only one bank, not the whole feeder.
    sim.inject("bank_off", target=fdr_banks[0].id)

    snap = sim.snapshot()
    feeder_snap = next(f for f in snap["feeders"] if f["id"] == target_feeder)
    assert feeder_snap["operator_shutdown"] is False, \
        "feeder operator_shutdown must be False when only some banks are shut down"


# ---------------------------------------------------------------------------
# TC-OP-3  Missing target or unknown feeder/bank is rejected
# ---------------------------------------------------------------------------

def test_op3_bank_off_without_target_returns_error(sim):
    """bank_off with no target must return ok=False with an explanatory error."""
    result = sim.inject("bank_off")
    assert result["ok"] is False, "bank_off with no target must return ok=False"
    assert "error" in result,     "result must contain an 'error' key"


def test_op3_bank_on_without_target_returns_error(sim):
    """bank_on with no target must return ok=False."""
    result = sim.inject("bank_on")
    assert result["ok"] is False
    assert "error" in result


def test_op3_bank_off_unknown_bank_returns_error(sim):
    """bank_off with a non-existent bank ID must return ok=False."""
    result = sim.inject("bank_off", target="bank-99")
    assert result["ok"] is False, "bank_off on unknown bank must return ok=False"
    assert "error" in result


def test_op3_bank_on_unknown_bank_returns_error(sim):
    """bank_on with a non-existent bank ID must return ok=False."""
    result = sim.inject("bank_on", target="bank-99")
    assert result["ok"] is False
    assert "error" in result


def test_op3_feeder_off_without_target_returns_error(sim):
    """feeder_off with no target must return ok=False."""
    result = sim.inject("feeder_off")
    assert result["ok"] is False
    assert "error" in result


def test_op3_feeder_on_without_target_returns_error(sim):
    """feeder_on with no target must return ok=False."""
    result = sim.inject("feeder_on")
    assert result["ok"] is False
    assert "error" in result


def test_op3_feeder_off_unknown_feeder_returns_error(sim):
    """feeder_off with a feeder that has no banks must return ok=False."""
    result = sim.inject("feeder_off", target="fdr-Z")
    assert result["ok"] is False, "feeder_off on unknown feeder must return ok=False"
    assert "error" in result


def test_op3_feeder_on_unknown_feeder_returns_error(sim):
    """feeder_on with a feeder that has no banks must return ok=False."""
    result = sim.inject("feeder_on", target="fdr-Z")
    assert result["ok"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# TC-OP-4  tick() does not reclassify an operator-shutdown bank back to nominal
#
# bank_off sets fault="operator_shutdown" (a non-None fault).  The classifier's
# latched-fault path (step 2 of _update_bank_classifier) keeps the bank in
# 'out' while any fault is set, regardless of physical output.  This test
# confirms the latch survives many ticks.
# ---------------------------------------------------------------------------

def test_op4_classifier_respects_operator_shutdown_latch(sim):
    """After bank_off, 20 ticks must not reclassify the bank back to nominal.

    The operator_shutdown fault prevents the hysteresis from observing a
    recovery, even though the physical irradiance model would otherwise show
    the bank producing normally.
    """
    cfg, st = sim.cfg, sim.state
    target = "bank-05"
    b = next(b for b in st.blocks if b.id == target)

    sim.inject("bank_off", target=target)
    assert b.fault == "operator_shutdown", "precondition: fault must be set"
    assert b.state == "out",              "precondition: state must be 'out'"

    for tick_n in range(20):
        sim.tick()
        assert b.state == "out", (
            f"operator-shutdown bank reclassified to '{b.state}' on tick {tick_n+1}; "
            "classifier must respect the operator_shutdown latch"
        )
        assert b.operator_shutdown is True, (
            f"operator_shutdown flag was cleared by tick on tick {tick_n+1}"
        )
        assert counted_output_mw(cfg, st, b) == pytest.approx(0.0), (
            f"counted_output_mw non-zero on tick {tick_n+1} despite operator shutdown"
        )


def test_op4_classifier_also_keeps_bank_off_when_called_directly(sim):
    """Calling _update_bank_classifier() directly on a shutdown bank must keep it out.

    This guards the path used by tests that bypass SolarSim.tick().
    """
    cfg, st = sim.cfg, sim.state
    target = "bank-07"
    b = next(b for b in st.blocks if b.id == target)

    sim.inject("bank_off", target=target)

    for _ in range(10):
        _update_bank_classifier(cfg, st, b)
        assert b.state == "out", (
            "direct classifier call on shutdown bank must keep state='out'"
        )


def test_op4_feeder_off_latch_survives_multiple_ticks(sim):
    """All banks on a feeder shut down via feeder_off stay out after many ticks."""
    cfg, st = sim.cfg, sim.state
    target_feeder = "fdr-C"
    fdr_banks = [b for b in st.blocks if b.feeder_id == target_feeder]

    sim.inject("feeder_off", target=target_feeder)

    for _ in range(10):
        sim.tick()

    for b in fdr_banks:
        assert b.state == "out", (
            f"bank {b.id} on {target_feeder} reclassified after feeder_off+ticks; "
            "operator_shutdown latch must persist across ticks"
        )
        assert b.operator_shutdown is True


# ---------------------------------------------------------------------------
# TC-OP-5  reset clears all operator shutdowns and restores the full plant
# ---------------------------------------------------------------------------

def test_op5_reset_clears_bank_operator_shutdown(sim):
    """reset must clear operator_shutdown on a previously shutdown bank."""
    cfg, st = sim.cfg, sim.state
    target = "bank-10"
    b = next(b for b in st.blocks if b.id == target)

    sim.inject("bank_off", target=target)
    assert b.operator_shutdown is True   # precondition

    sim.inject("reset")

    # After reset, re-find the bank (reset recreates the state object).
    b_new = next(b for b in sim.state.blocks if b.id == target)
    assert b_new.operator_shutdown is False, \
        "reset must clear operator_shutdown on a previously shutdown bank"
    assert b_new.fault is None, \
        "reset must clear fault on a previously shutdown bank"
    assert b_new.state == "nominal", \
        "reset must restore state to 'nominal'"


def test_op5_reset_clears_feeder_shutdown(sim):
    """reset must clear operator_shutdown on every bank of a feeder-shutdown feeder."""
    target_feeder = "fdr-B"
    sim.inject("feeder_off", target=target_feeder)

    sim.inject("reset")

    for b in sim.state.blocks:
        assert b.operator_shutdown is False, \
            f"reset must clear operator_shutdown on bank {b.id} (was on feeder {target_feeder})"
        assert b.fault is None, \
            f"reset must clear fault on bank {b.id}"


def test_op5_reset_restores_full_plant_output(sim):
    """reset after shutting down all banks must restore P_renewable to the seed value."""
    cfg, st = sim.cfg, sim.state
    seed_p = p_renewable_mw(cfg, st)

    # Shut down every bank via feeder_off on all feeders.
    for fid in cfg.feeder_ids:
        sim.inject("feeder_off", target=fid)
    assert p_renewable_mw(sim.cfg, sim.state) == pytest.approx(0.0), \
        "precondition: plant must be dark after all-feeder shutdown"

    sim.inject("reset")

    restored_p = p_renewable_mw(sim.cfg, sim.state)
    assert restored_p == pytest.approx(seed_p, abs=0.01), (
        f"P_renewable must return to seed value after reset; "
        f"seed={seed_p:.4f} MW, after reset={restored_p:.4f} MW"
    )


def test_op5_reset_clears_multiple_independent_shutdowns(sim):
    """reset must clear operator_shutdown from a mix of bank_off and feeder_off actions."""
    sim.inject("bank_off",   target="bank-02")
    sim.inject("bank_off",   target="bank-15")
    sim.inject("feeder_off", target="fdr-D")

    sim.inject("reset")

    for b in sim.state.blocks:
        assert b.operator_shutdown is False, \
            f"bank {b.id}: operator_shutdown must be False after reset"
        assert b.fault is None, \
            f"bank {b.id}: fault must be None after reset"


def test_op5_reset_snapshot_shows_no_shutdowns(sim):
    """After reset, the snapshot must show no bank with operator_shutdown=True."""
    sim.inject("feeder_off", target="fdr-A")
    sim.inject("bank_off",   target="bank-11")
    sim.inject("reset")

    snap = sim.snapshot()
    for bank_snap in snap["banks"]:
        assert bank_snap["operator_shutdown"] is False, (
            f"bank {bank_snap['id']}: snapshot operator_shutdown must be False after reset"
        )
    for feeder_snap in snap["feeders"]:
        assert feeder_snap["operator_shutdown"] is False, (
            f"feeder {feeder_snap['id']}: snapshot operator_shutdown must be False after reset"
        )
