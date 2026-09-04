import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ProcessingProgress } from './ProcessingProgress'

describe('ProcessingProgress', () => {
  it('expone la etapa real con progreso accesible', () => {
    render(<ProcessingProgress status="processing" stage="primary_ocr" />)

    expect(screen.getByText('Procesando factura')).toBeInTheDocument()
    expect(screen.getByText('Leyendo los datos')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '48')
  })

  it('usa progreso indeterminado si el backend antiguo no devuelve etapa', () => {
    render(<ProcessingProgress status="processing" />)

    expect(screen.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow')
  })

  it('muestra un rango aproximado solo cuando el backend tiene base estadística', () => {
    render(
      <ProcessingProgress
        status="pending_ocr"
        stage="queued"
        etaSecondsMin={20}
        etaSecondsMax={35}
      />,
    )

    expect(screen.getByText('Aproximadamente 20–35 s')).toBeInTheDocument()
  })
})
