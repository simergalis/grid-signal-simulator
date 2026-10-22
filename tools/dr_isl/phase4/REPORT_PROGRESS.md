# Phase4 progress — not a final acceptance report

Application candidate is uncommitted. P3 R4 is running. P4/full suite, P5 tracking and P6 commits have NOT been reached.

## P1
51 passed,0 failed (12 new reserve cases); source guards unchanged by AST proof: P1_UNCHANGED_RELEASE_GUARDS.json. Approved TC18 expectation uses max(depth,diesel,D2-r), every other assertion retained.

## P2
See P2_REPORT.md, P2_CLASSIFICATION.json and all per-case incremental XML. Base isolation3/3 pass, file fail2400s, prefix fail720s. Candidate isolation3/3,file,prefix pass. No added prefix failures. Shared runtime latest-tick snapshot + interval-start profile / interval-end stamp; not a candidate GPU regression.

## R1/R2

| Scenario/version | Ticks | Min SoC | Floor min/max MWh | First floor | Next120s min Hz | Full Hz min/max | Unserved MWh | Collapse |
|---|---:|---:|---|---:|---:|---|---:|---|
| demo-islanded-ramp/base | 2160 | 0.0 | 0.0 / 0.0 | 771 | 56.30124604916138 | -127.48961154607643 / 60.0 | 0.7984763561509628 | None |
| demo-islanded-ramp/candidate | 2160 | 0.45166506501035325 | 0.0625 / 7.5 | 312 | 59.98901877366516 | -127.48961154607643 / 60.0 | 0.785895723386723 | None |
| S10_mit_supercloud_2021-08-11/base | 17280 | 0.0 | 0.0 / 0.0 | 2372 | 54.48350997809083 | -729.1075118080669 / 998.9330534505464 | 10.600341682490331 | None |
| S10_mit_supercloud_2021-08-11/candidate | 17280 | 0.0 | 0.0 / 14.9375 | 1012 | 79.88266332350686 | -729.1075118080669 / 998.9330534505464 | 8.4639919161834 | None |

All repetitions hash-identical within each version. Zero balance failures and zero observed illegal below-D2r discharges. TC04 passes using first reserve-floor onset (candidate never reaches0 SoC), exact+60s59.9963608710769Hz and GT+solar-demand0MW. TC05 completes17280ticks/86400s. Full basis and windows are in the case JSONs.

S10 first target-floor onset occurs while charging; first discharge-floor onset is recorded separately. Frequency extremes remain unphysical; completion does not validate that separate frequency/protection problem. No frequency/protection code changed.

D9b is a BUILD-TIME warning only; runtime S10 floor rises to14.9375MWh above14MWh usable. It is neither capped nor rejected.

R2: both candidate advisories precede first floor onset; exact timing in P3_R1_R2_EVALUATION.json.

## R3 — six historical hashes unchanged
- scenario-equinix-sj-1: `328309c3a181aefdb702a0577f41acfe673a945450ce61f9ad560696cf0aaa84` — base/candidate/reference identical.
- scenario-turbine-01: `006006e6c9eac82460ee4a343a4d1691f2a34f231ca7fb038c7ae583ab63471a` — base/candidate/reference identical.
- scenario-hybrid-ai-100mw-addendum-i: `9377f009785094697116d356ef554985107ce1ee4c92f01c672f4b30b5f7577a` — base/candidate/reference identical.
- scenario-100mw-fuel-cell-bess-diesel: `565edaad7557ed06b545d92fe6c10105ef1a709e1aeb2e224d041e1e475e581b` — base/candidate/reference identical.
- scenario-fc100-islanded-v2: `d8146d3e37d9d7e1b306bbf2dc7dea7b2675be9c2bdabca0a209a028772c73d3` — base/candidate/reference identical.
- scenario-fc100-islanded-zero-hot-v2: `d89d3132a5f87e94de6869a1246f5d3f434e03ecab72d744f90329ac8608d8f2` — base/candidate/reference identical.

## R4
RUNNING — no claim of protected-record acceptance yet. Per-pair files are written on completion.

## Source scope
Full literal diff: CANDIDATE_DIFF.patch; line ranges: CANDIDATE_CHANGED_LINES.json. No scenario JSON edits.

## Remaining
P4 full suite: NOT RUN. P5 tracking: NOT DONE. P6 commits: NOT PERMITTED until P3/P4 pass.
