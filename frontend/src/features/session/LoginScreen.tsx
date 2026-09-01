// Pantalla de login (S4.9, C1-C3). Solo conoce la sesión (`useSession`), nunca el router: la
// decisión de a dónde navegar tras un login correcto vive en `app/AppRoutes.tsx` (`LoginRoute`),
// que re-renderiza en cuanto el contexto de sesión pasa a `authenticated`.
import { useState, type FormEvent } from 'react'

import type { AppliedTheme } from '../tenancy/theme'
import { useSession } from './SessionProvider'

export function LoginScreen({ theme }: { theme: AppliedTheme }) {
  const { login } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordVisible, setPasswordVisible] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const [totpRequired, setTotpRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    const result = await login(email, password, totpRequired ? totpCode : undefined)
    setSubmitting(false)
    if (result.outcome === 'totp_required') {
      setTotpRequired(true)
      return
    }
    if (result.outcome === 'error') setError(result.message)
  }

  return (
    <main className="tn-login-shell flex min-h-screen items-center justify-center">
      <div className="tn-auth-layout">
        <section className="tn-auth-brand tn-liquid-glass" aria-labelledby="auth-brand-title">
          {theme.logoUrl && (
            <img
              src={theme.logoUrl}
              alt={theme.appName}
              referrerPolicy="no-referrer"
              className="tn-brand-logo"
            />
          )}
          <h1 id="auth-brand-title">Gestiona tus facturas con claridad</h1>
          <p>Revisa, confirma y organiza tu trabajo diario desde un solo lugar.</p>
        </section>
        <form
          onSubmit={(e) => void handleSubmit(e)}
          aria-label="Inicio de sesión"
          className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8"
        >
        <h1 className="text-xl font-semibold">Iniciar sesión</h1>

        {error && (
          <p role="alert" className="text-sm text-fg" style={{ color: 'var(--tn-error)' }}>
            {error}
          </p>
        )}

        <label className="tn-login-label flex flex-col text-sm">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="tn-login-input rounded px-2 py-1"
          />
        </label>

        <label className="tn-login-label flex flex-col text-sm">
          Contraseña
          <span className="tn-password-field">
            <input
              id="login-password"
              type={passwordVisible ? 'text' : 'password'}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="tn-login-input rounded px-2 py-1"
            />
            <button
              type="button"
              aria-label={passwordVisible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              aria-controls="login-password"
              aria-pressed={passwordVisible}
              className="tn-password-toggle"
              onClick={() => setPasswordVisible((visible) => !visible)}
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                {passwordVisible ? (
                  <>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A10.8 10.8 0 0 1 12 5c5 0 8.6 4.2 9.8 7a12.8 12.8 0 0 1-3 4.4M6.2 6.2A13.2 13.2 0 0 0 2.2 12c1.2 2.8 4.8 7 9.8 7 1 0 2-.2 2.9-.5" />
                  </>
                ) : (
                  <>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.2 12C3.4 9.2 7 5 12 5s8.6 4.2 9.8 7c-1.2 2.8-4.8 7-9.8 7s-8.6-4.2-9.8-7Z" />
                    <circle cx="12" cy="12" r="2.5" />
                  </>
                )}
              </svg>
            </button>
          </span>
        </label>

        {totpRequired && (
          <label className="tn-login-label flex flex-col text-sm">
            Código de verificación
            <input
              type="text"
              required
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              className="tn-login-input rounded px-2 py-1"
            />
          </label>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-40"
        >
          {submitting ? 'Entrando…' : 'Entrar'}
        </button>
        </form>
      </div>
    </main>
  )
}
