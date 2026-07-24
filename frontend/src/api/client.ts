import createClient from 'openapi-fetch'

import { getToken, notifyUnauthorized, refreshOnce } from './tokenStore'
import type { paths } from './schema'

// Cliente HTTP tipado generado desde el OpenAPI del backend.
// Los tipos viven en ./schema.d.ts (regenerar con `npm run gen:api`).
// baseUrl vacío: las rutas del OpenAPI ya incluyen el prefijo /api/v1.
export const api = createClient<paths>({ baseUrl: '' })

// Rutas de auth excluidas del interceptor de 401 (S4.9 decisión 4): un 401 de estas mismas rutas
// nunca debe disparar un intento de refresh (entraría en bucle contra sí mismo).
const AUTH_EXCLUDED_PATHS = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/refresh',
  '/api/v1/auth/logout',
])

// El body de una Request solo puede leerse una vez; `fetch(request)` lo consume al enviarlo. Para
// poder reconstruir la petición original tras un refresh (C7), se guarda una copia sin usar en
// `onRequest`, indexada por el `id` que openapi-fetch asigna a cada llamada.
const pendingRequests = new Map<string, Request>()

api.use({
  onRequest({ id, request }) {
    const token = getToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    pendingRequests.set(id, request.clone())
    return request
  },
  async onResponse({ id, schemaPath, response }) {
    const original = pendingRequests.get(id)
    pendingRequests.delete(id)

    if (response.status !== 401 || AUTH_EXCLUDED_PATHS.has(schemaPath) || !original) {
      return response
    }

    const newToken = await refreshOnce()
    if (!newToken) {
      notifyUnauthorized()
      return response
    }

    const retryRequest = new Request(original, { headers: new Headers(original.headers) })
    retryRequest.headers.set('Authorization', `Bearer ${newToken}`)
    return fetch(retryRequest)
  },
  // Si `fetch()` lanza (red caída, CORS, abort) openapi-fetch nunca llega a invocar `onResponse`
  // (hallazgo de auditoría, confirmado contra la librería): sin este `onError`, la copia guardada en
  // `pendingRequests` para esa petición se quedaba en el Map para siempre.
  onError({ id }) {
    pendingRequests.delete(id)
  },
})
