"""Synthetic tick payloads.

These are constructed to exercise the checkers, not to imitate the real system.
Where a real recording disagrees with a fixture, the recording is right.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from nar001.checkers import TickCtx


def tick(**over: Any) -> dict[str, Any]:
    """A balanced islanded tick.

    Self-consistent by construction: two consecutive copies satisfy every
    invariant, so any residual a test sees comes from what that test changed.
    """
    base: dict[str, Any] = {
        "sim_time_seconds": 100.0,
        "p_compute_demand_mw": 8.0,
        "p_cooling_demand_mw": 2.0,
        "p_demand_mw": 10.0,
        "p_compute_mw": 8.0,          # wire alias, same value
        "p_cooling_mw": 2.0,
        "p_total_mw": 10.0,
        "net_demand_mw": 7.0,
        "p_generation_mw": 10.0,
        "grid_exchange_mw": 0.0,
        "d4_balance_defect_mw": 0.0,
        "frequency_forcing_mw": 0.0,
        "asset_delivery_error_mw": 0.0,
        "turbine_output_mw": 6.0,
        # BESS idle and solar carrying the balance: with a constant state of
        # charge, any non-zero BESS power makes two consecutive identical ticks
        # physically inconsistent, and I5 correctly flags it. The original
        # fixture had 1.0 MW here and was caught by the checker.
        "bess_output_mw": 0.0,
        "p_renewable_mw": 4.0,
        "p_served_mw": 10.0,
        "p_unserved_mw": 0.0,
        "p_compute_served_mw": 8.0,
        "p_compute_unserved_mw": 0.0,
        "p_cooling_served_mw": 2.0,
        "p_cooling_unserved_mw": 0.0,
        "bess_soc_fraction": 0.50,
        "bess_usable_mwh": 8.0,
        "bess_rated_mw": 15.0,
        "rated_cooling_mw": 4.0,
        "kube_metrics": None,
        "turbine_units": [
            {"unit_id": "turbine-0", "state": "synchronised", "output_mw": 6.0,
             "rated_mw": 7.0, "hot_standby": False},
            {"unit_id": "turbine-1", "state": "offline", "output_mw": 0.0,
             "rated_mw": 7.0, "hot_standby": False},
        ],
        "commitment_block": {
            "action": "hold",
            "committed_rated_mw": 7.0,
            "reserve_floor_mw": 17.0,      # p_demand_mw (10) + largest on-bus (7)
            "reserve_satisfied": False,    # 7.0 < 17.0 -> floor violated
            "utilisation": 0.8,
        },
    }
    base.update(over)
    return base


def ctx(payload: dict[str, Any] | None = None, prev: TickCtx | None = None,
        seq: int = 0, run_id: str = "run-test") -> TickCtx:
    return TickCtx(run_id=run_id, seq=seq, payload=payload or tick(), prev=prev)


def chain(payloads: list[dict[str, Any]], run_id: str = "run-test") -> list[TickCtx]:
    out: list[TickCtx] = []
    prev = None
    for i, p in enumerate(payloads):
        c = TickCtx(run_id=run_id, seq=i, payload=p, prev=prev)
        out.append(c)
        prev = c
    return out


def deep_without(payload: dict[str, Any], path: str) -> dict[str, Any]:
    """Copy with a dotted path removed (top-level or one level of nesting)."""
    p = copy.deepcopy(payload)
    parts = path.split(".")
    cur = p
    for seg in parts[:-1]:
        cur = cur[seg]
    cur.pop(parts[-1], None)
    return p


def deep_set(payload: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    p = copy.deepcopy(payload)
    parts = path.split(".")
    cur = p
    for seg in parts[:-1]:
        cur = cur[seg]
    cur[parts[-1]] = value
    return p


def write_jsonl(path, payloads: list[dict[str, Any]], *, events=None,
                sentinel: bool = True) -> None:
    with open(path, "w") as fh:
        for i, p in enumerate(payloads):
            fh.write(json.dumps({"seq": i, "received_wall_utc": "2026-08-09T00:00:00Z",
                                 "payload": p}) + "\n")
        for e in events or []:
            fh.write(json.dumps(e) + "\n")
        if sentinel:
            fh.write(json.dumps({"seq": len(payloads),
                                 "received_wall_utc": "2026-08-09T00:00:01Z",
                                 "payload": {"type": "run_complete",
                                             "run_id": "run-test"}}) + "\n")
