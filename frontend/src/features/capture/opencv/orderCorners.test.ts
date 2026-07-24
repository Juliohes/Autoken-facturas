import { describe, expect, it } from 'vitest'

import { orderCorners } from './orderCorners'

describe('orderCorners', () => {
  it('ordena 4 puntos en cualquier orden de entrada a sup-izq, sup-der, inf-der, inf-izq', () => {
    const topLeft = { x: 10, y: 10 }
    const topRight = { x: 90, y: 12 }
    const bottomRight = { x: 88, y: 95 }
    const bottomLeft = { x: 8, y: 92 }

    // Entrada en un orden distinto y "revuelto" a propósito.
    const result = orderCorners([bottomRight, topLeft, bottomLeft, topRight])

    expect(result).toEqual([topLeft, topRight, bottomRight, bottomLeft])
  })

  it('funciona igual si la entrada ya viene en el orden canónico', () => {
    const topLeft = { x: 0, y: 0 }
    const topRight = { x: 100, y: 0 }
    const bottomRight = { x: 100, y: 100 }
    const bottomLeft = { x: 0, y: 100 }

    const result = orderCorners([topLeft, topRight, bottomRight, bottomLeft])

    expect(result).toEqual([topLeft, topRight, bottomRight, bottomLeft])
  })
})
