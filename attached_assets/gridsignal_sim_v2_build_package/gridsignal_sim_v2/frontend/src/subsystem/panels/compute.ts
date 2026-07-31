/**
 * compute.ts — Compute & Workload subsystem panel config.
 *
 * Accent: Teal #3fb6a8.
 * Shows active jobs, ramp status, and the two-stage power draw signature.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { StatTable }  from '../../charts/StatTable'

const TEAL  = '#3fb6a8'
const AMBER = '#f0883e'

function fmtCountdown(s: number): string {
  if (s <= 0) return '—'
  if (s >= 60) { const m = Math.floor(s / 60); return `${m}m ${Math.round(s % 60)}s` }
  return `${s.toFixed(1)}s`
}

export const computePanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: '#30363d',
        verdict:     'No active run. Start a scenario to see compute readiness.',
        heroValue:   '—',
        heroLabel:   'until next GPU at full TDP',
        chartTitle:  'POWER DRAW — COMPUTE + COOLING',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'GridSignal reads the job scheduler queue, not a power meter.',
          'It knows a step-load is coming 30–60 s before any current flows.',
          'The two-stage rise (compute then cooling 90 s later) is the signature the product is designed around.',
        ],
      }
    }

    const jobs   = tick.checkpoint_states
    const jobIds = Object.keys(jobs)
    const running = jobIds.filter(j => jobs[j] === 'running')
    const starting = jobIds.filter(j => jobs[j] === 'starting' || jobs[j] === 'in_valley')

    const stateLabel  = running.length > 0 || starting.length > 0 ? 'ACTIVE' : 'READY'
    const stateColour = '#3fb6a8'

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'IT compute',  colour: TEAL,    points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_compute_mw })), filled: true },
        { label: 'cooling',     colour: '#4a9fe0', points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_cooling_mw })) },
        { label: 'total site',  colour: '#e6edf3', points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })) },
      ],
      xLabel:  'seconds from run start',
      height:  200,
    })

    // Per-job rows for the table
    const jobRows = jobIds.slice(0, 6).map(jid => ({
      label: jid,
      value: jobs[jid] ?? '—',
      colour: jobs[jid] === 'running' ? TEAL : jobs[jid] === 'starting' ? AMBER : undefined,
    }))

    return {
      stateLabel,
      stateColour,
      verdict: tick.dt_lead_next_s > 0
        ? `Ramp in progress — ${fmtCountdown(tick.dt_lead_next_s)} until GPU reaches full TDP.`
        : running.length > 0
        ? `${running.length} job${running.length > 1 ? 's' : ''} at full draw. Cooling will settle in ~90 s.`
        : 'No jobs queued. Thermal load at rest.',
      heroValue:  fmtCountdown(tick.dt_lead_next_s),
      heroLabel:  'until next GPU at full TDP',
      chartTitle: 'POWER DRAW — COMPUTE + COOLING',
      chart,
      statRows: [
        { label: 'IT draw',      value: `${tick.p_compute_mw.toFixed(2)} MW`,  colour: TEAL },
        { label: 'Cooling draw', value: `${tick.p_cooling_mw.toFixed(2)} MW` },
        { label: 'Total site',   value: `${tick.p_total_mw.toFixed(2)} MW` },
        { label: 'Δt_lead',      value: tick.dt_lead_next_s > 0 ? `${tick.dt_lead_next_s.toFixed(0)} s` : '—' },
        { label: 'Running jobs', value: running.length.toString(), colour: running.length > 0 ? TEAL : undefined },
        { label: 'Starting',     value: starting.length.toString() },
        { label: 'Total jobs',   value: jobIds.length.toString() },
        { label: 'Renewable offset', value: `${tick.p_renewable_mw.toFixed(2)} MW` },
        ...jobRows,
      ],
      secondary: undefined,
      why: [
        'GridSignal reads the job scheduler queue, not a power meter — it knows a step-load is coming 30–60 s before any current flows.',
        'The two-stage power draw (compute at job start, cooling 90 s later) is the pattern incumbents cannot handle with a single threshold.',
        'Δt_lead is the window in which turbine ramp and battery bridge must be staged — the product exists to exploit this interval.',
      ],
    }
  },
}
