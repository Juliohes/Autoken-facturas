// Tests de comportamiento de `SessionProvider` (S4.9, C1-C3/C5-C8/C13 + hallazgos de auditoría:
// rol desconocido y limpieza de la caché de TanStack Query al terminar la sesión). El cliente de
// API está mockeado (login/logout/`auth/me`); el `fetch` global también, porque el refresh
// silencioso y el propio refresh viven en `tokenStore` con `fetch` crudo (fuera del cliente `api`,
// a propósito, para no entrar en bucle con su propio middleware).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import * as tokenStore from '../../api/tokenStore'
import { SessionProvider, useSession } from './SessionProvider'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock
const fetchMock = vi.fn()

const ME_TENANT_ADMIN = {
  id: 'u1',
  email: 'a@a.com',
  role: 'tenant_admin',
  tenant: 'ilex',
  company: null,
}

function Harness() {
  const session = useSession()
  const [result, setResult] = useState('')
  return (
    <div>
      <p data-testid="status">{session.status}</p>
      <p data-testid="role">{session.user?.role ?? ''}</p>
      <p data-testid="result">{result}</p>
      <button
        onClick={() => {
          void session.login('a@a.com', 'pw').then((r) => setResult(JSON.stringify(r)))
        }}
      >
        login
      </button>
      <button onClick={() => void session.logout()}>logout</button>
    </div>
  )
}

function renderHarness(queryClient = new QueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <Harness />
      </SessionProvider>
    </QueryClientProvider>,
  )
  return queryClient
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

describe('SessionProvider (S4.9)', () => {
  it('C6: sin cookie de refresh válida, arranca en unauthenticated', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))
    renderHarness()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))
  })

  it('C5: con cookie de refresh válida, restaura la sesión sin pedir credenciales', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer' }), { status: 200 }),
    )
    getMock.mockResolvedValueOnce({ data: ME_TENANT_ADMIN, error: undefined })

    renderHarness()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('role')).toHaveTextContent('tenant_admin')
  })

  it('rol desconocido/inesperado en /auth/me se trata como sesión inválida, no como autenticada', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer' }), { status: 200 }),
    )
    getMock.mockResolvedValueOnce({
      data: { ...ME_TENANT_ADMIN, role: 'super_admin_nuevo_sin_desplegar_en_frontend' },
      error: undefined,
    })

    renderHarness()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))
    expect(screen.getByTestId('role')).toHaveTextContent('')
  })

  it('C1: login correcto deja la sesión autenticada con el usuario resuelto', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))
    postMock.mockResolvedValueOnce({
      data: { access_token: 'tok', token_type: 'bearer' },
      error: undefined,
    })
    getMock.mockResolvedValueOnce({ data: ME_TENANT_ADMIN, error: undefined })

    renderHarness()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))

    fireEvent.click(screen.getByText('login'))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(postMock).toHaveBeenCalledWith('/api/v1/auth/login', {
      body: { email: 'a@a.com', password: 'pw', totp_code: null },
    })
  })

  it('C3: login con totp_required no autentica y lo señala en el resultado', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))
    postMock.mockResolvedValueOnce({ data: undefined, error: { totp_required: true } })

    renderHarness()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))

    fireEvent.click(screen.getByText('login'))

    await waitFor(() => expect(screen.getByTestId('result')).toHaveTextContent('totp_required'))
    expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated')
  })

  it('C2: login con credenciales incorrectas no autentica y expone el mensaje', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))
    postMock.mockResolvedValueOnce({ data: undefined, error: { detail: 'Invalid credentials' } })

    renderHarness()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))

    fireEvent.click(screen.getByText('login'))

    await waitFor(() => expect(screen.getByTestId('result')).toHaveTextContent('Invalid credentials'))
    expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated')
  })

  it('C13: logout limpia la sesión aunque la llamada de red falle', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer' }), { status: 200 }),
    )
    getMock.mockResolvedValueOnce({ data: ME_TENANT_ADMIN, error: undefined })
    postMock.mockRejectedValueOnce(new Error('network down'))

    renderHarness()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))

    fireEvent.click(screen.getByText('logout'))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))
    expect(screen.getByTestId('role')).toHaveTextContent('')
  })

  it('logout limpia la caché de datos de negocio (evita que el siguiente usuario vea los del anterior)', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer' }), { status: 200 }),
    )
    getMock.mockResolvedValueOnce({ data: ME_TENANT_ADMIN, error: undefined })
    postMock.mockResolvedValueOnce({ data: { status: 'logged_out' }, error: undefined })

    const queryClient = renderHarness()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    queryClient.setQueryData(['invoice-history'], { entries: [{ id: 'factura-de-ana' }] })

    fireEvent.click(screen.getByText('logout'))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))
    expect(queryClient.getQueryData(['invoice-history'])).toBeUndefined()
  })

  it('C7: un aviso de "no autorizado" a mitad de sesión limpia el estado local y la caché', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer' }), { status: 200 }),
    )
    getMock.mockResolvedValueOnce({ data: ME_TENANT_ADMIN, error: undefined })

    const queryClient = renderHarness()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    queryClient.setQueryData(['invoice-history'], { entries: [{ id: 'factura-de-ana' }] })

    tokenStore.notifyUnauthorized()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))
    expect(queryClient.getQueryData(['invoice-history'])).toBeUndefined()
    expect(tokenStore.getToken()).toBeNull()
  })
})
