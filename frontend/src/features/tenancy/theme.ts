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
}

/** Branding del tenant (o su ausencia) -> tema a aplicar. Cada campo cae a su propio default. */
export function resolveTheme(tenant: CurrentTenant | undefined): AppliedTheme {
  return {
    appName: tenant?.app_name ?? DEFAULT_APP_NAME,
    colorPrimary: tenant?.color_primary ?? DEFAULT_COLOR_PRIMARY,
    colorSecondary: tenant?.color_secondary ?? DEFAULT_COLOR_SECONDARY,
    logoUrl: tenant?.logo_url ?? null,
  }
}

/** Aplica el tema al DOM: título de la pestaña + variables CSS en `:root` (efecto secundario). */
export function applyTenantTheme(theme: AppliedTheme): void {
  document.title = theme.appName
  document.documentElement.style.setProperty('--color-primary', theme.colorPrimary)
  document.documentElement.style.setProperty('--color-secondary', theme.colorSecondary)
}
