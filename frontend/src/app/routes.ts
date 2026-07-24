// Fuente única de rutas y visibilidad por rol (S4.9 decisión 5). `AppRoutes.tsx` (protección por
// rol) y `Menu.tsx` (enlaces visibles) derivan ambos de `ROUTE_DEFS`, para no duplicar la tabla
// rol->ruta en dos sitios (hallazgo de auditoría: antes `AppRoutes.tsx` repetía a mano los mismos
// roles que ya vivían en el menú, sin nada que avisara si un día divergían).
//
// `Role` se importa de `features/session/SessionProvider` (no se redeclara aquí): la dirección de
// dependencia correcta es `app/` -> `features/session/` (identidad es de más bajo nivel que
// routing), nunca al revés (hallazgo de auditoría de arquitectura).
import type { Role } from '../features/session/SessionProvider'

export const ROUTES = {
  login: '/login',
  platform: '/plataforma',
  invoices: '/facturas',
  companies: '/empresas',
  history: '/historial',
  capture: '/capturar',
  confirmationPattern: '/confirmar/:fileId',
  confirmation: (fileId: string) => `/confirmar/${fileId}`,
} as const

export type { Role }

export interface MenuLink {
  to: string
  label: string
}

interface RouteDef {
  path: string
  roles: Role[]
  /** Presente => aparece en el menú con este texto; ausente => ruta protegida pero no navegable desde el menú. */
  label?: string
}

const ROUTE_DEFS: RouteDef[] = [
  { path: ROUTES.platform, roles: ['platform_admin'], label: 'Plataforma' },
  { path: ROUTES.invoices, roles: ['tenant_admin'], label: 'Facturas' },
  { path: ROUTES.companies, roles: ['tenant_admin'], label: 'Empresas' },
  { path: ROUTES.history, roles: ['tenant_admin', 'user'], label: 'Historial' },
  { path: ROUTES.capture, roles: ['tenant_admin', 'user'], label: 'Subir factura' },
  { path: ROUTES.confirmationPattern, roles: ['tenant_admin', 'user'] },
]

// `user` entra directo a capturar (S2.2 decisión 1): subir facturas es su tarea principal del día a
// día, no consultar el historial. `tenant_admin` mantiene `/facturas` (su tarea es supervisar).
const ROLE_HOME: Record<Role, string> = {
  platform_admin: ROUTES.platform,
  tenant_admin: ROUTES.invoices,
  user: ROUTES.capture,
}

export function homeRouteForRole(role: Role): string {
  return ROLE_HOME[role]
}

export function menuLinksForRole(role: Role): MenuLink[] {
  return ROUTE_DEFS.filter((def) => def.label && def.roles.includes(role)).map((def) => ({
    to: def.path,
    label: def.label as string,
  }))
}

export function rolesAllowedFor(path: string): Role[] {
  return ROUTE_DEFS.find((def) => def.path === path)?.roles ?? []
}
