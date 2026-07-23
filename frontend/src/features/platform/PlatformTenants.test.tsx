// Tests de comportamiento del panel de plataforma (S4.1), C1-C4 (frontend). El cliente de API
// está mockeado: se inyectan las respuestas de `platform/tenants` de cada escenario (sin
// navegador ni backend reales).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { PlatformTenants } from './PlatformTenants'
import type { Tenant } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock

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

function mockRoutes(tenants: Tenant[] = []) {
  getMock.mockImplementation((path: string) => {
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
