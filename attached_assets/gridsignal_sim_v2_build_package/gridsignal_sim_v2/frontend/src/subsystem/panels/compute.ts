/**
 * compute.ts — Compute & Workload subsystem panel config.
 *
 * Accent: Teal #3fb6a8.
 * Shows active jobs, ramp status, and the two-stage power draw signature.
 * When the Kubernetes demand agent is active (kube_metrics != null), the panel
 * additionally shows GPU utilisation, live node count, and power-cap state.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { useGpuGeneratorStore } from '../../store/gpuGeneratorStore'

const TEAL   = '#3fb6a8'
const AMBER  = '#f0883e'
const RED    = '#f85149'

// ── per-run power-cap flip tracking ──────────────────────────────────────────
// Module-level mutable state: persists across ticks within the same run,
// resets automatically when run_id changes.
let _capFlipRunId:   string  = ''
let _capFlipCount:   number  = 0
let _capFlipPrev:    boolean = false

function fmtCountdown(s: number): string {
  if (s <= 0) return '—'
  if (s >= 60) { const m = Math.floor(s / 60); return `${m}m ${Math.round(s % 60)}s` }
  return `${s.toFixed(1)}s`
}

function fmtNodes(n: number): string {
  return n.toLocaleString()
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

    const kube  = tick.kube_metrics ?? null
    const jobs  = tick.checkpoint_states
    const jobIds = Object.keys(jobs)
    const running  = jobIds.filter(j => jobs[j] === 'running')
    const starting = jobIds.filter(j => jobs[j] === 'starting' || jobs[j] === 'in_valley')

    // ── state label ──────────────────────────────────────────────────────
    let stateLabel: string
    let stateColour = TEAL
    if (kube) {
      if (kube.power_cap_active) {
        stateLabel  = 'CAP'
        stateColour = RED
      } else if (kube.utilization > 0.78) {
        stateLabel  = 'HIGH'
        stateColour = AMBER
      } else {
        stateLabel  = 'KUBE'
      }
    } else {
      stateLabel = running.length > 0 || starting.length > 0 ? 'ACTIVE' : 'READY'
    }

    // ── hero ─────────────────────────────────────────────────────────────
    const heroValue = kube
      ? `${(kube.utilization * 100).toFixed(0)}%`
      : fmtCountdown(tick.dt_lead_next_s)
    const heroLabel = kube ? 'GPU cluster utilisation' : 'until next GPU at full TDP'

    // ── verdict ──────────────────────────────────────────────────────────
    let verdict: string
    if (kube) {
      if (kube.power_cap_active) {
        verdict = `Power cap ACTIVE — grid headroom ${kube.headroom_mw.toFixed(1)} MW. `
                + `Kubernetes scheduler capped at ${fmtNodes(kube.node_count)} nodes.`
      } else {
        verdict = `Kubernetes demand: ${(kube.utilization * 100).toFixed(0)}% GPU utilisation, `
                + `${fmtNodes(kube.node_count)} nodes scheduled. `
                + (kube.headroom_mw > 100
                    ? 'Grid headroom unconstrained.'
                    : `Grid headroom ${kube.headroom_mw.toFixed(1)} MW.`)
      }
    } else if (tick.dt_lead_next_s > 0) {
      verdict = `Ramp in progress — ${fmtCountdown(tick.dt_lead_next_s)} until GPU reaches full TDP.`
    } else if (running.length > 0) {
      // GS-DES-CFG-001 §Phase-5 / Item-4 (stale): was hardcoded "~90 s".
      // dt_thermal_seconds is now on the wire (catalogue default 90 s, range 60–120 s).
      verdict = `${running.length} job${running.length > 1 ? 's' : ''} at full draw. Cooling will settle in ~${tick.dt_thermal_seconds.toFixed(0)} s.`
    } else {
      verdict = 'No jobs queued. Thermal load at rest.'
    }

    // ── chart ────────────────────────────────────────────────────────────
    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'IT compute',  colour: TEAL,      points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_compute_mw })), filled: true },
        { label: 'cooling',     colour: '#4a9fe0',  points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_cooling_mw })) },
        { label: 'total site',  colour: '#e6edf3',  points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })) },
      ],
      xLabel:  'seconds from run start',
      height:  200,
    })

    // ── stat rows ─────────────────────────────────────────────────────────
    const jobRows = jobIds.slice(0, 6).map(jid => ({
      label: jid,
      value: jobs[jid] ?? '—',
      colour: jobs[jid] === 'running' ? TEAL : jobs[jid] === 'starting' ? AMBER : undefined,
    }))

    // ── power-cap flip counter (reset on new run) ────────────────────────────
    if (kube) {
      const runId = tick.run_id ?? ''
      if (runId !== _capFlipRunId) {
        // New run started — reset all tracking state.
        _capFlipRunId = runId
        _capFlipCount = 0
        _capFlipPrev  = kube.power_cap_active
      } else if (kube.power_cap_active !== _capFlipPrev) {
        _capFlipCount++
        _capFlipPrev = kube.power_cap_active
      }
    }

    const kubeRows = kube ? [
      { label: 'K8s utilisation',      value: `${(kube.utilization * 100).toFixed(1)}%`,       colour: kube.utilization > 0.78 ? AMBER : TEAL },
      { label: 'Active jobs',          value: kube.active_jobs.toString(),                      colour: kube.active_jobs > 0 ? TEAL : undefined },
      { label: 'Admitted nodes',       value: fmtNodes(kube.admitted_nodes) },
      { label: 'Total nodes',          value: fmtNodes(kube.node_count) },
      { label: 'Power cap',            value: kube.power_cap_active ? 'ACTIVE' : '—',           colour: kube.power_cap_active ? RED : undefined },
      { label: 'Cap flips this run',   value: _capFlipCount.toString(),                         colour: _capFlipCount > 0 ? AMBER : undefined },
      { label: 'Grid headroom',        value: kube.headroom_mw > 100 ? '∞' : `${kube.headroom_mw.toFixed(1)} MW` },
      { label: 'Arrivals this tick',   value: (kube.arrivals_this_tick ?? 0).toString() },
      {
        label: 'Requeued (cap hold)',
        value: (kube.requeued_this_tick ?? 0).toString(),
        colour: AMBER,
        // Renders as an amber call-to-action card (pulsing dot + "click →" hint).
        featured: true,
        onClick: () => useGpuGeneratorStore.getState().setOpenGeneratorAtTab('queue'),
      },
    ] : []

    return {
      stateLabel,
      stateColour,
      verdict,
      heroValue,
      heroLabel,
      chartTitle: 'POWER DRAW — COMPUTE + COOLING',
      chart,
      statRows: [
        { label: 'IT draw',          value: `${tick.p_compute_mw.toFixed(2)} MW`,  colour: TEAL },
        { label: 'Cooling draw',     value: `${tick.p_cooling_mw.toFixed(2)} MW` },
        { label: 'Total site',       value: `${tick.p_total_mw.toFixed(2)} MW` },
        {
          label: 'Unserved load',
          value: tick.p_compute_unserved_mw != null ? `${tick.p_compute_unserved_mw.toFixed(2)} MW` : '—',
          colour: (tick.p_compute_unserved_mw ?? 0) > 0.01 ? AMBER : undefined,
          sub: "compute's pro-rata share of any site-wide generation shortfall — not a job kill or admission failure",
        },
        { label: 'Δt_lead',          value: tick.dt_lead_next_s > 0 ? `${tick.dt_lead_next_s.toFixed(0)} s` : '—' },
        { label: 'Running jobs',     value: running.length.toString(),  colour: running.length > 0 ? TEAL : undefined },
        { label: 'Starting',         value: starting.length.toString() },
        { label: 'Total jobs',       value: jobIds.length.toString() },
        { label: 'Renewable offset', value: `${tick.p_renewable_mw.toFixed(2)} MW` },
        ...kubeRows,
        ...jobRows,
      ],
      secondary: undefined,
      why: kube ? [
        'Gang admission is the trigger — when Kueue or Volcano admits a pod group the node count jumps instantly. A 10-second reorder buffer and event dedup model the real NTP-timestamp guarantee.',
        'P_compute = Σ [nodes × kW] × PUE / 1000 is computed by the GPUModule each tick; P_cooling follows with a 90-second thermal lag — steps 3–4 of the Kube-to-turbine path.',
        'Power-cap holds new admissions when grid headroom falls below threshold; critical headroom evicts the largest running job so BESS can recover before the turbine ramps up.',
        '"Unserved load" is not a job kill — it is compute\'s share of any site-wide generation shortfall, split in proportion to demand. Queued jobs remain eligible for admission; nothing is cancelled. It reads zero whenever generation covers total site load.',
      ] : [
        'GridSignal reads the job scheduler queue, not a power meter — it knows a step-load is coming 30–60 s before any current flows.',
        'The two-stage power draw (compute at job start, cooling 90 s later) is the pattern incumbents cannot handle with a single threshold.',
        'Δt_lead is the window in which turbine ramp and battery bridge must be staged — the product exists to exploit this interval.',
        '"Unserved load" is not a job kill — it is compute\'s share of any site-wide generation shortfall, split in proportion to demand. It reads zero whenever generation covers total site load.',
      ],
    }
  },
}
