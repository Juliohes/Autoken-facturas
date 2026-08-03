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

import structlog
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from invoice_intake import mime, repository, scanner, storage
from jobs import queue
from shared.audit import write_audit
from shared.db import tenant_session
from tenancy.constants import Role

logger = structlog.get_logger("invoice_intake")

# Traza de auditoría del intake (spec S2.1 C13): entidad y acción en constantes, no literales.
_AUDIT_ENTITY = "uploaded_file"
AUDIT_ACTION_UPLOAD = "intake.upload"

# Expiración fija y corta de la URL firmada de descarga (S2.7 spec §4): no configurable por el
# cliente. Pensada para que el navegador cargue la imagen al momento, no para compartir el enlace.
DOWNLOAD_URL_TTL_SECONDS = 300


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


class FileForbidden(IntakeError):
    """El fichero pertenece a otra empresa del propio tenant (-> 403)."""


class FileNotVisible(IntakeError):
    """El fichero no existe en el contexto del actor (inexistente u otro tenant) (-> 404)."""


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


async def authorize_file_access(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    file_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
) -> repository.UploadedFileContext:
    """Autoriza el acceso a un fichero ya existente por su visibilidad en el contexto (RLS).

    Misma pregunta ("¿es visible este fichero para el actor?") que usan
    `invoicing.service._load_file` (S2.5, review/confirm) y la descarga (S2.7): visible en la
    sesión de la petición -> autorizado; visible solo en el tenant (empresa hermana) ->
    `FileForbidden` (403); ni eso -> `FileNotVisible` (404, inexistente u otro tenant). Una sola
    implementación, en el módulo dueño de `uploaded_files`.

    Segundo nivel dentro de la propia empresa (2026-08-02, cumplimiento): un `user` (a diferencia
    de un `tenant_admin`, que revisa el trabajo de toda su asesoría) solo puede ver lo que subió él
    mismo, aunque comparta empresa con otro `user` y la RLS los deje pasar a ambos -> también
    `FileForbidden`. Julio lo pidió de forma explícita y expresa (ninguna foto/dato ajeno, nunca).
    """
    ctx = await repository.get_file_context(session, file_id)
    if ctx is not None:
        if actor_role == Role.USER and ctx.uploaded_by != actor_user_id:
            raise FileForbidden
        return ctx
    async with tenant_session(tenant_id) as sess:
        in_tenant = await repository.get_file_context(sess, file_id)
    if in_tenant is not None:
        raise FileForbidden
    raise FileNotVisible


async def get_download_url(
    session: AsyncSession, *, tenant_id: UUID, file_id: UUID, actor_user_id: UUID, actor_role: str
) -> str:
    """URL de descarga firmada del fichero (S2.7): autoriza, localiza y firma en una operación.

    Autorización idéntica a `authorize_file_access` (403/404 vía `FileForbidden`/`FileNotVisible`);
    solo si el fichero es visible se toca MinIO (spec §4: nunca se genera una URL de un fichero que
    el actor no puede ver). Puede lanzar `storage.StorageUnavailable` (-> 503) si MinIO falla al
    firmar.

    Solo funciona si el navegador puede alcanzar `MINIO_ENDPOINT` directamente (spec S2.7 §1): en
    el despliegue real de esta VPS, MinIO nunca se expone a Internet (solo la API, vía Traefik) —
    esta URL firmada apunta al hostname interno de Docker (`minio:9000`), inalcanzable desde fuera.
    `get_download_bytes` (2026-08-01) es el camino real que usa el botón "Ver" del panel.
    """
    ctx = await authorize_file_access(
        session,
        tenant_id=tenant_id,
        file_id=file_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    location = await repository.get_file_location(session, ctx.id)
    assert location is not None  # ctx ya confirmó que la fila existe en esta misma sesión
    return await asyncio.to_thread(
        storage.presigned_get_url, location.bucket, location.key, DOWNLOAD_URL_TTL_SECONDS
    )


async def get_download_bytes(
    session: AsyncSession, *, tenant_id: UUID, file_id: UUID, actor_user_id: UUID, actor_role: str
) -> tuple[bytes, str]:
    """Bytes + MIME real del fichero (2026-08-01): la API hace de proxy en vez de redirigir al
    navegador a una URL firmada de MinIO.

    MinIO nunca se expone públicamente en este proyecto (aislamiento por tenant, ADR-0015) — a
    diferencia de `get_download_url`, esto no depende de que el navegador pueda alcanzar MinIO
    directamente: los bytes pasan por la API, que sí es pública. Misma autorización que
    `get_download_url` (403/404).
    """
    ctx = await authorize_file_access(
        session,
        tenant_id=tenant_id,
        file_id=file_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    location = await repository.get_file_location(session, ctx.id)
    assert location is not None  # ctx ya confirmó que la fila existe en esta misma sesión
    content = await asyncio.to_thread(storage.get_object, location.bucket, location.key)
    return content, location.content_type


async def delete_uploaded_file_row(
    session: AsyncSession, file_id: UUID
) -> repository.UploadedFileLocation | None:
    """Borra la fila de `uploaded_files` y devuelve su ubicación en MinIO, sin tocar el objeto.

    Llamada desde `invoicing.service.purge_test_invoices` (S3.5, dueño de la orquestación), una vez
    por factura de prueba purgada. A propósito NO borra el objeto de MinIO aquí: eso implicaría una
    llamada de red por factura dentro de la MISMA transacción abierta de la petición, alargándola y
    reteniendo los locks de las filas ya borradas mientras dura la purga. `schedule_storage_cleanup`
    agenda esas bajas para DESPUÉS del commit. La ubicación se lee ANTES de borrar la fila: después
    ya no habría de dónde leerla.
    """
    location = await repository.get_file_location(session, file_id)
    await repository.delete_uploaded_file(session, file_id)
    return location


def schedule_storage_cleanup(
    session: AsyncSession, locations: list[repository.UploadedFileLocation]
) -> None:
    """Agenda el borrado best-effort de objetos de MinIO tras el commit de la petición (S3.5).

    Mismo patrón que `identity.registration._dispatch_after_commit` (S1.4, evento `after_commit` de
    SQLAlchemy): el borrado en Postgres ya es la fuente de verdad y ya se completó (regla de dominio
    4 de la spec S3.5); los objetos solo se tocan si la transacción confirma de verdad, y fuera de
    sus locks. Un fallo al borrar un objeto se avisa (log), nunca en silencio ni bloqueante: no hay
    nada que revertir, la fila ya no existe.
    """
    if not locations:
        return

    def _cleanup(_sync_session: Session) -> None:
        for location in locations:
            try:
                storage.remove_object(location.bucket, location.key)
            except storage.StorageUnavailable:
                logger.warning(
                    "invoice_intake.purge.storage_removal_failed",
                    bucket=location.bucket,
                    key=location.key,
                )

    event.listen(session.sync_session, "after_commit", _cleanup, once=True)


def schedule_bucket_cleanup(session: AsyncSession, bucket: str) -> None:
    """Agenda el borrado best-effort del bucket entero de un tenant tras el commit (S4.4).

    Mismo patrón que `schedule_storage_cleanup`: la purga de `tenants` en Postgres ya es la fuente
    de verdad y ya se completó (la fila ya no existe pase lo que pase con MinIO); un fallo al
    vaciar/borrar el bucket se avisa (log), nunca en silencio ni bloqueante.
    """

    def _cleanup(_sync_session: Session) -> None:
        try:
            storage.remove_bucket_recursive(bucket)
        except storage.StorageUnavailable:
            logger.warning("invoice_intake.tenant_purge.bucket_removal_failed", bucket=bucket)

    event.listen(session.sync_session, "after_commit", _cleanup, once=True)


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

    record = await _persist_or_compensate(
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
    # Encola el OCR del fichero (S2.3) best-effort: si el worker/Redis no está, el fichero se queda
    # en `pending_ocr` y se reprocesará; el encolado NUNCA hace fallar la subida ya persistida.
    await queue.enqueue_ocr(tenant_id, company_id, record.id)
    return record


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
