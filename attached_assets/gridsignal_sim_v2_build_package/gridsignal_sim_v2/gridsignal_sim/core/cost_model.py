"""
core/cost_model.py — §21.2 workstream-3 cost model for the Scenario Planner.

Answers "what would this run have cost under a different asset mix?"

§21.2 cost attribution
-----------------------
Three cost streams:

1. Grid import           price_per_mwh × energy_imported_mwh

                         DIAG-4 (scope): grid_import_price_per_mwh represents a
                         wholesale/direct-access spot price.  It does NOT include
                         demand charges, TOU adders, or other C&I tariff line items.
                         The system default ($120/MWh) is a CAISO-style wholesale
                         fallback; sites on utility tariffs should supply their
                         all-in energy-charge line item via ScenarioSpec.
                         Tag: WHOLESALE_SPOT_FALLBACK.  See open item DIAG-4 for
                         calibration plan (Option B dual-tariff defaults deferred
                         until PG&E B-20 / SDG&E AL-TOU sheets are sourced).

2. On-site generation    amortised capital + variable O&M.
                         Turbine capacity is typically debt-financed, so the
                         economically relevant question is how often the asset
                         runs against what it costs to own — not the marginal
                         cost of the hour it runs.  This is modelled as:
                           capital_portion = capital_per_mw_year × rated_mw
                                           × (run_hours / 8760)
                           total_gen_cost  = capital_portion + variable_per_mwh
                                           × energy_generated_mwh

                         DIAG-3: turbine $/kWh is a SCENARIO OUTPUT dependent
                         on capacity factor — it is not a fixed input assumption.
                         At the turbine defaults ($45 k/MW·year capital, $55/MWh
                         variable), combined $/kWh by duty cycle:
                           10% duty (bridging/staging):   ~$0.106/kWh
                           15% duty:                      ~$0.089/kWh
                           25% duty:                      ~$0.076/kWh
                           50% duty:                      ~$0.065/kWh
                          100% duty (baseload):           ~$0.060/kWh
                         The old "$0.005–$0.010/kWh" characterisation omitted
                         the $55/MWh variable component entirely and used a
                         50–100% duty range that is not realistic for this
                         deployment profile (bridging/staging ≈ 10–15% duty).

3. Storage round-trip    Charge cost + round-trip loss cost.
                           charge_cost  = charge_mwh × charge_price_per_mwh
                           loss_cost    = charge_mwh × (1 − efficiency)
                                        × discharge_price_per_mwh
                         Note: the usable discharge energy (charge_mwh × eff)
                         offsets grid import and is already captured in
                         grid_import_mwh being lower.

                         DIAG-2: storage_charge_price_per_mwh should track the
                         effective grid_import_price_per_mwh (Path A billing
                         price) unless the operator supplies an explicit BESS
                         charge tariff override.  The flat $60/MWh fallback
                         in _COST_CFG_DEFAULTS is NOT used when an import price
                         override is present; see compute_run_cost_from_completed.

DIAG-5 (scope): solar PV and fuel cell carry zero modelled variable cost and no
capital component in this engine.  Their MWh output reduces grid_import_mwh and
is therefore captured indirectly; their own capital efficiency is out of scope
for this pass.  If solar or fuel cell capital matters for a scenario comparison,
add it as a separate input stream.

Open item PROC-1: SyntheticPriceCurve produces a smooth $25–$85/MWh sine with
no negative-price troughs or scarcity spikes.  Tail-event modeling is deferred;
any implementation must preserve the AT-7 determinism invariant via seeded RNG.

Plane separation: pure computation, no I/O, no SimulationState imports.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CostModelConfig:
    """Cost parameters for one scenario run.  All monetary values are in the
    same currency unit (e.g. GBP or USD); the model does not enforce currency.

    grid_import_price_per_mwh:
        Spot or contract price for grid import energy.

    turbine_capital_per_mw_year:
        Amortised capital cost per MW of rated turbine capacity per year.
        Covers debt service on capex — independent of whether the turbine runs.

    turbine_variable_per_mwh:
        Variable O&M cost per MWh generated (fuel + consumables, if any).

    storage_roundtrip_efficiency:
        Fraction of energy in that comes back out on discharge (0.0–1.0).
        Typical BESS: 0.85–0.92.

    storage_charge_price_per_mwh:
        Cost of the energy used to charge the BESS (typically the import price
        or the on-site generation cost at charge time).

    storage_discharge_price_per_mwh:
        Variable discharge cost per MWh recovered (typically near zero for BESS;
        non-zero for CAES or other conversion-loss systems).
    """

    grid_import_price_per_mwh:    float
    turbine_capital_per_mw_year:  float
    turbine_variable_per_mwh:     float
    storage_roundtrip_efficiency: float
    storage_charge_price_per_mwh: float
    storage_discharge_price_per_mwh: float


# ---------------------------------------------------------------------------
# Run cost breakdown
# ---------------------------------------------------------------------------

@dataclass
class RunCostBreakdown:
    """Cost breakdown for a single run.

    All monetary values are in the same unit as CostModelConfig.
    Energy values are in MWh.

    grid_import_cost:           Grid energy cost.
    generation_cost:            Turbine capital (duty-cycle amortised) + variable.
    storage_cost:               Charge cost + round-trip loss cost.
    total_cost:                 Sum of above.
    generation_duty_fraction:   Fraction of run hours the turbine was generating
                                (energy_mwh / (rated_mw × run_hours)).
    grid_fraction:              Fraction of total served energy from grid import.
    """

    grid_import_cost:          float
    generation_cost:           float
    storage_cost:              float
    total_cost:                float
    generation_duty_fraction:  float
    grid_fraction:             float


# ---------------------------------------------------------------------------
# Scenario comparison result
# ---------------------------------------------------------------------------

@dataclass
class ScenarioComparison:
    """Comparison of two run-cost breakdowns (Scenario Planner what-if).

    cost_delta:         alternative.total_cost − baseline.total_cost.
                        Positive → alternative is more expensive.
    cost_delta_pct:     cost_delta as a percentage of baseline.total_cost.
    grid_fraction_delta: change in the fraction of energy from grid import.
                        Positive → alternative relies more on the grid.
    gen_duty_delta:     change in turbine duty fraction.
    """

    cost_delta:          float
    cost_delta_pct:      float
    grid_fraction_delta: float
    gen_duty_delta:      float


# ---------------------------------------------------------------------------
# Cost model engine
# ---------------------------------------------------------------------------

class CostModelEngine:
    """§21.2 cost engine.

    Usage
    -----
        config  = CostModelConfig(...)
        engine  = CostModelEngine(config)
        result  = engine.compute_run_cost(
                      grid_import_mwh=...,
                      generation_mwh=...,
                      storage_charge_mwh=...,
                      run_duration_hours=...,
                      turbine_rated_mw=...,
                  )
        diff    = engine.compare(baseline_result, alternative_result)
    """

    def __init__(self, config: CostModelConfig) -> None:
        if not (0.0 < config.storage_roundtrip_efficiency <= 1.0):
            raise ValueError(
                f"storage_roundtrip_efficiency must be in (0, 1]; "
                f"got {config.storage_roundtrip_efficiency}"
            )
        self.config = config

    def compute_run_cost(
        self,
        *,
        grid_import_mwh:      float,
        generation_mwh:       float,
        storage_charge_mwh:   float,
        run_duration_hours:   float,
        turbine_rated_mw:     float,
    ) -> RunCostBreakdown:
        """Compute the cost breakdown for one run.

        Parameters
        ----------
        grid_import_mwh:
            Total energy imported from the grid during the run.
        generation_mwh:
            Total energy generated on-site (turbines) during the run.
        storage_charge_mwh:
            Total energy delivered into BESS during the run (gross charge).
        run_duration_hours:
            Duration of the run in hours (for capital amortisation).
        turbine_rated_mw:
            Rated MW of all turbines in this asset mix (for duty fraction calc).
        """
        c = self.config

        # ── Grid import ──────────────────────────────────────────────────
        grid_cost = grid_import_mwh * c.grid_import_price_per_mwh

        # ── On-site generation (§21.2: capital vs duty cycle) ────────────
        # Capital is owed regardless of whether the turbine runs.  The
        # duty fraction tells you how hard the asset is working relative
        # to what it costs to own.
        if run_duration_hours > 0 and turbine_rated_mw > 0:
            duty_fraction = min(
                1.0,
                generation_mwh / (turbine_rated_mw * run_duration_hours),
            )
        else:
            duty_fraction = 0.0
        duty_fraction = max(0.0, duty_fraction)

        capital_portion = (
            c.turbine_capital_per_mw_year
            * turbine_rated_mw
            * (run_duration_hours / 8760.0)
        )
        gen_cost = capital_portion + generation_mwh * c.turbine_variable_per_mwh

        # ── Storage round-trip ────────────────────────────────────────────
        round_trip_loss_mwh = storage_charge_mwh * (1.0 - c.storage_roundtrip_efficiency)
        storage_cost = (
            storage_charge_mwh * c.storage_charge_price_per_mwh
            + round_trip_loss_mwh * c.storage_discharge_price_per_mwh
        )

        # ── Fractions ─────────────────────────────────────────────────────
        total_mwh = grid_import_mwh + generation_mwh
        grid_fraction = (
            grid_import_mwh / total_mwh if total_mwh > 0.0 else 0.0
        )

        total_cost = grid_cost + gen_cost + storage_cost

        return RunCostBreakdown(
            grid_import_cost=round(grid_cost, 4),
            generation_cost=round(gen_cost, 4),
            storage_cost=round(storage_cost, 4),
            total_cost=round(total_cost, 4),
            generation_duty_fraction=round(duty_fraction, 6),
            grid_fraction=round(grid_fraction, 6),
        )

    def compare(
        self,
        baseline:     RunCostBreakdown,
        alternative:  RunCostBreakdown,
    ) -> ScenarioComparison:
        """Compare two runs — Scenario Planner what-if surface.

        Positive cost_delta means the alternative is more expensive.
        """
        cost_delta = alternative.total_cost - baseline.total_cost
        cost_delta_pct = (
            cost_delta / baseline.total_cost * 100.0
            if baseline.total_cost != 0.0 else 0.0
        )
        return ScenarioComparison(
            cost_delta=round(cost_delta, 4),
            cost_delta_pct=round(cost_delta_pct, 4),
            grid_fraction_delta=round(
                alternative.grid_fraction - baseline.grid_fraction, 6
            ),
            gen_duty_delta=round(
                alternative.generation_duty_fraction
                - baseline.generation_duty_fraction,
                6,
            ),
        )
