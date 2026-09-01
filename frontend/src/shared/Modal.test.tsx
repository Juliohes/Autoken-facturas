import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Modal } from './Modal'

describe('Modal', () => {
  it('expone un nombre accesible y enfoca el primer control al abrirse', () => {
    render(
      <Modal title="Editar factura" onClose={vi.fn()}>
        <button type="button">Guardar</button>
      </Modal>,
    )

    expect(screen.getByRole('dialog', { name: 'Editar factura' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar' })).toHaveFocus()
  })

  it('cierra con Escape y mantiene el foco dentro del diálogo', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(
      <Modal title="Editar factura" onClose={onClose}>
        <button type="button">Primero</button>
        <button type="button">Segundo</button>
      </Modal>,
    )

    await user.tab()
    expect(screen.getByRole('button', { name: 'Segundo' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Primero' })).toHaveFocus()
    await user.keyboard('{Escape}')

    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('cierra al pulsar el fondo, pero no al pulsar el contenido', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()

    render(
      <Modal title="Editar factura" onClose={onClose}>
        <button type="button">Guardar</button>
      </Modal>,
    )

    await user.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(onClose).not.toHaveBeenCalled()
    await user.click(screen.getByRole('dialog'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
