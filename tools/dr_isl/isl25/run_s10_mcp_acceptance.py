#!/usr/bin/env python3
"""Run S10 through MCP in-process and save summaries, not tick exports."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = (
    ROOT
    / "attached_assets"
    / "gridsignal_sim_v2_build_package"
    / "gridsignal_sim_v2"
    / "gridsignal_sim"
)
OUTPUT = ROOT / "tools/dr_isl/isl25/S10_MCP_ACCEPTANCE.json"
SCENARIO_ID = "S10_mit_supercloud_2021-08-11"
READ_TOKEN = "isl25-local-read"
RUN_TOKEN = "isl25-local-run"

sys.path.insert(0, str(PACKAGE))
# The app resolves catalogue and fabric fixture paths relative to the package
# root, matching the configured web workflow's working directory.
os.chdir(PACKAGE)
os.environ["GRIDSIGNAL_MCP_READ_TOKEN"] = READ_TOKEN
os.environ["GRIDSIGNAL_MCP_RUN_TOKEN"] = RUN_TOKEN
os.environ["GRIDSIGNAL_MCP_MAX_WORKERS"] = "1"

from fastapi.testclient import TestClient

import mcp_server.server as server
import study_harness.executor as executor_module


def call(client: TestClient, tool: str, arguments: dict, token: str) -> dict:
    response = client.post(
        "/",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": tool,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
    )
    response.raise_for_status()
    return response.json()["result"]["structuredContent"]


def wait_for_completion(client: TestClient, run_id: str) -> dict:
    while True:
        state = call(client, "get_run_status", {"run_id": run_id}, READ_TOKEN)
        if state["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return state
        time.sleep(2)


def compare_demand_inputs(left: list[dict], right: list[dict]) -> dict:
    selected = (
        "p_compute_mw",
        "p_cooling_mw",
        "p_non_gpu_demand_mw",
    )
    result: dict = {
        "tick_count_baseline": len(left),
        "tick_count_informed": len(right),
        "differing_tick_count_by_field": {},
        "missing_tick_count_by_field": {},
    }
    for field in selected:
        result["missing_tick_count_by_field"][field] = sum(
            field not in row for row in left
        ) + sum(field not in row for row in right)
        result["differing_tick_count_by_field"][field] = sum(
            left_row.get(field) != right_row.get(field)
            for left_row, right_row in zip(left, right)
        )
    return result


def seed_manifest_seed_values(manifest: dict) -> dict:
    """Compare deterministic seed selections, not each request's timestamp."""
    return {
        key: value
        for key, value in manifest.items()
        if key != "resolved_at_utc"
    }


def normalize_tick(row: dict) -> dict:
    """Map each path's TickPayload spelling to the D6b comparison field set."""
    def first(*keys):
        for key in keys:
            if key in row:
                return row[key]
        return None

    units = row.get("turbine_units") or []
    return {
        "p_demand_mw": first("p_demand_mw", "p_total_mw"),
        "p_served_mw": first("p_served_mw"),
        "p_unserved_mw": first("p_unserved_mw"),
        "p_generation_mw": first("p_generation_mw"),
        "p_dispatch_curtailed_mw": first("p_dispatch_curtailed_mw"),
        "turbine_output_mw": first("turbine_output_mw"),
        "bess_output_mw": first("bess_output_mw"),
        "bess_soc_fraction": first("bess_soc_fraction"),
        "frequency_hz": first("frequency_hz"),
        "frequency_valid": first("frequency_valid"),
        "p_compute_demand_mw": first("p_compute_demand_mw", "p_compute_mw"),
        "p_cooling_demand_mw": first("p_cooling_demand_mw", "p_cooling_mw"),
        "p_non_gpu_demand_mw": first("p_non_gpu_demand_mw"),
        "turbine_start_count": first("turbine_start_count"),
        "turbine_units": sorted(
            [
                {
                    "asset_id": unit.get("asset_id"),
                    "state": unit.get("state"),
                    "output_mw": unit.get("output_mw"),
                }
                for unit in units
            ],
            key=lambda unit: str(unit["asset_id"]),
        ),
    }


def compare_rest_ticks(mcp_rows: list[dict], rest_rows: list[dict]) -> dict:
    float_fields = (
        "p_demand_mw",
        "p_served_mw",
        "p_unserved_mw",
        "p_generation_mw",
        "p_dispatch_curtailed_mw",
        "turbine_output_mw",
        "bess_output_mw",
        "bess_soc_fraction",
        "frequency_hz",
        "p_compute_demand_mw",
        "p_cooling_demand_mw",
        "p_non_gpu_demand_mw",
    )
    discrete_fields = ("frequency_valid", "turbine_start_count")
    result = {
        "mcp_tick_count": len(mcp_rows),
        "rest_tick_count": len(rest_rows),
        "absolute_tolerance": 0.00005,
        "max_abs_difference_by_field": {field: 0.0 for field in float_fields},
        "exceedance_count_by_field": {field: 0 for field in float_fields},
        "first_exceedance_by_field": {},
        "discrete_mismatch_count_by_field": {
            field: 0 for field in discrete_fields
        },
        "first_discrete_mismatch_by_field": {},
        "missing_discrete_count_by_field": {
            field: 0 for field in discrete_fields
        },
        "unit_mismatch_count": 0,
        "unit_state_mismatch_count": 0,
        "first_unit_state_mismatch": None,
        "max_abs_difference_by_turbine_output_mw": {},
        "unit_output_exceedance_count_by_asset": {},
        "first_unit_output_exceedance_by_asset": {},
        "missing_unit_count": 0,
        "first_unit_mismatch": None,
        "missing_value_count_by_field": {},
    }
    if len(mcp_rows) != len(rest_rows):
        result["tick_count_mismatch"] = True
    numeric_missing: dict[str, int] = {field: 0 for field in float_fields}
    for index, (mcp_raw, rest_raw) in enumerate(zip(mcp_rows, rest_rows)):
        mcp = normalize_tick(mcp_raw)
        rest = normalize_tick(rest_raw)
        for field in float_fields:
            left, right = mcp[field], rest[field]
            if left is None or right is None:
                numeric_missing[field] += 1
                continue
            difference = abs(float(left) - float(right))
            result["max_abs_difference_by_field"][field] = max(
                result["max_abs_difference_by_field"][field], difference
            )
            if difference > result["absolute_tolerance"]:
                result["exceedance_count_by_field"][field] += 1
                result["first_exceedance_by_field"].setdefault(
                    field,
                    {
                        "tick_index": index,
                        "mcp": left,
                        "rest": right,
                        "abs_difference": difference,
                    },
                )
        for field in discrete_fields:
            if mcp[field] is None or rest[field] is None:
                result["missing_discrete_count_by_field"][field] += 1
            if mcp[field] != rest[field]:
                result["discrete_mismatch_count_by_field"][field] += 1
                result["first_discrete_mismatch_by_field"].setdefault(
                    field,
                    {
                        "tick_index": index,
                        "mcp": mcp[field],
                        "rest": rest[field],
                    },
                )
        if len(mcp["turbine_units"]) != len(rest["turbine_units"]):
            mismatch = True
        else:
            mismatch = False
            for left_unit, right_unit in zip(
                mcp["turbine_units"], rest["turbine_units"], strict=True
            ):
                asset_id = str(left_unit["asset_id"])
                result["max_abs_difference_by_turbine_output_mw"].setdefault(
                    asset_id, 0.0
                )
                result["unit_output_exceedance_count_by_asset"].setdefault(
                    asset_id, 0
                )
                if left_unit["output_mw"] is not None and right_unit[
                    "output_mw"
                ] is not None:
                    unit_difference = abs(
                        float(left_unit["output_mw"])
                        - float(right_unit["output_mw"])
                    )
                    result["max_abs_difference_by_turbine_output_mw"][
                        asset_id
                    ] = max(
                        result["max_abs_difference_by_turbine_output_mw"][
                            asset_id
                        ],
                        unit_difference,
                    )
                else:
                    unit_difference = None
                if left_unit["state"] != right_unit["state"]:
                    result["unit_state_mismatch_count"] += 1
                    if result["first_unit_state_mismatch"] is None:
                        result["first_unit_state_mismatch"] = {
                            "tick_index": index,
                            "asset_id": asset_id,
                            "mcp": left_unit["state"],
                            "rest": right_unit["state"],
                        }
                if (
                    unit_difference is not None
                    and unit_difference > result["absolute_tolerance"]
                ):
                    result["unit_output_exceedance_count_by_asset"][
                        asset_id
                    ] += 1
                    result["first_unit_output_exceedance_by_asset"].setdefault(
                        asset_id,
                        {
                            "tick_index": index,
                            "mcp": left_unit["output_mw"],
                            "rest": right_unit["output_mw"],
                            "abs_difference": unit_difference,
                        },
                    )
                if (
                    left_unit["asset_id"] is None
                    or right_unit["asset_id"] is None
                    or left_unit["state"] is None
                    or right_unit["state"] is None
                    or left_unit["asset_id"] != right_unit["asset_id"]
                    or left_unit["state"] != right_unit["state"]
                    or left_unit["output_mw"] is None
                    or right_unit["output_mw"] is None
                    or abs(
                        float(left_unit["output_mw"])
                        - float(right_unit["output_mw"])
                    )
                    > result["absolute_tolerance"]
                ):
                    mismatch = True
                    break
        if not mcp["turbine_units"] or not rest["turbine_units"]:
            result["missing_unit_count"] += 1
        if mismatch:
            result["unit_mismatch_count"] += 1
            if result["first_unit_mismatch"] is None:
                result["first_unit_mismatch"] = {
                    "tick_index": index,
                    "mcp": mcp["turbine_units"],
                    "rest": rest["turbine_units"],
                }
    result["missing_value_count_by_field"] = numeric_missing
    result["passed"] = (
        result["mcp_tick_count"] == 17280
        and result["rest_tick_count"] == 17280
        and not result.get("tick_count_mismatch", False)
        and not any(result["exceedance_count_by_field"].values())
        and not any(result["discrete_mismatch_count_by_field"].values())
        and not any(result["missing_discrete_count_by_field"].values())
        and result["unit_mismatch_count"] == 0
        and result["unit_state_mismatch_count"] == 0
        and not any(
            result["unit_output_exceedance_count_by_asset"].values()
        )
        and result["missing_unit_count"] == 0
        and not any(numeric_missing.values())
    )
    return result


def write_output(value: dict) -> None:
    OUTPUT.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    scenario_path = (
        PACKAGE / "config" / "scenarios" / f"{SCENARIO_ID}.json"
    )
    scenario = json.loads(scenario_path.read_text())
    encoded_profile = json.dumps(
        scenario["non_gpu_load_profile_mw"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    original_compact = executor_module._compact_tick
    captured_rows: list[dict] | None = None

    def observe_tick(tick):
        if captured_rows is not None:
            captured_rows.append(executor_module._tick_result_to_dict(tick))
        return original_compact(tick)

    executor_module._compact_tick = observe_tick
    evidence: dict = {
        "scenario_id": SCENARIO_ID,
        "study_class": "supercloud_replay",
        "operational_not_certified": True,
        "source_events": len(scenario["workload_events"]),
        "non_gpu_profile_points": len(scenario["non_gpu_load_profile_mw"]),
        "non_gpu_profile_sha256": hashlib.sha256(encoded_profile).hexdigest(),
        "runs": {},
    }

    with tempfile.TemporaryDirectory(prefix="isl25-mcp-") as temporary:
        server.DATA_ROOT = Path(temporary)
        service = server.StudyService()
        service._rate_limiter = server.RateLimiter(1000)
        server.service = service
        try:
            with TestClient(server.app) as client:
                listed = call(client, "list_scenarios", {}, READ_TOKEN)
                evidence["listed"] = any(
                    row["scenario_id"] == SCENARIO_ID
                    and row["study_class"] == "supercloud_replay"
                    for row in listed["scenarios"]["items"]
                )
                fetched = call(
                    client, "get_scenario", {"scenario_id": SCENARIO_ID}, READ_TOKEN
                )
                evidence["get_scenario_source"] = fetched["source"]

                for seed in (42, 1729):
                    seed_key = str(seed)
                    evidence["runs"][seed_key] = {}
                    captured_rows_by_mode: dict[str, list[dict]] = {}
                    for mode in ("baseline", "informed"):
                        captured_rows = [] if seed == 42 else None
                        start_time = time.monotonic()
                        started = call(
                            client,
                            "start_run",
                            {
                                "scenario_id": SCENARIO_ID,
                                "mode": mode,
                                "seed": seed,
                                "reuse_cache": False,
                            },
                            RUN_TOKEN,
                        )
                        evidence["runs"][seed_key][mode] = {
                            "run_id": started["run_id"],
                            "status": "RUNNING",
                            "seed": seed,
                            "mode": mode,
                            "started_at_epoch": time.time(),
                        }
                        write_output(evidence)
                        status = wait_for_completion(client, started["run_id"])
                        wall_seconds = time.monotonic() - start_time
                        if status["status"] != "COMPLETED":
                            evidence["runs"][seed_key][mode] = {
                                "status": status["status"],
                                "error": status.get("error"),
                                "wall_seconds": wall_seconds,
                            }
                            write_output(evidence)
                            return 1
                        if captured_rows is not None:
                            captured_rows_by_mode[mode] = captured_rows
                        run_state = service._runs[started["run_id"]]
                        record = run_state.record or {}
                        energy = call(
                            client,
                            "get_run_metrics",
                            {"run_id": started["run_id"], "section": "energy"},
                            READ_TOKEN,
                        )["energy"]
                        evidence["runs"][seed_key][mode] = {
                            "run_id": started["run_id"],
                            "identity_digest": run_state.identity_digest,
                            "physical_identity_sha256": record.get(
                                "physical_identity_sha256"
                            ),
                            "seed_manifest": record.get("seed_manifest"),
                            "status": status["status"],
                            "tick_count": record.get("tick_count"),
                            "wall_seconds": wall_seconds,
                            "study_metrics": {
                                key: record.get(key)
                                for key in (
                                    "demand_mwh",
                                    "served_mwh",
                                    "unserved_mwh",
                                    "peak_unserved_mw",
                                    "dispatch_curtailed_mwh",
                                    "turbine_fuel_mmbtu",
                                    "starts",
                                    "bess_soc_min",
                                    "bess_soc_final",
                                    "stop_floor_refusal_count",
                                    "compute_trace_sha256",
                                    "frequency_feedback_configured",
                                    "protection_configured",
                                    "invalid_frequency_tick_count",
                                    "invalid_frequency_fraction",
                                )
                            },
                            "operating_cost": energy.get("operating_cost"),
                        }
                        evidence["runs"][seed_key][mode]["_run_id"] = started[
                            "run_id"
                        ]
                    compared = call(
                        client,
                        "compare_runs",
                        {
                            "baseline_run_id": evidence["runs"][seed_key][
                                "baseline"
                            ]["_run_id"],
                            "informed_run_id": evidence["runs"][seed_key][
                                "informed"
                            ]["_run_id"],
                        },
                        READ_TOKEN,
                    )
                    evidence["runs"][seed_key]["compare"] = compared
                    for mode in ("baseline", "informed"):
                        evidence["runs"][seed_key][mode].pop("_run_id", None)
                    if seed == 42:
                        demand_inputs = compare_demand_inputs(
                            captured_rows_by_mode["baseline"],
                            captured_rows_by_mode["informed"],
                        )
                        evidence["runs"][seed_key]["shared_probe_inputs"] = (
                            demand_inputs
                        )
                        evidence["runs"][seed_key][
                            "seed_manifests_equal_between_arms"
                        ] = (
                            seed_manifest_seed_values(
                                evidence["runs"][seed_key]["baseline"][
                                    "seed_manifest"
                                ]
                            )
                            == seed_manifest_seed_values(
                                evidence["runs"][seed_key]["informed"][
                                    "seed_manifest"
                                ]
                            )
                        )
                        evidence["runs"][seed_key][
                            "seed_manifests_byte_identical"
                        ] = (
                            evidence["runs"][seed_key]["baseline"][
                                "seed_manifest"
                            ]
                            == evidence["runs"][seed_key]["informed"][
                                "seed_manifest"
                            ]
                        )
                        evidence["runs"][seed_key][
                            "seed_manifest_ignored_metadata_field"
                        ] = "resolved_at_utc"
                        if (
                            demand_inputs["tick_count_baseline"]
                            != demand_inputs["tick_count_informed"]
                            or any(
                            demand_inputs["differing_tick_count_by_field"].values()
                            )
                            or any(
                                demand_inputs["missing_tick_count_by_field"].values()
                            )
                            or not evidence["runs"][seed_key][
                                "seed_manifests_equal_between_arms"
                            ]
                        ):
                            evidence["status"] = "STOP"
                            write_output(evidence)
                            return 1
                        from api.app import app as rest_app

                        rest_started_at = time.monotonic()
                        with TestClient(rest_app) as rest_client:
                            response = rest_client.post(
                                "/runs",
                                json={
                                    "scenario_id": SCENARIO_ID,
                                    "run_seed": 42,
                                    "end_sim_time": 86400.0,
                                    "playback_speed": 0.0,
                                },
                            )
                            response.raise_for_status()
                            rest_run_id = response.json()["run_id"]
                            rest_manager = rest_client.app.state.run_manager
                            while rest_run_id not in rest_manager._completed:
                                time.sleep(2)
                            completed = rest_manager._completed[rest_run_id]
                            rest_rows = completed.tick_dicts
                        rest_parity = compare_rest_ticks(
                            captured_rows_by_mode["baseline"], rest_rows
                        )
                        evidence["runs"][seed_key]["rest_run"] = {
                            "run_id": rest_run_id,
                            "status": "COMPLETED",
                            "wall_seconds": time.monotonic() - rest_started_at,
                            "physical_identity_sha256": getattr(
                                completed,
                                "physical_identity_sha256",
                                None,
                            ),
                        }
                        evidence["runs"][seed_key]["mcp_rest_parity"] = rest_parity
                        write_output(evidence)
                        if not rest_parity["passed"]:
                            evidence["status"] = "STOP"
                            write_output(evidence)
                            return 1
        finally:
            executor_module._compact_tick = original_compact
            service._pool.shutdown(wait=True)

    write_output(evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
