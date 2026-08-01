"""Construcción del fichero Excel del export del panel (S3.2, spec §2/§3 C4).

Módulo de presentación puro (sin sesión de BD, sin HTTP): toma las filas ya resueltas por el
servicio y devuelve los bytes del `.xlsx`. Separado del router para que sea testable sin cliente
ASGI y del servicio para no mezclar "qué facturas" con "cómo se ven en una hoja de cálculo".
"""

from __future__ import annotations

import io

from openpyxl import Workbook

from reporting.service import ExportItem

_HEADERS = [
    "Empresa",
    "Fecha",
    "Proveedor",
    "CIF proveedor",
    "Base",
    "IVA",
    "Total",
    "IRPF",
    "Tramos IVA",
    "Confirmado por",
]


def _cell(value: object) -> object:
    """`None` -> celda vacía; el resto tal cual (openpyxl ya sabe escribir `Decimal`/`date`)."""
    return "" if value is None else value


# Caracteres que openpyxl (y Excel/LibreOffice al abrir) interpretan como el inicio de una fórmula.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _text_cell(value: str | None) -> str:
    """Celda de texto segura: `None` -> vacía; neutraliza una posible inyección de fórmula.

    `counterparty_name` (y el resto de texto libre de esta fila) puede venir del OCR de la factura
    de un TERCERO: es dato no confiable. Si un `str` empieza por `=`/`+`/`-`/`@` (o tab/retorno de
    carro), openpyxl lo escribe como fórmula real, que Excel/LibreOffice ejecutaría al abrir el
    fichero (fuga de datos vía `=WEBSERVICE(...)`, phishing vía `=HYPERLINK(...)`...). Anteponer un
    apóstrofo fuerza texto literal, nunca fórmula.
    """
    if not value:
        return ""
    if value[0] in _FORMULA_TRIGGERS:
        return f"'{value}"
    return value


def _tax_lines_cell(item: ExportItem) -> str:
    """Resumen de los tramos de IVA en una sola celda (spec §2), p. ej. "21% (100,00 → 21,00)"."""
    if not item.tax_lines:
        return ""
    return ", ".join(
        f"{_cell(line.iva_pct)}% ({_cell(line.base)} → {_cell(line.cuota)})"
        for line in item.tax_lines
    )


def build_export_workbook(items: list[ExportItem]) -> bytes:
    """Construye el `.xlsx` del export: cabecera + una fila por factura (spec §2/§3 C1/C4)."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Facturas"
    sheet.append(_HEADERS)
    for item in items:
        sheet.append(
            [
                _text_cell(item.company_name),
                _cell(item.issue_date),
                _text_cell(item.counterparty_name),
                _text_cell(item.counterparty_tax_id),
                _cell(item.net_amount),
                _cell(item.tax_amount),
                _cell(item.total_amount),
                _cell(item.irpf_amount),
                _text_cell(_tax_lines_cell(item)),
                _text_cell(item.confirmed_by_email),
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
