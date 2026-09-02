// Tests de comportamiento de `ActivateScreen` (Bloque 4, PROMPT-AUTOFACTU-AUTH-COMPLETO): dos
// pasos, contraseña -> QR/TOTP.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import type { AppliedTheme } from '../tenancy/theme'
import { ActivateScreen } from './ActivateScreen'

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

const OTPAUTH_URI = 'otpauth://totp/Autofactu:ana@ilex.es?secret=JBSWY3DPEHPK3PXP&issuer=Autofactu'

function renderScreen(path = '/activar?token=tok-123') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ActivateScreen theme={THEME} />
    </MemoryRouter>,
  )
}

async function setPassword(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Contraseña'), 'UnaClaveSegura1!')
  await user.type(screen.getByLabelText('Repite la contraseña'), 'UnaClaveSegura1!')
  await user.click(screen.getByRole('button', { name: 'Continuar' }))
}

beforeEach(() => {
  postMock.mockReset()
})

describe('ActivateScreen (Bloque 4)', () => {
  it('sin token en la URL muestra el aviso de enlace no válido', () => {
    renderScreen('/activar')
    expect(screen.getByText('Enlace no válido')).toBeInTheDocument()
  })

  it('tras fijar la contraseña, muestra el QR y el secreto para entrada manual', async () => {
    postMock.mockResolvedValueOnce({ data: { otpauth_uri: OTPAUTH_URI }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    await setPassword(user)

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith('/api/v1/auth/activate', {
        body: { token: 'tok-123', password: 'UnaClaveSegura1!' },
      }),
    )
    expect(await screen.findByRole('img', { name: 'Código QR de activación' })).toBeInTheDocument()
    expect(screen.getByText('JBSWY3DPEHPK3PXP')).toBeInTheDocument()
  })

  it('confirma el TOTP y muestra la cuenta activada', async () => {
    postMock
      .mockResolvedValueOnce({ data: { otpauth_uri: OTPAUTH_URI }, error: undefined })
      .mockResolvedValueOnce({ data: { status: 'active' }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    await setPassword(user)
    await screen.findByLabelText('Código de verificación')
    await user.type(screen.getByLabelText('Código de verificación'), '123456')
    await user.click(screen.getByRole('button', { name: 'Activar cuenta' }))

    await waitFor(() =>
      expect(postMock).toHaveBeenLastCalledWith('/api/v1/auth/activate/confirm', {
        body: { token: 'tok-123', totp_code: '123456' },
      }),
    )
    expect(await screen.findByText('Cuenta activada')).toBeInTheDocument()
  })

  it('un código incorrecto muestra el error y deja reintentar sin perder el QR', async () => {
    postMock
      .mockResolvedValueOnce({ data: { otpauth_uri: OTPAUTH_URI }, error: undefined })
      .mockResolvedValueOnce({ data: undefined, error: { detail: 'invalid' }, response: { status: 400 } })
    const user = userEvent.setup()
    renderScreen()

    await setPassword(user)
    await screen.findByLabelText('Código de verificación')
    await user.type(screen.getByLabelText('Código de verificación'), '000000')
    await user.click(screen.getByRole('button', { name: 'Activar cuenta' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Código incorrecto/)
    expect(screen.getByRole('img', { name: 'Código QR de activación' })).toBeInTheDocument()
  })

  it('un 401 al fijar la contraseña (token inválido/caducado) muestra el aviso', async () => {
    postMock.mockResolvedValueOnce({
      data: undefined,
      error: { detail: 'Invalid activation token' },
      response: { status: 401 },
    })
    const user = userEvent.setup()
    renderScreen()

    await setPassword(user)

    expect(await screen.findByRole('alert')).toHaveTextContent(/no es válido o ha caducado/)
  })
})
