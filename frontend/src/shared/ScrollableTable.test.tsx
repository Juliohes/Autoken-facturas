import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ScrollableTable } from './ScrollableTable'

describe('ScrollableTable', () => {
  it('renderiza el contenido tal cual, envuelto en las dos barras', () => {
    render(
      <ScrollableTable>
        <table data-testid="inner-table">
          <tbody>
            <tr>
              <td>Contenido</td>
            </tr>
          </tbody>
        </table>
      </ScrollableTable>,
    )

    expect(screen.getByTestId('inner-table')).toBeInTheDocument()
    expect(screen.getByTestId('scrollable-table-top-bar')).toBeInTheDocument()
    expect(screen.getByTestId('scrollable-table-bottom-bar')).toBeInTheDocument()
  })

  it('la barra de arriba es inaccesible por lectores de pantalla (aria-hidden)', () => {
    render(
      <ScrollableTable>
        <span>x</span>
      </ScrollableTable>,
    )

    expect(screen.getByTestId('scrollable-table-top-bar')).toHaveAttribute('aria-hidden', 'true')
  })

  it('desplazar la barra de abajo mueve la de arriba a la misma posición', () => {
    render(
      <ScrollableTable>
        <span>x</span>
      </ScrollableTable>,
    )
    const top = screen.getByTestId('scrollable-table-top-bar')
    const bottom = screen.getByTestId('scrollable-table-bottom-bar')

    Object.defineProperty(bottom, 'scrollLeft', { value: 120, writable: true })
    fireEvent.scroll(bottom)

    expect(top.scrollLeft).toBe(120)
  })

  it('desplazar la barra de arriba mueve la de abajo a la misma posición', () => {
    render(
      <ScrollableTable>
        <span>x</span>
      </ScrollableTable>,
    )
    const top = screen.getByTestId('scrollable-table-top-bar')
    const bottom = screen.getByTestId('scrollable-table-bottom-bar')

    Object.defineProperty(top, 'scrollLeft', { value: 80, writable: true })
    fireEvent.scroll(top)

    expect(bottom.scrollLeft).toBe(80)
  })
})
