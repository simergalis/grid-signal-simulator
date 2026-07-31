/**
 * smoke_charts.test.tsx — mounting tests for the 5 U1 chart primitives.
 *
 * Verifies each component mounts without throwing given representative props.
 * The 19 existing tests in smoke_panels.test.tsx are not modified.
 */

import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { TimeSeries }  from '../charts/TimeSeries'
import { BulletBar }   from '../charts/BulletBar'
import { StatTable }   from '../charts/StatTable'
import { StackBar }    from '../charts/StackBar'
import { GaugeArc }    from '../charts/GaugeArc'

// ── Representative props ──────────────────────────────────────────────────────

const SERIES = [
  { label: 'series-a', colour: '#3fb6a8', points: [{ x: 0, y: 1 }, { x: 5, y: 2 }, { x: 10, y: 1.5 }] },
  { label: 'series-b', colour: '#e0a458', points: [{ x: 0, y: 0.5 }, { x: 5, y: 1 }, { x: 10, y: 0.8 }], filled: true },
]

const STAT_ROWS = [
  { label: 'Metric A', value: '9.00 MW', colour: '#3fb6a8', sub: 'rated capacity' },
  { label: 'Metric B', value: 'never',   colour: '#f0883e' },
  { label: 'Metric C', value: '125 s' },
]

const STACK_SEGS = [
  { label: 'Compute', value: 19.96, colour: '#3fb6a8' },
  { label: 'Cooling', value:  3.99, colour: '#4a9fe0' },
]

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('U1 chart primitives — mounting', () => {
  it('TimeSeries mounts with series and ceiling', () => {
    const { container } = render(
      <TimeSeries
        series={SERIES}
        yMax={30}
        ceiling={{ y: 25, label: 'rated ceiling' }}
        markers={[{ x: 5, label: 'event A' }]}
        xLabel="seconds"
      />
    )
    expect(container.firstChild).not.toBeNull()
  })

  it('TimeSeries mounts in dense mode', () => {
    const { container } = render(
      <TimeSeries series={SERIES} dense />
    )
    expect(container.firstChild).not.toBeNull()
  })

  it('BulletBar mounts with value, max, and target', () => {
    const { getByText } = render(
      <BulletBar
        label="Ramp capability"
        value={9.0}
        max={25.0}
        target={8.96}
        colour="#e0a458"
        unit=" MW"
        note="capability exceeds target"
      />
    )
    expect(getByText(/Ramp capability/i)).toBeInTheDocument()
    expect(getByText(/9\.00 MW/i)).toBeInTheDocument()
  })

  it('BulletBar mounts in dense mode without note', () => {
    const { container } = render(
      <BulletBar label="Output" value={17} max={18} colour="#4a9fe0" dense />
    )
    expect(container.firstChild).not.toBeNull()
  })

  it('StatTable mounts with colour-coded rows', () => {
    const { getByText } = render(<StatTable rows={STAT_ROWS} />)
    expect(getByText(/Metric A/i)).toBeInTheDocument()
    expect(getByText(/9\.00 MW/i)).toBeInTheDocument()
    expect(getByText(/rated capacity/i)).toBeInTheDocument()
  })

  it('StatTable mounts in dense mode', () => {
    const { container } = render(<StatTable rows={STAT_ROWS} dense />)
    expect(container.firstChild).not.toBeNull()
  })

  it('StackBar mounts and shows segment labels', () => {
    const { getByText } = render(<StackBar segments={STACK_SEGS} unit=" MW" />)
    expect(getByText(/Compute/i)).toBeInTheDocument()
    expect(getByText(/Cooling/i)).toBeInTheDocument()
  })

  it('StackBar mounts with explicit total', () => {
    const { container } = render(
      <StackBar segments={STACK_SEGS} total={30} dense />
    )
    expect(container.firstChild).not.toBeNull()
  })

  it('GaugeArc mounts with fraction and labels', () => {
    const { getByText } = render(
      <GaugeArc
        fraction={0.95}
        colour="#4a9fe0"
        bigLabel="95%"
        smallLabel="state of charge"
      />
    )
    expect(getByText(/95%/i)).toBeInTheDocument()
    expect(getByText(/state of charge/i)).toBeInTheDocument()
  })

  it('GaugeArc mounts with zero fraction (empty state)', () => {
    const { container } = render(
      <GaugeArc fraction={0} colour="#f85149" bigLabel="0%" smallLabel="depleted" />
    )
    expect(container.firstChild).not.toBeNull()
  })

  it('GaugeArc mounts in dense mode', () => {
    const { container } = render(
      <GaugeArc fraction={0.75} colour="#3fb6a8" bigLabel="75%" smallLabel="SoC" dense />
    )
    expect(container.firstChild).not.toBeNull()
  })
})
