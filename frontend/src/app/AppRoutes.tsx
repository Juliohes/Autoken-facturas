// Rutas del app-shell (S4.9). Monta las 5 pantallas ya construidas sin tocar su lógica interna
// (solo cablea props/navegación, spec §4 invariante). El control de acceso real vive en el
// backend; aquí solo se evita mostrar enlaces/pantallas que el backend rechazaría de todos modos.
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom'
import type { ReactNode } from 'react'

import { CaptureScreen } from '../features/capture/CaptureScreen'
import type { Direction } from '../features/capture/types'
import { CompaniesPanel } from '../features/companies/CompaniesPanel'
import { ConfirmationScreen } from '../features/confirmation/ConfirmationScreen'
import { InvoiceHistory } from '../features/history/InvoiceHistory'
import { InvoicesPanel } from '../features/panel/InvoicesPanel'
import { OcrRanking } from '../features/platform/OcrRanking'
import { PlatformLab } from '../features/platform/PlatformLab'
import { PlatformSettings } from '../features/platform/PlatformSettings'
import { PlatformTenants } from '../features/platform/PlatformTenants'
import { LoginScreen } from '../features/session/LoginScreen'
import { useSession } from '../features/session/SessionProvider'
import type { AppliedTheme } from '../features/tenancy/theme'
import { Menu } from './Menu'
import { homeRouteForRole, rolesAllowedFor, ROUTES } from './routes'

function ProtectedRoute({ children, path }: { children: ReactNode; path: string }) {
  const { status, user } = useSession()
  const location = useLocation()

  if (status === 'loading') return null
  if (status === 'unauthenticated' || !user) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`)
    return <Navigate to={`${ROUTES.login}?next=${next}`} replace />
  }
  if (!rolesAllowedFor(path).includes(user.role)) {
    return <Navigate to={homeRouteForRole(user.role)} replace />
  }
  return <>{children}</>
}

// A diferencia de `ProtectedRoute`, aquí "ya hay sesión" redirige LEJOS del login (evita que un
// usuario ya logueado vuelva a ver el formulario si navega a /login a mano). La guarda de
// `status === 'loading'` es la misma que `ProtectedRoute`/`RootRoute` (hallazgo de auditoría: sin
// ella, visitar /login directamente mostraba el formulario un instante antes de que terminara el
// refresh silencioso, violando C5 "antes de mostrar login").
function LoginRoute({ theme }: { theme: AppliedTheme }) {
  const { status, user } = useSession()
  const [searchParams] = useSearchParams()

  if (status === 'loading') return null
  if (status === 'authenticated' && user) {
    const next = searchParams.get('next')
    return <Navigate to={next || homeRouteForRole(user.role)} replace />
  }
  return <LoginScreen theme={theme} />
}

function RootRoute() {
  const { status, user } = useSession()
  if (status === 'loading') return null
  if (status === 'authenticated' && user) {
    return <Navigate to={homeRouteForRole(user.role)} replace />
  }
  return <Navigate to={ROUTES.login} replace />
}

function CompaniesRoute() {
  const navigate = useNavigate()
  return (
    <CompaniesPanel
      onViewInvoices={(companyId) => navigate(`${ROUTES.invoices}?empresa=${companyId}`)}
    />
  )
}

function InvoicesRoute() {
  const [searchParams] = useSearchParams()
  const companyId = searchParams.get('empresa')
  return <InvoicesPanel initialFilters={companyId ? { company_id: companyId } : undefined} />
}

function CaptureRoute() {
  const navigate = useNavigate()
  return (
    <CaptureScreen
      onUploaded={(fileId, direction) =>
        navigate(ROUTES.confirmation(fileId), { state: { direction } })
      }
    />
  )
}

function ConfirmationRoute() {
  const { fileId } = useParams<{ fileId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  if (!fileId) return <Navigate to={ROUTES.history} replace />
  const direction = (location.state as { direction?: Direction } | null)?.direction
  return (
    <ConfirmationScreen
      fileId={fileId}
      direction={direction}
      onConfirmed={() => navigate(ROUTES.history)}
      onRetry={() => navigate(ROUTES.history)}
    />
  )
}

export function AppRoutes({ theme }: { theme: AppliedTheme }) {
  const { status, user } = useSession()

  return (
    // `min-h-screen bg-slate-900 text-slate-100`: cada pantalla ya autenticada (Plataforma,
    // facturas, historial...) da por hecho un fondo oscuro (usa `text-slate-300`/`text-slate-400`
    // etc, pensados para leerse sobre oscuro) pero nadie lo había puesto en un contenedor común —
    // sin esto, el fondo por defecto es blanco y ese texto queda casi invisible (hallazgo real,
    // reportado por Julio al entrar de verdad). El login ya tenía su propio fondo aparte
    // (`LoginScreen`); este envoltorio cubre el resto del árbol autenticado.
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {status === 'authenticated' && user && (
        <Menu role={user.role} isAdminTech={user.is_admin_tech} theme={theme} />
      )}
      <Routes>
        <Route path="/" element={<RootRoute />} />
        <Route path={ROUTES.login} element={<LoginRoute theme={theme} />} />
        <Route
          path={ROUTES.platform}
          element={
            <ProtectedRoute path={ROUTES.platform}>
              <PlatformTenants />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.platformSettings}
          element={
            <ProtectedRoute path={ROUTES.platformSettings}>
              <PlatformSettings />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.platformOcrRanking}
          element={
            <ProtectedRoute path={ROUTES.platformOcrRanking}>
              <OcrRanking />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.platformLab}
          element={
            <ProtectedRoute path={ROUTES.platformLab}>
              <PlatformLab />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.invoices}
          element={
            <ProtectedRoute path={ROUTES.invoices}>
              <InvoicesRoute />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.companies}
          element={
            <ProtectedRoute path={ROUTES.companies}>
              <CompaniesRoute />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.history}
          element={
            <ProtectedRoute path={ROUTES.history}>
              <InvoiceHistory />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.capture}
          element={
            <ProtectedRoute path={ROUTES.capture}>
              <CaptureRoute />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.confirmationPattern}
          element={
            <ProtectedRoute path={ROUTES.confirmationPattern}>
              <ConfirmationRoute />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}
