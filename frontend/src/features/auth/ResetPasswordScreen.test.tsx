// Tests de comportamiento de `ResetPasswordScreen` (Bloque 4, PROMPT-AUTOFACTU-AUTH-COMPLETO).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import type { AppliedTheme } from '../tenancy/theme'
import { ResetPasswordScreen } from './ResetPasswordScreen'

vi.mock('../../api/client', () => ({
  api: { POST: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const postMock = api.POST as unknown as AsyncMock

const THEME: AppliedTheme = {
  appName: 'Autoken Facturas',
  colorPrimary: '#059669',
  colorSecondary: '#0f172a',
  logoUrl: null,
  faviconUrl: null,
}

function renderScreen(path = '/restablecer?token=tok-123') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ResetPasswordScreen theme={THEME} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  postMock.mockReset()
})

describe('ResetPasswordScreen (Bloque 4)', () => {
  it('sin token en la URL muestra el aviso de enlace no válido, sin formulario', () => {
    renderScreen('/restablecer')

    expect(screen.getByText('Enlace no válido')).toBeInTheDocument()
    expect(screen.queryByLabelText('Contraseña nueva')).not.toBeInTheDocument()
  })

  it('envía el token + la contraseña nueva y muestra el éxito', async () => {
    postMock.mockResolvedValue({ data: { status: 'reset' }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Contraseña nueva'), 'UnaClaveSegura1!')
    await user.type(screen.getByLabelText('Repite la contraseña'), 'UnaClaveSegura1!')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith('/api/v1/auth/password/reset', {
        body: { token: 'tok-123', password: 'UnaClaveSegura1!' },
      }),
    )
    expect(await screen.findByText(/Tu contraseña se ha actualizado/)).toBeInTheDocument()
  })

  it('contraseñas distintas no llaman al backend', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Contraseña nueva'), 'UnaClaveSegura1!')
    await user.type(screen.getByLabelText('Repite la contraseña'), 'Otra')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Las contraseñas no coinciden.')
    expect(postMock).not.toHaveBeenCalled()
  })

  it('un 401 (token inválido/caducado) no distingue el motivo', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Invalid or expired token' },
      response: { status: 401 },
    })
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Contraseña nueva'), 'UnaClaveSegura1!')
    await user.type(screen.getByLabelText('Repite la contraseña'), 'UnaClaveSegura1!')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no es válido o ha caducado/)
  })

  it('un 422 (contraseña floja) muestra el mensaje de política', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'password does not meet policy' },
      response: { status: 422 },
    })
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Contraseña nueva'), 'floja')
    await user.type(screen.getByLabelText('Repite la contraseña'), 'floja')
    await user.click(screen.getByRole('button', { name: 'Guardar contraseña' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no cumple los requisitos/)
  })
})
