---
name: Ray Phase 5 KubeRay autoscaling
description: Durable rules for feeding Ray demand into Kubernetes worker admission.
---

KubeRay autoscaling must convert pending logical Ray demand into worker replica
requests through Kubernetes admission. Scale-up and scale-down delays, per-group
limits, admission rejection, simulated power budgets, worker registration, and
replacement are observable control-plane behavior. Slurm-backed Ray remains
fixed and never enters this path.

**Why:** Ray logical capacity cannot be increased by bypassing Kubernetes
admission, and a failed worker must not leave its admission allocation
double-counted during replacement.

**How to apply:** Keep worker replica admissions individually accountable,
release failed or idle dynamic replicas before re-requesting them, and treat
initial elastic workers as part of the original admission footprint.