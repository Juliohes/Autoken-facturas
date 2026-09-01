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
import { useInvoiceInbox } from '../features/inbox/useInvoiceInbox'
import { Modal } from '../shared/Modal'

interface Props {
  role: Role
  isAdminTech: boolean
  theme: AppliedTheme
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'font-semibold text-cyan-300' : 'text-slate-200 hover:text-white'

export function Menu({ role, isAdminTech, theme }: Props) {
  const { logout } = useSession()
  const [logoutOpen, setLogoutOpen] = useState(false)
  const { data } = useInvoiceInbox(null, role === 'user')
  const [mobileOpen, setMobileOpen] = useState(false)
  const links: MenuLink[] = menuLinksForRole(role, { isAdminTech })

  if (role === 'user') {
    const actionable = (data?.summary?.ready ?? 0) + (data?.summary?.attention ?? 0)
    const order = ['/capturar', '/subir-archivo', '/mis-facturas', '/historial']
    const userLinks = [...links].sort((left, right) => order.indexOf(left.to) - order.indexOf(right.to))
    return (
      <>
        <nav aria-label="Navegación principal" className="tn-user-nav">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            {theme.logoUrl && <img src={theme.logoUrl} alt={theme.appName} className="tn-brand-logo max-h-10" />}
            <button type="button" aria-label="Cerrar sesión" onClick={() => setLogoutOpen(true)} className="min-h-11 min-w-11 rounded border border-slate-300 px-3 text-xl">×</button>
          </div>
          <div className="tn-user-nav-links">
            {userLinks.map((link) => (
              <NavLink key={link.to} to={link.to} className={linkClass}>
                <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="8" /></svg>
                <span>{link.label}</span>
                {link.to === '/mis-facturas' && actionable > 0 && <span aria-label={`${actionable} pendientes accionables`} className="ml-1 rounded-full bg-orange-600 px-1.5 text-xs text-white">{actionable > 9 ? '9+' : actionable}</span>}
              </NavLink>
            ))}
          </div>
        </nav>
        {logoutOpen && <Modal title="Cerrar sesión" onClose={() => setLogoutOpen(false)} panelClassName="max-w-md space-y-4"><p>¿Quieres cerrar sesión?</p><div className="flex justify-end gap-2"><button type="button" onClick={() => setLogoutOpen(false)} className="rounded border px-4 py-2">Cancelar</button><button type="button" onClick={() => void logout()} className="rounded bg-orange-600 px-4 py-2 font-semibold text-white">Cerrar sesión</button></div></Modal>}
      </>
    )
  }

  return (
    <nav className="tn-top-nav tn-liquid-glass text-white">
      <div className="flex flex-wrap items-center justify-between gap-y-2 px-4 py-3 sm:px-6">
        {theme.logoUrl && (
          // Más grande (2026-08-02, a petición de Julio): `max-h-8` (32px) quedaba minúsculo junto
          // al resto de la cabecera.
          <img
            src={theme.logoUrl}
            alt={theme.appName}
            referrerPolicy="no-referrer"
            className="tn-brand-logo max-h-14"
          />
        )}
        <button
          type="button"
          onClick={() => setMobileOpen((open) => !open)}
          aria-expanded={mobileOpen}
          aria-label={mobileOpen ? 'Cerrar menú' : 'Abrir menú'}
          className="rounded-md border border-cyan-200/50 p-2 text-white md:hidden"
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
             ' w-full flex-col gap-3 border-t border-cyan-100/20 pt-3 md:flex md:w-auto md:flex-row md:items-center md:gap-6 md:border-t-0 md:pt-0'
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
              className="text-sm text-slate-200 hover:text-white"
            >
              Cerrar sesión
            </button>
          </li>
        </ul>
      </div>
    </nav>
  )
}
