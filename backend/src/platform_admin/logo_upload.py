"""Subida del logo de un tenant como imagen (S4.1 ampliación, 2026-08-01, decisión de Julio).

Antes `logo_url` solo admitía pegar una URL ya alojada en otro sitio. Reutiliza el mismo pipeline
de validación que el intake de facturas (S2.1) — MIME real por número mágico (`invoice_intake.mime`)
y antivirus fail-closed (`invoice_intake.scanner`) — porque ninguno de los dos tiene acoplamiento
alguno a tenant/factura: son utilidades de bytes puras, no tendría sentido reimplementarlas aquí.

Al final almacena en `invoice_intake.storage.PLATFORM_ASSETS_BUCKET` (ver su docstring: el único
bucket de todo el proyecto de lectura pública, a propósito) y devuelve su URL pública.
"""

from __future__ import annotations

import hashlib

from invoice_intake import mime, scanner, storage
from invoice_intake.scanner import ScanInfected, ScannerUnavailable

# Solo imágenes rasterizadas (S2.1 ya reutiliza `filetype`, que las detecta por número mágico de
# forma fiable). Sin SVG a propósito: es texto/XML, no hay número mágico fiable que lo distinga de
# cualquier otro XML, y admitirlo sin más análisis abriría una vía de XSS si algún día se sirve o
# se referencia de un modo que lo interprete (spec: minimizar el tipo de dato aceptado).
ALLOWED_LOGO_MIME_TYPES = frozenset({"image/jpeg", "image/png"})
_EXTENSION_FOR_MIME = {"image/jpeg": ".jpg", "image/png": ".png"}

# Un logo no necesita más: tope bajo a propósito (vs. 15 MiB del intake de facturas), coherente con
# lo que realmente es esto (un icono/imagen de marca, no un documento).
MAX_LOGO_BYTES = 2 * 1024 * 1024


class LogoUploadError(Exception):
    """Raíz de los errores de subida de logo."""


class LogoEmpty(LogoUploadError):
    """Fichero vacío (-> 422)."""


class LogoTooLarge(LogoUploadError):
    """Supera `MAX_LOGO_BYTES` (-> 413)."""


class LogoTypeNotAllowed(LogoUploadError):
    """El MIME real no es jpeg/png (-> 415)."""


def upload_logo(content: bytes) -> str:
    """Valida y almacena una imagen de logo; devuelve su URL pública.

    Orden (mismo criterio que el intake, spec S2.1): vacío -> tamaño -> tipo real -> antivirus ->
    almacenar. `ScanInfected`/`ScannerUnavailable` (antivirus, S2.1) se propagan tal cual: el
    router las traduce a 422/503, igual que ya hace `invoice_intake.router`.
    """
    if len(content) == 0:
        raise LogoEmpty()
    if len(content) > MAX_LOGO_BYTES:
        raise LogoTooLarge()

    real_mime = mime.sniff_mime(content)
    if real_mime not in ALLOWED_LOGO_MIME_TYPES:
        raise LogoTypeNotAllowed()

    # ScanInfected / ScannerUnavailable se propagan sin capturar (fail-closed).
    scanner.scan(content)

    digest = hashlib.sha256(content).hexdigest()
    key = storage.asset_key_for(digest, _EXTENSION_FOR_MIME[real_mime])
    storage.ensure_public_asset_bucket()
    storage.put_object(storage.PLATFORM_ASSETS_BUCKET, key, content, len(content), real_mime)
    return storage.public_url_for(storage.PLATFORM_ASSETS_BUCKET, key)


__all__ = [
    "MAX_LOGO_BYTES",
    "LogoEmpty",
    "LogoTooLarge",
    "LogoTypeNotAllowed",
    "LogoUploadError",
    "ScanInfected",
    "ScannerUnavailable",
    "upload_logo",
]
