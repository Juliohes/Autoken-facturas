import { useState } from 'react'

import { useSession } from '../session/SessionProvider'
import { useOcrLabSettings } from './useOcrLabSettings'
import { useOcrPolicy } from './useOcrPolicy'
import { useUpdateOcrLabSettings } from './useUpdateOcrLabSettings'
import { usePromoteOcrPolicy } from './usePromoteOcrPolicy'

export function PlatformSettings() {
  const { user } = useSession()
  const enabled = user?.is_admin_tech ?? false
  const policy = useOcrPolicy(enabled)
  const lab = useOcrLabSettings(enabled)
  const updateLab = useUpdateOcrLabSettings()
  const promote = usePromoteOcrPolicy()
  const [promotionOpen, setPromotionOpen] = useState(false)

  if (!enabled) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No tienes acceso a esta pantalla.
        </p>
      </div>
    )
  }

  const loading = policy.isLoading || lab.isLoading
  const error = policy.isError || lab.isError

  return (
    <section className="mx-auto max-w-3xl space-y-6 p-6 text-slate-100">
      <header>
        <h1 className="text-xl font-semibold">Ajustes de plataforma</h1>
        <p className="mt-1 text-sm text-slate-400">Producción y laboratorio OCR tienen controles separados.</p>
      </header>

      {loading && <p className="text-slate-400">Cargando configuración OCR...</p>}
      {error && <p role="alert" className="text-red-400">No se pudo cargar la configuración OCR.</p>}

      {policy.data && (
        <article className="rounded-lg border border-slate-700 bg-slate-900/60 p-5">
          <h2 className="font-semibold">Producción OCR</h2>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="text-slate-400">Primario</dt><dd>{policy.data.primary_engine} / {policy.data.primary_model}</dd></div>
            <div><dt className="text-slate-400">Fallback</dt><dd>{policy.data.fallback_enabled ? `${policy.data.fallback_engine} / ${policy.data.fallback_model}` : 'Desactivado'}</dd></div>
            <div><dt className="text-slate-400">Política</dt><dd>v{policy.data.version}</dd></div>
            <div><dt className="text-slate-400">Consenso</dt><dd>{policy.data.consensus_mode}</dd></div>
          </dl>
          <p className="mt-4 text-xs text-slate-400">La producción continúa usando esta política aunque el laboratorio automático esté apagado.</p>
          <button
            type="button"
            className="mt-4 rounded border border-sky-500/60 px-3 py-2 text-sm text-sky-200"
            onClick={() => setPromotionOpen(true)}
          >
            Promover esta combinación a producción
          </button>
          {promotionOpen && (
            <div role="dialog" aria-modal="true" className="mt-4 rounded border border-slate-600 bg-slate-950 p-4">
              <h3 className="font-medium">Confirmar promoción</h3>
              <p className="mt-2 text-sm text-slate-400">Se registrará la política anterior, la nueva política, el actor y la fecha.</p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  className="rounded bg-sky-600 px-3 py-2 text-sm text-white disabled:opacity-50"
                  disabled={promote.isPending}
                  onClick={() => {
                    if (!policy.data) return
                    promote.mutate({ ...policy.data, version: policy.data.version + 1 })
                    setPromotionOpen(false)
                  }}
                >
                  Confirmar promoción
                </button>
                <button type="button" className="rounded border border-slate-600 px-3 py-2 text-sm" onClick={() => setPromotionOpen(false)}>
                  Cancelar
                </button>
              </div>
            </div>
          )}
          {promote.isError && <p role="alert" className="mt-3 text-sm text-red-400">No se pudo promover la combinación.</p>}
        </article>
      )}

      {lab.data && (
        <article className="rounded-lg border border-slate-700 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold">Laboratorio</h2>
              <p className="mt-1 text-sm text-slate-400">Las llamadas automáticas de benchmark permanecen aisladas de producción.</p>
            </div>
            <button
              type="button"
              className="rounded border border-amber-500/60 px-3 py-2 text-sm text-amber-200 disabled:opacity-50"
              disabled={updateLab.isPending || !lab.data.auto_benchmark_enabled}
              onClick={() => updateLab.mutate({ ...lab.data, auto_benchmark_enabled: false })}
            >
              Desactivar laboratorio automático
            </button>
          </div>
          <label className="mt-5 flex items-center gap-3 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={lab.data.lab_visible}
              disabled={updateLab.isPending}
              onChange={(event) => updateLab.mutate({ ...lab.data, lab_visible: event.target.checked })}
            />
            Mostrar laboratorio en el panel admin-tech
          </label>
          <p className="mt-3 text-sm text-slate-300">
            Benchmark automático: <strong>{lab.data.auto_benchmark_enabled ? 'Activado' : 'Desactivado'}</strong>
          </p>
          <p className="mt-2 text-xs text-slate-400">Motores: {lab.data.benchmark_engines.join(', ')}. Variantes: {lab.data.benchmark_variants.join(', ')}.</p>
          {updateLab.isError && <p role="alert" className="mt-3 text-sm text-red-400">No se pudo cambiar el laboratorio.</p>}
        </article>
      )}
    </section>
  )
}
