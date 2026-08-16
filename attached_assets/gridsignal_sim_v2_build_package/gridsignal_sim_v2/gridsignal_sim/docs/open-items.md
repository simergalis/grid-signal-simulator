# Implementation-Level Open Items

This file tracks implementation-level gaps and deferred invariants that are
distinct from the spec-level open-items registry (PSP-/PX-/CL-/A- prefixes)
maintained in the formal spec documents.  Entries here describe constraints
that are correct but unenforced, or coverage gaps that are intentionally
deferred.  They are not bugs — the simulator produces correct output — but
they represent places where a future change could silently break an invariant
that currently holds by convention only.

---

## IMPL-1 — Fleet `max_nodes` agreement across KubeDemandAgent instances

**Status:** Convention only. Runtime assertion added at construction time
(scenario_factory.py) catches *mismatched* `max_nodes` values the moment three
agents are built, so a misconfigured spec fails loudly at run start rather than
silently under-enforcing the shared ceiling.

**What is enforced:** The assertion checks that all three agents share an
identical `max_nodes` value after construction.  If they don't, it raises with
a message naming the offending tenant and both values.

**What is NOT enforced / future risk:** The assertion only fires at
construction.  A future change that mutates `agent.config.max_nodes` after
construction, or that introduces a fourth agent with a different ceiling, would
not be caught by the current check.  Additionally, the ramp patch in
`simulation_core.py` uses `state.kube_agents[0].config.max_nodes` as the fleet
denominator; if the invariant ever breaks in a way the construction assertion
misses, this silently uses the wrong denominator.

**Review trigger:** Revisit if the number of agents changes from three, if
`max_nodes` becomes per-tenant rather than fleet-wide, or if any post-
construction mutation of `KubeConfig` is introduced.

---

## IMPL-2 — `payload_guard` verifies top-level broadcast keys only; sub-field shape is not checked

**Status:** Intentional deferred scope.

`test_payload_guard.py` confirms that every top-level key in the broadcast dict
(built by `_tick_result_to_dict` in `runtime/run_manager.py`) has a
corresponding typed field in `frontend/src/types.ts`.  This is enforced via
source-level parsing.

**What is NOT verified:** Sub-field shape correspondence between Python
dataclasses and TypeScript interfaces is not checked.  For example, if a field
is added to `QueuedJobSummary` (Python) but omitted from `QueuedJobSummary`
(TypeScript), or vice versa, the guard does not catch it.  The correspondence
is maintained by convention — the two definitions must be updated in lockstep.

**Review trigger:** Any change to `QueuedJobSummary`, `ActiveJobSummary`, or
any other sub-object carried inside `kube_metrics` (or any other nested dict in
the broadcast) should include a manual check that the TypeScript interface
mirrors the Python fields.  A sub-field schema test could be added in the
future to automate this.
