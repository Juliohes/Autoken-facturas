// Sección "Facturas de prueba" de la pantalla Empresas (S3.5): un botón, confirmación nativa del
// navegador (la purga es irreversible, spec S3.5 decisión 8: sin listado previo) y el resultado.
import { useState } from 'react'

import { usePurgeTestInvoices } from './usePurgeTestInvoices'

const CONFIRM_MESSAGE =
  'Esto borra TODAS las facturas de prueba de la asesoría (y sus ficheros originales). ' +
  'No se puede deshacer. ¿Continuar?'

export function PurgeTestInvoices() {
  const purge = usePurgeTestInvoices()
  const [lastResult, setLastResult] = useState<number | null>(null)

  const handlePurge = () => {
    if (!window.confirm(CONFIRM_MESSAGE)) return
    purge.mutate(undefined, { onSuccess: (purged) => setLastResult(purged) })
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Facturas de prueba</h2>
      <p className="text-sm text-slate-400">
        Las facturas marcadas como prueba nunca aparecen en el panel, el histórico ni el export.
        Puedes borrarlas todas de una vez cuando ya no las necesites.
      </p>
      <button
        type="button"
        onClick={handlePurge}
        disabled={purge.isPending}
        className="rounded-md border border-red-500 px-4 py-2 text-red-400 disabled:opacity-40"
      >
        {purge.isPending ? 'Purgando…' : 'Purgar facturas de prueba'}
      </button>
      {purge.isError && (
        <p role="alert" className="text-sm text-red-400">
          {purge.error instanceof Error ? purge.error.message : 'No se pudo purgar.'}
        </p>
      )}
      {lastResult !== null && !purge.isError && (
        <p className="text-sm text-slate-400">
          {lastResult === 0
            ? 'No había ninguna factura de prueba.'
            : `Se ${lastResult === 1 ? 'ha borrado 1 factura' : `han borrado ${lastResult} facturas`} de prueba.`}
        </p>
      )}
    </section>
  )
}
