"""Lógica de dominio del intake seguro (S2.1): orquesta la subida de un fichero de factura.

El router HTTP es fino: traduce la petición a estas operaciones y sus excepciones de dominio a
códigos HTTP. Aquí vive el invariante "entero y verificado, o nada" (spec S2.1 §4) en el orden que
fija la spec: pertenencia -> MIME real -> SHA-256 -> dedup (antes del antivirus) -> antivirus ->
almacenar objeto -> insertar registro -> auditar. Cualquier fallo deshace lo hecho: sin objeto sin
registro y sin registro sin objeto (C12). La persistencia se delega en `repository`, el almacén en
`storage`, el antivirus en `scanner` y la traza en `shared.audit`.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_intake import mime, repository, scanner, storage
from shared.audit import write_audit
from shared.db import tenant_session
from tenancy.constants import Role

# Traza de auditoría del intake (spec S2.1 C13): entidad y acción en constantes, no literales.
_AUDIT_ENTITY = "uploaded_file"
AUDIT_ACTION_UPLOAD = "intake.upload"


class IntakeError(Exception):
    """Raíz de los errores de dominio del intake."""


class NotAMember(IntakeError):
    """El que sube no pertenece a la empresa destino (del propio tenant) (-> 403)."""


class CompanyNotInContext(IntakeError):
    """La empresa destino no existe en el contexto del que sube (inexistente u otro tenant)."""


class EmptyFile(IntakeError):
    """El fichero está vacío (0 bytes): no es una imagen/PDF válido (-> 422)."""


class UnsupportedMediaType(IntakeError):
    """El MIME real del fichero no está admitido (jpeg/png/pdf) (-> 415)."""


class DuplicateUpload(IntakeError):
    """Ya existe ese fichero en la empresa (mismo `(company_id, sha256)`) (-> 409)."""

    def __init__(self, duplicate_of: UUID) -> None:
        super().__init__(f"Fichero duplicado en la empresa (original {duplicate_of})")
        self.duplicate_of = duplicate_of


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def _company_in_tenant(tenant_id: UUID, company_id: UUID) -> bool:
    """¿Existe la empresa en el tenant? Se lee en contexto de asesoría (ve todo el tenant).

    Es una sesión propia (no la de la petición): la del `user` está acotada a su empresa por la RLS
    y no vería una empresa hermana, así que no podría distinguir 403 de 404.
    """
    async with tenant_session(tenant_id) as sess:
        return await repository.company_exists(sess, company_id)


async def authorize_upload(
    *, tenant_id: UUID, role: str, member_company_id: UUID | None, company_id: UUID
) -> None:
    """Autoriza la subida a `company_id` según la pertenencia (spec S2.1 C10).

    `member_company_id` es la empresa de la que el que sube es miembro (su única empresa activa,
    invariante 1-A) o `None` para un `tenant_admin` (contexto de asesoría).

    - `user`: solo a su empresa. A otra del propio tenant -> 403; a una que no existe en su tenant
      -> 404.
    - `tenant_admin`: a cualquier empresa **de su** asesoría; si no existe en su tenant -> 404.
    """
    if member_company_id is not None and member_company_id == company_id:
        return  # el `user` sube a su propia empresa (es miembro)

    exists = await _company_in_tenant(tenant_id, company_id)
    if role == Role.TENANT_ADMIN:
        if not exists:
            raise CompanyNotInContext
        return
    # `user` que no es miembro de la empresa destino
    if exists:
        raise NotAMember
    raise CompanyNotInContext


async def create_upload(
    *, session: AsyncSession, tenant_id: UUID, user_id: UUID, company_id: UUID, content: bytes
) -> repository.UploadedFileRecord:
    """Verifica y persiste el fichero de intake (o no deja nada). Devuelve la fila creada (201).

    Orden (spec S2.1 §3): vacío -> MIME real -> SHA-256 -> dedup -> antivirus -> almacenar ->
    insertar + auditar (en la MISMA transacción). El tipo lo decide SOLO el MIME real, nunca la
    cabecera declarada (C4). La autorización por pertenencia ya la comprobó `authorize_upload`.
    """
    if not content:
        raise EmptyFile

    real_mime = mime.sniff_mime(content)
    if not mime.is_allowed(real_mime):
        raise UnsupportedMediaType
    assert real_mime is not None  # `is_allowed(None)` es False: aquí el MIME está determinado

    sha256 = _sha256(content)
    bucket = storage.bucket_for(tenant_id)
    key = storage.key_for(company_id, sha256)

    # Dedup por empresa ANTES del antivirus (spec): si ya existe, ni se escanea ni se almacena.
    existing = await repository.find_duplicate_id(session, company_id, sha256)
    if existing is not None:
        raise DuplicateUpload(existing)

    # Antivirus (fail-closed): infectado -> ScanInfected (422); caído -> ScannerUnavailable (503).
    # Se usa el atributo de módulo (no se importa la función) para permitir el monkeypatch C7.
    await asyncio.to_thread(scanner.scan, content)

    # Almacenar el objeto ANTES de insertar el registro; un fallo aquí -> StorageUnavailable (503)
    # y sin fila (C12a). Se usa `storage.put_object` como atributo de módulo (monkeypatch C12a).
    await asyncio.to_thread(storage.put_object, bucket, key, content, len(content), real_mime)

    return await _persist_or_compensate(
        session=session,
        tenant_id=tenant_id,
        user_id=user_id,
        company_id=company_id,
        sha256=sha256,
        bucket=bucket,
        key=key,
        content_type=real_mime,
        size_bytes=len(content),
    )


async def _persist_or_compensate(
    *,
    session: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    company_id: UUID,
    sha256: str,
    bucket: str,
    key: str,
    content_type: str,
    size_bytes: int,
) -> repository.UploadedFileRecord:
    """Inserta el registro + la traza en la transacción de la petición; compensa si algo falla.

    - Violación del UNIQUE `(company_id, sha256)` (carrera concurrente, C14): el objeto en esa clave
      es el del ganador (misma clave, mismos bytes), así que NO se borra; se responde 409 con el id
      del original.
    - Cualquier otro fallo al registrar (C12b): se borra el objeto recién subido para no dejar un
      huérfano y se propaga (>= 500).
    """
    try:
        record = await repository.insert_uploaded_file(
            session,
            company_id=company_id,
            uploaded_by=user_id,
            storage_bucket=bucket,
            storage_key=key,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        await write_audit(
            session,
            actor_id=user_id,
            action=AUDIT_ACTION_UPLOAD,
            entity=_AUDIT_ENTITY,
            entity_id=record.id,
        )
        return record
    except IntegrityError as exc:
        if repository.is_duplicate_violation(exc):
            duplicate_of = await _resolve_duplicate(tenant_id, company_id, sha256)
            raise DuplicateUpload(duplicate_of) from exc
        await _remove_object_best_effort(bucket, key)
        raise
    except Exception:
        await _remove_object_best_effort(bucket, key)
        raise


async def _resolve_duplicate(tenant_id: UUID, company_id: UUID, sha256: str) -> UUID:
    """Id del original tras perder la carrera del UNIQUE (la transacción de la petición ya abortó).

    Se lee en una sesión nueva (la del ganador ya cometió): el original es visible. Si por una
    condición extrema no se encontrara, se propaga el fallo original (no se inventa un id).
    """
    async with tenant_session(tenant_id) as sess:
        duplicate_of = await repository.find_duplicate_id(sess, company_id, sha256)
    if duplicate_of is None:  # pragma: no cover - el ganador está cometido cuando saltó el UNIQUE
        raise RuntimeError("violación de unicidad sin fila original visible")
    return duplicate_of


async def _remove_object_best_effort(bucket: str, key: str) -> None:
    """Borra el objeto para no dejar huérfanos; si el borrado falla, no tapa el error original."""
    # Compensación best-effort: un fallo al borrar no debe enmascarar el error que la disparó.
    with contextlib.suppress(storage.StorageUnavailable):
        await asyncio.to_thread(storage.remove_object, bucket, key)
