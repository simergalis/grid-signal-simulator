# DR-2026-10-20-ISLAND-COLLAPSE — Phase 5 / D3

Base application: fd87fc75b995f19556f598cdc5b0f443a4edce75.

- Reporting only. Final TickResult construction stamps the two flags once.
- The one resolved-protection predicate examines the five UF/OF thresholds,
  81U threshold and UFLS stage thresholds; delays alone do not configure a relay.
  Any non-null threshold counts as configured, not necessarily complete coverage.
- ScenarioSpec logs a warning without rejection/mutation; build diagnostics use
  the same predicate and existing build_warnings/start-response channel.
- Frequency is neither assigned nor clamped by reporting. The proposed symmetric
  ten-percent band is not a protection setting.
- Study collector adds three metrics; an identity-only reporting version resets
  old caches. Existing execution specs and compare_runs conditions stay unchanged.
- UI has a frequency readout in Forecast Quality, not a frequency-history chart.
  Mark invalid readouts grey and add the specified explanation. An inner-app
  run-level notice observes the same tick flags. Legacy saved payloads may omit
  flags; no frontend copy of the validity calculation.
- TC-ISL-07a–g is already used by staging-start tests. TC-ISL-08 is the next free
  number found in the package tests; this phase uses TC-ISL-08a–d.
- Evidence streams raw ticks into paired comparisons and hashes, dropping ONLY
  the two new reporting keys for base/candidate physical comparisons.
- No scenario, dispatch, commitment, reserve, diesel, threshold, trip, or
  frequency equation changes are permitted. On a failed gate, stash the candidate
  and restore base application code. No publish/deploy/push.
