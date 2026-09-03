// Tests de comportamiento de `RegisterScreen` (Bloque 4, PROMPT-AUTOFACTU-AUTH-COMPLETO).
// `api.POST` mockeado: la pantalla no sabe nada de sesión ni de router más allá de sus propios
// enlaces (envuelta en MemoryRouter porque usa <Link>).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import type { AppliedTheme } from '../tenancy/theme'
import { RegisterScreen } from './RegisterScreen'

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
      <RegisterScreen theme={THEME} />
    </MemoryRouter>,
  )
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Email'), 'nuevo@correo.es')
  await user.type(screen.getByLabelText('Razón Social'), 'Empresa Nueva SL')
  await user.type(screen.getByLabelText('CIF'), 'B12345674')
  await user.type(screen.getByLabelText('Contraseña'), 'UnaClaveSegura1!')
  await user.type(screen.getByLabelText('Repite la contraseña'), 'UnaClaveSegura1!')
  await user.click(screen.getByRole('checkbox'))
}

beforeEach(() => {
  postMock.mockReset()
})

describe('RegisterScreen (Bloque 4)', () => {
  it('envía el alta con legal_consent y muestra el mensaje genérico de éxito', async () => {
    postMock.mockResolvedValue({ data: { status: 'pending_approval' }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Solicitar acceso' }))

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith('/api/v1/register', {
        body: {
          email: 'nuevo@correo.es',
          company_name: 'Empresa Nueva SL',
          cif: 'B12345674',
          password: 'UnaClaveSegura1!',
          legal_consent: true,
        },
      }),
    )
    expect(await screen.findByText(/Hemos enviado un correo/)).toBeInTheDocument()
  })

  it('sin aceptar las condiciones, el navegador bloquea el envío (checkbox required)', async () => {
    const user = userEvent.setup()
    renderScreen()
    await user.type(screen.getByLabelText('Email'), 'nuevo@correo.es')
    await user.type(screen.getByLabelText('Razón Social'), 'Empresa Nueva SL')
    await user.type(screen.getByLabelText('CIF'), 'B12345674')
    await user.type(screen.getByLabelText('Contraseña'), 'UnaClaveSegura1!')
    await user.type(screen.getByLabelText('Repite la contraseña'), 'UnaClaveSegura1!')

    expect(screen.getByRole('checkbox')).toBeRequired()
  })

  it('el consentimiento enlaza a los términos del servicio y a la política de privacidad', () => {
    renderScreen()

    expect(screen.getByRole('link', { name: 'términos del servicio' })).toHaveAttribute(
      'href',
      '/terminos',
    )
    expect(screen.getByRole('link', { name: 'política de privacidad' })).toHaveAttribute(
      'href',
      '/privacidad',
    )
  })

  it('contraseñas distintas no llaman al backend y muestran el error', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.type(screen.getByLabelText('Email'), 'nuevo@correo.es')
    await user.type(screen.getByLabelText('Razón Social'), 'Empresa Nueva SL')
    await user.type(screen.getByLabelText('CIF'), 'B12345674')
    await user.type(screen.getByLabelText('Contraseña'), 'UnaClaveSegura1!')
    await user.type(screen.getByLabelText('Repite la contraseña'), 'Otra')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Solicitar acceso' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Las contraseñas no coinciden.')
    expect(postMock).not.toHaveBeenCalled()
  })

  it('un 422 del backend (p. ej. CIF inválido) muestra el detalle del error', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'invalid check digit' },
      response: { status: 422 },
    })
    const user = userEvent.setup()
    renderScreen()

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Solicitar acceso' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('invalid check digit')
  })

  it('un 429 muestra el mensaje de límite de solicitudes', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Too many registrations' },
      response: { status: 429 },
    })
    const user = userEvent.setup()
    renderScreen()

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Solicitar acceso' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Demasiadas solicitudes/)
  })

  it('un 404 (dominio sin gestoría, p. ej. la consola de plataforma) explica por qué, sin enseñar "Not found"', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'Not found' },
      response: { status: 404 },
    })
    const user = userEvent.setup()
    renderScreen()

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Solicitar acceso' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/dirección de tu asesoría/)
    expect(alert).not.toHaveTextContent('Not found')
  })
})
