/**
 * BessConfigWidget.tsx — BESS sizing configuration shown in the Energy Storage
 * modal when no run is active.
 *
 * Clicking a preset card opens an edit modal:
 *   • The bright MW value is editable.
 *   • MWh auto-derives from the preset's fixed C-rate as MW changes.
 *   • Custom card: both MW and MWh are independently editable.
 *   • Save commits to bessConfigStore (RunControlBar reads at run-start).
 *   • Cancel discards with no side-effects.
 */

import { useState } from 'react'
import { useBessConfigStore } from '../../store/bessConfigStore'

// ── Preset definitions ───────────────────────────────────────────────────────

interface Preset {
  id:        string
  label:     string
  tag:       string
  cRate:     number | null   // null = custom (both inputs free)
  ratedMw:   number | null   // default MW shown when modal opens
  usableMwh: number | null
  bridgeMin: string
  desc:      string
}

const PRESETS: Preset[] = [
  {
    id: 'long-bridge', label: 'Long Bridge',
    tag: 'Renewables shifting · 0.25 C', cRate: 0.25,
    ratedMw: 5, usableMwh: 20, bridgeMin: '~4 h',
    desc: 'Matches long-duration solar variability or extended grid faults. Energy-dense, cheap per MWh, slow to recharge.',
  },
  {
    id: 'grid-firm', label: 'Grid Firming',
    tag: 'Backup islanding · 0.5 C', cRate: 0.5,
    ratedMw: 5, usableMwh: 10, bridgeMin: '~2 h',
    desc: 'The most common data-centre UPS configuration. Bridges a full generator start sequence with comfortable margin.',
  },
  {
    id: 'freq-anchor', label: 'Freq. Anchor',
    tag: 'Frequency response · 1 C', cRate: 1.0,
    ratedMw: 30, usableMwh: 30, bridgeMin: '~60 min',
    desc: 'Balanced for fast frequency injection and 1-hour bridging. Simulator default — anchor reserve is a small fraction of rated power.',
  },
  {
    id: 'peak-shave', label: 'Peak Shaving',
    tag: 'Demand charge mgmt · 2 C', cRate: 2.0,
    ratedMw: 5, usableMwh: 2.5, bridgeMin: '~30 min',
    desc: 'Optimised for high-power short bursts. Power-dense chemistry (NMC). Bridge duration is short — best paired with fast gas peakers.',
  },
  {
    id: 'fast-ffr', label: 'Fast FFR',
    tag: 'Grid code compliance · 4 C', cRate: 4.0,
    ratedMw: 5, usableMwh: 1.25, bridgeMin: '~15 min',
    desc: 'Maximum response speed. The 1 MW anchor reserve withheld (§7.1.2) consumes most usable capacity — bridge cover is minimal.',
  },
  {
    id: 'custom', label: 'Custom',
    tag: 'Set your own values', cRate: null,
    ratedMw: null, usableMwh: null, bridgeMin: '—',
    desc: 'Enter any rated power and usable capacity. C-rate and validity are shown live.',
  },
]

// ── Layman tooltips ──────────────────────────────────────────────────────────

const PRESET_TOOLTIPS: Record<string, { title: string; body: string }> = {
  'long-bridge': {
    title: 'What is Long Bridge storage?',
    body:
      'Think of this as a very large fuel tank. The battery holds enough energy to keep the data centre ' +
      'running for about 4 hours with no power from the grid at all. This is the right choice when solar ' +
      'power can disappear for long stretches — like an overcast day — or when the grid might be down for ' +
      'hours at a time. You pay more up front for all that storage capacity, but you never have to worry ' +
      'about a long outage catching you short.',
  },
  'grid-firm': {
    title: 'What is Grid Firming storage?',
    body:
      'The most common battery setup in real data centres today. The battery keeps everything running for ' +
      '2 hours — long enough to start a backup generator, wait for the grid to recover, or ride out a ' +
      'storm. It\'s the sweet spot between cost and protection. In practice, most outages that operators ' +
      'experience last less than 30 minutes, so 2 hours feels very comfortable.',
  },
  'freq-anchor': {
    title: 'What is a Frequency Anchor?',
    body:
      'This battery does two jobs at once. First, it acts like a shock absorber for the grid — instantly ' +
      'injecting or absorbing power to keep the frequency steady (think of it as smoothing out the ' +
      '"hum" of the electrical system). Second, it provides 1 hour of backup power if the grid goes ' +
      'dark. This is the simulator\'s default and a good all-round choice for sites where the grid is ' +
      'generally reliable but you need fast reaction to sudden spikes.',
  },
  'peak-shave': {
    title: 'What is Peak Shaving storage?',
    body:
      'Less about backup, more about saving money on your electricity bill. The battery charges up ' +
      'during cheap overnight hours (when grid power is plentiful) and discharges during expensive ' +
      'peak times — shaving the spike off your demand charge. It responds very quickly but runs out ' +
      'faster, giving about 30 minutes of bridge time. Think of it as a sprinter, not a marathon ' +
      'runner. Ideal if your grid is reliable and cost control is the priority.',
  },
  'fast-ffr': {
    title: 'What is Fast FFR storage?',
    body:
      'FFR stands for Fast Frequency Response. This battery can discharge at full power almost ' +
      'instantly — within a fraction of a second — to prevent a grid frequency collapse during a ' +
      'sudden loss of generation (for example, a large power plant tripping offline). The catch is ' +
      'that it runs out very quickly: only about 15 minutes of backup cover. It\'s primarily a ' +
      'grid-code compliance tool, not a backup power solution. Investors: this type of battery ' +
      'can earn revenue by selling frequency services to the grid operator.',
  },
}

// ── Palette ──────────────────────────────────────────────────────────────────

const BATT   = '#4a9fe0'
const TEAL   = '#3fb6a8'
const AMBER  = '#f0883e'
const DIM    = '#4b5764'
const LABEL  = '#6e7681'
const BORDER = '#2a3a4a'
const CANVAS = '#0d1117'
const TEXT   = '#c9d1d9'
const MONO   = { fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace" } as const

function cRateOk(c: number) { return c >= 0.25 && c <= 4 }

// ── Component ─────────────────────────────────────────────────────────────────

export function BessConfigWidget() {
  const ratedMw        = useBessConfigStore(s => s.ratedMw)
  const usableMwh      = useBessConfigStore(s => s.usableMwh)
  const selectedId     = useBessConfigStore(s => s.selectedPresetId)
  const applyPreset    = useBessConfigStore(s => s.applyPreset)
  const clearOverride  = useBessConfigStore(s => s.clearOverride)

  // Edit modal state
  const [editing,  setEditing]  = useState<Preset | null>(null)
  const [editMw,   setEditMw]   = useState('')
  const [editMwh,  setEditMwh]  = useState('')

  // Layman tooltip hover state
  const [tipState, setTipState] = useState<{ id: string; rect: DOMRect } | null>(null)

  // ── Open modal ──────────────────────────────────────────────────────────────

  function openEdit(p: Preset) {
    // Seed MW from: current store (if this preset is selected) → preset default → 5
    const seedMw = selectedId === p.id && ratedMw !== null
      ? ratedMw
      : p.ratedMw ?? 5
    const seedMwh = selectedId === p.id && usableMwh !== null
      ? usableMwh
      : p.usableMwh ?? (p.cRate ? seedMw / p.cRate : 5)

    setEditMw(String(seedMw))
    setEditMwh(Number(seedMwh).toFixed(2).replace(/\.?0+$/, ''))
    setEditing(p)
  }

  // ── MW edit — auto-derive MWh for fixed-C-rate presets ─────────────────────

  function onMwChange(val: string) {
    setEditMw(val)
    if (editing?.cRate !== null && editing?.cRate && val !== '') {
      const derived = Number(val) / editing.cRate
      setEditMwh(derived.toFixed(2).replace(/\.?0+$/, ''))
    }
  }

  // ── MWh edit (custom only) ──────────────────────────────────────────────────

  function onMwhChange(val: string) {
    setEditMwh(val)
  }

  // ── Save / Cancel ───────────────────────────────────────────────────────────

  function handleSave() {
    const mw  = editMw  !== '' ? Number(editMw)  : null
    const mwh = editMwh !== '' ? Number(editMwh) : null
    applyPreset(editing?.id ?? null, mw, mwh)
    setEditing(null)
  }

  function handleCancel() {
    setEditing(null)
  }

  // ── Live C-rate for edit modal ──────────────────────────────────────────────

  const editMwN  = editMw  !== '' ? Number(editMw)  : null
  const editMwhN = editMwh !== '' ? Number(editMwh) : null
  const editC    = editMwN !== null && editMwhN !== null && editMwhN > 0
    ? editMwN / editMwhN : null

  // ── Saved override C-rate (card strip) ─────────────────────────────────────

  const liveC = ratedMw !== null && usableMwh !== null && usableMwh > 0
    ? ratedMw / usableMwh : null

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ── Card grid ─────────────────────────────────────────────────────── */}
      <div style={{ padding: '2px 0 6px' }}>

        <div style={{
          ...MONO, fontSize: 18, fontWeight: 700, letterSpacing: '0.12em',
          textTransform: 'uppercase', color: DIM, marginBottom: 18,
        }}>
          Choose a sizing profile for the next run
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 10, marginBottom: 16,
        }}>
          {PRESETS.map(p => {
            const active = selectedId === p.id
            return (
              <div
                key={p.id}
                role="button"
                tabIndex={0}
                onClick={() => openEdit(p)}
                onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && openEdit(p)}
                style={{
                  background:   active ? 'rgba(74,159,224,0.08)' : CANVAS,
                  border:       `1px solid ${active ? BATT : BORDER}`,
                  borderRadius: 7, padding: '14px 16px',
                  cursor: 'pointer', outline: 'none', position: 'relative',
                  transition: 'border-color 0.15s, background 0.15s',
                }}
              >
                {active && (
                  <div style={{
                    position: 'absolute', top: 10, right: 12,
                    width: 9, height: 9, borderRadius: '50%', background: BATT,
                  }} />
                )}

                {/* ⓘ info button — solid blue circle with white i */}
                {PRESET_TOOLTIPS[p.id] && (
                  <span
                    role="button"
                    aria-label={`About ${p.label}`}
                    style={{
                      position: 'absolute', top: 8,
                      right: active ? 28 : 10,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 16, height: 16,
                      borderRadius: '50%',
                      background: '#4a9fe0',
                      color: '#fff',
                      fontSize: 11, fontWeight: 700, fontStyle: 'italic',
                      lineHeight: 1,
                      cursor: 'help',
                      userSelect: 'none',
                      zIndex: 2,
                      flexShrink: 0,
                    }}
                    onMouseEnter={e => {
                      e.stopPropagation()
                      setTipState({ id: p.id, rect: (e.currentTarget as HTMLElement).getBoundingClientRect() })
                    }}
                    onMouseLeave={() => setTipState(null)}
                    onClick={e => e.stopPropagation()}
                  >
                    i
                  </span>
                )}

                <div style={{ ...MONO, fontSize: 18, fontWeight: 700, color: active ? BATT : TEXT, marginBottom: 5 }}>
                  {p.label}
                </div>
                <div style={{ ...MONO, fontSize: 14, color: DIM, marginBottom: 10, lineHeight: 1.4 }}>
                  {p.tag}
                </div>

                {p.ratedMw !== null ? (
                  <div style={{ marginBottom: 10 }}>
                    {/* MW is the bright editable number — hint with underline */}
                    <span style={{
                      ...MONO, fontSize: 24, fontWeight: 700,
                      color: active ? BATT : TEXT,
                      borderBottom: `1px dashed ${active ? BATT : BORDER}`,
                    }}>
                      {active && ratedMw !== null ? ratedMw : p.ratedMw} MW
                    </span>
                    <span style={{ ...MONO, fontSize: 16, color: LABEL, marginLeft: 6 }}>
                      / {active && usableMwh !== null ? usableMwh : p.usableMwh} MWh
                    </span>
                  </div>
                ) : (
                  <div style={{ ...MONO, fontSize: 20, color: LABEL, marginBottom: 10 }}>— / —</div>
                )}

                {p.ratedMw !== null && (
                  <div style={{
                    display: 'inline-block', ...MONO, fontSize: 14,
                    color:      active ? BATT : LABEL,
                    background: active ? 'rgba(74,159,224,0.12)' : 'rgba(74,159,224,0.04)',
                    border:     `1px solid ${active ? 'rgba(74,159,224,0.3)' : 'rgba(74,159,224,0.1)'}`,
                    borderRadius: 4, padding: '3px 8px', marginBottom: 10,
                  }}>
                    bridge {p.bridgeMin}
                  </div>
                )}

                <div style={{ ...MONO, fontSize: 13, color: DIM, lineHeight: 1.55 }}>
                  {p.desc}
                </div>

                {/* Tap-to-edit hint */}
                <div style={{
                  ...MONO, fontSize: 11, color: active ? BATT : '#333d47',
                  marginTop: 8, textAlign: 'right',
                }}>
                  click to configure →
                </div>
              </div>
            )
          })}
        </div>

        {/* Layman tooltip overlay */}
        {tipState && PRESET_TOOLTIPS[tipState.id] && (() => {
          const tip   = PRESET_TOOLTIPS[tipState.id]
          const r     = tipState.rect
          // Position below the ⓘ icon; flip above if near bottom of viewport
          const spaceBelow = window.innerHeight - r.bottom
          const top = spaceBelow > 200 ? r.bottom + 8 : r.top - 8
          const transform = spaceBelow > 200 ? 'none' : 'translateY(-100%)'
          return (
            <div style={{
              position: 'fixed',
              left: Math.min(r.left, window.innerWidth - 400 - 16),
              top,
              transform,
              width: 380,
              background: '#1a2332',
              border: `1px solid ${BATT}`,
              borderRadius: 9,
              padding: '16px 18px',
              zIndex: 999999,
              pointerEvents: 'none',
              boxShadow: '0 12px 40px rgba(0,0,0,0.7)',
            }}>
              <div style={{
                ...MONO, fontSize: 14, fontWeight: 700, color: BATT,
                marginBottom: 10, letterSpacing: '0.04em',
              }}>
                {tip.title}
              </div>
              <div style={{
                ...MONO, fontSize: 14, color: '#a0b0c0',
                lineHeight: 1.65,
              }}>
                {tip.body}
              </div>
            </div>
          )
        })()}

        {/* Live C-rate strip */}
        {liveC !== null && (
          <div style={{
            ...MONO, fontSize: 16,
            color:      cRateOk(liveC) ? TEAL : AMBER,
            background: cRateOk(liveC) ? 'rgba(63,182,168,0.07)' : 'rgba(240,136,62,0.07)',
            border:     `1px solid ${cRateOk(liveC) ? 'rgba(63,182,168,0.2)' : 'rgba(240,136,62,0.2)'}`,
            borderRadius: 5, padding: '7px 12px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: 10,
          }}>
            <span>
              {liveC.toFixed(2)} C-rate
              {cRateOk(liveC) ? ' ✓ within normal range (0.25–4 C)' : ' ⚠ outside normal range'}
            </span>
            <span style={{ color: BATT, marginLeft: 16 }}>{ratedMw} MW / {usableMwh} MWh</span>
          </div>
        )}

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          {selectedId !== null
            ? <div style={{ ...MONO, fontSize: 15, color: BATT }}>● Override active — applies when you start the next run.</div>
            : <div style={{ ...MONO, fontSize: 15, color: DIM }}>No override — scenario's stored BESS settings will be used.</div>
          }
          {selectedId !== null && (
            <span
              role="button"
              style={{ ...MONO, fontSize: 15, color: LABEL, cursor: 'pointer', textDecoration: 'underline' }}
              onClick={clearOverride}
            >
              Clear
            </span>
          )}
        </div>
      </div>

      {/* ── Edit modal ────────────────────────────────────────────────────────── */}
      {editing && (
        <div
          style={{
            position: 'fixed', inset: 0,
            background: 'rgba(0,0,0,0.72)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 99999,
          }}
          onClick={e => { if (e.target === e.currentTarget) handleCancel() }}
        >
          <div style={{
            background: '#161b22',
            border: `1px solid ${BATT}`,
            borderRadius: 12,
            padding: '32px 36px',
            width: 520,
            maxWidth: '90vw',
            boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
          }}>

            {/* Modal header */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ ...MONO, fontSize: 22, fontWeight: 700, color: BATT, marginBottom: 4 }}>
                {editing.label}
              </div>
              <div style={{ ...MONO, fontSize: 15, color: DIM }}>
                {editing.tag}
              </div>
            </div>

            {/* MW input — always editable, shown bright */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ ...MONO, fontSize: 14, color: LABEL, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                Rated power (MW)
              </div>
              <input
                autoFocus
                type="number"
                min={0.1}
                step={0.5}
                value={editMw}
                placeholder="e.g. 5"
                onChange={e => onMwChange(e.target.value)}
                style={{
                  width: '100%', boxSizing: 'border-box' as const,
                  background: '#0d1117',
                  border: `2px solid ${BATT}`,
                  borderRadius: 7, padding: '12px 16px',
                  ...MONO, fontSize: 28, fontWeight: 700, color: BATT,
                  outline: 'none',
                }}
              />
              {editing.cRate !== null && (
                <div style={{ ...MONO, fontSize: 13, color: DIM, marginTop: 6 }}>
                  Changing this value auto-updates MWh at {editing.cRate} C ({editing.tag.split('·')[0].trim()}).
                </div>
              )}
            </div>

            {/* MWh — read-only (derived) for presets, editable for custom */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ ...MONO, fontSize: 14, color: LABEL, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                Usable capacity (MWh)
                {editing.cRate !== null && (
                  <span style={{ color: DIM, fontWeight: 400, textTransform: 'none', letterSpacing: 0, marginLeft: 8 }}>
                    — auto-derived from {editing.cRate} C-rate
                  </span>
                )}
              </div>

              {editing.cRate !== null ? (
                /* Derived — display only */
                <div style={{
                  background: '#0a0f14',
                  border: `1px solid ${BORDER}`,
                  borderRadius: 7, padding: '12px 16px',
                  ...MONO, fontSize: 28, fontWeight: 700, color: TEXT,
                  opacity: 0.85,
                }}>
                  {editMwh || '—'} MWh
                </div>
              ) : (
                /* Custom — editable */
                <input
                  type="number"
                  min={0.1}
                  step={0.5}
                  value={editMwh}
                  placeholder="e.g. 5"
                  onChange={e => onMwhChange(e.target.value)}
                  style={{
                    width: '100%', boxSizing: 'border-box' as const,
                    background: '#0d1117',
                    border: `2px solid ${BORDER}`,
                    borderRadius: 7, padding: '12px 16px',
                    ...MONO, fontSize: 28, fontWeight: 700, color: TEXT,
                    outline: 'none',
                  }}
                  onFocus={e  => { e.currentTarget.style.borderColor = BATT }}
                  onBlur={e   => { e.currentTarget.style.borderColor = BORDER }}
                />
              )}
            </div>

            {/* Live C-rate inside modal */}
            {editC !== null && (
              <div style={{
                ...MONO, fontSize: 15,
                color:      cRateOk(editC) ? TEAL : AMBER,
                background: cRateOk(editC) ? 'rgba(63,182,168,0.07)' : 'rgba(240,136,62,0.07)',
                border:     `1px solid ${cRateOk(editC) ? 'rgba(63,182,168,0.25)' : 'rgba(240,136,62,0.25)'}`,
                borderRadius: 5, padding: '8px 14px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                marginBottom: 28,
              }}>
                <span>
                  {editC.toFixed(2)} C-rate
                  {cRateOk(editC) ? ' ✓ normal range (0.25–4 C)' : ' ⚠ outside normal range'}
                </span>
                <span style={{ color: BATT }}>
                  {editMwN} MW / {editMwhN?.toFixed ? editMwhN.toFixed(2) : editMwh} MWh
                </span>
              </div>
            )}

            {/* Buttons */}
            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button
                onClick={handleCancel}
                style={{
                  ...MONO, fontSize: 16, fontWeight: 600,
                  padding: '10px 24px', borderRadius: 7,
                  background: 'transparent',
                  border: `1px solid ${BORDER}`,
                  color: LABEL, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={editMw === '' || editMwh === ''}
                style={{
                  ...MONO, fontSize: 16, fontWeight: 700,
                  padding: '10px 28px', borderRadius: 7,
                  background: BATT,
                  border: 'none',
                  color: '#fff', cursor: 'pointer',
                  opacity: editMw === '' || editMwh === '' ? 0.45 : 1,
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
