// Menú superior (S4.9, C9-C11; S4.10 C8, enlace de Ajustes condicional al flag admin-tech): enlaces
// según el rol de la sesión activa, más "Cerrar sesión" siempre visible. Ocultar un enlace aquí es
// solo UX; el backend ya rechaza (401/403) cualquier intento de saltárselo por URL directa (spec §4).
//
// Responsive (hallazgo real de Julio entrando desde el móvil): por debajo de `md` los enlaces viven
// en un desplegable controlado por el botón de hamburguesa, en vez de la fila horizontal fija de
// antes — que en una pantalla estrecha desbordaba el ancho y dejaba "Historial"/"Subir factura"
// inalcanzables (sin scroll horizontal ni forma de llegar a ellos). Un único `<ul>` (nunca dos
// listas duplicadas): en `md` y superior, `md:flex` lo muestra siempre en fila sin importar el
// estado del desplegable; por debajo, la clase `hidden`/`flex` según `mobileOpen` decide si se ve.
import { useState } from 'react'
import { NavLink } from 'react-router-dom'

import { useSession } from '../features/session/SessionProvider'
import type { AppliedTheme } from '../features/tenancy/theme'
import { menuLinksForRole, type MenuLink, type Role } from './routes'

interface Props {
  role: Role
  isAdminTech: boolean
  theme: AppliedTheme
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'font-semibold text-emerald-400' : 'text-slate-300 hover:text-slate-100'

export function Menu({ role, isAdminTech, theme }: Props) {
  const { logout } = useSession()
  const [mobileOpen, setMobileOpen] = useState(false)
  const links: MenuLink[] = menuLinksForRole(role, { isAdminTech })

  return (
    <nav className="border-b border-slate-700 bg-slate-800 text-slate-100">
      <div className="flex flex-wrap items-center justify-between gap-y-2 px-4 py-3 sm:px-6">
        {theme.logoUrl && (
          // Más grande (2026-08-02, a petición de Julio): `max-h-8` (32px) quedaba minúsculo junto
          // al resto de la cabecera.
          <img
            src={theme.logoUrl}
            alt={theme.appName}
            referrerPolicy="no-referrer"
            className="max-h-14"
          />
        )}
        <button
          type="button"
          onClick={() => setMobileOpen((open) => !open)}
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? 'Cerrar menú' : 'Abrir menú'}
          className="rounded-md border border-slate-600 p-2 text-slate-100 md:hidden"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2}>
            {mobileOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
        {/* Un único <ul>: a partir de `md`, `md:flex md:w-auto` lo coloca en la misma fila que el
            logo (el `justify-between` del contenedor lo empuja a la derecha, igual que antes). Por
            debajo de `md`, `w-full` fuerza que ocupe su propia línea (el contenedor tiene
            `flex-wrap`) y `hidden`/`flex` según `mobileOpen` decide si esa línea se ve. */}
        <ul
          className={
            (mobileOpen ? 'flex' : 'hidden') +
            ' w-full flex-col gap-3 border-t border-slate-700 pt-3 md:flex md:w-auto md:flex-row md:items-center md:gap-6 md:border-t-0 md:pt-0'
          }
        >
          {links.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} className={linkClass} onClick={() => setMobileOpen(false)}>
                {link.label}
              </NavLink>
            </li>
          ))}
          <li>
            <button
              type="button"
              onClick={() => void logout()}
              className="text-sm text-slate-300 hover:text-slate-100"
            >
              Cerrar sesión
            </button>
          </li>
        </ul>
      </div>
    </nav>
  )
}
