"""FrameFact assembler and template narrator tests."""
from __future__ import annotations

import copy
import json

import pytest

from nar001 import narrator as nar
from nar001.detector import ChangeDetector
from nar001.framefact import (CAP_KEY, MissingFrameFactParameters, assemble,
                              fold_redundant)
from nar001.trend import TrendAggregator

from fixtures import deep_set, tick
from test_detector import CATALOGUE, ramp
from test_trend import TREND_CAT

from nar001.framefact import SPREAD_KEY

FF_CAT = {**TREND_CAT, CAP_KEY: 8, SPREAD_KEY: 1e-9}


def build_frame(payloads, cap=8, **cat):
    det = ChangeDetector(dict(CATALOGUE))
    agg = TrendAggregator(dict(TREND_CAT))
    history, window = [], []
    prev = None
    for i, p in enumerate(payloads):
        recs = det.step("run-test", i, p)
        history.extend(recs)
        window = recs
        agg.update(p)
        prev = payloads[i - 1] if i else None
    return assemble("run-test", len(payloads) - 1, payload=payloads[-1],
                    changes=window, trends=agg.facts("run-test", 0),
                    catalogue={**FF_CAT, CAP_KEY: cap, **cat},
                    prev_payload=prev, change_history=history)


# ------------------------------------------------------------------- assembly
def test_missing_cap_parameter_raises():
    with pytest.raises(MissingFrameFactParameters):
        assemble("r", 0, payload=tick(), changes=[], trends=[], catalogue={})


def test_failing_invariants_are_named_not_collapsed():
    """A boolean would let a narrator say 'something is wrong' without saying
    which reading not to trust."""
    p = tick(p_generation_mw=30.90, p_demand_mw=40.36, p_total_mw=40.36)
    ff = build_frame([tick(), p])
    assert ff.invariants_ok is False
    assert "I1" in ff.invariants_failed
    assert isinstance(ff.invariants_failed, list)


def test_clean_frame_reports_ok():
    ff = build_frame([tick(), tick(sim_time_seconds=105.0)])
    assert ff.invariants_ok is True
    assert ff.invariants_failed == []


def test_i6_disagreement_is_surfaced_even_though_it_is_not_a_residual():
    p = deep_set(tick(sim_time_seconds=105.0),
                 "commitment_block.reserve_satisfied", True)
    ff = build_frame([tick(), p])
    assert "I6_agreement" in ff.invariants_failed


def test_state_carries_the_two_contradictions_a_narrator_would_smooth_over():
    ff = build_frame([tick(), tick(sim_time_seconds=105.0)])
    assert ff.state["hold_with_unsatisfied_reserve"] is True
    assert ff.state["reconstructed_floor_violated"] is True
    assert "power_balance_residual_mw" in ff.state


def test_not_evaluable_invariants_are_listed_as_skipped_not_passing():
    ff = build_frame([tick(), tick(sim_time_seconds=105.0)])
    assert "I2b" in ff.invariants_skipped          # kube_metrics is null
    assert "I2b" not in ff.invariants_failed
    assert any("not evaluable" in n for n in ff.notes)


# --------------------------------------------------------------- redundancy
def test_redundant_cofiring_signals_are_folded_to_one_representative():
    """Four signals firing on identical ticks because each is an affine function
    of the others would otherwise fill the cap with restatements of one move."""
    payloads = []
    for i, v in enumerate([10.0, 12.0, 14.0, 16.0, 18.0]):
        p = tick(sim_time_seconds=float(i * 5), p_demand_mw=v, p_total_mw=v,
                 p_generation_mw=v)
        p["commitment_block"]["reserve_floor_mw"] = v + 7.0
        payloads.append(p)
    ff = build_frame(payloads)
    signals = [c["signal"] for c in ff.changes]
    assert len(signals) == len(set(signals))
    assert len(ff.folded) >= 1
    assert all("represented_by" in f for f in ff.folded)


def test_folding_never_discards_an_edge_or_an_availability_change():
    a = tick(sim_time_seconds=0.0)
    b = deep_set(tick(sim_time_seconds=5.0), "commitment_block.action", "commit")
    b = deep_set(b, "p_expected_mw", None)
    ff = build_frame([a, b])
    kinds = {c["kind"] for c in ff.changes}
    assert "edge" in kinds
    assert "availability" in kinds


def test_folded_changes_are_recorded_not_silently_dropped():
    payloads = []
    for i, v in enumerate([10.0, 12.0, 14.0, 16.0]):
        p = tick(sim_time_seconds=float(i * 5), p_demand_mw=v, p_total_mw=v,
                 p_generation_mw=v)
        payloads.append(p)
    ff = build_frame(payloads)
    for f in ff.folded:
        assert f["signal"] and f["represented_by"]
    if ff.folded:
        assert any("folded" in n for n in ff.notes)


def test_single_coincidence_is_not_treated_as_a_relationship():
    a = tick(sim_time_seconds=0.0)
    b = tick(sim_time_seconds=5.0, p_demand_mw=20.0, p_total_mw=20.0,
             ambient_avg_c=99.0)
    kept, folded = fold_redundant([], history=[], spread_max=1e-9)
    assert (kept, folded) == ([], [])
    ff = build_frame([a, b])
    assert ff.folded == []


# ----------------------------------------------------------------------- cap
def _independent_payloads(n=6):
    """Signals moving on different schedules and with unrelated magnitudes, so
    no pair holds a constant delta ratio."""
    out = []
    demand = [10.0, 14.0, 14.0, 21.0, 21.0, 29.0]
    cooling = [2.0, 2.0, 5.0, 5.0, 5.0, 9.0]
    freq = [60.0, 60.3, 59.8, 60.4, 59.7, 60.2]
    bess = [0.0, 0.0, 3.0, 3.0, 8.0, 8.0]
    for i in range(n):
        out.append(tick(sim_time_seconds=float(i * 5),
                        p_demand_mw=demand[i], p_total_mw=demand[i],
                        p_cooling_demand_mw=cooling[i], p_cooling_mw=cooling[i],
                        frequency_hz=freq[i], bess_output_mw=bess[i],
                        bess_soc_fraction=0.5 - i * 0.02))
    return out


def test_cap_drops_are_counted_and_disclosed():
    ff = build_frame(_independent_payloads(), cap=2)
    assert len(ff.changes) == 2
    assert ff.n_changes_dropped == ff.n_changes_total - 2 - len(ff.folded)
    assert any("dropped by the cap" in n for n in ff.notes)


def test_cap_note_disclaims_that_ordering_is_not_salience():
    ff = build_frame(_independent_payloads(), cap=1)
    assert any("not a salience ranking" in n for n in ff.notes)


def test_unrelated_signals_moving_together_are_not_folded():
    """Co-timing is not a relationship. Cooling, frequency and BESS power all
    move during the same window without any fixed ratio between them."""
    ff = build_frame(_independent_payloads(), cap=99)
    signals = {c["signal"] for c in ff.changes}
    assert len(signals) >= 3
    assert ff.folded == []


def test_linear_ramps_fold_and_the_limitation_is_documented():
    """Known false positive: two unrelated signals that both ramp linearly hold a
    constant delta ratio and fold. Only a longer history separates them, so the
    folding is reported rather than silent."""
    from nar001 import framefact as ffmod
    payloads = [tick(sim_time_seconds=float(i * 5),
                     p_demand_mw=10.0 + i * 5, p_total_mw=10.0 + i * 5,
                     frequency_hz=60.0 + i * 0.2) for i in range(5)]
    ff = build_frame(payloads, cap=99)
    assert ff.folded                      # the false positive, pinned
    assert all(f["represented_by"] for f in ff.folded)
    assert "Known limitation" in ffmod.fold_redundant.__doc__


def test_trends_are_filtered_to_the_notable_ones():
    payloads = ramp([10.0 + i * 0.4 for i in range(80)])
    ff = build_frame(payloads)
    assert all(t["direction"] in ("rising", "falling", "oscillating")
               for t in ff.trends)


def test_framefact_is_json_serialisable_and_deterministic():
    payloads = ramp([10.0 + i * 0.4 for i in range(40)])
    a = json.dumps(build_frame(copy.deepcopy(payloads)).to_dict(),
                   sort_keys=True, default=str)
    b = json.dumps(build_frame(copy.deepcopy(payloads)).to_dict(),
                   sort_keys=True, default=str)
    assert a == b


# ------------------------------------------------------------------- narrator
def test_narrator_leads_with_the_anomaly_when_invariants_fail():
    p = tick(sim_time_seconds=105.0, p_generation_mw=30.90,
             p_demand_mw=40.36, p_total_mw=40.36)
    out = nar.narrate(build_frame([tick(), p]))
    assert out["headline"].startswith("Readings do not add up")
    assert out["body"].startswith("The site's own numbers are inconsistent")
    assert "not\n    reliable" in out["body"] or "not reliable" in out["body"]


def test_narrator_never_recommends_an_action():
    for payloads in ([tick(), tick(sim_time_seconds=105.0)],
                     ramp([10.0 + i for i in range(20)])):
        out = nar.narrate(build_frame(payloads))
        text = (out["headline"] + " " + out["body"]).lower()
        for banned in ("should ", "recommend", "you can safely", "must start",
                       "consider "):
            assert banned not in text


def test_every_numeral_the_narrator_writes_is_in_numbers_used():
    out = nar.narrate(build_frame(ramp([10.0 + i * 0.6 for i in range(40)])))
    found = nar._numerals(out["headline"]) | nar._numerals(out["body"])
    assert found == set(out["numbers_used"])


def test_narrator_output_matches_the_model_response_shape():
    """Fallback must not be a different code path from the model path."""
    out = nar.narrate(build_frame([tick(), tick(sim_time_seconds=105.0)]))
    assert set(out) >= {"headline", "body", "numbers_used", "source", "as_of_s"}
    assert out["source"] == "template"
    assert isinstance(out["numbers_used"], list)


def test_narrator_is_present_tense_about_a_stamped_window_not_now():
    ff = build_frame(ramp([10.0, 11.0, 12.0]))
    out = nar.narrate(ff)
    assert out["as_of_s"] is not None


def test_narrator_surfaces_hold_with_unsatisfied_reserve():
    out = nar.narrate(build_frame([tick(), tick(sim_time_seconds=105.0)]))
    assert "Reserve is short of its floor" in out["headline"]


def test_narrator_expands_jargon_rather_than_naming_invariants():
    p = tick(sim_time_seconds=105.0, p_generation_mw=30.90,
             p_demand_mw=40.36, p_total_mw=40.36)
    body = nar.narrate(build_frame([tick(), p]))["body"]
    assert "I1" not in body
    assert "does not match the power coming in" in body


def test_narrator_reports_a_quiet_window_plainly():
    a = tick(sim_time_seconds=100.0)
    b = tick(sim_time_seconds=105.0)
    ff = build_frame([a, b])
    out = nar.narrate(ff)
    assert out["headline"] and out["body"]
    assert "None" not in out["body"]


def test_narrator_is_deterministic():
    payloads = ramp([10.0 + i * 0.4 for i in range(40)])
    a = nar.narrate(build_frame(copy.deepcopy(payloads)))
    b = nar.narrate(build_frame(copy.deepcopy(payloads)))
    assert a == b


def test_narrator_describes_a_staircase_as_steps():
    vals, v = [], 5.0
    for _ in range(8):
        vals += [v] * 7
        v += 0.9
    out = nar.narrate(build_frame(ramp(vals)))
    assert "step" in out["body"]


# -------------------------------- regressions found by reading real narration
def test_trend_subject_is_the_signal_not_its_domain():
    """'generation has been falling to 0.76 fraction' told a non-technical
    reader that generation was failing when the battery was discharging."""
    payloads = [tick(sim_time_seconds=float(i * 5),
                     bess_soc_fraction=0.80 - i * 0.01) for i in range(40)]
    out = nar.narrate(build_frame(payloads))
    assert "battery charge level" in out["body"]
    assert "generation has been falling" not in out["body"]


def test_fraction_units_are_not_spoken_aloud():
    payloads = [tick(sim_time_seconds=float(i * 5),
                     bess_soc_fraction=0.80 - i * 0.01) for i in range(40)]
    assert "fraction" not in nar.narrate(build_frame(payloads))["body"]


def test_named_faults_are_capped_with_a_count_of_the_rest():
    p = tick(sim_time_seconds=105.0, p_generation_mw=30.0, p_demand_mw=40.0,
             p_total_mw=40.0, p_served_mw=1.0, p_compute_served_mw=1.0,
             p_cooling_served_mw=1.0, turbine_output_mw=99.0)
    ff = build_frame([tick(), p])
    body = nar.narrate(ff)["body"]
    assert len(ff.invariants_failed) > nar.MAX_NAMED_FAULTS
    assert "other checks" in body or "other check" in body


def test_equal_demand_and_generation_read_naturally():
    """'drawing 26.48 MW against 26.48 MW of generation' reads as a fault."""
    p = tick(sim_time_seconds=105.0, p_demand_mw=26.48, p_total_mw=26.48,
             p_generation_mw=26.48)
    body = nar.narrate(build_frame([tick(), p]))["body"]
    assert "matched by generation" in body
    assert "against 26.48 MW" not in body
