// Pantalla de confirmación (S2.4): el humano revisa lo que leyó la IA y confirma
// o repite la foto. Orquesta los hooks de datos y los componentes de presentación;
// la lógica (color de confianza, botón habilitado, body del confirm) vive en
// módulos puros aparte (sin monolito). Comportamientos C1-C12 de la spec.
//
// Experimento 2026-08-01 (rama experiment/setex-user-ui-v1): el rol `user` ve la anatomía de
// HIPERDOC-FRONTEND-USUARIO-v1-setex1.md §09 (encabezado adaptativo, cajas de color, semáforo de
// CIF, texto legal en su posición exacta) — misma lógica/datos/handlers de siempre, solo cambia el
// JSX. `tenant_admin` sigue viendo la pantalla oscura original sin cambios.
import { useState } from 'react'

import { formatCurrency } from '../../shared/format'
import { SetexBadge } from '../../shared/SetexBadge'
import { useCurrentUser } from '../identity/useCurrentUser'
import { CounterpartyVerdictBlock } from './CounterpartyVerdictBlock'
import { FieldRow } from './FieldRow'
import { ResponsibilityCheckbox } from './ResponsibilityCheckbox'
import { confidenceMark } from './confidence'
import { isConfirmEnabled } from './confirmGate'
import { formStateToConfirmBody, initialFormState, type ConfirmFormState } from './formState'
import { useConfirm } from './useConfirm'
import { useReview } from './useReview'
import { WARNING_IMBALANCE, type Confidence, type ReviewResponse } from './types'

// Aviso rojo de responsabilidad, SIEMPRE bajo el botón (spec §2, C9).
export const RESPONSIBILITY_NOTICE =
  'Revisa bien los datos antes de confirmar: su veracidad es responsabilidad de quien los confirma.'

// Texto legal literal (HIPERDOC §16, "no alterar").
const SETEX_CONSENT_TEXT =
  'Al confirmar, declaro que he revisado los datos y que son correctos y veraces.'

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
  const isUserRole = currentUser.data?.role === 'user'

  const conf = (field: string): Confidence => review.confidences[field] ?? null
  const set = (patch: Partial<ConfirmFormState>) => setForm((prev) => ({ ...prev, ...patch }))

  const enabled = isConfirmEnabled({
    blockingReasons: review.blocking_reasons,
    responsibilityAccepted,
    submitting: confirm.isPending,
  })

  const hasImbalance = review.warnings.includes(WARNING_IMBALANCE)

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

  if (isUserRole) {
    return (
      <SetexConfirmationLayout
        review={review}
        form={form}
        set={set}
        conf={conf}
        direction={direction}
        hasImbalance={hasImbalance}
        enabled={enabled}
        submitting={confirm.isPending}
        confirmError={confirm.isError ? confirm.error.message : null}
        responsibilityAccepted={responsibilityAccepted}
        onResponsibilityChange={setResponsibilityAccepted}
        onConfirm={handleConfirm}
        onRetry={onRetry}
      />
    )
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
            <div key={i} className="grid grid-cols-3 gap-2 sm:gap-3" data-testid={`tax-line-${i}`}>
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

// --- Variante SETEX (rol user, experimento 2026-08-01) ------------------------------------------

interface SetexLayoutProps {
  review: ReviewResponse
  form: ConfirmFormState
  set: (patch: Partial<ConfirmFormState>) => void
  conf: (field: string) => Confidence
  direction: 'recibida' | 'emitida'
  hasImbalance: boolean
  enabled: boolean
  submitting: boolean
  confirmError: string | null
  responsibilityAccepted: boolean
  onResponsibilityChange: (checked: boolean) => void
  onConfirm: () => void
  onRetry: () => void
}

// Borde/fondo del semáforo de un campo (§09): rojo = no leído, ámbar = dudoso, verde = ok.
const SETEX_FIELD_STYLE: Record<'ok' | 'dudoso' | 'no_leido', { border: string; bg: string }> = {
  ok: { border: '#68d391', bg: '#f0fff4' },
  dudoso: { border: '#d69e2e', bg: '#fffff0' },
  no_leido: { border: '#e53e3e', bg: '#fff5f5' },
}

function SetexField({
  label,
  value,
  onChange,
  mark,
  type = 'text',
  mono = false,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  mark: 'ok' | 'dudoso' | 'no_leido'
  type?: string
  mono?: boolean
}) {
  const style = SETEX_FIELD_STYLE[mark]
  return (
    <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-sx-ink3">
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className={`rounded-md border-2 px-3 py-2 text-base normal-case text-sx-ink1 ${mono ? 'font-mono tracking-widest' : ''}`}
        style={{ borderColor: style.border, background: style.bg }}
      />
    </label>
  )
}

function SetexConfirmationLayout({
  review,
  form,
  set,
  conf,
  direction,
  hasImbalance,
  enabled,
  submitting,
  confirmError,
  responsibilityAccepted,
  onResponsibilityChange,
  onConfirm,
  onRetry,
}: SetexLayoutProps) {
  // Encabezado adaptativo (§09 punto 1): rojo si falta algo que el servidor bloquearía o algún
  // campo clave no se leyó; verde en caso contrario.
  const keyMarks = ['total_amount', 'counterparty_tax_id', 'issue_date'].map((f) =>
    confidenceMark(conf(f)),
  )
  const hasMissing = review.blocking_reasons.length > 0 || keyMarks.includes('no_leido')

  const base = Number(form.net_amount) || 0
  const cuotaIva = Number(form.tax_amount) || 0
  const cuotaIrpf = Number(form.irpf_amount) || 0
  const summaryTotal = base + cuotaIva - cuotaIrpf

  return (
    <div className="mx-auto w-[90%] max-w-[600px] py-6">
      <div className="space-y-4 rounded-xl border-t-4 border-sx-brand bg-gradient-to-b from-[#fafafa] via-[#f5f5f5] to-[#f0f0f0] p-5 text-sx-ink1 shadow-[0_8px_30px_rgba(0,0,0,.15)]">
        <div className="flex items-center gap-2">
          <SetexBadge />
        </div>

        {/* 1. Encabezado adaptativo */}
        {hasMissing ? (
          <div>
            <h1 className="text-[1.2em] font-semibold" style={{ color: '#c53030' }}>
              Completa los datos que faltan
            </h1>
            <p className="text-sm text-sx-ink3">
              La IA no pudo leer algún campo. Introduce los datos manualmente o cancela para repetir
              la foto.
            </p>
          </div>
        ) : (
          <div>
            <h1 className="text-[1.2em] font-semibold" style={{ color: '#276749' }}>
              Confirma los datos
            </h1>
            <p className="text-sm text-sx-ink3">
              Revisa que la información extraída es correcta. Puedes corregir cualquier campo antes
              de guardar.
            </p>
          </div>
        )}

        {/* 2. Píldora de tipo */}
        <span
          className="inline-block rounded-full px-3 py-1 text-xs font-semibold"
          style={
            direction === 'emitida'
              ? { background: '#f0fff4', color: '#276749' }
              : { background: '#ebf8ff', color: '#2b6cb0' }
          }
        >
          {direction === 'emitida' ? '📤 Factura Emitida' : '📥 Factura Recibida'}
        </span>

        {/* 4. Empresa en la factura (caja ámbar) */}
        <div
          className="space-y-2 rounded-lg border p-3"
          style={{ borderColor: '#fbd38d', background: '#fffaf0' }}
        >
          <p className="text-xs font-bold uppercase tracking-wide" style={{ color: '#c05621' }}>
            {direction === 'recibida' ? 'Empresa en la factura (IA)' : 'Datos del emisor'}
          </p>
          <SetexField
            label={direction === 'recibida' ? 'Proveedor / Emisor' : 'Emisor (nuestra empresa)'}
            value={form.counterparty_name}
            onChange={(v) => set({ counterparty_name: v })}
            mark={confidenceMark(conf('counterparty_name'))}
          />
          <SetexField
            label={direction === 'recibida' ? 'CIF / NIF proveedor' : 'CIF / NIF emisor'}
            value={form.counterparty_tax_id}
            onChange={(v) => set({ counterparty_tax_id: v })}
            mark={confidenceMark(conf('counterparty_tax_id'))}
            mono
          />
          <CounterpartyVerdictBlock verdict={review.counterparty_verdict} />
        </div>

        {/* 5. Receptor (caja gris) */}
        <div className="space-y-1 rounded-lg border border-sx-line bg-white p-3">
          <p className="text-xs font-bold uppercase tracking-wide text-sx-ink3">
            {direction === 'recibida' ? 'Receptor (nuestra empresa)' : 'Receptor / Cliente'}
          </p>
          <p className="text-sm">{review.own.name ?? '—'}</p>
          <p className="font-mono text-sm tracking-widest">{review.own.cif ?? '—'}</p>
        </div>

        {/* 6. Fecha y Total, dos columnas */}
        <div className="grid grid-cols-2 gap-3">
          <SetexField
            label="Fecha"
            type="date"
            value={form.issue_date}
            onChange={(v) => set({ issue_date: v })}
            mark={confidenceMark(conf('issue_date'))}
          />
          <SetexField
            label="Total"
            value={form.total_amount}
            onChange={(v) => set({ total_amount: v })}
            mark={confidenceMark(conf('total_amount'))}
          />
        </div>

        {hasImbalance && (
          <p
            data-testid="warning-imbalance"
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: '#fc8181', background: '#fff5f5', color: '#c53030' }}
          >
            ⚠ Los importes no cuadran. Revisa Base, IVA, IRPF y Total antes de guardar.
          </p>
        )}

        {/* 7. Cuadro IVA (plegable, solo abierto si hay descuadre — §09 "solo se abren si hay
            anomalía") */}
        <details open={hasImbalance} className="rounded-lg border" style={{ borderColor: '#bee3f8' }}>
          <summary
            className="cursor-pointer rounded-t-lg px-3 py-2 text-sm font-semibold"
            style={{ background: '#ebf8ff', color: '#2b6cb0' }}
          >
            🧾 Desglose de IVA
          </summary>
          <div className="space-y-2 p-3" style={{ background: '#ebf8ff' }}>
            <div className="grid grid-cols-2 gap-3">
              <SetexField
                label="Base imponible"
                value={form.net_amount}
                onChange={(v) => set({ net_amount: v })}
                mark={confidenceMark(conf('net_amount'))}
              />
              <SetexField
                label="Cuota IVA"
                value={form.tax_amount}
                onChange={(v) => set({ tax_amount: v })}
                mark={confidenceMark(conf('tax_amount'))}
              />
            </div>
            {form.tax_lines.length >= 2 &&
              form.tax_lines.map((line, i) => (
                <div key={i} className="grid grid-cols-3 gap-2" data-testid={`tax-line-${i}`}>
                  <SetexField
                    label="% IVA"
                    value={line.iva_pct}
                    onChange={(v) =>
                      set({ tax_lines: form.tax_lines.map((l, j) => (j === i ? { ...l, iva_pct: v } : l)) })
                    }
                    mark="ok"
                  />
                  <SetexField
                    label="Base"
                    value={line.base}
                    onChange={(v) =>
                      set({ tax_lines: form.tax_lines.map((l, j) => (j === i ? { ...l, base: v } : l)) })
                    }
                    mark="ok"
                  />
                  <SetexField
                    label="Cuota"
                    value={line.cuota}
                    onChange={(v) =>
                      set({ tax_lines: form.tax_lines.map((l, j) => (j === i ? { ...l, cuota: v } : l)) })
                    }
                    mark="ok"
                  />
                </div>
              ))}
          </div>
        </details>

        {/* 8. Cuadro IRPF (plegable) */}
        <details className="rounded-lg border" style={{ borderColor: '#fbd38d' }}>
          <summary
            className="cursor-pointer rounded-t-lg px-3 py-2 text-sm font-semibold"
            style={{ background: '#fffaf0', color: '#c05621' }}
          >
            Retención IRPF
          </summary>
          <div className="p-3" style={{ background: '#fffaf0' }}>
            <SetexField
              label="Cuota IRPF"
              value={form.irpf_amount}
              onChange={(v) => set({ irpf_amount: v })}
              mark="ok"
            />
          </div>
        </details>

        {/* 9. Resumen, fijo, siempre visible */}
        <div
          className="space-y-1 rounded-lg border-2 bg-white p-3 text-sm"
          style={{ borderColor: '#1a365d', color: '#1a365d' }}
        >
          <p className="font-bold uppercase tracking-wide">Resumen</p>
          <div className="flex justify-between">
            <span>Base</span>
            <span>{formatCurrency(form.net_amount || null)}</span>
          </div>
          <div className="flex justify-between">
            <span>Cuota IVA</span>
            <span>{formatCurrency(form.tax_amount || null)}</span>
          </div>
          <div className="flex justify-between">
            <span>Cuota IRPF</span>
            <span>−{formatCurrency(form.irpf_amount || null)}</span>
          </div>
          <div className="flex justify-between border-t pt-1 font-bold" style={{ borderColor: '#1a365d' }}>
            <span>Total</span>
            <span>{formatCurrency(String(summaryTotal))}</span>
          </div>
        </div>

        {/* 11. Confirmar + declaración + Repetir foto */}
        <button
          type="button"
          disabled={!enabled}
          onClick={onConfirm}
          title={!enabled ? 'Corrige los errores indicados antes de guardar' : undefined}
          className="w-full rounded-md bg-gradient-to-br from-sx-brand to-sx-brand2 px-4 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? 'Guardando...' : '✓ Confirmar y guardar'}
        </button>

        <ResponsibilityCheckbox checked={responsibilityAccepted} onChange={onResponsibilityChange} />

        {/* Texto legal literal, en rojo, centrado, bajo el botón (§16, "no alterar"). */}
        <p role="alert" className="text-center text-sm font-medium" style={{ color: '#c53030' }}>
          {SETEX_CONSENT_TEXT}
        </p>
        <p className="text-center text-xs font-semibold text-red-500">{RESPONSIBILITY_NOTICE}</p>

        {confirmError && (
          <p data-testid="confirm-error" role="alert" className="text-sm text-red-600">
            {confirmError}
          </p>
        )}

        <button
          type="button"
          onClick={onRetry}
          className="w-full rounded-md border border-sx-line bg-white px-4 py-2 font-medium text-sx-ink2"
        >
          ✗ Repetir foto
        </button>
      </div>
    </div>
  )
}
