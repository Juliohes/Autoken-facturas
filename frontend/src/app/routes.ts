// Fuente única de rutas y visibilidad por rol (S4.9 decisión 5). `AppRoutes.tsx` (protección por
// rol) y `Menu.tsx` (enlaces visibles) derivan ambos de `ROUTE_DEFS`, para no duplicar la tabla
// rol->ruta en dos sitios (hallazgo de auditoría: antes `AppRoutes.tsx` repetía a mano los mismos
// roles que ya vivían en el menú, sin nada que avisara si un día divergían). Visibilidad adicional
// dentro de un rol ya permitido (p. ej. el flag `is_admin_tech`, S4.10) también se declara aquí, vía
// `visible`, en vez de que `Menu.tsx` la resuelva por su cuenta (hallazgo de auditoría S4.10: un
// `if` suelto en `Menu.tsx` habría reabierto la duplicación que esta misma tarea cerró).
//
// `Role` se importa de `features/session/SessionProvider` (no se redeclara aquí): la dirección de
// dependencia correcta es `app/` -> `features/session/` (identidad es de más bajo nivel que
// routing), nunca al revés (hallazgo de auditoría de arquitectura).
import type { Role } from '../features/session/SessionProvider'

export const ROUTES = {
  login: '/login',
  platform: '/plataforma',
  platformSettings: '/plataforma/ajustes',
  platformOcrRanking: '/plataforma/ranking-ocr',
  platformLab: '/plataforma/laboratorio',
  platformPending: '/plataforma/pendientes',
  invoices: '/facturas',
  companies: '/empresas',
  history: '/historial',
  inbox: '/mis-facturas',
  supervision: '/pendientes-equipo',
  supervisionReviewPattern: '/pendientes-equipo/:fileId',
  supervisionReview: (fileId: string) => `/pendientes-equipo/${fileId}`,
  capture: '/capturar',
  upload: '/subir-archivo',
  confirmationPattern: '/confirmar/:fileId',
  confirmation: (fileId: string) => `/confirmar/${fileId}`,
} as const

export type { Role }

export interface MenuLink {
  to: string
  label: string
}

/** Contexto de visibilidad más allá del rol, para el predicado `visible` de un `RouteDef`. */
export interface MenuVisibilityContext {
  isAdminTech: boolean
}

interface RouteDef {
  path: string
  roles: Role[]
  /** Presente => aparece en el menú con este texto; ausente => ruta protegida pero no navegable desde el menú. */
  label?: string
  /**
   * Visibilidad adicional dentro de un rol ya permitido (p. ej. el flag `is_admin_tech`). Ausente
   * => visible siempre que el rol coincida. Solo afecta al MENÚ, nunca a la protección de la ruta
   * (`rolesAllowedFor`): la ruta sigue accesible por rol como cualquier otra; la pantalla en sí
   * decide si muestra su contenido o un "sin acceso" (S4.10 decisión 6).
   */
  visible?: (ctx: MenuVisibilityContext) => boolean
}

const ROUTE_DEFS: RouteDef[] = [
  { path: ROUTES.platform, roles: ['platform_admin'], label: 'Plataforma' },
  {
    path: ROUTES.platformSettings,
    roles: ['platform_admin'],
    label: 'Ajustes',
    visible: (ctx) => ctx.isAdminTech,
  },
  {
    path: ROUTES.platformOcrRanking,
    roles: ['platform_admin'],
    label: 'Ranking OCR',
    visible: (ctx) => ctx.isAdminTech,
  },
  {
    path: ROUTES.platformLab,
    roles: ['platform_admin'],
    label: 'Laboratorio',
    visible: (ctx) => ctx.isAdminTech,
  },
  {
    path: ROUTES.platformPending,
    roles: ['platform_admin'],
    label: 'Pendientes globales',
    visible: (ctx) => ctx.isAdminTech,
  },
  { path: ROUTES.invoices, roles: ['tenant_admin'], label: 'Facturas' },
  { path: ROUTES.companies, roles: ['tenant_admin'], label: 'Empresas' },
  // Sin `label` (2026-08-01, a petición de Julio): ya no es una entrada propia del menú, sigue
  // siendo una ruta protegida igual, pero se llega a ella desde el enlace "Ver historial" dentro
  // de `CaptureScreen` ("Subir factura"), no desde el menú principal.
  { path: ROUTES.history, roles: ['user'], label: 'Historial' },
  { path: ROUTES.inbox, roles: ['tenant_admin', 'user'], label: 'Mis facturas' },
  { path: ROUTES.supervision, roles: ['tenant_admin'], label: 'Pendientes del equipo' },
  { path: ROUTES.capture, roles: ['tenant_admin', 'user'], label: 'Subir factura' },
  { path: ROUTES.upload, roles: ['user'], label: 'Subir Archivo' },
  { path: ROUTES.confirmationPattern, roles: ['tenant_admin', 'user'] },
  { path: ROUTES.supervisionReviewPattern, roles: ['tenant_admin'] },
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

export function menuLinksForRole(role: Role, ctx: MenuVisibilityContext): MenuLink[] {
  return ROUTE_DEFS.filter(
    (def) => def.label && def.roles.includes(role) && (def.visible?.(ctx) ?? true),
  ).map((def) => ({
    to: def.path,
    label: def.path === ROUTES.capture && role === 'user'
      ? 'Escáner'
      : def.path === ROUTES.inbox && role === 'user'
        ? 'Pendientes'
        : def.label as string,
  }))
}

export function rolesAllowedFor(path: string): Role[] {
  return ROUTE_DEFS.find((def) => def.path === path)?.roles ?? []
}
