// Tema del tenant: mapeo puro branding->tema (con los valores por defecto de "Setex tal cual hoy",
// spec S4.2 decisión 2) y su aplicación al DOM, separados para que el mapeo se pueda probar sin
// tocar `document`.
import type { CurrentTenant } from './types'

export const DEFAULT_APP_NAME = 'Autoken Facturas'
// Verde ya usado hoy en los botones principales (`bg-emerald-600`).
export const DEFAULT_COLOR_PRIMARY = '#059669'
// Fondo ya usado hoy (`bg-slate-900`), mismo valor que `theme_color`/`background_color` del manifest.
export const DEFAULT_COLOR_SECONDARY = '#0f172a'

export interface AppliedTheme {
  appName: string
  colorPrimary: string
  colorSecondary: string
  logoUrl: string | null
  // Sin default (S4.3 decisión 4): hoy no hay favicon propio, "Setex tal cual hoy" es no tener
  // ninguno, no inventar uno por defecto.
  faviconUrl: string | null
}

/** Branding del tenant (o su ausencia) -> tema a aplicar. Cada campo cae a su propio default. */
export function resolveTheme(tenant: CurrentTenant | undefined): AppliedTheme {
  return {
    appName: tenant?.app_name ?? DEFAULT_APP_NAME,
    colorPrimary: tenant?.color_primary ?? DEFAULT_COLOR_PRIMARY,
    colorSecondary: tenant?.color_secondary ?? DEFAULT_COLOR_SECONDARY,
    logoUrl: tenant?.logo_url ?? null,
    faviconUrl: tenant?.favicon ?? null,
  }
}

const FAVICON_LINK_ID = 'tenant-favicon'

/** Aplica el tema al DOM: título de la pestaña, variables CSS en `:root` y favicon (S4.3). */
export function applyTenantTheme(theme: AppliedTheme): void {
  document.title = theme.appName
  document.documentElement.style.setProperty('--color-primary', theme.colorPrimary)
  document.documentElement.style.setProperty('--color-secondary', theme.colorSecondary)
  applyFavicon(theme.faviconUrl)
}

/** Inyecta/actualiza el `<link rel="icon">` si hay favicon; lo retira si no (sin hueco vacío). */
function applyFavicon(faviconUrl: string | null): void {
  const existing = document.getElementById(FAVICON_LINK_ID) as HTMLLinkElement | null
  if (faviconUrl === null) {
    existing?.remove()
    return
  }
  const link = existing ?? document.createElement('link')
  link.id = FAVICON_LINK_ID
  link.rel = 'icon'
  // El favicon lo aloja el propio tenant (URL de terceros potencialmente): evita filtrar el
  // Referer (con el subdominio del tenant) a ese host, mismo motivo que el <img> del logo (S4.2).
  link.referrerPolicy = 'no-referrer'
  link.href = faviconUrl
  if (!existing) document.head.appendChild(link)
}
