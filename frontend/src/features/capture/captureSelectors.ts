// Decisiones de negocio pequeñas de la pantalla de captura (S2.2), extraídas a funciones puras
// para poder testearlas sin montar el componente entero (hallazgo de auditoría SOLID: vivían
// inline en `CaptureScreen.tsx`, rompiendo el patrón "decisión → función pura" que sigue el resto
// del módulo, p. ej. `captureLoop.ts`/`uploadErrors.ts`).
import type { Role } from '../session/SessionProvider'
import { UploadCaptureError } from './useUploadCapture'

/** `user` sube siempre a su propia empresa, ya fijada; `tenant_admin` elige de un selector (C11/C12). */
export function resolveEffectiveCompanyId(
  role: Role | undefined,
  fixedCompanyId: string | undefined,
  selectedCompanyId: string,
): string {
  return role === 'user' ? (fixedCompanyId ?? '') : selectedCompanyId
}

export interface UploadState {
  message: string | null
  retryable: boolean
}

/** Traduce el error (si lo hay) de `useUploadCapture` al mensaje/reintentabilidad que ve el
 * usuario (C14): `UploadCaptureError` ya trae el mensaje de negocio correcto por código HTTP. */
export function describeUploadState(error: unknown, isError: boolean): UploadState {
  if (error instanceof UploadCaptureError) return { message: error.message, retryable: error.retryable }
  if (isError) return { message: 'No se pudo subir la foto.', retryable: true }
  return { message: null, retryable: true }
}
