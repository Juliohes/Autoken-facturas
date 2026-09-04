// Tests de la regla pura del botón "Confirmar y guardar" (spec §4, C4-C8).
import { describe, expect, it } from 'vitest'

import { isConfirmEnabled } from './confirmGate'

describe('isConfirmEnabled', () => {
  it('habilita sin bloqueos, con responsabilidad y sin envío en curso', () => {
    expect(
      isConfirmEnabled({ blockingReasons: [], responsibilityAccepted: true, reviewAcknowledged: true, submitting: false }),
    ).toBe(true)
  })

  it('deshabilita si hay cualquier motivo de bloqueo', () => {
    expect(
      isConfirmEnabled({
        blockingReasons: ['counterparty_cif_invalid'],
        responsibilityAccepted: true,
        reviewAcknowledged: true,
        submitting: false,
      }),
    ).toBe(false)
  })

  it('deshabilita si no se acepta la responsabilidad', () => {
    expect(
      isConfirmEnabled({ blockingReasons: [], responsibilityAccepted: false, reviewAcknowledged: true, submitting: false }),
    ).toBe(false)
  })

  it('deshabilita mientras hay un envío en curso', () => {
    expect(
      isConfirmEnabled({ blockingReasons: [], responsibilityAccepted: true, reviewAcknowledged: true, submitting: true }),
    ).toBe(false)
  })

  it('S6.10 C10: permite al user aceptar expresamente la excepción de CIF propio, sin retirar otros bloqueos', () => {
    expect(isConfirmEnabled({ blockingReasons: ['own_tax_id_missing'], responsibilityAccepted: true, reviewAcknowledged: true, submitting: false, ownTaxIdExceptionAccepted: true })).toBe(true)
    expect(isConfirmEnabled({ blockingReasons: ['own_tax_id_missing', 'counterparty_cif_invalid'], responsibilityAccepted: true, reviewAcknowledged: true, submitting: false, ownTaxIdExceptionAccepted: true })).toBe(false)
  })

  it('deshabilita si no se ha marcado la revisión explícita', () => {
    expect(isConfirmEnabled({ blockingReasons: [], responsibilityAccepted: true, reviewAcknowledged: false, submitting: false })).toBe(false)
  })
})
