"""TC-87 .. TC-91 and the change predicates.

Catalogue values here are test fixtures, not proposals. Real deadbands must come
from a distribution scan over recordings (NAR-2), not from this file.
"""
from __future__ import annotations

import copy
import inspect
import json
import time

import pytest

from nar001 import detector as det
from nar001.detector import (AVAILABILITY, COUNT, EDGE, LEVEL, RATE, SET,
                             ChangeDetector, MissingParameters, required_parameters)

from fixtures import tick

CATALOGUE = {
    "deadband_power_mw": 0.5,
    "deadband_power_small_mw": 0.1,
    "deadband_soc_fraction": 0.01,
    "deadband_frequency_hz": 0.05,
    "deadband_temp_c": 0.5,
    "deadband_dt_lead_s": 1.0,
    "deadband_step_phase": 0.1,
    "rate_band_mw_per_s": 0.2,
    "rate_confirm_ticks": 2,
}


def new() -> ChangeDetector:
    return ChangeDetector(dict(CATALOGUE))


def feed(d: ChangeDetector, payloads, signal=None):
    out = []
    for i, p in enumerate(payloads):
        out.extend(d.step("run-test", i, p))
    return [r for r in out if signal is None or r.signal == signal]


def ramp(values, key="p_demand_mw", start_t=0.0, dt=5.0):
    """Ticks varying one field, with the mirrored wire alias kept consistent."""
    alias = {"p_demand_mw": "p_total_mw", "p_compute_demand_mw": "p_compute_mw",
             "p_cooling_demand_mw": "p_cooling_mw"}.get(key)
    out = []
    for i, v in enumerate(values):
        over = {key: v, "sim_time_seconds": start_t + i * dt}
        if alias:
            over[alias] = v
        out.append(tick(**over))
    return out


# ------------------------------------------------------------- TC-87 deadband
def test_tc87_below_deadband_emits_nothing():
    band = CATALOGUE["deadband_power_mw"]
    recs = feed(new(), ramp([10.0, 10.0 + band - 1e-9]), "LOAD.p_demand_mw")
    assert recs == []


def test_tc87_at_deadband_emits():
    band = CATALOGUE["deadband_power_mw"]
    recs = feed(new(), ramp([10.0, 10.0 + band]), "LOAD.p_demand_mw")
    assert len(recs) == 1
    assert recs[0].kind == LEVEL
    assert recs[0].delta == pytest.approx(band)
    assert recs[0].deadband_applied == band
    assert recs[0].deadband_key == "deadband_power_mw"


def test_tc87_deadband_is_symmetric():
    band = CATALOGUE["deadband_power_mw"]
    assert feed(new(), ramp([10.0, 10.0 - band]), "LOAD.p_demand_mw")
    assert feed(new(), ramp([10.0, 10.0 - band + 1e-9]), "LOAD.p_demand_mw") == []


def test_tc87_first_observation_is_a_baseline_not_a_change():
    assert feed(new(), ramp([10.0]), "LOAD.p_demand_mw") == []


# ------------------------------------------------------------ TC-88 hysteresis
def test_tc88_monotonic_ramp_emits_once_per_deadband_crossed():
    band = CATALOGUE["deadband_power_mw"]
    values = [10.0 + i * (band / 4.0) for i in range(21)]   # spans 5 deadbands
    recs = feed(new(), ramp(values), "LOAD.p_demand_mw")
    assert len(recs) == 5
    assert [r.prev for r in recs] == pytest.approx(
        [10.0 + i * band for i in range(5)])


def test_tc88_dither_inside_one_deadband_emits_nothing():
    """Baseline is the last *reported* value, so oscillation inside the band is
    silent. (The v0.3 design text says 'emits 1' -- it should say 0.)"""
    band = CATALOGUE["deadband_power_mw"]
    values = [10.0] + [10.0 + (band * 0.9 if i % 2 else -band * 0.9)
                       for i in range(40)]
    assert feed(new(), ramp(values), "LOAD.p_demand_mw") == []


def test_tc88_slow_ramp_is_not_lost():
    """Comparing against the previous tick instead would emit nothing here."""
    band = CATALOGUE["deadband_power_mw"]
    values = [10.0 + i * (band / 10.0) for i in range(31)]  # 3 bands, tiny steps
    assert len(feed(new(), ramp(values), "LOAD.p_demand_mw")) == 3


def test_tc88_baseline_advances_to_reported_value():
    band = CATALOGUE["deadband_power_mw"]
    recs = feed(new(), ramp([10.0, 10.0 + band, 10.0 + band + band / 2]),
                "LOAD.p_demand_mw")
    assert len(recs) == 1
    assert recs[0].curr == pytest.approx(10.0 + band)


# ----------------------------------------------------------------- TC-89 edges
def test_tc89_state_transitions_always_fire():
    seq = ["offline", "starting", "synchronised", "unloading", "offline"]
    payloads = []
    for i, s in enumerate(seq):
        p = tick(sim_time_seconds=float(i * 5))
        p["turbine_units"] = [{"unit_id": "t0", "state": s, "output_mw": 0.0,
                               "rated_mw": 7.0, "hot_standby": False}]
        payloads.append(p)
    recs = feed(new(), payloads, "GEN.unit_state[0]")
    assert [(r.prev, r.curr) for r in recs] == [
        ("offline", "starting"), ("starting", "synchronised"),
        ("synchronised", "unloading"), ("unloading", "offline")]
    assert all(r.deadband_applied is None for r in recs)


def test_tc89_boolean_and_string_edges_fire():
    a = tick(sim_time_seconds=0.0)
    b = copy.deepcopy(a)
    b["sim_time_seconds"] = 5.0
    b["commitment_block"]["reserve_satisfied"] = True
    b["commitment_block"]["action"] = "commit"
    recs = feed(new(), [a, b])
    kinds = {r.signal: (r.prev, r.curr) for r in recs if r.kind == EDGE}
    assert kinds["GEN.reserve_satisfied"] == (False, True)
    assert kinds["GEN.commitment_action"] == ("hold", "commit")


def test_tc89_per_unit_signals_are_independent():
    a = tick(sim_time_seconds=0.0)
    b = copy.deepcopy(a)
    b["sim_time_seconds"] = 5.0
    b["turbine_units"][1]["state"] = "starting"
    recs = [r for r in feed(new(), [a, b]) if r.kind == EDGE]
    assert [r.signal for r in recs] == ["GEN.unit_state[1]"]


def test_tc89_unit_count_change_is_reported():
    a = tick(sim_time_seconds=0.0)
    b = copy.deepcopy(a)
    b["sim_time_seconds"] = 5.0
    b["turbine_units"] = b["turbine_units"][:1]
    recs = [r for r in feed(new(), [a, b]) if r.kind == COUNT]
    assert len(recs) == 1 and (recs[0].prev, recs[0].curr) == (2, 1)


# ----------------------------------------------------------- sets and nullness
def test_set_membership_reports_added_and_removed():
    a = tick(sim_time_seconds=0.0, data_quality_tags=["UNCALIBRATED_SITE"])
    b = tick(sim_time_seconds=5.0,
             data_quality_tags=["UNCALIBRATED_SITE", "WORKLOAD_SIGNAL_STALE"])
    c = tick(sim_time_seconds=10.0, data_quality_tags=["WORKLOAD_SIGNAL_STALE"])
    recs = feed(new(), [a, b, c], "DEMAND.data_quality_tags")
    assert recs[0].delta == {"added": ["WORKLOAD_SIGNAL_STALE"], "removed": []}
    assert recs[1].delta == {"added": [], "removed": ["UNCALIBRATED_SITE"]}


def test_checkpoint_states_dict_is_tracked_as_a_set():
    a = tick(sim_time_seconds=0.0, checkpoint_states={"job-1": "running"})
    b = tick(sim_time_seconds=5.0,
             checkpoint_states={"job-1": "checkpoint", "job-2": "running"})
    recs = feed(new(), [a, b], "SCHED.checkpoint_states")
    assert recs[0].delta["added"] == ["job-1=checkpoint", "job-2=running"]
    assert recs[0].delta["removed"] == ["job-1=running"]


def test_field_going_null_is_an_availability_change_not_a_value_change():
    a = tick(sim_time_seconds=0.0, p_expected_mw=4.0)
    b = tick(sim_time_seconds=5.0, p_expected_mw=None)
    recs = feed(new(), [a, b], "RENEW.p_expected_mw")
    assert len(recs) == 1
    assert recs[0].kind == AVAILABILITY
    assert (recs[0].prev, recs[0].curr) == ("ok", "null")
    assert recs[0].delta is None      # never a numeric delta against a null


def test_null_to_value_is_reported_and_rebaselines():
    a = tick(sim_time_seconds=0.0, p_expected_mw=None)
    b = tick(sim_time_seconds=5.0, p_expected_mw=4.0)
    c = tick(sim_time_seconds=10.0, p_expected_mw=4.1)      # inside deadband
    recs = feed(new(), [a, b, c], "RENEW.p_expected_mw")
    assert [r.kind for r in recs] == [AVAILABILITY]


def test_absent_field_never_emits_a_value_change():
    a = tick(sim_time_seconds=0.0)
    b = tick(sim_time_seconds=5.0)
    for p in (a, b):
        p.pop("frequency_hz", None)
    assert feed(new(), [a, b], "GEN.frequency_hz") == []


# ------------------------------------------------------------------- rate kind
def test_rate_requires_consecutive_confirmations():
    band = CATALOGUE["rate_band_mw_per_s"]
    step = band * 5.0 * 1.5                       # 1.5x band over a 5 s tick
    recs = feed(new(), ramp([10.0, 10.0 + step]), "LOAD.p_demand_rate")
    assert recs == []                             # one tick is not a confirmation
    recs = feed(new(), ramp([10.0, 10.0 + step, 10.0 + 2 * step]),
                "LOAD.p_demand_rate")
    assert len(recs) == 1 and recs[0].kind == RATE


def test_rate_rearms_only_after_falling_back_inside_the_band():
    band = CATALOGUE["rate_band_mw_per_s"]
    step = band * 5.0 * 1.5
    vals = [10.0] + [10.0 + step * i for i in range(1, 6)]      # sustained
    assert len(feed(new(), ramp(vals), "LOAD.p_demand_rate")) == 1
    vals2 = vals + [vals[-1]] * 3 + [vals[-1] + step * i for i in range(1, 4)]
    assert len(feed(new(), ramp(vals2), "LOAD.p_demand_rate")) == 2


def test_rate_derives_dt_from_sim_time_not_a_constant():
    band = CATALOGUE["rate_band_mw_per_s"]
    step = band * 2.0 * 1.5                       # 1.5x band over a 2 s tick
    vals = [10.0, 10.0 + step, 10.0 + 2 * step]
    assert len(feed(new(), ramp(vals, dt=2.0), "LOAD.p_demand_rate")) == 1
    # the same absolute steps over 20 s ticks are well inside the band
    assert feed(new(), ramp(vals, dt=20.0), "LOAD.p_demand_rate") == []


# ------------------------------------------------- TC-90 purity and determinism
def test_tc90_same_input_yields_identical_output():
    payloads = ramp([10.0 + i * 0.13 for i in range(60)])
    runs = []
    for _ in range(2):
        recs = feed(new(), copy.deepcopy(payloads))
        runs.append(json.dumps([r.to_dict() for r in recs], sort_keys=True,
                               default=str))
    assert runs[0] == runs[1]


def test_tc90_no_rng_clock_or_environment_in_detector():
    src = inspect.getsource(det)
    for banned in ("import random", "random.", "time.time", "datetime.now",
                   "uuid", "os.environ", "sorted(set(" ):
        if banned == "sorted(set(":
            continue
        assert banned not in src, f"detector references {banned}"


def test_tc90_detector_does_not_mutate_the_payload():
    payloads = ramp([10.0, 11.0, 12.0])
    before = json.dumps(payloads, sort_keys=True)
    feed(new(), payloads)
    assert json.dumps(payloads, sort_keys=True) == before


def test_tc90_output_order_is_registry_order():
    a = tick(sim_time_seconds=0.0)
    b = tick(sim_time_seconds=5.0, p_demand_mw=20.0, p_total_mw=20.0,
             turbine_output_mw=12.0)
    recs = feed(new(), [a, b])
    order = [s.signal for s in det.REGISTRY]
    got = [r.signal for r in recs if r.signal in order]
    assert got == sorted(got, key=order.index)


# ----------------------------------------------------------------- TC-91 budget
def test_tc91_step_completes_within_budget():
    d = new()
    payloads = ramp([10.0 + i * 0.13 for i in range(200)])
    d.step("run-test", 0, payloads[0])            # warm the state
    start = time.perf_counter()
    for i, p in enumerate(payloads[1:], start=1):
        d.step("run-test", i, p)
    per_tick_ms = (time.perf_counter() - start) / (len(payloads) - 1) * 1000.0
    assert per_tick_ms < 50.0, f"{per_tick_ms:.2f} ms/tick"


# --------------------------------------------------- catalogue, not constants
def test_missing_catalogue_keys_raise_with_the_full_list():
    with pytest.raises(MissingParameters) as ei:
        ChangeDetector({})
    assert set(ei.value.keys) == set(required_parameters())
    assert len(ei.value.keys) >= 8


def test_partial_catalogue_names_only_what_is_missing():
    cat = dict(CATALOGUE)
    del cat["deadband_soc_fraction"]
    del cat["rate_band_mw_per_s"]
    with pytest.raises(MissingParameters) as ei:
        ChangeDetector(cat)
    assert ei.value.keys == ["deadband_soc_fraction", "rate_band_mw_per_s"]


def test_every_banded_signal_names_a_catalogue_key():
    for spec in det.REGISTRY:
        if spec.kind in (LEVEL, RATE):
            assert spec.band_key, f"{spec.signal} has no band_key"
        if spec.kind == RATE:
            assert spec.confirm_key, f"{spec.signal} has no confirm_key"


def test_band_value_comes_from_the_catalogue_not_the_module():
    tight = ChangeDetector({**CATALOGUE, "deadband_power_mw": 0.01})
    loose = ChangeDetector({**CATALOGUE, "deadband_power_mw": 5.0})
    payloads = ramp([10.0, 10.2, 10.4, 10.6])
    assert len(feed(tight, copy.deepcopy(payloads), "LOAD.p_demand_mw")) == 3
    assert feed(loose, copy.deepcopy(payloads), "LOAD.p_demand_mw") == []


def test_records_carry_provenance():
    recs = feed(new(), ramp([10.0, 11.0]), "LOAD.p_demand_mw")
    r = recs[0]
    assert r.wire_path in ("p_demand_mw", "p_total_mw")
    assert r.units == "MW" and r.spec_ref == "§4"
    assert r.t_sim_s == pytest.approx(5.0)
    assert r.run_id == "run-test"


def test_detector_reports_no_severity_or_ranking():
    r = feed(new(), ramp([10.0, 11.0]), "LOAD.p_demand_mw")[0]
    keys = set(r.to_dict())
    assert not keys & {"severity", "priority", "salience", "rank", "score",
                       "cause", "verdict"}


def test_alias_fallback_resolves_when_canonical_name_absent():
    payloads = ramp([10.0, 11.0])
    for p in payloads:
        p.pop("p_demand_mw")                       # only the wire alias remains
    recs = feed(new(), payloads, "LOAD.p_demand_mw")
    assert len(recs) == 1 and recs[0].wire_path == "p_total_mw"


# --------------------------------------- regressions found by running the SC-20
def test_rating_change_smaller_than_a_power_deadband_still_fires():
    """Ratings are configuration. The 4.59 -> 2.03 MW cooling rating change seen
    between two console captures would clear a 0.5 MW deadband, but a 4.59 -> 4.5
    change would not, and any change to a rating matters. EDGE, not LEVEL."""
    a = tick(sim_time_seconds=0.0, rated_cooling_mw=4.59)
    b = tick(sim_time_seconds=5.0, rated_cooling_mw=4.50)   # 0.09 MW, well inside
    recs = feed(new(), [a, b], "THERM.rated_cooling_mw")
    assert len(recs) == 1 and recs[0].kind == EDGE
    assert (recs[0].prev, recs[0].curr) == (4.59, 4.50)


def test_bess_capacity_changes_are_edges_too():
    a = tick(sim_time_seconds=0.0, bess_usable_mwh=2.0, bess_rated_mw=15.0)
    b = tick(sim_time_seconds=5.0, bess_usable_mwh=8.0, bess_rated_mw=15.0)
    recs = [r for r in feed(new(), [a, b]) if r.signal == "GEN.bess_usable_mwh"]
    assert len(recs) == 1 and recs[0].kind == EDGE


def test_balance_defect_and_generation_are_in_the_registry():
    """Both were missing from the first registry draft. p_generation_mw is half
    of the power-balance identity and d4_balance_defect_mw is the system's own
    statement about it -- neither is optional to watch."""
    names = {s.signal for s in det.REGISTRY}
    assert {"GEN.p_generation_mw", "GEN.d4_balance_defect_mw",
            "GEN.grid_exchange_mw", "GEN.asset_delivery_error_mw",
            "GEN.frequency_forcing_mw", "GEN.protection_provisional"} <= names


def test_rate_cannot_see_a_single_tick_step_and_that_is_documented():
    """A step is exactly one tick of high derivative, so it can never satisfy a
    consecutive-confirmation predicate. LEVEL catches it instead. This pins the
    limitation so nobody later 'fixes' RATE by dropping the confirmation count."""
    band = CATALOGUE["rate_band_mw_per_s"]
    step = band * 5.0 * 10                       # 10x the band, one tick only
    payloads = ramp([10.0, 10.0, 10.0 + step, 10.0 + step, 10.0 + step])
    d = new()
    all_recs = feed(d, payloads)
    assert [r for r in all_recs if r.signal == "LOAD.p_demand_rate"] == []
    level = [r for r in all_recs if r.signal == "LOAD.p_demand_mw"]
    assert len(level) == 1 and level[0].delta == pytest.approx(step)
    assert "structurally invisible" in det.__doc__


# ------------------------------------------------------------- co-occurrence
def test_cooccurrence_finds_mutually_implied_signals():
    from nar001.cooccurrence import co_occurrence, redundant_pairs
    # reserve_floor_mw is demand plus a constant, so the two always move together
    payloads = []
    for i, v in enumerate([10.0, 12.0, 14.0, 16.0]):
        p = tick(sim_time_seconds=float(i * 5), p_demand_mw=v, p_total_mw=v)
        p["commitment_block"]["reserve_floor_mw"] = v + 7.0
        payloads.append(p)
    recs = feed(new(), payloads)
    pairs = {(p["a"], p["b"]) for p in redundant_pairs(recs)}
    assert ("GEN.reserve_floor_mw", "LOAD.p_demand_mw") in pairs
    co = co_occurrence(recs)
    assert co["n_ticks_with_change"] == 3


def test_cooccurrence_requires_more_than_one_coincidence():
    from nar001.cooccurrence import redundant_pairs
    a = tick(sim_time_seconds=0.0)
    b = tick(sim_time_seconds=5.0, p_demand_mw=20.0, p_total_mw=20.0,
             ambient_avg_c=99.0)
    recs = feed(new(), [a, b])
    assert redundant_pairs(recs, min_co_ticks=2) == []
    assert redundant_pairs(recs, min_co_ticks=1)


def test_detector_stays_quiet_on_a_realistic_run():
    """A feed that scrolls every tick is unreadable. On an 800-tick staircase
    only a small fraction of ticks should produce anything at all."""
    from sc20_scenario import build
    from nar001.cooccurrence import co_occurrence
    d = new()
    recs = []
    for i, p in enumerate(build()):
        recs.extend(d.step("run-sc20", i, p))
    co = co_occurrence(recs)
    assert co["n_ticks_with_change"] / 800 < 0.25
    assert co["records_per_changed_tick"] < 10
