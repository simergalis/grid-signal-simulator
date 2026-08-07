/**
 * plantLayout.ts — geometry data for the one-line plant mimic diagram.
 *
 * All coordinates are in the SVG viewBox space: 0 0 1200 440.
 * The diagram SVG uses preserveAspectRatio="xMidYMid meet" so it scales
 * proportionally with the container and remains correct at all widths ≥ 768 px.
 *
 * Positions were derived from the gs-01-opening-rest.svg design file.
 */

export const DIAGRAM_W = 1200
// Height trimmed to actual content bottom (grid-connection y=310+h=72=382) + 8px margin.
// Reduces dead space below the nodes without clipping any element.
export const DIAGRAM_H = 390

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
 * Source column nodes (left side, stacked vertically).
 * Each is w=155, h=72.  Right-centre x=155.
 */
export const NODES: NodeDef[] = [
  {
    id: 'gas-turbine',
    x: 0, y: 10, w: 155, h: 72,
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
    x: 0, y: 110, w: 155, h: 72,
    label: 'SOLAR PV',
    mwField: 'p_renewable_mw',
    staticMW: 4.99,  // always producing before any run starts
    clickable: true, modalId: 'renewable',
    accentColor: '#f2c94c',
  },
  {
    id: 'battery-bess',
    x: 0, y: 210, w: 155, h: 72,
    label: 'BATTERY', label2: '(BESS)',
    mwField: 'bess_output_mw',
    staticMW: 0,   // at rest: armed, not discharging
    clickable: true, modalId: 'storage',
    accentColor: '#4a9fe0',
  },
  {
    id: 'grid-connection',
    x: 0, y: 310, w: 155, h: 72,
    label: 'GRID', label2: 'CONNECTION',
    // Grid is always 0 MW — islanded by design
    clickable: true, modalId: 'grid',
    gridStyle: true,
    accentColor: '#5a6673',
  },
  // ─── Bus / chain nodes ────────────────────────────────────────────────────
  {
    id: 'switchgear-pms',
    x: 210, y: 172, w: 150, h: 98,
    label: 'SWITCHGEAR', label2: '/ PMS',
    clickable: true, tabRoute: 'overview',
    accentColor: '#3fb6a8',
  },
  {
    id: 'distribution',
    x: 397, y: 186, w: 118, h: 70,
    label: 'DISTRIBUTION',
    clickable: false, passive: true,
    accentColor: '#5a6673',
  },
  {
    id: 'pdu-rpp',
    x: 552, y: 186, w: 118, h: 70,
    label: 'PDU / RPP',
    clickable: false, passive: true,
    accentColor: '#5a6673',
  },
  // ─── Load nodes ───────────────────────────────────────────────────────────
  {
    id: 'compute-racks',
    x: 716, y: 62, w: 165, h: 90,
    label: 'COMPUTE RACKS',
    mwField: 'p_compute_mw',
    staticMW: 0,   // at rest: nodes idle, 0 MW
    clickable: true, modalId: 'compute',
    accentColor: '#3fb6a8',
  },
  {
    id: 'cooling-plant',
    x: 716, y: 278, w: 165, h: 78,
    label: 'COOLING PLANT',
    mwField: 'p_cooling_mw',
    staticMW: 0,   // at rest: lags compute, 0 MW
    clickable: true, modalId: 'thermal',
    accentColor: '#4a9fe0',
  },
]

// ─── Derived anchor points ────────────────────────────────────────────────────

/** Convenience: right-centre of each left-column source. */
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

/** Switchgear left-centre in the flow coordinate system. */
const SW_IN_X = 210
const SW_IN_Y = 221  // y=172 + h=98/2 = 221

// Source → switchgear cubic bezier paths
// Curve bows right then arrives at the switchgear left edge horizontally.
const GAS_RC: [number, number]    = [155, 46]   // rightCentre of gas turbine
const SOLAR_RC: [number, number]  = [155, 146]  // rightCentre of solar pv
const BATT_RC: [number, number]   = [155, 246]  // rightCentre of battery
const GRID_RC: [number, number]   = [155, 346]  // rightCentre of grid

function srcPath(sx: number, sy: number): string {
  const cx1 = sx + 36
  const cx2 = SW_IN_X - 14
  return `M${sx},${sy} C${cx1},${sy} ${cx2},${SW_IN_Y} ${SW_IN_X},${SW_IN_Y}`
}

// Switchgear right: x=360, y=221
// Distribution left: x=397, y=221  right: x=515, y=221
// PDU left: x=552, y=221  right: x=670, y=221
// Compute left-centre: x=716, y=107 (y=62 + h=90/2)
// Compute bottom-centre: x=798.5, y=152 (y=62+h=90)
// Cooling top-centre: x=798.5, y=278

const COMP_LEFT_Y = 62 + 90 / 2   // = 107
const COMP_BTM_Y  = 62 + 90        // = 152
const COOL_TOP_Y  = 278
const COMP_X_MID  = 716 + 165 / 2  // = 798.5

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
    d: `M360,${SW_IN_Y} L397,${SW_IN_Y}`,
    mwField: 'p_total_mw',
    maxMW: 30,
    color: '#3fb6a8',
  },
  {
    id: 'dist-to-pdu',
    d: `M515,${SW_IN_Y} L552,${SW_IN_Y}`,
    mwField: 'p_total_mw',
    maxMW: 30,
    color: '#3fb6a8',
  },
  {
    id: 'pdu-to-compute',
    // L-turn: right to elbow at x=695, then up to compute left-centre
    d: `M670,${SW_IN_Y} L695,${SW_IN_Y} L695,${COMP_LEFT_Y} L716,${COMP_LEFT_Y}`,
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

/** Lead-time callout box geometry (rendered as HTML foreignObject). */
export const LEADTIME_BOX = {
  x: 910, y: 62, w: 280, h: 230,
}

/**
 * "What you are watching / demonstrates" copy box.
 * Centred in the gap between Gas Turbine right edge (x=155) and
 * Compute Racks left edge (x=716), above the Switchgear row (y=172).
 */
export const WATCHING_BOX = {
  x: 210, y: 0, w: 460, h: 198,
}
