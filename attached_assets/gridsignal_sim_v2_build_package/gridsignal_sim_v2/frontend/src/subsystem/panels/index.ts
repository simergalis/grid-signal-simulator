/**
 * panels/index.ts — registry mapping subsystem id → panel config.
 *
 * Each panel config implements deriveData(tick, alert, history) → PanelData.
 * The modal shell calls this once per render; the panel never fetches data itself.
 */

import type { TickPayload, HistoryPoint } from '../../types'
import type { ReactNode } from 'react'
import type { StatRow } from '../../charts/StatTable'

export interface PanelData {
  stateLabel:  string
  stateColour: string
  verdict:     string
  heroValue:   string
  heroLabel:   string
  /** Optional subtitle rendered below heroLabel — used to surface a second key
   *  metric alongside the primary hero without adding a stat row.
   *  E.g. "28.0 MW N−1 firm" on the Gas Turbine Fleet tile. */
  heroSub?:    string
  /** Colour override for heroSub text; defaults to muted when omitted. */
  heroSubColour?: string
  chartTitle:  string
  chart:       ReactNode
  statRows:    StatRow[]
  secondary?:  ReactNode
  why:         string[]
  /** Phase 0 §0.1: derived identity line overrides the static subsystems.ts string.
   *  When present, SubsystemModal renders this instead of cfg.identityLine. */
  identityLine?: string
}

export interface PanelConfig {
  deriveData: (
    tick:    TickPayload | null,
    alert:   TickPayload | null,
    history: HistoryPoint[],
    extra?:  unknown
  ) => PanelData
}

import { generationPanel }      from './generation'
import { turbineFleetPanel }    from './turbineFleet'
import { storagePanel }         from './storage'
import { renewablePanel }       from './renewable'
import { thermalPanel }         from './thermal'
import { computePanel }         from './compute'
import { gridPanel }            from './grid'
import { forecastQualityPanel } from './forecastQuality'
import { networkPanel }         from './network'
import { agentsPanel }          from './agents'
import { gccPanel }             from './gcc'

export const PANEL_CONFIGS: Record<string, PanelConfig> = {
  generation:           generationPanel,
  'gas-turbine-fleet':  turbineFleetPanel,
  storage:              storagePanel,
  renewable:            renewablePanel,
  thermal:              thermalPanel,
  compute:              computePanel,
  grid:                 gridPanel,
  'forecast-quality':   forecastQualityPanel,
  network:              networkPanel,
  agents:               agentsPanel,
  gcc:                  gccPanel,
}
