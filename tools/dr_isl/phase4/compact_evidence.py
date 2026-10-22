"""Retain audit summaries, not redundant full per-tick refusal event lists."""
import hashlib
import json
from pathlib import Path

D = Path(__file__).resolve().parent
proof = []
for path in sorted(D.glob("P3_R4_*.json")):
    pair = json.loads(path.read_text())
    if not isinstance(pair, dict) or "runs" not in pair:
        continue
    changed = False
    entry = {"file": path.name, "original_bytes": path.stat().st_size, "versions": {}}
    for version, run in pair["runs"].items():
        summary = run["summary"]
        record = summary["record"]
        events = record.get("stop_floor_refusals")
        if not isinstance(events, list):
            continue
        encoded = json.dumps(events, sort_keys=True, separators=(",", ":"), allow_nan=True).encode()
        bounded = {
            "count": len(events),
            "canonical_sha256": hashlib.sha256(encoded).hexdigest(),
            # PROPOSED_HERE: three boundary examples are an evidence-storage
            # limit only, not a simulation or acceptance parameter.
            "first_three": events[:3],
            "last_three": events[-3:],
        }
        record["audit_stop_floor_refusals_summary"] = bounded
        del record["stop_floor_refusals"]
        entry["versions"][version] = {
            "count": bounded["count"], "canonical_sha256": bounded["canonical_sha256"],
            "physical_sha256": summary["physical_sha256"],
            "compact_sha256": record["audit_compact_sha256"],
            "metrics_sha256": hashlib.sha256(json.dumps(
                summary["metrics"], sort_keys=True, separators=(",", ":"),
                allow_nan=True).encode()).hexdigest(),
        }
        changed = True
    if changed:
        path.write_text(json.dumps(pair, indent=2, allow_nan=True) + "\n")
        entry["retained_bytes"] = path.stat().st_size
        proof.append(entry)
if proof:
    (D / "EVIDENCE_COMPACTION.json").write_text(json.dumps({
        "reason": "Persist summaries/hashes/bounded examples, not full per-tick refusal event logs",
        "physical_fields_compact_ticks_and_27_metrics": "UNCHANGED",
        "files": proof,
    }, indent=2) + "\n")
    print(json.dumps({"compacted_files": len(proof),
                      "bytes_before": sum(x["original_bytes"] for x in proof),
                      "bytes_after": sum(x["retained_bytes"] for x in proof)}))
