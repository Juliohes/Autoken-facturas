"""Acceso a datos del intake (S2.1): el SQL de `uploaded_files` vive aquí, no en el router/servicio.

La sesión llega ya abierta en el contexto de aislamiento del tenant (S1.1): la RLS decide qué filas
se ven y se escriben. El `tenant_id` de la escritura NO viaja por parámetro: se toma de
`app.tenant_id` (la misma fuente que la RLS), de modo que ninguna fila puede crearse fuera del
tenant de la petición. `insert_uploaded_file` es una función de módulo a propósito, para que los
tests inyecten un fallo de registro con `monkeypatch.setattr(repository, "insert_uploaded_file")`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_intake.constants import FileStatus
from shared.integrity import violates_unique_constraint

# `tenant_id` de la escritura derivado del contexto de la sesión (coherente con la RLS).
_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# Nombre de los UNIQUE por empresa+quien sube: red última de la no-duplicación privada, resistente a
# concurrencia (C14). Traduce su violación a un 409 sin revelar el id de un compañero.
_DUPLICATE_CONSTRAINTS = frozenset(
    {
        "uploaded_files_company_uploader_sha256_unique",
        "uploaded_file_pages_company_uploader_sha256_unique",
        "uploaded_file_document_uploader_sha256_unique",
    }
)


@dataclass(frozen=True)
class UploadedFileRecord:
    """Fila de `uploaded_files` recién creada (datos para la respuesta 201)."""

    id: UUID
    company_id: UUID
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    scan_status: str
    created_at: datetime


@dataclass(frozen=True)
class UploadedFileContext:
    """Contexto mínimo de un fichero de intake para autorizar/confirmar (S2.5): empresa + estado.

    `uploaded_by` (2026-08-02): quién lo subió, para el segundo nivel de autorización de
    `authorize_file_access` (un `user` solo ve lo suyo, aunque comparta empresa con otro `user`).
    """

    id: UUID
    company_id: UUID
    status: str
    uploaded_by: UUID


@dataclass(frozen=True)
class UploadedFileLocation:
    """Ubicación del objeto de un fichero de intake en MinIO (bucket/clave) + su MIME real."""

    bucket: str
    key: str
    content_type: str


@dataclass(frozen=True)
class UploadedFilePageLocation:
    """Ubicación ordenada de una hoja de documento, incluida la raíz como página 1."""

    page_number: int
    bucket: str
    key: str
    content_type: str


async def get_file_location(session: AsyncSession, file_id: UUID) -> UploadedFileLocation | None:
    """Ubicación en MinIO de un fichero de intake, visible en el contexto (RLS), o `None`.

    La usa el worker OCR (S2.3) para localizar el objeto antes de descargarlo. El SQL de
    `uploaded_files` vive en su contexto (`invoice_intake`), no en `ocr`: la máquina de estados y la
    ubicación del fichero son dominio del intake.
    """
    row = (
        await session.execute(
            text(
                "SELECT storage_bucket, storage_key, content_type FROM uploaded_files "
                "WHERE id = :id"
            ),
            {"id": str(file_id)},
        )
    ).first()
    if row is None:
        return None
    return UploadedFileLocation(
        bucket=row.storage_bucket, key=row.storage_key, content_type=row.content_type
    )


async def get_document_pages(
    session: AsyncSession, root_uploaded_file_id: UUID
) -> list[UploadedFilePageLocation]:
    """Todas las hojas visibles de un documento, siempre en orden de captura."""
    rows = (
        await session.execute(
            text(
                "SELECT 1 AS page_number, storage_bucket, storage_key, content_type "
                "FROM uploaded_files WHERE id = :id "
                "UNION ALL "
                "SELECT page_number, storage_bucket, storage_key, content_type "
                "FROM uploaded_file_pages WHERE root_uploaded_file_id = :id "
                "ORDER BY page_number"
            ),
            {"id": str(root_uploaded_file_id)},
        )
    ).all()
    return [
        UploadedFilePageLocation(
            page_number=row.page_number,
            bucket=row.storage_bucket,
            key=row.storage_key,
            content_type=row.content_type,
        )
        for row in rows
    ]


async def get_page_location(
    session: AsyncSession, root_uploaded_file_id: UUID, page_number: int
) -> UploadedFileLocation | None:
    """Ubicación de una página adicional visible, sin revelar páginas de otro documento."""
    row = (
        await session.execute(
            text(
                "SELECT storage_bucket, storage_key, content_type FROM uploaded_file_pages "
                "WHERE root_uploaded_file_id = :id AND page_number = :page_number"
            ),
            {"id": str(root_uploaded_file_id), "page_number": page_number},
        )
    ).first()
    if row is None:
        return None
    return UploadedFileLocation(row.storage_bucket, row.storage_key, row.content_type)


async def get_file_context(session: AsyncSession, file_id: UUID) -> UploadedFileContext | None:
    """Empresa y estado de un fichero de intake visible en el contexto (RLS), o `None`.

    La usa `invoicing` (S2.5) para autorizar el review/confirm (distinguir 403 vs 404 según si el
    fichero es visible en el contexto de la petición o solo en asesoría) y para comprobar que el
    fichero está en un estado confirmable. El SQL de `uploaded_files` vive en su contexto
    (`invoice_intake`), no en `invoicing`.
    """
    row = (
        await session.execute(
            text("SELECT id, company_id, status, uploaded_by FROM uploaded_files WHERE id = :id"),
            {"id": str(file_id)},
        )
    ).first()
    if row is None:
        return None
    return UploadedFileContext(
        id=row.id, company_id=row.company_id, status=row.status, uploaded_by=row.uploaded_by
    )


async def transition_status(session: AsyncSession, file_id: UUID, status: FileStatus) -> None:
    """Transiciona `uploaded_files.status` del fichero del contexto (RLS acota e impide cruzar).

    Punto único de la transición de estado del intake. El rol runtime solo tiene `UPDATE (status)`
    en `uploaded_files` (migración 0005): no reescribe `sha256`/`storage_key` (append-only del
    resto). El worker OCR (S2.3) la invoca; nunca escribe SQL de `uploaded_files` desde `ocr`.
    """
    await session.execute(
        text("UPDATE uploaded_files SET status = :status WHERE id = :id"),
        {"status": status.value, "id": str(file_id)},
    )


async def delete_uploaded_file(session: AsyncSession, file_id: UUID) -> None:
    """Borra la fila de `uploaded_files` del contexto (purga de facturas de prueba, S3.5).

    Solo el borrado de la fila; el objeto en MinIO lo borra `service.delete_uploaded_file` (dueño
    del almacén). Nada llama a esta función directamente salvo ese caso: el resto del intake es
    append-only por diseño (spec S2.1 §4).
    """
    await session.execute(text("DELETE FROM uploaded_files WHERE id = :id"), {"id": str(file_id)})


def is_duplicate_violation(exc: IntegrityError) -> bool:
    """True si la integridad global de hash de un documento rechazó la escritura."""
    return any(violates_unique_constraint(exc, constraint) for constraint in _DUPLICATE_CONSTRAINTS)


async def company_exists(session: AsyncSession, company_id: UUID) -> bool:
    """True si la empresa existe y es visible en el contexto de la sesión (RLS del tenant).

    Sirve para distinguir 403 (empresa del propio tenant, sin pertenencia) de 404 (empresa que no
    existe en el contexto del que sube). Se consulta en contexto de asesoría (ve todo el tenant).
    """
    row = (
        await session.execute(
            text("SELECT 1 FROM companies WHERE id = :id LIMIT 1"),
            {"id": str(company_id)},
        )
    ).first()
    return row is not None


async def find_duplicate_id(
    session: AsyncSession, company_id: UUID, uploaded_by: UUID, sha256: str
) -> UUID | None:
    """Id propio existente con ese `(company_id, uploaded_by, sha256)`, o `None` si no hay.

    Alimenta el `duplicate_of` del 409 (dedup previo al antivirus y captura de la carrera).
    """
    row = (
        await session.execute(
            text(
                "SELECT id FROM uploaded_files WHERE company_id = :cid "
                "AND uploaded_by = :uploaded_by "
                "AND sha256 = :sha LIMIT 1"
            ),
            {"cid": str(company_id), "uploaded_by": str(uploaded_by), "sha": sha256},
        )
    ).first()
    return row.id if row is not None else None


async def find_document_duplicate_id(
    session: AsyncSession, company_id: UUID, uploaded_by: UUID, sha256: str
) -> UUID | None:
    """Documento propio que ya contiene esos bytes, incluso si están en una hoja secundaria."""
    row = (
        await session.execute(
            text(
                "SELECT id FROM uploaded_files WHERE company_id = :cid "
                "AND uploaded_by = :uploaded_by "
                "AND sha256 = :sha "
                "UNION ALL "
                "SELECT root_uploaded_file_id AS id FROM uploaded_file_pages "
                "WHERE company_id = :cid AND uploaded_by = :uploaded_by AND sha256 = :sha LIMIT 1"
            ),
            {"cid": str(company_id), "uploaded_by": str(uploaded_by), "sha": sha256},
        )
    ).first()
    return row.id if row is not None else None


async def insert_uploaded_file(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_by: UUID,
    storage_bucket: str,
    storage_key: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
) -> UploadedFileRecord:
    """Inserta el fichero de intake en el tenant del contexto (`pending_ocr` + `scan_status=clean`).

    `status`/`scan_status` NO se escriben aquí: los pone el `server_default` del esquema (migración
    0004 y modelo ORM), única fuente de esos estados iniciales; el `RETURNING` los devuelve. Puede
    lanzar `IntegrityError` del UNIQUE `(company_id, sha256)` si otra subida concurrente ganó la
    carrera (C14); el llamante la traduce a 409. Devuelve la fila creada.
    """
    row = (
        await session.execute(
            text(
                f"INSERT INTO uploaded_files "
                f"(tenant_id, company_id, uploaded_by, storage_bucket, storage_key, "
                f" content_type, size_bytes, sha256) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_by, :bucket, :key, "
                f" :content_type, :size_bytes, :sha256) "
                f"RETURNING id, company_id, content_type, size_bytes, sha256, "
                f"          status, scan_status, created_at"
            ),
            {
                "company_id": str(company_id),
                "uploaded_by": str(uploaded_by),
                "bucket": storage_bucket,
                "key": storage_key,
                "content_type": content_type,
                "size_bytes": size_bytes,
                "sha256": sha256,
            },
        )
    ).one()
    return UploadedFileRecord(
        id=row.id,
        company_id=row.company_id,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        status=row.status,
        scan_status=row.scan_status,
        created_at=row.created_at,
    )


async def insert_uploaded_file_page(
    session: AsyncSession,
    *,
    root_uploaded_file_id: UUID,
    company_id: UUID,
    uploaded_by: UUID,
    page_number: int,
    storage_bucket: str,
    storage_key: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
) -> None:
    """Inserta una hoja secundaria bajo la raíz ya creada, en la misma transacción."""
    await session.execute(
        text(
            "INSERT INTO uploaded_file_pages "
            "(root_uploaded_file_id, company_id, uploaded_by, page_number, storage_bucket, "
            "storage_key, "
            "content_type, size_bytes, sha256) VALUES "
            "(:root, :company_id, :uploaded_by, :page_number, :bucket, :key, :content_type, "
            ":size_bytes, :sha256)"
        ),
        {
            "root": str(root_uploaded_file_id),
            "company_id": str(company_id),
            "uploaded_by": str(uploaded_by),
            "page_number": page_number,
            "bucket": storage_bucket,
            "key": storage_key,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "sha256": sha256,
        },
    )
