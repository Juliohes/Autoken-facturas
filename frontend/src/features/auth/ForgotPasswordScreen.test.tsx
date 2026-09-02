// Tests de comportamiento de `ForgotPasswordScreen` (Bloque 4, PROMPT-AUTOFACTU-AUTH-COMPLETO).
// Respuesta siempre genérica en éxito (anti-enumeración): el mismo mensaje exista o no la cuenta.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import type { AppliedTheme } from '../tenancy/theme'
import { ForgotPasswordScreen } from './ForgotPasswordScreen'

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

function renderScreen() {
  return render(
    <MemoryRouter>
      <ForgotPasswordScreen theme={THEME} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  postMock.mockReset()
})

describe('ForgotPasswordScreen (Bloque 4)', () => {
  it('envía el email y muestra el mensaje genérico, exista o no la cuenta', async () => {
    postMock.mockResolvedValue({ data: { status: 'requested' }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.click(screen.getByRole('button', { name: 'Enviar enlace' }))

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith('/api/v1/auth/password/forgot', {
        body: { email: 'ana@ilex.es' },
      }),
    )
    expect(await screen.findByText(/Si existe una cuenta con ese email/)).toBeInTheDocument()
  })

  it('un 429 muestra el aviso de demasiadas solicitudes, sin revelar nada sobre la cuenta', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Too many attempts' },
      response: { status: 429 },
    })
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.click(screen.getByRole('button', { name: 'Enviar enlace' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Demasiadas solicitudes/)
  })

  it('un 503 (Redis caído) muestra que el servicio no está disponible', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Service unavailable' },
      response: { status: 503 },
    })
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Email'), 'ana@ilex.es')
    await user.click(screen.getByRole('button', { name: 'Enviar enlace' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no está disponible/)
  })
})
