"""Carga del dataset de evaluación: facturas reales + ground truth anotado a mano (tarea 1.1).

Cada caso del dataset es una factura (imagen o PDF) acompañada de un fichero `*.gt.json` con
los valores correctos anotados por una persona. Este módulo lee esos ficheros y los convierte
al modelo `InvoiceFields`, validando de paso que el JSON está bien formado para que un error
de anotación se detecte aquí y no a mitad del bench.

Formato del fichero `<id>.gt.json` (ver docs/ocr-eval/README.md):

    {
      "id": "setex-0001",
      "imagen": "setex-0001.pdf",
      "dificultad": "facil|media|dificil",
      "notas": "borrosa / multi-tramo / con IRPF ...",
      "campos": {
        "numero": "FRA-2026-001",
        "fecha": "2026-03-14",
        "emisor_nombre": "Acme S.L.",
        "emisor_nif": "B12345678",
        "receptor_nombre": "Setex ...",
        "receptor_nif": "B87654321",
        "tramos": [{"base": "100.00", "iva_pct": "21", "cuota": "21.00"}],
        "irpf_cuota": "0",
        "total": "121.00"
      }
    }
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ocr.bench.schema import InvoiceFields, TaxLine

GROUND_TRUTH_SUFFIX = ".gt.json"


class DatasetError(ValueError):
    """Error de formato o contenido en un fichero de ground truth."""


@dataclass(frozen=True)
class DatasetCase:
    """Un caso del dataset: la imagen a procesar y sus campos correctos."""

    id: str
    image_path: Path
    truth: InvoiceFields
    difficulty: str = "media"
    notes: str = ""


def _to_decimal(value: object, *, field_name: str, case_id: str) -> Decimal:
    """Convierte un valor del JSON a Decimal, aceptando string o número."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise DatasetError(
            f"[{case_id}] campo '{field_name}' no es un número válido: {value!r}"
        ) from exc


def _parse_tramos(raw: object, *, case_id: str) -> tuple[TaxLine, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise DatasetError(f"[{case_id}] 'tramos' debe ser una lista")
    tramos: list[TaxLine] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DatasetError(f"[{case_id}] tramo #{i} debe ser un objeto")
        tramos.append(
            TaxLine(
                base=_to_decimal(item.get("base"), field_name=f"tramos[{i}].base", case_id=case_id),
                iva_pct=_to_decimal(
                    item.get("iva_pct"), field_name=f"tramos[{i}].iva_pct", case_id=case_id
                ),
                cuota=_to_decimal(
                    item.get("cuota"), field_name=f"tramos[{i}].cuota", case_id=case_id
                ),
            )
        )
    return tuple(tramos)


def _parse_fields(campos: dict[str, object], *, case_id: str) -> InvoiceFields:
    def opt_decimal(key: str) -> Decimal | None:
        value = campos.get(key)
        return None if value is None else _to_decimal(value, field_name=key, case_id=case_id)

    def opt_str(key: str) -> str | None:
        value = campos.get(key)
        return None if value is None else str(value)

    return InvoiceFields(
        numero=opt_str("numero"),
        fecha=opt_str("fecha"),
        emisor_nombre=opt_str("emisor_nombre"),
        emisor_nif=opt_str("emisor_nif"),
        receptor_nombre=opt_str("receptor_nombre"),
        receptor_nif=opt_str("receptor_nif"),
        tramos=_parse_tramos(campos.get("tramos"), case_id=case_id),
        irpf_cuota=opt_decimal("irpf_cuota"),
        total=opt_decimal("total"),
    )


def load_case(gt_path: Path) -> DatasetCase:
    """Carga y valida un único fichero de ground truth."""
    try:
        data = json.loads(gt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{gt_path.name}: JSON inválido ({exc})") from exc
    if not isinstance(data, dict):
        raise DatasetError(f"{gt_path.name}: la raíz debe ser un objeto JSON")

    case_id = str(data.get("id") or gt_path.name.removesuffix(GROUND_TRUTH_SUFFIX))
    campos = data.get("campos")
    if not isinstance(campos, dict):
        raise DatasetError(f"[{case_id}] falta el objeto 'campos'")

    image_name = data.get("imagen")
    image_path = gt_path.parent / str(image_name) if image_name else gt_path

    return DatasetCase(
        id=case_id,
        image_path=image_path,
        truth=_parse_fields(campos, case_id=case_id),
        difficulty=str(data.get("dificultad", "media")),
        notes=str(data.get("notas", "")),
    )


def iter_cases(dataset_dir: Path) -> Iterator[DatasetCase]:
    """Itera los casos del dataset en orden estable (por nombre de fichero)."""
    for gt_path in sorted(dataset_dir.glob(f"*{GROUND_TRUTH_SUFFIX}")):
        yield load_case(gt_path)


def load_dataset(dataset_dir: Path) -> list[DatasetCase]:
    """Carga todos los casos `*.gt.json` de un directorio."""
    if not dataset_dir.is_dir():
        raise DatasetError(f"El directorio del dataset no existe: {dataset_dir}")
    return list(iter_cases(dataset_dir))
