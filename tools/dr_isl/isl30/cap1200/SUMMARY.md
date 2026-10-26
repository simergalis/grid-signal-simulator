# 20-minute lookahead comparison

Seed: `42`. Each cap-1200 pair was run with `parameter_overrides={"turbine_forecast_announcement_cap_seconds": 1200}` through `StudyRunExecutor.run_pair`; cap-1800 values are the existing `isl30/*_COUNTERFACTUAL.json` `arms.*.now` references.

All four baseline gates passed: physical hash, unserved MWh, peak unserved MW, starts, turbine fuel, operating-cost total, and invalid-frequency tick count match cap 1800 exactly. The cap-1200 value appears in both arm identities for every case. Cap-1200 identity digests are listed below; the D6g `now` reference objects do not contain cap-1800 identity digests. Compare-runs passed 10/10 for each case with no failed conditions.

| Scenario | Arm | Physical hash (1800 → 1200) | Unserved MWh | Peak unserved MW | Starts | Fuel MMBtu | Operating cost USD | Invalid ticks | Identity digest (1200) | Compare runs | RTS vetoes* |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| S10 | baseline | `22a109ae31e928518db467fbe3ff90675604ce2e38c0f6ed5551c21aa10d9a3f` → `22a109ae31e928518db467fbe3ff90675604ce2e38c0f6ed5551c21aa10d9a3f` | 5.535769413 → 5.535769413 | 16.8004944 → 16.8004944 | 37 → 37 | 7785.288838529 → 7785.288838529 | $50128.167955 → $50128.167955 | 519 → 519 | `e5a9489d6cc03033864bf6ab8f49626132e8cafc34e8f7831cbdc68e8ffcf336` | PASS (10/10) | — |
| S10 | informed | `97215a592356fd54c598bf2bcd5998ea84ab014cc250037c4a4096146ec144bb` → `97215a592356fd54c598bf2bcd5998ea84ab014cc250037c4a4096146ec144bb` | 0.234620241 → 0.234620241 | 9.859394658 → 9.859394658 | 27 → 27 | 7880.913411826 → 7880.913411826 | $50720.665774 → $50720.665774 | 28 → 28 | `69bf20fa9286ed7afa1431b25fa375cddc36f7212a93e4a782c8ed3f0ebed74a` | PASS (10/10) | 2 |
| Base demo | baseline | `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` → `f1ebd90e589a217bbaf85264a2153a268a493a8b644c75ebbe74fd89c7f5def6` | 0.351692658 → 0.351692658 | 22.309362466 → 22.309362466 | 2 → 2 | 714.363019086 → 714.363019086 | — | 53 → 53 | `8588a62b29ba5390c35f9d1a901138939336c78282e130169f6975a0e6e0356e` | PASS (10/10) | — |
| Base demo | informed | `23c4c5b7d7f0eb98a9e9071a1a64ab8ea2d7c843d1e7f1af072f9daf99a84ef1` → `23c4c5b7d7f0eb98a9e9071a1a64ab8ea2d7c843d1e7f1af072f9daf99a84ef1` | 0.02072299 → 0.02072299 | 7.524660522 → 7.524660522 | 2 → 2 | 733.778735734 → 733.778735734 | — | 0 → 0 | `9510c2f2e40c9a383f10366861b87842152e786f834bd8a46e3660c408e3204a` | PASS (10/10) | 0 |
| H1-24h | baseline | `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` → `c4fa3b355b2eebf949f1f0ad9f43b1b76770cf05bb380d224a3282699985fc20` | 0.894372986 → 0.894372986 | 35.021533247 → 35.021533247 | 12 → 12 | 6039.74023024 → 6039.74023024 | — | 811 → 811 | `76b7d376f992214dafd73faecf3b9660e933b0d5fb7d9d16d0794db9d5740766` | PASS (10/10) | — |
| H1-24h | informed | `49fe8905d6e97f8654a0bc3febab07198f6f89cac66e7b0993bbeb62e7cb4de2` → `49fe8905d6e97f8654a0bc3febab07198f6f89cac66e7b0993bbeb62e7cb4de2` | 0.066482927 → 0.066482927 | 13.754584348 → 13.754584348 | 12 → 12 | 6103.92584995 → 6103.92584995 | — | 24 → 24 | `9ea7a390cb03646960354f65e146ce2cc6223cdeddd0a6d2c3ef30e54e061bb4` | PASS (10/10) | 1 |
| H2-24h | baseline | `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` → `603441374503951709dc77d5ae11234e966d5b479e50edca5dd608c7782f217f` | 5.011418076 → 5.011418076 | 44.86838787 → 44.86838787 | 11 → 11 | 5330.503098761 → 5330.503098761 | — | 549 → 549 | `92889f41a27ce390697386373f62d62a9444fc6f3942cc8bc3333399c50d34cb` | PASS (10/10) | — |
| H2-24h | informed | `0562d2e0df0fc06547a3fa301cd4c237ae8857f60c40ae2331241db2b5b1dbec` → `0562d2e0df0fc06547a3fa301cd4c237ae8857f60c40ae2331241db2b5b1dbec` | 0.538242266 → 0.538242266 | 27.36838787 → 27.36838787 | 12 → 12 | 5349.03370309 → 5349.03370309 | — | 382 → 382 | `5c7c810bf233cdd4b8468aab0a032e198cf08231ec6dd4d35fd696333fb32d75` | PASS (10/10) | 0 |

* Veto count is for the informed arm. Each JSON file includes the first five veto entries (when present), full comparison conditions, gate comparison fields, and the identity path/value confirming cap 1200.

Evidence files were committed individually before the next scenario was run:
- S10: `6374acb`
- Base demo: `ede0e3f`
- H1-24h: `c94e444`
- H2-24h: `2f1aae5`
