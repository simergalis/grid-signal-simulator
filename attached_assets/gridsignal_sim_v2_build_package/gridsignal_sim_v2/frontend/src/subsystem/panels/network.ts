/**
 * network.ts — Network Fabric subsystem panel config.
 *
 * Phase 10: live data from FabricModel (Simulator Spec Section 12).
 * Six plant-plane fields are now carried on the WS tick payload under
 * tick.fabric when FabricEngine is wired.  When absent, the honest
 * "not instrumented" state is preserved (§0.2: never a plausible placeholder).
 *
 * Accent: Battery blue #4a9fe0.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint, FabricModalView } from '../../types'

// ---------------------------------------------------------------------------
// Helper: format latency
// ---------------------------------------------------------------------------

function fmtMs(ms: number | undefined | null): string {
  if (ms == null) return '—'
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`
  return `${ms.toFixed(1)} ms`
}

function fmtPct(v: number | undefined | null, decimals = 3): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(decimals)}%`
}

// ---------------------------------------------------------------------------
// Mini heat strip for link utilisation (rendered inside the chart slot)
// ---------------------------------------------------------------------------

function LinkHeatStrip({ utilisation }: { utilisation: Record<string, number> }) {
  const entries = Object.entries(utilisation)
  if (entries.length === 0) {
    return React.createElement('div', { className: 'text-xs text-muted py-4 text-center' },
      'Waiting for first fabric tick…')
  }

  // Group by fabric_id prefix (e.g. "compute/leaf0/up0" → "compute")
  const groups: Record<string, Array<{ id: string; u: number }>> = {}
  for (const [id, u] of entries) {
    const fab = id.split('/')[0]
    if (!groups[fab]) groups[fab] = []
    groups[fab].push({ id, u })
  }

  const FABRIC_COLOURS: Record<string, string> = {
    compute:  '#4a9fe0',
    storage:  '#e0a84a',
    frontend: '#4ae0a8',
  }

  return React.createElement('div', { className: 'space-y-1.5 py-1' },
    Object.entries(groups).map(([fab, links]) =>
      React.createElement('div', { key: fab },
        React.createElement('div', { className: 'flex items-center gap-1.5 mb-0.5' },
          React.createElement('span', { className: 'font-mono text-[9px] text-muted uppercase w-14' }, fab),
          React.createElement('div', { className: 'flex-1 flex gap-px h-3 overflow-hidden rounded' },
            links.slice(0, 64).map(({ id, u }) => {
              const colour = FABRIC_COLOURS[fab] ?? '#4a9fe0'
              const opacity = Math.max(0.08, u)
              return React.createElement('div', {
                key: id,
                className: 'flex-1',
                style: { backgroundColor: colour, opacity },
                title: `${id}: u=${(u * 100).toFixed(1)}%`,
              })
            })
          )
        )
      )
    )
  )
}

// ---------------------------------------------------------------------------
// Panel config
// ---------------------------------------------------------------------------

export const networkPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, _history: HistoryPoint[]): PanelData {
    const fab: FabricModalView | null = tick?.fabric ?? null

    if (!fab) {
      // No fabric data — preserve the honest "not instrumented" state.
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
    }

    // ── Live fabric data available ─────────────────────────────────────────
    const breached = fab.control?.breached ?? false
    const latencyMs = fab.control_latency_ms ?? 0
    const congested = fab.congested_links ?? 0

    const stateLabel  = breached ? 'NFR-2 BREACH' : congested > 0 ? 'CONGESTED' : 'NOMINAL'
    const stateColour = breached ? '#e05050' : congested > 0 ? '#e0a84a' : '#4ae07a'

    const disc = fab.discrimination
    const verdictStr = disc
      ? `${disc.verdict} · tier: ${disc.capability_tier}`
      : 'no discrimination data'

    const chart = React.createElement(LinkHeatStrip, {
      utilisation: fab.link_utilisation ?? {},
    })

    const cp = fab.control
    const dominant = cp?.dominant_term ? ` (${cp.dominant_term})` : ''

    return {
      stateLabel,
      stateColour,
      verdict:    verdictStr,
      heroValue:  fmtMs(latencyMs),
      heroLabel:  breached ? 'NFR-2 BREACH' : 'control latency',
      chartTitle: 'LINK UTILISATION',
      chart,
      statRows: [
        { label: 'Control latency',    value: fmtMs(latencyMs) + dominant },
        { label: 'Packet loss',        value: fmtPct(fab.packet_loss) },
        { label: 'Topology nodes',     value: String(fab.topology_nodes ?? '—') },
        { label: 'Congested links',    value: String(congested) },
        { label: 'Bandwidth headroom', value: fmtPct(fab.bandwidth_headroom_frac, 1) },
        { label: 'Retransmit rate',    value: fmtPct(fab.retransmit_rate) },
        { label: 'Budget',             value: fmtMs(cp?.budget_ms) },
        { label: 'Discrimination',     value: disc?.verdict ?? '—' },
      ],
      secondary: undefined,
      why: [
        'Network telemetry is a real-time signal for the dispatch layer — high latency on control traffic can delay staging commands.',
        `Control path: fabric ${fmtMs(cp?.l_fabric_ms)} + gateway ${fmtMs(cp?.l_gateway_ms)} + ack ${fmtMs(cp?.l_asset_ack_ms)} = ${fmtMs(latencyMs)} vs ${fmtMs(cp?.budget_ms)} budget.`,
        'Phase discrimination (§25.5): checkpoint is corroborated when compute quiesces AND storage carries sustained WRITE elephant flows — direction separates checkpoint from job-start weight load.',
      ],
    }
  },
}
