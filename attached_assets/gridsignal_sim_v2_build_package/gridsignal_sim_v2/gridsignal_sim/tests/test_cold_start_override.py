"""
tests/test_cold_start_override.py — TC-251: cold_start_s scenario override.

TC-251-1  Turbine with cold_start_s=60 in spec reaches SYNCHRONISED within 60 s,
          well before the 900 s global default would have elapsed.

TC-251-2  Turbine whose spec omits cold_start_s retains the 900 s catalogue
          default (backward-compatibility check).

Strategy
--------
The factory pre-synchronises every non-hot-standby turbine at t=0 so the
on-bus fleet is ready when the first tick executes (runtime/scenario_factory.py
lines ~698-700).  Driving the factory-built module through command_start() in
a test would therefore require first resetting it to OFFLINE, which couples the
test to the factory's internal mutation pattern.

Instead each test:
  1. Builds a RunContext from the spec (exercises the factory-wiring path).
  2. Extracts the TurbineConfig from the first turbine (confirms the factory
     wrote cold_start_s into the config correctly).
  3. Constructs a fresh TurbineModule with that config — TurbineModule defaults
     to TurbineState.OFFLINE, so no state manipulation is needed.
  4. Calls command_start() and runs advance() ticks to measure synchronisation
     time.

This isolates the two concerns (factory wiring and state-machine behaviour)
while testing both in a single, self-contained test.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, ".")

from core.models import TurbineState
from core.asset_modules import TurbineModule


# ── shared minimal spec template ─────────────────────────────────────────────

def _make_spec(cold_start_s=None) -> dict:
    """Return a minimal scenario spec with one turbine.

    When cold_start_s is None the key is omitted from the turbine unit dict,
    so the factory falls back to the catalogue default (900 s).
    """
    turbine_unit: dict = {
        "asset_id": "gt-test",
        "rated_mw": 10.0,
        "r_asset_mw_per_s": 0.2,
        "hot_standby": False,
        # Disable min-down enforcement so command_start() is never gated.
        "t_min_down_s": 0.0,
        "min_down_enabled": False,
    }
    if cold_start_s is not None:
        turbine_unit["cold_start_s"] = cold_start_s

    return {
        "name": "tc-251-test",
        "description": "",
        "hardware_profile_id": "hpc-datacenter",
        "dt_lead_seconds": 30,
        "bess_units": [
            {
                "asset_id": "bess-0",
                "rated_mw": 20.0,
                "usable_mwh": 10.0,
                "initial_soc_fraction": 0.9,
                "grid_forming": True,
            }
        ],
        "turbine_units": [turbine_unit],
        "solar_rated_mw": 0.0,
        "irradiance_steps": [],
        "island_mode": True,
        "pue_base": 1.03,
        "run_duration_s": 1200,
        "location": "Auckland",
        "workload_events": [],
        "frequency_nominal_hz": 60.0,
        "power_factor": 0.85,
    }


def _config_from_spec(spec: dict):
    """Build a RunContext from *spec* and return the first turbine's TurbineConfig.

    The factory pre-synchronises every non-hot-standby turbine (lines ~698-700
    of scenario_factory.py) so the returned turbine is already in SYNCHRONISED
    state.  We extract only the config here; callers create a fresh TurbineModule
    to test the state machine independently.
    """
    from runtime.scenario_factory import build_run_context_from_spec
    ctx = build_run_context_from_spec("tc-251-run", spec)
    return ctx.sim_state.turbines[0].config


def _ticks_to_sync(turbine: TurbineModule, dt: float = 10.0) -> float:
    """Drive *turbine* from OFFLINE to SYNCHRONISED via command_start + advance loop.

    Returns the sim_time (seconds) at which the unit reaches SYNCHRONISED.
    Raises AssertionError after 2000 s if SYNCHRONISED is never reached.

    Pre-condition: turbine must be in TurbineState.OFFLINE before calling.
    """
    assert turbine.state == TurbineState.OFFLINE, (
        f"Pre-condition: turbine must start OFFLINE, got {turbine.state}."
    )

    turbine.command_start(0.0)
    assert turbine.state == TurbineState.STARTING, (
        "Pre-condition: command_start() must transition unit to STARTING. "
        f"Actual state: {turbine.state}. "
        "Check min_down_enabled / hot_standby on the config."
    )

    sim_time = 0.0
    max_time = 2000.0
    while sim_time < max_time:
        sim_time += dt
        turbine.advance(sim_time, dt)
        if turbine.state == TurbineState.SYNCHRONISED:
            return sim_time

    raise AssertionError(
        f"Turbine did not reach SYNCHRONISED within {max_time} s. "
        f"Final state: {turbine.state}, _time_to_online_s: {turbine._time_to_online_s}"
    )


# ── TC-251-1: short override is honoured ─────────────────────────────────────

class TestTC251ColdStartOverride:
    """TC-251-1: factory passes cold_start_s from scenario JSON to TurbineConfig."""

    def test_turbine_synchronises_within_scenario_cold_start_duration(self):
        """Turbine with cold_start_s=60 reaches SYNCHRONISED before 900 s elapses.

        The scenario factory is the path under test: it must propagate the per-unit
        cold_start_s value from the scenario JSON to TurbineConfig rather than letting
        the dataclass default (the catalogue value, 900 s) shadow it.

        Test flow:
          1. Build RunContext from spec with cold_start_s=60 (factory-wiring path).
          2. Confirm TurbineConfig.cold_start_s == 60 (factory wrote the override).
          3. Create a fresh TurbineModule in OFFLINE state with that config.
          4. command_start → advance loop → assert SYNCHRONISED within 60 s.
        """
        OVERRIDE_S = 60.0
        GLOBAL_DEFAULT_S = 900.0

        spec = _make_spec(cold_start_s=OVERRIDE_S)
        config = _config_from_spec(spec)

        # Step 1: confirm the factory wired the override into the config.
        assert config.cold_start_s == OVERRIDE_S, (
            f"Factory must set TurbineConfig.cold_start_s to the scenario value "
            f"{OVERRIDE_S} s, not the catalogue default {GLOBAL_DEFAULT_S} s. "
            f"Got: {config.cold_start_s} s."
        )

        # Step 2: fresh OFFLINE module with the factory-wired config.
        turbine = TurbineModule(config=config)
        assert turbine.state == TurbineState.OFFLINE

        sync_time = _ticks_to_sync(turbine, dt=10.0)

        # Assert: synchronised within the overridden window (plus one tick tolerance).
        assert sync_time <= OVERRIDE_S + 10.0, (
            f"TC-251-1 FAIL: turbine with cold_start_s={OVERRIDE_S} s reached "
            f"SYNCHRONISED at t={sync_time} s — must synchronise within "
            f"{OVERRIDE_S + 10.0} s, not at the {GLOBAL_DEFAULT_S} s global default."
        )

        # Assert: synchronised well before the global default would have fired.
        assert sync_time < GLOBAL_DEFAULT_S, (
            f"TC-251-1 FAIL: turbine synchronised at t={sync_time} s, which is "
            f">= the global default ({GLOBAL_DEFAULT_S} s). "
            f"The scenario override cold_start_s={OVERRIDE_S} is being ignored."
        )


# ── TC-251-2: omitting cold_start_s keeps the 900 s catalogue default ────────

class TestTC251DefaultPreserved:
    """TC-251-2: omitting cold_start_s from a scenario turbine unit yields 900 s default."""

    def test_default_cold_start_is_900_seconds_when_not_overridden(self):
        """Turbine spec without cold_start_s keeps the catalogue default of 900 s.

        This is a backward-compatibility guard: existing scenarios that never set
        cold_start_s must not silently get a different duration after the factory
        wiring was introduced.

        Test flow:
          1. Build RunContext from spec with cold_start_s absent (omitted key).
          2. Confirm TurbineConfig.cold_start_s == 900.
          3. Create a fresh TurbineModule in OFFLINE state with that config.
          4. command_start → advance loop → assert SYNCHRONISED near 900 s.
        """
        EXPECTED_DEFAULT_S = 900.0

        spec = _make_spec(cold_start_s=None)   # key absent from turbine unit
        config = _config_from_spec(spec)

        # Step 1: confirm the catalogue default is preserved.
        assert config.cold_start_s == EXPECTED_DEFAULT_S, (
            f"TC-251-2 FAIL: TurbineConfig.cold_start_s is {config.cold_start_s} s "
            f"but the catalogue default is {EXPECTED_DEFAULT_S} s. "
            f"Omitting cold_start_s from a scenario spec must leave the default intact."
        )

        # Step 2: fresh OFFLINE module with the factory-wired config.
        turbine = TurbineModule(config=config)
        assert turbine.state == TurbineState.OFFLINE

        sync_time = _ticks_to_sync(turbine, dt=30.0)

        # Synchronised at or after 900 s (within one-tick tolerance of 30 s).
        assert sync_time >= EXPECTED_DEFAULT_S - 30.0, (
            f"TC-251-2 FAIL: turbine without override reached SYNCHRONISED at "
            f"t={sync_time} s, earlier than the expected {EXPECTED_DEFAULT_S} s default. "
            f"The catalogue default may have changed or is being overridden unexpectedly."
        )
        assert sync_time <= EXPECTED_DEFAULT_S + 30.0, (
            f"TC-251-2 FAIL: turbine took {sync_time} s to synchronise, which exceeds "
            f"{EXPECTED_DEFAULT_S + 30.0} s. Advance loop or default value is wrong."
        )
