// Tests mínimos de los primitivos src/ui (Bloque 2).
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Banner } from './Banner'
import { Button } from './Button'
import { EmptyState } from './EmptyState'
import { SegmentedControl } from './SegmentedControl'
import { Spinner } from './Spinner'
import { StatusBadge } from './StatusBadge'

describe('src/ui primitivos', () => {
  it('Button primary usa la variante de acento y respeta loading/disabled', () => {
    render(<Button variant="primary" loading>Guardar</Button>)
    const btn = screen.getByRole('button', { name: 'Guardar' })
    expect(btn).toHaveClass('tn-btn-primary')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('aria-busy', 'true')
  })

  it('StatusBadge comunica el estado con color + icono + texto', () => {
    render(<StatusBadge tone="ok" label="Fiable" />)
    const badge = screen.getByText('Fiable')
    expect(badge.closest('.tn-status-badge')).toHaveAttribute('data-tone', 'ok')
    expect(badge.closest('.tn-status-badge')?.querySelector('svg')).toBeInTheDocument()
  })

  it('Spinner anuncia el estado de carga a lectores de pantalla', () => {
    render(<Spinner label="Guardando factura" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('Guardando factura')).toBeInTheDocument()
  })

  it('Banner de error usa role=alert', () => {
    render(<Banner tone="bad">No se pudo subir</Banner>)
    expect(screen.getByRole('alert')).toHaveTextContent('No se pudo subir')
  })

  it('EmptyState muestra título, descripción y acción', () => {
    render(<EmptyState title="Sin facturas" description="Sube la primera" action={<span>CTA</span>} />)
    expect(screen.getByText('Sin facturas')).toBeInTheDocument()
    expect(screen.getByText('Sube la primera')).toBeInTheDocument()
    expect(screen.getByText('CTA')).toBeInTheDocument()
  })

  it('SegmentedControl marca la opción activa y notifica el cambio', async () => {
    const onChange = vi.fn()
    render(
      <SegmentedControl
        label="Dirección"
        value={null}
        onChange={onChange}
        options={[{ value: 'recibida', label: 'Recibida' }, { value: 'emitida', label: 'Emitida' }]}
      />,
    )
    const user = userEvent.setup()
    const recibida = screen.getByRole('radio', { name: 'Recibida' })
    expect(recibida).toHaveAttribute('aria-checked', 'false')
    await user.click(recibida)
    expect(onChange).toHaveBeenCalledWith('recibida')
  })
})
