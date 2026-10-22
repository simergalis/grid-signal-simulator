"""Real-package full suite, incremental durable XML/IDs and strict set comparison."""
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
P = ROOT / "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim"
# PROPOSED_HERE: leave headroom below the user's 50 MB evidence cap.
LOG_LIMIT = 48_000_000
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
           PYTHONPATH=os.pathsep.join([str(D), str(D.parent / "phase4"),
                                      os.environ.get("PYTHONPATH", "")]))
cmd = [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short",
       "--disable-warnings", "-p", "P5_observer",
       "--p2-output", str(D / "P5_FULL_SUITE"), "--p2-port", "22126",
       "--junitxml=" + str(D / "P5_FULL_SUITE_FINAL.xml")]
(D / "SUITE_STATUS.json").write_text(json.dumps(dict(state="RUNNING", command=cmd, cwd=str(P)), indent=2))
with (D / "P5_FULL_SUITE.txt").open("wb") as log:
    proc = subprocess.Popen(cmd, cwd=P, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    size = 0
    for chunk in iter(lambda: proc.stdout.read(8192), b""):
        size += len(chunk)
        if size > LOG_LIMIT:
            proc.terminate()
            raise RuntimeError("STOP: suite output would exceed evidence cap")
        log.write(chunk)
        log.flush()
    code = proc.wait()
root = ET.parse(D / "P5_FULL_SUITE_FINAL.xml").getroot()
suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
counts = {k: sum(int(s.attrib.get(k, 0)) for s in suites)
          for k in ("tests", "failures", "errors", "skipped")}
counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
actual = set((D / "P5_FAILING_TESTS.incremental.txt").read_text().splitlines())
known = set((D.parent / "PHASE_4_FAILING_TESTS.txt").read_text().splitlines())
result = dict(pytest_exit_code=code, junit_counts=counts, added=sorted(actual-known),
              removed=sorted(known-actual), remaining=sorted(actual & known),
              passed_gate=code in (0, 1) and counts["errors"] == 0 and not (actual-known))
native = (D / "P5_FULL_SUITE.txt").read_text()
result["pytest_summary"] = next(
    (line for line in reversed(native.splitlines()) if re.search(r"\d+ failed, \d+ passed", line)), "")
result["pytest_counts"] = {
    word: int(match.group(1)) if (match := re.search(rf"(\d+) {word}", result["pytest_summary"])) else 0
    for word in ["passed", "failed", "skipped", "xfailed"]
}
rows = json.loads((D / "P5_FULL_SUITE.results.json").read_text()).get("cases", {})
result["gpu_load_profile"] = rows.get("tests/test_gpu_load_profile.py::test_gpu_load_profile")
(D / "SUITE_RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
(D.parent / "PHASE_5_FAILING_TESTS.txt").write_text("".join(n + "\n" for n in sorted(actual)))
print(json.dumps(result, indent=2), flush=True)
raise SystemExit(0 if result["passed_gate"] else 2)
