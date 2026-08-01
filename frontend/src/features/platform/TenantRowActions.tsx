// Acciones de una fila del panel de plataforma (S4.4 demo + S4.7 ciclo de vida), extraídas de
// PlatformTenants.tsx tras la auditoría de S4.7 (la celda había crecido a ~100 líneas mezclando 4
// flujos de mutación + el estado local del diálogo de borrado). El estado de "¿está esta fila
// pidiendo el slug de confirmación?" vive aquí, por fila, en vez de coordinado desde el padre: no
// hace falta que solo una fila pueda tener el diálogo abierto a la vez.
import { useState } from 'react'

import { MutationErrorBanner } from './MutationErrorBanner'
import { useConvertToProduction } from './useConvertToProduction'
import { useDeleteTenant } from './useDeleteTenant'
import { useExportTenant } from './useExportTenant'
import { usePurgeTenant } from './usePurgeTenant'
import { useReactivateTenant } from './useReactivateTenant'
import { useSuspendTenant } from './useSuspendTenant'
import type { Tenant } from './types'

const PURGE_CONFIRM_MESSAGE =
  'Esto borra el tenant demo por completo (empresas, facturas, ficheros). No se puede deshacer. ' +
  '¿Continuar?'

const buttonClass =
  'rounded border border-slate-600 px-2 py-1 text-xs text-slate-100 disabled:opacity-40'
const dangerButtonClass =
  'rounded border border-red-500 px-2 py-1 text-xs text-red-400 disabled:opacity-40'

export function TenantRowActions({ tenant }: { tenant: Tenant }) {
  const convertToProduction = useConvertToProduction()
  const purgeTenant = usePurgeTenant()
  const suspendTenant = useSuspendTenant()
  const reactivateTenant = useReactivateTenant()
  const exportTenant = useExportTenant()
  const deleteTenant = useDeleteTenant()
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [confirmSlugInput, setConfirmSlugInput] = useState('')

  const handlePurge = () => {
    if (!window.confirm(PURGE_CONFIRM_MESSAGE)) return
    purgeTenant.mutate(tenant.id)
  }

  const handleExport = () => {
    exportTenant.mutate(tenant.id, {
      onSuccess: (data) => window.open(data.download_url, '_blank', 'noopener,noreferrer'),
    })
  }

  const cancelDeleteConfirm = () => {
    setConfirmingDelete(false)
    setConfirmSlugInput('')
  }

  const handleConfirmDelete = () => {
    deleteTenant.mutate(
      { tenantId: tenant.id, confirmSlug: confirmSlugInput },
      { onSuccess: cancelDeleteConfirm },
    )
  }

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        {tenant.is_demo && (
          <>
            <button
              type="button"
              onClick={() => convertToProduction.mutate(tenant.id)}
              disabled={convertToProduction.isPending}
              className={buttonClass}
            >
              Convertir a producción
            </button>
            <button
              type="button"
              onClick={handlePurge}
              disabled={purgeTenant.isPending}
              className={dangerButtonClass}
            >
              Purgar
            </button>
          </>
        )}
        {tenant.status === 'active' ? (
          <button
            type="button"
            onClick={() => suspendTenant.mutate(tenant.id)}
            disabled={suspendTenant.isPending}
            className={buttonClass}
          >
            Suspender
          </button>
        ) : (
          <button
            type="button"
            onClick={() => reactivateTenant.mutate(tenant.id)}
            disabled={reactivateTenant.isPending}
            className={buttonClass}
          >
            Reactivar
          </button>
        )}
        <button
          type="button"
          onClick={handleExport}
          disabled={exportTenant.isPending}
          className={buttonClass}
        >
          {exportTenant.isPending ? 'Exportando…' : 'Exportar'}
        </button>
        {confirmingDelete ? (
          <div className="flex flex-col gap-1">
            {/* Texto visible aparte del placeholder: el placeholder es del mismo color casi que el
                texto ya escrito, así que a simple vista parece "ya relleno" aunque el campo esté
                vacío (confusión real de Julio, 2026-08-01) y el botón se vea bloqueado sin motivo
                aparente. */}
            <span className="text-xs text-slate-400">
              Escribe &quot;{tenant.slug}&quot; para confirmar:
            </span>
            <div className="flex flex-wrap items-center gap-1">
              <input
                type="text"
                value={confirmSlugInput}
                onChange={(e) => setConfirmSlugInput(e.target.value)}
                placeholder={tenant.slug}
                aria-label={`Escribe "${tenant.slug}" para confirmar el borrado`}
                className="w-24 rounded border border-slate-600 bg-slate-800 px-1 py-1 text-xs placeholder:text-slate-600"
              />
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={confirmSlugInput !== tenant.slug || deleteTenant.isPending}
                className={dangerButtonClass}
              >
                Confirmar borrado
              </button>
              <button type="button" onClick={cancelDeleteConfirm} className={buttonClass}>
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            className={dangerButtonClass}
          >
            Borrar
          </button>
        )}
      </div>
      <MutationErrorBanner mutation={convertToProduction} fallback="No se pudo convertir a producción." />
      <MutationErrorBanner mutation={purgeTenant} fallback="No se pudo purgar." />
      <MutationErrorBanner mutation={suspendTenant} fallback="No se pudo suspender." />
      <MutationErrorBanner mutation={reactivateTenant} fallback="No se pudo reactivar." />
      <MutationErrorBanner mutation={exportTenant} fallback="No se pudo exportar." />
      <MutationErrorBanner mutation={deleteTenant} fallback="No se pudo borrar." />
    </div>
  )
}
