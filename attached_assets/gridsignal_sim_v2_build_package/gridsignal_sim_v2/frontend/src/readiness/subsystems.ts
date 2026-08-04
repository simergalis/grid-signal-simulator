/**
 * subsystems.ts — static config for the nine readiness tiles.
 *
 * Data, not components. Each entry drives ONE SubsystemTile instance.
 * Grouped into: data-centre | storage | supply | system.
 *
 * Colour discipline (§4 of UI-IMPLEMENTATION-PLAN):
 *   Teal    #3fb6a8 — compute/healthy
 *   Gold    #e0a458 — generation
 *   Solar   #f2c94c — renewable
 *   Battery #4a9fe0 — storage, cooling
 *   Violet  #9b8ce0 — agents
 *   Grey    #5a6673 — inactive / islanded / advisory-only
 */

export type SubsystemGroup = 'data-centre' | 'storage' | 'supply' | 'system'

export interface SubsystemConfig {
  id: string
  name: string
  group: SubsystemGroup
  /** Accent colour for the top bar and state dot. */
  accentColor: string
  /** Identity line shown under the title in the modal. */
  identityLine: string
  /** Which existing tab to navigate to on "Open full page". */
  tabId?: string
}

export const SUBSYSTEMS: SubsystemConfig[] = [
  // ── DATA CENTRE ───────────────────────────────────────────────────────────
  {
    id: 'compute',
    name: 'Compute & Workload',
    group: 'data-centre',
    accentColor: '#3fb6a8',
    identityLine: 'GPU workloads · ramp-limited by Δt_lead · two-stage power draw',
    tabId: 'overview',
  },
  {
    id: 'thermal',
    name: 'Thermal & Cooling',
    group: 'data-centre',
    accentColor: '#4a9fe0',
    identityLine: 'cooling-0 · liquid loop · BMS retains override',
    tabId: 'thermal',
  },

  // ── ENERGY STORAGE ────────────────────────────────────────────────────────
  {
    id: 'storage',
    name: 'Energy Storage',
    group: 'storage',
    accentColor: '#4a9fe0',
    identityLine: 'bess-0 · grid-forming anchor · anchor reserve withheld',
    tabId: 'overview',
  },

  // ── POWER SOURCES ─────────────────────────────────────────────────────────
  {
    id: 'gas-turbine-fleet',
    name: 'Gas Turbine Fleet',
    group: 'supply',
    accentColor: '#e0a458',
    // Phase 0 §0.1: derived at runtime from turbine_units in the fleet modal
    // (turbineFleet.ts _identityLine).  Static literal deleted — count, rating,
    // and prime-mover class all come from the scenario spec via TickPayload.
    identityLine: '',
    tabId: 'overview',
  },
  {
    id: 'generation',
    name: 'Generation',
    group: 'supply',
    accentColor: '#e0a458',
    identityLine: 'turbine-0 · gas turbine · ramp-limited dispatchable',
    tabId: 'overview',
  },
  {
    id: 'renewable',
    name: 'Renewable Supply',
    group: 'supply',
    accentColor: '#f2c94c',
    identityLine: 'solar-0 · fixed-mount PV · non-dispatchable',
    tabId: 'overview',
  },
  {
    id: 'grid',
    name: 'Grid Connection',
    group: 'supply',
    accentColor: '#5a6673',
    identityLine: 'islanded microgrid · open-transition · no utility feed',
    tabId: 'procurement',
  },

  // ── SYSTEM ────────────────────────────────────────────────────────────────
  {
    id: 'forecast-quality',
    name: 'Forecast Quality',
    group: 'system',
    accentColor: '#3fb6a8',
    identityLine: 'confidence engine · data-quality tags · calibration state',
    tabId: 'overview',
  },
  {
    id: 'network',
    name: 'Network Fabric',
    group: 'system',
    accentColor: '#4a9fe0',
    identityLine: 'network telemetry · latency · topology',
    tabId: 'network',
  },
  {
    id: 'agents',
    name: 'Optimisation Agents',
    group: 'system',
    accentColor: '#9b8ce0',
    identityLine: '6 agents · analysis and proposals · human-gated · no dispatch authority',
    tabId: 'proposals',
  },
]

export const GROUP_LABELS: Record<SubsystemGroup, string> = {
  'data-centre': 'Data Centre',
  'storage':     'Energy Storage',
  'supply':      'Power Sources',
  'system':      'System',
}

export const GROUP_ORDER: SubsystemGroup[] = ['data-centre', 'storage', 'supply', 'system']
