"""Advisory-only forecast readiness planning for block fuel-cell arrays.

This controller deliberately has no command path to ``BlockFuelCellArray``.
Hot-hold fuel consumption is not calibrated, therefore every recommendation is
routed through ``AdvisoryGate`` for review, including high-confidence forecasts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from core.fuel_cell_module import BlockFuelCellArray, FuelCellState
from runtime.advisory_gate import AdvisoryGate, Proposal, make_proposal


@dataclass(frozen=True)
class ReadinessTarget:
    """Derived target counts; these are recommendations, never commands."""

    target_hot_blocks: int
    target_warming_blocks: int
    horizon_s: float
    forecast_peak_mw: float


class BlockFuelCellReadinessController:
    """Translate a forecast into reviewable warm/hold recommendations.

    ``horizon_s`` is never shorter than the array's cold-to-hot path.  The
    controller retains existing hot blocks by default: a lower target is only
    suggested after the configured ``readiness_dwell_s`` has elapsed with a
    lower forecast.  It does not use a hysteresis setting or terminology.
    """

    def __init__(self, gate: AdvisoryGate) -> None:
        self._gate = gate
        self._low_peak_since: dict[str, float] = {}
        self._last_proposal_id: dict[str, str] = {}

    @staticmethod
    def _horizon(array: BlockFuelCellArray) -> float:
        cfg = array.config
        # Include the complete cold/warm path, then hot synchronisation/dwell.
        return max(cfg.cold_start_s, cfg.warm_start_s) + cfg.hot_start_s + cfg.readiness_dwell_s

    def derive_target(
        self, array: BlockFuelCellArray, forecast_mw: Iterable[float]
    ) -> ReadinessTarget:
        peak = max((max(0.0, float(value)) for value in forecast_mw), default=0.0)
        required_ready = min(
            array.config.block_count,
            math.ceil(peak / array.config.effective_block_rated_mw),
        )
        running = sum(b.state == FuelCellState.RUNNING for b in array.blocks)
        hot = sum(b.state == FuelCellState.HOT_STANDBY for b in array.blocks)
        # A hot pool is the non-running part of the peak-ready block target.
        target_hot = max(array.config.hot_standby_floor_blocks, required_ready - running)
        # Warming blocks close the gap between current hot capacity and the
        # retained hot target; warm blocks are explicitly not contingency MW.
        target_warming = max(0, target_hot - hot)
        return ReadinessTarget(target_hot, target_warming, self._horizon(array), peak)

    def evaluate(
        self,
        array: BlockFuelCellArray,
        forecast_mw: Iterable[float],
        *,
        sim_time: float,
        confidence: float,
        degraded: bool = False,
    ) -> Proposal | None:
        """Create one gate-validated pre-staging proposal when review is useful.

        Degraded or low-confidence forecast input creates no autonomous action
        and no block mutation.  A caller may surface its own data-quality alert;
        omitting a proposal avoids presenting spurious precision to reviewers.
        """
        if degraded or not math.isfinite(confidence) or confidence < 0.5:
            return None
        target = self.derive_target(array, forecast_mw)
        hot = sum(b.state == FuelCellState.HOT_STANDBY for b in array.blocks)
        warming = sum(b.state == FuelCellState.WARMING for b in array.blocks)
        delta_blocks = target.target_hot_blocks - hot

        if delta_blocks < 0:
            # Strong retention: only recommend releasing hot blocks after the
            # named readiness dwell, never immediately on a lower forecast.
            since = self._low_peak_since.setdefault(array.asset_id, sim_time)
            if sim_time - since < array.config.readiness_dwell_s:
                return None
        else:
            self._low_peak_since.pop(array.asset_id, None)

        warm_gap = target.target_warming_blocks - warming
        if delta_blocks == 0 and warm_gap == 0:
            return None

        impact_mw = min(
            20.0,
            max(0.1, abs(delta_blocks or warm_gap) * array.config.effective_block_rated_mw),
        )
        action = "warm" if delta_blocks > 0 or warm_gap > 0 else "hold"
        standby_scfm = (
            target.target_hot_blocks
            * array.config.effective_block_rated_mw
            * 1000
            * array.effective_heat_rate_btu_per_kwh
            / array.config.gas_heating_value_btu_per_scf
            / 60
            * array.config.hot_standby_fuel_fraction
        )
        standby_scf = standby_scfm * target.horizon_s / 60.0
        standby_mmbtu = (
            standby_scf
            * array.config.gas_heating_value_btu_per_scf
            / 1_000_000
        )
        monetary_cost = (
            None
            if array.config.gas_price_usd_per_mmbtu is None
            else standby_mmbtu * array.config.gas_price_usd_per_mmbtu
        )
        proposal = make_proposal(
            kind="pre_staging",
            estimated_impact_mw=impact_mw,
            confidence=confidence,
            reasoning=(
                f"fuel_cell_{action}_target: hot={target.target_hot_blocks}; "
                f"warming={target.target_warming_blocks}; peak={target.forecast_peak_mw:.3f}MW; "
                f"horizon={target.horizon_s:.0f}s; low-confidence proposed hot-standby fuel fraction; "
                + (
                    f"estimated standby fuel={standby_mmbtu:.3f} MMBtu; estimated gas cost=${monetary_cost:.2f}"
                    if monetary_cost is not None
                    else "no gas price configured; quantity only"
                )
            ),
            created_at_sim_time=sim_time,
        )
        proposal.requires_confirmation = True
        proposal.fuel_hold_estimate = {
            "target_hot_block_count": target.target_hot_blocks,
            "hold_duration_s": target.horizon_s,
            "horizon_s": target.horizon_s,
            "total_standby_fuel_scf": standby_scf,
            "total_standby_fuel_mmbtu": standby_mmbtu,
            "gas_price_usd_per_mmbtu": array.config.gas_price_usd_per_mmbtu,
            "monetary_cost_usd": monetary_cost,
            "confidence_qualification": "low-confidence: hot_standby_fuel_fraction is proposed",
        }
        if not self._gate.validate(proposal):
            return proposal
        old_id = self._last_proposal_id.get(array.asset_id)
        if old_id:
            self._gate.supersede(old_id)
        self._last_proposal_id[array.asset_id] = proposal.proposal_id
        return proposal