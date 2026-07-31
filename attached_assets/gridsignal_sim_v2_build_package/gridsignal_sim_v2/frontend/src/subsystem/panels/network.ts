/**
 * network.ts — Network Fabric subsystem panel config.
 *
 * Accent: Battery blue #4a9fe0.
 * Network telemetry lives at the /network-telemetry endpoint.
 * The tick payload does not carry network fields — the honest empty state
 * is shown on the tile; the modal directs the user to the full Network page.
 *
 * "not instrumented" is the correct string here — not a placeholder number.
 * §0.2 of the plan: never a plausible placeholder.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'

export const networkPanel: PanelConfig = {
  deriveData(_tick: TickPayload | null, _alert, _history: HistoryPoint[]): PanelData {
    const chart = React.createElement('div', {
      className: 'flex flex-col items-center justify-center py-12 gap-3',
    },
      React.createElement('div', { className: 'font-mono text-xs text-muted text-center leading-relaxed' },
        'Network telemetry is not carried on the WebSocket tick payload.'),
      React.createElement('div', { className: 'font-mono text-[10px] text-muted text-center' },
        'Open the Network Telemetry page for live latency, packet loss, and topology data.'),
    )

    return {
      stateLabel:  '—',
      stateColour: '#30363d',
      verdict:     'Network metrics not carried on the tick stream — see full page for live data.',
      heroValue:   '—',
      heroLabel:   'not instrumented',
      chartTitle:  'NETWORK TELEMETRY',
      chart,
      statRows: [
        { label: 'Control latency',    value: 'not instrumented' },
        { label: 'Packet loss',        value: 'not instrumented' },
        { label: 'Topology nodes',     value: 'not instrumented' },
        { label: 'Congested links',    value: 'not instrumented' },
        { label: 'Bandwidth headroom', value: 'not instrumented' },
        { label: 'WS tick latency',    value: 'not instrumented' },
        { label: 'Retransmit rate',    value: 'not instrumented' },
        { label: 'API round-trip',     value: 'not instrumented' },
      ],
      secondary: undefined,
      why: [
        'Network telemetry is a real-time signal for the dispatch layer — high latency on control traffic can delay staging commands.',
        'The Network Telemetry page (§19.9) shows live topology and latency; this modal summarises availability only.',
        '"Not instrumented" is the correct state — a zero that reads as a measurement is worse than an honest gap.',
      ],
    }
  },
}
