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
