"""R5 requested subset only; keep the original full-table evidence unchanged."""
from pathlib import Path
import json

D = Path(__file__).resolve().parent
source = D.parent / "compare.py"
namespace = {"__file__": str(source)}
exec(compile(source.read_text().split("\nresults = []", 1)[0], str(source), "exec"), namespace)
namespace["D"] = D
results = []
for scenario, arm in [
    ("scenario-uneven-multisched-01", "baseline"),
    ("scenario-uneven-multisched-01", "informed"),
    ("scenario-equinix-sj-1", "app"),
]:
    namespace["save"](D / "STATUS.json", dict(state="RUNNING", item="V1 subset", scenario=scenario, arm=arm))
    result = namespace["pair"](scenario, arm)
    results.append({k: v for k, v in result.items() if k != "summaries"})
    namespace["save"](D / "V1_SUBSET.json", results)
    print(json.dumps(results[-1]), flush=True)
    if not result["passed"]:
        raise SystemExit("STOP: R5 V1 subset mismatch")
namespace["save"](D / "V1_COMPLETE.json", dict(passed=True, cases=results))
