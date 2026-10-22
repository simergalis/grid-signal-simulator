"""Real-package full suite; bounded log, incremental XML/IDs, durable set diff."""
import json
import re
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
P = ROOT / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
# PROPOSED_HERE: 48 MB leaves space below the user's 50 MB evidence-file cap.
LOG_LIMIT = 48_000_000
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
           PYTHONPATH=str(D) + os.pathsep + os.environ.get("PYTHONPATH", ""))
cmd = [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short",
       "--disable-warnings", "-p", "P4_observer",
       "--p2-output", str(D / "P4_FULL_SUITE"), "--p2-port", "22126",
       "--junitxml=" + str(D / "P4_FULL_SUITE_FINAL.xml")]
(D / "STATUS.json").write_text(json.dumps({"item": "P4", "state": "RUNNING",
                                          "command": cmd, "cwd": str(P)}, indent=2) + "\n")
with (D / "P4_FULL_SUITE.txt").open("wb") as log:
    proc = subprocess.Popen(cmd, cwd=P, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    size = 0
    for chunk in iter(lambda: proc.stdout.read(8192), b""):
        size += len(chunk)
        if size > LOG_LIMIT:
            proc.terminate()
            raise RuntimeError("STOP: suite output would exceed evidence-file cap")
        log.write(chunk)
        log.flush()
    code = proc.wait()

root = ET.parse(D / "P4_FULL_SUITE_FINAL.xml").getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
counts = {k: sum(int(s.attrib.get(k, 0)) for s in suites)
          for k in ("tests", "failures", "errors", "skipped")}
counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
actual = set((D / "P4_FAILING_TESTS.incremental.txt").read_text().splitlines())
known = set((ROOT / "tools/dr_isl/HOUSEKEEPING_FAILING_TESTS.txt").read_text().splitlines())
added, removed, remaining = sorted(actual - known), sorted(known - actual), sorted(actual & known)
gpu = "tests/test_gpu_load_profile.py::test_gpu_load_profile"
waiver = False
if added == [gpu]:
    evidence = json.loads((D / "P2_CLASSIFICATION.json").read_text())
    waiver = (evidence["base_context_results"]["prefix"] == "failed"
              and all(evidence["base_context_results"][f"isolation{i}"] == "passed" for i in [1, 2, 3])
              and evidence["common_preceding_order_identical"])
result = dict(pytest_exit_code=code, counts=counts, added=added, removed=removed,
              remaining=remaining, gpu_waiver_as_IMPL_SSH_07=waiver,
              passed=code in (0, 1) and counts["errors"] == 0 and (not added or waiver))
native_output = (D / "P4_FULL_SUITE.txt").read_text()
native_summary = next(
    line for line in reversed(native_output.splitlines())
    if re.search(r"\d+ failed, \d+ passed", line)
)
result["pytest_summary"] = native_summary
result["counting_note"] = (
    "Native pytest passed excludes subtests; JUnit passed includes passing "
    "subtests and its skipped count includes xfailed cases."
)
data = "".join(node + "\n" for node in sorted(actual))
(D / "PHASE_4_FAILING_TESTS.txt").write_text(data)
(ROOT / "tools/dr_isl/PHASE_4_FAILING_TESTS.txt").write_text(data)
(D / "P4_EVALUATION.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
raise SystemExit(0 if result["passed"] else 2)
