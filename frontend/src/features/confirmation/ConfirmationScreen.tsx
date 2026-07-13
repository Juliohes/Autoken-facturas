// Pantalla de confirmación (S2.4): el humano revisa lo que leyó la IA y confirma
// o repite la foto. Orquesta los hooks de datos y los componentes de presentación;
// la lógica (color de confianza, botón habilitado, body del confirm) vive en
// módulos puros aparte (sin monolito). Comportamientos C1-C12 de la spec.
import { useState } from 'react'

import { CounterpartyVerdictBlock } from './CounterpartyVerdictBlock'
import { FieldRow } from './FieldRow'
import { ResponsibilityCheckbox } from './ResponsibilityCheckbox'
import { isConfirmEnabled } from './confirmGate'
import { formStateToConfirmBody, initialFormState, type ConfirmFormState } from './formState'
import { useConfirm } from './useConfirm'
import { useReview } from './useReview'
import { WARNING_IMBALANCE, type Confidence, type ReviewResponse } from './types'

// Aviso rojo de responsabilidad, SIEMPRE bajo el botón (spec §2, C9).
export const RESPONSIBILITY_NOTICE =
  'Revisa bien los datos antes de confirmar: su veracidad es responsabilidad de quien los confirma.'

interface Props {
  fileId: string
  onConfirmed: () => void
  onRetry: () => void
}

export function ConfirmationScreen({ fileId, onConfirmed, onRetry }: Props) {
  const review = useReview(fileId)

  if (review.isLoading) {
    return <p className="p-6 text-slate-400">Cargando datos de revisión…</p>
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
    />
  )
}

interface FormProps {
  fileId: string
  review: ReviewResponse
  onConfirmed: () => void
  onRetry: () => void
}

/** Formulario propiamente dicho: se monta con los datos ya cargados. */
function ConfirmationForm({ fileId, review, onConfirmed, onRetry }: FormProps) {
  const confirm = useConfirm(fileId)
  const [form, setForm] = useState<ConfirmFormState>(() => initialFormState(review))
  const [responsibilityAccepted, setResponsibilityAccepted] = useState(false)

  const conf = (field: string): Confidence => review.confidences[field] ?? null
  const set = (patch: Partial<ConfirmFormState>) => setForm((prev) => ({ ...prev, ...patch }))

  const enabled = isConfirmEnabled({
    blockingReasons: review.blocking_reasons,
    responsibilityAccepted,
    submitting: confirm.isPending,
  })

  const hasImbalance = review.warnings.includes(WARNING_IMBALANCE)

  const handleConfirm = () => {
    // `direction` se propaga (la selección Recibida/Emitida es de S2.2, §6): por
    // defecto "recibida", el flujo del CIF de contraparte de §11.8.
    const body = formStateToConfirmBody(form, {
      direction: 'recibida',
      responsibilityAccepted,
    })
    confirm.mutate(body, { onSuccess: () => onConfirmed() })
  }

  return (
    <section className="mx-auto max-w-xl space-y-4 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Revisar y confirmar</h1>

      {/* C1: tres campos siempre visibles (total, CIF de contraparte, fecha). */}
      <FieldRow
        name="total_amount"
        label="Importe total"
        value={form.total_amount}
        confidence={conf('total_amount')}
        onChange={(v) => set({ total_amount: v })}
      />
      <div className="space-y-2">
        <FieldRow
          name="counterparty_tax_id"
          label="CIF de contraparte"
          value={form.counterparty_tax_id}
          confidence={conf('counterparty_tax_id')}
          onChange={(v) => set({ counterparty_tax_id: v })}
        />
        <CounterpartyVerdictBlock verdict={review.counterparty_verdict} />
      </div>
      <FieldRow
        name="issue_date"
        label="Fecha"
        type="date"
        value={form.issue_date}
        confidence={conf('issue_date')}
        onChange={(v) => set({ issue_date: v })}
      />

      {/* C10: descuadre aritmético -> aviso "Revisar" (no bloquea). */}
      {hasImbalance && (
        <p
          data-testid="warning-imbalance"
          className="rounded-md border border-yellow-500 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-200"
        >
          Revisar: el total no cuadra con los tramos de IVA.
        </p>
      )}

      {/* C1: el resto plegado por defecto. */}
      <details data-testid="more-fields" className="rounded-md border border-slate-700 p-3">
        <summary className="cursor-pointer text-sm text-slate-300">Ver todos los campos</summary>
        <div className="mt-3 space-y-3">
          <FieldRow
            name="counterparty_name"
            label="Nombre de la contraparte"
            value={form.counterparty_name}
            confidence={conf('counterparty_name')}
            onChange={(v) => set({ counterparty_name: v })}
          />
          <FieldRow
            name="net_amount"
            label="Base imponible"
            value={form.net_amount}
            confidence={conf('net_amount')}
            onChange={(v) => set({ net_amount: v })}
          />
          <FieldRow
            name="tax_amount"
            label="IVA"
            value={form.tax_amount}
            confidence={conf('tax_amount')}
            onChange={(v) => set({ tax_amount: v })}
          />
          <FieldRow
            name="irpf_amount"
            label="IRPF (retención)"
            value={form.irpf_amount}
            scored={false}
            onChange={(v) => set({ irpf_amount: v })}
          />
          {form.tax_lines.map((line, i) => (
            <div key={i} className="grid grid-cols-3 gap-2" data-testid={`tax-line-${i}`}>
              <FieldRow
                name={`tax_lines.${i}.iva_pct`}
                label="% IVA"
                value={line.iva_pct}
                scored={false}
                onChange={(v) =>
                  set({
                    tax_lines: form.tax_lines.map((l, j) =>
                      j === i ? { ...l, iva_pct: v } : l,
                    ),
                  })
                }
              />
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
          ))}
          {/* Identidad propia conocida (no editable, no se puntúa; ADR-0011). */}
          <div data-testid="own-identity" className="text-sm text-slate-400">
            <p>Empresa propia: {review.own.name ?? '—'}</p>
            <p>CIF propio: {review.own.cif ?? '—'}</p>
          </div>
        </div>
      </details>

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
