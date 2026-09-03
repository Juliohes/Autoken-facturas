// Confirmación del email del registrante (Bloque 4 de PROMPT-AUTOFACTU-AUTH-COMPLETO, backend en
// identity/email_verification.py). NO aprueba el alta -- eso lo sigue haciendo el `tenant_admin` en
// "Pendientes de aprobación"; esta pantalla solo confirma que el email es del registrante.
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../../api/client'
import { Banner, Spinner } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'
import { TENANT_NOT_FOUND_MESSAGE } from './authErrors'
import { AuthShell } from '../session/AuthShell'

type Result = 'pending' | 'ok' | 'invalid' | 'unavailable' | 'tenant_not_found'

export function VerifyEmailScreen({ theme }: { theme: AppliedTheme }) {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [result, setResult] = useState<Result>(token ? 'pending' : 'invalid')

  useEffect(() => {
    if (!token) return
    let cancelled = false
    void (async () => {
      const { error, response } = await api.POST('/api/v1/auth/register/verify-email', {
        body: { token },
      })
      if (cancelled) return
      if (!error) {
        setResult('ok')
        return
      }
      if (response.status === 401) setResult('invalid')
      else if (response.status === 404) setResult('tenant_not_found')
      else setResult('unavailable')
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <AuthShell theme={theme}>
      <div className="tn-login-card tn-auth-form-card w-full max-w-sm space-y-4 rounded-xl p-8">
        <h1 className="text-xl font-semibold">Confirmar email</h1>

        {result === 'pending' && (
          <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
            <Spinner label="Confirmando tu email…" />
            Confirmando tu email…
          </div>
        )}

        {result === 'ok' && (
          <Banner tone="ok">
            Tu email ha sido confirmado. Un administrador de tu asesoría revisará tu alta en breve.
          </Banner>
        )}

        {result === 'invalid' && (
          <Banner tone="bad">Este enlace de confirmación no es válido o ha caducado.</Banner>
        )}

        {result === 'unavailable' && (
          <Banner tone="warn">El servicio no está disponible ahora mismo. Inténtalo más tarde.</Banner>
        )}

        {result === 'tenant_not_found' && <Banner tone="bad">{TENANT_NOT_FOUND_MESSAGE}</Banner>}

        <Link to="/login" className="tn-auth-link text-sm">
          Volver a iniciar sesión
        </Link>
      </div>
    </AuthShell>
  )
}
