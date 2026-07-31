/**
 * scenarioStore.ts — Zustand store for scenario catalogue (Step 8).
 *
 * Mirrors the api/routes/scenarios.py ScenarioStore shape.
 * Fetches from GET /scenarios on demand; actions call POST / PUT / DELETE.
 * selectedId drives the RunControlBar dropdown.
 *
 * The store does NOT auto-fetch on import — RunControlBar.useEffect() calls
 * fetchScenarios() on mount so the list is available when the dropdown opens.
 * This keeps the store testable without a live server.
 */

import { create } from 'zustand'
import type { ScenarioSpec, ScenarioSummary, CreateScenarioResponse } from '../types'

const BASE = ''   // same-origin API; no prefix needed

interface ScenarioState {
  scenarios: ScenarioSummary[]
  selectedId: string | null
  isLoading: boolean
  error: string | null

  // ── Actions ───────────────────────────────────────────────────────────
  fetchScenarios: () => Promise<void>
  selectScenario: (id: string | null) => void
  createScenario: (spec: ScenarioSpec) => Promise<CreateScenarioResponse>
  updateScenario: (id: string, spec: ScenarioSpec) => Promise<CreateScenarioResponse>
  deleteScenario: (id: string) => Promise<void>
}

export const useScenarioStore = create<ScenarioState>((set, get) => ({
  scenarios: [],
  selectedId: null,
  isLoading: false,
  error: null,

  fetchScenarios: async () => {
    set({ isLoading: true, error: null })
    try {
      const resp = await fetch(`${BASE}/scenarios`)
      if (!resp.ok) throw new Error(`GET /scenarios → ${resp.status}`)
      const data = await resp.json() as ScenarioSummary[]
      set({ scenarios: data, isLoading: false })
      // Auto-select first scenario if nothing is selected
      if (!get().selectedId && data.length > 0) {
        set({ selectedId: data[0].scenario_id })
      }
    } catch (e) {
      set({ error: String(e), isLoading: false })
    }
  },

  selectScenario: (id) => set({ selectedId: id }),

  createScenario: async (spec) => {
    const resp = await fetch(`${BASE}/scenarios`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(spec),
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`POST /scenarios → ${resp.status}: ${text}`)
    }
    const data = await resp.json() as CreateScenarioResponse
    // Re-fetch the full list (cheapest, keeps order consistent)
    await get().fetchScenarios()
    set({ selectedId: data.scenario_id })
    return data
  },

  updateScenario: async (id, spec) => {
    const resp = await fetch(`${BASE}/scenarios/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(spec),
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`PUT /scenarios/${id} → ${resp.status}: ${text}`)
    }
    const data = await resp.json() as CreateScenarioResponse
    await get().fetchScenarios()
    return data
  },

  deleteScenario: async (id) => {
    const resp = await fetch(`${BASE}/scenarios/${id}`, { method: 'DELETE' })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`DELETE /scenarios/${id} → ${resp.status}: ${text}`)
    }
    const state = get()
    await state.fetchScenarios()
    // If the deleted scenario was selected, pick the first remaining
    if (state.selectedId === id) {
      const remaining = get().scenarios
      set({ selectedId: remaining.length > 0 ? remaining[0].scenario_id : null })
    }
  },
}))
