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
  // Bloque 4 (PROMPT-AUTOFACTU-AUTH-COMPLETO): endpoints públicos sin token. Un 401 aquí (token de
  // activación/restablecimiento/verificación inválido o caducado) no tiene nada que ver con la
  // sesión del navegador -- no debe disparar un refresh silencioso ni un `notifyUnauthorized()`.
  '/api/v1/auth/password/forgot',
  '/api/v1/auth/password/reset',
  '/api/v1/register',
  '/api/v1/auth/activate',
  '/api/v1/auth/activate/confirm',
  // Decisión de un alta por email (2026-09-03): mismo motivo, un token inválido/caducado del
  // enlace del email no tiene nada que ver con la sesión del navegador.
  '/api/v1/auth/registrations/decision',
])

type MultipartPath = '/api/v1/uploads' | '/api/v1/uploads/batch'
// Contrato S6.13 pendiente de que el backend publique OpenAPI actualizado. Se acota la ruta en
// origen para no aceptar URLs arbitrarias mientras `schema.d.ts` aún no la puede describir.
type RetryOcrPath = `/api/v1/uploads/${string}/retry-ocr`
type DeleteUploadPath = `/api/v1/uploads/${string}`

/**
 * Envía ficheros multipart sin forzar un `FormData` a través del tipo JSON que FastAPI publica
 * en OpenAPI. Mantiene la misma autenticación y recuperación de sesión que el cliente generado.
 */
export async function postMultipart(path: MultipartPath, body: FormData): Promise<Response> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response = await fetch(path, { method: 'POST', headers, body })
  if (response.status !== 401) return response

  const newToken = await refreshOnce()
  if (!newToken) {
    notifyUnauthorized()
    return response
  }

  headers.set('Authorization', `Bearer ${newToken}`)
  response = await fetch(path, { method: 'POST', headers, body })
  return response
}

/**
 * Llamada sin body al reintento OCR. Sustituir por `api.POST` al regenerar `schema.d.ts` con S6.13.
 * Conserva el mismo refresh transparente que la subida multipart.
 */
export async function postJson(path: RetryOcrPath): Promise<Response> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response = await fetch(path, { method: 'POST', headers })
  if (response.status !== 401) return response

  const newToken = await refreshOnce()
  if (!newToken) {
    notifyUnauthorized()
    return response
  }

  headers.set('Authorization', `Bearer ${newToken}`)
  response = await fetch(path, { method: 'POST', headers })
  return response
}

/** Borra un fichero pendiente manteniendo el mismo refresh transparente que el resto de acciones. */
export async function deleteUpload(path: DeleteUploadPath): Promise<Response> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response = await fetch(path, { method: 'DELETE', headers })
  if (response.status !== 401) return response

  const newToken = await refreshOnce()
  if (!newToken) {
    notifyUnauthorized()
    return response
  }

  headers.set('Authorization', `Bearer ${newToken}`)
  response = await fetch(path, { method: 'DELETE', headers })
  return response
}

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
