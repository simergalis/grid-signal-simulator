"""
api/routes/ws.py — WebSocket tick-stream endpoint.

Step 6 / v2.5 §8.1 / Design Spec Section 4.4.

WS /ws/{run_id}

On connect, the client is subscribed to the shared WebSocketHub so
it receives every tick broadcast by that run's _drive coroutine.  The
handler keeps the socket open until the client disconnects; on
disconnect it removes the subscription so dead sockets don't accumulate.

Invariants:
  - WebSocketHub is retrieved from app.state (set once in the lifespan).
    No endpoint creates its own WebSocketHub instance.
  - The hub's broadcast() is called by RunContext's drive loop (in
    runtime/run_manager.py), never by this handler.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from runtime.run_manager import WebSocketHub

router = APIRouter(tags=["ws"])


@router.websocket("/ws/{run_id}")
async def subscribe_run(websocket: WebSocket, run_id: str) -> None:
    """Subscribe to live tick data for *run_id*.

    Ticks are pushed by the RunManager's drive loop via WebSocketHub.broadcast().
    This handler's only job is to hold the connection open and clean up
    when the client disconnects — it never produces data itself.
    """
    hub: WebSocketHub = websocket.app.state.ws_hub
    await websocket.accept()
    hub.subscribe(run_id, websocket)
    try:
        # Drain client-sent messages to detect disconnects.
        # send_json() calls from hub.broadcast() are independent and
        # interleave with this receive loop in the same event loop.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(run_id, websocket)
