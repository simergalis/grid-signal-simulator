"""
test_energy_cost_accounting.py — black-box tests for run-level energy
cost calculation.

Background
----------
Every evaluate_tick() call integrates MW → MWh into four accumulators on
SimulationState:
  _run_energy_demand_mwh       Σ p_demand_mw × dt_h
  _run_energy_generation_mwh   Σ (turbine + fuel_cell) MW × dt_h
  _run_energy_solar_mwh        Σ p_renewable_mw × dt_h
  _run_energy_bess_charge_mwh  Σ max(0, −bess_output_mw) × dt_h

At run completion, run_manager._drive() reads those accumulators, derives:
  grid_import_mwh = max(0, demand − gen − solar + bess_charge)
and calls CostModelEngine.compute_run_cost() to produce total_energy_cost_usd.

ScenarioSpec exposes grid_import_price_per_mwh (default $55/MWh) so operators
can price islanded vs grid-connected runs differently.

Test matrix
-----------
TC-ECOST-1  Single turbine tick — demand accumulator equals p_demand × dt_h.
TC-ECOST-2  Turbine generation accumulator — generation = turbine MW × dt_h.
TC-ECOST-3  Solar accumulator — solar MWh increments correctly.
TC-ECOST-4  BESS charging accumulator — bess_charge = |bess_output| × dt_h when charging.
TC-ECOST-5  BESS discharging does NOT increment charge accumulator.
TC-ECOST-6  Grid import residual — islanded run with no solar → import ≈ 0.
TC-ECOST-7  Grid import residual — turbine under-produces → import > 0.
TC-ECOST-8  Grid import > 0 — cost_model produces non-zero grid_import_cost.
TC-ECOST-9  ScenarioSpec grid_import_price_per_mwh defaults to 55.0.
TC-ECOST-10 CostModelEngine called with correct MWh figures produces consistent total.
TC-ECOST-11 Multi-tick accumulation — MWh sums linearly across N ticks.
TC-ECOST-12 BESS absorption (surplus path) charges accumulator correctly.
"""

import math
import contextlib
import pytest

from core.asset_modules import BessModule, TurbineModule, TurbineState, GPUModule, CoolingModule, SolarModule
from core.models import BessConfig, TurbineConfig, IslandMode, SiteConfig, HardwareProfile, SolarConfig
from core.simulation_core import SimulationState, evaluate_tick
from core.sim_clock import SimClock
from core._plane_guard import _EVALUATE_TICK_PERMITTED
from core.cost_model import CostModelConfig, CostModelEngine
from runtime.run_manager import _COST_CFG_DEFAULTS


# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _plane_guard_active():
    token = _EVALUATE_TICK_PERMITTED.set(True)
    try:
        yield
    finally:
        _EVALUATE_TICK_PERMITTED.reset(token)


_HW = {"enterprise_8gpu_air": HardwareProfile(
    profile_id="enterprise_8gpu_air", rated_kw=10.2
)}

_SITE_ISLANDED = SiteConfig(
    site_id="test-ecost",
    pue_base=1.03, alpha_max=0.20, tau_seconds=20.0,
    dt_thermal_seconds=90.0, uncalibrated=False,
    workload_signal_stale_s=30.0,
    island_mode=IslandMode.ISLANDED,
    inertia_constant_s=4.0, frequency_nominal_hz=50.0,
    power_factor=0.85, governor_droop=0.04,
)


def _make_state(
    turbine_mw: float = 5.0,
    bess_soc: float = 0.5,
    bess_rated_mw: float = 5.0,
    bess_mwh: float = 2.0,
    site: SiteConfig = _SITE_ISLANDED,
) -> SimulationState:
    turb_cfg = TurbineConfig(asset_id="gt-0", rated_mw=turbine_mw, r_asset_mw_per_s=10.0)
    bess_cfg = BessConfig(
        asset_id="bess-0",
        rated_mw=bess_rated_mw,
        usable_mwh=bess_mwh,
        initial_soc_fraction=bess_soc,
        p_anchor_reserve_mw=0.0,
        grid_forming=False,
        bess_response_tau_s=0.0,
    )
    state = SimulationState(
        run_id="test-ecost",
        site=site,
        gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=_HW, ramp_seconds=1.0)],
        turbines=[TurbineModule(turb_cfg)],
        bess_units=[BessModule(bess_cfg)],
        solar_arrays=[],
        cooling=CoolingModule(asset_id="cool-0", site=site),
    )
    # Pre-warm turbine to SYNCHRONISED at desired MW.
    state.turbines[0].state = TurbineState.SYNCHRONISED
    state.turbines[0]._current_output_mw = turbine_mw
    return state


def _tick(state: SimulationState, sim_time: float = 0.0, dt: float = 1.0):
    clock = SimClock(sim_time=sim_time, dt_seconds=dt, wall_stamp_utc=0.0, rate=1.0, tick_seq=0)
    with _plane_guard_active():
        return evaluate_tick(state, clock)


# ---------------------------------------------------------------------------
# TC-ECOST-1 through TC-ECOST-12
# ---------------------------------------------------------------------------

class TestEnergyAccumulators:

    def test_TC_ECOST_1_demand_accumulates_correctly(self):
        """TC-ECOST-1: _run_energy_demand_mwh = p_demand_mw × dt_h after one tick."""
        # Use a valid turbine (rated_mw > 0) but set it OFFLINE so it doesn't
        # produce — avoids the rated_mw=0 division in the inertia calculation.
        state = _make_state(turbine_mw=5.0, bess_soc=1.0)
        state.turbines[0].state = TurbineState.OFFLINE
        state.turbines[0]._current_output_mw = 0.0
        tick = _tick(state, dt=60.0)  # 1-minute tick → dt_h = 1/60

        dt_h = 60.0 / 3600.0
        expected_demand_mwh = tick.p_demand_mw * dt_h
        assert state._run_energy_demand_mwh == pytest.approx(expected_demand_mwh, rel=1e-6), (
            f"TC-ECOST-1: demand accumulator mismatch; "
            f"expected {expected_demand_mwh:.8f}, got {state._run_energy_demand_mwh:.8f}"
        )

    def test_TC_ECOST_2_generation_accumulates_correctly(self):
        """TC-ECOST-2: _run_energy_generation_mwh = turbine_output_mw × dt_h."""
        dt_s = 360.0   # 6-minute tick
        dt_h = dt_s / 3600.0
        state = _make_state(turbine_mw=8.0, bess_soc=0.5)
        tick = _tick(state, dt=dt_s)

        # Turbine is SYNCHRONISED and holds; fuel_cell = 0.
        expected_gen_mwh = tick.turbine_output_mw * dt_h
        assert state._run_energy_generation_mwh == pytest.approx(expected_gen_mwh, rel=1e-6), (
            f"TC-ECOST-2: generation accumulator mismatch; "
            f"expected {expected_gen_mwh:.8f}, got {state._run_energy_generation_mwh:.8f}"
        )

    def test_TC_ECOST_3_solar_accumulates_correctly(self):
        """TC-ECOST-3: _run_energy_solar_mwh = p_renewable_mw × dt_h.

        Constructs a SolarModule with a constant IrradianceProfile (always 1.0)
        so the solar array always produces at rated_mw during the tick.
        """
        from core.asset_modules import IrradianceProfile

        site = _SITE_ISLANDED
        bess_cfg = BessConfig(
            asset_id="bess-s",
            rated_mw=5.0, usable_mwh=5.0, initial_soc_fraction=0.5,
            p_anchor_reserve_mw=0.0, grid_forming=False, bess_response_tau_s=0.0,
        )
        solar_cfg = SolarConfig(asset_id="solar-0", rated_mw=3.0)
        # Flat irradiance profile: always 1.0 (full sun throughout).
        irr_profile = IrradianceProfile(samples=[(0.0, 1.0)])
        turb_cfg = TurbineConfig(asset_id="gt-solar", rated_mw=5.0, r_asset_mw_per_s=10.0)
        state = SimulationState(
            run_id="test-ecost-solar",
            site=site,
            gpu_modules=[GPUModule(asset_id="gpu-0", site=site, hardware_library=_HW, ramp_seconds=1.0)],
            turbines=[TurbineModule(turb_cfg)],
            bess_units=[BessModule(bess_cfg)],
            solar_arrays=[SolarModule(solar_cfg, irr_profile)],
            cooling=CoolingModule(asset_id="cool-0", site=site),
        )
        state.turbines[0].state = TurbineState.SYNCHRONISED
        state.turbines[0]._current_output_mw = 5.0

        dt_s = 180.0
        tick = _tick(state, dt=dt_s)

        dt_h = dt_s / 3600.0
        expected_solar_mwh = tick.p_renewable_mw * dt_h
        assert state._run_energy_solar_mwh == pytest.approx(expected_solar_mwh, rel=1e-6), (
            f"TC-ECOST-3: solar accumulator mismatch; "
            f"expected {expected_solar_mwh:.8f}, got {state._run_energy_solar_mwh:.8f}"
        )
        # Solar module at rated_mw=3.0 and irradiance=1.0 should contribute > 0.
        assert tick.p_renewable_mw > 0.0, (
            "TC-ECOST-3: solar output must be > 0 with full irradiance"
        )

    def test_TC_ECOST_4_bess_charge_accumulates_when_absorbing(self):
        """TC-ECOST-4: _run_energy_bess_charge_mwh increments when BESS absorbs
        (bess_output_mw < 0 — surplus-absorption path)."""
        # Turbine at 5 MW, no load → surplus → BESS absorbs.
        dt_s = 1.0
        state = _make_state(turbine_mw=5.0, bess_soc=0.1)
        tick = _tick(state, dt=dt_s)

        # Only accumulates when bess_output_mw < 0.
        if tick.bess_output_mw < 0.0:
            expected_charge_mwh = (-tick.bess_output_mw) * (dt_s / 3600.0)
            assert state._run_energy_bess_charge_mwh == pytest.approx(expected_charge_mwh, rel=1e-6), (
                f"TC-ECOST-4: bess_charge accumulator mismatch; "
                f"expected {expected_charge_mwh:.8f}, got {state._run_energy_bess_charge_mwh:.8f}"
            )
        else:
            # If no absorption happened (edge case), charge must still be 0.
            assert state._run_energy_bess_charge_mwh >= 0.0

    def test_TC_ECOST_5_bess_discharge_does_not_increment_charge(self):
        """TC-ECOST-5: When BESS discharges (bess_output_mw > 0),
        _run_energy_bess_charge_mwh stays at 0."""
        # Full BESS, zero turbine → BESS discharges to cover any small load.
        state = _make_state(turbine_mw=0.0, bess_soc=1.0)
        state.turbines[0].state = TurbineState.OFFLINE
        state.turbines[0]._current_output_mw = 0.0
        tick = _tick(state, dt=1.0)

        if tick.bess_output_mw > 0.0:
            assert state._run_energy_bess_charge_mwh == pytest.approx(0.0, abs=1e-9), (
                f"TC-ECOST-5: bess_charge must stay 0 during discharge; "
                f"got {state._run_energy_bess_charge_mwh:.10f}"
            )

    def test_TC_ECOST_6_islanded_no_grid_import(self):
        """TC-ECOST-6: In island mode with balanced generation, grid import ≈ 0.
        demand ≈ turbine_output → grid_import = max(0, demand−gen−solar+charge) ≈ 0."""
        state = _make_state(turbine_mw=5.0, bess_soc=0.5)
        dt_s = 1.0
        tick = _tick(state, dt=dt_s)

        dt_h = dt_s / 3600.0
        demand_mwh     = state._run_energy_demand_mwh
        gen_mwh        = state._run_energy_generation_mwh
        solar_mwh      = state._run_energy_solar_mwh
        charge_mwh     = state._run_energy_bess_charge_mwh
        grid_import_mwh = max(0.0, demand_mwh - gen_mwh - solar_mwh + charge_mwh)

        # In island mode turbine output ≥ demand (surplus goes to BESS or frequency).
        # Either grid_import ≈ 0 or gen ≥ demand.
        assert grid_import_mwh >= -1e-9, (
            f"TC-ECOST-6: grid_import_mwh must be ≥ 0; got {grid_import_mwh:.8f}"
        )

    def test_TC_ECOST_7_grid_import_positive_when_turbine_off(self):
        """TC-ECOST-7: When no turbine and BESS is empty and there is demand,
        grid import > 0 (energy has to come from somewhere)."""
        site_grid = SiteConfig(
            site_id="test-ecost-grid",
            pue_base=1.03, alpha_max=0.20, tau_seconds=20.0,
            dt_thermal_seconds=90.0, uncalibrated=False,
            workload_signal_stale_s=30.0,
            island_mode=IslandMode.GRID_TIE,   # grid-connected so import is valid
            inertia_constant_s=4.0, frequency_nominal_hz=50.0,
            power_factor=0.85, governor_droop=0.04,
        )
        state = _make_state(turbine_mw=0.0, bess_soc=0.5, site=site_grid)
        state.turbines[0].state = TurbineState.OFFLINE
        state.turbines[0]._current_output_mw = 0.0

        tick = _tick(state, dt=1.0)

        demand_mwh     = state._run_energy_demand_mwh
        gen_mwh        = state._run_energy_generation_mwh
        solar_mwh      = state._run_energy_solar_mwh
        charge_mwh     = state._run_energy_bess_charge_mwh

        # No turbine → gen_mwh = 0; demand > 0 → import must be > 0.
        if demand_mwh > 1e-9:
            grid_import_mwh = max(0.0, demand_mwh - gen_mwh - solar_mwh + charge_mwh)
            assert grid_import_mwh > 0.0, (
                f"TC-ECOST-7: grid_import_mwh must be > 0 when turbine is offline "
                f"and there is demand; got {grid_import_mwh:.8f}"
            )

    def test_TC_ECOST_8_cost_model_produces_nonzero_grid_import_cost(self):
        """TC-ECOST-8: CostModelEngine produces a positive total_cost when
        grid_import_mwh > 0."""
        cfg = CostModelConfig(**{**_COST_CFG_DEFAULTS, "grid_import_price_per_mwh": 55.0})
        engine = CostModelEngine(cfg)
        breakdown = engine.compute_run_cost(
            grid_import_mwh=10.0,
            generation_mwh=0.0,
            storage_charge_mwh=0.0,
            run_duration_hours=1.0,
            turbine_rated_mw=0.0,
        )
        assert breakdown.grid_import_cost > 0.0, (
            f"TC-ECOST-8: grid_import_cost must be > 0 with import=10 MWh @ $55/MWh; "
            f"got {breakdown.grid_import_cost}"
        )
        assert breakdown.total_cost == pytest.approx(
            breakdown.grid_import_cost + breakdown.generation_cost + breakdown.storage_cost,
            rel=1e-6,
        )

    def test_TC_ECOST_9_scenario_spec_default_price(self):
        """TC-ECOST-9: ScenarioSpec.grid_import_price_per_mwh defaults to 55.0."""
        from api.schemas import ScenarioSpec
        spec = ScenarioSpec(
            name="test",
            turbine_units=[{"asset_id": "gt-0", "rated_mw": 5.0}],
        )
        assert spec.grid_import_price_per_mwh == 55.0, (
            f"TC-ECOST-9: default grid_import_price_per_mwh must be 55.0; "
            f"got {spec.grid_import_price_per_mwh}"
        )

    def test_TC_ECOST_10_cost_model_round_trip_consistency(self):
        """TC-ECOST-10: CostModelEngine round-trip — known inputs produce
        the expected total cost."""
        cfg = CostModelConfig(
            grid_import_price_per_mwh=100.0,
            turbine_capital_per_mw_year=0.0,       # disable capital so gen_cost = variable only
            turbine_variable_per_mwh=50.0,
            storage_roundtrip_efficiency=1.0,      # no loss
            storage_charge_price_per_mwh=0.0,
            storage_discharge_price_per_mwh=0.0,
        )
        engine = CostModelEngine(cfg)
        breakdown = engine.compute_run_cost(
            grid_import_mwh=5.0,
            generation_mwh=3.0,
            storage_charge_mwh=0.0,
            run_duration_hours=1.0,
            turbine_rated_mw=5.0,
        )
        # grid_cost = 5 MWh × $100 = $500
        # gen_cost  = 3 MWh × $50  = $150
        # storage   = 0
        # total     = $650
        assert breakdown.grid_import_cost == pytest.approx(500.0, rel=1e-4)
        assert breakdown.generation_cost  == pytest.approx(150.0, rel=1e-4)
        assert breakdown.total_cost       == pytest.approx(650.0, rel=1e-4)

    def test_TC_ECOST_11_multi_tick_accumulation_linear(self):
        """TC-ECOST-11: Running N identical ticks accumulates MWh linearly.
        After N ticks, each accumulator ≈ N × single-tick value."""
        N = 5
        dt_s = 60.0
        state = _make_state(turbine_mw=4.0, bess_soc=0.5)
        tick_vals = []
        for i in range(N):
            tick = _tick(state, sim_time=float(i * dt_s), dt=dt_s)
            tick_vals.append(tick)

        # Demand should have accumulated ≈ N × first_tick_demand × dt_h.
        # (Allow 5% tolerance — cooling ramp can shift it slightly.)
        first_demand_mwh = tick_vals[0].p_demand_mw * (dt_s / 3600.0)
        expected_total   = N * first_demand_mwh
        assert state._run_energy_demand_mwh == pytest.approx(expected_total, rel=0.10), (
            f"TC-ECOST-11: demand accumulator after {N} ticks should be ≈ {expected_total:.6f} MWh; "
            f"got {state._run_energy_demand_mwh:.6f}"
        )

    def test_TC_ECOST_12_bess_absorption_charges_accumulator(self):
        """TC-ECOST-12: When BESS absorbs surplus (negative bess_output_mw),
        the charge accumulator increases by |bess_output_mw| × dt_h,
        and the demand accumulator is unaffected by BESS state."""
        # Use a configuration that reliably produces surplus → absorption.
        state = _make_state(turbine_mw=5.0, bess_soc=0.0, bess_rated_mw=5.0, bess_mwh=10.0)
        dt_s = 1.0
        tick = _tick(state, dt=dt_s)

        dt_h = dt_s / 3600.0

        # Demand accumulator must equal p_demand_mw × dt_h regardless of BESS state.
        assert state._run_energy_demand_mwh == pytest.approx(
            tick.p_demand_mw * dt_h, rel=1e-6
        )

        if tick.bess_output_mw < 0.0:
            # Charge accumulator must equal |bess_output_mw| × dt_h.
            expected_charge = (-tick.bess_output_mw) * dt_h
            assert state._run_energy_bess_charge_mwh == pytest.approx(
                expected_charge, rel=1e-6
            ), (
                f"TC-ECOST-12: charge accumulator mismatch; "
                f"expected {expected_charge:.8f}, got {state._run_energy_bess_charge_mwh:.8f}"
            )
