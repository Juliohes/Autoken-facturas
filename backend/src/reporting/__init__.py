"""Contexto `reporting` (S3.1): panel de facturas de la asesoría, de solo lectura (CQRS-light).

Consulta datos de otros contextos (`invoices`/`invoice_tax_lines` de `invoicing`,
`uploaded_files` de `invoice_intake`) filtrados, ordenados y paginados; no los posee ni escribe en
ellos. Ver ADR-0017 para la justificación de este patrón.
"""
