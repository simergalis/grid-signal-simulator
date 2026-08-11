/**
 * bessConfigStore.ts — operator BESS sizing overrides.
 *
 * Values here are applied to every BESS unit when POST /runs is called.
 * null = "use whatever the scenario stores" (no override sent to the backend).
 *
 * Written by BessConfigWidget (inside the Energy Storage modal idle state).
 * Read by RunControlBar when building the POST /runs body.
 */

import { create } from 'zustand'

interface BessConfigState {
  ratedMw:     number | null   // rated power override (MW); null = scenario default
  usableMwh:   number | null   // usable energy override (MWh); null = scenario default
  setRatedMw:  (v: number | null) => void
  setUsableMwh:(v: number | null) => void
}

export const useBessConfigStore = create<BessConfigState>((set) => ({
  ratedMw:     null,
  usableMwh:   null,
  setRatedMw:  (v) => set({ ratedMw: v }),
  setUsableMwh:(v) => set({ usableMwh: v }),
}))
