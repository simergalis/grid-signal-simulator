/**
 * gpu_queue_tab.test.ts — Queue tab logic and tile→tab routing.
 *
 * Covers the three areas flagged as untested after JOBQ-001 Part 3:
 *
 *   QQ-1  Sort order — compareByQueuedSince puts longest-waiting-first
 *          (ascending queued_since_s).
 *
 *   QQ-2  fmtQueueWait — format function across sub-minute, exact-minute,
 *          and over-minute cases; negative input guard.
 *
 *   QQ-3  queueWaitColour — boundary behaviour at the two PROPOSED_HERE
 *          thresholds (30 s and 120 s).  Strictly-greater-than contract:
 *            29.9  → teal   (below amber threshold)
 *            30.0  → teal   (exactly at threshold — NOT amber)
 *            30.1  → amber  (strictly above threshold)
 *           119.9  → amber  (below red threshold)
 *           120.0  → amber  (exactly at threshold — NOT red)
 *           120.1  → red    (strictly above threshold)
 *
 *   QQ-4  Tile→tab routing — the "Requeued (cap hold)" stat row in the
 *          Compute panel always carries an onClick handler; calling it
 *          invokes useGpuGeneratorStore.getState().setOpenGeneratorAtTab
 *          with the string 'queue'.
 */

import { vi, describe, it, expect, beforeEach } from 'vitest'

// ── Mock setup (hoisted above imports by vitest) ──────────────────────────────

const { mockSetOpenGeneratorAtTab } = vi.hoisted(() => ({
  mockSetOpenGeneratorAtTab: vi.fn(),
}))

vi.mock('../store/gpuGeneratorStore', () => ({
  useGpuGeneratorStore: Object.assign(
    vi.fn(() => ({})),
    { getState: () => ({ setOpenGeneratorAtTab: mockSetOpenGeneratorAtTab }) },
  ),
}))

// ── Imports ───────────────────────────────────────────────────────────────────

import {
  compareByQueuedSince,
  fmtQueueWait,
  queueWaitColour,
  QUEUE_WAIT_AMBER_THRESHOLD_S,
  QUEUE_WAIT_RED_THRESHOLD_S,
} from '../opening/queueUtils'
import { computePanel } from '../subsystem/panels/compute'
import type { TickPayload, KubeMetrics, QueuedJobSummary } from '../types'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeQueuedJob(overrides: Partial<QueuedJobSummary> = {}): QueuedJobSummary {
  return {
    event_id:       'job-x',
    scheduler_type: 'B',
    tenant_id:      'B',
    node_count:     10,
    est_draw_mw:    0.102,
    status:         'QUEUED',
    queued_since_s: 0,
    requeue_count:  0,
    ...overrides,
  }
}

function makeKube(overrides: Partial<KubeMetrics> = {}): KubeMetrics {
  return {
    utilization:         0.5,
    node_count:          1900,
    power_cap_active:    false,
    headroom_mw:         200,
    active_jobs:         3,
    admitted_nodes:      950,
    queued_jobs:         0,
    queued_nodes:        0,
    arrivals_this_tick:  0,
    requeued_this_tick:  0,
    pending_jobs:        [],
    active_jobs_detail:  [],
    ...overrides,
  }
}

function makeTick(overrides: Partial<TickPayload> = {}): TickPayload {
  return {
    run_id:                     'qq-test',
    tick_index:                 1,
    sim_time_seconds:           5.0,
    p_compute_mw:               10.0,
    p_cooling_mw:               2.0,
    p_total_mw:                 12.0,
    net_demand_mw:              7.0,
    turbine_output_mw:          9.0,
    bess_output_mw:             0.0,
    bess_soc_fraction:          0.95,
    confidence_lower_mw:        10.0,
    confidence_upper_mw:        14.0,
    forecast_mw:                12.0,
    bess_setpoint_mw:           0.0,
    frequency_hz:               60.0,
    frequency_nominal_hz:       60.0,
    protection_provisional:     false,
    data_quality_tags:          [],
    p_renewable_mw:             5.0,
    bess_bridging_seconds:      3600,
    bridging_basis:             'predicted_peak',
    dt_lead_next_s:             0.0,
    insufficient_reserve_alert: false,
    checkpoint_states:          {},
    rated_cooling_mw:           4.0,
    absorbable_mw:              4.0,
    time_to_limit_s:            86400,
    approach_rate_mw_s:         0.0,
    turbine_units:              [],
    kube_metrics:               makeKube(),
    ...overrides,
  } as unknown as TickPayload
}

// ── QQ-1  Sort order ──────────────────────────────────────────────────────────

describe('QQ-1  compareByQueuedSince — longest-waiting-first sort', () => {

  it('sorts ascending on queued_since_s (earlier sim-time first)', () => {
    const jobs = [
      makeQueuedJob({ event_id: 'late',    queued_since_s: 120 }),
      makeQueuedJob({ event_id: 'early',   queued_since_s:  10 }),
      makeQueuedJob({ event_id: 'middle',  queued_since_s:  60 }),
    ]
    const sorted = [...jobs].sort(compareByQueuedSince)
    expect(sorted.map(j => j.event_id)).toEqual(['early', 'middle', 'late'])
  })

  it('is stable for equal timestamps (insertion order preserved)', () => {
    const jobs = [
      makeQueuedJob({ event_id: 'A', queued_since_s: 50 }),
      makeQueuedJob({ event_id: 'B', queued_since_s: 50 }),
    ]
    const sorted = [...jobs].sort(compareByQueuedSince)
    // comparator returns 0 for ties; Array.prototype.sort is stable in V8
    expect(sorted.map(j => j.event_id)).toEqual(['A', 'B'])
  })

  it('handles a single-element list without error', () => {
    const jobs = [makeQueuedJob({ queued_since_s: 42 })]
    expect([...jobs].sort(compareByQueuedSince)).toHaveLength(1)
  })

  it('handles an empty list without error', () => {
    expect([].sort(compareByQueuedSince)).toHaveLength(0)
  })

})

// ── QQ-2  fmtQueueWait ────────────────────────────────────────────────────────

describe('QQ-2  fmtQueueWait — wait duration formatting', () => {

  it('returns "—" for negative durations', () => {
    expect(fmtQueueWait(-1)).toBe('—')
    expect(fmtQueueWait(-0.001)).toBe('—')
  })

  it('returns "0s" for zero', () => {
    expect(fmtQueueWait(0)).toBe('0s')
  })

  it('formats whole seconds under one minute', () => {
    expect(fmtQueueWait(1)).toBe('1s')
    expect(fmtQueueWait(29)).toBe('29s')
    expect(fmtQueueWait(59)).toBe('59s')
  })

  it('truncates (floors) fractional seconds', () => {
    expect(fmtQueueWait(29.9)).toBe('29s')
    expect(fmtQueueWait(59.99)).toBe('59s')
  })

  it('formats exactly 60 s as "1m" with no seconds component', () => {
    expect(fmtQueueWait(60)).toBe('1m')
  })

  it('formats minutes with a non-zero seconds remainder', () => {
    expect(fmtQueueWait(61)).toBe('1m 1s')
    expect(fmtQueueWait(90)).toBe('1m 30s')
    expect(fmtQueueWait(125)).toBe('2m 5s')
  })

  it('omits the seconds component when remainder is 0', () => {
    expect(fmtQueueWait(120)).toBe('2m')
    expect(fmtQueueWait(180)).toBe('3m')
  })

})

// ── QQ-3  queueWaitColour — boundary behaviour ────────────────────────────────

describe(`QQ-3  queueWaitColour — thresholds at ${QUEUE_WAIT_AMBER_THRESHOLD_S}s / ${QUEUE_WAIT_RED_THRESHOLD_S}s (PROPOSED_HERE)`, () => {

  // Colours returned
  const TEAL  = '#3fb6a8'
  const AMBER = '#f0883e'
  const RED   = '#f85149'

  // ── Amber boundary (30 s) ─────────────────────────────────────────────────

  it('29.9 s → teal (below amber threshold)', () => {
    expect(queueWaitColour(29.9)).toBe(TEAL)
  })

  it('30.0 s → teal (exactly at amber threshold — NOT amber; boundary is exclusive)', () => {
    expect(queueWaitColour(QUEUE_WAIT_AMBER_THRESHOLD_S)).toBe(TEAL)
  })

  it('30.1 s → amber (strictly above amber threshold)', () => {
    expect(queueWaitColour(30.1)).toBe(AMBER)
  })

  // ── Red boundary (120 s) ──────────────────────────────────────────────────

  it('119.9 s → amber (below red threshold)', () => {
    expect(queueWaitColour(119.9)).toBe(AMBER)
  })

  it('120.0 s → amber (exactly at red threshold — NOT red; boundary is exclusive)', () => {
    expect(queueWaitColour(QUEUE_WAIT_RED_THRESHOLD_S)).toBe(AMBER)
  })

  it('120.1 s → red (strictly above red threshold)', () => {
    expect(queueWaitColour(120.1)).toBe(RED)
  })

  // ── Interior / extreme values ─────────────────────────────────────────────

  it('0 s → teal', () => {
    expect(queueWaitColour(0)).toBe(TEAL)
  })

  it('very large wait → red', () => {
    expect(queueWaitColour(3600)).toBe(RED)
  })

})

// ── QQ-4  Tile→tab routing ────────────────────────────────────────────────────

describe('QQ-4  Compute panel tile→tab routing', () => {

  beforeEach(() => {
    mockSetOpenGeneratorAtTab.mockClear()
  })

  it('"Requeued (cap hold)" row has an onClick handler when kube metrics are present', () => {
    const tick = makeTick({ kube_metrics: makeKube({ requeued_this_tick: 2 }) })
    const data = computePanel.deriveData(tick, false, [])
    const row = data.statRows.find(r => r.label === 'Requeued (cap hold)')

    expect(row).toBeDefined()
    expect(row?.onClick).toBeTypeOf('function')
  })

  it('calling onClick invokes setOpenGeneratorAtTab("queue")', () => {
    const tick = makeTick({ kube_metrics: makeKube({ requeued_this_tick: 1 }) })
    const data = computePanel.deriveData(tick, false, [])
    const row = data.statRows.find(r => r.label === 'Requeued (cap hold)')

    row!.onClick!()

    expect(mockSetOpenGeneratorAtTab).toHaveBeenCalledOnce()
    expect(mockSetOpenGeneratorAtTab).toHaveBeenCalledWith('queue')
  })

  it('onClick is present even when requeued_this_tick is 0 (row always wired)', () => {
    // The row is always in the statRows array; the colour changes but the
    // onClick must not be conditional on the value being > 0.
    const tick = makeTick({ kube_metrics: makeKube({ requeued_this_tick: 0 }) })
    const data = computePanel.deriveData(tick, false, [])
    const row = data.statRows.find(r => r.label === 'Requeued (cap hold)')

    expect(row?.onClick).toBeTypeOf('function')
  })

  it('"Requeued" row is absent when kube_metrics is null', () => {
    const tick = makeTick({ kube_metrics: null })
    const data = computePanel.deriveData(tick, false, [])
    const row = data.statRows.find(r => r.label === 'Requeued (cap hold)')
    expect(row).toBeUndefined()
  })

})
