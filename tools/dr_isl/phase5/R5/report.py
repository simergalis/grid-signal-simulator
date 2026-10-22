"""Current R5 report; previous STOP and full 14-case measurements remain durable."""
from pathlib import Path
import json
import subprocess

R = Path(__file__).resolve().parent
D = R.parent
ROOT = R.parents[3]


def load(path):
    return json.loads(path.read_text())


def block(value):
    return ["```json", json.dumps(value, indent=2), "```"]


text = [
    "# DR-2026-10-20-ISLAND-COLLAPSE — Phase 5 D3 / R5",
    "",
    "Application baseline: fd87fc75b995f19556f598cdc5b0f443a4edce75.",
    "Resumption HEAD: 1db4393. Original candidate stash 3b856fd is retained.",
    "Evidence is incremental in tools/dr_isl/phase5/R5/. No physics/control/scenario JSON changes.",
    "",
    "## R5.1 Suite waiver and current gate",
]
text[2:2] = [
    "State: " + ("COMPLETE — R5 gates passed." if (R / "FINAL_GATE.json").exists()
                 and load(R / "FINAL_GATE.json").get("passed")
                 else "RUNNING — final suite/failure-mode gate and commits are pending."),
    "",
]
if (R / "SUITE_RESULT.json").exists():
    text += block(load(R / "SUITE_RESULT.json"))
if (R / "FAILURE_MODE_REVIEW.json").exists():
    text += ["Known failure modes (not only node IDs):"] + block(load(R / "FAILURE_MODE_REVIEW.json"))
text += [
    "",
    "## R5.2 Layering fix",
    "The candidate-only ScenarioSpec validator/import was removed. api/schemas.py equals the application baseline.",
    "The sole build-warning producer remains runtime/build_warnings.py::frequency_configuration_warnings on resolved SiteConfig.",
    "ScenarioSpec still validates. TC-ISL-08d asserts the runtime warning, unchanged null thresholds, and StartRunResponse.build_warnings.",
    "Three literal violation lists: base, candidate before R5.2, and after R5.2:",
] + block(load(R / "LAYERING_THREE_WAY.json"))
text += [
    "",
    "## Focused checks",
    "105 passed; the one known API-static test fails with exactly the base violation list.",
    "TC-ISL-07 is occupied by staging-start tests; frequency tests remain TC-ISL-08a–d (14 parametrized cases).",
    "Full output and JUnit: R5/FOCUSED.txt and R5/FOCUSED.xml.",
    "",
    "## R5.3 Frontend tracking — report only",
] + block(load(R / "FRONTEND_TRACKING_BEFORE.json"))
text += [
    "The root counts include ignored dependency/build files. No .gitignore change and no new frontend files are tracked.",
    "Only src/types.ts is already tracked among the edited files and can be committed separately.",
    "App.tsx, panels/forecastQuality.ts and the panel test stay ignored/untracked in the working tree.",
    "Their working-only changes are saved in the tracked tools/dr_isl/phase5/UI_CANDIDATE.diff.",
    "Thus the full UI implementation is NOT recoverable from the code commits alone; apply/review that saved diff against the existing frontend.",
    "",
    "## Requested R5 V1 subset",
    "Base demo both arms: raw physical fields and all 27 existing study metrics match fd87fc7.",
    "SJ-1 app path: raw physical fields/hash match; the app runner has no study metrics table.",
] + block(load(R / "V1_COMPLETE.json"))
text += [
    "",
    "## Full invalid-frequency table (previously measured; retained, not re-run in R5)",
    "Source: phase5/V1_V3_COMPLETE.json. The requested three-case subset above is the R5 recheck.",
    "| scenario / arm | ticks | protection configured | invalid count | fraction | first invalid | min / max Hz |",
    "|---|---:|---|---:|---:|---|---|",
]
if (R / "FRONTEND_TRACKING_AFTER.json").exists():
    text += ["End-of-phase tracking counts:"] + block(load(R / "FRONTEND_TRACKING_AFTER.json"))
for c in load(D / "V1_V3_COMPLETE.json")["cases"]:
    text.append(f'| {c["scenario"]} / {c["arm"]} | {c["ticks"]} | {c["protection_configured"]} | '
                f'{c["invalid_frequency_tick_count"]} | {c["invalid_frequency_fraction"]!r} | '
                f'{json.dumps(c["first_invalid_tick"])} | {c["frequency_min"]!r} / {c["frequency_max"]!r} |')
text += [
    "",
    "Published base demo and H1/H2 records contain the invalid ticks shown above. The trajectories were NOT changed or clamped.",
    "The nominal ±10% reporting band is PROPOSED_HERE, not a trip or acceptance condition.",
    "protection_configured means any resolved UF/OF/UFLS/81U threshold (including advisory thresholds), not full trip coverage.",
    "OPEN-ISL-3 remains open; compare_runs was not edited. Previous base-demo/H1/H2 comparisons remain PASS 10/10:",
] + block(load(D / "V3_COMPARE_RUNS.json"))
text += [
    "Metric identity reset: frequency_reporting_metrics_version=1 is identity-only; execution inputs and old metrics are unchanged.",
    "Version-only old/new identity digests: phase5/METRIC_IDENTITY_MAP.json.",
    "",
    "## Files, line ranges and commits",
]
for name in ["COMMITS.json", "SERVING.json", "FINAL_GATE.json"]:
    if (R / name).exists():
        text += [f"### {name}"] + block(load(R / name))
if (R / "CHANGED_LINE_RANGES.json").exists():
    text += ["### Changed files and literal hunk ranges"] + block(load(R / "CHANGED_LINE_RANGES.json"))
text += ["", "### Literal tracked application diff vs fd87fc7", "```diff"]
text.append(subprocess.check_output([
    "git", "diff", "fd87fc7", "--",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim",
    "attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/frontend/src/types.ts",
], cwd=ROOT, text=True))
text += [
    "```",
    "Persistence uses runtime/persistence.py::_tick_to_json/dataclasses.asdict; no schema migration.",
    "The run-manager serializer carries both flags into existing REST/WebSocket payloads.",
    "The opening and inner UI layouts show the unprotected-island notice; Forecast Quality marks invalid current readings grey without changing Hz.",
    "The two payload fields remain optional in TypeScript only for legacy saved payloads.",
    "No automatic checkpoint appeared during this resumption. The separate report-only commit hash is supplied in the completion response (not self-embedded).",
    "The startup screenshot verifies the signed-out app only; its unauthenticated resource 401 is expected. Display behavior was unit-tested in the prior unchanged UI evidence (17 passed).",
    "",
    "Historical STOP evidence is retained in phase5/STOP_RESULT.json and commit 1db4393; it is superseded by this R5 report.",
    "STOP — end of Phase 5. No Phase 6, publish, deploy or push.",
]
data = "\n".join(text) + "\n"
assert len(data.encode()) <= 50_000_000
(D.parent / "PHASE_5_REPORT.md").write_text(data)
