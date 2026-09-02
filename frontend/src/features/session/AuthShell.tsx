// Envoltorio visual común de las pantallas públicas de autenticación (Bloque 4 de
// PROMPT-AUTOFACTU-AUTH-COMPLETO): extraído de LoginScreen para que login, registro, recuperación,
// restablecimiento y activación compartan el mismo panel de marca en vez de repetirlo cinco veces.
import type { ReactNode } from 'react'

import type { AppliedTheme } from '../tenancy/theme'

export function AuthShell({ theme, children }: { theme: AppliedTheme; children: ReactNode }) {
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
        {children}
      </div>
    </main>
  )
}
