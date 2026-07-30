/**
 * useTickStream.ts — WebSocket lifecycle hook for the tick stream.
 *
 * Connects to WS /ws/{runId}, deserialises each message as TickPayload,
 * and pushes it to the Zustand store via pushTick().
 *
 * Reconnect behaviour: on close (including network errors) the hook
 * schedules a reconnect after RECONNECT_DELAY_MS.  Reconnect is aborted
 * if the component unmounts (the effect cleanup clears the timer and
 * closes the socket).
 *
 * KNOWN BOUNDARY (Step 7): a dropped server-side subscriber (due to the
 * _SEND_TIMEOUT_S back-pressure mechanism) is NOT auto-recovered here.
 * The client's WebSocket connection to the server stays open, but if the
 * server dropped the hub subscription the client will receive no further
 * ticks.  Step 8's snapshot-on-connect + resync protocol will address
 * this.  Until then, the user sees a stale panel and must reload.
 */

import { useEffect, useRef } from 'react'
import type { TickPayload } from '../types'
import { useTickStore } from '../store/tickStore'

const RECONNECT_DELAY_MS = 2_000

export function useTickStream(runId: string | null) {
  const pushTick = useTickStore(s => s.pushTick)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!runId) return

    let destroyed = false

    function connect() {
      if (destroyed) return
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/${runId}`)
      wsRef.current = ws

      ws.onmessage = (event: MessageEvent<string>) => {
        try {
          const tick = JSON.parse(event.data) as TickPayload
          pushTick(tick)
        } catch {
          console.warn('[useTickStream] malformed message:', event.data)
        }
      }

      ws.onclose = () => {
        if (destroyed) return
        console.info(`[useTickStream] closed for run ${runId}; reconnecting in ${RECONNECT_DELAY_MS}ms`)
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }

      ws.onerror = (err) => {
        console.warn('[useTickStream] error', err)
        ws.close()  // triggers onclose → scheduled reconnect
      }
    }

    connect()

    return () => {
      destroyed = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [runId, pushTick])
}
