// Tests de comportamiento de `RegistrationDecisionScreen` (2026-09-03, a petición de Julio):
// decidir un alta desde el enlace del email, sin iniciar sesión.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import type { AppliedTheme } from '../tenancy/theme'
import { RegistrationDecisionScreen } from './RegistrationDecisionScreen'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock

const THEME: AppliedTheme = {
  appName: 'Autoken Facturas',
  colorPrimary: '#059669',
  colorSecondary: '#0f172a',
  logoUrl: null,
  faviconUrl: null,
}

function renderScreen(path = '/decidir-alta?token=tok-123') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RegistrationDecisionScreen theme={THEME} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
})

describe('RegistrationDecisionScreen', () => {
  it('sin token en la URL muestra el aviso de enlace no válido, sin llamar al backend', () => {
    renderScreen('/decidir-alta')

    expect(screen.getByText('Este enlace no es válido.')).toBeInTheDocument()
    expect(getMock).not.toHaveBeenCalled()
  })

  it('carga la solicitud y muestra a quién aprobar/rechazar', async () => {
    getMock.mockResolvedValue({
      data: { email: 'nuevo@correo.es', company: 'Empresa Nueva SL', already_decided: false },
      error: undefined,
    })
    renderScreen()

    expect(getMock).toHaveBeenCalledWith('/api/v1/auth/registrations/decision', {
      params: { query: { token: 'tok-123' } },
    })
    expect(await screen.findByText(/nuevo@correo.es/)).toBeInTheDocument()
    expect(screen.getByText(/Empresa Nueva SL/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Aprobar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rechazar' })).toBeInTheDocument()
  })

  it('aprobar llama al backend con decision=approve y muestra el éxito', async () => {
    getMock.mockResolvedValue({
      data: { email: 'nuevo@correo.es', company: 'Empresa Nueva SL', already_decided: false },
      error: undefined,
    })
    postMock.mockResolvedValue({ data: { status: 'approved' }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    await user.click(await screen.findByRole('button', { name: 'Aprobar' }))

    expect(postMock).toHaveBeenCalledWith('/api/v1/auth/registrations/decision', {
      body: { token: 'tok-123', decision: 'approve' },
    })
    expect(await screen.findByText(/Alta aprobada/)).toBeInTheDocument()
  })

  it('rechazar llama al backend con decision=reject y muestra el resultado', async () => {
    getMock.mockResolvedValue({
      data: { email: 'nuevo@correo.es', company: null, already_decided: false },
      error: undefined,
    })
    postMock.mockResolvedValue({ data: { status: 'rejected' }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    await user.click(await screen.findByRole('button', { name: 'Rechazar' }))

    expect(postMock).toHaveBeenCalledWith('/api/v1/auth/registrations/decision', {
      body: { token: 'tok-123', decision: 'reject' },
    })
    expect(await screen.findByText(/Alta rechazada/)).toBeInTheDocument()
  })

  it('si ya se decidió (otro admin, o el panel), lo dice y no ofrece botones', async () => {
    getMock.mockResolvedValue({
      data: { email: 'nuevo@correo.es', company: null, already_decided: true },
      error: undefined,
    })
    renderScreen()

    expect(await screen.findByText(/ya fue decidida/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Aprobar' })).not.toBeInTheDocument()
  })

  it('un 401 (token inválido/caducado) lo dice, sin distinguir el motivo', async () => {
    getMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Invalid or expired token' },
      response: { status: 401 },
    })
    renderScreen()

    expect(await screen.findByText(/ya no es válido o ha caducado/)).toBeInTheDocument()
  })

  it('un 404 (dominio sin gestoría) explica por qué', async () => {
    getMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Not found' },
      response: { status: 404 },
    })
    renderScreen()

    expect(await screen.findByText(/dirección de tu asesoría/)).toBeInTheDocument()
  })
})
