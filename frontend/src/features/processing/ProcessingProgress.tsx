import { progressModel } from './progressModel'

interface Props {
  status: string
  stage?: string | null
  etaSecondsMin?: number | null
  etaSecondsMax?: number | null
}

export function ProcessingProgress({ status, stage, etaSecondsMin, etaSecondsMax }: Props) {
  const model = progressModel(status, stage)
  return (
    <div className="w-full max-w-md space-y-4 text-center" data-testid="processing-progress">
      <div
        className="h-2 overflow-hidden rounded-full bg-slate-700"
        role="progressbar"
        aria-label="Progreso de la lectura"
        aria-valuemin={0}
        aria-valuemax={100}
        {...(model.percent === null ? {} : { 'aria-valuenow': model.percent })}
      >
        {model.percent !== null && (
          <div
            className="h-full rounded-full bg-emerald-400 transition-[width] duration-500"
            style={{ width: `${model.percent}%` }}
          />
        )}
      </div>
      <div aria-live="polite">
        <p className="font-medium text-slate-100">{model.message}</p>
        {model.subtext && <p className="text-sm text-slate-400">{model.subtext}</p>}
        {etaSecondsMin != null && etaSecondsMax != null && (
          <p className="mt-2 text-sm text-slate-400">
            Aproximadamente {etaSecondsMin}–{etaSecondsMax} s
          </p>
        )}
      </div>
    </div>
  )
}
