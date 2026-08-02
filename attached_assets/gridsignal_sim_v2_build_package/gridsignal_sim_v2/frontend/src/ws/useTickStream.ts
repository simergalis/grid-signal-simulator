/**
 * useTickStream.ts — WebSocket lifecycle hook for the tick stream.
 *
 * Connects to WS /ws/{runId}, deserialises each message as TickPayload,
 * and pushes it to the Zustand store via pushTick().
 *
 * Run-complete handling: the server sends {"type":"run_complete"} as its
 * final message when the scenario's end_sim_time is reached, then closes
 * the socket.  On receipt the hook calls onRunComplete() (if provided)
 * instead of scheduling a reconnect — the run is done, not dropped.
 *
 * Reconnect behaviour: on any other close (network errors, server restart)
 * the hook schedules a reconnect after RECONNECT_DELAY_MS.  Reconnect is
 * aborted if the component unmounts.
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

export function useTickStream(runId: string | null, onRunComplete?: () => void) {
  const pushTick = useTickStore(s => s.pushTick)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Track whether the WS closed because the run completed (not a network error).
  const runCompletedRef = useRef(false)

  useEffect(() => {
    if (!runId) return

    let destroyed = false
    runCompletedRef.current = false

    function connect() {
      if (destroyed) return
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/${runId}`)
      wsRef.current = ws

      ws.onmessage = (event: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(event.data) as Record<string, unknown>

          // Run-complete sentinel — server sends this when end_sim_time is reached.
          // Do NOT reconnect; call the parent callback so the UI transitions to
          // the completed state and shows the View Results button.
          if (msg.type === 'run_complete') {
            console.info(`[useTickStream] run ${runId} completed naturally`)
            runCompletedRef.current = true
            ws.close()
            onRunComplete?.()
            return
          }

          const tick = msg as unknown as TickPayload
          pushTick(tick)
          // Phase 10 §12.10 — echo t_emit_ns back so the server can record
          // the round-trip latency in InstrumentPlane.observe_tick().
          // Fire-and-forget: latency instrumentation must never block tick ingestion.
          if (tick.t_emit_ns != null) {
            fetch('/api/session/observe-tick', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ t_emit_ns: tick.t_emit_ns }),
            }).catch(() => {
              // Silently drop observe errors — latency measurement is best-effort.
            })
          }
        } catch {
          console.warn('[useTickStream] malformed message:', event.data)
        }
      }

      ws.onclose = () => {
        if (destroyed) return
        // If the run completed normally the onmessage handler already called
        // onRunComplete() — do not schedule a reconnect loop.
        if (runCompletedRef.current) return
        console.info(`[useTickStream] closed for run ${runId}; reconnecting in ${RECONNECT_DELAY_MS}ms`)
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }

      ws.onerror = (err) => {
        console.warn('[useTickStream] error', err)
        ws.close()  // triggers onclose → scheduled reconnect (unless run completed)
      }
    }

    connect()

    return () => {
      destroyed = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [runId, pushTick, onRunComplete])
}
