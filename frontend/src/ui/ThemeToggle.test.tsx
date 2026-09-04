// Test mínimo del toggle de tema (Bloque 1): verifica el estado activo y que la elección
// escribe data-theme en <html>. jsdom no aplica CSS, así que se comprueba el atributo y ARIA.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'

import { ThemeToggle } from './ThemeToggle'

beforeEach(() => {
  document.documentElement.removeAttribute('data-theme')
  window.localStorage.clear()
})

describe('ThemeToggle', () => {
  it('ofrece solo claro y oscuro, sin la opción "sistema"', () => {
    render(<ThemeToggle />)

    const group = screen.getByRole('radiogroup', { name: /tema de la aplicación/i })
    expect(group).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /tema claro/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /tema oscuro/i })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /tema sistema/i })).not.toBeInTheDocument()
  })

  it('sin elección previa, no fuerza data-theme (sigue el tema del sistema)', () => {
    render(<ThemeToggle />)

    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('al elegir oscuro escribe data-theme="dark" en el documento y lo persiste', async () => {
    render(<ThemeToggle />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: /tema oscuro/i }))

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(window.localStorage.getItem('autofactu-theme')).toBe('dark')
    expect(screen.getByRole('radio', { name: /tema oscuro/i })).toHaveAttribute('aria-checked', 'true')
  })

  it('al elegir claro escribe data-theme="light" en el documento y lo persiste', async () => {
    render(<ThemeToggle />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: /tema claro/i }))

    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(window.localStorage.getItem('autofactu-theme')).toBe('light')
    expect(screen.getByRole('radio', { name: /tema claro/i })).toHaveAttribute('aria-checked', 'true')
  })
})
