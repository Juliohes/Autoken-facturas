// Recuperación de contraseña, paso 2 (Bloque 4 de PROMPT-AUTOFACTU-AUTH-COMPLETO). El token llega
// por `?token=` (enlace del email). Un token inválido/caducado/consumido, o de otro tenant (F2), da
// 401 sin distinguir el motivo (backend, identity/password_reset.py) -- aquí tampoco se distingue.
import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../../api/client'
import { Banner, PasswordField } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'
import { AuthShell } from '../session/AuthShell'

type Status = 'idle' | 'submitting' | 'done'

export function ResetPasswordScreen({ theme }: { theme: AppliedTheme }) {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    if (password !== passwordConfirm) {
      setError('Las contraseñas no coinciden.')
      return
    }
    if (!token) return
    setStatus('submitting')
    const { error: apiError, response } = await api.POST('/api/v1/auth/password/reset', {
      body: { token, password },
    })
    if (apiError) {
      setStatus('idle')
      if (response.status === 401) {
        setError('El enlace no es válido o ha caducado. Solicita uno nuevo.')
      } else if (response.status === 422) {
        setError('La contraseña no cumple los requisitos de seguridad.')
      } else {
        setError('El servicio no está disponible ahora mismo. Inténtalo más tarde.')
      }
      return
    }
    setStatus('done')
  }

  if (!token) {
    return (
      <AuthShell theme={theme}>
        <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
          <h1 className="text-xl font-semibold">Enlace no válido</h1>
          <Banner tone="bad">
            Este enlace de restablecimiento no es válido. Solicita uno nuevo.
          </Banner>
          <Link to="/recuperar" className="tn-auth-link text-sm">
            Solicitar un nuevo enlace
          </Link>
        </div>
      </AuthShell>
    )
  }

  if (status === 'done') {
    return (
      <AuthShell theme={theme}>
        <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
          <h1 className="text-xl font-semibold">Contraseña actualizada</h1>
          <Banner tone="ok">
            Tu contraseña se ha actualizado y hemos cerrado el resto de tus sesiones abiertas. Ya
            puedes iniciar sesión.
          </Banner>
          <Link to="/login" className="tn-auth-link text-sm">
            Iniciar sesión
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell theme={theme}>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        aria-label="Restablecer contraseña"
        className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8"
      >
        <h1 className="text-xl font-semibold">Elige una contraseña nueva</h1>

        {error && (
          <p role="alert" className="text-sm" style={{ color: 'var(--tn-error)' }}>
            {error}
          </p>
        )}

        <PasswordField
          label="Contraseña nueva"
          id="reset-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="new-password"
        />

        <PasswordField
          label="Repite la contraseña"
          id="reset-password-confirm"
          value={passwordConfirm}
          onChange={(e) => setPasswordConfirm(e.target.value)}
          required
          autoComplete="new-password"
        />

        <button
          type="submit"
          disabled={status === 'submitting'}
          className="tn-btn tn-btn-primary tn-btn-lg w-full"
        >
          {status === 'submitting' ? 'Guardando…' : 'Guardar contraseña'}
        </button>
      </form>
    </AuthShell>
  )
}
