# Phase 3 — D2 design, before implementation

Base: 134538067d4eb4c2ce14232e483e9a91fd31276b, "Published your App".
`git diff --stat 5e55706..HEAD` is empty. Main working tree initially clean.
Package P: attached_assets/gridsignal_sim_v2_build_package/gridsignal_sim_v2/gridsignal_sim.

## Current locations

- P/core/asset_modules.py:1057–1081: command_start checks hot_standby,
  OFFLINE state, then enabled minimum-down with a non-NaN stop time.
- P/core/asset_modules.py:1117–1145: unit_availability creates the frozen
  UnitAvailability boundary (P/core/models.py:725–751).
- P/core/simulation_core.py:601–617: thermal/roster ordering; also used by
  standby relabelling (:621–644) and release (:693–736, :2239–2251).
- P/core/simulation_core.py:2180–2187: commitment availability snapshots;
  :2306 onward evaluates commitment; :2350 command_start; :2383–2390
  repeatedly warns about a silently dropped start.
- P/core/commitment.py:306–331: pending and settle gates, then offline[0].
- P/core/dispatch.py:593–623: pre-staging selects offline[0], starts it.

## One predicate, unchanged guards

TurbineModule.start_eligibility(sim_time) will return (bool, reason), preserving
the exact hot_standby/state/min-down ordering and conditions. command_start
calls it for its safety check. unit_availability(sim_time) calls it and carries
the evaluated result into UnitAvailability; commitment consumes that result,
not a duplicate of the guard logic and not a live turbine reference.

Candidate selection retains thermal/roster priority and skips ineligible units.
Pre-staging similarly filters using the predicate without changing allocation.
The raw offline roster remains available separately for reserve labels: filtering
it by startability would otherwise erase deliberately reserved hot-standby units.
The existing explicit hot-standby release paths must test the predicate AFTER
temporarily releasing the reserve flag and restore it if the unit cannot start;
this preserves release authority without bypassing another guard.

No-candidate logging means a contiguous requested-commit episode with physical
offline, non-reserved candidates but no eligible one. The engine writes the
reasons once, rearming after that blocked episode ends. Sites with no turbine
candidates retain their previous decision telemetry. No guard duration,
dispatch policy, scenario, diesel, reserve, frequency or protection changes.
No physical threshold or duration is introduced.

Runtime caller discovered by the base command trace: the H2 informed controller
queues starts via P/runtime/turbine_commitment.py:622–635, :831; command
application is P/runtime/run_manager.py:1521–1529. Its selector also consumes
the same predicate, retaining standby-first then roster order. Its core-proposal
adjudicator (:1199) and explicit operator command path delegate to the predicate
as well; explicit operator commands are never retargeted.
The compatibility epoch default on unit_availability is marked PROPOSED_HERE;
no physical threshold or duration is introduced.

## Evidence plan

Scratch base worktree: /tmp/DR-ISL-phase3/base at the above hash. Reuse the
Phase 2d output-only streaming adapters and unchanged baseline_runner pinning.
Observe original TurbineModule.command_start calls, distinguishing real-arm
and probe calls; stream physical SHA-256 and bounded start/rejection evidence,
never full tick exports. Compare prefixes before the first base rejection,
then whole-run hashes when there was no rejection. H keeps its existing raw
expansion/seeds; both 24h arms run twice and retain native guard results.
Stop at the first acceptance failure, particularly any H base rejection,
before committing implementation. TC-ISL-06 search returned no collision.
