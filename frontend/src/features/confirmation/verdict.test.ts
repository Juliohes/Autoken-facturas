// Tests de la lógica pura del veredicto del CIF de contraparte (spec §2, C3).
import { describe, expect, it } from 'vitest'

import { renderVerdict } from './verdict'

describe('renderVerdict', () => {
  it('valid + name_match -> verde', () => {
    expect(
      renderVerdict({ status: 'valid', name_match: true, official_name: null }),
    ).toEqual({ tone: 'ok', message: expect.stringMatching(/verificado/i) })
  })

  it('valid + name_match=false -> aviso con la razón social oficial', () => {
    const rendered = renderVerdict({
      status: 'valid',
      name_match: false,
      official_name: 'ACME SL',
    })
    expect(rendered.tone).toBe('warn')
    expect(rendered.message).toContain('ACME SL')
  })

  it('invalid y not_found -> rojo', () => {
    expect(renderVerdict({ status: 'invalid', name_match: null, official_name: null }).tone).toBe(
      'error',
    )
    expect(
      renderVerdict({ status: 'not_found', name_match: null, official_name: null }).tone,
    ).toBe('error')
  })

  it('unverified -> aviso revisar manual', () => {
    const rendered = renderVerdict({ status: 'unverified', name_match: null, official_name: null })
    expect(rendered.tone).toBe('warn')
    expect(rendered.message).toMatch(/revisar manual/i)
  })
})
