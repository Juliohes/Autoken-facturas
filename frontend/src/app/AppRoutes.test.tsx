// Tests de comportamiento de integración del app-shell (S4.9, C4/C9-C13). Cliente de API y
// `fetch` global mockeados; router en memoria para controlar la URL de arranque de cada escenario.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../api/client'
import * as tokenStore from '../api/tokenStore'
import { SessionProvider } from '../features/session/SessionProvider'
import type { Direction } from '../features/capture/types'
import type { AppliedTheme } from '../features/tenancy/theme'
import { AppRoutes } from './AppRoutes'

const THEME: AppliedTheme = {
  appName: 'Autoken Facturas',
  colorPrimary: '#059669',
  colorSecondary: '#0f172a',
  logoUrl: null,
  faviconUrl: null,
}

vi.mock('../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))

vi.mock('../features/capture/CaptureScreen', () => ({
  CaptureScreen: ({ onUploaded }: { onUploaded: (fileId: string, direction: Direction, lowSharpness: boolean) => void }) => (
    <CaptureScreenStub onUploaded={onUploaded} />
  ),
}))

function CaptureScreenStub({ onUploaded }: { onUploaded: (fileId: string, direction: Direction, lowSharpness: boolean) => void }) {
  const navigate = useNavigate()
  return (
    <section>
      <h1>Capturar factura</h1>
      <button type="button" role="link" onClick={() => navigate('/historial')}>Ver historial</button>
      <button type="button" onClick={() => onUploaded('file-accepted', 'recibida', false)}>Simular subida aceptada</button>
    </section>
  )
}

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock
const fetchMock = vi.fn()

const ME_BY_ROLE = {
  platform_admin: {
    id: 'p1',
    email: 'julio@autoken.es',
    role: 'platform_admin',
    tenant: null,
    company: null,
    is_admin_tech: false,
  },
  admin_tech: {
    id: 'p1',
    email: 'julio@autoken.es',
    role: 'platform_admin',
    tenant: null,
    company: null,
    is_admin_tech: true,
  },
  tenant_admin: {
    id: 't1',
    email: 'ana@ilex.es',
    role: 'tenant_admin',
    tenant: 'ilex',
    company: null,
    is_admin_tech: false,
  },
  user: {
    id: 'u1',
    email: 'raul@ilex.es',
    role: 'user',
    tenant: 'ilex',
    company: { id: 'c1', name: 'Cliente SL' },
    is_admin_tech: false,
  },
}

const COMPANIES = [
  { id: 'c1', name: 'Cliente SL', cif: 'B12345678', status: 'active', notes: null, created_at: '2026-07-01T00:00:00Z' },
]

function mockAuthenticatedAs(role: keyof typeof ME_BY_ROLE) {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer' }), { status: 200 }),
  )
  getMock.mockImplementation((path: string) => {
    if (path.includes('/auth/me')) return Promise.resolve({ data: ME_BY_ROLE[role], error: undefined })
    if (path.includes('/platform/tenants/metrics')) return Promise.resolve({ data: [], error: undefined })
    if (path.includes('/platform/tenants')) return Promise.resolve({ data: [], error: undefined })
    if (path.includes('/platform/settings')) {
      return Promise.resolve({ data: { ocr_experiment_enabled: false }, error: undefined })
    }
    if (path.includes('/platform/ocr-ranking')) {
      return Promise.resolve({ data: [], error: undefined })
    }
    if (path.includes('/reporting/invoices')) {
      return Promise.resolve({ data: { items: [], next_cursor: null }, error: undefined })
    }
    if (path.includes('/reporting/companies')) return Promise.resolve({ data: COMPANIES, error: undefined })
    if (path === '/api/v1/companies') return Promise.resolve({ data: COMPANIES, error: undefined })
    if (path.includes('/registrations')) return Promise.resolve({ data: [], error: undefined })
    if (path.includes('/invoices/inbox')) return Promise.resolve({ data: { items: [], next_cursor: null, summary: { processing: 0, ready: 0, attention: 0 } }, error: undefined })
    if (path.includes('/invoices/history')) return Promise.resolve({ data: { entries: [] }, error: undefined })
    throw new Error(`ruta GET no mockeada: ${path}`)
  })
}

function mockUnauthenticated() {
  fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))
  getMock.mockImplementation((path: string) => {
    throw new Error(`ruta GET no mockeada (sin sesión): ${path}`)
  })
}

function renderApp(initialPath: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <SessionProvider>
          <AppRoutes theme={THEME} />
        </SessionProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  tokenStore.setToken(null)
  tokenStore.setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AppRoutes (S4.9)', () => {
  it('C4: sin sesión, una ruta protegida redirige a login conservando el destino', async () => {
    mockUnauthenticated()
    renderApp('/facturas')

    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())
  })

  it('C9: platform_admin solo ve "Plataforma" en el menú', async () => {
    mockAuthenticatedAs('platform_admin')
    renderApp('/plataforma')

    expect(await screen.findByRole('heading', { name: 'Plataforma — Asesorías' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation')
    expect(within(nav).getByText('Plataforma')).toBeInTheDocument()
    expect(within(nav).queryByText('Facturas')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Empresas')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Historial')).not.toBeInTheDocument()
  })

  it('S4.10 C8: un platform_admin normal (sin flag) no ve "Ajustes" en el menú', async () => {
    mockAuthenticatedAs('platform_admin')
    renderApp('/plataforma')

    await screen.findByRole('heading', { name: 'Plataforma — Asesorías' })
    expect(within(screen.getByRole('navigation')).queryByText('Ajustes')).not.toBeInTheDocument()
  })

  it('S4.10 C8: admin-tech sí ve "Ajustes" en el menú y puede entrar', async () => {
    mockAuthenticatedAs('admin_tech')
    renderApp('/plataforma')
    const user = userEvent.setup()

    await screen.findByRole('heading', { name: 'Plataforma — Asesorías' })
    const ajustesLink = within(screen.getByRole('navigation')).getByText('Ajustes')
    await user.click(ajustesLink)

    expect(await screen.findByRole('heading', { name: 'Ajustes de plataforma' })).toBeInTheDocument()
  })

  it('S4.8 C10: un platform_admin normal (sin flag) no ve "Ranking OCR" en el menú', async () => {
    mockAuthenticatedAs('platform_admin')
    renderApp('/plataforma')

    await screen.findByRole('heading', { name: 'Plataforma — Asesorías' })
    expect(within(screen.getByRole('navigation')).queryByText('Ranking OCR')).not.toBeInTheDocument()
  })

  it('S4.8 C10: admin-tech sí ve "Ranking OCR" en el menú y puede entrar', async () => {
    mockAuthenticatedAs('admin_tech')
    renderApp('/plataforma')
    const user = userEvent.setup()

    await screen.findByRole('heading', { name: 'Plataforma — Asesorías' })
    const rankingLink = within(screen.getByRole('navigation')).getByText('Ranking OCR')
    await user.click(rankingLink)

    expect(await screen.findByRole('heading', { name: 'Ranking OCR multi-modelo' })).toBeInTheDocument()
  })

  it('C10: tenant_admin ve Facturas/Empresas/Subir factura, no Plataforma ni Historial (ya no es entrada de menú)', async () => {
    mockAuthenticatedAs('tenant_admin')
    renderApp('/facturas')

    expect(await screen.findByRole('heading', { name: 'Panel de facturas' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation')
    expect(within(nav).getByText('Facturas')).toBeInTheDocument()
    expect(within(nav).getByText('Empresas')).toBeInTheDocument()
    expect(within(nav).getByText('Subir factura')).toBeInTheDocument()
    expect(within(nav).queryByText('Historial')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Plataforma')).not.toBeInTheDocument()
  })

  it('R-056 C1: user ve exactamente los cuatro destinos del flujo', async () => {
    mockAuthenticatedAs('user')
    renderApp('/historial')

    await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument())
    const nav = screen.getByRole('navigation')
    expect(within(nav).getByText('Escáner')).toBeInTheDocument()
    expect(within(nav).getByText('Subir Archivo')).toBeInTheDocument()
    expect(within(nav).getByText('Pendientes')).toBeInTheDocument()
    expect(within(nav).getByText('Historial')).toBeInTheDocument()
    expect(within(nav).queryByText('Facturas')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Empresas')).not.toBeInTheDocument()
    expect(within(nav).queryByText('Plataforma')).not.toBeInTheDocument()
  })

  it('R-056: historial es una pantalla propia de confirmadas', async () => {
    mockAuthenticatedAs('user')
    renderApp('/capturar')
    const user = userEvent.setup()

    expect(await screen.findByRole('heading', { name: 'Capturar factura' })).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Ver historial' }))

    expect(await screen.findByRole('heading', { name: 'Historial' })).toBeInTheDocument()
  })

  it('R-014: una subida aceptada no navega directamente a confirmación', async () => {
    mockAuthenticatedAs('user')
    renderApp('/capturar')
    const user = userEvent.setup()

    await screen.findByRole('heading', { name: 'Capturar factura' })
    await user.click(screen.getByRole('button', { name: 'Simular subida aceptada' }))

    expect(await screen.findByRole('heading', { name: 'Capturar factura' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Confirmar factura' })).not.toBeInTheDocument()
  })

  it('S2.2 decisión 1: la ruta de inicio de user es /capturar, no /historial', async () => {
    mockAuthenticatedAs('user')
    renderApp('/')

    expect(await screen.findByRole('heading', { name: 'Capturar factura' })).toBeInTheDocument()
  })

  it('un tenant_admin no puede entrar a /plataforma: vuelve a su ruta de inicio', async () => {
    mockAuthenticatedAs('tenant_admin')
    renderApp('/plataforma')

    expect(await screen.findByRole('heading', { name: 'Panel de facturas' })).toBeInTheDocument()
  })

  it('C12: "Ver facturas" desde una empresa navega al panel con esa empresa preseleccionada', async () => {
    mockAuthenticatedAs('tenant_admin')
    renderApp('/empresas')
    const user = userEvent.setup()

    expect(await screen.findByRole('heading', { name: 'Empresas' })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Ver facturas' }))

    expect(await screen.findByRole('heading', { name: 'Panel de facturas' })).toBeInTheDocument()
    // El combobox muestra el NOMBRE de la empresa (2026-08-10, buscable escribiendo), no el id
    // crudo que llevaba el `<select>` anterior -- el filtro real que viaja a la API sigue siendo
    // el id (`company_id=c1`), verificado aparte en `CompanyFilterCombobox.test.tsx`.
    expect(screen.getByLabelText('Empresa')).toHaveValue('Cliente SL')
  })

  it('C13: cerrar sesión desde el menú vuelve a login', async () => {
    mockAuthenticatedAs('tenant_admin')
    postMock.mockResolvedValueOnce({ data: { status: 'logged_out' }, error: undefined })
    renderApp('/facturas')
    const user = userEvent.setup()

    await screen.findByRole('heading', { name: 'Panel de facturas' })
    await user.click(screen.getByRole('button', { name: 'Cerrar sesión' }))

    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())
  })

  it('C5: visitar /login mientras el refresh silencioso está en curso no muestra el formulario todavía', async () => {
    let resolveRefresh: (value: Response) => void = () => {}
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveRefresh = resolve
        }),
    )
    renderApp('/login')

    // Mientras el refresh sigue pendiente, ni el login ni ningún contenido protegido deben verse.
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()

    resolveRefresh(new Response(null, { status: 401 }))

    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())
  })

  it('C4 + decisión 7: tras el login, vuelve a la ruta originalmente pedida, no a la de inicio del rol', async () => {
    mockUnauthenticated()
    renderApp('/empresas')
    const user = userEvent.setup()

    // Redirigido a login conservando el destino (empresas no es la ruta de inicio de tenant_admin,
    // que sería /facturas — si el test terminara ahí por casualidad no probaría nada).
    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())

    postMock.mockResolvedValueOnce({
      data: { access_token: 'tok', token_type: 'bearer' },
      error: undefined,
    })
    getMock.mockImplementation((path: string) => {
      if (path.includes('/auth/me')) {
        return Promise.resolve({ data: ME_BY_ROLE.tenant_admin, error: undefined })
      }
      if (path.includes('/reporting/companies')) return Promise.resolve({ data: COMPANIES, error: undefined })
      if (path.includes('/registrations')) return Promise.resolve({ data: [], error: undefined })
      throw new Error(`ruta GET no mockeada: ${path}`)
    })

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.type(screen.getByLabelText('Contraseña'), 's3cret')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('heading', { name: 'Empresas' })).toBeInTheDocument()
  })
})
