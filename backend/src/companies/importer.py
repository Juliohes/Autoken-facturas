"""Importador del Excel de empresas (`.xlsx`): parseo y carga en bloque de la cartera (S1.5).

Pieza propia del contexto `companies`, separada del CRUD: aquí vive el parseo del Excel con
`openpyxl` y la orquestación de la importación (validar cada fila, crear las válidas, omitir las
duplicadas y componer el informe). Reutiliza las reglas de dominio (`service.validated_cif`), la
persistencia (`repository`) y la traza (`shared.audit`).

Contrato de importación (spec S1.5):
- **Nivel de fila**: todo-o-nada. Una fila entra solo si tiene nombre y un CIF/NIF válido; si no, se
  rechaza entera y se reporta (número de fila 1-based, incluyendo la cabecera, + motivo).
- **Nivel de fichero**: éxito parcial. Las válidas entran; las duplicadas (CIF ya existente) se
  omiten (no son error) y se reportan; re-importar es idempotente.
- Fichero no-`.xlsx` o sin las columnas `Nombre`/`CIF/NIF` -> `MalformedFile` (400 controlado).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from uuid import UUID
from zipfile import BadZipFile

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from companies import repository, service
from companies.service import CompanyError, InvalidTaxId, is_cif_unique_violation
from companies.service import persist_new_company as _persist_new_company

_NAME_HEADER = "Nombre"
_CIF_HEADER = "CIF/NIF"


class MalformedFile(CompanyError):
    """El fichero no es un `.xlsx` legible o le faltan las columnas requeridas (-> 400).

    Hereda de `CompanyError` (raíz del dominio) para permitir un `except CompanyError` uniforme.
    """


@dataclass(frozen=True)
class InvalidRow:
    """Fila rechazada por dominio: su número (1-based) y el motivo del rechazo."""

    row: int
    reason: str


@dataclass(frozen=True)
class DuplicateRow:
    """Fila omitida por CIF ya existente: su número (1-based) y el CIF tal como venía el Excel."""

    row: int
    cif: str


@dataclass
class ImportReport:
    """Resultado de una importación: creadas, filas inválidas, duplicadas omitidas y truncado.

    `invalid` = filas rechazadas por dominio; `duplicates` = filas cuyo CIF ya existía, omitidas sin
    machacar la existente. `row` es el número de fila 1-based del Excel (la cabecera es la fila 1).
    `truncated` indica que el fichero superó el tope de filas y el resto no se procesó.
    """

    created: int = 0
    invalid: list[InvalidRow] = field(default_factory=list)
    duplicates: list[DuplicateRow] = field(default_factory=list)
    truncated: bool = False


@dataclass(frozen=True)
class _ParsedRow:
    """Fila cruda del Excel: su número (1-based, cabecera incluida) y los textos de sus celdas."""

    number: int
    name: str
    cif: str


def _cell_text(value: object) -> str:
    """Texto normalizado de una celda (tolera `None`, números y espacios sobrantes)."""
    if value is None:
        return ""
    return str(value).strip()


def _parse_rows(content: bytes, *, max_rows: int) -> tuple[list[_ParsedRow], bool]:
    """Parsea el `.xlsx` y devuelve `(filas_de_datos, truncado)`; `MalformedFile` si no es válido.

    Exige que la cabecera contenga las columnas `Nombre` y `CIF/NIF` (en cualquier orden). Un
    fichero que no es un Excel (o corrupto) o sin esas columnas se traduce a `MalformedFile` para
    que el router responda 400 en vez de un 500.

    Itera las filas de forma perezosa (openpyxl `read_only`) y corta al llegar a `max_rows` filas
    de datos: así un fichero manipulado con millones de filas no materializa toda la hoja en
    memoria. `truncado=True` señala que había más filas de las procesadas.
    """
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile) as exc:
        raise MalformedFile("El fichero no es un Excel (.xlsx) válido") from exc

    try:
        sheet = workbook.active
        if sheet is None:
            raise MalformedFile("El Excel no tiene ninguna hoja")
        rows_iter = sheet.iter_rows(values_only=True)

        header_row = next(rows_iter, None)
        if header_row is None:
            raise MalformedFile("El Excel está vacío (sin cabecera)")
        header = [_cell_text(cell) for cell in header_row]
        try:
            name_idx = header.index(_NAME_HEADER)
            cif_idx = header.index(_CIF_HEADER)
        except ValueError as exc:
            raise MalformedFile(
                f"Faltan las columnas requeridas '{_NAME_HEADER}' y '{_CIF_HEADER}'"
            ) from exc

        parsed: list[_ParsedRow] = []
        truncated = False
        for number, row in enumerate(rows_iter, start=2):  # la cabecera es la fila 1
            name = _cell_text(row[name_idx]) if name_idx < len(row) else ""
            cif = _cell_text(row[cif_idx]) if cif_idx < len(row) else ""
            if not name and not cif:
                continue  # fila en blanco: se ignora (no cuenta como inválida)
            if len(parsed) >= max_rows:
                truncated = True
                break
            parsed.append(_ParsedRow(number=number, name=name, cif=cif))
    finally:
        workbook.close()
    return parsed, truncated


async def import_companies(
    session: AsyncSession, *, actor_id: UUID, content: bytes, max_rows: int
) -> ImportReport:
    """Importa el Excel: crea las filas válidas y no duplicadas y devuelve el informe.

    Las duplicadas se resuelven contra los CIF ya presentes en el tenant y contra los creados en
    esta misma importación (idempotente al re-importar). Cada empresa creada deja una entrada
    `company.create` en el audit log. El fichero se corta a `max_rows` filas de datos (guardarraíl
    anti-DoS): el resto no se procesa y se marca `truncated`.

    Cada INSERT de fila corre en su propio SAVEPOINT (`begin_nested`): si una fila viola el UNIQUE
    `(tenant_id, cif)` (p. ej. una carrera que esquiva el pre-check), se revierte solo esa fila —se
    reporta como duplicada— y la importación continúa, preservando el éxito parcial (C11).
    """
    parsed, truncated = _parse_rows(content, max_rows=max_rows)
    report = ImportReport(truncated=truncated)
    seen = await repository.existing_cifs(session)

    for row in parsed:
        if not row.name:
            report.invalid.append(InvalidRow(row=row.number, reason="Falta el nombre"))
            continue
        if not row.cif:
            report.invalid.append(InvalidRow(row=row.number, reason="Falta el CIF/NIF"))
            continue
        try:
            canonical = service.validated_cif(row.cif)
        except InvalidTaxId as exc:
            report.invalid.append(InvalidRow(row=row.number, reason=exc.reason))
            continue
        if canonical in seen:  # fast-path: CIF ya conocido (del tenant o de esta importación)
            report.duplicates.append(DuplicateRow(row=row.number, cif=row.cif))
            continue

        try:
            async with session.begin_nested():
                await _persist_new_company(
                    session, actor_id=actor_id, name=row.name, canonical_cif=canonical
                )
        except IntegrityError as exc:
            if not is_cif_unique_violation(exc):
                raise  # otra violación de integridad no se enmascara como duplicado
            report.duplicates.append(DuplicateRow(row=row.number, cif=row.cif))
            continue
        seen.add(canonical)
        report.created += 1
    return report
