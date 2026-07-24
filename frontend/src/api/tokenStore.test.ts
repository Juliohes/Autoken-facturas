// Tests de comportamiento de `tokenStore` (S4.9): el almacén de sesión fuera de React que usa el
// middleware de `api/client.ts`. Puro (sin componentes): `fetch` global mockeado.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as tokenStore from './tokenStore'

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
  tokenStore.setToken(null)
  tokenStore.setUnauthorizedHandler(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('tokenStore (S4.9)', () => {
  it('getToken/setToken: guarda y devuelve el token en memoria', () => {
    expect(tokenStore.getToken()).toBeNull()
    tokenStore.setToken('abc123')
    expect(tokenStore.getToken()).toBe('abc123')
  })

  it('refreshOnce: éxito guarda el nuevo access_token y lo devuelve', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'nuevo-token', token_type: 'bearer' }), {
        status: 200,
      }),
    )

    const result = await tokenStore.refreshOnce()

    expect(result).toBe('nuevo-token')
    expect(tokenStore.getToken()).toBe('nuevo-token')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/refresh', { method: 'POST' })
  })

  it('refreshOnce: un 401 del backend devuelve null sin lanzar', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 401 }))

    const result = await tokenStore.refreshOnce()

    expect(result).toBeNull()
  })

  it('refreshOnce: un fallo de red devuelve null sin lanzar', async () => {
    fetchMock.mockRejectedValueOnce(new Error('network down'))

    const result = await tokenStore.refreshOnce()

    expect(result).toBeNull()
  })

  it('refreshOnce: dos llamadas concurrentes disparan una única petición de red (spec §5)', async () => {
    let resolveFetch: (value: Response) => void = () => {}
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve
        }),
    )

    const first = tokenStore.refreshOnce()
    const second = tokenStore.refreshOnce()

    resolveFetch(
      new Response(JSON.stringify({ access_token: 'unico', token_type: 'bearer' }), {
        status: 200,
      }),
    )

    expect(await first).toBe('unico')
    expect(await second).toBe('unico')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('refreshOnce: tras resolverse, una llamada posterior dispara una petición nueva', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'uno', token_type: 'bearer' }), { status: 200 }),
    )
    await tokenStore.refreshOnce()

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: 'dos', token_type: 'bearer' }), { status: 200 }),
    )
    const result = await tokenStore.refreshOnce()

    expect(result).toBe('dos')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('notifyUnauthorized: dispara el handler registrado, sin fallar si no hay ninguno', () => {
    expect(() => tokenStore.notifyUnauthorized()).not.toThrow()

    const handler = vi.fn()
    tokenStore.setUnauthorizedHandler(handler)
    tokenStore.notifyUnauthorized()
    expect(handler).toHaveBeenCalledTimes(1)
  })
})
