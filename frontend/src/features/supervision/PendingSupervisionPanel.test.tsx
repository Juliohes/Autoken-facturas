import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { PendingSupervisionPanel } from './PendingSupervisionPanel'
import { SupervisionReviewScreen } from './SupervisionReviewScreen'

vi.mock('../../api/client', () => ({ api: { GET: vi.fn() } }))

const getMock = api.GET as unknown as Mock

function renderWithQuery(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => getMock.mockReset())

describe('supervisión tenant_admin (R-026)', () => {
  it('muestra metadata ajena y enlaza a una apertura read-only', async () => {
    getMock.mockResolvedValue({
      data: {
        items: [{
          id: 'file-1', user_email: 'alice@example.com', company_name: 'Empresa SL',
          status: 'needs_review', created_at: '2026-08-21T10:00:00Z', direction: 'recibida', page_count: 2,
        }],
        next_cursor: null,
      },
      error: undefined,
    })

    renderWithQuery(<PendingSupervisionPanel />)

    expect(await screen.findByText('Pendientes del equipo')).toBeInTheDocument()
    expect(screen.getByText('alice@example.com')).toBeInTheDocument()
    expect(screen.getByText('Empresa SL')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver solo lectura' })).toHaveAttribute(
      'href', '/pendientes-equipo/file-1',
    )
  })

  it('no muestra botones de guardar o confirmar en la revisión ajena', async () => {
    getMock.mockResolvedValue({
      data: {
        fields: {
          total_amount: '121.00', counterparty_name: 'Proveedor', invoice_number: 'F-1',
        },
        source: 'draft', confidences: {}, counterparty_verdict: {}, own: {},
        warnings: [], blocking_reasons: [], direction: 'recibida',
      },
      error: undefined,
    })

    renderWithQuery(<SupervisionReviewScreen fileId="file-1" />)

    expect(await screen.findByRole('heading', { name: 'Revisión de supervisión' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /guardar|confirmar/i })).not.toBeInTheDocument()
    expect(screen.getByText('Proveedor')).toBeInTheDocument()
  })
})
