// Menú superior (S4.9, C9-C11; S4.10 C8, enlace de Ajustes condicional al flag admin-tech): enlaces
// según el rol de la sesión activa, más "Cerrar sesión" siempre visible. Ocultar un enlace aquí es
// solo UX; el backend ya rechaza (401/403) cualquier intento de saltárselo por URL directa (spec §4).
import { NavLink } from 'react-router-dom'

import { useSession } from '../features/session/SessionProvider'
import type { AppliedTheme } from '../features/tenancy/theme'
import { menuLinksForRole, type MenuLink, type Role } from './routes'

interface Props {
  role: Role
  isAdminTech: boolean
  theme: AppliedTheme
}

export function Menu({ role, isAdminTech, theme }: Props) {
  const { logout } = useSession()
  const links: MenuLink[] = menuLinksForRole(role, { isAdminTech })

  return (
    <nav className="flex items-center justify-between border-b border-slate-700 bg-slate-800 px-6 py-3 text-slate-100">
      <div className="flex items-center gap-6">
        {theme.logoUrl && (
          <img
            src={theme.logoUrl}
            alt={theme.appName}
            referrerPolicy="no-referrer"
            className="max-h-8"
          />
        )}
        <ul className="flex gap-4">
          {links.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                className={({ isActive }) =>
                  isActive ? 'font-semibold text-emerald-400' : 'text-slate-300 hover:text-slate-100'
                }
              >
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        onClick={() => void logout()}
        className="text-sm text-slate-300 hover:text-slate-100"
      >
        Cerrar sesión
      </button>
    </nav>
  )
}
