/**
 * BessConfigWidget.tsx — BESS sizing configuration shown in the Energy Storage
 * modal when no run is active.
 *
 * Presents 5 credible industry presets (each teaching one C-rate regime) plus
 * a Custom option. Writes to bessConfigStore; RunControlBar reads the store at
 * run-start and sends the values as overrides in POST /runs.
 */

import { useState } from 'react'
import { useBessConfigStore } from '../../store/bessConfigStore'

// ── Preset definitions ───────────────────────────────────────────────────────

interface Preset {
  id:        string
  label:     string
  tag:       string           // short use-case label
  cRate:     number | null    // null = custom
  ratedMw:   number | null
  usableMwh: number | null
  desc:      string           // one-liner educational copy
  bridgeMin: string           // expected bridge duration at rated discharge
}

const PRESETS: Preset[] = [
  {
    id:        'long-bridge',
    label:     'Long Bridge',
    tag:       'Renewables shifting · 0.25 C',
    cRate:     0.25,
    ratedMw:   5,
    usableMwh: 20,
    bridgeMin: '~4 h',
    desc:      'Matches long-duration solar variability or extended grid faults. Energy-dense, cheap per MWh, slow to recharge.',
  },
  {
    id:        'grid-firm',
    label:     'Grid Firming',
    tag:       'Backup islanding · 0.5 C',
    cRate:     0.5,
    ratedMw:   5,
    usableMwh: 10,
    bridgeMin: '~2 h',
    desc:      'The most common data-centre UPS configuration. Bridges a full generator start sequence with comfortable margin.',
  },
  {
    id:        'freq-anchor',
    label:     'Freq. Anchor',
    tag:       'Frequency response · 1 C',
    cRate:     1.0,
    ratedMw:   5,
    usableMwh: 5,
    bridgeMin: '~60 min',
    desc:      'Balanced for fast frequency injection and 1-hour bridging. Simulator default — anchor reserve is a small fraction of rated power.',
  },
  {
    id:        'peak-shave',
    label:     'Peak Shaving',
    tag:       'Demand charge mgmt · 2 C',
    cRate:     2.0,
    ratedMw:   5,
    usableMwh: 2.5,
    bridgeMin: '~30 min',
    desc:      'Optimised for high-power short bursts. Power-dense chemistry (NMC). Bridge duration is short — best paired with fast gas peakers.',
  },
  {
    id:        'fast-ffr',
    label:     'Fast FFR',
    tag:       'Grid code compliance · 4 C',
    cRate:     4.0,
    ratedMw:   5,
    usableMwh: 1.25,
    bridgeMin: '~15 min',
    desc:      'Maximum response speed. The 1 MW anchor reserve withheld (§7.1.2) consumes most usable capacity — bridge cover is minimal.',
  },
  {
    id:        'custom',
    label:     'Custom',
    tag:       'Set your own values',
    cRate:     null,
    ratedMw:   null,
    usableMwh: null,
    bridgeMin: '—',
    desc:      'Enter any rated power and usable capacity. C-rate and validity are shown live.',
  },
]

// ── Colour palette ────────────────────────────────────────────────────────────

const BATT   = '#4a9fe0'
const TEAL   = '#3fb6a8'
const AMBER  = '#f0883e'
const DIM    = '#4b5764'
const LABEL  = '#6e7681'
const BORDER = '#2a3a4a'
const CANVAS = '#0d1117'
const TEXT   = '#c9d1d9'
const MONO   = { fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace" }

// ── C-rate colour helper ──────────────────────────────────────────────────────

function cRateColour(c: number): string {
  if (c < 0.25 || c > 4) return AMBER
  return TEAL
}

// ── Main widget ───────────────────────────────────────────────────────────────

export function BessConfigWidget() {
  const ratedMw      = useBessConfigStore(s => s.ratedMw)
  const usableMwh    = useBessConfigStore(s => s.usableMwh)
  const setRatedMw   = useBessConfigStore(s => s.setRatedMw)
  const setUsableMwh = useBessConfigStore(s => s.setUsableMwh)

  // Track which preset card is selected (null = nothing selected yet → show "use scenario default")
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Custom input raw strings (so user can type partial numbers)
  const [customMwStr,  setCustomMwStr]  = useState('')
  const [customMwhStr, setCustomMwhStr] = useState('')

  function selectPreset(p: Preset) {
    setSelectedId(p.id)
    if (p.id === 'custom') {
      // Retain whatever is already in the store as the custom starting point
      setCustomMwStr(ratedMw  !== null ? String(ratedMw)  : '')
      setCustomMwhStr(usableMwh !== null ? String(usableMwh) : '')
      // Don't clear store — keep previous value until user edits
    } else {
      setRatedMw(p.ratedMw)
      setUsableMwh(p.usableMwh)
    }
  }

  function handleCustomMw(val: string) {
    setCustomMwStr(val)
    setRatedMw(val !== '' ? Number(val) : null)
  }

  function handleCustomMwh(val: string) {
    setCustomMwhStr(val)
    setUsableMwh(val !== '' ? Number(val) : null)
  }

  function clearAll() {
    setSelectedId(null)
    setRatedMw(null)
    setUsableMwh(null)
    setCustomMwStr('')
    setCustomMwhStr('')
  }

  // Compute live C-rate for display
  const liveC = (ratedMw !== null && usableMwh !== null && usableMwh > 0)
    ? ratedMw / usableMwh
    : null

  return (
    <div style={{ padding: '2px 0 6px' }}>

      {/* Section header */}
      <div style={{
        ...MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
        textTransform: 'uppercase', color: DIM, marginBottom: 14,
      }}>
        Choose a sizing profile for the next run
      </div>

      {/* Preset cards — 3-column grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 8,
        marginBottom: 14,
      }}>
        {PRESETS.map(p => {
          const active = selectedId === p.id
          return (
            <div
              key={p.id}
              role="button"
              tabIndex={0}
              onClick={() => selectPreset(p)}
              onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && selectPreset(p)}
              style={{
                background:   active ? 'rgba(74,159,224,0.08)' : CANVAS,
                border:       `1px solid ${active ? BATT : BORDER}`,
                borderRadius: 6,
                padding:      '10px 12px',
                cursor:       'pointer',
                transition:   'border-color 0.15s, background 0.15s',
                position:     'relative',
                outline:      'none',
              }}
            >
              {/* Active dot */}
              {active && (
                <div style={{
                  position: 'absolute', top: 8, right: 9,
                  width: 7, height: 7, borderRadius: '50%',
                  background: BATT,
                }} />
              )}

              {/* Label */}
              <div style={{
                ...MONO, fontSize: 11, fontWeight: 700,
                color: active ? BATT : TEXT,
                marginBottom: 4,
              }}>
                {p.label}
              </div>

              {/* Tag / C-rate */}
              <div style={{
                ...MONO, fontSize: 9, color: DIM,
                marginBottom: 7, lineHeight: 1.4,
              }}>
                {p.tag}
              </div>

              {/* MW / MWh values */}
              {p.ratedMw !== null ? (
                <div style={{ marginBottom: 8 }}>
                  <span style={{ ...MONO, fontSize: 16, fontWeight: 700, color: active ? BATT : TEXT }}>
                    {p.ratedMw} MW
                  </span>
                  <span style={{ ...MONO, fontSize: 11, color: LABEL, marginLeft: 4 }}>
                    / {p.usableMwh} MWh
                  </span>
                </div>
              ) : (
                <div style={{ ...MONO, fontSize: 13, color: LABEL, marginBottom: 8 }}>
                  — / —
                </div>
              )}

              {/* Bridge duration pill */}
              {p.ratedMw !== null && (
                <div style={{
                  display:      'inline-block',
                  ...MONO, fontSize: 9,
                  color:        active ? BATT : LABEL,
                  background:   active ? 'rgba(74,159,224,0.12)' : 'rgba(74,159,224,0.04)',
                  border:       `1px solid ${active ? 'rgba(74,159,224,0.3)' : 'rgba(74,159,224,0.1)'}`,
                  borderRadius: 3,
                  padding:      '2px 6px',
                  marginBottom: 8,
                }}>
                  bridge {p.bridgeMin}
                </div>
              )}

              {/* Description */}
              <div style={{
                ...MONO, fontSize: 9, color: DIM,
                lineHeight: 1.5,
              }}>
                {p.desc}
              </div>
            </div>
          )
        })}
      </div>

      {/* Custom inputs — revealed when "Custom" card is selected */}
      {selectedId === 'custom' && (
        <div style={{
          background: CANVAS,
          border:     `1px solid ${BATT}`,
          borderRadius: 6,
          padding:    '12px 14px',
          marginBottom: 12,
        }}>
          <div style={{
            ...MONO, fontSize: 9, color: LABEL, marginBottom: 10,
            textTransform: 'uppercase', letterSpacing: '0.1em',
          }}>
            Custom values
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <div style={{ ...MONO, fontSize: 10, color: LABEL, marginBottom: 5 }}>
                Rated power (MW)
              </div>
              <input
                type="number"
                style={{
                  width: '100%', boxSizing: 'border-box' as const,
                  background: '#0a0f14', border: `1px solid ${BORDER}`,
                  borderRadius: 4, padding: '7px 10px',
                  ...MONO, fontSize: 15, color: TEXT, outline: 'none',
                }}
                value={customMwStr}
                placeholder="e.g. 5.0"
                min={0.1} step={0.5}
                onFocus={e  => { e.currentTarget.style.borderColor = BATT }}
                onBlur={e   => { e.currentTarget.style.borderColor = BORDER }}
                onChange={e => handleCustomMw(e.target.value)}
              />
            </div>
            <div>
              <div style={{ ...MONO, fontSize: 10, color: LABEL, marginBottom: 5 }}>
                Usable capacity (MWh)
              </div>
              <input
                type="number"
                style={{
                  width: '100%', boxSizing: 'border-box' as const,
                  background: '#0a0f14', border: `1px solid ${BORDER}`,
                  borderRadius: 4, padding: '7px 10px',
                  ...MONO, fontSize: 15, color: TEXT, outline: 'none',
                }}
                value={customMwhStr}
                placeholder="e.g. 5.0"
                min={0.1} step={0.5}
                onFocus={e  => { e.currentTarget.style.borderColor = BATT }}
                onBlur={e   => { e.currentTarget.style.borderColor = BORDER }}
                onChange={e => handleCustomMwh(e.target.value)}
              />
            </div>
          </div>
        </div>
      )}

      {/* Live C-rate + active override status */}
      {liveC !== null && (
        <div style={{
          ...MONO, fontSize: 10,
          color:      cRateColour(liveC),
          background: liveC >= 0.25 && liveC <= 4
            ? 'rgba(63,182,168,0.07)' : 'rgba(240,136,62,0.07)',
          border: `1px solid ${liveC >= 0.25 && liveC <= 4
            ? 'rgba(63,182,168,0.2)' : 'rgba(240,136,62,0.2)'}`,
          borderRadius: 4, padding: '5px 10px',
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
        }}>
          <span>
            {liveC.toFixed(2)} C-rate
            {liveC >= 0.25 && liveC <= 4
              ? ' ✓ within normal range (0.25–4 C)'
              : ' ⚠ outside normal range'}
          </span>
          <span style={{ color: BATT, marginLeft: 16 }}>
            {ratedMw} MW / {usableMwh} MWh
          </span>
        </div>
      )}

      {/* Footer row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {selectedId !== null ? (
          <div style={{ ...MONO, fontSize: 9, color: BATT }}>
            ● Override active — applies when you start the next run.
          </div>
        ) : (
          <div style={{ ...MONO, fontSize: 9, color: DIM }}>
            No override — scenario's stored BESS settings will be used.
          </div>
        )}
        {selectedId !== null && (
          <span
            role="button"
            style={{ ...MONO, fontSize: 9, color: LABEL, cursor: 'pointer', textDecoration: 'underline' }}
            onClick={clearAll}
          >
            Clear
          </span>
        )}
      </div>
    </div>
  )
}
