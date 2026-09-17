# Addendum H Phase 2a change record

Date: 2026-09-17
Scope: Phase 2a cleanup only. Phase 2b is not started.

## Fixed contract

This work preserves the Phase 2a contract:

- The exact comparison fixture remains two spinning turbines plus two hot-standby
  turbines, aero turbine mode, minimum run and minimum down time enabled.
- Baseline remains measured-core-only. It has no forecast input, forecast
  commitment/decommitment/preload action, or minimum synchronized floor.
- Informed mode remains the forecast controller that adjudicates measured-core
  proposals. The baseline and informed runs remove `kube_clusters` and
  `slurm_config` identically; scripted workload events are unchanged.
- The acceptance rule remains energy and peak unserved power no worse in informed
  mode, with no BESS-anchor violations, valid controller constraints, and
  reconciled start counts.
- Alert firing, acknowledgment, and disposition logic were not changed.

## Change sequence after `3d9b088`

| Commit | Change |
| --- | --- |
| `623aed2` | Prevented informed turbine rundown when a future scale burst arrives inside the restart window. |
| `4fe5c51` | Documented the rule that future `SCALE` events are forecast burst starts, including job-level deduplication. |
| `14ffc37` | Completed the cleanup: corrected cumulative fuel attribution, compacted repeated preload records, added one outcome per burst, and added TC-133 through TC-136 coverage. |

## Fuel attribution correction

Turbine telemetry fuel fields are cumulative run counters. The report now takes
the final row per unit for total run fuel and its load, no-load, hot-standby,
and start components. Dispatch-curtailment attribution is different: it is
interval-based, so the report adds only positive per-tick increments on ticks
with explicit dispatch curtailment. Exported component values retain nine
decimal places so per-unit component sums reconcile within the acceptance
tolerance.

Final two-hour smoke values:

| Mode | Total turbine fuel (MMBtu) | Load | No-load | Hot standby | Start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 574.613363426 | 551.938155092 | 6.520000000 | 0.155208333 | 16.000000000 |
| Informed | 478.758420879 | 457.769740323 | 4.988333333 | 0.000347222 | 16.000000000 |

The informed-minus-baseline total is **-95.854942547 MMBtu**. Component
differences are load **-94.168414769**, no-load **-1.531666667**, hot standby
**-0.154861111**, and start **0.000000000 MMBtu**. The informed preload tag is
**0.910955657 MMBtu**; it is reported separately and is not added a second time
to cumulative turbine fuel.

## Compact preload audit

Repeated evaluations now update the most recent identical target/unit record
with a suppressed-repeat count instead of appending duplicate records. A target
signature includes the per-unit targets, so a changed per-unit distribution is
logged even when the aggregate MW target is unchanged. Each forecast burst has
one report record with target, actual output at onset, reached status, and a
reason when it was not reached.

The informed smoke produced 13 compact preload records and 23 suppressed
identical repeats. It produced four burst outcomes:

| Burst (s) | Target MW | Actual onset MW | Reached | Reason |
| ---: | ---: | ---: | :---: | --- |
| 30 | 33.746638 | 22.500000 | No | ramp-limited |
| 310 | 54.010454 | 44.010454 | No | BESS charge limit |
| 1850 | 51.250000 | 51.250000 | Yes | — |
| 2700 | 36.709879 | 36.709879 | Yes | — |

## Verification

Focused Addendum H coverage is **28 passed** with one existing physical-range
warning from the TC-131 fixture.

The batched full suite collected **2,079 tests** and completed with:

| Outcome | Count |
| --- | ---: |
| Passed | 1,977 |
| Failed | 75 |
| Skipped | 4 |
| Xfailed | 23 |

The historical comparison was 2,068 collected, 1,977 passed, 65 failed,
3 skipped, and 23 xfailed. The current collection adds 11 tests; pass and
xfailed totals are unchanged. The ten-test failure increase and one additional
skip are unrelated existing-suite results and were not changed as part of this
cleanup. The complete per-test current outcome list is in
`docs/addendum-h-phase2a-full-suite-outcomes.md`.

The final smoke acceptance is **PASS**:

- baseline unserved energy: **2.252165190 MWh**
- informed unserved energy: **0.075899258 MWh**
- baseline peak unserved power: **37.096602998 MW**
- informed peak unserved power: **14.565234489 MW**
- BESS-anchor violations: **none**
- start-count reconciliation: **valid in both modes**

The four compact smoke artifacts are in
`docs/addendum-h-phase2a-results/`.