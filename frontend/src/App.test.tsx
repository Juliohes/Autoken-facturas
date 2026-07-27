// Tests de comportamiento de S4.2/S4.3 (theming) + S4.9 C14 (el branding se aplica también en
// login). El cliente de API está mockeado (`tenants/current`); `fetch` global también, porque sin
// sesión el arranque del app-shell intenta un refresh silencioso (401 esperado) antes de mostrar
// login.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import App from './App'
import { api } from './api/client'
import {
  DEFAULT_APP_NAME,
  DEFAULT_COLOR_PRIMARY,
  DEFAULT_COLOR_SECONDARY,
  DEFAULT_LOGO_URL,
} from './features/tenancy/theme'
import type { CurrentTenant } from './features/tenancy/types'

vi.mock('./api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const fetchMock = vi.fn()

function makeTenant(over: Partial<CurrentTenant> = {}): CurrentTenant {
  return {
    slug: 'ilex',
    name: 'I-Lex Asesoría',
    is_demo: false,
    logo_url: null,
    color_primary: null,
    color_secondary: null,
    app_name: null,
    favicon: null,
    ...over,
  }
}

function mockRoutes(tenant: CurrentTenant | 'error') {
  getMock.mockImplementation((path: string) => {
    if (path.includes('/tenants/current')) {
      if (tenant === 'error') {
        return Promise.resolve({ data: undefined, error: { detail: 'Not Found' } })
      }
      return Promise.resolve({ data: tenant, error: undefined })
    }
    throw new Error(`ruta GET no mockeada: ${path}`)
  })
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  // Sin cookie de refresh válida: el app-shell arranca en login (mismo criterio en todos los casos
  // de este fichero, que solo prueban theming, no sesión).
  fetchMock.mockResolvedValue(new Response(null, { status: 401 }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  document.title = ''
  document.documentElement.style.removeProperty('--color-primary')
  document.documentElement.style.removeProperty('--color-secondary')
  document.getElementById('tenant-favicon')?.remove()
})

describe('App (S4.2/S4.3 theming runtime + S4.9 C14)', () => {
  it('C5: con branding, aplica colores y título del tenant', async () => {
    mockRoutes(
      makeTenant({ app_name: 'I-Lex', color_primary: '#112233', color_secondary: '#445566' }),
    )
    renderApp()

    await waitFor(() => expect(document.title).toBe('I-Lex'))
    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe('#112233')
    expect(document.documentElement.style.getPropertyValue('--color-secondary')).toBe('#445566')
  })

  it('C6: sin branding, aplica los valores por defecto (Setex igual que hoy)', async () => {
    mockRoutes(makeTenant())
    renderApp()

    await waitFor(() => expect(document.title).toBe(DEFAULT_APP_NAME))
    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe(
      DEFAULT_COLOR_PRIMARY,
    )
    expect(document.documentElement.style.getPropertyValue('--color-secondary')).toBe(
      DEFAULT_COLOR_SECONDARY,
    )
  })

  it('C7 + S4.9 C14: con logo, se muestra ya en la pantalla de login', async () => {
    mockRoutes(makeTenant({ app_name: 'I-Lex', logo_url: 'https://cdn.x/logo.png' }))
    renderApp()

    const logo = await screen.findByAltText('I-Lex')
    expect(logo).toHaveAttribute('src', 'https://cdn.x/logo.png')
    // El branding se aplicó ANTES/junto con el formulario de login (S4.9 decisión 9).
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
  })

  it('C7 (revisado): sin logo_url propio, cae al logo real de Autoken (no queda sin imagen)', async () => {
    mockRoutes(makeTenant())
    renderApp()

    await waitFor(() => expect(document.title).toBe(DEFAULT_APP_NAME))
    expect(screen.getByRole('img')).toHaveAttribute('src', DEFAULT_LOGO_URL)
  })

  it('S4.3 C5: con favicon (aunque sea el único campo de branding), inyecta el link', async () => {
    mockRoutes(makeTenant({ favicon: 'https://cdn.x/favicon.png' }))
    renderApp()

    await waitFor(() => {
      const link = document.querySelector('link[rel="icon"]')
      expect(link).not.toBeNull()
      expect(link).toHaveAttribute('href', 'https://cdn.x/favicon.png')
    })
  })

  it('S4.3 C6: sin favicon, no hay ningún <link rel="icon">', async () => {
    mockRoutes(makeTenant())
    renderApp()

    await waitFor(() => expect(document.title).toBe(DEFAULT_APP_NAME))
    expect(document.querySelector('link[rel="icon"]')).toBeNull()
  })

  it('C8: un fallo al cargar el tenant no bloquea el arranque ni muestra error', async () => {
    mockRoutes('error')
    renderApp()

    await waitFor(() => expect(document.title).toBe(DEFAULT_APP_NAME))
    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe(
      DEFAULT_COLOR_PRIMARY,
    )
    // El login (contenido por defecto sin sesión) sigue mostrándose con normalidad.
    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
