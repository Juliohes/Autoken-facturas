// Almacén de sesión fuera de React (S4.9). `api/client.ts` es un cliente singleton importado
// fuera del árbol de componentes: no puede leer un contexto de React. Este módulo es el único
// punto de contacto entre el middleware HTTP (que añade `Authorization` y reacciona a un 401) y
// `SessionProvider` (que muestra el estado en la UI). El access token vive SOLO en memoria de
// JavaScript (ADR-0012), nunca en localStorage/sessionStorage.
let token: string | null = null
let unauthorizedHandler: (() => void) | null = null
let refreshPromise: Promise<string | null> | null = null

export function getToken(): string | null {
  return token
}

export function setToken(next: string | null): void {
  token = next
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

export function notifyUnauthorized(): void {
  unauthorizedHandler?.()
}

// Deduplica refresh concurrentes (spec §5 "refresh concurrente"): si dos peticiones reciben 401 a
// la vez, la segunda espera el resultado de la primera en vez de rotar el refresh token dos veces.
export function refreshOnce(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function performRefresh(): Promise<string | null> {
  try {
    const response = await fetch('/api/v1/auth/refresh', { method: 'POST' })
    if (!response.ok) return null
    const body = (await response.json()) as { access_token?: string }
    if (!body.access_token) return null
    token = body.access_token
    return token
  } catch {
    return null
  }
}
