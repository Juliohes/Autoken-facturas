"""Object storage del intake sobre MinIO (bucket por tenant como frontera de aislamiento, ADR-0015).

Funciones de módulo (síncronas) que el servicio invoca envueltas en un hilo (`asyncio.to_thread`)
para no bloquear el event loop. Son funciones de módulo a propósito, para que los tests inyecten el
"almacén caído" con `monkeypatch.setattr(storage, "put_object", ...)` (C12a).

Aislamiento: cada asesoría tiene su **propio bucket** `tenant-{tenant_id}`; la clave del objeto es
`{company_id}/{sha256}`. Un fallo del almacén se traduce a `StorageUnavailable` (-> 503), nunca a un
500 silencioso ni a un éxito falso (spec S2.1 §5, C12).
"""

from __future__ import annotations

import io
from datetime import timedelta
from functools import lru_cache

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from shared.config import get_settings

# Códigos de error de S3 que significan "el objeto/bucket no existe" (no es un fallo del almacén):
# `object_exists` los traduce a `False` en vez de propagar.
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "NoSuchObject"})

# Códigos de `make_bucket` que significan "el bucket ya existe" (éxito idempotente): dos subidas
# concurrentes de la PRIMERA factura de un tenant pueden lanzar dos `make_bucket` a la vez y la
# perdedora recibir uno de estos; no es un fallo del almacén (evita un 503 espurio que rompe C14).
_BUCKET_ALREADY_CODES = frozenset({"BucketAlreadyOwnedByYou", "BucketAlreadyExists"})


def bucket_for(tenant_id: object) -> str:
    """Nombre del bucket del tenant (frontera de aislamiento). Fuente única del formato."""
    return f"tenant-{tenant_id}"


def key_for(company_id: object, sha256: str) -> str:
    """Clave del objeto dentro del bucket del tenant. Fuente única del formato."""
    return f"{company_id}/{sha256}"


class StorageError(Exception):
    """Raíz de los errores del object storage del intake."""


class StorageUnavailable(StorageError):
    """El object storage no está disponible o falló la operación (503). Sin estado a medias."""


@lru_cache(maxsize=8)
def _client_for(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    """Cliente MinIO memoizado por configuración: se reutiliza entre peticiones (issue #67).

    El cliente MinIO es un envoltorio HTTP con pool de conexiones interno y sin estado por petición;
    reconstruirlo por cada operación era coste inútil. Se cachea por la tupla de configuración, de
    modo que un cambio de endpoint/credenciales (p. ej. entre entornos) construye uno nuevo.
    """
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def _client() -> Minio:
    """Cliente MinIO para la configuración actual (endpoint/credenciales por env en prod)."""
    settings = get_settings()
    return _client_for(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        settings.minio_secure,
    )


def _ensure_bucket(client: Minio, bucket: str) -> None:
    """Crea el bucket del tenant si aún no existe (idempotente, resistente a concurrencia).

    El `bucket_exists` + `make_bucket` es un check-then-act: dos subidas concurrentes de la primera
    factura de un tenant pueden entrar ambas al `make_bucket`; la perdedora recibe
    `BucketAlreadyOwnedByYou`/`BucketAlreadyExists`, que aquí se trata como éxito (ya está creado),
    no como fallo del almacén.
    """
    if client.bucket_exists(bucket):
        return
    try:
        client.make_bucket(bucket)
    except S3Error as exc:
        if exc.code not in _BUCKET_ALREADY_CODES:
            raise


def put_object(bucket: str, key: str, data: bytes, length: int, content_type: str) -> None:
    """Guarda `data` en `bucket/key` (crea el bucket si falta). Fallo -> `StorageUnavailable`."""
    client = _client()
    try:
        _ensure_bucket(client, bucket)
        client.put_object(bucket, key, io.BytesIO(data), length, content_type=content_type)
    except (Urllib3HTTPError, S3Error, ConnectionError, OSError) as exc:
        raise StorageUnavailable(f"No se pudo almacenar el objeto en MinIO: {exc}") from exc


def get_object(bucket: str, key: str) -> bytes:
    """Descarga el objeto `bucket/key` y devuelve sus bytes. Fallo/ausencia -> `StorageUnavailable`.

    Lo usa el worker OCR (S2.3) para leer la factura antes de extraerla. Un objeto borrado/corrupto
    o un almacén caído se traduce a `StorageUnavailable` (nunca bytes a medias ni fallo silencioso).
    """
    client = _client()
    try:
        response = client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except (Urllib3HTTPError, S3Error, ConnectionError, OSError) as exc:
        raise StorageUnavailable(f"No se pudo descargar el objeto de MinIO: {exc}") from exc


def presigned_get_url(bucket: str, key: str, expires_seconds: int) -> str:
    """URL de descarga firmada de `bucket/key`, válida `expires_seconds` (S2.7, ADR-0015).

    Único camino sancionado para que un cliente descargue el objeto sin credenciales de MinIO ni
    pasar el fichero entero por la API (spec S2.7 §1). Fallo -> `StorageUnavailable` (503), igual
    que el resto de operaciones del almacén.
    """
    client = _client()
    try:
        return client.presigned_get_object(bucket, key, expires=timedelta(seconds=expires_seconds))
    except (Urllib3HTTPError, S3Error, ConnectionError, OSError) as exc:
        raise StorageUnavailable(f"No se pudo generar la URL de descarga: {exc}") from exc


def object_exists(bucket: str, key: str) -> bool:
    """True si el objeto `bucket/key` existe. Inexistente -> False; almacén caído -> excepción."""
    client = _client()
    try:
        client.stat_object(bucket, key)
        return True
    except S3Error as exc:
        if exc.code in _NOT_FOUND_CODES:
            return False
        raise StorageUnavailable(f"Error al consultar el objeto en MinIO: {exc}") from exc
    except (Urllib3HTTPError, ConnectionError, OSError) as exc:
        raise StorageUnavailable(f"No se pudo consultar el objeto en MinIO: {exc}") from exc


def remove_object(bucket: str, key: str) -> None:
    """Borra el objeto `bucket/key` (compensación anti-huérfano si falla el registro)."""
    client = _client()
    try:
        client.remove_object(bucket, key)
    except (Urllib3HTTPError, S3Error, ConnectionError, OSError) as exc:
        raise StorageUnavailable(f"No se pudo borrar el objeto en MinIO: {exc}") from exc
