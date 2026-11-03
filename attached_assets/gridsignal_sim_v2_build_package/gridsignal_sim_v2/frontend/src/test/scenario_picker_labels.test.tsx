import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { RunControlBar } from '../components/RunControlBar'
import { useScenarioStore } from '../store/scenarioStore'

const QUEUE_SCENARIO_ID = 'proxim8-5mw-24h-queue'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('scenario picker labels', () => {
  it('shows the friendly queue-stress name while keeping the scenario ID as the option value', async () => {
    useScenarioStore.setState({
      scenarios: [],
      selectedId: QUEUE_SCENARIO_ID,
      selectedSpec: null,
      isLoading: false,
      error: null,
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{
        scenario_id: QUEUE_SCENARIO_ID,
        name: QUEUE_SCENARIO_ID,
        description: '',
        created_at: '',
      }],
    }))

    render(
      <RunControlBar
        runId={null}
        lastRunId={null}
        isPaused={false}
        onRunStarted={() => {}}
        onRunStopped={() => {}}
        onRunPaused={() => {}}
        onRunResumed={() => {}}
        onNewScenario={() => {}}
        onViewResults={() => {}}
      />,
    )

    const option = await screen.findByRole('option', { name: 'Proxim8 with queue-stress' })
    expect(option).toHaveValue(QUEUE_SCENARIO_ID)
  })
})
