// Tests de comportamiento de `LoginScreen` (S4.9, C1-C3). Aislado de `SessionProvider`: se
// mockea `useSession` directamente, la pantalla solo debe orquestar el formulario y mostrar el
// resultado de `login()`, sin saber nada de rutas.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

beforeEach(() => {
  useSessionMock.mockReset()
})

describe('LoginScreen (S4.9)', () => {
  it('C1: envía email + contraseña a login()', async () => {
    const login = vi.fn().mockResolvedValue({ outcome: 'ok' })
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login, logout: vi.fn() })
    const user = userEvent.setup()
    render(<LoginScreen theme={THEME} />)

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.type(screen.getByLabelText('Contraseña'), 's3cret')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    await waitFor(() => expect(login).toHaveBeenCalledWith('ana@ilex.es', 's3cret', undefined))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('C2: credenciales incorrectas muestran un error legible, sin perder lo escrito', async () => {
    const login = vi.fn().mockResolvedValue({ outcome: 'error', message: 'Invalid credentials' })
    useSessionMock.mockReturnValue({ status: 'unauthenticated', user: null, login, logout: vi.fn() })
    const user = userEvent.setup()
    render(<LoginScreen theme={THEME} />)

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
    render(<LoginScreen theme={THEME} />)

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
})
