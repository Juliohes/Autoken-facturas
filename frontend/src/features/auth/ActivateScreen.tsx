// Activación de cuenta (Bloque 4 de PROMPT-AUTOFACTU-AUTH-COMPLETO, backend en identity/activation.py).
// Dos pasos: 1) fijar contraseña (devuelve la URI `otpauth://` del secreto TOTP recién generado),
// 2) enrolar el segundo factor confirmando un código de la app de autenticación. El token de
// activación es de un solo uso: se consume al confirmar el TOTP, no al fijar la contraseña.
import { useState, type FormEvent } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../../api/client'
import { Banner, PasswordField } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'
import { TENANT_NOT_FOUND_MESSAGE } from './authErrors'
import { PASSWORD_POLICY_ERROR, PASSWORD_POLICY_HINT } from './passwordPolicy'
import { AuthShell } from '../session/AuthShell'

type Step =
  | { kind: 'password' }
  | { kind: 'totp'; otpauthUri: string }
  | { kind: 'done' }

/** Extrae el `secret` de una URI `otpauth://totp/...?secret=XXXX&issuer=...` para la entrada manual
 * (si el usuario no puede escanear el QR). Devuelve `null` si la URI no trae el parámetro. */
function extractSecret(otpauthUri: string): string | null {
  const query = otpauthUri.split('?')[1]
  if (!query) return null
  return new URLSearchParams(query).get('secret')
}

export function ActivateScreen({ theme }: { theme: AppliedTheme }) {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [step, setStep] = useState<Step>({ kind: 'password' })
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSetPassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    if (password !== passwordConfirm) {
      setError('Las contraseñas no coinciden.')
      return
    }
    if (!token) return
    setSubmitting(true)
    const { data, error: apiError, response } = await api.POST('/api/v1/auth/activate', {
      body: { token, password },
    })
    setSubmitting(false)
    if (apiError || !data) {
      if (response.status === 401) {
        setError('El enlace de activación no es válido o ha caducado. Pide a tu administrador que te lo reenvíe.')
      } else if (response.status === 422) {
        setError(PASSWORD_POLICY_ERROR)
      } else if (response.status === 404) {
        setError(TENANT_NOT_FOUND_MESSAGE)
      } else {
        setError('El servicio no está disponible ahora mismo. Inténtalo más tarde.')
      }
      return
    }
    setStep({ kind: 'totp', otpauthUri: data.otpauth_uri })
  }

  const handleConfirmTotp = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    if (!token) return
    setSubmitting(true)
    const { error: apiError, response } = await api.POST('/api/v1/auth/activate/confirm', {
      body: { token, totp_code: totpCode },
    })
    setSubmitting(false)
    if (apiError) {
      if (response.status === 429) {
        setError('Demasiados intentos con este código. Espera un momento y vuelve a probarlo.')
      } else if (response.status === 401) {
        setError('El enlace de activación no es válido o ha caducado. Pide a tu administrador que te lo reenvíe.')
      } else if (response.status === 404) {
        setError(TENANT_NOT_FOUND_MESSAGE)
      } else {
        setError('Código incorrecto. Revisa la app de autenticación e inténtalo de nuevo.')
      }
      return
    }
    setStep({ kind: 'done' })
  }

  if (!token) {
    return (
      <AuthShell theme={theme}>
        <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
          <h1 className="text-xl font-semibold">Enlace no válido</h1>
          <Banner tone="bad">Este enlace de activación no es válido.</Banner>
          <Link to="/login" className="tn-auth-link text-sm">
            Volver a iniciar sesión
          </Link>
        </div>
      </AuthShell>
    )
  }

  if (step.kind === 'done') {
    return (
      <AuthShell theme={theme}>
        <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
          <h1 className="text-xl font-semibold">Cuenta activada</h1>
          <Banner tone="ok">Tu cuenta está activada. Ya puedes iniciar sesión.</Banner>
          <Link to="/login" className="tn-auth-link text-sm">
            Iniciar sesión
          </Link>
        </div>
      </AuthShell>
    )
  }

  if (step.kind === 'totp') {
    const secret = extractSecret(step.otpauthUri)
    return (
      <AuthShell theme={theme}>
        <form
          onSubmit={(e) => void handleConfirmTotp(e)}
          aria-label="Verificar código de autenticación"
          className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8"
        >
          <h1 className="text-xl font-semibold">Configura la verificación en dos pasos</h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Escanea este código con tu app de autenticación (Google Authenticator, Authy...) y
            escribe el código de 6 dígitos que te muestre.
          </p>

          <div className="flex justify-center rounded-lg bg-white p-3">
            <QRCodeSVG value={step.otpauthUri} size={180} role="img" aria-label="Código QR de activación" />
          </div>

          {secret && (
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              ¿No puedes escanear el QR? Introduce este código manualmente:{' '}
              <code className="tn-login-input rounded px-1 py-0.5">{secret}</code>
            </p>
          )}

          {error && (
            <p role="alert" className="text-sm" style={{ color: 'var(--tn-error)' }}>
              {error}
            </p>
          )}

          <label className="tn-login-label flex flex-col text-sm">
            Código de verificación
            <input
              type="text"
              required
              inputMode="numeric"
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value)}
              className="tn-login-input rounded px-2 py-1"
            />
          </label>

          <button
            type="submit"
            disabled={submitting}
            className="tn-btn tn-btn-primary tn-btn-lg w-full"
          >
            {submitting ? 'Verificando…' : 'Activar cuenta'}
          </button>
        </form>
      </AuthShell>
    )
  }

  return (
    <AuthShell theme={theme}>
      <form
        onSubmit={(e) => void handleSetPassword(e)}
        aria-label="Activar cuenta"
        className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8"
      >
        <h1 className="text-xl font-semibold">Activa tu cuenta</h1>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Elige tu contraseña para completar la activación.
        </p>

        {error && (
          <p role="alert" className="text-sm" style={{ color: 'var(--tn-error)' }}>
            {error}
          </p>
        )}

        <PasswordField
          label="Contraseña"
          id="activate-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="new-password"
          hint={PASSWORD_POLICY_HINT}
        />

        <PasswordField
          label="Repite la contraseña"
          id="activate-password-confirm"
          value={passwordConfirm}
          onChange={(e) => setPasswordConfirm(e.target.value)}
          required
          autoComplete="new-password"
        />

        <button
          type="submit"
          disabled={submitting}
          className="tn-btn tn-btn-primary tn-btn-lg w-full"
        >
          {submitting ? 'Guardando…' : 'Continuar'}
        </button>
      </form>
    </AuthShell>
  )
}
