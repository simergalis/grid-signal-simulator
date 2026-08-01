/**
 * grid.ts — Grid Connection subsystem panel config.
 *
 * Accent: Grey #5a6673.
 * ISLANDED is the design, not a fault — the "bring your own power" case.
 * Colour is grey, not red. §4 of UI-IMPLEMENTATION-PLAN.
 *
 * Copy matches gridsignal-12-grid.svg.
 * Procurement data (price curves) exists at /procurement — the modal notes
 * that the full page has more detail.
 */

import React from 'react'
import type { PanelConfig, PanelData } from './index'
import type { TickPayload, HistoryPoint } from '../../types'

const GREY   = '#5a6673'
const TEAL   = '#3fb6a8'

export const gridPanel: PanelConfig = {
  deriveData(_tick: TickPayload | null, _alert, _history: HistoryPoint[]): PanelData {
    const chart = React.createElement('div', {
      className: 'flex flex-col items-center justify-center py-12 gap-2',
    },
      React.createElement('div', { className: 'font-mono text-xs text-muted text-center' },
        'Islanded microgrid — no utility feed.'),
      React.createElement('div', { className: 'font-mono text-[10px] text-muted text-center' },
        'Procurement price curve available on the Grid & Procurement page.'),
    )

    return {
      stateLabel:  'ISLANDED',
      stateColour: GREY,
      verdict:     'Islanded by design — no utility dependency.',
      heroValue:   '0.00',
      heroLabel:   'MW imported',
      chartTitle:  'SEEDED SYNTHETIC PRICE CURVE — NO LIVE MARKET FEED',
      chart,
      statRows: [
        { label: 'MW imported',        value: '0.00 MW',            colour: GREY },
        { label: 'Connection mode',    value: 'islanded',           colour: GREY, sub: 'open-transition · no utility feed' },
        { label: 'Firm contracted',    value: '0.00 MW',            sub: 'counts toward reserve' },
        { label: 'Reserved window',    value: '0.00 MW',            sub: 'counts toward reserve' },
        { label: 'Non-firm spot',      value: '0.00 MW',            sub: 'does NOT close the gap' },
        { label: 'Grid reliability',   value: 'not modelled',       sub: 'procurement models firmness, not reliability' },
        { label: 'Anti-islanding',     value: 'GridSignal advises', colour: TEAL, sub: 'never commands · TC-68' },
        { label: 'Droop control',      value: 'GridSignal advises', colour: TEAL, sub: 'PMS retains authority' },
      ],
      secondary: undefined,
      why: [
        'Islanded microgrid is the "bring your own power" case — the motivation for the product.',
        'GridSignal advises on grid-connection events but never commands islanding, synchro-check, or protective load shed.',
        'TC-68 audit recorded 71 allowed commands and zero in all five protection categories across a fully-loaded 60-tick run.',
      ],
    }
  },
}
