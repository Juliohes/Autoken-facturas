// Tests del formateo del % de IVA (spec §2, C8-bis): nunca ".0"/",0" superfluo,
// pero sin tocar decimales reales. Petición explícita de Julio, 2026-07-22.
import { describe, expect, it } from 'vitest'

import { formatIvaPercentage } from './percentage'

describe('formatIvaPercentage', () => {
  it('entero con .0 -> sin decimales', () => {
    expect(formatIvaPercentage(21.0)).toBe('21')
    expect(formatIvaPercentage('21.0')).toBe('21')
    expect(formatIvaPercentage('21.00')).toBe('21')
  })

  it('coma decimal (formato ES) con ceros -> sin decimales', () => {
    expect(formatIvaPercentage('21,0')).toBe('21')
    expect(formatIvaPercentage('4,00')).toBe('4')
  })

  it('entero ya limpio se mantiene igual', () => {
    expect(formatIvaPercentage(10)).toBe('10')
    expect(formatIvaPercentage('0')).toBe('0')
  })

  it('decimal real (no .0) se conserva, nunca se inventa ni redondea', () => {
    expect(formatIvaPercentage(4.5)).toBe('4.5')
    expect(formatIvaPercentage('4,5')).toBe('4.5')
  })

  it('campo no leído (null/undefined/vacío/no numérico) -> string vacío, nunca inventado', () => {
    expect(formatIvaPercentage(null)).toBe('')
    expect(formatIvaPercentage(undefined)).toBe('')
    expect(formatIvaPercentage('')).toBe('')
    expect(formatIvaPercentage('  ')).toBe('')
    expect(formatIvaPercentage('no-es-un-numero')).toBe('')
  })

  it('otros campos del tramo (base/cuota) no pasan por aquí y conservan sus decimales', () => {
    // Documentado por contrato, no por comportamiento de esta función: ver
    // taxLineToForm en formState.ts, que solo aplica formatIvaPercentage a `iva_pct`.
    expect(formatIvaPercentage(1250.5)).toBe('1250.5')
  })
})
