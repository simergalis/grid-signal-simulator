# IMPL-ISL-30/31 — Stage 4 counterfactual summary

Seed-42 `StudyRunExecutor.run_pair` results. Each baseline arm matched its
D6g-after reference exactly on physical hash and the reported metrics.
`compare_runs` passed all 10 conditions in all four pairs.

| Scenario | Baseline: hash; unserved / peak MW; starts; fuel MMBtu; invalid ticks | Informed: D6g-after → now (hash; unserved / peak MW; starts; fuel MMBtu; invalid ticks) | Baseline gate | compare_runs |
|---|---|---|---|---|
| S10 | `22a109ae…10d9a3f`; 5.535769413 / 16.8004944; 37; 7,785.288838529; 519 | `7e63ec90…a5d63b` → `97215a59…a84ef1`; 4.399430718 → 0.234620241 / 31.8004944 → 9.859394658; 42 → 27; 7,471.889208508 → 7,880.913411826; 226 → 28 | PASS | PASS 10/10 |
| Base demo | `f1ebd90e…c7f5def6`; 0.351692658 / 22.309362466; 2; 714.363019086; 53 | `a5cb3e37…522af049` → `23c4c5b7…9a84ef1`; 0.020722990 → 0.020722990 / 7.524660522 → 7.524660522; 2 → 2; 665.395402401 → 733.778735734; 0 → 0 | PASS | PASS 10/10 |
| H1-24h | `c4fa3b35…9985fc20`; 0.894372986 / 35.021533247; 12; 6,039.740230240; 811 | `90246518…4ca4474` → `49fe8905…7cb4de2`; 0.138684661 → 0.066482927 / 20.746308977 → 13.754584348; 12 → 12; 5,836.177208739 → 6,103.925849950; 76 → 24 | PASS | PASS 10/10 |
| H2-24h | `60344137…c7782f217f`; 5.011418076 / 44.868387870; 11; 5,330.503098761; 549 | `17954e94…e3a9fba` → `0562d2e0…b5b1dbec`; 0.859772492 → 0.538242266 / 42.368387870 → 27.368387870; 14 → 12; 5,327.349493050 → 5,349.033703090; 412 → 382 | PASS | PASS 10/10 |

Sources: `tools/dr_isl/isl30/S10_COUNTERFACTUAL.json`,
`BASE_COUNTERFACTUAL.json`, `H1_COUNTERFACTUAL.json`, and
`H2_COUNTERFACTUAL.json`. The S10 operating-cost totals are in its evidence:
baseline $50,128.167955; informed $48,180.603997 → $50,720.665774.

## H2 run details

- Scenario: `scenario-h2-slurm-24h`; seed 42; 17,280 ticks per arm; elapsed
  203.374 s. The baseline matched all six D6g-after fields exactly, including
  physical hash `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f`.
- Informed arm: physical hash
  `0562d2e0df0fc06547a3fa301cd4c237ae8857f60c40ae2331241db2b5b1dbec`;
  unserved 0.538242266 MWh; peak unserved 27.368387870 MW; 12 starts;
  5,349.033703090 MMBtu; 382 invalid-frequency ticks.
- RTS/announced-job vetoes: 0.
- Informed peak: tick 11,583 at 57,915 s; unserved 27.3684 MW. At the peak,
  `gt-spin-01`, `gt-spin-02`, `gt-hot-01`, and `gt-hot-02` were synchronized,
  producing 11.25, 11.25, 8.75, and 8.75 MW respectively.

### Six synthetic Slurm jobs

All six resolve to `enterprise_8gpu_air` (10.2 kW/node), PUE 1.03, and
89.994396 MW at start. Effective warning is
`start − max(submit, start − 1,800 s)`.

| Job | Synthetic submit (s) | Start (s) | Effective warning (s) | MW |
|---|---:|---:|---:|---:|
| phase2b-h2-c01-signal-burst-02 | 27,762 | 29,110 | 1,348 | 89.994396 |
| phase2b-h2-c02-signal-burst-02 | 30,123 | 36,310 | 1,800 | 89.994396 |
| phase2b-h2-c03-signal-burst-02 | 33,398 | 43,510 | 1,800 | 89.994396 |
| phase2b-h2-c04-signal-burst-02 | 47,573 | 50,710 | 1,800 | 89.994396 |
| phase2b-h2-c05-signal-burst-02 | 57,910 | 57,910 | 0 | 89.994396 |
| phase2b-h2-c06-signal-burst-02 | 64,778 | 65,110 | 332 | 89.994396 |

## Evidence commits

- `9d06372` — S10 counterfactual
- `2533172` — base-demo counterfactual
- `60462ac` — H1 counterfactual
- `14b2dbd` — H2 counterfactual

No full-suite run, re-baselining, or publishing was performed.
