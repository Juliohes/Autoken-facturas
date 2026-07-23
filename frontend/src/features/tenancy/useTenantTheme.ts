// Hook que aplica el tema del tenant actual al DOM (S4.2). Un fallo al cargar el tenant (404 en
// hosts sin tenant, red caída...) no bloquea nada: `resolveTheme` cae a los valores por defecto,
// mismo criterio que si no hubiera branding (spec §0 decisión 6, cosmético y no bloqueante).
import { useEffect } from 'react'

import { applyTenantTheme, resolveTheme, type AppliedTheme } from './theme'
import { useCurrentTenant } from './useCurrentTenant'

export function useTenantTheme(): AppliedTheme {
  const currentTenant = useCurrentTenant()
  const theme = resolveTheme(currentTenant.data)

  // `theme` es un objeto nuevo cada render (`resolveTheme` no memoiza); las claves listadas abajo
  // son su contenido real. Listar el objeto entero dispararía el efecto en cada render sin motivo.
  useEffect(() => {
    applyTenantTheme(theme)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme.appName, theme.colorPrimary, theme.colorSecondary, theme.faviconUrl])

  return theme
}
