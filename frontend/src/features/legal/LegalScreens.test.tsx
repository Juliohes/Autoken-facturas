// Tests de comportamiento de las páginas legales (a petición de Julio, 2026-09-03): existen, se
// pueden leer y enlazan entre sí y de vuelta al registro/login. No comprueban el contenido jurídico
// en sí (eso lo revisa un abogado), solo que la pantalla renderiza y navega correctamente.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import type { AppliedTheme } from '../tenancy/theme'
import { PrivacidadScreen } from './PrivacidadScreen'
import { TerminosScreen } from './TerminosScreen'

const THEME: AppliedTheme = {
  appName: 'Autoken Facturas',
  colorPrimary: '#059669',
  colorSecondary: '#0f172a',
  logoUrl: null,
  faviconUrl: null,
}

describe('Páginas legales', () => {
  it('TerminosScreen: muestra el título, el aviso de borrador y enlaza a privacidad/registro/login', () => {
    render(
      <MemoryRouter>
        <TerminosScreen theme={THEME} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Términos del servicio' })).toBeInTheDocument()
    expect(screen.getByText(/Nota para Julio/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Política de Privacidad' })).toHaveAttribute(
      'href',
      '/privacidad',
    )
    expect(screen.getByRole('link', { name: 'Volver al registro' })).toHaveAttribute(
      'href',
      '/registro',
    )
    expect(screen.getByRole('link', { name: 'Volver a iniciar sesión' })).toHaveAttribute(
      'href',
      '/login',
    )
  })

  it('PrivacidadScreen: muestra el título, el aviso de borrador y enlaza a términos', () => {
    render(
      <MemoryRouter>
        <PrivacidadScreen theme={THEME} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Política de privacidad' })).toBeInTheDocument()
    expect(screen.getByText(/Nota para Julio/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Términos del servicio' })).toHaveAttribute(
      'href',
      '/terminos',
    )
  })
})
