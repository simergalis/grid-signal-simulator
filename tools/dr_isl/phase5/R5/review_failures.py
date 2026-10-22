"""Compare assertion/error signatures, not just failing node IDs."""
from pathlib import Path
import json
import re

R = Path(__file__).resolve().parent
D = R.parent
base = json.loads((D.parent / "phase4/P4_FULL_SUITE.results.json").read_text())["cases"]
current = json.loads((R / "P5_FULL_SUITE.results.json").read_text())["cases"]
known = set((D.parent / "PHASE_4_FAILING_TESTS.txt").read_text().splitlines())


def assertions(row):
    return [line for line in row.get("failure", "").splitlines() if line.startswith("E ")]


def signature(row):
    # Preserve every asserted number/name; normalize only representation noise.
    lines = []
    for line in assertions(row):
        line = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", line)
        if " = ScenarioRecord(" in line:
            # This display-name assertion prints created_at and a clipped JSON
            # repr. The actual asserted name precedes the repr and is retained.
            line = line.split(" = ScenarioRecord(", 1)[0] + " = ScenarioRecord(<context repr>)"
        lines.append(line)
    # Pytest dictionary-diff item order can vary; keep all keys and exact values.
    return sorted(lines)


rows = []
for node in sorted(known):
    after = current.get(node, {})
    rows.append(dict(nodeid=node, base_assertions=assertions(base[node]),
                     after_assertions=assertions(after),
                     base_signature=signature(base[node]),
                     after_signature=signature(after),
                     same_failure_mode=signature(base[node]) == signature(after),
                     outcome=after.get("outcome")))
report = dict(known_failure_reviews=rows,
              changed=[r["nodeid"] for r in rows
                       if r["outcome"] == "failed" and not r["same_failure_mode"]],
              normalization="Object addresses; ScenarioRecord context repr after the asserted name; dictionary-diff display ordering. Raw diagnostics and every asserted value are retained.")
(R / "FAILURE_MODE_REVIEW.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"changed_assertion_signatures": report["changed"]}, indent=2))
