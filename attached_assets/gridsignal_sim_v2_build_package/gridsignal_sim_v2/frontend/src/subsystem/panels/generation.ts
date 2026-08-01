/**
 * generation.ts — Generation subsystem panel config.
 *
 * Accent: Gold #e0a458 — gas turbine / ramp-limited dispatchable.
 * Copy matches gridsignal-07-generation.svg exactly.
 *
 * Verdict phrased against FORECAST DEMAND:
 *   "Can close a X.XX MW gap inside the 45 s lead window."
 *   Not "turbine operational" — that is equipment status, not the product argument.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { BulletBar }  from '../../charts/BulletBar'

const GOLD  = '#e0a458'
const TEAL  = '#3fb6a8'
const RATED_MW      = 25.0   // demo-20mw turbine nameplate
const RAMP_MW_S     = 0.2    // site parameter

function fmtMW(v: number): string { return `${v.toFixed(2)} MW` }

export const generationPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: '#30363d',
        verdict:     'No active run. Start a scenario to see generation readiness.',
        heroValue:   '—',
        heroLabel:   'MW in lead window',
        chartTitle:  'TURBINE OUTPUT VS REQUIRED, FIRST 300 S',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [
          { label: 'Units online',         value: '—' },
          { label: 'Rated output',         value: `${RATED_MW.toFixed(1)} MW`, sub: 'nameplate per unit' },
          { label: 'Ramp rate configured', value: `${RAMP_MW_S.toFixed(3)} MW/s`, sub: 'site parameter' },
          { label: 'Ramp rate measured',   value: 'not instrumented', sub: 'no maintenance config in this scenario' },
          { label: 'Time to full output',  value: `${Math.round(RATED_MW / RAMP_MW_S)} s`, sub: 'from cold at configured ramp' },
          { label: 'Runtime hours',        value: 'not instrumented' },
          { label: 'Starts',               value: 'not instrumented' },
          { label: 'Availability',         value: '—' },
        ],
        secondary: undefined,
        why: [
          'Ramp rate, not capacity, is what decides whether a turbine can answer a step-load.',
          `At ${RAMP_MW_S} MW/s this unit delivers ${(RAMP_MW_S * 45).toFixed(1)} MW in the 45 s of warning the scheduler gives.`,
          'Five megawatts of nameplate sit unused — capacity is not the constraint, ramp rate is.',
        ],
      }
    }

    const outputMW   = tick.turbine_output_mw
    const demandMW   = tick.net_demand_mw
    const rampCap    = RAMP_MW_S * tick.dt_lead_next_s  // MW closeable in lead window
    const canClose   = rampCap >= demandMW

    // Chart series from history
    // Note: turbine_output_mw not in HistoryPoint; use p_total as proxy
    const dispatchSeries = history.map(h => ({ x: h.sim_time_seconds, y: Math.max(0, h.p_total_mw - h.p_renewable_mw) }))

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'turbine output',    colour: GOLD, points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })), filled: true },
        { label: 'dispatch required', colour: TEAL, points: dispatchSeries },
      ],
      ceiling:  { y: RATED_MW, label: 'rated ceiling', colour: '#d9534f' },
      xLabel:   'seconds from run start',
      height:   200,
    })

    const secondary = React.createElement('div', { className: 'space-y-2' },
      React.createElement(BulletBar, {
        label:  'Ramp capability in lead window',
        value:  rampCap,
        max:    RATED_MW,
        target: demandMW,
        colour: GOLD,
        unit:   ' MW',
        note:   `red marker = predicted shortfall (${fmtMW(demandMW)}). ${canClose ? 'Capability exceeds it.' : 'Shortfall exceeds ramp capability.'}`,
      }),
      React.createElement(BulletBar, {
        label:  'Output as share of rated',
        value:  outputMW,
        max:    RATED_MW,
        colour: GOLD,
        unit:   ' MW',
        note:   outputMW < RATED_MW ? `${fmtMW(RATED_MW - outputMW)} of unused nameplate — capacity is not the constraint, ramp rate is.` : 'At rated output.',
      }),
    )

    return {
      stateLabel:  outputMW > 0 ? 'ACTIVE' : 'READY',
      stateColour: '#3fb6a8',
      verdict:     canClose
        ? `Can close a ${fmtMW(demandMW)} gap inside the ${tick.dt_lead_next_s.toFixed(0)} s lead window.`
        : `Ramp cannot close the ${fmtMW(demandMW)} shortfall — BESS bridge required.`,
      heroValue:   `${rampCap.toFixed(1)}`,
      heroLabel:   'MW in lead window',
      chartTitle:  'TURBINE OUTPUT VS REQUIRED, FIRST 300 S',
      chart,
      statRows: [
        { label: 'Units online',         value: '1 of 1', sub: 'no unit in maintenance or failed' },
        { label: 'Rated output',         value: `${RATED_MW.toFixed(1)} MW`, sub: 'nameplate per unit' },
        { label: 'Ramp rate configured', value: `${RAMP_MW_S.toFixed(3)} MW/s`, sub: 'site parameter' },
        { label: 'Ramp rate measured',   value: 'not instrumented', sub: 'no maintenance config in this scenario' },
        { label: 'Time to full output',  value: `${Math.round(RATED_MW / RAMP_MW_S)} s`, sub: 'from cold at configured ramp' },
        { label: 'Runtime hours',        value: 'not instrumented' },
        { label: 'Starts',               value: 'not instrumented' },
        { label: 'Availability',         value: 'operational', colour: TEAL, sub: 'not degraded, not scheduled out' },
      ],
      secondary,
      why: [
        'Ramp rate, not capacity, is what decides whether a turbine can answer a step-load.',
        `At ${RAMP_MW_S} MW/s this unit delivers ${rampCap.toFixed(1)} MW in the ${tick.dt_lead_next_s.toFixed(0)} s of warning the scheduler gives.`,
        `${canClose ? `This covers the ${fmtMW(demandMW)} shortfall.` : `This does not cover the ${fmtMW(demandMW)} shortfall — BESS bridge is required.`} Unused nameplate: ${fmtMW(RATED_MW - outputMW)}.`,
      ],
    }
  },
}
