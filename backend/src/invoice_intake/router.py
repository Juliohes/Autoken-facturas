"""Endpoints HTTP del intake seguro: `POST /api/v1/uploads` (S2.1),
`GET /api/v1/uploads/{file_id}/download-url` (S2.7) y `GET /api/v1/uploads/{file_id}/image`
(2026-08-01, el camino real que usa el botón "Ver" del panel — ver su docstring).

Capa HTTP **fina**: autentica y autoriza (portero de roles + pertenencia a la empresa), lee el
fichero de forma acotada (guardarraíl de tamaño), y traduce el resultado o la excepción de dominio
de `invoice_intake.service` a la respuesta HTTP. No contiene SQL ni reglas de negocio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from identity.authz import require_roles
from identity.dependencies import AuthContext
from identity.ratelimit import intake_attempt_exceeds
from invoice_intake import scanner, service, storage
from invoice_intake.image import InvalidImage
from shared.config import get_settings
from shared.redis import get_redis
from tenancy.constants import Role

router = APIRouter(prefix="/uploads", tags=["intake"])

# Identidad autenticada autorizada a subir: empleado (`user`) o administrador de la asesoría
# (`tenant_admin`). La pertenencia fina a la empresa destino la comprueba el servicio (C10).
Uploader = Annotated[AuthContext, Depends(require_roles(Role.USER, Role.TENANT_ADMIN))]

# Mismo conjunto de roles que `Uploader`; nombre propio porque descargar no es "subir" (S2.7).
Downloader = Uploader

_BINARY_IMAGE_CONTENT: dict[str, Any] = {
    "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
    "image/png": {"schema": {"type": "string", "format": "binary"}},
}
_BINARY_IMAGE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Bytes binarios de la imagen original autorizada.",
        "content": _BINARY_IMAGE_CONTENT,
    }
}
_BINARY_DOCUMENT_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Bytes binarios del documento original autorizado.",
        "content": {
            **_BINARY_IMAGE_CONTENT,
            "application/pdf": {"schema": {"type": "string", "format": "binary"}},
        },
    }
}


class UploadOut(BaseModel):
    """Fichero de intake creado (respuesta 201)."""

    id: UUID
    company_id: UUID
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    scan_status: str
    created_at: datetime
    direction: Literal["recibida", "emitida"] | None


async def duplicate_upload_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Traduce `DuplicateUpload` a 409 con `duplicate_of` (id del original) en el cuerpo.

    Se registra como manejador de la app (ver `main.create_app`) para que la excepción PROPAGUE
    desde el endpoint: así la dependencia de identidad deshace la transacción de la petición
    (rollback tras la violación del UNIQUE de la carrera C14) antes de emitir la respuesta.
    """
    assert isinstance(exc, service.DuplicateUpload)
    return JSONResponse(status_code=409, content={"duplicate_of": str(exc.duplicate_of)})


@router.post("", status_code=201)
async def upload_file(
    identity: Uploader,
    file: UploadFile,
    company_id: Annotated[UUID, Form()],
    direction: Annotated[Literal["recibida", "emitida"] | None, Form()] = None,
) -> UploadOut:
    """Sube un fichero de factura a una empresa. Ver spec S2.1 para los códigos (201/4xx/503).

    Orden: pertenencia (403/404) -> tamaño (413) -> el servicio hace el resto (415/422/409/503/201).
    """
    # El servicio recibe primitivos (no el `AuthContext`, acoplado a FastAPI): el router es la única
    # capa que conoce la identidad HTTP y extrae de ella lo que la lógica de dominio necesita.
    member_company_id = identity.company.id if identity.company is not None else None
    try:
        await service.authorize_upload(
            tenant_id=identity.tenant_id,
            role=identity.role,
            member_company_id=member_company_id,
            company_id=company_id,
        )
    except service.NotAMember as exc:
        raise HTTPException(status_code=403, detail="No perteneces a la empresa destino") from exc
    except service.CompanyNotInContext as exc:
        raise HTTPException(status_code=404, detail="Empresa no encontrada") from exc

    settings = get_settings()
    if await intake_attempt_exceeds(
        get_redis(),
        kind="upload",
        tenant_id=str(identity.tenant_id),
        user_id=str(identity.user_id),
        max_per_user=settings.intake_uploads_per_user,
        max_per_tenant=settings.intake_uploads_per_tenant,
        window_seconds=settings.intake_rate_limit_window_seconds,
    ):
        raise HTTPException(status_code=429, detail="Demasiadas subidas. Espera un minuto.")

    max_bytes = settings.max_upload_bytes
    # Lectura acotada: como mucho `max_bytes + 1` bytes en memoria; si sobra, excede el tope (413),
    # sin materializar de golpe un fichero gigante ni caerse con un 500 (spec S2.1 C5).
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"El fichero supera el tamaño máximo ({max_bytes} bytes)"
        )

    try:
        record = await service.create_upload(
            session=identity.session,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            company_id=company_id,
            content=content,
            direction=direction,
        )
    except service.EmptyFile as exc:
        raise HTTPException(status_code=422, detail="El fichero está vacío") from exc
    except service.UnsupportedMediaType as exc:
        raise HTTPException(status_code=415, detail="Tipo de fichero no admitido") from exc
    except InvalidImage as exc:
        raise HTTPException(
            status_code=422, detail="La imagen no es válida o supera el límite"
        ) from exc
    except scanner.ScanInfected as exc:
        raise HTTPException(status_code=422, detail="El fichero no supera el antivirus") from exc
    except scanner.ScannerUnavailable as exc:
        raise HTTPException(status_code=503, detail="Antivirus no disponible, reintenta") from exc
    except storage.StorageUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Almacenamiento no disponible, reintenta"
        ) from exc
    # `service.DuplicateUpload` NO se captura aquí: propaga al manejador de la app (409 con
    # `duplicate_of`) para que la dependencia deshaga antes la transacción de la petición.

    return UploadOut(
        id=record.id,
        company_id=record.company_id,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        status=record.status,
        scan_status=record.scan_status,
        created_at=record.created_at,
        direction=cast(Literal["recibida", "emitida"] | None, record.direction),
    )


@router.post("/batch", status_code=201)
async def upload_batch(
    identity: Uploader,
    files: list[UploadFile],
    company_id: Annotated[UUID, Form()],
    direction: Annotated[Literal["recibida", "emitida"], Form()],
) -> UploadOut:
    """Acepta de dos a cinco imágenes como un único documento multipágina (S6.12).

    La dirección se valida aquí porque forma parte del contrato de captura. La confirmación
    existente sigue siendo quien la persiste, igual que en una subida simple.
    """
    member_company_id = identity.company.id if identity.company is not None else None
    try:
        await service.authorize_upload(
            tenant_id=identity.tenant_id,
            role=identity.role,
            member_company_id=member_company_id,
            company_id=company_id,
        )
    except service.NotAMember as exc:
        raise HTTPException(status_code=403, detail="No perteneces a la empresa destino") from exc
    except service.CompanyNotInContext as exc:
        raise HTTPException(status_code=404, detail="Empresa no encontrada") from exc

    if not 2 <= len(files) <= 5:
        raise HTTPException(
            status_code=422, detail="Un documento requiere entre dos y cinco páginas"
        )
    settings = get_settings()
    if await intake_attempt_exceeds(
        get_redis(),
        kind="upload",
        tenant_id=str(identity.tenant_id),
        user_id=str(identity.user_id),
        max_per_user=settings.intake_uploads_per_user,
        max_per_tenant=settings.intake_uploads_per_tenant,
        window_seconds=settings.intake_rate_limit_window_seconds,
    ):
        raise HTTPException(status_code=429, detail="Demasiadas subidas. Espera un minuto.")
    max_bytes = settings.max_upload_bytes
    contents: list[bytes] = []
    for file in files:
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413, detail=f"El fichero supera el tamaño máximo ({max_bytes} bytes)"
            )
        contents.append(content)
    try:
        record = await service.create_upload_batch(
            session=identity.session,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            company_id=company_id,
            contents=contents,
            direction=direction,
        )
    except service.EmptyFile as exc:
        raise HTTPException(status_code=422, detail="El fichero está vacío") from exc
    except service.UnsupportedMediaType as exc:
        raise HTTPException(status_code=415, detail="Tipo de fichero no admitido") from exc
    except InvalidImage as exc:
        raise HTTPException(
            status_code=422, detail="La imagen no es válida o supera el límite"
        ) from exc
    except scanner.ScanInfected as exc:
        raise HTTPException(status_code=422, detail="El fichero no supera el antivirus") from exc
    except scanner.ScannerUnavailable as exc:
        raise HTTPException(status_code=503, detail="Antivirus no disponible, reintenta") from exc
    except storage.StorageUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Almacenamiento no disponible, reintenta"
        ) from exc
    return UploadOut(
        id=record.id,
        company_id=record.company_id,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        status=record.status,
        scan_status=record.scan_status,
        created_at=record.created_at,
        direction=cast(Literal["recibida", "emitida"] | None, record.direction),
    )


class OcrRetryOut(BaseModel):
    status: Literal["pending_ocr"]


@router.post("/{file_id}/retry-ocr", status_code=202)
async def retry_ocr(identity: Uploader, file_id: UUID) -> OcrRetryOut:
    """Reencola de forma autorizada una lectura que terminó en fallo, sin volver a subir bytes."""
    try:
        ctx = await service.prepare_ocr_retry(
            identity.session,
            tenant_id=identity.tenant_id,
            file_id=file_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
        )
    except (service.FileForbidden, service.FileNotVisible) as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except service.OcrRetryUnavailable as exc:
        raise HTTPException(
            status_code=409, detail="La lectura OCR no se puede reintentar"
        ) from exc

    settings = get_settings()
    if await intake_attempt_exceeds(
        get_redis(),
        kind="retry",
        tenant_id=str(identity.tenant_id),
        user_id=str(identity.user_id),
        max_per_user=settings.ocr_retries_per_user,
        max_per_tenant=settings.ocr_retries_per_tenant,
        window_seconds=settings.intake_rate_limit_window_seconds,
    ):
        raise HTTPException(status_code=429, detail="Demasiados reintentos OCR. Espera un minuto.")
    if not await service.retry_ocr(identity.session, file_id):
        raise HTTPException(status_code=409, detail="La lectura OCR no se puede reintentar")
    service._enqueue_ocr_after_commit(identity.session, identity.tenant_id, ctx.company_id, file_id)
    return OcrRetryOut(status="pending_ocr")


class DownloadUrlOut(BaseModel):
    """URL firmada de descarga de un fichero (respuesta 200, S2.7)."""

    url: str
    expires_in: int


@router.get("/{file_id}/download-url")
async def download_url(identity: Downloader, file_id: UUID) -> DownloadUrlOut:
    """URL firmada (5 min) para descargar un fichero de intake. Ver spec S2.7 para los códigos.

    Autorización idéntica a `review`/`confirm` (S2.5): 403 empresa hermana del propio tenant, 404
    otro tenant/inexistente. La descarga no depende del estado del fichero (spec S2.7 §5).
    """
    try:
        url = await service.get_download_url(
            identity.session,
            tenant_id=identity.tenant_id,
            file_id=file_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
        )
    except service.PrivateFileNotVisible as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except service.FileForbidden as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except service.FileNotVisible as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except storage.StorageUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Almacenamiento no disponible, reintenta"
        ) from exc
    return DownloadUrlOut(url=url, expires_in=service.DOWNLOAD_URL_TTL_SECONDS)


@router.get("/{file_id}/image", responses=_BINARY_DOCUMENT_RESPONSE)
async def download_image(identity: Downloader, file_id: UUID) -> Response:
    """Bytes reales del fichero de intake (2026-08-01), vía la API — no una redirección a MinIO.

    Reemplaza a `download-url` como camino real del botón "Ver" del panel: MinIO nunca se expone
    públicamente en este proyecto, así que una URL firmada de MinIO es inalcanzable desde el
    navegador del usuario en el despliegue real (ver docstring de `service.get_download_bytes`).
    Misma autorización que `download-url` (403/404).
    """
    try:
        content, content_type = await service.get_download_bytes(
            identity.session,
            tenant_id=identity.tenant_id,
            file_id=file_id,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
        )
    except service.PrivateFileNotVisible as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except service.FileForbidden as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except service.FileNotVisible as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except storage.StorageUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Almacenamiento no disponible, reintenta"
        ) from exc
    return Response(content=content, media_type=content_type)


@router.get("/{file_id}/pages/{page_number}/image", responses=_BINARY_IMAGE_RESPONSE)
async def download_page_image(identity: Downloader, file_id: UUID, page_number: int) -> Response:
    """Bytes de una hoja secundaria, con la misma privacidad por usuario que la raíz (S6.12)."""
    try:
        content, content_type = await service.get_page_download_bytes(
            identity.session,
            tenant_id=identity.tenant_id,
            root_file_id=file_id,
            page_number=page_number,
            actor_user_id=identity.user_id,
            actor_role=identity.role,
        )
    except (service.FileForbidden, service.FileNotVisible) as exc:
        # Para páginas, también la empresa hermana devuelve 404: una URL no debe ser un oráculo.
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except storage.StorageUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Almacenamiento no disponible, reintenta"
        ) from exc
    return Response(content=content, media_type=content_type)
