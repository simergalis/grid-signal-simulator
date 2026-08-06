/**
 * ScenarioModal.tsx — Centered modal for full scenario CRUD.
 *
 * Create  → "+ New Scenario" button → closes modal, opens ScenarioBuilder
 * Edit    → "Edit" row button       → closes modal, opens ScenarioBuilder
 * Delete  → two-step inline confirm; seeded scenarios are protected
 * Upload  → file picker + drag-and-drop anywhere on the panel
 * Download→ fetches GET /scenarios/{id}, saves spec as .json
 */

import { useEffect, useRef, useState } from 'react'
import { useScenarioStore } from '../store/scenarioStore'
import type { ScenarioSpec } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function isSeeded(id: string): boolean {
  return id.startsWith('demo-') || /^S\d+_/.test(id) || id === 'demo_solar_peak'
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function validateSpec(obj: unknown): string | null {
  if (typeof obj !== 'object' || obj === null) return 'File is not a JSON object.'
  const s = obj as Record<string, unknown>
  if (!s.name || typeof s.name !== 'string' || !s.name.trim()) return 'Missing required field: name.'
  if (!Array.isArray(s.bess_units) || s.bess_units.length === 0)
    return 'Missing required field: bess_units (array, ≥1 entry).'
  if (!Array.isArray(s.turbine_units) || s.turbine_units.length === 0)
    return 'Missing required field: turbine_units (array, ≥1 entry).'
  return null
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Badge({ label, variant }: { label: string; variant: 'muted' | 'accent' }) {
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[9px] leading-none
      ${variant === 'accent'
        ? 'bg-accent/10 text-accent border-accent/30'
        : 'bg-canvas text-muted border-border'}`}>
      {label}
    </span>
  )
}

function Toast({ msg, kind, onDismiss }: { msg: string; kind: 'ok' | 'err'; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 5000)
    return () => clearTimeout(t)
  }, [onDismiss])
  return (
    <div className={`flex items-start gap-2 rounded border px-3 py-2 text-xs mx-6 mb-3
      ${kind === 'ok' ? 'bg-surface border-success/40 text-success' : 'bg-surface border-danger/40 text-danger'}`}>
      <span className="flex-1 leading-snug">{msg}</span>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100 leading-none">×</button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  onClose:       () => void
  onNew:         () => void           // closes modal + opens ScenarioBuilder (new)
  onEdit:        (id: string) => void  // closes modal + opens ScenarioBuilder (edit)
  /** Called after a run is successfully started from the Execute button. */
  onExecute?:    (runId: string, speed: number, socFloor?: number, socCeil?: number) => void
}

export function ScenarioModal({ onClose, onNew, onEdit, onExecute }: Props) {
  const scenarios      = useScenarioStore(s => s.scenarios)
  const isLoading      = useScenarioStore(s => s.isLoading)
  const fetchScenarios = useScenarioStore(s => s.fetchScenarios)
  const deleteScenario = useScenarioStore(s => s.deleteScenario)
  const createScenario = useScenarioStore(s => s.createScenario)

  const fileRef    = useRef<HTMLInputElement>(null)
  const panelRef   = useRef<HTMLDivElement>(null)

  const [toast,        setToast]        = useState<{ msg: string; kind: 'ok' | 'err' } | null>(null)
  const [confirmId,    setConfirmId]    = useState<string | null>(null)
  const [deleteBusy,   setDeleteBusy]   = useState(false)
  const [uploadBusy,   setUploadBusy]   = useState(false)
  const [downloadBusy, setDownloadBusy] = useState<string | null>(null)
  const [executeBusy,  setExecuteBusy]  = useState<string | null>(null)
  const [dragOver,     setDragOver]     = useState(false)
  const [search,       setSearch]       = useState('')

  // ── Execute (start a run directly from the scenario list) ──────────────────
  const handleExecute = async (scenarioId: string) => {
    setExecuteBusy(scenarioId)
    setToast(null)
    try {
      const resp = await fetch('/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: scenarioId, playback_speed: 1, end_sim_time: 1800 }),
      })
      if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`)
      const data = await resp.json() as { run_id: string; soc_floor_pct?: number; soc_ceil_pct?: number }
      onExecute?.(data.run_id, 1, data.soc_floor_pct, data.soc_ceil_pct)
      onClose()
    } catch (e) {
      setToast({ msg: `Failed to start run: ${String(e)}`, kind: 'err' })
    } finally {
      setExecuteBusy(null)
    }
  }

  useEffect(() => { fetchScenarios() }, [fetchScenarios])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  // Filtered list
  const q = search.trim().toLowerCase()
  const filtered = q
    ? scenarios.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.scenario_id.toLowerCase().includes(q) ||
        (s.description ?? '').toLowerCase().includes(q))
    : scenarios

  const customCount = scenarios.filter(s => !isSeeded(s.scenario_id)).length

  // ── Upload ──────────────────────────────────────────────────────────────────
  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.json')) {
      setToast({ msg: 'Only .json files are supported.', kind: 'err' }); return
    }
    setUploadBusy(true)
    try {
      const text = await file.text()
      let obj: unknown
      try { obj = JSON.parse(text) } catch {
        setToast({ msg: 'File is not valid JSON.', kind: 'err' }); return
      }
      const err = validateSpec(obj)
      if (err) { setToast({ msg: err, kind: 'err' }); return }
      const result = await createScenario(obj as ScenarioSpec)
      const warn   = result.c_rate_warnings?.length
        ? `  ⚠ C-rate warnings: ${result.c_rate_warnings.join('; ')}`
        : ''
      setToast({ msg: `Created "${result.name}" (${result.scenario_id}).${warn}`, kind: 'ok' })
    } catch (e) {
      setToast({ msg: String(e), kind: 'err' })
    } finally {
      setUploadBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (f) handleFile(f)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragOver(false)
    const f = e.dataTransfer.files[0]; if (f) handleFile(f)
  }

  // ── Download ────────────────────────────────────────────────────────────────
  const handleDownload = async (id: string, name: string) => {
    setDownloadBusy(id)
    try {
      const resp = await fetch(`/scenarios/${id}`)
      if (!resp.ok) throw new Error(`${resp.status}`)
      const data = await resp.json() as { spec: ScenarioSpec }
      const blob = new Blob([JSON.stringify(data.spec, null, 2)], { type: 'application/json' })
      const url  = URL.createObjectURL(blob)
      const a    = Object.assign(document.createElement('a'), {
        href: url, download: `${name.replace(/[^a-z0-9_-]/gi, '_')}.json`,
      })
      document.body.appendChild(a); a.click()
      document.body.removeChild(a); URL.revokeObjectURL(url)
    } catch (e) {
      setToast({ msg: `Download failed: ${e}`, kind: 'err' })
    } finally {
      setDownloadBusy(null)
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────
  const handleDeleteConfirm = async (id: string) => {
    setDeleteBusy(true)
    try {
      await deleteScenario(id)
      setConfirmId(null)
      setToast({ msg: 'Scenario deleted.', kind: 'ok' })
    } catch (e) {
      setToast({ msg: String(e), kind: 'err' })
    } finally {
      setDeleteBusy(false)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/65"
      onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {dragOver && (
        <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
          <div className="rounded-xl border-2 border-dashed border-accent px-14 py-10 text-center bg-canvas/80">
            <p className="text-sm font-semibold text-accent">Drop JSON to upload</p>
            <p className="text-xs text-muted mt-1">Needs: name · bess_units · turbine_units</p>
          </div>
        </div>
      )}

      {/* Panel */}
      <div
        ref={panelRef}
        className="relative flex flex-col w-full max-w-4xl mx-4 rounded-xl border border-border shadow-2xl"
        style={{ background: '#0e151d', maxHeight: '85vh' }}
      >
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 border-b border-border px-6 py-4 flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-text tracking-wide">Scenarios</h2>
            <p className="text-[10px] text-muted mt-0.5">
              {scenarios.length} total · {customCount} custom
            </p>
          </div>
          <div className="flex-1" />

          {/* Search */}
          <input
            type="search"
            placeholder="Search…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-44 rounded border border-border bg-canvas px-2 py-1 text-xs text-text
                       placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
          />

          {/* Upload */}
          <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={handleFileInput} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploadBusy}
            className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs
                       text-muted hover:border-accent hover:text-accent disabled:opacity-40 transition-colors"
          >
            {uploadBusy
              ? <span className="h-3 w-3 rounded-full border border-accent border-t-transparent animate-spin inline-block" />
              : <span>↑</span>}
            Upload JSON
          </button>

          {/* New */}
          <button
            onClick={onNew}
            className="rounded px-3 py-1.5 text-xs font-semibold text-white transition-colors"
            style={{ background: '#3fb6a8' }}
          >
            + New Scenario
          </button>

          {/* Close */}
          <button
            onClick={onClose}
            className="ml-2 rounded border border-border w-7 h-7 flex items-center justify-center
                       text-muted hover:text-text hover:border-muted/60 transition-colors text-sm"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* ── Table (scrollable) ──────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {isLoading && scenarios.length === 0 ? (
            <p className="text-center text-xs text-muted mt-8">Loading…</p>
          ) : filtered.length === 0 ? (
            <div className="text-center mt-8 space-y-2">
              <p className="text-xs text-muted">
                {search ? 'No scenarios match your search.' : 'No scenarios yet.'}
              </p>
              {!search && (
                <button onClick={onNew} className="text-xs text-accent hover:underline">
                  Create your first scenario →
                </button>
              )}
            </div>
          ) : (
            <table className="w-full text-xs border-separate border-spacing-0">
              <thead>
                <tr className="text-muted">
                  {['Name','ID','Type','Description','Created',''].map((h, i) => (
                    <th key={i}
                      className={`text-left pb-2 pr-4 font-medium uppercase tracking-wide text-[10px]
                        ${i === 5 ? 'text-right pr-0' : ''}
                        ${i === 3 ? 'hidden md:table-cell' : ''}
                        ${i === 4 ? 'hidden lg:table-cell' : ''}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map(s => {
                  const seeded       = isSeeded(s.scenario_id)
                  const isConfirming = confirmId === s.scenario_id
                  const isDown       = downloadBusy === s.scenario_id
                  const isExec       = executeBusy === s.scenario_id

                  return (
                    <tr key={s.scenario_id}
                      className="border-t border-border hover:bg-white/[0.02] transition-colors group">

                      {/* Name */}
                      <td className="py-3 pr-4 font-medium text-text">
                        <span className="block max-w-[160px] truncate" title={s.name}>{s.name}</span>
                      </td>

                      {/* ID */}
                      <td className="py-3 pr-4">
                        <span className="font-mono text-[10px] text-muted block max-w-[130px] truncate"
                          title={s.scenario_id}>{s.scenario_id}</span>
                      </td>

                      {/* Type */}
                      <td className="py-3 pr-4 whitespace-nowrap">
                        <Badge label={seeded ? 'built-in' : 'custom'} variant={seeded ? 'muted' : 'accent'} />
                      </td>

                      {/* Description */}
                      <td className="py-3 pr-4 text-muted hidden md:table-cell">
                        <span className="block max-w-[220px] truncate" title={s.description}>
                          {s.description || '—'}
                        </span>
                      </td>

                      {/* Created */}
                      <td className="py-3 pr-4 text-muted font-mono text-[10px] whitespace-nowrap hidden lg:table-cell">
                        {seeded ? '—' : formatDate(s.created_at)}
                      </td>

                      {/* Actions */}
                      <td className="py-3 text-right">
                        {isConfirming ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="text-danger text-[10px]">Delete?</span>
                            <button disabled={deleteBusy} onClick={() => handleDeleteConfirm(s.scenario_id)}
                              className="rounded border border-danger px-2 py-0.5 text-[10px] text-danger
                                         hover:bg-danger/10 disabled:opacity-40 transition-colors">
                              {deleteBusy ? '…' : 'Yes'}
                            </button>
                            <button disabled={deleteBusy} onClick={() => setConfirmId(null)}
                              className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                         hover:text-text disabled:opacity-40 transition-colors">
                              No
                            </button>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5">
                            {/* Execute — start run immediately */}
                            <button
                              onClick={() => handleExecute(s.scenario_id)}
                              disabled={!!executeBusy}
                              title="Start a run with this scenario"
                              className="inline-flex items-center gap-1 rounded border px-2 py-0.5
                                         text-[10px] font-semibold transition-colors disabled:opacity-40"
                              style={{
                                borderColor: '#3fb6a8aa',
                                color:        '#3fb6a8',
                                background:   isExec ? 'rgba(63,182,168,0.12)' : 'rgba(63,182,168,0.06)',
                              }}
                            >
                              {isExec
                                ? <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border border-accent border-t-transparent" />
                                : <span>▶</span>
                              }
                              {isExec ? 'Starting…' : 'Run'}
                            </button>
                            <button onClick={() => onEdit(s.scenario_id)}
                              className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                         hover:border-accent hover:text-accent transition-colors">
                              Edit
                            </button>
                            <button onClick={() => handleDownload(s.scenario_id, s.name)}
                              disabled={isDown}
                              className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                         hover:border-accent hover:text-accent disabled:opacity-40 transition-colors">
                              {isDown ? '…' : '↓ JSON'}
                            </button>
                            <button onClick={() => setConfirmId(s.scenario_id)}
                              disabled={seeded}
                              title={seeded ? 'Built-in scenarios cannot be deleted' : 'Delete'}
                              className="rounded border border-border px-2 py-0.5 text-[10px] text-muted
                                         hover:border-danger hover:text-danger disabled:opacity-30
                                         disabled:cursor-not-allowed transition-colors">
                              Delete
                            </button>
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* ── Toast ──────────────────────────────────────────────────────── */}
        {toast && (
          <Toast msg={toast.msg} kind={toast.kind} onDismiss={() => setToast(null)} />
        )}

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        <div className="border-t border-border px-6 py-2 flex-shrink-0">
          <p className="text-[10px] text-muted">
            Drag a <span className="font-mono">.json</span> file onto this window to upload.
            Required fields: <span className="font-mono">name</span>,{' '}
            <span className="font-mono">bess_units</span>,{' '}
            <span className="font-mono">turbine_units</span>.{' '}
            <a href="/scenario_spec_schema.json" target="_blank" rel="noreferrer"
              className="text-accent hover:underline">Schema ↗</a>
          </p>
        </div>
      </div>
    </div>
  )
}
