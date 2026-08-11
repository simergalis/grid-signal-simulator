/**
 * BessConfigWidget.tsx — BESS sizing config shown in the Energy Storage modal
 * when no run is active.
 *
 * Writes to bessConfigStore, which RunControlBar reads at run-start.
 * Leave either field empty to use whatever the selected scenario stores.
 */

import { useBessConfigStore } from '../../store/bessConfigStore'

const MONO = { fontFamily: "'SF Mono','Roboto Mono',Menlo,Consolas,monospace" }
const BATT = '#4a9fe0'

export function BessConfigWidget() {
  const ratedMw     = useBessConfigStore(s => s.ratedMw)
  const usableMwh   = useBessConfigStore(s => s.usableMwh)
  const setRatedMw  = useBessConfigStore(s => s.setRatedMw)
  const setUsableMwh= useBessConfigStore(s => s.setUsableMwh)

  const inputStyle = {
    width: '100%',
    background: '#0d1117',
    border: '1px solid #2a3a4a',
    borderRadius: 5,
    padding: '7px 10px',
    ...MONO,
    fontSize: 18,
    color: '#c9d1d9',
    outline: 'none',
    boxSizing: 'border-box' as const,
  }

  const focusStyle = (e: React.FocusEvent<HTMLInputElement>) => {
    e.currentTarget.style.borderColor = BATT
  }
  const blurStyle = (e: React.FocusEvent<HTMLInputElement>) => {
    e.currentTarget.style.borderColor = '#2a3a4a'
  }

  return (
    <div style={{ padding: '4px 0 8px' }}>
      {/* Header */}
      <div style={{
        ...MONO, fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
        textTransform: 'uppercase', color: '#4b5764', marginBottom: 16,
      }}>
        Configure BESS for next run
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
        {/* Rated MW */}
        <div>
          <div style={{ ...MONO, fontSize: 10, color: '#6e7681', marginBottom: 5 }}>
            Rated power (MW)
          </div>
          <input
            type="number"
            style={inputStyle}
            value={ratedMw ?? ''}
            placeholder="e.g. 5.0"
            min={0.1}
            step={0.5}
            onFocus={focusStyle}
            onBlur={blurStyle}
            onChange={e => setRatedMw(e.target.value !== '' ? Number(e.target.value) : null)}
          />
          <div style={{ ...MONO, fontSize: 9, color: '#4b5764', marginTop: 4 }}>
            Peak charge / discharge rate
          </div>
        </div>

        {/* Usable MWh */}
        <div>
          <div style={{ ...MONO, fontSize: 10, color: '#6e7681', marginBottom: 5 }}>
            Usable capacity (MWh)
          </div>
          <input
            type="number"
            style={inputStyle}
            value={usableMwh ?? ''}
            placeholder="e.g. 2.0"
            min={0.1}
            step={0.5}
            onFocus={focusStyle}
            onBlur={blurStyle}
            onChange={e => setUsableMwh(e.target.value !== '' ? Number(e.target.value) : null)}
          />
          <div style={{ ...MONO, fontSize: 9, color: '#4b5764', marginTop: 4 }}>
            Total energy the battery can store
          </div>
        </div>
      </div>

      {/* C-rate hint */}
      {ratedMw !== null && usableMwh !== null && usableMwh > 0 && (() => {
        const c = ratedMw / usableMwh
        const ok = c >= 0.25 && c <= 4.0
        return (
          <div style={{
            ...MONO, fontSize: 10,
            color: ok ? '#3fb6a8' : '#f0883e',
            background: ok ? 'rgba(63,182,168,0.07)' : 'rgba(240,136,62,0.07)',
            border: `1px solid ${ok ? 'rgba(63,182,168,0.2)' : 'rgba(240,136,62,0.2)'}`,
            borderRadius: 4, padding: '5px 9px',
          }}>
            {c.toFixed(2)} C-rate {ok ? '✓ within normal range (0.25–4 C)' : '⚠ outside normal range'}
          </div>
        )
      })()}

      {/* Active override indicator */}
      {(ratedMw !== null || usableMwh !== null) && (
        <div style={{
          marginTop: 12, ...MONO, fontSize: 9, color: BATT,
          borderTop: '1px solid #1a2a36', paddingTop: 10,
        }}>
          ● Override active — will apply when you start the next run.{' '}
          <span
            role="button"
            style={{ cursor: 'pointer', textDecoration: 'underline', color: '#6e7681' }}
            onClick={() => { setRatedMw(null); setUsableMwh(null) }}
          >
            Clear
          </span>
        </div>
      )}

      {(ratedMw === null && usableMwh === null) && (
        <div style={{ ...MONO, fontSize: 9, color: '#4b5764', marginTop: 8 }}>
          Leave blank to use the scenario's stored BESS settings.
        </div>
      )}
    </div>
  )
}
