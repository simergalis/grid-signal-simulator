/**
 * ScenarioBuilder complete seed-catalog round-trip coverage.
 *
 * The fixture comes directly from build_seeded_store(), so this test follows
 * the maintained backend catalog: Python-defined demos, JSON-backed customer
 * scenarios, and fabric regressions. It deliberately uses persisted payloads,
 * not a simplified hand-written ScenarioSpec.
 */

import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ScenarioBuilder } from '../components/ScenarioBuilder'
import { useScenarioStore } from '../store/scenarioStore'
import type { ScenarioSpec } from '../types'

const testDir = dirname(fileURLToPath(import.meta.url))
const simulatorDir = resolve(testDir, '../../../gridsignal_sim')

function loadPersistedSeedSpecs(): Record<string, ScenarioSpec> {
  const output = execFileSync(
    'python',
    ['-c', [
      'import json',
      'from api.routes.scenarios import build_seeded_store',
      'store = build_seeded_store()',
      'print(json.dumps({record.scenario_id: json.loads(record.spec_json) for record in store.list_all()}))',
    ].join('; ')],
    { cwd: simulatorDir, encoding: 'utf8' },
  )
  return JSON.parse(output) as Record<string, ScenarioSpec>
}

const SEEDED_SPECS = loadPersistedSeedSpecs()
const SEEDED_ENTRIES = Object.entries(SEEDED_SPECS)
const PMS_SEED_IDS = SEEDED_ENTRIES
  .filter(([, spec]) => spec.pms_config !== null && spec.pms_config !== undefined)
  .map(([scenarioId]) => scenarioId)

const REQUIRED_SEED_CATEGORIES = [
  'demo-pms-shortfall',
  'demo-islanded-ramp',
  'demo-10-tenant-random-gpu',
  'demo-grid-fc-bess-shaped-load',
  'scenario-equinix-sj-1',
  'scenario-turbine-01',
  'regression-test-healthy-training-baseline',
]

const updates = new Map<string, ScenarioSpec>()

beforeEach(() => {
  cleanup()
  updates.clear()
  useScenarioStore.setState({
    scenarios: [],
    selectedId: null,
    selectedSpec: null,
    isLoading: false,
    error: null,
  })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    const method = init?.method ?? 'GET'
    const scenarioId = path.split('/').pop()

    if (method === 'GET' && path === '/scenarios') {
      return {
        ok: true,
        json: async () => SEEDED_ENTRIES.map(([id, spec]) => ({
          scenario_id: id,
          name: spec.name,
          description: spec.description,
          created_at: '2026-01-01T00:00:00Z',
        })),
      } as Response
    }
    if (method === 'GET' && scenarioId && SEEDED_SPECS[scenarioId]) {
      return {
        ok: true,
        json: async () => ({
          scenario_id: scenarioId,
          spec: SEEDED_SPECS[scenarioId],
          c_rate_warnings: [],
        }),
      } as Response
    }
    if (method === 'PUT' && scenarioId && SEEDED_SPECS[scenarioId]) {
      updates.set(scenarioId, JSON.parse(String(init?.body)) as ScenarioSpec)
      return {
        ok: true,
        json: async () => ({
          scenario_id: scenarioId,
          name: SEEDED_SPECS[scenarioId].name,
          c_rate_warnings: [],
        }),
      } as Response
    }
    throw new Error(`Unexpected scenario request: ${method} ${path}`)
  }))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ScenarioBuilder seeded editor round-trip', () => {
  it('derives the complete supported catalog from the backend seed contract', () => {
    expect(SEEDED_ENTRIES).toHaveLength(40)
    expect(Object.keys(SEEDED_SPECS)).toEqual(expect.arrayContaining(REQUIRED_SEED_CATEGORIES))
    expect(PMS_SEED_IDS).toEqual(expect.arrayContaining(['demo-pms-shortfall', 'demo-pms']))
  })

  it.each(SEEDED_ENTRIES)(
    'loads and saves %s without blank profile fields or data loss',
    async (scenarioId, persistedSpec) => {
      const onSaved = vi.fn()
      const { container } = render(
        <ScenarioBuilder editId={scenarioId} onClose={() => {}} onSaved={onSaved} />,
      )

      await waitFor(() => {
        expect(fetch).toHaveBeenCalledWith(`/scenarios/${scenarioId}`)
        expect(screen.getByDisplayValue(persistedSpec.name)).toBeInTheDocument()
      })

      const expectedIrradiance = persistedSpec.irradiance_steps.length > 0
        ? persistedSpec.irradiance_steps
        : [[0, 1]]
      const irradianceTable = container.querySelector('table')
      expect(irradianceTable).not.toBeNull()
      expect(within(irradianceTable as HTMLElement).getAllByRole('row'))
        .toHaveLength(expectedIrradiance.length + 1)

      const gpuLoadProfile = persistedSpec.gpu_load_profile ?? []
      if (gpuLoadProfile.length === 0) {
        expect(screen.getByText('Flat 100 % (full TDP) — no throttling')).toBeInTheDocument()
        fireEvent.click(screen.getByRole('button', { name: '✎ Edit Profile' }))
        expect(await screen.findByRole('heading', { name: 'GPU Load Profile' })).toBeInTheDocument()
        expect(screen.getByText('No points — flat 100 % load')).toBeInTheDocument()
        const canvas = container.querySelector('svg')
        expect(canvas?.querySelector('path')?.getAttribute('d')).toContain('M 38 10 H 512')
        fireEvent.keyDown(window, { key: 'Escape' })
      } else {
        expect(screen.getByText(
          `${gpuLoadProfile.length} point${gpuLoadProfile.length === 1 ? '' : 's'} · zero-order hold`,
        )).toBeInTheDocument()
      }

      fireEvent.click(screen.getByRole('button', { name: 'Update' }))
      await waitFor(() => expect(onSaved).toHaveBeenCalledWith(scenarioId))

      const savedSpec = updates.get(scenarioId)
      expect(savedSpec).toBeDefined()
      expect(savedSpec).toMatchObject({
        name: persistedSpec.name,
        description: persistedSpec.description,
        workload_events: persistedSpec.workload_events,
        bess_units: persistedSpec.bess_units,
        turbine_units: persistedSpec.turbine_units,
        irradiance_steps: expectedIrradiance,
        gpu_load_profile: gpuLoadProfile,
      })
      expect(savedSpec?.fabric_scenario_id).toBe(persistedSpec.fabric_scenario_id)
      expect(savedSpec?.kube_config).toEqual(persistedSpec.kube_config)
      expect(savedSpec?.tenant_events).toEqual(persistedSpec.tenant_events)
    },
  )

  it.each(PMS_SEED_IDS)(
    'keeps transition mode controls stable when toggling PMS for %s',
    async scenarioId => {
      render(
        <ScenarioBuilder editId={scenarioId} onClose={() => {}} onSaved={() => {}} />,
      )

      await screen.findByDisplayValue(SEEDED_SPECS[scenarioId].name)
      const pmsToggle = screen.getByRole('checkbox', { name: /Enable PMS integration/i })
      expect(pmsToggle).toBeChecked()
      expect(screen.getByText('Transition mode')).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /Open transition/i })).toBeChecked()

      fireEvent.click(pmsToggle)
      expect(screen.queryByText('Transition mode')).not.toBeInTheDocument()

      fireEvent.click(pmsToggle)
      expect(screen.getByText('Transition mode')).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: /Open transition/i })).toBeChecked()
    },
  )
})