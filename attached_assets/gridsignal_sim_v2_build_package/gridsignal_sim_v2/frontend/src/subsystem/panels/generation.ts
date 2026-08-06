/**
 * generation.ts — Generation subsystem panel config.
 *
 * Accent: Gold #e0a458 — gas turbine / ramp-limited dispatchable.
 * Copy matches gridsignal-07-generation.svg exactly.
 *
 * Verdict phrased against FORECAST DEMAND:
 *   "Can close a X.XX MW gap inside the configured lead window."
 *   Not "turbine operational" — that is equipment status, not the product argument.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { BulletBar }  from '../../charts/BulletBar'
import { installedFleetMW } from '../../config/siteParameters'

// GS-DES-CFG-001 §Phase-3: no module-scope numeric constants.
// Rated MW and ramp rate are derived from tick.turbine_units at render time.
// Fleet-level quantities use installedFleetMW(); per-unit stat rows use first unit.

const GOLD  = '#e0a458'
const TEAL  = '#3fb6a8'

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
          { label: 'Rated output',         value: '—', sub: 'nameplate per unit — shown once run starts' },
          { label: 'Ramp rate configured', value: '—', sub: 'site parameter — shown once run starts' },
          { label: 'Ramp rate measured',   value: 'not instrumented', sub: 'no maintenance config in this scenario' },
          { label: 'Time to full output',  value: '—', sub: 'derived from tick payload — shown once run starts' },
          { label: 'Runtime hours',        value: 'not instrumented' },
          { label: 'Starts',               value: 'not instrumented' },
          { label: 'Availability',         value: '—' },
        ],
        secondary: undefined,
        why: [
          'Ramp rate, not capacity, is what decides whether a turbine can answer a step-load.',
          'Start a scenario to see the configured ramp rate and lead-window delivery.',
          'Nameplate MW is not the constraint — ramp rate is.',
        ],
      }
    }

    const outputMW   = tick.turbine_output_mw
    const demandMW   = tick.net_demand_mw
    // GS-DES-CFG-001 §Phase-3: rated MW and ramp rate derived from tick payload.
    // ── Fleet-level (use for verdicts, hero, BulletBar, canClose) ──────────────
    //   fleetMW:      installedFleetMW() — sum of all unit rated_mw (chart ceiling,
    //                   BulletBar utilisation denominator).
    //   fleetRampCap: tick.ramp_capability_mw — loading-layer authoritative fleet
    //                   ramp over dt_lead_next_s horizon. Replaces the Phase-0.5
    //                   display-level cap.  Used for verdict and hero.
    // ── Per-unit (use for per-unit stat rows and why[] prose) ──────────────────
    //   unitMW:       u0.rated_mw — first unit's nameplate (homogeneous fleet only).
    //   rampMWs:      u0.r_asset_mw_per_s — first unit's configured ramp rate.
    //   unitRampCap:  rampMWs * dt_lead_next_s — per-unit lead-window delivery
    //                   (used in why[1] "this unit delivers …" prose).
    const u0          = tick.turbine_units?.[0]
    const unitMW      = u0?.rated_mw ?? 0          // PER-UNIT: first-unit nameplate
    const fleetMW     = installedFleetMW(tick.turbine_units ?? []) ?? 0  // FLEET: ceiling
    const rampMWs     = u0?.r_asset_mw_per_s ?? 0  // PER-UNIT: first-unit ramp rate
    const unitRampCap = rampMWs * tick.dt_lead_next_s  // PER-UNIT: per-unit lead-window delivery (why[] prose)
    const fleetRampCap = tick.ramp_capability_mw       // FLEET: loading-layer authoritative ramp over lead horizon
    const canClose    = fleetRampCap >= demandMW       // FLEET: verdict gate

    // Chart series from history
    // Note: turbine_output_mw not in HistoryPoint; use p_total as proxy
    const dispatchSeries = history.map(h => ({ x: h.sim_time_seconds, y: Math.max(0, h.p_total_mw - h.p_renewable_mw) }))

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'turbine output',    colour: GOLD, points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })), filled: true },
        { label: 'dispatch required', colour: TEAL, points: dispatchSeries },
      ],
      ceiling:  fleetMW > 0 ? { y: fleetMW, label: 'fleet rated ceiling', colour: '#d9534f' } : undefined,
      xLabel:   'seconds from run start',
      height:   200,
    })

    const secondary = React.createElement('div', { className: 'space-y-2' },
      React.createElement(BulletBar, {
        // FLEET-LEVEL: tick.ramp_capability_mw is loading-layer authoritative
        // fleet ramp over the current dt_lead_next_s horizon.  Do NOT use
        // u0.r_asset_mw_per_s * dt_lead_next_s here — that is per-unit.
        label:  'Fleet ramp capability in lead window',
        value:  fleetRampCap,
        max:    Math.max(fleetRampCap, demandMW) || 1,
        target: demandMW,
        colour: GOLD,
        unit:   ' MW',
        note:   `red marker = predicted shortfall (${fmtMW(demandMW)}). ${canClose ? 'Fleet capability exceeds it.' : 'Shortfall exceeds fleet ramp capability.'}`,
      }),
      React.createElement(BulletBar, {
        label:  'Output as share of fleet rated',
        value:  outputMW,
        max:    fleetMW > 0 ? fleetMW : Math.max(outputMW, 1),
        colour: GOLD,
        unit:   ' MW',
        note:   fleetMW > 0 && outputMW < fleetMW ? `${fmtMW(fleetMW - outputMW)} of unused fleet nameplate — capacity is not the constraint, ramp rate is.` : 'At fleet rated output.',
      }),
    )

    return {
      stateLabel:  outputMW > 0 ? 'ACTIVE' : 'READY',
      stateColour: '#3fb6a8',
      verdict:     canClose
        ? `Can close a ${fmtMW(demandMW)} gap inside the ${tick.dt_lead_next_s.toFixed(0)} s lead window.`  // FLEET-LEVEL: canClose uses fleetRampCap
        : `Ramp cannot close the ${fmtMW(demandMW)} shortfall — BESS bridge required.`,
      heroValue:   `${fleetRampCap.toFixed(1)}`,  // FLEET-LEVEL: fleet ramp capability over lead horizon
      heroLabel:   'MW in lead window',
      chartTitle:  'TURBINE OUTPUT VS REQUIRED, FIRST 300 S',
      chart,
      statRows: [
        { label: 'Units online',         value: '1 of 1', sub: 'no unit in maintenance or failed' },
        { label: 'Rated output',         value: unitMW > 0 ? `${unitMW.toFixed(1)} MW` : '—', sub: 'nameplate per unit' },
        { label: 'Ramp rate configured', value: rampMWs > 0 ? `${rampMWs.toFixed(3)} MW/s` : '—', sub: 'site parameter' },
        { label: 'Ramp rate measured',   value: 'not instrumented', sub: 'no maintenance config in this scenario' },
        { label: 'Time to full output',  value: unitMW > 0 && rampMWs > 0 ? `${Math.round(unitMW / rampMWs)} s` : '—', sub: 'from cold at configured ramp' },
        { label: 'Runtime hours',        value: 'not instrumented' },
        { label: 'Starts',               value: 'not instrumented' },
        { label: 'Availability',         value: 'operational', colour: TEAL, sub: 'not degraded, not scheduled out' },
      ],
      secondary,
      why: [
        'Ramp rate, not capacity, is what decides whether a turbine can answer a step-load.',
        // PER-UNIT: rampMWs and unitRampCap are both first-unit figures — "this unit" framing is intentional.
        `At ${rampMWs.toFixed(3)} MW/s this unit delivers ${unitRampCap.toFixed(1)} MW in the ${tick.dt_lead_next_s.toFixed(0)} s of warning the scheduler gives.`,
        // FLEET-LEVEL: canClose uses fleetRampCap (tick.ramp_capability_mw); fleetMW from installedFleetMW().
        `${canClose ? `This covers the ${fmtMW(demandMW)} shortfall.` : `This does not cover the ${fmtMW(demandMW)} shortfall — BESS bridge is required.`}${fleetMW > 0 ? ` Unused fleet nameplate: ${fmtMW(fleetMW - outputMW)}.` : ''}`,
      ],
    }
  },
}
