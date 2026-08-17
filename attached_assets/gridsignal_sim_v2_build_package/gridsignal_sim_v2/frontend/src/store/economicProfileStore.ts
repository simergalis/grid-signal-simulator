/**
 * economicProfileStore.ts — Zustand store for Economic Profile catalogue (§30).
 *
 * Mirrors the shape of scenarioStore.ts but hits /api/economic-profiles/*.
 * Unlike gpuGeneratorStore (Zustand-only, ephemeral), profiles are persisted
 * durably in the backend PostgreSQL/SQLite DB — they survive server restarts
 * (AC-2.6).  This store is the frontend cache layer only; the DB is the
 * source of truth.
 *
 * Following scenarioStore.ts pattern exactly per T1 locked decision:
 *   - fetch on demand (not on import)
 *   - actions call POST / PUT / DELETE
 *   - selectedProfileId drives the "Configure Economics" selector in
 *     ScenarioPlannerPage before a run starts
 */

import { create } from 'zustand'
import type {
  EconomicProfileSummary,
  EconomicProfileDetail,
  EconomicProfileSpec,
  CreateEconomicProfileResponse,
} from '../types'

const BASE = ''   // same-origin, no prefix

interface EconomicProfileState {
  profiles: EconomicProfileSummary[]
  selectedProfileId: string | null
  selectedProfile: EconomicProfileDetail | null
  isLoading: boolean
  error: string | null

  // ── Actions ─────────────────────────────────────────────────────────────
  fetchProfiles: () => Promise<void>
  selectProfile: (id: string | null) => void
  fetchSelectedProfile: () => Promise<void>
  setSelectedProfile: (profile: EconomicProfileDetail | null) => void
  createProfile: (spec: EconomicProfileSpec) => Promise<CreateEconomicProfileResponse>
  updateProfile: (id: string, spec: EconomicProfileSpec) => Promise<CreateEconomicProfileResponse>
  deleteProfile: (id: string) => Promise<void>
}

export const useEconomicProfileStore = create<EconomicProfileState>((set, get) => ({
  profiles: [],
  selectedProfileId: null,
  selectedProfile: null,
  isLoading: false,
  error: null,

  setSelectedProfile: (profile) => set({ selectedProfile: profile }),

  fetchProfiles: async () => {
    set({ isLoading: true, error: null })
    try {
      const resp = await fetch(`${BASE}/api/economic-profiles`)
      if (!resp.ok) throw new Error(`GET /api/economic-profiles → ${resp.status}`)
      const data = await resp.json() as EconomicProfileSummary[]
      set({ profiles: data, isLoading: false })
    } catch (e) {
      set({ error: String(e), isLoading: false })
    }
  },

  selectProfile: (id) => {
    set({ selectedProfileId: id, selectedProfile: null })
    if (id) get().fetchSelectedProfile()
  },

  fetchSelectedProfile: async () => {
    const { selectedProfileId } = get()
    if (!selectedProfileId) return
    try {
      const resp = await fetch(`${BASE}/api/economic-profiles/${selectedProfileId}`)
      if (!resp.ok) return
      const data = await resp.json() as EconomicProfileDetail
      if (get().selectedProfileId === selectedProfileId) {
        set({ selectedProfile: data })
      }
    } catch {
      // Non-critical — UI will show no selection
    }
  },

  createProfile: async (spec) => {
    const resp = await fetch(`${BASE}/api/economic-profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(spec),
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`POST /api/economic-profiles → ${resp.status}: ${text}`)
    }
    const data = await resp.json() as CreateEconomicProfileResponse
    await get().fetchProfiles()
    set({ selectedProfileId: data.profile_id })
    get().fetchSelectedProfile()
    return data
  },

  updateProfile: async (id, spec) => {
    const resp = await fetch(`${BASE}/api/economic-profiles/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(spec),
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`PUT /api/economic-profiles/${id} → ${resp.status}: ${text}`)
    }
    const data = await resp.json() as CreateEconomicProfileResponse
    await get().fetchProfiles()
    // Refresh the selected profile if it was just updated
    if (get().selectedProfileId === id) {
      get().fetchSelectedProfile()
    }
    return data
  },

  deleteProfile: async (id) => {
    const resp = await fetch(`${BASE}/api/economic-profiles/${id}`, { method: 'DELETE' })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`DELETE /api/economic-profiles/${id} → ${resp.status}: ${text}`)
    }
    const state = get()
    await state.fetchProfiles()
    if (state.selectedProfileId === id) {
      const remaining = get().profiles
      const nextId = remaining.length > 0 ? remaining[0].profile_id : null
      set({ selectedProfileId: nextId, selectedProfile: null })
      if (nextId) get().fetchSelectedProfile()
    }
  },
}))
