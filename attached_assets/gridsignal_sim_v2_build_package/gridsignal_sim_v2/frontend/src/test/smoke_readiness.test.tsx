/**
 * smoke_readiness.test.tsx — mounting tests for U2/U3 readiness components.
 *
 * Verifies tiles, banner, and modal shell mount without throwing.
 * Uses the same tick fixtures as smoke_panels.test.tsx.
 * The 19 existing tests are not modified.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { useTickStore }       from '../store/tickStore'
import { SubsystemTile }      from '../readiness/SubsystemTile'
import { ReadinessBanner }    from '../readiness/ReadinessBanner'
import { ReadinessScreen }    from '../readiness/ReadinessScreen'
import type { TickPayload }   from '../types'

// Reuse the same ALERT_TICK fixture shape
const BASE_TICK: TickPayload = {
  run_id: 'readiness-test',
  tick_index: 1,
  sim_time_seconds: 5.0,
  p_compute_mw: 10.0,
  p_cooling_mw: 2.0,
  p_total_mw: 12.0,
  net_demand_mw: 7.0,
  turbine_output_mw: 9.0,
  bess_output_mw: 0.0,
  bess_soc_fraction: 0.95,
  confidence_lower_mw: 10.0,
  confidence_upper_mw: 14.0,
  p_renewable_mw: 5.0,
  bess_bridging_seconds: 3060,
  bridging_basis: 'predicted_peak',
  dt_lead_next_s: 40.0,
  insufficient_reserve_alert: false,
  data_quality_tags: [],
  checkpoint_states: { 'job-a': 'running' },
  rated_cooling_mw: 4.59,
  absorbable_mw: 4.59,
  time_to_limit_s: 86400,
  approach_rate_mw_s: 0.0,
}

function seedTick(tick: TickPayload) {
  const store = useTickStore.getState()
  store.setRunMeta({ run_id: tick.run_id, playback_speed: 10 })
  store.pushTick(tick)
  store.drainFrame()
}

beforeEach(() => {
  useTickStore.getState().reset()
  cleanup()
})

// ── SubsystemTile ─────────────────────────────────────────────────────────────

describe('SubsystemTile — mounting', () => {
  it('renders name, state badge, verdict, and three metrics', () => {
    const clicks: string[] = []
    render(
      <SubsystemTile
        id="generation"
        name="Generation"
        state="READY"
        accentColor="#e0a458"
        verdict="Can close a 9.0 MW gap inside the 45 s lead window."
        metrics={[
          { label: 'Output', value: '9.00 MW', colour: '#e0a458' },
          { label: 'Net demand', value: '8.96 MW' },
          { label: 'Coverage', value: '100%' },
        ]}
        onClick={id => clicks.push(id)}
      />
    )
    expect(screen.getByText(/Generation/i)).toBeInTheDocument()
    expect(screen.getByText(/READY/i)).toBeInTheDocument()
    expect(screen.getByText(/Can close/i)).toBeInTheDocument()
    expect(screen.getByText(/9\.00 MW/i)).toBeInTheDocument()
  })

  it('clicking the tile calls onClick with the subsystem id', () => {
    const clicks: string[] = []
    render(
      <SubsystemTile
        id="thermal"
        name="Thermal & Cooling"
        state="ATTENTION"
        accentColor="#4a9fe0"
        verdict="Low headroom."
        metrics={[
          { label: 'Absorbable', value: '0.10 MW' },
          { label: 'Time to limit', value: '30 s' },
          { label: 'Approach rate', value: '0.003 MW/s' },
        ]}
        onClick={id => clicks.push(id)}
      />
    )
    screen.getByText(/Thermal/i).closest('button')!.click()
    expect(clicks).toContain('thermal')
  })

  it('shows idle state correctly', () => {
    render(
      <SubsystemTile
        id="network"
        name="Network Fabric"
        state="—"
        accentColor="#4a9fe0"
        verdict="No active run."
        metrics={[
          { label: '—', value: '—' },
          { label: '—', value: '—' },
          { label: '—', value: '—' },
        ]}
        onClick={() => {}}
      />
    )
    expect(screen.getByText(/Network Fabric/i)).toBeInTheDocument()
  })
})

// ── ReadinessBanner ───────────────────────────────────────────────────────────

describe('ReadinessBanner — mounting', () => {
  it('shows NO RUN state before any tick', () => {
    render(<ReadinessBanner />)
    expect(screen.getByText(/NO RUN/i)).toBeInTheDocument()
  })

  it('shows ARMED after a healthy tick', () => {
    seedTick(BASE_TICK)
    render(<ReadinessBanner />)
    expect(screen.getByText(/ARMED/i)).toBeInTheDocument()
  })

  it('shows four hero figure labels', () => {
    seedTick(BASE_TICK)
    render(<ReadinessBanner />)
    expect(screen.getByText(/Dispatchable/i)).toBeInTheDocument()
    expect(screen.getByText(/Lead time/i)).toBeInTheDocument()
    expect(screen.getByText(/Bridge duration/i)).toBeInTheDocument()
    expect(screen.getByText(/Needs attention/i)).toBeInTheDocument()
  })
})

// ── ReadinessScreen ───────────────────────────────────────────────────────────

describe('ReadinessScreen — mounting', () => {
  it('renders without throwing in pre-run state', () => {
    const { container } = render(<ReadinessScreen />)
    expect(container.firstChild).not.toBeNull()
  })

  it('renders four group headers', () => {
    render(<ReadinessScreen />)
    // Some group names (e.g. "Energy Storage") also appear as tile names — use getAllByText.
    expect(screen.getAllByText(/Data Centre/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Energy Storage/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Power Sources/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/System/i).length).toBeGreaterThan(0)
  })

  it('renders all nine subsystem tile names', () => {
    render(<ReadinessScreen />)
    const expected = [
      'Compute & Workload', 'Thermal & Cooling', 'Energy Storage',
      'Generation', 'Renewable Supply', 'Grid Connection',
      'Forecast Quality', 'Network Fabric', 'Optimisation Agents',
    ]
    // Some names (e.g. "Energy Storage") appear both as a group header and a tile — use getAllByText.
    expected.forEach(name => {
      const matches = screen.getAllByText(name)
      expect(matches.length).toBeGreaterThan(0)
    })
  })

  it('renders with live tick without throwing', () => {
    seedTick(BASE_TICK)
    const { container } = render(<ReadinessScreen />)
    expect(container.firstChild).not.toBeNull()
  })
})
