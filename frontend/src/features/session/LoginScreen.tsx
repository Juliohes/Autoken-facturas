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
    <main className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-100">
      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="w-full max-w-sm space-y-4 rounded-xl border border-slate-700 bg-slate-800 p-8"
      >
        {theme.logoUrl && (
          // `referrerPolicy="no-referrer"`: el logo lo aloja el propio tenant (URL de terceros
          // potencialmente), evita filtrar el Referer (con el subdominio del tenant) a ese host.
          <img
            src={theme.logoUrl}
            alt={theme.appName}
            referrerPolicy="no-referrer"
            className="mx-auto mb-2 max-h-16"
          />
        )}
        <h1 className="text-xl font-semibold">Iniciar sesión</h1>

        {error && (
          <p role="alert" className="text-sm text-red-400">
            {error}
          </p>
        )}

        <label className="flex flex-col text-sm text-slate-300">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-slate-600 bg-slate-900 px-2 py-1"
          />
        </label>

        <label className="flex flex-col text-sm text-slate-300">
          Contraseña
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-slate-600 bg-slate-900 px-2 py-1"
          />
        </label>

        {totpRequired && (
          <label className="flex flex-col text-sm text-slate-300">
            Código de verificación
            <input
              type="text"
              required
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              className="rounded border border-slate-600 bg-slate-900 px-2 py-1"
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
    </main>
  )
}
