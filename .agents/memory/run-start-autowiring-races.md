---
name: run-start-autowiring-races
description: Pattern for auto-arming a subsystem right after a run/session starts without racing an async store fetch.
---

## The trap

A "start" action that reads a store field populated by a *separate,
fire-and-forget* async fetch triggered elsewhere (e.g. on initial selection
or on switching the active item) can silently no-op whatever it's supposed
to auto-arm if the user acts before that fetch resolves. A per-selection
staleness guard in the store (only apply a fetch result if the selection
hasn't changed since) prevents a *stale* write — it does not guarantee the
field is populated *at all* by the time the dependent action fires.

## The fix

Don't trust the render-time store field for a one-shot, post-action
decision. Capture the id you're acting on, then fetch that resource fresh,
scoped to that id, inside the action handler itself — independent of
whatever the component's subscribed state happens to hold at click time.

**Why:** this makes the auto-arm decision correct regardless of component
re-render/network timing, at the cost of one extra small request per action.

**How to apply:** any time code reacts to "just started X" and needs a
field from a store populated by an untracked/unawaited fetch elsewhere,
prefer a scoped fresh fetch over reading the shared store field, or
explicitly await the in-flight fetch before deciding.

## Multiple start surfaces

Every user-facing run creation path must apply the same scoped preset fetch.
The opening/readiness screen has its own DemoBar start handler, separate from
the inner-page RunControlBar; fixing only one leaves the other path silently
without generator wiring.

**Why:** the 100 MW scenario was correctly seeded and the backend override
logic worked, but opening-screen runs bypassed the patched control because they
used a different component.

**How to apply:** search for every POST /runs caller when changing run-start
behavior, not just the primary run-control component.

## Stale run IDs after a server restart

When latest-tick returns 404 for a tracked run, treat the run ID as stale and
return the UI to idle. Preserve 202 as a valid “active but no first tick yet”
state.

**Why:** restarting the dev server removes in-memory runs while the browser can
still hold the old run ID, otherwise the UI remains stuck in a reconnect loop.

**How to apply:** distinguish unknown runs (404) from valid startup (202) in
tick-stream recovery.
