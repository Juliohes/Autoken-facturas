"""Construcción del fichero Excel del export del panel (S3.2, spec §2/§3 C4).

Módulo de presentación puro (sin sesión de BD, sin HTTP): toma las filas ya resueltas por el
servicio y devuelve los bytes del `.xlsx`. Separado del router para que sea testable sin cliente
ASGI y del servicio para no mezclar "qué facturas" con "cómo se ven en una hoja de cálculo".
"""

from __future__ import annotations

import io
from decimal import Decimal

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


# Traduce "1,234.56" (salida de f"{...:,.2f}", coma de millar/punto decimal en inglés) a
# "1.234,56" (español) intercambiando los dos caracteres a la vez — un `.replace()` encadenado
# pisaría el primer cambio con el segundo.
_EN_TO_ES_SEPARATORS = str.maketrans(",.", ".,")


def _format_amount(value: Decimal | None) -> str:
    """Importe con coma decimal y punto de millar (formato español), igual que el panel
    (`shared/format.ts::formatCurrency`) — nunca con punto, sin importar el idioma con el que se
    abra el Excel (2026-08-01, pregunta de Julio: un número real en una celda numérica se muestra
    según el idioma del programa que lo abre, no según el fichero; forzar el separador exige texto,
    no una celda numérica — aquí se prioriza que se vea siempre igual sobre poder sumarla en Excel).
    `None` -> celda vacía.
    """
    if value is None:
        return ""
    return f"{value:,.2f}".translate(_EN_TO_ES_SEPARATORS)


def _tax_lines_cell(item: ExportItem) -> str:
    """Resumen de los tramos de IVA en una sola celda (spec §2), p. ej. "21% (100,00 → 21,00)".

    Antes de 2026-08-01 interpolaba el `Decimal` tal cual (`str(Decimal(...))`, con punto) pese a
    que este mismo comentario ya prometía coma — nunca se detectó porque ningún test comprobaba el
    contenido real de esta celda, solo su presencia. `_format_amount` corrige ambas cosas a la vez.
    """
    if not item.tax_lines:
        return ""
    return ", ".join(
        f"{_cell(line.iva_pct)}% ({_format_amount(line.base)} → {_format_amount(line.cuota)})"
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
                _text_cell(_format_amount(item.net_amount)),
                _text_cell(_format_amount(item.tax_amount)),
                _text_cell(_format_amount(item.total_amount)),
                _text_cell(_format_amount(item.irpf_amount)),
                _text_cell(_tax_lines_cell(item)),
                _text_cell(item.confirmed_by_email),
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
