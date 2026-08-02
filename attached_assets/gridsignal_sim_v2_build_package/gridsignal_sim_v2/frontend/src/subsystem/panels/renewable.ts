/**
 * renewable.ts — Renewable Supply subsystem panel config.
 *
 * Accent: Solar yellow #f2c94c.
 * Copy matches gridsignal-09-renewable.svg.
 *
 * Key distinction: "solar output" vs "reserve contribution" — never the same.
 * Solar is subtracted from demand (reduces the load the fleet must serve).
 * It is NEVER counted toward ramp capability. An inverter trip is a step change
 * with Δt_lead = 0. This is the "availability vs dispatchability" argument.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'
import { BulletBar }  from '../../charts/BulletBar'

const SOLAR  = '#f2c94c'
const TEAL   = '#3fb6a8'
const RED    = '#f85149'
const AMBER  = '#f0883e'

export const renewablePanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  'ADVISORY',
        stateColour: '#5a6673',
        verdict:     'Non-dispatchable — subtracts from demand, never closes a gap.',
        heroValue:   '—',
        heroLabel:   'MW, uncounted',
        chartTitle:  'CONTRIBUTION, AND EXPOSURE IF IT STOPS',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'Renewable output is subtracted from the load the fleet must serve.',
          'It is never added to ramp capability — it cannot be commanded, and carries no lead time on loss.',
          'A 5 MW solar collapse and a 5 MW compute spike are the same event to the arbitrator.',
        ],
      }
    }

    const solarMW    = tick.p_renewable_mw
    const totalMW    = tick.p_total_mw          // compute + cooling (gross site draw)
    const netDemand  = tick.net_demand_mw        // what fleet must serve after solar offset
    // "if solar vanished" line: the gap that would open without warning
    const exposureMW = solarMW
    // Share: cap at 100% — when solar > current draw the note explains the surplus
    const solarExceedsDraw = totalMW > 0 && solarMW >= totalMW
    const sharePct = totalMW > 0
      ? Math.min(100, solarMW / totalMW * 100).toFixed(0)
      : '0'
    const shareDisplay = solarExceedsDraw ? '≥ 100%' : `${sharePct}%`
    const shareNote    = solarExceedsDraw
      ? 'solar exceeds current draw · surplus absorbed by BESS'
      : 'at current compute load'

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'solar output',                colour: SOLAR, points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_renewable_mw })), filled: true },
        { label: 'dispatch required with solar', colour: TEAL,  points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_lower_mw })) },
        { label: 'if solar vanished',            colour: RED,   points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })) },
      ],
      xLabel:  'seconds from run start',
      height:  200,
    })

    const secondary = React.createElement('div', { className: 'space-y-2' },
      React.createElement(BulletBar, {
        label:  'Current output against rated',
        value:  solarMW,
        max:    Math.max(solarMW, 5),
        colour: SOLAR,
        unit:   ' MW',
        note:   solarMW > 0 ? 'contributing at rated output' : 'zero output — full load falls to dispatchable sources',
      }),
      React.createElement(BulletBar, {
        label:  'Gap if output is lost instantaneously',
        value:  exposureMW,
        max:    Math.max(exposureMW, 5),
        colour: RED,
        unit:   ' MW',
        note:   'an inverter trip is a step change with Δt_lead = 0 — no advance warning',
      }),
    )

    return {
      stateLabel:  'ADVISORY',
      stateColour: '#5a6673',
      verdict:     solarMW > 0
        ? `Contributing ${solarMW.toFixed(2)} MW — and it can vanish with no warning.`
        : 'No renewable output. Dispatch required equals total load.',
      heroValue:  solarMW.toFixed(2),
      heroLabel:  'MW, uncounted',
      chartTitle: 'CONTRIBUTION, AND EXPOSURE IF IT STOPS',
      chart,
      statRows: [
        { label: 'Output',                  value: `${solarMW.toFixed(2)} MW`, sub: 'real-time · instantaneous' },
        // net_demand_mw is the live interpolated field the fleet must cover after solar
        // offset — it changes visibly as compute ramps from idle (near 0) to full draw
        { label: 'Fleet must cover',        value: `${netDemand.toFixed(2)} MW`, colour: netDemand > 0 ? TEAL : SOLAR, sub: 'net demand after solar offset · live' },
        { label: 'Share of site draw',      value: shareDisplay, sub: shareNote },
        // Solar weather forecast from Mistral — constant per run, stamped on every tick.
        // weather label drives the colour: physics_estimate shown in muted grey.
        (() => {
          const w = tick.solar_weather
          const c = tick.solar_conditions
          if (!w || w === 'physics_estimate') {
            return { label: 'Conditions', value: 'Physics estimate', sub: 'San Diego baseline — Mistral unavailable', colour: '#5a6673' }
          }
          const label = w.replace(/_/g, ' ')
          return { label: 'Conditions', value: label, sub: c || 'Mistral solar forecast · San Diego', colour: SOLAR }
        })(),
        // PROTO-32-AMB: ambient temperature row — hidden when ambient_avg_c is 0
        // (no solar forecast was generated for this run, so the adjustment is absent).
        ...(tick.ambient_avg_c > 0 ? [(() => {
          const pct = (tick.ambient_alpha_scale - 1) * 100
          const sign = pct >= 0 ? '+' : ''
          const adj = Math.abs(pct) < 0.1
            ? 'cooling nominal (19 °C baseline)'
            : `cooling ${sign}${pct.toFixed(0)} % vs 19 °C baseline`
          return { label: 'Ambient temp', value: `${tick.ambient_avg_c.toFixed(1)} °C avg`, sub: adj, colour: pct > 0 ? AMBER : TEAL }
        })()] : []),
        { label: 'Counted toward reserve',  value: 'never', colour: AMBER, sub: 'availability, not dispatchability · §7.1.1' },
        { label: 'Control surface',         value: 'none', sub: 'passive collector — nothing to command' },
        { label: 'Lead time on loss',       value: '0 s', colour: RED, sub: 'no advance signal exists' },
        { label: 'Forecast treatment',      value: 'subtracted', sub: 'reduces demand, never closes a gap' },
        { label: 'Agent authority',         value: 'advisory only', sub: 'by construction — no dispatch path' },
      ],
      secondary,
      why: [
        'Renewable output is subtracted from the load the fleet must serve.',
        'It is never added to ramp capability, because it cannot be commanded and carries no lead time on loss.',
        `Fleet must cover ${netDemand.toFixed(1)} MW right now. A ${solarMW.toFixed(1)} MW solar collapse instantly adds ${solarMW.toFixed(1)} MW to that figure with no advance warning.`,
      ],
    }
  },
}
