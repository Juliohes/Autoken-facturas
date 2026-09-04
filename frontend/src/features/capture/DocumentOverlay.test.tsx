import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DocumentOverlay } from './DocumentOverlay'

describe('DocumentOverlay', () => {
  it('dibuja el perímetro detectado sin rellenar el área de la factura', async () => {
    Object.defineProperty(SVGSVGElement.prototype, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ width: 800, height: 600 }),
    })

    render(
      <DocumentOverlay
        corners={[{ x: 80, y: 60 }, { x: 720, y: 60 }, { x: 720, y: 540 }, { x: 80, y: 540 }]}
        sourceWidth={800}
        sourceHeight={600}
        state="good"
      />,
    )

    const polygon = await waitFor(() => screen.getByTestId('document-overlay-polygon'))
    expect(polygon).toHaveAttribute('fill', 'none')
  })
})
