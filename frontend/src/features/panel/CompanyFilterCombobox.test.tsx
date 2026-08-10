// Tests de comportamiento del combobox de "Empresa" del panel de facturas (2026-08-10, a petición
// de Julio: "poder buscar escribiendo la empresa, no solo scroll por las opciones"). Componente
// puro (sin red): se prueba en aislado, sin mockear el cliente de API.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CompanyFilterCombobox } from './CompanyFilterCombobox'

const OPTIONS = [
  { id: 'c1', name: 'Zapatería Correa SL' },
  { id: 'c2', name: 'Aceros del Norte SA' },
  { id: 'c3', name: 'Zumos Naturales SL' },
]

describe('CompanyFilterCombobox (2026-08-10)', () => {
  it('escribir filtra la lista por texto, no hace falta hacer scroll por todas', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<CompanyFilterCombobox options={OPTIONS} value="" onChange={onChange} />)

    await user.type(screen.getByRole('combobox', { name: 'Empresa' }), 'zumo')

    expect(screen.getByRole('option', { name: 'Zumos Naturales SL' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Zapatería Correa SL' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Aceros del Norte SA' })).not.toBeInTheDocument()
  })

  it('el filtro no distingue mayúsculas/minúsculas', async () => {
    const user = userEvent.setup()
    render(<CompanyFilterCombobox options={OPTIONS} value="" onChange={vi.fn()} />)

    await user.type(screen.getByRole('combobox', { name: 'Empresa' }), 'ACEROS')

    expect(screen.getByRole('option', { name: 'Aceros del Norte SA' })).toBeInTheDocument()
  })

  it('pulsar una opción fija el filtro real (el id) y muestra su nombre en el campo', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<CompanyFilterCombobox options={OPTIONS} value="" onChange={onChange} />)

    await user.type(screen.getByRole('combobox', { name: 'Empresa' }), 'zumo')
    await user.click(screen.getByRole('option', { name: 'Zumos Naturales SL' }))

    expect(onChange).toHaveBeenCalledWith('c3')
    expect(screen.getByRole('combobox', { name: 'Empresa' })).toHaveValue('Zumos Naturales SL')
  })

  it('sin coincidencias, lo dice explícito en vez de una lista vacía muda', async () => {
    const user = userEvent.setup()
    render(<CompanyFilterCombobox options={OPTIONS} value="" onChange={vi.fn()} />)

    await user.type(screen.getByRole('combobox', { name: 'Empresa' }), 'no existe ninguna así')

    expect(screen.getByText('Sin resultados')).toBeInTheDocument()
  })

  it('"Todas" siempre aparece primero y limpia el filtro', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<CompanyFilterCombobox options={OPTIONS} value="c1" onChange={onChange} />)

    await user.click(screen.getByRole('combobox', { name: 'Empresa' }))
    await user.click(screen.getByRole('option', { name: 'Todas' }))

    expect(onChange).toHaveBeenCalledWith('')
  })

  it('escribir sin llegar a elegir y perder el foco vuelve al nombre de la empresa ya filtrada', async () => {
    const user = userEvent.setup()
    render(
      <>
        <CompanyFilterCombobox options={OPTIONS} value="c1" onChange={vi.fn()} />
        <button type="button">otro elemento</button>
      </>,
    )

    const input = screen.getByRole('combobox', { name: 'Empresa' })
    expect(input).toHaveValue('Zapatería Correa SL')
    await user.clear(input)
    await user.type(input, 'algo a medias')
    await user.click(screen.getByRole('button', { name: 'otro elemento' }))

    expect(input).toHaveValue('Zapatería Correa SL')
  })

  it('Escape cierra el desplegable y descarta lo escrito sin fijar nada', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<CompanyFilterCombobox options={OPTIONS} value="" onChange={onChange} />)

    const input = screen.getByRole('combobox', { name: 'Empresa' })
    await user.type(input, 'zumo')
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('Enter sobre un único resultado filtrado lo selecciona', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<CompanyFilterCombobox options={OPTIONS} value="" onChange={onChange} />)

    await user.type(screen.getByRole('combobox', { name: 'Empresa' }), 'zumo{Enter}')

    expect(onChange).toHaveBeenCalledWith('c3')
  })
})
