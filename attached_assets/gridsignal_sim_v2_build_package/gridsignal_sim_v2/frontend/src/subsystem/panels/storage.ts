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
import { BessConfigWidget } from './BessConfigWidget'
// GS-DES-CFG-001 §Phase-4: bess_rated_mw, bess_usable_mwh, bess_unit_count are now
// broadcast per tick (TickPayload).  BulletBar restored, max from bess_rated_mw.

const BATTERY = '#4a9fe0'
const AMBER   = '#f0883e'
const RED     = '#f85149'

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
        verdict:     'No active run. Configure BESS below, then start a scenario.',
        heroValue:   '—',
        heroLabel:   'bridge duration',
        chartTitle:  'BESS CONFIGURATION',
        chart: React.createElement(BessConfigWidget, {}),
        statRows: [],
        why: [
          'A larger BESS buys five things for a data centre.',
          '1 · Longer turbine deferral — the GCC commits a gas turbine when utilisation crosses a threshold. BESS covering the gap keeps turbines in cold standby longer, saving fuel, wear, and start-up emissions. A 5 MWh battery bridges a 5 MW shortfall for 1 h; a 20 MWh battery covers the same gap for 4 h.',
          '2 · Bigger step-load absorption — a GPU rack powers up in milliseconds; turbines need 45 s to ramp. A larger rated-MW battery absorbs a bigger instantaneous step, letting the scheduler admit larger jobs without tripping the power cap or risking a frequency dip.',
          '3 · N-1 survivability with fewer committed turbines — the GCC\'s N-1 floor is turbine-only and ignores BESS. But a large battery with healthy SoC provides a real-world ride-through cushion while fewer turbines are on bus.',
          '4 · More solar, less curtailment — a small battery fills quickly at midday and forces solar to be curtailed. A larger battery absorbs the full solar peak and discharges it into the evening ramp, increasing renewable utilisation.',
          '5 · Anchor reserve stays cheap — the grid-forming unit permanently withholds p_anchor_reserve_mw for frequency regulation. On a small battery that is a large fraction of usable capacity; on a large battery it is a small fraction, leaving more nameplate capacity available for bridging.',
          'Trade-off: larger BESS costs more capex. Try increasing rated MW/MWh in the config above and watch whether the GCC still needs to commit a third turbine during the step-load sequence.',
        ],
      }
    }

    const soc       = tick.bess_soc_fraction
    const socPct    = Math.round(soc * 100)
    const bridge_s  = tick.bess_bridging_seconds
    const bridgeStr = fmtBridge(bridge_s)
    const outputMW  = tick.bess_output_mw

    // GS-DES-CFG-001 §Phase-4: BESS fleet aggregates from TickPayload.
    // bess_output_mw: FLEET-LEVEL sum — accumulated via += in BessArbitrator.tick()
    //   over all bess_units (dispatch.py:681–683, candidate_id "bess-fleet").
    //   Sub-label must state fleet scope so an operator reading "0.5 MW" knows
    //   it is the total discharge across all units, not a per-unit figure.
    // bess_rated_mw / bess_usable_mwh: config nameplate aggregates, NOT from
    //   contingency_coverage.bess_usable_energy_mwh (fault-injected figure).
    const ratedMW   = tick.bess_rated_mw    // FLEET: config nameplate rated power (MW)
    const usableMWh = tick.bess_usable_mwh  // FLEET: config nameplate usable energy (MWh)
    const unitCount = tick.bess_unit_count  // count of BESS units
    const unitLabel = `${unitCount} unit${unitCount !== 1 ? 's' : ''}`

    const stateLabel  = alert ? 'ATTENTION' : bridge_s > 0 ? 'READY' : 'ATTENTION'
    const stateColour = alert ? AMBER : bridge_s > 0 ? '#3fb6a8' : RED

    const chart = React.createElement(GaugeArc, {
      fraction:   soc,
      colour:     soc < 0.2 ? RED : soc < 0.4 ? AMBER : BATTERY,
      bigLabel:   `${socPct}%`,
      smallLabel: 'state of charge',
    })

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
      secondary: React.createElement(BulletBar, {
        // FLEET-LEVEL: value = fleet discharge (sum of all units); max = fleet rated power
        // from config nameplate.  max comes from bess_rated_mw, never from outputMW itself
        // (a bar whose max equals its own value is permanently full).
        label:  'Current output vs fleet rated power',
        value:  outputMW,
        max:    ratedMW > 0 ? ratedMW : Math.max(outputMW, 1),
        colour: BATTERY,
        unit:   ' MW',
        note:   ratedMW > 0
          ? `Fleet discharge ${outputMW.toFixed(2)} MW of ${ratedMW.toFixed(2)} MW rated (${unitLabel}). SoC ${socPct}%.`
          : 'Rated power not yet available on this tick',
      }),
      statRows: [
        { label: 'State of charge',   value: `${socPct}%`,                        colour: soc < 0.2 ? RED : soc < 0.4 ? AMBER : undefined },
        { label: 'Rated power',       value: `${ratedMW.toFixed(2)} MW`,           sub: `fleet aggregate — ${unitLabel}` },
        // GS-DES-CFG-001 §Phase-6 / Item-2: bess_anchor_reserve_mw now on wire.
        { label: 'Anchor reserve',    value: `${tick.bess_anchor_reserve_mw.toFixed(1)} MW`,  colour: AMBER, sub: 'withheld for grid-forming (§7.1.2) — catalogue: locked bess_anchor_reserve_mw' },
        { label: 'Current output',    value: `${outputMW.toFixed(2)} MW`,          colour: BATTERY, sub: 'fleet discharge — sum across all units' },
        { label: 'Usable energy',     value: `${usableMWh.toFixed(2)} MWh`,        sub: `fleet aggregate — ${unitLabel}` },
        { label: 'Bridging basis',    value: tick.bridging_basis.replace('_', ' ') },
        { label: 'State of health',   value: 'not modelled',                       sub: 'no degradation curve in this version' },
      ],
      why: [
        'A larger BESS buys five things for a data centre.',
        `1 · Longer turbine deferral — the GCC commits a gas turbine when utilisation crosses its threshold. BESS covering the gap keeps turbines in cold standby longer, saving fuel and start-up wear. At current rated power (${ratedMW.toFixed(1)} MW rated / ${usableMWh.toFixed(1)} MWh usable), bridge duration is the live measure of how much deferral headroom remains.`,
        '2 · Bigger step-load absorption — GPU racks power up in milliseconds; turbines need 45 s to ramp. A higher rated-MW battery absorbs a larger instantaneous step, letting the scheduler admit bigger jobs without tripping the power cap or risking a frequency dip.',
        '3 · N-1 survivability with fewer turbines on bus — the GCC\'s N-1 floor is turbine-only and ignores BESS, but a large battery with healthy SoC provides a real-world ride-through cushion while fewer turbines are committed.',
        '4 · More solar, less curtailment — a small battery fills quickly at midday and forces solar to be curtailed. A larger battery absorbs the full solar peak and discharges it into the evening ramp, raising renewable utilisation.',
        // GS-DES-CFG-001 §Phase-6 / Item-2: bess_anchor_reserve_mw is the live configured value.
        `5 · Anchor reserve stays cheap — ${tick.bess_anchor_reserve_mw.toFixed(1)} MW is permanently withheld for grid-forming frequency regulation (§7.1.2). On a small battery that is a large fraction of usable capacity; on a large battery it is a small fraction, leaving more nameplate power available for bridging.`,
        'Trade-off: larger BESS costs more capex. Change the sizing profile above and restart the scenario to see the effect on turbine commitment and bridge duration.',
      ],
    }
  },
}
