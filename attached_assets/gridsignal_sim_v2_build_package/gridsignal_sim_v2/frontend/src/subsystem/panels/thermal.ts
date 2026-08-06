/**
 * thermal.ts — Thermal & Cooling subsystem panel config.
 *
 * Accent: Battery blue #4a9fe0.
 * Copy matches gridsignal-10-thermal.svg.
 *
 * The 90-second lag is the product argument: compute spike and cooling rise are
 * two separate events. A reactive system meets each one after it arrives, and
 * meets the second having already spent its ramp on the first.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { BulletBar }  from '../../charts/BulletBar'

const BATTERY = '#4a9fe0'
const TEAL    = '#3fb6a8'
const AMBER   = '#f0883e'

// GS-DES-CFG-001 §Phase-3: no module-scope numeric constants.
// DT_THERMAL_S and ALPHA_MAX are derived from tick.dt_thermal_seconds and tick.alpha_max.

function fmtTime(s: number): string {
  if (s >= 86400) return '—'
  if (s >= 3600)  return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

export const thermalPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: '#30363d',
        verdict:     'No active run. Start a scenario to see thermal readiness.',
        heroValue:   '—',
        heroLabel:   'MW absorbable',
        chartTitle:  'THE 90-SECOND LAG — TWO EVENTS, NOT ONE',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'A compute step and its cooling response are two separate events roughly 90 seconds apart.',
          'A reactive controller meets each one after it arrives, and meets the second having already spent its ramp on the first.',
          'The lag is why one threshold cannot work.',
        ],
      }
    }

    const absorbMW  = tick.absorbable_mw
    const ratedMW   = tick.rated_cooling_mw
    const fraction  = ratedMW > 0 ? absorbMW / ratedMW : 1
    const limitTime = tick.time_to_limit_s
    const approach  = tick.approach_rate_mw_s
    const lowHdr    = fraction < 0.05

    // GS-DES-CFG-001 §Phase-3: derive from tick payload, not module-scope constants.
    const dtThermalS = tick.dt_thermal_seconds ?? null
    const alphaMax   = tick.alpha_max ?? null

    const stateLabel  = lowHdr ? 'ATTENTION' : 'READY'
    const stateColour = lowHdr ? AMBER : '#3fb6a8'

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'compute draw', colour: TEAL,    points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_compute_mw })) },
        { label: 'cooling draw', colour: BATTERY, points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_cooling_mw })), filled: true },
      ],
      ceiling: ratedMW > 0 ? { y: ratedMW, label: 'rated ceiling', colour: '#d9534f' } : undefined,
      xLabel:  'seconds from run start',
      height:  200,
    })

    const secondary = React.createElement('div', { className: 'space-y-2' },
      React.createElement(BulletBar, {
        label:  'Absorbable before approach to limit',
        value:  absorbMW,
        max:    ratedMW > 0 ? ratedMW : absorbMW + 1,
        colour: BATTERY,
        unit:   ' MW',
        note:   ratedMW > 0
          ? `full headroom at rest. Rated ${ratedMW.toFixed(2)} MW includes a 15% margin over α_max × peak`
          : 'rated capacity not available in this tick',
      }),
      React.createElement(BulletBar, {
        label:  'Steady-state cooling as fraction of compute',
        value:  alphaMax !== null ? alphaMax * 100 : 0,
        max:    100,
        colour: BATTERY,
        unit:   '%',
        note:   `α_max = ${alphaMax !== null ? alphaMax : '—'} · effective PUE at full load = PUE_base × (1 + α_max)`,
      }),
    )

    return {
      stateLabel,
      stateColour,
      verdict: lowHdr
        ? `Low headroom — only ${absorbMW.toFixed(2)} MW absorbable before approach.`
        : `Full headroom — ${absorbMW.toFixed(2)} MW absorbable before approach.`,
      heroValue:  absorbMW.toFixed(2),
      heroLabel:  'MW absorbable',
      chartTitle: 'THE 90-SECOND LAG — TWO EVENTS, NOT ONE',
      chart,
      statRows: [
        { label: 'Plant load',       value: `${tick.p_cooling_mw.toFixed(2)} MW`, sub: tick.p_compute_mw === 0 ? 'no compute running' : undefined },
        { label: 'Rated capacity',   value: ratedMW > 0 ? `${ratedMW.toFixed(2)} MW` : 'not instrumented', sub: 'includes 15% margin · PROTO-10' },
        { label: 'Absorbable now',   value: `${absorbMW.toFixed(2)} MW`, colour: lowHdr ? AMBER : '#3fb6a8', sub: 'additional load before approach' },
        { label: 'Time to limit',    value: fmtTime(limitTime), sub: limitTime >= 86400 ? 'no approach in progress' : 'at current approach rate' },
        { label: 'Approach rate',    value: `${approach.toFixed(3)} MW/s`, sub: 'rate of headroom consumption' },
        { label: 'Δt_thermal',       value: dtThermalS !== null ? `${dtThermalS} s` : '—', sub: 'compute spike to cooling onset' },
        { label: 'τ rise constant',  value: '20 s', sub: 'first-order settling' },
        { label: 'Pre-staging',      value: 'not configured', sub: 'shiftable load unavailable in this scenario' },
      ],
      secondary,
      why: [
        'A compute step and its cooling response are two separate events roughly 90 seconds apart.',
        'A reactive controller meets each one after it arrives, and meets the second having already spent its ramp on the first.',
        'The lag is why one threshold cannot work — GridSignal reads the scheduler queue before any current flows.',
      ],
    }
  },
}
