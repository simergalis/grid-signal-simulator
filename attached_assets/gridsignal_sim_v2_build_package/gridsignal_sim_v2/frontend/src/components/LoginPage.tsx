/**
 * LoginPage.tsx — Two-step email OTP authentication.
 *
 * Step 1: enter email → "Send code"   (POST /api/auth/request-code)
 * Step 2: enter 6-digit code → "Sign in"  (POST /api/auth/login)
 */

import { FormEvent, useState } from 'react'

interface Props {
  onAuthenticated: (displayName: string, role: string) => void
  adminMode?: boolean
}

type Step = 'email' | 'code'

export function LoginPage({ onAuthenticated, adminMode = false }: Props) {
  const [step,    setStep]    = useState<Step>('email')
  const [email,   setEmail]   = useState('')
  const [code,    setCode]    = useState('')
  const [error,   setError]   = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [resendIn, setResendIn] = useState(0)

  // ── Step 1: request a code ──────────────────────────────────────────────
  async function handleRequestCode(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const resp = await fetch('/api/auth/request-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (resp.ok) {
        setStep('code')
        startResendCountdown()
      } else {
        const body = await resp.json().catch(() => ({})) as { detail?: string }
        setError(body.detail ?? 'Could not send code — please try again.')
      }
    } catch {
      setError('Network error — please try again.')
    } finally {
      setLoading(false)
    }
  }

  // ── Step 2: verify code ─────────────────────────────────────────────────
  async function handleVerifyCode(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code }),
        credentials: 'include',
      })
      if (resp.ok) {
        const data = await resp.json() as { display_name: string; role: string }
        if (adminMode && data.role !== 'admin') {
          await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
          setError('Admin access required. Use the main sign-in page for operator access.')
        } else {
          onAuthenticated(data.display_name, data.role)
        }
      } else {
        const body = await resp.json().catch(() => ({})) as { detail?: string }
        setError(body.detail ?? 'Incorrect code — please try again.')
      }
    } catch {
      setError('Network error — please try again.')
    } finally {
      setLoading(false)
    }
  }

  // ── Resend cooldown ─────────────────────────────────────────────────────
  function startResendCountdown(secs = 60) {
    setResendIn(secs)
    const id = setInterval(() => {
      setResendIn(prev => {
        if (prev <= 1) { clearInterval(id); return 0 }
        return prev - 1
      })
    }, 1000)
  }

  async function handleResend() {
    if (resendIn > 0) return
    setError(null)
    setLoading(true)
    try {
      const resp = await fetch('/api/auth/request-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (resp.ok) {
        startResendCountdown()
        setCode('')
      } else {
        const body = await resp.json().catch(() => ({})) as { detail?: string }
        setError(body.detail ?? 'Could not resend code.')
      }
    } catch {
      setError('Network error — please try again.')
    } finally {
      setLoading(false)
    }
  }

  // ── Shared chrome ───────────────────────────────────────────────────────
  const inputCls = `rounded border border-border px-3 py-2 font-sans outline-none
                    focus:border-[#3fb6a8] transition-colors w-full`
  const inputStyle = { background: '#0b1017', color: '#e6ecf2', fontSize: 13 } as const

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center"
      style={{ background: '#0b1017' }}
    >
      {/* Brand mark */}
      <div className="flex items-center gap-3 mb-10">
        <svg width="28" height="32" viewBox="0 0 22 26" aria-hidden="true">
          <path d="M14 2L2 14h8l-2 10 12-14h-8z" fill="#3fb6a8" strokeLinejoin="round" />
        </svg>
        <div>
          <div className="font-sans font-bold tracking-[0.1em]"
               style={{ fontSize: 20, color: '#e6ecf2', letterSpacing: '0.1em' }}>
            GRIDSIGNAL
          </div>
          <div className="font-sans" style={{ fontSize: 11, color: '#4b5764', marginTop: 2 }}>
            Predictive power management
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-5 w-full max-w-sm rounded-lg border border-border p-8"
           style={{ background: '#111821' }}>

        <h1 className="font-sans font-semibold text-center"
            style={{ fontSize: 15, color: '#e6ecf2', marginBottom: 4 }}>
          {adminMode ? 'Admin sign-in' : 'Operator sign-in'}
        </h1>

        {/* ── Step 1: email ── */}
        {step === 'email' && (
          <form onSubmit={handleRequestCode} className="flex flex-col gap-5">
            <div className="flex flex-col gap-1.5">
              <label className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
                Email address
              </label>
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                className={inputCls}
                style={inputStyle}
              />
            </div>

            {error && <ErrorBox message={error} />}

            <button
              type="submit"
              disabled={loading}
              className="rounded px-4 py-2.5 font-sans font-semibold tracking-wide
                         transition-opacity disabled:opacity-50"
              style={{ background: '#3fb6a8', color: '#0b1017', fontSize: 13 }}
            >
              {loading ? 'Sending…' : 'Send code'}
            </button>

            <p className="font-sans text-center" style={{ fontSize: 11, color: '#4b5764' }}>
              {adminMode ? (
                <>Administrator accounts only.{' '}
                  <a href="/" style={{ color: '#3fb6a8', textDecoration: 'none' }}>
                    Operator sign-in →
                  </a>
                </>
              ) : 'Contact your administrator to request access.'}
            </p>
          </form>
        )}

        {/* ── Step 2: code ── */}
        {step === 'code' && (
          <form onSubmit={handleVerifyCode} className="flex flex-col gap-5">
            <p className="font-sans text-center" style={{ fontSize: 12, color: '#7d8b9c' }}>
              A 6-digit code was sent to<br />
              <span style={{ color: '#e6ecf2' }}>{email}</span>
            </p>

            <div className="flex flex-col gap-1.5">
              <label className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
                Sign-in code
              </label>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                required
                autoFocus
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                className={inputCls}
                style={{ ...inputStyle, fontSize: 22, letterSpacing: '0.25em', textAlign: 'center' }}
              />
            </div>

            {error && <ErrorBox message={error} />}

            <button
              type="submit"
              disabled={loading || code.length < 6}
              className="rounded px-4 py-2.5 font-sans font-semibold tracking-wide
                         transition-opacity disabled:opacity-50"
              style={{ background: '#3fb6a8', color: '#0b1017', fontSize: 13 }}
            >
              {loading ? 'Verifying…' : 'Sign in'}
            </button>

            <div className="flex justify-between items-center">
              <button
                type="button"
                onClick={() => { setStep('email'); setCode(''); setError(null) }}
                className="font-sans"
                style={{ fontSize: 11, color: '#4b5764', background: 'none', border: 'none', cursor: 'pointer' }}
              >
                ← Change email
              </button>
              <button
                type="button"
                disabled={resendIn > 0}
                onClick={handleResend}
                className="font-sans transition-opacity disabled:opacity-40"
                style={{ fontSize: 11, color: '#3fb6a8', background: 'none', border: 'none',
                         cursor: resendIn > 0 ? 'default' : 'pointer' }}
              >
                {resendIn > 0 ? `Resend in ${resendIn}s` : 'Resend code'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded px-3 py-2 font-sans text-center"
         style={{ background: '#2a1a1a', color: '#e05a5a', fontSize: 12, border: '1px solid #5a2020' }}>
      {message}
    </div>
  )
}
