"""Trabajos del worker asíncrono (arq): OCR de facturas y su cableado (S2.3).

`jobs.ocr` es invocable directamente (los tests ejecutan la coroutine sin arq corriendo);
`jobs.worker` define el `WorkerSettings` de arq y `jobs.queue` encola trabajos best-effort.
"""
