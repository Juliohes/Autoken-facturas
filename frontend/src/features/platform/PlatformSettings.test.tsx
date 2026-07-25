// Tests de comportamiento de `PlatformSettings` (S4.10, C9/C10). Cliente de API mockeado; sesión
// mockeada para controlar `user.is_admin_tech`.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { PlatformSettings } from './PlatformSettings'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), PUT: vi.fn() },
}))
vi.mock('../session/SessionProvider', () => ({
  useSession: vi.fn(),
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const putMock = api.PUT as unknown as AsyncMock
const useSessionMock = vi.mocked(useSession)

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PlatformSettings />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  putMock.mockReset()
})

describe('PlatformSettings (S4.10)', () => {
  it('C9: un platform_admin sin el flag ve "sin acceso", nunca el interruptor', () => {
    useSessionMock.mockReturnValue({
      status: 'authenticated',
      user: {
        id: 'p1',
        email: 'alberto@autoken.es',
        role: 'platform_admin',
        tenant: null,
        company: null,
        is_admin_tech: false,
      },
      login: vi.fn(),
      logout: vi.fn(),
    })

    renderScreen()

    expect(screen.getByRole('alert')).toHaveTextContent(/no tienes acceso/i)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('admin-tech ve el estado actual del interruptor', async () => {
    useSessionMock.mockReturnValue({
      status: 'authenticated',
      user: {
        id: 'p1',
        email: 'julio@autoken.es',
        role: 'platform_admin',
        tenant: null,
        company: null,
        is_admin_tech: true,
      },
      login: vi.fn(),
      logout: vi.fn(),
    })
    getMock.mockResolvedValueOnce({ data: { ocr_experiment_enabled: false }, error: undefined })

    renderScreen()

    const checkbox = await screen.findByRole('checkbox')
    expect(checkbox).not.toBeChecked()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('C10: encender el interruptor llama a PUT y refleja el estado ya confirmado por el backend', async () => {
    useSessionMock.mockReturnValue({
      status: 'authenticated',
      user: {
        id: 'p1',
        email: 'julio@autoken.es',
        role: 'platform_admin',
        tenant: null,
        company: null,
        is_admin_tech: true,
      },
      login: vi.fn(),
      logout: vi.fn(),
    })
    getMock.mockResolvedValueOnce({ data: { ocr_experiment_enabled: false }, error: undefined })
    getMock.mockResolvedValueOnce({ data: { ocr_experiment_enabled: true }, error: undefined })
    putMock.mockResolvedValueOnce({ data: { ocr_experiment_enabled: true }, error: undefined })

    renderScreen()
    const user = userEvent.setup()
    const checkbox = await screen.findByRole('checkbox')
    expect(checkbox).not.toBeChecked()

    await user.click(checkbox)

    await waitFor(() =>
      expect(putMock).toHaveBeenCalledWith('/api/v1/platform/settings', {
        body: { ocr_experiment_enabled: true },
      }),
    )
    await waitFor(() => expect(screen.getByRole('checkbox')).toBeChecked())
  })
})
