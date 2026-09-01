import { Modal } from '../../shared/Modal'

interface Props {
  onReview: () => void
  onClose: () => void
}

export function PostConfirmDialog({ onReview, onClose }: Props) {
  return (
    <Modal title="Factura guardada" onClose={onClose} panelClassName="tn-liquid-glass max-w-md space-y-4">
      <p className="text-slate-300">
        Quedan facturas pendientes de revisión. ¿Quieres revisar la siguiente?
      </p>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-cyan-100/40 px-4 py-2 text-slate-100"
        >
          No, volver a mis facturas
        </button>
        <button
          type="button"
          onClick={onReview}
          className="tn-primary-action rounded-md px-4 py-2 font-semibold"
        >
          Sí, revisar
        </button>
      </div>
    </Modal>
  )
}
