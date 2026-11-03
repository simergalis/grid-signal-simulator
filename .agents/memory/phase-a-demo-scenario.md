---
name: Phase A scheduler demo scenarios
description: Conditions needed for a catalogue scenario to visibly prove real K8S queueing.
---

A K8S catalogue demo should use an explicit `kube_clusters` entry with an empty
`workload_events` list. To prove scheduler behavior rather than merely delayed
container startup, the arrival rate multiplied by job duration must exceed the
bounded node/GPU capacity, and the run should use a short backoff plus a finite
retry count so both backoff and unschedulable states can be observed before
resource-release requeue.

For grid-cap admission stress scenarios, count contiguous cap-held intervals
from simulation telemetry, not intended arrival waves. A planned surge can fail
to hold or merge with a neighboring interval, and its actual drain time need not
match a seeded timing input.

**Why:** A low-contention workload can instantiate `KubeSchedulerEngine` while
never exposing active queue pressure; `container_start_delay_s` by itself is
not evidence of queue wait. Admission pressure is a runtime outcome, not a
property guaranteed by the generator's scheduled windows.

**How to apply:** Keep the scenario RNG fixed and assert catalogue registration,
engine construction, GPU compatibility, positive queue wait, backoff depth, and
unschedulable depth in one deterministic regression test. For cap admission,
derive episode boundaries, peak depth, and drain duration from held-job ticks,
and report random timing draws separately from observed queue duration.