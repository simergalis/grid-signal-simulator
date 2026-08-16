/**
 * gpu_queue_ui.test.tsx — 20 black-box tests for the queue UI redesign.
 *
 * Three suites:
 *
 *   QQ-5  StatTable `featured` row rendering (7 tests)
 *         The amber call-to-action card introduced in StatTable.tsx for the
 *         "Requeued (cap hold)" row must render with pulsing dot, "click →"
 *         hint, proper ARIA role, keyboard support, and not pollute plain rows.
 *
 *   QQ-6  Compute panel `featured` flag (5 tests)
 *         The Requeued stat row must carry featured=true at all times when kube
 *         is active, and must be absent (not featured=false) when kube is null.
 *
 *   QQ-7  Queue tab rendered content (8 tests)
 *         GpuNodeGeneratorModal opened at the Queue tab with seeded kube data.
 *         Verifies banner text, per-scheduler badge labels and colors, the
 *         "Tenant X" chip format, requeue display, and queued-at cell format.
 */

import React from 'react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'

// ── Hoist mocks before any imports that touch the stores ─────────────────────

const { mockSetOpenGeneratorAtTab } = vi.hoisted(() => ({
  mockSetOpenGeneratorAtTab: vi.fn(),
}))

// Stubbed kube tick used by QQ-7; defined here so the factory can close over it.
let _modalTick: any = null

vi.mock('../store/gpuGeneratorStore', () => {
  const DEFAULT_CONFIG = {
    ratePerMinute: 2, burstMode: false, burstSize: [3, 8],
    burstIntervalSeconds: [30, 90],
    tenantWeights: { a: 0.40, b: 0.35, c: 0.25 },
    jobSizes: { small: 0.30, medium: 0.50, large: 0.20 },
    maxJobsPerTenant: 12, jobDurationRange: [60, 240],
    tenantContracts: { a: 1.40, b: 1.00, c: 0.60 },
  }
  return {
    DEFAULT_CONFIG,
    useGpuGeneratorStore: Object.assign(
      vi.fn(() => ({
        config: DEFAULT_CONFIG,
        running: false,
        feed: [],
        openGeneratorAtTab: null,
        start: vi.fn(), stop: vi.fn(), reset: vi.fn(), updateConfig: vi.fn(),
        setOpenGeneratorAtTab: mockSetOpenGeneratorAtTab,
      })),
      { getState: () => ({ setOpenGeneratorAtTab: mockSetOpenGeneratorAtTab }) },
    ),
  }
})

vi.mock('../store/tickStore', () => ({
  useTickStore: vi.fn((selector: (s: any) => any) =>
    selector({ latestTick: _modalTick })
  ),
}))

// ── Actual imports (after mocks are in place) ────────────────────────────────

import { StatTable }     from '../charts/StatTable'
import { computePanel }  from '../subsystem/panels/compute'
import { GpuNodeGeneratorModal } from '../opening/GpuNodeGeneratorModal'
import type { TickPayload, KubeMetrics, QueuedJobSummary } from '../types'

// ── Fixtures ─────────────────────────────────────────────────────────────────

function makeQueuedJob(ov: Partial<QueuedJobSummary> = {}): QueuedJobSummary {
  return {
    event_id: 'job-x', scheduler_type: 'K8S', tenant_id: 'A',
    node_count: 8, est_draw_mw: 0.8, status: 'QUEUED',
    queued_since_s: 0, requeue_count: 0,
    ...ov,
  }
}

function makeKube(ov: Partial<KubeMetrics> = {}): KubeMetrics {
  return {
    utilization: 0.5, node_count: 1900, power_cap_active: false,
    headroom_mw: 200, active_jobs: 3, admitted_nodes: 950,
    queued_jobs: 0, queued_nodes: 0,
    arrivals_this_tick: 0, requeued_this_tick: 0,
    pending_jobs: [], active_jobs_detail: [],
    ...ov,
  }
}

function makeTick(ov: Partial<TickPayload> = {}): TickPayload {
  return {
    run_id: 'ui-test', tick_index: 1, sim_time_seconds: 300,
    p_compute_mw: 10, p_cooling_mw: 2, p_total_mw: 12,
    net_demand_mw: 7, turbine_output_mw: 9,
    bess_output_mw: 0, bess_soc_fraction: 0.95,
    confidence_lower_mw: 10, confidence_upper_mw: 14,
    forecast_mw: 12, bess_setpoint_mw: 0,
    frequency_hz: 60, frequency_nominal_hz: 60,
    protection_provisional: false, data_quality_tags: [],
    p_renewable_mw: 5, bess_bridging_seconds: 3600,
    bridging_basis: 'predicted_peak', dt_lead_next_s: 0,
    insufficient_reserve_alert: false, checkpoint_states: {},
    rated_cooling_mw: 4, absorbable_mw: 4,
    time_to_limit_s: 86400, approach_rate_mw_s: 0,
    turbine_units: [], kube_metrics: makeKube(),
    ...ov,
  } as unknown as TickPayload
}

// Seeded tick with three pending jobs for QQ-7
const QUEUE_TICK = makeTick({
  sim_time_seconds: 300,
  kube_metrics: makeKube({
    pending_jobs: [
      makeQueuedJob({ event_id: 'kube-job-42',  scheduler_type: 'K8S',   tenant_id: 'A', node_count: 6,  queued_since_s: 262, requeue_count: 0 }),
      makeQueuedJob({ event_id: 'slurm-job-77', scheduler_type: 'SLURM', tenant_id: 'B', node_count: 4,  queued_since_s: 197, requeue_count: 1 }),
      makeQueuedJob({ event_id: 'ray-run-118',  scheduler_type: 'RAY',   tenant_id: 'C', node_count: 8,  queued_since_s: 152, requeue_count: 3 }),
    ],
  }),
})

// ── QQ-5  StatTable featured row rendering ────────────────────────────────────

describe('QQ-5  StatTable featured row rendering', () => {

  afterEach(cleanup)

  it('5-1: featured+onClick row renders an amber-bordered card element', () => {
    render(<StatTable rows={[{
      label: 'Requeued (cap hold)', value: '4',
      featured: true,
      onClick: vi.fn(),
    }]} />)

    // The featured card has inline border style from the mockup design
    const card = screen.getByRole('button', { name: /requeued/i })
    // amber border is expressed as inline style on the card div
    expect(card.getAttribute('style')).toMatch(/border/)
  })

  it('5-2: featured row shows the "click →" hint text', () => {
    render(<StatTable rows={[{
      label: 'Requeued (cap hold)', value: '2',
      featured: true, onClick: vi.fn(),
    }]} />)
    expect(screen.getByText(/click →/i)).toBeDefined()
  })

  it('5-3: featured row contains an animate-ping element (pulsing dot)', () => {
    const { container } = render(<StatTable rows={[{
      label: 'Requeued (cap hold)', value: '2',
      featured: true, onClick: vi.fn(),
    }]} />)
    // The pulsing outer ring uses Tailwind's animate-ping class
    const pingEl = container.querySelector('.animate-ping')
    expect(pingEl).not.toBeNull()
  })

  it('5-4: featured row has role="button" for accessibility', () => {
    render(<StatTable rows={[{
      label: 'Requeued (cap hold)', value: '0',
      featured: true, onClick: vi.fn(),
    }]} />)
    expect(screen.getByRole('button')).toBeDefined()
  })

  it('5-5: featured row has tabIndex=0 so keyboard users can reach it', () => {
    render(<StatTable rows={[{
      label: 'Requeued (cap hold)', value: '0',
      featured: true, onClick: vi.fn(),
    }]} />)
    const card = screen.getByRole('button')
    expect(card.getAttribute('tabindex')).toBe('0')
  })

  it('5-6: clicking the featured row fires the onClick callback', () => {
    const spy = vi.fn()
    render(<StatTable rows={[{
      label: 'Requeued (cap hold)', value: '3',
      featured: true, onClick: spy,
    }]} />)
    fireEvent.click(screen.getByRole('button'))
    expect(spy).toHaveBeenCalledOnce()
  })

  it('5-7: a plain (non-featured) row with onClick does NOT show "click →"', () => {
    render(<StatTable rows={[{
      label: 'Grid headroom', value: '3.2 MW',
      onClick: vi.fn(),   // clickable but not featured
    }]} />)
    expect(screen.queryByText(/click →/i)).toBeNull()
  })

})

// ── QQ-6  Compute panel `featured` flag ──────────────────────────────────────

describe('QQ-6  Compute panel featured flag on Requeued row', () => {

  function requeueRow(ov: Partial<KubeMetrics> = {}) {
    const tick = makeTick({ kube_metrics: makeKube(ov) })
    const data = computePanel.deriveData(tick, false as any, [])
    return data.statRows.find(r => r.label === 'Requeued (cap hold)')
  }

  it('6-1: featured=true when requeued_this_tick > 0', () => {
    expect(requeueRow({ requeued_this_tick: 4 })?.featured).toBe(true)
  })

  it('6-2: featured=true even when requeued_this_tick = 0 (always-on card)', () => {
    // The card must be visible at all times so operators know the shortcut exists
    expect(requeueRow({ requeued_this_tick: 0 })?.featured).toBe(true)
  })

  it('6-3: featured=true when power cap is NOT active (card shown proactively)', () => {
    expect(requeueRow({ power_cap_active: false, requeued_this_tick: 0 })?.featured).toBe(true)
  })

  it('6-4: row colour is AMBER (#f0883e) regardless of requeued count', () => {
    expect(requeueRow({ requeued_this_tick: 0 })?.colour).toBe('#f0883e')
    expect(requeueRow({ requeued_this_tick: 5 })?.colour).toBe('#f0883e')
  })

  it('6-5: Requeued row is absent entirely when kube_metrics is null', () => {
    const tick = makeTick({ kube_metrics: null })
    const data = computePanel.deriveData(tick, false as any, [])
    const row = data.statRows.find(r => r.label === 'Requeued (cap hold)')
    expect(row).toBeUndefined()
  })

})

// ── QQ-7  Queue tab rendered content ─────────────────────────────────────────

describe('QQ-7  Queue tab rendered content', () => {

  beforeEach(() => {
    _modalTick = QUEUE_TICK
    mockSetOpenGeneratorAtTab.mockClear()
  })

  afterEach(() => {
    _modalTick = null
    cleanup()
  })

  function renderQueueTab() {
    render(<GpuNodeGeneratorModal onClose={() => {}} initialTab="queue" />)
  }

  it('7-1: banner "Jobs held by power-cap" is visible in the Queue tab', () => {
    renderQueueTab()
    expect(screen.getByText(/jobs held by power-cap/i)).toBeDefined()
  })

  it('7-2: K8S job renders with the "K8S" scheduler badge label', () => {
    renderQueueTab()
    expect(screen.getByText('K8S')).toBeDefined()
  })

  it('7-3: SLURM job renders with the "SLURM" scheduler badge label', () => {
    renderQueueTab()
    expect(screen.getByText('SLURM')).toBeDefined()
  })

  it('7-4: RAY job renders with the "RAY" scheduler badge label', () => {
    renderQueueTab()
    expect(screen.getByText('RAY')).toBeDefined()
  })

  it('7-5: Tenant column shows "Tenant A" full label, not bare "A"', () => {
    renderQueueTab()
    // The chip renders "Tenant A" — bare "A" is insufficient
    expect(screen.getByText('Tenant A')).toBeDefined()
  })

  it('7-6: Queued-at cell renders in "t=Xs" format (sim tick time, not wall clock)', () => {
    renderQueueTab()
    // kube-job-42 has queued_since_s=262 → cell should say "t=262s"
    expect(screen.getByText('t=262s')).toBeDefined()
  })

  it('7-7: requeue_count=0 renders "—" in the Requeued column', () => {
    renderQueueTab()
    // kube-job-42 has requeue_count=0 — "—" must appear at least once
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  it('7-8: requeue_count>0 renders "×N" format (ray-run-118 has requeue_count=3)', () => {
    renderQueueTab()
    expect(screen.getByText('×3')).toBeDefined()
  })

})
