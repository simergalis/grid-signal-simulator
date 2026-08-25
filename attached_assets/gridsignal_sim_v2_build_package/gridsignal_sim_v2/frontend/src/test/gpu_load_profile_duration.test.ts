import { describe, expect, it } from 'vitest'
import { trimGpuLoadProfileForDuration } from '../components/ScenarioBuilder'

describe('GPU load profile duration bounds', () => {
  it('trims only points after the run duration', () => {
    const points: [number, number][] = [
      [0, 0.5],
      [300, 0.8],
      [600, 0.2],
      [900, 1.0],
    ]

    expect(trimGpuLoadProfileForDuration(points, 600)).toEqual([
      [0, 0.5],
      [300, 0.8],
      [600, 0.2],
    ])
  })

  it('keeps a point exactly at the run end', () => {
    expect(trimGpuLoadProfileForDuration([[600, 0.2]], 600)).toEqual([[600, 0.2]])
  })

  it('returns an empty profile when every point is out of range', () => {
    expect(trimGpuLoadProfileForDuration([[601, 0.2], [900, 1.0]], 600)).toEqual([])
  })
})