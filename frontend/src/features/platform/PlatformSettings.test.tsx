// Tests de comportamiento del panel admin-tech de producción y laboratorio (R-046).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { PlatformSettings } from './PlatformSettings'

vi.mock('../../api/client', () => ({ api: { GET: vi.fn(), PUT: vi.fn() } }))
vi.mock('../session/SessionProvider', () => ({ useSession: vi.fn() }))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const putMock = api.PUT as unknown as AsyncMock
const useSessionMock = vi.mocked(useSession)

const user = {
  id: 'p1', email: 'julio@autoken.es', role: 'platform_admin' as const,
  tenant: null, company: null, is_admin_tech: true,
}
const policy = {
  version: 7, primary_engine: 'gemini-3.5-flash', primary_model: 'gemini-3.5-flash',
  fallback_enabled: true, fallback_engine: 'mistral-ocr-4', fallback_model: 'mistral-ocr-4-0',
  consensus_mode: 'per_field' as const,
}
const lab = {
  lab_visible: false, auto_benchmark_enabled: true,
  benchmark_engines: ['tesseract'], benchmark_variants: ['original', 'clahe'],
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><PlatformSettings /></QueryClientProvider>)
}

beforeEach(() => {
  getMock.mockReset()
  putMock.mockReset()
})

describe('PlatformSettings (R-046)', () => {
  it('un platform_admin sin el flag ve sin acceso y no realiza peticiones', () => {
    useSessionMock.mockReturnValue({ status: 'authenticated', user: { ...user, is_admin_tech: false }, login: vi.fn(), logout: vi.fn() })

    renderScreen()

    expect(screen.getByRole('alert')).toHaveTextContent(/no tienes acceso/i)
    expect(getMock).not.toHaveBeenCalled()
  })

  it('muestra por separado la política fija de producción y el laboratorio', async () => {
    useSessionMock.mockReturnValue({ status: 'authenticated', user, login: vi.fn(), logout: vi.fn() })
    getMock.mockResolvedValueOnce({ data: policy, error: undefined })
    getMock.mockResolvedValueOnce({ data: lab, error: undefined })

    renderScreen()

    expect(await screen.findByText(/Producción OCR/i)).toBeInTheDocument()
    expect(screen.getByText(/gemini-3.5-flash \/ gemini-3.5-flash/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Laboratorio' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
  })

  it('desactiva el benchmark automático con una actualización confirmada por backend', async () => {
    useSessionMock.mockReturnValue({ status: 'authenticated', user, login: vi.fn(), logout: vi.fn() })
    getMock.mockResolvedValueOnce({ data: policy, error: undefined })
    getMock.mockResolvedValueOnce({ data: lab, error: undefined })
    getMock.mockResolvedValueOnce({ data: { ...lab, auto_benchmark_enabled: false }, error: undefined })
    putMock.mockResolvedValueOnce({ data: { ...lab, auto_benchmark_enabled: false }, error: undefined })

    renderScreen()
    await screen.findByRole('button', { name: /desactivar laboratorio automático/i })
    await userEvent.setup().click(screen.getByRole('button', { name: /desactivar laboratorio automático/i }))

    await waitFor(() => expect(putMock).toHaveBeenCalledWith('/api/v1/platform/ocr-lab/settings', {
      body: { ...lab, auto_benchmark_enabled: false },
    }))
  })
})
