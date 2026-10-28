/**
 * plantLayout.ts — geometry data for the one-line plant mimic diagram.
 *
 * All coordinates are in the SVG viewBox space: 0 0 1200 526.
 * The diagram SVG uses preserveAspectRatio="xMidYMid meet" so it scales
 * proportionally with the container and remains correct at all widths ≥ 768 px.
 *
 * Positions were derived from the gs-01-opening-rest.svg design file.
 */

export const DIAGRAM_W = 1200
// Height extended to fit optional Fuel Cell and Diesel nodes when both are
// enabled and packed below the always-present source stack.
// Height extended for the optional Fuel Cell and Diesel source tiles when
// both are enabled and packed below the always-present source stack.
export const DIAGRAM_H = 526

/** One node in the one-line diagram. */
export interface NodeDef {
  /** Subsystem id — matches SUBSYSTEMS ids in subsystems.ts */
  id: string
  /** Node box position and size (SVG coord space). */
  x: number
  y: number
  w: number
  h: number
  /** Upper-case label (first line). */
  label: string
  /** Optional second label line (e.g. "/ PMS"). */
  label2?: string
  /** TickPayload field name providing the live MW value. Undefined = no MW display. */
  mwField?: string
  /**
   * Static MW shown at rest (no tick).  When tick is null this value is used
   * instead of "—" so the diagram reflects configured site capacity.
   * Example: Solar PV = 4.99 (always producing); turbine/BESS/loads = 0.
   */
  staticMW?: number
  /** Whether clicking this node opens a modal or navigates. */
  clickable: boolean
  /**
   * If set, clicking opens the SubsystemModal for this id.
   * Overridden by tabRoute (switchgear navigates, no modal).
   */
  modalId?: string
  /** If set, clicking navigates to this tab page instead of a modal. */
  tabRoute?: string
  /** Distribution and PDU are purely passive (no click at all). */
  passive?: boolean
  /** Grid connection is always dashed + grey — islanded by design. */
  gridStyle?: boolean
  /** Accent colour for the node border and MW value. */
  accentColor: string
}

/** One flow line connecting two positions. */
export interface FlowDef {
  id: string
  /** SVG path `d` attribute. */
  d: string
  /** TickPayload field name for the live MW value. Undefined = static zero. */
  mwField?: string
  /**
   * Static MW used at rest (no tick).  Set this to make a flow visibly active
   * before any run starts.  Solar uses 4.99 — it is the one real pre-run flow.
   */
  staticMW?: number
  /** Reference MW for stroke-width scaling (strokeWidth at maxMW ≈ 9). */
  maxMW: number
  /** Stroke colour when the flow is active (mwValue > 0). */
  color: string
  /** Grid connection — always dashed, always grey. */
  isGrid?: boolean
  /** Optional arrowhead marker id. */
  marker?: 'arrow-teal' | 'arrow-grey'
}

// ─── Node definitions ────────────────────────────────────────────────────────

/**
 * Source column nodes (right side, stacked vertically).
 * Each is w=155, h=72.  Left-centre x=1045.
 */
export const NODES: NodeDef[] = [
  {
    id: 'gas-turbine',
    x: 1045, y: 10, w: 155, h: 88,
    label: 'GAS TURBINE', label2: 'FLEET',
    // Algebraic formula: P_fleet = Σ_{i ∈ A} p_i where A = {SYNCHRONISED, UNLOADING} (is_on_bus).
    // Phase C D-05: on_bus_output_mw — renamed from synchronised_output_mw.
    // Includes UNLOADING units so the tile always matches the per-unit row sum.
    mwField: 'on_bus_output_mw',
    staticMW: 0,   // at rest: standby, 0 MW
    clickable: true, modalId: 'gas-turbine-fleet',
    accentColor: '#e0a458',
  },
  {
    id: 'solar-pv',
    x: 1045, y: 110, w: 155, h: 72,
    label: 'SOLAR PV',
    mwField: 'p_renewable_mw',
    staticMW: 4.99,  // always producing before any run starts
    clickable: true, modalId: 'renewable',
    accentColor: '#f2c94c',
  },
  {
    id: 'battery-bess',
    x: 1045, y: 210, w: 155, h: 72,
    label: 'BATTERY', label2: '(BESS)',
    mwField: 'bess_output_mw',
    staticMW: 0,   // at rest: armed, not discharging
    clickable: true, modalId: 'storage',
    accentColor: '#4a9fe0',
  },
  {
    id: 'grid-connection',
    x: 1045, y: 310, w: 155, h: 72,
    label: 'GRID', label2: 'CONNECTION',
    // Positive-direction meter value; importing power is shown as a positive MW draw.
    mwField: 'grid_import_mw',
    staticMW: 0,
    clickable: true, modalId: 'grid',
    accentColor: '#3fb6a8',
  },
  // ─── Bus / chain nodes ────────────────────────────────────────────────────
  {
    id: 'switchgear-pms',
    x: 840, y: 172, w: 150, h: 98,
    label: 'SWITCHGEAR', label2: '/ PMS',
    clickable: true, tabRoute: 'overview',
    accentColor: '#3fb6a8',
  },
  {
    id: 'distribution',
    x: 685, y: 186, w: 118, h: 70,
    label: 'DISTRIBUTION',
    clickable: false, passive: true,
    accentColor: '#5a6673',
  },
  {
    id: 'pdu-rpp',
    x: 530, y: 186, w: 118, h: 70,
    label: 'PDU / RPP',
    clickable: false, passive: true,
    accentColor: '#5a6673',
  },
  // ─── Load nodes ───────────────────────────────────────────────────────────
  {
    id: 'compute-racks',
    x: 319, y: 62, w: 165, h: 188,
    label: 'GPU COLO CENTER',
    mwField: 'p_compute_mw',
    staticMW: 0,   // at rest: nodes idle, 0 MW
    clickable: true, modalId: 'compute',
    accentColor: '#3fb6a8',
  },
  {
    id: 'cooling-plant',
    x: 319, y: 278, w: 165, h: 100,
    label: 'COOLING PLANT',
    mwField: 'p_cooling_mw',
    staticMW: 0,   // at rest: lags compute, 0 MW
    clickable: true, modalId: 'thermal',
    accentColor: '#4a9fe0',
  },
]

// ─── Derived anchor points ────────────────────────────────────────────────────

/** Convenience anchor-point helpers for diagram nodes. */
export function nodeRightCentre(n: NodeDef): [number, number] {
  return [n.x + n.w, n.y + n.h / 2]
}
export function nodeLeftCentre(n: NodeDef): [number, number] {
  return [n.x, n.y + n.h / 2]
}
export function nodeBottomCentre(n: NodeDef): [number, number] {
  return [n.x + n.w / 2, n.y + n.h]
}
export function nodeTopCentre(n: NodeDef): [number, number] {
  return [n.x + n.w / 2, n.y]
}

// ─── Flow definitions ────────────────────────────────────────────────────────

/** Switchgear right-centre in the mirrored flow coordinate system. */
const SW_IN_X = 990
const SW_IN_Y = 221  // y=172 + h=98/2 = 221

// Source → switchgear cubic bezier paths
// Mirrored from the original paths: curves bow left and arrive at the
// switchgear right edge horizontally.
const GAS_RC: [number, number]    = [1045, 46]   // leftCentre of gas turbine
const SOLAR_RC: [number, number]  = [1045, 146]  // leftCentre of solar pv
const BATT_RC: [number, number]   = [1045, 246]  // leftCentre of battery
const GRID_RC: [number, number]   = [1045, 346]  // leftCentre of grid

function srcPath(sx: number, sy: number): string {
  const cx1 = sx - 36
  const cx2 = SW_IN_X + 14
  return `M${sx},${sy} C${cx1},${sy} ${cx2},${SW_IN_Y} ${SW_IN_X},${SW_IN_Y}`
}

// Switchgear left: x=840, right-centre x=990, y=221
// Distribution left: x=685, y=221  right: x=803, y=221
// PDU left: x=530, y=221  right: x=648, y=221
// Compute right-centre: x=484, y=136 (y=62 + h=148/2)
// Compute bottom-centre: x=401.5, y=210 (y=62+h=148)
// Cooling top-centre: x=401.5, y=278

const COMP_LEFT_Y = 62 + 148 / 2  // = 136
const COMP_BTM_Y  = 62 + 148       // = 210
const COOL_TOP_Y  = 278
const COMP_X_MID  = 319 + 165 / 2  // = 401.5

export const FLOWS: FlowDef[] = [
  {
    id: 'gas-to-sw',
    d: srcPath(...GAS_RC),
    mwField: 'on_bus_output_mw',
    staticMW: 0,
    maxMW: 25,
    color: '#e0a458',
  },
  {
    id: 'solar-to-sw',
    d: srcPath(...SOLAR_RC),
    mwField: 'p_renewable_mw',
    staticMW: 4.99,  // solar is the one live flow before a run — gold + animated
    maxMW: 5,
    color: '#f2c94c',
  },
  {
    id: 'battery-to-sw',
    d: srcPath(...BATT_RC),
    mwField: 'bess_output_mw',
    maxMW: 4,
    color: '#4a9fe0',
  },
  {
    id: 'grid-to-sw',
    d: srcPath(...GRID_RC),
    maxMW: 1,
    color: '#5a6673',
    isGrid: true,
  },
  {
    id: 'sw-to-dist',
    d: `M840,${SW_IN_Y} L803,${SW_IN_Y}`,
    mwField: 'p_total_mw',
    maxMW: 30,
    color: '#3fb6a8',
  },
  {
    id: 'dist-to-pdu',
    d: `M685,${SW_IN_Y} L648,${SW_IN_Y}`,
    mwField: 'p_total_mw',
    maxMW: 30,
    color: '#3fb6a8',
  },
  {
    id: 'pdu-to-compute',
    // Mirrored L-turn: left to elbow at x=505, then up to compute right-centre
    d: `M530,${SW_IN_Y} L505,${SW_IN_Y} L505,${COMP_LEFT_Y} L484,${COMP_LEFT_Y}`,
    mwField: 'p_compute_mw',
    maxMW: 25,
    color: '#3fb6a8',
  },
  {
    id: 'compute-to-cooling',
    d: `M${COMP_X_MID},${COMP_BTM_Y} L${COMP_X_MID},${COOL_TOP_Y}`,
    mwField: 'p_cooling_mw',
    maxMW: 6,
    color: '#4a9fe0',
    marker: 'arrow-teal',
  },
]

/**
 * Fuel Cell Module Array node — conditionally rendered in PlantDiagram when the
 * selected scenario has fuel_cell_enabled: true.  Exported separately so the
 * diagram can add it only when relevant without reserving a permanent empty slot.
 *
 * Position: below grid-connection (y=310+72=382 → start at 392).
 * Accent: hydrogen green (#3fd490) to distinguish from teal BESS.
 */
export const FUEL_CELL_NODE: NodeDef = {
  id: 'fuel-cell',
  x: 1045, y: 392, w: 155, h: 72,
  label: 'FUEL CELL', label2: 'MODULE ARRAY',
  // mwField wired so the tile shows a live MW number and lights up when dispatching.
  mwField: 'fuel_cell_output_mw',
  staticMW: 0,
  clickable: true,
  accentColor: '#3fd490',
}

// Left-centre of the fuel-cell node (x=1045, y=392+72/2=428)
const FUEL_RC: [number, number] = [1045, 428]

export const FUEL_CELL_FLOW: FlowDef = {
  id: 'fuel-cell-to-sw',
  d: srcPath(...FUEL_RC),
  // mwField wired so the flow line animates proportionally to FC output.
  // maxMW raised to match the scenario's 20 MW single-stack rated capacity.
  mwField: 'fuel_cell_output_mw',
  maxMW: 20,
  color: '#3fd490',
}

/**
 * Diesel Generation node — conditionally rendered when the selected scenario
 * has diesel_power_block.enabled: true.  It follows the optional Fuel Cell
 * node pattern rather than reserving a permanent empty tile.
 *
 * Accent: emergency orange (#f0883e), distinct from turbine/fuel-cell amber.
 */
export const DIESEL_NODE: NodeDef = {
  id: 'diesel-generator',
  x: 1045, y: 464, w: 155, h: 72,
  label: 'DIESEL', label2: 'FINAL RESERVE',
  mwField: 'diesel_output_mw',
  staticMW: 0,
  clickable: true,
  modalId: 'diesel-generator',
  accentColor: '#f0883e',
}

const DIESEL_RC: [number, number] = [1045, 500]

export const DIESEL_FLOW: FlowDef = {
  id: 'diesel-to-sw',
  d: srcPath(...DIESEL_RC),
  mwField: 'diesel_output_mw',
  maxMW: 25,
  color: '#f0883e',
}

/** Lead-time callout box geometry (rendered as HTML foreignObject). */
export const LEADTIME_BOX = {
  x: 10, y: 62, w: 280, h: 310,
}

/** Always-visible headline timer strip, below the row and existing overlays. */
export const JOB_SIGNAL_TIMER_BOX = {
  x: 10, y: 404, w: 580, h: 64,
}

export const TURBINE_ONLINE_TIMER_BOX = {
  x: 610, y: 404, w: 580, h: 64,
}

/**
 * "What you are watching / demonstrates" copy box.
 * Centred in the gap between Compute Racks right edge (x=484) and
 * Gas Turbine left edge (x=1045), above the Switchgear row (y=172).
 */
export const WATCHING_BOX = {
  x: 530, y: 10, w: 460, h: 155,
}
