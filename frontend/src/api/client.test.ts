// Tests de comportamiento del middleware de `api/client.ts` (S4.9, C7/C8): inyección de
// `Authorization`, interceptor de 401 con refresh + reintento, y exclusión de las propias rutas de
// auth. `fetch` global mockeado (sin backend real); `tokenStore` real (no se mockea, es el propio
// mecanismo bajo prueba).
import { beforeEach, describe, expect, it, vi } from 'vitest'

// El navegador resuelve `fetch('/api/v1/...')` y `new Request('/api/v1/...')` contra el origen de
// la página; Node (el entorno de test) no tiene "página": su `Request` global exige URLs
// absolutas, y `createClient()` (en `./client`) captura tanto `globalThis.Request` como
// `globalThis.fetch` una única vez, al importarse el módulo. `vi.stubGlobal` en un `beforeEach` no
// llegaría a tiempo (los imports ya se evaluaron); por eso el parche vive en `vi.hoisted`, que
// Vitest sube por encima de los imports. No afecta a producción: ahí el navegador ya resuelve la
// URL relativa por sí solo.
const { fetchMock } = vi.hoisted(() => {
  const fetchMock = vi.fn()
  class TestRequest extends globalThis.Request {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      const resolved =
        typeof input === 'string' && input.startsWith('/') ? new URL(input, 'http://localhost') : input
      super(resolved as RequestInfo | URL, init)
    }
  }
  globalThis.Request = TestRequest as unknown as typeof Request
  globalThis.fetch = ((...args: Parameters<typeof fetch>) => fetchMock(...args)) as typeof fetch
  return { fetchMock }
})

import * as tokenStore from './tokenStore'
import { api } from './client'

// `tokenStore.refreshOnce()` llama a `fetch('/api/v1/auth/refresh', ...)` directamente (a
// propósito, fuera del cliente `api`, para no entrar en bucle con su propio middleware) — a ese
// `fetchMock` le llega la URL como string plano, no como `Request`; las llamadas del cliente `api`
// sí llegan como `Request` ya construido. `pathOf` soporta ambas formas.
function pathOf(input: Request | string): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.url).pathname
}

beforeEach(() => {
  fetchMock.mockReset()
  tokenStore.setToken(null)
  tokenStore.setUnauthorizedHandler(null)
})

describe('api client middleware (S4.9)', () => {
  it('añade Authorization: Bearer cuando hay un token en memoria', async () => {
    tokenStore.setToken('mi-token')
    fetchMock.mockImplementationOnce(async (request: Request) => {
      expect(request.headers.get('Authorization')).toBe('Bearer mi-token')
      return new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    })

    await api.GET('/api/v1/health')

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('no añade Authorization si no hay sesión', async () => {
    fetchMock.mockImplementationOnce(async (request: Request) => {
      expect(request.headers.has('Authorization')).toBe(false)
      return new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    })

    await api.GET('/api/v1/health')
  })

  it('C7: un 401 dispara un refresh y reintenta la petición original con el token nuevo', async () => {
    tokenStore.setToken('caducado')
    let healthCalls = 0
    fetchMock.mockImplementation(async (input: Request | string) => {
      const path = pathOf(input)
      if (path === '/api/v1/auth/refresh') {
        return new Response(JSON.stringify({ access_token: 'nuevo', token_type: 'bearer' }), {
          status: 200,
        })
      }
      if (path === '/api/v1/health') {
        const request = input as Request
        healthCalls += 1
        if (healthCalls === 1) {
          expect(request.headers.get('Authorization')).toBe('Bearer caducado')
          return new Response(null, { status: 401 })
        }
        expect(request.headers.get('Authorization')).toBe('Bearer nuevo')
        return new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
      }
      throw new Error(`ruta no esperada: ${path}`)
    })

    const { data, error } = await api.GET('/api/v1/health')

    expect(error).toBeUndefined()
    expect(data).toEqual({ status: 'ok' })
    expect(healthCalls).toBe(2)
    expect(tokenStore.getToken()).toBe('nuevo')
  })

  it('si el refresh también falla, avisa al handler de sesión y no reintenta la petición', async () => {
    const handler = vi.fn()
    tokenStore.setUnauthorizedHandler(handler)
    fetchMock.mockImplementation(async () => new Response(null, { status: 401 }))

    await api.GET('/api/v1/health')

    expect(handler).toHaveBeenCalledTimes(1)
    // original (401) + intento de refresh (401 también) — sin un tercer reintento.
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('C8: un 401 de las propias rutas de auth nunca dispara un refresh (evita el bucle)', async () => {
    fetchMock.mockImplementation(async (input: Request | string) => {
      const path = pathOf(input)
      if (path === '/api/v1/auth/login') {
        return new Response(JSON.stringify({ detail: 'Invalid credentials' }), { status: 401 })
      }
      throw new Error(`no debería llamarse: ${path}`)
    })

    const { error } = await api.POST('/api/v1/auth/login', {
      body: { email: 'a@a.com', password: 'x' },
    })

    expect(error).toEqual({ detail: 'Invalid credentials' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('un fallo de red no deja el middleware en un estado roto para la siguiente petición', async () => {
    // openapi-fetch invoca `onError`, no `onResponse`, cuando `fetch()` rechaza — sin un `onError`
    // que limpie `pendingRequests`, la entrada de esa petición se quedaba en el Map para siempre
    // (hallazgo de auditoría). El síntoma observable si el cleanup faltara sería que una petición
    // POSTERIOR con el mismo `id` reciclado por `openapi-fetch` arrastrara datos obsoletos; aquí
    // comprobamos el caso simple y real: tras un fallo de red, la siguiente petición funciona con
    // normalidad (inyecta el token, no arrastra ningún estado del intento fallido).
    tokenStore.setToken('mi-token')
    fetchMock.mockRejectedValueOnce(new Error('network down'))

    await expect(api.GET('/api/v1/health')).rejects.toThrow('network down')

    fetchMock.mockImplementationOnce(async (request: Request) => {
      expect(request.headers.get('Authorization')).toBe('Bearer mi-token')
      return new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    })
    const { data, error } = await api.GET('/api/v1/health')

    expect(error).toBeUndefined()
    expect(data).toEqual({ status: 'ok' })
  })
})
