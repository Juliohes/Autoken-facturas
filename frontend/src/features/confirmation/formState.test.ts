// Tests de formState (spec docs/specs/S6.1-rediseno-celdas-comprobacion.md, Áreas A y D).
// Sin componente de por medio: lógica pura de conversión entre lo que devuelve `review`, lo que
// edita el humano (coma decimal, spec C16-C19) y lo que espera `confirm` (punto decimal).
import { describe, expect, it } from 'vitest'

import { formStateToConfirmBody, reviewToFormState, type ConfirmFormState } from './formState'
import type { ReviewFields } from './types'

function baseFields(overrides: Partial<ReviewFields> = {}): ReviewFields {
  return {
    issue_date: '2026-05-10',
    total_amount: '121.45',
    net_amount: '100.00',
    tax_amount: '21.45',
    invoice_number: 'F-2026-001',
    irpf_rate: null,
    irpf_amount: null,
    counterparty_tax_id: 'A39031620',
    counterparty_name: 'Proveedor SA',
    tax_lines: [],
    ...overrides,
  }
}

function baseForm(overrides: Partial<ConfirmFormState> = {}): ConfirmFormState {
  return {
    issue_date: '2026-05-10',
    counterparty_tax_id: 'A39031620',
    counterparty_name: 'Proveedor SA',
    invoice_number: '',
    net_amount: '100,00',
    tax_amount: '21,45',
    total_amount: '121,45',
    irpf_amount: '',
    tax_lines: [],
    ...overrides,
  }
}

describe('reviewToFormState — formato con coma decimal (spec: S6.1 C16)', () => {
  it('muestra las cantidades con coma decimal, nunca con punto', () => {
    const form = reviewToFormState(baseFields())
    expect(form.total_amount).toBe('121,45')
    expect(form.net_amount).toBe('100,00')
    expect(form.tax_amount).toBe('21,45')
  })

  it('vuelca el IRPF leído por el OCR en su casilla editable', () => {
    const form = reviewToFormState(
      baseFields({ irpf_rate: '19', irpf_amount: '19.00' }),
    )

    expect(form.irpf_amount).toBe('19,00')
  })

  it('un valor sin parte decimal no gana una coma superflua', () => {
    const form = reviewToFormState(baseFields({ total_amount: '121' }))
    expect(form.total_amount).toBe('121')
  })

  it('un campo ausente (null) sigue siendo un input vacío, no "null" ni "NaN"', () => {
    const form = reviewToFormState(baseFields({ total_amount: null }))
    expect(form.total_amount).toBe('')
  })
})

describe('reviewToFormState — número de factura (spec: S6.1 C1/C19)', () => {
  it('vuelca el número de factura leído tal cual, sin formato de importe', () => {
    const form = reviewToFormState(baseFields({ invoice_number: 'F-2026.05' }))
    expect(form.invoice_number).toBe('F-2026.05')
  })

  it('sin número de factura leído, el input queda vacío (no inventa uno)', () => {
    const form = reviewToFormState(baseFields({ invoice_number: null }))
    expect(form.invoice_number).toBe('')
  })
})

describe('formStateToConfirmBody — conversión coma/punto al confirmar (spec: S6.1 C17/C18)', () => {
  const options = { direction: 'recibida' as const, responsibilityAccepted: true }

  it('convierte una cantidad escrita con coma al punto decimal que espera el backend', () => {
    const body = formStateToConfirmBody(baseForm({ total_amount: '121,45' }), options)
    expect(body.total_amount).toBe('121.45')
  })

  it('tolera que el usuario haya tecleado con punto por costumbre, sin romper', () => {
    const body = formStateToConfirmBody(baseForm({ total_amount: '121.45' }), options)
    expect(body.total_amount).toBe('121.45')
  })

  it('una coma con 3+ dígitos detrás (posible separador de miles, ej. "1,234") NO se convierte a ciegas — hallazgo de auditoría: convertirla en 1.234 sería un importe ~1000x distinto, silenciosamente aceptado', () => {
    const body = formStateToConfirmBody(baseForm({ total_amount: '1,234' }), options)
    // Se envía sin convertir: el backend (Decimal de Pydantic) la rechaza con un 422 claro,
    // en vez de aceptar en silencio un importe equivocado.
    expect(body.total_amount).toBe('1,234')
    expect(body.total_amount).not.toBe('1.234')
  })

  it('convierte también la base y la cuota de cada tramo de IVA', () => {
    const body = formStateToConfirmBody(
      baseForm({ tax_lines: [{ iva_pct: '21', base: '100,00', cuota: '21,00' }] }),
      options,
    )
    expect(body.tax_lines[0].base).toBe('100.00')
    expect(body.tax_lines[0].cuota).toBe('21.00')
  })

  it('convierte el IRPF igual que el resto de cantidades', () => {
    const body = formStateToConfirmBody(baseForm({ irpf_amount: '15,00' }), options)
    expect(body.irpf_amount).toBe('15.00')
  })
})

describe('formStateToConfirmBody — número de factura (spec: S6.1 C5/C19)', () => {
  const options = { direction: 'recibida' as const, responsibilityAccepted: true }

  it('envía el número de factura tal cual, sin convertir separador decimal', () => {
    const body = formStateToConfirmBody(baseForm({ invoice_number: 'F-2026.05' }), options)
    expect(body.invoice_number).toBe('F-2026.05')
  })

  it('un número de factura vacío se envía como null (campo no leído, regla 4)', () => {
    const body = formStateToConfirmBody(baseForm({ invoice_number: '' }), options)
    expect(body.invoice_number).toBeNull()
  })
})
