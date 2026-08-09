// Tests de comportamiento de `OcrRanking` (S4.8, C10/C11; 2026-08-09 "ver ejemplos concretos").
// Cliente de API mockeado; sesión mockeada para controlar `user.is_admin_tech`.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { OcrRanking } from './OcrRanking'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn() },
}))
vi.mock('../session/SessionProvider', () => ({
  useSession: vi.fn(),
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const useSessionMock = vi.mocked(useSession)

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <OcrRanking />
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

beforeEach(() => {
  getMock.mockReset()
})

describe('OcrRanking (S4.8)', () => {
  it('C10: un platform_admin sin el flag ve "sin acceso", nunca la tabla', () => {
    asUser(false)

    renderScreen()

    expect(screen.getByRole('alert')).toHaveTextContent(/no tienes acceso/i)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(getMock).not.toHaveBeenCalled() // evita el GET que el backend rechazaría con 403
  })

  it('C11: admin-tech ve el ranking agregado por motor', async () => {
    asUser(true)
    getMock.mockResolvedValueOnce({
      data: [
        { engine: 'gemini-3-flash', invoices_read: 10, average_score: 4.5, first_place_count: 6 },
        { engine: 'mistral-ocr-4', invoices_read: 10, average_score: 0.2, first_place_count: 0 },
      ],
      error: undefined,
    })

    renderScreen()

    expect(await screen.findByText('gemini-3-flash')).toBeInTheDocument()
    expect(screen.getByText('mistral-ocr-4')).toBeInTheDocument()
    expect(screen.getByText('4.50')).toBeInTheDocument()
  })

  it('marca los motores sin campos estructurados por diseño de su API (spec §0)', async () => {
    asUser(true)
    getMock.mockResolvedValueOnce({
      data: [
        { engine: 'gemini-3-flash', invoices_read: 10, average_score: 4.5, first_place_count: 6 },
        { engine: 'mistral-ocr-4', invoices_read: 10, average_score: 0.2, first_place_count: 0 },
        { engine: 'azure-docintel', invoices_read: 10, average_score: 1.1, first_place_count: 0 },
      ],
      error: undefined,
    })

    renderScreen()

    await screen.findByText('gemini-3-flash')
    const flashRow = screen.getByText('gemini-3-flash').closest('tr')
    const mistralRow = screen.getByText('mistral-ocr-4').closest('tr')
    const azureRow = screen.getByText('azure-docintel').closest('tr')

    expect(flashRow).not.toHaveTextContent(/sin campos estructurados/i)
    expect(mistralRow).toHaveTextContent(/sin campos estructurados/i)
    expect(azureRow).toHaveTextContent(/sin campos estructurados/i)
  })

  it('sin facturas rankeadas todavía, muestra un estado vacío en vez de una tabla en blanco', async () => {
    asUser(true)
    getMock.mockResolvedValueOnce({ data: [], error: undefined })

    renderScreen()

    expect(await screen.findByText(/todavía no hay facturas rankeadas/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('fallo de red muestra un aviso, no una pantalla en blanco', async () => {
    asUser(true)
    getMock.mockResolvedValueOnce({ data: undefined, error: { detail: 'boom' } })

    renderScreen()

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo cargar el ranking/i)
  })

  it('2026-08-09: "Ver ejemplos" abre una ventana con lecturas reales de ese motor', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/examples')) {
        return Promise.resolve({
          data: [
            {
              uploaded_file_id: 'f1',
              model: 'gemini-3-flash-001',
              // El CIF/nombre de contraparte NUNCA llega aquí (el backend ya los redacta, S5.2
              // §6): un campo anidado real (`tax_lines`) para probar que se muestra legible.
              reading: {
                total_amount: '121.00',
                tax_lines: [{ iva_pct: '21', base: '100.00', cuota: '21.00' }],
              },
              score: 4,
            },
          ],
          error: undefined,
        })
      }
      return Promise.resolve({
        data: [
          { engine: 'gemini-3-flash', invoices_read: 10, average_score: 4.5, first_place_count: 6 },
        ],
        error: undefined,
      })
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('gemini-3-flash')

    await user.click(screen.getByRole('button', { name: 'Ver ejemplos' }))

    const dialog = await screen.findByRole('dialog', { name: /gemini-3-flash/i })
    expect(getMock).toHaveBeenCalledWith(
      '/api/v1/platform/ocr-ranking/{engine}/examples',
      expect.objectContaining({ params: { path: { engine: 'gemini-3-flash' } } }),
    )
    expect(within(dialog).getByText('121.00')).toBeInTheDocument()
    // Un campo anidado (array/objeto) se muestra como JSON legible, no "[object Object]".
    expect(within(dialog).getByText(/"iva_pct":"21"/)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('2026-08-09: fallo al cargar los ejemplos muestra un aviso dentro de la ventana', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/examples')) {
        return Promise.resolve({ data: undefined, error: { detail: 'boom' } })
      }
      return Promise.resolve({
        data: [
          { engine: 'gemini-3-flash', invoices_read: 10, average_score: 4.5, first_place_count: 6 },
        ],
        error: undefined,
      })
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('gemini-3-flash')

    await user.click(screen.getByRole('button', { name: 'Ver ejemplos' }))

    const dialog = await screen.findByRole('dialog', { name: /gemini-3-flash/i })
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      /no se pudieron cargar los ejemplos/i,
    )
  })

  it('2026-08-09: sin ejemplos todavía para ese motor, lo dice explícito', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/examples')) {
        return Promise.resolve({ data: [], error: undefined })
      }
      return Promise.resolve({
        data: [
          { engine: 'mistral-ocr-4', invoices_read: 3, average_score: 1.2, first_place_count: 0 },
        ],
        error: undefined,
      })
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByText('mistral-ocr-4')

    await user.click(screen.getByRole('button', { name: 'Ver ejemplos' }))

    const dialog = await screen.findByRole('dialog', { name: /mistral-ocr-4/i })
    expect(within(dialog).getByText(/todavía no hay ejemplos/i)).toBeInTheDocument()
  })
})
