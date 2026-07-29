"""B-10 remediation: a slow client must not kill the broadcaster. Design §2.2."""
import asyncio
from collections import defaultdict

RESYNC = b'{"t":"resync"}'

class ClientV01:
    def __init__(self, n): self.q = asyncio.Queue(maxsize=n)

async def broadcast_v01(clients, frame):
    for c in clients:
        try:
            c.q.put_nowait(frame)
        except asyncio.QueueFull:
            c.q.put_nowait(RESYNC)      # <-- raises QueueFull again, uncaught

class Client:
    """FIX: resync is a flag on the client, not a message in the full queue."""
    def __init__(self, n):
        self.q = asyncio.Queue(maxsize=n)
        self.needs_resync = False
        self.dropped = 0

async def broadcast_fixed(clients, frame):
    for c in clients:
        if c.needs_resync:
            continue                     # nothing sent until the client re-requests
        try:
            c.q.put_nowait(frame)
        except asyncio.QueueFull:
            c.needs_resync = True        # mark, drain, never raise
            c.dropped += 1
            while not c.q.empty():
                c.q.get_nowait()
