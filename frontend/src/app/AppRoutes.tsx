// Rutas del app-shell (S4.9). Monta las 5 pantallas ya construidas sin tocar su lógica interna
// (solo cablea props/navegación, spec §4 invariante). El control de acceso real vive en el
// backend; aquí solo se evita mostrar enlaces/pantallas que el backend rechazaría de todos modos.
import {
  Link,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'

import { CaptureScreen } from '../features/capture/CaptureScreen'
import type { Direction } from '../features/capture/types'
import { CompaniesPanel } from '../features/companies/CompaniesPanel'
import { ConfirmationScreen } from '../features/confirmation/ConfirmationScreen'
import { InvoiceHistory } from '../features/history/InvoiceHistory'
import { InvoiceInbox } from '../features/inbox/InvoiceInbox'
import { PendingSupervisionPanel } from '../features/supervision/PendingSupervisionPanel'
import { SupervisionReviewScreen } from '../features/supervision/SupervisionReviewScreen'
import { InvoicesPanel } from '../features/panel/InvoicesPanel'
import { BenchmarkRanking } from '../features/platform/BenchmarkRanking'
import { PlatformLab } from '../features/platform/PlatformLab'
import { GlobalPendingPanel } from '../features/platform/GlobalPendingPanel'
import { PlatformSettings } from '../features/platform/PlatformSettings'
import { PlatformTenants } from '../features/platform/PlatformTenants'
import { LoginScreen } from '../features/session/LoginScreen'
import { useSession } from '../features/session/SessionProvider'
import type { AppliedTheme } from '../features/tenancy/theme'
import { Menu } from './Menu'
import { homeRouteForRole, rolesAllowedFor, ROUTES } from './routes'
import { navigateAfterConfirm } from '../features/confirmation/postConfirmNavigation'

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
  const [accepted, setAccepted] = useState<{ fileId: string; direction: Direction; lowSharpness: boolean } | null>(null)
  if (accepted) {
    return (
      <section className="mx-auto flex max-w-xl flex-col gap-4 p-6 pt-20 text-slate-100" aria-label="Factura aceptada">
        <h1 className="text-2xl font-semibold">Factura aceptada</h1>
        <p className="text-slate-300">La estamos procesando. Puedes continuar trabajando y revisarla cuando esté lista.</p>
        <div className="flex flex-wrap gap-3">
          <Link to={ROUTES.confirmation(accepted.fileId)} state={{ direction: accepted.direction, lowSharpness: accepted.lowSharpness }} className="rounded-md bg-emerald-600 px-4 py-3 font-medium text-white">
            Revisar cuando esté lista
          </Link>
          <Link to={ROUTES.inbox} className="rounded-md border border-slate-600 px-4 py-3 font-medium text-slate-100">
            Ir a Mis facturas
          </Link>
        </div>
      </section>
    )
  }
  return (
    <CaptureScreen
      onUploaded={(fileId, direction, lowSharpness) =>
        setAccepted({ fileId, direction, lowSharpness })
      }
    />
  )
}

function ConfirmationRoute() {
  const { fileId } = useParams<{ fileId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const location = useLocation()
  if (!fileId) return <Navigate to={ROUTES.history} replace />
  const direction = (location.state as { direction?: Direction } | null)?.direction
  return (
    <ConfirmationScreen
      fileId={fileId}
      direction={direction}
      onConfirmed={() => void navigateAfterConfirm(queryClient, navigate)}
      onRetry={() => navigate(ROUTES.history)}
    />
  )
}

function SupervisionReviewRoute() {
  const { fileId } = useParams<{ fileId: string }>()
  if (!fileId) return <Navigate to={ROUTES.supervision} replace />
  return <SupervisionReviewScreen fileId={fileId} />
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
              <BenchmarkRanking />
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
          path={ROUTES.platformPending}
          element={
            <ProtectedRoute path={ROUTES.platformPending}>
              <GlobalPendingPanel />
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
          path={ROUTES.supervision}
          element={
            <ProtectedRoute path={ROUTES.supervision}>
              <PendingSupervisionPanel />
            </ProtectedRoute>
          }
        />
        <Route
          path={ROUTES.supervisionReviewPattern}
          element={
            <ProtectedRoute path={ROUTES.supervisionReviewPattern}>
              <SupervisionReviewRoute />
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
          path={ROUTES.inbox}
          element={
            <ProtectedRoute path={ROUTES.inbox}>
              <InvoiceInbox />
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
