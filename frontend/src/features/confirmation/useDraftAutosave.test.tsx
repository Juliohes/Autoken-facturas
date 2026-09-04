import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import type { ConfirmFormState } from './formState'
import { useDraftAutosave } from './useDraftAutosave'

vi.mock('../../api/client', () => ({ api: { PUT: vi.fn() } }))

const putMock = api.PUT as unknown as Mock

const form: ConfirmFormState = {
  issue_date: '2026-08-21',
  counterparty_tax_id: 'B12345678',
  counterparty_name: 'Proveedor',
  invoice_number: 'F-1',
  net_amount: '100',
  tax_amount: '21',
  total_amount: '121',
  irpf_amount: '',
  tax_lines: [{ iva_pct: '21', base: '100', cuota: '21' }],
}

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>
}

beforeEach(() => {
  putMock.mockReset()
})

describe('useDraftAutosave (R-022)', () => {
  it('espera 750 ms, guarda el snapshot y avanza la revisión', async () => {
    putMock.mockResolvedValue({ data: { revision: 1, updated_at: '2026-08-21T10:00:00Z' }, error: undefined })
    const onSaved = vi.fn()
    const { result, rerender } = renderHook(
      ({ currentForm }) => useDraftAutosave({
        fileId: 'file-1', form: currentForm, direction: 'recibida', revision: 0, onSaved,
      }),
      { initialProps: { currentForm: form }, wrapper },
    )

    rerender({ currentForm: { ...form, total_amount: '122' } })
    expect(result.current.state).toBe('dirty')
    await new Promise((resolve) => window.setTimeout(resolve, 800))

    await waitFor(() => expect(putMock).toHaveBeenCalledTimes(1))
    expect(putMock.mock.calls[0][1].body).toMatchObject({ revision: 0, total_amount: '122' })
    await waitFor(() => expect(result.current.state).toBe('saved'))
    expect(onSaved).toHaveBeenCalledWith({ revision: 1, updated_at: '2026-08-21T10:00:00Z' })
  })

  it('expone error de guardado y permite que la pantalla reintente', async () => {
    putMock.mockResolvedValue({ error: { detail: 'conflict' } })
    const { result, rerender } = renderHook(
      ({ currentForm }) => useDraftAutosave({
        fileId: 'file-1', form: currentForm, direction: 'recibida', revision: 1, onSaved: vi.fn(),
      }),
      { initialProps: { currentForm: form }, wrapper },
    )

    rerender({ currentForm: { ...form, total_amount: '123' } })
    await new Promise((resolve) => window.setTimeout(resolve, 800))

    await waitFor(() => expect(result.current.state).toBe('save_error'))
    expect(await result.current.saveNow()).toBe(false)
  })

  it('no escribe borradores cuando el rollout del autosave está apagado', async () => {
    const { result, rerender } = renderHook(
      ({ currentForm }) => useDraftAutosave({
        fileId: 'file-1',
        form: currentForm,
        direction: 'recibida',
        revision: 1,
        onSaved: vi.fn(),
        enabled: false,
      }),
      { initialProps: { currentForm: form }, wrapper },
    )

    rerender({ currentForm: { ...form, total_amount: '124' } })
    await new Promise((resolve) => window.setTimeout(resolve, 800))

    expect(putMock).not.toHaveBeenCalled()
    expect(result.current.state).toBe('clean')
    expect(await result.current.saveNow()).toBe(true)
  })
})
