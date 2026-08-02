/**
 * LoginPage.tsx — Authentication gate for the GridSignal operator interface.
 *
 * Users must supply their registered email address, mobile phone number,
 * and password.  All three fields must match what the admin registered.
 *
 * On success the server sets an httpOnly session cookie; the page calls
 * onAuthenticated() so App.tsx can unmount this component and show the
 * main interface.
 */

import { FormEvent, useState } from 'react'

interface Props {
  onAuthenticated: (displayName: string, role: string) => void
  /** When true the form is the admin-only entry point (/admin path). */
  adminMode?: boolean
}

export function LoginPage({ onAuthenticated, adminMode = false }: Props) {
  const [email,    setEmail]    = useState('')
  const [phone,    setPhone]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState<string | null>(null)
  const [loading,  setLoading]  = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, phone, password }),
        credentials: 'include',
      })
      if (resp.ok) {
        const data = await resp.json() as { display_name: string; role: string }
        if (adminMode && data.role !== 'admin') {
          // Clear the session immediately — non-admins must not stay logged in
          // via this entry point.
          await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {})
          setError('Admin access required. Use the main login page for operator access.')
        } else {
          onAuthenticated(data.display_name, data.role)
        }
      } else {
        const body = await resp.json().catch(() => ({})) as { detail?: string }
        setError(body.detail ?? 'Login failed — please check your credentials.')
      }
    } catch {
      setError('Network error — please try again.')
    } finally {
      setLoading(false)
    }
  }

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
          <div
            className="font-sans font-bold tracking-[0.1em]"
            style={{ fontSize: 20, color: '#e6ecf2', letterSpacing: '0.1em' }}
          >
            GRIDSIGNAL
          </div>
          <div className="font-sans" style={{ fontSize: 11, color: '#4b5764', marginTop: 2 }}>
            Predictive power management
          </div>
        </div>
      </div>

      {/* Login card */}
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-5 w-full max-w-sm rounded-lg border border-border p-8"
        style={{ background: '#111821' }}
      >
        <h1
          className="font-sans font-semibold text-center"
          style={{ fontSize: 15, color: '#e6ecf2', marginBottom: 4 }}
        >
          {adminMode ? 'Admin sign-in' : 'Operator sign-in'}
        </h1>

        {/* Email */}
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
            className="rounded border border-border px-3 py-2 font-sans outline-none
                       focus:border-[#3fb6a8] transition-colors"
            style={{ background: '#0b1017', color: '#e6ecf2', fontSize: 13 }}
          />
        </div>

        {/* Phone */}
        <div className="flex flex-col gap-1.5">
          <label className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
            Mobile phone number
          </label>
          <input
            type="tel"
            autoComplete="tel"
            required
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="+1 555 000 0000"
            className="rounded border border-border px-3 py-2 font-sans outline-none
                       focus:border-[#3fb6a8] transition-colors"
            style={{ background: '#0b1017', color: '#e6ecf2', fontSize: 13 }}
          />
        </div>

        {/* Password */}
        <div className="flex flex-col gap-1.5">
          <label className="font-sans" style={{ fontSize: 11, color: '#7d8b9c' }}>
            Password
          </label>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="••••••••"
            className="rounded border border-border px-3 py-2 font-sans outline-none
                       focus:border-[#3fb6a8] transition-colors"
            style={{ background: '#0b1017', color: '#e6ecf2', fontSize: 13 }}
          />
        </div>

        {/* Error */}
        {error && (
          <div
            className="rounded px-3 py-2 font-sans text-center"
            style={{ background: '#2a1a1a', color: '#e05a5a', fontSize: 12, border: '1px solid #5a2020' }}
          >
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="rounded px-4 py-2.5 font-sans font-semibold tracking-wide
                     transition-opacity disabled:opacity-50"
          style={{ background: '#3fb6a8', color: '#0b1017', fontSize: 13 }}
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="font-sans text-center" style={{ fontSize: 11, color: '#4b5764' }}>
          {adminMode ? (
            <>
              Administrator accounts only.{' '}
              <a href="/" style={{ color: '#3fb6a8', textDecoration: 'none' }}>
                Operator sign-in →
              </a>
            </>
          ) : (
            'Contact your administrator to request access.'
          )}
        </p>
      </form>
    </div>
  )
}
