import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '../../api/client'
import { useDraftCounterpartyVerdict } from './useDraftCounterpartyVerdict'

vi.mock('../../api/client', () => ({ api: { POST: vi.fn() } }))

function Probe({ taxId, name }: { taxId: string; name: string }) {
  const result = useDraftCounterpartyVerdict({
    fileId: 'file-1',
    taxId,
    name,
    initialTaxId: 'B00000000',
    initialName: 'OCR inicial',
  })
  return <p>{result.data?.counterparty_verdict.status ?? (result.isError ? 'error' : 'waiting')}</p>
}

describe('useDraftCounterpartyVerdict', () => {
  beforeEach(() => vi.mocked(api.POST).mockReset())

  it('S6.10 C6: valida el borrador actual y no consulta mientras no haya cambios', async () => {
    vi.mocked(api.POST).mockResolvedValue({
      data: { counterparty_verdict: { status: 'valid', name_match: true, official_name: null }, blocking_reasons: [] },
      error: undefined,
    } as never)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { rerender } = render(<QueryClientProvider client={client}><Probe taxId="B00000000" name="OCR inicial" /></QueryClientProvider>)

    expect(api.POST).not.toHaveBeenCalled()
    rerender(<QueryClientProvider client={client}><Probe taxId="B12345678" name="Proveedor SL" /></QueryClientProvider>)

    expect(await screen.findByText('valid', {}, { timeout: 1000 })).toBeInTheDocument()
    expect(api.POST).toHaveBeenCalledWith(
      '/api/v1/uploads/{file_id}/counterparty-verdict',
      expect.objectContaining({ body: { counterparty_tax_id: 'B12345678', counterparty_name: 'Proveedor SL' } }),
    )
  })
})
