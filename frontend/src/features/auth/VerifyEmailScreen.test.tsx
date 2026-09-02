// Tests de comportamiento de `VerifyEmailScreen` (Bloque 4, PROMPT-AUTOFACTU-AUTH-COMPLETO): auto-
// confirma el token al montar, sin acción del usuario.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import type { AppliedTheme } from '../tenancy/theme'
import { VerifyEmailScreen } from './VerifyEmailScreen'

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

function renderScreen(path = '/registro/confirmar?token=tok-123') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <VerifyEmailScreen theme={THEME} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  postMock.mockReset()
})

describe('VerifyEmailScreen (Bloque 4)', () => {
  it('sin token en la URL muestra directamente el aviso de enlace no válido, sin llamar al backend', () => {
    renderScreen('/registro/confirmar')

    expect(screen.getByText(/no es válido o ha caducado/)).toBeInTheDocument()
    expect(postMock).not.toHaveBeenCalled()
  })

  it('con token, confirma automáticamente y muestra el éxito', async () => {
    postMock.mockResolvedValue({ data: { status: 'verified' }, error: undefined })
    renderScreen()

    expect(await screen.findByText(/Tu email ha sido confirmado/)).toBeInTheDocument()
    expect(postMock).toHaveBeenCalledWith('/api/v1/auth/register/verify-email', {
      body: { token: 'tok-123' },
    })
  })

  it('un 401 (token consumido/caducado/de otro tenant) muestra el aviso, sin distinguir el motivo', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Invalid or expired token' },
      response: { status: 401 },
    })
    renderScreen()

    expect(await screen.findByText(/no es válido o ha caducado/)).toBeInTheDocument()
  })

  it('un 503 (Redis caído) muestra que el servicio no está disponible', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Service unavailable' },
      response: { status: 503 },
    })
    renderScreen()

    expect(await screen.findByText(/no está disponible/)).toBeInTheDocument()
  })
})
