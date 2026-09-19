# H-1 forecast-history determinism

## Scope

This check compares the same H-1 24-hour informed execution with the production
two-snapshot forecast-history bound and with a test-only unbounded logical
history. The unbounded variant preserves the current forecast as the last
entry and prevents the production slice from shortening the history; older
payloads are discarded by the test double only to avoid retaining millions of
profile tuples.

## Forecast storage dimensions

The controller uses the configured `stop_lookahead_seconds` of `1200` seconds
and the executor's `5` second forecast step. That requires:

```text
ceil(1200 / 5) + 1 = 241 profile points per forecast snapshot
```

The production history retains `2` forecast snapshots. It does not truncate
the 241 points inside the current snapshot.

## Result

Both executions used the same baseline workload replay and the same 17,280
five-second ticks:

| Metric | Bounded | Unbounded | Delta |
| --- | ---: | ---: | ---: |
| Turbine fuel (MMBtu) | 5848.898717938 | 5848.898717938 | 0 |
| Unserved energy (MWh) | 0.124133405 | 0.124133405 | 0 |
| Peak unserved power (MW) | 20.746308977 | 20.746308977 | 0 |

The compute trace SHA-256 was identical in both executions:
`916eb28339ae921141941a8c90069e573e80ef4bf65f2be39cc3e45b8747ccff`.
Every metric in the determinism test's metric set also matched exactly. The
first divergent simulated time is **none**.

Conclusion: the two-snapshot history bound is not changing H-1 informed
physics for this scenario. The result does not justify changing the bound or
any commitment, fuel, acceptance, or engine behavior.

The earlier `5771.387452462` H-1 informed figure cannot be assigned to the
history-bound change from this evidence. It was emitted by the legacy
Stage-2b-1 runner, while `5848.898717938` was emitted by the S1
`StudyRunExecutor` introduced with the study-harness implementation. The
bounded/unbounded test isolates the bound but does not make those two
measurement paths equivalent, so attributing the historical delta to a
production engine commit would be false. A commit-level historical bisect
requires replaying both figures through one identical runner.

## GPU full-suite triage

The new GPU node reached `sim_t=3600.0s` with the expected fractions and
compute means, then kept polling the completed run's final latest-tick
payload. That payload has no status field, and the test required ten distinct
phase-3 samples even though max-speed polling can observe fewer. It therefore
waited until its timeout; this was a test polling defect, not a GPU load
profile or engine defect.

The test now stops at the scenario end when the final tick is observed. The
black-box test passes with all fraction, boundary, and mean-compute checks.