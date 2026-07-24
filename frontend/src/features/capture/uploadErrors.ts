// Mensajes de subida por código de estado (S2.2, C14) — pura, sin red, fácil de testear frente a
// cada caso del contrato de `POST /uploads` (S2.1).
export interface UploadErrorInfo {
  message: string
  retryable: boolean
}

export function describeUploadError(status: number, detail?: string): UploadErrorInfo {
  switch (status) {
    case 409:
      return { message: 'Esta factura ya se había subido antes (fichero duplicado).', retryable: false }
    case 413:
      return { message: 'La foto pesa demasiado. Repite la captura o baja la calidad.', retryable: false }
    case 415:
      return { message: 'Ese tipo de fichero no se admite.', retryable: false }
    case 503:
      return { message: 'El servicio no está disponible ahora mismo. Puedes reintentar.', retryable: true }
    default:
      return { message: detail ?? 'No se pudo subir la foto. Inténtalo de nuevo.', retryable: true }
  }
}
