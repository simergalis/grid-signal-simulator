"""Render the Phase 4 report solely from durable completed evidence."""
import json
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]


def load(name):
    return json.loads((D / name).read_text())


def block(value):
    return "```json\n" + json.dumps(value, indent=2, allow_nan=True) + "\n```\n"


def main():
    r4 = load("P3_R4_EVALUATION.json")
    suite = load("P4_EVALUATION.json")
    if not r4["passed"] or not suite["passed"]:
        raise SystemExit("STOP: this completion renderer requires passed R4 and suite gates")
    sections = [
        "# DR-2026-10-20-ISLAND-COLLAPSE — Phase 4 reserve report",
        "",
        "Status: COMPLETE; STOP at end of Phase 4. No Phase 5 work.",
        "Base application: ae49aaab89564ccf2ef42d505e021641484d0d3a.",
        "P = attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim/.",
        "All numerical results below are copied from the named durable evidence files.",
        "",
        "## P1 / design and approved clarifications",
        block(load("APPROVALS.json")),
        "The existing release function and shared unit-interlock helper are unchanged.",
        "The reserve queries the unit helper before an event; it does not require an active contingency.",
        "The shared eligibility predicate and thermal start timing remain authoritative.",
        "The TC-ISL-18 edit changes only the expected maximum of the three floor terms.",
        block(load("P1_UNCHANGED_RELEASE_GUARDS.json")),
        block(load("P1_RESULT.json")),
        "Focused output and JUnit: phase4/P1_FOCUSED.txt and phase4/P1_FOCUSED.xml.",
        "",
        "## P2 / GPU boundary test diagnosis, no GPU code or test changes",
        block(load("P2_CLASSIFICATION.json")),
        "Detailed source evidence and individual outcomes: phase4/P2_REPORT.md,",
        "phase4/P2_SOURCE_PROOF.json and phase4/P2_{base,candidate}_*.results.json.",
        "",
        "## P3 R1 / R2",
        block(load("P3_R1_R2_EVALUATION.json")),
        "Tick numbering in these new evidence files is one-based; timestamps are interval ends.",
        "The first floor-onset window and first discharge-floor window are reported separately:",
        "S10 first crosses the moving floor while charging, not while discharging.",
        "TC-ISL-04 uses first reserve-floor onset because template candidate SoC never reaches zero;",
        "its 0.1 Hz nominal reporting band is PROPOSED_HERE, an audit proxy only.",
        "No frequency/protection constant was changed.",
        "",
        "### Important limitations (not concealed by completion checks)",
        "The unprotected full-run frequency extremes persist in both versions.",
        "Completion and a passing power ledger do not certify frequency fidelity.",
        "S10's runtime floor can exceed its 14 MWh usable capacity (14.9375 MWh peak).",
        "There is no cap or rejection. D9b remains a build-time warning, as approved;",
        "it does not detect a floor increase occurring later in a run.",
        "A below-floor held SoC is not itself an illegal release: the floor is time-varying.",
        "The discharge audit separately checks the presence of an on-bus synchronous machine.",
        "",
        "### Floor-onset details and below-floor accounting",
    ]
    for scenario in ["demo-islanded-ramp", "S10_mit_supercloud_2021-08-11"]:
        pair = load(f"P3_R1_{scenario}_app_1.json")
        details = {}
        for version, run in pair["runs"].items():
            details[version] = {
                k: run[k] for k in [
                    "first_floor", "first_discharge_floor", "below_floor_hold_ticks",
                    "below_floor_discharge_ticks", "illegal_d2r_discharge_count",
                    "first_illegal_d2r_discharge", "frequency_min_time",
                ]
            }
            details[version]["physical_sha256"] = run["summary"]["physical_sha256"]
            details[version]["build_warnings"] = run["summary"]["build_warnings"]
        sections += [f"### {scenario}", block(details)]
    sections += ["## P3 R3 / unchanged historical physical hashes"]
    for scenario in load("P3_R3_REFERENCE_HASHES.json"):
        sections += [block(load(f"P3_R3_{scenario}_reference_check.json"))]
    sections += [
        "## P3 R4 / protected records",
        block(r4),
        "Each pair below used fresh base/candidate runs; no result-cache reuse.",
        "The physical fields, native compact ticks and all 27 metrics are compared exactly.",
        "Complete 27-metric before/after tables follow (one of two identical repetitions per arm).",
    ]
    for scenario in ["scenario-uneven-multisched-01",
                     "scenario-h1-k8s-ray-24h", "scenario-h2-slurm-24h"]:
        for arm in ["baseline", "informed"]:
            pair = load(f"P3_R4_{scenario}_{arm}_1.json")
            before = pair["runs"]["base"]["summary"]
            after = pair["runs"]["candidate"]["summary"]
            sections += [
                f"### {scenario} / {arm}",
                block({
                    "base_physical_sha256": before["physical_sha256"],
                    "candidate_physical_sha256": after["physical_sha256"],
                    "base_compact_sha256": before["record"]["audit_compact_sha256"],
                    "candidate_compact_sha256": after["record"]["audit_compact_sha256"],
                    "before_metrics": before["metrics"],
                    "after_metrics": after["metrics"],
                    "base_final_floor_basis": before["final_floor_basis"],
                    "candidate_final_floor_basis": after["final_floor_basis"],
                    "physical_identical": pair["physical_identical"],
                    "compact_identical": pair["compact_identical"],
                    "metrics_identical": pair["metrics_identical"],
                }),
            ]
    sections += [
        "## P4 / full suite, real package",
        block(suite),
        "JUnit is updated after every test in phase4/P4_FULL_SUITE.incremental.xml.",
        "Final native JUnit: phase4/P4_FULL_SUITE_FINAL.xml.",
        "Full stdout: phase4/P4_FULL_SUITE.txt.",
        "Failing IDs: PHASE_4_FAILING_TESTS.txt and phase4/PHASE_4_FAILING_TESTS.txt.",
        "The comparison reference is HOUSEKEEPING_FAILING_TESTS.txt (15 known failures).",
        "",
        "## P5 / tracking only, no content change",
        block(load("P5_TRACKING.json")),
        "gridsignal.db was not added.",
        "",
        "## Implementation, tests, source ranges, commits and git state",
        block(load("CANDIDATE_CHANGED_LINES.json")),
        "Full literal diff: phase4/CANDIDATE_DIFF.patch.",
        block(load("P6_COMMITS.json")),
        "The report-only commit hash is supplied in the delivery message, not embedded here",
        "(embedding its own hash would be self-referential).",
        "",
        "## Boundaries and durability",
        "No scenario JSON, costs, commitment, eligibility conditions, diesel dispatch,",
        "frequency, protection, or advisory bridge-escalation logic changed.",
        "S10 was run for evidence but its scenario file was not edited.",
        "No publish, deploy, push, or Phase 5 work.",
        "Ticks were streamed to hashes/accumulators; only summaries and bounded windows were saved.",
        "Every retained evidence file is at most 50 MB.",
        "",
        "STOP — end of Phase 4.",
    ]
    text = "\n".join(sections) + "\n"
    (ROOT / "tools/dr_isl/PHASE_4_RESERVE_REPORT.md").write_text(text)
    print("Report bytes:", len(text.encode()))


if __name__ == "__main__":
    main()
