"""Construcción del ZIP de export de un tenant (S4.7): función pura, sin sesión de BD ni HTTP.

Mismo criterio que `reporting/xlsx.py` (S3.2): quien orquesta (`service.py`) reúne los datos, este
módulo solo los convierte a bytes. Un fichero JSON por tabla (`{tabla}.json`) más una carpeta
`files/` con el contenido real de cada fichero subido.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

# Tablas con datos de un tenant, en el orden en que se escriben al ZIP (S4.7 §0, mismo inventario
# ya confirmado en S4.4: cascada FK hasta `tenants.id`, excepto `cif_lookups`, caché global sin
# `tenant_id`, ADR-0011).
TENANT_TABLES = (
    "tenant_branding",
    "users",
    "companies",
    "memberships",
    "uploaded_files",
    "uploaded_file_pages",
    "ocr_extractions",
    "counterparties",
    "invoices",
    "invoice_tax_lines",
    "ocr_corrections",
    "invoice_edits",
    "audit_log",
)

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}


def extension_for_content_type(content_type: str) -> str:
    """Extensión de fichero para `content_type` (S4.7 §0 decisión 7). Desconocido -> sin
    extensión."""
    return _CONTENT_TYPE_EXTENSIONS.get(content_type, "")


def _json_default(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"No se sabe serializar a JSON: {type(value)!r}")


def build_tenant_export_zip(
    tables: Mapping[str, list[dict[str, Any]]],
    files: list[tuple[str, bytes]],
) -> bytes:
    """Construye el ZIP completo: `{tabla}.json` por cada tabla + `files/{nombre}` por cada fichero.

    `tables` debe traer una entrada por cada nombre de `TENANT_TABLES` (aunque sea lista vacía, spec
    C8: un tenant sin datos no falla, solo produce JSONs vacíos). `files` es una lista de
    `(nombre_dentro_del_zip, contenido)`.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for table in TENANT_TABLES:
            rows = tables.get(table, [])
            zip_file.writestr(f"{table}.json", json.dumps(rows, default=_json_default, indent=2))
        for name, content in files:
            zip_file.writestr(f"files/{name}", content)
    return buffer.getvalue()
