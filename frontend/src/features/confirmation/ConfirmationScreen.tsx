// Pantalla de confirmación (S2.4): el humano revisa lo que leyó la IA y confirma
// o repite la foto. Orquesta los hooks de datos y los componentes de presentación;
// la lógica (color de confianza, botón habilitado, body del confirm) vive en
// módulos puros aparte (sin monolito). Comportamientos C1-C12 de la spec.
import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import type { Direction } from '../capture/types'
import { useCurrentUser } from '../identity/useCurrentUser'
import { CounterpartyVerdictBlock } from './CounterpartyVerdictBlock'
import { Modal } from '../../shared/Modal'
import { Banner } from '../../ui'
import { FieldRow } from './FieldRow'
import { ResponsibilityCheckbox } from './ResponsibilityCheckbox'
import { isConfirmEnabled } from './confirmGate'
import { formStateToConfirmBody, initialFormState, type ConfirmFormState } from './formState'
import { availableTaxRates, taxRateLabel } from './taxLines'
import { ConfirmRejectedError, useConfirm } from './useConfirm'
import { useReview, CaptureUnreadableError, PendingOcrError } from './useReview'
import { useDraftCounterpartyVerdict } from './useDraftCounterpartyVerdict'
import { useDraftAutosave } from './useDraftAutosave'
import { ProcessingProgress } from '../processing/ProcessingProgress'
import { useUploadStatus } from '../processing/useUploadStatus'
import { useDeleteUpload } from './useDeleteUpload'
import {
  BLOCKING_REASONS,
  WARNING_IMBALANCE,
  type CounterpartyVerdict,
  type ReviewResponse,
} from './types'

// Aviso rojo de responsabilidad, SIEMPRE bajo el botón (spec §2, C9).
export const RESPONSIBILITY_NOTICE =
  'Revisa bien los datos antes de confirmar: su veracidad es responsabilidad de quien los confirma.'

interface Props {
  fileId: string
  onConfirmed: () => void
  onRetry: () => void
  onDeleted?: () => void
  /** Dirección elegida en la captura; la persistida por el backend siempre tiene prioridad. */
  direction?: Direction
}

// Mensaje mostrado en la pantalla de captura tras el redirect de C7 (constante compartida para no
// desincronizar el `navigate` de aquí con lo que espera `CaptureScreen.tsx`).
const CAPTURE_UNREADABLE_MESSAGE = 'La foto no se pudo leer. Repite la captura.'

export function ConfirmationScreen({ fileId, onConfirmed, onRetry, onDeleted = () => undefined, direction }: Props) {
  const review = useReview(fileId)
  const currentUser = useCurrentUser()
  const navigate = useNavigate()
  const location = useLocation()
  const isCaptureUnreadable = review.failureReason instanceof CaptureUnreadableError
  const isPendingOcr = review.failureReason instanceof PendingOcrError
  const uploadStatus = useUploadStatus(fileId, isPendingOcr)
  const processingStagesEnabled = currentUser.data?.feature_flags?.processing_stages_enabled !== false

  // C7: una captura ilegible nunca abre un formulario con campos vacíos ni el error genérico de
  // "No se pudo abrir esta factura" — se explica y se vuelve a capturar automáticamente.
  useEffect(() => {
    if (isCaptureUnreadable) {
      navigate(ROUTES.capture, { state: { message: CAPTURE_UNREADABLE_MESSAGE } })
    }
  }, [isCaptureUnreadable, navigate])

  if (isCaptureUnreadable) return null

  if (review.isLoading) {
    return (
      <div className="p-6 flex flex-col items-center justify-center space-y-4 text-center py-20">
        {isPendingOcr ? (
          <>
            <ProcessingProgress
              status={uploadStatus.data?.status ?? 'pending_ocr'}
              stage={processingStagesEnabled ? uploadStatus.data?.processing_stage : undefined}
              etaSecondsMin={uploadStatus.data?.eta_seconds_min}
              etaSecondsMax={uploadStatus.data?.eta_seconds_max}
            />
            <p className="sr-only">Leyendo la factura...</p>
          </>
        ) : (
          <div role="status" className="flex flex-col items-center gap-4">
            <span aria-hidden="true" className="tn-spinner" />
            <p className="text-fg font-medium">Cargando datos de revisión…</p>
            <p className="text-sm text-muted">Espera un momento, por favor.</p>
          </div>
        )}
        {isPendingOcr && <Link to={ROUTES.history} className="text-sm text-accent-strong">Volver al historial</Link>}
      </div>
    )
  }
  if (review.isError || !review.data) {
    return (
      <div className="p-6 space-y-4">
        <Banner tone="bad">No se pudo abrir esta factura. Inténtalo de nuevo.</Banner>
        <button
          type="button"
          onClick={onRetry}
          className="tn-btn tn-btn-secondary tn-btn-md"
        >
          Repetir foto
        </button>
      </div>
    )
  }

  // S6.14 C8: aviso no bloqueante de una sola vez, vía estado de navegación efímero (mismo patrón
  // que `direction` antes de S6.13) — si se recarga o se reabre desde el historial más tarde, el
  // estado ya no está y el aviso no reaparece. Decisión de diseño propia (no explícita en la spec,
  // enmendada en su §5): persistir la nitidez para que el aviso reapareciera siempre sería
  // sobredimensionar lo que es solo telemetría.
  const lowSharpness = (location.state as { lowSharpness?: boolean } | null)?.lowSharpness === true

  return (
    <ConfirmationForm
      fileId={fileId}
      review={review.data}
      onConfirmed={onConfirmed}
      onRetry={onRetry}
      onDeleted={onDeleted}
      direction={review.data.direction === undefined ? direction ?? null : review.data.direction}
      lowSharpness={lowSharpness}
    />
  )
}

interface FormProps {
  fileId: string
  review: ReviewResponse
  onConfirmed: () => void
  onRetry: () => void
  onDeleted: () => void
  direction: Direction | null
  /** S6.14 C8: aviso no bloqueante, nunca impide confirmar. */
  lowSharpness: boolean
}

/** Formulario propiamente dicho: se monta con los datos ya cargados. */
function ConfirmationForm({ fileId, review, onConfirmed, onRetry, onDeleted, direction, lowSharpness }: FormProps) {
  const confirm = useConfirm(fileId)
  const currentUser = useCurrentUser()
  const draftAutosaveEnabled = currentUser.data?.feature_flags?.draft_autosave_enabled !== false
  const [form, setForm] = useState<ConfirmFormState>(() => initialFormState(review))
  const [responsibilityAccepted, setResponsibilityAccepted] = useState(false)
  const [reviewAcknowledged, setReviewAcknowledged] = useState(false)
  const [isTest, setIsTest] = useState(false)
  const [ownTaxIdExceptionAccepted, setOwnTaxIdExceptionAccepted] = useState(false)
  const [serverVerdict, setServerVerdict] = useState<CounterpartyVerdict | null>(null)
  const [serverBlockingReasons, setServerBlockingReasons] = useState<string[] | null>(null)
  const [selectedDirection, setSelectedDirection] = useState<Direction | null>(direction)
  const [draftRevision, setDraftRevision] = useState(review.draft_revision ?? 0)
  const isAdmin = currentUser.data?.role === 'tenant_admin'
  const isUser = currentUser.data?.role === 'user'
  const draftAutosave = useDraftAutosave({
    fileId,
    form,
    direction: selectedDirection,
    revision: draftRevision,
    enabled: draftAutosaveEnabled,
    onSaved: (result) => setDraftRevision(result.revision),
  })
  const deleteUpload = useDeleteUpload(fileId)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const draftVerdict = useDraftCounterpartyVerdict({
    fileId,
    taxId: form.counterparty_tax_id,
    name: form.counterparty_name,
    initialTaxId: review.fields.counterparty_tax_id ?? '',
    initialName: review.fields.counterparty_name ?? '',
  })

  const set = (patch: Partial<ConfirmFormState>) => {
    setReviewAcknowledged(false)
    if ('counterparty_tax_id' in patch || 'counterparty_name' in patch) {
      setServerVerdict(null)
      setServerBlockingReasons(null)
    }
    setForm((prev) => ({ ...prev, ...patch }))
  }

  const initialCounterpartyReasons = new Set<string>([
    BLOCKING_REASONS.cifInvalid,
    BLOCKING_REASONS.cifNotFound,
  ])
  const counterpartyChanged =
    form.counterparty_tax_id !== (review.fields.counterparty_tax_id ?? '') ||
    form.counterparty_name !== (review.fields.counterparty_name ?? '')
  const hasCurrentDraftVerdict = counterpartyChanged && !draftVerdict.isDebouncing && draftVerdict.isSuccess
  const waitingForDraftVerdict = counterpartyChanged && !hasCurrentDraftVerdict && !serverBlockingReasons
  const blockingReasons = counterpartyChanged
    ? [
        ...review.blocking_reasons.filter((reason) => !initialCounterpartyReasons.has(reason)),
        ...(serverBlockingReasons ?? (hasCurrentDraftVerdict
          ? draftVerdict.data.blocking_reasons
          : [BLOCKING_REASONS.cifInvalid])),
      ]
    : review.blocking_reasons
  // 2026-08-08 (petición de Julio): sin caja "CIF de contraparte verificado" — un check verde
  // junto al campo, mismo estilo que las marcas de confianza. La caja se conserva para los casos
  // que sí necesitan explicación (inválido/no encontrado/nombre que no coincide/sin verificar).
  const counterpartyVerdict = serverVerdict ?? (hasCurrentDraftVerdict
    ? draftVerdict.data.counterparty_verdict
    : counterpartyChanged ? null : review.counterparty_verdict)
  const isCounterpartyVerified = counterpartyVerdict?.status === 'valid' && counterpartyVerdict.name_match !== false
  const missingOwnTaxId = review.blocking_reasons.includes(BLOCKING_REASONS.ownTaxIdMissing)
  const submitting = confirm.isPending || draftAutosave.state === 'confirming' || draftAutosave.state === 'saving'
  const enabled = isConfirmEnabled({
    blockingReasons,
    responsibilityAccepted,
    reviewAcknowledged,
    submitting,
    ownTaxIdExceptionAccepted: isUser && ownTaxIdExceptionAccepted,
  }) && selectedDirection !== null
  const blockMessages = getConfirmBlockMessages({
    blockingReasons,
    isUser,
    ownTaxIdExceptionAccepted,
    responsibilityAccepted,
    reviewAcknowledged,
    selectedDirection,
    submitting,
    waitingForDraftVerdict,
    draftVerdictError: draftVerdict.isError,
  })

  const hasImbalance = review.warnings.includes(WARNING_IMBALANCE)
  const navigate = useNavigate()

  const handleConfirm = async () => {
    if (!selectedDirection) return
    if (draftAutosaveEnabled && (draftAutosave.state === 'dirty' || draftAutosave.state === 'save_error')) {
      const saved = await draftAutosave.saveNow()
      if (!saved) return
    }
    draftAutosave.markConfirming()
    const body = formStateToConfirmBody(form, {
      direction: selectedDirection,
      responsibilityAccepted,
      ownTaxIdExceptionAccepted: isUser && ownTaxIdExceptionAccepted,
      isTest: isAdmin && isTest,
    })
    confirm.mutate(body, {
      onSuccess: () => onConfirmed(),
      onError: (error) => {
        draftAutosave.markConfirmError()
        if (error instanceof ConfirmRejectedError && error.counterpartyVerdict) {
          setServerVerdict(error.counterpartyVerdict)
          setServerBlockingReasons(error.blockingReasons ?? [BLOCKING_REASONS.cifInvalid])
        }
      },
    })
  }

  return (
    <section className="tn-panel-page mx-auto max-w-xl space-y-6 p-6">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-xl font-semibold">Revisar y confirmar</h1>
        <p data-testid="draft-save-state" className="text-xs text-muted">
          {draftSaveLabel(draftAutosave.state)}
        </p>
      </div>

      {/* S6.14 C8: aviso no bloqueante de nitidez, solo en esta primera visita (estado de
          navegación efímero, se pierde al recargar — decisión de diseño propia, spec §5). */}
      {lowSharpness && (
        <div data-testid="warning-low-sharpness">
          <Banner tone="warn">Esta foto puede estar borrosa. Revisa bien los datos antes de confirmar.</Banner>
        </div>
      )}

      {direction === null && (
        <fieldset className="space-y-2 rounded-md border p-4" style={{ borderColor: 'var(--tn-warning)' }}>
          <legend className="px-1 text-sm font-medium" style={{ color: 'var(--tn-warning)' }}>Dirección de la factura</legend>
          <p className="text-sm text-fg">Elige si la factura es recibida o emitida antes de guardar.</p>
          <div className="flex gap-3">
            <label><input type="radio" name="historical-direction" checked={selectedDirection === 'recibida'} onChange={() => setSelectedDirection('recibida')} /> Recibida</label>
            <label><input type="radio" name="historical-direction" checked={selectedDirection === 'emitida'} onChange={() => setSelectedDirection('emitida')} /> Emitida</label>
          </div>
        </fieldset>
      )}

      {/* Enmienda S6.1 §8 (2026-08-08, tras probar con Julio): 4 secciones siempre visibles, en
          vez de "3-4 campos siempre visibles + resto plegado". Solo tramos de IVA e IRPF
          conservan su propio desplegable interno (sin cambios de comportamiento ahí). */}

      <div data-testid="section-counterparty" className="space-y-3 rounded-md border border-line p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Contraparte</h2>
        <FieldRow
          name="counterparty_tax_id"
          label="CIF de contraparte"
          value={form.counterparty_tax_id}
          onChange={(v) => set({ counterparty_tax_id: v })}
          extraBadge={
            isCounterpartyVerified ? (
              <span
                data-testid="mark-counterparty-verified"
                title="CIF verificado"
                className="rounded px-1.5 py-0.5 text-xs font-semibold"
                style={{ color: 'var(--tn-success)' }}
              >
                ✓
              </span>
            ) : undefined
          }
        />
        {counterpartyVerdict && !isCounterpartyVerified && <CounterpartyVerdictBlock verdict={counterpartyVerdict} />}
        {waitingForDraftVerdict && !draftVerdict.isError && (
          <p className="text-sm text-muted">Comprobando CIF...</p>
        )}
        {counterpartyChanged && !serverVerdict && !draftVerdict.isDebouncing && draftVerdict.isError && (
          <p role="alert" className="text-sm" style={{ color: 'var(--tn-error)' }}>No se pudo verificar el CIF. Revísalo antes de guardar.</p>
        )}
        <FieldRow
          name="counterparty_name"
          label="Nombre de la contraparte"
          value={form.counterparty_name}
          onChange={(v) => set({ counterparty_name: v })}
        />
      </div>

      <div data-testid="section-amounts" className="space-y-3 rounded-md border border-line p-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">Importes</h2>
        <FieldRow
          name="net_amount"
          label="Base imponible"
          value={form.net_amount}
          onChange={(v) => set({ net_amount: v })}
        />

        {/* S6.1 C8-C12: tramos de IVA en desplegable con resumen; añadir/quitar con tasa
            cerrada {21,10,4,Sin IVA}, nunca un % libre. */}
        <details data-testid="tax-lines" className="rounded-md border border-line p-3">
          <summary className="cursor-pointer text-sm text-muted">Tramos de IVA</summary>
          <div className="mt-3 space-y-3">
            {form.tax_lines.map((line, i) => (
              <div
                key={i}
                className="space-y-2 rounded-md border border-line p-2"
                data-testid={`tax-line-${i}`}
              >
                <div className="flex items-center justify-between">
                  <span data-testid={`tax-line-${i}-summary`} className="text-sm text-muted">
                    {taxRateLabel(line.iva_pct)} · Base {line.base || '—'}
                  </span>
                  <button
                    type="button"
                    data-testid={`remove-tax-line-${i}`}
                    onClick={() => set({ tax_lines: form.tax_lines.filter((_, j) => j !== i) })}
                    className="text-xs font-semibold text-fg"
                  >
                    Quitar
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:gap-3">
                  <FieldRow
                    name={`tax_lines.${i}.base`}
                    label="Base"
                    value={line.base}
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
                className="w-full rounded-md border border-line bg-surface px-3 py-2 text-fg"
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
          onChange={(v) => set({ tax_amount: v })}
        />
        <FieldRow
          name="total_amount"
          label="Importe total"
          value={form.total_amount}
          onChange={(v) => set({ total_amount: v })}
        />

        {/* IRPF separado del IVA: si la IA lo leyó, el importe aparece ya cargado y sigue siendo
            editable; si no existe, el campo queda vacío y no se inventa nada. */}
        <details data-testid="irpf-details" className="rounded-md border border-line p-3">
          <summary className="cursor-pointer text-sm text-muted">
            IRPF{form.irpf_amount && review.fields.irpf_rate ? ` (${review.fields.irpf_rate}%)` : ''}
          </summary>
          <div className="mt-3">
            <FieldRow
              name="irpf_amount"
              label="IRPF (retención)"
              value={form.irpf_amount}
              onChange={(v) => set({ irpf_amount: v })}
            />
          </div>
        </details>

        {/* C10: descuadre aritmético -> aviso "Revisar" (no bloquea). */}
      {hasImbalance && (
          <div data-testid="warning-imbalance">
            <Banner tone="warn">El total no cuadra con el IVA.</Banner>
          </div>
        )}
      </div>

      {review.duplicate && (
        <div data-testid="warning-duplicate">
          <Banner
            tone="bad"
            action={
              <button
                type="button"
                onClick={() => navigate(`/confirmar/${review.duplicate?.uploaded_file_id}`)}
                className="tn-btn tn-btn-danger tn-btn-sm"
              >
                Revisar factura original
              </button>
            }
          >
            <p className="font-semibold">
              {review.duplicate.kind === 'confirmed'
                ? 'Esta factura ya está guardada como duplicado.'
                : 'Esta factura parece coincidir con otra ya subida.'}
            </p>
            <p>No puedes continuar con esta factura duplicada.</p>
          </Banner>
        </div>
      )}

      <div
        data-testid="section-invoice-identity"
        className="space-y-3 rounded-md border border-line p-4"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
          Fecha y número de factura
        </h2>
        <FieldRow
          name="issue_date"
          label="Fecha"
          type="date"
          value={form.issue_date}
          onChange={(v) => set({ issue_date: v })}
        />
        <FieldRow
          name="invoice_number"
          label="Número de factura"
          value={form.invoice_number}
          onChange={(v) => set({ invoice_number: v })}
        />
      </div>

      {/* Identidad propia conocida (no editable, no se puntúa; ADR-0011): al final, texto plano,
          sin caja de campo — viene del registro de la empresa, no se lee ni se confirma aquí. */}
      <div data-testid="own-identity" className="text-sm text-muted">
        <p>Empresa propia: {review.own.name ?? '—'}</p>
        <p>CIF propio: {review.own.cif ?? '—'}</p>
      </div>

      {/* 2026-08-08 (hallazgo de Julio): antes este motivo de bloqueo no tenía NINGÚN mensaje
          visible — el botón se deshabilitaba sin que el usuario supiera por qué. */}
      {missingOwnTaxId && (
        <div data-testid="warning-own-tax-id-missing">
          <Banner tone="bad">
            No se ve el CIF de {review.own.name ?? 'tu empresa'} ({review.own.cif ?? '—'}). Confirma que esta factura es suya.
          </Banner>
        </div>
      )}

      {missingOwnTaxId && isUser && (
        <label className="flex items-start gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={ownTaxIdExceptionAccepted}
            onChange={(event) => setOwnTaxIdExceptionAccepted(event.target.checked)}
          />
          Confirmo que esta factura corresponde a {review.own.name ?? 'mi empresa'} ({review.own.cif ?? '—'})
        </label>
      )}

      {/* S3.5: solo el tenant_admin puede marcar una factura como de prueba (excluida de
          informes, purgable de un clic); un empleado ni ve la casilla. */}
      {isAdmin && (
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={isTest}
            onChange={(e) => setIsTest(e.target.checked)}
          />
          Factura de prueba (no aparecerá en informes)
        </label>
      )}

      <label className="flex items-start gap-2 text-sm text-muted">
        <input
          type="checkbox"
          aria-label="He revisado todos los datos de la factura."
          checked={reviewAcknowledged}
          onChange={(event) => setReviewAcknowledged(event.target.checked)}
          className="mt-1"
        />
        He revisado todos los datos de la factura.
      </label>

      <ResponsibilityCheckbox
        checked={responsibilityAccepted}
        onChange={setResponsibilityAccepted}
      />

      {blockMessages.length > 0 && (
        <div data-testid="confirm-blockers">
          <Banner tone="warn">
            <p className="font-semibold">Para confirmar falta:</p>
            {blockMessages.map((message) => <p key={message}>{message}</p>)}
          </Banner>
        </div>
      )}

      <button
        type="button"
        disabled={!enabled}
        onClick={handleConfirm}
        className="tn-btn tn-btn-primary tn-btn-lg w-full"
      >
        Confirmar y guardar
      </button>

      <button
        type="button"
        onClick={() => setShowDeleteDialog(true)}
        disabled={deleteUpload.isPending}
        className="tn-btn tn-btn-danger tn-btn-md w-full"
      >
        Eliminar factura sin confirmar
      </button>

      {deleteUpload.isError && (
        <p data-testid="delete-error" role="alert" className="text-sm" style={{ color: 'var(--tn-error)' }}>
          {deleteUpload.error instanceof Error ? deleteUpload.error.message : 'No se pudo eliminar la factura.'}
        </p>
      )}

      {showDeleteDialog && (
        <Modal title="Eliminar factura" onClose={() => setShowDeleteDialog(false)} panelClassName="max-w-md space-y-4">
          <p className="text-muted">
            Esta factura todavía no se ha confirmado ni guardado. Se eliminará para que puedas hacerla de nuevo.
          </p>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => setShowDeleteDialog(false)}
              className="tn-btn tn-btn-secondary tn-btn-md"
            >
              Cancelar
            </button>
            <button
              type="button"
              disabled={deleteUpload.isPending}
              onClick={() => deleteUpload.mutate(undefined, {
                onSuccess: () => {
                  setShowDeleteDialog(false)
                  onDeleted()
                },
              })}
              className="tn-btn tn-btn-danger tn-btn-md"
            >
              {deleteUpload.isPending ? 'Eliminando...' : 'Sí, eliminar'}
            </button>
          </div>
        </Modal>
      )}

      {/* C9: aviso rojo, grande y legible, SIEMPRE bajo el botón. */}
      <p role="alert" className="text-center text-base font-semibold" style={{ color: 'var(--tn-error)' }}>
        {RESPONSIBILITY_NOTICE}
      </p>

      {/* C12: rechazo del servidor mostrado sin perder lo editado ni navegar. */}
      {confirm.isError && (
        <div data-testid="confirm-error">
          <Banner tone="bad">No se pudo guardar. Revisa los datos e inténtalo de nuevo.</Banner>
        </div>
      )}

      <button
        type="button"
        onClick={onRetry}
        className="tn-btn tn-btn-secondary tn-btn-md w-full"
      >
        Repetir foto
      </button>
    </section>
  )
}

function draftSaveLabel(state: ReturnType<typeof useDraftAutosave>['state']): string {
  switch (state) {
    case 'dirty': return 'Cambios pendientes'
    case 'saving': return 'Guardando borrador...'
    case 'saved': return 'Borrador guardado'
    case 'save_error': return 'No se pudo guardar el borrador'
    case 'confirming': return 'Confirmando...'
    default: return 'Borrador sin cambios'
  }
}

interface ConfirmBlockMessageOptions {
  blockingReasons: string[]
  isUser: boolean
  ownTaxIdExceptionAccepted: boolean
  responsibilityAccepted: boolean
  reviewAcknowledged: boolean
  selectedDirection: Direction | null
  submitting: boolean
  waitingForDraftVerdict: boolean
  draftVerdictError: boolean
}

function getConfirmBlockMessages(options: ConfirmBlockMessageOptions): string[] {
  if (options.submitting) return ['Estamos guardando la factura. No cierres esta pantalla.']

  const messages: string[] = []
  const effectiveReasons = new Set(options.blockingReasons)
  if (options.isUser && options.ownTaxIdExceptionAccepted) effectiveReasons.delete(BLOCKING_REASONS.ownTaxIdMissing)

  if (options.waitingForDraftVerdict) {
    effectiveReasons.delete(BLOCKING_REASONS.cifInvalid)
    effectiveReasons.delete(BLOCKING_REASONS.cifNotFound)
    messages.push('Espera a que se verifique el CIF de la contraparte.')
  } else if (options.draftVerdictError) {
    effectiveReasons.delete(BLOCKING_REASONS.cifInvalid)
    effectiveReasons.delete(BLOCKING_REASONS.cifNotFound)
    messages.push('No se pudo verificar el CIF de la contraparte. Revísalo antes de guardar.')
  }

  for (const reason of effectiveReasons) {
    if (reason === BLOCKING_REASONS.cifInvalid) messages.push('El CIF de la contraparte no es válido. Corrígelo.')
    else if (reason === BLOCKING_REASONS.cifNotFound) messages.push('No encontramos el CIF de la contraparte. Revísalo.')
    else if (reason === BLOCKING_REASONS.ownTaxIdMissing) messages.push('Confirma que la factura corresponde a tu empresa.')
    else if (reason === BLOCKING_REASONS.duplicate) messages.push('La factura está duplicada. Revisa la original o elimínala.')
    else messages.push('Hay un dato que el servidor no permite confirmar. Revisa la factura.')
  }

  if (options.selectedDirection === null) messages.push('Selecciona si la factura es recibida o emitida.')
  if (!options.reviewAcknowledged) messages.push('Marca que has revisado todos los datos de la factura.')
  if (!options.responsibilityAccepted) messages.push('Acepta la responsabilidad de los datos confirmados.')
  return messages
}
