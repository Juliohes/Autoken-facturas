// Laboratorio OCR (S6.2): diagnóstico por factura, solo panel de plataforma (admin-tech). Elige un
// tenant -> lista sus facturas confirmadas (solo lectura) -> "Ver" (la foto) / "Laboratorio" (las 3
// lecturas + comparativa de modelos). El panel de facturas de cada tenant no cambia en nada (C3):
// esta pantalla no importa nada de `features/panel`, salvo `InvoiceImageModal` (presentación pura,
// sin acoplarse a datos tenant-scoped).
import { useState } from 'react'

import { formatCurrency, formatDateTime } from '../../shared/format'
import { InvoiceImageModal } from '../panel/InvoiceImageModal'
import { useSession } from '../session/SessionProvider'
import type { LabDetail } from './labTypes'
import { useInvoiceLab } from './useInvoiceLab'
import { useTenantInvoiceImage } from './useTenantInvoiceImage'
import { useTenantInvoices } from './useTenantInvoices'
import { useTenants } from './useTenants'

export function PlatformLab() {
  const { user } = useSession()
  const [tenantId, setTenantId] = useState<string | null>(null)
  const [labFileId, setLabFileId] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)

  const isAdminTech = user?.is_admin_tech ?? false
  const tenants = useTenants(isAdminTech)
  const invoices = useTenantInvoices(isAdminTech ? tenantId : null)
  const lab = useInvoiceLab(isAdminTech ? tenantId : null, labFileId)
  const image = useTenantInvoiceImage()

  // C1: un platform_admin sin el flag nunca ve el selector ni dispara ningún GET (evita un 403
  // predecible), aunque entre a la URL a mano — la ruta ya está protegida por rol (app/routes.ts).
  if (!isAdminTech) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No tienes acceso a esta pantalla.
        </p>
      </div>
    )
  }

  const handleView = (fileId: string) => {
    if (!tenantId) return
    image.mutate({ tenantId, fileId }, { onSuccess: (url) => setImageUrl(url) })
  }

  const closeImage = () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    setImageUrl(null)
    image.reset()
  }

  const rows = invoices.data ?? []

  return (
    <section className="mx-auto max-w-5xl space-y-4 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Laboratorio OCR</h1>
      <p className="text-sm text-slate-400">
        Diagnóstico por factura: Lectura 1 (lo que leyó la IA), Lectura 2 (tras los ajustes
        internos), Lectura 3 (lo guardado tras tus cambios) y la comparativa de modelos. Solo
        lectura, herramienta interna temporal.
      </p>

      <label className="flex max-w-xs flex-col gap-1 text-sm text-slate-300">
        Tenant
        <select
          aria-label="Tenant"
          value={tenantId ?? ''}
          onChange={(e) => {
            setTenantId(e.target.value || null)
            setLabFileId(null)
          }}
          className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
        >
          <option value="">Elige un tenant…</option>
          {(tenants.data ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>

      {tenantId && invoices.isLoading && <p className="text-slate-400">Cargando facturas…</p>}
      {tenantId && invoices.isError && (
        <p role="alert" className="text-red-400">
          No se pudieron cargar las facturas de este tenant.
        </p>
      )}
      {tenantId && !invoices.isLoading && !invoices.isError && rows.length === 0 && (
        <p className="text-slate-400">Este tenant no tiene facturas confirmadas todavía.</p>
      )}

      {tenantId && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="p-2">Empresa</th>
                <th className="p-2">Proveedor</th>
                <th className="p-2">Fecha</th>
                <th className="p-2">Total</th>
                <th className="p-2">Confirmada</th>
                <th className="p-2">Ver</th>
                <th className="p-2">Laboratorio</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {rows.map((row) => (
                <tr key={row.id} data-testid="lab-invoice-row">
                  <td className="p-2">{row.company_name}</td>
                  <td className="p-2">{row.counterparty_name ?? '—'}</td>
                  <td className="p-2">{row.issue_date ?? '—'}</td>
                  <td className="p-2">{formatCurrency(row.total_amount)}</td>
                  <td className="p-2">{formatDateTime(row.confirmed_at)}</td>
                  <td className="p-2">
                    <button
                      type="button"
                      onClick={() => handleView(row.uploaded_file_id)}
                      className="text-emerald-400 underline"
                    >
                      Ver
                    </button>
                  </td>
                  <td className="p-2">
                    <button
                      type="button"
                      onClick={() => setLabFileId(row.uploaded_file_id)}
                      className="text-emerald-400 underline"
                    >
                      Laboratorio
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {labFileId && lab.isLoading && <p className="text-slate-400">Cargando laboratorio…</p>}
      {labFileId && lab.isError && (
        <p role="alert" className="text-red-400">
          No se pudo cargar el laboratorio de esta factura.
        </p>
      )}
      {labFileId && lab.data && (
        <LabDetailModal detail={lab.data} onClose={() => setLabFileId(null)} />
      )}

      {imageUrl && <InvoiceImageModal src={imageUrl} onClose={closeImage} />}
      {image.isError && (
        <p role="alert" className="text-sm text-red-400">
          No se pudo cargar la imagen de la factura.
        </p>
      )}
    </section>
  )
}

function scalarFields(fields: Record<string, unknown>): [string, unknown][] {
  return Object.entries(fields).filter(
    ([, value]) => value === null || typeof value !== 'object',
  )
}

/** Tramos de IVA de la Lectura 2 (`ReviewTaxLine[]`, claves `rate`/`base`/`cuota`) o de la Lectura 3
 * (`_invoice_dict`, claves `iva_pct`/`base`/`cuota`): `scalarFields` los descarta por ser un array,
 * así que se muestran aparte (hallazgo de auditoría: quedaban invisibles en ambas lecturas, justo
 * el dato más reciente y complejo del formulario, S6.1). */
function TaxLinesList({ value }: { value: unknown }) {
  if (!Array.isArray(value)) return null
  if (value.length === 0) {
    return (
      <li>
        <span className="font-medium">tax_lines:</span> sin tramos
      </li>
    )
  }
  return (
    <li>
      <span className="font-medium">tax_lines:</span>
      <ul className="ml-4 list-disc space-y-0.5">
        {value.map((line: Record<string, unknown>, i) => {
          const rate = line.rate ?? line.iva_pct
          return (
            <li key={i}>
              {String(rate ?? '—')}%: base {String(line.base ?? '—')}, cuota{' '}
              {String(line.cuota ?? '—')}
            </li>
          )
        })}
      </ul>
    </li>
  )
}

interface LabDetailProps {
  detail: LabDetail
  onClose: () => void
}

// Ventana emergente (2026-08-09, a petición de Julio: "quiero que aparezca en una ventana
// emergente, no abajo"), mismo patrón que `TaxLinesModal`/`InvoiceImageModal` (`role="dialog"`,
// fondo oscuro, clic fuera cierra). `LabDetailView` no cambia por dentro: solo se envuelve.
function LabDetailModal({ detail, onClose }: LabDetailProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Laboratorio de esta factura"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <LabDetailView detail={detail} onClose={onClose} />
      </div>
    </div>
  )
}

function LabDetailView({ detail, onClose }: LabDetailProps) {
  return (
    <div className="space-y-6 rounded-lg border border-slate-700 bg-slate-800 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Laboratorio de esta factura</h2>
        <button type="button" onClick={onClose} className="text-sm text-slate-400 underline">
          Cerrar
        </button>
      </div>

      <section data-testid="lab-reading-1" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Lectura 1 — lo que leyó la IA</h3>
        {detail.reading_1 ? (
          <>
            {/* N=1 hoy (ADR-0016): el mismo motor produjo todos los campos de esta lectura, se
                muestra así tal cual (spec C7), sin inventar una granularidad por campo que el
                sistema no tiene todavía. */}
            <p className="text-xs text-slate-400">
              Motor: {detail.reading_1.engine} ({detail.reading_1.model})
            </p>
            <pre className="max-h-64 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-300">
              {JSON.stringify(detail.reading_1.raw, null, 2)}
            </pre>
          </>
        ) : (
          <p className="text-slate-400">Sin lectura cruda disponible para esta factura.</p>
        )}
      </section>

      <section data-testid="lab-reading-2" className="space-y-2">
        <h3 className="font-semibold text-slate-200">
          Lectura 2 — tras los ajustes internos (reglas actuales)
        </h3>
        <p className="text-xs text-slate-500">
          Recalculada ahora mismo con el rol más restrictivo (no necesariamente el rol real de quien
          confirmó en su día): puede mostrar un motivo de bloqueo que en la confirmación real no se
          disparó.
        </p>
        {detail.reading_2 ? (
          <>
            <p className="text-sm text-slate-300">
              Veredicto CIF de contraparte:{' '}
              <span className="font-medium">{detail.reading_2.counterparty_verdict.status}</span>
            </p>
            <p className="text-xs text-slate-400">
              Identidad propia conocida (no leída por IA, ADR-0011): {detail.reading_2.own.name ?? '—'}{' '}
              ({detail.reading_2.own.cif ?? '—'})
            </p>
            <ul className="space-y-1 text-sm text-slate-300">
              {scalarFields(detail.reading_2.fields as unknown as Record<string, unknown>).map(
                ([field, value]) => (
                  <li key={field}>
                    <span className="font-medium">{field}:</span>{' '}
                    {value === null || value === '' ? 'No leído' : String(value)}{' '}
                    <span className="text-xs text-slate-500">
                      (confianza: {detail.reading_2?.confidences[field] ?? 'sin dato'})
                    </span>
                  </li>
                ),
              )}
              <TaxLinesList value={detail.reading_2.fields.tax_lines} />
            </ul>
            {detail.reading_2.blocking_reasons.length > 0 && (
              <p className="text-sm text-red-400">
                Motivos de bloqueo: {detail.reading_2.blocking_reasons.join(', ')}
              </p>
            )}
            {detail.reading_2.warnings.length > 0 && (
              <p className="text-sm text-yellow-400">
                Avisos: {detail.reading_2.warnings.join(', ')}
              </p>
            )}
          </>
        ) : (
          <p className="text-slate-400">Sin lectura disponible para esta factura.</p>
        )}
      </section>

      <section data-testid="lab-reading-3" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Lectura 3 — lo guardado tras tus cambios</h3>
        <ul className="space-y-1 text-sm text-slate-300">
          {scalarFields(detail.reading_3.invoice).map(([field, value]) => (
            <li key={field}>
              <span className="font-medium">{field}:</span> {String(value ?? '—')}
            </li>
          ))}
          <TaxLinesList value={detail.reading_3.invoice.tax_lines} />
        </ul>
        {detail.reading_3.has_corrections ? (
          <table className="w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="p-1">Campo</th>
                <th className="p-1">Leído por la IA</th>
                <th className="p-1">Guardado por el humano</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {detail.reading_3.corrections.map((c) => (
                <tr key={c.field}>
                  <td className="p-1">{c.field}</td>
                  <td className="p-1">{c.ai_value ?? '—'}</td>
                  <td className="p-1">{c.human_value ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-400">Sin correcciones: el humano confirmó tal cual lo leyó la IA.</p>
        )}
      </section>

      <section data-testid="lab-ranking" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Comparativa de modelos</h3>
        {detail.ranking_available ? (
          <table className="w-full text-left text-sm">
            <thead className="text-slate-400">
              <tr>
                <th className="p-1">Motor</th>
                <th className="p-1">Puntuación</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {detail.ranking.map((row) => (
                <tr key={row.engine}>
                  <td className="p-1">{row.engine}</td>
                  <td className="p-1">{row.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-400">
            Sin datos de comparativa para esta factura (el experimento no estaba encendido cuando
            se procesó).
          </p>
        )}
      </section>
    </div>
  )
}
