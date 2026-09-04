import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CapturePreview } from './CapturePreview'

describe('CapturePreview (R-010)', () => {
  it('ofrece Repetir y Usar foto sin llamar al backend por sí mismo', () => {
    const onRepeat = vi.fn()
    const onUse = vi.fn()
    render(<CapturePreview previewUrl="blob:preview" status="idle" onRepeat={onRepeat} onUse={onUse} />)

    expect(screen.getByRole('heading', { name: 'Revisar foto' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Vista previa de la factura' })).toHaveAttribute('src', 'blob:preview')
    fireEvent.click(screen.getByRole('button', { name: 'Repetir' }))
    fireEvent.click(screen.getByRole('button', { name: 'Usar foto' }))

    expect(onRepeat).toHaveBeenCalledOnce()
    expect(onUse).toHaveBeenCalledOnce()
  })

  it('muestra Guardando factura y bloquea acciones mientras confirma', () => {
    render(<CapturePreview previewUrl="blob:preview" status="uploading" onRepeat={vi.fn()} onUse={vi.fn()} />)

    expect(screen.getByText('Guardando factura…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Repetir' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Usar foto' })).toBeDisabled()
  })
})
