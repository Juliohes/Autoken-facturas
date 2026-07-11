"""Contexto `invoice_intake` (S2.1): intake seguro de ficheros de factura.

El empleado sube una factura (foto o PDF); antes de llegar al OCR (S2.3) el fichero entra de forma
segura y trazable: verificado por su MIME real (número mágico), pasado por antivirus (fail-closed),
acotado en tamaño, sin duplicar por empresa, y guardado en object storage aislado por asesoría
(bucket por tenant). Ver `docs/specs/S2.1-upload-seguro.md` y ADR-0015.
"""
