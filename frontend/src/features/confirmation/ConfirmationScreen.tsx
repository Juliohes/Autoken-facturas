// Pantalla de confirmación (S2.4): el humano revisa lo que leyó la IA y confirma
// o repite la foto. Orquesta los hooks de datos y los componentes de presentación;
// la lógica (color de confianza, botón habilitado, body del confirm) vive en
// módulos puros aparte (sin monolito). Comportamientos C1-C12 de la spec.
import { useState } from 'react'

import { useCurrentUser } from '../identity/useCurrentUser'
import { CounterpartyVerdictBlock } from './CounterpartyVerdictBlock'
import { FieldRow } from './FieldRow'
import { ResponsibilityCheckbox } from './ResponsibilityCheckbox'
import { isConfirmEnabled } from './confirmGate'
import { formStateToConfirmBody, initialFormState, type ConfirmFormState } from './formState'
import { availableTaxRates, taxRateLabel } from './taxLines'
import { useConfirm } from './useConfirm'
import { useReview, PendingOcrError } from './useReview'
import { BLOCKING_REASONS, WARNING_IMBALANCE, type Confidence, type ReviewResponse } from './types'

// Aviso rojo de responsabilidad, SIEMPRE bajo el botón (spec §2, C9).
export const RESPONSIBILITY_NOTICE =
  'Revisa bien los datos antes de confirmar: su veracidad es responsabilidad de quien los confirma.'

interface Props {
  fileId: string
  onConfirmed: () => void
  onRetry: () => void
  /** Recibida/Emitida elegida en la captura (S2.2); sin captura de por medio (navegación directa a
   * esta URL), se mantiene el valor por defecto de siempre. */
  direction?: 'recibida' | 'emitida'
}

export function ConfirmationScreen({ fileId, onConfirmed, onRetry, direction = 'recibida' }: Props) {
  const review = useReview(fileId)

  if (review.isLoading) {
    const isPendingOcr = review.failureReason instanceof PendingOcrError
    return (
      <div className="p-6 flex flex-col items-center justify-center space-y-4 text-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-emerald-500" />
        <p className="text-slate-100 font-medium">
          {isPendingOcr ? 'Procesando factura con IA…' : 'Cargando datos de revisión…'}
        </p>
        <p className="text-sm text-slate-400">
          {isPendingOcr ? 'Esto puede tardar unos segundos.' : 'Espera un momento, por favor.'}
        </p>
      </div>
    )
  }
  if (review.isError || !review.data) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No se pudieron cargar los datos de esta factura.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-md border border-slate-600 px-4 py-2 text-slate-100"
        >
          Repetir foto
        </button>
      </div>
    )
  }

  return (
    <ConfirmationForm
      fileId={fileId}
      review={review.data}
      onConfirmed={onConfirmed}
      onRetry={onRetry}
      direction={direction}
    />
  )
}

interface FormProps {
  fileId: string
  review: ReviewResponse
  onConfirmed: () => void
  onRetry: () => void
  direction: 'recibida' | 'emitida'
}

/** Formulario propiamente dicho: se monta con los datos ya cargados. */
function ConfirmationForm({ fileId, review, onConfirmed, onRetry, direction }: FormProps) {
  const confirm = useConfirm(fileId)
  const currentUser = useCurrentUser()
  const [form, setForm] = useState<ConfirmFormState>(() => initialFormState(review))
  const [responsibilityAccepted, setResponsibilityAccepted] = useState(false)
  const [isTest, setIsTest] = useState(false)
  const isAdmin = currentUser.data?.role === 'tenant_admin'

  const conf = (field: string): Confidence => review.confidences[field] ?? null
  const set = (patch: Partial<ConfirmFormState>) => setForm((prev) => ({ ...prev, ...patch }))

  const enabled = isConfirmEnabled({
    blockingReasons: review.blocking_reasons,
    responsibilityAccepted,
    submitting: confirm.isPending,
  })

  const hasImbalance = review.warnings.includes(WARNING_IMBALANCE)
  // 2026-08-08 (petición de Julio): sin caja "CIF de contraparte verificado" — un check verde
  // junto al campo, mismo estilo que las marcas de confianza. La caja se conserva para los casos
  // que sí necesitan explicación (inválido/no encontrado/nombre que no coincide/sin verificar).
  const isCounterpartyVerified =
    review.counterparty_verdict.status === 'valid' && review.counterparty_verdict.name_match !== false
  const missingOwnTaxId = review.blocking_reasons.includes(BLOCKING_REASONS.ownTaxIdMissing)

  const handleConfirm = () => {
    // `direction` llega de la selección Recibida/Emitida de S2.2; por defecto "recibida" si se
    // navega aquí sin pasar por la captura (flujo del CIF de contraparte de §11.8).
    const body = formStateToConfirmBody(form, {
      direction,
      responsibilityAccepted,
      isTest: isAdmin && isTest,
    })
    confirm.mutate(body, { onSuccess: () => onConfirmed() })
  }

  return (
    <section className="mx-auto max-w-xl space-y-6 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Revisar y confirmar</h1>

      {/* Enmienda S6.1 §8 (2026-08-08, tras probar con Julio): 4 secciones siempre visibles, en
          vez de "3-4 campos siempre visibles + resto plegado". Solo tramos de IVA e IRPF
          conservan su propio desplegable interno (sin cambios de comportamiento ahí). */}

      <div data-testid="section-counterparty" className="space-y-3 rounded-md border border-slate-700 p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Contraparte</h2>
        <FieldRow
          name="counterparty_tax_id"
          label="CIF de contraparte"
          value={form.counterparty_tax_id}
          confidence={conf('counterparty_tax_id')}
          onChange={(v) => set({ counterparty_tax_id: v })}
          extraBadge={
            isCounterpartyVerified ? (
              <span
                data-testid="mark-counterparty-verified"
                title="CIF verificado"
                className="rounded px-1.5 py-0.5 text-xs font-semibold text-emerald-300"
              >
                ✓
              </span>
            ) : undefined
          }
        />
        {!isCounterpartyVerified && <CounterpartyVerdictBlock verdict={review.counterparty_verdict} />}
        <FieldRow
          name="counterparty_name"
          label="Nombre de la contraparte"
          value={form.counterparty_name}
          confidence={conf('counterparty_name')}
          onChange={(v) => set({ counterparty_name: v })}
        />
      </div>

      <div data-testid="section-amounts" className="space-y-3 rounded-md border border-slate-700 p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Importes</h2>
        <FieldRow
          name="net_amount"
          label="Base imponible"
          value={form.net_amount}
          confidence={conf('net_amount')}
          onChange={(v) => set({ net_amount: v })}
        />

        {/* S6.1 C8-C12: tramos de IVA en desplegable con resumen; añadir/quitar con tasa
            cerrada {21,10,4,Sin IVA}, nunca un % libre. */}
        <details data-testid="tax-lines" className="rounded-md border border-slate-700 p-3">
          <summary className="cursor-pointer text-sm text-slate-300">Tramos de IVA</summary>
          <div className="mt-3 space-y-3">
            {form.tax_lines.map((line, i) => (
              <div
                key={i}
                className="space-y-2 rounded-md border border-slate-700 p-2"
                data-testid={`tax-line-${i}`}
              >
                <div className="flex items-center justify-between">
                  <span data-testid={`tax-line-${i}-summary`} className="text-sm text-slate-300">
                    {taxRateLabel(line.iva_pct)} · Base {line.base || '—'}
                  </span>
                  <button
                    type="button"
                    data-testid={`remove-tax-line-${i}`}
                    onClick={() => set({ tax_lines: form.tax_lines.filter((_, j) => j !== i) })}
                    className="text-xs font-semibold text-red-400"
                  >
                    Quitar
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:gap-3">
                  <FieldRow
                    name={`tax_lines.${i}.base`}
                    label="Base"
                    value={line.base}
                    scored={false}
                    onChange={(v) =>
                      set({
                        tax_lines: form.tax_lines.map((l, j) => (j === i ? { ...l, base: v } : l)),
                      })
                    }
                  />
                  <FieldRow
                    name={`tax_lines.${i}.cuota`}
                    label="Cuota"
                    value={line.cuota}
                    scored={false}
                    onChange={(v) =>
                      set({
                        tax_lines: form.tax_lines.map((l, j) => (j === i ? { ...l, cuota: v } : l)),
                      })
                    }
                  />
                </div>
              </div>
            ))}
            {availableTaxRates(form.tax_lines).length > 0 && (
              <select
                data-testid="add-tax-line-rate"
                aria-label="Añadir tramo de IVA"
                value=""
                onChange={(e) => {
                  const rate = e.target.value
                  if (!rate) return
                  set({ tax_lines: [...form.tax_lines, { iva_pct: rate, base: '', cuota: '' }] })
                }}
                className="w-full rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100"
              >
                <option value="">Añadir tramo…</option>
                {availableTaxRates(form.tax_lines).map((rate) => (
                  <option key={rate} value={rate}>
                    {taxRateLabel(rate)}
                  </option>
                ))}
              </select>
            )}
          </div>
        </details>

        <FieldRow
          name="tax_amount"
          label="IVA"
          value={form.tax_amount}
          confidence={conf('tax_amount')}
          onChange={(v) => set({ tax_amount: v })}
        />
        <FieldRow
          name="total_amount"
          label="Importe total"
          value={form.total_amount}
          confidence={conf('total_amount')}
          onChange={(v) => set({ total_amount: v })}
        />

        {/* S6.1 C13-C15: IRPF en su propio desplegable; sigue sin ser un campo de oro leído por IA
            (manual, como siempre), vacío de verdad si no hay retención. */}
        <details data-testid="irpf-details" className="rounded-md border border-slate-700 p-3">
          <summary className="cursor-pointer text-sm text-slate-300">IRPF</summary>
          <div className="mt-3">
            <FieldRow
              name="irpf_amount"
              label="IRPF (retención)"
              value={form.irpf_amount}
              scored={false}
              onChange={(v) => set({ irpf_amount: v })}
            />
          </div>
        </details>

        {/* C10: descuadre aritmético -> aviso "Revisar" (no bloquea). */}
        {hasImbalance && (
          <p
            data-testid="warning-imbalance"
            className="rounded-md border border-yellow-500 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-200"
          >
            Revisar: el total no cuadra con los tramos de IVA.
          </p>
        )}
      </div>

      <div
        data-testid="section-invoice-identity"
        className="space-y-3 rounded-md border border-slate-700 p-4"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Fecha y número de factura
        </h2>
        <FieldRow
          name="issue_date"
          label="Fecha"
          type="date"
          value={form.issue_date}
          confidence={conf('issue_date')}
          onChange={(v) => set({ issue_date: v })}
        />
        <FieldRow
          name="invoice_number"
          label="Número de factura"
          value={form.invoice_number}
          confidence={conf('invoice_number')}
          onChange={(v) => set({ invoice_number: v })}
        />
      </div>

      {/* Identidad propia conocida (no editable, no se puntúa; ADR-0011): al final, texto plano,
          sin caja de campo — viene del registro de la empresa, no se lee ni se confirma aquí. */}
      <div data-testid="own-identity" className="text-sm text-slate-400">
        <p>Empresa propia: {review.own.name ?? '—'}</p>
        <p>CIF propio: {review.own.cif ?? '—'}</p>
      </div>

      {/* 2026-08-08 (hallazgo de Julio): antes este motivo de bloqueo no tenía NINGÚN mensaje
          visible — el botón se deshabilitaba sin que el usuario supiera por qué. */}
      {missingOwnTaxId && (
        <p
          data-testid="warning-own-tax-id-missing"
          role="alert"
          className="rounded-md border border-red-500 bg-red-500/10 px-3 py-2 text-sm text-red-200"
        >
          Tu CIF no aparece en esta factura: solo un administrador de la asesoría puede confirmarla
          así. Revisa la foto o pide a un administrador que la confirme.
        </p>
      )}

      {/* S3.5: solo el tenant_admin puede marcar una factura como de prueba (excluida de
          informes, purgable de un clic); un empleado ni ve la casilla. */}
      {isAdmin && (
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={isTest}
            onChange={(e) => setIsTest(e.target.checked)}
          />
          Factura de prueba (no aparecerá en informes)
        </label>
      )}

      <ResponsibilityCheckbox
        checked={responsibilityAccepted}
        onChange={setResponsibilityAccepted}
      />

      <button
        type="button"
        disabled={!enabled}
        onClick={handleConfirm}
        className="w-full rounded-md bg-emerald-600 px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        Confirmar y guardar
      </button>

      {/* C9: aviso rojo, grande y legible, SIEMPRE bajo el botón. */}
      <p role="alert" className="text-center text-base font-semibold text-red-400">
        {RESPONSIBILITY_NOTICE}
      </p>

      {/* C12: rechazo del servidor mostrado sin perder lo editado ni navegar. */}
      {confirm.isError && (
        <p data-testid="confirm-error" role="alert" className="text-sm text-red-400">
          {confirm.error.message}
        </p>
      )}

      <button
        type="button"
        onClick={onRetry}
        className="w-full rounded-md border border-slate-600 px-4 py-2 text-slate-100"
      >
        Repetir foto
      </button>
    </section>
  )
}
