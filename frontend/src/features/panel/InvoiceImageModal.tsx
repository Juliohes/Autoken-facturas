import { Modal } from '../../shared/Modal'

// Ventana con la foto original de una factura (2026-08-01): reemplaza a la vieja URL firmada de
// MinIO (S2.7, inalcanzable desde el navegador en el despliegue real) — la imagen llega como blob
// ya autenticado (`useInvoiceImage`) y se muestra aquí, dentro de la propia app.
interface Props {
  src: string
  onClose: () => void
}

export function InvoiceImageModal({ src, onClose }: Props) {
  return (
    <Modal title="Foto de la factura" onClose={onClose} panelClassName="max-h-full !w-auto max-w-full">
        <img
          src={src}
          alt="Foto original de la factura"
          className="max-h-[85vh] max-w-full rounded bg-slate-800"
        />
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-400 bg-slate-800 px-3 py-1 text-sm text-slate-100"
          >
            Cerrar
          </button>
        </div>
    </Modal>
  )
}
