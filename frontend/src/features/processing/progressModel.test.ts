import { describe, expect, it } from 'vitest'

import { progressModel } from './progressModel'

describe('progressModel', () => {
  it('muestra el texto y porcentaje de la etapa durable', () => {
    expect(progressModel('processing', 'validating')).toEqual({
      message: 'Comprobando datos',
      subtext: 'Revisando CIF, importes e impuestos',
      percent: 70,
    })
  })

  it('no inventa una etapa si el backend antiguo no la devuelve', () => {
    expect(progressModel('processing', null).percent).toBeNull()
  })

  it('marca como lista una factura terminada', () => {
    expect(progressModel('needs_review', null).percent).toBe(100)
  })
})
