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

**Why:** A low-contention workload can instantiate `KubeSchedulerEngine` while
never exposing active queue pressure; `container_start_delay_s` by itself is
not evidence of queue wait.

**How to apply:** Keep the scenario RNG fixed and assert catalogue registration,
engine construction, GPU compatibility, positive queue wait, backoff depth, and
unschedulable depth in one deterministic regression test.