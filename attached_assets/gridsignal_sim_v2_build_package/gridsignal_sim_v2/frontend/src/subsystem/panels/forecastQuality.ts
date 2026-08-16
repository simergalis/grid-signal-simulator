/**
 * forecastQuality.ts — Forecast Quality subsystem panel config.
 *
 * Accent: Teal #3fb6a8.
 * Shows DQ tags, confidence band, calibration state.
 * Copy matches gridsignal-13-forecast-quality context.
 *
 * This is the tile an engineer will linger on — it shows how much to trust
 * the numbers on every other panel.
 *
 * Phase 11.5 additions:
 *   • Chart centre changed from p_total_mw → forecast_mw (F4 criterion).
 *   • Second "actual" trace (p_total_mw) added so the prediction gap is visible.
 *   • BESS setpoint vs measured gap shown in stat rows.
 *   • Frequency deviation indicator shown in islanded mode (protection_provisional).
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'
import { TimeSeries } from '../../charts/TimeSeries'

const TEAL    = '#3fb6a8'
const AMBER   = '#f0883e'
const GREY    = '#30363d'
// Dimmed teal for the confidence band fill
const BAND_BG = '#1a2e2d'

const DQ_LABELS: Record<string, string> = {
  unmapped_hardware:   'Unmapped hardware — +10% CI widening',
  uncalibrated_site:   'Uncalibrated site — +8% CI widening',
  invalid_payload:     'Invalid payload — +15% CI widening',
  stale_profile:       'Stale profile — +5% CI widening',
}

// Frequency nominal fallback — used only when the tick predates Phase 11.5
// and frequency_nominal_hz is not yet on the wire.  All live runs include it.
const FREQ_NOMINAL_FALLBACK_HZ = 60.0

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

    // Phase 11.5: two-trace chart.
    // Series order matters for z-ordering: confidence band fill first, then
    // the two signal lines on top so they are always visible.
    const chart = React.createElement(TimeSeries, {
      series: [
        // Confidence band — upper bound filled; lower bound filled with a dark
        // colour to "mask out" the region below the band, producing a shaded
        // corridor between the two bounds around the forecast line.
        { label: 'upper bound', colour: GREY, points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_upper_mw })), filled: true },
        { label: 'lower bound', colour: BAND_BG, points: history.map(h => ({ x: h.sim_time_seconds, y: h.confidence_lower_mw })), filled: true },
        // Predicted — forecast_mw is the centre of the confidence band (F4
        // criterion: agrees with the PREDICTED PEAK header figure bit-for-bit).
        { label: 'predicted',   colour: TEAL,      points: history.map(h => ({ x: h.sim_time_seconds, y: h.forecast_mw })) },
        // Actual — p_total_mw is the real measured site demand this tick.
        // The gap between predicted and actual is the prediction error.
        { label: 'actual',      colour: '#e6edf3', points: history.map(h => ({ x: h.sim_time_seconds, y: h.p_total_mw })) },
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

    // Phase 11.5: BESS setpoint vs measured gap.
    const bessDelta = tick.bess_setpoint_mw - tick.bess_output_mw
    const bessGapStr = `${bessDelta >= 0 ? '+' : ''}${bessDelta.toFixed(3)} MW`
    const bessGapColour = Math.abs(bessDelta) > 0.5 ? AMBER : undefined

    // Phase 11.5: frequency deviation indicator — only meaningful in islanded
    // mode.  protection_provisional is true on every islanded tick (§2A spec).
    // frequency_nominal_hz is stamped from SiteConfig per-run — 60 Hz (WECC/SDG&E)
    // or 50 Hz (EU/APAC/NZ).  Fall back to 60 Hz only on pre-Phase-11.5 ticks.
    const isIslanded  = tick.protection_provisional
    const nominalHz   = tick.frequency_nominal_hz ?? FREQ_NOMINAL_FALLBACK_HZ
    const freqDevHz   = tick.frequency_hz - nominalHz
    const freqStr     = `${tick.frequency_hz.toFixed(3)} Hz (${freqDevHz >= 0 ? '+' : ''}${freqDevHz.toFixed(3)})`
    // Colour: amber when deviation > 0.5 Hz, red when > 1.5 Hz (UFLS proximity).
    const freqColour = Math.abs(freqDevHz) > 1.5 ? '#d9534f' :
                       Math.abs(freqDevHz) > 0.5 ? AMBER     : undefined

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
        { label: 'DQ flags active',      value: dqTags.length.toString(),                colour: hasFlags ? AMBER : undefined },
        { label: 'Band width',           value: `${bandMW.toFixed(2)} MW` },
        { label: 'Upper bound',          value: `${tick.confidence_upper_mw.toFixed(2)} MW` },
        { label: 'Lower bound',          value: `${tick.confidence_lower_mw.toFixed(2)} MW` },
        // Phase 11.5: BESS dispatch tracking.
        { label: 'BESS setpoint',        value: `${tick.bess_setpoint_mw.toFixed(3)} MW`,  sub: 'dispatch command (pre-clip)' },
        { label: 'BESS measured',        value: `${tick.bess_output_mw.toFixed(3)} MW`,    sub: 'actual output this tick' },
        { label: 'BESS setpoint gap',    value: bessGapStr,                               colour: bessGapColour, sub: 'setpoint − measured' },
        // Phase 11.5: frequency deviation (islanded mode only).
        ...(isIslanded ? [
          { label: 'Frequency',          value: freqStr, colour: freqColour, sub: 'islanded — swing-equation driven' },
        ] : [
          { label: 'Frequency',          value: 'grid-tied',                              sub: `locked to ${nominalHz} Hz reference` },
        ]),
        { label: 'Base widening',        value: '5%',                                     sub: 'always applied — chosen value, not derived' },
        ...tagRows,
        ...clearTags.slice(0, Math.max(0, 4 - tagRows.length)),
      ],
      secondary: undefined,
      why: [
        'The confidence band is the only live indicator of how much to trust every other number on screen.',
        'The "predicted" trace is forecast_mw — the queue-derived point estimate used to size the confidence band. It agrees exactly with the PREDICTED PEAK header figure (F4).',
        'The "actual" trace is p_total_mw — real measured site demand. The gap between the two traces is live prediction error.',
        'BESS setpoint gap = dispatch command minus measured output. A large gap indicates clipping at rated power or an SoC limit.',
        'Each data-quality flag widens the band independently and additively — they are chosen values, not derived from measurements.',
        'A calibrated site with known hardware and clean payloads has a 5% base widening. Flags add 5–15% each.',
      ],
    }
  },
}
