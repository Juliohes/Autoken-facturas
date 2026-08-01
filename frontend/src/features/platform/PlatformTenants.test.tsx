// Tests de comportamiento del panel de plataforma (S4.1), C1-C4 (frontend). El cliente de API
// está mockeado: se inyectan las respuestas de `platform/tenants` de cada escenario (sin
// navegador ni backend reales).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { PlatformTenants } from './PlatformTenants'
import type { Tenant, TenantMetrics } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock
const deleteMock = api.DELETE as unknown as AsyncMock

function makeTenant(over: Partial<Tenant> = {}): Tenant {
  return {
    id: 't1',
    slug: 'nueva',
    name: 'Nueva SL',
    status: 'active',
    is_demo: false,
    created_at: '2026-07-24T00:00:00Z',
    ...over,
  }
}

function makeMetric(over: Partial<TenantMetrics> = {}): TenantMetrics {
  return {
    tenant_id: 't1',
    slug: 'nueva',
    name: 'Nueva SL',
    companies_count: 0,
    admins_count: 0,
    users_count: 0,
    invoices_this_month: 0,
    invoices_total_count: 0,
    ocr_extractions_count: 0,
    last_activity_at: null,
    ...over,
  }
}

function mockRoutes(tenants: Tenant[] = [], metrics: TenantMetrics[] = []) {
  getMock.mockImplementation((path: string) => {
    if (path.includes('/platform/tenants/metrics')) {
      return Promise.resolve({ data: metrics, error: undefined })
    }
    if (path.includes('/platform/tenants')) {
      return Promise.resolve({ data: tenants, error: undefined })
    }
    throw new Error(`ruta GET no mockeada: ${path}`)
  })
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PlatformTenants />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  deleteMock.mockReset()
})

describe('PlatformTenants (S4.1)', () => {
  it('C1: muestra una fila por tenant con subdominio, nombre, estado, demo y alta', async () => {
    mockRoutes([makeTenant({ slug: 'ilex', name: 'I-Lex', status: 'active', is_demo: true })])
    renderPanel()

    const rows = await screen.findAllByTestId('tenant-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('ilex')
    expect(rows[0]).toHaveTextContent('I-Lex')
    expect(rows[0]).toHaveTextContent('Activo')
    expect(rows[0]).toHaveTextContent('Sí')
  })

  it('C2: crear un tenant envía el alta con nombre, slug, logo y colores', async () => {
    mockRoutes([])
    postMock.mockResolvedValue({ data: makeTenant(), error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Todavía no hay tenants.')

    await user.type(screen.getByLabelText('Nombre'), 'Nueva SL')
    await user.type(screen.getByLabelText('Subdominio'), 'nueva')
    await user.type(screen.getByLabelText('Logo (URL)'), 'https://cdn.x/logo.png')
    await user.type(screen.getByLabelText('Color primario'), '#112233')
    await user.type(screen.getByLabelText('Color secundario'), '#445566')
    await user.click(screen.getByRole('button', { name: 'Nuevo tenant' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/api/v1/platform/tenants', {
        body: {
          name: 'Nueva SL',
          slug: 'nueva',
          logo_url: 'https://cdn.x/logo.png',
          color_primary: '#112233',
          color_secondary: '#445566',
          is_demo: false,
        },
      })
    })
  })

  it('C3: un error del servidor (slug duplicado) se muestra legible', async () => {
    mockRoutes([])
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Ya existe un tenant con ese slug' },
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Todavía no hay tenants.')

    await user.type(screen.getByLabelText('Nombre'), 'Otra')
    await user.type(screen.getByLabelText('Subdominio'), 'ilex')
    await user.click(screen.getByRole('button', { name: 'Nuevo tenant' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe un tenant con ese slug')
  })

  it('C4: sin tenants muestra el mensaje de vacío, no una tabla vacía', async () => {
    mockRoutes([])
    renderPanel()

    expect(await screen.findByText('Todavía no hay tenants.')).toBeInTheDocument()
    expect(screen.queryByTestId('tenants-table')).not.toBeInTheDocument()
  })
})

// --- S4.4 Modo demo (spec docs/specs/S4.4-modo-demo.md, criterios C12-C17 frontend) --------------

describe('PlatformTenants — modo demo (S4.4)', () => {
  it('C12/C13: el checkbox "Es demo" viaja en el alta (marcado -> true, sin marcar -> false)', async () => {
    mockRoutes([])
    postMock.mockResolvedValue({ data: makeTenant(), error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Todavía no hay tenants.')

    await user.type(screen.getByLabelText('Nombre'), 'Prospecto SL')
    await user.type(screen.getByLabelText('Subdominio'), 'prospecto')
    await user.click(screen.getByLabelText('Es demo'))
    await user.click(screen.getByRole('button', { name: 'Nuevo tenant' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        '/api/v1/platform/tenants',
        expect.objectContaining({ body: expect.objectContaining({ is_demo: true }) }),
      )
    })
  })

  it('C14: solo la fila demo muestra "Convertir a producción" y "Purgar"', async () => {
    mockRoutes([
      makeTenant({ id: 'demo-1', slug: 'demo', is_demo: true }),
      makeTenant({ id: 'prod-1', slug: 'prod', is_demo: false }),
    ])
    renderPanel()

    const rows = await screen.findAllByTestId('tenant-row')
    expect(rows).toHaveLength(2)
    const demoRow = rows.find((r) => r.textContent?.startsWith('demo'))
    const prodRow = rows.find((r) => r.textContent?.startsWith('prod'))
    expect(demoRow).toHaveTextContent('Convertir a producción')
    expect(demoRow).toHaveTextContent('Purgar')
    expect(prodRow).not.toHaveTextContent('Convertir a producción')
    expect(prodRow).not.toHaveTextContent('Purgar')
  })

  it('C15: "Convertir a producción" refresca la fila a "No" y oculta los botones', async () => {
    let tenants = [makeTenant({ id: 'demo-1', slug: 'demo', is_demo: true })]
    getMock.mockImplementation((path: string) =>
      path.includes('/metrics')
        ? Promise.resolve({ data: [], error: undefined })
        : Promise.resolve({ data: tenants, error: undefined }),
    )
    postMock.mockImplementation((path: string) => {
      if (path.includes('convert-to-production')) {
        tenants = tenants.map((t) => ({ ...t, is_demo: false }))
        return Promise.resolve({ data: tenants[0], error: undefined })
      }
      throw new Error(`ruta POST no mockeada: ${path}`)
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Convertir a producción' }))

    await waitFor(() => {
      const row = screen.getByTestId('tenant-row')
      expect(row).toHaveTextContent('No')
      expect(row).not.toHaveTextContent('Convertir a producción')
    })
  })

  it('C16: "Purgar" cancelado no llama a la API', async () => {
    mockRoutes([makeTenant({ id: 'demo-1', slug: 'demo', is_demo: true })])
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Purgar' }))

    expect(postMock).not.toHaveBeenCalledWith(
      '/api/v1/platform/tenants/{tenant_id}/purge',
      expect.anything(),
    )
  })

  it('un error del servidor al convertir a producción se muestra legible', async () => {
    mockRoutes([makeTenant({ id: 'demo-1', slug: 'demo', is_demo: true })])
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'No existe ese tenant' },
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Convertir a producción' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No existe ese tenant')
  })

  it('un error del servidor al purgar se muestra legible', async () => {
    mockRoutes([makeTenant({ id: 'demo-1', slug: 'demo', is_demo: true })])
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Solo se pueden purgar tenants demo' },
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Purgar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Solo se pueden purgar tenants demo')
  })

  it('C17: "Purgar" confirmado hace desaparecer la fila', async () => {
    let tenants = [makeTenant({ id: 'demo-1', slug: 'demo', is_demo: true })]
    getMock.mockImplementation((path: string) =>
      path.includes('/metrics')
        ? Promise.resolve({ data: [], error: undefined })
        : Promise.resolve({ data: tenants, error: undefined }),
    )
    postMock.mockImplementation((path: string) => {
      if (path.includes('/purge')) {
        tenants = []
        return Promise.resolve({ data: undefined, error: undefined })
      }
      throw new Error(`ruta POST no mockeada: ${path}`)
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Purgar' }))

    await waitFor(() => {
      expect(screen.queryByTestId('tenant-row')).not.toBeInTheDocument()
    })
  })
})

// --- S4.5 Métricas y consumo (spec docs/specs/S4.5-metricas-y-consumo.md, criterios C7-C8) --------

describe('PlatformTenants — métricas y consumo (S4.5)', () => {
  it('C7: muestra una fila por tenant con empresas/usuarios/admins/facturas/OCR/último uso', async () => {
    mockRoutes(
      [makeTenant()],
      [
        makeMetric({
          companies_count: 3,
          admins_count: 1,
          users_count: 2,
          invoices_this_month: 5,
          invoices_total_count: 9,
          ocr_extractions_count: 7,
          last_activity_at: '2026-07-24T10:00:00Z',
        }),
      ],
    )
    renderPanel()

    const rows = await screen.findAllByTestId('tenant-metrics-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('3')
    expect(rows[0]).toHaveTextContent('1')
    expect(rows[0]).toHaveTextContent('2')
    expect(rows[0]).toHaveTextContent('5')
    expect(rows[0]).toHaveTextContent('9')
    expect(rows[0]).toHaveTextContent('7')
    // Formateada (fecha+hora:minuto, sin segundos, hora peninsular): 10:00Z en julio -> 12:00 CEST.
    expect(rows[0]).toHaveTextContent('24/07/2026, 12:00')
  })

  it('spec §4: nunca presenta las métricas como dinero (sin €/$ ni la palabra "coste")', async () => {
    mockRoutes(
      [makeTenant()],
      [makeMetric({ companies_count: 3, admins_count: 1, users_count: 2, ocr_extractions_count: 7 })],
    )
    renderPanel()

    const row = await screen.findByTestId('tenant-metrics-row')
    expect(row).not.toHaveTextContent(/[€$]/)
    expect(row).not.toHaveTextContent(/coste/i)
  })

  it('C8: "último uso" nulo se muestra como texto legible, no null ni vacío', async () => {
    mockRoutes([makeTenant()], [makeMetric({ last_activity_at: null })])
    renderPanel()

    const row = await screen.findByTestId('tenant-metrics-row')
    expect(row).toHaveTextContent('Sin actividad')
  })
})

// --- S4.7 Ciclo de vida tenant (spec docs/specs/S4.7-ciclo-de-vida-tenant.md, C15-C16) ------------

describe('PlatformTenants — ciclo de vida (S4.7)', () => {
  it('C15: fila activa muestra "Suspender", fila suspendida muestra "Reactivar"', async () => {
    mockRoutes([
      makeTenant({ id: 't-activo', slug: 'activo', status: 'active' }),
      makeTenant({ id: 't-suspendido', slug: 'suspendido', status: 'suspended' }),
    ])
    renderPanel()

    const rows = await screen.findAllByTestId('tenant-row')
    const activo = rows.find((r) => r.textContent?.startsWith('activo'))
    const suspendido = rows.find((r) => r.textContent?.startsWith('suspendido'))
    expect(activo).toHaveTextContent('Suspender')
    expect(activo).not.toHaveTextContent('Reactivar')
    expect(suspendido).toHaveTextContent('Reactivar')
    expect(suspendido).not.toHaveTextContent('Suspender')
  })

  it('suspender llama al endpoint con el id del tenant', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'nueva', status: 'active' })])
    postMock.mockResolvedValue({ data: makeTenant({ status: 'suspended' }), error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Suspender' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        '/api/v1/platform/tenants/{tenant_id}/suspend',
        expect.objectContaining({ params: { path: { tenant_id: 't1' } } }),
      )
    })
  })

  it('exportar abre la URL de descarga en una pestaña nueva', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'nueva' })])
    postMock.mockResolvedValue({
      data: { download_url: 'https://minio.local/export.zip' },
      error: undefined,
    })
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Exportar' }))

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(
        'https://minio.local/export.zip',
        '_blank',
        'noopener,noreferrer',
      )
    })
  })

  it('C16: el botón de confirmar borrado está deshabilitado hasta escribir el slug exacto', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'clientex' })])
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))
    const confirmButton = screen.getByRole('button', { name: 'Confirmar borrado' })
    expect(confirmButton).toBeDisabled()

    const input = screen.getByLabelText('Escribe "clientex" para confirmar el borrado')
    await user.type(input, 'algo-distinto')
    expect(confirmButton).toBeDisabled()

    await user.clear(input)
    await user.type(input, 'clientex')
    expect(confirmButton).toBeEnabled()
  })

  it('C16: confirmar borrado con el slug exacto llama al DELETE con confirm_slug', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'clientex' })])
    deleteMock.mockResolvedValue({ data: undefined, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))
    await user.type(
      screen.getByLabelText('Escribe "clientex" para confirmar el borrado'),
      'clientex',
    )
    await user.click(screen.getByRole('button', { name: 'Confirmar borrado' }))

    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith('/api/v1/platform/tenants/{tenant_id}', {
        params: { path: { tenant_id: 't1' } },
        body: { confirm_slug: 'clientex' },
      })
    })
  })

  it('un error del servidor al suspender se muestra legible', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'nueva', status: 'active' })])
    postMock.mockResolvedValue({ data: undefined, error: { detail: 'No existe ese tenant' } })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Suspender' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No existe ese tenant')
  })

  it('un error del servidor al reactivar se muestra legible', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'nueva', status: 'suspended' })])
    postMock.mockResolvedValue({ data: undefined, error: { detail: 'No existe ese tenant' } })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Reactivar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No existe ese tenant')
  })

  it('un error del servidor al exportar se muestra legible', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'nueva' })])
    postMock.mockResolvedValue({ data: undefined, error: { detail: 'No existe ese tenant' } })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Exportar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No existe ese tenant')
  })

  it('un error del servidor al borrar se muestra legible', async () => {
    mockRoutes([makeTenant({ id: 't1', slug: 'clientex' })])
    deleteMock.mockResolvedValue({
      error: { detail: 'Hace falta exportar el tenant antes de poder borrarlo' },
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('tenant-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))
    await user.type(
      screen.getByLabelText('Escribe "clientex" para confirmar el borrado'),
      'clientex',
    )
    await user.click(screen.getByRole('button', { name: 'Confirmar borrado' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Hace falta exportar el tenant antes de poder borrarlo',
    )
  })
})
