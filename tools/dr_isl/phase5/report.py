"""Generate the literal Phase 5 report from durable evidence, not recalled values."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

D = Path(__file__).resolve().parent
ROOT = D.parents[2]


def load(name):
    return json.loads((D / name).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


results = load("V1_V2_PROGRESS.json")
stop = load("STOP_RESULT.json") if (D / "STOP_RESULT.json").exists() else None
text = [
    "# DR-2026-10-20-ISLAND-COLLAPSE — Phase 5 / D3 (IMPL-ISL-3)",
    "",
    "Base: fd87fc75b995f19556f598cdc5b0f443a4edce75.",
    "Evidence directory: tools/dr_isl/phase5/. No scenario JSON or physical control changes.",
    "",
    "## 5.1–5.4 Candidate implementation (not active; stashed after the STOP)" if stop else "## 5.1–5.4 Implementation",
    "- core/frequency_reporting.py contains the reporting band and one resolved-protection predicate.",
    "- TickResult flags are stamped together at final evaluate_tick construction. No frequency assignment/clamp was added.",
    "- runtime/run_manager.py carries both flags in the existing serializer used by WebSocket/REST.",
    "- runtime/persistence.py::_tick_to_json uses dataclasses.asdict: both flags persist in complete tick_json; no table migration.",
    "- ScenarioSpec logs a non-rejecting warning. Factory-resolved SiteConfig produces the same structured build warning in metadata and the existing run-start response.",
    "- protection_configured means ANY specified UF/OF/UFLS/81U threshold, including advisory thresholds; it does not claim complete trip coverage. Delays alone do not enable it.",
    "- Frontend Forecast Quality greys invalid current-frequency readings and shows the exact requested explanation. Opening/inner layouts show the unprotected-island notice.",
    "- New payload flags are optional in TypeScript only for legacy saved payloads; every newly produced tick includes both.",
    "- MetricsCollector adds three metrics. Identity-only frequency_reporting_metrics_version=1 resets old caches. compare_runs conditions are not edited.",
    "",
    "## 5.5 Focused tests",
    "TC-ISL-07a–g already names staging-event tests. TC-ISL-08a–d is used here.",
    "TC-ISL-18 initially counted ALL build warnings: failures 2 vs 1 and 1 vs 0 after the additive D3 warning.",
    "Its warning list now selects the D9b reserve-warning code only; every existing floor/dispatch assertion is retained. TC-ISL-08d independently asserts D3.",
    "Initial output: phase5/FOCUSED_ATTEMPT1.txt/XML. Final output: phase5/FOCUSED.txt/XML.",
    "",
    "```text",
    (D / "FOCUSED.txt").read_text().strip(),
    "```",
    "Frontend focused output: phase5/UI_TESTS.txt; build/type-check output: phase5/UI_BUILD.txt.",
    "",
    "## 5.6 V1/V2: raw physical fields, hashes and validity",
    "Pinned seeder-path app runs / native study probe and arm configuration reuse tools/dr_isl/baseline_runner.py unchanged.",
    "Pinning and output-only hooks are inherited from phase4/stream_worker.py. No full per-tick disk exports.",
    "Hash contract: compact sorted-key JSON + LF per raw tick; the four established nonphysical exclusions are retained; ONLY the two new reporting flags are additionally excluded.",
    "Established nonphysical exclusions: advisory_telemetry, fabric_modal, wall_stamp_utc, insufficient_reserve_proposal_id.",
    "Compact study rows are also compared with only those two new keys removed. Every old study metric is compared recursively.",
    "",
    "| Scenario / arm | ticks | protection configured | invalid ticks / fraction | first invalid: tick; time; Hz | min / max Hz | physical hash |",
    "|---|---:|---|---|---|---|---|",
]
if stop:
    text[5:5] = [
        "## STOP — Phase 5 is not finished",
        "5.7 failed its zero-added-failure gate. No implementation/UI/test commits were made.",
        "The GPU failure is pre-existing sampling sensitivity, but Phase 5 provided no waiver.",
        "The already-failing API-static test also reports a new candidate-only core import; it is not fixed here.",
        "Main application code is restored to fd87fc7; all 15 candidate files are verified in the stash.",
        "```json", json.dumps(stop, indent=2), "```", "",
    ]
identities = []
details = []
for r in results:
    full = load(f'{r["scenario"]}_{r["arm"]}.json')
    before, after = [full["summaries"][v] for v in ["base", "candidate"]]
    text.append(
        f'| {r["scenario"]} / {r["arm"]} | {r["ticks"]} | {r["protection_configured"]} | '
        f'{r["invalid_frequency_tick_count"]} / {r["invalid_frequency_fraction"]!r} | '
        f'{json.dumps(r["first_invalid_tick"])} | {r["frequency_min"]!r} / {r["frequency_max"]!r} | '
        f'{after["physical_sha256"]} |')
    if r["arm"] != "app":
        old, new = [copy.deepcopy(s["record"]["identity"]) for s in [before, after]]
        # Isolate the metrics-version reset from audit worker provenance labels.
        new["engine_commit"] = old["engine_commit"]
        new["harness_commit"] = old["harness_commit"]
        without = copy.deepcopy(new)
        version = without["parameter_set"].pop("frequency_reporting_metrics_version")
        assert without == old
        identities.append(dict(scenario=r["scenario"], arm=r["arm"], old=digest(old),
                               new=digest(new), reporting_version=version,
                               fixed_engine_commit=old["engine_commit"],
                               fixed_harness_commit=old["harness_commit"]))
    details.extend([
        "",
        f'### {r["scenario"]} / {r["arm"]}: comparison',
        "```json",
        json.dumps({k: full.get(k) for k in [
            "passed", "first_difference", "physical_identical", "existing_metrics_count",
            "existing_metric_differences", "compact_identical_excluding_new_flags", "added_metrics",
        ]}, indent=2),
        "```",
        f'Evidence: tools/dr_isl/phase5/{r["scenario"]}_{r["arm"]}.json (both complete 27-metric tables and run records).',
    ])
text.extend(details)
text += [
    "",
    "### Published/certified records explicitly flagged",
    "The base-demo published record and H1/H2 reference records contain invalid-frequency ticks wherever their table count is nonzero.",
    "These are pre-existing trajectories, not newly altered frequency. A compare_runs PASS is NOT a frequency-validity certificate.",
    "OPEN-ISL-3 remains deferred: no acceptance/trip rule was added.",
    "",
    "### Metric identity cache reset (provenance fixed for the version-only comparison)",
    "```json", json.dumps(identities, indent=2), "```",
    "",
    "### V3: compare_runs unchanged",
    "```json", json.dumps(load("V3_COMPARE_RUNS.json"), indent=2), "```",
]
(D / "METRIC_IDENTITY_MAP.json").write_text(json.dumps(identities, indent=2) + "\n")
if (D / "SUITE_RESULT.json").exists():
    text += ["", "## 5.7 Full suite", "```json",
             json.dumps(load("SUITE_RESULT.json"), indent=2), "```",
             "Native pytest summary (JUnit includes passing subtests and groups xfails with skipped):",
             "```text",
             "\n".join((D / "P5_FULL_SUITE.txt").read_text().splitlines()[-20:]),
             "```",
             "Failing IDs: tools/dr_isl/PHASE_5_FAILING_TESTS.txt.",
             "Incremental JUnit: tools/dr_isl/phase5/P5_FULL_SUITE.incremental.xml.",
             "Final JUnit: tools/dr_isl/phase5/P5_FULL_SUITE_FINAL.xml."]
if (D / "COMMITS.json").exists():
    text += ["", "## 5.8 Local commits", "```json", json.dumps(load("COMMITS.json"), indent=2), "```"]
if (D / "SERVING.json").exists():
    text += ["", "### Dev serving check", "```json", json.dumps(load("SERVING.json"), indent=2), "```"]
if stop:
    classification = load("P2_CLASSIFICATION.json")
    text += ["", "### GPU classification using the Phase 4 P2 protocol",
             classification["classification"], classification["explanation"],
             classification["shared_state"], classification["fix_direction"],
             "| version | context | outcome |", "|---|---|---|"]
    for c in classification["contexts"]:
        text.append(f'| {c["version"]} | {c["context"]} | {c["gpu_result"]["outcome"]} |')
    text += ["Source snippets and every literal assertion: phase5/P2_CLASSIFICATION.json.",
             "Both prefix runs use the same common preceding order; candidate adds only its 14 new cases.",
             "", "### Additional violation inside the known API-static failure",
             "```json", json.dumps(load("ARCHITECTURE_SIGNATURE_DELTA.json"), indent=2), "```",
             "", "### Restoration limitation: previously ignored frontend source",
             json.dumps(load("UI_RESTORATION_NOTE.json"), indent=2),
             "The three files were restored by reversing only D3 edits, not by claiming a nonexistent fd87fc7 Git copy.",
             "Candidate and restored copies, plus the exact reversal, are preserved in phase5/UI_*.",
             "The restored frontend builds successfully. The screenshot is the signed-out base app, not a verification of candidate UI.",
             "", "### Candidate paths and line counts (refer to the stash, NOT active source)",
             "```json", json.dumps(load("CANDIDATE_FILES.json"), indent=2), "```"]
text += ["", "### Literal stashed candidate diff and line ranges" if stop else "### Literal application/frontend diff and line ranges", "```diff"]
text.append((D / "CANDIDATE_DIFF.patch").read_text() if stop else subprocess.check_output([
    "git", "diff", "fd87fc7", "--",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src",
], cwd=ROOT, text=True))
text += ["```", "", "STOP — end of Phase 5. No Phase 6, publish, deploy or push."]
report = "\n".join(text) + "\n"
assert len(report.encode()) < 50_000_000
(D.parent / "PHASE_5_REPORT.md").write_text(report)
