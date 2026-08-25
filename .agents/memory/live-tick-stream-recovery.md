---
name: Live tick stream recovery
description: Realtime simulator UI recovery when a WebSocket subscriber is dropped or becomes silent.
---

The simulator’s WebSocket is the primary live stream, but the frontend must periodically rehydrate from the authenticated latest-tick REST endpoint. A socket can remain open after the server drops its subscriber because of back-pressure, leaving the dashboard stuck on stale command or alert state while physics continues.

**Why:** Production users saw a queued turbine-command message remain visible while the simulator appeared frozen; the backend continued running and the issue matched the documented stale-subscriber boundary.

**How to apply:** Poll latest-tick while a run is active, deduplicate by tick index against the rendered and pending queues, and keep polling best-effort so transient REST failures do not replace the WebSocket path.