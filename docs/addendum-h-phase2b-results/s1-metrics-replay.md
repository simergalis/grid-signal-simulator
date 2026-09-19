# GS-DES-SSH-001 S1 metric replay

Replay date: 2026-09-18
Input: the four committed seven-day tick streams under this directory.
Simulation: none; this report was produced by the S1 metrics module only.

## Per-run assertions

| Run | Fuel components | Start-fuel tiers | Curtailment measures | Run-local unserved | Commitment counts | Restart-window count | Forecast misses |
|---|---|---|---|---|---|---|---|
| H-1 baseline | PASS | PASS | PASS | PASS, 5.348514157 MWh | PASS, 24 distinct / 0 suppressed | PASS, 0 | PASS, 0 |
| H-1 informed | PASS | PASS | PASS | PASS, 0.911887467 MWh | PASS, 24 distinct / 98,025 suppressed | PASS, 0 | PASS, 0 |
| H-2 baseline | PASS | **FAIL: `StartFuelReconciliationError`** | not evaluated after hard guard | not evaluated after hard guard | not evaluated after hard guard | not evaluated after hard guard | not evaluated after hard guard |
| H-2 informed | PASS | PASS | PASS | PASS, 10.979787784 MWh | PASS, 24 distinct / 99,835 suppressed | PASS, 0 | PASS, 39 |

The H-2 baseline failure is intentional and required. Its guard message is:

```text
reported=940.000000000, measured=940.000000000,
recorded_events=30, measured_events=71,
hot_standby_release_charged=True
```

The harness charges a hot-standby release as a start-fuel event because that
is the event set represented by the engine's start counter and fuel telemetry.
The policy is explicitly marked `PROPOSED_HERE` in the metrics module.

## Replayed totals

| Run | Ticks | Turbine fuel (MMBtu) | Dispatch curtailment (MWh) | Curtailment interval-exposure fuel (MMBtu) | Curtailment attributable fuel (MMBtu) |
|---|---:|---:|---:|---:|---:|
| H-1 baseline | 120,960 | 40,734.141940344 | 1,333.996734107 | 25,064.666045576 | 14,213.938792097 |
| H-1 informed | 120,960 | 39,538.111109868 | 1,253.227657917 | 23,168.697405534 | 13,343.633479586 |
| H-2 informed | 120,960 | 36,515.145193270 | 2,416.909275329 | 33,438.098269830 | 25,753.449955637 |

## Executor reproduction

The new engine-importing executor reproduced the existing H-1 24-hour baseline
with `17,280` ticks and:

```text
6,039.74023024 MMBtu
```

The second identical invocation was a cache hit for both baseline and informed
records and did not execute the engine.