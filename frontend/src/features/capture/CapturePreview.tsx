export type CapturePreviewStatus = 'idle' | 'uploading' | 'saved'

export interface CapturePreviewProps {
  previewUrl: string
  status: CapturePreviewStatus
  error?: string | null
  onRepeat: () => void
  onUse: () => void
}

export function CapturePreview({ previewUrl, status, error = null, onRepeat, onUse }: CapturePreviewProps) {
  const busy = status === 'uploading' || status === 'saved'
  return (
    <section aria-label="Vista previa de la captura" className="mx-auto flex max-w-xl flex-col items-center gap-5 p-6 pt-10 text-slate-100">
      <div className="w-full overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
        <img src={previewUrl} alt="Vista previa de la factura" className="max-h-[65vh] w-full object-contain" />
      </div>
      <h1 className="text-xl font-semibold">Revisar foto</h1>
      {status === 'uploading' && <p className="font-medium">Guardando factura…</p>}
      {status === 'saved' && <p className="font-medium text-emerald-300">✓ Guardada</p>}
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      {status !== 'saved' && (
        <div className="flex w-full gap-3">
          <button type="button" onClick={onRepeat} disabled={busy} className="flex-1 rounded-md border border-slate-600 px-4 py-3 font-medium disabled:opacity-40">Repetir</button>
          <button type="button" onClick={onUse} disabled={busy} className="flex-1 rounded-md bg-emerald-600 px-4 py-3 font-semibold text-white disabled:opacity-40">Usar foto</button>
        </div>
      )}
    </section>
  )
}
