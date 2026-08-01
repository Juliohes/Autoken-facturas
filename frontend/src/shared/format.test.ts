import { describe, expect, it } from 'vitest'

import { formatCurrency, formatDate, formatDateTime } from './format'

describe('formatDateTime', () => {
  it('formatea fecha+hora:minuto sin segundos por defecto, en hora peninsular', () => {
    // 2026-08-01T13:45:30Z en verano es CEST (UTC+2) -> 15:45 en Madrid.
    expect(formatDateTime('2026-08-01T13:45:30Z')).toBe('01/08/2026, 15:45')
  })

  it('incluye segundos cuando se pide explícitamente', () => {
    expect(formatDateTime('2026-08-01T13:45:30Z', { seconds: true })).toBe('01/08/2026, 15:45:30')
  })

  it('usa el fallback cuando no hay valor', () => {
    expect(formatDateTime(null)).toBe('Sin actividad')
    expect(formatDateTime(undefined, { fallback: 'Nunca' })).toBe('Nunca')
  })

  it('usa el fallback ante una fecha inválida', () => {
    expect(formatDateTime('no-es-una-fecha')).toBe('Sin actividad')
  })
})

describe('formatDate', () => {
  it('formatea solo día/mes/año, sin hora', () => {
    expect(formatDate('2026-08-01T13:45:30Z')).toBe('01/08/2026')
  })

  it('usa el fallback ante valores vacíos', () => {
    expect(formatDate(null)).toBe('—')
  })
})

describe('formatCurrency', () => {
  it('usa coma para los decimales, nunca punto', () => {
    expect(formatCurrency(1234.5)).toBe('1.234,50')
    expect(formatCurrency('121.00')).toBe('121,00')
  })

  it('usa el fallback ante valores vacíos o no numéricos', () => {
    expect(formatCurrency(null)).toBe('—')
    expect(formatCurrency(undefined)).toBe('—')
    expect(formatCurrency('no-numero')).toBe('—')
  })
})
