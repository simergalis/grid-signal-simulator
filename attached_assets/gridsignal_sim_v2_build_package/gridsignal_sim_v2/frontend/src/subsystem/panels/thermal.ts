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

    // GS-DES-CFG-001 §Phase-4: thermal site parameters now on TickPayload.
    // dt_thermal_seconds: base thermal lag — SiteConfig value, unscaled.
    // alpha_max: base cooling fraction — SiteConfig value, NOT × ambient_alpha_scale.
    //   ambient_alpha_scale (already on wire) is the FACTOR; a panel must keep
    //   base and effective clearly separate to avoid misleading during heat stress.
    const dtThermalS = tick.dt_thermal_seconds    // base thermal lag from SiteConfig (s)
    const alphaMax   = tick.alpha_max             // base α_max from SiteConfig
    const alphaEff   = alphaMax * tick.ambient_alpha_scale  // effective (with ambient scaling)

    // Derive rated-ceiling headroom without a hardcoded literal (replaces "15% margin").
    // rated_cooling_mw = site.alpha_max × max(p_compute_mw, 1e-6) × 1.15 in simulation_core.py.
    // When alpha_max and p_compute_mw are available, the margin falls out of the ratio.
    const alphaMaxCeiling = alphaMax * Math.max(tick.p_compute_mw, 1e-6)
    const marginPct = alphaMax > 0 && alphaMaxCeiling > 0
      ? (ratedMW / alphaMaxCeiling - 1) * 100
      : null
    const ratedSub = marginPct !== null
      ? `${marginPct.toFixed(0)}% headroom over α_max × compute ceiling`
      : 'rated ceiling from thermal model'

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
        // GS-DES-CFG-001 §Phase-4: α_max now on wire.
        // value: effective fraction (base α_max × ambient_alpha_scale) as %.
        // target: base fraction (α_max alone) as % — the nameplate design point.
        // Note states both so a panel reading during heat stress does not confuse
        // the scaled effective value with the SiteConfig base parameter.
        label:  'Steady-state cooling as fraction of compute',
        value:  Math.round(alphaEff * 1000) / 10,    // effective % (with ambient scale)
        max:    100,
        target: Math.round(alphaMax * 1000) / 10,    // base % (SiteConfig nameplate)
        colour: BATTERY,
        unit:   '%',
        note:   `base α_max ${(alphaMax * 100).toFixed(1)}% · ambient scale ×${tick.ambient_alpha_scale.toFixed(2)} → effective ${(alphaEff * 100).toFixed(1)}%`,
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
        { label: 'Rated capacity',   value: ratedMW > 0 ? `${ratedMW.toFixed(2)} MW` : 'not instrumented', sub: ratedSub },
        { label: 'Absorbable now',   value: `${absorbMW.toFixed(2)} MW`, colour: lowHdr ? AMBER : '#3fb6a8', sub: 'additional load before approach' },
        { label: 'Time to limit',    value: fmtTime(limitTime), sub: limitTime >= 86400 ? 'no approach in progress' : 'at current approach rate' },
        { label: 'Approach rate',    value: `${approach.toFixed(3)} MW/s`, sub: 'rate of headroom consumption' },
        { label: 'Δt_thermal',       value: dtThermalS > 0 ? `${dtThermalS.toFixed(0)} s` : 'not populated', sub: 'base thermal lag — from SiteConfig, unscaled' },
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
