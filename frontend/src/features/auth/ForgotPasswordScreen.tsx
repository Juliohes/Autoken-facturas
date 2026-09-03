// Recuperación de contraseña, paso 1 (Bloque 4 de PROMPT-AUTOFACTU-AUTH-COMPLETO, backend en
// identity/password_reset.py). Respuesta SIEMPRE genérica (200, anti-enumeración) salvo 429/503,
// que sí son visibles (no revelan si la cuenta existe, solo que hay demasiadas solicitudes o que el
// servicio está caído).
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../api/client'
import { Banner } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'
import { TENANT_NOT_FOUND_MESSAGE } from './authErrors'
import { AuthShell } from '../session/AuthShell'

type Status = 'idle' | 'submitting' | 'done'

export function ForgotPasswordScreen({ theme }: { theme: AppliedTheme }) {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setStatus('submitting')
    const { error: apiError, response } = await api.POST('/api/v1/auth/password/forgot', {
      body: { email },
    })
    if (apiError) {
      setStatus('idle')
      if (response.status === 429) {
        setError('Demasiadas solicitudes. Espera unos minutos antes de volver a intentarlo.')
      } else if (response.status === 404) {
        setError(TENANT_NOT_FOUND_MESSAGE)
      } else {
        setError('El servicio no está disponible ahora mismo. Inténtalo más tarde.')
      }
      return
    }
    setStatus('done')
  }

  return (
    <AuthShell theme={theme}>
      <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
        <h1 className="text-xl font-semibold">Recuperar contraseña</h1>

        {status === 'done' ? (
          <Banner tone="ok">
            Si existe una cuenta con ese email, te hemos enviado un enlace para restablecer tu
            contraseña. Revisa tu bandeja de entrada (y la carpeta de spam).
          </Banner>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} aria-label="Recuperar contraseña" className="space-y-4">
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Escribe tu email y, si tienes una cuenta, te enviaremos un enlace para elegir una
              contraseña nueva.
            </p>

            {error && (
              <p role="alert" className="text-sm" style={{ color: 'var(--tn-error)' }}>
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

            <button
              type="submit"
              disabled={status === 'submitting'}
              className="tn-btn tn-btn-primary tn-btn-lg w-full"
            >
              {status === 'submitting' ? 'Enviando…' : 'Enviar enlace'}
            </button>
          </form>
        )}

        <Link to="/login" className="tn-auth-link text-sm block text-center">
          Volver a iniciar sesión
        </Link>
      </div>
    </AuthShell>
  )
}
