// Tests de comportamiento de la pantalla de confirmación (S2.4), C1-C12. El
// cliente de API está mockeado: se inyectan las respuestas de `review`/`confirm`
// de cada escenario (sin navegador ni backend reales; jsdom).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { ConfirmationScreen, RESPONSIBILITY_NOTICE } from './ConfirmationScreen'
import { PendingOcrError } from './useReview'
import type { ReviewResponse } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock

function makeReview(over: Partial<ReviewResponse> = {}): ReviewResponse {
  return {
    fields: {
      issue_date: '2026-01-15',
      total_amount: '100.00',
      net_amount: '82.64',
      tax_amount: '17.36',
      invoice_number: 'F-2026-001',
      counterparty_tax_id: 'B12345678',
      counterparty_name: 'Proveedor SL',
      tax_lines: [],
    },
    confidences: {},
    counterparty_verdict: { status: 'valid', name_match: true, official_name: null },
    own: { cif: 'A11111111', name: 'Mi Empresa SL' },
    warnings: [],
    blocking_reasons: [],
    ...over,
  }
}

function renderScreen() {
  const onConfirmed = vi.fn()
  const onRetry = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <ConfirmationScreen fileId="file-1" onConfirmed={onConfirmed} onRetry={onRetry} />
    </QueryClientProvider>,
  )
  return { onConfirmed, onRetry }
}

/** Marca la responsabilidad y espera a que el botón se habilite. */
async function acceptResponsibility(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('checkbox'))
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  getMock.mockResolvedValue({ data: makeReview(), error: undefined })
  postMock.mockResolvedValue({ data: { id: 'inv-1' }, error: undefined })
})

describe('ConfirmationScreen (S2.4)', () => {
  it('C1 (enmienda S6.1 §8): datos organizados en 4 secciones siempre visibles', async () => {
    renderScreen()

    // Sección Contraparte: CIF (con su check de verificado, spec por defecto 'valid') + nombre.
    const contraparte = await screen.findByTestId('section-counterparty')
    expect(within(contraparte).getByLabelText('CIF de contraparte')).toBeInTheDocument()
    expect(within(contraparte).getByTestId('mark-counterparty-verified')).toBeInTheDocument()
    expect(within(contraparte).getByLabelText('Nombre de la contraparte')).toBeInTheDocument()

    // Sección Importes: base, IVA, total e IRPF juntos (tramos e IRPF conservan su desplegable).
    const importes = screen.getByTestId('section-amounts')
    expect(within(importes).getByLabelText('Base imponible')).toBeInTheDocument()
    expect(within(importes).getByLabelText('IVA')).toBeInTheDocument()
    expect(within(importes).getByLabelText('Importe total')).toBeInTheDocument()
    expect(within(importes).getByTestId('tax-lines')).toBeInTheDocument()
    expect(within(importes).getByLabelText('IRPF (retención)')).toBeInTheDocument()

    // Sección Fecha y número de factura, juntos.
    const invoiceIdentity = screen.getByTestId('section-invoice-identity')
    expect(within(invoiceIdentity).getByLabelText('Fecha')).toBeInTheDocument()
    expect(within(invoiceIdentity).getByLabelText('Número de factura')).toBeInTheDocument()

    // Sección Datos propios: al final, sin cambios de comportamiento (texto plano, no editable).
    const ownIdentity = screen.getByTestId('own-identity')
    expect(ownIdentity).toHaveTextContent('Mi Empresa SL')

    // Ya no hay una sección "siempre visible" separada de una "plegada" (enmienda §8).
    expect(screen.queryByTestId('more-fields')).not.toBeInTheDocument()
  })

  it('C2: media = dudoso (amarillo), alta sin marca (spec S6.1 C20: baja+valor ya no es "no leído")', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        // `issue_date` tiene valor en `makeReview()` (no es null): con confianza `baja` debe
        // marcarse "Dudoso, revisar" (spec S6.1 C20), NO "No leído" (eso es solo para C21, valor
        // realmente ausente — ver el describe "S6.1" más abajo).
        confidences: { total_amount: 'media', issue_date: 'baja', counterparty_tax_id: 'alta' },
      }),
      error: undefined,
    })
    renderScreen()

    const totalMark = await screen.findByTestId('mark-total_amount')
    expect(totalMark).toHaveAttribute('data-mark', 'dudoso')
    expect(totalMark).toHaveTextContent('Dudoso')

    const dateMark = screen.getByTestId('mark-issue_date')
    expect(dateMark).toHaveAttribute('data-mark', 'revisar')
    expect(dateMark).toHaveTextContent('Dudoso, revisar')

    // `alta` no lleva marca de aviso.
    expect(screen.queryByTestId('mark-counterparty_tax_id')).not.toBeInTheDocument()
  })

  it('C3 (revisado 2026-08-08): veredicto valid+name_match -> check verde junto al CIF, sin caja', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        counterparty_verdict: { status: 'valid', name_match: true, official_name: null },
      }),
      error: undefined,
    })
    renderScreen()

    // Julio pidió quitar la caja "CIF de contraparte verificado": ahora es un check junto al
    // campo, mismo estilo que las marcas de confianza (Dudoso/No leído), en verde.
    const badge = await screen.findByTestId('mark-counterparty-verified')
    expect(badge).toHaveTextContent('✓')
    expect(screen.queryByTestId('counterparty-verdict')).not.toBeInTheDocument()
  })

  it('C3: veredicto valid+name_match=false -> aviso con la razón social oficial', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        counterparty_verdict: {
          status: 'valid',
          name_match: false,
          official_name: 'ACME SOCIEDAD LIMITADA',
        },
      }),
      error: undefined,
    })
    renderScreen()
    const block = await screen.findByTestId('counterparty-verdict')
    expect(block).toHaveAttribute('data-tone', 'warn')
    expect(block).toHaveTextContent('El nombre no coincide con el registrado.')
  })

  it('C3: veredicto invalid/not_found -> rojo; unverified -> aviso revisar manual', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        counterparty_verdict: { status: 'invalid', name_match: null, official_name: null },
      }),
      error: undefined,
    })
    const { onConfirmed } = renderScreen()
    await waitFor(() => expect(onConfirmed).not.toHaveBeenCalled())
    expect(await screen.findByTestId('counterparty-verdict')).toHaveAttribute('data-tone', 'error')

    // not_found -> rojo.
    getMock.mockResolvedValue({
      data: makeReview({
        counterparty_verdict: { status: 'not_found', name_match: null, official_name: null },
      }),
      error: undefined,
    })
    renderScreen()
    await waitFor(() =>
      expect(screen.getAllByTestId('counterparty-verdict').at(-1)).toHaveAttribute(
        'data-tone',
        'error',
      ),
    )

    // unverified -> aviso "revisar manual".
    getMock.mockResolvedValue({
      data: makeReview({
        counterparty_verdict: { status: 'unverified', name_match: null, official_name: null },
      }),
      error: undefined,
    })
    renderScreen()
    await waitFor(() => {
      const last = screen.getAllByTestId('counterparty-verdict').at(-1)
      expect(last).toHaveAttribute('data-tone', 'warn')
      expect(last).toHaveTextContent('No se pudo verificar el CIF. Revísalo antes de guardar.')
    })
  })

  it('C4: counterparty_cif_invalid deshabilita el botón (con checkbox marcado)', async () => {
    getMock.mockResolvedValue({
      data: makeReview({ blocking_reasons: ['counterparty_cif_invalid'] }),
      error: undefined,
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')
    await acceptResponsibility(user)
    expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeDisabled()
  })

  it('C5: counterparty_cif_not_found deshabilita el botón (con checkbox marcado)', async () => {
    getMock.mockResolvedValue({
      data: makeReview({ blocking_reasons: ['counterparty_cif_not_found'] }),
      error: undefined,
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')
    await acceptResponsibility(user)
    expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeDisabled()
  })

  it('C6: own_tax_id_missing deshabilita el botón (con checkbox marcado)', async () => {
    getMock.mockResolvedValue({
      data: makeReview({ blocking_reasons: ['own_tax_id_missing'] }),
      error: undefined,
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')
    await acceptResponsibility(user)
    expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeDisabled()
  })

  it('C6 (2026-08-08, hallazgo de Julio): own_tax_id_missing explica en pantalla por qué no se puede confirmar', async () => {
    // Antes de este cambio, `own_tax_id_missing` bloqueaba el botón sin ningún mensaje visible: el
    // usuario no tenía forma de saber por qué. `counterparty_cif_invalid`/`not_found` ya se
    // explicaban vía el veredicto del CIF; este era el único motivo de bloqueo mudo.
    getMock.mockResolvedValue({
      data: makeReview({ blocking_reasons: ['own_tax_id_missing'] }),
      error: undefined,
    })
    renderScreen()

    expect(await screen.findByTestId('warning-own-tax-id-missing')).toHaveTextContent(
      'No se ve el CIF de Mi Empresa SL (A11111111). Confirma que esta factura es suya.',
    )
  })

  it('S6.10 C6-C7: al editar el CIF, sustituye el bloqueo OCR por el veredicto del borrador actual', async () => {
    getMock.mockImplementation((path: string) => {
      if (path.includes('/auth/me')) {
        return Promise.resolve({ data: { id: 'u1', role: 'user', company: { id: 'c1', name: 'Mi Empresa SL' } }, error: undefined })
      }
      return Promise.resolve({ data: makeReview({ blocking_reasons: ['counterparty_cif_invalid'], counterparty_verdict: { status: 'invalid', name_match: null, official_name: null } }), error: undefined })
    })
    postMock.mockResolvedValueOnce({
      data: { counterparty_verdict: { status: 'valid', name_match: true, official_name: null }, blocking_reasons: [] },
      error: undefined,
    })
    const user = userEvent.setup()
    renderScreen()
    const cif = await screen.findByLabelText('CIF de contraparte')
    await user.clear(cif)
    await user.type(cif, 'A12345678')

    // Mientras espera la pausa breve y la respuesta, un veredicto anterior nunca habilita guardar.
    await user.click(screen.getByLabelText('Acepto la responsabilidad de la veracidad de los datos que confirmo.'))
    expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeDisabled()

    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/api/v1/uploads/{file_id}/counterparty-verdict',
      expect.objectContaining({ body: { counterparty_tax_id: 'A12345678', counterparty_name: 'Proveedor SL' } }),
    ))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeEnabled())
  })

  it('S6.10 C10-C11: un user puede aceptar expresamente el CIF propio ausente', async () => {
    getMock.mockImplementation((path: string) => {
      if (path.includes('/auth/me')) {
        return Promise.resolve({ data: { id: 'u1', role: 'user', company: { id: 'c1', name: 'Mi Empresa SL' } }, error: undefined })
      }
      return Promise.resolve({ data: makeReview({ blocking_reasons: ['own_tax_id_missing'] }), error: undefined })
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')
    await user.click(screen.getByLabelText('Acepto la responsabilidad de la veracidad de los datos que confirmo.'))
    expect(screen.getByText('Marca la confirmación para guardar.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeDisabled()

    await user.click(screen.getByLabelText('Confirmo que esta factura corresponde a Mi Empresa SL (A11111111)'))
    expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Confirmar y guardar' }))
    await waitFor(() => expect(postMock).toHaveBeenCalledWith(
      '/api/v1/uploads/{file_id}/confirm',
      expect.objectContaining({ body: expect.objectContaining({ own_tax_id_exception_accepted: true }) }),
    ))
  })

  it('sin own_tax_id_missing, no se muestra el aviso', async () => {
    renderScreen()
    await screen.findByLabelText('Importe total')
    expect(screen.queryByTestId('warning-own-tax-id-missing')).not.toBeInTheDocument()
  })

  it('C7: sin aceptar responsabilidad el botón está deshabilitado; al marcarlo se habilita', async () => {
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')

    const button = screen.getByRole('button', { name: 'Confirmar y guardar' })
    expect(button).toBeDisabled()

    await acceptResponsibility(user)
    expect(button).toBeEnabled()
  })

  it('C8: sin bloqueos y con responsabilidad, confirma y llama onConfirmed al 201', async () => {
    const user = userEvent.setup()
    const { onConfirmed } = renderScreen()
    await screen.findByLabelText('Importe total')
    await acceptResponsibility(user)

    await user.click(screen.getByRole('button', { name: 'Confirmar y guardar' }))

    expect(postMock).toHaveBeenCalledWith(
      '/api/v1/uploads/{file_id}/confirm',
      expect.objectContaining({
        params: { path: { file_id: 'file-1' } },
        body: expect.objectContaining({
          direction: 'recibida',
          total_amount: '100.00',
          counterparty_tax_id: 'B12345678',
          issue_date: '2026-01-15',
          responsibility_accepted: true,
        }),
      }),
    )
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledTimes(1))
  })

  it('C9: aviso rojo de responsabilidad siempre bajo el botón', async () => {
    renderScreen()
    expect(await screen.findByText(RESPONSIBILITY_NOTICE)).toBeInTheDocument()
  })

  it('C10: warnings con descuadre muestra aviso "Revisar" (no bloquea)', async () => {
    getMock.mockResolvedValue({
      data: makeReview({ warnings: ['descuadre'] }),
      error: undefined,
    })
    const user = userEvent.setup()
    renderScreen()
    expect(await screen.findByTestId('warning-imbalance')).toHaveTextContent('El total no cuadra con el IVA.')

    // El descuadre NO bloquea: con la responsabilidad marcada el botón se habilita.
    await acceptResponsibility(user)
    expect(screen.getByRole('button', { name: 'Confirmar y guardar' })).toBeEnabled()
  })

  it('C11: "Repetir foto" invoca onRetry', async () => {
    const user = userEvent.setup()
    const { onRetry } = renderScreen()
    await screen.findByLabelText('Importe total')
    await user.click(screen.getByRole('button', { name: 'Repetir foto' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('C12: un 4xx del servidor se muestra legible, no pierde lo editado ni navega a éxito', async () => {
    postMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'El CIF de contraparte no es válido o no consta' },
    })
    const user = userEvent.setup()
    const { onConfirmed } = renderScreen()
    await screen.findByLabelText('Importe total')

    // El humano edita un valor antes de confirmar.
    const total = screen.getByLabelText('Importe total')
    await user.clear(total)
    await user.type(total, '250.00')

    await acceptResponsibility(user)
    await user.click(screen.getByRole('button', { name: 'Confirmar y guardar' }))

    // Error legible mostrado; no se navega a éxito; el valor editado se conserva.
    expect(await screen.findByTestId('confirm-error')).toHaveTextContent(
      'No se pudo guardar. Revisa los datos e inténtalo de nuevo.',
    )
    expect(onConfirmed).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Importe total')).toHaveValue('250.00')
  })

  it('extra: el botón se deshabilita mientras el confirm está en vuelo (anti doble envío)', async () => {
    let resolvePost: (value: unknown) => void = () => {}
    postMock.mockReturnValue(
      new Promise((resolve) => {
        resolvePost = resolve
      }),
    )
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')
    await acceptResponsibility(user)

    const button = screen.getByRole('button', { name: 'Confirmar y guardar' })
    await user.click(button)
    await waitFor(() => expect(button).toBeDisabled())

    resolvePost({ data: { id: 'inv-1' }, error: undefined })
  })

  it('S3.5 C9: un tenant_admin ve la casilla "Factura de prueba" y marcarla manda is_test: true', async () => {
    getMock.mockImplementation((path: string) => {
      if (path.includes('/auth/me')) {
        return Promise.resolve({
          data: { id: 'u1', email: 'admin@ilex.es', role: 'tenant_admin', tenant: 'ilex', company: null },
          error: undefined,
        })
      }
      return Promise.resolve({ data: makeReview(), error: undefined })
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')
    const checkbox = await screen.findByText('Factura de prueba (no aparecerá en informes)')
    expect(checkbox).toBeInTheDocument()
    await user.click(screen.getByLabelText('Factura de prueba (no aparecerá en informes)'))
    // Dos casillas en pantalla aquí (prueba + responsabilidad): se identifica por su propia
    // etiqueta, no por `acceptResponsibility` (que asume una única casilla, S2.4).
    await user.click(
      screen.getByLabelText('Acepto la responsabilidad de la veracidad de los datos que confirmo.'),
    )

    await user.click(screen.getByRole('button', { name: 'Confirmar y guardar' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        '/api/v1/uploads/{file_id}/confirm',
        expect.objectContaining({ body: expect.objectContaining({ is_test: true }) }),
      )
    })
  })

  it('S3.5 C10: un empleado no ve la casilla y siempre manda is_test: false', async () => {
    getMock.mockImplementation((path: string) => {
      if (path.includes('/auth/me')) {
        return Promise.resolve({
          data: {
            id: 'u1',
            email: 'ana@ilex.es',
            role: 'user',
            tenant: 'ilex',
            company: { id: 'c1', name: 'Empresa' },
          },
          error: undefined,
        })
      }
      return Promise.resolve({ data: makeReview(), error: undefined })
    })
    const user = userEvent.setup()
    renderScreen()
    await screen.findByLabelText('Importe total')
    expect(screen.queryByText('Factura de prueba (no aparecerá en informes)')).not.toBeInTheDocument()
    await acceptResponsibility(user)

    await user.click(screen.getByRole('button', { name: 'Confirmar y guardar' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        '/api/v1/uploads/{file_id}/confirm',
        expect.objectContaining({ body: expect.objectContaining({ is_test: false }) }),
      )
    })
  })

  it('muestra la pantalla de procesando con IA si la consulta está pendiente de OCR (409)', async () => {
    let reviewCallCount = 0
    getMock.mockImplementation((path: string) => {
      if (path.includes('/auth/me')) {
        return Promise.resolve({
          data: { id: 'u1', email: 'user@ilex.es', role: 'user', tenant: 'ilex', company: { id: 'c1' } },
          error: undefined,
        })
      }
      if (path.includes('/review')) {
        reviewCallCount++
        if (reviewCallCount === 1) {
          return Promise.resolve({
            data: undefined,
            error: { detail: 'La factura todavía se está procesando con IA' },
            response: { status: 409 } as unknown as Response,
          })
        }
        return Promise.resolve({
          data: makeReview(),
          error: undefined,
          response: { status: 200 } as unknown as Response,
        })
      }
      return Promise.resolve({ data: {}, error: undefined })
    })

    const client = new QueryClient({
      defaultOptions: {
        queries: {
          retry: (failureCount, error) => error instanceof PendingOcrError && failureCount < 5,
          retryDelay: 10,
        },
      },
    })

    render(
      <QueryClientProvider client={client}>
        <ConfirmationScreen fileId="file-1" onConfirmed={vi.fn()} onRetry={vi.fn()} />
      </QueryClientProvider>,
    )

    // Se muestra el spinner de procesamiento
    expect(await screen.findByText('Leyendo la factura...')).toBeInTheDocument()

    // Eventualmente carga el formulario de confirmación con éxito tras el reintento de QueryClient
    expect(await screen.findByLabelText('Importe total', {}, { timeout: 3000 })).toBeInTheDocument()
  })

  it('muestra el error genérico sin reintentar si el 409 es permanente (ocr_failed, ya confirmado)', async () => {
    let reviewCallCount = 0
    getMock.mockImplementation((path: string) => {
      if (path.includes('/auth/me')) {
        return Promise.resolve({
          data: { id: 'u1', email: 'user@ilex.es', role: 'user', tenant: 'ilex', company: { id: 'c1' } },
          error: undefined,
        })
      }
      if (path.includes('/review')) {
        reviewCallCount++
        return Promise.resolve({
          data: undefined,
          error: { detail: 'El fichero no tiene datos de revisión que confirmar' },
          response: { status: 409 } as unknown as Response,
        })
      }
      return Promise.resolve({ data: {}, error: undefined })
    })

    const client = new QueryClient({
      defaultOptions: {
        queries: {
          retry: (failureCount, error) => error instanceof PendingOcrError && failureCount < 5,
          retryDelay: 10,
        },
      },
    })

    render(
      <QueryClientProvider client={client}>
        <ConfirmationScreen fileId="file-1" onConfirmed={vi.fn()} onRetry={vi.fn()} />
      </QueryClientProvider>,
    )

    // Error inmediato, no el spinner de "procesando" (no es un caso transitorio: no debe reintentar)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'No se pudo abrir esta factura. Inténtalo de nuevo.',
    )
    expect(screen.queryByText('Leyendo la factura...')).not.toBeInTheDocument()
    expect(reviewCallCount).toBe(1)
  })
})

// spec: docs/specs/S6.1-rediseno-celdas-comprobacion.md
describe('ConfirmationScreen — S6.1 rediseño de celdas de comprobación', () => {
  it('C6 (enmienda §8): número de factura visible, junto a la fecha, en su propia sección', async () => {
    getMock.mockResolvedValue({
      data: makeReview({ fields: { ...makeReview().fields, invoice_number: 'F-2026-001' } }),
      error: undefined,
    })
    renderScreen()

    const invoiceNumber = await screen.findByLabelText('Número de factura')
    expect(invoiceNumber).toBeInTheDocument()
    expect(invoiceNumber).toHaveValue('F-2026-001')
    const section = screen.getByTestId('section-invoice-identity')
    expect(section).toContainElement(invoiceNumber)
    expect(within(section).getByLabelText('Fecha')).toBeInTheDocument()
  })

  it('C8: el desplegable de tramos resume tasa + base de cada tramo existente', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        fields: {
          ...makeReview().fields,
          tax_lines: [
            { base: '100.00', rate: '21', cuota: '21.00' },
            { base: '50.00', rate: '10', cuota: '5.00' },
          ],
        },
      }),
      error: undefined,
    })
    renderScreen()

    const taxLines = await screen.findByTestId('tax-lines')
    expect(within(taxLines).getByTestId('tax-line-0-summary')).toHaveTextContent('21%')
    expect(within(taxLines).getByTestId('tax-line-0-summary')).toHaveTextContent('100,00')
    expect(within(taxLines).getByTestId('tax-line-1-summary')).toHaveTextContent('10%')
    expect(within(taxLines).getByTestId('tax-line-1-summary')).toHaveTextContent('50,00')
  })

  it('C9: "Añadir tramo" solo ofrece las tasas todavía no usadas', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        fields: {
          ...makeReview().fields,
          tax_lines: [
            { base: '100.00', rate: '21', cuota: '21.00' },
            { base: '50.00', rate: '10', cuota: '5.00' },
          ],
        },
      }),
      error: undefined,
    })
    renderScreen()

    const select = await screen.findByTestId('add-tax-line-rate')
    const optionLabels = within(select)
      .getAllByRole('option')
      .map((option) => option.textContent)
    expect(optionLabels).toEqual(['Añadir tramo…', '4%', 'Sin IVA'])
  })

  it('C9b: elegir una tasa en "Añadir tramo" añade un tramo nuevo editable', async () => {
    const user = userEvent.setup()
    getMock.mockResolvedValue({
      data: makeReview({ fields: { ...makeReview().fields, tax_lines: [] } }),
      error: undefined,
    })
    renderScreen()

    const select = await screen.findByTestId('add-tax-line-rate')
    await user.selectOptions(select, '4')

    expect(await screen.findByTestId('tax-line-0')).toBeInTheDocument()
    expect(screen.getByTestId('tax-line-0-summary')).toHaveTextContent('4%')
  })

  it('C10: con las 4 tasas ya usadas, no queda ninguna disponible para añadir', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        fields: {
          ...makeReview().fields,
          tax_lines: [
            { base: '100.00', rate: '21', cuota: '21.00' },
            { base: '50.00', rate: '10', cuota: '5.00' },
            { base: '25.00', rate: '4', cuota: '1.00' },
            { base: '10.00', rate: '0', cuota: '0.00' },
          ],
        },
      }),
      error: undefined,
    })
    renderScreen()

    await screen.findByTestId('tax-lines')
    expect(screen.queryByTestId('add-tax-line-rate')).not.toBeInTheDocument()
  })

  it('C12: quitar un tramo lo elimina y su tasa vuelve a estar disponible para añadir', async () => {
    const user = userEvent.setup()
    getMock.mockResolvedValue({
      data: makeReview({
        fields: { ...makeReview().fields, tax_lines: [{ base: '100.00', rate: '21', cuota: '21.00' }] },
      }),
      error: undefined,
    })
    renderScreen()

    await user.click(await screen.findByTestId('remove-tax-line-0'))

    expect(screen.queryByTestId('tax-line-0')).not.toBeInTheDocument()
    const select = screen.getByTestId('add-tax-line-rate')
    expect(within(select).getByRole('option', { name: '21%' })).toBeInTheDocument()
  })

  it('C13: sin IRPF en la factura, el desplegable no muestra ninguna cantidad', async () => {
    renderScreen()

    const irpfInput = await screen.findByLabelText('IRPF (retención)')
    expect(irpfInput).toHaveValue('')
    const details = screen.getByTestId('irpf-details')
    expect(details).toContainElement(irpfInput)
  })

  it('C15: el IRPF sigue siendo editable dentro de su desplegable', async () => {
    const user = userEvent.setup()
    renderScreen()

    const irpfInput = await screen.findByLabelText('IRPF (retención)')
    await user.type(irpfInput, '15,00')

    expect(irpfInput).toHaveValue('15,00')
  })

  it('C20: un valor presente con confianza baja se marca "Dudoso, revisar", no "No leído"', async () => {
    getMock.mockResolvedValue({
      // `total_amount` tiene un valor real ('100.00') en `makeReview()`.
      data: makeReview({ confidences: { total_amount: 'baja' } }),
      error: undefined,
    })
    renderScreen()

    const mark = await screen.findByTestId('mark-total_amount')
    expect(mark).toHaveAttribute('data-mark', 'revisar')
    expect(mark).toHaveTextContent('Dudoso, revisar')
  })

  it('C21: un campo REALMENTE ausente (null) se marca "No leído"', async () => {
    getMock.mockResolvedValue({
      data: makeReview({
        fields: { ...makeReview().fields, total_amount: null },
        confidences: { total_amount: 'baja' },
      }),
      error: undefined,
    })
    renderScreen()

    const mark = await screen.findByTestId('mark-total_amount')
    expect(mark).toHaveAttribute('data-mark', 'no_leido')
    expect(mark).toHaveTextContent('No leído')
  })
})
