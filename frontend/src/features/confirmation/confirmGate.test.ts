// Tests de la regla pura del botón "Confirmar y guardar" (spec §4, C4-C8).
import { describe, expect, it } from 'vitest'

import { isConfirmEnabled } from './confirmGate'

describe('isConfirmEnabled', () => {
  it('habilita sin bloqueos, con responsabilidad y sin envío en curso', () => {
    expect(
      isConfirmEnabled({ blockingReasons: [], responsibilityAccepted: true, submitting: false }),
    ).toBe(true)
  })

  it('deshabilita si hay cualquier motivo de bloqueo', () => {
    expect(
      isConfirmEnabled({
        blockingReasons: ['counterparty_cif_invalid'],
        responsibilityAccepted: true,
        submitting: false,
      }),
    ).toBe(false)
  })

  it('deshabilita si no se acepta la responsabilidad', () => {
    expect(
      isConfirmEnabled({ blockingReasons: [], responsibilityAccepted: false, submitting: false }),
    ).toBe(false)
  })

  it('deshabilita mientras hay un envío en curso', () => {
    expect(
      isConfirmEnabled({ blockingReasons: [], responsibilityAccepted: true, submitting: true }),
    ).toBe(false)
  })
})
