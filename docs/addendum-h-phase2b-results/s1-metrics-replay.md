# GS-DES-SSH-001 S1 metric replay

Replay date: 2026-09-19 UTC / 2026-09-18 America/Los_Angeles
Input: the four committed seven-day tick streams under this directory.
Simulation: none; this report was produced by the S1 metrics module only.

## Per-run assertions

| Run | Fuel components | Start-fuel tiers | Curtailment measures | Run-local unserved | Commitment counts | Restart-window count | Forecast misses |
|---|---|---|---|---|---|---|---|
| H-1 baseline | PASS | PASS | PASS | PASS, 5.348514157 MWh | PASS, bounded log; 24 visible / 96 omitted | PASS, 0 | PASS, 0 |
| H-1 informed | PASS | PASS | PASS | PASS, 0.911887467 MWh | PASS, bounded log; 24 visible / 96 omitted; 98,025 explicit suppressed | PASS, 0 | PASS, 0 |
| H-2 baseline | PASS | **FAIL: `StartFuelReconciliationError`** | not evaluated after hard guard | not evaluated after hard guard | not evaluated after hard guard | not evaluated after hard guard | not evaluated after hard guard |
| H-2 informed | PASS | PASS | PASS | PASS, 10.979787784 MWh | PASS, bounded log; 24 visible / 96 omitted; 99,835 explicit suppressed | PASS, 0 | PASS, 39 |

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
| H-1 baseline | 120,960 | 40,734.141940344 | 1,333.996734107 | 25,064.666045576 | 14,031.113385149 |
| H-1 informed | 120,960 | 39,538.111109868 | 1,253.227657917 | 23,168.697405534 | 13,172.325157871 |
| H-2 baseline | 120,960 | 37,023.310692264 | 2,482.333533657 | 34,309.131713505 | 26,110.848119770 |
| H-2 informed | 120,960 | 36,515.145193270 | 2,416.909275329 | 34,398.098269830 | 25,422.165180245 |

The H-2 baseline row intentionally does not invent a replay metric from the
incomplete recorded start list. The committed record reports the seven-day
day-one fuel as `5,330.503098761` MMBtu, but the S1 guard stops the replay
before metric finalization: 30 recorded start events versus 71 measured events.
The corrected interval-exposure total is `34,398.098269830` MMBtu, not
`33,438.098269830`; start-fuel increments remain exposure during curtailed
intervals even when operating fuel for that tick is zero. Attributable fuel
uses the operating-point load-fuel curve and therefore excludes no-load and
start fuel.

## Executor reproduction

The new engine-importing executor reproduced both 24-hour pairs with `17,280`
ticks per mode. Both pairs used engine and harness commit
`433f3da5900ff261153fbd6be349a5f1128f94c1`, and each baseline/informed compute
trace was identical.

```text
H-1 baseline: 6,039.740230240 MMBtu
H-1 informed: 5,848.898717938 MMBtu
H-2 baseline: 5,330.503098761 MMBtu [FAIL: 6 recorded starts, 11 measured]
H-2 informed: 5,328.350142303 MMBtu
```

Acceptance verdicts were `PASS` for H-1 and `FAIL` for H-2. H-2 fails only
because the baseline start-event reconciliation is invalid; build parity,
energy closure, fuel-component reconciliation, identical compute traces, and
the informed unserved-energy/peak checks all pass. The diagnostic executor
path preserves that failure while publishing the measured total.

## Record completeness and counter semantics

The prior Stage 2b-1 writer caps `commitment_log` at 24 records, `starts` and
`stops` at 40, `stop_floor_refusals` at 24, and `preload_actions` at 40. The
H-1 baseline/informed and H-2 informed records carry explicit truncation
markers with omission counts; H-2 baseline `starts` has 30 entries and no
marker even though telemetry measures 71 events. That is a controller-recording
defect, not JSON clipping. No missing H-2 start records were re-emitted as
real controller events. Metrics now mark bounded commitment/refusal logs
incomplete rather than presenting the visible 24 records as the complete
distinct-event count.

The `24 visible + 98,025 explicit suppressed` commitment values are not
supposed to add to `114,871` stop-floor refusals. They are different streams:
the first is the bounded commitment log plus its controller-supplied repeat
counter; the second is the refusal stream. The metrics output now labels the
bounded counts and omitted records separately.

The strict induced-miss test reports exactly one miss. In the seven-day replay,
H-1 informed has zero controller misses across 120,960 ticks while H-2
informed has 39, so the counter is live rather than hard-coded.

The informed H-1 difference from the older Stage 2b-1 value
(`5,771.387452462` MMBtu) is associated with commit
`a7d1f872e732e4db946f8c667f63f7f8fa2f80b4`, “Bound forecast history for
seven-day replays.” The later behavior is the applicable one: the current
executor matches the seven-day day-one value (`5,848.898717938` MMBtu), and
the change is covered by a bounded-history test. The older Stage 2b-1 number
is retained as historical evidence, not as the current build result.