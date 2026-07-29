import itertools, random
from arbitration_fix import *

cap = Capability({"storage_discharge": 2.0, "turbine_ramp": 3.0,
                  "curtail_ladder_ab": 5.0})
recs = [
    Rec("r1", "turbine_ramp",      "Generation", 3.0),
    Rec("r2", "storage_discharge", "Storage",    2.0),
    Rec("r3", "curtail_ladder_ab", "Compute",    5.0),
    Rec("r4", "storage_discharge", "Thermal",    1.0),   # same-kind collision
]

def trace(sel): return [(r.recommendation_id, round(r.contribution_mw, 3)) for r in sel]

print("TC-49: selection must be reproducible from the recommendation SET alone.\n")
for name, fn in (("v0.1 as written", select_v01), ("fixed", select_fixed)):
    results = {tuple(trace(fn(6.0, list(p), cap))) for p in itertools.permutations(recs)}
    status = "PASS" if len(results) == 1 else f"FAIL — {len(results)} distinct outcomes"
    print(f"  {name:16s} over all 24 input orderings: {status}")
    if len(results) > 1:
        for r in sorted(results)[:3]: print(f"      {r}")

print("\nSame-kind collision handling (r2 and r4 both storage_discharge):")
print("  v0.1 :", trace(select_v01(6.0, recs, cap)), "<- r4 silently dropped")
print("  fixed:", trace(select_fixed(6.0, recs, cap)), "<- both ranked, headroom shared")

random.seed(0)
sh = [random.sample(recs, len(recs)) for _ in range(200)]
uniq = {tuple(trace(select_fixed(6.0, s, cap))) for s in sh}
print(f"\n200 random shuffles against fixed selector -> {len(uniq)} distinct outcome(s)")
