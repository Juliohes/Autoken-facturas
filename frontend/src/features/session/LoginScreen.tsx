// Pantalla de login (S4.9, C1-C3). Solo conoce la sesión (`useSession`), nunca el router: la
// decisión de a dónde navegar tras un login correcto vive en `app/AppRoutes.tsx` (`LoginRoute`),
// que re-renderiza en cuanto el contexto de sesión pasa a `authenticated`. Los dos enlaces al pie
// (recuperar contraseña, solicitar acceso, Bloque 4 de PROMPT-AUTOFACTU-AUTH-COMPLETO) usan rutas
// literales, no `app/routes.ts` (esta pantalla no depende de `app/`, ver `routes.ts` §11).
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { PasswordField } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'
import { AuthShell } from './AuthShell'
import { useSession } from './SessionProvider'

export function LoginScreen({ theme }: { theme: AppliedTheme }) {
  const { login } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
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
    <AuthShell theme={theme}>
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

        <PasswordField
          label="Contraseña"
          id="login-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

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
          className="tn-btn tn-btn-primary tn-btn-lg w-full"
        >
          {submitting ? 'Entrando…' : 'Entrar'}
        </button>

        <div className="flex flex-col items-center gap-1 text-sm">
          <Link to="/registro" className="tn-auth-link">
            Regístrate
          </Link>
          <Link to="/recuperar" className="tn-auth-link">
            ¿No recuerdas tu contraseña?
          </Link>
        </div>
      </form>
    </AuthShell>
  )
}
