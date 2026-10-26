# IMPL-ISL-30/31 multi-seed summary

Seeds: 1–10 rerun at current HEAD; seed 42 imported from the existing cap-1800 counterfactual. Default announcement cap: 1,800 s.

All values are min / median / max across the 11 seeds (1–10, 42).

| Scenario | Metric | Baseline min / median / max | Informed min / median / max |
|---|---|---:|---:|
| scenario-uneven-multisched-01 | unserved_mwh | 0.351692658 / 0.351692658 / 0.351692658 | 0.020722990 / 0.020722990 / 0.081720457 |
| scenario-uneven-multisched-01 | peak_unserved_mw | 22.309362466 / 22.309362466 / 22.309362466 | 7.524660522 / 7.524660522 / 19.809362466 |
| scenario-uneven-multisched-01 | fuel_mmbtu | 714.363019086 / 714.363019086 / 714.363019086 | 727.889142859 / 733.778735734 / 733.778735734 |

**scenario-uneven-multisched-01: 11/11 seeds PASS 10/10.**
- Failing seeds: none.

| scenario-h2-slurm-24h | unserved_mwh | 5.011418076 / 5.011418076 / 5.011418076 | 0.538242266 / 0.538242266 / 2.898965668 |
| scenario-h2-slurm-24h | peak_unserved_mw | 44.868387870 / 44.868387870 / 44.868387870 | 27.368387870 / 27.368387870 / 38.098732218 |
| scenario-h2-slurm-24h | fuel_mmbtu | 5330.503098761 / 5330.503098761 / 5330.503098761 | 5340.998905305 / 5349.033703090 / 5349.033703090 |

**scenario-h2-slurm-24h: 11/11 seeds PASS 10/10.**
- Failing seeds: none.

Per-seed effective warning times for Slurm jobs (seconds):
- Seed 1: phase2b-h2-c01-signal-burst-02=1800s; phase2b-h2-c02-signal-burst-02=1800s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=1800s; phase2b-h2-c05-signal-burst-02=1800s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 2: phase2b-h2-c01-signal-burst-02=1800s; phase2b-h2-c02-signal-burst-02=0s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=1800s; phase2b-h2-c05-signal-burst-02=412s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 3: phase2b-h2-c01-signal-burst-02=412s; phase2b-h2-c02-signal-burst-02=1800s; phase2b-h2-c03-signal-burst-02=332s; phase2b-h2-c04-signal-burst-02=1800s; phase2b-h2-c05-signal-burst-02=412s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 4: phase2b-h2-c01-signal-burst-02=0s; phase2b-h2-c02-signal-burst-02=1800s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=1800s; phase2b-h2-c05-signal-burst-02=332s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 5: phase2b-h2-c01-signal-burst-02=1800s; phase2b-h2-c02-signal-burst-02=0s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=1800s; phase2b-h2-c05-signal-burst-02=1800s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 6: phase2b-h2-c01-signal-burst-02=1391s; phase2b-h2-c02-signal-burst-02=0s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=412s; phase2b-h2-c05-signal-burst-02=1800s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 7: phase2b-h2-c01-signal-burst-02=1800s; phase2b-h2-c02-signal-burst-02=1s; phase2b-h2-c03-signal-burst-02=1s; phase2b-h2-c04-signal-burst-02=332s; phase2b-h2-c05-signal-burst-02=1800s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 8: phase2b-h2-c01-signal-burst-02=1800s; phase2b-h2-c02-signal-burst-02=412s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=412s; phase2b-h2-c05-signal-burst-02=1800s; phase2b-h2-c06-signal-burst-02=412s
- Seed 9: phase2b-h2-c01-signal-burst-02=4s; phase2b-h2-c02-signal-burst-02=1800s; phase2b-h2-c03-signal-burst-02=0s; phase2b-h2-c04-signal-burst-02=0s; phase2b-h2-c05-signal-burst-02=1800s; phase2b-h2-c06-signal-burst-02=1800s
- Seed 10: phase2b-h2-c01-signal-burst-02=412s; phase2b-h2-c02-signal-burst-02=0s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=1800s; phase2b-h2-c05-signal-burst-02=1800s; phase2b-h2-c06-signal-burst-02=1407s
- Seed 42: phase2b-h2-c01-signal-burst-02=1348s; phase2b-h2-c02-signal-burst-02=1800s; phase2b-h2-c03-signal-burst-02=1800s; phase2b-h2-c04-signal-burst-02=1800s; phase2b-h2-c05-signal-burst-02=0s; phase2b-h2-c06-signal-burst-02=332s
