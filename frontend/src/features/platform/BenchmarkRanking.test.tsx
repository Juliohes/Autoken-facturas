// Tests de comportamiento de `BenchmarkRanking` (S6.7 Área C/D, spec
// docs/specs/S6.7-benchmark-real-motor-variante.md, C10-C11/C13/C16-C20). Cliente de API mockeado;
// sesión mockeada para controlar `user.is_admin_tech`, mismo patrón que `OcrRanking.test.tsx`.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { BenchmarkRanking } from './BenchmarkRanking'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))
vi.mock('../session/SessionProvider', () => ({
  useSession: vi.fn(),
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock
const useSessionMock = vi.mocked(useSession)

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <BenchmarkRanking />
    </QueryClientProvider>,
  )
}

function asUser(isAdminTech: boolean) {
  useSessionMock.mockReturnValue({
    status: 'authenticated',
    user: {
      id: 'p1',
      email: 'julio@autoken.es',
      role: 'platform_admin',
      tenant: null,
      company: null,
      is_admin_tech: isAdminTech,
    },
    login: vi.fn(),
    logout: vi.fn(),
  })
}

const RANKING = {
  by_field_group: [
    { field_group: 'CIF/NIF', variant: 'original', engine: 'gemini-3-flash', aciertos: 9, comparables: 10, ratio: 0.9 },
    { field_group: 'CIF/NIF', variant: 'original', engine: 'mistral-ocr-4', aciertos: 3, comparables: 10, ratio: 0.3 },
    { field_group: 'Fecha', variant: 'clahe', engine: 'gemini-3-pro', aciertos: 10, comparables: 10, ratio: 1.0 },
  ],
  by_combination: [
    { variant: 'original', engine: 'gemini-3-flash', executions: 10, errors: 0, aciertos: 9, comparables: 10, avg_duration_ms: 1200 },
    { variant: 'clahe', engine: 'gemini-3-pro', executions: 10, errors: 1, aciertos: 10, comparables: 10, avg_duration_ms: 900 },
  ],
}

const STATUS_IDLE = { running: false, batch: null }
const STATUS_RUNNING = {
  running: true,
  batch: { status: 'running', total: 10, completed: 3, failed_count: 0 },
}
const STATUS_DONE = {
  running: false,
  batch: { status: 'done', total: 10, completed: 10, failed_count: 1 },
}

function mockRoutes(overrides: {
  ranking?: unknown
  status?: unknown
}) {
  getMock.mockImplementation((path: string) => {
    if (path.includes('/benchmark/ranking')) {
      return Promise.resolve({ data: overrides.ranking ?? RANKING, error: undefined })
    }
    if (path.includes('/benchmark/backfill/status')) {
      return Promise.resolve({ data: overrides.status ?? STATUS_IDLE, error: undefined })
    }
    return Promise.resolve({ data: {}, error: undefined })
  })
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('BenchmarkRanking (S6.7)', () => {
  it('sin el flag admin-tech ve "sin acceso", nunca la pantalla', () => {
    asUser(false)

    renderScreen()

    expect(screen.getByRole('alert')).toHaveTextContent(/no tienes acceso/i)
    expect(getMock).not.toHaveBeenCalled()
  })

  it('C18: muestra la mejor combinación por grupo de campo, no un único ganador global', async () => {
    asUser(true)
    mockRoutes({})
    renderScreen()

    await screen.findByText('CIF/NIF')
    const cifSection = screen.getByText('CIF/NIF').closest('section') as HTMLElement
    expect(within(cifSection).getByText(/gemini-3-flash/)).toBeInTheDocument()
    const fechaSection = screen.getByText('Fecha').closest('section') as HTMLElement
    expect(within(fechaSection).getByText(/gemini-3-pro/)).toBeInTheDocument()
  })

  it('C20: la tabla de combinaciones muestra ejecuciones y errores', async () => {
    asUser(true)
    mockRoutes({})
    renderScreen()

    const row = (await screen.findByText('gemini-3-pro')).closest('tr') as HTMLElement
    expect(within(row).getByText('10')).toBeInTheDocument() // ejecuciones
    expect(within(row).getByText('1')).toBeInTheDocument() // errores
  })

  it('C10: pulsar el botón encola el lote y pasa a "Procesando…"', async () => {
    asUser(true)
    mockRoutes({})
    postMock.mockResolvedValue({ data: { iniciado: true, total: 10 }, error: undefined })
    const user = userEvent.setup()
    renderScreen()

    const button = await screen.findByRole('button', { name: /Últimas/i })
    await user.click(button)

    expect(postMock).toHaveBeenCalledWith(
      '/api/v1/platform/benchmark/backfill',
      expect.objectContaining({ body: expect.objectContaining({ limit: expect.any(Number) }) }),
    )
    await screen.findByText(/procesando/i)
  })

  it('C16: al entrar con un lote ya corriendo, se engancha al progreso sin mostrar el botón inicial', async () => {
    asUser(true)
    mockRoutes({ status: STATUS_RUNNING })
    renderScreen()

    await screen.findByText(/procesando.*3.*10/i)
    expect(screen.queryByRole('button', { name: /Últimas/i })).not.toBeInTheDocument()
  })

  it('C11: si el lote ya está corriendo, el POST devuelve 409 y el panel se engancha al progreso sin tratarlo como error', async () => {
    asUser(true)
    mockRoutes({})
    postMock.mockResolvedValue({
      data: undefined,
      error: { batch: STATUS_RUNNING.batch },
      response: { status: 409 },
    })
    const user = userEvent.setup()
    renderScreen()

    const button = await screen.findByRole('button', { name: /Últimas/i })
    await user.click(button)

    await screen.findByText(/procesando/i)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('C13/C17: cuando el lote termina, vuelve al botón inicial y refresca el ranking', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    asUser(true)
    let statusCall = 0
    getMock.mockImplementation((path: string) => {
      if (path.includes('/benchmark/ranking')) {
        return Promise.resolve({ data: RANKING, error: undefined })
      }
      if (path.includes('/benchmark/backfill/status')) {
        statusCall += 1
        return Promise.resolve({
          data: statusCall === 1 ? STATUS_RUNNING : STATUS_DONE,
          error: undefined,
        })
      }
      return Promise.resolve({ data: {}, error: undefined })
    })
    renderScreen()

    await vi.waitFor(() => expect(screen.getByText(/procesando/i)).toBeInTheDocument())
    const rankingCallsBefore = getMock.mock.calls.filter((c) =>
      String(c[0]).includes('/benchmark/ranking'),
    ).length

    await vi.advanceTimersByTimeAsync(4000)

    await vi.waitFor(() =>
      expect(screen.getByRole('button', { name: /Últimas/i })).toBeInTheDocument(),
    )
    const rankingCallsAfter = getMock.mock.calls.filter((c) =>
      String(c[0]).includes('/benchmark/ranking'),
    ).length
    expect(rankingCallsAfter).toBeGreaterThan(rankingCallsBefore)
  })
})
