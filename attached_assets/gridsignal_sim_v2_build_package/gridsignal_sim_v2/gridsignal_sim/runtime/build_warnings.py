"""Build-time diagnostics only; never change reserve floors or dispatch."""
import logging

from core.dispatch import MARGIN_MULTIPLIER

_log = logging.getLogger("gridsignal.scenario_factory")


def reserve_capacity_warnings(state) -> list[dict]:
    """DR D9b: flag the arbitrator's actual floor, without capping/rejecting it."""
    arbitrator = state.arbitrator
    timings = [
        {
            "asset_id": unit.config.asset_id,
            "delta_t_start_s": unit.config.delta_t_start_s,
            "residual_ramp_s": unit.config.residual_ramp_s,
            "start_offset_s": unit.config.start_offset_s,
        }
        for unit in state.diesel_units
    ]
    warnings = []
    for bess in state.bess_units:
        floor = arbitrator.soc_floor_mwh(bess)
        if floor <= bess.config.usable_mwh:
            continue
        # Diagnostic attribution of the existing diesel term, not a second floor.
        diesel_term = (
            MARGIN_MULTIPLIER * bess.config.rated_mw
            * arbitrator.diesel_worst_case_sync_s() / 3600.0
        )
        warning = {
            # PROPOSED_HERE: stable diagnostic code for API/study consumers.
            "code": "bess_reserve_floor_above_usable",
            "bess_id": bess.config.asset_id,
            "floor_mwh": floor,
            "usable_mwh": bess.config.usable_mwh,
            "winning_term": "diesel_floor" if diesel_term >= floor else "depth_reserve",
            "diesel_units": timings,
            "diesel_worst_case_sync_s": arbitrator.diesel_worst_case_sync_s(),
        }
        warnings.append(warning)
        _log.warning("DR D9b build warning: %s", warning)
    return warnings
