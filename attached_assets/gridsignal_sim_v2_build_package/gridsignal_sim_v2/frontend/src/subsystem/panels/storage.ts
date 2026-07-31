/**
 * storage.ts — Energy Storage subsystem panel config.
 *
 * Accent: Battery blue #4a9fe0.
 * Copy matches gridsignal-08-storage.svg.
 *
 * Key distinction: "battery 95%" is equipment status.
 * "can bridge the predicted peak for 51 minutes" is the product argument.
 *
 * One megawatt is withheld as anchor reserve (§7.1.2) when grid-forming.
 * We show bridging_available = bess_output_mw-based figure from the tick.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { GaugeArc }  from '../../charts/GaugeArc'
import { BulletBar } from '../../charts/BulletBar'

const BATTERY = '#4a9fe0'
const AMBER   = '#f0883e'
const RED     = '#f85149'
const RATED_MW  = 18.0   // demo-20mw fleet rated MW
const USABLE_MWH = 8.0

function fmtBridge(s: number): string {
  if (s >= 86400) return 'full reserve'
  if (s >= 3600)  return `${(s / 3600).toFixed(1)} h`
  if (s >= 60)    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${s.toFixed(0)} s`
}

export const storagePanel: PanelConfig = {
  deriveData(tick: TickPayload | null, alert, _history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: '#30363d',
        verdict:     'No active run. Start a scenario to see storage readiness.',
        heroValue:   '—',
        heroLabel:   'bridge duration',
        chartTitle:  'STATE OF CHARGE',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'The battery serves two purposes: grid-forming anchor and bridge reserve.',
          'One megawatt is permanently withheld to regulate frequency — anchor reserve (§7.1.2).',
          'Bridge duration is the only metric that answers the operator question: how long can we cover the gap?',
        ],
      }
    }

    const soc       = tick.bess_soc_fraction
    const socPct    = Math.round(soc * 100)
    const bridge_s  = tick.bess_bridging_seconds
    const bridgeStr = fmtBridge(bridge_s)
    const outputMW  = tick.bess_output_mw

    // Available MW = what the tick reports as bridging
    const availMW   = bridge_s > 0 ? Math.min(outputMW > 0 ? outputMW : RATED_MW - 1.0, RATED_MW) : 0

    const stateLabel  = alert ? 'ATTENTION' : bridge_s > 0 ? 'READY' : 'ATTENTION'
    const stateColour = alert ? AMBER : bridge_s > 0 ? '#3fb6a8' : RED

    const chart = React.createElement(GaugeArc, {
      fraction:   soc,
      colour:     soc < 0.2 ? RED : soc < 0.4 ? AMBER : BATTERY,
      bigLabel:   `${socPct}%`,
      smallLabel: 'state of charge',
    })

    const secondary = React.createElement('div', { className: 'space-y-2' },
      React.createElement(BulletBar, {
        label:  'Available power vs rated',
        value:  availMW,
        max:    RATED_MW,
        colour: BATTERY,
        unit:   ' MW',
        note:   'anchor reserve (1.0 MW) withheld for grid-forming frequency regulation (§7.1.2)',
      }),
    )

    return {
      stateLabel,
      stateColour,
      verdict: bridge_s >= 86400
        ? 'Full reserve — can bridge the predicted peak for the run duration.'
        : bridge_s > 0
        ? `Can bridge the predicted peak for ${bridgeStr}.`
        : 'Cannot bridge — BESS power below predicted peak shortfall.',
      heroValue:  bridgeStr,
      heroLabel:  'bridge duration',
      chartTitle: 'STATE OF CHARGE',
      chart,
      statRows: [
        { label: 'State of charge',   value: `${socPct}%`,          colour: soc < 0.2 ? RED : soc < 0.4 ? AMBER : undefined },
        { label: 'Rated power',        value: `${RATED_MW.toFixed(1)} MW`,   sub: 'fleet nameplate' },
        { label: 'Anchor reserve',     value: '1.0 MW',              colour: AMBER, sub: 'withheld for grid-forming (§7.1.2)' },
        { label: 'Available power',    value: `${availMW.toFixed(1)} MW`,    colour: BATTERY },
        { label: 'Current output',     value: `${outputMW.toFixed(2)} MW` },
        { label: 'Usable energy',      value: `${USABLE_MWH.toFixed(1)} MWh`, sub: 'at rated SoC' },
        { label: 'Bridge basis',       value: tick.bridging_basis.replace('_', ' ') },
        { label: 'State of health',    value: 'not modelled',        sub: 'no degradation curve in this version' },
      ],
      secondary,
      why: [
        'The battery serves two purposes simultaneously: grid-forming anchor and bridge reserve.',
        'One megawatt is permanently withheld to regulate frequency — this is the anchor reserve (§7.1.2).',
        'Bridge duration at current shortfall is the metric that answers the operator question, not SoC percentage.',
      ],
    }
  },
}
