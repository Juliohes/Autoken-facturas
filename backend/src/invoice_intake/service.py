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
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from invoice_intake import mime, repository, scanner, storage
from invoice_intake.image import validate_image
from jobs import eta_repository, queue
from ocr.eta import estimate_eta
from platform_admin import settings_repository
from shared.audit import write_audit
from shared.config import get_settings
from shared.db import tenant_session, tenant_statement_session
from shared.metrics import observe_upload_phase, page_count_bucket
from tenancy.constants import Role

logger = structlog.get_logger("invoice_intake")

# Traza de auditoría del intake (spec S2.1 C13): entidad y acción en constantes, no literales.
_AUDIT_ENTITY = "uploaded_file"
AUDIT_ACTION_UPLOAD = "intake.upload"
AUDIT_ACTION_DELETE_UNCONFIRMED = "intake.delete_unconfirmed"

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
    """Ya existe ese fichero para quien lo sube (mismo hash privado) (-> 409)."""

    def __init__(self, duplicate_of: UUID) -> None:
        super().__init__(f"Fichero duplicado en la empresa (original {duplicate_of})")
        self.duplicate_of = duplicate_of


class FileForbidden(IntakeError):
    """El fichero pertenece a otra empresa del propio tenant (-> 403)."""


class FileNotVisible(IntakeError):
    """El fichero no existe en el contexto del actor (inexistente u otro tenant) (-> 404)."""


class PrivateFileNotVisible(FileNotVisible):
    """Un compañero intenta acceder a un documento propio de otro `user` (-> 404)."""


class ConfirmedFile(IntakeError):
    """Una factura ya confirmada no admite borrado manual (-> 409)."""


class InvalidPageCount(IntakeError):
    """Un documento multipágina debe contener de dos a cinco imágenes (-> 422)."""


class OcrRetryUnavailable(IntakeError):
    """El documento no está en un estado fallido que se pueda reintentar (-> 409)."""


@dataclass(frozen=True)
class UploadedFileStatus:
    """Estado operativo mínimo de un fichero, sin PII ni ubicación del objeto (R-019)."""

    id: UUID
    status: str
    processing_stage: str | None
    created_at: datetime
    ocr_started_at: datetime | None
    ocr_finished_at: datetime | None
    eta_seconds_min: int | None
    eta_seconds_max: int | None


@dataclass(frozen=True)
class _PreparedUpload:
    content: bytes
    content_type: str
    sha256: str


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
            raise PrivateFileNotVisible
        return ctx
    async with tenant_session(tenant_id) as sess:
        in_tenant = await repository.get_file_context(sess, file_id)
    if in_tenant is not None:
        raise FileForbidden
    raise FileNotVisible


async def authorize_file_edit(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    file_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
) -> repository.UploadedFileContext:
    """Autoriza una operación editable, manteniendo el owner guard del borrador.

    Un `tenant_admin` puede leer pendientes ajenas para supervisarlas, pero no se convierte por ello
    en propietario de sus borradores ni puede usar el flujo editable de review/confirmación.
    """
    context = await authorize_file_access(
        session,
        tenant_id=tenant_id,
        file_id=file_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    if actor_role == Role.TENANT_ADMIN and context.uploaded_by != actor_user_id:
        raise FileForbidden
    return context


async def get_file_status(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    file_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
) -> UploadedFileStatus:
    """Devuelve el progreso de un fichero tras aplicar su autorización privada (R-019)."""
    context = await authorize_file_access(
        session,
        tenant_id=tenant_id,
        file_id=file_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    eta_min: int | None = None
    eta_max: int | None = None
    if context.status == "pending_ocr":
        try:
            pages = await repository.get_document_pages(session, file_id)
            policy = await settings_repository.get_ocr_policy(session)
            samples = await eta_repository.get_samples(
                engine=policy.primary_engine,
                model=policy.primary_model,
                page_count_bucket=page_count_bucket(len(pages)),
            )
            eta = estimate_eta(
                pending_ahead=await repository.count_ocr_ahead(
                    session, created_at=context.created_at
                ),
                effective_concurrency=get_settings().ocr_worker_max_jobs,
                processing_seconds=samples.processing_seconds,
                queue_wait_seconds=samples.queue_wait_seconds,
            )
            if eta is not None:
                eta_min, eta_max = eta.minimum_seconds, eta.maximum_seconds
        except Exception as exc:  # noqa: BLE001 - la ETA nunca bloquea el estado del upload
            logger.warning("upload_status.eta_unavailable", reason=type(exc).__name__)
    return UploadedFileStatus(
        id=context.id,
        status=context.status,
        processing_stage=context.processing_stage,
        created_at=context.created_at,
        ocr_started_at=context.ocr_started_at,
        ocr_finished_at=context.ocr_finished_at,
        eta_seconds_min=eta_min,
        eta_seconds_max=eta_max,
    )


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


async def get_page_download_bytes(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    root_file_id: UUID,
    page_number: int,
    actor_user_id: UUID,
    actor_role: str,
) -> tuple[bytes, str]:
    """Bytes de una hoja secundaria tras autorizar primero el documento raíz.

    La autorización queda anclada en la raíz, que conserva `uploaded_by`; una URL de página no
    permite a un compañero inferir que existe un documento ajeno.
    """
    await authorize_file_access(
        session,
        tenant_id=tenant_id,
        file_id=root_file_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    location = await repository.get_page_location(session, root_file_id, page_number)
    if location is None:
        raise FileNotVisible
    content = await asyncio.to_thread(storage.get_object, location.bucket, location.key)
    return content, location.content_type


async def prepare_ocr_retry(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    file_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
) -> repository.UploadedFileContext:
    """Autoriza un reintento sin revelar archivos ajenos y exige un fallo OCR real."""
    ctx = await authorize_file_edit(
        session,
        tenant_id=tenant_id,
        file_id=file_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    if ctx.status != "ocr_failed":
        raise OcrRetryUnavailable
    return ctx


async def retry_ocr(session: AsyncSession, file_id: UUID) -> bool:
    """Reabre atómicamente un fallo OCR para que el worker lo pueda reclamar otra vez."""
    return await repository.retry_ocr(session, file_id)


async def delete_uploaded_file_row(
    session: AsyncSession, file_id: UUID
) -> list[repository.UploadedFileLocation]:
    """Borra la raíz y devuelve las ubicaciones de todas sus páginas, sin tocar MinIO.

    Llamada desde `invoicing.service.purge_test_invoices` (S3.5, dueño de la orquestación), una vez
    por factura de prueba purgada. A propósito NO borra el objeto de MinIO aquí: eso implicaría una
    llamada de red por factura dentro de la MISMA transacción abierta de la petición, alargándola y
    reteniendo los locks de las filas ya borradas mientras dura la purga. `schedule_storage_cleanup`
    agenda esas bajas para DESPUÉS del commit. La ubicación se lee ANTES de borrar la fila: después
    ya no habría de dónde leerla.
    """
    pages = await repository.get_document_pages(session, file_id)
    await repository.delete_uploaded_file(session, file_id)
    return [
        repository.UploadedFileLocation(page.bucket, page.key, page.content_type) for page in pages
    ]


async def delete_unconfirmed_file(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    file_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
) -> None:
    """Elimina un documento pendiente del propietario y agenda la limpieza de sus objetos.

    La fila es la fuente de verdad: el almacenamiento se limpia solo después del commit y el worker
    OCR que pudiera estar ejecutándose pierde su fila antes de poder publicar un resultado.
    """
    context = await authorize_file_edit(
        session,
        tenant_id=tenant_id,
        file_id=file_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    if context.status == "confirmed":
        raise ConfirmedFile
    deleted, locations = await repository.delete_unconfirmed_file(session, file_id)
    if not deleted:
        raise ConfirmedFile
    await write_audit(
        session,
        actor_id=actor_user_id,
        action=AUDIT_ACTION_DELETE_UNCONFIRMED,
        entity=_AUDIT_ENTITY,
        entity_id=file_id,
    )
    schedule_storage_cleanup(session, locations)


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
    *,
    tenant_id: UUID,
    user_id: UUID,
    company_id: UUID,
    rls_company_id: UUID | None,
    content: bytes,
    direction: str | None = None,
    capture_session_id: UUID | None = None,
    capture_sequence: int | None = None,
) -> repository.UploadedFileRecord:
    """Verifica y persiste el fichero de intake (o no deja nada). Devuelve la fila creada (201).

    Orden (spec S2.1 §3): vacío -> MIME real -> SHA-256 -> dedup -> antivirus -> almacenar ->
    insertar + auditar (en la MISMA transacción). El tipo lo decide SOLO el MIME real, nunca la
    cabecera declarada (C4). La autorización por pertenencia ya la comprobó `authorize_upload`.
    """
    with observe_upload_phase("validation"):
        if not content:
            raise EmptyFile

        real_mime = mime.sniff_mime(content)
        if not mime.is_allowed(real_mime):
            raise UnsupportedMediaType
        assert real_mime is not None  # `is_allowed(None)` es False: aquí el MIME está determinado
        await asyncio.to_thread(
            validate_image, content, real_mime, max_pixels=get_settings().max_upload_image_pixels
        )
        sha256 = _sha256(content)
    bucket = storage.bucket_for(tenant_id)
    key = storage.key_for(company_id, uuid4())

    # Dedup privado ANTES del antivirus: un compañero puede subir los mismos bytes sin descubrir
    # este documento ni su id; quien ya lo subió no vuelve a escanearlo ni almacenarlo.
    with observe_upload_phase("deduplication"):
        async with tenant_statement_session() as duplicate_session:
            existing = await repository.find_duplicate_id(
                duplicate_session, tenant_id, company_id, user_id, sha256
            )
    if existing is not None:
        raise DuplicateUpload(existing)
    # Antivirus (fail-closed): infectado -> ScanInfected (422); caído -> ScannerUnavailable (503).
    # Se usa el atributo de módulo (no se importa la función) para permitir el monkeypatch C7.
    with observe_upload_phase("antivirus"):
        await asyncio.to_thread(scanner.scan, content)

    # Almacenar el objeto ANTES de insertar el registro; un fallo aquí -> StorageUnavailable (503)
    # y sin fila (C12a). Se usa `storage.put_object` como atributo de módulo (monkeypatch C12a).
    with observe_upload_phase("storage"):
        await asyncio.to_thread(storage.put_object, bucket, key, content, len(content), real_mime)

    with observe_upload_phase("persistence"):
        async with tenant_session(tenant_id, rls_company_id) as persist_session:
            record = await _persist_or_compensate(
                session=persist_session,
                tenant_id=tenant_id,
                user_id=user_id,
                company_id=company_id,
                sha256=sha256,
                bucket=bucket,
                key=key,
                content_type=real_mime,
                size_bytes=len(content),
                direction=direction,
                capture_session_id=capture_session_id,
                capture_sequence=capture_sequence,
            )
            _enqueue_ocr_after_commit(persist_session, tenant_id, company_id, record.id)
    return record


async def create_upload_batch(
    *,
    tenant_id: UUID,
    user_id: UUID,
    company_id: UUID,
    rls_company_id: UUID | None,
    contents: list[bytes],
    direction: str,
) -> repository.UploadedFileRecord:
    """Persiste de dos a cinco imágenes como un único documento raíz y sus hojas secundarias.

    Todas las validaciones y el antivirus terminan antes de tocar MinIO. Tras ello, cualquier fallo
    de almacenamiento o BD compensa todos los objetos ya escritos y no agenda ningún OCR parcial.
    """
    if not 2 <= len(contents) <= 5:
        raise InvalidPageCount

    prepared: list[_PreparedUpload] = []
    seen_hashes: set[str] = set()
    for content in contents:
        if not content:
            raise EmptyFile
        content_type = mime.sniff_mime(content)
        if content_type not in {"image/jpeg", "image/png"}:
            raise UnsupportedMediaType
        await asyncio.to_thread(
            validate_image, content, content_type, max_pixels=get_settings().max_upload_image_pixels
        )
        sha256 = _sha256(content)
        if sha256 in seen_hashes:
            raise DuplicateUpload(UUID(int=0))
        seen_hashes.add(sha256)
        prepared.append(_PreparedUpload(content, content_type, sha256))

    # Todas las páginas se deduplican antes de tocar ClamAV, para no escanear parcialmente un lote
    # que ya sabemos que no puede entrar. La sesión solo cubre estas lecturas RLS.
    async with tenant_session(tenant_id, rls_company_id) as duplicate_session:
        for page in prepared:
            duplicate_of = await repository.find_document_duplicate_id(
                duplicate_session, company_id, user_id, page.sha256
            )
            if duplicate_of is not None:
                raise DuplicateUpload(duplicate_of)

    for page in prepared:
        await asyncio.to_thread(scanner.scan, page.content)

    bucket = storage.bucket_for(tenant_id)
    locations = [
        repository.UploadedFileLocation(
            bucket=bucket,
            key=storage.key_for(company_id, uuid4()),
            content_type=page.content_type,
        )
        for page in prepared
    ]
    stored: list[repository.UploadedFileLocation] = []
    try:
        for page, location in zip(prepared, locations, strict=True):
            # Una llamada de red puede escribir el objeto y aun así fallar al recibir la respuesta.
            # La ubicación se registra antes para compensarla también en ese caso ambiguo.
            stored.append(location)
            await asyncio.to_thread(
                storage.put_object,
                location.bucket,
                location.key,
                page.content,
                len(page.content),
                page.content_type,
            )
        async with tenant_session(tenant_id, rls_company_id) as persist_session:
            first = prepared[0]
            root = await repository.insert_uploaded_file(
                persist_session,
                company_id=company_id,
                uploaded_by=user_id,
                storage_bucket=locations[0].bucket,
                storage_key=locations[0].key,
                content_type=first.content_type,
                size_bytes=len(first.content),
                sha256=first.sha256,
                direction=direction,
            )
            for page_number, (page, location) in enumerate(
                zip(prepared[1:], locations[1:], strict=True), start=2
            ):
                await repository.insert_uploaded_file_page(
                    persist_session,
                    root_uploaded_file_id=root.id,
                    company_id=company_id,
                    uploaded_by=user_id,
                    page_number=page_number,
                    storage_bucket=location.bucket,
                    storage_key=location.key,
                    content_type=page.content_type,
                    size_bytes=len(page.content),
                    sha256=page.sha256,
                )
            await write_audit(
                persist_session,
                actor_id=user_id,
                action=AUDIT_ACTION_UPLOAD,
                entity=_AUDIT_ENTITY,
                entity_id=root.id,
            )
            _enqueue_ocr_after_commit(persist_session, tenant_id, company_id, root.id)
    except IntegrityError as exc:
        await _remove_locations_best_effort(stored)
        if repository.is_duplicate_violation(exc):
            duplicate_of = await _resolve_batch_duplicate(tenant_id, company_id, user_id, prepared)
            raise DuplicateUpload(duplicate_of) from exc
        raise
    except Exception:
        await _remove_locations_best_effort(stored)
        raise

    return root


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
    direction: str | None,
    capture_session_id: UUID | None,
    capture_sequence: int | None,
) -> repository.UploadedFileRecord:
    """Inserta el registro + la traza en la transacción de la petición; compensa si algo falla.

    - Violación de la unicidad global `(company_id, sha256)` (carrera concurrente, C14): cada
      intento tiene su propia clave de objeto, así que se borra únicamente el objeto perdedor.
    - Cualquier otro fallo al registrar (C12b): se borra el objeto recién subido para no dejar un
      huérfano y se propaga (>= 500).
    """
    try:
        record = await repository.insert_uploaded_file_with_audit(
            session,
            company_id=company_id,
            uploaded_by=user_id,
            storage_bucket=bucket,
            storage_key=key,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            direction=direction,
            capture_session_id=capture_session_id,
            capture_sequence=capture_sequence,
        )
        return record
    except IntegrityError as exc:
        if repository.is_duplicate_violation(exc):
            duplicate_of = await _resolve_duplicate(tenant_id, company_id, user_id, sha256)
            await _remove_object_best_effort(bucket, key)
            raise DuplicateUpload(duplicate_of) from exc
        await _remove_object_best_effort(bucket, key)
        raise
    except Exception:
        await _remove_object_best_effort(bucket, key)
        raise


async def _resolve_duplicate(
    tenant_id: UUID, company_id: UUID, uploaded_by: UUID, sha256: str
) -> UUID:
    """Id del original tras perder la carrera del UNIQUE (la transacción de la petición ya abortó).

    Se lee en una sesión nueva (la del ganador ya cometió): el original es visible. Si por una
    condición extrema no se encontrara, se propaga el fallo original (no se inventa un id).
    """
    async with tenant_session(tenant_id) as sess:
        duplicate_of = await repository.find_document_duplicate_id(
            sess, company_id, uploaded_by, sha256
        )
    if duplicate_of is None:  # pragma: no cover - el ganador está cometido cuando saltó el UNIQUE
        raise RuntimeError("violación de unicidad sin fila original visible")
    return duplicate_of


async def _resolve_batch_duplicate(
    tenant_id: UUID, company_id: UUID, uploaded_by: UUID, prepared: list[_PreparedUpload]
) -> UUID:
    """Devuelve el documento propio que ganó una carrera de un lote."""
    async with tenant_session(tenant_id) as session:
        for page in prepared:
            duplicate_of = await repository.find_document_duplicate_id(
                session, company_id, uploaded_by, page.sha256
            )
            if duplicate_of is not None:
                return duplicate_of
    raise RuntimeError("violación de unicidad sin documento original visible")


def _enqueue_ocr_after_commit(
    session: AsyncSession, tenant_id: UUID, company_id: UUID, file_id: UUID
) -> None:
    """Publica OCR cuando la fila confirmada ya es visible para el worker."""

    async def dispatch() -> None:
        try:
            await queue.enqueue_ocr(tenant_id, company_id, file_id)
        except Exception:  # noqa: BLE001 - un post-commit no puede invalidar datos confirmados
            logger.exception("ocr.enqueue_unexpected_failure", uploaded_file_id=str(file_id))

    def after_commit(_sync_session: Session) -> None:
        try:
            asyncio.get_running_loop().create_task(dispatch())
        except RuntimeError:
            logger.exception("ocr.enqueue_dispatcher_unavailable", uploaded_file_id=str(file_id))

    event.listen(session.sync_session, "after_commit", after_commit, once=True)


async def _remove_object_best_effort(bucket: str, key: str) -> None:
    """Borra el objeto para no dejar huérfanos; si el borrado falla, no tapa el error original."""
    # Compensación best-effort: un fallo al borrar no debe enmascarar el error que la disparó.
    with contextlib.suppress(storage.StorageUnavailable):
        await asyncio.to_thread(storage.remove_object, bucket, key)


async def _remove_locations_best_effort(locations: list[repository.UploadedFileLocation]) -> None:
    """Compensa todos los objetos escritos por un lote, sin ocultar su error original."""
    for location in locations:
        await _remove_object_best_effort(location.bucket, location.key)
