"""Commit only after durable Phase 4 gates pass; never push or publish."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
P = Path("attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim")
ENV = dict(os.environ, DANGEROUSLY_ALLOW_GIT="1")


def read(name):
    return json.loads((D / name).read_text())


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, env=ENV, text=True).strip()


def commit(message, files):
    git("add", "-f", *files)
    git("commit", "--only", "-m", message, "--", *files)
    return git("rev-parse", "HEAD")


assert read("P1_RESULT.json")["failed"] == 0
assert read("P3_R1_R2_EVALUATION.json")["gate_passed"]
assert read("P3_R4_EVALUATION.json")["passed"]
assert read("P4_EVALUATION.json")["passed"]
assert all(read(f"P3_R3_{s}_reference_check.json")["identical"]
           for s in read("P3_R3_REFERENCE_HASHES.json"))

# No application edits may occur between the measured candidate and commit.
patch = git("diff", "--binary", "ae49aaa", "--", str(P))
expected = (D / "CANDIDATE_DIFF.patch").read_text().strip()
assert patch == expected, "STOP: measured candidate diff changed before commit"

before = read("P5_BEFORE_TRACKING.json")
for item in before:
    path = ROOT / item["file"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256_before"]

head_before = git("rev-parse", "HEAD")
production = [str(P / name) for name in [
    "core/asset_modules.py", "core/dispatch.py", "core/simulation_core.py",
    "runtime/build_warnings.py", "runtime/scenario_factory.py",
]]
tests = [str(P / name) for name in [
    "tests/test_dr_isl_phase4_reserve.py", "tests/test_dr_isl_phase2c.py",
]]
implementation = commit(
    "D2-r + D1-b (IMPL-ISL-2): bridging reserve on the grid-forming BESS; conditional emergency release",
    production,
)
test_commit = commit(
    "D2-r/D1-b: reserve population and release tests; approved TC-ISL-18 max-floor expectation",
    tests,
)
tracking = commit(
    "DR-ISL IMPL-ISL-16: track knowledge, mcp_server init and remaining test file (no content change)",
    [item["file"] for item in before],
)
for item in before:
    path = ROOT / item["file"]
    item["sha256_after"] = hashlib.sha256(path.read_bytes()).hexdigest()
    item["unchanged"] = item["sha256_before"] == item["sha256_after"]
    item["tracked_after"] = bool(git("ls-files", "--", item["file"]))
    assert item["unchanged"] and item["tracked_after"]
(D / "P5_TRACKING.json").write_text(json.dumps({
    "commit": tracking, "files": before, "gridsignal_db_added": False,
}, indent=2) + "\n")

result = {
    "head_before": head_before,
    "automatic_checkpoint_note": (
        "5c8dbf2 preceded this resumption and contains documentation only; "
        "no automatic application checkpoint was treated as a validated implementation"
    ),
    "implementation_commit": implementation,
    "implementation_files": production,
    "test_commit": test_commit,
    "test_files": tests,
    "tracking_commit": tracking,
    "tracking_files": [item["file"] for item in before],
    "application_status_after_commits": git("status", "--short", "--", str(P)),
    "main_source_equals_measured_candidate": (
        git("diff", "--binary", "ae49aaa", "--", str(P / "core"),
            str(P / "runtime"), str(P / "api"))
        == git("diff", "--binary", "ae49aaa", "HEAD", "--", str(P / "core"),
               str(P / "runtime"), str(P / "api"))
    ),
    "no_scenario_content_change": not git("diff", "ae49aaa", "HEAD", "--", str(P / "config/scenarios")),
    "no_publish_deploy_push": True,
}
assert result["main_source_equals_measured_candidate"]
assert result["no_scenario_content_change"]
(D / "P6_COMMITS.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
