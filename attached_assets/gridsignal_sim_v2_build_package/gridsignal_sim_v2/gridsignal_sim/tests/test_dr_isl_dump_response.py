"""TC-ISL-23–25. D11 finite dump response; no control/physics fixture overrides."""
import inspect
import sys

import core.simulation_core as core
from tests.test_13_3_frequency import _make_islanded_solar_state
from tests.test_forecast_path import _run_tick, _starting_signal

# PROPOSED_HERE: all numeric fixture inputs below are synthetic, chosen to
# isolate a 1 MW solar surplus or an uncovered IT demand, not plant calibration.


def _state(delay=0.5, *, deficit=False):
    state, _ = _make_islanded_solar_state(
        f_nominal=60.0, solar_mw=0.0 if deficit else 1.0,
        turbine_rated_mw=1.0 if deficit else 10.0,
        turbine_ramp=0.001 if deficit else 5.0,
        bess_soc=0.0 if deficit else 1.0,
    )
    state.site.dispatch_curtailment_response_delay_s = delay
    if deficit:
        state.apply_workload_signal(_starting_signal(
            nodes=1000, site_id=state.site.site_id), dt_lead_seconds=0.0)
    return state


def _trace_tick(state, sim_time=0.0):
    """Observe the real integrator; never replace its state or calculations."""
    fn = core.evaluate_tick
    lines, start = inspect.getsourcelines(fn)
    marker = next(i for i, line in enumerate(lines)
                  if "# If _s_base_mva==0 or _h_aggregate==0" in line)
    line_number = start + next(i for i in range(marker + 1, len(lines))
                              if lines[i].strip().startswith("if isinstance("))
    samples = []

    def trace(frame, event, arg):
        if frame.f_code is fn.__code__ and event == "line" and frame.f_lineno == line_number:
            v = frame.f_locals
            samples.append({k: v[k] for k in (
                "_k", "_f", "_f0", "_s_base_mva", "_h_aggregate",
                "_dynamic_frequency_forcing_mw", "_shed_this_tick_mw",
                "_last_integrated_frequency_forcing_mw", "_d_eff", "_dt_sub")})
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        tick = _run_tick(state, sim_time=sim_time, dt=5.0)
    finally:
        sys.settrace(previous)
    return tick, samples


def test_tc_isl_23_finite_surplus_response_and_unchanged_ledger():
    state = _state()
    tick, samples = _trace_tick(state)
    assert len(samples) == 500
    forces = [s["_last_integrated_frequency_forcing_mw"] for s in samples]
    assert all(f > 0 for f in forces[:49])
    assert all(f == 0 for f in forces[49:])
    assert tick.frequency_forcing_mw == 0
    assert tick.frequency_valid and 54.0 <= tick.frequency_hz <= 66.0
    # Pre-D11 ledger: min(delay, outer_dt)/delay * 1 MW = 1 MW.
    assert tick.p_dispatch_curtailed_mw == 1.0
    assert tick.physical_balance.passed
    assert state._dispatch_curtailment_elapsed_s == 0.5
    continued, continuing_samples = _trace_tick(state, sim_time=5.0)
    assert all(s["_last_integrated_frequency_forcing_mw"] == 0
               for s in continuing_samples)
    assert continued.p_dispatch_curtailed_mw == 1.0
    state.solar_arrays[0].override_output_mw(0.0)
    _run_tick(state, sim_time=10.0, dt=5.0)
    assert state._dispatch_curtailment_elapsed_s == 0.0
    state.solar_arrays[0].override_output_mw(1.0)
    restarted, restarting_samples = _trace_tick(state, sim_time=15.0)
    assert restarting_samples[0]["_last_integrated_frequency_forcing_mw"] > 0
    assert restarting_samples[-1]["_last_integrated_frequency_forcing_mw"] == 0
    assert restarted.p_dispatch_curtailed_mw == 1.0


def test_tc_isl_24_deficit_matches_original_swing_trajectory():
    state = _state(deficit=True)
    tick, samples = _trace_tick(state)
    assert len(samples) == 500
    assert tick.frequency_forcing_mw < 0
    expected = 60.0
    for s in samples:
        original_forcing = (
            s["_dynamic_frequency_forcing_mw"] + s["_shed_this_tick_mw"])
        assert original_forcing < 0
        assert s["_last_integrated_frequency_forcing_mw"] == original_forcing
        # Unchanged pre-D11 swing recurrence, using the actual inertial/damping
        # inputs. Exact equality checks the entire 500-substep trajectory.
        derivative = (
            (original_forcing / s["_s_base_mva"]) * s["_f0"]
            - s["_d_eff"] * (expected - s["_f0"])
        ) / (2.0 * s["_h_aggregate"])
        expected += derivative * s["_dt_sub"]
        assert s["_f"] == expected
    assert tick.frequency_hz == expected
    assert tick.p_dispatch_curtailed_mw == 0


def test_tc_isl_25_zero_delay_from_first_substep():
    state = _state(delay=0.0)
    tick, samples = _trace_tick(state)
    assert len(samples) == 500
    assert all(s["_last_integrated_frequency_forcing_mw"] == 0 for s in samples)
    assert tick.frequency_hz == 60.0
    assert tick.frequency_forcing_mw == 0
    assert tick.p_dispatch_curtailed_mw == 1.0
    assert tick.physical_balance.passed
