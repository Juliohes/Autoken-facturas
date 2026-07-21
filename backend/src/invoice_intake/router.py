"""Endpoints HTTP del intake seguro: `POST /api/v1/uploads` (S2.1) y
`GET /api/v1/uploads/{file_id}/download-url` (S2.7).

Capa HTTP **fina**: autentica y autoriza (portero de roles + pertenencia a la empresa), lee el
fichero de forma acotada (guardarraíl de tamaño), y traduce el resultado o la excepción de dominio
de `invoice_intake.service` a la respuesta HTTP. No contiene SQL ni reglas de negocio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from identity.authz import require_roles
from identity.dependencies import AuthContext
from invoice_intake import scanner, service, storage
from shared.config import get_settings
from tenancy.constants import Role

router = APIRouter(prefix="/uploads", tags=["intake"])

# Identidad autenticada autorizada a subir: empleado (`user`) o administrador de la asesoría
# (`tenant_admin`). La pertenencia fina a la empresa destino la comprueba el servicio (C10).
Uploader = Annotated[AuthContext, Depends(require_roles(Role.USER, Role.TENANT_ADMIN))]

# Mismo conjunto de roles que `Uploader`; nombre propio porque descargar no es "subir" (S2.7).
Downloader = Uploader


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

    max_bytes = get_settings().max_upload_bytes
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
        )
    except service.EmptyFile as exc:
        raise HTTPException(status_code=422, detail="El fichero está vacío") from exc
    except service.UnsupportedMediaType as exc:
        raise HTTPException(status_code=415, detail="Tipo de fichero no admitido") from exc
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
    )


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
            identity.session, tenant_id=identity.tenant_id, file_id=file_id
        )
    except service.FileForbidden as exc:
        raise HTTPException(
            status_code=403, detail="No perteneces a la empresa del fichero"
        ) from exc
    except service.FileNotVisible as exc:
        raise HTTPException(status_code=404, detail="Fichero no encontrado") from exc
    except storage.StorageUnavailable as exc:
        raise HTTPException(
            status_code=503, detail="Almacenamiento no disponible, reintenta"
        ) from exc
    return DownloadUrlOut(url=url, expires_in=service.DOWNLOAD_URL_TTL_SECONDS)
