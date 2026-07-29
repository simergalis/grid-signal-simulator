import asyncio
from broadcaster_fix import *

async def consumer(c, stop):
    while not stop.is_set():
        try: await asyncio.wait_for(c.q.get(), 0.01)
        except asyncio.TimeoutError: pass

async def main():
    print("Scenario: 3 clients. 0 and 2 consume normally; client 1 is suspended.")
    print("Broadcast 5 frames.\n")

    cs = [ClientV01(2) for _ in range(3)]
    cs[1].q.put_nowait(b'x'); cs[1].q.put_nowait(b'x')
    stop = asyncio.Event()
    tasks = [asyncio.create_task(consumer(cs[i], stop)) for i in (0, 2)]
    ok = 0
    try:
        for i in range(5):
            await broadcast_v01(cs, b'f%d' % i); ok += 1; await asyncio.sleep(0.02)
    except asyncio.QueueFull:
        print(f"  v0.1 as written : QueueFull raised after {ok} frame(s).")
        print(f"                    broadcaster task dies -> all 3 clients starve,")
        print(f"                    including the 2 that were perfectly healthy.")
    stop.set(); await asyncio.gather(*tasks)

    cs = [Client(2) for _ in range(3)]
    cs[1].q.put_nowait(b'x'); cs[1].q.put_nowait(b'x')
    stop = asyncio.Event()
    tasks = [asyncio.create_task(consumer(cs[i], stop)) for i in (0, 2)]
    for i in range(5):
        await broadcast_fixed(cs, b'f%d' % i); await asyncio.sleep(0.02)
    stop.set(); await asyncio.gather(*tasks)
    healthy = [i for i, c in enumerate(cs) if not c.needs_resync]
    print(f"\n  fixed           : no exception raised. 5/5 frames broadcast.")
    print(f"                    healthy clients still served : {healthy}")
    print(f"                    slow client marked           : needs_resync="
          f"{cs[1].needs_resync}, queue drained to {cs[1].q.qsize()}")
    print(f"                    tick loop never back-pressured -> SIM-12 assertable.")

asyncio.run(main())
