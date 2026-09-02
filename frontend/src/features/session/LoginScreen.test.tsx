// Tests de comportamiento de `LoginScreen` (S4.9, C1-C3). Aislado de `SessionProvider`: se
// mockea `useSession` directamente, la pantalla solo debe orquestar el formulario y mostrar el
// resultado de `login()`, sin saber nada de rutas. Envuelto en `MemoryRouter` (Bloque 4): los dos
// enlaces al pie (recuperar contraseña, solicitar acceso) usan `<Link>`, que exige un Router.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AppliedTheme } from '../tenancy/theme'
import { LoginScreen } from './LoginScreen'
import { useSession } from './SessionProvider'

vi.mock('./SessionProvider', () => ({
  useSession: vi.fn(),
}))

const useSessionMock = vi.mocked(useSession)
const THEME: AppliedTheme = {
  appName: 'Autoken Facturas',
  colorPrimary: '#059669',
  colorSecondary: '#0f172a',
  logoUrl: null,
  faviconUrl: null,
}

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginScreen theme={THEME} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useSessionMock.mockReset()
})

describe('LoginScreen (S4.9)', () => {
  it('usa el tono azul de marca en el shell y un panel con acabado glass', () => {
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login: vi.fn(), logout: vi.fn() })
    renderLogin()

    expect(screen.getByRole('main')).toHaveClass('tn-login-shell')
    expect(screen.getByRole('form', { name: 'Inicio de sesión' })).toHaveClass('tn-login-card')
  })

  it('C1: envía email + contraseña a login()', async () => {
    const login = vi.fn().mockResolvedValue({ outcome: 'ok' })
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login, logout: vi.fn() })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.type(screen.getByLabelText('Contraseña'), 's3cret')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => expect(login).toHaveBeenCalledWith('ana@ilex.es', 's3cret', undefined))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('C4: permite mostrar y volver a ocultar la contraseña sin cambiar su valor', async () => {
    const login = vi.fn().mockResolvedValue({ outcome: 'ok' })
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login, logout: vi.fn() })
    const user = userEvent.setup()
    renderLogin()

    const password = screen.getByLabelText('Contraseña')
    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.type(password, 's3cret')
    expect(password).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('button', { name: 'Mostrar contraseña' }))
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'text')
    expect(screen.getByLabelText('Contraseña')).toHaveValue('s3cret')

    await user.click(screen.getByRole('button', { name: 'Ocultar contraseña' }))
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'password')
    expect(screen.getByLabelText('Contraseña')).toHaveValue('s3cret')

    await user.click(screen.getByRole('button', { name: 'Entrar' }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('ana@ilex.es', 's3cret', undefined))
  })

  it('C2: credenciales incorrectas muestran un error legible, sin perder lo escrito', async () => {
    const login = vi.fn().mockResolvedValue({ outcome: 'error', message: 'Invalid credentials' })
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login, logout: vi.fn() })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.type(screen.getByLabelText('Contraseña'), 'mala')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials')
    expect(screen.getByLabelText('Email')).toHaveValue('ana@ilex.es')
  })

  it('C3: totp_required muestra el campo de código y lo incluye en el siguiente envío', async () => {
    const login = vi
      .fn()
      .mockResolvedValueOnce({ outcome: 'totp_required' })
      .mockResolvedValueOnce({ outcome: 'ok' })
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login, logout: vi.fn() })
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.type(screen.getByLabelText('Contraseña'), 's3cret')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    const totpField = await screen.findByLabelText('Código de verificación')
    await user.type(totpField, '123456')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() =>
      expect(login).toHaveBeenLastCalledWith('ana@ilex.es', 's3cret', '123456'),
    )
  })

  it('Bloque 4: enlaza a recuperar contraseña y a solicitar acceso', () => {
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login: vi.fn(), logout: vi.fn() })
    renderLogin()

    expect(screen.getByRole('link', { name: '¿No recuerdas tu contraseña?' })).toHaveAttribute(
      'href',
      '/recuperar',
    )
    expect(
      screen.getByRole('link', { name: '¿No tienes cuenta? Solicita acceso' }),
    ).toHaveAttribute('href', '/registro')
  })
})
