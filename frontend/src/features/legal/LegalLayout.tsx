// Envoltorio común de las páginas legales (/terminos, /privacidad): cabecera con la marca del
// tenant (igual que AuthShell, pero en formato documento largo, no tarjeta de formulario) y enlaces
// de vuelta a los dos sitios desde los que realmente se llega aquí.
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Banner } from '../../ui'
import type { AppliedTheme } from '../tenancy/theme'

/** Encabezado de sección dentro de un documento legal (mismo tamaño en /terminos y /privacidad). */
export function LegalHeading({ children }: { children: ReactNode }) {
  return <h2 className="text-base font-semibold">{children}</h2>
}

/** Aviso, igual en ambos documentos, de que el texto es un borrador pendiente de revisión legal y
 * de que Julio tiene que rellenar los datos identificativos reales (ver companyInfo.ts). */
export function LegalDraftNotice() {
  return (
    <Banner tone="warn">
      <strong>Nota para Julio:</strong> este texto se ha redactado con ayuda de un asistente de IA a
      partir de la normativa española vigente (LSSI-CE, RGPD, LOPDGDD, Código de Comercio), pero NO
      sustituye la revisión de un abogado especializado en protección de datos y comercio
      electrónico. Los datos entre corchetes (razón social, NIF, domicilio, registro mercantil) son
      marcadores de posición: hay que rellenarlos con los datos reales antes de considerar este
      documento definitivo.
    </Banner>
  )
}

export function LegalLayout({
  theme,
  title,
  lastUpdated,
  children,
}: {
  theme: AppliedTheme
  title: string
  lastUpdated: string
  children: ReactNode
}) {
  return (
    <main className="tn-login-shell min-h-screen">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <header className="mb-8 flex items-center gap-3">
          {theme.logoUrl && (
            <img
              src={theme.logoUrl}
              alt={theme.appName}
              referrerPolicy="no-referrer"
              className="h-10 w-auto"
            />
          )}
          <span className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
            {theme.appName}
          </span>
        </header>

        <article className="tn-login-card rounded-xl p-6 sm:p-10">
          <h1 className="text-2xl font-semibold">{title}</h1>
          <p className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>
            Última actualización: {lastUpdated}
          </p>

          <div
            className="tn-legal-doc mt-8 space-y-6 text-sm leading-relaxed"
            style={{ color: 'var(--text-primary)' }}
          >
            {children}
          </div>
        </article>

        <div className="mt-6 flex flex-col items-center gap-1 text-sm sm:flex-row sm:justify-center sm:gap-4">
          <Link to="/registro" className="tn-auth-link">
            Volver al registro
          </Link>
          <Link to="/login" className="tn-auth-link">
            Volver a iniciar sesión
          </Link>
        </div>
      </div>
    </main>
  )
}
