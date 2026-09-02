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
import { useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'

import { CaptureScreen } from '../features/capture/CaptureScreen'
import type { Direction } from '../features/capture/types'
import { CompaniesPanel } from '../features/companies/CompaniesPanel'
import { ConfirmationScreen } from '../features/confirmation/ConfirmationScreen'
import { PostConfirmDialog } from '../features/confirmation/PostConfirmDialog'
import { InvoiceInbox } from '../features/inbox/InvoiceInbox'
import { InvoiceHistory } from '../features/history/InvoiceHistory'
import { UploadFileScreen } from '../features/upload/UploadFileScreen'
import { PendingSupervisionPanel } from '../features/supervision/PendingSupervisionPanel'
import { SupervisionReviewScreen } from '../features/supervision/SupervisionReviewScreen'
import { InvoicesPanel } from '../features/panel/InvoicesPanel'
import { BenchmarkRanking } from '../features/platform/BenchmarkRanking'
import { PlatformLab } from '../features/platform/PlatformLab'
import { GlobalPendingPanel } from '../features/platform/GlobalPendingPanel'
import { PlatformSettings } from '../features/platform/PlatformSettings'
import { PlatformTenants } from '../features/platform/PlatformTenants'
import { ActivateScreen } from '../features/auth/ActivateScreen'
import { ForgotPasswordScreen } from '../features/auth/ForgotPasswordScreen'
import { RegisterScreen } from '../features/auth/RegisterScreen'
import { ResetPasswordScreen } from '../features/auth/ResetPasswordScreen'
import { VerifyEmailScreen } from '../features/auth/VerifyEmailScreen'
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
  return <CaptureScreen onUploaded={() => undefined} />
}

function ConfirmationRoute() {
  const { fileId } = useParams<{ fileId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const location = useLocation()
  const [nextInvoice, setNextInvoice] = useState<Awaited<ReturnType<typeof navigateAfterConfirm>>>(null)
  if (!fileId) return <Navigate to={ROUTES.history} replace />
  const direction = (location.state as { direction?: Direction } | null)?.direction
  return (
    <>
      <ConfirmationScreen
        fileId={fileId}
        direction={direction}
        onConfirmed={async () => {
          const next = await navigateAfterConfirm(queryClient)
          if (next) setNextInvoice(next)
          else navigate(ROUTES.inbox)
        }}
        onRetry={() => navigate(ROUTES.history)}
        onDeleted={() => navigate(ROUTES.inbox, { state: { message: 'La factura no se ha confirmado ni guardado.' } })}
      />
      {nextInvoice && (
        <PostConfirmDialog
          onReview={() => {
            const next = nextInvoice
            setNextInvoice(null)
            navigate(ROUTES.confirmation(next.id), { state: { direction: next.direction ?? undefined } })
          }}
          onClose={() => {
            setNextInvoice(null)
            navigate(ROUTES.inbox)
          }}
        />
      )}
    </>
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
    <div className="tn-app-shell min-h-screen">
      {status === 'authenticated' && user && (
        <Menu role={user.role} isAdminTech={user.is_admin_tech} theme={theme} />
      )}
      <Routes>
        <Route path="/" element={<RootRoute />} />
        <Route path={ROUTES.login} element={<LoginRoute theme={theme} />} />
        {/* Públicas, sin token (Bloque 4 de PROMPT-AUTOFACTU-AUTH-COMPLETO): fuera de `ProtectedRoute`,
            cada una resuelve su propio estado (token de la URL, éxito/error) sin depender de la sesión. */}
        <Route path={ROUTES.register} element={<RegisterScreen theme={theme} />} />
        <Route path={ROUTES.registerConfirm} element={<VerifyEmailScreen theme={theme} />} />
        <Route path={ROUTES.forgotPassword} element={<ForgotPasswordScreen theme={theme} />} />
        <Route path={ROUTES.resetPassword} element={<ResetPasswordScreen theme={theme} />} />
        <Route path={ROUTES.activate} element={<ActivateScreen theme={theme} />} />
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
          path={ROUTES.upload}
          element={
            <ProtectedRoute path={ROUTES.upload}>
              <UploadFileScreen />
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
