/**
 * forecastQuality.ts — Forecast Quality subsystem panel config.
 *
 * Accent: Teal #3fb6a8.
 * Shows DQ tags, confidence band, calibration state.
 * Copy matches gridsignal-13-forecast-quality context.
 *
 * This is the tile an engineer will linger on — it shows how much to trust
 * the numbers on every other panel.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'

const TEAL  = '#3fb6a8'
const AMBER = '#f0883e'

const DQ_LABELS: Record<string, string> = {
  unmapped_hardware:   'Unmapped hardware — +10% CI widening',
  uncalibrated_site:   'Uncalibrated site — +8% CI widening',
  invalid_payload:     'Invalid payload — +15% CI widening',
  stale_profile:       'Stale profile — +5% CI widening',
}

export const forecastQualityPanel: PanelConfig = {
  deriveData(tick: TickPayload | null, _alert, history: HistoryPoint[]): PanelData {
    if (!tick) {
      return {
        stateLabel:  '—',
        stateColour: '#30363d',
        verdict:     'No active run. Start a scenario to see forecast quality.',
        heroValue:   '—',
        heroLabel:   'confidence band MW',
        chartTitle:  'CONFIDENCE BAND — FORECAST VS ACTUAL',
        chart: React.createElement('div', { className: 'font-mono text-xs text-muted py-12 text-center' }, 'No data'),
        statRows: [],
        why: [
          'The confidence band is the only live indicator of how much to trust every other number on screen.',
          'Each data-quality flag widens the band independently and additively — they are chosen values, not derived.',
          'A calibrated site with known hardware and clean payloads has a 5% base widening and nothing more.',
        ],
      }
    }

    const dqTags  = tick.data_quality_tags
    const bandMW  = tick.confidence_upper_mw - tick.confidence_lower_mw
    const hasFlags = dqTags.length > 0

    const chart = React.createElement(TimeSeries, {
      series: [
        { label: 'upper bound', colour: '#30363d', points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_upper_mw })), filled: true },
        { label: 'forecast',    colour: TEAL,      points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })) },
        { label: 'lower bound', colour: '#30363d', points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_lower_mw })) },
      ],
      xLabel:  'seconds from run start',
      height:  200,
    })

    const tagRows = dqTags.map(tag => ({
      label: tag,
      value: 'ACTIVE',
      colour: AMBER,
      sub: DQ_LABELS[tag] ?? tag,
    }))

    const clearTags = Object.keys(DQ_LABELS).filter(t => !dqTags.includes(t)).map(tag => ({
      label: tag,
      value: 'clear',
      sub:   DQ_LABELS[tag],
    }))

    return {
      stateLabel:  hasFlags ? 'ATTENTION' : 'READY',
      stateColour: hasFlags ? AMBER : TEAL,
      verdict:     hasFlags
        ? `${dqTags.length} data-quality flag${dqTags.length > 1 ? 's' : ''} active — confidence band widened.`
        : 'All calibration checks clear. Confidence band nominal.',
      heroValue:  `±${(bandMW / 2).toFixed(2)}`,
      heroLabel:  'MW confidence band',
      chartTitle: 'CONFIDENCE BAND — FORECAST VS ACTUAL',
      chart,
      statRows: [
        { label: 'DQ flags active',  value: dqTags.length.toString(), colour: hasFlags ? AMBER : undefined },
        { label: 'Band width',       value: `${bandMW.toFixed(2)} MW` },
        { label: 'Upper bound',      value: `${tick.confidence_upper_mw.toFixed(2)} MW` },
        { label: 'Lower bound',      value: `${tick.confidence_lower_mw.toFixed(2)} MW` },
        { label: 'Base widening',    value: '5%', sub: 'always applied — chosen value, not derived' },
        ...tagRows,
        ...clearTags.slice(0, Math.max(0, 4 - tagRows.length)),
      ],
      secondary: undefined,
      why: [
        'The confidence band is the only live indicator of how much to trust every other number on screen.',
        'Each data-quality flag widens the band independently and additively — they are chosen values, not derived from measurements.',
        'A calibrated site with known hardware and clean payloads has a 5% base widening. Flags add 5–15% each.',
      ],
    }
  },
}
