// Contexto de sesión (S4.9): el `access_token` vive en memoria (nunca persistido, ADR-0012) más la
// identidad resuelta de `GET /auth/me` (rol, tenant, empresa). Al montar, intenta un refresh
// silencioso contra la cookie httpOnly antes de mostrar login (C5/C6); si un 401 llega a mitad de
// sesión, `tokenStore` avisa aquí para limpiar el estado y volver a login (C7).
import { useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import type { components } from '../../api/schema'
import * as tokenStore from '../../api/tokenStore'

// Cerrado a propósito (hallazgo de auditoría): `MeOut.role` llega como `string` suelto desde el
// OpenAPI generado (el backend no expone su `StrEnum` al esquema), y nada impedía un typo en una
// tabla rol->ruta. `Role` vive aquí (identidad/sesión) y `app/routes.ts` lo importa desde aquí, no
// al revés: `app/` depende de `features/session/`, nunca en la dirección contraria. Debe mantenerse
// a mano en sync con el enum real del backend (`backend/src/tenancy/constants.py`).
export type Role = 'platform_admin' | 'tenant_admin' | 'user'

function parseRole(value: string): Role | null {
  return value === 'platform_admin' || value === 'tenant_admin' || value === 'user' ? value : null
}

// El rol cerrado (spec §5 "rol desconocido/inesperado"): `parseRole` es el único punto que decide
// si un valor cuenta como identidad válida; cualquier cosa fuera del conjunto cerrado se trata
// igual que un `/auth/me` fallido, nunca como una sesión autenticada rota.
export type CurrentUser = Omit<components['schemas']['MeOut'], 'role'> & { role: Role }

export type SessionStatus = 'loading' | 'authenticated' | 'unauthenticated'

export type LoginResult =
  | { outcome: 'ok' }
  | { outcome: 'totp_required' }
  | { outcome: 'error'; message: string }

interface SessionValue {
  status: SessionStatus
  user: CurrentUser | null
  login: (email: string, password: string, totpCode?: string) => Promise<LoginResult>
  logout: () => Promise<void>
}

const SessionContext = createContext<SessionValue | null>(null)

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession debe usarse dentro de <SessionProvider>')
  return value
}

async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const { data, error } = await api.GET('/api/v1/auth/me')
  if (error || !data) return null
  const role = parseRole(data.role)
  if (!role) return null
  return { ...data, role }
}

function isTotpRequired(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'totp_required' in error
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('loading')
  const [user, setUser] = useState<CurrentUser | null>(null)
  const queryClient = useQueryClient()

  // Único punto que da por terminada una sesión (logout explícito o 401 sin refresh posible): limpia
  // el token en memoria, el estado de React y la caché de TanStack Query. Sin esto último, los datos
  // de negocio de un usuario (facturas, empresas...) sobrevivían en caché y podían aparecer
  // brevemente al iniciar sesión otra persona en la misma pestaña (hallazgo de auditoría de seguridad).
  const endSession = () => {
    tokenStore.setToken(null)
    queryClient.clear()
    setUser(null)
    setStatus('unauthenticated')
  }

  useEffect(() => {
    let cancelled = false

    tokenStore.setUnauthorizedHandler(() => {
      if (cancelled) return
      endSession()
    })

    void (async () => {
      const refreshed = await tokenStore.refreshOnce()
      if (cancelled) return
      if (!refreshed) {
        setStatus('unauthenticated')
        return
      }
      const me = await fetchCurrentUser()
      if (cancelled) return
      if (!me) {
        tokenStore.setToken(null)
        setStatus('unauthenticated')
        return
      }
      setUser(me)
      setStatus('authenticated')
    })()

    return () => {
      cancelled = true
      tokenStore.setUnauthorizedHandler(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = async (email: string, password: string, totpCode?: string): Promise<LoginResult> => {
    const { data, error } = await api.POST('/api/v1/auth/login', {
      body: { email, password, totp_code: totpCode ?? null },
    })
    if (error) {
      if (isTotpRequired(error)) return { outcome: 'totp_required' }
      return { outcome: 'error', message: errorDetail(error) ?? 'No se pudo iniciar sesión' }
    }
    const { access_token: accessToken } = data as { access_token: string; token_type: string }
    tokenStore.setToken(accessToken)

    const me = await fetchCurrentUser()
    if (!me) {
      tokenStore.setToken(null)
      return { outcome: 'error', message: 'No se pudo cargar la identidad del usuario' }
    }
    setUser(me)
    setStatus('authenticated')
    return { outcome: 'ok' }
  }

  const logout = async (): Promise<void> => {
    try {
      await api.POST('/api/v1/auth/logout')
    } catch {
      // best-effort (spec C13): aunque falle la llamada de red, la sesión local se limpia igual.
    }
    endSession()
  }

  return (
    <SessionContext.Provider value={{ status, user, login, logout }}>
      {children}
    </SessionContext.Provider>
  )
}
