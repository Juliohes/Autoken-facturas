"""Contrato común de los motores OCR del bench y utilidades compartidas.

Define:

- :class:`OcrEngine`: el protocolo que implementa cada motor (un método ``extract``).
- :class:`EngineError`: error de un motor que el bench captura y registra como fallo del caso.
- :func:`encode_image`: lee una factura y la devuelve como *data URI* base64 con su MIME.
- :func:`build_extraction_messages`: construye el prompt de chat-visión común a los motores
  estilo OpenAI (system + user con texto e imagen). El prompt es deliberadamente estricto con
  la regla anti-alucinación (§1 del plan): campo no legible = ``null``, nunca inventado.
- :func:`parse_invoice_json`: convierte la respuesta JSON del modelo en
  :class:`~ocr.bench.schema.InvoiceFields`, tolerando vallas ```` ```json ```` y campos
  ausentes, y validando los números con :class:`~decimal.Decimal`.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol, runtime_checkable

from ocr.bench.schema import EngineResult, InvoiceFields, TaxLine

# MIME por extensión. Los motores de visión estilo OpenAI aceptan imágenes; el PDF debe
# rasterizarse antes (ver _MIME_BY_SUFFIX y la nota de PDF en encode_image).
_MIME_BY_SUFFIX: Mapping[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# Campos de texto y numéricos que el modelo debe devolver en el JSON de nivel superior.
_STR_FIELDS: tuple[str, ...] = (
    "numero",
    "fecha",
    "emisor_nombre",
    "emisor_nif",
    "receptor_nombre",
    "receptor_nif",
)
_DECIMAL_FIELDS: tuple[str, ...] = ("irpf_cuota", "total")


class EngineError(RuntimeError):
    """Fallo recuperable de un motor (red, respuesta inválida, formato inesperado).

    El bench lo captura y lo refleja como ``EngineResult.error`` del caso, sin abortar la
    comparación del resto de motores ni facturas.
    """


@runtime_checkable
class OcrEngine(Protocol):
    """Contrato de un motor del bench: extrae los campos de una factura.

    `name` identifica el motor en el informe (p. ej. ``"azure-openai"``). `extract` nunca
    debe lanzar por errores del servicio: los envuelve en ``EngineResult.error`` para que un
    motor caído no tumbe el bench completo.
    """

    name: str

    def extract(self, image_path: Path) -> EngineResult: ...


def encode_image(image_path: Path) -> tuple[str, str]:
    """Devuelve ``(base64, mime)`` de la imagen. Lanza EngineError si el formato no es imagen.

    El PDF no se sube directamente a los motores de visión: requiere rasterizado previo a PNG,
    que se aborda en una tarea aparte (ver issue de rasterización de PDF). Aquí se rechaza con
    un mensaje claro para que el bench lo registre como caso no soportado por este motor.
    """
    suffix = image_path.suffix.lower()
    if suffix == ".pdf":
        raise EngineError(
            f"{image_path.name}: PDF no soportado por visión; requiere rasterizado previo a PNG"
        )
    mime = _MIME_BY_SUFFIX.get(suffix)
    if mime is None:
        raise EngineError(f"{image_path.name}: extensión de imagen no soportada ({suffix!r})")
    try:
        data = image_path.read_bytes()
    except OSError as exc:
        raise EngineError(f"{image_path.name}: no se pudo leer la imagen ({exc})") from exc
    return base64.b64encode(data).decode("ascii"), mime


# Prompt de sistema: español (dominio), estricto con la anti-alucinación y con el foco del plan
# en los campos más críticos y propensos a error (NIF de las partes, fecha e importe total).
_SYSTEM_PROMPT = (
    "Eres un extractor de datos de facturas españolas. Devuelves EXCLUSIVAMENTE un objeto JSON "
    "válido, sin texto adicional ni vallas de código. Reglas:\n"
    "- Si un dato no aparece o no es legible con certeza, su valor es null. NUNCA inventes ni "
    "deduzcas un valor que no esté escrito.\n"
    "- Presta especial atención a los campos más críticos y que más fallan: el NIF/CIF de emisor "
    "y receptor, la fecha y el importe total.\n"
    "- Los importes son números decimales con punto (sin símbolo de moneda ni separador de "
    "miles). La fecha en formato ISO AAAA-MM-DD.\n"
    "Esquema exacto del JSON:\n"
    "{\n"
    '  "numero": string|null,\n'
    '  "fecha": string|null,            // AAAA-MM-DD\n'
    '  "emisor_nombre": string|null,\n'
    '  "emisor_nif": string|null,\n'
    '  "receptor_nombre": string|null,\n'
    '  "receptor_nif": string|null,\n'
    '  "tramos": [ { "base": number, "iva_pct": number, "cuota": number } ],\n'
    '  "irpf_cuota": number|null,\n'
    '  "total": number|null\n'
    "}"
)

_USER_PROMPT = "Extrae los campos de esta factura siguiendo el esquema y las reglas."


def build_extraction_messages(image_b64: str, mime: str) -> list[dict[str, object]]:
    """Construye los `messages` de chat-visión (estilo OpenAI) para extraer la factura."""
    data_uri = f"data:{mime};base64,{image_b64}"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _USER_PROMPT},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        },
    ]


def _strip_code_fences(text: str) -> str:
    """Quita vallas ```` ```json ... ``` ```` si el modelo las añade pese al prompt."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped[3:]
    if body[:4].lower() == "json":
        body = body[4:]
    if body.endswith("```"):
        body = body[:-3]
    return body.strip()


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_decimal(value: object, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise EngineError(f"campo '{field_name}' no es un número válido: {value!r}") from exc


def _parse_tramos(raw: object) -> tuple[TaxLine, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise EngineError("'tramos' debe ser una lista")
    tramos: list[TaxLine] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise EngineError(f"tramo #{i} debe ser un objeto")
        base = _opt_decimal(item.get("base"), field_name=f"tramos[{i}].base")
        iva_pct = _opt_decimal(item.get("iva_pct"), field_name=f"tramos[{i}].iva_pct")
        cuota = _opt_decimal(item.get("cuota"), field_name=f"tramos[{i}].cuota")
        # Un tramo solo es válido si trae sus tres números; si el modelo deja huecos, se
        # descarta el tramo (no se inventan ceros que falsearían el cuadre aritmético).
        if base is None or iva_pct is None or cuota is None:
            continue
        tramos.append(TaxLine(base=base, iva_pct=iva_pct, cuota=cuota))
    return tuple(tramos)


def parse_invoice_json(content: str) -> InvoiceFields:
    """Convierte la respuesta JSON del modelo en `InvoiceFields`.

    Tolera vallas de código y campos ausentes (que pasan a ``None``). Lanza :class:`EngineError`
    si el contenido no es un objeto JSON o si un número está malformado.
    """
    text = _strip_code_fences(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EngineError(f"respuesta no es JSON válido: {exc}") from exc
    if not isinstance(data, dict):
        raise EngineError("la respuesta JSON debe ser un objeto")

    str_values = {name: _opt_str(data.get(name)) for name in _STR_FIELDS}
    decimal_values = {
        name: _opt_decimal(data.get(name), field_name=name) for name in _DECIMAL_FIELDS
    }
    return InvoiceFields(
        numero=str_values["numero"],
        fecha=str_values["fecha"],
        emisor_nombre=str_values["emisor_nombre"],
        emisor_nif=str_values["emisor_nif"],
        receptor_nombre=str_values["receptor_nombre"],
        receptor_nif=str_values["receptor_nif"],
        tramos=_parse_tramos(data.get("tramos")),
        irpf_cuota=decimal_values["irpf_cuota"],
        total=decimal_values["total"],
    )
