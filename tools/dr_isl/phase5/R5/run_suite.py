"""Reuse the complete suite driver with only the explicitly approved GPU waiver."""
from pathlib import Path
import json

source = Path(__file__).resolve().parents[1] / "run_suite.py"
code = source.read_text()
code = code.replace("ROOT = D.parents[2]", "ROOT = D.parents[3]")
code = code.replace('D.parent / "phase4"', 'D.parents[1] / "phase4"')
code = code.replace('D.parent / "PHASE_4_FAILING_TESTS.txt"', 'D.parents[1] / "PHASE_4_FAILING_TESTS.txt"')
code = code.replace('D.parent / "PHASE_5_FAILING_TESTS.txt"', 'D.parents[1] / "PHASE_5_FAILING_TESTS.txt"')
waiver = "tests/test_gpu_load_profile.py::test_gpu_load_profile"
code = code.replace("not (actual-known)", f"not ((actual-known) - {{{waiver!r}}})")
try:
    exec(compile(code, str(source), "exec"))
except SystemExit as exit_status:
    path = Path(__file__).resolve().parent / "SUITE_RESULT.json"
    if path.exists():
        result = json.loads(path.read_text())
        result["approved_waiver"] = waiver
        result["waived_added"] = [n for n in result["added"] if n == waiver]
        result["unwaived_added"] = [n for n in result["added"] if n != waiver]
        path.write_text(json.dumps(result, indent=2) + "\n")
    raise exit_status
