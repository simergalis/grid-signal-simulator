"""SP-6 persistence tests across an actual Python process boundary."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


CSV = """site_id,date,time,mw_measured,measurement_source,kubernetes_node_count,kubernetes_request_rate,slurm_node_count,slurm_request_rate,ray_node_count,ray_request_rate
equinix-sj-2,2026-08-23,00:00:00,1.383,utility_meter,99,128.7,0,,0,
equinix-sj-2,2026-08-23,01:00:00,5.364,utility_meter,285,370.5,0,,25,
equinix-sj-2,2026-08-23,18:00:00,16.307,utility_meter,530,689.0,464,,14,
"""

_WRITE_SCRIPT = "CSV = " + repr(CSV) + r"""
import asyncio, json
from types import SimpleNamespace
from api.routes import trace_import, trace_comparison

class Request:
    def __init__(self, body=b""):
        self.app = SimpleNamespace(state=SimpleNamespace(scenario_store=None))
        self._body = body
        self.query_params = {}
        self.headers = {"content-length": str(len(body))}
    async def body(self):
        return self._body
    async def json(self):
        return json.loads(self._body)

async def main():
    imported = await trace_import.import_trace(Request(CSV.encode()))
    comparison = await trace_comparison.compare_trace(
        imported["import_id"], Request(b"{}")
    )
    print(json.dumps({
        "import_id": imported["import_id"],
        "comparison_id": comparison["comparison_id"],
        "import": imported,
        "comparison": comparison,
    }, separators=(",", ":")))

asyncio.run(main())
"""

_READ_SCRIPT = r"""
import asyncio, json, sys
from types import SimpleNamespace
from api.routes import trace_import, trace_comparison

class Request:
    def __init__(self):
        self.app = SimpleNamespace(state=SimpleNamespace())

async def main():
    imported = await trace_import.get_imported_trace(sys.argv[1], Request())
    comparison = await trace_comparison.get_trace_comparison(sys.argv[2], Request())
    print(json.dumps({"import": imported, "comparison": comparison}, separators=(",", ":")))

asyncio.run(main())
"""


def _run_in_fresh_process(script: str, db_path: Path, *args: str) -> dict:
    env = os.environ.copy()
    env["GRIDSIGNAL_DB"] = str(db_path)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_import_and_comparison_survive_a_real_process_restart():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "trace-restart.db"

        created = _run_in_fresh_process(_WRITE_SCRIPT, db_path)
        # The writer process has exited here. The reader is a new interpreter,
        # with fresh module state and a newly-created SQLAlchemy engine.
        restored = _run_in_fresh_process(
            _READ_SCRIPT,
            db_path,
            created["import_id"],
            created["comparison_id"],
        )

    assert restored["import"] == created["import"]
    assert restored["comparison"] == created["comparison"]
    assert json.dumps(
        restored["import"], separators=(",", ":"), allow_nan=False
    ) == json.dumps(created["import"], separators=(",", ":"), allow_nan=False)
    assert json.dumps(
        restored["comparison"], separators=(",", ":"), allow_nan=False
    ) == json.dumps(created["comparison"], separators=(",", ":"), allow_nan=False)
    assert restored["import"]["quarantined"][0]["reason"] == (
        "ray_node_count exceeds configured maximum 21 racks"
    )
    assert restored["import"]["site_capacity_validation"]["status"] == "validated"
    assert restored["import"]["site_capacity_validation"]["configured_domains"] == [
        "kubernetes",
        "ray",
        "slurm",
    ]
    assert restored["comparison"]["pas"]["reserve_series"]
    assert restored["comparison"]["pas"]["confidence_note"]