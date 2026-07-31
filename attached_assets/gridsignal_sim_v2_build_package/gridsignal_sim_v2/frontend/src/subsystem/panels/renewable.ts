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

    const solarMW  = tick.p_renewable_mw
    const totalMW  = tick.p_total_mw
    const sharePct = totalMW > 0 ? (solarMW / totalMW * 100).toFixed(0) : '0'
    // "if solar vanished" line: the gap that would open without warning
    const exposureMW = solarMW

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
        { label: 'Output',                  value: `${solarMW.toFixed(2)} MW`, sub: 'instantaneous' },
        { label: 'Rated',                   value: `${solarMW > 0 ? solarMW.toFixed(2) : '—'} MW`, sub: 'nameplate · PROTO-7 sizing' },
        { label: 'Share of site demand',    value: `${sharePct}%`, sub: 'at current compute load' },
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
        `A ${solarMW.toFixed(1)} MW solar collapse and a ${solarMW.toFixed(1)} MW compute spike are the same event to the arbitrator.`,
      ],
    }
  },
}
