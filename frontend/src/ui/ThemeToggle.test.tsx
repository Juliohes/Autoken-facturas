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
  it('ofrece claro, oscuro y sistema, con "sistema" como modo por defecto', () => {
    render(<ThemeToggle />)

    const group = screen.getByRole('radiogroup', { name: /tema de la aplicación/i })
    expect(screen.getByRole('radio', { name: /tema claro/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /tema oscuro/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /tema sistema/i })).toBeInTheDocument()
    expect(group).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /tema sistema/i })).toHaveAttribute('aria-checked', 'true')
  })

  it('al elegir oscuro escribe data-theme="dark" en el documento y lo persiste', async () => {
    render(<ThemeToggle />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: /tema oscuro/i }))

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(window.localStorage.getItem('autofactu-theme')).toBe('dark')
  })

  it('al elegir claro escribe data-theme="light" y al volver a sistema retira el atributo', async () => {
    render(<ThemeToggle />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: /tema claro/i }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    await user.click(screen.getByRole('radio', { name: /tema sistema/i }))
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
})
