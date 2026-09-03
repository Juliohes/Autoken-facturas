// Decisión de un alta por email, sin iniciar sesión (2026-09-03, a petición de Julio, sustituye la
// verificación de email del registrante: backend en identity/registration_decision.py). El enlace
// del email SOLO trae hasta aquí (GET, no muta nada); la decisión de verdad ocurre al pulsar uno de
// los dos botones (POST) -- un cliente de correo o un antivirus que "previsite" el enlace del email
// no puede aprobar ni rechazar nada por su cuenta, solo cargar esta pantalla de confirmación.
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import { Banner, Button, Spinner } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'
import { TENANT_NOT_FOUND_MESSAGE } from './authErrors'
import { AuthShell } from '../session/AuthShell'

type State =
  | { kind: 'loading' }
  | { kind: 'invalid'; message: string }
  | { kind: 'ready'; email: string; company: string | null }
  | { kind: 'already_decided' }
  | { kind: 'done'; decision: 'approve' | 'reject' }

export function RegistrationDecisionScreen({ theme }: { theme: AppliedTheme }) {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [state, setState] = useState<State>(
    token ? { kind: 'loading' } : { kind: 'invalid', message: 'Este enlace no es válido.' },
  )
  const [deciding, setDeciding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    void (async () => {
      const { data, error: apiError, response } = await api.GET(
        '/api/v1/auth/registrations/decision',
        { params: { query: { token } } },
      )
      if (cancelled) return
      if (apiError || !data) {
        if (response.status === 404) {
          setState({ kind: 'invalid', message: TENANT_NOT_FOUND_MESSAGE })
        } else if (response.status === 401) {
          setState({ kind: 'invalid', message: 'Este enlace ya no es válido o ha caducado.' })
        } else {
          setState({
            kind: 'invalid',
            message: errorDetail(apiError) ?? 'El servicio no está disponible ahora mismo.',
          })
        }
        return
      }
      setState(
        data.already_decided
          ? { kind: 'already_decided' }
          : { kind: 'ready', email: data.email, company: data.company },
      )
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  const handleDecide = async (decision: 'approve' | 'reject') => {
    if (!token) return
    setError(null)
    setDeciding(true)
    const { data, error: apiError, response } = await api.POST(
      '/api/v1/auth/registrations/decision',
      { body: { token, decision } },
    )
    setDeciding(false)
    if (apiError || !data) {
      if (response.status === 401) {
        setError('Este enlace ya no es válido o ha caducado.')
      } else if (response.status === 404) {
        setError(TENANT_NOT_FOUND_MESSAGE)
      } else {
        setError('El servicio no está disponible ahora mismo. Inténtalo más tarde.')
      }
      return
    }
    setState(data.status === 'already_decided' ? { kind: 'already_decided' } : { kind: 'done', decision })
  }

  return (
    <AuthShell theme={theme}>
      <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
        <h1 className="text-xl font-semibold">Solicitud de acceso</h1>

        {state.kind === 'loading' && (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
            <Spinner label="Cargando la solicitud…" />
            Cargando la solicitud…
          </div>
        )}

        {state.kind === 'invalid' && <Banner tone="bad">{state.message}</Banner>}

        {state.kind === 'already_decided' && (
          <Banner tone="info">
            Esta solicitud ya fue decidida (por ti o por otro administrador de tu asesoría). No
            hace falta hacer nada más.
          </Banner>
        )}

        {state.kind === 'done' && (
          <Banner tone="ok">
            {state.decision === 'approve'
              ? 'Alta aprobada. La persona ya puede iniciar sesión.'
              : 'Alta rechazada.'}
          </Banner>
        )}

        {state.kind === 'ready' && (
          <>
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              <strong>{state.email}</strong> solicita acceso
              {state.company ? (
                <>
                  {' '}
                  para <strong>{state.company}</strong>
                </>
              ) : null}
              . ¿Qué quieres hacer?
            </p>

            {error && (
              <p role="alert" className="text-sm" style={{ color: 'var(--tn-error)' }}>
                {error}
              </p>
            )}

            <div className="flex gap-2">
              <Button
                variant="primary"
                className="flex-1"
                loading={deciding}
                onClick={() => void handleDecide('approve')}
              >
                Aprobar
              </Button>
              <Button
                variant="danger"
                className="flex-1"
                loading={deciding}
                onClick={() => void handleDecide('reject')}
              >
                Rechazar
              </Button>
            </div>
          </>
        )}

        <Link to="/empresas" className="tn-auth-link text-sm block text-center">
          Ir al panel
        </Link>
      </div>
    </AuthShell>
  )
}
