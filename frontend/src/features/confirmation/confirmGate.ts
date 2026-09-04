// Regla pura del botón "Confirmar y guardar" (spec §2/§4, C4-C8). El botón no es
// la frontera de seguridad (el backend reimpone las guardas en `confirm`); aquí
// se replica desde `blocking_reasons` para no dejar enviar algo que se rechazará.

export interface ConfirmGateInput {
  /** Motivos de bloqueo calculados por el servidor (vacío = confirmable). */
  blockingReasons: string[]
  /** Checkbox de responsabilidad marcado (regla 8, C7). */
  responsibilityAccepted: boolean
  /** `POST confirm` en vuelo: se deshabilita para evitar doble envío (§5). */
  submitting: boolean
  /** Un user solo puede continuar sin CIF propio si acepta expresamente esa excepción. */
  ownTaxIdExceptionAccepted?: boolean
  /** Confirmación explícita de que la persona ha revisado los datos mostrados. */
  reviewAcknowledged: boolean
}

/**
 * El botón está habilitado solo si NO hay motivos de bloqueo, la responsabilidad
 * está aceptada y no hay un envío en curso.
 */
export function isConfirmEnabled(input: ConfirmGateInput): boolean {
  const effectiveReasons = input.ownTaxIdExceptionAccepted
    ? input.blockingReasons.filter((reason) => reason !== 'own_tax_id_missing')
    : input.blockingReasons
  return (
    effectiveReasons.length === 0 &&
    input.responsibilityAccepted &&
    input.reviewAcknowledged &&
    !input.submitting
  )
}
