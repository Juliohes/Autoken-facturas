// Alta autoservicio (Bloque 4 de PROMPT-AUTOFACTU-AUTH-COMPLETO, backend en identity/registration.py).
// Respuesta SIEMPRE genérica (201, anti-enumeración): esta pantalla nunca puede saber ni insinuar si
// el email ya existía, solo mostrar el mismo mensaje de éxito en cualquier caso.
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import { Banner, PasswordField } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'
import { TENANT_NOT_FOUND_MESSAGE } from './authErrors'
import { PASSWORD_POLICY_ERROR, PASSWORD_POLICY_HINT, WEAK_PASSWORD_DETAIL } from './passwordPolicy'
import { AuthShell } from '../session/AuthShell'

const LEGAL_CONSENT_REQUIRED_DETAIL = 'legal consent is required'

type Status = 'idle' | 'submitting' | 'done'

export function RegisterScreen({ theme }: { theme: AppliedTheme }) {
  const [email, setEmail] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [cif, setCif] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [legalConsent, setLegalConsent] = useState(false)
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    if (password !== passwordConfirm) {
      setError('Las contraseñas no coinciden.')
      return
    }
    setStatus('submitting')
    const { error: apiError, response } = await api.POST('/api/v1/register', {
      body: { email, company_name: companyName, cif, password, legal_consent: legalConsent },
    })
    if (apiError) {
      setStatus('idle')
      const detail = errorDetail(apiError)
      if (response.status === 429) {
        setError('Demasiadas solicitudes desde tu conexión. Inténtalo más tarde.')
      } else if (response.status === 404) {
        setError(TENANT_NOT_FOUND_MESSAGE)
      } else if (detail === WEAK_PASSWORD_DETAIL) {
        setError(PASSWORD_POLICY_ERROR)
      } else if (detail === LEGAL_CONSENT_REQUIRED_DETAIL) {
        setError('Tienes que aceptar los términos del servicio y la política de privacidad para continuar.')
      } else {
        setError(detail ?? 'No se pudo completar el alta. Revisa los datos.')
      }
      return
    }
    setStatus('done')
  }

  if (status === 'done') {
    return (
      <AuthShell theme={theme}>
        <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
          <h1 className="text-xl font-semibold">Solicitud enviada</h1>
          <Banner tone="ok">
            Un administrador de tu asesoría revisará tu solicitud antes de darte acceso.
          </Banner>
          <Link to="/login" className="tn-auth-link text-sm">
            Volver a iniciar sesión
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell theme={theme}>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        aria-label="Solicitar acceso"
        className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8"
      >
        <h1 className="text-xl font-semibold">Solicitar acceso</h1>

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

        <label className="tn-login-label flex flex-col text-sm">
          Razón Social
          <input
            type="text"
            required
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            className="tn-login-input rounded px-2 py-1"
          />
        </label>

        <label className="tn-login-label flex flex-col text-sm">
          CIF
          <input
            type="text"
            required
            value={cif}
            onChange={(e) => setCif(e.target.value)}
            className="tn-login-input rounded px-2 py-1"
          />
        </label>

        <PasswordField
          label="Contraseña"
          id="register-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="new-password"
          hint={PASSWORD_POLICY_HINT}
        />

        <PasswordField
          label="Repite la contraseña"
          id="register-password-confirm"
          value={passwordConfirm}
          onChange={(e) => setPasswordConfirm(e.target.value)}
          required
          autoComplete="new-password"
        />

        <label className="flex items-start gap-2 text-sm tn-login-label">
          <input
            type="checkbox"
            required
            checked={legalConsent}
            onChange={(e) => setLegalConsent(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            Acepto los{' '}
            <Link to="/terminos" target="_blank" className="tn-auth-link">
              términos del servicio
            </Link>{' '}
            y la{' '}
            <Link to="/privacidad" target="_blank" className="tn-auth-link">
              política de privacidad
            </Link>{' '}
            de Autofactu.
          </span>
        </label>

        <button
          type="submit"
          disabled={status === 'submitting'}
          className="tn-btn tn-btn-primary tn-btn-lg w-full"
        >
          {status === 'submitting' ? 'Enviando…' : 'Solicitar acceso'}
        </button>

        <Link to="/login" className="tn-auth-link text-sm block text-center">
          Ya tengo cuenta, iniciar sesión
        </Link>
      </form>
    </AuthShell>
  )
}
